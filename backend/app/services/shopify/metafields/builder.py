# app/services/shopify/metafields/builder.py
import logging
from app.services.shopify._helpers import _slugify_key

logger = logging.getLogger(__name__)

def _build_all_metafields(product_data: dict) -> list:
    metafields = []
    seen_keys = set()

    def _add(key: str, value, mf_type: str = "single_line_text_field"):
        if not key or key in seen_keys or value is None: 
            return
        
        val_str = str(value).strip()
        if not val_str or val_str == "None" or val_str == "null": 
            return
        
        if len(val_str) > 5000: 
            val_str = val_str[:5000]
            
        metafields.append({
            "namespace": "custom", 
            "key": key, 
            "value": val_str, 
            "type": mf_type
        })
        seen_keys.add(key)

    # ── 1. Core Fields ──
    _add("asin", product_data.get("asin"))
    _add("brand", product_data.get("brand"))
    _add("manufacturer", product_data.get("manufacturer"))
    _add("availability", product_data.get("availability"))
    
    # ✅ Rating aur Reviews ko safe parse karein
    rating = product_data.get("rating")
    if rating is not None:
        try:
            clean_rating = float(str(rating).replace(",", "").strip().split()[0])
            _add("rating", str(clean_rating), "number_decimal")
        except (ValueError, TypeError, IndexError): pass
        
    reviews = product_data.get("reviews_count")
    if reviews is not None:
        try:
            clean_reviews = int(str(reviews).replace(",", "").strip().split()[0])
            _add("reviews_count", str(clean_reviews), "number_integer")
        except (ValueError, TypeError, IndexError): pass
        
    amazon_price = product_data.get("amazon_price")
    if amazon_price is not None:
        try: _add("amazon_price", str(float(amazon_price)), "number_decimal")
        except: pass

    # ── 2. Physical Attributes ──
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

    # ── 3. Amazon Specs Dictionary (Direct) ──
    # ✅ FIX: Agar Apify direct specs dictionary bhejta hai
    specs_dict = product_data.get("specifications") or {}
    if isinstance(specs_dict, dict):
        for k, v in specs_dict.items():
            if not k or v is None: continue
            key = _slugify_key(str(k))
            if key and len(key) > 2:
                _add(key, str(v).strip(), "single_line_text_field")

    # ── 4. Dynamic Product Details ──
    # ✅ FIX: product_details array se saari fields uthayein
    product_details = product_data.get("product_details") or []
    if isinstance(product_details, list):
        for item in product_details:
            if not isinstance(item, dict): continue
            field_type = item.get("type") or ""
            field_value = item.get("value")
            if not field_type or field_value is None: continue
            
            key = _slugify_key(field_type)
            if not key or len(key) < 3: continue
            
            val_str = str(field_value).strip()
            if not val_str or val_str == "None": continue
            
            # Type decide karo
            if len(val_str) > 100: 
                mf_type = "multi_line_text_field"
            elif val_str.replace(".", "").replace("-", "").isdigit(): 
                mf_type = "number_decimal" if "." in val_str else "number_integer"
            else: 
                mf_type = "single_line_text_field"
                
            _add(key, val_str, mf_type)

    # ── 5. Fallback (Agar specs bilkul khali hain) ──
    if len(metafields) < 4: # Sirf ASIN, Brand, etc.
        for attr in (product_data.get("variant_attributes") or []):
            if isinstance(attr, dict) and attr.get("name") and attr.get("value"):
                key = _slugify_key(attr["name"])
                if key: _add(key, attr["value"])

    logger.info(f"   Built {len(metafields)} metafields")
    return metafields