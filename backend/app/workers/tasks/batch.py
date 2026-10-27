# app/workers/tasks/batch.py
import logging
from typing import Any, Dict

from app.services.amazon.brightdata_scraper import fetch_product_from_brightdata
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

async def process_batch_urls(ctx: Dict[str, Any], job_id: str, urls: list):
    results = {"succeeded": 0, "failed": 0, "details": []}
    total = len(urls)

    logger.info(f"Starting batch {job_id} with {total} URLs")

    for index, url in enumerate(urls, start=1):
        try:
            product_data = await fetch_product_from_brightdata(url)
            db = SessionLocal()
            try:
                pass
            finally:
                db.close()

            results["succeeded"] += 1
            results["details"].append({"url": url, "status": "success"})
            logger.info(f"[{job_id}] {index}/{total} SUCCESS {url}")

        except Exception as e:
            results["failed"] += 1
            results["details"].append({"url": url, "status": "failed", "error": str(e)})
            logger.error(f"[{job_id}] {index}/{total} FAILED {url} - {e}")

        try:
            await ctx["redis"].hset(
                f"batch:{job_id}",
                mapping={
                    "processed": results["succeeded"] + results["failed"],
                    "succeeded": results["succeeded"],
                    "failed": results["failed"],
                    "total": total,
                },
            )
            await ctx["redis"].expire(f"batch:{job_id}", 86400)
        except Exception as e:
            logger.warning(f"Progress update fail: {e}")

    logger.info(f"[{job_id}] Done - {results['succeeded']} success, {results['failed']} failed")
    return results
