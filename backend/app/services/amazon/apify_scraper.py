# ============================================
# app/services/amazon/apify_scraper.py
# ============================================

import logging
import urllib.parse
from apify_client import ApifyClient

from app.config import settings
from .exceptions import ApifyError
from .helpers import extract_asin_from_url, validate_parent_asin, parse_price
from .inventory_apify import check_availability_apify

logger = logging.getLogger(__name__)

def fetch_product_from_apify(amazon_url: str) -> dict:
    if not settings.APIFY_API_TOKEN:
        logger.error("❌ APIFY_API_TOKEN is not configured.")
        raise ApifyError("Apify token not configured.")

    client = ApifyClient(settings.APIFY_API_TOKEN)
    actor_id = getattr(settings, "APIFY_ACTOR_ID", None) or "junglee/amazon-crawler"
    if actor_id == "apify/amazon-product-details-scraper":
        actor_id = "junglee/amazon-crawler"

    if actor_id in ("junglee/amazon-crawler", "BG3WDrGdteHgZgbPK"):
        run_input = {
            "categoryOrProductUrls": [{"url": amazon_url}],
            "scrapeProductDetails": True,
            "maxItemsPerStartUrl": 100,
            "proxyCountry": "AUTO_SELECT_PROXY_COUNTRY",
        }
    else:
        run_input = {
            "Params": [amazon_url],
            "scrapeProductDetails": True,
            "country": "US",
            "zipCode": "30024",
        }

    try:
        run = client.actor(actor_id).call(run_input=run_input)
        dataset_id = run.get("defaultDatasetId") if isinstance(run, dict) else run.default_dataset_id
        items = client.dataset(dataset_id).iterate_items()

        for item in items:
            if not isinstance(item, dict):
                continue

            asin = item.get("asin") or item.get("originalAsin") or extract_asin_from_url(amazon_url)
            
            # ✅ Parent ASIN extraction
            parent_asin = item.get("parent_asin") or item.get("parentAsin")
            if not parent_asin:
                raw_url = item.get("url", "") or item.get("product_url", "")
                if raw_url:
                    parsed = urllib.parse.urlparse(raw_url)
                    query_params = urllib.parse.parse_qs(parsed.query)
                    if "parent_asin" in query_params:
                        parent_asin = query_params["parent_asin"][0]
            if not parent_asin:
                apify_variants = item.get("variants") or []
                for v in apify_variants:
                    if isinstance(v, dict):
                        p = v.get("parent_asin") or v.get("parentAsin")
                        if p:
                            parent_asin = p
                            break
                            
            parent_asin = validate_parent_asin(parent_asin, asin)
            is_variation = bool(parent_asin)

            # ✅ Main product attributes (Color, Size)
            variant_attributes = []
            for attr in (item.get("variantAttributes") or item.get("variant_attributes") or []):
                if isinstance(attr, dict):
                    key = attr.get("key") or attr.get("name")
                    val = attr.get("value")
                    if key and val:
                        variant_attributes.append({"name": str(key).strip(), "value": str(val).strip()})

            base_option_names = [a["name"] for a in variant_attributes]
            if not base_option_names and item.get("default_variant"):
                for dv in item["default_variant"]:
                    if isinstance(dv, str) and ":" in dv:
                        base_option_names.append(dv.split(":", 1)[0].strip())

            # ✅ 1. Saare unique child ASINs nikaalein (variantAsins + variantDetails + variants)
            raw_asins = []
            for a in (item.get("variantAsins") or item.get("variant_asins") or []):
                if a and isinstance(a, str):
                    raw_asins.append(a.strip())

            raw_variant_details = item.get("variantDetails") or item.get("variant_details") or []
            for vd in raw_variant_details:
                if isinstance(vd, dict):
                    a = vd.get("asin")
                    if a and isinstance(a, str):
                        raw_asins.append(a.strip())

            raw_variants = item.get("variants") or []
            for v in raw_variants:
                if isinstance(v, dict):
                    a = v.get("asin")
                    if a and isinstance(a, str):
                        raw_asins.append(a.strip())

            # Main ASIN include karein
            if asin and isinstance(asin, str):
                raw_asins.insert(0, asin.strip())

            # Deduplicate karein (order maintain)
            seen = set()
            variant_asins = []
            for a in raw_asins:
                if a and a not in seen:
                    seen.add(a)
                    variant_asins.append(a)

            # ✅ Saare variants ki details map banayein
            variant_details = []
            vd_by_asin = {}
            for vd in raw_variant_details:
                if isinstance(vd, dict) and vd.get("asin"):
                    vd_by_asin[vd["asin"]] = vd

            v_by_asin = {}
            for v in raw_variants:
                if isinstance(v, dict) and v.get("asin"):
                    v_by_asin[v["asin"]] = v

            for v_asin in variant_asins:
                vd = vd_by_asin.get(v_asin) or v_by_asin.get(v_asin) or {}
                v_name = vd.get("name", "")
                v_price = parse_price(vd.get("price"))
                v_thumb = vd.get("thumbnail") or vd.get("thumbnailImage")
                v_imgs = vd.get("images") or []
                if isinstance(v_imgs, str):
                    v_imgs = [v_imgs]

                v_attrs = []
                if v_asin == asin and variant_attributes:
                    v_attrs = list(variant_attributes)
                elif isinstance(vd.get("attributes"), list):
                    attrs_list = vd["attributes"]
                    if attrs_list and isinstance(attrs_list[0], dict):
                        for a in attrs_list:
                            k = a.get("key") or a.get("name")
                            val = a.get("value")
                            if k and val:
                                v_attrs.append({"name": str(k).strip(), "value": str(val).strip()})
                    elif attrs_list and isinstance(attrs_list[0], str):
                        for idx, val in enumerate(attrs_list):
                            opt_name = base_option_names[idx] if idx < len(base_option_names) else f"Option {idx+1}"
                            v_attrs.append({"name": opt_name, "value": str(val).strip()})

                if not v_attrs and v_name:
                    if "/" in v_name:
                        parts = [p.strip() for p in v_name.split("/") if p.strip()]
                        for idx, p in enumerate(parts):
                            opt_name = base_option_names[idx] if idx < len(base_option_names) else (f"Option {idx+1}" if len(parts) > 1 else "Style")
                            v_attrs.append({"name": opt_name, "value": p})
                    else:
                        parts = v_name.split()
                        if len(parts) >= 2 and len(base_option_names) >= 2:
                            v_attrs.append({"name": base_option_names[0], "value": parts[0]})
                            v_attrs.append({"name": base_option_names[1], "value": " ".join(parts[1:])})
                        elif len(parts) >= 2:
                            v_attrs.append({"name": "Size", "value": parts[0]})
                            v_attrs.append({"name": "Color", "value": " ".join(parts[1:])})
                        elif len(base_option_names) == 1:
                            v_attrs.append({"name": base_option_names[0], "value": v_name})
                        else:
                            v_attrs.append({"name": "Style", "value": v_name})

                variant_details.append({
                    "asin": v_asin,
                    "name": v_name,
                    "price": v_price,
                    "thumbnail": v_thumb,
                    "images": v_imgs,
                    "attributes": v_attrs,
                })

            # ✅ Images: Do not treat galleryThumbnails or highResolutionImages as product variations
            high_res = item.get("highResolutionImages")
            images_raw = high_res if isinstance(high_res, list) and high_res else (item.get("images") or [])
            if not images_raw and item.get("thumbnailImage"):
                images_raw = [item["thumbnailImage"]]
            images = images_raw if isinstance(images_raw, list) else ([images_raw] if images_raw else [])

            # Other data
            is_available = item.get("inStock") if "inStock" in item else item.get("is_available", True)
            avail_text = item.get("inStockText") or item.get("availability") or ("In Stock" if is_available else "Out of Stock")
            stock_qty = 100 if is_available else 0

            price_raw = item.get("price") or item.get("price_value") or item.get("buybox_price")
            price = parse_price(price_raw)
            list_price = parse_price(item.get("listPrice") or item.get("list_price"))

            bullets = item.get("about_item") or item.get("feature_bullets") or []
            if isinstance(bullets, str):
                bullets = [b.strip() for b in bullets.split("   ") if b.strip()]

            specs = {}
            for detail in (item.get("product_details") or item.get("attributes") or []):
                if isinstance(detail, dict):
                    k = detail.get("type") or detail.get("key")
                    v = detail.get("value")
                    if k and v:
                        specs[str(k).strip()] = str(v).strip()

            title = item.get("title") or "Untitled Product"
            brand = item.get("brand") or item.get("brand_name") or item.get("manufacturer") or ""
            categories = []
            breadcrumbs = item.get("breadCrumbs") or item.get("breadcrumbs") or ""
            if breadcrumbs and isinstance(breadcrumbs, str):
                clean_breadcrumbs = breadcrumbs.replace("›", ">")
                categories = [c.strip() for c in clean_breadcrumbs.split(">") if c.strip()]
            tags = []
            for t in (item.get("tags") or []):
                if isinstance(t, str): tags.append(t)

            return {
                "asin": asin,
                "parent_asin": parent_asin,
                "is_variation": is_variation,
                "title": title,
                "brand": brand,
                "amazon_price": price,
                "list_price": list_price,
                "image_url": images[0] if images else None,
                "images": images,
                "description": item.get("description") or item.get("product_description") or "",
                "feature_bullets": bullets,
                "availability": avail_text,
                "is_available": is_available,
                "stock_quantity": stock_qty,
                "categories": categories,
                "tags": tags,
                "specifications": specs,
                "product_details": item.get("product_details") or item.get("attributes") or [],
                "variant_attributes": variant_attributes,
                "item_weight": item.get("item_weight") or item.get("weight") or specs.get("Item Weight"),
                "item_dimensions": item.get("item_dimensions") or item.get("dimensions") or specs.get("Item Dimensions"),
                "package_dimensions": item.get("package_dimensions") or specs.get("Package Dimensions"),
                "model_number": item.get("model_number") or specs.get("Model number") or specs.get("Item model number"),
                "manufacturer": item.get("manufacturer") or specs.get("Manufacturer"),
                "variant_asins": variant_asins,  # ✅ All unique ASINs
                "variant_details": variant_details,
            }

        return {}

    except Exception as e:
        logger.error(f"Apify fetch failed: {e}")
        raise ApifyError(f"Apify Error: {str(e)}")