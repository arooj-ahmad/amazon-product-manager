# ============================================
# app/services/shopify_product.py
# Product create (simple + variants), variant add,
# images, status update, tags update,
# product delete, SKU search, PUBLISH, METAFIELDS
# + ✅ FIXED: Metafield DEFINITIONS auto-create (Admin UI mein show honge)
# + ✅ FIXED: Multiple variants support (Color + Size)
# + ✅ FIXED: SKU (ASIN) always set on variants
# + ✅ FIXED: Metafields in Description HTML (auto-show)
# + ✅ FIXED: Auto-publish to channels
# + ✅ FIXED v2: Metafield TYPE mismatch (INVALID_TYPE)
# + ✅ UPGRADED: Description mein SAARE metafields HTML table
# + ✅ FIXED v3: Chunked metafields (25 per call) + Pinned limit handle
# + ✅ NEW: Auto compare_at_price (price × 1.2)
# ============================================

import logging
from typing import Optional

from app.services.shopify_helpers import (
    shopify_graphql,
    _build_shopify_tags,
    _get_product_type,
)
from app.services.shopify_taxonomy import find_best_category
from app.services.shopify_inventory import set_inventory_quantity

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

    # Identification
    "model_number": ("Model Number", "single_line_text_field", "Model number"),
    "item_model_number": ("Item Model Number", "single_line_text_field", "Item model number"),
    "model_name": ("Model Name", "single_line_text_field", "Model name"),
    "part_number": ("Part Number", "single_line_text_field", "Part number"),
    "upc": ("UPC", "single_line_text_field", "Universal Product Code"),
    "ean": ("EAN", "single_line_text_field", "European Article Number"),
    "isbn": ("ISBN", "single_line_text_field", "International Standard Book Number"),

    # Dimensions
    "item_dimensions": ("Item Dimensions", "single_line_text_field", "Item dimensions"),
    "item_weight": ("Item Weight", "single_line_text_field", "Item weight"),
    "package_dimensions": ("Package Dimensions", "single_line_text_field", "Package dimensions"),
    "size": ("Size", "single_line_text_field", "Size"),
    "color": ("Color", "single_line_text_field", "Color"),
    "material_type": ("Material Type", "single_line_text_field", "Material"),
    "style_name": ("Style Name", "single_line_text_field", "Style"),
    "theme": ("Theme", "single_line_text_field", "Theme"),

    # Details
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

    # Category specific
    "number_of_players": ("Number of Players", "single_line_text_field", "Number of players"),
    "educational_objective": ("Educational Objective", "single_line_text_field", "Educational objective"),
    "power_source": ("Power Source", "single_line_text_field", "Power source"),
    "battery_types": ("Battery Types", "single_line_text_field", "Battery types"),
    "operation_mode": ("Operation Mode", "single_line_text_field", "Operation mode"),
    "specific_uses": ("Specific Uses", "single_line_text_field", "Specific uses"),
    "special_features": ("Special Features", "single_line_text_field", "Special features"),

    # Electronics
    "connectivity": ("Connectivity", "single_line_text_field", "Connectivity"),
    "processor": ("Processor", "single_line_text_field", "Processor"),
    "ram_technology": ("RAM Technology", "single_line_text_field", "RAM technology"),
    "memory": ("Memory", "single_line_text_field", "Memory"),
    "screen_size": ("Screen Size", "single_line_text_field", "Screen size"),
    "resolution": ("Resolution", "single_line_text_field", "Resolution"),
    "operating_system": ("Operating System", "single_line_text_field", "Operating system"),
    "hard_disk": ("Hard Disk", "single_line_text_field", "Hard disk"),
    "graphics_coprocessor": ("Graphics Coprocessor", "single_line_text_field", "Graphics coprocessor"),

    # Warranty
    "warranty": ("Warranty", "multi_line_text_field", "Warranty information"),
}


# ============================================
# HELPER: Slugify key
# ============================================
def _slugify_key(name: str) -> str:
    """Field name → snake_case key."""
    return (
        name.lower()
        .strip()
        .replace(" ", "_")
        .replace("&", "and")
        .replace("-", "_")
        .replace("/", "_")
        .replace("(", "")
        .replace(")", "")
        .replace(".", "")
        .strip("_")
        [:50]
    )


# ============================================
# ✅ FIXED v3: Ensure Metafield Definitions exist
# - Pinned limit (50) handle karta hai
# - Existing definitions ka type bhi return karta hai
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

    # ✅ Pinned limit check
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

        # ✅ Dynamic pin decision
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
                # ✅ PINNED_LIMIT_REACHED ko gracefully handle karo
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
                    # Retry without pin
                    logger.warning(
                        f"   ⚠️ {defn['key']} — pinned limit hit, "
                        f"retrying without pin"
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
                        logger.error(
                            f"   ❌ {defn['key']} retry failed: {ue2}"
                        )
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
# HELPER: Build ALL Metafields
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

    # 1. CORE
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

    # 2. IDENTIFICATION
    _add("model_number", product_data.get("model_number"))
    _add("item_model_number", product_data.get("item_model_number"))
    _add("model_name", product_data.get("model_name"))
    _add("part_number", product_data.get("part_number"))
    _add("upc", product_data.get("upc"))
    _add("ean", product_data.get("ean"))
    _add("isbn", product_data.get("isbn"))

    # 3. DIMENSIONS
    _add("item_dimensions", product_data.get("item_dimensions"))
    _add("item_weight", product_data.get("item_weight"))
    _add("package_dimensions", product_data.get("package_dimensions"))
    _add("size", product_data.get("size"))
    _add("color", product_data.get("color"))
    _add("material_type", product_data.get("material_type"))
    _add("style_name", product_data.get("style_name"))
    _add("theme", product_data.get("theme"))

    # 4. DETAILS
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

    # 5. CATEGORY-SPECIFIC
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

    # Warranty
    _add("warranty", product_data.get("warranty"), "multi_line_text_field")

    # 6. AUTO-MAP
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
# ✅ UPGRADED: Build Description with SAARE Metafields
# ============================================
def _build_description_with_metafields(product_data: dict) -> str:
    """Amazon description + SAARE metafields HTML table."""
    description = product_data.get("description", "") or ""

    FIELD_LABELS = {
        "asin": "ASIN", "brand": "Brand", "manufacturer": "Manufacturer",
        "rating": "Rating", "reviews_count": "Reviews",
        "amazon_price": "Amazon Price", "availability": "Availability",
        "model_number": "Model Number", "item_model_number": "Item Model Number",
        "model_name": "Model Name", "part_number": "Part Number",
        "upc": "UPC", "ean": "EAN", "isbn": "ISBN",
        "item_dimensions": "Item Dimensions", "item_weight": "Item Weight",
        "package_dimensions": "Package Dimensions", "size": "Size",
        "color": "Color", "material_type": "Material", "style_name": "Style",
        "theme": "Theme", "department": "Department",
        "country_of_origin": "Country of Origin",
        "date_first_available": "Date First Available",
        "best_sellers_rank": "Best Sellers Rank", "language": "Language",
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
        "rating", "reviews_count", "amazon_price", "availability",
        "color", "size", "material_type", "style_name",
        "item_dimensions", "item_weight", "package_dimensions",
        "department", "country_of_origin", "date_first_available",
        "best_sellers_rank", "language", "reading_age",
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

        val_str = (
            val_str.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

        label = FIELD_LABELS.get(key, key.replace("_", " ").title())

        if key == "rating":
            try:
                r = float(value)
                val_str = f"{r} ★ out of 5"
            except (ValueError, TypeError):
                pass
        elif key == "amazon_price":
            try:
                p = float(value)
                val_str = f"${p:.2f}"
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


# ============================================
# ✅ PUBLISH PRODUCT TO CHANNELS
# ============================================
async def publish_product_to_channels(
    shop: str,
    access_token: str,
    shopify_product_id: str,
) -> bool:
    """Product ko saare sales channels pe publish karo."""
    if not shopify_product_id:
        return False

    if not shopify_product_id.startswith("gid://"):
        product_gid = f"gid://shopify/Product/{shopify_product_id}"
    else:
        product_gid = shopify_product_id

    publications_query = """
    query getPublications {
      publications(first: 10) {
        edges {
          node { id name }
        }
      }
    }
    """

    result = await shopify_graphql(shop, access_token, publications_query)

    if "errors" in result:
        logger.error(f"❌ Failed to fetch publications: {result['errors']}")
        return False

    edges = result.get("data", {}).get("publications", {}).get("edges", [])

    if not edges:
        logger.warning("⚠️ No publications found")
        return False

    publication_ids = []
    for edge in edges:
        pub = edge["node"]
        pub_id = pub.get("id")
        pub_name = pub.get("name", "")
        if pub_id:
            publication_ids.append(pub_id)
            logger.info(f"   📢 Publishing to: {pub_name}")

    if not publication_ids:
        return False

    mutation = """
    mutation publishablePublish(
      $id: ID!
      $input: [PublicationInput!]!
    ) {
      publishablePublish(id: $id, input: $input) {
        publishable {
          availablePublicationsCount { count }
        }
        userErrors { field message }
      }
    }
    """

    input_data = [{"publicationId": pid} for pid in publication_ids]

    variables = {"id": product_gid, "input": input_data}

    publish_result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in publish_result:
        logger.error(f"❌ Publish errors: {publish_result['errors']}")
        return False

    user_errors = (
        publish_result.get("data", {})
        .get("publishablePublish", {})
        .get("userErrors", [])
    )

    if user_errors:
        logger.error(f"❌ Publish user errors: {user_errors}")
        return False

    count = (
        publish_result.get("data", {})
        .get("publishablePublish", {})
        .get("publishable", {})
        .get("availablePublicationsCount", {})
        .get("count", 0)
    )

    logger.info(f"✅ Product published to {count} channel(s)")
    return True


# ============================================
# DELETE SHOPIFY PRODUCT
# ============================================
async def delete_shopify_product(
    shop_domain: str,
    access_token: str,
    shopify_product_id: str,
    refresh_token: Optional[str] = None,
) -> bool:
    """Shopify product delete karo."""
    if not all([shop_domain, access_token, shopify_product_id]):
        logger.warning("Shopify delete skipped: missing config")
        return False

    if not str(shopify_product_id).startswith("gid://"):
        product_gid = f"gid://shopify/Product/{shopify_product_id}"
    else:
        product_gid = shopify_product_id

    from app.services.shopify_helpers import _safe_api_version
    import httpx

    api_version = _safe_api_version()
    api_url = f"https://{shop_domain}/admin/api/{api_version}/graphql.json"

    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }

    mutation = """
    mutation productDelete($input: ProductDeleteInput!) {
      productDelete(input: $input) {
        deletedProductId
        userErrors { field message }
      }
    }
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                api_url,
                headers=headers,
                json={"query": mutation, "variables": {"input": {"id": product_gid}}},
            )

            if res.status_code in (401, 403):
                if refresh_token:
                    logger.warning(f"🔄 {res.status_code} — refreshing token")
                    from app.services.shopify_auth import refresh_shopify_token
                    new_data = await refresh_shopify_token(shop_domain, refresh_token)
                    if new_data and new_data.get("access_token"):
                        return await delete_shopify_product(
                            shop_domain=shop_domain,
                            access_token=new_data["access_token"],
                            shopify_product_id=shopify_product_id,
                            refresh_token=new_data.get("refresh_token"),
                        )
                logger.error(f"❌ {res.status_code} Unauthorized")
                return False

            res.raise_for_status()
            data = res.json()

        if "errors" in data:
            logger.error(f"❌ Shopify delete errors: {data['errors']}")
            return False

        delete_data = data.get("data", {}).get("productDelete", {})
        user_errors = delete_data.get("userErrors", [])

        if user_errors:
            logger.error(f"❌ Shopify delete user errors: {user_errors}")
            return False

        deleted_id = delete_data.get("deletedProductId")
        if deleted_id:
            logger.info(f"✅ Shopify product deleted: {deleted_id}")
            return True

        return False

    except Exception as e:
        logger.error(f"❌ Shopify delete failed: {e}")
        return False


# ============================================
# ✅ VARIANT UPDATE (with COMPARE AT PRICE)
# ============================================
async def update_variant_with_tracked(
    shop: str,
    access_token: str,
    product_id: str,
    variant_id: str,
    price: float,
    sku: str = "",
    compare_at_price: float = None,   # ✅ NAYA PARAM
) -> bool:
    """Variant update karo — price + SKU + compare_at_price ke saath."""
    mutation = """
    mutation productVariantsBulkUpdate(
      $productId: ID!,
      $variants: [ProductVariantsBulkInput!]!
    ) {
      productVariantsBulkUpdate(productId: $productId, variants: $variants) {
        productVariants {
          id
          price
          compareAtPrice
          inventoryItem { id sku tracked }
        }
        userErrors { field message }
      }
    }
    """

    inventory_item_input = {"tracked": True}
    if sku:
        inventory_item_input["sku"] = sku

    variant_input = {
        "id": variant_id,
        "price": str(price),
        "inventoryItem": inventory_item_input,
    }

    # ✅ Compare at price add karo agar diya hai aur price se zyada hai
    if compare_at_price is not None:
        try:
            cap = float(compare_at_price)
            if cap > float(price):
                variant_input["compareAtPrice"] = f"{cap:.2f}"
        except (ValueError, TypeError):
            pass

    variables = {
        "productId": product_id,
        "variants": [variant_input],
    }

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Variant update errors: {result['errors']}")
        return False

    update_errors = (
        result.get("data", {}).get("productVariantsBulkUpdate", {}).get("userErrors", [])
    )

    if update_errors:
        logger.error(f"❌ Variant update user errors: {update_errors}")
        return False

    updated = (
        result.get("data", {}).get("productVariantsBulkUpdate", {}).get("productVariants", [])
    )

    if updated:
        v = updated[0]
        logger.info(
            f"✅ Variant updated: price=${v.get('price')}, "
            f"compare_at=${v.get('compareAtPrice')}, "
            f"sku={v.get('inventoryItem', {}).get('sku', 'N/A')}"
        )
        return True

    return False


# ============================================
# ✅ FIXED v3: SET PRODUCT METAFIELDS (CHUNKED)
# - 25 per call (Shopify limit)
# - Type-aware
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

    # STEP 1: Definitions ensure
    keys = [mf["key"] for mf in metafields]
    actual_types = await ensure_metafield_definitions(shop, access_token, keys)

    # STEP 2: Value adaptation
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

    # STEP 3: CHUNKED sending (25 per call)
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


# ============================================
# ENSURE PRODUCT HAS OPTION
# ============================================
async def ensure_product_has_option(
    shop: str,
    access_token: str,
    product_id: str,
    option_name: str,
    option_values: list,
) -> bool:
    """Ensure karo ki product mein yeh option exist karta hai."""
    query = """
    query getProductWithVariants($id: ID!) {
      product(id: $id) {
        id
        options { id name values }
        variants(first: 100) {
          edges {
            node {
              id
              selectedOptions { name value }
            }
          }
        }
      }
    }
    """

    result = await shopify_graphql(shop, access_token, query, {"id": product_id})

    if "errors" in result:
        logger.error(f"❌ Failed to fetch options: {result['errors']}")
        return False

    product = result.get("data", {}).get("product")
    if not product:
        logger.error(f"❌ Product not found: {product_id}")
        return False

    existing_options = product.get("options", [])
    existing_names = [opt.get("name", "").lower() for opt in existing_options]

    if option_name.lower() in existing_names:
        logger.info(f"   ✅ Option '{option_name}' already exists")
        return True

    logger.info(f"   ➕ Creating option '{option_name}' with values: {option_values}")

    new_options = []
    for opt in existing_options:
        name = opt.get("name", "")
        values = opt.get("values", [])

        if name.lower() == "default title":
            continue

        values_as_dicts = []
        for v in values:
            if isinstance(v, str) and v:
                values_as_dicts.append({"name": v})
            elif isinstance(v, dict) and v.get("name"):
                values_as_dicts.append({"name": v["name"]})

        new_options.append({"name": name, "values": values_as_dicts})

    new_option_values = []
    for v in option_values:
        if isinstance(v, str) and v:
            new_option_values.append({"name": v})
        elif isinstance(v, dict) and v.get("name"):
            new_option_values.append({"name": v["name"]})

    new_options.append({"name": option_name, "values": new_option_values})

    variants_edges = product.get("variants", {}).get("edges", [])
    existing_variants_input = []

    for edge in variants_edges:
        node = edge["node"]
        variant_id = node.get("id")
        selected_options = node.get("selectedOptions", [])

        if not variant_id:
            continue

        variant_option_values = []
        for opt in selected_options:
            variant_option_values.append({
                "optionName": opt["name"],
                "name": opt["value"],
            })

        if new_option_values:
            first_value = new_option_values[0]
            val_name = (
                first_value if isinstance(first_value, str)
                else first_value.get("name", "Default")
            )
            variant_option_values.append({
                "optionName": option_name,
                "name": val_name,
            })

        existing_variants_input.append({
            "id": variant_id,
            "optionValues": variant_option_values,
        })

    mutation = """
    mutation productSet($input: ProductSetInput!) {
      productSet(input: $input) {
        product { id options { id name values } }
        userErrors { field message }
      }
    }
    """

    input_data = {
        "id": product_id,
        "productOptions": new_options,
    }

    if existing_variants_input:
        input_data["variants"] = existing_variants_input

    variables = {"input": input_data}

    update_result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in update_result:
        logger.error(f"❌ Option create errors: {update_result['errors']}")
        return False

    user_errors = (
        update_result.get("data", {}).get("productSet", {}).get("userErrors", [])
    )

    if user_errors:
        logger.error(f"❌ Option create user errors: {user_errors}")
        return False

    logger.info(f"   ✅ Option '{option_name}' created successfully")
    return True


# ============================================
# UPDATE PRODUCT TAGS AND TYPE
# ============================================
async def update_shopify_product_tags_and_type(
    shop: str,
    access_token: str,
    shopify_product_id: str,
    tags: list[str],
    product_type: str = "",
) -> bool:
    if not shopify_product_id.startswith("gid://"):
        product_gid = f"gid://shopify/Product/{shopify_product_id}"
    else:
        product_gid = shopify_product_id

    mutation = """
    mutation productUpdate($input: ProductInput!) {
      productUpdate(input: $input) {
        product { id title tags productType }
        userErrors { field message }
      }
    }
    """

    input_data = {"id": product_gid, "tags": tags}
    if product_type:
        input_data["productType"] = product_type

    variables = {"input": input_data}

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Tags update GraphQL errors: {result['errors']}")
        return False

    update_data = result.get("data", {}).get("productUpdate", {})
    user_errors = update_data.get("userErrors", [])

    if user_errors:
        logger.error(f"❌ Tags update user errors: {user_errors}")
        return False

    updated = update_data.get("product", {})
    logger.info(f"✅ Tags updated: {len(updated.get('tags', []))} tags")
    return True


# ============================================
# CREATE PRODUCT WITH VARIANTS
# ============================================
async def create_shopify_product_with_variants(
    shop: str,
    access_token: str,
    product_data: dict,
    variants: list,
) -> dict:
    is_available = product_data.get("is_available", True)
    status = "ACTIVE" if is_available else "DRAFT"

    shopify_tags = _build_shopify_tags(product_data)
    product_type = _get_product_type(product_data)

    categories = product_data.get("categories") or []
    product_title = product_data.get("title", "")

    shopify_category_id = None
    if product_title or categories:
        shopify_category_id = await find_best_category(
            shop=shop,
            access_token=access_token,
            product_title=product_title,
            categories=categories,
        )

    input_data = {
        "title": product_data.get("title") or "Untitled Product",
        "descriptionHtml": _build_description_with_metafields(product_data),
        "vendor": product_data.get("brand", ""),
        "status": status,
        "productOptions": [
            {
                "name": "Style",
                "values": [
                    {"name": v["title"]} for v in variants if v.get("title")
                ] or [{"name": "Default"}],
            }
        ],
    }

    if shopify_tags:
        input_data["tags"] = shopify_tags

    if product_type:
        input_data["productType"] = product_type

    if shopify_category_id:
        input_data["category"] = shopify_category_id

    mutation_create = """
    mutation productSet($input: ProductSetInput!) {
      productSet(input: $input) {
        product {
          id title handle tags productType
          category { id name fullName }
          options { id name values }
          variants(first: 50) {
            edges { node { id title price inventoryItem { id sku tracked } } }
          }
        }
        userErrors { field message }
      }
    }
    """

    result = await shopify_graphql(
        shop, access_token, mutation_create, {"input": input_data}
    )

    if "errors" in result:
        logger.error(f"❌ Product create error: {result['errors']}")
        return result

    product_create = result.get("data", {}).get("productSet", {})
    user_errors = product_create.get("userErrors", [])

    if user_errors:
        logger.error(f"❌ Product user errors: {user_errors}")
        return result

    shopify_product = product_create.get("product", {})
    product_id = shopify_product.get("id")

    logger.info(f"✅ Product created: {shopify_product.get('title')}")

    if product_id:
        await publish_product_to_channels(
            shop=shop,
            access_token=access_token,
            shopify_product_id=product_id,
        )

    if product_id:
        all_mfs = _build_all_metafields(product_data)
        if all_mfs:
            await set_product_metafields(
                shop=shop,
                access_token=access_token,
                product_id=product_id,
                metafields=all_mfs,
            )

    images = product_data.get("images", [])
    if product_id and images:
        await add_product_images(
            shop=shop,
            access_token=access_token,
            product_id=product_id,
            image_urls=images[:10],
        )

    return result


# ============================================
# ADD VARIANT TO EXISTING PRODUCT
# ============================================
async def add_variant_to_existing_product(
    shop: str,
    access_token: str,
    product_id: str,
    variant_data: dict,
    all_options: list = None,
) -> dict:
    """Existing product mein naya variant add karo."""
    if not all_options:
        option_name = variant_data.get("option_name") or "Style"
        option_value = variant_data.get("title") or "Default"
        all_options = [{"name": option_name, "value": option_value}]

    logger.info(
        f"   Adding variant: "
        + " / ".join(f"{o['name']}={o['value']}" for o in all_options)
    )

    for opt in all_options:
        option_exists = await ensure_product_has_option(
            shop=shop,
            access_token=access_token,
            product_id=product_id,
            option_name=opt["name"],
            option_values=[opt["value"]],
        )

        if not option_exists:
            logger.error(f"❌ Could not ensure option '{opt['name']}'")
            return {
                "errors": [{"message": f"Failed to create option '{opt['name']}'"}]
            }

    option_values = [
        {"optionName": opt["name"], "name": opt["value"]}
        for opt in all_options
    ]

    sku_value = variant_data.get("sku", "") or ""

    mutation = """
    mutation productVariantsBulkCreate(
      $productId: ID!,
      $variants: [ProductVariantsBulkInput!]!
    ) {
      productVariantsBulkCreate(productId: $productId, variants: $variants) {
        productVariants { id title price inventoryItem { id sku tracked } }
        userErrors { field message }
      }
    }
    """

    variants_input = {
        "optionValues": option_values,
        "price": str(variant_data.get("price", 0)),
        "inventoryItem": {"tracked": True},
    }

    if sku_value:
        variants_input["inventoryItem"]["sku"] = sku_value

    variables = {"productId": product_id, "variants": [variants_input]}

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Variant create error: {result['errors']}")
        return result

    var_errors = (
        result.get("data", {}).get("productVariantsBulkCreate", {}).get("userErrors", [])
    )

    if var_errors:
        for err in var_errors:
            msg = (err.get("message") or "").lower()
            if "already exists" in msg:
                logger.info(f"ℹ️ Variant already exists: {msg}")
                return {"already_exists": True, "userErrors": var_errors}

        logger.error(f"❌ Variant create user errors: {var_errors}")
        return result

    created = (
        result.get("data", {}).get("productVariantsBulkCreate", {}).get("productVariants", [])
    )

    if created:
        v = created[0]
        logger.info(
            f"✅ Variant added: {v.get('title')} — ${v.get('price')} "
            f"— SKU: {v.get('inventoryItem', {}).get('sku', 'N/A')}"
        )

        inv_item_id = v.get("inventoryItem", {}).get("id")
        stock = variant_data.get("stock", 0)
        if inv_item_id and stock:
            await set_inventory_quantity(
                shop=shop,
                access_token=access_token,
                inventory_item_id=inv_item_id,
                quantity=stock,
            )

    return result


# ============================================
# ✅ PRODUCT CREATE (SIMPLE) — with COMPARE AT PRICE
# ============================================
async def create_shopify_product(
    shop: str,
    access_token: str,
    product_data: dict,
) -> dict:
    is_available = product_data.get("is_available", True)
    status = "ACTIVE" if is_available else "DRAFT"

    price_float = 0.0
    try:
        price_float = float(product_data.get("price", 0) or 0)
    except (ValueError, TypeError):
        price_float = 0.0

    asin_value = str(product_data.get("asin", "") or "").strip()
    if not asin_value or asin_value == "None":
        asin_value = "NO-SKU"

    metafields_input = _build_all_metafields(product_data)

    shopify_tags = _build_shopify_tags(product_data)
    product_type = _get_product_type(product_data)

    categories = product_data.get("categories") or []
    product_title = product_data.get("title", "")

    shopify_category_id = None
    if product_title or categories:
        shopify_category_id = await find_best_category(
            shop=shop,
            access_token=access_token,
            product_title=product_title,
            categories=categories,
        )

    description_html = _build_description_with_metafields(product_data)

    input_data = {
        "title": product_data.get("title") or "Untitled Product",
        "descriptionHtml": description_html,
        "vendor": product_data.get("brand", ""),
        "status": status,
    }

    if shopify_tags:
        input_data["tags"] = shopify_tags

    if product_type:
        input_data["productType"] = product_type

    if shopify_category_id:
        input_data["category"] = shopify_category_id

    variant_attrs = product_data.get("variant_attributes") or []
    product_options = []
    variant_values = []

    for attr in variant_attrs:
        if not isinstance(attr, dict):
            continue
        name = (attr.get("name") or "").strip()
        value = (attr.get("value") or "").strip()
        if name.lower() in ("color", "size") and value:
            product_options.append({"name": name, "values": [{"name": value}]})
            variant_values.append({"optionName": name, "name": value})

    if product_options and variant_values:
        input_data["productOptions"] = product_options
        input_data["variants"] = [
            {
                "optionValues": variant_values,
                "price": str(price_float or 0),
                "inventoryItem": {
                    "sku": asin_value,
                    "tracked": True,
                },
            }
        ]
        logger.info(
            f"   Adding variant: "
            + " / ".join(f"{v['optionName']}={v['name']}" for v in variant_values)
        )
    else:
        logger.info("   No variant options — Shopify will create default variant")

    mutation_create = """
    mutation productSet($input: ProductSetInput!) {
      productSet(input: $input) {
        product {
          id title handle tags productType
          category { id name fullName }
          options { id name values }
          variants(first: 5) {
            edges {
              node {
                id
                title
                price
                inventoryItem { id sku tracked }
              }
            }
          }
        }
        userErrors { field message }
      }
    }
    """

    result = await shopify_graphql(
        shop, access_token, mutation_create, {"input": input_data}
    )

    if "errors" in result:
        logger.error(f"❌ Product create error: {result['errors']}")
        return result

    product_create = result.get("data", {}).get("productSet", {})
    user_errors = product_create.get("userErrors", [])

    if user_errors:
        logger.error(f"❌ Product user errors: {user_errors}")
        return result

    shopify_product = product_create.get("product", {})
    product_id = shopify_product.get("id")

    logger.info(f"✅ Product created: {shopify_product.get('title')}")

    if product_id:
        await publish_product_to_channels(
            shop=shop,
            access_token=access_token,
            shopify_product_id=product_id,
        )

    if product_id and metafields_input:
        await set_product_metafields(
            shop=shop,
            access_token=access_token,
            product_id=product_id,
            metafields=metafields_input,
        )

    variants_edges = shopify_product.get("variants", {}).get("edges", [])

    if variants_edges:
        variant_node = variants_edges[0]["node"]
        variant_id = variant_node.get("id")
        inventory_item_id = variant_node.get("inventoryItem", {}).get("id")

        if product_id and variant_id:
            # ✅ Compare at price calculate karo (price se 20% zyada)
            compare_price = None
            if price_float and price_float > 0:
                compare_price = round(price_float * 1.2, 2)

            await update_variant_with_tracked(
                shop=shop,
                access_token=access_token,
                product_id=product_id,
                variant_id=variant_id,
                price=price_float,
                sku=asin_value,
                compare_at_price=compare_price,   # ✅ YEH ADD KAREIN
            )

        if inventory_item_id:
            stock_qty = product_data.get("stock_quantity", 0)
            if stock_qty == 0 and is_available:
                stock_qty = 100

            await set_inventory_quantity(
                shop=shop,
                access_token=access_token,
                inventory_item_id=inventory_item_id,
                quantity=stock_qty,
            )

    images = product_data.get("images", [])
    if product_id and images:
        await add_product_images(
            shop=shop,
            access_token=access_token,
            product_id=product_id,
            image_urls=images[:10],
        )

    return result


# ============================================
# PRODUCT IMAGES ADD
# ============================================
async def add_product_images(
    shop: str,
    access_token: str,
    product_id: str,
    image_urls: list,
) -> dict:
    mutation = """
    mutation productCreateMedia(
      $productId: ID!,
      $media: [CreateMediaInput!]!
    ) {
      productCreateMedia(productId: $productId, media: $media) {
        media { ... on MediaImage { id image { url } } }
        mediaUserErrors { field message }
      }
    }
    """

    media_input = [
        {"originalSource": url, "mediaContentType": "IMAGE"}
        for url in image_urls
        if url
    ]

    if not media_input:
        return {}

    variables = {"productId": product_id, "media": media_input}

    return await shopify_graphql(shop, access_token, mutation, variables)


# ============================================
# PRODUCT STATUS UPDATE
# ============================================
async def update_shopify_product_status(
    shop: str,
    access_token: str,
    shopify_product_id: str,
    is_available: bool,
) -> bool:
    if not shopify_product_id.startswith("gid://"):
        product_gid = f"gid://Shopify/Product/{shopify_product_id}"
    else:
        product_gid = shopify_product_id

    new_status = "ACTIVE" if is_available else "DRAFT"

    mutation = """
    mutation updateProductStatus($input: ProductInput!) {
      productUpdate(input: $input) {
        product { id title status }
        userErrors { field message }
      }
    }
    """

    variables = {"input": {"id": product_gid, "status": new_status}}

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Status update errors: {result['errors']}")
        return False

    return True


# ============================================
# SHOPIFY PRODUCT BY SKU
# ============================================
async def get_shopify_product_by_sku(
    shop: str,
    access_token: str,
    sku: str,
) -> Optional[str]:
    query = """
    query getProductBySku($query: String!) {
      products(first: 1, query: $query) {
        edges {
          node {
            id title status
            variants(first: 1) {
              edges { node { id inventoryItem { id } } }
            }
          }
        }
      }
    }
    """

    result = await shopify_graphql(shop, access_token, query, {"query": f"sku:{sku}"})

    if "errors" in result:
        logger.error(f"SKU search errors: {result['errors']}")
        return None

    edges = result.get("data", {}).get("products", {}).get("edges", [])

    if edges:
        product_gid = edges[0]["node"]["id"]
        logger.info(f"Found Shopify product: {product_gid} for SKU={sku}")
        return product_gid

    logger.warning(f"No Shopify product found for SKU={sku}")
    return None