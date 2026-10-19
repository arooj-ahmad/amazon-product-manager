# run_worker.py
import sys
import os

# ✅ NAYA: PYTHONPATH fix
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from arq.worker import run_worker
from app.workers.settings import WorkerSettings

if __name__ == "__main__":
    run_worker(WorkerSettings)