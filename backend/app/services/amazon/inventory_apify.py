# ============================================
# app/services/amazon/inventory_apify.py
# ============================================

import logging

logger = logging.getLogger(__name__)

def check_availability_apify(raw: dict) -> tuple[bool, str, str]:
    """
    Apify ka strict check.
    Agar inStock True hai to 100, warna 0.
    """
    in_stock = raw.get("inStock")
    
    if in_stock is True:
        return True, "In Stock", "apify_in_stock_true"
        
    if isinstance(in_stock, str) and in_stock.lower() == "true":
        return True, "In Stock", "apify_in_stock_string_true"

    return False, "Out of Stock", "apify_in_stock_false_or_missing"