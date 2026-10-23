# ============================================
# app/services/shopify/product_core.py
# Product create (simple + variants) + delete + search
# + ✅ NAYA: Weight mapping to Shopify variant
# + ✅ NAYA v2: Compare-at price store settings se aata hai
# + ✅ NAYA v3: 4 rule types support (none/amazon/fixed/percent)
# + ✅ FIXED v6: Out-of-stock product add hoga, lekin stock 0 hoga (ACTIVE/DRAFT fix)
# + ✅ FIXED v7: Category & Tags explicitly update honge
# + ✅ FIXED v8: Taxonomy fallback (agar category na mile toh "Toys & Games" set karein)
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
# ✅ NAYA v7: Category & Tags ko explicitly update karo
# ============================================
async def _update_product_category_and_tags(
    shop: str,
    access_token: str,
    product_id: str,
    category_id: str,
    tags: list,
):
    """Shopify mein category aur tags ko explicitly update karta hai."""
    
    # 1. Category Update (productUpdate)
    if category_id:
        cat_mutation = """
        mutation productUpdate($input: ProductInput!) {
          productUpdate(input: $input) {
            product { id category { id name } }
            userErrors { field message }
          }
        }
        """
        cat_result = await shopify_graphql(
            shop, access_token, cat_mutation, 
            {"input": {"id": product_id, "category": category_id}}
        )
        if "errors" in cat_result or cat_result.get("data", {}).get("productUpdate", {}).get("userErrors"):
            logger.warning(f"⚠️ Category update failed: {cat_result}")

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
# ✅ NAYA v3: Compare-at price calculate karo
# ============================================
def calculate_compare_at_price(
    final_price: float,
    compare_at_type: str,
    compare_at_value: float,
    amazon_price: float = None,
) -> Optional[float]:
    """Compare-at price calculate karo."""
    if compare_at_type == "none":
        return None

    if compare_at_type == "amazon":
        if amazon_price is None:
            logger.warning("⚠️ amazon rule selected but no amazon_price")
            return None

        compare_price = round(float(amazon_price), 2)

        if compare_price <= final_price:
            logger.warning(
                f"⚠️ Amazon price (${compare_price}) <= final price "
                f"(${final_price}) — skipping compare_at"
            )
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
            logger.warning(
                f"⚠️ Unknown compare_at_type: {compare_at_type} — skipping"
            )
            return None

        compare_price = round(compare_price, 2)

        if compare_price <= final_price:
            logger.warning(
                f"⚠️ Compare price (${compare_price}) <= final price "
                f"(${final_price}) — skipping"
            )
            return None

        return compare_price

    except (ValueError, TypeError) as e:
        logger.error(f"❌ Compare price calc error: {e}")
        return None


# ============================================
# ✅ NAYA v3: Store ki compare-at settings fetch karo
# ============================================
def _get_compare_at_settings_from_store(
    shop: str,
) -> tuple:
    """Store ki compare-at settings fetch karo (DB se)."""
    db: Session = SessionLocal()
    try:
        store = db.query(ShopifyStore).filter(
            ShopifyStore.shop_domain == shop
        ).first()

        if not store:
            logger.warning(f"⚠️ Store not found in DB: {shop}")
            return False, "none", 0.0

        rule = getattr(store, "default_compare_at_rule", None)

        if not rule:
            enabled_old = bool(
                getattr(store, "default_compare_at_enabled", False)
            )
            type_old = (
                getattr(store, "default_compare_at_type", None) or "percent"
            )

            if not enabled_old:
                rule = "none"
            elif type_old == "amazon":
                rule = "amazon"
            elif type_old == "fixed":
                rule = "fixed"
            else:
                rule = "percent"

        compare_value = float(
            getattr(store, "default_compare_at_value", None) or 0.0
        )

        enabled = rule != "none"

        logger.info(
            f"   💰 Compare-at rule: rule={rule}, "
            f"enabled={enabled}, value={compare_value}"
        )

        return enabled, rule, compare_value

    except Exception as e:
        logger.error(f"❌ Failed to fetch compare-at settings: {e}")
        return False, "none", 0.0
    finally:
        db.close()


# ============================================
# ✅ NAYA: Parse weight string → (value, unit)
# ============================================
def _parse_weight(weight_str) -> tuple:
    """Parse weight string like '1.5 pounds', '680 g', etc."""
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
        unit = "POUNDS"
    elif "gram" in s or " g" in s or s.endswith("g"):
        value = value * 0.00220462
        unit = "POUNDS"
    elif "ounce" in s or " oz" in s or s.endswith("oz"):
        value = value * 0.0625
        unit = "POUNDS"
    elif "milligram" in s or " mg" in s:
        value = value * 0.00000220462
        unit = "POUNDS"
    elif "pound" in s or " lb" in s or s.endswith("lb"):
        unit = "POUNDS"
    else:
        unit = "POUNDS"

    return round(value, 4), unit


# ============================================
# ✅ NAYA: Build inventoryItem with weight
# ============================================
def _build_inventory_item(product_data: dict, sku: str) -> dict:
    """Build inventoryItem dict with SKU, tracked, and weight."""
    inventory_item = {
        "sku": sku,
        "tracked": True, # ✅ Shopify ko batata hai ke stock track karo
    }

    weight_str = (
        product_data.get("item_weight")
        or product_data.get("package_weight")
        or product_data.get("shipping_weight")
    )

    weight_value, weight_unit = _parse_weight(weight_str)

    if weight_value and weight_value > 0:
        inventory_item["measurement"] = {
            "weight": {
                "value": weight_value,
                "unit": weight_unit,
            }
        }
        logger.info(
            f"   ⚖️ Weight mapped: {weight_str} → {weight_value} {weight_unit}"
        )

    return inventory_item


# ============================================
# ✅ PRODUCT CREATE (SIMPLE)
# ✅ FIXED v8: Out-of-stock = 0, Category fallback
# ============================================
async def create_shopify_product(
    shop: str,
    access_token: str,
    product_data: dict,
) -> dict:
    is_available = product_data.get("is_available", False)
    
    # ✅ FIXED: Agar Out of Stock hai toh DRAFT karein (taake 1000 stock ke sath live na ho)
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
    
    # ✅ FIXED v8: Fallback Category (Agar Shopify taxonomy match na ho)
    if not shopify_category_id:
        logger.warning("⚠️ Taxonomy match failed. Using default 'Toys & Games' category.")
        shopify_category_id = "gid://shopify/TaxonomyCategory/toys-games"

    description_html = _build_description_with_metafields(product_data)

    compare_enabled, compare_rule, compare_value = (
        _get_compare_at_settings_from_store(shop)
    )

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

    if product_type:
        input_data["productType"] = product_type

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
            logger.info(
                f"   💰 Compare-at price: ${compare_at_price} (rule={compare_rule})"
            )

        input_data["variants"] = [variant_input]
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
                compareAtPrice
                inventoryItem {
                  id
                  sku
                  tracked
                  measurement {
                    weight { value unit }
                  }
                }
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

    # ✅ FIXED v7: Category aur Tags explicitly update karein
    if product_id:
        await _update_product_category_and_tags(
            shop=shop,
            access_token=access_token,
            product_id=product_id,
            category_id=shopify_category_id,
            tags=shopify_tags
        )

    if product_id and is_available:
        # Sirf tab publish karein jab product available ho
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
            await update_variant_with_tracked(
                shop=shop,
                access_token=access_token,
                product_id=product_id,
                variant_id=variant_id,
                price=price_float,
                sku=asin_value,
                compare_at_price=compare_at_price,
            )

        if inventory_item_id:
            # ✅ FIXED v6: Agar product available nahi hai to stock 0
            if not is_available:
                stock_qty = 0
            else:
                stock_qty = product_data.get("stock_quantity", 0)

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
# ✅ FIXED v8: Out-of-stock = 0, Category fallback
# ============================================
async def create_shopify_product_with_variants(
    shop: str,
    access_token: str,
    product_data: dict,
    variants: list,
) -> dict:
    is_available = product_data.get("is_available", False)
    
    # ✅ FIXED: Out of stock product ko DRAFT rakhein
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

    # ✅ FIXED v8: Fallback Category
    if not shopify_category_id:
        shopify_category_id = "gid://shopify/TaxonomyCategory/toys-games"

    asin_value = str(product_data.get("asin", "") or "").strip() or "NO-SKU"

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

    if product_type:
        input_data["productType"] = product_type

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

    # ✅ FIXED v7: Category aur Tags explicitly update karein
    if product_id:
        await _update_product_category_and_tags(
            shop=shop,
            access_token=access_token,
            product_id=product_id,
            category_id=shopify_category_id,
            tags=shopify_tags
        )

    if product_id and is_available:
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

    # ✅ FIXED v6: Inventory set karo har variant ke liye (OOS = 0)
    variants_edges = shopify_product.get("variants", {}).get("edges", [])
    if variants_edges:
        if not is_available:
            stock_qty = 0
        else:
            stock_qty = product_data.get("stock_quantity", 0)

        for edge in variants_edges:
            variant_node = edge.get("node", {})
            inventory_item_id = variant_node.get("inventoryItem", {}).get("id")
            if inventory_item_id:
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