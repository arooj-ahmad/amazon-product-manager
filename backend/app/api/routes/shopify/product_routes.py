# app/api/routes/shopify/product_routes.py

import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Product, ShopifyStore
from app.config import settings
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
    store = db.query(ShopifyStore).filter(ShopifyStore.shop_domain == shop_domain).first()

    # Token Refresh logic yahan aayega (jo aapke paas pehle se tha)
    
    asin_quick = extract_asin_from_url(amazon_url)
    if asin_quick and db.query(Product).filter(Product.asin == asin_quick).first():
        raise HTTPException(status_code=409, detail=f"Product already exists (ASIN: {asin_quick})")

    _resolve_markup(store, markup, markup_type, extra_percent)

    background_tasks.add_task(
        _background_fetch_and_push,
        amazon_url=amazon_url, shop_domain=shop_domain, store_id=store.id,
        markup=markup, markup_type=markup_type, extra_percent=extra_percent,
        collection_ids=collection_ids or [],
    )
    return {"success": True, "message": "Product fetch started (Apify)."}