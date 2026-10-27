import logging
import httpx
from typing import Optional
from app.services.shopify.helpers import shopify_graphql, _safe_api_version

logger = logging.getLogger(__name__)

async def delete_shopify_product(shop_domain: str, access_token: str, shopify_product_id: str, refresh_token: Optional[str] = None) -> bool:
    if not all([shop_domain, access_token, shopify_product_id]): return False
    product_gid = shopify_product_id if str(shopify_product_id).startswith("gid://") else f"gid://shopify/Product/{shopify_product_id}"
    
    api_url = f"https://{shop_domain}/admin/api/{_safe_api_version()}/graphql.json"
    headers = {"X-Shopify-Access-Token": access_token, "Content-Type": "application/json"}
    mutation = """mutation productDelete($input: ProductDeleteInput!) { productDelete(input: $input) { deletedProductId userErrors { field message } } }"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(api_url, headers=headers, json={"query": mutation, "variables": {"input": {"id": product_gid}}})
            if res.status_code in (401, 403) and refresh_token:
                from app.services.shopify.auth import refresh_shopify_token
                new_data = await refresh_shopify_token(shop_domain, refresh_token)
                if new_data and new_data.get("access_token"):
                    return await delete_shopify_product(shop_domain, new_data["access_token"], shopify_product_id, new_data.get("refresh_token"))
                return False
            res.raise_for_status()
            data = res.json()
        if "errors" in data or data.get("data", {}).get("productDelete", {}).get("userErrors"): return False
        return bool(data.get("data", {}).get("productDelete", {}).get("deletedProductId"))
    except Exception: return False

async def get_shopify_product_by_sku(shop: str, access_token: str, sku: str) -> Optional[str]:
    query = """query getProductBySku($query: String!) { products(first: 1, query: $query) { edges { node { id title status variants(first: 1) { edges { node { id inventoryItem { id } } } } } } } }"""
    result = await shopify_graphql(shop, access_token, query, {"query": f"sku:{sku}"})
    edges = result.get("data", {}).get("products", {}).get("edges", [])
    return edges[0]["node"]["id"] if edges else None
