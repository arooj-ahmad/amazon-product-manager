# ============================================
# app/services/shopify_helpers.py
# Shared helpers, GraphQL caller, API version
# ============================================

import logging
from typing import Optional

import httpx

from app.config import settings

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
