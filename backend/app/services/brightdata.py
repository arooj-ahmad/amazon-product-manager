# ============================================
# app/services/brightdata.py
# Bright Data Scraper API se Amazon data fetch karne ke liye
# + Out of Stock tracking (IMPROVED)
# + Rating field (multiple names support)
# + Amazon Original Price + List Price extraction
# + Parent ASIN validation (fake ASIN skip)
# + Variations + Variant Attributes (for Shopify grouping)
# + ✅ NAYA: Availability check with fallback
# + ✅ NAYA: Categories (Collections) + Tags (Features/Specs)
# + ✅ NAYA: Standard metafields fields (model, dimensions, etc.)
# + ✅ FIXED: Tags — CLEAN & PROFESSIONAL (no duplicates, no garbage)
# ============================================

import logging
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
    import re

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
# PARENT ASIN VALIDATION
# ============================================
def validate_parent_asin(parent_asin, asin: str) -> Optional[str]:
    """Parent ASIN validate karta hai."""
    if not parent_asin or parent_asin == "None" or parent_asin == "":
        return None

    if not isinstance(parent_asin, str):
        logger.info(f"⚠️ Parent ASIN not string: {parent_asin} → ignoring")
        return None

    parent_asin = parent_asin.strip()

    if parent_asin == asin:
        logger.info(f"⚠️ Parent ASIN same as ASIN ({asin}) → ignoring")
        return None

    if len(parent_asin) != 10:
        logger.info(f"⚠️ Parent ASIN length invalid: '{parent_asin}' → ignoring")
        return None

    if not parent_asin.isalnum():
        logger.info(f"⚠️ Parent ASIN not alphanumeric: '{parent_asin}' → ignoring")
        return None

    parent_asin = parent_asin.upper()

    logger.info(f"✅ Valid Parent ASIN: {parent_asin}")
    return parent_asin


# ============================================
# AVAILABILITY CHECK
# ============================================
def check_availability(raw: dict) -> tuple[bool, str, str]:
    """Availability check karta hai multiple fields se."""
    add_to_cart = raw.get("add_to_cart_available")
    if isinstance(add_to_cart, bool):
        return add_to_cart, "In Stock" if add_to_cart else "Out of Stock", "add_to_cart_available"

    buybox = raw.get("buybox_available")
    if isinstance(buybox, bool):
        return buybox, "In Stock" if buybox else "Out of Stock", "buybox_available"

    in_stock = raw.get("in_stock")
    if isinstance(in_stock, bool):
        return in_stock, "In Stock" if in_stock else "Out of Stock", "in_stock"

    availability_text = (
        raw.get("availability")
        or raw.get("availabilityText")
        or raw.get("availability_text")
        or raw.get("stock_status")
        or raw.get("stockStatus")
        or ""
    )

    if isinstance(availability_text, str) and availability_text.strip():
        avail_lower = availability_text.lower().strip()

        out_of_stock_keywords = [
            "out of stock", "unavailable", "currently unavailable",
            "not available", "sold out", "temporarily out",
            "no disponible", "temporarily unavailable",
            "back order", "backorder",
        ]

        in_stock_keywords = [
            "in stock", "only", "usually ships", "ships within",
            "available", "in stock soon", "add to cart",
        ]

        if any(kw in avail_lower for kw in out_of_stock_keywords):
            return False, availability_text, "availability_text (out)"
        elif any(kw in avail_lower for kw in in_stock_keywords):
            return True, availability_text, "availability_text (in)"
        else:
            return True, availability_text, "availability_text (unknown)"

    return True, "In Stock", "default"


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

    categories = [
        c for c in dict.fromkeys(categories)
        if c and len(c) < 100
    ]

    logger.info(f"✅ Parsed categories: {categories}")
    return categories


# ============================================
# ✅ NAYA HELPER: STANDARD METAFIELDS FIELDS
# ============================================
def parse_standard_fields(raw: dict) -> dict:
    """
    Amazon response se saare standard metafield fields nikalta hai.
    Yeh fields HAR product mein hote hain (95%+).
    """
    fields = {}

    # ── Identification ──
    fields["model_number"] = raw.get("model_number")
    fields["manufacturer"] = raw.get("manufacturer")
    fields["part_number"] = raw.get("part_number")

    # ── Department / Category ──
    fields["department"] = raw.get("department")
    fields["country_of_origin"] = raw.get("country_of_origin")
    fields["date_first_available"] = raw.get("date_first_available")

    # ── Product Details se specific fields ──
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

            # Map Amazon field types to our keys
            if field_type in ("item dimensions", "item dimensions l x w x h", "product dimensions"):
                fields["item_dimensions"] = value_str
            elif field_type in ("item weight", "item weight", "shipping weight"):
                fields["item_weight"] = value_str
            elif field_type == "package dimensions":
                fields["package_dimensions"] = value_str
            elif field_type in ("material", "material type", "fabric type"):
                fields["material_type"] = value_str
            elif field_type == "color":
                fields["color"] = value_str
            elif field_type == "size":
                fields["size"] = value_str
            elif field_type == "theme":
                fields["theme"] = value_str
            elif field_type == "power source":
                fields["power_source"] = value_str
            elif field_type in ("battery type", "supported battery types", "batteries required"):
                fields["battery_types"] = value_str
            elif field_type == "operation mode":
                fields["operation_mode"] = value_str
            elif field_type in ("number of players", "players"):
                fields["number_of_players"] = value_str
            elif field_type == "educational objective":
                fields["educational_objective"] = value_str
            elif field_type in ("warranty description", "warranty"):
                fields["warranty"] = value_str
            elif field_type == "best sellers rank":
                fields["best_sellers_rank"] = value_str
            elif field_type == "isbn-13":
                fields["isbn"] = value_str
            elif field_type == "language":
                fields["language"] = value_str
            elif field_type in ("reading age", "manufacturer recommended age"):
                fields["reading_age"] = value_str
            elif field_type == "number of pieces":
                fields["number_of_pieces"] = value_str
            elif field_type in ("unit count", "item package quantity"):
                fields["unit_count"] = value_str
            elif field_type in ("style name", "style"):
                fields["style_name"] = value_str
            elif field_type == "specific uses for product":
                fields["specific_uses"] = value_str
            elif field_type == "special feature":
                fields["special_features"] = value_str
            elif field_type in ("hardware interface", "connectivity technology"):
                fields["connectivity"] = value_str
            elif field_type in ("processor brand", "processor type"):
                fields["processor"] = value_str
            elif field_type in ("ram memory technology", "memory technology"):
                fields["ram_technology"] = value_str
            elif field_type in ("memory storage capacity", "ram memory installed size"):
                fields["memory"] = value_str
            elif field_type in ("screen size", "display size"):
                fields["screen_size"] = value_str
            elif field_type == "resolution":
                fields["resolution"] = value_str
            elif field_type in ("operating system", "os"):
                fields["operating_system"] = value_str
            elif field_type in ("hard disk description", "hard drive"):
                fields["hard_disk"] = value_str
            elif field_type == "graphics coprocessor":
                fields["graphics_coprocessor"] = value_str
            elif field_type in ("country of origin", "origin"):
                fields["country_of_origin"] = value_str
            elif field_type == "department":
                fields["department"] = value_str
            elif field_type == "brand":
                fields["brand"] = value_str
            elif field_type == "care instructions":
                fields["care_instructions"] = value_str
            elif field_type == "closure type":
                fields["closure_type"] = value_str
            elif field_type == "fabric type":
                fields["fabric_type"] = value_str
            elif field_type == "item model number":
                fields["item_model_number"] = value_str
            elif field_type == "model name":
                fields["model_name"] = value_str
            elif field_type == "upc":
                fields["upc"] = value_str
            elif field_type == "ean":
                fields["ean"] = value_str

    # Clean — remove None / empty / "None"
    fields = {
        k: v for k, v in fields.items()
        if v is not None and str(v).strip() and str(v).strip() != "None"
    }

    logger.info(f"✅ Parsed standard fields: {list(fields.keys())}")
    return fields


# ============================================
# ✅ IMPROVED: TAGS PARSE — Clean & Professional
# Amazon ke raw tags ko clean karke Shopify-ready banata hai
# - Duplicate hataata hai
# - "Color: Red" format use karta hai
# - "Customer Reviews: 4.04.0 out of 5 stars(..." jaisa garbage skip karta hai
# - Useless values (No, None, 0) skip karta hai
# - 25 tags max
# ============================================
def parse_tags(raw: dict, categories: list[str]) -> list[str]:
    """
    Amazon response se CLEAN aur USEFUL tags nikalta hai.
    
    Rules:
    - Colors → "Color: Red" (consistent prefix)
    - Specs → "Brand: Drayear" (key: value)
    - Categories → plain text
    - Rating → "Rating: 4.0 stars" (clean)
    - Skip useless values (No, None, 0, empty)
    - Max 25 tags
    """
    import re

    tags: list[str] = []
    seen_lower: set = set()

    def _add(tag: str):
        """Add tag with deduplication."""
        if not tag:
            return
        tag = tag.strip()
        if not tag:
            return
        if len(tag) > 80:
            tag = tag[:77] + "..."
        if len(tag) < 3:
            return
        low = tag.lower()
        if low in seen_lower:
            return
        seen_lower.add(low)
        tags.append(tag)

    # ─────────────────────────────────────────
    # 1. COLORS — "Color: Red" format
    # ─────────────────────────────────────────
    COLOR_KEYWORDS = {
        "red", "blue", "green", "yellow", "black", "white",
        "orange", "purple", "pink", "brown", "gray", "grey",
        "silver", "gold", "beige", "navy", "teal", "cyan",
        "magenta", "maroon", "olive", "lime", "aqua", "violet",
        "multicolor", "multi", "dark blue", "light blue",
        "dark green", "light green", "dark red", "light pink",
        "rose gold", "space gray", "space grey",
    }

    product_details = raw.get("product_details") or []
    if isinstance(product_details, list):
        for item in product_details:
            if not isinstance(item, dict):
                continue
            field_type = (item.get("type") or "").strip().lower()
            value = (item.get("value") or "").strip()
            if field_type in ("color", "colour") and value:
                if value.lower() not in seen_lower:
                    _add(f"Color: {value}")
            elif field_type in ("material", "material type") and value:
                _add(f"Material: {value}")
            elif field_type == "style" and value:
                _add(f"Style: {value}")
            elif field_type == "theme" and value:
                _add(f"Theme: {value}")

    features = raw.get("features") or []
    if isinstance(features, list):
        for f in features:
            if not isinstance(f, str):
                continue
            f_lower = f.lower()
            for color in COLOR_KEYWORDS:
                if color in f_lower and f_lower.startswith(color):
                    _add(f"Color: {color.title()}")
                    break

    # ─────────────────────────────────────────
    # 2. BRAND / MANUFACTURER
    # ─────────────────────────────────────────
    brand = raw.get("brand")
    if brand and isinstance(brand, str) and brand.strip():
        _add(f"Brand: {brand.strip()}")

    manufacturer = raw.get("manufacturer")
    if manufacturer and isinstance(manufacturer, str) and manufacturer.strip():
        if manufacturer.strip().lower() != (brand or "").strip().lower():
            _add(f"Manufacturer: {manufacturer.strip()}")

    # ─────────────────────────────────────────
    # 3. RATING — clean format
    # ─────────────────────────────────────────
    rating = raw.get("rating")
    if rating is not None:
        try:
            r = float(rating)
            if 0 < r <= 5:
                _add(f"Rating: {r:.1f} stars")
        except (ValueError, TypeError):
            pass

    # ─────────────────────────────────────────
    # 4. CATEGORIES — plain text
    # ─────────────────────────────────────────
    for cat in categories:
        if cat and len(cat) < 60:
            _add(cat)

    # ─────────────────────────────────────────
    # 5. KEY SPECS — from product_details
    # ─────────────────────────────────────────
    SPEC_LABELS = {
        "material": "Material",
        "material type": "Material",
        "fabric type": "Fabric",
        "style": "Style",
        "style name": "Style",
        "theme": "Theme",
        "pattern": "Pattern",
        "size": "Size",
        "department": "Department",
        "age range description": "Age Range",
        "recommended age": "Age Range",
        "manufacturer recommended age": "Age Range",
        "power source": "Power Source",
        "battery type": "Battery",
        "batteries required": "Battery",
        "number of pieces": "Pieces",
        "unit count": "Unit Count",
        "number of items": "Items",
        "item package quantity": "Pack Qty",
        "special feature": "Feature",
        "special features": "Feature",
        "additional features": "Feature",
        "operation mode": "Operation",
        "toy vehicle form": "Form",
        "educational objective": "Educational",
        "specific uses for product": "Uses",
        "included components": "Includes",
        "model number": "Model",
        "model name": "Model Name",
        "part number": "Part Number",
        "manufacturer part number": "Part Number",
    }

    USELESS_VALUES = {
        "", "no", "none", "n/a", "na", "0", "null",
        "not applicable", "false", "-",
    }

    seen_specs = set()
    if isinstance(product_details, list):
        for item in product_details:
            if not isinstance(item, dict):
                continue
            field_type = (item.get("type") or "").strip().lower()
            value = (item.get("value") or "").strip()

            if not value:
                continue
            if value.lower() in USELESS_VALUES:
                continue
            if field_type in ("color", "colour"):
                continue

            label = SPEC_LABELS.get(field_type)
            if not label:
                continue

            if label in seen_specs:
                continue
            seen_specs.add(label)

            value = re.sub(r"\s+", " ", value)
            if len(value) > 50:
                value = value[:47] + "..."

            _add(f"{label}: {value}")

    # ─────────────────────────────────────────
    # 6. ASIN
    # ─────────────────────────────────────────
    asin = raw.get("asin")
    if asin and isinstance(asin, str):
        _add(f"ASIN: {asin.strip()}")

    # ─────────────────────────────────────────
    # 7. UNIT COUNT from raw
    # ─────────────────────────────────────────
    unit_count = raw.get("unit_count")
    if unit_count:
        uc = str(unit_count).strip()
        uc_clean = re.sub(r"\s*(count|pcs|pieces|pack)\s*", "", uc, flags=re.IGNORECASE)
        if uc_clean and "Unit Count" not in seen_specs:
            _add(f"Unit Count: {uc_clean}")

    # ─────────────────────────────────────────
    # LIMIT: 25 tags max
    # ─────────────────────────────────────────
    tags = tags[:25]

    logger.info(f"✅ Parsed tags ({len(tags)}): {tags}")
    return tags


# ============================================
# BRIGHT DATA API CALL
# ============================================
async def fetch_product_from_brightdata(amazon_url: str) -> dict:
    """Bright Data API se product data fetch karta hai."""
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

    logger.info(f"Bright Data API call: {amazon_url}")

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(api_url, headers=headers, json=body)
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Bright Data HTTP error: {e.response.status_code} - {e.response.text}"
        )
        raise BrightDataError(f"Bright Data API error: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"Bright Data request error: {e}")
        raise BrightDataError(f"Bright Data connection error: {str(e)}")

    try:
        data = response.json()
    except Exception as e:
        logger.error(f"Bright Data JSON parse error: {e}")
        raise BrightDataError("Invalid JSON response from Bright Data")

    if isinstance(data, list):
        if len(data) == 0:
            logger.error("Bright Data empty array response")
            raise BrightDataError("Bright Data ne koi data return nahi kiya")
        raw = data[0]
    elif isinstance(data, dict):
        raw = data
    else:
        logger.error(f"Bright Data unexpected response type: {type(data)}")
        raise BrightDataError("Bright Data ne unexpected response bheja")

    if "error" in raw:
        logger.error(f"Bright Data error in response: {raw['error']}")
        raise BrightDataError(f"Bright Data error: {raw['error']}")

    # DEBUG LOGS
    logger.info("=" * 60)
    logger.info("=== BRIGHT DATA RAW RESPONSE ===")
    logger.info(f"ALL KEYS: {list(raw.keys())}")
    logger.info(f"--- AVAILABILITY FIELDS ---")
    logger.info(f"add_to_cart_available: {raw.get('add_to_cart_available')}")
    logger.info(f"buybox_available: {raw.get('buybox_available')}")
    logger.info(f"in_stock: {raw.get('in_stock')}")
    logger.info(f"availability: {raw.get('availability')}")
    logger.info(f"--- PRICE FIELDS ---")
    logger.info(f"final_price: {raw.get('final_price')}")
    logger.info(f"list_price: {raw.get('list_price')}")
    logger.info(f"--- CATEGORY FIELDS ---")
    logger.info(f"category_tree: {raw.get('category_tree')}")
    logger.info(f"--- STANDARD FIELDS ---")
    logger.info(f"model_number: {raw.get('model_number')}")
    logger.info(f"manufacturer: {raw.get('manufacturer')}")
    logger.info(f"department: {raw.get('department')}")
    logger.info(f"country_of_origin: {raw.get('country_of_origin')}")
    logger.info("=" * 60)

    # Extract fields
    asin = raw.get("asin") or extract_asin_from_url(amazon_url)
    if not asin:
        raise BrightDataError("ASIN nahi mila - na response mein, na URL mein")

    # Parent ASIN
    parent_asin_raw = raw.get("parent_asin") or None
    parent_asin = validate_parent_asin(parent_asin_raw, asin)
    is_variation = bool(parent_asin)

    # Variant attributes
    variant_attrs_raw = raw.get("variant_attributes") or []
    variant_attributes = []
    if isinstance(variant_attrs_raw, list):
        for attr in variant_attrs_raw:
            if isinstance(attr, dict):
                name = attr.get("name") or ""
                value = attr.get("value") or ""
                if name and value:
                    variant_attributes.append({
                        "name": str(name).strip(),
                        "value": str(value).strip(),
                    })

    # Variations
    variations_raw = raw.get("variations") or []
    variations = []
    if isinstance(variations_raw, list):
        for v in variations_raw:
            if isinstance(v, dict):
                v_name = v.get("variation_name") or ""
                v_value = v.get("variation_value") or ""
                if v_name and v_value:
                    variations.append({
                        "name": str(v_name).strip(),
                        "value": str(v_value).strip(),
                    })

    # Price
    amazon_price_raw = (
        raw.get("final_price")
        or raw.get("price")
        or raw.get("buybox_price")
        or raw.get("initial_price")
    )
    amazon_price = parse_price(amazon_price_raw)

    list_price_raw = (
        raw.get("list_price")
        or raw.get("original_price")
        or raw.get("initial_price")
    )
    list_price = parse_price(list_price_raw)

    # Rating
    rating_raw = (
        raw.get("rating")
        or raw.get("average_rating")
        or raw.get("customer_rating")
        or raw.get("star_rating")
        or raw.get("rating_value")
        or raw.get("ratingValue")
        or raw.get("stars")
        or raw.get("review_rating")
    )

    rating_value = None
    if rating_raw is not None:
        try:
            if isinstance(rating_raw, str):
                import re
                match = re.search(r"(\d+\.?\d*)", rating_raw)
                if match:
                    rating_value = float(match.group(1))
            else:
                rating_value = float(rating_raw)
        except (ValueError, TypeError):
            rating_value = None

    # Reviews
    reviews_raw = (
        raw.get("reviews_count")
        or raw.get("review_count")
        or raw.get("ratings_count")
        or raw.get("total_reviews")
        or raw.get("num_reviews")
    )

    reviews_count = None
    if reviews_raw is not None:
        try:
            if isinstance(reviews_raw, str):
                import re
                match = re.search(r"(\d[\d,]*)", reviews_raw)
                if match:
                    reviews_count = int(match.group(1).replace(",", ""))
            else:
                reviews_count = int(reviews_raw)
        except (ValueError, TypeError):
            reviews_count = None

    # Images
    images_list = raw.get("images") or []
    if not isinstance(images_list, list):
        images_list = []

    main_image = raw.get("image_url") or raw.get("image")

    unique_images = []
    if main_image:
        unique_images.append(main_image)

    for img in images_list:
        if isinstance(img, str) and img not in unique_images:
            unique_images.append(img)

    if not main_image and unique_images:
        main_image = unique_images[0]

    # Availability
    is_available, availability_text, source = check_availability(raw)
    logger.info(
        f"✅ Availability: is_available={is_available}, text='{availability_text}'"
    )

    # Stock
    stock_quantity = raw.get("stock_quantity") or raw.get("stock") or 0
    try:
        stock_quantity = int(stock_quantity) if stock_quantity else 0
    except (ValueError, TypeError):
        stock_quantity = 0

    if not is_available:
        stock_quantity = 0
    elif stock_quantity == 0:
        stock_quantity = 100

    # Specifications
    specs = {}
    product_details = raw.get("product_details") or []
    if isinstance(product_details, list):
        for item in product_details:
            if isinstance(item, dict):
                key = item.get("type")
                value = item.get("value")
                if key and value and str(value).strip():
                    if key not in specs:
                        specs[key] = str(value).strip()

    extra_fields = {
        "Rating": rating_value,
        "Reviews": reviews_count,
        "Availability": availability_text,
        "Seller": raw.get("seller_name") or raw.get("buybox_seller"),
    }

    for key, value in extra_fields.items():
        if value is not None and str(value).strip() and key not in specs:
            specs[key] = str(value).strip()

    final_availability = str(availability_text) if availability_text else "In Stock"

    # ✅ Categories + Tags + Standard Fields
    categories = parse_categories(raw)
    tags = parse_tags(raw, categories)
    standard_fields = parse_standard_fields(raw)

    logger.info(
        f"Parsed product: ASIN={asin}, ParentASIN={parent_asin}, "
        f"AmazonPrice=${amazon_price}, Rating={rating_value}, "
        f"Reviews={reviews_count}, Categories={len(categories)}, "
        f"Tags={len(tags)}, StandardFields={len(standard_fields)}"
    )

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
        "description": raw.get("description"),
        "rating": rating_value,
        "reviews_count": reviews_count,
        "availability": final_availability,
        "is_available": is_available,
        "stock_quantity": stock_quantity,
        "variations": variations,
        "variant_attributes": variant_attributes,
        "categories": categories,
        "tags": tags,
        # ✅ NAYA: Standard metafields
        **standard_fields,
        # ✅ Raw product_details — auto-mapping ke liye
        "product_details": raw.get("product_details") or [],
    }


# ============================================
# CALCULATE FINAL PRICE
# ============================================
def calculate_final_price(
    amazon_price: Optional[float],
    markup: float = 2.0,
    markup_type: str = "fixed",
    admin_price: Optional[float] = None,
    is_manual_override: bool = False,
) -> Optional[float]:
    """Final website price calculate karta hai."""
    if amazon_price is None:
        return admin_price

    markup = markup or 0.0

    if markup_type == "percent":
        auto_price = amazon_price * (1 + markup / 100.0)
    else:
        auto_price = amazon_price + markup

    if is_manual_override and admin_price is not None:
        return round(max(admin_price, auto_price), 2)

    return round(auto_price, 2)