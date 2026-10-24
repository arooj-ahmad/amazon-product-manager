# ============================================
# app/services/amazon/inventory.py
# ============================================

import logging

logger = logging.getLogger(__name__)

def check_availability_apify(raw: dict) -> tuple[bool, str, str]:
    """
    Sirf Apify ke 'inStock' field ko check karta hai.
    """
    in_stock = raw.get("inStock")
    
    if in_stock is True:
        return True, "In Stock", "apify_in_stock_true"
        
    if isinstance(in_stock, str) and in_stock.lower() == "true":
        return True, "In Stock", "apify_in_stock_string_true"

    return False, "Out of Stock", "apify_in_stock_false_or_missing"


def check_availability_brightdata(raw: dict) -> tuple[bool, str, str]:
    """
    Bright Data ke liye Strict Check.
    """
    # 1. Text check
    avail_text = str(raw.get("availability") or raw.get("availability_text") or "").strip().lower()
    
    if "in stock" in avail_text and "out of stock" not in avail_text:
        return True, raw.get("availability") or "In Stock", "brightdata_text_in_stock"
    
    if "out of stock" in avail_text or "unavailable" in avail_text or "currently unavailable" in avail_text:
        return False, "Out of Stock", "brightdata_text_out_of_stock"
        
    if "available" in avail_text and "unavailable" not in avail_text:
         return True, raw.get("availability") or "In Stock", "brightdata_text_available"

    # 2. Quantity check
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

    # 3. Delivery / Buybox check
    buybox = raw.get("buybox") or raw.get("buybox_price")
    delivery = raw.get("delivery_info") or raw.get("delivery")
    
    if buybox or delivery:
         return True, "In Stock", "brightdata_has_buybox_or_delivery"

    # ✅ 4. Default (No price check at all!)
    logger.warning(f"⚠️ BD: Availability unknown. Returning None to trigger Smart Fallback. Keys: {list(raw.keys())}")
    # Hum None return karenge taake Scheduler apna Smart Fallback laga sake
    return None, "Unknown", "brightdata_unknown_trigger_fallback"