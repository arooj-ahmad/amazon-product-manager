# app/services/shopify/metafields/setter.py
import logging
from app.services.shopify.helpers import shopify_graphql
from .definitions import ensure_metafield_definitions

logger = logging.getLogger(__name__)

async def set_product_metafields(shop: str, access_token: str, product_id: str, metafields: list) -> bool:
    if not metafields: return True

    keys = [mf["key"] for mf in metafields]
    actual_types = await ensure_metafield_definitions(shop, access_token, keys)

    def _adapt_value_and_type(raw_value, definition_type: str) -> tuple:
        val_str = str(raw_value) if raw_value is not None else ""
        if definition_type == "number_integer":
            try: return str(int(float(val_str))), "number_integer"
            except: return val_str, "single_line_text_field"
        if definition_type == "number_decimal":
            try: return str(float(val_str)), "number_decimal"
            except: return val_str, "single_line_text_field"
        if definition_type == "boolean":
            return ("true" if val_str.strip().lower() in ("true", "1", "yes") else "false"), "boolean"
        return val_str, definition_type

    metafields_with_owner = []
    for mf in metafields:
        key = mf["key"]
        def_type = actual_types.get(key, mf.get("type", "single_line_text_field"))
        value_str, final_type = _adapt_value_and_type(mf["value"], def_type)
        if not value_str or value_str == "None": continue
        metafields_with_owner.append({"ownerId": product_id, "namespace": mf.get("namespace", "custom"), "key": key, "value": value_str, "type": final_type})

    if not metafields_with_owner: return True

    CHUNK_SIZE = 25
    total = len(metafields_with_owner)
    chunks = [metafields_with_owner[i:i + CHUNK_SIZE] for i in range(0, total, CHUNK_SIZE)]
    mutation = """mutation metafieldsSet($metafields: [MetafieldsSetInput!]!) { metafieldsSet(metafields: $metafields) { metafields { id namespace key value type } userErrors { field message code } } }"""
    
    all_success = True
    for idx, chunk in enumerate(chunks, 1):
        result = await shopify_graphql(shop, access_token, mutation, {"metafields": chunk})
        if "errors" in result or result.get("data", {}).get("metafieldsSet", {}).get("userErrors"):
            all_success = False

    return all_success
