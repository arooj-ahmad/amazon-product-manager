# ============================================
# app/services/amazon/inventory_apify.py
# ============================================

import logging

logger = logging.getLogger(__name__)

def check_availability_apify(raw: dict) -> tuple[bool, str, str]:
    """
    Apify ke liye simple logic: Hamesha In Stock (100).
    """
    return True, "In Stock", "apify_always_in_stock"