# ============================================
# app/services/shopify.py
# Shopify OAuth + GraphQL Admin API + ID Token Verify
# + Product Status Update (OUT OF STOCK tracking)
# + Inventory Tracking (with changeFromQuantity)
# + 2026-07 API compatible (variants removed from productCreate)
# + Storefront API (real-time availability check)
# + 5 Metafields: asin, rating, amazon_price, reviews_count, availability
#   (parent_asin — temporarily disabled due to fake ASINs from Bright Data)
# + Variations Support (parent + variant creation & auto-grouping)
# + Option Existence Check (via productSet — 2026-07 compatible)
# ============================================

import hashlib
import hmac
import logging
import time
from typing import Optional
from urllib.parse import urlencode

import httpx
import jwt

from app.config import settings

logger = logging.getLogger(__name__)


# ============================================
# OAUTH: AUTH URL BANAO
# ============================================
def build_auth_url(shop: str, state: str = "default") -> str:
    params = {
        "client_id": settings.SHOPIFY_API_KEY,
        "scope": settings.SHOPIFY_SCOPES,
        "redirect_uri": settings.SHOPIFY_REDIRECT_URI,
        "state": state,
    }
    return f"https://{shop}/admin/oauth/authorize?{urlencode(params)}"


# ============================================
# OAUTH: HMAC VERIFY KARO
# ============================================
def verify_hmac(query_params: dict) -> bool:
    received_hmac = query_params.get("hmac")
    if not received_hmac:
        return False

    params = {k: v for k, v in query_params.items() if k != "hmac"}
    sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))

    computed_hmac = hmac.new(
        settings.SHOPIFY_API_SECRET.encode(),
        sorted_params.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed_hmac, received_hmac)


# ============================================
# ID TOKEN VERIFY (Strict Mode)
# ============================================
def verify_id_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.SHOPIFY_API_SECRET,
            algorithms=["HS256"],
            audience=settings.SHOPIFY_API_KEY,
        )

        now = int(time.time())

        if payload.get("exp", 0) < now:
            raise ValueError("Token expired")

        if payload.get("nbf", 0) > now:
            raise ValueError("Token not yet valid")

        iss = payload.get("iss", "")
        if not iss.startswith("https://"):
            raise ValueError("Invalid issuer")

        iss_domain = iss.replace("https://", "").split("/")[0]
        dest_domain = (
            payload.get("dest", "").replace("https://", "").split("/")[0]
        )

        if iss_domain != dest_domain:
            raise ValueError("Domain mismatch")

        if not iss_domain.endswith(".myshopify.com"):
            raise ValueError("Not a valid Shopify store")

        logger.info(f"ID token verified for: {iss_domain}")
        return payload

    except jwt.ExpiredSignatureError:
        raise ValueError("Token expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {e}")


# ============================================
# OAUTH: ACCESS TOKEN EXCHANGE
# ============================================
async def exchange_code_for_token(shop: str, code: str) -> Optional[str]:
    url = f"https://{shop}/admin/oauth/access_token"

    payload = {
        "client_id": settings.SHOPIFY_API_KEY,
        "client_secret": settings.SHOPIFY_API_SECRET,
        "code": code,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("access_token")
    except Exception as e:
        logger.error(f"Token exchange fail: {e}")
        return None


# ============================================
# GRAPHQL API CALL (Admin API)
# ============================================
async def shopify_graphql(
    shop: str,
    access_token: str,
    query: str,
    variables: dict = None,
) -> dict:
    url = (
        f"https://{shop}/admin/api/"
        f"{settings.SHOPIFY_API_VERSION}/graphql.json"
    )

    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }

    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"GraphQL call fail: {e}")
        return {"errors": [{"message": str(e)}]}


# ============================================
# PRIMARY LOCATION DHUNDO
# ============================================
async def get_primary_location(shop: str, access_token: str) -> Optional[str]:
    query = """
    query {
      locations(first: 10) {
        edges {
          node {
            id
            name
            isActive
            isPrimary
          }
        }
      }
    }
    """

    result = await shopify_graphql(shop, access_token, query)

    if "errors" in result:
        logger.error(f"Location query errors: {result['errors']}")
        return None

    edges = result.get("data", {}).get("locations", {}).get("edges", [])

    if not edges:
        logger.warning("No location found")
        return None

    for edge in edges:
        node = edge["node"]
        name = node.get("name", "")
        if "shop location" in name.lower():
            logger.info(f"✅ Shop location found: {node['id']}")
            return node["id"]

    for edge in edges:
        node = edge["node"]
        if node.get("isPrimary"):
            logger.info(f"✅ Primary location: {node['id']}")
            return node["id"]

    for edge in edges:
        node = edge["node"]
        if node.get("isActive"):
            logger.info(f"✅ First active location: {node['id']}")
            return node["id"]

    location_id = edges[0]["node"]["id"]
    logger.info(f"✅ Fallback location: {location_id}")
    return location_id


# ============================================
# INVENTORY SET KARO
# ============================================
async def set_inventory_quantity(
    shop: str,
    access_token: str,
    inventory_item_id: str,
    quantity: int,
) -> bool:
    import uuid

    location_id = await get_primary_location(shop, access_token)
    if not location_id:
        logger.warning("No location — inventory set nahi hoga")
        return False

    query_current = """
    query getInventoryLevel($inventoryItemId: ID!, $locationId: ID!) {
      inventoryItem(id: $inventoryItemId) {
        inventoryLevel(locationId: $locationId) {
          quantities(names: ["available"]) {
            name
            quantity
          }
        }
      }
    }
    """

    current_result = await shopify_graphql(
        shop,
        access_token,
        query_current,
        {"inventoryItemId": inventory_item_id, "locationId": location_id},
    )

    current_qty = 0
    try:
        quantities = (
            current_result.get("data", {})
            .get("inventoryItem", {})
            .get("inventoryLevel", {})
            .get("quantities", [])
        )
        for q in quantities:
            if q.get("name") == "available":
                current_qty = q.get("quantity", 0)
                break
    except Exception:
        current_qty = 0

    logger.info(f"   Current inventory: {current_qty}, target: {quantity}")

    idempotency_key = str(uuid.uuid4())

    mutation = """
    mutation inventorySetQuantities($input: InventorySetQuantitiesInput!) {
      inventorySetQuantities(input: $input) @idempotent(key: "%s") {
        inventoryAdjustmentGroup {
          createdAt
          reason
        }
        userErrors {
          field
          message
        }
      }
    }
    """ % idempotency_key

    variables = {
        "input": {
            "name": "available",
            "reason": "correction",
            "quantities": [
                {
                    "inventoryItemId": inventory_item_id,
                    "locationId": location_id,
                    "quantity": quantity,
                    "changeFromQuantity": current_qty,
                }
            ],
        }
    }

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Inventory set GraphQL errors: {result['errors']}")
        return False

    inv_errors = (
        result.get("data", {})
        .get("inventorySetQuantities", {})
        .get("userErrors", [])
    )

    if inv_errors:
        logger.error(f"❌ Inventory set user errors: {inv_errors}")
        return False

    logger.info(f"✅ Inventory set to: {quantity}")
    return True


# ============================================
# VARIANT UPDATE WITH TRACKED
# ============================================
async def update_variant_with_tracked(
    shop: str,
    access_token: str,
    product_id: str,
    variant_id: str,
    price: float,
) -> bool:
    mutation = """
    mutation productVariantsBulkUpdate(
      $productId: ID!,
      $variants: [ProductVariantsBulkInput!]!
    ) {
      productVariantsBulkUpdate(
        productId: $productId,
        variants: $variants
      ) {
        productVariants {
          id
          price
          inventoryItem {
            id
            tracked
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "productId": product_id,
        "variants": [
            {
                "id": variant_id,
                "price": str(price),
                "inventoryItem": {
                    "tracked": True,
                },
            }
        ],
    }

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Variant update errors: {result['errors']}")
        return False

    update_errors = (
        result.get("data", {})
        .get("productVariantsBulkUpdate", {})
        .get("userErrors", [])
    )

    if update_errors:
        logger.error(f"❌ Variant update user errors: {update_errors}")
        return False

    updated = (
        result.get("data", {})
        .get("productVariantsBulkUpdate", {})
        .get("productVariants", [])
    )

    if updated:
        v = updated[0]
        logger.info(f"✅ Variant updated: price=${v.get('price')}, "
                    f"tracked={v.get('inventoryItem', {}).get('tracked')}")
        return True

    return False


# ============================================
# SET PRODUCT METAFIELDS (Separate Mutation)
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

    mutation = """
    mutation metafieldsSet($metafields: [MetafieldsSetInput!]!) {
      metafieldsSet(metafields: $metafields) {
        metafields {
          id
          namespace
          key
          value
        }
        userErrors {
          field
          message
          code
        }
      }
    }
    """

    metafields_with_owner = [
        {
            "ownerId": product_id,
            "namespace": mf["namespace"],
            "key": mf["key"],
            "value": mf["value"],
            "type": mf["type"],
        }
        for mf in metafields
    ]

    variables = {"metafields": metafields_with_owner}

    logger.info(f"   Setting {len(metafields)} metafields...")

    result = await shopify_graphql(
        shop, access_token, mutation, variables
    )

    if "errors" in result:
        logger.error(f"❌ Metafields set GraphQL errors: {result['errors']}")
        return False

    mf_data = result.get("data", {}).get("metafieldsSet", {})
    user_errors = mf_data.get("userErrors", [])

    if user_errors:
        logger.error(f"❌ Metafields set user errors: {user_errors}")
        return False

    created = mf_data.get("metafields", [])
    logger.info(f"✅ Metafields set successfully: {len(created)}")
    for mf in created:
        logger.info(f"   • {mf['namespace']}.{mf['key']} = {mf['value']}")

    return True


# ============================================
# ✅ ENSURE PRODUCT HAS OPTION (productSet — 2026-07 compatible)
# ============================================
async def ensure_product_has_option(
    shop: str,
    access_token: str,
    product_id: str,
    option_name: str,
    option_values: list,
) -> bool:
    """
    Product mein option exist karta hai ya nahi, check karta hai.
    Agar nahi, toh `productSet` mutation se add karta hai.
    Shopify API 2026-07 compatible.
    """
    # Pehle current options fetch karo
    query = """
    query getProductOptions($id: ID!) {
      product(id: $id) {
        id
        options {
          id
          name
          values
        }
      }
    }
    """

    result = await shopify_graphql(
        shop, access_token, query, {"id": product_id}
    )

    if "errors" in result:
        logger.error(f"❌ Failed to fetch options: {result['errors']}")
        return False

    product = result.get("data", {}).get("product")
    if not product:
        logger.error(f"❌ Product not found: {product_id}")
        return False

    existing_options = product.get("options", [])
    existing_names = [opt.get("name", "").lower() for opt in existing_options]

    # ✅ Agar option already exist karta hai, toh kuch nahi karna
    if option_name.lower() in existing_names:
        logger.info(f"   ✅ Option '{option_name}' already exists")
        return True

    # ❌ Agar nahi exist karta, toh productSet se update karo
    logger.info(f"   ➕ Creating option '{option_name}' with values: {option_values}")

    # ✅ Existing options prepare karo (Default Title skip karo)
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

        new_options.append({
            "name": name,
            "values": values_as_dicts,
        })

    # ✅ Naya option add karo
    new_option_values = []
    for v in option_values:
        if isinstance(v, str) and v:
            new_option_values.append({"name": v})
        elif isinstance(v, dict) and v.get("name"):
            new_option_values.append({"name": v["name"]})

    new_options.append({
        "name": option_name,
        "values": new_option_values,
    })

    # ✅ productSet mutation (2026-07 compatible)
    mutation = """
    mutation productSet($input: ProductSetInput!) {
      productSet(input: $input) {
        product {
          id
          options {
            id
            name
            values
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "input": {
            "id": product_id,
            "productOptions": new_options,
        }
    }

    update_result = await shopify_graphql(
        shop, access_token, mutation, variables
    )

    if "errors" in update_result:
        logger.error(
            f"❌ Option create errors: {update_result['errors']}"
        )
        return False

    user_errors = (
        update_result.get("data", {})
        .get("productSet", {})
        .get("userErrors", [])
    )

    if user_errors:
        logger.error(f"❌ Option create user errors: {user_errors}")
        return False

    logger.info(f"   ✅ Option '{option_name}' created successfully")
    return True


# ============================================
# ✅ CREATE PRODUCT WITH VARIANTS
# ============================================
async def create_shopify_product_with_variants(
    shop: str,
    access_token: str,
    product_data: dict,
    variants: list,
) -> dict:
    is_available = product_data.get("is_available", True)
    status = "ACTIVE" if is_available else "DRAFT"

    mutation_create = """
    mutation productCreate($input: ProductCreateInput!) {
      productCreate(product: $input) {
        product {
          id
          title
          handle
          options {
            id
            name
            values
          }
          variants(first: 50) {
            edges {
              node {
                id
                title
                price
                inventoryItem {
                  id
                  sku
                  tracked
                }
              }
            }
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    option_values = [{"name": v["title"]} for v in variants if v.get("title")]

    if not option_values:
        logger.warning("No option values provided — using default")
        option_values = [{"name": "Default"}]

    input_data = {
        "title": product_data.get("title") or "Untitled Product",
        "descriptionHtml": product_data.get("description", ""),
        "vendor": product_data.get("brand", ""),
        "status": status,
        "productOptions": [
            {
                "name": "Style",
                "values": option_values,
            }
        ],
    }

    result = await shopify_graphql(
        shop, access_token, mutation_create, {"input": input_data}
    )

    if "errors" in result:
        logger.error(f"❌ Product create error: {result['errors']}")
        return result

    product_create = result.get("data", {}).get("productCreate", {})
    user_errors = product_create.get("userErrors", [])

    if user_errors:
        logger.error(f"❌ Product user errors: {user_errors}")
        return result

    shopify_product = product_create.get("product", {})
    product_id = shopify_product.get("id")

    logger.info(f"✅ Product created with {len(option_values)} variants: {shopify_product.get('title')}")
    logger.info(f"   Product ID: {product_id}")

    variant_edges = (
        shopify_product.get("variants", {}).get("edges", [])
    )

    variants_to_update = []
    for idx, edge in enumerate(variant_edges):
        if idx >= len(variants):
            break

        shopify_variant = edge["node"]
        our_variant = variants[idx]

        variants_to_update.append({
            "id": shopify_variant["id"],
            "price": str(our_variant.get("price", 0)),
            "inventoryItem": {
                "sku": our_variant.get("sku", ""),
                "tracked": True,
            },
        })

    if variants_to_update:
        mutation_var = """
        mutation productVariantsBulkUpdate(
          $productId: ID!,
          $variants: [ProductVariantsBulkInput!]!
        ) {
          productVariantsBulkUpdate(
            productId: $productId,
            variants: $variants
          ) {
            productVariants {
              id
              title
              price
              inventoryItem {
                id
                sku
                tracked
              }
            }
            userErrors {
              field
              message
            }
          }
        }
        """

        var_result = await shopify_graphql(
            shop,
            access_token,
            mutation_var,
            {"productId": product_id, "variants": variants_to_update},
        )

        var_errors = (
            var_result.get("data", {})
            .get("productVariantsBulkUpdate", {})
            .get("userErrors", [])
        )
        if var_errors:
            logger.error(f"❌ Variant update errors: {var_errors}")
        else:
            logger.info(f"✅ {len(variants_to_update)} variants updated")

        updated_variants = (
            var_result.get("data", {})
            .get("productVariantsBulkUpdate", {})
            .get("productVariants", [])
        )

        for idx, var in enumerate(updated_variants):
            if idx >= len(variants):
                break

            our_variant = variants[idx]
            inv_item_id = var.get("inventoryItem", {}).get("id")
            stock = our_variant.get("stock", 0)

            if inv_item_id:
                await set_inventory_quantity(
                    shop=shop,
                    access_token=access_token,
                    inventory_item_id=inv_item_id,
                    quantity=stock,
                )

    images = product_data.get("images", [])
    if product_id and images:
        await add_product_images(
            shop=shop,
            access_token=access_token,
            product_id=product_id,
            image_urls=images[:10],
        )

    metafields_input = []

    asin_value = str(product_data.get("asin", "") or "")
    if asin_value and asin_value != "None":
        metafields_input.append({
            "namespace": "custom",
            "key": "asin",
            "value": asin_value,
            "type": "single_line_text_field",
        })

    rating_value = str(product_data.get("rating", "") or "")
    if rating_value and rating_value != "None":
        metafields_input.append({
            "namespace": "custom",
            "key": "rating",
            "value": rating_value,
            "type": "single_line_text_field",
        })

    reviews_count_value = product_data.get("reviews_count")
    if reviews_count_value is not None:
        reviews_count_str = str(reviews_count_value)
        if reviews_count_str and reviews_count_str != "None":
            metafields_input.append({
                "namespace": "custom",
                "key": "reviews_count",
                "value": reviews_count_str,
                "type": "single_line_text_field",
            })

    amazon_price_value = product_data.get("amazon_price")
    if amazon_price_value is not None:
        amazon_price_str = str(amazon_price_value)
        if amazon_price_str and amazon_price_str != "None":
            metafields_input.append({
                "namespace": "custom",
                "key": "amazon_price",
                "value": amazon_price_str,
                "type": "single_line_text_field",
            })

    availability_value = str(product_data.get("availability", "") or "")
    if availability_value and availability_value != "None":
        metafields_input.append({
            "namespace": "custom",
            "key": "availability",
            "value": availability_value,
            "type": "single_line_text_field",
        })

    if product_id and metafields_input:
        await set_product_metafields(
            shop=shop,
            access_token=access_token,
            product_id=product_id,
            metafields=metafields_input,
        )

    return result


# ============================================
# ✅ ADD VARIANT TO EXISTING PRODUCT
# ============================================
async def add_variant_to_existing_product(
    shop: str,
    access_token: str,
    product_id: str,
    variant_data: dict,
) -> dict:
    option_name = variant_data.get("option_name") or "Style"
    option_value = variant_data.get("title") or "Default"

    logger.info(f"   Adding variant: {option_name}={option_value}")

    # ✅ STEP 0: Ensure option exists
    option_exists = await ensure_product_has_option(
        shop=shop,
        access_token=access_token,
        product_id=product_id,
        option_name=option_name,
        option_values=[option_value],
    )

    if not option_exists:
        logger.error(
            f"❌ Could not ensure option '{option_name}' exists"
        )
        return {
            "errors": [
                {"message": f"Failed to create option '{option_name}'"}
            ]
        }

    # STEP 1: Add variant
    mutation = """
    mutation productVariantsBulkCreate(
      $productId: ID!,
      $variants: [ProductVariantsBulkInput!]!
    ) {
      productVariantsBulkCreate(
        productId: $productId,
        variants: $variants
      ) {
        productVariants {
          id
          title
          price
          inventoryItem {
            id
            sku
            tracked
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "productId": product_id,
        "variants": [
            {
                "optionValues": [
                    {"name": option_value, "optionName": option_name}
                ],
                "price": str(variant_data.get("price", 0)),
                "inventoryItem": {
                    "sku": variant_data.get("sku", ""),
                    "tracked": True,
                },
            }
        ],
    }

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Variant create error: {result['errors']}")
        return result

    var_errors = (
        result.get("data", {})
        .get("productVariantsBulkCreate", {})
        .get("userErrors", [])
    )
    if var_errors:
        logger.error(f"❌ Variant create user errors: {var_errors}")
        return result

    created = (
        result.get("data", {})
        .get("productVariantsBulkCreate", {})
        .get("productVariants", [])
    )

    if created:
        v = created[0]
        logger.info(f"✅ Variant added: {v.get('title')} — ${v.get('price')}")

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
# PRODUCT CREATE (SIMPLE)
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

    metafields_input = []

    asin_value = str(product_data.get("asin", "") or "")
    if asin_value and asin_value != "None":
        metafields_input.append({
            "namespace": "custom",
            "key": "asin",
            "value": asin_value,
            "type": "single_line_text_field",
        })
        logger.info(f"   ASIN metafield: {asin_value}")

    logger.info(f"   ⏭️ Parent ASIN skipped (temporarily disabled)")

    rating_value = str(product_data.get("rating", "") or "")
    if rating_value and rating_value != "None":
        metafields_input.append({
            "namespace": "custom",
            "key": "rating",
            "value": rating_value,
            "type": "single_line_text_field",
        })
        logger.info(f"   Rating metafield: {rating_value}")

    reviews_count_value = product_data.get("reviews_count")
    if reviews_count_value is not None:
        reviews_count_str = str(reviews_count_value)
        if reviews_count_str and reviews_count_str != "None":
            metafields_input.append({
                "namespace": "custom",
                "key": "reviews_count",
                "value": reviews_count_str,
                "type": "single_line_text_field",
            })
            logger.info(f"   Reviews Count metafield: {reviews_count_str}")

    amazon_price_value = product_data.get("amazon_price")
    if amazon_price_value is not None:
        amazon_price_str = str(amazon_price_value)
        if amazon_price_str and amazon_price_str != "None":
            metafields_input.append({
                "namespace": "custom",
                "key": "amazon_price",
                "value": amazon_price_str,
                "type": "single_line_text_field",
            })
            logger.info(f"   Amazon Price metafield: {amazon_price_str}")

    availability_value = str(product_data.get("availability", "") or "")
    if availability_value and availability_value != "None":
        metafields_input.append({
            "namespace": "custom",
            "key": "availability",
            "value": availability_value,
            "type": "single_line_text_field",
        })
        logger.info(f"   Availability metafield: {availability_value}")

    logger.info(f"   Total metafields to set: {len(metafields_input)}")

    input_data = {
        "title": product_data.get("title") or "Untitled Product",
        "descriptionHtml": product_data.get("description", ""),
        "vendor": product_data.get("brand", ""),
        "status": status,
    }

    variant_attrs = product_data.get("variant_attributes") or []
    product_options = []

    for attr in variant_attrs:
        if not isinstance(attr, dict):
            continue
        name = (attr.get("name") or "").strip()
        value = (attr.get("value") or "").strip()
        if name.lower() in ("size", "color", "style") and value:
            product_options.append({
                "name": name,
                "values": [{"name": value}],
            })
            break

    if product_options:
        input_data["productOptions"] = product_options
        logger.info(f"   ✅ Product options: {product_options}")

    mutation_create = """
    mutation productCreate($input: ProductCreateInput!) {
      productCreate(product: $input) {
        product {
          id
          title
          handle
          options {
            id
            name
            values
          }
          variants(first: 5) {
            edges {
              node {
                id
                title
                price
                inventoryItem {
                  id
                  tracked
                }
              }
            }
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    result = await shopify_graphql(
        shop, access_token, mutation_create, {"input": input_data}
    )

    if "errors" in result:
        logger.error(f"❌ Product create error: {result['errors']}")
        return result

    product_create = result.get("data", {}).get("productCreate", {})
    user_errors = product_create.get("userErrors", [])

    if user_errors:
        logger.error(f"❌ Product user errors: {user_errors}")
        return result

    shopify_product = product_create.get("product", {})
    product_id = shopify_product.get("id")

    logger.info(f"✅ Product created: {shopify_product.get('title')}")
    logger.info(f"   Product ID: {product_id}")

    if product_id and metafields_input:
        await set_product_metafields(
            shop=shop,
            access_token=access_token,
            product_id=product_id,
            metafields=metafields_input,
        )

    variants_edges = (
        shopify_product.get("variants", {}).get("edges", [])
    )

    variant_id = None
    inventory_item_id = None

    if variants_edges:
        variant_node = variants_edges[0]["node"]
        variant_id = variant_node.get("id")
        inventory_item_id = (
            variant_node.get("inventoryItem", {}).get("id")
        )

    if product_id and variant_id and price_float > 0:
        await update_variant_with_tracked(
            shop=shop,
            access_token=access_token,
            product_id=product_id,
            variant_id=variant_id,
            price=price_float,
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
        media {
          ... on MediaImage {
            id
            image {
              url
            }
          }
        }
        mediaUserErrors {
          field
          message
        }
      }
    }
    """

    media_input = [
        {
            "originalSource": url,
            "mediaContentType": "IMAGE",
        }
        for url in image_urls
        if url
    ]

    if not media_input:
        return {}

    variables = {
        "productId": product_id,
        "media": media_input,
    }

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
        product_gid = f"gid://shopify/Product/{shopify_product_id}"
    else:
        product_gid = shopify_product_id

    new_status = "ACTIVE" if is_available else "DRAFT"

    mutation = """
    mutation updateProductStatus($input: ProductInput!) {
      productUpdate(input: $input) {
        product {
          id
          title
          status
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "input": {
            "id": product_gid,
            "status": new_status,
        }
    }

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Status update GraphQL errors: {result['errors']}")
        return False

    update_data = result.get("data", {}).get("productUpdate", {})
    user_errors = update_data.get("userErrors", [])

    if user_errors:
        logger.error(f"❌ Status update user errors: {user_errors}")
        return False

    return True


# ============================================
# SHOPIFY PRODUCT DHUNDO SKU SE
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
            id
            title
            status
            variants(first: 1) {
              edges {
                node {
                  id
                  inventoryItem {
                    id
                  }
                }
              }
            }
          }
        }
      }
    }
    """

    result = await shopify_graphql(
        shop, access_token, query, {"query": f"sku:{sku}"}
    )

    if "errors" in result:
        logger.error(f"SKU search errors: {result['errors']}")
        return None

    edges = (
        result.get("data", {}).get("products", {}).get("edges", [])
    )

    if edges:
        product_gid = edges[0]["node"]["id"]
        logger.info(f"Found Shopify product: {product_gid} for SKU={sku}")
        return product_gid

    logger.warning(f"No Shopify product found for SKU={sku}")
    return None


# ============================================
# STOREFRONT API — AVAILABILITY CHECK
# ============================================
async def check_product_availability(
    shopify_product_id: str,
) -> dict:
    if not shopify_product_id.startswith("gid://"):
        product_gid = f"gid://shopify/Product/{shopify_product_id}"
    else:
        product_gid = shopify_product_id

    store_domain = settings.SHOPIFY_SHOP_URL
    storefront_token = settings.SHOPIFY_STOREFRONT_TOKEN

    if not storefront_token:
        logger.warning("Storefront token missing")
        return {
            "available": None,
            "error": "Storefront token not configured",
            "source": "none",
        }

    if not store_domain:
        logger.warning("Shop URL missing")
        return {
            "available": None,
            "error": "SHOPIFY_SHOP_URL not configured",
            "source": "none",
        }

    api_url = (
        f"https://{store_domain}/api/"
        f"{settings.SHOPIFY_API_VERSION}/graphql.json"
    )

    query = """
    query getProductAvailability($id: ID!) {
      product(id: $id) {
        id
        title
        availableForSale
        totalInventory
        variants(first: 10) {
          edges {
            node {
              id
              title
              availableForSale
              quantityAvailable
              price {
                amount
                currencyCode
              }
            }
          }
        }
      }
    }
    """

    headers = {
        "X-Shopify-Storefront-Access-Token": storefront_token,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                api_url,
                headers=headers,
                json={"query": query, "variables": {"id": product_gid}},
            )
            response.raise_for_status()
            data = response.json()

        product = data.get("data", {}).get("product")
        if not product:
            return {
                "available": False,
                "source": "shopify",
                "error": "Product not found in Shopify Storefront",
            }

        variants = []
        for edge in product.get("variants", {}).get("edges", []):
            v = edge["node"]
            variants.append({
                "id": v["id"],
                "title": v["title"],
                "available": v["availableForSale"],
                "quantity": v.get("quantityAvailable", 0),
                "price": float(v["price"]["amount"]),
                "currency": v["price"]["currencyCode"],
            })

        return {
            "available": product["availableForSale"],
            "quantity": product.get("totalInventory", 0),
            "title": product["title"],
            "variants": variants,
            "source": "shopify",
        }

    except httpx.HTTPStatusError as e:
        logger.error(
            f"Storefront API HTTP error: {e.response.status_code} — "
            f"{e.response.text[:200]}"
        )
        return {
            "available": None,
            "error": f"HTTP {e.response.status_code}",
            "source": "none",
        }
    except Exception as e:
        logger.error(f"Storefront API error: {e}")
        return {
            "available": None,
            "error": str(e),
            "source": "none",
        }