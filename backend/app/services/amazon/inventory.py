# ============================================
# app/services/amazon/inventory.py
# ============================================

import logging

logger = logging.getLogger(__name__)

def check_availability_apify(raw: dict) -> tuple[bool, str, str]:
    """Apify Logic for Add Product"""
    in_stock = raw.get("inStock")
    if in_stock is True:
        return True, "In Stock", "apify_in_stock_true"
    if isinstance(in_stock, str) and in_stock.lower() == "true":
        return True, "In Stock", "apify_in_stock_string_true"
    return False, "Out of Stock", "apify_in_stock_false_or_missing"


def check_availability_brightdata(raw: dict) -> tuple[bool, str, str]:
    """
    Bright Data ke liye Perfect Check.
    (Buybox aur Delivery check karta hai, kyunki Out of Stock mein yeh khali hote hain)
    """
    
    # 1. Text check (Agar text mein Out of Stock likha hai)
    avail_text = str(raw.get("availability") or raw.get("availability_text") or "").strip().lower()
    if "out of stock" in avail_text or "unavailable" in avail_text or "currently unavailable" in avail_text:
        return False, "Out of Stock", "bd_text_out_of_stock"

    # 2. Buybox Check (Sab se pakka tareeqa)
    # Agar product Out of Stock hai, toh buybox aur delivery khali hoti hai.
    buybox = raw.get("buybox_prices")
    delivery = raw.get("delivery")
    
    if buybox is None and delivery is None:
        return False, "Out of Stock", "bd_no_buybox_or_delivery"

    # 3. Agar buybox ya delivery mojood hai, matlab Add to Cart button hai -> In Stock
    if buybox or delivery:
        return True, "In Stock", "bd_has_buybox_or_delivery"

    # 4. Fallback: Agar text mein "In Stock" likha hai
    if "in stock" in avail_text:
        return True, "In Stock", "bd_text_in_stock"

    # 5. Agar sab fail, toh Out of Stock maan lo
    logger.warning(f"⚠️ BD: Availability unknown. Keys: {list(raw.keys())}")
    return False, "Out of Stock", "bd_unknown_default"