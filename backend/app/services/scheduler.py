# ============================================
# app/services/scheduler.py
# Har 24 ghante Amazon se fresh prices fetch karne wala scheduler
# + Out of Stock tracking
# + Shopify Status Sync (DB token use karta hai)
# + Inventory quantity sync (har variant)
# + Shopify price update (HAR CHANGE PE — increase ya decrease)
# + SAARE products process (draft bhi)
# + price hamesha amazon_price + markup update
# + Shopify metafields update
# + ✅ NAYA: shopify_status field DB mein save
# + ✅ NAYA: SKU na mile toh title se Shopify product dhoondo
# + ✅ FIXED: sync_update_shopify_price ab await ke saath
# + ✅ FIXED: refresh_token pass hota hai
# + ✅ FIXED: Product ke shopify_store_id se store dhoondha jata hai
# + ✅ FIXED: Manual override skip NAHI hota — sab products process hote hain
# + ✅ FIXED: Price push HAR change pe (increase ya decrease)
# + ✅ FIXED: is_available filter HATA DIYA — saare products process hote hain
# + ✅ FIXED: set_inventory_quantity ka result check hota hai
# + ✅ FIXED: Inventory error par warning log hoti hai
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
    set_product_metafields,
)

logger = logging.getLogger(__name__)


# ============================================
# GLOBAL SCHEDULER INSTANCE
# ============================================
scheduler = AsyncIOScheduler()


# ============================================
# ✅ HELPER: Product ke liye sahi store dhoondho
# ============================================
def _get_store_for_product(
    db: Session,
    product: Product,
    fallback_store_id: int = None,
) -> ShopifyStore:
    """Product ke shopify_store_id se store dhoondho."""
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
# ✅ HELPER: TITLE SE SHOPIFY PRODUCT DHOONDO
# ============================================
async def find_shopify_product_by_title(
    shop: str,
    access_token: str,
    title: str,
) -> str | None:
    """Shopify pe product ko title se dhoondta hai (SKU fallback)."""
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
        result = await shopify_graphql(
            shop, access_token, query, {"query": search_term}
        )

        edges = (
            result.get("data", {})
            .get("products", {})
            .get("edges", [])
        )

        if edges:
            shopify_id = edges[0]["node"]["id"]
            found_title = edges[0]["node"]["title"]
            logger.info(
                f"✅ Shopify product found by title: "
                f"'{found_title[:50]}...' → {shopify_id}"
            )
            return shopify_id

        logger.warning(f"⚠️ Shopify product not found by title: {search_term}")
        return None

    except Exception as e:
        logger.error(f"❌ Title search error: {e}")
        return None


# ============================================
# ✅ HELPER: SHOPIFY STATUS + INVENTORY SYNC
# ✅ FIXED: set_inventory_quantity ka result check hota hai
# ============================================
async def sync_shopify_product(
    product: Product,
    is_available: bool,
    stock_quantity: int,
    db: Session,
):
    """Product ka Shopify status + inventory update karta hai."""
    store = _get_store_for_product(db, product)

    if not store or not store.access_token:
        logger.warning("⚠️ No Shopify store in DB — skip sync")
        product.shopify_status = "draft"
        db.commit()
        return

    shop = store.shop_domain
    access_token = store.access_token

    try:
        shopify_id = product.shopify_product_id

        if shopify_id:
            logger.info(f"✅ Using saved shopify_product_id: {shopify_id}")

        if not shopify_id:
            shopify_id = await get_shopify_product_by_sku(
                shop=shop,
                access_token=access_token,
                sku=product.asin,
            )
            if shopify_id:
                product.shopify_product_id = shopify_id
                logger.info(f"✅ Shopify product linked by SKU: {shopify_id}")

        if not shopify_id and product.title:
            shopify_id = await find_shopify_product_by_title(
                shop=shop,
                access_token=access_token,
                title=product.title,
            )
            if shopify_id:
                product.shopify_product_id = shopify_id
                logger.info(f"✅ Shopify product linked by TITLE: {shopify_id}")

        if not shopify_id:
            logger.warning(
                f"❌ Shopify product not found for ASIN={product.asin} "
                f"(tried: DB ID, SKU, Title)"
            )
            product.shopify_status = "draft"
            db.commit()
            return

        # ── Status update ──
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
        else:
            logger.warning(
                f"⚠️ Shopify status update failed: ASIN={product.asin}"
            )

        product.shopify_status = "active" if is_available else "draft"
        product.shopify_product_id = shopify_id
        db.commit()
        logger.info(
            f"✅ shopify_status saved in DB: "
            f"ASIN={product.asin}, status={product.shopify_status}"
        )

        # ── Inventory quantity update (HAR VARIANT) ──
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

        result = await shopify_graphql(
            shop, access_token, query, {"id": shopify_id}
        )

        # ✅ Check GraphQL error
        if "errors" in result:
            logger.error(
                f"❌ Inventory query error for ASIN={product.asin}: "
                f"{result['errors']}"
            )
            return

        edges = (
            result.get("data", {})
            .get("product", {})
            .get("variants", {})
            .get("edges", [])
        )

        if not edges:
            logger.warning(
                f"⚠️ No variants found for ASIN={product.asin}"
            )
            return

        # ✅ Har variant ka inventory update karo
        for edge in edges:
            inventory_item_id = (
                edge.get("node", {})
                .get("inventoryItem", {})
                .get("id")
            )

            if not inventory_item_id:
                logger.warning(
                    f"⚠️ inventory_item_id missing for ASIN={product.asin}"
                )
                continue

            qty = stock_quantity
            if qty == 0 and is_available:
                qty = 100

            inv_ok = await set_inventory_quantity(
                shop=shop,
                access_token=access_token,
                inventory_item_id=inventory_item_id,
                quantity=qty,
            )

            if inv_ok:
                logger.info(
                    f"✅ Inventory synced: ASIN={product.asin}, qty={qty}"
                )
            else:
                logger.error(
                    f"❌ Inventory update FAILED: ASIN={product.asin}, "
                    f"qty={qty}"
                )

    except Exception as e:
        logger.error(f"❌ Shopify sync error: ASIN={product.asin}: {e}")


# ============================================
# ✅ HELPER: SHOPIFY PRICE + METAFIELDS UPDATE
# ============================================
async def sync_shopify_price(product: Product, new_price: float, db: Session):
    """Shopify pe product ka price + metafields update karta hai."""
    store = _get_store_for_product(db, product)

    if not store or not store.access_token:
        logger.warning("⚠️ No Shopify store in DB — skip price update")
        return False

    shop = store.shop_domain
    access_token = store.access_token
    refresh_token = store.refresh_token

    shopify_id = product.shopify_product_id

    if not shopify_id:
        shopify_id = await get_shopify_product_by_sku(
            shop=shop,
            access_token=access_token,
            sku=product.asin,
        )
        if shopify_id:
            product.shopify_product_id = shopify_id

    if not shopify_id and product.title:
        shopify_id = await find_shopify_product_by_title(
            shop=shop,
            access_token=access_token,
            title=product.title,
        )
        if shopify_id:
            product.shopify_product_id = shopify_id

    if not shopify_id:
        logger.warning(f"⚠️ Shopify product not found for ASIN={product.asin}")
        return False

    try:
        success = await sync_update_shopify_price(
            shop_domain=shop,
            access_token=access_token,
            shopify_product_id=shopify_id,
            new_price=new_price,
            refresh_token=refresh_token,
        )
        if success:
            logger.info(
                f"✅ Shopify price updated: ASIN={product.asin}, "
                f"new_price=${new_price}"
            )
        else:
            logger.warning(
                f"⚠️ Shopify price update returned False: ASIN={product.asin}"
            )

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
# ✅ FIXED: is_available filter HATA DIYA
# ============================================
async def update_all_prices():
    """SAARE products ke prices update karta hai (24h)."""
    logger.info("=" * 60)
    logger.info("PRICE UPDATE JOB STARTED")
    logger.info("=" * 60)

    db: Session = SessionLocal()

    try:
        # ✅ FIXED: Saare products process karo (draft/out-of-stock bhi)
        # Isse wapas stock aane pe is_available = true ho jayega
        products = db.query(Product).all()
        logger.info(f"Total products: {len(products)}")

        updated_count = 0
        skipped_count = 0
        error_count = 0
        out_of_stock_count = 0
        back_in_stock_count = 0
        shopify_synced_count = 0
        price_changed_count = 0
        price_recalculated_count = 0

        for product in products:
            try:
                amazon_url = f"https://www.amazon.com/dp/{product.asin}"
                data = await fetch_product_from_brightdata(amazon_url)

                new_amazon_price = data["amazon_price"]

                # STEP 1: Availability
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

                availability_changed = (old_availability != new_availability)

                if availability_changed:
                    if new_availability:
                        logger.info(f"✅ [BACK IN STOCK] ASIN={product.asin}")
                        back_in_stock_count += 1
                    else:
                        logger.warning(f"❌ [OUT OF STOCK] ASIN={product.asin}")
                        out_of_stock_count += 1

                # STEP 2: Shopify sync (status + inventory)
                await sync_shopify_product(
                    product=product,
                    is_available=new_availability,
                    stock_quantity=product.stock_quantity,
                    db=db,
                )
                shopify_synced_count += 1

                # STEP 3: Price check
                if new_amazon_price is None:
                    logger.warning(f"[WARN] ASIN={product.asin} — price nahi mila")
                    db.commit()
                    db.refresh(product)
                    error_count += 1
                    continue

                old_amazon = product.amazon_price or 0
                old_price = product.price

                new_final_price = calculate_final_price(
                    amazon_price=new_amazon_price,
                    markup=product.markup or 2.0,
                    markup_type=getattr(product, "markup_type", "fixed") or "fixed",
                )

                product.amazon_price = new_amazon_price
                product.price = new_final_price

                # Metadata update
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

                # STEP 4: Shopify pe price + metafields HAR change pe push
                if new_amazon_price != old_amazon:
                    await sync_shopify_price(
                        product=product,
                        new_price=new_final_price,
                        db=db,
                    )

                    logger.info(
                        f"[PRICE CHANGED] ASIN={product.asin} "
                        f"amazon: ${old_amazon} → ${new_amazon_price}, "
                        f"final: ${old_price} → ${new_final_price}"
                    )
                    price_changed_count += 1
                    updated_count += 1
                else:
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
            f"Errors: {error_count}, "
            f"Out of Stock: {out_of_stock_count}, "
            f"Back in Stock: {back_in_stock_count}, "
            f"Shopify Synced: {shopify_synced_count}, "
            f"Price Changed: {price_changed_count}, "
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