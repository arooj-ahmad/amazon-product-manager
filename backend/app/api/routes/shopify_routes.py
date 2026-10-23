# ============================================
# app/api/routes/shopify_routes.py
# Shopify OAuth + Product Push + Embedded App
# + ✅ 100% APIFY for Product Add
# + ✅ BackgroundTasks (no frontend timeout)
# + ✅ FIXED: Removed manual HTML description (handled by description.py)
# ============================================

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_admin
from app.config import settings
from app.database import get_db, SessionLocal
from app.models import Admin, Product, ShopifyStore
from app.services.brightdata import (
    ApifyError,
    calculate_final_price,
    extract_asin_from_url,
    fetch_product_from_apify,  # ✅ Sirf Apify use hoga product add ke liye
)
from app.services.shopify import (
    build_auth_url,
    create_shopify_product,
    add_variant_to_existing_product,
    add_product_to_collections,
    exchange_code_for_token,
    exchange_id_token_for_offline_token,
    verify_hmac,
    verify_id_token,
    shopify_graphql,
    refresh_shopify_token,
)
from app.services.scheduler import run_price_update_now, last_run_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/shopify", tags=["Shopify"])


# ============================================
# HELPER: Safe float parse
# ============================================
def _safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


# ============================================
# HELPER: Normalize Amazon URL
# ============================================
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

    logger.warning(f"⚠️ Could not normalize URL: {url[:80]}...")
    return url


# ============================================
# HELPER: 401 check
# ============================================
def _is_auth_error(result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    for err in result.get("errors", []) or []:
        if isinstance(err, dict) and err.get("status") in (401, 403):
            return True
    return False


# ============================================
# HELPER: Valid access token (auto-refresh)
# ============================================
async def _get_valid_access_token(
    store: ShopifyStore,
    db: Session,
    force_refresh: bool = False,
) -> str:
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


# ============================================
# HELPER: Store default markup + tax
# ============================================
def _get_store_markup(store: ShopifyStore) -> tuple:
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


# ============================================
# HELPER: Extract weight
# ============================================
def _extract_weight(source: dict) -> str:
    if not source:
        return None
    return (
        source.get("item_weight")
        or source.get("package_weight")
        or source.get("weight")
    )


# ============================================
# HELPER: Resolve markup (frontend OR store default)
# ============================================
def _resolve_markup(store: ShopifyStore, markup, markup_type, extra_percent) -> tuple:
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

    raise HTTPException(
        status_code=400,
        detail=(
            "Markup required — na frontend se diya, na store default hai. "
            "Pehle store settings mein default markup set karein, "
            "ya product add form mein markup fill karein."
        ),
    )


# ============================================
# HELPER: Build product_data
# ============================================
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
            "description": product.description or "", # ✅ Direct description
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
            # ✅ Bullets added so description.py can use them
            "feature_bullets": getattr(product, "feature_bullets", []) or [],
        }
    else:
        base = {
            "title": data.get("title"),
            "description": data.get("description") or "", # ✅ Direct description
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
            # ✅ Bullets added so description.py can use them
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
                import json
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


# ============================================
# HELPER: Extract all variations
# ============================================
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


# ============================================
# HELPER: Check if variant exists
# ============================================
async def check_variant_exists_in_shopify(
    shop: str,
    access_token: str,
    shopify_product_id: str,
    variation_values: list,
) -> bool:
    try:
        query = """
        query getProductVariants($id: ID!) {
          product(id: $id) {
            variants(first: 100) {
              edges {
                node {
                  title
                  selectedOptions { name value }
                }
              }
            }
          }
        }
        """
        result = await shopify_graphql(shop, access_token, query, {"id": shopify_product_id})

        if "errors" in result:
            logger.warning(f"⚠️ Failed to fetch variants: {result['errors']}")
            return False

        edges = result.get("data", {}).get("product", {}).get("variants", {}).get("edges", [])
        new_values = {v["name"].lower(): v["value"].lower().strip() for v in variation_values}

        for edge in edges:
            node = edge["node"]
            existing_values = {opt["name"].lower(): opt["value"].lower().strip() for opt in node.get("selectedOptions", [])}
            if existing_values == new_values:
                return True

        return False
    except Exception as e:
        logger.error(f"❌ check_variant_exists error: {e}")
        return False


# ============================================
# HELPER: Smart markup cap
# ============================================
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


# ============================================
# HELPER: Verify parent match
# ============================================
def _verify_parent_match(existing_parent: Product, new_data: dict) -> bool:
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


# ============================================
# INSTALL
# ============================================
@router.get("/install")
def shopify_install(shop: str = Query(..., description="Shopify store domain")):
    if not shop:
        raise HTTPException(status_code=400, detail="Shop parameter required")
    auth_url = build_auth_url(shop)
    return RedirectResponse(url=auth_url)


# ============================================
# CALLBACK (OAuth)
# ============================================
@router.get("/callback")
async def shopify_callback(
    request: Request,
    shop: str = Query(...),
    code: str = Query(...),
    state: str = Query(None),
    hmac: str = Query(None),
    db: Session = Depends(get_db),
):
    query_params = dict(request.query_params)
    if not hmac or not verify_hmac(query_params):
        raise HTTPException(status_code=401, detail="HMAC verification failed")

    token_data = await exchange_code_for_token(shop, code)
    if not token_data or not token_data.get("access_token"):
        return HTMLResponse(content="<h1>❌ Installation Failed</h1>", status_code=400)

    access_token = token_data["access_token"]
    now = datetime.now(timezone.utc)
    
    expires_in = token_data.get("expires_in")
    refresh_expires_in = token_data.get("refresh_token_expires_in")
    expires_at = now + timedelta(seconds=int(expires_in)) if expires_in else None
    refresh_token_expires_at = now + timedelta(seconds=int(refresh_expires_in)) if refresh_expires_in else None

    existing = db.query(ShopifyStore).filter(ShopifyStore.shop_domain == shop).first()
    if existing:
        existing.access_token = access_token
        existing.refresh_token = token_data.get("refresh_token")
        existing.expires_at = expires_at
        existing.refresh_token_expires_at = refresh_token_expires_at
        existing.scopes = settings.SHOPIFY_SCOPES
    else:
        new_store = ShopifyStore(
            shop_domain=shop,
            access_token=access_token,
            refresh_token=token_data.get("refresh_token"),
            expires_at=expires_at,
            refresh_token_expires_at=refresh_token_expires_at,
            scopes=settings.SHOPIFY_SCOPES,
        )
        db.add(new_store)

    db.commit()
    return HTMLResponse(content="<h1>✅ App Installed! You can close this window.</h1>")


# ============================================
# STORES & COLLECTIONS
# ============================================
@router.get("/stores")
def list_installed_stores(db: Session = Depends(get_db)):
    stores = db.query(ShopifyStore).all()
    return {"total": len(stores), "stores": [{"shop_domain": s.shop_domain, "installed_at": s.installed_at, "scopes": s.scopes} for s in stores]}

@router.get("/store-id")
def get_store_id_by_domain(shop: str = Query(...), db: Session = Depends(get_db)):
    store = db.query(ShopifyStore).filter(ShopifyStore.shop_domain == shop).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return {"store_id": store.id, "shop_domain": store.shop_domain}

@router.get("/collections")
async def get_shopify_collections(shop_domain: str = Query(...), db: Session = Depends(get_db)):
    store = db.query(ShopifyStore).filter(ShopifyStore.shop_domain == shop_domain).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not connected")

    query = """
    query getCollections($first: Int!) {
      collections(first: $first) {
        edges { node { id title handle productsCount { count } } }
      }
    }
    """
    access_token = await _get_valid_access_token(store, db)
    result = await shopify_graphql(shop_domain, access_token, query, {"first": 250})

    if _is_auth_error(result):
        access_token = await _get_valid_access_token(store, db, force_refresh=True)
        result = await shopify_graphql(shop_domain, access_token, query, {"first": 250})

    if "errors" in result:
        raise HTTPException(status_code=400, detail="Failed to fetch collections")

    edges = result.get("data", {}).get("collections", {}).get("edges", [])
    collections = [{"id": n.get("node", {}).get("id"), "title": n.get("node", {}).get("title"), "handle": n.get("node", {}).get("handle"), "products_count": (n.get("node", {}).get("productsCount") or {}).get("count", 0)} for n in edges]

    return {"success": True, "total": len(collections), "collections": collections}


# ============================================
# CRON TRIGGER
# ============================================
@router.post("/trigger-price-update-async")
async def trigger_price_update_async(authorization: str = Header(...), db: Session = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization")

    token = authorization.replace("Bearer ", "").strip()
    try:
        payload = verify_id_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid ID token: {str(e)}")

    shop_domain = payload.get("dest", "").replace("https://", "").split("/")[0]
    if not shop_domain:
        raise HTTPException(status_code=401, detail="Shop domain missing")

    if last_run_status.get("running"):
        return {"success": True, "message": "Price update already running"}

    asyncio.create_task(run_price_update_now())
    return {"success": True, "message": "Price update started in background"}


@router.get("/price-update-status")
async def get_price_update_status():
    return {"success": True, "running": last_run_status.get("running", False), "summary": last_run_status.get("summary")}


# ============================================
# PUSH PRODUCT TO SHOPIFY (Manual Admin Push)
# ============================================
@router.post("/push-product/{product_id}")
async def push_product_to_shopify(
    product_id: int,
    shop_domain: str = Body(..., embed=True),
    collection_ids: list = Body(default=[], embed=True),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    store = db.query(ShopifyStore).filter(ShopifyStore.shop_domain == shop_domain).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not connected")

    product.shopify_store_id = store.id
    product.shopify_status = "active"

    existing_parent = None
    if product.parent_asin:
        existing_parent = db.query(Product).filter(
            Product.parent_asin == product.parent_asin,
            Product.id != product.id,
            Product.shopify_product_id.isnot(None),
        ).first()

        if existing_parent and not _verify_parent_match(existing_parent, {"categories": product.categories or [], "brand": product.brand or ""}):
            existing_parent = None

    all_variations = extract_all_variations({"variant_attributes": product.variant_attributes or [], "specifications": product.specifications or {}})
    access_token = await _get_valid_access_token(store, db)

    if existing_parent and existing_parent.shopify_product_id:
        variant_exists = await check_variant_exists_in_shopify(
            shop=store.shop_domain, access_token=access_token,
            shopify_product_id=existing_parent.shopify_product_id, variation_values=all_variations,
        )
        if variant_exists:
            existing_parent = None

    if existing_parent and existing_parent.shopify_product_id:
        _temp_product_data = _build_product_data_for_shopify(data={}, product=product)
        _weight = _extract_weight(_temp_product_data)

        result = await add_variant_to_existing_product(
            shop=store.shop_domain, access_token=access_token,
            product_id=existing_parent.shopify_product_id,
            variant_data={"price": product.price, "sku": product.asin, "stock": product.stock_quantity or 0, "weight": _weight},
            all_options=all_variations,
        )

        if "errors" not in result:
            product.shopify_product_id = existing_parent.shopify_product_id
            product.shopify_handle = existing_parent.shopify_handle
            db.commit()
            if collection_ids:
                await add_product_to_collections(shop=store.shop_domain, access_token=access_token, product_id=existing_parent.shopify_product_id, collection_ids=collection_ids)
            return {"success": True, "message": "Variant added", "shopify_product_id": existing_parent.shopify_product_id}

    product_data = _build_product_data_for_shopify(data={}, product=product)
    result = await create_shopify_product(shop=store.shop_domain, access_token=access_token, product_data=product_data)

    if "errors" in result:
        raise HTTPException(status_code=400, detail="Shopify API error")

    shopify_product = result.get("data", {}).get("productSet", {}).get("product", {})
    new_pid = shopify_product.get("id")

    product.shopify_product_id = new_pid
    product.shopify_handle = shopify_product.get("handle")
    db.commit()

    if new_pid and collection_ids:
        await add_product_to_collections(shop=store.shop_domain, access_token=access_token, product_id=new_pid, collection_ids=collection_ids)

    return {"success": True, "message": "Product pushed to Shopify", "shopify_product_id": new_pid, "variant_added": False}


# ============================================
# ✅ Background worker (100% APIFY)
# ============================================
async def _background_fetch_and_push(
    amazon_url: str,
    shop_domain: str,
    store_id: int,
    markup,
    markup_type,
    extra_percent,
    collection_ids: list,
):
    db = SessionLocal()
    try:
        logger.info(f"🔄 Background job START (Apify Only): {amazon_url}")

        store = db.query(ShopifyStore).filter(ShopifyStore.id == store_id).first()
        if not store:
            logger.error(f"❌ Background: Store {store_id} not found")
            return

        # ── 1. APIFY FETCH ──
        loop = asyncio.get_running_loop()
        try:
            data = await loop.run_in_executor(None, fetch_product_from_apify, amazon_url)
        except ApifyError as e:
            logger.error(f"❌ Background: Apify fail: {e}")
            return

        if not data or not data.get("asin"):
            logger.error("❌ Background: ASIN missing in Apify response")
            return

        asin = data["asin"]
        parent_asin = data.get("parent_asin")

        existing = db.query(Product).filter(Product.asin == asin).first()
        if existing:
            logger.warning(f"⚠️ Background: ASIN {asin} already exists")
            return

        existing_parent = None
        if parent_asin:
            existing_parent = db.query(Product).filter(
                Product.parent_asin == parent_asin,
                Product.asin != asin,
                Product.shopify_product_id.isnot(None),
            ).first()
            if existing_parent and not _verify_parent_match(existing_parent, data):
                existing_parent = None

        all_variations = extract_all_variations(data)
        access_token = await _get_valid_access_token(store, db)

        if existing_parent and existing_parent.shopify_product_id:
            variant_exists = await check_variant_exists_in_shopify(
                shop=shop_domain, access_token=access_token,
                shopify_product_id=existing_parent.shopify_product_id, variation_values=all_variations,
            )
            if variant_exists:
                logger.warning("⚠️ Background: Variant exists — new product")
                existing_parent = None

        # ── 2. Markup Resolve ──
        try:
            (user_markup, user_markup_type, user_extra, user_tax_rate) = _resolve_markup(store, markup, markup_type, extra_percent)
        except HTTPException as e:
            logger.error(f"❌ Background: markup resolve fail: {e.detail}")
            return

        user_markup = apply_markup_cap(user_markup, user_markup_type)

        final_price = calculate_final_price(
            amazon_price=data.get("amazon_price"),
            markup=user_markup,
            markup_type=user_markup_type,
            extra_percent=user_extra,
            tax_rate=user_tax_rate,
        )

        weight_str = _extract_weight(data)

        # ── 3. DB Save ──
        new_product = Product(
            asin=asin,
            parent_asin=parent_asin,
            is_variation=data.get("is_variation", False),
            title=data.get("title"),
            brand=data.get("brand"),
            description=data.get("description") or "",
            image_url=data.get("image_url"),
            images=data.get("images", []),
            specifications=data.get("specifications", {}),
            rating=data.get("rating"),
            reviews_count=data.get("reviews_count"),
            availability=data.get("availability", "In Stock"),
            is_available=data.get("is_available", False),
            stock_quantity=data.get("stock_quantity", 0),
            amazon_price=data.get("amazon_price"),
            price=final_price,
            markup=user_markup,
            markup_type=user_markup_type,
            extra_percent=user_extra,
            tax_rate=user_tax_rate,
            is_manual_override=False,
            variant_attributes=data.get("variant_attributes", []),
            categories=data.get("categories", []),
            tags=data.get("tags", []),
            # ✅ BULLETS SAVE KAREIN
            feature_bullets=data.get("feature_bullets", []),
            shopify_store_id=store.id,
            shopify_status="active",
        )
        db.add(new_product)
        db.commit()
        db.refresh(new_product)

        # ── 4. Shopify Push ──
        shopify_pushed = False
        variant_added = False
        shopify_product_id = None
        collections_added = 0

        try:
            if existing_parent and existing_parent.shopify_product_id:
                result = await add_variant_to_existing_product(
                    shop=shop_domain, access_token=access_token,
                    product_id=existing_parent.shopify_product_id,
                    variant_data={"price": final_price, "sku": asin, "stock": new_product.stock_quantity or 0, "weight": weight_str},
                    all_options=all_variations,
                )
                
                if _is_auth_error(result):
                    access_token = await _get_valid_access_token(store, db, force_refresh=True)
                    result = await add_variant_to_existing_product(
                        shop=shop_domain, access_token=access_token,
                        product_id=existing_parent.shopify_product_id,
                        variant_data={"price": final_price, "sku": asin, "stock": new_product.stock_quantity or 0, "weight": weight_str},
                        all_options=all_variations,
                    )

                if "errors" not in result:
                    variant_added = True
                    shopify_pushed = True
                    shopify_product_id = existing_parent.shopify_product_id
                    new_product.shopify_product_id = shopify_product_id
                    new_product.shopify_handle = existing_parent.shopify_handle
                    db.commit()
            else:
                product_data = _build_product_data_for_shopify(data=data, product=new_product)
                result = await create_shopify_product(
                    shop=shop_domain, access_token=access_token, product_data=product_data,
                )
                
                if _is_auth_error(result):
                    access_token = await _get_valid_access_token(store, db, force_refresh=True)
                    result = await create_shopify_product(
                        shop=shop_domain, access_token=access_token, product_data=product_data,
                    )

                if "errors" not in result:
                    shopify_pushed = True
                    shopify_product_id = result.get("data", {}).get("productSet", {}).get("product", {}).get("id")
                    if shopify_product_id:
                        new_product.shopify_product_id = shopify_product_id
                        new_product.shopify_handle = result.get("data", {}).get("productSet", {}).get("product", {}).get("handle")
                        db.commit()

            if shopify_pushed and shopify_product_id and collection_ids:
                ok = await add_product_to_collections(
                    shop=shop_domain, access_token=access_token,
                    product_id=shopify_product_id, collection_ids=collection_ids,
                )
                if ok: collections_added = len(collection_ids)

        except Exception as e:
            logger.error(f"❌ Background: Shopify push fail: {e}")

        logger.info(f"🏁 Background DONE: ASIN={asin}, pushed={shopify_pushed}")

    except Exception as e:
        logger.exception(f"❌ Background job crashed: {e}")
    finally:
        db.close()


# ============================================
# ✅ ADD PRODUCT (BackgroundTasks)
# ============================================
@router.post("/app/add-product")
async def add_product_from_shopify_app(
    background_tasks: BackgroundTasks,
    amazon_url: str = Body(..., embed=True),
    markup: float = Body(None, embed=True),
    markup_type: str = Body(None, embed=True),
    extra_percent: float = Body(None, embed=True),
    collection_ids: list = Body(default=[], embed=True),
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization")

    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty ID token")

    amazon_url = _normalize_amazon_url(amazon_url)
    
    try:
        payload = verify_id_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid ID token: {str(e)}")

    shop_domain = payload.get("dest", "").replace("https://", "").split("/")[0]
    if not shop_domain:
        raise HTTPException(status_code=401, detail="Shop domain missing")

    store = db.query(ShopifyStore).filter(ShopifyStore.shop_domain == shop_domain).first()

    async def refresh_store_token() -> bool:
        nonlocal store
        token_data = await exchange_id_token_for_offline_token(shop_domain, token)
        if not token_data or not token_data.get("access_token"): return False

        now = datetime.now(timezone.utc)
        expires_in = token_data.get("expires_in")
        refresh_expires_in = token_data.get("refresh_token_expires_in")

        expires_at = now + timedelta(seconds=int(expires_in)) if expires_in else None
        refresh_token_expires_at = now + timedelta(seconds=int(refresh_expires_in)) if refresh_expires_in else None

        if store:
            store.access_token = token_data["access_token"]
            store.refresh_token = token_data.get("refresh_token")
            store.expires_at = expires_at
            store.refresh_token_expires_at = refresh_token_expires_at
            store.scopes = token_data.get("scope") or settings.SHOPIFY_SCOPES
        else:
            store = ShopifyStore(
                shop_domain=shop_domain, access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"), expires_at=expires_at,
                refresh_token_expires_at=refresh_token_expires_at, scopes=token_data.get("scope") or settings.SHOPIFY_SCOPES,
            )
            db.add(store)

        db.commit()
        db.refresh(store)
        return True

    refreshed_ok = await refresh_store_token()

    if not refreshed_ok:
        if not store:
            raise HTTPException(status_code=404, detail="Store not connected")
        if not store.access_token:
            raise HTTPException(status_code=401, detail="Token exchange failed and no existing token.")

    asin_quick = extract_asin_from_url(amazon_url)
    if asin_quick:
        if db.query(Product).filter(Product.asin == asin_quick).first():
            raise HTTPException(status_code=409, detail=f"Product already exists (ASIN: {asin_quick})")

    _resolve_markup(store, markup, markup_type, extra_percent)

    try:
        background_tasks.add_task(
            _background_fetch_and_push,
            amazon_url=amazon_url,
            shop_domain=shop_domain,
            store_id=store.id,
            markup=markup,
            markup_type=markup_type,
            extra_percent=extra_percent,
            collection_ids=collection_ids or [],
        )
    except Exception as e:
        logger.exception(f"❌ Failed to enqueue background task: {e}")
        raise HTTPException(status_code=500, detail="Failed to enqueue background job")

    return {
        "success": True,
        "message": "Product fetch and push started in background (Apify). Refresh in 30 seconds.",
        "asin": asin_quick,
        "shop_domain": shop_domain,
        "background": True,
    }


# ============================================
# HEALTH CHECK
# ============================================
@router.get("/health")
def shopify_health():
    return {"status": "ok", "service": "shopify-integration"}