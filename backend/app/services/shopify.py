# ============================================
# app/services/shopify.py
# Shopify OAuth + GraphQL Admin API + ID Token Verify
# + Product Status Update (OUT OF STOCK tracking)
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
    """
    Shopify OAuth authorization URL banata hai.
    Merchant is URL par jaakar app install karega.
    """
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
    """
    Shopify se aane wale OAuth callback ka HMAC verify karta hai.
    Security ke liye zaroori hai.
    """
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
# ID TOKEN VERIFY KARO (Strict Mode)
# ============================================
def verify_id_token(token: str) -> dict:
    """
    Shopify ID token (JWT) verify karta hai.
    Strict mode — saare claims check hote hain.
    """
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
            payload.get("dest", "")
            .replace("https://", "")
            .split("/")[0]
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
    """
    OAuth code ko access token se exchange karta hai.
    Ye token permanent hai — DB mein save karna hai.
    """
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
# GRAPHQL API CALL
# ============================================
async def shopify_graphql(
    shop: str,
    access_token: str,
    query: str,
    variables: dict = None,
) -> dict:
    """
    Shopify Admin GraphQL API ko call karta hai.
    """
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
# PRODUCT CREATE KARO (GraphQL)
# ============================================
async def create_shopify_product(
    shop: str,
    access_token: str,
    product_data: dict,
) -> dict:
    """
    Shopify mein naya product create karta hai.
    """

    # ========================================
    # STEP 1: Product create
    # ========================================
    mutation_create = """
    mutation productCreate($input: ProductCreateInput!) {
      productCreate(product: $input) {
        product {
          id
          title
          handle
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    input_data = {
        "title": product_data.get("title") or "Untitled Product",
        "descriptionHtml": product_data.get("description", ""),
        "vendor": product_data.get("brand", ""),
        "status": "ACTIVE",
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
    logger.info(f"   Product ID: {product_id}")

    # ========================================
    # STEP 2: Price update (variant)
    # ========================================
    price_value = product_data.get("price", "0.00")
    try:
        price_float = float(price_value) if price_value else 0.0
    except (ValueError, TypeError):
        price_float = 0.0

    logger.info(f"   Target price: ${price_float}")

    if product_id and price_float > 0:
        query_variants = """
        query getProductVariants($id: ID!) {
          product(id: $id) {
            variants(first: 5) {
              edges {
                node {
                  id
                  price
                  title
                }
              }
            }
          }
        }
        """

        variant_result = await shopify_graphql(
            shop, access_token, query_variants, {"id": product_id}
        )

        variants_data = (
            variant_result.get("data", {})
            .get("product", {})
            .get("variants", {})
            .get("edges", [])
        )

        logger.info(f"   Variants found: {len(variants_data)}")

        if variants_data:
            variant_id = variants_data[0]["node"]["id"]
            logger.info(f"   Variant ID: {variant_id}")

            mutation_update = """
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

            variables_update = {
                "productId": product_id,
                "variants": [
                    {
                        "id": variant_id,
                        "price": str(price_float),
                    }
                ],
            }

            update_result = await shopify_graphql(
                shop, access_token, mutation_update, variables_update
            )

            update_errors = (
                update_result.get("data", {})
                .get("productVariantsBulkUpdate", {})
                .get("userErrors", [])
            )

            if update_errors:
                logger.error(f"❌ Price update errors: {update_errors}")
            else:
                updated_variants = (
                    update_result.get("data", {})
                    .get("productVariantsBulkUpdate", {})
                    .get("productVariants", [])
                )
                if updated_variants:
                    final_price = updated_variants[0].get("price")
                    logger.info(f"✅ Price updated to: ${final_price}")
        else:
            logger.warning("⚠️ No variants found after create")

    # ========================================
    # STEP 3: Images add karo
    # ========================================
    images = product_data.get("images", [])
    if product_id and images:
        logger.info(f"   Adding {len(images)} images...")
        images_result = await add_product_images(
            shop=shop,
            access_token=access_token,
            product_id=product_id,
            image_urls=images[:10],
        )

        if "errors" in images_result:
            logger.warning(f"⚠️ Images add fail: {images_result['errors']}")

    return result


# ============================================
# PRODUCT IMAGES ADD KARO (Media API)
# ============================================
async def add_product_images(
    shop: str,
    access_token: str,
    product_id: str,
    image_urls: list,
) -> dict:
    """
    Product ke liye images add karta hai (Shopify Media API se).
    """
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
# ✅ NAYA — PRODUCT STATUS UPDATE
# (In Stock ↔ Out of Stock)
# write_products scope se kaam karta hai
# ============================================
async def update_shopify_product_status(
    shop: str,
    access_token: str,
    shopify_product_id: str,
    is_available: bool,
) -> bool:
    """
    Shopify product ka status update karta hai.

    - is_available = True  → status = ACTIVE  (In Stock)
    - is_available = False → status = DRAFT   (Sold Out / Out of Stock)

    Yeh `write_products` scope se kaam karta hai —
    koi naya scope add karne ki zaroorat nahi.
    """
    # ID format check karo
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

    logger.info(
        f"Shopify status update: product={product_gid}, status={new_status}"
    )

    result = await shopify_graphql(
        shop, access_token, mutation, variables
    )

    # Errors check
    if "errors" in result:
        logger.error(f"❌ Status update GraphQL errors: {result['errors']}")
        return False

    update_data = result.get("data", {}).get("productUpdate", {})
    user_errors = update_data.get("userErrors", [])

    if user_errors:
        logger.error(f"❌ Status update user errors: {user_errors}")
        return False

    product = update_data.get("product", {})
    logger.info(
        f"✅ Shopify status updated: "
        f"{product.get('title')} → {product.get('status')}"
    )
    return True


# ============================================
# ✅ NAYA — SHOPIFY PRODUCT DHUNDO SKU SE
# ============================================
async def get_shopify_product_by_sku(
    shop: str,
    access_token: str,
    sku: str,
) -> Optional[str]:
    """
    Shopify product ID dhundo SKU (ASIN) se.
    Returns: Shopify Product GID (e.g., "gid://shopify/Product/12345")
    """
    query = """
    query getProductBySku($query: String!) {
      products(first: 1, query: $query) {
        edges {
          node {
            id
            title
            status
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
        result.get("data", {})
        .get("products", {})
        .get("edges", [])
    )

    if edges:
        product_gid = edges[0]["node"]["id"]
        logger.info(f"Found Shopify product: {product_gid} for SKU={sku}")
        return product_gid

    logger.warning(f"No Shopify product found for SKU={sku}")
    return None