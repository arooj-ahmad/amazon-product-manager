# ============================================
# app/services/shopify.py
# ============================================
# Yeh file sirf backward compatibility ke liye hai.
# Sab functions ab chhote modules mein hain.
# ============================================

from app.services.shopify_helpers import (  # noqa: F401
    _safe_api_version,
    _build_shopify_tags,
    _get_product_type,
    shopify_graphql,
)

from app.services.shopify_auth import (  # noqa: F401
    build_auth_url,
    verify_hmac,
    verify_id_token,
    exchange_code_for_token,
    exchange_id_token_for_offline_token,
    refresh_shopify_token,
)

from app.services.shopify_taxonomy import (  # noqa: F401
    search_shopify_taxonomy,
    find_best_category,
)

from app.services.shopify_inventory import (  # noqa: F401
    get_primary_location,
    set_inventory_quantity,
)

from app.services.shopify_product import (  # noqa: F401
    create_shopify_product,
    create_shopify_product_with_variants,
    add_variant_to_existing_product,
    add_product_to_collections,        # ✅ NAYA
    add_product_images,
    publish_product_to_channels,        # ✅ NAYA
    update_variant_with_tracked,
    set_product_metafields,
    ensure_metafield_definitions,       # ✅ NAYA
    ensure_product_has_option,
    update_shopify_product_tags_and_type,
    update_shopify_product_status,
    get_shopify_product_by_sku,
    delete_shopify_product,
)

from app.services.shopify_sync import (  # noqa: F401
    check_product_availability,
    sync_update_shopify_price,
)