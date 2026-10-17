# app/services/shopify/description.py
# Product description builder with metafields HTML table
# + ✅ FIXED: Amazon Price aur Best Sellers Rank exclude
# + ✅ NAYA: Feature Bullets (About this item) added to description

import logging
import html

logger = logging.getLogger(__name__)


def _build_description_with_metafields(product_data: dict) -> str:
    """Amazon description + Feature Bullets + SAARE metafields HTML table."""
    
    # ✅ 1. Feature Bullets Extract & Format
    feature_bullets = product_data.get("feature_bullets") or []
    bullets_html = ""

    if feature_bullets and isinstance(feature_bullets, list):
        bullets_list_html = ""
        for b in feature_bullets:
            if b and str(b).strip():
                # HTML escape taake koi invalid character break na kare
                clean_b = html.escape(str(b).strip())
                
                # Shopify Rich text editor ke liye proper styling
                bullets_list_html += (
                    f'<li style="margin-bottom: 8px; font-size: 14px; color: #333333; line-height: 1.5;">'
                    f'{clean_b}'
                    f'</li>'
                )
        
        if bullets_list_html:
            bullets_html = (
                '<div style="margin-bottom: 24px;">'
                '<h3 style="font-size: 18px; font-weight: 700; color: #000000; margin-bottom: 12px; border-bottom: 1px solid #eeeeee; padding-bottom: 8px;">About this item</h3>'
                '<ul style="list-style-type: disc; padding-left: 20px; margin: 0;">'
                f'{bullets_list_html}'
                '</ul>'
                '</div>'
            )

    # ✅ 2. Main Description
    raw_description = product_data.get("description", "") or ""
    
    # Agar description mein pehle se HTML tags hain toh waise hi rakhein, warna paragraph mein wrap karein
    desc_html = ""
    if raw_description.strip():
        if "<" in raw_description and ">" in raw_description:
            desc_html = raw_description
        else:
            desc_html = f'<p style="font-size: 14px; line-height: 1.6; color: #333333;">{html.escape(raw_description)}</p>'

    # Combine: Pehle "About this item" (Bullets), Phir Main Description
    description = bullets_html + desc_html

    # ✅ 3. Product Details Table
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
        "availability",
        "color", "size", "material_type", "style_name",
        "item_dimensions", "item_weight", "package_dimensions",
        "department", "country_of_origin", "date_first_available",
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
        if value is None:
            continue
        val_str = str(value).strip()
        if not val_str or val_str == "None":
            continue

        val_str = html.escape(val_str)
        label = FIELD_LABELS.get(key, key.replace("_", " ").title())

        if key == "rating":
            try:
                r = float(value)
                val_str = f"{r} ★ out of 5"
            except (ValueError, TypeError):
                pass
        elif key == "reviews_count":
            try:
                c = int(float(value))
                val_str = f"{c:,}"
            except (ValueError, TypeError):
                pass

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