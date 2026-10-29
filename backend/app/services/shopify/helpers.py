# ============================================
# app/services/shopify/helpers.py
# + ✅ FIXED: Strict Tags (No Brand / No Title Fallback)
# + ✅ FIXED: Universal 401 Token Refresh Logic
# ============================================

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.core.config import settings
from app.services.shopify.auth import refresh_shopify_token

logger = logging.getLogger(__name__)


def _safe_api_version() -> str:
    v = (settings.SHOPIFY_API_VERSION or "2025-01").strip()
    if v in ("2026-10", "unstable", ""):
        return "2025-01"
    return v


# ============================================
# HELPER: Build Shopify tags (Only actual data)
# ============================================
def _build_shopify_tags(product_data: dict) -> list[str]:
    """Product data se Shopify tags ka array banao (No Fallback)."""
    tags: list[str] = []

    def clean_tag(t: str) -> str:
        return str(t).replace("#", "").replace(",", "").strip()

    # 1. Amazon Tags (jo brightdata.py se aayenge)
    raw_tags = product_data.get("tags") or []
    if isinstance(raw_tags, list):
        for t in raw_tags:
            if t:
                clean = clean_tag(t)
                if clean and len(clean) < 50 and clean not in tags:
                    tags.append(clean)

    # 2. Categories/Breadcrumbs (jo brightdata.py se aayenge)
    raw_cats = product_data.get("categories") or []
    if isinstance(raw_cats, list):
        for c in raw_cats:
            if c:
                clean = clean_tag(c)
                if clean and len(clean) < 50 and clean not in tags:
                    tags.append(clean)

    tags = list(dict.fromkeys(tags))
    return tags[:50]


def _get_product_type(product_data: dict) -> str:
    categories = product_data.get("categories") or []
    if isinstance(categories, list) and categories:
        first = categories[0]
        if isinstance(first, str):
            return first.strip()[:255]
    return ""


# ============================================
# TOKEN REFRESH HELPERS
# ============================================
async def get_fresh_access_token(shop_domain: str, db) -> Optional[str]:
    from app.models.shopify_store import ShopifyStore
    store = db.query(ShopifyStore).filter_by(shop_domain=shop_domain).first()
    if not store:
        return None
        
    now = datetime.now(timezone.utc)
    buffer = timedelta(minutes=10)
    needs_refresh = bool(store.expires_at and store.expires_at <= (now + buffer))
    
    if needs_refresh and store.refresh_token:
        result = await refresh_shopify_token(shop_domain, store.refresh_token)
        if not result:
            return None
            
        store.access_token = result["access_token"]
        if result.get("refresh_token"):
            store.refresh_token = result["refresh_token"]
        if result.get("expires_in"):
            store.expires_at = now + timedelta(seconds=int(result["expires_in"]))
        if result.get("refresh_token_expires_in"):
            store.refresh_token_expires_at = now + timedelta(seconds=int(result["refresh_token_expires_in"]))
        store.updated_at = now
        db.commit()
        db.refresh(store)
        
    return store.access_token


# ============================================
# GRAPHQL CLIENT (Universal 401 Handler)
# ============================================
async def shopify_graphql(shop: str, access_token: str, query: str, variables: dict = None) -> dict:
    """
    Shopify Admin API call. Agar 401 aata hai to khud hi token refresh karke retry karta hai.
    """
    api_version = _safe_api_version()
    url = f"https://{shop}/admin/api/{api_version}/graphql.json"
    headers = {"X-Shopify-Access-Token": access_token, "Content-Type": "application/json"}
    payload = {"query": query}
    if variables is not None:
        payload["variables"] = variables
        
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            # ✅ FIX: 401 Handle karo (Token expired)
            if response.status_code in (401, 403):
                logger.warning(f"🔄 401 Unauthorized on {shop}. Attempting automatic token refresh...")
                
                # Import locally to avoid circular import
                from app.core.database import SessionLocal
                from app.models.shopify_store import ShopifyStore
                
                db = SessionLocal()
                try:
                    store = db.query(ShopifyStore).filter_by(shop_domain=shop).first()
                    if store and store.refresh_token:
                        refresh_result = await refresh_shopify_token(shop, store.refresh_token)
                        if refresh_result and refresh_result.get("access_token"):
                            now = datetime.now(timezone.utc)
                            store.access_token = refresh_result["access_token"]
                            if refresh_result.get("refresh_token"):
                                store.refresh_token = refresh_result["refresh_token"]
                            if refresh_result.get("expires_in"):
                                store.expires_at = now + timedelta(seconds=int(refresh_result["expires_in"]))
                            if refresh_result.get("refresh_token_expires_in"):
                                store.refresh_token_expires_at = now + timedelta(seconds=int(refresh_result["refresh_token_expires_in"]))
                            store.updated_at = now
                            db.commit()
                            
                            logger.info(f"✅ Token refreshed for {shop}. Retrying request...")
                            # Retry with new token
                            new_headers = {"X-Shopify-Access-Token": store.access_token, "Content-Type": "application/json"}
                            retry_response = await client.post(url, headers=new_headers, json=payload)
                            
                            if retry_response.status_code >= 400:
                                return {"errors": [{"message": f"HTTP {retry_response.status_code} after refresh", "status": retry_response.status_code}]}
                            return retry_response.json()
                finally:
                    db.close()
                    
                # Agar refresh fail ho jaye
                return {"errors": [{"message": f"HTTP {response.status_code} - Token refresh failed", "status": response.status_code}]}
            
            # Baaki errors
            if response.status_code >= 400:
                return {"errors": [{"message": f"HTTP {response.status_code}", "status": response.status_code}]}
                
            return response.json()
            
    except Exception as e:
        logger.error(f"❌ shopify_graphql exception: {e}")
        return {"errors": [{"message": str(e)}]}


# ============================================
# LEGACY WRAPPER (Backward Compatibility)
# ============================================
async def shopify_graphql_with_refresh(shop: str, query: str, variables: dict = None, db=None) -> dict:
    """
    Yeh function ab deprecated hai kyunki shopify_graphql khud refresh handle karta hai.
    Lekin purane code ko break hone se bachane ke liye rakha gaya hai.
    """
    # Fetch token from DB if db provided
    if db:
        access_token = await get_fresh_access_token(shop, db)
    else:
        # Fallback
        from app.core.database import SessionLocal
        from app.models.shopify_store import ShopifyStore
        temp_db = SessionLocal()
        try:
            store = temp_db.query(ShopifyStore).filter_by(shop_domain=shop).first()
            access_token = store.access_token if store else None
        finally:
            temp_db.close()
            
    if not access_token:
        return {"errors": [{"message": "Could not get access token"}]}
        
    # Just call the universal function
    return await shopify_graphql(shop, access_token, query, variables)