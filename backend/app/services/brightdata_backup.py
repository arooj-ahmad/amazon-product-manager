# ============================================
# app/services/brightdata.py
# Bright Data Scraper API se Amazon data fetch karne ke liye
# + Out of Stock tracking (IMPROVED)
# + Rating field (multiple names support)
# + Amazon Original Price + List Price extraction
# + Parent ASIN validation (fake ASIN skip)
# + Variations + Variant Attributes (for Shopify grouping)
# + ✅ NAYA: Availability check with fallback
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
    """
    Amazon URL se ASIN nikalta hai.
    """
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
    """
    Price ko float mein parse karta hai.
    "$49.99", "49.99", "1,299.00" sab handle karega.
    """
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
    """
    Parent ASIN validate karta hai.
    Returns valid parent_asin ya None.
    """
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
# ✅ NAYA HELPER: AVAILABILITY CHECK
# ============================================
def check_availability(raw: dict) -> tuple[bool, str, str]:
    """
    Availability check karta hai multiple fields se.
    Returns: (is_available, availability_text, source)
    """
    # ── Priority 1: add_to_cart_available (bool) ──
    add_to_cart = raw.get("add_to_cart_available")
    if isinstance(add_to_cart, bool):
        return add_to_cart, "In Stock" if add_to_cart else "Out of Stock", "add_to_cart_available"

    # ── Priority 2: buybox_available (bool) ──
    buybox = raw.get("buybox_available")
    if isinstance(buybox, bool):
        return buybox, "In Stock" if buybox else "Out of Stock", "buybox_available"

    # ── Priority 3: in_stock (bool) ──
    in_stock = raw.get("in_stock")
    if isinstance(in_stock, bool):
        return in_stock, "In Stock" if in_stock else "Out of Stock", "in_stock"

    # ── Priority 4: availability text ──
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
            "out of stock",
            "unavailable",
            "currently unavailable",
            "not available",
            "sold out",
            "temporarily out",
            "no disponible",
            "temporarily unavailable",
            "back order",
            "backorder",
        ]

        in_stock_keywords = [
            "in stock",
            "only",
            "usually ships",
            "ships within",
            "available",
            "in stock soon",
            "add to cart",
        ]

        if any(kw in avail_lower for kw in out_of_stock_keywords):
            return False, availability_text, "availability_text (out)"

        elif any(kw in avail_lower for kw in in_stock_keywords):
            return True, availability_text, "availability_text (in)"

        else:
            return True, availability_text, "availability_text (unknown)"

    # ── Priority 5: Default — AVAILABLE ──
    return True, "In Stock", "default"


# ============================================
# BRIGHT DATA API CALL
# ============================================
async def fetch_product_from_brightdata(amazon_url: str) -> dict:
    """
    Bright Data API se product data fetch karta hai.
    """
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

    # ========================================
    # ✅ DEBUG LOGS — Yeh zaroor dekho
    # ========================================
    logger.info("=" * 60)
    logger.info("=== BRIGHT DATA RAW RESPONSE ===")
    logger.info(f"ALL KEYS: {list(raw.keys())}")
    logger.info(f"--- AVAILABILITY FIELDS ---")
    logger.info(f"add_to_cart_available: {raw.get('add_to_cart_available')}")
    logger.info(f"buybox_available: {raw.get('buybox_available')}")
    logger.info(f"in_stock: {raw.get('in_stock')}")
    logger.info(f"availability: {raw.get('availability')}")
    logger.info(f"availabilityText: {raw.get('availabilityText')}")
    logger.info(f"availability_text: {raw.get('availability_text')}")
    logger.info(f"stock_status: {raw.get('stock_status')}")
    logger.info(f"stockStatus: {raw.get('stockStatus')}")
    logger.info(f"--- PRICE FIELDS ---")
    logger.info(f"final_price: {raw.get('final_price')}")
    logger.info(f"price: {raw.get('price')}")
    logger.info(f"list_price: {raw.get('list_price')}")
    logger.info("=" * 60)

    # Extract fields
    asin = raw.get("asin") or extract_asin_from_url(amazon_url)
    if not asin:
        raise BrightDataError("ASIN nahi mila - na response mein, na URL mein")

    # ========================================
    # ✅ PARENT ASIN VALIDATION
    # ========================================
    parent_asin_raw = raw.get("parent_asin") or None
    parent_asin = validate_parent_asin(parent_asin_raw, asin)
    is_variation = bool(parent_asin)

    if parent_asin:
        logger.info(f"✅ Parent ASIN accepted: {parent_asin}")
    else:
        logger.info(f"ℹ️ No valid parent ASIN → standalone product")

    # ========================================
    # ✅ VARIANT ATTRIBUTES
    # ========================================
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

    # ========================================
    # ✅ VARIATIONS
    # ========================================
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

    # ========================================
    # ✅ PRICE EXTRACTION
    # ========================================
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

    # ========================================
    # ✅ RATING EXTRACT
    # ========================================
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

    # ========================================
    # ✅ REVIEWS COUNT EXTRACT
    # ========================================
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

    # ========================================
    # Images
    # ========================================
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

    # ========================================
    # ✅ IMPROVED: AVAILABILITY CHECK
    # ========================================
    is_available, availability_text, source = check_availability(raw)
    logger.info(
        f"✅ Availability check: is_available={is_available}, "
        f"text='{availability_text}', source={source}"
    )

    # ========================================
    # Stock quantity
    # ========================================
    stock_quantity = raw.get("stock_quantity") or raw.get("stock") or 0
    try:
        stock_quantity = int(stock_quantity) if stock_quantity else 0
    except (ValueError, TypeError):
        stock_quantity = 0

    if not is_available:
        stock_quantity = 0
    elif stock_quantity == 0:
        stock_quantity = 100

    # ========================================
    # Specifications
    # ========================================
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
        "Rating": rating_value if rating_value is not None else raw.get("rating"),
        "Reviews": reviews_count if reviews_count is not None else raw.get("reviews_count"),
        "Availability": availability_text,
        "Seller": raw.get("seller_name") or raw.get("buybox_seller"),
        "Category": (
            raw.get("categories", [None])[-1]
            if raw.get("categories")
            else None
        ),
    }

    for key, value in extra_fields.items():
        if value is not None and str(value).strip() and key not in specs:
            specs[key] = str(value).strip()

    final_availability = str(availability_text) if availability_text else "In Stock"

    logger.info(
        f"Parsed product: ASIN={asin}, ParentASIN={parent_asin}, "
        f"AmazonPrice=${amazon_price}, ListPrice=${list_price}, "
        f"Rating={rating_value}, Reviews={reviews_count}, "
        f"Variations={len(variations)}, VarAttrs={len(variant_attributes)}, "
        f"Images={len(unique_images)}, Specs={len(specs)}, "
        f"Availability='{final_availability}', Available={is_available}, "
        f"Stock={stock_quantity}"
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
    """
    Final website price calculate karta hai.
    """
    if amazon_price is None:
        return admin_price

    markup = markup or 0.0

    if markup_type == "percent":
        auto_price = amazon_price * (1 + markup / 100.0)
    else:  # fixed
        auto_price = amazon_price + markup

    if is_manual_override and admin_price is not None:
        return round(max(admin_price, auto_price), 2)

    return round(auto_price, 2)