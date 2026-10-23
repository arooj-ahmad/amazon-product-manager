# ============================================
# app/services/brightdata.py
# + ✅ Inventory: Prime Exclusive / Join Prime detect karke 0 karega
# + ✅ Category: breadCrumbs parse karke categories mein daala
# ============================================

import logging
import re
from typing import Optional

import httpx
from apify_client import ApifyClient

from app.config import settings

logger = logging.getLogger(__name__)


# ============================================
# EXCEPTIONS
# ============================================
class BrightDataError(Exception):
    pass


class ApifyError(Exception):
    pass


# ============================================
# HELPERS
# ============================================
def extract_asin_from_url(url: str) -> Optional[str]:
    if not url or not isinstance(url, str):
        return None
    patterns = [
        r"/dp/([A-Z0-9]{10})",
        r"/gp/product/([A-Z0-9]{10})",
        r"/product/([A-Z0-9]{10})",
        r"asin=([A-Z0-9]{10})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def parse_price(value) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            cleaned = value.replace("$", "").replace(",", "").strip()
            if not cleaned:
                return None
            return float(cleaned)
        return float(value)
    except (ValueError, TypeError):
        return None


def parse_package_dimensions(package_dims_str: str) -> dict:
    result = {}
    if not package_dims_str or not isinstance(package_dims_str, str):
        return result
    s = package_dims_str.strip()
    if not s:
        return result

    dims_match = re.search(
        r"([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)\s*"
        r"(inches|inch|in|cm|centimeters|centimeter|mm|millimeters|millimeter)?",
        s,
        re.IGNORECASE,
    )
    if dims_match:
        l, w, h = dims_match.group(1), dims_match.group(2), dims_match.group(3)
        unit = dims_match.group(4) or "inches"
        result["item_dimensions"] = f"{l} x {w} x {h} {unit}"

    weight_match = re.search(
        r"([\d.]+)\s*(ounces?|oz|pounds?|lbs?|lb|grams?|g|kilograms?|kg|milligrams?|mg)",
        s,
        re.IGNORECASE,
    )
    if weight_match:
        result["item_weight"] = f"{weight_match.group(1)} {weight_match.group(2)}"
    return result


def validate_parent_asin(parent_asin, asin: str) -> Optional[str]:
    if not parent_asin or parent_asin == "None" or parent_asin == "":
        return None
    if not isinstance(parent_asin, str):
        return None
    parent_asin = parent_asin.strip()
    if parent_asin == asin or len(parent_asin) != 10 or not parent_asin.isalnum():
        return None
    return parent_asin.upper()


def parse_standard_fields(raw: dict) -> dict:
    fields = {}
    fields["model_number"] = raw.get("model_number")
    fields["manufacturer"] = raw.get("manufacturer")
    fields["item_dimensions"] = raw.get("item_dimensions") or raw.get("product_dimensions") or ""
    fields["item_weight"] = raw.get("item_weight") or raw.get("product_weight") or ""

    package_dims_raw = raw.get("package_dimensions") or ""
    if package_dims_raw and isinstance(package_dims_raw, str):
        fields["package_dimensions"] = package_dims_raw.strip()
        parsed = parse_package_dimensions(package_dims_raw)
        if not fields["item_dimensions"] and parsed.get("item_dimensions"):
            fields["item_dimensions"] = parsed["item_dimensions"]
        if not fields["item_weight"] and parsed.get("item_weight"):
            fields["item_weight"] = parsed["item_weight"]

    product_details = raw.get("product_details") or []
    if isinstance(product_details, list):
        for item in product_details:
            if not isinstance(item, dict):
                continue
            field_type = (item.get("type") or "").strip().lower()
            field_value = item.get("value")
            if not field_value:
                continue
            value_str = str(field_value).strip()

            if field_type in ("item dimensions", "item dimensions l x w x h", "product dimensions"):
                if not fields["item_dimensions"]:
                    fields["item_dimensions"] = value_str
            elif field_type in ("item weight", "shipping weight"):
                if not fields["item_weight"]:
                    fields["item_weight"] = value_str
            elif field_type == "color":
                fields["color"] = value_str
            elif field_type == "material":
                fields["material_type"] = value_str

    return {
        k: v
        for k, v in fields.items()
        if v is not None and str(v).strip() and str(v).strip() != "None"
    }


# ============================================
# 1. APIFY FETCH (100% Product Details)
# ============================================
def fetch_product_from_apify(amazon_url: str) -> dict:
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
            raw_parent = item.get("parent_asin")
            parent_asin = validate_parent_asin(raw_parent, asin)
            is_variation = bool(parent_asin)

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

            # ✅ INVENTORY FIX: Prime Exclusive & Join Prime detect karo
            price_raw = item.get("buybox_price") or item.get("price")
            avail_text = str(item.get("availability") or "").strip()
            avail_lower = avail_text.lower()
            
            # Poore item ko string mein convert kar ke check karo (Join Prime / Prime exclusive)
            item_str = str(item).lower()

            out_of_stock_keywords = [
                "out of stock", "unavailable", "currently unavailable",
                "not available", "sold out", "no featured offers"
            ]

            # 1. Agar text mein out of stock likha hai
            if any(kw in avail_lower for kw in out_of_stock_keywords):
                is_available = False
                stock_qty = 0
                avail_text = "Out of Stock"
            
            # 2. Agar "Join Prime" ya "Prime exclusive" ka zikr hai (Add to cart nahi hai)
            elif "join prime" in item_str or "prime exclusive" in item_str:
                is_available = False
                stock_qty = 0
                avail_text = "Prime Exclusive - Out of Stock for non-Prime"
            
            # 3. Agar price hi nahi hai
            elif price_raw is None or price_raw == "":
                is_available = False
                stock_qty = 0
                avail_text = "Out of Stock"
            
            # 4. Warna In Stock (Add to cart button mojood hai)
            else:
                is_available = True
                stock_qty = 100
                if not avail_text:
                    avail_text = "In Stock"

            # Images
            images_raw = item.get("images") or []
            if isinstance(images_raw, str):
                images = [images_raw]
            elif isinstance(images_raw, list):
                images = [img for img in images_raw if isinstance(img, str)]
            else:
                images = []

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
                # "Toys & Games > Vehicles > Vehicle Playsets > Motor Vehicles"
                categories = [c.strip() for c in breadcrumbs.split(">") if c.strip()]
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
            }

        logger.warning(f"⚠️ Apify: no item found for {amazon_url}")
        return {}

    except Exception as e:
        logger.error(f"Apify fetch failed: {e}")
        raise ApifyError(f"Apify Error: {str(e)}")


# ============================================
# 2. BRIGHT DATA FETCH (Only for Cron / Price Update)
# ============================================
async def fetch_product_from_brightdata(amazon_url: str) -> dict:
    api_url = (
        f"{settings.BRIGHT_DATA_API_URL}"
        f"?dataset_id={settings.BRIGHT_DATA_DATASET_ID}"
        f"&include_errors=true"
    )
    headers = {
        "Authorization": f"Bearer {settings.BRIGHT_DATA_API_KEY}",
        "Content-Type": "application/json",
    }
    body = [{"url": amazon_url}]

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(api_url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        raise BrightDataError(f"Bright Data API Error: {str(e)}")

    raw = data[0] if isinstance(data, list) and len(data) > 0 else data
    if "error" in raw:
        raise BrightDataError(f"Bright Data error: {raw['error']}")

    asin = raw.get("asin") or extract_asin_from_url(amazon_url)
    if not asin:
        raise BrightDataError("ASIN nahi mila")

    parent_asin = validate_parent_asin(raw.get("parent_asin"), asin)
    is_variation = bool(parent_asin)

    variations = []
    if isinstance(raw.get("variations"), list):
        for v in raw.get("variations"):
            if isinstance(v, dict) and v.get("variation_name") and v.get("variation_value"):
                variations.append({"name": str(v["variation_name"]).strip(), "value": str(v["variation_value"]).strip()})

    variant_attributes = []
    if isinstance(raw.get("variant_attributes"), list):
        for attr in raw.get("variant_attributes"):
            if isinstance(attr, dict) and attr.get("name") and attr.get("value"):
                variant_attributes.append({"name": str(attr["name"]).strip(), "value": str(attr["value"]).strip()})

    images_list = raw.get("images") or []
    main_image = raw.get("image_url") or raw.get("image")
    unique_images = [main_image] if main_image else []
    if isinstance(images_list, list):
        for img in images_list:
            if isinstance(img, str) and img not in unique_images:
                unique_images.append(img)
    if not main_image and unique_images:
        main_image = unique_images[0]

    in_stock = raw.get("in_stock")
    if in_stock is True:
        is_available = True
        availability_text = "In Stock"
    else:
        is_available = False
        availability_text = "Out of Stock"

    stock_quantity = 100 if is_available else 0

    specs = {}
    product_details = raw.get("product_details") or []
    if isinstance(product_details, list):
        for item in product_details:
            if isinstance(item, dict) and item.get("type") and item.get("value"):
                if item["type"] not in specs:
                    specs[item["type"]] = str(item["value"]).strip()

    categories = raw.get("categories") or []
    feature_bullets = []
    if isinstance(raw.get("feature_bullets"), list) and len(raw["feature_bullets"]) > 0:
        feature_bullets = [str(b).strip() for b in raw["feature_bullets"] if b]

    if not feature_bullets:
        desc_text = raw.get("description", "") or raw.get("product_description", "") or raw.get("about_this_item", "")
        if desc_text:
            if "About this item" in desc_text:
                bullets_text = desc_text.split("About this item")[-1].strip()
                lines = bullets_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if line:
                        feature_bullets.append(line)
            else:
                lines = desc_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if line:
                        feature_bullets.append(line)

    if not feature_bullets:
        feature_bullets = ["Check Amazon for full product details."]

    return {
        "asin": asin,
        "parent_asin": parent_asin,
        "is_variation": is_variation,
        "title": raw.get("title"),
        "brand": raw.get("brand"),
        "amazon_price": parse_price(raw.get("final_price") or raw.get("price")),
        "list_price": parse_price(raw.get("list_price")),
        "image_url": main_image,
        "images": unique_images,
        "specifications": specs,
        "description": "",
        "feature_bullets": feature_bullets,
        "availability": availability_text,
        "is_available": is_available,
        "stock_quantity": stock_quantity,
        "variations": variations,
        "variant_attributes": variant_attributes,
        "categories": categories,
        "tags": raw.get("tags") or [],
        **parse_standard_fields(raw),
        "product_details": product_details,
    }


# ============================================
# CALCULATE FINAL PRICE
# ============================================
def calculate_final_price(
    amazon_price: Optional[float],
    markup: Optional[float] = None,
    markup_type: Optional[str] = None,
    admin_price: Optional[float] = None,
    is_manual_override: bool = False,
    extra_percent: float = 0.0,
    tax_rate: float = 0.0,
) -> Optional[float]:
    if amazon_price is None:
        return admin_price
    if markup is None or markup_type is None:
        return admin_price

    markup = markup or 0.0
    extra_percent = extra_percent or 0.0
    tax_rate = tax_rate or 0.0

    if markup_type == "percent":
        base_price = amazon_price + (amazon_price * (markup / 100.0))
    elif markup_type == "both":
        base_price = (amazon_price + markup) * (1 + extra_percent / 100.0)
    else:
        base_price = amazon_price + markup

    final_price = base_price + (base_price * (tax_rate / 100.0))

    if is_manual_override and admin_price is not None:
        return max(admin_price, final_price)

    return round(final_price, 2)