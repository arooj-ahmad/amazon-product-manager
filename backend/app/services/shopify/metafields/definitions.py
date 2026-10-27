# app/services/shopify/metafields/definitions.py
import logging
from app.services.shopify.helpers import shopify_graphql

logger = logging.getLogger(__name__)

METAFIELD_DEFINITIONS = {
    "asin": ("ASIN", "single_line_text_field", "Amazon Standard Identification Number"),
    "brand": ("Brand", "single_line_text_field", "Brand name"),
    "manufacturer": ("Manufacturer", "single_line_text_field", "Manufacturer name"),
    "rating": ("Rating", "number_decimal", "Amazon rating (0-5)"),
    "reviews_count": ("Reviews Count", "number_integer", "Number of reviews"),
    "amazon_price": ("Amazon Price", "number_decimal", "Price on Amazon"),
    "availability": ("Availability", "single_line_text_field", "Stock availability"),
    "model_number": ("Model Number", "single_line_text_field", "Model number"),
    "item_model_number": ("Item Model Number", "single_line_text_field", "Item model number"),
    "model_name": ("Model Name", "single_line_text_field", "Model name"),
    "part_number": ("Part Number", "single_line_text_field", "Part number"),
    "upc": ("UPC", "single_line_text_field", "Universal Product Code"),
    "ean": ("EAN", "single_line_text_field", "European Article Number"),
    "isbn": ("ISBN", "single_line_text_field", "International Standard Book Number"),
    "item_dimensions": ("Item Dimensions", "single_line_text_field", "Item dimensions"),
    "item_weight": ("Item Weight", "single_line_text_field", "Item weight"),
    "package_dimensions": ("Package Dimensions", "single_line_text_field", "Package dimensions"),
    "size": ("Size", "single_line_text_field", "Size"),
    "color": ("Color", "single_line_text_field", "Color"),
    "material_type": ("Material Type", "single_line_text_field", "Material"),
    "style_name": ("Style Name", "single_line_text_field", "Style"),
    "theme": ("Theme", "single_line_text_field", "Theme"),
    "department": ("Department", "single_line_text_field", "Department"),
    "country_of_origin": ("Country of Origin", "single_line_text_field", "Country of origin"),
    "date_first_available": ("Date First Available", "single_line_text_field", "Date first available"),
    "best_sellers_rank": ("Best Sellers Rank", "single_line_text_field", "Best sellers rank"),
    "language": ("Language", "single_line_text_field", "Language"),
    "reading_age": ("Reading Age", "single_line_text_field", "Reading age"),
    "unit_count": ("Unit Count", "single_line_text_field", "Unit count"),
    "number_of_pieces": ("Number of Pieces", "number_integer", "Number of pieces"),
    "care_instructions": ("Care Instructions", "multi_line_text_field", "Care instructions"),
    "closure_type": ("Closure Type", "single_line_text_field", "Closure type"),
    "fabric_type": ("Fabric Type", "single_line_text_field", "Fabric type"),
    "number_of_players": ("Number of Players", "single_line_text_field", "Number of players"),
    "educational_objective": ("Educational Objective", "single_line_text_field", "Educational objective"),
    "power_source": ("Power Source", "single_line_text_field", "Power source"),
    "battery_types": ("Battery Types", "single_line_text_field", "Battery types"),
    "operation_mode": ("Operation Mode", "single_line_text_field", "Operation mode"),
    "specific_uses": ("Specific Uses", "single_line_text_field", "Specific uses"),
    "special_features": ("Special Features", "single_line_text_field", "Special features"),
    "connectivity": ("Connectivity", "single_line_text_field", "Connectivity"),
    "processor": ("Processor", "single_line_text_field", "Processor"),
    "ram_technology": ("RAM Technology", "single_line_text_field", "RAM technology"),
    "memory": ("Memory", "single_line_text_field", "Memory"),
    "screen_size": ("Screen Size", "single_line_text_field", "Screen size"),
    "resolution": ("Resolution", "single_line_text_field", "Resolution"),
    "operating_system": ("Operating System", "single_line_text_field", "Operating system"),
    "hard_disk": ("Hard Disk", "single_line_text_field", "Hard disk"),
    "graphics_coprocessor": ("Graphics Coprocessor", "single_line_text_field", "Graphics coprocessor"),
    "warranty": ("Warranty", "multi_line_text_field", "Warranty information"),
}

async def ensure_metafield_definitions(shop: str, access_token: str, keys: list) -> dict:
    if not keys: return {}

    query = """query getDefinitions($first: Int!) { metafieldDefinitions(first: $first, ownerType: PRODUCT) { edges { node { id namespace key type { name } pinnedPosition } } } }"""
    result = await shopify_graphql(shop, access_token, query, {"first": 250})
    existing_types, pinned_count = {}, 0

    if "data" in result:
        for edge in result["data"].get("metafieldDefinitions", {}).get("edges", []):
            node = edge.get("node", {})
            if node.get("namespace") != "custom": continue
            key = node.get("key")
            type_name = (node.get("type") or {}).get("name")
            if key and type_name: existing_types[key] = type_name
            if node.get("pinnedPosition") is not None: pinned_count += 1

    PINNED_LIMIT = 50
    can_pin = pinned_count < PINNED_LIMIT
    to_create = []

    for key in keys:
        if key in existing_types: continue
        if key not in METAFIELD_DEFINITIONS:
            name = key.replace("_", " ").title()
            mf_type, desc = "single_line_text_field", f"Custom field: {name}"
        else:
            name, mf_type, desc = METAFIELD_DEFINITIONS[key]
        should_pin = can_pin and pinned_count < PINNED_LIMIT
        to_create.append({"name": name, "namespace": "custom", "key": key, "description": desc, "type": mf_type, "ownerType": "PRODUCT", "pin": should_pin})
        if should_pin: pinned_count += 1

    if not to_create: return existing_types

    mutation = """mutation createDefinition($definition: MetafieldDefinitionInput!) { metafieldDefinitionCreate(definition: $definition) { createdDefinition { id name key type { name } } userErrors { field message code } } }"""
    
    for defn in to_create:
        try:
            r = await shopify_graphql(shop, access_token, mutation, {"definition": defn})
            user_errors = r.get("data", {}).get("metafieldDefinitionCreate", {}).get("userErrors", [])
            
            if "errors" in r or user_errors:
                existing_types[defn["key"]] = "single_line_text_field"
                continue

            created = r.get("data", {}).get("metafieldDefinitionCreate", {}).get("createdDefinition", {})
            existing_types[defn["key"]] = (created.get("type") or {}).get("name") or defn["type"]
        except Exception:
            existing_types[defn["key"]] = "single_line_text_field"

    return existing_types
