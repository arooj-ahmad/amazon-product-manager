# app/services/amazon/apify_scraper.py
import logging
from apify_client import ApifyClient
from app.core.config import settings
from .exceptions import ApifyError
from .helpers import extract_asin_from_url, validate_parent_asin, parse_price
from .availability import check_availability

logger = logging.getLogger(__name__)

def fetch_product_from_apify(amazon_url: str) -> dict:
    client = ApifyClient(settings.APIFY_API_TOKEN)
    actor_id = "delicious_zebu/amazon-product-details-scraper"
    run_input = {"Params": [amazon_url], "scrapeProductDetails": True, "country": "US", "zipCode": "30024"}

    try:
        run = client.actor(actor_id).call(run_input=run_input)
        dataset_id = run.get("defaultDatasetId") if isinstance(run, dict) else run.default_dataset_id
        items = client.dataset(dataset_id).iterate_items()

        for item in items:
            if not isinstance(item, dict): continue
            asin = item.get("asin") or extract_asin_from_url(amazon_url)
            parent_asin = validate_parent_asin(item.get("parent_asin"), asin)
            
            variant_attributes, variations = [], []
            for v in (item.get("variants") or []):
                if isinstance(v, dict):
                    for attr in (v.get("attributes") or v.get("attributes_list") or []):
                        if isinstance(attr, str) and ":" in attr:
                            name, value = attr.split(":", 1)
                            variant_attributes.append({"name": name.strip(), "value": value.strip()})
                            variations.append({"name": name.strip(), "value": value.strip()})

            if not variant_attributes:
                for dv in (item.get("default_variant") or []):
                    if isinstance(dv, str) and ":" in dv:
                        name, value = dv.split(":", 1)
                        variant_attributes.append({"name": name.strip(), "value": value.strip()})
                        variations.append({"name": name.strip(), "value": value.strip()})

            is_available, avail_text, reason = check_availability(item)
            stock_qty = 100 if is_available else 0

            images_raw = item.get("images") or []
            images = [img for img in images_raw if isinstance(img, str)] if isinstance(images_raw, list) else ([images_raw] if isinstance(images_raw, str) else [])
            
            price = parse_price(item.get("buybox_price") or item.get("price"))
            
            bullets = item.get("about_item") or item.get("feature_bullets") or []
            if isinstance(bullets, str): bullets = [line.strip() for line in bullets.split("\n") if line.strip()]
            if not bullets: bullets = ["Check Amazon for full product details."]

            specs = {}
            for detail in (item.get("product_details") or []):
                if isinstance(detail, dict) and detail.get("type") and detail.get("value"):
                    specs[detail["type"]] = str(detail["value"]).strip()

            categories = []
            breadcrumbs = item.get("breadCrumbs") or item.get("breadcrumbs") or ""
            if breadcrumbs and isinstance(breadcrumbs, str):
                categories = [c.strip() for c in breadcrumbs.replace("›", ">").split(">") if c.strip()]

            categories = list(dict.fromkeys([str(c).strip() for c in categories if c and str(c).strip() and len(str(c)) < 100]))

            return {
                "asin": asin, "parent_asin": parent_asin, "is_variation": bool(parent_asin),
                "title": item.get("title") or "Untitled Product", "brand": item.get("brand") or item.get("manufacturer") or "",
                "amazon_price": price, "list_price": None, "image_url": images[0] if images else None, "images": images,
                "description": "", "feature_bullets": bullets, "availability": avail_text, "is_available": is_available,
                "stock_quantity": stock_qty, "categories": categories, "tags": item.get("tags") or [],
                "specifications": specs, "product_details": item.get("product_details") or [],
                "variant_attributes": variant_attributes, "variations": variations,
                "item_weight": item.get("item_weight") or item.get("weight"), "item_dimensions": item.get("item_dimensions") or item.get("dimensions"),
                "package_dimensions": item.get("package_dimensions"), "model_number": item.get("model_number"), "manufacturer": item.get("manufacturer"),
            }
        return {}
    except Exception as e:
        raise ApifyError(f"Apify Error: {str(e)}")
