# ============================================
# app/schemas/__init__.py
# Saare schemas yahan export karein
# ============================================

from app.schemas.product import (
    ProductBase,
    ProductCreate,
    ProductFetchResponse,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
    VariantGroup,
    VariantGroupListResponse,
)
from app.schemas.admin import (
    AdminLogin,
    AdminResponse,
    Token,
    TokenData,
)

__all__ = [
    # Product schemas
    "ProductBase",
    "ProductCreate",
    "ProductFetchResponse",
    "ProductListResponse",
    "ProductResponse",
    "ProductUpdate",
    "VariantGroup",
    "VariantGroupListResponse",
    # Admin schemas
    "AdminLogin",
    "AdminResponse",
    "Token",
    "TokenData",
]