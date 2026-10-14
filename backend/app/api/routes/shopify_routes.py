# ============================================
# app/api/routes/shopify_routes.py
# Shopify OAuth + Product Push + Embedded App
# + ✅ FIXED: refresh_store_token HAR BAAR call hota hai
# + ✅ FIXED: expires_at = calculate (Shopify ab expiring mandatory)
# + ✅ FIXED: exchange_code_for_token dict return karta hai
# + ✅ FIXED: /callback bhi expiring token handle kare
# + ✅ NAYA: categories + tags Shopify pe push
# + ✅ NAYA: Smart markup cap (max $50 fixed, max 500% percent)
# + ✅ NAYA: Multiple variants support (Color + Size)
# + ✅ NAYA: App uninstalled cleanup (subscription_staus)
# + ✅ NAYA: All standard metafields passed to shopify_product
# + ✅ FIXED v2: PRICE FLOW — variant price $0.00 issue solved
# + ✅ FIXED v3: DATA + PRODUCT MERGE — Bright Data ke saare
#               standard fields Shopify tak pahunchte hain
# + ✅ NAYA: Collections — fetch + add product to collections
# + ✅ NAYA: Manual Cron Trigger — /trigger-price-update
# + ✅ NAYA: Markup type "both" — Fixed + Percent
# + ✅ FIXED v4: /collections me auto-refresh (401 problem solved)
# ============================================

import logging
from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
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
from app.database import get_db
from app.models import Admin, Product, ShopifyStore
from app.services.brightdata import (
    BrightDataError,
    calculate_final_price,
    fetch_product_from_brightdata,
)
from app.services.shopify import (
    build_auth_url,
    create_shopify_product,
    create_shopify_product_with_variants,
    add_variant_to_existing_product,
    add_product_to_collections,
    exchange_code_for_token,
    exchange_id_token_for_offline_token,
    verify_hmac,
    verify_id_token,
    shopify_graphql,
)
from app.services.shopify import refresh_shopify_token  # ✅ NAYA
from app.services.scheduler import run_price_update_now

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/shopify", tags=["Shopify"])


# ============================================
# HELPER: 401 check
# ============================================
def _is_auth_error(result: dict) -> bool:
    """Check karo ki GraphQL result me 401/403 error hai ya nahi."""
    if not isinstance(result, dict):
        return False
    for err in result.get("errors", []) or []:
        if isinstance(err, dict) and err.get("status") in (401, 403):
            return True
    return False


# ============================================
# HELPER: Store ka valid access token (auto-refresh)
# ============================================
async def _get_valid_access_token(
    store: ShopifyStore,
    db: Session,
    force_refresh: bool = False,
) -> str:
    """
    Store ka access token return karta hai.
    Agar expire ho raha hai (10 min buffer) ya force_refresh=True,
    to refresh karta hai aur DB me save karta hai.
    """
    now = datetime.now(timezone.utc)
    buffer = timedelta(minutes=10)

    needs_refresh = force_refresh
    if not needs_refresh and store.expires_at and store.expires_at <= now + buffer:
        needs_refresh = True

    if needs_refresh and store.refresh_token:
        logger.info(f"🔄 Refreshing token for {store.shop_domain}")
        refreshed = await refresh_shopify_token(
            store.shop_domain, store.refresh_token
        )

        if refreshed and refreshed.get("access_token"):
            store.access_token = refreshed["access_token"]
            if refreshed.get("refresh_token"):
                store.refresh_token = refreshed["refresh_token"]
            if refreshed.get("expires_in"):
                store.expires_at = now + timedelta(
                    seconds=int(refreshed["expires_in"])
                )
            if refreshed.get("refresh_token_expires_in"):
                store.refresh_token_expires_at = now + timedelta(
                    seconds=int(refreshed["refresh_token_expires_in"])
                )
            db.commit()
            db.refresh(store)
            logger.info(f"✅ Token refreshed for {store.shop_domain}")
        else:
            logger.error(f"❌ Token refresh failed for {store.shop_domain}")

    return store.access_token


# ============================================
# ✅ FIXED v4: Build product_data with metafields
# + ✅ NAYA: "both" markup type support
# ============================================
def _build_product_data_for_shopify(data: dict, product=None) -> dict:
    """
    Bright Data data + product data → Shopify product_data.
    Dono sources ko merge karta hai.
    """
    base = {}

    # ═══════════════════════════════════════════
    # STEP 1: Base fields — product (DB) se, ya `data` se
    # ═══════════════════════════════════════════
    if product:
        # Price resolution
        product_price = product.price
        if product_price is None or float(product_price or 0) <= 0:
            amazon = float(product.amazon_price or 0)
            markup_val = float(product.markup or 2.0)
            markup_type = product.markup_type or "fixed"
            extra_pct = float(getattr(product, "extra_percent", 0.0) or 0.0)

            if markup_type == "percent":
                product_price = amazon * (1 + markup_val / 100)
            elif markup_type == "both":
                base_price = amazon + markup_val
                product_price = base_price * (1 + extra_pct / 100)
            else:
                product_price = amazon + markup_val

            logger.warning(
                f"⚠️ product.price was 0 — calculated ${product_price} "
                f"(type={markup_type})"
            )

        base = {
            "title": product.title,
            "description": product.description or "",
            "brand": product.brand or "",
            "images": product.images or (
                [product.image_url] if product.image_url else []
            ),
            "price": str(product_price) if product_price else "0.00",
            "stock_quantity": product.stock_quantity or 0,
            "is_available": (
                product.is_available
                if product.is_available is not None else True
            ),
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
        }
    else:
        base = {
            "title": data.get("title"),
            "description": data.get("description") or "",
            "brand": data.get("brand") or "",
            "images": data.get("images") or (
                [data["image_url"]] if data.get("image_url") else []
            ),
            "price": str(data.get("price", 0) or 0),
            "stock_quantity": data.get("stock_quantity", 0) or 0,
            "is_available": data.get("is_available", True),
            "availability": data.get("availability", "In Stock"),
            "rating": data.get("rating"),
            "reviews_count": data.get("reviews_count"),
            "amazon_price": data.get("amazon_price"),
            "asin": data.get("asin"),
            "parent_asin": data.get("parent_asin"),
            "variant_attributes": data.get("variant_attributes", []),
            "categories": data.get("categories", []),
            "tags": data.get("tags", []),
        }

    # ═══════════════════════════════════════════
    # STEP 2: STANDARD FIELDS — dono sources se merge
    # ═══════════════════════════════════════════
    standard_fields = [
        "model_number", "item_model_number", "model_name",
        "part_number", "upc", "ean", "isbn",
        "manufacturer", "department", "country_of_origin",
        "item_dimensions", "item_weight", "package_dimensions",
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

    # Source A: Bright Data `data`
    if data:
        for field in standard_fields:
            val = data.get(field)
            if val is not None and str(val).strip() and str(val).strip() != "None":
                base[field] = str(val).strip()

    # Source B: product.specifications
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

        # Source C: product columns
        for field in standard_fields:
            if field in base:
                continue
            val = getattr(product, field, None)
            if val is not None and str(val).strip() and str(val).strip() != "None":
                base[field] = str(val).strip()

    # STEP 3: product_details
    base["product_details"] = (data.get("product_details") if data else None) or []

    filled = [f for f in standard_fields if f in base]
    logger.info(
        f"   📦 product_data built: "
        f"price=${base.get('price')}, "
        f"{len(filled)} standard fields"
    )

    return base


# ============================================
# HELPER: EXTRACT ALL VARIATIONS
# ============================================
def extract_all_variations(data: dict) -> list:
    """Saare variation options nikalo — Color + Size dono."""
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
# HELPER: VARIATION TITLE NIKALO (Single)
# ============================================
def extract_variation_info(data: dict) -> tuple:
    """Legacy function — single variation."""
    variations = extract_all_variations(data)
    first = variations[0]
    return (first["name"], first["value"])


# ============================================
# HELPER: CHECK IF VARIANT EXISTS
# ============================================
async def check_variant_exists_in_shopify(
    shop: str,
    access_token: str,
    shopify_product_id: str,
    variation_values: list,
) -> bool:
    """Check karo ki variant already exists kya."""
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

        result = await shopify_graphql(
            shop, access_token, query, {"id": shopify_product_id}
        )

        if "errors" in result:
            logger.warning(f"⚠️ Failed to fetch variants: {result['errors']}")
            return False

        edges = (
            result.get("data", {})
            .get("product", {})
            .get("variants", {})
            .get("edges", [])
        )

        new_values = {
            v["name"].lower(): v["value"].lower().strip()
            for v in variation_values
        }

        for edge in edges:
            node = edge["node"]
            existing_values = {
                opt["name"].lower(): opt["value"].lower().strip()
                for opt in node.get("selectedOptions", [])
            }

            if existing_values == new_values:
                return True

        return False

    except Exception as e:
        logger.error(f"❌ check_variant_exists error: {e}")
        return False


# ============================================
# ✅ FIXED v2: SMART MARKUP CAP
# ============================================
def apply_markup_cap(markup: float, markup_type: str) -> float:
    """Markup ko safe limits mein cap karo."""
    try:
        markup = float(markup)
    except (ValueError, TypeError):
        return 2.0

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
    else:
        markup = min(markup, 50.0)

    return markup


# ============================================
# INSTALL
# ============================================
@router.get("/install")
def shopify_install(shop: str = Query(..., description="Shopify store domain")):
    if not shop:
        raise HTTPException(status_code=400, detail="Shop parameter required")

    auth_url = build_auth_url(shop)
    logger.info(f"Redirecting to Shopify OAuth: {auth_url}")
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
        logger.error(f"❌ HMAC verification failed for {shop}")
        raise HTTPException(status_code=401, detail="HMAC verification failed")

    logger.info(f"✅ HMAC verified for {shop}")

    token_data = await exchange_code_for_token(shop, code)

    if not token_data or not token_data.get("access_token"):
        logger.error(f"❌ Token exchange failed for {shop}")
        return HTMLResponse(
            content="<h1>❌ Installation Failed</h1>",
            status_code=400,
        )

    access_token = token_data["access_token"]

    now = datetime.now(timezone.utc)
    expires_in = token_data.get("expires_in")
    refresh_expires_in = token_data.get("refresh_token_expires_in")

    expires_at = now + timedelta(seconds=int(expires_in)) if expires_in else None
    refresh_token_expires_at = (
        now + timedelta(seconds=int(refresh_expires_in))
        if refresh_expires_in else None
    )

    existing = db.query(ShopifyStore).filter(
        ShopifyStore.shop_domain == shop
    ).first()

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

    return HTMLResponse(
        content=f"""
        <html>
            <body style="font-family: sans-serif; padding: 40px; text-align: center; background: #f6f6f7;">
                <div style="max-width: 500px; margin: 0 auto; background: white; padding: 40px; border-radius: 12px;">
                    <h1 style="color: #008060;">✅ App Installed!</h1>
                    <p style="color: #637381;">Your store <strong>{shop}</strong> is now connected.</p>
                    <a href="https://{shop}/admin/apps" style="display: inline-block; margin-top: 20px; padding: 12px 24px; background: #008060; color: white; text-decoration: none; border-radius: 6px;">
                        Go to Shopify Admin
                    </a>
                </div>
            </body>
        </html>
        """,
    )


# ============================================
# STORES
# ============================================
@router.get("/stores")
def list_installed_stores(db: Session = Depends(get_db)):
    stores = db.query(ShopifyStore).all()
    return {
        "total": len(stores),
        "stores": [
            {
                "shop_domain": s.shop_domain,
                "installed_at": s.installed_at,
                "scopes": s.scopes,
            }
            for s in stores
        ],
    }


# ============================================
# STORE ID BY DOMAIN
# ============================================
@router.get("/store-id")
def get_store_id_by_domain(
    shop: str = Query(..., description="Shopify store domain"),
    db: Session = Depends(get_db),
):
    if not shop:
        raise HTTPException(status_code=400, detail="shop parameter required")

    store = db.query(ShopifyStore).filter(
        ShopifyStore.shop_domain == shop
    ).first()

    if not store:
        raise HTTPException(
            status_code=404, detail=f"Store not found for shop: {shop}"
        )

    return {"store_id": store.id, "shop_domain": store.shop_domain}


# ============================================
# ✅ FETCH SHOPIFY COLLECTIONS (auto-refresh)
# ============================================
@router.get("/collections")
async def get_shopify_collections(
    shop_domain: str = Query(..., description="Shopify store domain"),
    db: Session = Depends(get_db),
):
    """
    Shopify store ki saari collections fetch karo.
    Token expire hone par automatically refresh karta hai.
    """
    store = (
        db.query(ShopifyStore)
        .filter(ShopifyStore.shop_domain == shop_domain)
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail=f"Store not connected: {shop_domain}",
        )

    query = """
    query getCollections($first: Int!) {
      collections(first: $first) {
        edges {
          node {
            id
            title
            handle
            productsCount { count }
          }
        }
      }
    }
    """

    # ✅ Pehla attempt — fresh/refreshed token ke saath
    access_token = await _get_valid_access_token(store, db)
    result = await shopify_graphql(
        shop_domain, access_token, query, {"first": 250}
    )

    # ✅ Agar 401 aaya — force refresh karke retry
    if _is_auth_error(result):
        logger.warning(f"🔄 401 for {shop_domain} — forcing refresh...")
        access_token = await _get_valid_access_token(
            store, db, force_refresh=True
        )
        result = await shopify_graphql(
            shop_domain, access_token, query, {"first": 250}
        )

    if "errors" in result:
        logger.error(f"❌ Collections fetch errors: {result['errors']}")
        raise HTTPException(
            status_code=400, detail="Failed to fetch collections"
        )

    edges = (
        result.get("data", {})
        .get("collections", {})
        .get("edges", [])
    )

    collections = []
    for edge in edges:
        node = edge.get("node", {})
        collections.append({
            "id": node.get("id"),
            "title": node.get("title"),
            "handle": node.get("handle"),
            "products_count": (node.get("productsCount") or {}).get("count", 0),
        })

    logger.info(f"✅ Fetched {len(collections)} collections for {shop_domain}")

    return {
        "success": True,
        "total": len(collections),
        "collections": collections,
    }


# ============================================
# ✅ TRIGGER CRON JOB MANUALLY
# ============================================
@router.post("/trigger-price-update")
async def trigger_price_update(
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    """
    Manually price update cron job trigger karo.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization")

    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty ID token")

    try:
        payload = verify_id_token(token)
        logger.info("✅ ID token verified for cron trigger")
    except ValueError as e:
        logger.error(f"❌ ID token verify fail: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid ID token: {str(e)}")

    dest = payload.get("dest", "")
    shop_domain = dest.replace("https://", "").split("/")[0]

    if not shop_domain:
        raise HTTPException(status_code=401, detail="Shop domain missing")

    logger.info(f"🚀 Manual price update triggered by {shop_domain}")

    store = (
        db.query(ShopifyStore)
        .filter(ShopifyStore.shop_domain == shop_domain)
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail=f"Store {shop_domain} not connected",
        )

    try:
        await run_price_update_now()
        logger.info(f"✅ Price update completed for {shop_domain}")
        return {
            "success": True,
            "message": "Price update completed successfully",
            "shop_domain": shop_domain,
        }
    except Exception as e:
        logger.error(f"❌ Price update failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Price update failed: {str(e)}",
        )


# ============================================
# PUSH PRODUCT TO SHOPIFY (Admin Panel Se)
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

    store = (
        db.query(ShopifyStore)
        .filter(ShopifyStore.shop_domain == shop_domain)
        .first()
    )

    if not store:
        raise HTTPException(status_code=404, detail="Store not connected")

    product.shopify_store_id = store.id
    product.shopify_status = "active"

    existing_parent = None
    if product.parent_asin:
        existing_parent = (
            db.query(Product)
            .filter(
                Product.parent_asin == product.parent_asin,
                Product.id != product.id,
                Product.shopify_product_id.isnot(None),
            )
            .first()
        )

    all_variations = extract_all_variations({
        "variant_attributes": product.variant_attributes or [],
        "specifications": product.specifications or {},
    })

    # ✅ Valid token ensure karo
    access_token = await _get_valid_access_token(store, db)

    if existing_parent and existing_parent.shopify_product_id:
        variant_exists = await check_variant_exists_in_shopify(
            shop=store.shop_domain,
            access_token=access_token,
            shopify_product_id=existing_parent.shopify_product_id,
            variation_values=all_variations,
        )

        if variant_exists:
            logger.warning("⚠️ Variant exists — creating new product")
            existing_parent = None

    if existing_parent and existing_parent.shopify_product_id:
        logger.info(
            f"➕ Adding variant to existing: {existing_parent.shopify_product_id}"
        )

        result = await add_variant_to_existing_product(
            shop=store.shop_domain,
            access_token=access_token,
            product_id=existing_parent.shopify_product_id,
            variant_data={
                "price": product.price,
                "sku": product.asin,
                "stock": product.stock_quantity or 0,
            },
            all_options=all_variations,
        )

        if "errors" not in result:
            product.shopify_product_id = existing_parent.shopify_product_id
            product.shopify_handle = existing_parent.shopify_handle
            db.commit()

            if collection_ids:
                await add_product_to_collections(
                    shop=store.shop_domain,
                    access_token=access_token,
                    product_id=existing_parent.shopify_product_id,
                    collection_ids=collection_ids,
                )

            return {
                "success": True,
                "message": "Variant added",
                "shopify_product_id": existing_parent.shopify_product_id,
                "variations": all_variations,
                "variant_added": True,
                "collections_added": len(collection_ids),
            }

    product_data = _build_product_data_for_shopify(
        data={}, product=product
    )

    logger.info(
        f"   📤 Shopify ko bheja ja raha price: "
        f"${product_data.get('price')}"
    )

    result = await create_shopify_product(
        shop=store.shop_domain,
        access_token=access_token,
        product_data=product_data,
    )

    if "errors" in result:
        raise HTTPException(status_code=400, detail="Shopify API error")

    shopify_product = (
        result.get("data", {}).get("productSet", {}).get("product", {})
    )

    new_pid = shopify_product.get("id")

    product.shopify_product_id = new_pid
    product.shopify_handle = shopify_product.get("handle")
    db.commit()

    if new_pid and collection_ids:
        await add_product_to_collections(
            shop=store.shop_domain,
            access_token=access_token,
            product_id=new_pid,
            collection_ids=collection_ids,
        )

    return {
        "success": True,
        "message": "Product pushed to Shopify",
        "shopify_product_id": new_pid,
        "shopify_handle": shopify_product.get("handle"),
        "variant_added": False,
        "collections_added": len(collection_ids),
    }


# ============================================
# ✅ ADD PRODUCT FROM SHOPIFY APP
# ============================================
@router.post("/app/add-product")
async def add_product_from_shopify_app(
    amazon_url: str = Body(..., embed=True),
    markup: float = Body(2.0, embed=True),
    markup_type: str = Body("fixed", embed=True),
    extra_percent: float = Body(0.0, embed=True),
    collection_ids: list = Body(default=[], embed=True),
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization")

    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty ID token")

    try:
        payload = verify_id_token(token)
        logger.info("✅ ID token verified")
    except ValueError as e:
        logger.error(f"❌ ID token verify fail: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid ID token: {str(e)}")

    dest = payload.get("dest", "")
    shop_domain = dest.replace("https://", "").split("/")[0]

    if not shop_domain:
        raise HTTPException(status_code=401, detail="Shop domain missing")

    logger.info(f"✅ Verified request from: {shop_domain}")
    logger.info(f"📁 Collections selected: {len(collection_ids)}")

    store = db.query(ShopifyStore).filter(
        ShopifyStore.shop_domain == shop_domain
    ).first()

    async def refresh_store_token() -> bool:
        nonlocal store
        token_data = await exchange_id_token_for_offline_token(
            shop_domain, token
        )
        if not token_data or not token_data.get("access_token"):
            return False

        now = datetime.now(timezone.utc)
        expires_in = token_data.get("expires_in")
        refresh_expires_in = token_data.get("refresh_token_expires_in")

        expires_at = (
            now + timedelta(seconds=int(expires_in)) if expires_in else None
        )
        refresh_token_expires_at = (
            now + timedelta(seconds=int(refresh_expires_in))
            if refresh_expires_in else None
        )

        if store:
            store.access_token = token_data["access_token"]
            store.refresh_token = token_data.get("refresh_token")
            store.expires_at = expires_at
            store.refresh_token_expires_at = refresh_token_expires_at
            store.scopes = token_data.get("scope") or settings.SHOPIFY_SCOPES
        else:
            store = ShopifyStore(
                shop_domain=shop_domain,
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                expires_at=expires_at,
                refresh_token_expires_at=refresh_token_expires_at,
                scopes=token_data.get("scope") or settings.SHOPIFY_SCOPES,
            )
            db.add(store)

        db.commit()
        db.refresh(store)
        logger.info(f"✅ Token refreshed for {shop_domain}")
        return True

    refreshed_ok = await refresh_store_token()
    if not refreshed_ok:
        if not store:
            raise HTTPException(
                status_code=404,
                detail=f"Store {shop_domain} not connected",
            )

    try:
        data = await fetch_product_from_brightdata(amazon_url)
    except BrightDataError as e:
        raise HTTPException(
            status_code=400, detail=f"Bright Data fail: {str(e)}"
        )

    asin = data["asin"]
    parent_asin = data.get("parent_asin")

    existing = db.query(Product).filter(Product.asin == asin).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Product already exists (ASIN: {asin})",
        )

    existing_parent = None
    if parent_asin:
        existing_parent = (
            db.query(Product)
            .filter(
                Product.parent_asin == parent_asin,
                Product.asin != asin,
                Product.shopify_product_id.isnot(None),
            )
            .first()
        )

    all_variations = extract_all_variations(data)

    if existing_parent and existing_parent.shopify_product_id:
        variant_exists = await check_variant_exists_in_shopify(
            shop=shop_domain,
            access_token=store.access_token,
            shopify_product_id=existing_parent.shopify_product_id,
            variation_values=all_variations,
        )

        if variant_exists:
            logger.warning("⚠️ Variant exists — new product")
            existing_parent = None

    user_markup = float(markup) if markup is not None else 2.0
    user_markup_type = (
        markup_type if markup_type in ("fixed", "percent", "both") else "fixed"
    )
    user_markup = apply_markup_cap(user_markup, user_markup_type)

    logger.info(
        f"💰 Markup: {user_markup} ({user_markup_type}), "
        f"extra_percent={extra_percent}"
    )

    final_price = calculate_final_price(
        amazon_price=data["amazon_price"],
        markup=user_markup,
        markup_type=user_markup_type,
        extra_percent=extra_percent,
    )

    logger.info(f"💰 Final price: ${final_price}")

    new_product = Product(
        asin=asin,
        parent_asin=parent_asin,
        is_variation=data["is_variation"],
        title=data["title"],
        brand=data["brand"],
        description=data["description"],
        image_url=data["image_url"],
        images=data.get("images", []),
        specifications=data.get("specifications", {}),
        rating=data.get("rating"),
        reviews_count=data.get("reviews_count"),
        availability=data.get("availability", "In Stock"),
        is_available=data.get("is_available", True),
        stock_quantity=data.get("stock_quantity", 0),
        amazon_price=data["amazon_price"],
        price=final_price,
        markup=user_markup,
        markup_type=user_markup_type,
        is_manual_override=False,
        variant_attributes=data.get("variant_attributes", []),
        categories=data.get("categories", []),
        tags=data.get("tags", []),
        shopify_store_id=store.id,
        shopify_status="active",
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    logger.info(
        f"✅ Product saved to Supabase: {asin} (price=${final_price})"
    )

    shopify_pushed = False
    shopify_product_id = None
    variant_added = False
    collections_added = 0

    try:
        async def do_push() -> tuple:
            _pushed = False
            _pid = None
            _vadd = False
            _result = {}

            if existing_parent and existing_parent.shopify_product_id:
                logger.info(
                    f"➕ Adding variant to: "
                    f"{existing_parent.shopify_product_id}"
                )

                _result = await add_variant_to_existing_product(
                    shop=shop_domain,
                    access_token=store.access_token,
                    product_id=existing_parent.shopify_product_id,
                    variant_data={
                        "price": final_price,
                        "sku": asin,
                        "stock": new_product.stock_quantity or 0,
                    },
                    all_options=all_variations,
                )

                if "errors" not in _result:
                    _vadd = True
                    _pushed = True
                    new_product.shopify_product_id = (
                        existing_parent.shopify_product_id
                    )
                    new_product.shopify_handle = (
                        existing_parent.shopify_handle
                    )
                    db.commit()
                    _pid = existing_parent.shopify_product_id

            else:
                logger.info("🆕 Creating new product")

                product_data = _build_product_data_for_shopify(
                    data=data, product=new_product
                )

                logger.info(
                    f"   📤 Shopify ko bheja ja raha price: "
                    f"${product_data.get('price')}"
                )

                _result = await create_shopify_product(
                    shop=shop_domain,
                    access_token=store.access_token,
                    product_data=product_data,
                )

                if _result is None:
                    logger.error("❌ create_shopify_product returned None")
                    _result = {
                        "errors": [{"message": "Product creation failed"}]
                    }
                    return _pushed, _pid, _vadd, _result

                if "errors" not in _result:
                    _pushed = True
                    _pid = (
                        _result.get("data", {})
                        .get("productSet", {})
                        .get("product", {})
                        .get("id")
                    )
                    if _pid:
                        new_product.shopify_product_id = _pid
                        new_product.shopify_handle = (
                            _result.get("data", {})
                            .get("productSet", {})
                            .get("product", {})
                            .get("handle")
                        )
                        db.commit()

            return _pushed, _pid, _vadd, _result

        shopify_pushed, shopify_product_id, variant_added, first_result = (
            await do_push()
        )

        if not shopify_pushed and _is_auth_error(first_result):
            logger.warning("🔄 401 — refreshing and retrying...")
            refreshed = await refresh_store_token()
            if refreshed:
                (
                    shopify_pushed,
                    shopify_product_id,
                    variant_added,
                    _,
                ) = await do_push()

        if shopify_pushed and shopify_product_id and collection_ids:
            logger.info(
                f"📁 Adding product to {len(collection_ids)} collection(s)..."
            )
            success = await add_product_to_collections(
                shop=shop_domain,
                access_token=store.access_token,
                product_id=shopify_product_id,
                collection_ids=collection_ids,
            )
            if success:
                collections_added = len(collection_ids)

    except Exception as e:
        logger.error(f"❌ Shopify push fail: {e}")

    return {
        "success": True,
        "message": (
            f"Product added (ASIN: {asin})"
            + (" + variant added ✅" if variant_added else "")
            + (
                " + new product created ✅"
                if shopify_pushed and not variant_added
                else ""
            )
            + (
                f" + added to {collections_added} collection(s) ✅"
                if collections_added
                else ""
            )
        ),
        "product_id": new_product.id,
        "asin": asin,
        "parent_asin": new_product.parent_asin,
        "markup": user_markup,
        "markup_type": user_markup_type,
        "extra_percent": extra_percent,
        "final_price": final_price,
        "amazon_price": new_product.amazon_price,
        "variations": all_variations,
        "shopify_pushed": shopify_pushed,
        "shopify_product_id": shopify_product_id,
        "variant_added": variant_added,
        "collections_added": collections_added,
        "shop_domain": shop_domain,
        "store_id": store.id,
    }


# ============================================
# HEALTH CHECK
# ============================================
@router.get("/health")
def shopify_health():
    return {"status": "ok", "service": "shopify-integration"}