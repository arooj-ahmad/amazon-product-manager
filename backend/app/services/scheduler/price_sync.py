# app/workers/tasks/sub_tasks/price_sync.py
import logging
from app.services.shopify import sync_update_shopify_price

logger = logging.getLogger(__name__)

async def sync_product_price(
    shop, 
    access_token, 
    refresh_token, 
    shopify_product_id, 
    new_price, 
    tags, 
    categories, 
    sku=None  # ✅ NAYA: sku parameter add kiya
):
    """Shopify pe price aur tags update karta hai (Specific variant ke liye)."""
    product_type = categories[0] if categories else ""
    
    ok = await sync_update_shopify_price(
        shop_domain=shop,
        access_token=access_token,
        shopify_product_id=shopify_product_id,
        new_price=new_price,
        refresh_token=refresh_token,
        tags=tags,
        product_type=product_type,
        sku=sku,  # ✅ FIX: SKU yahan pass kiya
    )
    
    if ok:
        logger.info(f"[PRICE] ✅ Price synced: ${new_price} (SKU: {sku})")
    else:
        logger.warning(f"[PRICE] ❌ Price update failed")
    return ok