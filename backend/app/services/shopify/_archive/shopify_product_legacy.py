# app/services/shopify_product.py
# ============================================
# ⚠️ Backward-compatibility wrapper
# Asli functions app/services/shopify/ package mein hain
# Isme koi logic nahi — sirf re-export
# ============================================

from app.services.shopify import (  # noqa: F401
    # Helpers
    shopify_graphql,
    _safe_api_version,
    _build_shopify_tags,
    _get_product_type,
    # Auth
    build_auth_url,
    verify_hmac,
    verify_id_token,
    exchange_code_for_token,
    exchange_id_token_for_offline_token,
    refresh_shopify_token,
    # Taxonomy
    search_shopify_taxonomy,
    find_best_category,
    # Inventory
    get_primary_location,
    set_inventory_quantity,
    # Metafields
    METAFIELD_DEFINITIONS,
    ensure_metafield_definitions,
    _build_all_metafields,
    set_product_metafields,
    # Description
    _build_description_with_metafields,
    # Product extras
    publish_product_to_channels,
    add_product_to_collections,
    add_product_images,
    update_shopify_product_tags_and_type,
    update_shopify_product_status,
    # Variants
    update_variant_with_tracked,
    ensure_product_has_option,
    add_variant_to_existing_product,
    # Product core
    create_shopify_product,
    create_shopify_product_with_variants,
    delete_shopify_product,
    get_shopify_product_by_sku,
    # Sync
    check_product_availability,
    sync_update_shopify_price,
)

__all__ = [
    # Helpers
    "shopify_graphql",
    "_safe_api_version",
    "_build_shopify_tags",
    "_get_product_type",
    # Auth
    "build_auth_url",
    "verify_hmac",
    "verify_id_token",
    "exchange_code_for_token",
    "exchange_id_token_for_offline_token",
    "refresh_shopify_token",
    # Taxonomy
    "search_shopify_taxonomy",
    "find_best_category",
    # Inventory
    "get_primary_location",
    "set_inventory_quantity",
    # Metafields
    "METAFIELD_DEFINITIONS",
    "ensure_metafield_definitions",
    "_build_all_metafields",
    "set_product_metafields",
    # Description
    "_build_description_with_metafields",
    # Product extras
    "publish_product_to_channels",
    "add_product_to_collections",
    "add_product_images",
    "update_shopify_product_tags_and_type",
    "update_shopify_product_status",
    # Variants
    "update_variant_with_tracked",
    "ensure_product_has_option",
    "add_variant_to_existing_product",
    # Product core
    "create_shopify_product",
    "create_shopify_product_with_variants",
    "delete_shopify_product",
    "get_shopify_product_by_sku",
    # Sync
    "check_product_availability",
    "sync_update_shopify_price",
]