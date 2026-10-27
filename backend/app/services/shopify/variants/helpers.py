# app/services/shopify/variants/helpers.py
import logging
import re

logger = logging.getLogger(__name__)

def _parse_weight(weight_str) -> tuple:
    if not weight_str: return None, None
    s = str(weight_str).strip().lower()
    if not s or s == "none": return None, None
    match = re.search(r"([\d.]+)", s)
    if not match: return None, None
    try: value = float(match.group(1))
    except ValueError: return None, None
    if "kg" in s or "kilogram" in s: unit = "KILOGRAMS"
    elif "gram" in s or s.endswith("g") or " g" in s: unit = "GRAMS"
    elif "ounce" in s or " oz" in s or s.endswith("oz"): unit = "OUNCES"
    elif "milligram" in s or " mg" in s: value = value / 1000; unit = "GRAMS"
    else: unit = "POUNDS"
    return round(value, 4), unit

def _build_measurement(variant_data: dict) -> dict:
    weight_str = variant_data.get("weight") or variant_data.get("item_weight") or variant_data.get("package_weight")
    weight_value, weight_unit = _parse_weight(weight_str)
    if weight_value and weight_value > 0:
        return {"weight": {"value": weight_value, "unit": weight_unit}}
    return {}

def _normalize_compare_at_price(compare_at_price, price) -> str | None:
    if compare_at_price is None: return None
    try:
        cap = float(compare_at_price)
        price_f = float(price)
        if cap <= price_f:
            return None
        return f"{cap:.2f}"
    except (ValueError, TypeError):
        return None
