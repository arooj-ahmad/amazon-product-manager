# ============================================
# app/api/routes/shopify/background_worker.py
# + ✅ NAYA: Ek URL se saare variants add karega
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

        # ✅ 1. Apify se saare variantAsins nikaalein (Agar nahi hain to khud ka asin)
        variant_asins = data.get("variantAsins") or []
        if not variant_asins:
            variant_asins = [data["asin"]]

        logger.info(f"🔍 DEBUG: Total {len(variant_asins)} variants found to process.")

        # ✅ 2. Base Product setup (Pehla variant parent banega)
        base_asin = variant_asins[0]
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
        for index, v_asin in enumerate(variant_asins):
            logger.info(f"🔄 Processing variant {index+1}/{len(variant_asins)}: ASIN={v_asin}")

            # Agar product database mein pehle se hai, to skip karein (Duplicate rokne ke liye)
            if db.query(Product).filter(Product.asin == v_asin).first():
                logger.info(f"⏭️ Skipping ASIN={v_asin}, already exists in DB.")
                continue

            # Us specific variant ka URL banayein aur uski details fetch karein
            v_url = f"https://www.amazon.com/dp/{v_asin}"
            try:
                v_data = await loop.run_in_executor(None, fetch_product_from_apify, v_url)
            except Exception as e:
                logger.error(f"❌ Failed to fetch variant {v_asin}: {e}")
                continue

            if not v_data or not v_data.get("asin"):
                continue

            # Is variant ka price calculate karein
            final_price = calculate_final_price(
                amazon_price=v_data.get("amazon_price"), 
                markup=user_markup, 
                markup_type=user_markup_type, 
                extra_percent=user_extra, 
                tax_rate=user_tax_rate
            )
            weight_str = _extract_weight(v_data)
            all_variations = extract_all_variations(v_data)

            # Database mein save karein
            new_product = Product(
                asin=v_asin, parent_asin=base_asin, is_variation=(index > 0),
                title=v_data.get("title"), brand=v_data.get("brand"), description=v_data.get("description") or "",
                image_url=v_data.get("image_url"), images=v_data.get("images", []), specifications=v_data.get("specifications", {}),
                rating=v_data.get("rating"), reviews_count=v_data.get("reviews_count"),
                availability=v_data.get("availability", "In Stock"), is_available=v_data.get("is_available", False),
                stock_quantity=v_data.get("stock_quantity", 0), amazon_price=v_data.get("amazon_price"), price=final_price,
                markup=user_markup, markup_type=user_markup_type, extra_percent=user_extra, tax_rate=user_tax_rate,
                is_manual_override=False, variant_attributes=v_data.get("variant_attributes", []),
                categories=v_data.get("categories", []), tags=v_data.get("tags", []), feature_bullets=v_data.get("feature_bullets", []),
                shopify_store_id=store.id, shopify_status="active"
            )
            db.add(new_product)
            db.commit()
            db.refresh(new_product)

            # Shopify Push
            try:
                if existing_shopify_product_id:
                    # Agar parent pehle se bana hua hai, to usme naya variant add karein
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
                        all_options=all_variations,
                    )
                    
                    if "errors" not in result:
                        new_product.shopify_product_id = existing_shopify_product_id
                        new_product.shopify_handle = existing_parent_db.shopify_handle if existing_parent_db else None
                        db.commit()
                else:
                    # Agar pehli dafa hai, to naya Shopify product create karein
                    product_data = _build_product_data_for_shopify(data=v_data, product=new_product)
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