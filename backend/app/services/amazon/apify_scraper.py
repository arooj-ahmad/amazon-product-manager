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
            
            # Parent ASIN extraction
            parent_asin = item.get("parent_asin")
            if not parent_asin:
                raw_url = item.get("url", "")
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
            
            # Main product attributes
            variant_attributes = []
            raw_item_attrs = item.get("attributes") or []
            for attr in raw_item_attrs:
                if isinstance(attr, dict) and attr.get("key") and attr.get("value"):
                    variant_attributes.append({"name": attr["key"], "value": attr["value"]})
            
            # Variant Details
            raw_variant_details = item.get("variantDetails") or []
            variant_details = []
            for vd in raw_variant_details:
                if isinstance(vd, dict):
                    v_asin = vd.get("asin")
                    v_name = vd.get("name")
                    
                    v_attrs = []
                    if v_asin == asin and variant_attributes:
                        v_attrs = variant_attributes
                    else:
                        if v_name:
                            parts = v_name.split()
                            if len(parts) >= 2:
                                v_attrs.append({"name": "Size", "value": parts[0]})
                                v_attrs.append({"name": "Color", "value": " ".join(parts[1:])})
                            else:
                                v_attrs.append({"name": "Style", "value": v_name})

                    variant_details.append({
                        "asin": v_asin,
                        "name": v_name,
                        "thumbnail": vd.get("thumbnail"),
                        "images": vd.get("images", []),
                        "attributes": v_attrs
                    })

            # Other data
            is_available = True
            avail_text = "In Stock"
            stock_qty = 100
            images_raw = item.get("images") or []
            images = images_raw if isinstance(images_raw, list) else ([images_raw] if images_raw else [])
            price_raw = item.get("buybox_price") or item.get("price")
            price = parse_price(price_raw) if price_raw else None
            bullets = item.get("about_item") or item.get("feature_bullets") or []
            specs = {}
            for detail in (item.get("product_details") or []):
                if isinstance(detail, dict) and detail.get("type") and detail.get("value"):
                    specs[detail["type"]] = str(detail["value"]).strip()
            title = item.get("title") or "Untitled Product"
            brand = item.get("brand") or item.get("manufacturer") or ""
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
                "product_details": item.get("product_details") or [],
                "variant_attributes": variant_attributes,
                "item_weight": item.get("item_weight") or item.get("weight"),
                "item_dimensions": item.get("item_dimensions") or item.get("dimensions"),
                "package_dimensions": item.get("package_dimensions"),
                "model_number": item.get("model_number"),
                "manufacturer": item.get("manufacturer"),
                "variant_asins": item.get("variantAsins") or [],
                "variant_details": variant_details,
            }

        return {}

    except Exception as e:
        logger.error(f"Apify fetch failed: {e}")
        raise ApifyError(f"Apify Error: {str(e)}")