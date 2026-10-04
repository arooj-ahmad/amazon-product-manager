# ============================================
# app/api/routes/shopify_routes.py
# Shopify OAuth + Product Push + Embedded App
# + Availability + Inventory tracking
# + ASIN + Parent ASIN + Rating + Reviews Count + Amazon Price + Availability
# ============================================

import logging

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
    exchange_code_for_token,
    verify_hmac,
    verify_id_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/shopify", tags=["Shopify"])


# ============================================
# INSTALL
# ============================================
@router.get("/install")
def shopify_install(
    shop: str = Query(..., description="Shopify store domain"),
):
    """Merchant ko OAuth authorize page par bhejo."""
    if not shop:
        raise HTTPException(status_code=400, detail="Shop parameter required")

    auth_url = build_auth_url(shop)
    logger.info(f"Redirecting to Shopify OAuth: {auth_url}")
    return RedirectResponse(url=auth_url)


# ============================================
# CALLBACK
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
    """OAuth callback — access token exchange + save."""
    query_params = dict(request.query_params)

    # HMAC verification
    if not hmac or not verify_hmac(query_params):
        logger.error(f"❌ HMAC verification failed for {shop}")
        raise HTTPException(
            status_code=401,
            detail="HMAC verification failed. Request may be tampered.",
        )

    logger.info(f"✅ HMAC verified for {shop}")

    # Token exchange
    access_token = await exchange_code_for_token(shop, code)

    if not access_token:
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

    # Save to DB (upsert)
    existing = (
        db.query(ShopifyStore)
        .filter(ShopifyStore.shop_domain == shop)
        .first()
    )

    if existing:
        existing.access_token = access_token
        existing.scopes = settings.SHOPIFY_SCOPES
        logger.info(f"Updated token for {shop}")
    else:
        new_store = ShopifyStore(
            shop_domain=shop,
            access_token=access_token,
            scopes=settings.SHOPIFY_SCOPES,
        )
        db.add(new_store)
        logger.info(f"New store installed: {shop}")

    db.commit()

    return HTMLResponse(
        content=f"""
        <html>
            <body style="font-family: sans-serif; padding: 40px; text-align: center; background: #f6f6f7;">
                <div style="max-width: 500px; margin: 0 auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <h1 style="color: #008060;">✅ App Installed!</h1>
                    <p style="color: #637381;">Your store <strong>{shop}</strong> is now connected.</p>
                    <p style="color: #637381; font-size: 14px;">Access token saved successfully.</p>
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
    """Installed stores list."""
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
# PUSH PRODUCT TO SHOPIFY (Admin Panel Se)
# ============================================
@router.post("/push-product/{product_id}")
async def push_product_to_shopify(
    product_id: int,
    shop_domain: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    """Ek product ko Supabase se Shopify mein push karta hai."""
    # Product dhundo
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(
            status_code=404, detail="Product not found in database"
        )

    # Store dhundo
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

    # ✅ Product data with ALL 6 metafields fields
    product_data = {
        "title": product.title,
        "description": product.description or "",
        "brand": product.brand or "",
        "images": product.images or (
            [product.image_url] if product.image_url else []
        ),
        "price": str(product.price) if product.price else "0.00",
        # availability + inventory
        "stock_quantity": product.stock_quantity or 0,
        "is_available": (
            product.is_available
            if product.is_available is not None
            else True
        ),
        "availability": product.availability or "In Stock",
        # ✅ rating + reviews
        "rating": product.rating,
        "reviews_count": product.reviews_count,
        # ✅ amazon_price
        "amazon_price": product.amazon_price,
        # ✅ asin + parent_asin
        "asin": product.asin,
        "parent_asin": product.parent_asin,
    }

    result = await create_shopify_product(
        shop=store.shop_domain,
        access_token=store.access_token,
        product_data=product_data,
    )

    # Errors check
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

    # ✅ Shopify product ID save karo (future sync ke liye)
    product.shopify_product_id = shopify_product.get("id")
    product.shopify_handle = shopify_product.get("handle")
    db.commit()

    return {
        "success": True,
        "message": "Product pushed to Shopify successfully",
        "shopify_product_id": shopify_product.get("id"),
        "shopify_handle": shopify_product.get("handle"),
        "shopify_title": shopify_product.get("title"),
    }


# ============================================
# ADD PRODUCT FROM SHOPIFY APP (Iframe Se)
# ✅ All 6 metafields fields: asin, parent_asin, rating, reviews_count, amazon_price, availability
# ============================================
@router.post("/app/add-product")
async def add_product_from_shopify_app(
    amazon_url: str = Body(..., embed=True),
    markup: float = Body(2.0, embed=True),
    markup_type: str = Body("fixed", embed=True),
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    """
    Shopify App ke iframe se product add karta hai.
    User apna markup ($ fixed ya % percent) bhej sakta hai.
    """

    # ── Step 1: Auth header ──
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid authorization header",
        )

    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty ID token")

    # ── Step 2: Verify ID token ──
    try:
        payload = verify_id_token(token)
        logger.info("✅ ID token verified successfully")
    except ValueError as e:
        logger.error(f"❌ ID token verify fail: {e}")
        raise HTTPException(
            status_code=401, detail=f"Invalid ID token: {str(e)}"
        )

    # ── Step 3: Shop domain ──
    dest = payload.get("dest", "")
    shop_domain = dest.replace("https://", "").split("/")[0]

    if not shop_domain:
        raise HTTPException(
            status_code=401, detail="Shop domain missing from token"
        )

    logger.info(f"✅ Verified Shopify request from: {shop_domain}")

    # ── Step 4: Store dhundo ──
    store = (
        db.query(ShopifyStore)
        .filter(ShopifyStore.shop_domain == shop_domain)
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail=f"Store {shop_domain} not connected. Please reinstall the app.",
        )

    # ── Step 5: Subscription check (disabled for testing) ──
    # from app.services.billing import get_active_subscription
    # sub_status = await get_active_subscription(
    #     shop=shop_domain,
    #     access_token=store.access_token,
    # )
    # if not sub_status.get("active"):
    #     raise HTTPException(status_code=402, detail="Active subscription required.")

    # ── Step 6: Bright Data fetch ──
    try:
        data = await fetch_product_from_brightdata(amazon_url)
    except BrightDataError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Bright Data fetch fail: {str(e)}",
        )

    asin = data["asin"]

    # Duplicate check
    existing = db.query(Product).filter(Product.asin == asin).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Product already exists (ASIN: {asin})",
        )

    # ── Step 7: User ka markup use karo ──
    user_markup = float(markup) if markup is not None else 2.0
    user_markup_type = (
        markup_type if markup_type in ("fixed", "percent") else "fixed"
    )

    final_price = calculate_final_price(
        amazon_price=data["amazon_price"],
        markup=user_markup,
        markup_type=user_markup_type,
    )

    logger.info(
        f"💰 Markup: {user_markup} ({user_markup_type}) | "
        f"Amazon: {data['amazon_price']} → Final: {final_price}"
    )

    # ── Step 8: Save to DB with all fields ──
    new_product = Product(
        asin=asin,
        parent_asin=data["parent_asin"],
        is_variation=data["is_variation"],
        title=data["title"],
        brand=data["brand"],
        description=data["description"],
        image_url=data["image_url"],
        images=data.get("images", []),
        specifications=data.get("specifications", {}),
        rating=data.get("rating"),
        reviews_count=data.get("reviews_count"),
        # availability + inventory
        availability=data.get("availability", "In Stock"),
        is_available=data.get("is_available", True),
        stock_quantity=data.get("stock_quantity", 0),
        # Pricing
        amazon_price=data["amazon_price"],
        price=final_price,
        markup=user_markup,
        markup_type=user_markup_type,
        is_manual_override=False,
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    logger.info(f"✅ Product saved to Supabase: {asin}")

    # ── Step 9: Push to Shopify with ALL 6 metafields fields ──
    shopify_pushed = False
    shopify_product_id = None

    try:
        shopify_result = await create_shopify_product(
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
                # availability + inventory
                "stock_quantity": new_product.stock_quantity or 0,
                "is_available": (
                    new_product.is_available
                    if new_product.is_available is not None
                    else True
                ),
                "availability": new_product.availability or "In Stock",
                # ✅ rating + reviews
                "rating": new_product.rating,
                "reviews_count": new_product.reviews_count,
                # ✅ amazon_price
                "amazon_price": new_product.amazon_price,
                # ✅ asin + parent_asin
                "asin": new_product.asin,
                "parent_asin": new_product.parent_asin,
            },
        )

        if "errors" not in shopify_result:
            shopify_pushed = True

            # Shopify product ID save karo
            shopify_product_id = (
                shopify_result.get("data", {})
                .get("productCreate", {})
                .get("product", {})
                .get("id")
            )

            if shopify_product_id:
                new_product.shopify_product_id = shopify_product_id
                new_product.shopify_handle = (
                    shopify_result.get("data", {})
                    .get("productCreate", {})
                    .get("product", {})
                    .get("handle")
                )
                db.commit()

            logger.info(f"✅ Product pushed to Shopify: {asin}")
        else:
            logger.warning(
                f"⚠️ Shopify push warnings: {shopify_result.get('errors')}"
            )

    except Exception as e:
        logger.error(f"❌ Shopify push fail: {e}")

    return {
        "success": True,
        "message": f"Product added (ASIN: {asin})"
        + (" and pushed to Shopify ✅" if shopify_pushed else ""),
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
        "shop_domain": shop_domain,
    }


# ============================================
# HEALTH CHECK
# ============================================
@router.get("/health")
def shopify_health():
    """Simple health check."""
    return {"status": "ok", "service": "shopify-integration"}