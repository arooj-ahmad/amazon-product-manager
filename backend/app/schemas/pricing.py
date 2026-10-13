# ============================================
# app/schemas/pricing.py
# Pricing schemas — Pydantic models
# + ✅ NAYA: extra_percent (Fixed + Percent) support
# ============================================

from pydantic import BaseModel
from typing import Optional


class SinglePricingUpdate(BaseModel):
    product_id: int
    country_id: int
    markup_type: str = "fixed"
    markup_value: float = 2.00
    tax_rate: Optional[float] = 0
    extra_percent: Optional[float] = 0.0   # ✅ NAYA


class BulkPricingUpdate(BaseModel):
    store_id: Optional[int] = None          # ✅ NAYA (frontend bhej raha hai)
    country_id: int
    markup_type: str = "fixed"
    markup_value: float = 2.00
    tax_rate: Optional[float] = 0
    extra_percent: Optional[float] = 0.0   # ✅ NAYA