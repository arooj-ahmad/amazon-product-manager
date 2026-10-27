# app/workers/tasks/sub_tasks/metadata_sync.py
import logging
from app.services.shopify import (
    update_shopify_product_status,
    set_product_metafields,
)

logger = logging.getLogger(__name__)

async def sync_product_metadata(shop, access_token, shopify_product_id, product, is_available):
    """Status aur Metafields update karta hai."""
    
    # 1. Status Update
    status_ok = await update_shopify_product_status(
        shop=shop,
        access_token=access_token,
        shopify_product_id=shopify_product_id,
        is_available=is_available,
    )
    if status_ok:
        logger.info(f"[METADATA] ? Status synced, available={is_available}")

    # 2. Metafields Update
    metafields_input = []
    if product.amazon_price is not None:
        metafields_input.append({"namespace": "custom", "key": "amazon_price", "value": str(product.amazon_price), "type": "single_line_text_field"})
    if product.availability:
        metafields_input.append({"namespace": "custom", "key": "availability", "value": str(product.availability), "type": "single_line_text_field"})
    if product.rating is not None:
        metafields_input.append({"namespace": "custom", "key": "rating", "value": str(product.rating), "type": "single_line_text_field"})
    if product.reviews_count is not None:
        metafields_input.append({"namespace": "custom", "key": "reviews_count", "value": str(product.reviews_count), "type": "single_line_text_field"})
    if product.asin:
        metafields_input.append({"namespace": "custom", "key": "asin", "value": str(product.asin), "type": "single_line_text_field"})

    if metafields_input:
        await set_product_metafields(
            shop=shop,
            access_token=access_token,
            product_id=shopify_product_id,
            metafields=metafields_input,
        )
        logger.info(f"[METADATA] ? Metafields synced ({len(metafields_input)} items)")
