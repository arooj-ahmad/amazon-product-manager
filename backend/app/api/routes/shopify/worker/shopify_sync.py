# app/api/routes/shopify/worker/shopify_sync.py
# ============================================================
# Pushes a parent product + all its variants to Shopify as a
# single product with multiple variants (not separate products).
# ============================================================
import logging
from app.services.shopify import create_shopify_product_with_variants, add_variant_to_existing_product, add_product_to_collections
from ..helpers import _build_product_data_for_shopify

logger = logging.getLogger(__name__)


async def push_to_shopify(
    shop_domain: str,
    access_token: str,
    data: dict,
    prepared_variants: list,
    existing_shopify_product_id: str,
    collection_ids: list,
    base_asin: str,
) -> tuple:
    """
    Push one Shopify product with all variants.

    Returns:
        (variants_pushed_count, failure_count, shopify_product_id)
    """
    variants_pushed_count = 0
    failure_count = 0
    new_shopify_id = existing_shopify_product_id

    if not existing_shopify_product_id:
        # ── Create brand-new Shopify product with all variants ─────────
        logger.info(
            f"[ShopifySync] Creating new product for base_asin={base_asin} "
            f"with {len(prepared_variants)} variant(s)."
        )

        base_db_prod = next(
            (vp["db_product"] for vp in prepared_variants if vp["asin"] == base_asin),
            prepared_variants[0]["db_product"] if prepared_variants else None,
        )
        product_data_for_create = _build_product_data_for_shopify(
            data=data, product=base_db_prod
        )

        try:
            result = await create_shopify_product_with_variants(
                shop=shop_domain,
                access_token=access_token,
                product_data=product_data_for_create,
                variants=prepared_variants,
            )
            user_errors = result.get("data", {}).get("productSet", {}).get("userErrors", [])
            if "errors" in result or user_errors:
                logger.error(
                    f"[ShopifySync] productSet failed | errors={result.get('errors')} | "
                    f"userErrors={user_errors}"
                )
                failure_count += len(prepared_variants)
            else:
                new_shopify_id = (
                    result.get("data", {})
                    .get("productSet", {})
                    .get("product", {})
                    .get("id")
                )
                if new_shopify_id:
                    variants_pushed_count += len(prepared_variants)
                    logger.info(
                        f"[ShopifySync] Created Shopify product id={new_shopify_id} | "
                        f"variants_created={len(prepared_variants)}"
                    )
                    if collection_ids:
                        await add_product_to_collections(
                            shop=shop_domain,
                            access_token=access_token,
                            product_id=new_shopify_id,
                            collection_ids=collection_ids,
                        )
                else:
                    logger.error(
                        f"[ShopifySync] productSet succeeded but returned no product id"
                    )
                    failure_count += len(prepared_variants)
        except Exception as e:
            logger.error(f"[ShopifySync] Product creation exception: {e}")
            failure_count += len(prepared_variants)

    else:
        # ── Add variants to an existing Shopify product ────────────────
        logger.info(
            f"[ShopifySync] Adding {len(prepared_variants)} variant(s) to "
            f"existing product {existing_shopify_product_id}."
        )
        for vp in prepared_variants:
            try:
                result = await add_variant_to_existing_product(
                    shop=shop_domain,
                    access_token=access_token,
                    product_id=existing_shopify_product_id,
                    variant_data={
                        "price": vp["price"],
                        "sku": vp["asin"],
                        "stock": vp.get("stock_quantity", 0),
                        "weight": vp.get("weight"),
                        "image_url": vp.get("image_url"),
                    },
                    all_options=vp.get("attributes", []),
                )
                if result.get("already_exists"):
                    logger.info(
                        f"[ShopifySync] Variant {vp['asin']} already exists — skipping."
                    )
                    variants_pushed_count += 1
                elif "errors" not in result and not result.get("userErrors"):
                    variants_pushed_count += 1
                    logger.info(
                        f"[ShopifySync] Variant added: asin={vp['asin']}"
                    )
                else:
                    failure_count += 1
                    logger.warning(
                        f"[ShopifySync] Variant push failed for {vp['asin']}: "
                        f"{result.get('errors') or result.get('userErrors')}"
                    )
            except Exception as e:
                failure_count += 1
                logger.error(
                    f"[ShopifySync] Exception adding variant {vp['asin']}: {e}"
                )

        if collection_ids:
            await add_product_to_collections(
                shop=shop_domain,
                access_token=access_token,
                product_id=existing_shopify_product_id,
                collection_ids=collection_ids,
            )

        logger.info(
            f"[ShopifySync] Update done | product={existing_shopify_product_id} | "
            f"variants_updated={variants_pushed_count} | "
            f"variants_failed={failure_count}"
        )

    return variants_pushed_count, failure_count, new_shopify_id

