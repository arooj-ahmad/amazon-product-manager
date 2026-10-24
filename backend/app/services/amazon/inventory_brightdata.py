# ============================================
# app/services/amazon/inventory_brightdata.py
# ============================================

import logging

logger = logging.getLogger(__name__)

def check_availability_brightdata(raw: dict) -> tuple[bool, str, str]:
    """
    Bright Data Strict Logic (Buybox aur Delivery check)
    """
    # 1. Direct fields check karo (Agar Bright Data future mein bheje)
    if raw.get("add_to_cart_available") is True:
        return True, "In Stock", "add_to_cart_available"
    if raw.get("buybox_available") is True:
        return True, "In Stock", "buybox_available"
    if raw.get("in_stock") is True:
        return True, "In Stock", "in_stock"

    # 2. Bright Data ka asal Buybox aur Delivery check
    buybox = raw.get("buybox_prices")
    delivery = raw.get("delivery")
    final_price = raw.get("final_price") or raw.get("price")

    # Agar buybox, delivery aur price teeno mojood hain -> In Stock
    if buybox and delivery and final_price:
        return True, "In Stock", "has_buybox_delivery_and_price"

    # 3. Text check (Agar availability text mein kuch likha hai)
    avail_text = str(raw.get("availability") or raw.get("stock_status") or "").strip().lower()
    
    if any(kw in avail_text for kw in ["out of stock", "unavailable", "not available", "sold out"]):
        return False, "Out of Stock", "text_out_of_stock"
        
    if "in stock" in avail_text:
        return True, "In Stock", "text_in_stock"

    # 4. Agar buybox/delivery/price mein se koi ek bhi missing hai, toh Out of Stock
    if not buybox or not delivery or not final_price:
        return False, "Out of Stock", "missing_buybox_delivery_or_price"

    # 5. Default
    logger.warning(f"⚠️ BD: Availability unknown for ASIN={raw.get('asin')}.")
    return False, "Out of Stock", "unknown_default"