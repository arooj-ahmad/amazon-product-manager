# ============================================
# app/api/routes/shopify/background_worker.py
# ============================================

import asyncio
import logging
from datetime import datetime, timezone
from app.database import SessionLocal
from app.models import Product, ShopifyStore
from app.services.amazon import ApifyError, calculate_final_price, fetch_product_from_apify
from app.services.shopify import (
    create_shopify_product, 
    add_variant_to_existing_product, 
    add_product_to_collections, 
    shopify_graphql
)

from .helpers import (
    _resolve_markup, 
    apply_markup_cap, 
    _extract_weight, 
    _verify_parent_match,
    _get_valid_access_token,
    _build_product_data_for_shopify
)

logger = logging.getLogger(__name__)

async def _background_fetch_and_push(
    amazon_url: str, shop_domain: str, store_id: int,
    markup, markup_type, extra_percent, collection_ids: list,
):
    db = SessionLocal()
    try:
        logger.info(f"🔄 Background job START (All Variants): {amazon_url}")
        store = db.query(ShopifyStore).filter(ShopifyStore.id == store_id).first()
        if not store: return

        loop = asyncio.get_running_loop()
        try:
            data = await loop.run_in_executor(None, fetch_product_from_apify, amazon_url)
        except ApifyError as e:
            logger.error(f"❌ Apify fail: {e}")
            return

        if not data or not data.get("asin"): return

        # ✅ 1. Saare variantAsins nikaalein
        variant_asins = data.get("variant_asins") or [data["asin"]]
        
        # ✅ Main product ke variant_attributes
        main_variant_attrs = data.get("variant_attributes") or []

        # ✅ VariantDetails se har ASIN ke attributes ka map banayein
        variant_details_map = {}
        for vd in (data.get("variant_details") or []):
            vd_asin = vd.get("asin")
            vd_attrs = vd.get("attributes") or []
            if vd_asin:
                variant_details_map[vd_asin] = vd_attrs

        logger.info(f"🔍 DEBUG: Total {len(variant_asins)} variants to process.")

        # ✅ 2. Base Product setup
        base_asin = data["asin"]
        existing_shopify_product_id = None
        existing_parent_db = db.query(Product).filter(
            Product.asin == base_asin,
            Product.shopify_product_id.isnot(None)
        ).first()

        if existing_parent_db:
            existing_shopify_product_id = existing_parent_db.shopify_product_id
            logger.info(f"✅ Parent already exists: {existing_shopify_product_id}")

        # Markup & Pricing
        user_markup, user_markup_type, user_extra, user_tax_rate = _resolve_markup(store, markup, markup_type, extra_percent)
        user_markup = apply_markup_cap(user_markup, user_markup_type)
        access_token = await _get_valid_access_token(store, db)

        # ✅ 3. Loop har variant ASIN par
        for index, v_asin in enumerate(variant_asins):
            logger.info(f"🔄 Processing {index+1}/{len(variant_asins)}: ASIN={v_asin}")

            # Agar DB mein pehle se hai, skip
            if db.query(Product).filter(Product.asin == v_asin).first():
                logger.info(f"⏭️ Skipping ASIN={v_asin}, already in DB.")
                continue

            # Attributes uthayein:
            # 1. Agar variant_details_map mein hai, to wahan se
            # 2. Nahi to main product ke variant_attributes se
            variant_attrs = variant_details_map.get(v_asin) or main_variant_attrs

            # Us specific variant ka data fetch karein
            v_url = f"https://www.amazon.com/dp/{v_asin}"
            try:
                v_data = await loop.run_in_executor(None, fetch_product_from_apify, v_url)
            except Exception as e:
                logger.error(f"❌ Fetch fail for {v_asin}: {e}")
                continue

            if not v_data or not v_data.get("asin"):
                continue

            final_price = calculate_final_price(
                amazon_price=v_data.get("amazon_price"), 
                markup=user_markup, 
                markup_type=user_markup_type, 
                extra_percent=user_extra, 
                tax_rate=user_tax_rate
            )
            weight_str = _extract_weight(v_data)

            # DB mein save (agar attributes khali hain to bhi save hoga)
            new_product = Product(
                asin=v_asin, parent_asin=base_asin, is_variation=(index > 0),
                title=v_data.get("title"), brand=v_data.get("brand"), description=v_data.get("description") or "",
                image_url=v_data.get("image_url"), images=v_data.get("images", []), specifications=v_data.get("specifications", {}),
                rating=v_data.get("rating"), reviews_count=v_data.get("reviews_count"),
                availability=v_data.get("availability", "In Stock"), is_available=v_data.get("is_available", False),
                stock_quantity=v_data.get("stock_quantity", 0), amazon_price=v_data.get("amazon_price"), price=final_price,
                markup=user_markup, markup_type=user_markup_type, extra_percent=user_extra, tax_rate=user_tax_rate,
                is_manual_override=False, variant_attributes=variant_attrs,
                categories=v_data.get("categories", []), tags=v_data.get("tags", []), feature_bullets=v_data.get("feature_bullets", []),
                shopify_store_id=store.id, shopify_status="active"
            )
            db.add(new_product)
            db.commit()
            db.refresh(new_product)

            # Shopify Push
            try:
                if existing_shopify_product_id:
                    # Parent already exists -> Add variant
                    result = await add_variant_to_existing_product(
                        shop=shop_domain, access_token=access_token,
                        product_id=existing_shopify_product_id,
                        variant_data={
                            "price": final_price, 
                            "sku": v_asin, 
                            "stock": new_product.stock_quantity or 0, 
                            "weight": weight_str,
                            "image_url": new_product.image_url
                        },
                        all_options=variant_attrs,
                    )
                    
                    if "errors" not in result:
                        new_product.shopify_product_id = existing_shopify_product_id
                        db.commit()
                else:
                    # Pehli dafa -> Create new product
                    v_data["variant_attributes"] = variant_attrs
                    product_data = _build_product_data_for_shopify(data=v_data, product=new_product)
                    
                    result = await create_shopify_product(
                        shop=shop_domain, access_token=access_token, product_data=product_data,
                    )

                    if "errors" not in result:
                        new_id = result.get("data", {}).get("productSet", {}).get("product", {}).get("id")
                        if new_id:
                            existing_shopify_product_id = new_id
                            new_product.shopify_product_id = new_id
                            db.commit()

                # Collections
                if new_product.shopify_product_id and collection_ids:
                    await add_product_to_collections(
                        shop=shop_domain, access_token=access_token,
                        product_id=new_product.shopify_product_id, collection_ids=collection_ids,
                    )

            except Exception as e:
                logger.error(f"❌ Shopify push fail for {v_asin}: {e}")

        logger.info(f"🏁 Background DONE: All variants processed.")
        
    except Exception as e:
        logger.exception(f"❌ Background crashed: {e}")
    finally:
        db.close()