import logging
import re
from typing import Optional
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models import ShopifyStore
from app.services.shopify.taxonomy import find_best_category

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

def _parse_weight(weight_str) -> tuple:
    if not weight_str: return None, None
    s = str(weight_str).strip().lower()
    if not s or s == "none": return None, None
    match = re.search(r"([\d.]+)", s)
    if not match: return None, None
    try: value = float(match.group(1))
    except ValueError: return None, None
    if "kg" in s or "kilogram" in s: value = value * 2.20462
    elif "gram" in s or " g" in s or s.endswith("g"): value = value * 0.00220462
    elif "ounce" in s or " oz" in s or s.endswith("oz"): value = value * 0.0625
    elif "milligram" in s or " mg" in s: value = value * 0.00000220462
    return round(value, 4), "POUNDS"

def _build_inventory_item(product_data: dict, sku: str) -> dict:
    inventory_item = {"sku": sku, "tracked": True}
    weight_str = product_data.get("item_weight") or product_data.get("package_weight") or product_data.get("shipping_weight")
    weight_value, weight_unit = _parse_weight(weight_str)
    if weight_value and weight_value > 0:
        inventory_item["measurement"] = {"weight": {"value": weight_value, "unit": weight_unit}}
    return inventory_item

async def _find_category_from_breadcrumbs(shop: str, access_token: str, categories: list, product_title: str, tags: list = None) -> Optional[str]:
    if categories:
        cat_id = await find_best_category(shop=shop, access_token=access_token, product_title=product_title, categories=categories)
        if cat_id: return cat_id
    if tags:
        for tag in tags:
            if not isinstance(tag, str) or not tag.strip(): continue
            cat_id = await find_best_category(shop=shop, access_token=access_token, product_title=tag, categories=[])
            if cat_id: return cat_id
    return None
