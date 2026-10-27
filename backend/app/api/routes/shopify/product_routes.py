# app/api/routes/shopify/product_routes.py

import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import Product, ShopifyStore
from app.core.config import settings
from app.services.amazon import extract_asin_from_url
from app.services.shopify import exchange_id_token_for_offline_token, verify_id_token
from .helpers import _normalize_amazon_url, _resolve_markup
from .background_worker import _background_fetch_and_push

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Shopify Products"])

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
        if not token_data or not token_data.get("access_token"):
            return False

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

    # ✅ Duplicate ASIN wala check hata diya hai
    # (Kyunki humein saare variants add karne hain, agar product pehle se hai to worker khud handle kar lega)

    asin_quick = extract_asin_from_url(amazon_url)

    _resolve_markup(store, markup, markup_type, extra_percent)

    background_tasks.add_task(
        _background_fetch_and_push,
        amazon_url=amazon_url, shop_domain=shop_domain, store_id=store.id,
        markup=markup, markup_type=markup_type, extra_percent=extra_percent,
        collection_ids=collection_ids or [],
    )
    return {
        "success": True, 
        "message": "Product fetch started (Apify).",
        "asin": asin_quick,
        "shop_domain": shop_domain
    }