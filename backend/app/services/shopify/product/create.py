import logging
from app.services.shopify.helpers import shopify_graphql, _build_shopify_tags, _get_product_type
from app.services.shopify.metafields import _build_all_metafields, set_product_metafields
from app.services.shopify.description import _build_description_with_metafields
from app.services.shopify.product_extras import publish_product_to_channels, add_product_images
from app.services.shopify.product_variants import update_variant_with_tracked, _assign_image_to_variant, _normalize_compare_at_price
from app.services.shopify.inventory import set_inventory_quantity
from .pricing import calculate_compare_at_price, _get_compare_at_settings_from_store
from .helpers import _build_inventory_item, _find_category_from_breadcrumbs

logger = logging.getLogger(__name__)

async def create_shopify_product(shop: str, access_token: str, product_data: dict) -> dict:
    is_available = bool(product_data.get("is_available", False))
    status = "ACTIVE" if is_available else "DRAFT"
    
    if not is_available: logger.warning("?? Product is OUT OF STOCK. Setting status to DRAFT and stock to 0.")

    price_float = float(product_data.get("price", 0) or 0)
    amazon_price_float = float(product_data.get("amazon_price")) if product_data.get("amazon_price") is not None else None
    asin_value = str(product_data.get("asin", "") or "").strip() or "NO-SKU"

    metafields_input = _build_all_metafields(product_data)
    shopify_tags = _build_shopify_tags(product_data)
    product_type = _get_product_type(product_data) or (product_data.get("title") or "").split()[0][:255] or "General"

    shopify_category_id = await _find_category_from_breadcrumbs(shop, access_token, product_data.get("categories") or [], product_data.get("title", ""), product_data.get("tags") or [])
    description_html = _build_description_with_metafields(product_data)
    compare_enabled, compare_rule, compare_value = _get_compare_at_settings_from_store(shop)
    
    compare_at_price = None
    if compare_enabled:
        compare_at_price = calculate_compare_at_price(price_float, compare_rule, compare_value, amazon_price_float)

    input_data = {
        "title": product_data.get("title") or "Untitled Product",
        "descriptionHtml": description_html, "vendor": product_data.get("brand", ""),
        "status": status, "productType": product_type,
    }
    if shopify_category_id: input_data["category"] = shopify_category_id
    if shopify_tags: input_data["tags"] = shopify_tags

    variant_attrs = product_data.get("variant_attributes") or []
    product_options, variant_values = [], []
    for attr in variant_attrs:
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
    else:
        logger.info("   No variant options — Shopify will create default variant")

    mutation_create = """mutation productSet($input: ProductSetInput!) { productSet(input: $input) { product { id title handle tags productType category { id } options { id name values } variants(first: 5) { edges { node { id title price compareAtPrice inventoryItem { id sku tracked measurement { weight { value unit } } } } } } } userErrors { field message } } }"""
    result = await shopify_graphql(shop, access_token, mutation_create, {"input": input_data})

    if "errors" in result or result.get("data", {}).get("productSet", {}).get("userErrors"): 
        logger.error(f"? Product create error: {result}")
        return result

    shopify_product = result["data"]["productSet"]["product"]
    product_id = shopify_product.get("id")
    logger.info(f"? Product created: {shopify_product.get('title')}")

    if product_id and is_available: await publish_product_to_channels(shop, access_token, product_id)
    if product_id and metafields_input: await set_product_metafields(shop, access_token, product_id, metafields_input)

    variants_edges = shopify_product.get("variants", {}).get("edges", [])
    if variants_edges:
        v_node = variants_edges[0]["node"]
        if product_id and v_node.get("id"):
            await update_variant_with_tracked(shop, access_token, product_id, v_node["id"], price_float, asin_value, compare_at_price)
        if v_node.get("inventoryItem", {}).get("id"):
            stock_qty = int(product_data.get("stock_quantity", 0) or 0) if is_available else 0
            await set_inventory_quantity(shop, access_token, v_node["inventoryItem"]["id"], stock_qty)

    if product_id and product_data.get("images"): await add_product_images(shop, access_token, product_id, product_data["images"][:10])
    return result

async def create_shopify_product_with_variants(shop: str, access_token: str, product_data: dict, variants: list) -> dict:
    is_available = bool(product_data.get("is_available", False))
    status = "ACTIVE" if is_available else "DRAFT"
    
    shopify_tags = _build_shopify_tags(product_data)
    product_type = _get_product_type(product_data) or (product_data.get("title") or "").split()[0][:255] or "General"
    shopify_category_id = await _find_category_from_breadcrumbs(shop, access_token, product_data.get("categories") or [], product_data.get("title", ""), product_data.get("tags") or [])
    compare_enabled, compare_rule, compare_value = _get_compare_at_settings_from_store(shop)

    raw_option_names = []
    for v in variants:
        for opt in (v.get("options") or v.get("variant_attributes") or []):
            if isinstance(opt, dict):
                n = (opt.get("name") or opt.get("key") or "").strip()
                if n.lower() not in ("title", "default title") and n not in raw_option_names: raw_option_names.append(n)
    if not raw_option_names and product_data.get("variant_attributes"):
        for opt in product_data["variant_attributes"]:
            if isinstance(opt, dict):
                n = (opt.get("name") or opt.get("key") or "").strip()
                if n.lower() not in ("title", "default title") and n not in raw_option_names: raw_option_names.append(n)

    option_names = raw_option_names[:3] if raw_option_names else ["Style"]
    options_dict = {name: [] for name in option_names}
    for v in variants:
        v_opts = {(opt.get("name") or opt.get("key") or "").strip(): str(opt.get("value") or "").strip() for opt in (v.get("options") or v.get("variant_attributes") or []) if isinstance(opt, dict)}
        for name in option_names:
            val = v_opts.get(name) or "Default"
            if val not in options_dict[name]: options_dict[name].append(val)
    for name in option_names:
        if not options_dict[name]: options_dict[name].append("Default")

    product_options_input = [{"name": name, "values": [{"name": val} for val in options_dict[name]]} for name in option_names]
    variant_inputs, seen_combinations = [], set()

    for idx, v in enumerate(variants):
        v_asin = str(v.get("asin") or v.get("sku") or f"VAR-{idx+1}").strip()
        v_price = float(v.get("price") or product_data.get("price") or 0.0)
        
        v_cap = v.get("compare_at_price")
        if v_cap is None and compare_enabled:
            v_ap = v.get("amazon_price") or product_data.get("amazon_price")
            v_cap = calculate_compare_at_price(v_price, compare_rule, compare_value, float(v_ap) if v_ap is not None else None)

        v_opts = {(opt.get("name") or opt.get("key") or "").strip(): str(opt.get("value") or "").strip() for opt in (v.get("options") or v.get("variant_attributes") or []) if isinstance(opt, dict)}
        option_values_list = [{"optionName": name, "name": v_opts.get(name) or "Default"} for name in option_names]
        
        combo_str = " | ".join([f"{ov['optionName']}:{ov['name']}" for ov in option_values_list])
        if combo_str in seen_combinations:
            disambiguated = f"{option_values_list[-1]['name']} ({v_asin})"
            option_values_list[-1]["name"] = disambiguated
            if disambiguated not in [od["name"] for od in product_options_input[-1]["values"]]: product_options_input[-1]["values"].append({"name": disambiguated})
        seen_combinations.add(combo_str)

        var_input = {
            "optionValues": option_values_list, "price": f"{v_price:.2f}",
            "inventoryItem": _build_inventory_item({"item_weight": v.get("weight") or product_data.get("item_weight")}, v_asin),
            "metafields": [{"namespace": "custom", "key": "asin", "value": v_asin, "type": "single_line_text_field"}],
        }
        cap_str = _normalize_compare_at_price(v_cap, v_price)
        if cap_str: var_input["compareAtPrice"] = cap_str
        variant_inputs.append(var_input)

    if len(variant_inputs) > 100: variant_inputs = variant_inputs[:100]

    input_data = {
        "title": product_data.get("title") or "Untitled Product", "descriptionHtml": _build_description_with_metafields(product_data),
        "vendor": product_data.get("brand", ""), "status": status, "productType": product_type,
        "productOptions": product_options_input, "variants": variant_inputs,
    }
    if shopify_category_id: input_data["category"] = shopify_category_id
    if shopify_tags: input_data["tags"] = shopify_tags

    mutation_create = """mutation productSet($input: ProductSetInput!) { productSet(input: $input) { product { id title handle tags productType category { id } options { id name values } variants(first: 100) { edges { node { id title price compareAtPrice inventoryItem { id sku tracked } } } } } userErrors { field message } } }"""
    result = await shopify_graphql(shop, access_token, mutation_create, {"input": input_data})

    if "errors" in result or result.get("data", {}).get("productSet", {}).get("userErrors"): return result

    shopify_product = result["data"]["productSet"]["product"]
    product_id = shopify_product.get("id")
    if not product_id: return result

    if is_available: await publish_product_to_channels(shop, access_token, product_id)
    all_mfs = _build_all_metafields(product_data)
    if all_mfs: await set_product_metafields(shop, access_token, product_id, all_mfs)

    created_variants_by_sku = {edge["node"]["inventoryItem"]["sku"]: edge["node"] for edge in shopify_product.get("variants", {}).get("edges", []) if edge["node"].get("inventoryItem", {}).get("sku")}
    
    for idx, v in enumerate(variants):
        v_asin = str(v.get("asin") or v.get("sku") or "").strip()
        v_node = created_variants_by_sku.get(v_asin) or (shopify_product.get("variants", {}).get("edges", [])[idx]["node"] if idx < len(shopify_product.get("variants", {}).get("edges", [])) else None)
        if not v_node: continue

        inv_id = v_node.get("inventoryItem", {}).get("id")
        if inv_id:
            stock_qty = int(v.get("stock") or product_data.get("stock_quantity", 0) or 0) if is_available else 0
            await set_inventory_quantity(shop, access_token, inv_id, stock_qty)

        if v_node.get("id") and v.get("image_url"): await _assign_image_to_variant(shop, access_token, product_id, v_node["id"], v["image_url"])

    if product_data.get("images"): await add_product_images(shop, access_token, product_id, product_data["images"][:10])
    return result
