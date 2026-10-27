# app/services/shopify/metafields/builder.py
import logging
from app.services.shopify._helpers import _slugify_key

logger = logging.getLogger(__name__)

def _build_all_metafields(product_data: dict) -> list:
    metafields, seen_keys = [], set()

    def _add(key: str, value, mf_type: str = "single_line_text_field"):
        if key in seen_keys or value is None: return
        val_str = str(value).strip()
        if not val_str or val_str == "None": return
        if len(val_str) > 5000: val_str = val_str[:5000]
        metafields.append({"namespace": "custom", "key": key, "value": val_str, "type": mf_type})
        seen_keys.add(key)

    _add("asin", product_data.get("asin"))
    _add("brand", product_data.get("brand"))
    _add("manufacturer", product_data.get("manufacturer"))
    
    if product_data.get("rating") is not None:
        try: _add("rating", str(float(product_data["rating"])), "number_decimal")
        except: pass
    if product_data.get("reviews_count") is not None:
        try: _add("reviews_count", str(int(product_data["reviews_count"])), "number_integer")
        except: pass
    if product_data.get("amazon_price") is not None:
        try: _add("amazon_price", str(float(product_data["amazon_price"])), "number_decimal")
        except: pass

    _add("availability", product_data.get("availability"))
    _add("model_number", product_data.get("model_number"))
    _add("item_model_number", product_data.get("item_model_number"))
    _add("model_name", product_data.get("model_name"))
    _add("part_number", product_data.get("part_number"))
    _add("upc", product_data.get("upc"))
    _add("ean", product_data.get("ean"))
    _add("isbn", product_data.get("isbn"))
    _add("item_dimensions", product_data.get("item_dimensions"))
    _add("item_weight", product_data.get("item_weight"))
    _add("package_dimensions", product_data.get("package_dimensions"))
    _add("size", product_data.get("size"))
    _add("color", product_data.get("color"))
    _add("material_type", product_data.get("material_type"))
    _add("style_name", product_data.get("style_name"))
    _add("theme", product_data.get("theme"))
    _add("department", product_data.get("department"))
    _add("country_of_origin", product_data.get("country_of_origin"))
    _add("date_first_available", product_data.get("date_first_available"))
    _add("best_sellers_rank", product_data.get("best_sellers_rank"))
    _add("language", product_data.get("language"))
    _add("reading_age", product_data.get("reading_age"))
    _add("unit_count", product_data.get("unit_count"))
    _add("number_of_pieces", product_data.get("number_of_pieces"), "number_integer")
    _add("care_instructions", product_data.get("care_instructions"), "multi_line_text_field")
    _add("closure_type", product_data.get("closure_type"))
    _add("fabric_type", product_data.get("fabric_type"))
    _add("number_of_players", product_data.get("number_of_players"))
    _add("educational_objective", product_data.get("educational_objective"))
    _add("power_source", product_data.get("power_source"))
    _add("battery_types", product_data.get("battery_types"))
    _add("operation_mode", product_data.get("operation_mode"))
    _add("specific_uses", product_data.get("specific_uses"))
    _add("special_features", product_data.get("special_features"))
    _add("connectivity", product_data.get("connectivity"))
    _add("processor", product_data.get("processor"))
    _add("ram_technology", product_data.get("ram_technology"))
    _add("memory", product_data.get("memory"))
    _add("screen_size", product_data.get("screen_size"))
    _add("resolution", product_data.get("resolution"))
    _add("operating_system", product_data.get("operating_system"))
    _add("hard_disk", product_data.get("hard_disk"))
    _add("graphics_coprocessor", product_data.get("graphics_coprocessor"))
    _add("warranty", product_data.get("warranty"), "multi_line_text_field")

    for item in (product_data.get("product_details") or []):
        if not isinstance(item, dict): continue
        field_type, field_value = item.get("type") or "", item.get("value")
        if not field_type or field_value is None: continue
        key = _slugify_key(field_type)
        if not key or len(key) < 3: continue
        val_str = str(field_value).strip()
        if not val_str or val_str == "None": continue
        
        if len(val_str) > 100: mf_type = "multi_line_text_field"
        elif val_str.replace(".", "").replace("-", "").isdigit(): mf_type = "number_decimal" if "." in val_str else "number_integer"
        else: mf_type = "single_line_text_field"
        _add(key, val_str, mf_type)

    return metafields
