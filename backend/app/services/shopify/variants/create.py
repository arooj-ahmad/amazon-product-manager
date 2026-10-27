# app/services/shopify/variants/create.py
import logging
from app.services.shopify.helpers import shopify_graphql
from app.services.shopify.inventory import set_inventory_quantity
from .helpers import _build_measurement, _normalize_compare_at_price
from .update import ensure_product_has_option
from .image import _assign_image_to_variant

logger = logging.getLogger(__name__)

async def add_variant_to_existing_product(shop: str, access_token: str, product_id: str, variant_data: dict, all_options: list = None) -> dict:
    if not all_options:
        option_name = variant_data.get("option_name") or "Style"
        option_value = variant_data.get("title") or "Default"
        all_options = [{"name": option_name, "value": option_value}]

    for opt in all_options:
        option_exists = await ensure_product_has_option(shop, access_token, product_id, opt["name"], [opt["value"]])
        if not option_exists:
            return {"errors": [{"message": f"Failed to create option '{opt['name']}'"}]}

    option_values = [{"optionName": opt["name"], "name": opt["value"]} for opt in all_options]
    sku_value = variant_data.get("sku", "") or ""
    price_value = variant_data.get("price", 0)

    inventory_item_input = {"tracked": True}
    if sku_value: inventory_item_input["sku"] = sku_value
    measurement = _build_measurement(variant_data)
    if measurement: inventory_item_input["measurement"] = measurement

    mutation = """mutation productVariantsBulkCreate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) { productVariantsBulkCreate(productId: $productId, variants: $variants) { productVariants { id title price compareAtPrice inventoryItem { id sku tracked measurement { weight { value unit } } } } userErrors { field message } } }"""

    variants_input = {"optionValues": option_values, "price": str(price_value), "inventoryItem": inventory_item_input}
    cap_str = _normalize_compare_at_price(variant_data.get("compare_at_price"), price_value)
    if cap_str: variants_input["compareAtPrice"] = cap_str

    result = await shopify_graphql(shop, access_token, mutation, {"productId": product_id, "variants": [variants_input]})
    if "errors" in result: return result

    var_errors = result.get("data", {}).get("productVariantsBulkCreate", {}).get("userErrors", [])
    if var_errors:
        for err in var_errors:
            if "already exists" in (err.get("message") or "").lower(): return {"already_exists": True, "userErrors": var_errors}
        return result

    created = result.get("data", {}).get("productVariantsBulkCreate", {}).get("productVariants", [])
    if created:
        v = created[0]
        variant_id = v.get("id")
        
        inv_item_id = v.get("inventoryItem", {}).get("id")
        if inv_item_id and variant_data.get("stock"):
            await set_inventory_quantity(shop, access_token, inv_item_id, variant_data.get("stock"))

        if variant_id and variant_data.get("image_url"):
            await _assign_image_to_variant(shop, access_token, product_id, variant_id, variant_data["image_url"])

        asin_val = variant_data.get("sku") or variant_data.get("asin")
        if variant_id and asin_val:
            mf_mutation = """mutation metafieldsSet($metafields: [MetafieldsSetInput!]!) { metafieldsSet(metafields: $metafields) { userErrors { field message } } }"""
            await shopify_graphql(shop, access_token, mf_mutation, {
                "metafields": [{"ownerId": variant_id, "namespace": "custom", "key": "asin", "value": str(asin_val), "type": "single_line_text_field"}]
            })

    return result
