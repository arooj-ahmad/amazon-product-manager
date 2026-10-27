# app/services/shopify/variants/update.py
import logging
from app.services.shopify.helpers import shopify_graphql
from .helpers import _build_measurement, _normalize_compare_at_price

logger = logging.getLogger(__name__)

async def update_variant_with_tracked(shop: str, access_token: str, product_id: str, variant_id: str, price: float, sku: str = "", compare_at_price: float = None, weight: str = None) -> bool:
    mutation = """mutation productVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) { productVariantsBulkUpdate(productId: $productId, variants: $variants) { productVariants { id price compareAtPrice inventoryItem { id sku tracked measurement { weight { value unit } } } } userErrors { field message } } }"""
    
    inventory_item_input = {"tracked": True}
    if sku: inventory_item_input["sku"] = sku
    if weight:
        measurement = _build_measurement({"weight": weight})
        if measurement: inventory_item_input["measurement"] = measurement

    variant_input = {"id": variant_id, "price": str(price), "inventoryItem": inventory_item_input}
    cap_str = _normalize_compare_at_price(compare_at_price, price)
    if cap_str: variant_input["compareAtPrice"] = cap_str

    result = await shopify_graphql(shop, access_token, mutation, {"productId": product_id, "variants": [variant_input]})
    if "errors" in result or result.get("data", {}).get("productVariantsBulkUpdate", {}).get("userErrors"): return False
    
    updated = result.get("data", {}).get("productVariantsBulkUpdate", {}).get("productVariants", [])
    if updated:
        logger.info(f"Variant updated: price=${updated[0].get('price')}, sku={updated[0].get('inventoryItem', {}).get('sku', 'N/A')}")
        return True
    return False

async def ensure_product_has_option(shop: str, access_token: str, product_id: str, option_name: str, option_values: list) -> bool:
    query = """query getProductWithVariants($id: ID!) { product(id: $id) { id options { id name values } variants(first: 100) { edges { node { id selectedOptions { name value } } } } } }"""
    result = await shopify_graphql(shop, access_token, query, {"id": product_id})
    if "errors" in result: return False

    product = result.get("data", {}).get("product")
    if not product: return False

    existing_options = product.get("options", [])
    if option_name.lower() in [opt.get("name", "").lower() for opt in existing_options]:
        return True

    new_options = []
    for opt in existing_options:
        name = opt.get("name", "")
        if name.lower() == "default title": continue
        values_as_dicts = [{"name": v if isinstance(v, str) else v.get("name")} for v in opt.get("values", []) if (isinstance(v, str) and v) or (isinstance(v, dict) and v.get("name"))]
        new_options.append({"name": name, "values": values_as_dicts})

    new_option_values = [{"name": v if isinstance(v, str) else v.get("name")} for v in option_values if (isinstance(v, str) and v) or (isinstance(v, dict) and v.get("name"))]
    new_options.append({"name": option_name, "values": new_option_values})

    variants_edges = product.get("variants", {}).get("edges", [])
    existing_variants_input = []

    for edge in variants_edges:
        node = edge["node"]
        variant_id = node.get("id")
        selected_options = node.get("selectedOptions", [])
        if not variant_id: continue

        variant_option_values = [{"optionName": opt["name"], "name": opt["value"]} for opt in selected_options]
        if new_option_values:
            first_value = new_option_values[0]
            val_name = first_value if isinstance(first_value, str) else first_value.get("name", "Default")
            variant_option_values.append({"optionName": option_name, "name": val_name})

        existing_variants_input.append({"id": variant_id, "optionValues": variant_option_values})

    mutation = """mutation productSet($input: ProductSetInput!) { productSet(input: $input) { product { id options { id name values } } userErrors { field message } } }"""
    input_data = {"id": product_id, "productOptions": new_options}
    if existing_variants_input: input_data["variants"] = existing_variants_input

    update_result = await shopify_graphql(shop, access_token, mutation, {"input": input_data})
    if "errors" in update_result or update_result.get("data", {}).get("productSet", {}).get("userErrors"): return False
    return True
