# ============================================
# app/services/shopify_helpers.py
# Shared helpers, GraphQL caller, API version
# + ✅ AUTO TOKEN REFRESH (expire hone se pehle refresh)
# ============================================

import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

from app.config import settings
from app.services.shopify_auth import refresh_shopify_token

logger = logging.getLogger(__name__)


# ============================================
# HELPER: Safe API version
# ============================================
def _safe_api_version() -> str:
    """2026-10 / unstable / empty ko 2025-01 pe fallback karo."""
    v = (settings.SHOPIFY_API_VERSION or "2025-01").strip()
    if v in ("2026-10", "unstable", ""):
        return "2025-01"
    return v


# ============================================
# HELPER: Build Shopify tags (string array)
# ============================================
def _build_shopify_tags(product_data: dict) -> list[str]:
    """Product data se Shopify tags ka array banao."""
    tags: list[str] = []

    raw_tags = product_data.get("tags") or []
    if isinstance(raw_tags, list):
        for t in raw_tags:
            if isinstance(t, str):
                clean = t.strip()
                if clean and len(clean) < 100:
                    tags.append(clean)

    raw_cats = product_data.get("categories") or []
    if isinstance(raw_cats, list):
        for c in raw_cats:
            if isinstance(c, str):
                clean = c.strip()
                if clean and len(clean) < 50 and clean not in tags:
                    tags.append(clean)

    tags = list(dict.fromkeys(tags))
    return tags[:250]


# ============================================
# HELPER: First category → productType
# ============================================
def _get_product_type(product_data: dict) -> str:
    """Shopify mein ek hi productType hota hai."""
    categories = product_data.get("categories") or []
    if isinstance(categories, list) and categories:
        first = categories[0]
        if isinstance(first, str):
            return first.strip()[:255]
    return ""


# ============================================
# ✅ NAYA: Fresh access token get karo (auto-refresh)
# ============================================
async def get_fresh_access_token(shop_domain: str, db) -> Optional[str]:
    """
    Store ka access token return karta hai.
    Agar expire ho raha hai (10 min buffer), to refresh karta hai
    aur database me naya token save karta hai.

    Args:
        shop_domain: e.g. "test-store.myshopify.com"
        db: SQLAlchemy session (SessionLocal instance)

    Returns:
        Fresh access_token string, ya None agar refresh fail ho
    """
    # Lazy import taaki circular dependency na bane
    from app.models.shopify_store import ShopifyStore

    store = db.query(ShopifyStore).filter_by(shop_domain=shop_domain).first()
    if not store:
        logger.error(f"Store not found: {shop_domain}")
        return None

    now = datetime.utcnow()
    buffer = timedelta(minutes=10)

    # Agar expires_at set hai aur expire hone wala hai → refresh karo
    needs_refresh = False
    if store.expires_at and store.expires_at <= now + buffer:
        needs_refresh = True
    elif store.expires_at and store.expires_at <= now:
        # Already expired
        needs_refresh = True

    if needs_refresh and store.refresh_token:
        logger.info(f"🔄 Refreshing expired token for {shop_domain}")
        result = await refresh_shopify_token(shop_domain, store.refresh_token)

        if not result:
            logger.error(f"❌ Token refresh failed for {shop_domain}")
            return None

        # Naya token save karo
        store.access_token = result["access_token"]
        if result.get("refresh_token"):
            store.refresh_token = result["refresh_token"]
        if result.get("expires_in"):
            store.expires_at = now + timedelta(seconds=int(result["expires_in"]))
        if result.get("refresh_token_expires_in"):
            store.refresh_token_expires_at = now + timedelta(
                seconds=int(result["refresh_token_expires_in"])
            )
        store.updated_at = now

        db.commit()
        db.refresh(store)
        logger.info(f"✅ Token refreshed & saved for {shop_domain}")

    return store.access_token


# ============================================
# GRAPHQL API CALL
# ============================================
async def shopify_graphql(
    shop: str,
    access_token: str,
    query: str,
    variables: dict = None,
) -> dict:
    api_version = _safe_api_version()
    url = f"https://{shop}/admin/api/{api_version}/graphql.json"

    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }

    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 400:
                body = response.text[:1000]
                logger.error(
                    f"GraphQL HTTP {response.status_code} for {shop}: {body}"
                )
                return {
                    "errors": [
                        {
                            "message": f"HTTP {response.status_code}: {body}",
                            "status": response.status_code,
                        }
                    ]
                }
            return response.json()
    except Exception as e:
        logger.error(f"GraphQL call fail: {e}")
        return {"errors": [{"message": str(e)}]}


# ============================================
# ✅ NAYA: Auto-refresh + GraphQL combined
# ============================================
async def shopify_graphql_with_refresh(
    shop: str,
    query: str,
    variables: dict = None,
    db=None,
) -> dict:
    """
    Ye function automatically token refresh karta hai (agar zaroori ho),
    phir GraphQL call karta hai.

    Agar refresh ke baad bhi 401 aata hai, to dobara try karta hai
    (force refresh).
    """
    if db is None:
        # Import and create session
        from app.db.session import SessionLocal
        db = SessionLocal()
        should_close = True
    else:
        should_close = False

    try:
        access_token = await get_fresh_access_token(shop, db)
        if not access_token:
            return {
                "errors": [
                    {"message": f"Could not get access token for {shop}"}
                ]
            }

        # First attempt
        result = await shopify_graphql(shop, access_token, query, variables)

        # Agar 401 aaya, to force refresh karke dobara try karo
        first_error = (result.get("errors") or [{}])[0]
        if "401" in str(first_error.get("message", "")):
            logger.warning(f"⚠️ 401 received, forcing token refresh for {shop}")

            from app.models.shopify_store import ShopifyStore
            store = db.query(ShopifyStore).filter_by(shop_domain=shop).first()
            if store and store.refresh_token:
                refresh_result = await refresh_shopify_token(
                    shop, store.refresh_token
                )
                if refresh_result:
                    store.access_token = refresh_result["access_token"]
                    if refresh_result.get("refresh_token"):
                        store.refresh_token = refresh_result["refresh_token"]
                    if refresh_result.get("expires_in"):
                        store.expires_at = datetime.utcnow() + timedelta(
                            seconds=int(refresh_result["expires_in"])
                        )
                    db.commit()

                    # Retry with fresh token
                    result = await shopify_graphql(
                        shop, refresh_result["access_token"], query, variables
                    )

        return result

    finally:
        if should_close:
            db.close()