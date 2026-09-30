# ============================================
# app/main.py
# FastAPI application ka main entry point
# ============================================

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, products, shopify_routes
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
# LIFESPAN (Startup + Shutdown)
# ============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    App startup aur shutdown events handle karta hai.
    """
    # STARTUP
    logger.info("=" * 60)
    logger.info("Starting Amazon Product Manager API...")
    logger.info("=" * 60)

    try:
        start_scheduler()
        logger.info("Scheduler started")
    except Exception as e:
        logger.error(f"Scheduler start fail: {e}")

    logger.info("API is ready!")

    yield

    # SHUTDOWN
    logger.info("Shutting down...")
    try:
        stop_scheduler()
        logger.info("Scheduler stopped")
    except Exception as e:
        logger.error(f"Scheduler stop fail: {e}")
    logger.info("Goodbye!")


# ============================================
# FASTAPI APP
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
        # Shopify admin domain (development ke liye)
        "https://admin.shopify.com",
    ],
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
    """Health check endpoint — Render ke liye"""
    return {"status": "healthy"}