# enqueue_price_updates.py
import asyncio
import logging
from arq import create_pool
from arq.connections import RedisSettings

from app.config import settings
from app.database import SessionLocal
from app.models import Product

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


async def enqueue_all():
    """Saare Active products ko Redis queue mein enqueue karo."""
    db = SessionLocal()

    products = db.query(Product).filter(
        Product.is_available == True,  # noqa: E712
        Product.is_manual_override == False,  # noqa: E712
    ).all()

    db.close()

    total = len(products)
    logger.info(f"Total products to enqueue: {total}")

    if total == 0:
        logger.warning("No products to enqueue")
        return

    redis = await create_pool(
        RedisSettings.from_dsn(settings.REDIS_URL)
    )

    enqueued = 0

    for p in products:
        await redis.enqueue_job("process_price_update", p.asin)
        enqueued += 1

        if enqueued % 100 == 0:
            logger.info(f"Enqueued: {enqueued}/{total}")

    await redis.close()

    logger.info(f"✅ Enqueued: {enqueued} jobs")


if __name__ == "__main__":
    asyncio.run(enqueue_all())