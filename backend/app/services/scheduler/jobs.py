# ============================================
# app/services/scheduler/jobs.py
# ============================================

import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Product
from app.services.amazon import (
    BrightDataError,
    calculate_final_price,
    fetch_product_from_brightdata,
)
from .helpers import (
    get_store_for_product,
    get_store_default_markup,
    apply_markup_cap,
    calculate_compare_at_price,
)
from .shopify_sync import sync_shopify_product, sync_shopify_price

logger = logging.getLogger(__name__)

async def update_all_prices():
    logger.info("=" * 60)
    logger.info("PRICE UPDATE JOB STARTED")
    logger.info("=" * 60)

    # Global status (frontend polling ke liye)
    from . import last_run_status
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
                store = get_store_for_product(db, product)
                (
                    store_markup,
                    store_markup_type,
                    store_extra_pct,
                    store_tax_rate,
                ) = get_store_default_markup(store)

                amazon_url = f"https://www.amazon.com/dp/{product.asin}"
                
                # ✅ Bright Data se sirf Price aur Stock fetch hoga
                data = await fetch_product_from_brightdata(amazon_url)

                new_amazon_price = data.get("amazon_price")

                # SMART FALLBACK LOGIC
                old_availability = product.is_available
                
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

                # Shopify Inventory Sync
                await sync_shopify_product(
                    product=product,
                    is_available=new_availability,
                    stock_quantity=product.stock_quantity,
                    db=db,
                )
                shopify_synced_count += 1

                # Price Check & Update
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

                capped_markup = apply_markup_cap(store_markup, store_markup_type)

                new_final_price = calculate_final_price(
                    amazon_price=new_amazon_price,
                    markup=capped_markup,
                    markup_type=store_markup_type,
                    extra_percent=store_extra_pct,
                    tax_rate=store_tax_rate,
                )

                compare_at_price = calculate_compare_at_price(store, new_final_price, new_amazon_price)

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

                # Push to Shopify if changed
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