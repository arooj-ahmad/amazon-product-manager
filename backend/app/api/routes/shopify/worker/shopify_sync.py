# app/api/routes/shopify/worker/shopify_sync.py
import logging
from app.services.shopify import create_shopify_product_with_variants, add_variant_to_existing_product, add_product_to_collections
from ..helpers import _build_product_data_for_shopify

logger = logging.getLogger(__name__)

async def push_to_shopify(shop_domain, access_token, data, prepared_variants, existing_shopify_product_id, collection_ids, base_asin):
    variants_pushed_count, failure_count = 0, 0

    if not existing_shopify_product_id:
        logger.info(f"Creating new Shopify product with {len(prepared_variants)} variants...")
        base_db_prod = next((vp["db_product"] for vp in prepared_variants if vp["asin"] == base_asin), prepared_variants[0]["db_product"])
        product_data_for_create = _build_product_data_for_shopify(data=data, product=base_db_prod)

        try:
            result = await create_shopify_product_with_variants(
                shop=shop_domain, access_token=access_token,
                product_data=product_data_for_create, variants=prepared_variants,
            )
            if "errors" in result or result.get("data", {}).get("productSet", {}).get("userErrors"):
                failure_count += len(prepared_variants)
            else:
                new_id = result.get("data", {}).get("productSet", {}).get("product", {}).get("id")
                if new_id:
                    existing_shopify_product_id = new_id
                    variants_pushed_count += len(prepared_variants)
                    if collection_ids:
                        await add_product_to_collections(shop=shop_domain, access_token=access_token, product_id=new_id, collection_ids=collection_ids)
        except Exception as e:
            logger.error(f"Product creation exception: {e}")
            failure_count += len(prepared_variants)
    else:
        logger.info(f"Adding {len(prepared_variants)} variants to existing product {existing_shopify_product_id}...")
        for vp in prepared_variants:
            try:
                result = await add_variant_to_existing_product(
                    shop=shop_domain, access_token=access_token, product_id=existing_shopify_product_id,
                    variant_data={"price": vp["price"], "sku": vp["asin"], "stock": vp["stock_quantity"], "weight": vp["weight"], "image_url": vp["image_url"]},
                    all_options=vp["attributes"],
                )
                if "errors" not in result and not result.get("userErrors"):
                    variants_pushed_count += 1
                elif result.get("already_exists"):
                    variants_pushed_count += 1
                else:
                    failure_count += 1
            except Exception as e:
                failure_count += 1
                logger.error(f"Shopify push fail for {vp['asin']}: {e}")
        
        if collection_ids:
            await add_product_to_collections(shop=shop_domain, access_token=access_token, product_id=existing_shopify_product_id, collection_ids=collection_ids)

    return variants_pushed_count, failure_count, existing_shopify_product_id
