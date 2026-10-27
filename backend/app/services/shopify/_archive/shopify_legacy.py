# ============================================
# app/services/shopify.py
# ============================================
# ⚠️ DEPRECATED — use `app.services.shopify` package instead
# Yeh file sirf backward compatibility ke liye hai.
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

from app.services.shopify_sync import (  # noqa: F401
    check_product_availability,
    sync_update_shopify_price,
)

# ❌ `from app.services.shopify_product import ...` HATA DIYA
# Reason: shopify_product.py khud `app.services.shopify` package se import karta hai
#         → circular import ho jata tha.
#
# Ab product functions yahan se import karein:
#
#   from app.services.shopify import (
#       create_shopify_product,
#       create_shopify_product_with_variants,
#       ...
#   )
#
# Ya direct module se:
#
#   from app.services.shopify.product_core import create_shopify_product
#   from app.services.shopify.product_extras import add_product_images
#   from app.services.shopify.product_variants import update_variant_with_tracked
#   from app.services.shopify.metafields import set_product_metafields