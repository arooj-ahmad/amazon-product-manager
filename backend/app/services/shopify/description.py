# app/services/shopify/description.py
# Product description builder with metafields HTML table
# + ✅ FIXED: Smart Filter for Garbage Data & Bullet Points Priority

import logging
import re

logger = logging.getLogger(__name__)


def _build_description_with_metafields(product_data: dict) -> str:
    """Amazon description + SAARE metafields HTML table."""

    # 1. DATA EXTRACT KAREIN
    raw_description = (product_data.get("description") or "").strip()
    title = (product_data.get("title") or "").strip()
    
    # Scraper alag alag keys use kar sakta hai bullets ke liye
    feature_bullets = (
        product_data.get("feature_bullets") or 
        product_data.get("bullets") or 
        product_data.get("about_item") or 
        []
    )

    final_desc_html = ""

    # 2. PRIORITY 1: ASLI BULLET POINTS (Agar scraper ne bheje hain)
    if feature_bullets and isinstance(feature_bullets, list) and len(feature_bullets) > 0:
        bullets_html = "".join([
            f"<li style='margin-bottom: 8px;'>{str(b).strip()}</li>" 
            for b in feature_bullets if b and str(b).strip()
        ])
        if bullets_html:
            final_desc_html = f"<ul style='padding-left: 20px; margin-bottom: 20px;'>{bullets_html}</ul>"

    # 3. PRIORITY 2: DESCRIPTION KO FILTER KARNA (Agar bullets nahi hain)
    if not final_desc_html and raw_description:
        
        # Gande data ko pehchanne ke liye Regex patterns
        bad_patterns = [
            r'\$\d+',               # Prices ($10)
            r'★',                   # Stars
            r'out of \d stars',     # Reviews text
            r'\d+\.\d+ out of',     # Ratings (4.4 out of)
            r'Quantity \d+',        # Quantity variations
            r'Size \(In\)',         # Size variations
            r'Add to Cart',         # Junk
            r'Buying Options',      # Junk
            r'Customer Reviews',    # Reviews heading
            r'See more product details'
        ]
        
        # Text ko lines mein tod kar check karein
        lines = raw_description.split('\n')
        valid_lines = []
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # Agar line title ke barabar hai, skip karein
            if title and line.lower() == title.lower():
                continue

            # Agar line mein ganda pattern hai, skip karein
            is_bad = False
            for pattern in bad_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    is_bad = True
                    break
            
            if not is_bad:
                valid_lines.append(line)
        
        clean_text = " ".join(valid_lines)
        
        # Agar saaf karne ke baad text bacha hai (kam az kam 5 words), to use karein
        if len(clean_text.split()) > 5:
            final_desc_html = f"<p>{clean_text}</p>"

    # Table se pehle space dalein
    if final_desc_html and not final_desc_html.endswith("<br>"):
        final_desc_html += "<br>"

    # 4. METAFIELDS TABLE
    FIELD_LABELS = {
        "asin": "ASIN", "brand": "Brand", "manufacturer": "Manufacturer",
        "rating": "Rating", "reviews_count": "Reviews", "availability": "Availability",
        "model_number": "Model Number", "item_model_number": "Item Model Number",
        "model_name": "Model Name", "part_number": "Part Number",
        "upc": "UPC", "ean": "EAN", "isbn": "ISBN", "item_dimensions": "Item Dimensions",
        "item_weight": "Item Weight", "package_dimensions": "Package Dimensions", "size": "Size",
        "color": "Color", "material_type": "Material", "style_name": "Style", "theme": "Theme",
        "department": "Department", "country_of_origin": "Country of Origin",
        "date_first_available": "Date First Available", "language": "Language",
        "reading_age": "Reading Age", "unit_count": "Unit Count", "number_of_pieces": "Number of Pieces",
        "care_instructions": "Care Instructions", "closure_type": "Closure Type",
        "fabric_type": "Fabric Type", "number_of_players": "Number of Players",
        "educational_objective": "Educational Objective", "power_source": "Power Source",
        "battery_types": "Battery Types", "operation_mode": "Operation Mode",
        "specific_uses": "Specific Uses", "special_features": "Special Features",
        "connectivity": "Connectivity", "processor": "Processor", "ram_technology": "RAM Technology",
        "memory": "Memory", "screen_size": "Screen Size", "resolution": "Resolution",
        "operating_system": "Operating System", "hard_disk": "Hard Disk",
        "graphics_coprocessor": "Graphics Coprocessor", "warranty": "Warranty",
    }

    fields_to_show = list(FIELD_LABELS.keys())

    rows = []
    seen = set()

    for key in fields_to_show:
        if key in seen: continue
        value = product_data.get(key)
        if value is None: continue
        
        val_str = str(value).strip()
        if not val_str or val_str.lower() in ["none", "nan", "n/a", "null"]: continue

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