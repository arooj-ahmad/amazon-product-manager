# ============================================
# app/services/scheduler.py
# Har 24 ghante Amazon se fresh prices fetch karne wala scheduler
# + Out of Stock tracking
# + Shopify Status Sync (DB token use karta hai)
# + Inventory quantity sync
# + ✅ NAYA: Shopify price update (sirf increase pe)
# + ✅ NAYA: Sirf Active products (Draft skip)
# + ✅ NAYA: price hamesha amazon_price + markup update
# + ✅ NAYA: Shopify metafields update (amazon_price, availability, rating, etc.)
# ============================================

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Product, ShopifyStore
from app.services.brightdata import (
    BrightDataError,
    calculate_final_price,
    fetch_product_from_brightdata,
)
from app.services.shopify import (
    update_shopify_product_status,
    get_shopify_product_by_sku,
    set_inventory_quantity,
    get_primary_location,
    shopify_graphql,
    sync_update_shopify_price,
    set_product_metafields,  # ✅ NAYA IMPORT
)

logger = logging.getLogger(__name__)


# ============================================
# GLOBAL SCHEDULER INSTANCE
# ============================================
scheduler = AsyncIOScheduler()


# ============================================
# ✅ HELPER: SHOPIFY STATUS + INVENTORY SYNC
# ============================================
async def sync_shopify_product(
    product: Product,
    is_available: bool,
    stock_quantity: int,
    db: Session,
):
    """
    Product ka Shopify status + inventory update karta hai.
    """
    store = db.query(ShopifyStore).first()

    if not store or not store.access_token:
        logger.warning("⚠️ No Shopify store in DB — skip sync")
        return

    shop = store.shop_domain
    access_token = store.access_token

    try:
        shopify_id = product.shopify_product_id

        if not shopify_id:
            shopify_id = await get_shopify_product_by_sku(
                shop=shop,
                access_token=access_token,
                sku=product.asin,
            )
            if shopify_id:
                product.shopify_product_id = shopify_id
                logger.info(f"Shopify product linked: {shopify_id}")

        if not shopify_id:
            logger.warning(
                f"Shopify product not found for ASIN={product.asin}"
            )
            return

        # ── Step 1: Status update ──
        status_success = await update_shopify_product_status(
            shop=shop,
            access_token=access_token,
            shopify_product_id=shopify_id,
            is_available=is_available,
        )

        if status_success:
            logger.info(
                f"✅ Shopify status synced: ASIN={product.asin}, "
                f"available={is_available}"
            )

        # ── Step 2: Inventory quantity update ──
        query = """
        query getProductInventory($id: ID!) {
          product(id: $id) {
            variants(first: 1) {
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

        result = await shopify_graphql(
            shop, access_token, query, {"id": shopify_id}
        )

        edges = (
            result.get("data", {})
            .get("product", {})
            .get("variants", {})
            .get("edges", [])
        )

        if edges:
            inventory_item_id = (
                edges[0]["node"]
                .get("inventoryItem", {})
                .get("id")
            )

            if inventory_item_id:
                qty = stock_quantity
                if qty == 0 and is_available:
                    qty = 100

                await set_inventory_quantity(
                    shop=shop,
                    access_token=access_token,
                    inventory_item_id=inventory_item_id,
                    quantity=qty,
                )
                logger.info(f"✅ Inventory synced: {qty}")

    except Exception as e:
        logger.error(f"❌ Shopify sync error: ASIN={product.asin}: {e}")


# ============================================
# ✅ HELPER: SHOPIFY PRICE + METAFIELDS UPDATE
# ============================================
async def sync_shopify_price(product: Product, new_price: float, db: Session):
    """
    Shopify pe product ka price + metafields update karta hai.
    """
    store = db.query(ShopifyStore).first()

    if not store or not store.access_token:
        logger.warning("⚠️ No Shopify store in DB — skip price update")
        return False

    shop = store.shop_domain
    access_token = store.access_token

    shopify_id = product.shopify_product_id

    if not shopify_id:
        shopify_id = await get_shopify_product_by_sku(
            shop=shop,
            access_token=access_token,
            sku=product.asin,
        )
        if shopify_id:
            product.shopify_product_id = shopify_id

    if not shopify_id:
        logger.warning(f"⚠️ Shopify product not found for ASIN={product.asin}")
        return False

    try:
        # ✅ 1. Variant price update
        success = sync_update_shopify_price(
            shop_domain=shop,
            access_token=access_token,
            shopify_product_id=shopify_id,
            new_price=new_price,
        )
        if success:
            logger.info(
                f"✅ Shopify price updated: ASIN={product.asin}, "
                f"new_price=${new_price}"
            )

        # ✅ 2. Metafields update (amazon_price, availability, rating, etc.)
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

        if getattr(product, "rating", None) is not None:
            metafields_input.append({
                "namespace": "custom",
                "key": "rating",
                "value": str(product.rating),
                "type": "single_line_text_field",
            })

        if getattr(product, "reviews_count", None) is not None:
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
                shop=shop,
                access_token=access_token,
                product_id=shopify_id,
                metafields=metafields_input,
            )
            logger.info(
                f"✅ Shopify metafields updated: ASIN={product.asin}, "
                f"amazon_price=${product.amazon_price}"
            )

        return success
    except Exception as e:
        logger.error(f"❌ Shopify price update error: ASIN={product.asin}: {e}")
        return False


# ============================================
# JOB: UPDATE ALL PRICES
# ============================================
async def update_all_prices():
    """Saare Active products ke prices update karta hai (24h)."""
    logger.info("=" * 60)
    logger.info("PRICE UPDATE JOB STARTED")
    logger.info("=" * 60)

    db: Session = SessionLocal()

    try:
        # ✅ Sirf Active products uthao (Draft skip)
        products = db.query(Product).filter(
            Product.is_available == True  # noqa: E712
        ).all()
        logger.info(f"Total Active products: {len(products)}")

        updated_count = 0
        skipped_count = 0
        error_count = 0
        out_of_stock_count = 0
        back_in_stock_count = 0
        shopify_synced_count = 0
        price_increased_count = 0
        price_decreased_count = 0
        price_recalculated_count = 0

        for product in products:
            if product.is_manual_override:
                logger.info(f"[SKIP] ASIN={product.asin} (manual override)")
                skipped_count += 1
                continue

            try:
                amazon_url = f"https://www.amazon.com/dp/{product.asin}"
                data = await fetch_product_from_brightdata(amazon_url)

                new_amazon_price = data["amazon_price"]

                # ========================================
                # ✅ STEP 1: Availability update karo
                # ========================================
                old_availability = product.is_available
                new_availability = data.get("is_available", True)

                product.availability = data.get("availability", "In Stock")
                product.is_available = new_availability
                product.stock_quantity = data.get("stock_quantity", 0)
                product.last_synced_at = datetime.now(timezone.utc)

                # ✅ Rating + reviews_count bhi update karo
                if data.get("rating") is not None:
                    product.rating = data["rating"]
                if data.get("reviews_count") is not None:
                    product.reviews_count = data["reviews_count"]

                availability_changed = (old_availability != new_availability)

                if availability_changed:
                    if new_availability:
                        logger.info(f"✅ [BACK IN STOCK] ASIN={product.asin}")
                        back_in_stock_count += 1
                    else:
                        logger.warning(f"❌ [OUT OF STOCK] ASIN={product.asin}")
                        out_of_stock_count += 1

                # ========================================
                # ✅ STEP 2: Shopify sync (status + inventory)
                # ========================================
                if availability_changed:
                    await sync_shopify_product(
                        product=product,
                        is_available=new_availability,
                        stock_quantity=product.stock_quantity,
                        db=db,
                    )
                    shopify_synced_count += 1

                # ========================================
                # ✅ STEP 3: Price check
                # ========================================
                if new_amazon_price is None:
                    logger.warning(f"[WARN] ASIN={product.asin} — price nahi mila")
                    db.commit()
                    db.refresh(product)
                    error_count += 1
                    continue

                old_amazon = product.amazon_price or 0
                old_price = product.price

                # ✅ HAMESHA price recalculate karo (chahe badha ya ghata)
                new_final_price = calculate_final_price(
                    amazon_price=new_amazon_price,
                    markup=product.markup or 2.0,
                    markup_type=getattr(product, "markup_type", "fixed") or "fixed",
                )

                # ✅ HAMESHA amazon_price aur price update karo
                product.amazon_price = new_amazon_price
                product.price = new_final_price

                # ✅ Optional fields update
                if data.get("title") and data["title"] != product.title:
                    product.title = data["title"]
                if data.get("image_url") and data["image_url"] != product.image_url:
                    product.image_url = data["image_url"]
                if data.get("images") and data["images"] != product.images:
                    product.images = data["images"]
                if (
                    data.get("specifications")
                    and data["specifications"] != product.specifications
                ):
                    product.specifications = data["specifications"]
                if (
                    data.get("variant_attributes")
                    and data["variant_attributes"] != product.variant_attributes
                ):
                    product.variant_attributes = data["variant_attributes"]

                db.commit()
                db.refresh(product)

                price_recalculated_count += 1

                # ========================================
                # ✅ STEP 4: Shopify pe price + metafields update karo
                # ✅ SIRF INCREASE PE (Shopify update)
                # ========================================
                if new_amazon_price > old_amazon:
                    await sync_shopify_price(
                        product=product,
                        new_price=new_final_price,
                        db=db,
                    )

                    logger.info(
                        f"[PRICE INCREASED] ASIN={product.asin} "
                        f"amazon: ${old_amazon} → ${new_amazon_price}, "
                        f"final: ${old_price} → ${new_final_price}"
                    )
                    price_increased_count += 1
                    updated_count += 1

                elif new_amazon_price < old_amazon:
                    # ❌ Price decreased — Shopify update nahi, lekin DB update ho gaya
                    logger.info(
                        f"[PRICE DECREASED - DB UPDATED, SHOPIFY SKIPPED] "
                        f"ASIN={product.asin} "
                        f"amazon: ${old_amazon} → ${new_amazon_price}, "
                        f"final: ${old_price} → ${new_final_price}"
                    )
                    price_decreased_count += 1
                    updated_count += 1

                else:
                    # ⚪ Price same — DB update ho gaya (same value)
                    logger.info(
                        f"[NO CHANGE] ASIN={product.asin} "
                        f"(price: ${new_amazon_price}, "
                        f"available: {new_availability})"
                    )

            except BrightDataError as e:
                logger.error(f"[ERROR] ASIN={product.asin}: {e}")
                error_count += 1
                continue
            except Exception as e:
                logger.error(f"[UNEXPECTED] ASIN={product.asin}: {e}")
                error_count += 1
                continue

        logger.info("=" * 60)
        logger.info(
            f"PRICE UPDATE COMPLETE — "
            f"Updated: {updated_count}, "
            f"Skipped: {skipped_count}, "
            f"Errors: {error_count}, "
            f"Out of Stock: {out_of_stock_count}, "
            f"Back in Stock: {back_in_stock_count}, "
            f"Shopify Synced: {shopify_synced_count}, "
            f"Price Increased: {price_increased_count}, "
            f"Price Decreased (DB only): {price_decreased_count}, "
            f"Price Recalculated: {price_recalculated_count}"
        )
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Scheduler job failed: {e}")
    finally:
        db.close()


# ============================================
# SCHEDULER START / STOP
# ============================================
def start_scheduler():
    """Scheduler start karo."""
    if scheduler.running:
        logger.info("Scheduler already running")
        return

    scheduler.add_job(
        update_all_prices,
        trigger=IntervalTrigger(hours=24),
        id="update_prices_job",
        name="Update Amazon prices every 24 hours",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started — price update har 24 ghante chalega")


def stop_scheduler():
    """Scheduler stop karo."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")


# ============================================
# MANUAL TRIGGER
# ============================================
async def run_price_update_now():
    """Immediately price update chalao (testing)."""
    await update_all_prices()