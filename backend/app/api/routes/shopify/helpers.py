# ============================================
# app/api/routes/shopify/helpers.py
# ============================================

import logging
import re
from app.services.amazon import extract_asin_from_url

logger = logging.getLogger(__name__)

def _safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (ValueError, TypeError):
        return default

def _normalize_amazon_url(url: str) -> str:
    if not url or not isinstance(url, str):
        return url

    url = url.strip()
    if not url:
        return url

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    if "amazon." in url and "www.amazon." not in url:
        url = url.replace("amazon.", "www.amazon.", 1)

    # 1. Standard extract_asin_from_url try karein
    asin = extract_asin_from_url(url)
    if asin:
        normalized = f"https://www.amazon.com/dp/{asin}"
        if normalized != url:
            logger.info(f"🔗 URL normalized: {url[:60]}... → {normalized}")
        return normalized

    # 2. Search URL se ASIN nikalne ki koshish karein
    match = re.search(r"[?&]k=([A-Z0-9]{10})", url)
    if match:
        asin = match.group(1)
        normalized = f"https://www.amazon.com/dp/{asin}"
        logger.info(f"🔗 URL normalized (search): {url[:60]}... → {normalized}")
        return normalized
        
    # 3. Agar ASIN direct URL mein kahin aur ho
    match = re.search(r"/([A-Z0-9]{10})(?:[/?]|$)", url)
    if match:
        asin = match.group(1)
        if len(asin) == 10 and asin.isalnum():
            normalized = f"https://www.amazon.com/dp/{asin}"
            logger.info(f"🔗 URL normalized (raw ASIN): {url[:60]}... → {normalized}")
            return normalized

    logger.warning(f"⚠️ Could not normalize URL: {url[:80]}...")
    return url

def apply_markup_cap(markup: float, markup_type: str) -> float:
    try:
        markup = float(markup)
    except (ValueError, TypeError):
        return 0.0

    if markup < 0:
        markup = 0.0

    if markup_type == "fixed":
        if markup > 50: markup = 50.0
    elif markup_type == "percent":
        if markup > 500: markup = 500.0
    elif markup_type == "both":
        if markup > 50: markup = 50.0
    else:
        markup = min(markup, 50.0)

    return markup

def _get_store_markup(store) -> tuple:
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

def _resolve_markup(store, markup, markup_type, extra_percent) -> tuple:
    store_markup, store_markup_type, store_extra, store_tax = _get_store_markup(store)

    fe_markup = _safe_float(markup)
    if fe_markup is not None and fe_markup > 0:
        user_markup = fe_markup
        user_markup_type = markup_type if markup_type in ("fixed", "percent", "both") else "fixed"
        user_extra = _safe_float(extra_percent, 0.0) or 0.0
        return user_markup, user_markup_type, user_extra, store_tax

    if store_markup is not None and store_markup_type is not None:
        logger.info(f"💰 Using store default markup: {store_markup} ({store_markup_type})")
        return store_markup, store_markup_type, store_extra, store_tax

    raise ValueError(
        "Markup required — na frontend se diya, na store default hai. "
        "Pehle store settings mein default markup set karein, "
        "ya product add form mein markup fill karein."
    )

def _extract_weight(source: dict) -> str:
    if not source:
        return None
    return (
        source.get("item_weight")
        or source.get("package_weight")
        or source.get("weight")
    )

def extract_all_variations(data: dict) -> list:
    attrs = data.get("variant_attributes") or []

    variations = []
    seen_names = set()
    priority_order = ["color", "size", "style", "capacity"]

    for target in priority_order:
        for attr in attrs:
            if not isinstance(attr, dict):
                continue
            name = (attr.get("name") or "").strip()
            value = (attr.get("value") or "").strip()

            if name.lower() == target and value:
                variations.append({"name": name, "value": value})
                seen_names.add(name.lower())
                break

    if not variations:
        for attr in attrs:
            if isinstance(attr, dict):
                name = (attr.get("name") or "").strip()
                value = (attr.get("value") or "").strip()
                if name and value and name.lower() not in seen_names:
                    variations.append({"name": name, "value": value})
                    break

    if not variations:
        variations = [{"name": "Style", "value": "Default"}]

    return variations

def _verify_parent_match(existing_parent, new_data: dict) -> bool:
    if not existing_parent:
        return False

    existing_cats = set(existing_parent.categories or [])
    new_cats = set(new_data.get("categories") or [])

    if existing_cats and new_cats:
        if not (existing_cats & new_cats):
            logger.warning("⚠️ Parent ASIN matched but categories differ")
            return False

    existing_brand = (existing_parent.brand or "").strip().lower()
    new_brand = (new_data.get("brand") or "").strip().lower()

    if existing_brand and new_brand:
        if existing_brand != new_brand:
            logger.warning("⚠️ Parent ASIN matched but brands differ")
            return False

    return True