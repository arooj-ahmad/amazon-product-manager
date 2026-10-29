# app/services/amazon/apify_scraper.py
# ============================================================
# Fetches a single Amazon product page via Apify.
# Returns the normalised product dict INCLUDING the raw
# variantDetails and variantAsins arrays so that the worker
# can extract child ASINs without a second Apify call.
# ============================================================
import logging
from apify_client import ApifyClient
from app.core.config import settings
from .exceptions import ApifyError
from .helpers import extract_asin_from_url, validate_parent_asin, parse_price
from .inventory_apify import check_availability_apify

logger = logging.getLogger(__name__)


def _is_valid_asin(value) -> bool:
    """Return True when value looks like a 10-char alphanumeric ASIN."""
    if not value or not isinstance(value, str):
        return False
    v = value.strip().upper()
    return len(v) == 10 and v.isalnum()


def _extract_child_asins_from_raw(item: dict, base_asin: str) -> tuple:
    """Collect child ASINs from the raw Apify item using every known field."""
    raw_asins = []
    variant_details_raw = []
    
    for vd in (item.get("variantDetails") or item.get("variant_details") or []):
        if not isinstance(vd, dict): continue
        variant_details_raw.append(vd)
        asin_val = vd.get("asin") or vd.get("ASIN")
        if _is_valid_asin(asin_val): raw_asins.append(asin_val.strip().upper())

    for a in (item.get("variantAsins") or item.get("variant_asins") or []):
        if _is_valid_asin(a): raw_asins.append(a.strip().upper())

    for v in (item.get("variants") or []):
        if isinstance(v, dict):
            a = v.get("asin") or v.get("ASIN")
            if _is_valid_asin(a): raw_asins.append(a.strip().upper())

    seen = set()
    child_asins = []
    for a in raw_asins:
        if a != base_asin and a not in seen:
            seen.add(a)
            child_asins.append(a)

    return child_asins, variant_details_raw


def fetch_product_from_apify(amazon_url: str) -> dict:
    """Fetch one Amazon product page via Apify and return a normalised dict."""
    client = ApifyClient(settings.APIFY_API_TOKEN)
    actor_id = "delicious_zebu/amazon-product-details-scraper"
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
            if not isinstance(item, dict): continue

            asin = item.get("asin") or extract_asin_from_url(amazon_url)
            if asin: asin = asin.strip().upper()
            parent_asin = validate_parent_asin(item.get("parent_asin"), asin)

            is_available, avail_text, _reason = check_availability_apify(item)
            stock_qty = 100 if is_available else 0

            images_raw = item.get("images") or []
            images = [img for img in images_raw if isinstance(img, str)] if isinstance(images_raw, list) else ([images_raw] if isinstance(images_raw, str) else [])

            price = parse_price(item.get("buybox_price") or item.get("price"))

            bullets = item.get("about_item") or item.get("feature_bullets") or []
            if isinstance(bullets, str): bullets = [line.strip() for line in bullets.split("\n") if line.strip()]
            if not bullets: bullets = ["Check Amazon for full product details."]

            # ── Specifications (Multiple formats handle karein) ────────
            specs = {}
            
            # 1. Direct specifications dictionary se
            raw_specs = item.get("specifications")
            if isinstance(raw_specs, dict):
                for k, v in raw_specs.items():
                    if k and v: specs[str(k).strip()] = str(v).strip()

            # 2. product_details array se
            for detail in (item.get("product_details") or []):
                if isinstance(detail, dict) and detail.get("type") and detail.get("value"):
                    specs[str(detail["type"]).strip()] = str(detail["value"]).strip()

            # 3. technical_details se (agar ho)
            tech_details = item.get("technical_details")
            if isinstance(tech_details, dict):
                for k, v in tech_details.items():
                    if k and v and k not in specs: specs[str(k).strip()] = str(v).strip()

            categories = []
            breadcrumbs = item.get("breadCrumbs") or item.get("breadcrumbs") or ""
            if breadcrumbs and isinstance(breadcrumbs, str):
                categories = [c.strip() for c in breadcrumbs.replace("›", ">").split(">") if c.strip()]
            categories = list(dict.fromkeys([str(c).strip() for c in categories if c and str(c).strip() and len(str(c)) < 100]))

            variant_attributes = []
            for v in (item.get("variants") or []):
                if isinstance(v, dict):
                    for attr in (v.get("attributes") or v.get("attributes_list") or []):
                        if isinstance(attr, str) and ":" in attr:
                            name, value = attr.split(":", 1)
                            name, value = name.strip(), value.strip()
                            if name and value: variant_attributes.append({"name": name, "value": value})

            if not variant_attributes:
                for dv in (item.get("default_variant") or []):
                    if isinstance(dv, str) and ":" in dv:
                        name, value = dv.split(":", 1)
                        name, value = name.strip(), value.strip()
                        if name and value: variant_attributes.append({"name": name, "value": value})

            # ✅ Fallback: Agar specs abhi bhi khali hain, to ASIN aur Size daal dein
            if not specs:
                if asin: specs["ASIN"] = asin
                for attr in variant_attributes: specs[attr["name"]] = attr["value"]

            # ✅ NAYA: Specs dictionary ko product_details list mein convert karein
            product_details_list = [{"type": k, "value": v} for k, v in specs.items()]

            # ✅ NAYA: Physical attributes extract karein (specs dictionary se)
            item_weight = specs.get("Item Weight") or specs.get("Weight") or item.get("item_weight") or item.get("weight")
            item_dimensions = specs.get("Item Dimensions") or specs.get("Dimensions") or item.get("item_dimensions") or item.get("dimensions")
            package_dimensions = specs.get("Package Dimensions") or item.get("package_dimensions")
            size_val = specs.get("Size") or item.get("size")
            color_val = specs.get("Color") or item.get("color")
            material_val = specs.get("Material Type") or specs.get("Material") or item.get("material_type")

            child_asins, variant_details = _extract_child_asins_from_raw(item, asin)

            rating_val = item.get("rating") or item.get("stars") or item.get("average_rating")
            reviews_val = item.get("reviews_count") or item.get("reviews") or item.get("ratings_count")
            
            if rating_val is not None:
                try: rating_val = float(str(rating_val).replace(",", "").strip())
                except (ValueError, TypeError): rating_val = None
                    
            if reviews_val is not None:
                try: reviews_val = int(str(reviews_val).replace(",", "").strip().split()[0])
                except (ValueError, TypeError, IndexError): reviews_val = None

            return {
                "asin": asin,
                "parent_asin": parent_asin,
                "is_variation": bool(parent_asin),
                "title": item.get("title") or "Untitled Product",
                "brand": item.get("brand") or item.get("manufacturer") or "",
                "rating": rating_val,
                "reviews_count": reviews_val,
                "description": "",
                "feature_bullets": bullets,
                "amazon_price": price,
                "list_price": None,
                "image_url": images[0] if images else None,
                "images": images,
                "availability": avail_text,
                "is_available": is_available,
                "stock_quantity": stock_qty,
                "categories": categories,
                "tags": item.get("tags") or [],
                "specifications": specs,
                # ✅ YEH CHANGE KAREIN: ab product_details khali nahi jayega
                "product_details": product_details_list, 
                # ✅ Physical attributes
                "item_weight": item_weight,
                "item_dimensions": item_dimensions,
                "package_dimensions": package_dimensions,
                "size": size_val,
                "color": color_val,
                "material_type": material_val,
                "model_number": specs.get("Model Number") or item.get("model_number"),
                "manufacturer": item.get("manufacturer"),
                "variant_attributes": variant_attributes,
                "variations": variant_attributes,
                "variant_asins": child_asins,
                "variant_details": variant_details,
            }

        return {}

    except Exception as e:
        raise ApifyError(f"Apify Error: {str(e)}")