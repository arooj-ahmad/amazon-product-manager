# app/workers/tasks.py
# Worker tasks — Batch URLs import + Price update
# + ✅ FIXED: sync_update_shopify_price ab await ke saath call hota hai
# + ✅ FIXED: refresh_token pass hota hai
# + ✅ FIXED: Product ke shopify_store_id se store dhoondha jata hai
# + ✅ FIXED: update_shopify_product_status await ke saath call hota hai
# + ✅ FIXED: API version safety check
# + ✅ FIXED: 401/403 pe auto-refresh + retry
# + ✅ FIXED: Manual override skip NAHI hota
# + ✅ FIXED: Price push HAR change pe (increase ya decrease)
# + ✅ NAYA: Inventory update bhi hota hai (process_price_update mein)
# + ✅ NAYA: Har variant ka inventory update
# + ✅ NAYA: set_inventory_quantity ka result check
# + ✅ NAYA: Tags + Categories Shopify pe push (Collections ke liye)

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
# ✅ WORKER FUNCTION 2: PRICE + INVENTORY UPDATE
# + ✅ NAYA: Tags + Categories push
# ============================================
async def process_price_update(ctx: Dict[str, Any], asin: str):
    """
    Ek product ka price + inventory update karo.
    ✅ FIXED: Manual override skip NAHI hota
    ✅ FIXED: Price push HAR change pe
    ✅ NAYA: Inventory bhi update hota hai
    ✅ NAYA: Tags + Categories bhi push hote hain
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
        set_inventory_quantity,
        shopify_graphql,
        update_shopify_product_tags_and_type,  # ✅ NAYA
    )

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

        # ✅ NAYA: Categories + Tags update karo
        if data.get("categories") is not None:
            product.categories = data["categories"]
        if data.get("tags") is not None:
            product.tags = data["tags"]

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
                # ✅ 1. Status update
                status_ok = await update_shopify_product_status(
                    shop=store.shop_domain,
                    access_token=store.access_token,
                    shopify_product_id=shopify_id,
                    is_available=new_availability,
                )
                if status_ok:
                    logger.info(f"[PRICE] ✅ Status synced: {asin}, available={new_availability}")

                # ✅ 2. Price update (+ tags bhi saath mein)
                # sync_update_shopify_price ab tags + product_type bhi accept karta hai
                product_tags = product.tags or []
                product_categories = product.categories or []
                product_type = product_categories[0] if product_categories else ""

                ok = await sync_update_shopify_price(
                    shop_domain=store.shop_domain,
                    access_token=store.access_token,
                    shopify_product_id=shopify_id,
                    new_price=new_final_price,
                    refresh_token=store.refresh_token,
                    # ✅ NAYA: tags + product_type pass karo
                    tags=product_tags,
                    product_type=product_type,
                )

                if ok:
                    # ✅ 3. Inventory update (HAR VARIANT)
                    inv_query = """
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

                    inv_result = await shopify_graphql(
                        store.shop_domain,
                        store.access_token,
                        inv_query,
                        {"id": shopify_id},
                    )

                    if "errors" in inv_result:
                        logger.error(
                            f"[PRICE] ❌ Inventory query error: "
                            f"{inv_result['errors']}"
                        )
                    else:
                        inv_edges = (
                            inv_result.get("data", {})
                            .get("product", {})
                            .get("variants", {})
                            .get("edges", [])
                        )

                        for edge in inv_edges:
                            inv_item_id = (
                                edge.get("node", {})
                                .get("inventoryItem", {})
                                .get("id")
                            )
                            if inv_item_id:
                                qty = product.stock_quantity or 0
                                if qty == 0 and new_availability:
                                    qty = 100

                                inv_ok = await set_inventory_quantity(
                                    shop=store.shop_domain,
                                    access_token=store.access_token,
                                    inventory_item_id=inv_item_id,
                                    quantity=qty,
                                )

                                if inv_ok:
                                    logger.info(
                                        f"[PRICE] ✅ Inventory synced: "
                                        f"{asin}, qty={qty}"
                                    )
                                else:
                                    logger.error(
                                        f"[PRICE] ❌ Inventory update FAILED: "
                                        f"{asin}, qty={qty}"
                                    )

                    # ✅ 4. Metafields update
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

                    if product.rating is not None:
                        metafields_input.append({
                            "namespace": "custom",
                            "key": "rating",
                            "value": str(product.rating),
                            "type": "single_line_text_field",
                        })

                    if product.reviews_count is not None:
                        metafields_input.append({
                            "namespace": "custom",
                            "key": "reviews_count",
                            "value": str(product.reviews_count),
                            "type": "single_line_text_field",
                        })

                    if product.asin:
                        metafields_input.append({
                            "namespace": "custom",
                            "key": "asin",
                            "value": str(product.asin),
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
                        f"[PRICE] Shopify price update failed for {asin}"
                    )
        else:
            logger.warning(f"[PRICE] No valid store/token for {asin}")

        logger.info(
            f"[PRICE] ✅ {asin} "
            f"amazon: ${old_amazon} → ${new_amazon_price}, "
            f"final: ${old_price} → ${new_final_price}, "
            f"categories: {len(product.categories or [])}, "
            f"tags: {len(product.tags or [])}, "
            f"shopify_updated: {shopify_updated}"
        )

        return {
            "asin": asin,
            "status": "success",
            "old_amazon": old_amazon,
            "new_amazon": new_amazon_price,
            "old_price": old_price,
            "new_price": new_final_price,
            "categories_count": len(product.categories or []),
            "tags_count": len(product.tags or []),
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