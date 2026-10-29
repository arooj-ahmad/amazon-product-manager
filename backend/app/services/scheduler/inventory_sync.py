# ============================================
# app/services/scheduler/inventory_sync.py
# ============================================

import logging
from sqlalchemy.orm import Session
from app.models import Product
from app.services.shopify import (
    update_shopify_product_status,
    get_shopify_product_by_sku,
    set_inventory_quantity,
    shopify_graphql,
)
from .helpers import get_store_for_product

logger = logging.getLogger(__name__)


async def find_shopify_product_by_title(shop: str, access_token: str, title: str) -> str | None:
    if not title or len(title.strip()) < 3:
        return None

    search_term = title.strip()[:40]
    query = """
    query searchProduct($query: String!) {
      products(first: 5, query: $query) {
        edges {
          node {
            id
            title
          }
        }
      }
    }
    """

    try:
        result = await shopify_graphql(shop, access_token, query, {"query": search_term})
        if not result:
            return None

        data = result.get("data") or {}
        products_data = data.get("products") or {}
        edges = products_data.get("edges") or []

        if edges:
            return edges[0].get("node", {}).get("id")
        return None
    except Exception as e:
        logger.error(f"❌ Title search error: {e}")
        return None


async def sync_shopify_inventory(product: Product, is_available: bool, stock_quantity: int, db: Session):
    store = get_store_for_product(db, product)

    if not store or not store.access_token:
        logger.warning("⚠️ No Shopify store in DB — skip sync")
        product.shopify_status = "draft"
        db.commit()
        return

    shop = store.shop_domain
    access_token = store.access_token

    try:
        shopify_id = product.shopify_product_id

        if not shopify_id:
            shopify_id = await get_shopify_product_by_sku(shop, access_token, product.asin)
            if shopify_id:
                product.shopify_product_id = shopify_id

        if not shopify_id and product.title:
            shopify_id = await find_shopify_product_by_title(shop, access_token, product.title)
            if shopify_id:
                product.shopify_product_id = shopify_id

        if not shopify_id:
            logger.warning(f"❌ Shopify product not found for ASIN={product.asin}")
            product.shopify_status = "draft"
            db.commit()
            return

        # Status update (Ab yeh khud 401 handle karega helpers.py ke through)
        await update_shopify_product_status(
            shop=shop,
            access_token=access_token,
            shopify_product_id=shopify_id,
            is_available=is_available,
        )

        product.shopify_status = "active" if is_available else "draft"
        db.commit()

        # Inventory quantity update
        query = """
        query getProductInventory($id: ID!) {
          product(id: $id) {
            variants(first: 50) {
              edges {
                node {
                  id
                  sku
                  inventoryItem {
                    id
                  }
                }
              }
            }
          }
        }
        """

        # ✅ Ab helpers.py ka shopify_graphql khud 401 par token refresh karega
        result = await shopify_graphql(shop, access_token, query, {"id": shopify_id})

        # ✅ SAFE CHECKS
        if not result:
            logger.warning(f"⚠️ Shopify API ne khali response diya (None) ASIN={product.asin}")
            return

        if "errors" in result:
            logger.error(f"❌ Inventory query error for ASIN={product.asin}: {result['errors']}")
            return

        data = result.get("data")
        if not data:
            logger.warning(f"⚠️ Shopify response mein 'data' nahi mila ASIN={product.asin}")
            return

        product_data = data.get("product")
        if not product_data:
            logger.warning(f"⚠️ Shopify response mein 'product' nahi mila ASIN={product.asin}")
            return

        variants_data = product_data.get("variants") or {}
        edges = variants_data.get("edges") or []

        # ✅ FIX: Sirf usi variant ka stock update karein jiska SKU (ASIN) match kare
        target_sku = product.asin
        found_variant = False

        for edge in edges:
            node = edge.get("node", {})
            variant_sku = node.get("sku")
            
            # Agar SKU match karta hai (exact string match)
            if str(variant_sku).strip() == str(target_sku).strip():
                inventory_item_id = node.get("inventoryItem", {}).get("id")
                if inventory_item_id:
                    await set_inventory_quantity(
                        shop=shop,
                        access_token=access_token,
                        inventory_item_id=inventory_item_id,
                        quantity=stock_quantity,
                    )
                    logger.info(f"✅ Inventory synced: ASIN={target_sku}, Qty={stock_quantity}")
                    found_variant = True
                    break  # Sirf ek variant update karna hai

        if not found_variant:
            logger.warning(f"⚠️ No matching variant found for SKU {target_sku} in product {shopify_id}")

    except Exception as e:
        logger.error(f"❌ Shopify inventory sync error: ASIN={product.asin}: {e}")