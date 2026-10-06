from pydantic import BaseModel
from typing import Optional


class SinglePricingUpdate(BaseModel):
    product_id: str  # ya int — aapke product ID ke type ke hisaab se
    country_id: int
    markup_type: str = "fixed"
    markup_value: float = 2.00
    tax_rate: Optional[float] = None


class BulkPricingUpdate(BaseModel):
    country_id: int
    markup_type: str = "fixed"
    markup_value: float = 2.00
    tax_rate: Optional[float] = None