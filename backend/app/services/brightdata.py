# ============================================
# app/services/brightdata.py
# Bright Data Scraper API se Amazon data fetch karne ke liye
# + Out of Stock tracking (NEW)
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
# BRIGHT DATA API CALL
# ============================================
async def fetch_product_from_brightdata(amazon_url: str) -> dict:
    """
    Bright Data API se product data fetch karta hai.
    """
    # API URL with query params
    api_url = (
        f"{settings.BRIGHT_DATA_API_URL}"
        f"?dataset_id={settings.BRIGHT_DATA_DATASET_ID}"
        f"&include_errors=true"
    )

    # Headers
    headers = {
        "Authorization": f"Bearer {settings.BRIGHT_DATA_API_KEY}",
        "Content-Type": "application/json",
    }

    # Body
    body = [{"url": amazon_url}]

    logger.info(f"Bright Data API call: {amazon_url}")

    # API Call
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

    # Parse Response
    try:
        data = response.json()
    except Exception as e:
        logger.error(f"Bright Data JSON parse error: {e}")
        raise BrightDataError("Invalid JSON response from Bright Data")

    # Bright Data kabhi list, kabhi single object return karta hai
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

    # Check errors
    if "error" in raw:
        logger.error(f"Bright Data error in response: {raw['error']}")
        raise BrightDataError(f"Bright Data error: {raw['error']}")

    # Extract fields
    asin = raw.get("asin") or extract_asin_from_url(amazon_url)
    if not asin:
        raise BrightDataError("ASIN nahi mila - na response mein, na URL mein")

    parent_asin = raw.get("parent_asin") or None
    is_variation = bool(parent_asin)

    # Price
    amazon_price = (
        raw.get("final_price")
        or raw.get("price")
        or raw.get("buybox_price")
        or raw.get("initial_price")
    )

    if amazon_price is not None:
        try:
            if isinstance(amazon_price, str):
                amazon_price = float(
                    amazon_price.replace("$", "").replace(",", "").strip()
                )
            else:
                amazon_price = float(amazon_price)
        except (ValueError, TypeError):
            logger.warning(f"Price parse fail: {amazon_price}")
            amazon_price = None

    # ----------------------------------------
    # Images extract karo
    # ----------------------------------------
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

    # ----------------------------------------
    # ✅ NAYA: Availability extract karo
    # ========================================
    # ✅ IMPROVED: Amazon "Add to Cart" check
    # ========================================
    availability_text = (
        raw.get("availability")
        or raw.get("availabilityText")
        or raw.get("availability_text")
        or ""
    )

    # Priority 1: Direct boolean fields (sabse reliable)
    add_to_cart_available = raw.get("add_to_cart_available")
    buybox_available = raw.get("buybox_available")

    if isinstance(add_to_cart_available, bool):
        is_available = add_to_cart_available
        logger.info(f"Using add_to_cart_available: {is_available}")

    elif isinstance(buybox_available, bool):
        is_available = buybox_available
        logger.info(f"Using buybox_available: {is_available}")

    elif isinstance(availability_text, str) and availability_text:
        # Priority 2: Text parsing
        avail_lower = availability_text.lower()
        out_of_stock_keywords = [
            "out of stock",
            "unavailable",
            "currently unavailable",
            "not available",
            "sold out",
            "temporarily out",
            "no disponible",
        ]
        is_available = not any(kw in avail_lower for kw in out_of_stock_keywords)
        logger.info(
            f"Using availability text: {availability_text} → {is_available}"
        )

    else:
        # Priority 3: Data missing → safe default
        is_available = False
        logger.warning("No availability data → defaulting to OUT OF STOCK")

    # ----------------------------------------
    # Stock quantity
    # ----------------------------------------
    stock_quantity = raw.get("stock_quantity") or raw.get("stock") or 0
    try:
        stock_quantity = int(stock_quantity) if stock_quantity else 0
    except (ValueError, TypeError):
        stock_quantity = 0

    # ✅ NAYA: Agar out of stock hai toh stock 0 force karo
    if not is_available:
        stock_quantity = 0
        logger.info("Product out of stock → stock_quantity forced to 0")
    # ----------------------------------------
    # Specifications extract karo
    # ----------------------------------------
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

    # Extra useful fields
    extra_fields = {
        "Rating": raw.get("rating"),
        "Reviews": raw.get("reviews_count"),
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

    logger.info(
        f"Parsed product: ASIN={asin}, Price=${amazon_price}, "
        f"Images={len(unique_images)}, Specs={len(specs)}, "
        f"Availability={availability_text}, Available={is_available}"
    )

    return {
        "asin": asin,
        "parent_asin": parent_asin,
        "is_variation": is_variation,
        "title": raw.get("title"),
        "brand": raw.get("brand"),
        "amazon_price": amazon_price,
        "image_url": main_image,
        "images": unique_images,
        "specifications": specs,
        "description": raw.get("description"),
        
        "availability": str(availability_text),
        "is_available": is_available,
        "stock_quantity": stock_quantity,
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

    - fixed:   amazon_price + markup
    - percent: amazon_price * (1 + markup/100)

    Manual override case:
    - Agar admin ne manually price set ki hai, toh max(admin_price, auto_price) return karo

    Examples:
        calculate_final_price(35.99, 2.0, "fixed")     → 37.99
        calculate_final_price(35.99, 10, "percent")    → 39.59
        calculate_final_price(35.99, 5.0, "fixed", 50.0, True) → 50.00
    """
    if amazon_price is None:
        return admin_price

    markup = markup or 0.0

    # ✅ Markup type ke hisaab se calculate
    if markup_type == "percent":
        auto_price = amazon_price * (1 + markup / 100.0)
    else:  # fixed
        auto_price = amazon_price + markup

    # Manual override — agar admin ne khud price di hai
    if is_manual_override and admin_price is not None:
        return round(max(admin_price, auto_price), 2)

    return round(auto_price, 2)