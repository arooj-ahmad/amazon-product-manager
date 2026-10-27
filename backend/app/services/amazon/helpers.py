# app/services/amazon/helpers.py
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

def extract_asin_from_url(url: str) -> Optional[str]:
    if not url or not isinstance(url, str): return None
    patterns = [r"/dp/([A-Z0-9]{10})", r"/gp/product/([A-Z0-9]{10})", r"/product/([A-Z0-9]{10})", r"asin=([A-Z0-9]{10})"]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match: return match.group(1)
    return None

def parse_price(value) -> Optional[float]:
    if value is None: return None
    try:
        if isinstance(value, str):
            cleaned = value.replace("$", "").replace(",", "").strip()
            if not cleaned: return None
            return float(cleaned)
        return float(value)
    except (ValueError, TypeError): return None

def parse_package_dimensions(package_dims_str: str) -> dict:
    result = {}
    if not package_dims_str or not isinstance(package_dims_str, str): return result
    s = package_dims_str.strip()
    if not s: return result

    dims_match = re.search(r"([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)\s*(inches|inch|in|cm|centimeters|centimeter|mm|millimeters|millimeter)?", s, re.IGNORECASE)
    if dims_match:
        l, w, h, unit = dims_match.group(1), dims_match.group(2), dims_match.group(3), (dims_match.group(4) or "inches")
        result["item_dimensions"] = f"{l} x {w} x {h} {unit}"

    weight_match = re.search(r"([\d.]+)\s*(ounces?|oz|pounds?|lbs?|lb|grams?|g|kilograms?|kg|milligrams?|mg)", s, re.IGNORECASE)
    if weight_match:
        result["item_weight"] = f"{weight_match.group(1)} {weight_match.group(2)}"
    return result

def validate_parent_asin(parent_asin, asin: str) -> Optional[str]:
    if not parent_asin or parent_asin == "None" or parent_asin == "": return None
    if not isinstance(parent_asin, str): return None
    parent_asin = parent_asin.strip()
    if parent_asin == asin or len(parent_asin) != 10 or not parent_asin.isalnum(): return None
    return parent_asin.upper()

def parse_standard_fields(raw: dict) -> dict:
    fields = {}
    fields["model_number"] = raw.get("model_number")
    fields["manufacturer"] = raw.get("manufacturer")
    fields["item_dimensions"] = raw.get("item_dimensions") or raw.get("product_dimensions") or ""
    fields["item_weight"] = raw.get("item_weight") or raw.get("product_weight") or ""

    package_dims_raw = raw.get("package_dimensions") or ""
    if package_dims_raw and isinstance(package_dims_raw, str):
        fields["package_dimensions"] = package_dims_raw.strip()
        parsed = parse_package_dimensions(package_dims_raw)
        if not fields["item_dimensions"] and parsed.get("item_dimensions"): fields["item_dimensions"] = parsed["item_dimensions"]
        if not fields["item_weight"] and parsed.get("item_weight"): fields["item_weight"] = parsed["item_weight"]

    product_details = raw.get("product_details") or []
    if isinstance(product_details, list):
        for item in product_details:
            if not isinstance(item, dict): continue
            field_type = (item.get("type") or "").strip().lower()
            field_value = item.get("value")
            if not field_value: continue
            value_str = str(field_value).strip()

            if field_type in ("item dimensions", "item dimensions l x w x h", "product dimensions"):
                if not fields["item_dimensions"]: fields["item_dimensions"] = value_str
            elif field_type in ("item weight", "shipping weight"):
                if not fields["item_weight"]: fields["item_weight"] = value_str
            elif field_type == "color":
                fields["color"] = value_str
            elif field_type == "material":
                fields["material_type"] = value_str

    return {k: v for k, v in fields.items() if v is not None and str(v).strip() and str(v).strip() != "None"}
