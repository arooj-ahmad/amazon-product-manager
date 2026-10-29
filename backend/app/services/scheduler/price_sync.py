# ============================================
# app/services/scheduler/price_sync.py
# ============================================

import logging
from sqlalchemy.orm import Session
from app.models import Product
from app.services.shopify import (
    get_shopify_product_by_sku,
    sync_update_shopify_price,
    set_product_metafields,
)
from .helpers import get_store_for_product
from .inventory_sync import find_shopify_product_by_title

logger = logging.getLogger(__name__)

async def sync_shopify_price(
    product: Product, 
    new_price: float, 
    db: Session, 
    compare_at_price: float = None,
    sku: str = None
):
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

    target_sku = sku or product.asin

    try:
        success = await sync_update_shopify_price(
            shop_domain=shop,
            access_token=access_token,
            shopify_product_id=shopify_id,
            new_price=new_price,
            refresh_token=refresh_token,
            compare_at_price=compare_at_price,
            sku=target_sku,
        )

        if success:
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