# app/services/shopify/description.py
# Product description builder with metafields HTML table
# + ✅ FIXED: Strict Title Removal & Bullet fallback

import logging

logger = logging.getLogger(__name__)


def _build_description_with_metafields(product_data: dict) -> str:
    """Amazon description + SAARE metafields HTML table."""

    # 1. DATA EXTRACT KAREIN
    raw_description = (product_data.get("description") or "").strip()
    title = (product_data.get("title") or "").strip()
    
    # Bullets ke liye alag alag keys check karein
    feature_bullets = (
        product_data.get("feature_bullets") or 
        product_data.get("bullets") or 
        product_data.get("about_item") or 
        []
    )

    # 2. STRICT TITLE FILTER (MAIN FIX)
    clean_description = raw_description
    
    # Check 1: Exact Title match
    if title and clean_description.lower() == title.lower():
        clean_description = ""
    # Check 2: Description starts with Title
    elif title and clean_description.lower().startswith(title.lower()):
        clean_description = clean_description[len(title):].strip()
    # Check 3: Agar description lambi hai, commas zyada hain aur words kam hain (Yeh Title hota hai)
    elif clean_description:
        comma_count = clean_description.count(',')
        word_count = len(clean_description.split())
        # Agar 25 words se kam hain aur 3 se zyada comma hain, to yeh pakka Title hai
        if word_count < 25 and comma_count >= 3:
            clean_description = ""

    # 3. ASLI BULLET POINTS KO FORMAT KAREIN
    final_desc_html = ""
    
    # Agar bullets available hain, to unhe priority dein
    if feature_bullets and isinstance(feature_bullets, list):
        bullets_html = "".join([
            f"<li style='margin-bottom: 8px;'>{str(b).strip()}</li>" 
            for b in feature_bullets if b and str(b).strip()
        ])
        if bullets_html:
            final_desc_html = f"<ul style='padding-left: 20px; margin-bottom: 20px;'>{bullets_html}</ul>"
    
    # Agar bullets nahi hain, lekin koi valid description bachi hai
    if not final_desc_html and clean_description:
        final_desc_html = f"<p>{clean_description}</p>"

    # Agar dono khali hain, to code table se pehle khali space nahi banayega
    if final_desc_html and not final_desc_html.endswith("<br>"):
        final_desc_html += "<br>"

    # 4. METAFIELDS TABLE (Same as before)
    FIELD_LABELS = {
        "asin": "ASIN", "brand": "Brand", "manufacturer": "Manufacturer",
        "rating": "Rating", "reviews_count": "Reviews",
        "availability": "Availability",
        "model_number": "Model Number", "item_model_number": "Item Model Number",
        "model_name": "Model Name", "part_number": "Part Number",
        "upc": "UPC", "ean": "EAN", "isbn": "ISBN",
        "item_dimensions": "Item Dimensions", "item_weight": "Item Weight",
        "package_dimensions": "Package Dimensions", "size": "Size",
        "color": "Color", "material_type": "Material", "style_name": "Style",
        "theme": "Theme", "department": "Department",
        "country_of_origin": "Country of Origin",
        "date_first_available": "Date First Available",
        "language": "Language",
        "reading_age": "Reading Age", "unit_count": "Unit Count",
        "number_of_pieces": "Number of Pieces",
        "care_instructions": "Care Instructions",
        "closure_type": "Closure Type", "fabric_type": "Fabric Type",
        "number_of_players": "Number of Players",
        "educational_objective": "Educational Objective",
        "power_source": "Power Source", "battery_types": "Battery Types",
        "operation_mode": "Operation Mode", "specific_uses": "Specific Uses",
        "special_features": "Special Features", "connectivity": "Connectivity",
        "processor": "Processor", "ram_technology": "RAM Technology",
        "memory": "Memory", "screen_size": "Screen Size",
        "resolution": "Resolution", "operating_system": "Operating System",
        "hard_disk": "Hard Disk", "graphics_coprocessor": "Graphics Coprocessor",
        "warranty": "Warranty",
    }

    fields_to_show = [
        "asin", "brand", "manufacturer", "model_number", "model_name", "part_number",
        "rating", "reviews_count", "availability", "color", "size", "material_type", "style_name",
        "item_dimensions", "item_weight", "package_dimensions", "department", "country_of_origin", 
        "date_first_available", "language", "reading_age", "unit_count", "number_of_pieces",
        "care_instructions", "closure_type", "fabric_type", "number_of_players", "educational_objective",
        "power_source", "battery_types", "operation_mode", "specific_uses", "special_features",
        "connectivity", "processor", "ram_technology", "memory", "screen_size", "resolution",
        "operating_system", "hard_disk", "graphics_coprocessor", "upc", "ean", "isbn", "theme", "warranty",
    ]

    rows = []
    seen = set()

    for key in fields_to_show:
        if key in seen:
            continue
        value = product_data.get(key)
        if value is None:
            continue
        
        val_str = str(value).strip()
        if not val_str or val_str.lower() in ["none", "nan", "n/a", "null"]:
            continue

        val_str = val_str.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        label = FIELD_LABELS.get(key, key.replace("_", " ").title())

        if key == "rating":
            try: val_str = f"{float(value)} ★ out of 5"
            except (ValueError, TypeError): pass
        elif key == "reviews_count":
            try: val_str = f"{int(float(value)):,}"
            except (ValueError, TypeError): pass

        rows.append(
            f'<tr>'
            f'<td style="padding:8px 12px;font-weight:600;background:#f6f6f7;border:1px solid #e1e3e5;width:180px;vertical-align:top;">{label}</td>'
            f'<td style="padding:8px 12px;border:1px solid #e1e3e5;vertical-align:top;">{val_str}</td>'
            f'</tr>'
        )
        seen.add(key)

    # 5. FINAL OUTPUT ASSEMBLY
    if rows:
        table_html = (
            '<hr style="margin:24px 0;border:none;border-top:1px solid #e1e3e5;">'
            '<h3 style="font-size:18px;font-weight:700;margin-bottom:12px;">📋 Product Details</h3>'
            '<table style="width:100%;border-collapse:collapse;font-size:14px;line-height:1.5;">'
            '<tbody>' + "".join(rows) + '</tbody></table>'
        )
        final_desc_html += table_html

    return final_desc_html