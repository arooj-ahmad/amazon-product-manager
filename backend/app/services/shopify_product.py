# app/services/shopify_product.py


from app.services.shopify import *  # noqa: F401, F403

# Explicit imports for IDE support
from app.services.shopify import (
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
    add_product_images,               # ✅ YEH ADD KAREIN
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
)

__all__ = [
    "METAFIELD_DEFINITIONS",
    "ensure_metafield_definitions",
    "_build_all_metafields",
    "set_product_metafields",
    "_build_description_with_metafields",
    "publish_product_to_channels",
    "add_product_to_collections",
    "add_product_images",              # ✅ YEH ADD KAREIN
    "update_shopify_product_tags_and_type",
    "update_shopify_product_status",
    "update_variant_with_tracked",
    "ensure_product_has_option",
    "add_variant_to_existing_product",
    "create_shopify_product",
    "create_shopify_product_with_variants",
    "delete_shopify_product",
    "get_shopify_product_by_sku",
]