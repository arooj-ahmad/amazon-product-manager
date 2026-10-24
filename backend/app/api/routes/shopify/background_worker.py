# app/api/routes/shopify/background_worker.py

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

# ✅ Saare helpers (including _build_product_data_for_shopify) ab helpers.py se aa rahe hain
from .helpers import (
    _resolve_markup, 
    apply_markup_cap, 
    _extract_weight, 
    extract_all_variations, 
    _verify_parent_match,
    _get_valid_access_token,
    _build_product_data_for_shopify  # ✅ Yeh add kiya hai
)

logger = logging.getLogger(__name__)

async def _background_fetch_and_push(
    amazon_url: str, shop_domain: str, store_id: int,
    markup, markup_type, extra_percent, collection_ids: list,
):
    db = SessionLocal()
    try:
        logger.info(f"🔄 Background job START (Apify Only): {amazon_url}")
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

        asin = data["asin"]
        parent_asin = data.get("parent_asin")
        
        if db.query(Product).filter(Product.asin == asin).first():
            logger.warning(f"⚠️ ASIN {asin} already exists")
            return

        existing_parent = None
        if parent_asin:
            existing_parent = db.query(Product).filter(
                Product.parent_asin == parent_asin, Product.asin != asin,
                Product.shopify_product_id.isnot(None)
            ).first()
            if existing_parent and not _verify_parent_match(existing_parent, data):
                existing_parent = None

        all_variations = extract_all_variations(data)
        
        # Token & Markup
        try:
            user_markup, user_markup_type, user_extra, user_tax_rate = _resolve_markup(store, markup, markup_type, extra_percent)
        except ValueError as e:
            logger.error(f"❌ Markup resolve fail: {e}")
            return

        user_markup = apply_markup_cap(user_markup, user_markup_type)
        final_price = calculate_final_price(
            amazon_price=data.get("amazon_price"), 
            markup=user_markup, 
            markup_type=user_markup_type, 
            extra_percent=user_extra, 
            tax_rate=user_tax_rate
        )
        weight_str = _extract_weight(data)

        # Save to DB
        new_product = Product(
            asin=asin, parent_asin=parent_asin, is_variation=data.get("is_variation", False),
            title=data.get("title"), brand=data.get("brand"), description=data.get("description") or "",
            image_url=data.get("image_url"), images=data.get("images", []), specifications=data.get("specifications", {}),
            rating=data.get("rating"), reviews_count=data.get("reviews_count"),
            availability=data.get("availability", "In Stock"), is_available=data.get("is_available", False),
            stock_quantity=data.get("stock_quantity", 0), amazon_price=data.get("amazon_price"), price=final_price,
            markup=user_markup, markup_type=user_markup_type, extra_percent=user_extra, tax_rate=user_tax_rate,
            is_manual_override=False, variant_attributes=data.get("variant_attributes", []),
            categories=data.get("categories", []), tags=data.get("tags", []), feature_bullets=data.get("feature_bullets", []),
            shopify_store_id=store.id, shopify_status="active"
        )
        db.add(new_product)
        db.commit()
        db.refresh(new_product)

        # ── 4. Shopify Push ──
        shopify_pushed = False
        shopify_product_id = None

        try:
            access_token = await _get_valid_access_token(store, db)
            
            if existing_parent and existing_parent.shopify_product_id:
                # Add variant to existing product
                result = await add_variant_to_existing_product(
                    shop=shop_domain, access_token=access_token,
                    product_id=existing_parent.shopify_product_id,
                    variant_data={"price": final_price, "sku": asin, "stock": new_product.stock_quantity or 0, "weight": weight_str},
                    all_options=all_variations,
                )
                
                if "errors" not in result:
                    shopify_pushed = True
                    shopify_product_id = existing_parent.shopify_product_id
                    new_product.shopify_product_id = shopify_product_id
                    new_product.shopify_handle = existing_parent.shopify_handle
                    db.commit()
            else:
                # Create new product
                product_data = _build_product_data_for_shopify(data=data, product=new_product)
                
                result = await create_shopify_product(
                    shop=shop_domain, access_token=access_token, product_data=product_data,
                )

                if "errors" not in result:
                    shopify_pushed = True
                    shopify_product_id = result.get("data", {}).get("productSet", {}).get("product", {}).get("id")
                    if shopify_product_id:
                        new_product.shopify_product_id = shopify_product_id
                        new_product.shopify_handle = result.get("data", {}).get("productSet", {}).get("product", {}).get("handle")
                        db.commit()

            if shopify_pushed and shopify_product_id and collection_ids:
                await add_product_to_collections(
                    shop=shop_domain, access_token=access_token,
                    product_id=shopify_product_id, collection_ids=collection_ids,
                )

        except Exception as e:
            logger.error(f"❌ Background: Shopify push fail: {e}")

        logger.info(f"🏁 Background DONE: ASIN={asin}, pushed={shopify_pushed}")
        
    except Exception as e:
        logger.exception(f"❌ Background crashed: {e}")
    finally:
        db.close()