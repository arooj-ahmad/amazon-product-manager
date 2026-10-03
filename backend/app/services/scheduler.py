# ============================================
# app/services/scheduler.py
# Har 24 ghante Amazon se fresh prices fetch karne wala scheduler
# + Out of Stock tracking
# + Shopify Status Sync (DB token use karta hai)
# + Inventory quantity sync
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
)

logger = logging.getLogger(__name__)


# ============================================
# GLOBAL SCHEDULER INSTANCE
# ============================================
scheduler = AsyncIOScheduler()


# ============================================
# ✅ HELPER: SHOPIFY STATUS + INVENTORY SYNC
# DB se access token use karta hai
# ============================================
async def sync_shopify_product(
    product: Product,
    is_available: bool,
    stock_quantity: int,
    db: Session,
):
    """
    Product ka Shopify status + inventory update karta hai.
    - is_available = True  → status = ACTIVE
    - is_available = False → status = DRAFT
    - stock_quantity → inventory set
    """
    # ⚠️ DB se store dhundo (na ke .env se)
    store = db.query(ShopifyStore).first()

    if not store or not store.access_token:
        logger.warning("⚠️ No Shopify store in DB — skip sync")
        return

    shop = store.shop_domain
    access_token = store.access_token

    try:
        # Product ID dhundo
        shopify_id = product.shopify_product_id

        if not shopify_id:
            # SKU (ASIN) se Shopify product dhundo
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
        # Variant + inventory item ID nikalo
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
                # Stock quantity (0 ho lekin available ho → 100)
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
# JOB: UPDATE ALL PRICES
# ============================================
async def update_all_prices():
    """Saare products ke prices update karta hai (24h)."""
    logger.info("=" * 60)
    logger.info("PRICE UPDATE JOB STARTED")
    logger.info("=" * 60)

    db: Session = SessionLocal()

    try:
        products = db.query(Product).all()
        logger.info(f"Total products: {len(products)}")

        updated_count = 0
        skipped_count = 0
        error_count = 0
        out_of_stock_count = 0
        back_in_stock_count = 0
        shopify_synced_count = 0

        for product in products:
            # Manual override wale skip karo
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
                # STEP 3: Price check
                # ========================================
                if new_amazon_price is None:
                    logger.warning(f"[WARN] ASIN={product.asin} — price nahi mila")
                    db.commit()
                    db.refresh(product)
                    error_count += 1
                    continue

                if product.amazon_price == new_amazon_price:
                    logger.info(
                        f"[NO CHANGE] ASIN={product.asin} "
                        f"(price: ${new_amazon_price}, "
                        f"available: {new_availability})"
                    )
                    db.commit()
                    db.refresh(product)
                    continue

                old_price = product.price
                old_amazon = product.amazon_price

                # ✅ markup_type support
                new_final_price = calculate_final_price(
                    amazon_price=new_amazon_price,
                    markup=product.markup or 2.0,
                    markup_type=getattr(product, "markup_type", "fixed") or "fixed",
                )

                # Update price
                product.amazon_price = new_amazon_price
                product.price = new_final_price

                # Optional fields update
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

                db.commit()
                db.refresh(product)

                logger.info(
                    f"[UPDATED] ASIN={product.asin} "
                    f"amazon: ${old_amazon} → ${new_amazon_price}, "
                    f"final: ${old_price} → ${new_final_price}, "
                    f"available: {old_availability} → {new_availability}"
                )
                updated_count += 1

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
            f"Shopify Synced: {shopify_synced_count}"
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