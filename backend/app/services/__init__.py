# ============================================
# app/services/shopify/__init__.py
# ============================================

from app.services.shopify_auth import (
    build_auth_url,
    exchange_code_for_token,
    exchange_id_token_for_offline_token,
    refresh_shopify_token,
    verify_hmac,
    verify_id_token,
)

from app.services.shopify_helpers import (
    shopify_graphql,
    _build_shopify_tags,
    _get_product_type,
)

from app.services.shopify_product import (
    create_shopify_product,
    create_shopify_product_with_variants,
    add_variant_to_existing_product,
    add_product_to_collections,   # ✅ YEH ZAROORI HAI
    delete_shopify_product,
    update_variant_with_tracked,
    update_shopify_product_status,
    update_shopify_product_tags_and_type,
    get_shopify_product_by_sku,
    set_product_metafields,
    add_product_images,
    publish_product_to_channels,
    ensure_metafield_definitions,
)

from app.services.shopify_taxonomy import find_best_category

from app.services.shopify_inventory import (
    get_primary_location,
    set_inventory_quantity,
)

__all__ = [
    # Auth
    "build_auth_url",
    "exchange_code_for_token",
    "exchange_id_token_for_offline_token",
    "refresh_shopify_token",
    "verify_hmac",
    "verify_id_token",
    # Helpers
    "shopify_graphql",
    "_build_shopify_tags",
    "_get_product_type",
    # Product
    "create_shopify_product",
    "create_shopify_product_with_variants",
    "add_variant_to_existing_product",
    "add_product_to_collections",   # ✅ YEH ZAROORI HAI
    "delete_shopify_product",
    "update_variant_with_tracked",
    "update_shopify_product_status",
    "update_shopify_product_tags_and_type",
    "get_shopify_product_by_sku",
    "set_product_metafields",
    "add_product_images",
    "publish_product_to_channels",
    "ensure_metafield_definitions",
    # Taxonomy
    "find_best_category",
    # Inventory
    "get_primary_location",
    "set_inventory_quantity",
]