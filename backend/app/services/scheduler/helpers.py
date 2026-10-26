# ============================================
# app/services/scheduler/helpers.py
# ============================================

import logging
from sqlalchemy.orm import Session
from app.models import Product, ShopifyStore

logger = logging.getLogger(__name__)

def get_store_for_product(db: Session, product: Product, fallback_store_id: int = None) -> ShopifyStore:
    store = None
    if product and product.shopify_store_id:
        store = db.query(ShopifyStore).filter(ShopifyStore.id == product.shopify_store_id).first()
    if not store and fallback_store_id:
        store = db.query(ShopifyStore).filter(ShopifyStore.id == fallback_store_id).first()
    if not store:
        store = db.query(ShopifyStore).first()
    return store

def get_store_default_markup(store: ShopifyStore) -> tuple:
    if not store:
        return None, None, 0.0, 0.0

    markup_val = getattr(store, "default_markup", None)
    markup_type = getattr(store, "default_markup_type", None)
    extra_pct = float(getattr(store, "default_extra_percent", None) or 0.0)
    tax_rate = float(getattr(store, "default_tax_rate", None) or 0.0)

    if markup_val is not None:
        markup_val = float(markup_val)
    if markup_type is not None and markup_type not in ("fixed", "percent", "both"):
        markup_type = "fixed"

    return markup_val, markup_type, extra_pct, tax_rate

def apply_markup_cap(markup: float, markup_type: str) -> float:
    try:
        markup = float(markup)
    except (ValueError, TypeError):
        return 0.0

    if markup < 0:
        markup = 0.0

    if markup_type == "fixed":
        if markup > 50:
            logger.warning(f"⚠️ Fixed markup ${markup} capped at $50")
            markup = 50.0
    elif markup_type == "percent":
        if markup > 500:
            logger.warning(f"⚠️ Percent markup {markup}% capped at 500%")
            markup = 500.0
    elif markup_type == "both":
        if markup > 50:
            logger.warning(f"⚠️ Fixed part ${markup} capped at $50")
            markup = 50.0

    return markup

def calculate_compare_at_price(store: ShopifyStore, final_price: float, amazon_price: float) -> float | None:
    if not store or not final_price or final_price <= 0:
        return None

    rule = getattr(store, "default_compare_at_rule", None)
    if not rule:
        enabled = bool(getattr(store, "default_compare_at_enabled", False))
        if not enabled:
            rule = "none"
        else:
            old_type = getattr(store, "default_compare_at_type", None) or "percent"
            if old_type == "amazon":
                rule = "amazon"
            elif old_type == "fixed":
                rule = "fixed"
            else:
                rule = "percent"

    if rule == "none":
        return None

    compare_value = float(getattr(store, "default_compare_at_value", None) or 0.0)

    if rule == "amazon":
        if amazon_price and amazon_price > final_price:
            return round(float(amazon_price), 2)
        return None

    if compare_value <= 0:
        return None

    try:
        if rule == "percent":
            compare_price = final_price * (1 + compare_value / 100)
        elif rule == "fixed":
            compare_price = final_price + compare_value
        else:
            return None

        compare_price = round(compare_price, 2)
        return compare_price if compare_price > final_price else None
    except (ValueError, TypeError):
        return None