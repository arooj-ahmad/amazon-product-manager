# ============================================
# app/services/scheduler/shopify_sync.py
# ============================================

import logging
from sqlalchemy.orm import Session
from app.models import Product
from app.services.shopify import (
    update_shopify_product_status,
    get_shopify_product_by_sku,
    set_inventory_quantity,
    shopify_graphql,
    sync_update_shopify_price,
    set_product_metafields,
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

async def sync_shopify_product(product: Product, is_available: bool, stock_quantity: int, db: Session):
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

        # Status update
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
                  inventoryItem {
                    id
                  }
                }
              }
            }
          }
        }
        """

        result = await shopify_graphql(shop, access_token, query, {"id": shopify_id})
        if not result or "errors" in result:
            return

        edges = result.get("data", {}).get("product", {}).get("variants", {}).get("edges", [])
        
        for edge in edges:
            inventory_item_id = edge.get("node", {}).get("inventoryItem", {}).get("id")
            if not inventory_item_id:
                continue

            await set_inventory_quantity(
                shop=shop,
                access_token=access_token,
                inventory_item_id=inventory_item_id,
                quantity=stock_quantity,
            )

    except Exception as e:
        logger.error(f"❌ Shopify sync error: ASIN={product.asin}: {e}")


async def sync_shopify_price(product: Product, new_price: float, db: Session, compare_at_price: float = None):
    store = get_store_for_product(db, product)
    if not store or not store.access_token:
        return False

    shop = store.shop_domain
    access_token = store.access_token
    refresh_token = store.refresh_token

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
        return False

    try:
        success = await sync_update_shopify_price(
            shop_domain=shop,
            access_token=access_token,
            shopify_product_id=shopify_id,
            new_price=new_price,
            refresh_token=refresh_token,
            compare_at_price=compare_at_price,
        )

        # Metafields update
        metafields_input = []
        if product.amazon_price is not None:
            metafields_input.append({"namespace": "custom", "key": "amazon_price", "value": str(product.amazon_price), "type": "single_line_text_field"})
        if product.availability:
            metafields_input.append({"namespace": "custom", "key": "availability", "value": str(product.availability), "type": "single_line_text_field"})
        if getattr(product, "rating", None) is not None:
            metafields_input.append({"namespace": "custom", "key": "rating", "value": str(product.rating), "type": "single_line_text_field"})
        if getattr(product, "reviews_count", None) is not None:
            metafields_input.append({"namespace": "custom", "key": "reviews_count", "value": str(product.reviews_count), "type": "single_line_text_field"})
        if product.asin:
            metafields_input.append({"namespace": "custom", "key": "asin", "value": str(product.asin), "type": "single_line_text_field"})

        if metafields_input:
            await set_product_metafields(shop=shop, access_token=access_token, product_id=shopify_id, metafields=metafields_input)

        return success
    except Exception as e:
        logger.error(f"❌ Shopify price update error: ASIN={product.asin}: {e}")
        return False