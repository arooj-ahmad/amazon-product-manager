# ============================================
# app/services/amazon/inventory.py
# ============================================

import logging

logger = logging.getLogger(__name__)

def check_availability_apify(raw: dict) -> tuple[bool, str, str]:
    """
    Sirf Apify ke 'inStock' field ko check karta hai.
    (Strict logic for Add Product)
    """
    in_stock = raw.get("inStock")
    
    if in_stock is True:
        return True, "In Stock", "apify_in_stock_true"
        
    if isinstance(in_stock, str) and in_stock.lower() == "true":
        return True, "In Stock", "apify_in_stock_string_true"

    return False, "Out of Stock", "apify_in_stock_false_or_missing"


def check_availability_brightdata(raw: dict) -> tuple[bool, str, str]:
    """
    Bright Data ke apne fields (availability text, stock qty) ko check karta hai.
    (For Scheduler)
    """
    # 1. Text check (In Stock / Out of Stock)
    avail_text = str(raw.get("availability") or raw.get("availability_text") or "").strip().lower()
    
    if "in stock" in avail_text and "out of stock" not in avail_text:
        return True, raw.get("availability") or "In Stock", "brightdata_text_in_stock"
    
    if "out of stock" in avail_text or "unavailable" in avail_text or "currently unavailable" in avail_text:
        return False, "Out of Stock", "brightdata_text_out_of_stock"
        
    if "available" in avail_text and "unavailable" not in avail_text:
         return True, raw.get("availability") or "In Stock", "brightdata_text_available"

    # 2. Quantity check (Agar number mila hai)
    stock_qty = raw.get("stock") or raw.get("stock_quantity") or raw.get("inventory_quantity")
    
    if stock_qty is not None:
        try:
            qty = int(float(stock_qty))
            if qty > 0:
                return True, "In Stock", "brightdata_qty_greater_than_0"
            else:
                return False, "Out of Stock", "brightdata_qty_0"
        except (ValueError, TypeError):
            pass

    # 3. Fallback: Agar price mojood hai aur out of stock nahi likha
    if raw.get("final_price") or raw.get("price"):
        return True, "In Stock", "brightdata_has_price"

    # 4. Default Out of Stock
    logger.warning(f"⚠️ BD Availability could not be determined. Keys: {list(raw.keys())}")
    return False, "Out of Stock", "brightdata_unknown_default"