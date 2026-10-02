# run_worker.py
import sys
import asyncio
import logging

# Logging setup — INFO level (taake logs dikhein)
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