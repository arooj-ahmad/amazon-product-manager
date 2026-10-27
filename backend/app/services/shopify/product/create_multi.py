# app/services/shopify/product/create_multi.py
# ============================================================
# Creates one Shopify product with multiple variants.
# All Amazon variation attributes (Size, Color, Style, …) are
# mapped to Shopify product options.  Each child ASIN is
# preserved as a variant metafield (custom.asin).
# ============================================================
import logging
from app.services.shopify.helpers import shopify_graphql, _build_shopify_tags, _get_product_type
from app.services.shopify.metafields import _build_all_metafields, set_product_metafields
from app.services.shopify.description import _build_description_with_metafields
from app.services.shopify.product_extras import publish_product_to_channels, add_product_images
from app.services.shopify.variants import _assign_image_to_variant, _normalize_compare_at_price
from app.services.shopify.inventory import set_inventory_quantity
from .helpers import (
    calculate_compare_at_price, _get_compare_at_settings_from_store,
    _build_inventory_item, _find_category_from_breadcrumbs
)

logger = logging.getLogger(__name__)

def _extract_options(v):
    """
    Extract Shopify option name/value pairs from a prepared variant dict.

    Handles multiple attribute formats:
      • {"name": "Color", "value": "Red"}               (standard)
      • {"attributeName": "Size", "attributeValue": "M"} (variantDetails style)
      • {"key": "Style", "value": "Modern"}              (flat key/value)
      • "Color: Red"                                      (colon-separated string)
    """
    opts = []
    raw = (
        v.get("options")
        or v.get("variant_attributes")
        or v.get("attributes")
        or []
    )

    if isinstance(raw, str):
        raw = [{"name": "Style", "value": raw}]

    for opt in raw:
        if isinstance(opt, dict):
            # Standard + variantDetails key names
            name = (
                opt.get("name")
                or opt.get("attributeName")
                or opt.get("key")
                or ""
            ).strip()
            value = str(
                opt.get("value")
                or opt.get("attributeValue")
                or ""
            ).strip()
            if name and value and name.lower() not in ("title", "default title"):
                opts.append({"name": name, "value": value})
        elif isinstance(opt, str) and ":" in opt:
            name, value = opt.split(":", 1)
            name, value = name.strip(), value.strip()
            if name and value and name.lower() not in ("title", "default title"):
                opts.append({"name": name, "value": value})
    return opts

async def create_shopify_product_with_variants(
    shop: str,
    access_token: str,
    product_data: dict,
    variants: list,
) -> dict:
    """
    Create a single Shopify product with one variant per child ASIN.

    Amazon variation attributes (Color, Size, Style, …) are mapped to
    up to 3 Shopify product options.  Each variant carries its ASIN as
    a metafield (custom.asin) for reliable downstream lookup.
    """
    is_available = bool(product_data.get("is_available", False))
    status = "ACTIVE" if is_available else "DRAFT"
    shopify_tags = _build_shopify_tags(product_data)
    product_type = _get_product_type(product_data) or (product_data.get("title") or "").split()[0][:255]
    shopify_category_id = await _find_category_from_breadcrumbs(
        shop, access_token,
        product_data.get("categories") or [],
        product_data.get("title", ""),
        product_data.get("tags") or [],
    )
    compare_enabled, compare_rule, compare_value = _get_compare_at_settings_from_store(shop)

    logger.info(
        f"[CreateMulti] shop={shop} | variants_input={len(variants)} | "
        f"status={status} | compare_enabled={compare_enabled}"
    )

    # ── 1. Collect all unique option names (max 3 per Shopify limit) ──
    raw_option_names = []
    for v in variants:
        for opt in _extract_options(v):
            n = opt["name"]
            if n not in raw_option_names:
                raw_option_names.append(n)

    option_names = raw_option_names[:3] if raw_option_names else ["Style"]
    logger.info(
        f"[CreateMulti] option_names={option_names} | "
        f"unique_options_discovered={len(raw_option_names)}"
    )

    # ── 2. Collect unique values per option ───────────────────────────
    options_dict = {name: [] for name in option_names}
    for v in variants:
        v_opts = {opt["name"]: opt["value"] for opt in _extract_options(v)}
        for name in option_names:
            val = v_opts.get(name) or "Default"
            if val not in options_dict[name]:
                options_dict[name].append(val)

    product_options_input = [
        {"name": name, "values": [{"name": val} for val in options_dict[name]]}
        for name in option_names
    ]

    # ── 3. Build per-variant input ─────────────────────────────────────
    variant_inputs = []
    seen_combinations: set = set()
    skipped_duplicates = 0

    for idx, v in enumerate(variants):
        v_asin = str(v.get("asin") or v.get("sku") or f"VAR-{idx + 1}").strip()
        v_price = float(v.get("price") or product_data.get("price") or 0.0)

        v_cap = v.get("compare_at_price")
        if v_cap is None and compare_enabled:
            v_ap = v.get("amazon_price") or product_data.get("amazon_price")
            v_cap = calculate_compare_at_price(
                v_price, compare_rule, compare_value,
                float(v_ap) if v_ap is not None else None,
            )

        v_opts = {opt["name"]: opt["value"] for opt in _extract_options(v)}
        option_values_list = [
            {"optionName": name, "name": v_opts.get(name) or "Default"}
            for name in option_names
        ]

        # Resolve duplicate option combinations by appending the ASIN
        combo_str = " | ".join(
            f"{ov['optionName']}:{ov['name']}" for ov in option_values_list
        )
        if combo_str in seen_combinations:
            skipped_duplicates += 1
            option_values_list[-1]["name"] = (
                f"{option_values_list[-1]['name']} ({v_asin})"
            )
            logger.debug(
                f"[CreateMulti] Duplicate combo resolved for {v_asin}: {combo_str}"
            )
        seen_combinations.add(combo_str)

        var_input = {
            "optionValues": option_values_list,
            "price": f"{v_price:.2f}",
            "inventoryItem": _build_inventory_item(
                {"item_weight": v.get("weight") or product_data.get("item_weight")},
                v_asin,
            ),
            # ASIN stored as variant metafield for reliable downstream lookup
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

    # Shopify hard limit: 100 variants per product
    if len(variant_inputs) > 100:
        logger.warning(
            f"[CreateMulti] Truncating variants from {len(variant_inputs)} to 100 "
            f"(Shopify limit)."
        )
        variant_inputs = variant_inputs[:100]

    logger.info(
        f"[CreateMulti] variant_inputs_built={len(variant_inputs)} | "
        f"duplicate_combos_resolved={skipped_duplicates}"
    )

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

    mutation_create = """mutation productSet($input: ProductSetInput!) { productSet(input: $input) { product { id title handle tags productType category { id } options { id name values } variants(first: 100) { edges { node { id title price compareAtPrice inventoryItem { id sku tracked } } } } } userErrors { field message } } }"""
    result = await shopify_graphql(shop, access_token, mutation_create, {"input": input_data})

    user_errors = result.get("data", {}).get("productSet", {}).get("userErrors", [])
    if "errors" in result or user_errors:
        logger.error(
            f"[CreateMulti] productSet failed | "
            f"errors={result.get('errors')} | userErrors={user_errors}"
        )
        return result

    shopify_product = result["data"]["productSet"]["product"]
    product_id = shopify_product.get("id")
    if not product_id:
        logger.error("[CreateMulti] productSet returned no product id.")
        return result

    created_variant_edges = shopify_product.get("variants", {}).get("edges", [])
    logger.info(
        f"[CreateMulti] Shopify product created: id={product_id} | "
        f"shopify_variants_returned={len(created_variant_edges)}"
    )

    # ── 4. Post-creation steps ─────────────────────────────────────────
    if is_available:
        await publish_product_to_channels(shop, access_token, product_id)

    all_mfs = _build_all_metafields(product_data)
    if all_mfs:
        await set_product_metafields(shop, access_token, product_id, all_mfs)

    # Build a SKU → node map for inventory + image assignment
    created_variants_by_sku = {
        edge["node"]["inventoryItem"]["sku"]: edge["node"]
        for edge in created_variant_edges
        if edge["node"].get("inventoryItem", {}).get("sku")
    }

    inventory_set_count = 0
    image_set_count = 0
    post_failure_count = 0

    for idx, v in enumerate(variants[:100]):
        v_asin = str(v.get("asin") or v.get("sku") or "").strip()
        v_node = created_variants_by_sku.get(v_asin) or (
            created_variant_edges[idx]["node"]
            if idx < len(created_variant_edges)
            else None
        )
        if not v_node:
            logger.warning(
                f"[CreateMulti] No Shopify node found for variant {v_asin} "
                f"(idx={idx}) — skipping inventory/image."
            )
            post_failure_count += 1
            continue

        # Inventory
        inv_id = v_node.get("inventoryItem", {}).get("id")
        if inv_id:
            stock_qty = (
                int(v.get("stock") or product_data.get("stock_quantity", 0) or 0)
                if is_available else 0
            )
            try:
                await set_inventory_quantity(shop, access_token, inv_id, stock_qty)
                inventory_set_count += 1
            except Exception as inv_err:
                post_failure_count += 1
                logger.warning(
                    f"[CreateMulti] Inventory set failed for {v_asin}: {inv_err}"
                )

        # Variant image
        if v_node.get("id") and v.get("image_url"):
            try:
                await _assign_image_to_variant(
                    shop, access_token, product_id, v_node["id"], v["image_url"]
                )
                image_set_count += 1
            except Exception as img_err:
                post_failure_count += 1
                logger.warning(
                    f"[CreateMulti] Image assign failed for {v_asin}: {img_err}"
                )

    logger.info(
        f"[CreateMulti] POST-CREATE | "
        f"inventory_set={inventory_set_count} | "
        f"images_assigned={image_set_count} | "
        f"post_failures={post_failure_count}"
    )

    # Product-level images (gallery)
    if product_data.get("images"):
        await add_product_images(shop, access_token, product_id, product_data["images"][:10])

    return result