# ============================================
# app/services/shopify/product_core.py
# + ✅ FIXED v12: Category Update (productUpdate with 'category' field)
# ============================================

import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import ShopifyStore
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
# ✅ FIXED: Shopify se asli Category ID fetch karo
# ============================================
async def _get_default_category_id(shop: str, access_token: str) -> Optional[str]:
    query = """
    query {
      taxonomy {
        categories(first: 5, search: "Toys & Games") {
          edges {
            node {
              id
              name
            }
          }
        }
      }
    }
    """
    try:
        result = await shopify_graphql(shop, access_token, query)
        edges = result.get("data", {}).get("taxonomy", {}).get("categories", {}).get("edges", [])
        if edges:
            return edges[0]["node"]["id"]
    except Exception as e:
        logger.error(f"❌ Failed to fetch default category ID: {e}")
    
    return "gid://shopify/TaxonomyCategory/tg"


# ============================================
# ✅ FIXED: Category, Type & Tags explicitly update karo
# ============================================
async def _update_product_details(
    shop: str,
    access_token: str,
    product_id: str,
    category_id: str,
    product_type: str,
    tags: list,
):
    """Shopify mein category, type aur tags ko explicitly update karta hai."""
    
    # 1. Product Update (Category + ProductType)
    # ✅ SAHI FIELDS: 'category' aur 'productType'
    if category_id or product_type:
        update_input = {"id": product_id}
        
        if category_id:
            update_input["category"] = category_id
            
        if product_type:
            update_input["productType"] = product_type

        cat_mutation = """
        mutation productUpdate($input: ProductInput!) {
          productUpdate(input: $input) {
            product { id category { id name } productType }
            userErrors { field message }
          }
        }
        """
        cat_result = await shopify_graphql(
            shop, access_token, cat_mutation, 
            {"input": update_input}
        )
        if "errors" in cat_result or cat_result.get("data", {}).get("productUpdate", {}).get("userErrors"):
            logger.warning(f"⚠️ Product type/category update failed: {cat_result}")

    # 2. Tags Update (tagsAdd)
    if tags:
        tags_mutation = """
        mutation tagsAdd($id: ID!, $tags: [String!]!) {
          tagsAdd(id: $id, tags: $tags) {
            node { id }
            userErrors { field message }
          }
        }
        """
        tags_result = await shopify_graphql(
            shop, access_token, tags_mutation, 
            {"id": product_id, "tags": tags}
        )
        if "errors" in tags_result or tags_result.get("data", {}).get("tagsAdd", {}).get("userErrors"):
            logger.warning(f"⚠️ Tags update failed: {tags_result}")


# ============================================
# Compare-at price calculate karo
# ============================================
def calculate_compare_at_price(
    final_price: float,
    compare_at_type: str,
    compare_at_value: float,
    amazon_price: float = None,
) -> Optional[float]:
    if compare_at_type == "none":
        return None

    if compare_at_type == "amazon":
        if amazon_price is None:
            return None
        compare_price = round(float(amazon_price), 2)
        if compare_price <= final_price:
            return None
        return compare_price

    if not final_price or final_price <= 0:
        return None

    if not compare_at_value or compare_at_value <= 0:
        return None

    try:
        if compare_at_type == "percent":
            compare_price = final_price * (1 + compare_at_value / 100)
        elif compare_at_type == "fixed":
            compare_price = final_price + compare_at_value
        else:
            return None

        compare_price = round(compare_price, 2)
        if compare_price <= final_price:
            return None
        return compare_price

    except (ValueError, TypeError):
        return None


# ============================================
# Store ki compare-at settings fetch karo
# ============================================
def _get_compare_at_settings_from_store(shop: str) -> tuple:
    db: Session = SessionLocal()
    try:
        store = db.query(ShopifyStore).filter(ShopifyStore.shop_domain == shop).first()
        if not store:
            return False, "none", 0.0

        rule = getattr(store, "default_compare_at_rule", None)
        if not rule:
            enabled_old = bool(getattr(store, "default_compare_at_enabled", False))
            type_old = (getattr(store, "default_compare_at_type", None) or "percent")

            if not enabled_old:
                rule = "none"
            elif type_old == "amazon":
                rule = "amazon"
            elif type_old == "fixed":
                rule = "fixed"
            else:
                rule = "percent"

        compare_value = float(getattr(store, "default_compare_at_value", None) or 0.0)
        enabled = rule != "none"
        return enabled, rule, compare_value

    except Exception:
        return False, "none", 0.0
    finally:
        db.close()


# ============================================
# Parse weight string → (value, unit)
# ============================================
def _parse_weight(weight_str) -> tuple:
    if not weight_str:
        return None, None

    s = str(weight_str).strip().lower()
    if not s or s == "none":
        return None, None

    match = re.search(r"([\d.]+)", s)
    if not match:
        return None, None

    try:
        value = float(match.group(1))
    except ValueError:
        return None, None

    if "kg" in s or "kilogram" in s:
        value = value * 2.20462
    elif "gram" in s or " g" in s or s.endswith("g"):
        value = value * 0.00220462
    elif "ounce" in s or " oz" in s or s.endswith("oz"):
        value = value * 0.0625
    elif "milligram" in s or " mg" in s:
        value = value * 0.00000220462

    return round(value, 4), "POUNDS"


# ============================================
# Build inventoryItem with weight
# ============================================
def _build_inventory_item(product_data: dict, sku: str) -> dict:
    inventory_item = {
        "sku": sku,
        "tracked": True,
    }
    weight_str = (
        product_data.get("item_weight")
        or product_data.get("package_weight")
        or product_data.get("shipping_weight")
    )
    weight_value, weight_unit = _parse_weight(weight_str)
    if weight_value and weight_value > 0:
        inventory_item["measurement"] = {
            "weight": {"value": weight_value, "unit": weight_unit}
        }
    return inventory_item


# ============================================
# ✅ PRODUCT CREATE (SIMPLE)
# ============================================
async def create_shopify_product(
    shop: str,
    access_token: str,
    product_data: dict,
) -> dict:
    is_available = product_data.get("is_available", False)
    status = "ACTIVE" if is_available else "DRAFT"
    
    if not is_available:
        logger.warning("⚠️ Product is OUT OF STOCK. Setting status to DRAFT and stock to 0.")

    price_float = 0.0
    try:
        price_float = float(product_data.get("price", 0) or 0)
    except (ValueError, TypeError):
        price_float = 0.0

    amazon_price_float = None
    try:
        ap = product_data.get("amazon_price")
        if ap is not None:
            amazon_price_float = float(ap)
    except (ValueError, TypeError):
        amazon_price_float = None

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
    
    if not shopify_category_id:
        logger.warning("⚠️ Taxonomy match failed. Fetching default 'Toys & Games' ID.")
        shopify_category_id = await _get_default_category_id(shop, access_token)

    if not product_type:
        product_type = "General"

    description_html = _build_description_with_metafields(product_data)

    compare_enabled, compare_rule, compare_value = _get_compare_at_settings_from_store(shop)

    compare_at_price = None
    if compare_enabled:
        compare_at_price = calculate_compare_at_price(
            final_price=price_float,
            compare_at_type=compare_rule,
            compare_at_value=compare_value,
            amazon_price=amazon_price_float,
        )

    input_data = {
        "title": product_data.get("title") or "Untitled Product",
        "descriptionHtml": description_html,
        "vendor": product_data.get("brand", ""),
        "status": status,
    }

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
        variant_input = {
            "optionValues": variant_values,
            "price": str(price_float or 0),
            "inventoryItem": _build_inventory_item(product_data, asin_value),
        }
        if compare_at_price:
            variant_input["compareAtPrice"] = str(compare_at_price)
        input_data["variants"] = [variant_input]
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
                id title price compareAtPrice
                inventoryItem { id sku tracked measurement { weight { value unit } } }
              }
            }
          }
        }
        userErrors { field message }
      }
    }
    """

    result = await shopify_graphql(shop, access_token, mutation_create, {"input": input_data})

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

    # ✅ Category, Type aur Tags explicitly update karein
    if product_id:
        await _update_product_details(
            shop=shop,
            access_token=access_token,
            product_id=product_id,
            category_id=shopify_category_id,
            product_type=product_type,
            tags=shopify_tags
        )

    if product_id and is_available:
        await publish_product_to_channels(
            shop=shop, access_token=access_token, shopify_product_id=product_id,
        )

    if product_id and metafields_input:
        await set_product_metafields(
            shop=shop, access_token=access_token, product_id=product_id, metafields=metafields_input,
        )

    variants_edges = shopify_product.get("variants", {}).get("edges", [])

    if variants_edges:
        variant_node = variants_edges[0]["node"]
        variant_id = variant_node.get("id")
        inventory_item_id = variant_node.get("inventoryItem", {}).get("id")

        if product_id and variant_id:
            await update_variant_with_tracked(
                shop=shop, access_token=access_token, product_id=product_id,
                variant_id=variant_id, price=price_float, sku=asin_value, compare_at_price=compare_at_price,
            )

        if inventory_item_id:
            stock_qty = 0 if not is_available else product_data.get("stock_quantity", 0)
            await set_inventory_quantity(
                shop=shop, access_token=access_token, inventory_item_id=inventory_item_id, quantity=stock_qty,
            )

    images = product_data.get("images", [])
    if product_id and images:
        await add_product_images(
            shop=shop, access_token=access_token, product_id=product_id, image_urls=images[:10],
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
    is_available = product_data.get("is_available", False)
    status = "ACTIVE" if is_available else "DRAFT"

    shopify_tags = _build_shopify_tags(product_data)
    product_type = _get_product_type(product_data)

    categories = product_data.get("categories") or []
    product_title = product_data.get("title", "")

    shopify_category_id = None
    if product_title or categories:
        shopify_category_id = await find_best_category(
            shop=shop, access_token=access_token, product_title=product_title, categories=categories,
        )

    if not shopify_category_id:
        shopify_category_id = await _get_default_category_id(shop, access_token)

    if not product_type:
        product_type = "General"

    asin_value = str(product_data.get("asin", "") or "").strip() or "NO-SKU"

    input_data = {
        "title": product_data.get("title") or "Untitled Product",
        "descriptionHtml": _build_description_with_metafields(product_data),
        "vendor": product_data.get("brand", ""),
        "status": status,
        "productOptions": [
            {
                "name": "Style",
                "values": [{"name": v["title"]} for v in variants if v.get("title")] or [{"name": "Default"}],
            }
        ],
    }

    mutation_create = """
    mutation productSet($input: ProductSetInput!) {
      productSet(input: $input) {
        product {
          id title handle tags productType
          category { id name fullName }
          options { id name values }
          variants(first: 50) {
            edges { node { id title price compareAtPrice inventoryItem { id sku tracked } } }
          }
        }
        userErrors { field message }
      }
    }
    """

    result = await shopify_graphql(shop, access_token, mutation_create, {"input": input_data})

    if "errors" in result:
        return result

    product_create = result.get("data", {}).get("productSet", {})
    user_errors = product_create.get("userErrors", [])

    if user_errors:
        return result

    shopify_product = product_create.get("product", {})
    product_id = shopify_product.get("id")

    if product_id:
        await _update_product_details(
            shop=shop, access_token=access_token, product_id=product_id, 
            category_id=shopify_category_id, product_type=product_type, tags=shopify_tags
        )

    if product_id and is_available:
        await publish_product_to_channels(shop=shop, access_token=access_token, shopify_product_id=product_id)

    if product_id:
        all_mfs = _build_all_metafields(product_data)
        if all_mfs:
            await set_product_metafields(shop=shop, access_token=access_token, product_id=product_id, metafields=all_mfs)

    variants_edges = shopify_product.get("variants", {}).get("edges", [])
    if variants_edges:
        stock_qty = 0 if not is_available else product_data.get("stock_quantity", 0)

        for edge in variants_edges:
            variant_node = edge.get("node", {})
            inventory_item_id = variant_node.get("inventoryItem", {}).get("id")
            if inventory_item_id:
                await set_inventory_quantity(
                    shop=shop, access_token=access_token, inventory_item_id=inventory_item_id, quantity=stock_qty,
                )

    images = product_data.get("images", [])
    if product_id and images:
        await add_product_images(shop=shop, access_token=access_token, product_id=product_id, image_urls=images[:10])

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
        return False

    if not str(shopify_product_id).startswith("gid://"):
        product_gid = f"gid://shopify/Product/{shopify_product_id}"
    else:
        product_gid = shopify_product_id

    from app.services.shopify_helpers import _safe_api_version
    import httpx

    api_version = _safe_api_version()
    api_url = f"https://{shop_domain}/admin/api/{api_version}/graphql.json"

    headers = {"X-Shopify-Access-Token": access_token, "Content-Type": "application/json"}
    mutation = """
    mutation productDelete($input: ProductDeleteInput!) {
      productDelete(input: $input) { deletedProductId userErrors { field message } }
    }
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(api_url, headers=headers, json={"query": mutation, "variables": {"input": {"id": product_gid}}})

            if res.status_code in (401, 403) and refresh_token:
                from app.services.shopify_auth import refresh_shopify_token
                new_data = await refresh_shopify_token(shop_domain, refresh_token)
                if new_data and new_data.get("access_token"):
                    return await delete_shopify_product(shop_domain, new_data["access_token"], shopify_product_id, new_data.get("refresh_token"))
                return False

            res.raise_for_status()
            data = res.json()

        if "errors" in data or data.get("data", {}).get("productDelete", {}).get("userErrors"):
            return False

        return bool(data.get("data", {}).get("productDelete", {}).get("deletedProductId"))
    except Exception:
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
        edges { node { id title status variants(first: 1) { edges { node { id inventoryItem { id } } } } } }
      }
    }
    """

    result = await shopify_graphql(shop, access_token, query, {"query": f"sku:{sku}"})

    if "errors" in result:
        return None

    edges = result.get("data", {}).get("products", {}).get("edges", [])
    if edges:
        return edges[0]["node"]["id"]

    return None