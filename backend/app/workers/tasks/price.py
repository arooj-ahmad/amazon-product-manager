# app/workers/tasks/price.py
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from app.core.database import SessionLocal
from .helpers import _get_store_for_product
from .sub_tasks.price_sync import sync_product_price
from .sub_tasks.inventory_sync import sync_product_inventory
from .sub_tasks.metadata_sync import sync_product_metadata

logger = logging.getLogger(__name__)

async def process_price_update(ctx: Dict[str, Any], asin: str):
    """Main entry point: Amazon se fetch karo, DB update karo, phir Shopify sync karo."""
    from app.models import Product
    from app.services.amazon.brightdata_scraper import fetch_product_from_brightdata
    from app.services.amazon.pricing import calculate_final_price
    from app.services.amazon.exceptions import BrightDataError
    from app.services.shopify import get_shopify_product_by_sku

    db = SessionLocal()

    try:
        # 1. Product dhundo
        product = db.query(Product).filter(Product.asin == asin).first()
        if not product:
            logger.warning(f"[PRICE] Product not found: {asin}")
            return {"asin": asin, "status": "not_found"}

        # 2. Bright Data se fetch
        amazon_url = f"https://www.amazon.com/dp/{asin}"
        data = await fetch_product_from_brightdata(amazon_url)

        new_amazon_price = data["amazon_price"]
        old_amazon = product.amazon_price or 0
        old_price = product.price

        # 3. DB Update
        new_availability = data.get("is_available", True)
        product.availability = data.get("availability", "In Stock")
        product.is_available = new_availability
        product.stock_quantity = data.get("stock_quantity", 0)
        product.last_synced_at = datetime.now(timezone.utc)
        
        if data.get("rating") is not None: product.rating = data["rating"]
        if data.get("reviews_count") is not None: product.reviews_count = data["reviews_count"]
        if data.get("categories") is not None: product.categories = data["categories"]
        if data.get("tags") is not None: product.tags = data["tags"]

        # ✅ NO DEFAULT MARKUP: Sirf product mein save kiya hua markup use hoga
        user_markup = product.markup
        user_markup_type = product.markup_type
        user_extra = getattr(product, "extra_percent", 0.0) or 0.0
        user_tax = getattr(product, "tax_rate", 0.0) or 0.0

        # Agar product mein markup save hi nahi hai, to error dein
        if user_markup is None or user_markup_type is None:
            logger.error(f"[PRICE] ❌ No markup set for ASIN={asin}. Skipping price calculation.")
            return {"asin": asin, "status": "error", "error": "Markup not set for product"}

        new_final_price = calculate_final_price(
            amazon_price=new_amazon_price,
            markup=user_markup,
            markup_type=user_markup_type,
            extra_percent=user_extra,
            tax_rate=user_tax,
        )
        
        product.amazon_price = new_amazon_price
        product.price = new_final_price

        db.commit()
        db.refresh(product)

        # 4. Shopify Sync
        store = _get_store_for_product(db, product)
        shopify_updated = False

        if store and store.access_token:
            shopify_id = product.shopify_product_id
            if not shopify_id:
                shopify_id = await get_shopify_product_by_sku(shop=store.shop_domain, access_token=store.access_token, sku=product.asin)
                if shopify_id:
                    product.shopify_product_id = shopify_id
                    db.commit()

            if shopify_id:
                # 4a. Metadata (Status + Metafields)
                await sync_product_metadata(store.shop_domain, store.access_token, shopify_id, product, new_availability)
                
                # 4b. Price + Tags
                price_ok = await sync_product_price(
                    store.shop_domain, 
                    store.access_token, 
                    store.refresh_token, 
                    shopify_id, 
                    new_final_price, 
                    product.tags, 
                    product.categories,
                    sku=product.asin  # ✅ SKU yahan pass kiya
                )

                if price_ok:
                    # 4c. Inventory
                    await sync_product_inventory(
                        store.shop_domain, 
                        store.access_token, 
                        shopify_id, 
                        product.stock_quantity, 
                        new_availability,
                        sku=product.asin  # ✅ Inventory ke liye bhi SKU
                    )
                    shopify_updated = True
        else:
            logger.warning(f"[PRICE] No valid store/token for {asin}")

        return {
            "asin": asin, "status": "success",
            "old_amazon": old_amazon, "new_amazon": new_amazon_price,
            "old_price": old_price, "new_price": new_final_price,
            "shopify_updated": shopify_updated,
        }

    except BrightDataError as e:
        logger.error(f"[PRICE] BrightDataError for {asin}: {e}")
        return {"asin": asin, "status": "brightdata_error", "error": str(e)}
    except Exception as e:
        logger.error(f"[PRICE] Error for {asin}: {e}")
        return {"asin": asin, "status": "error", "error": str(e)}
    finally:
        db.close()