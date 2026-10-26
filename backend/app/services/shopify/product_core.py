# ============================================
# app/services/shopify/product_core.py
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
    _assign_image_to_variant,
    _normalize_compare_at_price,
)

logger = logging.getLogger(__name__)


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


async def _find_category_from_breadcrumbs(
    shop: str,
    access_token: str,
    categories: list,
    product_title: str,
    tags: list = None,
) -> Optional[str]:
    if categories:
        cat_id = await find_best_category(
            shop=shop,
            access_token=access_token,
            product_title=product_title,
            categories=categories,
        )
        
        if cat_id:
            logger.info(f"   ✅ Category matched via breadcrumbs list: {cat_id}")
            return cat_id

    if tags:
        for tag in tags:
            if not isinstance(tag, str) or not tag.strip():
                continue
                
            cat_id = await find_best_category(
                shop=shop,
                access_token=access_token,
                product_title=tag,
                categories=[],
            )
            if cat_id:
                logger.info(f"   ✅ Category matched via tag: '{tag}' -> {cat_id}")
                return cat_id

    logger.warning(f"⚠️ No category found for: {categories}")
    return None


async def create_shopify_product(
    shop: str,
    access_token: str,
    product_data: dict,
) -> dict:
    is_available = bool(product_data.get("is_available", False))
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

    if not product_type:
        title = product_data.get("title") or ""
        if title:
            product_type = title.split()[0][:255]
        else:
            product_type = "General"

    categories = product_data.get("categories") or []
    product_title = product_data.get("title", "")
    tags = product_data.get("tags") or []

    shopify_category_id = await _find_category_from_breadcrumbs(
        shop=shop,
        access_token=access_token,
        categories=categories,
        product_title=product_title,
        tags=tags
    )

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
        "productType": product_type,
    }

    if shopify_category_id:
        input_data["category"] = shopify_category_id

    if shopify_tags:
        input_data["tags"] = shopify_tags

    # ✅ Product options set karein (Color, Size)
    variant_attrs = product_data.get("variant_attributes") or []
    product_options = []
    variant_values = []

    for attr in variant_attrs:
        if not isinstance(attr, dict):
            continue
        name = (attr.get("name") or "").strip()
        value = (attr.get("value") or "").strip()
        if name and value:
            # Check karein ke option pehle se list mein na ho
            existing_opt = next((opt for opt in product_options if opt["name"] == name), None)
            if existing_opt:
                if value not in [v["name"] for v in existing_opt["values"]]:
                    existing_opt["values"].append({"name": value})
            else:
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
            stock_qty = 0 if not is_available else int(product_data.get("stock_quantity", 0) or 0)
            await set_inventory_quantity(
                shop=shop, access_token=access_token, inventory_item_id=inventory_item_id, quantity=stock_qty,
            )

    images = product_data.get("images", [])
    if product_id and images:
        await add_product_images(
            shop=shop, access_token=access_token, product_id=product_id, image_urls=images[:10],
        )

    return result


async def create_shopify_product_with_variants(
    shop: str,
    access_token: str,
    product_data: dict,
    variants: list,
) -> dict:
    is_available = bool(product_data.get("is_available", False))
    status = "ACTIVE" if is_available else "DRAFT"

    shopify_tags = _build_shopify_tags(product_data)
    product_type = _get_product_type(product_data)

    if not product_type:
        title = product_data.get("title") or ""
        if title:
            product_type = title.split()[0][:255]
        else:
            product_type = "General"

    categories = product_data.get("categories") or []
    product_title = product_data.get("title", "")
    tags = product_data.get("tags") or []

    shopify_category_id = await _find_category_from_breadcrumbs(
        shop=shop,
        access_token=access_token,
        categories=categories,
        product_title=product_title,
        tags=tags
    )

    compare_enabled, compare_rule, compare_value = _get_compare_at_settings_from_store(shop)

    # 1. Option names collect karein (Shopify limit: max 3 options)
    raw_option_names = []
    for v in variants:
        for opt in (v.get("options") or v.get("variant_attributes") or []):
            if isinstance(opt, dict):
                n = (opt.get("name") or opt.get("key") or "").strip()
                if n and n not in raw_option_names:
                    raw_option_names.append(n)

    if not raw_option_names and product_data.get("variant_attributes"):
        for opt in product_data["variant_attributes"]:
            if isinstance(opt, dict):
                n = (opt.get("name") or opt.get("key") or "").strip()
                if n and n not in raw_option_names:
                    raw_option_names.append(n)

    option_names = raw_option_names[:3] if raw_option_names else ["Style"]

    # 2. Collect unique values for each option
    options_dict = {name: [] for name in option_names}
    for v in variants:
        v_opts = {
            (opt.get("name") or opt.get("key") or "").strip(): str(opt.get("value") or "").strip()
            for opt in (v.get("options") or v.get("variant_attributes") or [])
            if isinstance(opt, dict)
        }
        for name in option_names:
            val = v_opts.get(name) or v.get("title") or "Default"
            if val not in options_dict[name]:
                options_dict[name].append(val)

    for name in option_names:
        if not options_dict[name]:
            options_dict[name].append("Default")

    product_options_input = [
        {"name": name, "values": [{"name": val} for val in options_dict[name]]}
        for name in option_names
    ]

    # 3. Build variants array
    variant_inputs = []
    seen_combinations = set()

    for idx, v in enumerate(variants):
        v_asin = str(v.get("asin") or v.get("sku") or f"VAR-{idx+1}").strip()
        try:
            v_price = float(v.get("price") or product_data.get("price") or 0.0)
        except (ValueError, TypeError):
            v_price = 0.0

        v_ap = v.get("amazon_price") or product_data.get("amazon_price")
        v_cap = v.get("compare_at_price")
        if v_cap is None and compare_enabled:
            v_cap = calculate_compare_at_price(
                final_price=v_price,
                compare_at_type=compare_rule,
                compare_at_value=compare_value,
                amazon_price=float(v_ap) if v_ap is not None else None,
            )

        v_opts = {
            (opt.get("name") or opt.get("key") or "").strip(): str(opt.get("value") or "").strip()
            for opt in (v.get("options") or v.get("variant_attributes") or [])
            if isinstance(opt, dict)
        }

        option_values_list = []
        combo_parts = []
        for name in option_names:
            val = v_opts.get(name) or v.get("title") or "Default"
            option_values_list.append({"optionName": name, "name": val})
            combo_parts.append(f"{name}:{val}")

        combo_str = " | ".join(combo_parts)
        if combo_str in seen_combinations:
            disambiguated = f"{option_values_list[-1]['name']} ({v_asin})"
            option_values_list[-1]["name"] = disambiguated
            if disambiguated not in [od["name"] for od in product_options_input[-1]["values"]]:
                product_options_input[-1]["values"].append({"name": disambiguated})
            combo_str = f"{combo_str} ({v_asin})"

        seen_combinations.add(combo_str)

        inventory_item_data = _build_inventory_item(
            {"item_weight": v.get("weight") or product_data.get("item_weight")},
            v_asin
        )

        var_input = {
            "optionValues": option_values_list,
            "price": f"{v_price:.2f}",
            "inventoryItem": inventory_item_data,
            "metafields": [
                {
                    "namespace": "custom",
                    "key": "asin",
                    "value": v_asin,
                    "type": "single_line_text_field",
                }
            ],
        }

        cap_str = _normalize_compare_at_price(v_cap, v_price)
        if cap_str:
            var_input["compareAtPrice"] = cap_str

        variant_inputs.append(var_input)

    # Shopify variant limit (cap at 100)
    if len(variant_inputs) > 100:
        logger.warning(f"⚠️ Total {len(variant_inputs)} variants exceeds Shopify limit 100. Capping at 100.")
        variant_inputs = variant_inputs[:100]

    input_data = {
        "title": product_data.get("title") or "Untitled Product",
        "descriptionHtml": _build_description_with_metafields(product_data),
        "vendor": product_data.get("brand", ""),
        "status": status,
        "productType": product_type,
        "productOptions": product_options_input,
        "variants": variant_inputs,
    }

    if shopify_category_id:
        input_data["category"] = shopify_category_id

    if shopify_tags:
        input_data["tags"] = shopify_tags

    mutation_create = """
    mutation productSet($input: ProductSetInput!) {
      productSet(input: $input) {
        product {
          id title handle tags productType
          category { id name fullName }
          options { id name values }
          variants(first: 100) {
            edges { node { id title price compareAtPrice inventoryItem { id sku tracked } } }
          }
        }
        userErrors { field message }
      }
    }
    """

    result = await shopify_graphql(shop, access_token, mutation_create, {"input": input_data})

    if "errors" in result:
        logger.error(f"❌ Product with variants create error: {result['errors']}")
        return result

    product_create = result.get("data", {}).get("productSet", {})
    user_errors = product_create.get("userErrors", [])

    if user_errors:
        logger.error(f"❌ Product with variants user errors: {user_errors}")
        return result

    shopify_product = product_create.get("product", {})
    product_id = shopify_product.get("id")

    if not product_id:
        return result

    logger.info(f"✅ Product created with {len(variant_inputs)} variants: {shopify_product.get('title')}")

    if is_available:
        await publish_product_to_channels(shop=shop, access_token=access_token, shopify_product_id=product_id)

    all_mfs = _build_all_metafields(product_data)
    if all_mfs:
        await set_product_metafields(shop=shop, access_token=access_token, product_id=product_id, metafields=all_mfs)

    variants_edges = shopify_product.get("variants", {}).get("edges", [])
    created_variants_by_sku = {}
    for edge in variants_edges:
        node = edge.get("node", {})
        sku = node.get("inventoryItem", {}).get("sku")
        if sku:
            created_variants_by_sku[sku] = node

    for idx, v in enumerate(variants):
        v_asin = str(v.get("asin") or v.get("sku") or "").strip()
        v_node = created_variants_by_sku.get(v_asin)
        if not v_node and idx < len(variants_edges):
            v_node = variants_edges[idx].get("node", {})

        if not v_node:
            continue

        inv_item_id = v_node.get("inventoryItem", {}).get("id")
        stock_qty = int(v.get("stock") or product_data.get("stock_quantity", 0) or 0) if is_available else 0
        if inv_item_id and stock_qty:
            await set_inventory_quantity(
                shop=shop, access_token=access_token, inventory_item_id=inv_item_id, quantity=stock_qty,
            )

        v_img = v.get("image_url")
        v_id = v_node.get("id")
        if v_id and v_img:
            await _assign_image_to_variant(shop, access_token, product_id, v_id, v_img)

    images = product_data.get("images", [])
    if images:
        await add_product_images(shop=shop, access_token=access_token, product_id=product_id, image_urls=images[:10])

    return result


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