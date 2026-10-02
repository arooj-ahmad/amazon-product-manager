# ============================================
# app/schemas/product.py
# Product ke liye Pydantic schemas
# + Out of Stock tracking (NEW)
# ============================================

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================
# BASE SCHEMA
# ============================================
class ProductBase(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    brand: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    image_url: Optional[str] = Field(None, max_length=1000)
    amazon_price: Optional[float] = Field(None, ge=0)
    price: Optional[float] = Field(None, ge=0)
    markup: float = Field(default=2.0, ge=0)
    markup_type: str = Field(default="fixed", description="'fixed' or 'percent'")

    # ✅ NAYA — Stock Tracking
    availability: Optional[str] = "In Stock"
    is_available: bool = True
    stock_quantity: int = 0


# ============================================
# RESPONSE SCHEMA
# ============================================
class ProductResponse(ProductBase):
    id: int
    asin: str
    parent_asin: Optional[str] = None
    is_variation: bool
    is_manual_override: bool
    images: List[str] = []
    specifications: Dict[str, str] = {}
    rating: Optional[float] = None
    reviews_count: Optional[int] = None

    # ✅ NAYA — Stock Tracking
    last_synced_at: Optional[datetime] = None

    # ✅ NAYA — Shopify fields
    shopify_product_id: Optional[str] = None
    shopify_handle: Optional[str] = None

    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================
# CREATE SCHEMA
# ============================================
class ProductCreate(BaseModel):
    amazon_url: str = Field(..., description="Amazon product URL")
    markup: Optional[float] = Field(
        2.0, ge=0, description="Markup value (dollar or percent)"
    )
    markup_type: Optional[Literal["fixed", "percent"]] = Field(
        "fixed", description="'fixed' = dollars, 'percent' = percentage"
    )


# ============================================
# UPDATE SCHEMA
# ============================================
class ProductUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    brand: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    image_url: Optional[str] = Field(None, max_length=1000)
    images: Optional[List[str]] = None
    specifications: Optional[Dict[str, str]] = None
    price: Optional[float] = Field(None, ge=0)
    markup: Optional[float] = Field(None, ge=0)
    markup_type: Optional[Literal["fixed", "percent"]] = None

    # ✅ NAYA — Stock Tracking (admin manually bhi change kar sakta hai)
    availability: Optional[str] = None
    is_available: Optional[bool] = None
    stock_quantity: Optional[int] = None


# ============================================
# MARKUP UPDATE SCHEMA (Settings page ke liye)
# ============================================
class MarkupUpdate(BaseModel):
    markup: float = Field(..., ge=0, description="Markup value")
    markup_type: Literal["fixed", "percent"] = Field(
        "fixed", description="'fixed' or 'percent'"
    )


# ============================================
# ADMIN FETCH RESPONSE
# ============================================
class ProductFetchResponse(BaseModel):
    success: bool
    message: str
    product: Optional[ProductResponse] = None


# ============================================
# LIST RESPONSE (Simple list)
# ============================================
class ProductListResponse(BaseModel):
    total: int
    products: list[ProductResponse]


# ============================================
# VARIANT GROUP
# ============================================
class VariantGroup(BaseModel):
    """Ek product group — parent + uske saare variants"""
    parent_product: ProductResponse
    variants: List[ProductResponse]
    total_variants: int


class VariantGroupListResponse(BaseModel):
    """Home page ke liye — groups ki list"""
    total: int
    groups: List[VariantGroup]