# ============================================
# app/services/shopify.py
# Shopify OAuth + GraphQL Admin API + ID Token Verify
# + Product Status Update (OUT OF STOCK tracking)
# + Inventory Tracking (with changeFromQuantity)
# + Storefront API (real-time availability check)
# + 5 Metafields: asin, rating, amazon_price, reviews_count, availability
# + Variations Support (parent + variant creation & auto-grouping)
# + Option Existence Check (via productSet)
# + ✅ FIXED: sync_update_shopify_price is async
# + ✅ FIXED: refresh_shopify_token() helper
# + ✅ FIXED: sync_update_shopify_price auto-refresh on 401 AND 403
# + ✅ FIXED: expiring:"1" WAPAS ADD KIYA (Shopify permanent reject karta hai)
# + ✅ FIXED: exchange_code_for_token ab DICT return karta hai
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
# HELPER: Safe API version
# ============================================
def _safe_api_version() -> str:
    """2026-10 / unstable / empty ko 2025-01 pe fallback karo."""
    v = (settings.SHOPIFY_API_VERSION or "2025-01").strip()
    if v in ("2026-10", "unstable", ""):
        return "2025-01"
    return v


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
    secret = (settings.SHOPIFY_API_SECRET or "").strip().strip('"').strip("'")
    api_key = (settings.SHOPIFY_API_KEY or "").strip().strip('"').strip("'")
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=api_key,
            leeway=10,
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
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
            logger.warning(
                f"ID token diag | token aud={unverified.get('aud')} "
                f"iss={unverified.get('iss')} | server api_key={api_key} "
                f"secret_prefix={secret[:10]}... secret_len={len(secret)}"
            )
        except Exception:
            pass
        raise ValueError(f"Invalid token: {e}")


# ============================================
# OAUTH: ACCESS TOKEN EXCHANGE
# ✅ FIXED: ab DICT return karta hai (na ki string)
# ============================================
async def exchange_code_for_token(shop: str, code: str) -> Optional[dict]:
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
            logger.info(f"✅ Token exchanged for {shop}")
            return {
                "access_token": data.get("access_token"),
                "scope": data.get("scope"),
                "expires_in": data.get("expires_in"),
                "refresh_token": data.get("refresh_token"),
                "refresh_token_expires_in": data.get("refresh_token_expires_in"),
            }
    except Exception as e:
        logger.error(f"Token exchange fail: {e}")
        return None


# ============================================
# TOKEN EXCHANGE (Session/ID token → Offline access token)
# ✅ FIXED: "expiring": "1" WAPAS ADD KIYA
# ============================================
async def exchange_id_token_for_offline_token(
    shop: str, id_token: str
) -> Optional[dict]:
    url = f"https://{shop}/admin/oauth/access_token"

    payload = {
        "client_id": (settings.SHOPIFY_API_KEY or "").strip(),
        "client_secret": (settings.SHOPIFY_API_SECRET or "").strip(),
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token": id_token,
        "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
        "requested_token_type": (
            "urn:shopify:params:oauth:token-type:offline-access-token"
        ),
        # ✅ WAPAS ADD KIYA — Shopify permanent tokens reject karta hai
        "expiring": "1",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Accept": "application/json"},
            )
            if response.status_code != 200:
                logger.error(
                    f"❌ Token exchange (id_token) failed for {shop}: "
                    f"{response.status_code} {response.text}"
                )
                return None
            data = response.json()
            logger.info(f"✅ Offline token obtained via token exchange: {shop}")
            return {
                "access_token": data.get("access_token"),
                "scope": data.get("scope"),
                "expires_in": data.get("expires_in"),
                "refresh_token": data.get("refresh_token"),
                "refresh_token_expires_in": data.get("refresh_token_expires_in"),
            }
    except Exception as e:
        logger.error(f"Token exchange (id_token) error for {shop}: {e}")
        return None


# ============================================
# ✅ TOKEN REFRESH
# ============================================
async def refresh_shopify_token(
    shop_domain: str,
    refresh_token: str,
) -> Optional[dict]:
    """
    Expired access token ko refresh token se renew karo.
    Shopify expiring offline tokens ke liye.
    """
    if not refresh_token:
        logger.warning(f"No refresh_token for {shop_domain}")
        return None

    url = f"https://{shop_domain}/admin/oauth/access_token"

    payload = {
        "client_id": (settings.SHOPIFY_API_KEY or "").strip(),
        "client_secret": (settings.SHOPIFY_API_SECRET or "").strip(),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Accept": "application/json"},
            )
            if response.status_code != 200:
                logger.error(
                    f"❌ Token refresh failed for {shop_domain}: "
                    f"{response.status_code} {response.text[:200]}"
                )
                return None
            data = response.json()
            logger.info(f"✅ Access token refreshed for {shop_domain}")
            return {
                "access_token": data.get("access_token"),
                "scope": data.get("scope"),
                "expires_in": data.get("expires_in"),
                "refresh_token": data.get("refresh_token"),
                "refresh_token_expires_in": data.get("refresh_token_expires_in"),
            }
    except Exception as e:
        logger.error(f"Token refresh error for {shop_domain}: {e}")
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
    api_version = _safe_api_version()
    url = f"https://{shop}/admin/api/{api_version}/graphql.json"

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
            if response.status_code >= 400:
                body = response.text[:1000]
                logger.error(
                    f"GraphQL HTTP {response.status_code} for {shop}: {body}"
                )
                return {
                    "errors": [
                        {
                            "message": f"HTTP {response.status_code}: {body}",
                            "status": response.status_code,
                        }
                    ]
                }
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
# SET PRODUCT METAFIELDS
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

    return True


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

        new_options.append({
            "name": name,
            "values": values_as_dicts,
        })

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

    logger.info(f"✅ Product created: {shopify_product.get('title')}")

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

    return result


# ============================================
# ADD VARIANT TO EXISTING PRODUCT
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
        f"{_safe_api_version()}/graphql.json"
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


# ============================================
# ✅ SYNC SHOPIFY PRICE UPDATE
# Async + auto-refresh on 401 AND 403
# ============================================
async def sync_update_shopify_price(
    shop_domain: str,
    access_token: str,
    shopify_product_id: str,
    new_price: float,
    refresh_token: Optional[str] = None,
) -> bool:
    """
    Shopify product ka price asynchronously update karein.
    Sab variants ka price set ho jayega.
    401/403 pe refresh_token se auto-retry.
    """
    if not all([shop_domain, access_token, shopify_product_id]):
        logger.warning("Shopify sync skipped: missing config")
        return False

    # GID format
    if not str(shopify_product_id).startswith("gid://"):
        product_gid = f"gid://shopify/Product/{shopify_product_id}"
    else:
        product_gid = shopify_product_id

    # ✅ API version safety check
    api_version = _safe_api_version()

    api_url = (
        f"https://{shop_domain}/admin/api/"
        f"{api_version}/graphql.json"
    )

    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }

    # Step 1: Fetch variants
    get_variants_query = """
    query getProductVariants($id: ID!) {
      product(id: $id) {
        id
        title
        variants(first: 50) {
          edges {
            node {
              id
              title
              price
            }
          }
        }
      }
    }
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                api_url,
                headers=headers,
                json={
                    "query": get_variants_query,
                    "variables": {"id": product_gid},
                },
            )
            # ✅ FIXED: 401 AND 403 pe refresh karo
            if res.status_code in (401, 403):
                if refresh_token:
                    logger.warning(
                        f"🔄 {res.status_code} — refreshing token for "
                        f"{shop_domain} and retrying..."
                    )
                    new_data = await refresh_shopify_token(
                        shop_domain, refresh_token
                    )
                    if new_data and new_data.get("access_token"):
                        return await sync_update_shopify_price(
                            shop_domain=shop_domain,
                            access_token=new_data["access_token"],
                            shopify_product_id=shopify_product_id,
                            new_price=new_price,
                            refresh_token=new_data.get("refresh_token"),
                        )
                logger.error(
                    f"❌ {res.status_code} Unauthorized for {shop_domain} "
                    f"(no valid refresh_token). "
                    f"Response: {res.text[:300]}"
                )
                return False

            res.raise_for_status()
            data = res.json()

        if "errors" in data:
            logger.error(f"❌ Shopify variants fetch errors: {data['errors']}")
            return False

        product = data.get("data", {}).get("product")
        if not product:
            logger.error(f"❌ Shopify product not found: {product_gid}")
            return False

        variant_edges = product.get("variants", {}).get("edges", [])
        if not variant_edges:
            logger.warning(f"⚠️ No variants found for: {product_gid}")
            return False

        # Step 2: Update all variants' price
        variants_to_update = [
            {
                "id": edge["node"]["id"],
                "price": str(new_price),
            }
            for edge in variant_edges
        ]

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
            }
            userErrors {
              field
              message
            }
          }
        }
        """

        async with httpx.AsyncClient(timeout=30.0) as client:
            update_res = await client.post(
                api_url,
                headers=headers,
                json={
                    "query": mutation,
                    "variables": {
                        "productId": product_gid,
                        "variants": variants_to_update,
                    },
                },
            )
            update_res.raise_for_status()
            update_data = update_res.json()

        if "errors" in update_data:
            logger.error(f"❌ Shopify update errors: {update_data['errors']}")
            return False

        user_errors = (
            update_data.get("data", {})
            .get("productVariantsBulkUpdate", {})
            .get("userErrors", [])
        )

        if user_errors:
            logger.error(f"❌ Shopify user errors: {user_errors}")
            return False

        updated = (
            update_data.get("data", {})
            .get("productVariantsBulkUpdate", {})
            .get("productVariants", [])
        )

        logger.info(
            f"✅ Shopify price updated: {len(updated)} variant(s) → ${new_price}"
        )
        return True

    except httpx.HTTPStatusError as e:
        logger.error(
            f"❌ Shopify HTTP error: {e.response.status_code} — "
            f"{e.response.text[:200]}"
        )
        return False
    except Exception as e:
        logger.error(f"❌ Shopify sync failed: {e}")
        return False