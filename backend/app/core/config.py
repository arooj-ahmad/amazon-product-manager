# ============================================
# app/config.py
# Environment variables load karne ke liye
# Pydantic Settings v2
# ============================================

import re

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Saari environment variables yahan define karenge."""

    # ----------------------------------------
    # ENVIRONMENT
    # ----------------------------------------
    ENVIRONMENT: str = "development"

    # ----------------------------------------
    # DATABASE
    # ----------------------------------------
    DATABASE_URL: str

    # ----------------------------------------
    # REDIS (ARQ Background Jobs — batch import)
    # ----------------------------------------
    REDIS_URL: str = "redis://localhost:6379"

    # ----------------------------------------
    # BRIGHT DATA (Cron Job + Background Job)
    # ----------------------------------------
    BRIGHT_DATA_API_KEY: str
    BRIGHT_DATA_DATASET_ID: str
    BRIGHT_DATA_API_URL: str = "https://api.brightdata.com/datasets/v3/scrape"

    # ----------------------------------------
    # APIFY (Background Job — About this item)
    # ⚠️ NEVER hardcode token in code — use .env only
    # ✅ FIXED: Ab yeh Optional hai (default empty string)
    # ----------------------------------------
    APIFY_API_TOKEN: str = ""

    # ----------------------------------------
    # JWT
    # ----------------------------------------
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # ----------------------------------------
    # FRONTEND
    # ----------------------------------------
    FRONTEND_URL: str = "http://localhost:5173"

    # ----------------------------------------
    # COUNTRY / TAX
    # ----------------------------------------
    COUNTRY_STATE_CITY_API_KEY: str = ""

    # ----------------------------------------
    # SHOPIFY INTEGRATION
    # ----------------------------------------
    SHOPIFY_API_KEY: str = ""
    SHOPIFY_API_SECRET: str = ""
    SHOPIFY_SCOPES: str = "read_products,write_products"
    SHOPIFY_APP_URL: str = "https://example.com"
    SHOPIFY_REDIRECT_URI: str = "https://example.com/api/shopify/callback"
    SHOPIFY_API_VERSION: str = "2025-01"

    # Shopify webhook signing secret
    SHOPIFY_WEBHOOK_SECRET: str = ""

    # Shopify Store URL & Admin API
    SHOPIFY_SHOP_URL: str = ""
    SHOPIFY_ACCESS_TOKEN: str = ""
    SHOPIFY_LOCATION_ID: str = ""

    # Storefront API
    SHOPIFY_STOREFRONT_TOKEN: str = ""

    # ----------------------------------------
    # BATCH IMPORT (ARQ)
    # ----------------------------------------
    BATCH_MAX_URLS: int = 100
    BATCH_JOB_TIMEOUT: int = 600
    BATCH_MAX_JOBS: int = 3

    # ----------------------------------------
    # LOGGING
    # ----------------------------------------
    LOG_LEVEL: str = "INFO"

    # ----------------------------------------
    # BACKGROUND JOBS
    # ----------------------------------------
    BACKGROUND_JOB_MAX_CONCURRENT: int = 5

    # ----------------------------------------
    # Pydantic config
    # ----------------------------------------
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ----------------------------------------
    # Validators
    # ----------------------------------------
    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = ("development", "staging", "production")
        if v not in allowed:
            raise ValueError(
                f"ENVIRONMENT must be one of {allowed}, got '{v}'"
            )
        return v

    @field_validator("SHOPIFY_API_VERSION")
    @classmethod
    def validate_shopify_version(cls, v: str) -> str:
        if not re.match(r"^\d{4}-\d{2}$", v):
            raise ValueError(
                f"SHOPIFY_API_VERSION must be YYYY-MM (e.g. '2025-01'), got '{v}'"
            )
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(
                f"LOG_LEVEL must be one of {allowed}, got '{v}'"
            )
        return v_upper

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith(("postgresql://", "postgresql+asyncpg://", "postgresql+psycopg2://")):
            raise ValueError(
                "DATABASE_URL must start with postgresql://"
            )
        return v

    # ----------------------------------------
    # Derived properties
    # ----------------------------------------
    @property
    def shopify_redirect_uri_derived(self) -> str:
        return f"{self.SHOPIFY_APP_URL.rstrip('/')}/api/shopify/callback"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    # ----------------------------------------
    # Production validation
    # ----------------------------------------
    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.ENVIRONMENT == "production":
            # 1. Real URL check (example.com nahi hona chahiye)
            if "example.com" in self.SHOPIFY_APP_URL:
                raise ValueError(
                    "Production mein SHOPIFY_APP_URL real URL hona chahiye"
                )
            if "example.com" in self.SHOPIFY_REDIRECT_URI:
                raise ValueError(
                    "Production mein SHOPIFY_REDIRECT_URI real URL hona chahiye"
                )

            # 2. Critical secrets check (APIFY_API_TOKEN hata diya hai)
            required = {
                "SHOPIFY_API_KEY": self.SHOPIFY_API_KEY,
                "SHOPIFY_API_SECRET": self.SHOPIFY_API_SECRET,
                "SHOPIFY_WEBHOOK_SECRET": self.SHOPIFY_WEBHOOK_SECRET,
                "BRIGHT_DATA_API_KEY": self.BRIGHT_DATA_API_KEY,
            }
            missing = [k for k, v in required.items() if not v]
            if missing:
                raise ValueError(
                    f"Production mein yeh secrets set karna zaroori hai: {missing}"
                )
        return self


# Global settings instance
settings = Settings()