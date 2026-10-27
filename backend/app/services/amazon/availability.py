# app/services/amazon/availability.py
import logging

logger = logging.getLogger(__name__)

def check_availability(raw: dict) -> tuple[bool, str, str]:
    """
    Sirf Apify/BrightData ke 'inStock' field ko check karta hai.
    Agar true hai to (True, "In Stock", "reason"), warna (False, "Out of Stock", "reason").
    """
    in_stock = raw.get("inStock")
    
    if in_stock is True:
        return True, "In Stock", "in_stock_true"
        
    if isinstance(in_stock, str) and in_stock.lower() == "true":
        return True, "In Stock", "in_stock_string_true"

    return False, "Out of Stock", "in_stock_false_or_missing"
