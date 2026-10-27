# ============================================
# app/services/scheduler/__init__.py
# ============================================

import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

# ✅ Dono alag-alag jobs import kiye hain
from .jobs import update_prices_only, update_inventory_only

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

    # ✅ 1. Price Update Job (Har 24 ghante)
    scheduler.add_job(
        update_prices_only,
        trigger=IntervalTrigger(hours=24),
        id="update_prices_job",
        name="Update Amazon prices every 24 hours",
        replace_existing=True,
    )

    # ✅ 2. Inventory Update Job (Har 24 ghante, 5 minute baad)
    scheduler.add_job(
        update_inventory_only,
        trigger=IntervalTrigger(hours=24),
        id="update_inventory_job",
        name="Update Amazon inventory every 24 hours",
        next_run_time=datetime.now() + timedelta(minutes=5),
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started — Price (0 min) aur Inventory (5 min) dono alag-alag chalenge")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")


# ✅ Manual triggers (Frontend ke buttons ke liye)
async def run_price_update_now():
    return await update_prices_only()

async def run_inventory_update_now():
    return await update_inventory_only()


# Purane imports ko break hone se bachane ke liye __all__
__all__ = [
    "scheduler",
    "last_run_status",
    "start_scheduler",
    "stop_scheduler",
    "run_price_update_now",
    "run_inventory_update_now",
    "update_prices_only",
    "update_inventory_only",
]