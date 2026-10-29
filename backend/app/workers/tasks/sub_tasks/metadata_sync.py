# app/workers/tasks/sub_tasks/metadata_sync.py
import logging
from app.services.shopify import (
    update_shopify_product_status,
    set_product_metafields,
)
from app.services.shopify.metafields.builder import _build_all_metafields

logger = logging.getLogger(__name__)

async def sync_product_metadata(shop, access_token, shopify_product_id, product, is_available):
    """Status aur Metafields (Specs, Rating, Reviews) update karta hai."""
    
    # 1. Status Update (ACTIVE ya DRAFT)
    status_ok = await update_shopify_product_status(
        shop=shop,
        access_token=access_token,
        shopify_product_id=shopify_product_id,
        is_available=is_available,
    )
    if status_ok:
        logger.info(f"[METADATA] ✅ Status synced, available={is_available}")

    # 2. Metafields Update (Saari dynamic specifications ke saath)
    product_data_for_mf = {
        "asin": product.asin,
        "brand": product.brand,
        "manufacturer": getattr(product, "manufacturer", None),
        "rating": product.rating,
        "reviews_count": product.reviews_count,
        "amazon_price": product.amazon_price,
        "availability": product.availability,
        "model_number": getattr(product, "model_number", None),
        "item_dimensions": getattr(product, "item_dimensions", None),
        "item_weight": getattr(product, "item_weight", None),
        "package_dimensions": getattr(product, "package_dimensions", None),
        "size": getattr(product, "size", None),
        "color": getattr(product, "color", None),
        "material_type": getattr(product, "material_type", None),
        
        # ✅ YEH LINE ZAROORI HAI (Dynamic specs ke liye)
        "product_details": getattr(product, "product_details", []), 
        
        "specifications": product.specifications or {},
        "variant_attributes": product.variant_attributes or [],
    }
    
    # Builder se saari specs nikaalein
    metafields_input = _build_all_metafields(product_data_for_mf)

    if metafields_input:
        await set_product_metafields(
            shop=shop,
            access_token=access_token,
            product_id=shopify_product_id,
            metafields=metafields_input,
        )
        logger.info(f"[METADATA] ✅ Metafields synced ({len(metafields_input)} items)")
    else:
        logger.info(f"[METADATA] ⚠️ No metafields to sync for {product.asin}")