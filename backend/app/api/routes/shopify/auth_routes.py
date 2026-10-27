# app/api/routes/shopify/auth_routes.py

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
import logging

from app.core.database import get_db
from app.models import ShopifyStore
from app.core.config import settings
from app.services.shopify import (
    build_auth_url, 
    exchange_code_for_token, 
    verify_hmac, 
    refresh_shopify_token,
    shopify_graphql  # ✅ Collections ke liye zaroori hai
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Shopify Auth"])

@router.get("/install")
def shopify_install(shop: str = Query(...)):
    return RedirectResponse(url=build_auth_url(shop))

@router.get("/callback")
async def shopify_callback(request: Request, shop: str = Query(...), code: str = Query(...), hmac: str = Query(None), db: Session = Depends(get_db)):
    if not hmac or not verify_hmac(dict(request.query_params)):
        raise HTTPException(status_code=401, detail="HMAC verification failed")
    
    token_data = await exchange_code_for_token(shop, code)
    if not token_data or not token_data.get("access_token"):
        return HTMLResponse(content="<h1>❌ Installation Failed</h1>", status_code=400)

    now = datetime.now(timezone.utc)
    expires_in = token_data.get("expires_in")
    refresh_expires_in = token_data.get("refresh_token_expires_in")
    
    existing = db.query(ShopifyStore).filter(ShopifyStore.shop_domain == shop).first()
    if existing:
        existing.access_token = token_data["access_token"]
        existing.refresh_token = token_data.get("refresh_token")
        existing.expires_at = now + timedelta(seconds=int(expires_in)) if expires_in else None
        existing.refresh_token_expires_at = now + timedelta(seconds=int(refresh_expires_in)) if refresh_expires_in else None
        existing.scopes = settings.SHOPIFY_SCOPES
    else:
        db.add(ShopifyStore(
            shop_domain=shop,
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            expires_at=now + timedelta(seconds=int(expires_in)) if expires_in else None,
            refresh_token_expires_at=now + timedelta(seconds=int(refresh_expires_in)) if refresh_expires_in else None,
            scopes=settings.SHOPIFY_SCOPES,
        ))
    db.commit()
    return HTMLResponse(content="<h1>✅ App Installed! You can close this window.</h1>")

@router.get("/stores")
def list_installed_stores(db: Session = Depends(get_db)):
    stores = db.query(ShopifyStore).all()
    return {"total": len(stores), "stores": [{"shop_domain": s.shop_domain, "installed_at": s.installed_at, "scopes": s.scopes} for s in stores]}

@router.get("/store-id")
def get_store_id(shop: str = Query(...), db: Session = Depends(get_db)):
    store = db.query(ShopifyStore).filter(ShopifyStore.shop_domain == shop).first()
    if not store: 
        raise HTTPException(status_code=404, detail="Store not found")
    return {"store_id": store.id, "shop_domain": store.shop_domain}


# ============================================
# ✅ NAYA: COLLECTIONS FETCH ROUTE
# ============================================
@router.get("/collections")
async def get_shopify_collections(shop_domain: str = Query(...), db: Session = Depends(get_db)):
    store = db.query(ShopifyStore).filter(ShopifyStore.shop_domain == shop_domain).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not connected")

    # Token valid karein
    from .helpers import _get_valid_access_token
    access_token = await _get_valid_access_token(store, db)

    # ✅ Naya Query: Naye collections ko fetch karne ke liye (source_id:*)
    query = """
    query getCollections($first: Int!) {
      collections(first: $first, query: "source_id:*") {
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
    
    result = await shopify_graphql(shop_domain, access_token, query, {"first": 250})

    if "errors" in result:
        logger.error(f"❌ Collections error: {result['errors']}")
        raise HTTPException(status_code=400, detail="Failed to fetch collections")

    edges = result.get("data", {}).get("collections", {}).get("edges", [])
    collections = [
        {
            "id": n.get("node", {}).get("id"), 
            "title": n.get("node", {}).get("title"), 
            "handle": n.get("node", {}).get("handle"), 
            "products_count": (n.get("node", {}).get("productsCount") or {}).get("count", 0)
        } 
        for n in edges
    ]

    return {"success": True, "total": len(collections), "collections": collections}