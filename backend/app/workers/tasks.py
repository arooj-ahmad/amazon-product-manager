# app/workers/tasks.py
# Worker tasks — Batch URLs import + Price update
# + ✅ FIXED: sync_update_shopify_price ab await ke saath call hota hai
# + ✅ FIXED: refresh_token pass hota hai
# + ✅ FIXED: Product ke shopify_store_id se store dhoondha jata hai
# + ✅ FIXED: update_shopify_product_status await ke saath call hota hai
# + ✅ FIXED: API version safety check
# + ✅ FIXED: 401 pe auto-refresh + retry
# + ✅ FIXED: Manual override skip NAHI hota
# + ✅ FIXED: Price push HAR change pe (increase ya decrease)

from typing import Any, Dict
import logging
from datetime import datetime, timezone

from app.services.brightdata import fetch_product_from_brightdata
from app.database import SessionLocal

logger = logging.getLogger(__name__)


# ============================================
# ✅ HELPER: Sahi store dhoondho (product ke store_id se)
# ============================================
def _get_store_for_product(db, product, fallback_store_id: int = None):
    """Product ke shopify_store_id se store dhoondho."""
    from app.models import ShopifyStore

    store = None
    if product and product.shopify_store_id:
        store = (
            db.query(ShopifyStore)
            .filter(ShopifyStore.id == product.shopify_store_id)
            .first()
        )
    if not store and fallback_store_id:
        store = (
            db.query(ShopifyStore)
            .filter(ShopifyStore.id == fallback_store_id)
            .first()
        )
    if not store:
        store = db.query(ShopifyStore).first()
    return store


# ============================================
# ✅ WORKER FUNCTION 1: BATCH URLS IMPORT
# ============================================
async def process_batch_urls(ctx: Dict[str, Any], job_id: str, urls: list):
    """Har URL ko process karega: Bright Data call -> extract -> DB save"""
    results = {"succeeded": 0, "failed": 0, "details": []}
    total = len(urls)

    logger.info(f"Starting batch {job_id} with {total} URLs")

    for index, url in enumerate(urls, start=1):
        try:
            product_data = await fetch_product_from_brightdata(url)

            db = SessionLocal()
            try:
                # Aapka existing logic yahan
                pass
            finally:
                db.close()

            results["succeeded"] += 1
            results["details"].append({"url": url, "status": "success"})
            logger.info(f"[{job_id}] {index}/{total} ✅ {url}")

        except Exception as e:
            results["failed"] += 1
            results["details"].append({
                "url": url,
                "status": "failed",
                "error": str(e),
            })
            logger.error(f"[{job_id}] {index}/{total} ❌ {url} — {e}")

        try:
            await ctx["redis"].hset(
                f"batch:{job_id}",
                mapping={
                    "processed": results["succeeded"] + results["failed"],
                    "succeeded": results["succeeded"],
                    "failed": results["failed"],
                    "total": total,
                },
            )
            await ctx["redis"].expire(f"batch:{job_id}", 86400)
        except Exception as e:
            logger.warning(f"Progress update fail: {e}")

    logger.info(
        f"[{job_id}] Done — {results['succeeded']} success, "
        f"{results['failed']} failed"
    )
    return results


# ============================================
# ✅ WORKER FUNCTION 2: PRICE UPDATE (FIXED)
# ============================================
async def process_price_update(ctx: Dict[str, Any], asin: str):
    """
    Ek product ka price update karo.
    ✅ FIXED: Manual override skip NAHI hota
    ✅ FIXED: Price push HAR change pe
    """
    from app.models import Product, ShopifyStore
    from app.services.brightdata import (
        calculate_final_price,
        BrightDataError,
    )
    from app.services.shopify import (
        sync_update_shopify_price,
        get_shopify_product_by_sku,
        set_product_metafields,
        update_shopify_product_status,
    )

    db = SessionLocal()

    try:
        # 1. Product dhundo
        product = db.query(Product).filter(Product.asin == asin).first()

        if not product:
            logger.warning(f"[PRICE] Product not found: {asin}")
            return {"asin": asin, "status": "not_found"}

        # ❌ MANUAL OVERRIDE CHECK HATAO — skip nahi karo

        # 2. Bright Data se fetch
        amazon_url = f"https://www.amazon.com/dp/{asin}"
        data = await fetch_product_from_brightdata(amazon_url)

        new_amazon_price = data["amazon_price"]
        old_amazon = product.amazon_price or 0
        old_price = product.price

        # 3. Availability update
        old_availability = product.is_available
        new_availability = data.get("is_available", True)

        product.availability = data.get("availability", "In Stock")
        product.is_available = new_availability
        product.stock_quantity = data.get("stock_quantity", 0)
        product.last_synced_at = datetime.now(timezone.utc)

        if data.get("rating") is not None:
            product.rating = data["rating"]
        if data.get("reviews_count") is not None:
            product.reviews_count = data["reviews_count"]

        # 4. Price recalculate
        new_final_price = calculate_final_price(
            amazon_price=new_amazon_price,
            markup=product.markup or 2.0,
            markup_type=getattr(product, "markup_type", "fixed") or "fixed",
        )

        product.amazon_price = new_amazon_price
        product.price = new_final_price

        db.commit()
        db.refresh(product)

        # ✅ Store dhoondho
        store = _get_store_for_product(db, product)

        shopify_updated = False

        # ✅ FIXED: HAR change pe push karo (increase ya decrease)
        if store and store.access_token:
            shopify_id = product.shopify_product_id

            if not shopify_id:
                shopify_id = await get_shopify_product_by_sku(
                    shop=store.shop_domain,
                    access_token=store.access_token,
                    sku=product.asin,
                )
                if shopify_id:
                    product.shopify_product_id = shopify_id
                    db.commit()

            if shopify_id:
                ok = await sync_update_shopify_price(
                    shop_domain=store.shop_domain,
                    access_token=store.access_token,
                    shopify_product_id=shopify_id,
                    new_price=new_final_price,
                    refresh_token=store.refresh_token,
                )

                if ok:
                    # Metafields update
                    metafields_input = []

                    if product.amazon_price is not None:
                        metafields_input.append({
                            "namespace": "custom",
                            "key": "amazon_price",
                            "value": str(product.amazon_price),
                            "type": "single_line_text_field",
                        })

                    if product.availability:
                        metafields_input.append({
                            "namespace": "custom",
                            "key": "availability",
                            "value": str(product.availability),
                            "type": "single_line_text_field",
                        })

                    if metafields_input:
                        await set_product_metafields(
                            shop=store.shop_domain,
                            access_token=store.access_token,
                            product_id=shopify_id,
                            metafields=metafields_input,
                        )

                    shopify_updated = True
                else:
                    logger.warning(
                        f"[PRICE] Shopify update failed for {asin}"
                    )
        else:
            logger.warning(f"[PRICE] No valid store/token for {asin}")

        # 6. Availability change pe Shopify status update
        if old_availability != new_availability:
            if store and store.access_token and product.shopify_product_id:
                await update_shopify_product_status(
                    shop=store.shop_domain,
                    access_token=store.access_token,
                    shopify_product_id=product.shopify_product_id,
                    is_available=new_availability,
                )

        logger.info(
            f"[PRICE] ✅ {asin} "
            f"amazon: ${old_amazon} → ${new_amazon_price}, "
            f"final: ${old_price} → ${new_final_price}, "
            f"shopify_updated: {shopify_updated}"
        )

        return {
            "asin": asin,
            "status": "success",
            "old_amazon": old_amazon,
            "new_amazon": new_amazon_price,
            "old_price": old_price,
            "new_price": new_final_price,
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