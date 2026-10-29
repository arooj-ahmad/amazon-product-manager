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

# ✅ Admin Auth (auth) ko hata diya gaya hai
from app.api.routes import (
    products,
    billing_routes,
    batch_routes,
    pricing,
    webhooks,
)
from app.api.routes.shopify import shopify_router  # ✅ Naya Shopify Router
from app.core.config import settings
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
# LIFESPAN
# ============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """App startup aur shutdown events handle karta hai."""
    # ---------- STARTUP ----------
    logger.info("=" * 60)
    logger.info("Starting Amazon Product Manager API...")
    logger.info("=" * 60)

    try:
        app.state.arq_pool = await create_pool(
            RedisSettings.from_dsn(settings.REDIS_URL)
        )
        logger.info("✅ ARQ pool initialized")
    except Exception as e:
        logger.error(f"❌ ARQ pool init fail: {e}")
        app.state.arq_pool = None

    try:
        start_scheduler()
        logger.info("✅ Scheduler started")
    except Exception as e:
        logger.error(f"❌ Scheduler start fail: {e}")

    logger.info("🚀 API is ready!")

    yield

    # ---------- SHUTDOWN ----------
    logger.info("Shutting down...")

    try:
        stop_scheduler()
        logger.info("✅ Scheduler stopped")
    except Exception as e:
        logger.error(f"❌ Scheduler stop fail: {e}")

    if getattr(app.state, "arq_pool", None):
        try:
            await app.state.arq_pool.close()
            logger.info("🔌 ARQ pool closed")
        except Exception as e:
            logger.error(f"❌ ARQ pool close fail: {e}")

    logger.info("Goodbye!")


# ============================================
# FASTAPI APP
# ============================================
app = FastAPI(
    title="Amazon Product Manager API",
    description=(
        "Amazon products manage karne ke liye API with Shopify integration. "
        "User side public hai, Shopify OAuth se protected hai."
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
# ✅ app.include_router(auth.router)  <-- YEH HATA DIYA HAI
app.include_router(products.router)

# ✅ Naya Shopify Router include kiya hai
app.include_router(shopify_router)

app.include_router(billing_routes.router)
app.include_router(batch_routes.router)
app.include_router(webhooks.router)

# ✅ Pricing/Markup — dono prefixes support karo (frontend compat)
app.include_router(pricing.router, prefix="/api/pricing", tags=["Pricing"])
app.include_router(pricing.router, prefix="/api/markup", tags=["Markup"])


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