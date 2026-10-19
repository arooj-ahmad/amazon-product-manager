# ============================================
# app/services/brightdata.py
# Bright Data Dataset API se data fetch karne ke liye
# + ✅ FIXED: Web Scraper hata diya, "About this item" ka paragraph utha rahe hain
# ============================================

import logging
import re
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class BrightDataError(Exception):
    """Bright Data API se related errors"""
    pass


def extract_asin_from_url(url: str) -> Optional[str]:
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
    if value is None: return None
    try:
        if isinstance(value, str):
            cleaned = value.replace("$", "").replace(",", "").strip()
            if not cleaned: return None
            return float(cleaned)
        return float(value)
    except (ValueError, TypeError):
        return None


def parse_package_dimensions(package_dims_str: str) -> dict:
    result = {}
    if not package_dims_str or not isinstance(package_dims_str, str):
        return result
    s = package_dims_str.strip()
    if not s: return result
    dims_match = re.search(r"([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)\s*(inches|inch|in|cm|centimeters|centimeter|mm|millimeters|millimeter)?", s, re.IGNORECASE)
    if dims_match:
        l, w, h = dims_match.group(1), dims_match.group(2), dims_match.group(3)
        unit = dims_match.group(4) or "inches"
        result["item_dimensions"] = f"{l} x {w} x {h} {unit}"
    weight_match = re.search(r"([\d.]+)\s*(ounces?|oz|pounds?|lbs?|lb|grams?|g|kilograms?|kg|milligrams?|mg)", s, re.IGNORECASE)
    if weight_match:
        result["item_weight"] = f"{weight_match.group(1)} {weight_match.group(2)}"
    return result


def validate_parent_asin(parent_asin, asin: str) -> Optional[str]:
    if not parent_asin or parent_asin == "None" or parent_asin == "": return None
    if not isinstance(parent_asin, str): return None
    parent_asin = parent_asin.strip()
    if parent_asin == asin or len(parent_asin) != 10 or not parent_asin.isalnum(): return None
    return parent_asin.upper()


def check_availability(raw: dict) -> tuple[bool, str, str]:
    add_to_cart = raw.get("add_to_cart_available")
    buybox = raw.get("buybox_available")
    in_stock = raw.get("in_stock")

    if add_to_cart is True: return True, "In Stock", "add_to_cart_available"
    if buybox is True: return True, "In Stock", "buybox_available"
    if in_stock is True: return True, "In Stock", "in_stock"

    availability_text = raw.get("availability") or raw.get("stock_status") or ""
    if not availability_text: return False, "Unknown", "no_info"

    avail_lower = availability_text.lower().strip()
    if any(kw in avail_lower for kw in ["out of stock", "unavailable", "not available", "sold out"]): return False, availability_text, "out"
    return True, availability_text, "in"


def parse_categories(raw: dict) -> list[str]:
    categories = []
    category_tree = raw.get("category_tree") or []
    for cat in category_tree:
        if isinstance(cat, dict) and cat.get("name"): categories.append(cat["name"].strip())
        elif isinstance(cat, str): categories.append(cat.strip())
    return [c for c in dict.fromkeys(categories) if c and len(c) < 100]


def parse_standard_fields(raw: dict) -> dict:
    fields = {}
    fields["model_number"] = raw.get("model_number")
    fields["manufacturer"] = raw.get("manufacturer")
    fields["item_dimensions"] = raw.get("package_dimensions") or ""
    fields["item_weight"] = raw.get("package_weight") or ""
    
    product_details = raw.get("product_details") or []
    for item in product_details:
        if isinstance(item, dict) and item.get("type") and item.get("value"):
            field_type = item["type"].strip().lower()
            value_str = str(item["value"]).strip()
            if field_type == "item weight": fields["item_weight"] = value_str
            if field_type == "color": fields["color"] = value_str
            if field_type == "material": fields["material_type"] = value_str
    return {k: v for k, v in fields.items() if v}


def parse_tags(raw: dict, categories: list[str]) -> list[str]:
    tags = list(categories)
    raw_tags = raw.get("tags") or []
    for t in raw_tags:
        if isinstance(t, str): tags.append(t.strip())
    return list(dict.fromkeys(tags))[:15]


# ============================================
# MAIN FETCH FUNCTION
# ============================================
async def fetch_product_from_brightdata(amazon_url: str) -> dict:
    
    api_url = f"{settings.BRIGHT_DATA_API_URL}?dataset_id={settings.BRIGHT_DATA_DATASET_ID}&include_errors=true"
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
    if "error" in raw: raise BrightDataError(f"Bright Data error: {raw['error']}")

    asin = raw.get("asin") or extract_asin_from_url(amazon_url)
    if not asin: raise BrightDataError("ASIN nahi mila")

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
    if not main_image and unique_images: main_image = unique_images[0]

    is_available, availability_text, _ = check_availability(raw)
    stock_quantity = 100 if is_available else 0

    specs = {}
    product_details = raw.get("product_details") or []
    if isinstance(product_details, list):
        for item in product_details:
            if isinstance(item, dict) and item.get("type") and item.get("value"):
                if item["type"] not in specs: specs[item["type"]] = str(item["value"]).strip()

    categories = parse_categories(raw)

    # =========================================================
    # ✅ FIXED: "About this item" ka PARAGRAPH nikalna
    # =========================================================
    feature_bullets = []
    
    # 1. Check karein agar API direct 'feature_bullets' bhej rahi hai
    if isinstance(raw.get("feature_bullets"), list) and len(raw["feature_bullets"]) > 0:
        feature_bullets = [str(b).strip() for b in raw["feature_bullets"] if b]
        
    # 2. Agar nahi, toh description se "About this item" ka paragraph uthayen
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

    # 3. Agar abhi bhi kuch nahi mila
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
        # ✅ Description empty, bullets mein paragraph
        "description": "",
        "feature_bullets": feature_bullets,
        "availability": str(availability_text) if availability_text else "In Stock",
        "is_available": is_available,
        "stock_quantity": stock_quantity,
        "variations": variations,
        "variant_attributes": variant_attributes,
        "categories": categories,
        "tags": parse_tags(raw, categories),
        **parse_standard_fields(raw),
        "product_details": product_details,
    }


# ============================================
# CALCULATE FINAL PRICE
# ============================================
def calculate_final_price(amazon_price, markup=None, markup_type=None, admin_price=None, is_manual_override=False, extra_percent=0.0, tax_rate=0.0):
    if amazon_price is None: return admin_price
    if markup is None or markup_type is None: return admin_price
    markup = markup or 0.0
    extra_percent = extra_percent or 0.0
    tax_rate = tax_rate or 0.0
    if markup_type == "percent": base_price = amazon_price + (amazon_price * (markup / 100.0))
    elif markup_type == "both": base_price = amazon_price + markup + (amazon_price * (extra_percent / 100.0))
    else: base_price = amazon_price + markup
    final_price = base_price + (base_price * (tax_rate / 100.0))
    if is_manual_override and admin_price is not None: return round(max(admin_price, final_price), 2)
    return round(final_price, 2)