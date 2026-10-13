# ============================================
# app/services/shopify/product_core.py
# Product create (simple + variants) + delete + search
# ============================================

import logging
from typing import Optional

from app.services.shopify_helpers import (
    shopify_graphql,
    _build_shopify_tags,
    _get_product_type,
)
from app.services.shopify_taxonomy import find_best_category
from app.services.shopify_inventory import set_inventory_quantity
from app.services.shopify.metafields import (
    _build_all_metafields,
    set_product_metafields,
)
from app.services.shopify.description import _build_description_with_metafields
from app.services.shopify.product_extras import (
    publish_product_to_channels,
    add_product_images,
)
from app.services.shopify.product_variants import (
    update_variant_with_tracked,
)

logger = logging.getLogger(__name__)


# ============================================
# ✅ PRODUCT CREATE (SIMPLE)
# ============================================
async def create_shopify_product(
    shop: str,
    access_token: str,
    product_data: dict,
) -> dict:
    is_available = product_data.get("is_available", True)
    status = "ACTIVE" if is_available else "DRAFT"

    price_float = 0.0
    try:
        price_float = float(product_data.get("price", 0) or 0)
    except (ValueError, TypeError):
        price_float = 0.0

    asin_value = str(product_data.get("asin", "") or "").strip()
    if not asin_value or asin_value == "None":
        asin_value = "NO-SKU"

    metafields_input = _build_all_metafields(product_data)

    shopify_tags = _build_shopify_tags(product_data)
    product_type = _get_product_type(product_data)

    categories = product_data.get("categories") or []
    product_title = product_data.get("title", "")

    shopify_category_id = None
    if product_title or categories:
        shopify_category_id = await find_best_category(
            shop=shop,
            access_token=access_token,
            product_title=product_title,
            categories=categories,
        )

    description_html = _build_description_with_metafields(product_data)

    input_data = {
        "title": product_data.get("title") or "Untitled Product",
        "descriptionHtml": description_html,
        "vendor": product_data.get("brand", ""),
        "status": status,
    }

    if shopify_tags:
        input_data["tags"] = shopify_tags

    if product_type:
        input_data["productType"] = product_type

    if shopify_category_id:
        input_data["category"] = shopify_category_id

    variant_attrs = product_data.get("variant_attributes") or []
    product_options = []
    variant_values = []

    for attr in variant_attrs:
        if not isinstance(attr, dict):
            continue
        name = (attr.get("name") or "").strip()
        value = (attr.get("value") or "").strip()
        if name.lower() in ("color", "size") and value:
            product_options.append({"name": name, "values": [{"name": value}]})
            variant_values.append({"optionName": name, "name": value})

    if product_options and variant_values:
        input_data["productOptions"] = product_options
        input_data["variants"] = [
            {
                "optionValues": variant_values,
                "price": str(price_float or 0),
                "inventoryItem": {
                    "sku": asin_value,
                    "tracked": True,
                },
            }
        ]
        logger.info(
            f"   Adding variant: "
            + " / ".join(f"{v['optionName']}={v['name']}" for v in variant_values)
        )
    else:
        logger.info("   No variant options — Shopify will create default variant")

    mutation_create = """
    mutation productSet($input: ProductSetInput!) {
      productSet(input: $input) {
        product {
          id title handle tags productType
          category { id name fullName }
          options { id name values }
          variants(first: 5) {
            edges {
              node {
                id
                title
                price
                inventoryItem { id sku tracked }
              }
            }
          }
        }
        userErrors { field message }
      }
    }
    """

    result = await shopify_graphql(
        shop, access_token, mutation_create, {"input": input_data}
    )

    if "errors" in result:
        logger.error(f"❌ Product create error: {result['errors']}")
        return result

    product_create = result.get("data", {}).get("productSet", {})
    user_errors = product_create.get("userErrors", [])

    if user_errors:
        logger.error(f"❌ Product user errors: {user_errors}")
        return result

    shopify_product = product_create.get("product", {})
    product_id = shopify_product.get("id")

    logger.info(f"✅ Product created: {shopify_product.get('title')}")

    if product_id:
        await publish_product_to_channels(
            shop=shop,
            access_token=access_token,
            shopify_product_id=product_id,
        )

    if product_id and metafields_input:
        await set_product_metafields(
            shop=shop,
            access_token=access_token,
            product_id=product_id,
            metafields=metafields_input,
        )

    variants_edges = shopify_product.get("variants", {}).get("edges", [])

    if variants_edges:
        variant_node = variants_edges[0]["node"]
        variant_id = variant_node.get("id")
        inventory_item_id = variant_node.get("inventoryItem", {}).get("id")

        if product_id and variant_id:
            compare_price = None
            if price_float and price_float > 0:
                compare_price = round(price_float * 1.2, 2)

            await update_variant_with_tracked(
                shop=shop,
                access_token=access_token,
                product_id=product_id,
                variant_id=variant_id,
                price=price_float,
                sku=asin_value,
                compare_at_price=compare_price,
            )

        if inventory_item_id:
            stock_qty = product_data.get("stock_quantity", 0)
            if stock_qty == 0 and is_available:
                stock_qty = 100

            await set_inventory_quantity(
                shop=shop,
                access_token=access_token,
                inventory_item_id=inventory_item_id,
                quantity=stock_qty,
            )

    images = product_data.get("images", [])
    if product_id and images:
        await add_product_images(
            shop=shop,
            access_token=access_token,
            product_id=product_id,
            image_urls=images[:10],
        )

    return result


# ============================================
# CREATE PRODUCT WITH VARIANTS
# ============================================
async def create_shopify_product_with_variants(
    shop: str,
    access_token: str,
    product_data: dict,
    variants: list,
) -> dict:
    is_available = product_data.get("is_available", True)
    status = "ACTIVE" if is_available else "DRAFT"

    shopify_tags = _build_shopify_tags(product_data)
    product_type = _get_product_type(product_data)

    categories = product_data.get("categories") or []
    product_title = product_data.get("title", "")

    shopify_category_id = None
    if product_title or categories:
        shopify_category_id = await find_best_category(
            shop=shop,
            access_token=access_token,
            product_title=product_title,
            categories=categories,
        )

    input_data = {
        "title": product_data.get("title") or "Untitled Product",
        "descriptionHtml": _build_description_with_metafields(product_data),
        "vendor": product_data.get("brand", ""),
        "status": status,
        "productOptions": [
            {
                "name": "Style",
                "values": [
                    {"name": v["title"]} for v in variants if v.get("title")
                ] or [{"name": "Default"}],
            }
        ],
    }

    if shopify_tags:
        input_data["tags"] = shopify_tags

    if product_type:
        input_data["productType"] = product_type

    if shopify_category_id:
        input_data["category"] = shopify_category_id

    mutation_create = """
    mutation productSet($input: ProductSetInput!) {
      productSet(input: $input) {
        product {
          id title handle tags productType
          category { id name fullName }
          options { id name values }
          variants(first: 50) {
            edges { node { id title price inventoryItem { id sku tracked } } }
          }
        }
        userErrors { field message }
      }
    }
    """

    result = await shopify_graphql(
        shop, access_token, mutation_create, {"input": input_data}
    )

    if "errors" in result:
        logger.error(f"❌ Product create error: {result['errors']}")
        return result

    product_create = result.get("data", {}).get("productSet", {})
    user_errors = product_create.get("userErrors", [])

    if user_errors:
        logger.error(f"❌ Product user errors: {user_errors}")
        return result

    shopify_product = product_create.get("product", {})
    product_id = shopify_product.get("id")

    logger.info(f"✅ Product created: {shopify_product.get('title')}")

    if product_id:
        await publish_product_to_channels(
            shop=shop,
            access_token=access_token,
            shopify_product_id=product_id,
        )

    if product_id:
        all_mfs = _build_all_metafields(product_data)
        if all_mfs:
            await set_product_metafields(
                shop=shop,
                access_token=access_token,
                product_id=product_id,
                metafields=all_mfs,
            )

    images = product_data.get("images", [])
    if product_id and images:
        await add_product_images(
            shop=shop,
            access_token=access_token,
            product_id=product_id,
            image_urls=images[:10],
        )

    return result


# ============================================
# DELETE SHOPIFY PRODUCT
# ============================================
async def delete_shopify_product(
    shop_domain: str,
    access_token: str,
    shopify_product_id: str,
    refresh_token: Optional[str] = None,
) -> bool:
    if not all([shop_domain, access_token, shopify_product_id]):
        logger.warning("Shopify delete skipped: missing config")
        return False

    if not str(shopify_product_id).startswith("gid://"):
        product_gid = f"gid://shopify/Product/{shopify_product_id}"
    else:
        product_gid = shopify_product_id

    from app.services.shopify_helpers import _safe_api_version
    import httpx

    api_version = _safe_api_version()
    api_url = f"https://{shop_domain}/admin/api/{api_version}/graphql.json"

    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }

    mutation = """
    mutation productDelete($input: ProductDeleteInput!) {
      productDelete(input: $input) {
        deletedProductId
        userErrors { field message }
      }
    }
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                api_url,
                headers=headers,
                json={"query": mutation, "variables": {"input": {"id": product_gid}}},
            )

            if res.status_code in (401, 403):
                if refresh_token:
                    logger.warning(f"🔄 {res.status_code} — refreshing token")
                    from app.services.shopify_auth import refresh_shopify_token
                    new_data = await refresh_shopify_token(shop_domain, refresh_token)
                    if new_data and new_data.get("access_token"):
                        return await delete_shopify_product(
                            shop_domain=shop_domain,
                            access_token=new_data["access_token"],
                            shopify_product_id=shopify_product_id,
                            refresh_token=new_data.get("refresh_token"),
                        )
                logger.error(f"❌ {res.status_code} Unauthorized")
                return False

            res.raise_for_status()
            data = res.json()

        if "errors" in data:
            logger.error(f"❌ Shopify delete errors: {data['errors']}")
            return False

        delete_data = data.get("data", {}).get("productDelete", {})
        user_errors = delete_data.get("userErrors", [])

        if user_errors:
            logger.error(f"❌ Shopify delete user errors: {user_errors}")
            return False

        deleted_id = delete_data.get("deletedProductId")
        if deleted_id:
            logger.info(f"✅ Shopify product deleted: {deleted_id}")
            return True

        return False

    except Exception as e:
        logger.error(f"❌ Shopify delete failed: {e}")
        return False


# ============================================
# SHOPIFY PRODUCT BY SKU
# ============================================
async def get_shopify_product_by_sku(
    shop: str,
    access_token: str,
    sku: str,
) -> Optional[str]:
    query = """
    query getProductBySku($query: String!) {
      products(first: 1, query: $query) {
        edges {
          node {
            id title status
            variants(first: 1) {
              edges { node { id inventoryItem { id } } }
            }
          }
        }
      }
    }
    """

    result = await shopify_graphql(shop, access_token, query, {"query": f"sku:{sku}"})

    if "errors" in result:
        logger.error(f"SKU search errors: {result['errors']}")
        return None

    edges = result.get("data", {}).get("products", {}).get("edges", [])

    if edges:
        product_gid = edges[0]["node"]["id"]
        logger.info(f"Found Shopify product: {product_gid} for SKU={sku}")
        return product_gid

    logger.warning(f"No Shopify product found for SKU={sku}")
    return None