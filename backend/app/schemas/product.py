# ============================================
# app/schemas/product.py
# Product ke liye Pydantic schemas
# ============================================

from datetime import datetime
from typing import Dict, List, Optional

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
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================
# CREATE SCHEMA
# ============================================
class ProductCreate(BaseModel):
    amazon_url: str = Field(..., description="Amazon product URL")


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


# ============================================
# ADMIN FETCH RESPONSE
# ============================================
class ProductFetchResponse(BaseModel):
    success: bool
    message: str
    product: Optional[ProductResponse] = None


# ============================================
# LIST RESPONSE (Purana — simple list)
# ============================================
class ProductListResponse(BaseModel):
    total: int
    products: list[ProductResponse]


# ============================================
# VARIANT GROUP (NEW)
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