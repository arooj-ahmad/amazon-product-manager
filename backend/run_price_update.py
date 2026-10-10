# run_price_update.py
import sys
import os

# ✅ NAYA: PYTHONPATH fix — script ke folder ko add karo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.services.scheduler import run_price_update_now

if __name__ == "__main__":
    asyncio.run(run_price_update_now())