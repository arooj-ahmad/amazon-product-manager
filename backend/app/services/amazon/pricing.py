# ============================================
# app/services/amazon/pricing.py
# ============================================

from typing import Optional

def calculate_final_price(
    amazon_price: Optional[float],
    markup: Optional[float] = None,
    markup_type: Optional[str] = None,
    admin_price: Optional[float] = None,
    is_manual_override: bool = False,
    extra_percent: float = 0.0,
    tax_rate: float = 0.0,
) -> Optional[float]:
    if amazon_price is None:
        return admin_price
    if markup is None or markup_type is None:
        return admin_price

    markup = markup or 0.0
    extra_percent = extra_percent or 0.0
    tax_rate = tax_rate or 0.0

    if markup_type == "percent":
        base_price = amazon_price + (amazon_price * (markup / 100.0))
    elif markup_type == "both":
        base_price = (amazon_price + markup) * (1 + extra_percent / 100.0)
    else:
        base_price = amazon_price + markup

    final_price = base_price + (base_price * (tax_rate / 100.0))

    if is_manual_override and admin_price is not None:
        return max(admin_price, final_price)

    return round(final_price, 2)