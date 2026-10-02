# app/workers/settings.py
from arq.connections import RedisSettings
from app.config import settings
from app.workers.tasks import process_batch_urls


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    functions = [process_batch_urls]
    max_jobs = 3
    job_timeout = 600
    keep_result = 3600
    # queue_name = "batch_import"   ← yeh line hata dein

    @staticmethod
    async def on_startup(ctx):
        print("✅ Worker started, ready to process jobs")

    @staticmethod
    async def on_shutdown(ctx):
        print("🔌 Worker shutting down")