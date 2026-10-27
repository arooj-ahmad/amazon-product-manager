import logging
from app.services.shopify.helpers import shopify_graphql, _build_shopify_tags, _get_product_type
from app.services.shopify.metafields import _build_all_metafields, set_product_metafields
from app.services.shopify.description import _build_description_with_metafields
from app.services.shopify.product_extras import publish_product_to_channels, add_product_images
from app.services.shopify.product_variants import update_variant_with_tracked
from app.services.shopify.inventory import set_inventory_quantity
from .helpers import (
    calculate_compare_at_price, _get_compare_at_settings_from_store,
    _build_inventory_item, _find_category_from_breadcrumbs
)

logger = logging.getLogger(__name__)

async def create_shopify_product(shop: str, access_token: str, product_data: dict) -> dict:
    is_available = bool(product_data.get("is_available", False))
    status = "ACTIVE" if is_available else "DRAFT"
    price_float = float(product_data.get("price", 0) or 0)
    amazon_price_float = float(product_data.get("amazon_price")) if product_data.get("amazon_price") is not None else None
    asin_value = str(product_data.get("asin", "") or "").strip() or "NO-SKU"

    metafields_input = _build_all_metafields(product_data)
    shopify_tags = _build_shopify_tags(product_data)
    product_type = _get_product_type(product_data) or (product_data.get("title") or "").split()[0][:255]
    shopify_category_id = await _find_category_from_breadcrumbs(shop, access_token, product_data.get("categories") or [], product_data.get("title", ""), product_data.get("tags") or [])
    description_html = _build_description_with_metafields(product_data)
    compare_enabled, compare_rule, compare_value = _get_compare_at_settings_from_store(shop)
    
    compare_at_price = None
    if compare_enabled: compare_at_price = calculate_compare_at_price(price_float, compare_rule, compare_value, amazon_price_float)

    input_data = {"title": product_data.get("title") or "Untitled Product", "descriptionHtml": description_html, "vendor": product_data.get("brand", ""), "status": status, "productType": product_type}
    if shopify_category_id: input_data["category"] = shopify_category_id
    if shopify_tags: input_data["tags"] = shopify_tags

    product_options, variant_values = [], []
    for attr in (product_data.get("variant_attributes") or []):
        if isinstance(attr, dict):
            name, value = (attr.get("name") or "").strip(), (attr.get("value") or "").strip()
            if name and value and name.lower() not in ("title", "default title"):
                opt = next((o for o in product_options if o["name"] == name), None)
                if opt:
                    if value not in [v["name"] for v in opt["values"]]: opt["values"].append({"name": value})
                else: product_options.append({"name": name, "values": [{"name": value}]})
                variant_values.append({"optionName": name, "name": value})

    if product_options and variant_values:
        input_data["productOptions"] = product_options
        variant_input = {"optionValues": variant_values, "price": str(price_float or 0), "inventoryItem": _build_inventory_item(product_data, asin_value)}
        if compare_at_price: variant_input["compareAtPrice"] = str(compare_at_price)
        input_data["variants"] = [variant_input]

    mutation_create = """mutation productSet($input: ProductSetInput!) { productSet(input: $input) { product { id title handle tags productType category { id } options { id name values } variants(first: 5) { edges { node { id title price compareAtPrice inventoryItem { id sku tracked measurement { weight { value unit } } } } } } } userErrors { field message } } }"""
    result = await shopify_graphql(shop, access_token, mutation_create, {"input": input_data})
    if "errors" in result or result.get("data", {}).get("productSet", {}).get("userErrors"): return result

    shopify_product = result["data"]["productSet"]["product"]
    product_id = shopify_product.get("id")
    if product_id and is_available: await publish_product_to_channels(shop, access_token, product_id)
    if product_id and metafields_input: await set_product_metafields(shop, access_token, product_id, metafields_input)

    variants_edges = shopify_product.get("variants", {}).get("edges", [])
    if variants_edges:
        v_node = variants_edges[0]["node"]
        if product_id and v_node.get("id"): await update_variant_with_tracked(shop, access_token, product_id, v_node["id"], price_float, asin_value, compare_at_price)
        if v_node.get("inventoryItem", {}).get("id"):
            stock_qty = int(product_data.get("stock_quantity", 0) or 0) if is_available else 0
            await set_inventory_quantity(shop, access_token, v_node["inventoryItem"]["id"], stock_qty)

    if product_id and product_data.get("images"): await add_product_images(shop, access_token, product_id, product_data["images"][:10])
    return result
