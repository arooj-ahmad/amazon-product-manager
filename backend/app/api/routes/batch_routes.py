# ============================================
# app/api/routes/batch_routes.py
# Batch import endpoints (ARQ powered)
# ============================================

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List
import time
import logging

from arq.jobs import Job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/batch", tags=["Batch Import"])


# ============================================
# SCHEMAS
# ============================================
class BatchImportRequest(BaseModel):
    urls: List[str] = Field(..., min_length=1, max_length=100)


class BatchImportResponse(BaseModel):
    job_id: str
    status: str
    total_urls: int
    message: str


class BatchStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: dict


# ============================================
# START BATCH IMPORT
# ============================================
@router.post("/import", response_model=BatchImportResponse)
async def start_batch_import(request: Request, body: BatchImportRequest):
    """
    50+ Amazon URLs receive karein, background mein process karein.
    """
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        raise HTTPException(
            status_code=503,
            detail="ARQ pool not available. Redis check karein."
        )

    # Basic URL validation
    valid_urls = []
    for url in body.urls:
        url = url.strip()
        if not url:
            continue
        if "amazon." not in url.lower():
            raise HTTPException(
                status_code=400,
                detail=f"Invalid Amazon URL: {url}"
            )
        valid_urls.append(url)

    if not valid_urls:
        raise HTTPException(status_code=400, detail="Koi valid URL nahi mila")

    # Unique job ID
    job_id = f"batch_{int(time.time() * 1000)}"

    # Progress initial state Redis mein set karein
    await pool.hset(
        f"batch:{job_id}",
        mapping={
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "total": len(valid_urls),
            "status": "queued",
        }
    )
    await pool.expire(f"batch:{job_id}", 86400)

    # ARQ mein enqueue karein — INSTANT return
    await pool.enqueue_job(
        "process_batch_urls",
        job_id,
        valid_urls,
        _job_id=job_id,
    )

    logger.info(f"Batch enqueued: {job_id} ({len(valid_urls)} URLs)")

    return BatchImportResponse(
        job_id=job_id,
        status="queued",
        total_urls=len(valid_urls),
        message=f"Batch started. Status check karein: /api/batch/job/{job_id}",
    )


# ============================================
# GET BATCH STATUS
# ============================================
@router.get("/job/{job_id}", response_model=BatchStatusResponse)
async def get_batch_status(request: Request, job_id: str):
    """
    Job ka status aur progress check karein.
    """
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="ARQ pool not available")

    # Redis se progress read karein
    progress = await pool.hgetall(f"batch:{job_id}")
    if not progress:
        raise HTTPException(status_code=404, detail="Job nahi mila")

    # ARQ se job status
    job = Job(job_id, pool)
    job_status = await job.status()

    # Progress values ko int mein convert karein
    progress_clean = {
        "processed": int(progress.get("processed", 0)),
        "succeeded": int(progress.get("succeeded", 0)),
        "failed": int(progress.get("failed", 0)),
        "total": int(progress.get("total", 0)),
    }

    return BatchStatusResponse(
        job_id=job_id,
        status=job_status.value if job_status else "unknown",
        progress=progress_clean,
    )


# ============================================
# GET JOB RESULT
# ============================================
@router.get("/job/{job_id}/result")
async def get_batch_result(request: Request, job_id: str):
    """
    Job complete hone ke baad detailed result.
    """
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="ARQ pool not available")

    job = Job(job_id, pool)

    try:
        result = await job.result(timeout=1)
        return {"job_id": job_id, "status": "complete", "result": result}
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Result abhi ready nahi ya job fail hua: {str(e)}"
        )