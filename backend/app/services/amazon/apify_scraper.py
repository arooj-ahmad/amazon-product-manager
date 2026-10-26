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
    # ✅ Check: Agar Apify token nahi hai to gracefully fail ho
    if not settings.APIFY_API_TOKEN:
        logger.error("❌ APIFY_API_TOKEN is not configured. Cannot fetch from Apify.")
        raise ApifyError("Apify token not configured in environment variables.")

    client = ApifyClient(settings.APIFY_API_TOKEN)
    actor_id = "delicious_zebu/amazon-product-details-scraper"

    run_input = {
        "Params": [amazon_url],
        "scrapeProductDetails": True,
        "country": "US",
        "zipCode": "30024"
    }

    try:
        run = client.actor(actor_id).call(run_input=run_input)
        dataset_id = run.get("defaultDatasetId") if isinstance(run, dict) else run.default_dataset_id
        items = client.dataset(dataset_id).iterate_items()

        for item in items:
            if not isinstance(item, dict):
                continue

            asin = item.get("asin") or extract_asin_from_url(amazon_url)
            
            # =====================================================
            # ✅ FIXED: Parent ASIN nikalne ka sab se pakka tareeqa
            # =====================================================
            parent_asin = item.get("parent_asin")
            
            # 1. Agar direct nahi mila, to URL se nikaalein
            if not parent_asin:
                raw_url = item.get("url", "")
                if raw_url:
                    parsed = urllib.parse.urlparse(raw_url)
                    query_params = urllib.parse.parse_qs(parsed.query)
                    if "parent_asin" in query_params:
                        parent_asin = query_params["parent_asin"][0]

            # 2. Agar URL se bhi na mile, to Product Details mein se "Parent ASIN" dhoondein
            if not parent_asin:
                product_details = item.get("product_details") or []
                for detail in product_details:
                    if isinstance(detail, dict):
                        field_type = str(detail.get("type", "")).lower()
                        if "parent asin" in field_type:
                            parent_asin = detail.get("value")
                            break

            # 3. Agar phir bhi na mile, to variants se nikaalein
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
            
            logger.info(f"🔍 DEBUG: Fetched ASIN={asin}, Parent ASIN={parent_asin}")

            variant_attributes = []
            variations = []
            apify_variants = item.get("variants") or []
            for v in apify_variants:
                if isinstance(v, dict):
                    attrs = v.get("attributes") or v.get("attributes_list") or []
                    if isinstance(attrs, str):
                        attrs = [attrs]
                    for attr in attrs:
                        if isinstance(attr, str) and ":" in attr:
                            name, value = attr.split(":", 1)
                            variant_attributes.append({"name": name.strip(), "value": value.strip()})
                            variations.append({"name": name.strip(), "value": value.strip()})

            if not variant_attributes:
                default_vars = item.get("default_variant") or []
                if isinstance(default_vars, str):
                    default_vars = [default_vars]
                for dv in default_vars:
                    if isinstance(dv, str) and ":" in dv:
                        name, value = dv.split(":", 1)
                        variant_attributes.append({"name": name.strip(), "value": value.strip()})
                        variations.append({"name": name.strip(), "value": value.strip()})

            # =====================================================
            # ✅ FIXED: Stock HAMESHA 100 hoga (Check hata diya)
            # =====================================================
            is_available = True
            avail_text = "In Stock"
            stock_qty = 100
            
            logger.info(f"   Apify Inventory Check: Force In Stock -> Stock: 100")

            # Images
            images_raw = item.get("images") or []
            if isinstance(images_raw, str):
                images = [images_raw]
            elif isinstance(images_raw, list):
                images = [img for img in images_raw if isinstance(img, str)]
            else:
                images = []

            price_raw = item.get("buybox_price") or item.get("price")
            price = parse_price(price_raw) if price_raw else None

            # Bullets
            bullets = item.get("about_item") or item.get("feature_bullets") or []
            if isinstance(bullets, str):
                bullets = [line.strip() for line in bullets.split("\n") if line.strip()]
            if not bullets and item.get("description"):
                bullets = [line.strip() for line in item["description"].split("\n") if line.strip()]
            if not isinstance(bullets, list) or len(bullets) == 0:
                bullets = ["Check Amazon for full product details."]

            # Specs
            specs = {}
            product_details = item.get("product_details") or []
            if isinstance(product_details, list):
                for detail in product_details:
                    if isinstance(detail, dict) and detail.get("type") and detail.get("value"):
                        specs[detail["type"]] = str(detail["value"]).strip()
            if item.get("specifications") and isinstance(item["specifications"], dict):
                specs.update(item["specifications"])

            title = item.get("title") or "Untitled Product"
            brand = item.get("brand") or item.get("manufacturer") or ""

            # ✅ Category: breadCrumbs se parse karo
            categories = []
            breadcrumbs = item.get("breadCrumbs") or item.get("breadcrumbs") or ""
            if breadcrumbs and isinstance(breadcrumbs, str):
                clean_breadcrumbs = breadcrumbs.replace("›", ">")
                categories = [c.strip() for c in clean_breadcrumbs.split(">") if c.strip()]
            else:
                raw_cat = item.get("categories") or item.get("category") or item.get("category_tree")
                if isinstance(raw_cat, list):
                    for c in raw_cat:
                        if isinstance(c, dict) and c.get("name"):
                            categories.append(c.get("name"))
                        elif isinstance(c, str):
                            categories.append(c)
                elif isinstance(raw_cat, str):
                    categories.append(raw_cat)

            tags = []
            raw_tags = item.get("tags") or item.get("best_sellers_rank") or []
            if isinstance(raw_tags, list):
                for t in raw_tags:
                    if isinstance(t, str):
                        tags.append(t)
                    elif isinstance(t, dict) and t.get("category"):
                        tags.append(t.get("category"))
                    elif isinstance(t, dict) and t.get("name"):
                        tags.append(t.get("name"))
            elif isinstance(raw_tags, str):
                tags.append(raw_tags)

            categories = list(dict.fromkeys([str(c).strip() for c in categories if c and str(c).strip() and len(str(c)) < 100]))
            tags = list(dict.fromkeys([str(t).strip() for t in tags if t and str(t).strip()]))[:15]

            # ✅ Apify se saari variants ki details nikaalein (colors/sizes ke sath)
            raw_variant_details = item.get("variantDetails") or []
            variant_details = []
            for vd in raw_variant_details:
                if isinstance(vd, dict):
                    variant_details.append({
                        "asin": vd.get("asin"),
                        "name": vd.get("name"),
                        "thumbnail": vd.get("thumbnail"),
                        "images": vd.get("images", [])
                    })

            return {
                "asin": asin,
                "parent_asin": parent_asin,
                "is_variation": is_variation,
                "title": title,
                "brand": brand,
                "amazon_price": price,
                "list_price": None,
                "image_url": images[0] if images else None,
                "images": images,
                "description": "",
                "feature_bullets": bullets,
                "availability": avail_text,
                "is_available": is_available,
                "stock_quantity": stock_qty,
                "categories": categories,
                "tags": tags,
                "specifications": specs,
                "product_details": product_details,
                "variant_attributes": variant_attributes,
                "variations": variations,
                "item_weight": item.get("item_weight") or item.get("weight"),
                "item_dimensions": item.get("item_dimensions") or item.get("dimensions"),
                "package_dimensions": item.get("package_dimensions"),
                "model_number": item.get("model_number"),
                "manufacturer": item.get("manufacturer"),
                "variant_asins": item.get("variantAsins") or [],
                "variant_details": variant_details, # ✅ YEH ADD KIYA HAI
            }

        logger.warning(f"⚠️ Apify: no item found for {amazon_url}")
        return {}

    except Exception as e:
        logger.error(f"Apify fetch failed: {e}")
        raise ApifyError(f"Apify Error: {str(e)}")