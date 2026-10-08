# app/workers/settings.py
from arq.connections import RedisSettings
from app.config import settings
from app.workers.tasks import process_batch_urls, process_price_update  # ✅ NAYA


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    functions = [
        process_batch_urls,
        process_price_update,  # ✅ NAYA
    ]
    max_jobs = 5          # ✅ 3 → 5 (zyada parallel)
    job_timeout = 600
    keep_result = 3600

    @staticmethod
    async def on_startup(ctx):
        print("✅ Worker started, ready to process jobs")

    @staticmethod
    async def on_shutdown(ctx):
        print("🔌 Worker shutting down")