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
    extract_all_variations, 
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
        if not store: 
            logger.error("❌ Background: Store not found")
            return

        loop = asyncio.get_running_loop()
        try:
            data = await loop.run_in_executor(None, fetch_product_from_apify, amazon_url)
        except ApifyError as e:
            logger.error(f"❌ Apify fail: {e}")
            return

        if not data or not data.get("asin"): 
            logger.error("❌ Background: ASIN missing in response")
            return

        # ✅ 1. Apify ke data se variant_details nikaalein (jisme saari details hain)
        variant_details = data.get("variant_details") or []
        if not variant_details:
            variant_details = [{
                "asin": data["asin"],
                "attributes": data.get("variant_attributes", []),
                "thumbnail": data.get("image_url"),
                "images": data.get("images", [])
            }]

        logger.info(f"🔍 DEBUG: Total {len(variant_details)} variants found to process.")

        # ✅ 2. Base Product setup (Pehla variant parent banega)
        base_asin = data["asin"]
        existing_shopify_product_id = None
        existing_parent_db = None

        # Check karein ke kya pehla variant pehle se add hai (parent)
        existing_parent_db = db.query(Product).filter(
            Product.asin == base_asin,
            Product.shopify_product_id.isnot(None)
        ).first()

        if existing_parent_db:
            existing_shopify_product_id = existing_parent_db.shopify_product_id
            logger.info(f"✅ Base product already exists in Shopify: {existing_shopify_product_id}")

        # Markup & Pricing
        try:
            user_markup, user_markup_type, user_extra, user_tax_rate = _resolve_markup(store, markup, markup_type, extra_percent)
        except ValueError as e:
            logger.error(f"❌ Markup resolve fail: {e}")
            return

        user_markup = apply_markup_cap(user_markup, user_markup_type)
        access_token = await _get_valid_access_token(store, db)

        # ✅ 3. Har ek variant par loop chalayein
        for index, v_detail in enumerate(variant_details):
            v_asin = v_detail.get("asin")
            v_name = v_detail.get("name", "")
            
            if not v_asin:
                continue

            logger.info(f"🔄 Processing variant {index+1}/{len(variant_details)}: {v_name} (ASIN={v_asin})")

            # Agar product database mein pehle se hai, to skip karein
            if db.query(Product).filter(Product.asin == v_asin).first():
                logger.info(f"⏭️ Skipping ASIN={v_asin}, already exists in DB.")
                continue

            # ✅ Attributes seedha Apify ke data se uthayein (No fallback)
            variant_attrs = v_detail.get("attributes") or []
            
            if not variant_attrs:
                logger.warning(f"⚠️ ASIN={v_asin} ke liye attributes nahi mile. Skip kar rahe hain.")
                continue

            # Price calculate karein
            final_price = calculate_final_price(
                amazon_price=data.get("amazon_price"), 
                markup=user_markup, 
                markup_type=user_markup_type, 
                extra_percent=user_extra, 
                tax_rate=user_tax_rate
            )
            weight_str = _extract_weight(data)

            v_image = v_detail.get("thumbnail") or data.get("image_url")
            v_images = v_detail.get("images") or data.get("images", [])

            # Database mein save karein
            new_product = Product(
                asin=v_asin, parent_asin=base_asin, is_variation=(index > 0),
                title=data.get("title"), brand=data.get("brand"), description=data.get("description") or "",
                image_url=v_image, images=v_images, specifications=data.get("specifications", {}),
                rating=data.get("rating"), reviews_count=data.get("reviews_count"),
                availability=data.get("availability", "In Stock"), is_available=data.get("is_available", False),
                stock_quantity=data.get("stock_quantity", 0), amazon_price=data.get("amazon_price"), price=final_price,
                markup=user_markup, markup_type=user_markup_type, extra_percent=user_extra, tax_rate=user_tax_rate,
                is_manual_override=False, variant_attributes=variant_attrs,
                categories=data.get("categories", []), tags=data.get("tags", []), feature_bullets=data.get("feature_bullets", []),
                shopify_store_id=store.id, shopify_status="active"
            )
            db.add(new_product)
            db.commit()
            db.refresh(new_product)

            # Shopify Push
            try:
                if existing_shopify_product_id:
                    # Agar parent pehle se bana hua hai, to naya variant add karein
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
                        new_product.shopify_handle = existing_parent_db.shopify_handle if existing_parent_db else None
                        db.commit()
                else:
                    # Agar pehli dafa hai, to naya Shopify product create karein
                    # Base data mein current variant ke attributes daal dein
                    data["variant_attributes"] = variant_attrs
                    product_data = _build_product_data_for_shopify(data=data, product=new_product)
                    
                    result = await create_shopify_product(
                        shop=shop_domain, access_token=access_token, product_data=product_data,
                    )

                    if "errors" not in result:
                        new_id = result.get("data", {}).get("productSet", {}).get("product", {}).get("id")
                        if new_id:
                            existing_shopify_product_id = new_id
                            new_product.shopify_product_id = new_id
                            new_product.shopify_handle = result.get("data", {}).get("productSet", {}).get("product", {}).get("handle")
                            db.commit()

                # Collections add karein
                if new_product.shopify_product_id and collection_ids:
                    await add_product_to_collections(
                        shop=shop_domain, access_token=access_token,
                        product_id=new_product.shopify_product_id, collection_ids=collection_ids,
                    )

            except Exception as e:
                logger.error(f"❌ Shopify push fail for {v_asin}: {e}")

        logger.info(f"🏁 Background DONE: All variants processed successfully.")
        
    except Exception as e:
        logger.exception(f"❌ Background crashed: {e}")
    finally:
        db.close()