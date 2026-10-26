# app/services/shopify/product_variants.py
# Variant + Option management
# + ✅ Weight mapping support
# + ✅ Measurement in variant input
# + ✅ Compare-at price in add_variant_to_existing_product
# + ✅ Compare-at price in variant mutation response
# + ✅ Variant Image Assignment (100% Working)

import logging
import re
import asyncio  # ✅ Image process ka wait karne ke liye

from app.services.shopify_helpers import shopify_graphql
from app.services.shopify_inventory import set_inventory_quantity

logger = logging.getLogger(__name__)

# ============================================
# Parse weight string → (value, unit)
# ============================================
def _parse_weight(weight_str) -> tuple:
    if not weight_str:
        return None, None

    s = str(weight_str).strip().lower()
    if not s or s == "none":
        return None, None

    match = re.search(r"([\d.]+)", s)
    if not match:
        return None, None

    try:
        value = float(match.group(1))
    except ValueError:
        return None, None

    if "kg" in s or "kilogram" in s:
        unit = "KILOGRAMS"
    elif "gram" in s or s.endswith("g") or " g" in s:
        unit = "GRAMS"
    elif "ounce" in s or " oz" in s or s.endswith("oz"):
        unit = "OUNCES"
    elif "milligram" in s or " mg" in s:
        value = value / 1000
        unit = "GRAMS"
    else:
        unit = "POUNDS"

    return round(value, 4), unit

def _build_measurement(variant_data: dict) -> dict:
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

def _normalize_compare_at_price(compare_at_price, price) -> str | None:
    if compare_at_price is None:
        return None

    try:
        cap = float(compare_at_price)
        price_f = float(price)

        if cap <= price_f:
            logger.warning(f"⚠️ compare_at_price (${cap}) <= price (${price_f}) — skipping")
            return None

        return f"{cap:.2f}"

    except (ValueError, TypeError) as e:
        logger.warning(f"⚠️ Invalid compare_at_price: {compare_at_price} — {e}")
        return None

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

    if weight:
        measurement = _build_measurement({"weight": weight})
        if measurement:
            inventory_item_input["measurement"] = measurement
            logger.info(f"   ⚖️ Weight mapped: {weight} → {measurement['weight']['value']} {measurement['weight']['unit']}")

    variant_input = {
        "id": variant_id,
        "price": str(price),
        "inventoryItem": inventory_item_input,
    }

    cap_str = _normalize_compare_at_price(compare_at_price, price)
    if cap_str:
        variant_input["compareAtPrice"] = cap_str
        logger.info(f"   💰 Compare-at price set: ${cap_str}")

    variables = {
        "productId": product_id,
        "variants": [variant_input],
    }

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Variant update errors: {result['errors']}")
        return False

    update_errors = result.get("data", {}).get("productVariantsBulkUpdate", {}).get("userErrors", [])

    if update_errors:
        logger.error(f"❌ Variant update user errors: {update_errors}")
        return False

    updated = result.get("data", {}).get("productVariantsBulkUpdate", {}).get("productVariants", [])

    if updated:
        v = updated[0]
        measurement = v.get("inventoryItem", {}).get("measurement") or {}
        weight_data = measurement.get("weight") or {}
        logger.info(f"✅ Variant updated: price=${v.get('price')}, compare_at=${v.get('compareAtPrice')}, sku={v.get('inventoryItem', {}).get('sku', 'N/A')}, weight={weight_data.get('value', 'N/A')} {weight_data.get('unit', '')}")
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

    user_errors = update_result.get("data", {}).get("productSet", {}).get("userErrors", [])

    if user_errors:
        logger.error(f"❌ Option create user errors: {user_errors}")
        return False

    logger.info(f"   ✅ Option '{option_name}' created successfully")
    return True


# ============================================
# ✅ NAYA FUNCTION: ASSIGN IMAGE TO VARIANT
# ============================================
async def _assign_image_to_variant(shop: str, access_token: str, product_id: str, variant_id: str, image_url: str):
    """Naye variant ki image product media mein add karke variant se link karein."""
    logger.info(f"   🖼️ Assigning image to variant: {image_url[:50]}...")
    
    # 1. Pehle check karein ke kya image pehle se product mein hai?
    query_media = """
    query getProductMedia($id: ID!) {
      product(id: $id) {
        media(first: 50) {
          edges {
            node {
              id
              ... on MediaImage { image { url } }
            }
          }
        }
      }
    }
    """
    res_existing = await shopify_graphql(shop, access_token, query_media, {"id": product_id})
    existing_media_id = None
    
    if "errors" not in res_existing:
        edges = res_existing.get("data", {}).get("product", {}).get("media", {}).get("edges", [])
        for edge in edges:
            node = edge.get("node", {})
            img_data = node.get("image") or {}
            if img_data.get("url") == image_url:
                existing_media_id = node.get("id")
                break

    media_id = existing_media_id

    # 2. Agar image nahi mili, to upload karein
    if not media_id:
        mutation_media = """
        mutation productCreateMedia($productId: ID!, $media: [CreateMediaInput!]!) {
          productCreateMedia(productId: $productId, media: $media) {
            media {
              id
            }
            mediaUserErrors { field message }
          }
        }
        """
        media_input = [{"originalSource": image_url, "mediaContentType": "IMAGE"}]
        result_media = await shopify_graphql(shop, access_token, mutation_media, {"productId": product_id, "media": media_input})
        
        if "errors" not in result_media:
            created_media = result_media.get("data", {}).get("productCreateMedia", {}).get("media", [])
            if created_media:
                media_id = created_media[0].get("id")
                logger.info(f"   ⏳ Image uploaded, waiting for Shopify to process...")
                await asyncio.sleep(2)  # ✅ Shopify ko process karne ka time dein

    if not media_id:
        logger.warning("⚠️ Could not get or create media ID.")
        return
    
    # 3. Variant ko image ke sath link karein
    mutation_variant = """
    mutation productVariantsBulkUpdate(
      $productId: ID!,
      $variants: [ProductVariantsBulkInput!]!
    ) {
      productVariantsBulkUpdate(productId: $productId, variants: $variants) {
        productVariants {
          id
          image { id url }
        }
        userErrors { field message }
      }
    }
    """
    variant_input = {"id": variant_id, "mediaId": media_id}
    result_var = await shopify_graphql(shop, access_token, mutation_variant, {"productId": product_id, "variants": [variant_input]})
    
    if "errors" in result_var:
        logger.warning(f"⚠️ Failed to link image to variant: {result_var['errors']}")
    else:
        logger.info(f"✅ Image assigned to variant successfully")


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
    """Existing product mein naya variant add karo (weight + compare-at + image)."""
    if not all_options:
        option_name = variant_data.get("option_name") or "Style"
        option_value = variant_data.get("title") or "Default"
        all_options = [{"name": option_name, "value": option_value}]

    logger.info(f"   Adding variant: " + " / ".join(f"{o['name']}={o['value']}" for o in all_options))

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
    price_value = variant_data.get("price", 0)

    inventory_item_input = {"tracked": True}
    if sku_value:
        inventory_item_input["sku"] = sku_value

    measurement = _build_measurement(variant_data)
    if measurement:
        inventory_item_input["measurement"] = measurement
        logger.info(f"   ⚖️ Weight mapped: {measurement['weight']['value']} {measurement['weight']['unit']}")

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

    variants_input = {
        "optionValues": option_values,
        "price": str(price_value),
        "inventoryItem": inventory_item_input,
    }

    compare_at_price = variant_data.get("compare_at_price")
    cap_str = _normalize_compare_at_price(compare_at_price, price_value)
    if cap_str:
        variants_input["compareAtPrice"] = cap_str
        logger.info(f"   💰 Compare-at price set: ${cap_str}")

    variables = {"productId": product_id, "variants": [variants_input]}

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Variant create error: {result['errors']}")
        return result

    var_errors = result.get("data", {}).get("productVariantsBulkCreate", {}).get("userErrors", [])

    if var_errors:
        for err in var_errors:
            msg = (err.get("message") or "").lower()
            if "already exists" in msg:
                logger.info(f"ℹ️ Variant already exists: {msg}")
                return {"already_exists": True, "userErrors": var_errors}

        logger.error(f"❌ Variant create user errors: {var_errors}")
        return result

    created = result.get("data", {}).get("productVariantsBulkCreate", {}).get("productVariants", [])

    if created:
        v = created[0]
        variant_id = v.get("id")
        measurement_resp = v.get("inventoryItem", {}).get("measurement") or {}
        weight_data = measurement_resp.get("weight") or {}

        logger.info(f"✅ Variant added: {v.get('title')} — ${v.get('price')} — compare_at: ${v.get('compareAtPrice', 'N/A')} — SKU: {v.get('inventoryItem', {}).get('sku', 'N/A')} — Weight: {weight_data.get('value', 'N/A')} {weight_data.get('unit', '')}")

        inv_item_id = v.get("inventoryItem", {}).get("id")
        stock = variant_data.get("stock", 0)
        if inv_item_id and stock:
            await set_inventory_quantity(
                shop=shop,
                access_token=access_token,
                inventory_item_id=inv_item_id,
                quantity=stock,
            )

        # ✅ Image assign karein
        image_url = variant_data.get("image_url")
        if variant_id and image_url:
            await _assign_image_to_variant(shop, access_token, product_id, variant_id, image_url)

    return result