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

    Ye token App Bridge se aata hai jab iframe se API call hoti hai.
    """
    try:
        # JWT decode with secret + audience verification
        payload = jwt.decode(
            token,
            settings.SHOPIFY_API_SECRET,
            algorithms=["HS256"],
            audience=settings.SHOPIFY_API_KEY,
        )

        now = int(time.time())

        # ----------------------------------------
        # Expiry check
        # ----------------------------------------
        if payload.get("exp", 0) < now:
            raise ValueError("Token expired")

        if payload.get("nbf", 0) > now:
            raise ValueError("Token not yet valid")

        # ----------------------------------------
        # Issuer check
        # ----------------------------------------
        iss = payload.get("iss", "")
        if not iss.startswith("https://"):
            raise ValueError("Invalid issuer")

        # ----------------------------------------
        # Domain match check
        # ----------------------------------------
        iss_domain = iss.replace("https://", "").split("/")[0]
        dest_domain = (
            payload.get("dest", "")
            .replace("https://", "")
            .split("/")[0]
        )

        if iss_domain != dest_domain:
            raise ValueError("Domain mismatch")

        # ----------------------------------------
        # Must be a .myshopify.com store
        # ----------------------------------------
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
# 2-Step: Create product + Update price
# ============================================
async def create_shopify_product(
    shop: str,
    access_token: str,
    product_data: dict,
) -> dict:
    """
    Shopify mein naya product create karta hai.
    Step 1: Product create (bina variants)
    Step 2: Variant ka price update
    Step 3: Images add
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

    # Check GraphQL errors
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
        # Variant query — pehla variant dhundo
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

            # Price update mutation
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

            logger.info(f"   Sending price update...")

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