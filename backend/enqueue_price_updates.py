# enqueue_price_updates.py
# ✅ FIXED: Direct process — Redis/arq bypass
# ✅ FIXED: Manual override skip NAHI hota
# Cron job yeh file chalayega → saare products ka price update hoga

import asyncio
import logging
import sys

from app.database import SessionLocal
from app.models import Product
from app.workers.tasks import process_price_update

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


async def run_all():
    """
    Saare products ka price update DIRECTLY chalao.
    - Active + Draft dono
    - Manual override bhi process (skip nahi)
    - Redis/arq ki zaroorat nahi
    """
    db = SessionLocal()

    # ✅ FIXED: Manual override filter HATA diya
    products = db.query(Product).filter(
        Product.asin.isnot(None),
    ).all()

    db.close()

    total = len(products)
    logger.info("=" * 60)
    logger.info(f"🚀 DIRECT PRICE UPDATE — Total products: {total}")
    logger.info("=" * 60)

    if total == 0:
        logger.warning("⚠️ No products to process")
        return

    # ✅ Context (Redis optional hai, None bhi chalega)
    ctx = {"redis": None}

    success = 0
    failed = 0
    skipped = 0

    for i, p in enumerate(products, start=1):
        try:
            logger.info(f"[{i}/{total}] Processing ASIN={p.asin}...")
            result = await process_price_update(ctx, p.asin)

            status = result.get("status") if isinstance(result, dict) else "unknown"

            if status == "success":
                success += 1
                logger.info(f"[{i}/{total}] ✅ {p.asin}: {result}")
            elif status == "skipped_manual_override":
                skipped += 1
                logger.info(f"[{i}/{total}] ⏭️ {p.asin}: skipped (manual override)")
            else:
                failed += 1
                logger.warning(f"[{i}/{total}] ⚠️ {p.asin}: {result}")

        except Exception as e:
            failed += 1
            logger.error(f"[{i}/{total}] ❌ {p.asin}: {e}", exc_info=True)

    logger.info("=" * 60)
    logger.info(f"✅ Success: {success}")
    logger.info(f"⏭️ Skipped: {skipped}")
    logger.info(f"❌ Failed: {failed}")
    logger.info(f"📊 Total: {total}")
    logger.info("=" * 60)


if __name__ == "__main__":
    # Windows event loop fix
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(run_all())