# ============================================
# app/config.py
# Environment variables load karne ke liye
# Pydantic Settings use kar rahe hain
# ============================================

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Saari environment variables yahan define karenge.
    Ye .env file se automatically load ho jayengi.
    """

    # ----------------------------------------
    # DATABASE
    # ----------------------------------------
    DATABASE_URL: str

    # ----------------------------------------
    # REDIS (ARQ Background Jobs)
    # ----------------------------------------
    REDIS_URL: str = "redis://localhost:6379"

    # ----------------------------------------
    # BRIGHT DATA (Amazon Scraper)
    # ----------------------------------------
    BRIGHT_DATA_API_KEY: str
    BRIGHT_DATA_DATASET_ID: str
    BRIGHT_DATA_API_URL: str = "https://api.brightdata.com/datasets/v3/scrape"

    # ----------------------------------------
    # JWT (Admin Authentication)
    # ----------------------------------------
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 ghante

    # ----------------------------------------
    # PRICING
    # ----------------------------------------
    DEFAULT_MARKUP: float = 2.0

    # ----------------------------------------
    # FRONTEND (CORS)
    # ----------------------------------------
    FRONTEND_URL: str = "http://localhost:5173"

    # ----------------------------------------
    # SHOPIFY INTEGRATION
    # ----------------------------------------
    SHOPIFY_API_KEY: str = ""
    SHOPIFY_API_SECRET: str = ""
    SHOPIFY_SCOPES: str = "read_products,write_products"
    SHOPIFY_APP_URL: str = "https://example.com"
    SHOPIFY_REDIRECT_URI: str = "https://example.com/api/shopify/callback"
    SHOPIFY_API_VERSION: str = "2025-01"

    # ✅ NAYA — Shopify Store URL aur Access Token
    SHOPIFY_SHOP_URL: str = ""           # e.g., "amazon-product-manager.myshopify.com"
    SHOPIFY_ACCESS_TOKEN: str = ""       # shpua_... or shpat_...
    SHOPIFY_LOCATION_ID: str = ""        # optional (inventory update ke liye)

    # ----------------------------------------
    # BATCH IMPORT (ARQ)
    # ----------------------------------------
    BATCH_MAX_URLS: int = 100          # Ek batch mein max URLs
    BATCH_JOB_TIMEOUT: int = 600       # 10 minutes per job
    BATCH_MAX_JOBS: int = 3            # Worker ek waqt mein kitne jobs

    # ----------------------------------------
    # Pydantic Settings Configuration
    # ----------------------------------------
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# Global settings instance
settings = Settings()