# ============================================
# app/services/brightdata.py
# + ✅ FINAL: Direct HTML Scraping via Bright Data for Bullets
# ============================================

import logging
import re
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class BrightDataError(Exception):
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
            return float(cleaned) if cleaned else None
        return float(value)
    except: return None


def parse_package_dimensions(package_dims_str: str) -> dict:
    result = {}
    if not package_dims_str or not isinstance(package_dims_str, str): return result
    s = package_dims_str.strip()
    if not s: return result
    dims_match = re.search(r"([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)\s*(inches|inch|in|cm|centimeters|centimeter|mm|millimeters|millimeter)?", s, re.IGNORECASE)
    if dims_match:
        unit = dims_match.group(4) or "inches"
        result["item_dimensions"] = f"{dims_match.group(1)} x {dims_match.group(2)} x {dims_match.group(3)} {unit}"
    weight_match = re.search(r"([\d.]+)\s*(ounces?|oz|pounds?|lbs?|lb|grams?|g|kilograms?|kg|milligrams?|mg)", s, re.IGNORECASE)
    if weight_match:
        result["item_weight"] = f"{weight_match.group(1)} {weight_match.group(2)}"
    return result


def validate_parent_asin(parent_asin, asin: str) -> Optional[str]:
    if not parent_asin or not isinstance(parent_asin, str): return None
    parent_asin = parent_asin.strip()
    if parent_asin == asin or len(parent_asin) != 10 or not parent_asin.isalnum(): return None
    return parent_asin.upper()


def check_availability(raw: dict) -> tuple[bool, str, str]:
    add_to_cart = raw.get("add_to_cart_available")
    if add_to_cart is True: return True, "In Stock", "add_to_cart"
    if add_to_cart is False: return False, "Out of Stock", "add_to_cart"
    availability_text = raw.get("availability") or ""
    if not availability_text: return False, "Unknown", "no_info"
    avail_lower = availability_text.lower()
    if any(kw in avail_lower for kw in ["out of stock", "unavailable", "sold out"]):
        return False, availability_text, "text"
    return True, availability_text, "text"


def parse_categories(raw: dict) -> list[str]:
    categories = []
    category_tree = raw.get("category_tree") or []
    if isinstance(category_tree, list):
        for cat in category_tree:
            if isinstance(cat, dict) and cat.get("name"): categories.append(cat["name"].strip())
            elif isinstance(cat, str): categories.append(cat.strip())
    return [c for c in dict.fromkeys(categories) if c and len(c) < 100]


def parse_standard_fields(raw: dict) -> dict:
    fields = {}
    product_details = raw.get("product_details") or []
    if isinstance(product_details, list):
        for item in product_details:
            if isinstance(item, dict) and item.get("type") and item.get("value"):
                fields[item["type"].lower()] = str(item["value"]).strip()
    return fields


def parse_tags(raw: dict, categories: list[str]) -> list[str]:
    tags = []
    for cat in categories: tags.append(cat)
    raw_tags = raw.get("tags") or []
    if isinstance(raw_tags, list):
        for t in raw_tags:
            if isinstance(t, str): tags.append(t.strip())
    return list(dict.fromkeys(tags))[:15]


def clean_description(description: str) -> str:
    if not description: return ""
    description = re.sub(r"The video showcases.*?(?=[A-Z]|$)", "", description, flags=re.IGNORECASE)
    description = re.sub(r"[>›»]\s*See\s+more.*", "", description, flags=re.IGNORECASE)
    return description.strip()


# ============================================
# ✅ BULLETS NIKALNE KA SMART FUNCTION
# ============================================
def extract_bullets_from_html(html_content: str) -> list[str]:
    if not html_content: return []
    bullets = []
    
    # 1. ID dhoondein aur uske andar ke <li> nikaalein
    match = re.search(r'<div id="feature-bullets".*?>(.*?)</div>', html_content, re.DOTALL | re.IGNORECASE)
    if match:
        li_matches = re.findall(r'<li.*?>(.*?)</li>', match.group(1), re.DOTALL | re.IGNORECASE)
        for li in li_matches:
            text = re.sub(r'<[^>]+>', '', li).strip()
            if text and len(text) > 5: bullets.append(text)
        if bullets: return bullets

    # 2. Agar ID na mile, toh <ul> dhoondein
    match = re.search(r'<ul.*?>(.*?)</ul>', html_content, re.DOTALL | re.IGNORECASE)
    if match:
        li_matches = re.findall(r'<li.*?>(.*?)</li>', match.group(1), re.DOTALL | re.IGNORECASE)
        for li in li_matches:
            text = re.sub(r'<[^>]+>', '', li).strip()
            if text and len(text) > 5: bullets.append(text)
        if bullets: return bullets

    # 3. Agar JSON mein bullets (•) hain
    if "•" in html_content:
        parts = re.split(r'•', html_content)
        for p in parts:
            clean_p = p.strip()
            if len(clean_p) > 20 and not clean_p.lower().startswith("the video"):
                bullets.append(clean_p)
        if bullets: return bullets

    return []


# ============================================
# BRIGHT DATA API CALL
# ============================================
async def fetch_product_from_brightdata(amazon_url: str) -> dict:
    # ✅ API URL sahi format mein hai
    api_url = f"{settings.BRIGHT_DATA_API_URL}?dataset_id={settings.BRIGHT_DATA_DATASET_ID}&include_errors=true"
    headers = {"Authorization": f"Bearer {settings.BRIGHT_DATA_API_KEY}", "Content-Type": "application/json"}
    
    # ✅ FORMAT RAW body ke andar daala hai
    body = [{"url": amazon_url, "format": "raw"}]

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(api_url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        raise BrightDataError(f"Bright Data Error: {str(e)}")

    raw = data[0] if isinstance(data, list) and len(data) > 0 else data
    if "error" in raw: raise BrightDataError(raw["error"])

    asin = raw.get("asin") or extract_asin_from_url(amazon_url)
    if not asin: raise BrightDataError("ASIN nahi mila")

    parent_asin = validate_parent_asin(raw.get("parent_asin"), asin)
    is_variation = bool(parent_asin)

    # Variations
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

    # Images
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

    cleaned_description = clean_description(raw.get("description"))
    
    # ✅ Bullets Extract (Raw HTML se)
    feature_bullets = []
    
    # Check if any string in raw contains feature-bullets
    html_content = ""
    for key, val in raw.items():
        if isinstance(val, str) and ("feature-bullets" in val or "<ul>" in val):
            html_content = val
            break
            
    if html_content:
        feature_bullets = extract_bullets_from_html(html_content)
        
    if not feature_bullets:
        possible_keys = ["feature_bullets", "feature-bullets", "about_this_item", "bullets"]
        for key in possible_keys:
            if isinstance(raw.get(key), list):
                feature_bullets = [str(b).strip() for b in raw.get(key) if b]
                break
            elif isinstance(raw.get(key), str) and "•" in raw.get(key):
                # Agar description ke andar direct • hai
                parts = re.split(r'•', raw.get(key))
                for p in parts:
                    if len(p.strip()) > 20 and not p.strip().lower().startswith("the video"):
                        feature_bullets.append(p.strip())
                break

    categories = parse_categories(raw)

    return {
        "asin": asin,
        "parent_asin": parent_asin,
        "is_variation": is_variation,
        "title": raw.get("title"),
        "brand": raw.get("brand"),
        "amazon_price": parse_price(raw.get("final_price") or raw.get("price") or raw.get("buybox_price")),
        "list_price": parse_price(raw.get("list_price") or raw.get("original_price")),
        "image_url": main_image,
        "images": unique_images,
        "specifications": specs,
        "description": cleaned_description,
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
def calculate_final_price(
    amazon_price: Optional[float],
    markup: Optional[float] = None,
    markup_type: Optional[str] = None,
    admin_price: Optional[float] = None,
    is_manual_override: bool = False,
    extra_percent: float = 0.0,
    tax_rate: float = 0.0,
) -> Optional[float]:
    if amazon_price is None: return admin_price
    if markup is None or markup_type is None: return admin_price

    markup = markup or 0.0
    extra_percent = extra_percent or 0.0
    tax_rate = tax_rate or 0.0

    if markup_type == "percent":
        base_price = amazon_price + (amazon_price * (markup / 100.0))
    elif markup_type == "both":
        base_price = amazon_price + markup + (amazon_price * (extra_percent / 100.0))
    else:
        base_price = amazon_price + markup

    final_price = base_price + (base_price * (tax_rate / 100.0))

    if is_manual_override and admin_price is not None:
        return round(max(admin_price, final_price), 2)

    return round(final_price, 2)