# ============================================
# app/services/shopify_product.py
# Product create (simple + variants), variant add,
# images, status update, tags update,
# product delete, SKU search
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

logger = logging.getLogger(__name__)


# ============================================
# DELETE SHOPIFY PRODUCT
# ============================================
async def delete_shopify_product(
    shop_domain: str,
    access_token: str,
    shopify_product_id: str,
    refresh_token: Optional[str] = None,
) -> bool:
    """Shopify product delete karo."""
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
        userErrors {
          field
          message
        }
      }
    }
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                api_url,
                headers=headers,
                json={
                    "query": mutation,
                    "variables": {"input": {"id": product_gid}},
                },
            )

            if res.status_code in (401, 403):
                if refresh_token:
                    logger.warning(
                        f"🔄 {res.status_code} — refreshing token for "
                        f"{shop_domain} and retrying..."
                    )
                    from app.services.shopify_auth import refresh_shopify_token
                    new_data = await refresh_shopify_token(
                        shop_domain, refresh_token
                    )
                    if new_data and new_data.get("access_token"):
                        return await delete_shopify_product(
                            shop_domain=shop_domain,
                            access_token=new_data["access_token"],
                            shopify_product_id=shopify_product_id,
                            refresh_token=new_data.get("refresh_token"),
                        )
                logger.error(
                    f"❌ {res.status_code} Unauthorized for {shop_domain}"
                )
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

    except httpx.HTTPStatusError as e:
        logger.error(
            f"❌ Shopify delete HTTP error: {e.response.status_code} — "
            f"{e.response.text[:200]}"
        )
        return False
    except Exception as e:
        logger.error(f"❌ Shopify delete failed: {e}")
        return False


# ============================================
# VARIANT UPDATE WITH TRACKED
# ============================================
async def update_variant_with_tracked(
    shop: str,
    access_token: str,
    product_id: str,
    variant_id: str,
    price: float,
) -> bool:
    mutation = """
    mutation productVariantsBulkUpdate(
      $productId: ID!,
      $variants: [ProductVariantsBulkInput!]!
    ) {
      productVariantsBulkUpdate(
        productId: $productId,
        variants: $variants
      ) {
        productVariants {
          id
          price
          inventoryItem {
            id
            tracked
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "productId": product_id,
        "variants": [
            {
                "id": variant_id,
                "price": str(price),
                "inventoryItem": {
                    "tracked": True,
                },
            }
        ],
    }

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Variant update errors: {result['errors']}")
        return False

    update_errors = (
        result.get("data", {})
        .get("productVariantsBulkUpdate", {})
        .get("userErrors", [])
    )

    if update_errors:
        logger.error(f"❌ Variant update user errors: {update_errors}")
        return False

    updated = (
        result.get("data", {})
        .get("productVariantsBulkUpdate", {})
        .get("productVariants", [])
    )

    if updated:
        v = updated[0]
        logger.info(f"✅ Variant updated: price=${v.get('price')}, "
                    f"tracked={v.get('inventoryItem', {}).get('tracked')}")
        return True

    return False


# ============================================
# SET PRODUCT METAFIELDS
# ============================================
async def set_product_metafields(
    shop: str,
    access_token: str,
    product_id: str,
    metafields: list,
) -> bool:
    if not metafields:
        logger.info("   No metafields to set")
        return True

    mutation = """
    mutation metafieldsSet($metafields: [MetafieldsSetInput!]!) {
      metafieldsSet(metafields: $metafields) {
        metafields {
          id
          namespace
          key
          value
        }
        userErrors {
          field
          message
          code
        }
      }
    }
    """

    metafields_with_owner = [
        {
            "ownerId": product_id,
            "namespace": mf["namespace"],
            "key": mf["key"],
            "value": mf["value"],
            "type": mf["type"],
        }
        for mf in metafields
    ]

    variables = {"metafields": metafields_with_owner}

    logger.info(f"   Setting {len(metafields)} metafields...")

    result = await shopify_graphql(
        shop, access_token, mutation, variables
    )

    if "errors" in result:
        logger.error(f"❌ Metafields set GraphQL errors: {result['errors']}")
        return False

    mf_data = result.get("data", {}).get("metafieldsSet", {})
    user_errors = mf_data.get("userErrors", [])

    if user_errors:
        logger.error(f"❌ Metafields set user errors: {user_errors}")
        return False

    created = mf_data.get("metafields", [])
    logger.info(f"✅ Metafields set successfully: {len(created)}")

    return True


# ============================================
# ENSURE PRODUCT HAS OPTION
# ============================================
async def ensure_product_has_option(
    shop: str,
    access_token: str,
    product_id: str,
    option_name: str,
    option_values: list,
) -> bool:
    query = """
    query getProductOptions($id: ID!) {
      product(id: $id) {
        id
        options {
          id
          name
          values
        }
      }
    }
    """

    result = await shopify_graphql(
        shop, access_token, query, {"id": product_id}
    )

    if "errors" in result:
        logger.error(f"❌ Failed to fetch options: {result['errors']}")
        return False

    product = result.get("data", {}).get("product")
    if not product:
        logger.error(f"❌ Product not found: {product_id}")
        return False

    existing_options = product.get("options", [])
    existing_names = [opt.get("name", "").lower() for opt in existing_options]

    if option_name.lower() in existing_names:
        logger.info(f"   ✅ Option '{option_name}' already exists")
        return True

    logger.info(f"   ➕ Creating option '{option_name}' with values: {option_values}")

    new_options = []

    for opt in existing_options:
        name = opt.get("name", "")
        values = opt.get("values", [])

        if name.lower() == "default title":
            continue

        values_as_dicts = []
        for v in values:
            if isinstance(v, str) and v:
                values_as_dicts.append({"name": v})
            elif isinstance(v, dict) and v.get("name"):
                values_as_dicts.append({"name": v["name"]})

        new_options.append({
            "name": name,
            "values": values_as_dicts,
        })

    new_option_values = []
    for v in option_values:
        if isinstance(v, str) and v:
            new_option_values.append({"name": v})
        elif isinstance(v, dict) and v.get("name"):
            new_option_values.append({"name": v["name"]})

    new_options.append({
        "name": option_name,
        "values": new_option_values,
    })

    mutation = """
    mutation productSet($input: ProductSetInput!) {
      productSet(input: $input) {
        product {
          id
          options {
            id
            name
            values
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "input": {
            "id": product_id,
            "productOptions": new_options,
        }
    }

    update_result = await shopify_graphql(
        shop, access_token, mutation, variables
    )

    if "errors" in update_result:
        logger.error(
            f"❌ Option create errors: {update_result['errors']}"
        )
        return False

    user_errors = (
        update_result.get("data", {})
        .get("productSet", {})
        .get("userErrors", [])
    )

    if user_errors:
        logger.error(f"❌ Option create user errors: {user_errors}")
        return False

    logger.info(f"   ✅ Option '{option_name}' created successfully")
    return True


# ============================================
# EXISTING PRODUCT KE TAGS + TYPE UPDATE KARO
# ============================================
async def update_shopify_product_tags_and_type(
    shop: str,
    access_token: str,
    shopify_product_id: str,
    tags: list[str],
    product_type: str = "",
) -> bool:
    if not shopify_product_id.startswith("gid://"):
        product_gid = f"gid://shopify/Product/{shopify_product_id}"
    else:
        product_gid = shopify_product_id

    mutation = """
    mutation productUpdate($input: ProductInput!) {
      productUpdate(input: $input) {
        product {
          id
          title
          tags
          productType
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    input_data = {
        "id": product_gid,
        "tags": tags,
    }

    if product_type:
        input_data["productType"] = product_type

    variables = {"input": input_data}

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Tags update GraphQL errors: {result['errors']}")
        return False

    update_data = result.get("data", {}).get("productUpdate", {})
    user_errors = update_data.get("userErrors", [])

    if user_errors:
        logger.error(f"❌ Tags update user errors: {user_errors}")
        return False

    updated = update_data.get("product", {})
    logger.info(f"✅ Tags updated: {len(updated.get('tags', []))} tags")
    if updated.get("productType"):
        logger.info(f"   Product type: {updated.get('productType')}")
    return True


# ============================================
# CREATE PRODUCT WITH VARIANTS — productSet
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
        "descriptionHtml": product_data.get("description", ""),
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
        logger.info(f"   Pushing {len(shopify_tags)} tags")

    if product_type:
        input_data["productType"] = product_type
        logger.info(f"   Product type: {product_type}")

    if shopify_category_id:
        input_data["category"] = shopify_category_id
        logger.info(f"   Category: {shopify_category_id}")

    mutation_create = """
    mutation productSet($input: ProductSetInput!) {
      productSet(input: $input) {
        product {
          id
          title
          handle
          tags
          productType
          category {
            id
            name
            fullName
          }
          options {
            id
            name
            values
          }
          variants(first: 50) {
            edges {
              node {
                id
                title
                price
                inventoryItem {
                  id
                  sku
                  tracked
                }
              }
            }
          }
        }
        userErrors {
          field
          message
        }
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
    if shopify_product.get("category"):
        logger.info(f"   Category confirmed: {shopify_product.get('category')}")

    variant_edges = shopify_product.get("variants", {}).get("edges", [])
    variants_to_update = []

    for idx, edge in enumerate(variant_edges):
        if idx >= len(variants):
            break
        shopify_variant = edge["node"]
        our_variant = variants[idx]
        variants_to_update.append({
            "id": shopify_variant["id"],
            "price": str(our_variant.get("price", 0)),
            "inventoryItem": {
                "sku": our_variant.get("sku", ""),
                "tracked": True,
            },
        })

    if variants_to_update:
        mutation_var = """
        mutation productVariantsBulkUpdate(
          $productId: ID!,
          $variants: [ProductVariantsBulkInput!]!
        ) {
          productVariantsBulkUpdate(
            productId: $productId,
            variants: $variants
          ) {
            productVariants {
              id
              title
              price
              inventoryItem {
                id
                sku
                tracked
              }
            }
            userErrors {
              field
              message
            }
          }
        }
        """

        var_result = await shopify_graphql(
            shop, access_token, mutation_var,
            {"productId": product_id, "variants": variants_to_update},
        )

        updated_variants = (
            var_result.get("data", {})
            .get("productVariantsBulkUpdate", {})
            .get("productVariants", [])
        )

        for idx, var in enumerate(updated_variants):
            if idx >= len(variants):
                break
            our_variant = variants[idx]
            inv_item_id = var.get("inventoryItem", {}).get("id")
            stock = our_variant.get("stock", 0)
            if inv_item_id:
                await set_inventory_quantity(
                    shop=shop,
                    access_token=access_token,
                    inventory_item_id=inv_item_id,
                    quantity=stock,
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
# ADD VARIANT TO EXISTING PRODUCT
# ============================================
async def add_variant_to_existing_product(
    shop: str,
    access_token: str,
    product_id: str,
    variant_data: dict,
) -> dict:
    option_name = variant_data.get("option_name") or "Style"
    option_value = variant_data.get("title") or "Default"

    logger.info(f"   Adding variant: {option_name}={option_value}")

    option_exists = await ensure_product_has_option(
        shop=shop,
        access_token=access_token,
        product_id=product_id,
        option_name=option_name,
        option_values=[option_value],
    )

    if not option_exists:
        logger.error(
            f"❌ Could not ensure option '{option_name}' exists"
        )
        return {
            "errors": [
                {"message": f"Failed to create option '{option_name}'"}
            ]
        }

    mutation = """
    mutation productVariantsBulkCreate(
      $productId: ID!,
      $variants: [ProductVariantsBulkInput!]!
    ) {
      productVariantsBulkCreate(
        productId: $productId,
        variants: $variants
      ) {
        productVariants {
          id
          title
          price
          inventoryItem {
            id
            sku
            tracked
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "productId": product_id,
        "variants": [
            {
                "optionValues": [
                    {"name": option_value, "optionName": option_name}
                ],
                "price": str(variant_data.get("price", 0)),
                "inventoryItem": {
                    "sku": variant_data.get("sku", ""),
                    "tracked": True,
                },
            }
        ],
    }

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Variant create error: {result['errors']}")
        return result

    var_errors = (
        result.get("data", {})
        .get("productVariantsBulkCreate", {})
        .get("userErrors", [])
    )
    if var_errors:
        logger.error(f"❌ Variant create user errors: {var_errors}")
        return result

    created = (
        result.get("data", {})
        .get("productVariantsBulkCreate", {})
        .get("productVariants", [])
    )

    if created:
        v = created[0]
        logger.info(f"✅ Variant added: {v.get('title')} — ${v.get('price')}")

        inv_item_id = v.get("inventoryItem", {}).get("id")
        stock = variant_data.get("stock", 0)
        if inv_item_id and stock:
            await set_inventory_quantity(
                shop=shop,
                access_token=access_token,
                inventory_item_id=inv_item_id,
                quantity=stock,
            )

    return result


# ============================================
# PRODUCT CREATE (SIMPLE) — productSet
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

    metafields_input = []

    asin_value = str(product_data.get("asin", "") or "")
    if asin_value and asin_value != "None":
        metafields_input.append({
            "namespace": "custom",
            "key": "asin",
            "value": asin_value,
            "type": "single_line_text_field",
        })

    rating_value = str(product_data.get("rating", "") or "")
    if rating_value and rating_value != "None":
        metafields_input.append({
            "namespace": "custom",
            "key": "rating",
            "value": rating_value,
            "type": "single_line_text_field",
        })

    reviews_count_value = product_data.get("reviews_count")
    if reviews_count_value is not None:
        reviews_count_str = str(reviews_count_value)
        if reviews_count_str and reviews_count_str != "None":
            metafields_input.append({
                "namespace": "custom",
                "key": "reviews_count",
                "value": reviews_count_str,
                "type": "single_line_text_field",
            })

    amazon_price_value = product_data.get("amazon_price")
    if amazon_price_value is not None:
        amazon_price_str = str(amazon_price_value)
        if amazon_price_str and amazon_price_str != "None":
            metafields_input.append({
                "namespace": "custom",
                "key": "amazon_price",
                "value": amazon_price_str,
                "type": "single_line_text_field",
            })

    availability_value = str(product_data.get("availability", "") or "")
    if availability_value and availability_value != "None":
        metafields_input.append({
            "namespace": "custom",
            "key": "availability",
            "value": availability_value,
            "type": "single_line_text_field",
        })

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
        "descriptionHtml": product_data.get("description", ""),
        "vendor": product_data.get("brand", ""),
        "status": status,
    }

    if shopify_tags:
        input_data["tags"] = shopify_tags
        logger.info(f"   Pushing {len(shopify_tags)} tags")

    if product_type:
        input_data["productType"] = product_type
        logger.info(f"   Product type: {product_type}")

    if shopify_category_id:
        input_data["category"] = shopify_category_id
        logger.info(f"   Category: {shopify_category_id}")

    # Smart variant detection
    # - Sirf "Size" ya "Color" ke liye variants bhejo
    # - "Style" ignore karo (usually generic value hoti hai)
    variant_attrs = product_data.get("variant_attributes") or []
    product_options = []
    variant_values = []

    for attr in variant_attrs:
        if not isinstance(attr, dict):
            continue
        name = (attr.get("name") or "").strip()
        value = (attr.get("value") or "").strip()
        if name.lower() in ("size", "color") and value:
            product_options.append({
                "name": name,
                "values": [{"name": value}],
            })
            variant_values.append({
                "optionName": name,
                "name": value,
            })
            break  # Ek hi option use karo

    # productOptions + variants DONO bhejo (warna Shopify error dega)
    if product_options and variant_values:
        input_data["productOptions"] = product_options
        input_data["variants"] = [
            {
                "optionValues": variant_values,
                "price": str(price_float or 0),
                "inventoryItem": {
                    "sku": product_data.get("asin", ""),
                    "tracked": True,
                },
            }
        ]
        logger.info(
            f"   Adding variant: {variant_values[0].get('optionName')}"
            f"={variant_values[0].get('name')}"
        )
    # Warna productOptions bilkul mat bhejo — Shopify default title banayega

    mutation_create = """
    mutation productSet($input: ProductSetInput!) {
      productSet(input: $input) {
        product {
          id
          title
          handle
          tags
          productType
          category {
            id
            name
            fullName
          }
          options {
            id
            name
            values
          }
          variants(first: 5) {
            edges {
              node {
                id
                title
                price
                inventoryItem {
                  id
                  tracked
                }
              }
            }
          }
        }
        userErrors {
          field
          message
        }
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
    if shopify_product.get("category"):
        logger.info(f"   Category confirmed: {shopify_product.get('category')}")

    if product_id and metafields_input:
        await set_product_metafields(
            shop=shop,
            access_token=access_token,
            product_id=product_id,
            metafields=metafields_input,
        )

    variants_edges = shopify_product.get("variants", {}).get("edges", [])

    variant_id = None
    inventory_item_id = None

    if variants_edges:
        variant_node = variants_edges[0]["node"]
        variant_id = variant_node.get("id")
        inventory_item_id = variant_node.get("inventoryItem", {}).get("id")

    if product_id and variant_id and price_float > 0:
        await update_variant_with_tracked(
            shop=shop,
            access_token=access_token,
            product_id=product_id,
            variant_id=variant_id,
            price=price_float,
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
# PRODUCT IMAGES ADD
# ============================================
async def add_product_images(
    shop: str,
    access_token: str,
    product_id: str,
    image_urls: list,
) -> dict:
    mutation = """
    mutation productCreateMedia(
      $productId: ID!,
      $media: [CreateMediaInput!]!
    ) {
      productCreateMedia(productId: $productId, media: $media) {
        media {
          ... on MediaImage {
            id
            image {
              url
            }
          }
        }
        mediaUserErrors {
          field
          message
        }
      }
    }
    """

    media_input = [
        {
            "originalSource": url,
            "mediaContentType": "IMAGE",
        }
        for url in image_urls
        if url
    ]

    if not media_input:
        return {}

    variables = {
        "productId": product_id,
        "media": media_input,
    }

    return await shopify_graphql(shop, access_token, mutation, variables)


# ============================================
# PRODUCT STATUS UPDATE
# ============================================
async def update_shopify_product_status(
    shop: str,
    access_token: str,
    shopify_product_id: str,
    is_available: bool,
) -> bool:
    if not shopify_product_id.startswith("gid://"):
        product_gid = f"gid://shopify/Product/{shopify_product_id}"
    else:
        product_gid = shopify_product_id

    new_status = "ACTIVE" if is_available else "DRAFT"

    mutation = """
    mutation updateProductStatus($input: ProductInput!) {
      productUpdate(input: $input) {
        product {
          id
          title
          status
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "input": {
            "id": product_gid,
            "status": new_status,
        }
    }

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Status update GraphQL errors: {result['errors']}")
        return False

    update_data = result.get("data", {}).get("productUpdate", {})
    user_errors = update_data.get("userErrors", [])

    if user_errors:
        logger.error(f"❌ Status update user errors: {user_errors}")
        return False

    return True


# ============================================
# SHOPIFY PRODUCT DHUNDO SKU SE
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
            id
            title
            status
            variants(first: 1) {
              edges {
                node {
                  id
                  inventoryItem {
                    id
                  }
                }
              }
            }
          }
        }
      }
    }
    """

    result = await shopify_graphql(
        shop, access_token, query, {"query": f"sku:{sku}"}
    )

    if "errors" in result:
        logger.error(f"SKU search errors: {result['errors']}")
        return None

    edges = (
        result.get("data", {}).get("products", {}).get("edges", [])
    )

    if edges:
        product_gid = edges[0]["node"]["id"]
        logger.info(f"Found Shopify product: {product_gid} for SKU={sku}")
        return product_gid

    logger.warning(f"No Shopify product found for SKU={sku}")
    return None
