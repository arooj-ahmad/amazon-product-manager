# ============================================
# app/api/routes/shopify_routes.py
# Shopify OAuth + Product Push + Embedded App
# + Availability + Inventory tracking
# + ASIN + Parent ASIN + Rating + Reviews + Amazon Price + Availability
# + Variations support (parent detection + smart variant attributes)
# + /store-id endpoint (shop domain se store ID)
# + ✅ NAYA: shopify_store_id aur shopify_status set karo
# + ✅ FIXED: refresh_store_token mein refresh_token + expiry save karo
# + ✅ FIXED: /callback bhi refresh_token + expiry save kare
# + ✅ FIXED: expires_at = None (permanent token ke liye)
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
    exchange_code_for_token,
    exchange_id_token_for_offline_token,
    verify_hmac,
    verify_id_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/shopify", tags=["Shopify"])


# ============================================
# ✅ HELPER: VARIATION TITLE NIKALO
# ============================================
def extract_variation_info(data: dict) -> tuple:
    attrs = data.get("variant_attributes") or []
    if attrs:
        for attr in attrs:
            name = (attr.get("name") or "").strip().lower()
            if name == "size":
                return ("Size", attr.get("value", "Default"))

        for attr in attrs:
            name = (attr.get("name") or "").strip().lower()
            if name == "color":
                return ("Color", attr.get("value", "Default"))

        for attr in attrs:
            name = (attr.get("name") or "").strip().lower()
            if name in ("style", "capacity"):
                return (attr["name"], attr.get("value", "Default"))

        first_attr = attrs[0]
        if first_attr.get("name") and first_attr.get("value"):
            return (first_attr["name"], first_attr["value"])

    variations = data.get("variations") or []
    if variations:
        v = variations[0]
        if v.get("name") and v.get("value"):
            return (v["name"], v["value"])

    specs = data.get("specifications") or {}
    for key in ["Size", "Color", "Style", "Capacity"]:
        if key in specs and specs[key]:
            return (key, str(specs[key]))

    return ("Style", "Default")


# ============================================
# INSTALL
# ============================================
@router.get("/install")
def shopify_install(
    shop: str = Query(..., description="Shopify store domain"),
):
    if not shop:
        raise HTTPException(status_code=400, detail="Shop parameter required")

    auth_url = build_auth_url(shop)
    logger.info(f"Redirecting to Shopify OAuth: {auth_url}")
    return RedirectResponse(url=auth_url)


# ============================================
# CALLBACK (OAuth)
# ✅ FIXED: expires_at = None (permanent token ke liye)
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
        raise HTTPException(
            status_code=401,
            detail="HMAC verification failed. Request may be tampered.",
        )

    logger.info(f"✅ HMAC verified for {shop}")

    token_data = await exchange_code_for_token(shop, code)

    if not token_data or not token_data.get("access_token"):
        logger.error(f"❌ Token exchange failed for {shop}")
        return HTMLResponse(
            content="""
            <html>
                <body style="font-family: sans-serif; padding: 40px; text-align: center;">
                    <h1>❌ Installation Failed</h1>
                    <p>Could not exchange authorization code for access token.</p>
                </body>
            </html>
            """,
            status_code=400,
        )

    access_token = token_data["access_token"]

    # ✅ FIXED: Permanent token — expiry NULL
    expires_at = None
    refresh_token_expires_at = None

    existing = (
        db.query(ShopifyStore)
        .filter(ShopifyStore.shop_domain == shop)
        .first()
    )

    if existing:
        existing.access_token = access_token
        existing.refresh_token = token_data.get("refresh_token")
        existing.expires_at = expires_at
        existing.refresh_token_expires_at = refresh_token_expires_at
        existing.scopes = settings.SHOPIFY_SCOPES
        logger.info(
            f"Updated token for {shop} "
            f"(refresh_token_saved={bool(token_data.get('refresh_token'))}, "
            f"permanent=True)"
        )
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
        logger.info(f"New store installed: {shop} (permanent token)")

    db.commit()

    return HTMLResponse(
        content=f"""
        <html>
            <body style="font-family: sans-serif; padding: 40px; text-align: center; background: #f6f6f7;">
                <div style="max-width: 500px; margin: 0 auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <h1 style="color: #008060;">✅ App Installed!</h1>
                    <p style="color: #637381;">Your store <strong>{shop}</strong> is now connected.</p>
                    <p style="color: #637381; font-size: 14px;">Permanent token saved successfully.</p>
                    <a href="https://{shop}/admin/apps"
                       style="display: inline-block; margin-top: 20px; padding: 12px 24px; background: #008060; color: white; text-decoration: none; border-radius: 6px;">
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
# ✅ SHOP DOMAIN SE STORE ID NIKALO
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
            status_code=404,
            detail=f"Store not found for shop: {shop}",
        )

    return {"store_id": store.id, "shop_domain": store.shop_domain}


# ============================================
# PUSH PRODUCT TO SHOPIFY (Admin Panel Se)
# ============================================
@router.post("/push-product/{product_id}")
async def push_product_to_shopify(
    product_id: int,
    shop_domain: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(
            status_code=404, detail="Product not found in database"
        )

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

    if existing_parent and existing_parent.shopify_product_id:
        logger.info(
            f"➕ Adding variant to existing product: "
            f"{existing_parent.shopify_product_id}"
        )

        option_name, variant_title = extract_variation_info({
            "variant_attributes": product.variant_attributes or [],
            "specifications": product.specifications or {},
        })

        result = await add_variant_to_existing_product(
            shop=store.shop_domain,
            access_token=store.access_token,
            product_id=existing_parent.shopify_product_id,
            variant_data={
                "title": variant_title,
                "option_name": option_name,
                "price": product.price,
                "sku": product.asin,
                "stock": product.stock_quantity or 0,
            },
        )

        if "errors" not in result:
            product.shopify_product_id = existing_parent.shopify_product_id
            product.shopify_handle = existing_parent.shopify_handle
            db.commit()

            logger.info(f"✅ Variant added: {product.asin}")

            return {
                "success": True,
                "message": "Variant added to existing product",
                "shopify_product_id": existing_parent.shopify_product_id,
                "shopify_handle": existing_parent.shopify_handle,
                "asin": product.asin,
                "option_name": option_name,
                "variant_title": variant_title,
                "variant_added": True,
            }

    product_data = {
        "title": product.title,
        "description": product.description or "",
        "brand": product.brand or "",
        "images": product.images or (
            [product.image_url] if product.image_url else []
        ),
        "price": str(product.price) if product.price else "0.00",
        "stock_quantity": product.stock_quantity or 0,
        "is_available": (
            product.is_available
            if product.is_available is not None
            else True
        ),
        "availability": product.availability or "In Stock",
        "rating": product.rating,
        "reviews_count": product.reviews_count,
        "amazon_price": product.amazon_price,
        "asin": product.asin,
        "parent_asin": product.parent_asin,
        "variant_attributes": product.variant_attributes or [],
    }

    result = await create_shopify_product(
        shop=store.shop_domain,
        access_token=store.access_token,
        product_data=product_data,
    )

    if "errors" in result:
        logger.error(f"❌ Shopify push error: {result['errors']}")
        raise HTTPException(
            status_code=400,
            detail=f"Shopify API error: {result['errors']}",
        )

    user_errors = (
        result.get("data", {})
        .get("productCreate", {})
        .get("userErrors", [])
    )

    if user_errors:
        logger.error(f"❌ Shopify user errors: {user_errors}")
        raise HTTPException(
            status_code=400,
            detail=f"Shopify validation error: {user_errors}",
        )

    shopify_product = (
        result.get("data", {}).get("productCreate", {}).get("product", {})
    )

    product.shopify_product_id = shopify_product.get("id")
    product.shopify_handle = shopify_product.get("handle")
    db.commit()

    return {
        "success": True,
        "message": "Product pushed to Shopify successfully",
        "shopify_product_id": shopify_product.get("id"),
        "shopify_handle": shopify_product.get("handle"),
        "shopify_title": shopify_product.get("title"),
        "variant_added": False,
    }


# ============================================
# ADD PRODUCT FROM SHOPIFY APP (Iframe Se)
# ✅ FIXED: refresh_store_token mein expires_at = None
# ============================================
@router.post("/app/add-product")
async def add_product_from_shopify_app(
    amazon_url: str = Body(..., embed=True),
    markup: float = Body(2.0, embed=True),
    markup_type: str = Body("fixed", embed=True),
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid authorization header",
        )

    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty ID token")

    try:
        payload = verify_id_token(token)
        logger.info("✅ ID token verified successfully")
    except ValueError as e:
        logger.error(f"❌ ID token verify fail: {e}")
        raise HTTPException(
            status_code=401, detail=f"Invalid ID token: {str(e)}"
        )

    dest = payload.get("dest", "")
    shop_domain = dest.replace("https://", "").split("/")[0]

    if not shop_domain:
        raise HTTPException(
            status_code=401, detail="Shop domain missing from token"
        )

    logger.info(f"✅ Verified Shopify request from: {shop_domain}")

    store = (
        db.query(ShopifyStore)
        .filter(ShopifyStore.shop_domain == shop_domain)
        .first()
    )

    # ✅ FIXED: expires_at = None — permanent token
    async def refresh_store_token() -> bool:
        nonlocal store
        token_data = await exchange_id_token_for_offline_token(shop_domain, token)
        if not token_data or not token_data.get("access_token"):
            return False

        # ✅ Permanent token — expiry NULL
        expires_at = None
        refresh_token_expires_at = None

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
        logger.info(
            f"🔄 Token refreshed for {shop_domain} "
            f"(permanent=True, refresh_token_saved={bool(store.refresh_token)})"
        )
        return True

    if not store:
        ok = await refresh_store_token()
        if not ok:
            raise HTTPException(
                status_code=404,
                detail=f"Store {shop_domain} not connected. Please reinstall the app.",
            )

    if not store:
        raise HTTPException(
            status_code=404,
            detail=f"Store {shop_domain} not connected. Please reinstall the app.",
        )

    try:
        data = await fetch_product_from_brightdata(amazon_url)
    except BrightDataError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Bright Data fetch fail: {str(e)}",
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

    user_markup = float(markup) if markup is not None else 2.0
    user_markup_type = (
        markup_type if markup_type in ("fixed", "percent") else "fixed"
    )

    final_price = calculate_final_price(
        amazon_price=data["amazon_price"],
        markup=user_markup,
        markup_type=user_markup_type,
    )

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
        shopify_store_id=store.id,
        shopify_status="active",
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    logger.info(f"✅ Product saved to Supabase: {asin} (store_id={store.id})")

    shopify_pushed = False
    shopify_product_id = None
    variant_added = False

    try:
        def is_401(result: dict) -> bool:
            for err in result.get("errors", []):
                if isinstance(err, dict) and err.get("status") == 401:
                    return True
            return False

        async def do_push() -> tuple:
            _pushed = False
            _pid = None
            _vadd = False
            _result = {}

            if existing_parent and existing_parent.shopify_product_id:
                logger.info(
                    f"➕ Adding variant to existing product: "
                    f"{existing_parent.shopify_product_id}"
                )
                option_name, variant_title = extract_variation_info(data)

                _result = await add_variant_to_existing_product(
                    shop=shop_domain,
                    access_token=store.access_token,
                    product_id=existing_parent.shopify_product_id,
                    variant_data={
                        "title": variant_title,
                        "option_name": option_name,
                        "price": final_price,
                        "sku": asin,
                        "stock": new_product.stock_quantity or 0,
                    },
                )

                if "errors" not in _result:
                    _vadd = True
                    _pushed = True
                    new_product.shopify_product_id = existing_parent.shopify_product_id
                    new_product.shopify_handle = existing_parent.shopify_handle
                    db.commit()
                    _pid = existing_parent.shopify_product_id

            else:
                logger.info("🆕 Creating new product")
                option_name, variant_title = extract_variation_info(data)

                _result = await create_shopify_product(
                    shop=shop_domain,
                    access_token=store.access_token,
                    product_data={
                        "title": new_product.title,
                        "description": new_product.description or "",
                        "brand": new_product.brand or "",
                        "images": new_product.images or (
                            [new_product.image_url] if new_product.image_url else []
                        ),
                        "price": str(new_product.price),
                        "stock_quantity": new_product.stock_quantity or 0,
                        "is_available": (
                            new_product.is_available
                            if new_product.is_available is not None
                            else True
                        ),
                        "availability": new_product.availability or "In Stock",
                        "rating": new_product.rating,
                        "reviews_count": new_product.reviews_count,
                        "amazon_price": new_product.amazon_price,
                        "asin": new_product.asin,
                        "parent_asin": new_product.parent_asin,
                        "variant_attributes": new_product.variant_attributes or [],
                    },
                )

                if "errors" not in _result:
                    _pushed = True
                    _pid = (
                        _result.get("data", {})
                        .get("productCreate", {})
                        .get("product", {})
                        .get("id")
                    )
                    if _pid:
                        new_product.shopify_product_id = _pid
                        new_product.shopify_handle = (
                            _result.get("data", {})
                            .get("productCreate", {})
                            .get("product", {})
                            .get("handle")
                        )
                        db.commit()

            return _pushed, _pid, _vadd, _result

        shopify_pushed, shopify_product_id, variant_added, first_result = (
            await do_push()
        )

        if not shopify_pushed and is_401(first_result):
            logger.warning(
                f"🔄 401 detected — refreshing token for {shop_domain} and retrying..."
            )
            refreshed = await refresh_store_token()
            if refreshed:
                shopify_pushed, shopify_product_id, variant_added, _ = (
                    await do_push()
                )

    except Exception as e:
        logger.error(f"❌ Shopify push fail: {e}")

    return {
        "success": True,
        "message": (
            f"Product added (ASIN: {asin})"
            + (" + variant added to parent ✅" if variant_added else "")
            + (" + new product created ✅" if shopify_pushed and not variant_added else "")
        ),
        "product_id": new_product.id,
        "asin": asin,
        "parent_asin": new_product.parent_asin,
        "markup": user_markup,
        "markup_type": user_markup_type,
        "final_price": final_price,
        "amazon_price": new_product.amazon_price,
        "availability": new_product.availability,
        "is_available": new_product.is_available,
        "rating": new_product.rating,
        "reviews_count": new_product.reviews_count,
        "shopify_pushed": shopify_pushed,
        "shopify_product_id": shopify_product_id,
        "variant_added": variant_added,
        "shop_domain": shop_domain,
        "store_id": store.id,
    }


# ============================================
# HEALTH CHECK
# ============================================
@router.get("/health")
def shopify_health():
    return {"status": "ok", "service": "shopify-integration"}