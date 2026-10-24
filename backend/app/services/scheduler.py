# ============================================
# app/services/scheduler.py
# Har 24 ghante Amazon se fresh prices fetch karne wala scheduler
# ============================================

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Product, ShopifyStore

# ✅ Naye folder structure se imports
from app.services.amazon import (
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

last_run_status = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "summary": None,
}


def _get_store_for_product(db: Session, product: Product, fallback_store_id: int = None) -> ShopifyStore:
    store = None
    if product and product.shopify_store_id:
        store = db.query(ShopifyStore).filter(ShopifyStore.id == product.shopify_store_id).first()
    if not store and fallback_store_id:
        store = db.query(ShopifyStore).filter(ShopifyStore.id == fallback_store_id).first()
    if not store:
        store = db.query(ShopifyStore).first()
    return store


def _get_store_default_markup(store: ShopifyStore) -> tuple:
    if not store:
        return None, None, 0.0, 0.0

    markup_val = getattr(store, "default_markup", None)
    markup_type = getattr(store, "default_markup_type", None)
    extra_pct = float(getattr(store, "default_extra_percent", None) or 0.0)
    tax_rate = float(getattr(store, "default_tax_rate", None) or 0.0)

    if markup_val is not None:
        markup_val = float(markup_val)
    if markup_type is not None and markup_type not in ("fixed", "percent", "both"):
        markup_type = "fixed"

    return markup_val, markup_type, extra_pct, tax_rate


def _apply_markup_cap(markup: float, markup_type: str) -> float:
    try:
        markup = float(markup)
    except (ValueError, TypeError):
        return 0.0

    if markup < 0:
        markup = 0.0

    if markup_type == "fixed":
        if markup > 50:
            logger.warning(f"⚠️ Fixed markup ${markup} capped at $50")
            markup = 50.0
    elif markup_type == "percent":
        if markup > 500:
            logger.warning(f"⚠️ Percent markup {markup}% capped at 500%")
            markup = 500.0
    elif markup_type == "both":
        if markup > 50:
            logger.warning(f"⚠️ Fixed part ${markup} capped at $50")
            markup = 50.0

    return markup


def _calculate_compare_at_price(store: ShopifyStore, final_price: float, amazon_price: float) -> float | None:
    if not store or not final_price or final_price <= 0:
        return None

    rule = getattr(store, "default_compare_at_rule", None)
    if not rule:
        enabled = bool(getattr(store, "default_compare_at_enabled", False))
        if not enabled:
            rule = "none"
        else:
            old_type = getattr(store, "default_compare_at_type", None) or "percent"
            if old_type == "amazon":
                rule = "amazon"
            elif old_type == "fixed":
                rule = "fixed"
            else:
                rule = "percent"

    if rule == "none":
        return None

    compare_value = float(getattr(store, "default_compare_at_value", None) or 0.0)

    if rule == "amazon":
        if amazon_price and amazon_price > final_price:
            return round(float(amazon_price), 2)
        return None

    if compare_value <= 0:
        return None

    try:
        if rule == "percent":
            compare_price = final_price * (1 + compare_value / 100)
        elif rule == "fixed":
            compare_price = final_price + compare_value
        else:
            return None

        compare_price = round(compare_price, 2)
        return compare_price if compare_price > final_price else None
    except (ValueError, TypeError):
        return None


async def find_shopify_product_by_title(shop: str, access_token: str, title: str) -> str | None:
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
        result = await shopify_graphql(shop, access_token, query, {"query": search_term})
        if not result:
            return None

        data = result.get("data") or {}
        products_data = data.get("products") or {}
        edges = products_data.get("edges") or []

        if edges:
            return edges[0].get("node", {}).get("id")
        return None
    except Exception as e:
        logger.error(f"❌ Title search error: {e}")
        return None


async def sync_shopify_product(product: Product, is_available: bool, stock_quantity: int, db: Session):
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

        if not shopify_id:
            shopify_id = await get_shopify_product_by_sku(shop, access_token, product.asin)
            if shopify_id:
                product.shopify_product_id = shopify_id

        if not shopify_id and product.title:
            shopify_id = await find_shopify_product_by_title(shop, access_token, product.title)
            if shopify_id:
                product.shopify_product_id = shopify_id

        if not shopify_id:
            logger.warning(f"❌ Shopify product not found for ASIN={product.asin}")
            product.shopify_status = "draft"
            db.commit()
            return

        # Status update
        await update_shopify_product_status(
            shop=shop,
            access_token=access_token,
            shopify_product_id=shopify_id,
            is_available=is_available,
        )

        product.shopify_status = "active" if is_available else "draft"
        db.commit()

        # Inventory quantity update
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

        result = await shopify_graphql(shop, access_token, query, {"id": shopify_id})
        if not result or "errors" in result:
            return

        edges = result.get("data", {}).get("product", {}).get("variants", {}).get("edges", [])
        
        for edge in edges:
            inventory_item_id = edge.get("node", {}).get("inventoryItem", {}).get("id")
            if not inventory_item_id:
                continue

            await set_inventory_quantity(
                shop=shop,
                access_token=access_token,
                inventory_item_id=inventory_item_id,
                quantity=stock_quantity,
            )

    except Exception as e:
        logger.error(f"❌ Shopify sync error: ASIN={product.asin}: {e}")


async def sync_shopify_price(product: Product, new_price: float, db: Session, compare_at_price: float = None):
    store = _get_store_for_product(db, product)
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

    try:
        success = await sync_update_shopify_price(
            shop_domain=shop,
            access_token=access_token,
            shopify_product_id=shopify_id,
            new_price=new_price,
            refresh_token=refresh_token,
            compare_at_price=compare_at_price,
        )

        # Metafields update
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


# ============================================
# JOB: UPDATE ALL PRICES
# ============================================
async def update_all_prices():
    global last_run_status
    logger.info("=" * 60)
    logger.info("PRICE UPDATE JOB STARTED")
    logger.info("=" * 60)

    last_run_status["running"] = True
    last_run_status["started_at"] = datetime.now(timezone.utc).isoformat()
    last_run_status["finished_at"] = None
    last_run_status["summary"] = None

    db: Session = SessionLocal()

    try:
        products = db.query(Product).all()
        total_products = len(products)
        
        updated_count = 0
        skipped_count = 0
        error_count = 0
        out_of_stock_count = 0
        back_in_stock_count = 0
        shopify_synced_count = 0
        price_changed_count = 0
        results = []

        for index, product in enumerate(products, start=1):
            try:
                store = _get_store_for_product(db, product)
                (
                    store_markup,
                    store_markup_type,
                    store_extra_pct,
                    store_tax_rate,
                ) = _get_store_default_markup(store)

                amazon_url = f"https://www.amazon.com/dp/{product.asin}"
                
                # ✅ Bright Data se sirf Price aur Stock fetch hoga
                data = await fetch_product_from_brightdata(amazon_url)

                new_amazon_price = data.get("amazon_price")

                # =====================================================
                # ✅ SMART FALLBACK LOGIC: Stock ko 0 hone se bachaye
                # =====================================================
                old_availability = product.is_available
                
                # Agar Bright Data ne data diya hai lekin availability clear nahi hai
                # toh purana stock aur purani availability hi rakho.
                if data.get("is_available") is None:
                    logger.warning(f"⚠️ Bright Data availability nahi de raha ASIN={product.asin}. Purana stock use kar rahe hain.")
                    new_availability = old_availability
                    new_stock = product.stock_quantity
                    new_availability_text = product.availability
                else:
                    new_availability = data.get("is_available")
                    new_stock = data.get("stock_quantity", 0)
                    new_availability_text = data.get("availability", "In Stock")

                product.availability = new_availability_text
                product.is_available = new_availability
                product.stock_quantity = new_stock
                product.last_synced_at = datetime.now(timezone.utc)

                if old_availability != new_availability:
                    if new_availability:
                        logger.info(f"✅ [BACK IN STOCK] ASIN={product.asin}")
                        back_in_stock_count += 1
                    else:
                        logger.warning(f"❌ [OUT OF STOCK] ASIN={product.asin}")
                        out_of_stock_count += 1

                # 2. Shopify Inventory Sync
                await sync_shopify_product(
                    product=product,
                    is_available=new_availability,
                    stock_quantity=product.stock_quantity,
                    db=db,
                )
                shopify_synced_count += 1

                # 3. Price Check & Update
                if new_amazon_price is None:
                    logger.warning(f"[WARN] ASIN={product.asin} — price nahi mila")
                    db.commit()
                    error_count += 1
                    results.append({"index": index, "asin": product.asin, "status": "error", "error": "Price not available"})
                    continue

                if store_markup is None or store_markup_type is None:
                    logger.warning(f"⚠️ ASIN={product.asin}: markup missing — skip")
                    skipped_count += 1
                    results.append({"index": index, "asin": product.asin, "status": "skipped", "reason": "Markup missing"})
                    continue

                old_amazon = product.amazon_price or 0
                old_price = product.price

                capped_markup = _apply_markup_cap(store_markup, store_markup_type)

                new_final_price = calculate_final_price(
                    amazon_price=new_amazon_price,
                    markup=capped_markup,
                    markup_type=store_markup_type,
                    extra_percent=store_extra_pct,
                    tax_rate=store_tax_rate,
                )

                compare_at_price = _calculate_compare_at_price(store, new_final_price, new_amazon_price)

                product.amazon_price = new_amazon_price
                product.price = new_final_price
                product.markup = capped_markup
                product.markup_type = store_markup_type
                
                if hasattr(product, "extra_percent"):
                    product.extra_percent = store_extra_pct
                if hasattr(product, "tax_rate"):
                    product.tax_rate = store_tax_rate

                db.commit()
                db.refresh(product)

                # 4. Push to Shopify if changed
                price_changed = (new_amazon_price != old_amazon or new_final_price != old_price)

                if price_changed:
                    await sync_shopify_price(
                        product=product,
                        new_price=new_final_price,
                        db=db,
                        compare_at_price=compare_at_price,
                    )
                    logger.info(f"[PRICE CHANGED] ASIN={product.asin} amazon: ${old_amazon} → ${new_amazon_price}")
                    price_changed_count += 1
                    updated_count += 1
                    results.append({"index": index, "asin": product.asin, "status": "updated", "old_price": old_price, "new_price": new_final_price})
                else:
                    skipped_count += 1
                    results.append({"index": index, "asin": product.asin, "status": "skipped"})

            except BrightDataError as e:
                logger.error(f"[ERROR] ASIN={product.asin}: {e}")
                error_count += 1
                results.append({"index": index, "asin": product.asin, "status": "error", "error": str(e)[:200]})
            except Exception as e:
                logger.error(f"[UNEXPECTED] ASIN={product.asin}: {e}")
                error_count += 1
                results.append({"index": index, "asin": product.asin, "status": "error", "error": str(e)[:200]})

        logger.info("=" * 60)
        logger.info(f"PRICE UPDATE COMPLETE — Updated: {updated_count}, Errors: {error_count}, OOS: {out_of_stock_count}, Back: {back_in_stock_count}")
        logger.info("=" * 60)

        summary = {
            "total": total_products,
            "updated": updated_count,
            "skipped": skipped_count,
            "errors": error_count,
            "out_of_stock": out_of_stock_count,
            "back_in_stock": back_in_stock_count,
            "shopify_synced": shopify_synced_count,
            "price_changed": price_changed_count,
            "results": results,
        }

        last_run_status["running"] = False
        last_run_status["finished_at"] = datetime.now(timezone.utc).isoformat()
        last_run_status["summary"] = summary

        return summary

    except Exception as e:
        logger.error(f"Scheduler job failed: {e}")
        last_run_status["running"] = False
        last_run_status["finished_at"] = datetime.now(timezone.utc).isoformat()
        last_run_status["summary"] = {"error": str(e)}
        return {"error": str(e)}
    finally:
        db.close()


# ============================================
# SCHEDULER START / STOP
# ============================================
def start_scheduler():
    if scheduler.running:
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
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")


async def run_price_update_now():
    return await update_all_prices()