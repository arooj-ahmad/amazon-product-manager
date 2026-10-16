# ============================================
# app/services/shopify_sync.py
# Price sync (Admin API) + Storefront availability check
# + ✅ FIXED: Circular import — direct module se import
# + ✅ NAYA v2: compare_at_price support
# ============================================

import logging
from typing import Optional

import httpx

from app.config import settings
from app.services.shopify_helpers import _safe_api_version
from app.services.shopify.product_extras import update_shopify_product_tags_and_type

logger = logging.getLogger(__name__)


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
# SYNC SHOPIFY PRICE UPDATE
# ✅ NAYA v2: compare_at_price support
# ============================================
async def sync_update_shopify_price(
    shop_domain: str,
    access_token: str,
    shopify_product_id: str,
    new_price: float,
    refresh_token: Optional[str] = None,
    tags: Optional[list] = None,
    product_type: Optional[str] = None,
    compare_at_price: Optional[float] = None,   # ✅ NAYA
) -> bool:
    """
    Update Shopify product price + compare_at_price.

    Args:
        compare_at_price: Agar diya toh variant pe set karega.
                          Agar None ya <= new_price hai toh skip.
    """
    if not all([shop_domain, access_token, shopify_product_id]):
        logger.warning("Shopify sync skipped: missing config")
        return False

    if not str(shopify_product_id).startswith("gid://"):
        product_gid = f"gid://Shopify/Product/{shopify_product_id}"
    else:
        product_gid = shopify_product_id

    api_version = _safe_api_version()

    api_url = (
        f"https://{shop_domain}/admin/api/"
        f"{api_version}/graphql.json"
    )

    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }

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
              compareAtPrice
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
            if res.status_code in (401, 403):
                if refresh_token:
                    logger.warning(
                        f"🔄 {res.status_code} — refreshing token for "
                        f"{shop_domain} and retrying..."
                    )
                    from app.services.shopify_auth import refresh_shopify_token
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
                            tags=tags,
                            product_type=product_type,
                            compare_at_price=compare_at_price,   # ✅ NAYA
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

        # ✅ Compare-at price normalize karo
        compare_at_str = None
        if compare_at_price is not None:
            try:
                cap = float(compare_at_price)
                price_f = float(new_price)

                if cap > price_f:
                    compare_at_str = f"{cap:.2f}"
                    logger.info(
                        f"   💰 Compare-at: ${compare_at_str} "
                        f"(price: ${price_f})"
                    )
                else:
                    logger.warning(
                        f"⚠️ compare_at (${cap}) <= price (${price_f}) "
                        f"— skipping compare_at"
                    )
            except (ValueError, TypeError) as e:
                logger.warning(f"⚠️ Invalid compare_at_price: {e}")

        # ✅ Har variant ke liye input banao
        variants_to_update = []
        for edge in variant_edges:
            variant_input = {
                "id": edge["node"]["id"],
                "price": str(new_price),
            }

            # ✅ Agar compare_at set karna hai toh add karo
            if compare_at_str:
                variant_input["compareAtPrice"] = compare_at_str

            variants_to_update.append(variant_input)

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
              compareAtPrice
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

        # ✅ Log price + compare_at
        if updated:
            first = updated[0]
            logger.info(
                f"✅ Shopify price updated: {len(updated)} variant(s) → "
                f"${first.get('price')}, "
                f"compare_at=${first.get('compareAtPrice', 'N/A')}"
            )

        if tags is not None:
            await update_shopify_product_tags_and_type(
                shop=shop_domain,
                access_token=access_token,
                shopify_product_id=shopify_product_id,
                tags=tags,
                product_type=product_type or "",
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