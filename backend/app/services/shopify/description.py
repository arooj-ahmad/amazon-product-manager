# app/services/shopify/description.py
# Product description builder with metafields HTML table
# + ✅ FIXED: Title duplication, Bullet points support, HTML formatting

import logging
import re

logger = logging.getLogger(__name__)


def _build_description_with_metafields(product_data: dict) -> str:
    """Amazon description + SAARE metafields HTML table."""

    # --- STEP 1: DESCRIPTION AUR BULLET POINTS KO HANDLE KARNA ---
    
    description = product_data.get("description", "") or ""
    feature_bullets = product_data.get("feature_bullets", [])
    
    # Check: Agar description bohot lambi hai aur usme Title jaisa text hai (e.g. comma separated words)
    # Ya phir description khali hai, to bullets use karein.
    
    is_description_valid = False
    if description and len(description) > 50:
        # Simple check: Agar description mein bullet points ya paragraph structure hai
        if "<p>" in description or "<ul>" in description or "<br>" in description:
            is_description_valid = True
        # Agar description sirf plain text hai aur bohot lamba title lag raha hai
        elif len(description.split()) < 30 and "," in description:
             # Yeh aksar title hota hai jo galti se description mein aa jata hai
             is_description_valid = False
        else:
            is_description_valid = True

    # Agar description valid nahi hai, to Bullets use karein
    if not is_description_valid and feature_bullets:
        if isinstance(feature_bullets, list):
            # List ko HTML list mein convert karein
            bullets_html = "".join([f"<li>{str(b).strip()}</li>" for b in feature_bullets if b])
            description = f"<ul style='margin-bottom: 20px;'>{bullets_html}</ul>"
        elif isinstance(feature_bullets, str):
            # Agar string hai to paragraph banayein
            description = f"<p>{feature_bullets}</p>"
    
    # Agar description abhi bhi khali hai, to default message
    if not description:
        description = ""

    # HTML Safety: Description ke baad line break dalein taake table chipke nahi
    if description and not description.endswith("<br>") and not description.endswith("</ul>"):
        description += "<br>"
    elif description.endswith("</ul>"):
        description += "<br>"

    # --- STEP 2: METAFIELDS TABLE BUILD KARNA ---

    FIELD_LABELS = {
        "asin": "ASIN", "brand": "Brand", "manufacturer": "Manufacturer",
        "rating": "Rating", "reviews_count": "Reviews",
        # ❌ amazon_price HATA DIYA
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
        # ❌ best_sellers_rank HATA DIYA
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
        "asin", "brand", "manufacturer",
        "model_number", "model_name", "part_number",
        "rating", "reviews_count",
        # ❌ amazon_price HATA DIYA
        "availability",
        "color", "size", "material_type", "style_name",
        "item_dimensions", "item_weight", "package_dimensions",
        "department", "country_of_origin", "date_first_available",
        # ❌ best_sellers_rank HATA DIYA
        "language", "reading_age",
        "unit_count", "number_of_pieces",
        "care_instructions", "closure_type", "fabric_type",
        "number_of_players", "educational_objective",
        "power_source", "battery_types", "operation_mode",
        "specific_uses", "special_features",
        "connectivity", "processor", "ram_technology",
        "memory", "screen_size", "resolution",
        "operating_system", "hard_disk", "graphics_coprocessor",
        "upc", "ean", "isbn", "theme", "warranty",
    ]

    rows = []
    seen = set()

    for key in fields_to_show:
        if key in seen:
            continue
        
        value = product_data.get(key)
        
        # Data Cleaning: None, Empty, ya 'nan' string ko skip karein
        if value is None:
            continue
            
        val_str = str(value).strip()
        if not val_str or val_str.lower() in ["none", "nan", "n/a", "null"]:
            continue

        # HTML Escaping (Security & Formatting)
        val_str = (
            val_str.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

        label = FIELD_LABELS.get(key, key.replace("_", " ").title())

        # Special Formatting for Rating
        if key == "rating":
            try:
                r = float(value)
                val_str = f"{r} ★ out of 5"
            except (ValueError, TypeError):
                pass
        
        # Special Formatting for Reviews Count
        elif key == "reviews_count":
            try:
                c = int(float(value))
                val_str = f"{c:,}"
            except (ValueError, TypeError):
                pass

        # Table Row HTML
        rows.append(
            f'<tr>'
            f'<td style="padding:8px 12px;font-weight:600;'
            f'background:#f6f6f7;border:1px solid #e1e3e5;'
            f'width:180px;vertical-align:top;">{label}</td>'
            f'<td style="padding:8px 12px;border:1px solid #e1e3e5;'
            f'vertical-align:top;">{val_str}</td>'
            f'</tr>'
        )
        seen.add(key)

    # --- STEP 3: FINAL ASSEMBLY ---
    
    if rows:
        table_html = (
            '<hr style="margin:24px 0;border:none;border-top:1px solid #e1e3e5;">'
            '<h3 style="font-size:18px;font-weight:700;margin-bottom:12px;">'
            '📋 Product Details</h3>'
            '<table style="width:100%;border-collapse:collapse;'
            'font-size:14px;line-height:1.5;">'
            '<tbody>'
            + "".join(rows) +
            '</tbody>'
            '</table>'
        )
        description += table_html

    return description