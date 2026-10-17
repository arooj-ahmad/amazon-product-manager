# ============================================
# app/services/brightdata.py
# + ✅ NAYA: Feature Bullets (About this item) extract kiya
# ============================================

import logging
import re
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# ============================================
# CUSTOM EXCEPTION
# ============================================
class BrightDataError(Exception):
    """Bright Data API se related errors"""
    pass


# ============================================
# AMAZON URL SE ASIN NIKALEIN
# ============================================
def extract_asin_from_url(url: str) -> Optional[str]:
    """Amazon URL se ASIN nikalta hai."""
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


# ============================================
# PRICE PARSE HELPER
# ============================================
def parse_price(value) -> Optional[float]:
    """Price ko float mein parse karta hai."""
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


# ============================================
# ✅ PACKAGE DIMENSIONS PARSE
# ============================================
def parse_package_dimensions(package_dims_str: str) -> dict:
    """Parse package_dimensions string."""
    result = {}

    if not package_dims_str or not isinstance(package_dims_str, str):
        return result

    s = package_dims_str.strip()
    if not s:
        return result

    # Dimensions part
    dims_match = re.search(
        r"([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)\s*(inches|inch|in|cm|centimeters|centimeter|mm|millimeters|millimeter)?",
        s,
        re.IGNORECASE,
    )
    if dims_match:
        l, w, h = dims_match.group(1), dims_match.group(2), dims_match.group(3)
        unit = dims_match.group(4) or "inches"
        unit_lower = unit.lower()
        if unit_lower in ("in", "inch"):
            unit = "inches"
        elif unit_lower in ("centimeter", "centimeters"):
            unit = "cm"
        elif unit_lower in ("millimeter", "millimeters"):
            unit = "mm"

        result["item_dimensions"] = f"{l} x {w} x {h} {unit}"

    # Weight part
    weight_match = re.search(
        r"([\d.]+)\s*(ounces?|oz|pounds?|lbs?|lb|grams?|g|kilograms?|kg|milligrams?|mg)",
        s,
        re.IGNORECASE,
    )
    if weight_match:
        weight_value = weight_match.group(1)
        weight_unit = weight_match.group(2)
        result["item_weight"] = f"{weight_value} {weight_unit}"

    return result


# ============================================
# PARENT ASIN VALIDATION
# ============================================
def validate_parent_asin(parent_asin, asin: str) -> Optional[str]:
    """Parent ASIN validate karta hai."""
    if not parent_asin or parent_asin == "None" or parent_asin == "":
        return None
    if not isinstance(parent_asin, str):
        return None
    parent_asin = parent_asin.strip()
    if parent_asin == asin:
        return None
    if len(parent_asin) != 10:
        return None
    if not parent_asin.isalnum():
        return None
    return parent_asin.upper()


# ============================================
# ✅ AVAILABILITY CHECK
# ============================================
def check_availability(raw: dict) -> tuple[bool, str, str]:
    """Availability check karta hai."""
    shipping_msg = (
        raw.get("shipping_message")
        or raw.get("delivery_message")
        or raw.get("buybox_message")
        or ""
    )
    if isinstance(shipping_msg, str) and shipping_msg.strip():
        msg_lower = shipping_msg.lower()
        if any(kw in msg_lower for kw in [
            "cannot be shipped", "cannot ship", "not shippable",
            "delivery location", "not available for delivery",
        ]):
            return False, "Shipping Restricted", "shipping_message"

    add_to_cart = raw.get("add_to_cart_available")
    buybox = raw.get("buybox_available")
    in_stock = raw.get("in_stock")

    if add_to_cart is True: return True, "In Stock", "add_to_cart_available (True)"
    if add_to_cart is False: return False, "Out of Stock", "add_to_cart_available (False)"
    if buybox is True: return True, "In Stock", "buybox_available (True)"
    if buybox is False: return False, "Out of Stock", "buybox_available (False)"
    if in_stock is True: return True, "In Stock", "in_stock (True)"
    if in_stock is False: return False, "Out of Stock", "in_stock (False)"

    availability_text = (
        raw.get("availability") or raw.get("availabilityText")
        or raw.get("availability_text") or raw.get("stock_status")
        or raw.get("stockStatus") or ""
    )

    if not availability_text or not isinstance(availability_text, str) or not availability_text.strip():
        return False, "Unknown", "no_info"

    avail_lower = availability_text.lower().strip()

    out_of_stock_keywords = [
        "out of stock", "unavailable", "currently unavailable",
        "not available", "sold out", "temporarily out",
        "no disponible", "temporarily unavailable",
        "back order", "backorder", "cannot be shipped",
        "cannot ship", "not shippable", "delivery location",
        "not available for delivery",
    ]

    in_stock_keywords = [
        "in stock", "only", "usually ships", "ships within",
        "available", "in stock soon", "add to cart",
    ]

    if any(kw in avail_lower for kw in out_of_stock_keywords):
        return False, availability_text, "availability_text (out)"
    if any(kw in avail_lower for kw in in_stock_keywords):
        return True, availability_text, "availability_text (in)"

    return True, availability_text, "availability_text (unknown)"


# ============================================
# CATEGORIES PARSE
# ============================================
def parse_categories(raw: dict) -> list[str]:
    """Amazon response se categories nikalta hai."""
    categories: list[str] = []
    category_tree = raw.get("category_tree") or []
    
    if isinstance(category_tree, list):
        for cat in category_tree:
            if isinstance(cat, dict):
                name = cat.get("name") or cat.get("title")
                if name and isinstance(name, str):
                    categories.append(name.strip())
            elif isinstance(cat, str):
                categories.append(cat.strip())

    if not categories:
        raw_cats = raw.get("categories") or []
        if isinstance(raw_cats, list):
            for c in raw_cats:
                if isinstance(c, str):
                    categories.append(c.strip())
                elif isinstance(c, dict) and c.get("name"):
                    categories.append(c["name"].strip())

    if not categories:
        root = raw.get("root_bs_category")
        sub = raw.get("bs_category")
        if root and isinstance(root, str):
            categories.append(root.strip())
        if sub and isinstance(sub, str) and sub != root:
            categories.append(sub.strip())

    return [c for c in dict.fromkeys(categories) if c and len(c) < 100]


# ============================================
# ✅ STANDARD METAFIELDS FIELDS
# ============================================
def parse_standard_fields(raw: dict) -> dict:
    """Amazon response se saare standard metafield fields nikalta hai."""
    fields = {}
    fields["model_number"] = raw.get("model_number")
    fields["manufacturer"] = raw.get("manufacturer")
    fields["part_number"] = raw.get("part_number")
    fields["department"] = raw.get("department")
    fields["country_of_origin"] = raw.get("country_of_origin")
    fields["date_first_available"] = raw.get("date_first_available")

    package_dims_raw = raw.get("package_dimensions") or ""
    if package_dims_raw and isinstance(package_dims_raw, str):
        fields["package_dimensions"] = package_dims_raw.strip()
        parsed = parse_package_dimensions(package_dims_raw)
        if parsed.get("item_dimensions"):
            fields["item_dimensions"] = parsed["item_dimensions"]
        if parsed.get("item_weight"):
            fields["item_weight"] = parsed["item_weight"]

    product_details = raw.get("product_details") or []
    if isinstance(product_details, list):
        for item in product_details:
            if not isinstance(item, dict): continue
            field_type = (item.get("type") or "").strip().lower()
            field_value = item.get("value")
            if not field_value: continue
            value_str = str(field_value).strip()

            if field_type in ("item dimensions", "item dimensions l x w x h", "product dimensions"): fields["item_dimensions"] = value_str
            elif field_type in ("item weight", "shipping weight"): fields["item_weight"] = value_str
            elif field_type == "package dimensions": fields["package_dimensions"] = value_str
            elif field_type in ("material", "material type", "fabric type"): fields["material_type"] = value_str
            elif field_type == "color": fields["color"] = value_str
            elif field_type == "size": fields["size"] = value_str
            elif field_type == "theme": fields["theme"] = value_str
            elif field_type == "power source": fields["power_source"] = value_str
            elif field_type in ("battery type", "supported battery types", "batteries required"): fields["battery_types"] = value_str
            elif field_type == "operation mode": fields["operation_mode"] = value_str
            elif field_type in ("number of players", "players"): fields["number_of_players"] = value_str
            elif field_type == "educational objective": fields["educational_objective"] = value_str
            elif field_type in ("warranty description", "warranty"): fields["warranty"] = value_str
            elif field_type == "isbn-13": fields["isbn"] = value_str
            elif field_type == "language": fields["language"] = value_str
            elif field_type in ("reading age", "manufacturer recommended age"): fields["reading_age"] = value_str
            elif field_type == "number of pieces": fields["number_of_pieces"] = value_str
            elif field_type in ("unit count", "item package quantity"): fields["unit_count"] = value_str
            elif field_type in ("style name", "style"): fields["style_name"] = value_str
            elif field_type == "specific uses for product": fields["specific_uses"] = value_str
            elif field_type == "special feature": fields["special_features"] = value_str
            elif field_type in ("hardware interface", "connectivity technology"): fields["connectivity"] = value_str
            elif field_type in ("processor brand", "processor type"): fields["processor"] = value_str
            elif field_type in ("ram memory technology", "memory technology"): fields["ram_technology"] = value_str
            elif field_type in ("memory storage capacity", "ram memory installed size"): fields["memory"] = value_str
            elif field_type in ("screen size", "display size"): fields["screen_size"] = value_str
            elif field_type == "resolution": fields["resolution"] = value_str
            elif field_type in ("operating system", "os"): fields["operating_system"] = value_str
            elif field_type in ("hard disk description", "hard drive"): fields["hard_disk"] = value_str
            elif field_type == "graphics coprocessor": fields["graphics_coprocessor"] = value_str
            elif field_type in ("country of origin", "origin"): fields["country_of_origin"] = value_str
            elif field_type == "department": fields["department"] = value_str
            elif field_type == "brand": fields["brand"] = value_str
            elif field_type == "care instructions": fields["care_instructions"] = value_str
            elif field_type == "closure type": fields["closure_type"] = value_str
            elif field_type == "fabric type": fields["fabric_type"] = value_str
            elif field_type == "item model number": fields["item_model_number"] = value_str
            elif field_type == "model name": fields["model_name"] = value_str
            elif field_type == "upc": fields["upc"] = value_str
            elif field_type == "ean": fields["ean"] = value_str

    return {k: v for k, v in fields.items() if v is not None and str(v).strip() and str(v).strip() != "None"}


# ============================================
# ✅ TAGS PARSE — Sirf REAL tags
# ============================================
def parse_tags(raw: dict, categories: list[str]) -> list[str]:
    tags: list[str] = []
    seen_lower: set = set()

    def _add(tag: str):
        if not tag: return
        tag = str(tag).strip()
        if not tag or len(tag) < 3: return
        if len(tag) > 80: tag = tag[:77] + "..."
        low = tag.lower()
        if low in seen_lower: return
        seen_lower.add(low)
        tags.append(tag)

    for cat in categories:
        if cat and len(cat) < 60: _add(cat)

    raw_tags = raw.get("tags") or []
    if isinstance(raw_tags, list):
        for t in raw_tags:
            if isinstance(t, str) and t.strip(): _add(t.strip())

    product_details = raw.get("product_details") or []
    if isinstance(product_details, list):
        # Color
        for item in product_details:
            if isinstance(item, dict):
                field_type = (item.get("type") or "").strip().lower()
                value = (item.get("value") or "").strip()
                if field_type in ("color", "colour") and value:
                    _add(f"Color: {value}")
                    break
        # Size
        for item in product_details:
            if isinstance(item, dict):
                field_type = (item.get("type") or "").strip().lower()
                value = (item.get("value") or "").strip()
                if field_type == "size" and value:
                    _add(f"Size: {value}")
                    break
        # Theme
        for item in product_details:
            if isinstance(item, dict):
                field_type = (item.get("type") or "").strip().lower()
                value = (item.get("value") or "").strip()
                if field_type == "theme" and value:
                    _add(f"Theme: {value}")
                    break

    return tags[:15]


# ============================================
# ✅ CLEAN DESCRIPTION
# ============================================
def clean_description(description: str) -> str:
    if not description or not isinstance(description, str): return ""
    garbage_patterns = [
        r"[>›»]\s*See\s+more\s+product\s+details\.?", r"[>›»]\s*See\s+more\.?", r"[>›»]\s*Read\s+more\.?",
        r"[>›»]\s*Show\s+more\.?", r"[>›»]\s*View\s+more\.?", r"See\s+more\s+product\s+details\.?",
        r"Read\s+more\s+product\s+details\.?", r"Report\s+incorrect\s+product\s+information\.?",
        r"Show\s+more\s+product\s+details\.?", r"View\s+more\s+product\s+details\.?",
        r"\bSee\s+more\b", r"\bRead\s+more\b", r"\bShow\s+more\b", r"\bView\s+more\b",
    ]
    for pattern in garbage_patterns:
        description = re.sub(pattern, "", description, flags=re.IGNORECASE)
    description = re.sub(r"^\s*[>›»]\s*", "", description)
    description = re.sub(r"\s+[>›»]\s+", " ", description)
    description = re.sub(r"\s+", " ", description)
    description = re.sub(r"\s+([.,!?;:])", r"\1", description)
    description = description.strip()
    return "" if len(description) < 20 else description


# ============================================
# BRIGHT DATA API CALL
# ============================================
async def fetch_product_from_brightdata(amazon_url: str) -> dict:
    api_url = (
        f"{settings.BRIGHT_DATA_API_URL}"
        f"?dataset_id={settings.BRIGHT_DATA_DATASET_ID}"
        f"&include_errors=true"
    )
    headers = {"Authorization": f"Bearer {settings.BRIGHT_DATA_API_KEY}", "Content-Type": "application/json"}
    body = [{"url": amazon_url}]

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(api_url, headers=headers, json=body)
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise BrightDataError(f"Bright Data API error: {e.response.status_code}")
    except httpx.RequestError as e:
        raise BrightDataError(f"Bright Data connection error: {str(e)}")

    try:
        data = response.json()
    except Exception:
        raise BrightDataError("Invalid JSON response from Bright Data")

    if isinstance(data, list):
        if len(data) == 0: raise BrightDataError("Bright Data ne koi data return nahi kiya")
        raw = data[0]
    elif isinstance(data, dict):
        raw = data
    else:
        raise BrightDataError("Bright Data ne unexpected response bheja")

    if "error" in raw:
        raise BrightDataError(f"Bright Data error: {raw['error']}")

    # Extract fields
    asin = raw.get("asin") or extract_asin_from_url(amazon_url)
    if not asin: raise BrightDataError("ASIN nahi mila")

    parent_asin = validate_parent_asin(raw.get("parent_asin"), asin)
    is_variation = bool(parent_asin)

    variant_attributes = []
    if isinstance(raw.get("variant_attributes"), list):
        for attr in raw.get("variant_attributes"):
            if isinstance(attr, dict) and attr.get("name") and attr.get("value"):
                variant_attributes.append({"name": str(attr["name"]).strip(), "value": str(attr["value"]).strip()})

    variations = []
    if isinstance(raw.get("variations"), list):
        for v in raw.get("variations"):
            if isinstance(v, dict) and v.get("variation_name") and v.get("variation_value"):
                variations.append({"name": str(v["variation_name"]).strip(), "value": str(v["variation_value"]).strip()})

    amazon_price = parse_price(raw.get("final_price") or raw.get("price") or raw.get("buybox_price") or raw.get("initial_price"))
    list_price = parse_price(raw.get("list_price") or raw.get("original_price") or raw.get("initial_price"))

    rating_value = None
    rating_raw = raw.get("rating") or raw.get("average_rating") or raw.get("customer_rating")
    if rating_raw is not None:
        try:
            if isinstance(rating_raw, str):
                match = re.search(r"(\d+\.?\d*)", rating_raw)
                if match: rating_value = float(match.group(1))
            else: rating_value = float(rating_raw)
        except: pass

    reviews_count = None
    reviews_raw = raw.get("reviews_count") or raw.get("review_count")
    if reviews_raw is not None:
        try:
            if isinstance(reviews_raw, str):
                match = re.search(r"(\d[\d,]*)", reviews_raw)
                if match: reviews_count = int(match.group(1).replace(",", ""))
            else: reviews_count = int(reviews_raw)
        except: pass

    main_image = raw.get("image_url") or raw.get("image")
    unique_images = [main_image] if main_image else []
    if isinstance(raw.get("images"), list):
        for img in raw.get("images"):
            if isinstance(img, str) and img not in unique_images:
                unique_images.append(img)

    is_available, availability_text, _ = check_availability(raw)
    stock_quantity = 100 if is_available else 0

    specs = {}
    product_details = raw.get("product_details") or []
    if isinstance(product_details, list):
        for item in product_details:
            if isinstance(item, dict) and item.get("type") and item.get("value"):
                if item["type"] not in specs: specs[item["type"]] = str(item["value"]).strip()

    extra_fields = {"Rating": rating_value, "Reviews": reviews_count, "Availability": availability_text, "Seller": raw.get("seller_name")}
    for k, v in extra_fields.items():
        if v is not None and str(v).strip() and k not in specs: specs[k] = str(v).strip()

    categories = parse_categories(raw)
    tags = parse_tags(raw, categories)
    standard_fields = parse_standard_fields(raw)
    cleaned_description = clean_description(raw.get("description"))

    # ✅ NAYA: Feature Bullets Extract karein
    feature_bullets = raw.get("feature_bullets") or raw.get("feature-bullets") or []
    if not isinstance(feature_bullets, list):
        feature_bullets = []

    return {
        "asin": asin,
        "parent_asin": parent_asin,
        "is_variation": is_variation,
        "title": raw.get("title"),
        "brand": raw.get("brand"),
        "amazon_price": amazon_price,
        "list_price": list_price,
        "image_url": main_image,
        "images": unique_images,
        "specifications": specs,
        "description": cleaned_description,
        "feature_bullets": feature_bullets, # ✅ Feature bullets added
        "rating": rating_value,
        "reviews_count": reviews_count,
        "availability": str(availability_text) if availability_text else "In Stock",
        "is_available": is_available,
        "stock_quantity": stock_quantity,
        "variations": variations,
        "variant_attributes": variant_attributes,
        "categories": categories,
        "tags": tags,
        **standard_fields,
        "product_details": product_details,
    }


# ============================================
# ✅ CALCULATE FINAL PRICE
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