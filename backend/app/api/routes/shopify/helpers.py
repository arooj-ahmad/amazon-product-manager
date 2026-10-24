# ============================================
# app/api/routes/shopify/helpers.py
# ============================================

import logging
import re
import json
from datetime import datetime, timedelta, timezone

from app.services.amazon import extract_asin_from_url
from app.services.shopify import refresh_shopify_token
from app.services.shopify_taxonomy import find_best_category  # ✅ Naya import

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

    asin = extract_asin_from_url(url)
    if asin:
        normalized = f"https://www.amazon.com/dp/{asin}"
        if normalized != url:
            logger.info(f"🔗 URL normalized: {url[:60]}... → {normalized}")
        return normalized

    match = re.search(r"[?&]k=([A-Z0-9]{10})", url)
    if match:
        asin = match.group(1)
        normalized = f"https://www.amazon.com/dp/{asin}"
        logger.info(f"🔗 URL normalized (search): {url[:60]}... → {normalized}")
        return normalized
        
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

async def _get_valid_access_token(store, db, force_refresh: bool = False) -> str:
    now = datetime.now(timezone.utc)
    buffer = timedelta(minutes=10)

    needs_refresh = force_refresh
    if not needs_refresh and store.expires_at and store.expires_at <= now + buffer:
        needs_refresh = True

    if needs_refresh and store.refresh_token:
        logger.info(f"🔄 Refreshing token for {store.shop_domain}")
        refreshed = await refresh_shopify_token(store.shop_domain, store.refresh_token)

        if refreshed and refreshed.get("access_token"):
            store.access_token = refreshed["access_token"]
            if refreshed.get("refresh_token"):
                store.refresh_token = refreshed["refresh_token"]
            if refreshed.get("expires_in"):
                store.expires_at = now + timedelta(seconds=int(refreshed["expires_in"]))
            if refreshed.get("refresh_token_expires_in"):
                store.refresh_token_expires_at = now + timedelta(seconds=int(refreshed["refresh_token_expires_in"]))
            db.commit()
            db.refresh(store)
            logger.info(f"✅ Token refreshed for {store.shop_domain}")
        else:
            logger.error(f"❌ Token refresh failed for {store.shop_domain}")

    return store.access_token

def _build_product_data_for_shopify(data: dict, product=None) -> dict:
    base = {}

    if product:
        product_price = product.price
        if product_price is None or float(product_price or 0) <= 0:
            amazon = float(product.amazon_price or 0)
            if amazon <= 0:
                product_price = 0.0
                logger.warning("⚠️ product.price and amazon_price both 0 — setting $0.00")
            else:
                markup_val = float(product.markup or 0.0)
                markup_type = product.markup_type or "fixed"
                extra_pct = float(getattr(product, "extra_percent", 0.0) or 0.0)

                if markup_type == "percent":
                    product_price = amazon * (1 + markup_val / 100)
                elif markup_type == "both":
                    base_price = amazon + markup_val
                    product_price = base_price * (1 + extra_pct / 100)
                else:
                    product_price = amazon + markup_val
                logger.warning(f"⚠️ product.price was 0 — calculated ${product_price}")

        base = {
            "title": product.title,
            "description": product.description or "",
            "brand": product.brand or "",
            "images": product.images or ([product.image_url] if product.image_url else []),
            "price": str(product_price) if product_price else "0.00",
            "stock_quantity": product.stock_quantity or 0,
            "is_available": (product.is_available if product.is_available is not None else False),
            "availability": product.availability or "In Stock",
            "rating": product.rating,
            "reviews_count": product.reviews_count,
            "amazon_price": product.amazon_price,
            "asin": product.asin,
            "parent_asin": product.parent_asin,
            "variant_attributes": product.variant_attributes or [],
            "categories": product.categories or [],
            "tags": product.tags or [],
            "manufacturer": getattr(product, "manufacturer", None),
            "department": getattr(product, "department", None),
            "country_of_origin": getattr(product, "country_of_origin", None),
            "item_weight": getattr(product, "item_weight", None),
            "package_weight": getattr(product, "package_weight", None),
            "package_dimensions": getattr(product, "package_dimensions", None),
            "item_dimensions": getattr(product, "item_dimensions", None),
            "feature_bullets": getattr(product, "feature_bullets", []) or [],
        }
    else:
        base = {
            "title": data.get("title"),
            "description": data.get("description") or "",
            "brand": data.get("brand") or "",
            "images": data.get("images") or ([data["image_url"]] if data.get("image_url") else []),
            "price": str(data.get("price", 0) or 0),
            "stock_quantity": data.get("stock_quantity", 0) or 0,
            "is_available": data.get("is_available", False),
            "availability": data.get("availability", "In Stock"),
            "rating": data.get("rating"),
            "reviews_count": data.get("reviews_count"),
            "amazon_price": data.get("amazon_price"),
            "asin": data.get("asin"),
            "parent_asin": data.get("parent_asin"),
            "variant_attributes": data.get("variant_attributes", []),
            "categories": data.get("categories", []),
            "tags": data.get("tags", []),
            "feature_bullets": data.get("feature_bullets", []),
        }

    standard_fields = [
        "model_number", "item_model_number", "model_name",
        "part_number", "upc", "ean", "isbn",
        "manufacturer", "department", "country_of_origin",
        "item_dimensions", "item_weight", "package_dimensions", "package_weight",
        "size", "color", "material_type", "style_name", "theme",
        "date_first_available", "best_sellers_rank",
        "language", "reading_age", "unit_count", "number_of_pieces",
        "care_instructions", "closure_type", "fabric_type",
        "number_of_players", "educational_objective",
        "power_source", "battery_types", "operation_mode",
        "specific_uses", "special_features",
        "connectivity", "processor", "ram_technology", "memory",
        "screen_size", "resolution", "operating_system",
        "hard_disk", "graphics_coprocessor", "warranty",
    ]

    if data:
        for field in standard_fields:
            val = data.get(field)
            if val is not None and str(val).strip() and str(val).strip() != "None":
                base[field] = str(val).strip()

    if product:
        specs = product.specifications or {}
        if isinstance(specs, str):
            try:
                specs = json.loads(specs)
            except Exception:
                specs = {}
        if isinstance(specs, dict):
            for field in standard_fields:
                if field in base:
                    continue
                val = specs.get(field)
                if val is not None and str(val).strip() and str(val).strip() != "None":
                    base[field] = str(val).strip()

        for field in standard_fields:
            if field in base:
                continue
            val = getattr(product, field, None)
            if val is not None and str(val).strip() and str(val).strip() != "None":
                base[field] = str(val).strip()

    base["product_details"] = (data.get("product_details") if data else None) or []

    filled = [f for f in standard_fields if f in base]
    logger.info(f"   📦 product_data built: price=${base.get('price')}, {len(filled)} standard fields")

    return base

# ✅ YEH NAYA FUNCTION ADD KAREIN (Category fix karne ke liye)
async def _find_category_from_breadcrumbs(shop: str, access_token: str, categories: list, product_title: str):
    """Breadcrumb terms ko try karta hai taake exact category mile."""
    if not categories:
        return await find_best_category(
            shop=shop, access_token=access_token,
            product_title=product_title, categories=[]
        )

    terms_to_try = list(reversed(categories))

    for term in terms_to_try:
        cat_id = await find_best_category(
            shop=shop, access_token=access_token,
            product_title=term, categories=categories
        )
        if cat_id:
            logger.info(f"   ✅ Category matched via term: '{term}'")
            return cat_id

    logger.warning(f"⚠️ No category found for breadcrumbs: {categories}")
    return None