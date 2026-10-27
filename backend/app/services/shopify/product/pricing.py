import logging
from typing import Optional
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models import ShopifyStore

logger = logging.getLogger(__name__)

def calculate_compare_at_price(final_price: float, compare_at_type: str, compare_at_value: float, amazon_price: float = None) -> Optional[float]:
    if compare_at_type == "none": return None
    if compare_at_type == "amazon":
        if amazon_price is None: return None
        compare_price = round(float(amazon_price), 2)
        return compare_price if compare_price > final_price else None
    if not final_price or final_price <= 0 or not compare_at_value or compare_at_value <= 0: return None
    try:
        if compare_at_type == "percent": compare_price = final_price * (1 + compare_at_value / 100)
        elif compare_at_type == "fixed": compare_price = final_price + compare_at_value
        else: return None
        compare_price = round(compare_price, 2)
        return compare_price if compare_price > final_price else None
    except (ValueError, TypeError): return None

def _get_compare_at_settings_from_store(shop: str) -> tuple:
    db: Session = SessionLocal()
    try:
        store = db.query(ShopifyStore).filter(ShopifyStore.shop_domain == shop).first()
        if not store: return False, "none", 0.0
        rule = getattr(store, "default_compare_at_rule", None)
        if not rule:
            enabled_old = bool(getattr(store, "default_compare_at_enabled", False))
            type_old = (getattr(store, "default_compare_at_type", None) or "percent")
            if not enabled_old: rule = "none"
            elif type_old == "amazon": rule = "amazon"
            elif type_old == "fixed": rule = "fixed"
            else: rule = "percent"
        compare_value = float(getattr(store, "default_compare_at_value", None) or 0.0)
        return (rule != "none"), rule, compare_value
    except Exception: return False, "none", 0.0
    finally: db.close()
