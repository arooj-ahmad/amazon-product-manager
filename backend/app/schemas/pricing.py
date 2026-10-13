# ============================================
# app/schemas/pricing.py
# Pricing schemas — Pydantic models
# + ✅ NAYA: extra_percent (Fixed + Percent) support
# + ✅ FIXED: markup_value default 0.00 (user khud set karega)
# ============================================

from pydantic import BaseModel
from typing import Optional, Literal


# ============================================
# SINGLE PRICING UPDATE
# ============================================
class SinglePricingUpdate(BaseModel):
    product_id: int
    country_id: int

    # ✅ FIXED: Default 0.00 — user khud set karega
    markup_type: Literal["fixed", "percent", "both"] = "fixed"
    markup_value: float = 0.00
    tax_rate: Optional[float] = 0
    extra_percent: Optional[float] = 0.0


# ============================================
# BULK PRICING UPDATE
# ============================================
class BulkPricingUpdate(BaseModel):
    store_id: Optional[int] = None
    country_id: int

    # ✅ FIXED: Default 0.00 — user khud set karega
    markup_type: Literal["fixed", "percent", "both"] = "fixed"
    markup_value: float = 0.00
    tax_rate: Optional[float] = 0
    extra_percent: Optional[float] = 0.0