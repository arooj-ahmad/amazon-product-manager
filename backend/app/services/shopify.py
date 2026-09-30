# ============================================
# app/services/shopify.py
# Shopify OAuth + GraphQL Admin API + ID Token Verify
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
# ID TOKEN VERIFY KARO
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
        dest = payload.get("dest", "")
        if iss and dest:
            iss_domain = iss.replace("https://", "").split("/")[0]
            dest_domain = dest.replace("https://", "").split("/")[0]
            if iss_domain != dest_domain:
                raise ValueError("Domain mismatch")

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
# GRAPHQL API CALL
# ============================================
async def shopify_graphql(
    shop: str,
    access_token: str,
    query: str,
    variables: dict = None,
) -> dict:
    url = f"https://{shop}/admin/api/{settings.SHOPIFY_API_VERSION}/graphql.json"
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
# PRODUCT CREATE KARO (GraphQL) — Simple
# Product create karo, phir variant query se lo
# ============================================
async def create_shopify_product(
    shop: str,
    access_token: str,
    product_data: dict,
) -> dict:
    """
    Product create karta hai, phir alag query se variant lo
    aur price update karo.
    """

    # ========================================
    # Step 1: Product create (simple, no variants)
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
    # Step 2: Variant fetch karo (alag query)
    # ========================================
    price_value = product_data.get("price", "0.00")
    try:
        price_float = float(price_value) if price_value else 0.0
    except (ValueError, TypeError):
        price_float = 0.0

    logger.info(f"   Target price: ${price_float}")

    if product_id and price_float > 0:
        # Variant query
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

            # ========================================
            # Step 3: Price update karo
            # ========================================
            mutation_update = """
            mutation productVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
              productVariantsBulkUpdate(productId: $productId, variants: $variants) {
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

            logger.info(f"   Sending price update...")

            update_result = await shopify_graphql(
                shop, access_token, mutation_update, variables_update
            )

            logger.info(f"   Update result: {update_result}")

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
    # Step 4: Images add karo
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
# PRODUCT IMAGES ADD KARO
# ============================================
async def add_product_images(
    shop: str,
    access_token: str,
    product_id: str,
    image_urls: list,
) -> dict:
    mutation = """
    mutation productCreateMedia($productId: ID!, $media: [CreateMediaInput!]!) {
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