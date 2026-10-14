# app/services/shopify/product_variants.py
# Variant + Option management
# + ✅ NAYA: Weight mapping support
# + ✅ NAYA: Measurement in variant input

import logging
import re

from app.services.shopify_helpers import shopify_graphql
from app.services.shopify_inventory import set_inventory_quantity

logger = logging.getLogger(__name__)


# ============================================
# ✅ NAYA: Parse weight string → (value, unit)
# ============================================
def _parse_weight(weight_str) -> tuple:
    """
    Parse weight string like "1.5 pounds", "680 g", "2.2 kg", "16 ounces".
    Returns: (float_value_in_lbs, "POUNDS") or (None, None)
    """
    if not weight_str:
        return None, None

    s = str(weight_str).strip().lower()
    if not s or s == "none":
        return None, None

    # Extract first number
    match = re.search(r"([\d.]+)", s)
    if not match:
        return None, None

    try:
        value = float(match.group(1))
    except ValueError:
        return None, None

    # Detect unit and convert to pounds (Shopify accepts POUNDS/GRAMS/KILOGRAMS/OUNCES)
    if "kg" in s or "kilogram" in s:
        unit = "KILOGRAMS"
    elif "gram" in s or s.endswith("g") or " g" in s:
        unit = "GRAMS"
    elif "ounce" in s or " oz" in s or s.endswith("oz"):
        unit = "OUNCES"
    elif "milligram" in s or " mg" in s:
        # Convert milligrams to grams
        value = value / 1000
        unit = "GRAMS"
    else:
        # Default: pounds
        unit = "POUNDS"

    return round(value, 4), unit


# ============================================
# ✅ NAYA: Build measurement input from variant_data
# ============================================
def _build_measurement(variant_data: dict) -> dict:
    """
    Build Shopify measurement input from variant_data.
    Returns dict with 'weight' key, or empty dict if no weight.
    """
    weight_str = (
        variant_data.get("weight")
        or variant_data.get("item_weight")
        or variant_data.get("package_weight")
    )

    weight_value, weight_unit = _parse_weight(weight_str)

    if weight_value and weight_value > 0:
        return {
            "weight": {
                "value": weight_value,
                "unit": weight_unit,
            }
        }
    return {}


# ============================================
# UPDATE VARIANT (with COMPARE AT PRICE)
# ============================================
async def update_variant_with_tracked(
    shop: str,
    access_token: str,
    product_id: str,
    variant_id: str,
    price: float,
    sku: str = "",
    compare_at_price: float = None,
    weight: str = None,
) -> bool:
    """Variant update — price + SKU + compare_at_price + weight."""
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
          inventoryItem {
            id
            sku
            tracked
            measurement {
              weight { value unit }
            }
          }
        }
        userErrors { field message }
      }
    }
    """

    inventory_item_input = {"tracked": True}
    if sku:
        inventory_item_input["sku"] = sku

    # ✅ NAYA: Add weight measurement if provided
    if weight:
        measurement = _build_measurement({"weight": weight})
        if measurement:
            inventory_item_input["measurement"] = measurement
            logger.info(
                f"   ⚖️ Weight mapped: {weight} → "
                f"{measurement['weight']['value']} {measurement['weight']['unit']}"
            )

    variant_input = {
        "id": variant_id,
        "price": str(price),
        "inventoryItem": inventory_item_input,
    }

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
        measurement = v.get("inventoryItem", {}).get("measurement") or {}
        weight_data = measurement.get("weight") or {}
        logger.info(
            f"✅ Variant updated: price=${v.get('price')}, "
            f"compare_at=${v.get('compareAtPrice')}, "
            f"sku={v.get('inventoryItem', {}).get('sku', 'N/A')}, "
            f"weight={weight_data.get('value', 'N/A')} {weight_data.get('unit', '')}"
        )
        return True

    return False


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
# ADD VARIANT TO EXISTING PRODUCT
# ============================================
async def add_variant_to_existing_product(
    shop: str,
    access_token: str,
    product_id: str,
    variant_data: dict,
    all_options: list = None,
) -> dict:
    """Existing product mein naya variant add karo (weight ke saath)."""
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

    # ✅ NAYA: Build inventory item with weight
    inventory_item_input = {"tracked": True}
    if sku_value:
        inventory_item_input["sku"] = sku_value

    measurement = _build_measurement(variant_data)
    if measurement:
        inventory_item_input["measurement"] = measurement
        logger.info(
            f"   ⚖️ Weight mapped: "
            f"{measurement['weight']['value']} {measurement['weight']['unit']}"
        )

    mutation = """
    mutation productVariantsBulkCreate(
      $productId: ID!,
      $variants: [ProductVariantsBulkInput!]!
    ) {
      productVariantsBulkCreate(productId: $productId, variants: $variants) {
        productVariants {
          id
          title
          price
          inventoryItem {
            id
            sku
            tracked
            measurement {
              weight { value unit }
            }
          }
        }
        userErrors { field message }
      }
    }
    """

    variants_input = {
        "optionValues": option_values,
        "price": str(variant_data.get("price", 0)),
        "inventoryItem": inventory_item_input,
    }

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
        measurement_resp = v.get("inventoryItem", {}).get("measurement") or {}
        weight_data = measurement_resp.get("weight") or {}

        logger.info(
            f"✅ Variant added: {v.get('title')} — ${v.get('price')} "
            f"— SKU: {v.get('inventoryItem', {}).get('sku', 'N/A')} "
            f"— Weight: {weight_data.get('value', 'N/A')} {weight_data.get('unit', '')}"
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