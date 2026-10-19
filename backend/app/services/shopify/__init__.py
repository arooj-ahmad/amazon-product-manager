# ============================================
# app/services/shopify/__init__.py
# Package exports — backward compatible
# ============================================

# ✅ Helpers (direct module se)
from app.services.shopify_helpers import (
    shopify_graphql,
    _safe_api_version,
    _build_shopify_tags,
    _get_product_type,
)

# ✅ Auth (direct module se)
from app.services.shopify_auth import (
    build_auth_url,
    verify_hmac,
    verify_id_token,
    exchange_code_for_token,
    exchange_id_token_for_offline_token,
    refresh_shopify_token,
)

# ✅ Taxonomy (direct module se)
from app.services.shopify_taxonomy import (
    search_shopify_taxonomy,
    find_best_category,
)

# ✅ Inventory (direct module se)
from app.services.shopify_inventory import (
    get_primary_location,
    set_inventory_quantity,
)

# ✅ Metafields (package ke andar ka module)
from app.services.shopify.metafields import (
    METAFIELD_DEFINITIONS,
    ensure_metafield_definitions,
    _build_all_metafields,
    set_product_metafields,
)

# ✅ Description (package ke andar ka module)
from app.services.shopify.description import (
    _build_description_with_metafields,
)

# ✅ Product extras (package ke andar ka module)
from app.services.shopify.product_extras import (
    publish_product_to_channels,
    add_product_to_collections,
    add_product_images,
    update_shopify_product_tags_and_type,
    update_shopify_product_status,
)

# ✅ Variants (package ke andar ka module)
from app.services.shopify.product_variants import (
    update_variant_with_tracked,
    ensure_product_has_option,
    add_variant_to_existing_product,
)

# ✅ Product core (package ke andar ka module)
from app.services.shopify.product_core import (
    create_shopify_product,
    create_shopify_product_with_variants,
    delete_shopify_product,
    get_shopify_product_by_sku,
)

# ✅ Sync (direct module se)
from app.services.shopify_sync import (
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