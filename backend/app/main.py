# ============================================
# app/main.py
# FastAPI application ka main entry point
# ============================================

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from arq import create_pool
from arq.connections import RedisSettings

from app.api.routes import auth, products, shopify_routes, billing_routes, batch_routes, pricing
from app.config import settings
from app.services.scheduler import start_scheduler, stop_scheduler

# ============================================
# LOGGING SETUP
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================
# LIFESPAN (Startup + Shutdown) — EK HI RAKHEIN
# ============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    App startup aur shutdown events handle karta hai.
    - Scheduler start/stop
    - ARQ Redis pool create/close
    """
    # ---------- STARTUP ----------
    logger.info("=" * 60)
    logger.info("Starting Amazon Product Manager API...")
    logger.info("=" * 60)

    # 1) ARQ Redis pool
    try:
        app.state.arq_pool = await create_pool(
            RedisSettings.from_dsn(settings.REDIS_URL)
        )
        logger.info("✅ ARQ pool initialized")
    except Exception as e:
        logger.error(f"❌ ARQ pool init fail: {e}")
        app.state.arq_pool = None

    # 2) Scheduler
    try:
        start_scheduler()
        logger.info("✅ Scheduler started")
    except Exception as e:
        logger.error(f"❌ Scheduler start fail: {e}")

    logger.info("🚀 API is ready!")

    yield

    # ---------- SHUTDOWN ----------
    logger.info("Shutting down...")

    # 1) Scheduler stop
    try:
        stop_scheduler()
        logger.info("✅ Scheduler stopped")
    except Exception as e:
        logger.error(f"❌ Scheduler stop fail: {e}")

    # 2) ARQ pool close
    if getattr(app.state, "arq_pool", None):
        try:
            await app.state.arq_pool.close()
            logger.info("🔌 ARQ pool closed")
        except Exception as e:
            logger.error(f"❌ ARQ pool close fail: {e}")

    logger.info("Goodbye!")


# ============================================
# FASTAPI APP — SIRF EK BAAR
# ============================================
app = FastAPI(
    title="Amazon Product Manager API",
    description=(
        "Amazon products manage karne ke liye API with Shopify integration. "
        "User side public hai, admin side JWT protected hai."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================
# CORS MIDDLEWARE
# ============================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:5173",
        "http://localhost:3000",
        "https://admin.shopify.com",
        "https://amazon-product-manager-asev.vercel.app",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# ROUTERS
# ============================================
app.include_router(auth.router)
app.include_router(products.router)
app.include_router(shopify_routes.router)
app.include_router(billing_routes.router)
app.include_router(batch_routes.router)   # ← Batch import routes
app.include_router(pricing.router, prefix="/api/pricing", tags=["Pricing"])  # ← NAYA


# ============================================
# ROOT ENDPOINTS
# ============================================
@app.get("/", tags=["Root"])
def root():
    """Root endpoint — API running check"""
    return {
        "message": "Amazon Product Manager API",
        "status": "running",
        "docs": "/docs",
        "shopify_health": "/api/shopify/health",
    }


@app.get("/health", tags=["Root"])
def health_check():
    """Health check endpoint — monitoring ke liye"""
    return {"status": "healthy"}