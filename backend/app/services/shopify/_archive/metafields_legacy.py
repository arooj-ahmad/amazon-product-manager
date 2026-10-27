# app/services/shopify/metafields.py
# Metafield definitions + builder + setter

import logging

from app.services.shopify.helpers import shopify_graphql
from app.services.shopify._helpers import _slugify_key

logger = logging.getLogger(__name__)


# ============================================
# ✅ METAFIELD DEFINITIONS MAP
# ============================================
METAFIELD_DEFINITIONS = {
    # Core
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


# ============================================
# ✅ Ensure Metafield Definitions exist
# ============================================
async def ensure_metafield_definitions(
    shop: str,
    access_token: str,
    keys: list,
) -> dict:
    """
    Har key ke liye metafieldDefinition create karo (agar exist nahi karti).
    Pinned limit (50) ka dhyan rakho.
    Returns: {key: type_name}
    """
    if not keys:
        return {}

    query = """
    query getDefinitions($first: Int!) {
      metafieldDefinitions(first: $first, ownerType: PRODUCT) {
        edges {
          node {
            id
            namespace
            key
            type { name }
            pinnedPosition
          }
        }
      }
    }
    """

    result = await shopify_graphql(shop, access_token, query, {"first": 250})

    existing_types = {}
    pinned_count = 0

    if "data" in result:
        edges = result["data"].get("metafieldDefinitions", {}).get("edges", [])
        for edge in edges:
            node = edge.get("node", {})
            if node.get("namespace") != "custom":
                continue
            key = node.get("key")
            type_obj = node.get("type") or {}
            type_name = type_obj.get("name") if isinstance(type_obj, dict) else None
            if key and type_name:
                existing_types[key] = type_name
            if node.get("pinnedPosition") is not None:
                pinned_count += 1

    PINNED_LIMIT = 50
    can_pin = pinned_count < PINNED_LIMIT

    if not can_pin:
        logger.warning(
            f"   ⚠️ Pinned limit reached ({pinned_count}/{PINNED_LIMIT}) — "
            f"new definitions won't be pinned"
        )

    to_create = []
    for key in keys:
        if key in existing_types:
            continue
        if key not in METAFIELD_DEFINITIONS:
            name = key.replace("_", " ").title()
            mf_type = "single_line_text_field"
            desc = f"Custom field: {name}"
        else:
            name, mf_type, desc = METAFIELD_DEFINITIONS[key]

        should_pin = can_pin and pinned_count < PINNED_LIMIT

        to_create.append({
            "name": name,
            "namespace": "custom",
            "key": key,
            "description": desc,
            "type": mf_type,
            "ownerType": "PRODUCT",
            "pin": should_pin,
        })

        if should_pin:
            pinned_count += 1

    if not to_create:
        logger.info(f"   ✅ All {len(keys)} metafield definitions already exist")
        return existing_types

    logger.info(f"   📝 Creating {len(to_create)} metafield definitions...")

    mutation = """
    mutation createDefinition($definition: MetafieldDefinitionInput!) {
      metafieldDefinitionCreate(definition: $definition) {
        createdDefinition { id name key type { name } }
        userErrors { field message code }
      }
    }
    """

    success_count = 0
    for defn in to_create:
        try:
            r = await shopify_graphql(shop, access_token, mutation, {"definition": defn})

            if "errors" in r:
                logger.error(f"   ❌ Definition error ({defn['key']}): {r['errors']}")
                existing_types[defn["key"]] = "single_line_text_field"
                continue

            user_errors = (
                r.get("data", {})
                .get("metafieldDefinitionCreate", {})
                .get("userErrors", [])
            )

            if user_errors:
                pinned_error = any(
                    "pinned" in (e.get("message") or "").lower()
                    or e.get("code") == "PINNED_LIMIT_REACHED"
                    for e in user_errors
                )
                already_exists = any(
                    "already exists" in (e.get("message") or "").lower()
                    or "taken" in (e.get("message") or "").lower()
                    for e in user_errors
                )

                if already_exists:
                    existing_types[defn["key"]] = "single_line_text_field"
                    success_count += 1
                    continue

                if pinned_error:
                    logger.warning(
                        f"   ⚠️ {defn['key']} — pinned limit hit, retrying without pin"
                    )
                    defn_nopin = dict(defn)
                    defn_nopin["pin"] = False

                    r2 = await shopify_graphql(
                        shop, access_token, mutation, {"definition": defn_nopin}
                    )
                    ue2 = (
                        r2.get("data", {})
                        .get("metafieldDefinitionCreate", {})
                        .get("userErrors", [])
                    )
                    if not ue2:
                        existing_types[defn["key"]] = defn_nopin["type"]
                        success_count += 1
                    else:
                        logger.error(f"   ❌ {defn['key']} retry failed: {ue2}")
                        existing_types[defn["key"]] = "single_line_text_field"
                    continue

                logger.error(
                    f"   ❌ Definition userErrors ({defn['key']}): {user_errors}"
                )
                existing_types[defn["key"]] = "single_line_text_field"
                continue

            created = (
                r.get("data", {})
                .get("metafieldDefinitionCreate", {})
                .get("createdDefinition", {})
            )
            created_type = (created.get("type") or {}).get("name")
            existing_types[defn["key"]] = created_type or defn["type"]
            success_count += 1

        except Exception as e:
            logger.error(f"   ❌ Definition exception ({defn['key']}): {e}")
            existing_types[defn["key"]] = "single_line_text_field"

    logger.info(f"   ✅ Metafield definitions ready: {success_count}/{len(to_create)}")
    return existing_types


# ============================================
# Build ALL Metafields
# ============================================
def _build_all_metafields(product_data: dict) -> list:
    """Amazon product data se SAARE standard metafields build karo."""
    metafields = []
    seen_keys = set()

    def _add(key: str, value, mf_type: str = "single_line_text_field"):
        if key in seen_keys:
            return
        if value is None:
            return
        val_str = str(value).strip()
        if not val_str or val_str == "None":
            return
        if len(val_str) > 5000:
            val_str = val_str[:5000]
        metafields.append({
            "namespace": "custom",
            "key": key,
            "value": val_str,
            "type": mf_type,
        })
        seen_keys.add(key)

    # CORE
    _add("asin", product_data.get("asin"))
    _add("brand", product_data.get("brand"))
    _add("manufacturer", product_data.get("manufacturer"))

    rating = product_data.get("rating")
    if rating is not None:
        try:
            _add("rating", str(float(rating)), "number_decimal")
        except (ValueError, TypeError):
            pass

    reviews = product_data.get("reviews_count")
    if reviews is not None:
        try:
            _add("reviews_count", str(int(reviews)), "number_integer")
        except (ValueError, TypeError):
            pass

    amazon_price = product_data.get("amazon_price")
    if amazon_price is not None:
        try:
            _add("amazon_price", str(float(amazon_price)), "number_decimal")
        except (ValueError, TypeError):
            pass

    _add("availability", product_data.get("availability"))

    # IDENTIFICATION
    _add("model_number", product_data.get("model_number"))
    _add("item_model_number", product_data.get("item_model_number"))
    _add("model_name", product_data.get("model_name"))
    _add("part_number", product_data.get("part_number"))
    _add("upc", product_data.get("upc"))
    _add("ean", product_data.get("ean"))
    _add("isbn", product_data.get("isbn"))

    # DIMENSIONS
    _add("item_dimensions", product_data.get("item_dimensions"))
    _add("item_weight", product_data.get("item_weight"))
    _add("package_dimensions", product_data.get("package_dimensions"))
    _add("size", product_data.get("size"))
    _add("color", product_data.get("color"))
    _add("material_type", product_data.get("material_type"))
    _add("style_name", product_data.get("style_name"))
    _add("theme", product_data.get("theme"))

    # DETAILS
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

    # CATEGORY-SPECIFIC
    _add("number_of_players", product_data.get("number_of_players"))
    _add("educational_objective", product_data.get("educational_objective"))
    _add("power_source", product_data.get("power_source"))
    _add("battery_types", product_data.get("battery_types"))
    _add("operation_mode", product_data.get("operation_mode"))
    _add("specific_uses", product_data.get("specific_uses"))
    _add("special_features", product_data.get("special_features"))

    # Electronics
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

    # AUTO-MAP
    product_details = product_data.get("product_details") or []
    if isinstance(product_details, list):
        for item in product_details:
            if not isinstance(item, dict):
                continue
            field_type = item.get("type") or ""
            field_value = item.get("value")
            if not field_type or field_value is None:
                continue

            key = _slugify_key(field_type)
            if not key or len(key) < 3:
                continue

            val_str = str(field_value).strip()
            if not val_str or val_str == "None":
                continue

            if len(val_str) > 100:
                mf_type = "multi_line_text_field"
            elif val_str.replace(".", "").replace("-", "").isdigit():
                mf_type = "number_decimal" if "." in val_str else "number_integer"
            else:
                mf_type = "single_line_text_field"

            _add(key, val_str, mf_type)

    logger.info(f"   Built {len(metafields)} metafields")
    return metafields


# ============================================
# SET PRODUCT METAFIELDS (CHUNKED)
# ============================================
async def set_product_metafields(
    shop: str,
    access_token: str,
    product_id: str,
    metafields: list,
) -> bool:
    if not metafields:
        logger.info("   No metafields to set")
        return True

    keys = [mf["key"] for mf in metafields]
    actual_types = await ensure_metafield_definitions(shop, access_token, keys)

    def _adapt_value_and_type(raw_value, definition_type: str) -> tuple:
        val_str = str(raw_value) if raw_value is not None else ""

        if definition_type == "single_line_text_field":
            return val_str, "single_line_text_field"
        if definition_type == "multi_line_text_field":
            return val_str, "multi_line_text_field"
        if definition_type == "number_integer":
            try:
                return str(int(float(val_str))), "number_integer"
            except (ValueError, TypeError):
                return val_str, "single_line_text_field"
        if definition_type == "number_decimal":
            try:
                return str(float(val_str)), "number_decimal"
            except (ValueError, TypeError):
                return val_str, "single_line_text_field"
        if definition_type == "boolean":
            b = val_str.strip().lower() in ("true", "1", "yes")
            return ("true" if b else "false"), "boolean"
        if definition_type == "date":
            return val_str, "date"
        if definition_type == "date_time":
            return val_str, "date_time"
        if definition_type == "url":
            return val_str, "url"

        return val_str, "single_line_text_field"

    metafields_with_owner = []
    for mf in metafields:
        key = mf["key"]
        def_type = actual_types.get(key, mf.get("type", "single_line_text_field"))
        value_str, final_type = _adapt_value_and_type(mf["value"], def_type)

        if not value_str or value_str == "None":
            continue

        metafields_with_owner.append({
            "ownerId": product_id,
            "namespace": mf.get("namespace", "custom"),
            "key": key,
            "value": value_str,
            "type": final_type,
        })

    if not metafields_with_owner:
        logger.info("   No valid metafields to set after adaptation")
        return True

    CHUNK_SIZE = 25
    total = len(metafields_with_owner)
    chunks = [
        metafields_with_owner[i:i + CHUNK_SIZE]
        for i in range(0, total, CHUNK_SIZE)
    ]

    mutation = """
    mutation metafieldsSet($metafields: [MetafieldsSetInput!]!) {
      metafieldsSet(metafields: $metafields) {
        metafields { id namespace key value type }
        userErrors { field message code }
      }
    }
    """

    logger.info(
        f"   Setting {total} metafields in {len(chunks)} chunk(s) "
        f"(max {CHUNK_SIZE} per call)..."
    )

    all_success = True
    total_created = 0

    for idx, chunk in enumerate(chunks, 1):
        logger.info(f"   📦 Chunk {idx}/{len(chunks)}: {len(chunk)} metafields")

        result = await shopify_graphql(
            shop, access_token, mutation, {"metafields": chunk}
        )

        if "errors" in result:
            logger.error(f"   ❌ Chunk {idx} GraphQL errors: {result['errors']}")
            all_success = False
            continue

        mf_data = result.get("data", {}).get("metafieldsSet", {})
        user_errors = mf_data.get("userErrors", [])

        if user_errors:
            logger.error(f"   ❌ Chunk {idx} user errors: {user_errors}")
            all_success = False
            continue

        created = mf_data.get("metafields", [])
        total_created += len(created)
        logger.info(f"   ✅ Chunk {idx} done: {len(created)} set")

    logger.info(f"✅ Metafields set: {total_created}/{total}")
    return all_success