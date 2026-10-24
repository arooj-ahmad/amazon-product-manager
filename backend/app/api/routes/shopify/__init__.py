# app/api/routes/shopify/__init__.py

from fastapi import APIRouter
from .auth_routes import router as auth_router
from .cron_routes import router as cron_router
from .product_routes import router as product_router

shopify_router = APIRouter(prefix="/api/shopify")
shopify_router.include_router(auth_router)
shopify_router.include_router(cron_router)
shopify_router.include_router(product_router)