# ============================================
# app/services/scheduler/__init__.py
# ============================================

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .jobs import update_all_prices

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

last_run_status = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "summary": None,
}

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

# Purane imports ko break hone se bachane ke liye __all__
__all__ = [
    "scheduler",
    "last_run_status",
    "start_scheduler",
    "stop_scheduler",
    "run_price_update_now",
    "update_all_prices",
]