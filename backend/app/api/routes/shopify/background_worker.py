# ============================================
# app/api/routes/shopify/background_worker.py
# ============================================

import asyncio
import logging
from datetime import datetime, timezone
from app.database import SessionLocal
from app.models import Product, ShopifyStore
from app.services.amazon import ApifyError, calculate_final_price, fetch_product_from_apify, parse_price
from app.services.shopify import (
    create_shopify_product, 
    create_shopify_product_with_variants,
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
    _build_product_data_for_shopify,
    extract_all_variations,
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
            logger.error(f"❌ Store id {store_id} not found")
            return

        loop = asyncio.get_running_loop()
        try:
            data = await loop.run_in_executor(None, fetch_product_from_apify, amazon_url)
        except ApifyError as e:
            logger.error(f"❌ Apify fail: {e}")
            return

        if not data or not data.get("asin"):
            logger.error("❌ No product data or ASIN returned by Apify")
            return

        base_asin = data["asin"]

        # ✅ 1. Saare unique child ASINs nikaalein (variantAsins + variantDetails + variants)
        raw_asins = []
        for a in (data.get("variant_asins") or data.get("variantAsins") or []):
            if a and isinstance(a, str):
                raw_asins.append(a.strip())

        raw_details = data.get("variant_details") or data.get("variantDetails") or []
        for vd in raw_details:
            if isinstance(vd, dict):
                a = vd.get("asin")
                if a and isinstance(a, str):
                    raw_asins.append(a.strip())

        for v in (data.get("variants") or []):
            if isinstance(v, dict):
                a = v.get("asin")
                if a and isinstance(a, str):
                    raw_asins.append(a.strip())

        # Main ASIN include karein
        if base_asin and isinstance(base_asin, str):
            raw_asins.insert(0, base_asin.strip())

        # Deduplicate karein (order maintain)
        seen = set()
        variant_asins = []
        for a in raw_asins:
            if a and a not in seen:
                seen.add(a)
                variant_asins.append(a)

        discovered_count = len(raw_asins)
        unique_count = len(variant_asins)
        logger.info(f"🔍 Discovered {discovered_count} variations across Apify response.")
        logger.info(f"🔍 DEBUG: Total {unique_count} variants to process (unique, including base ASIN: {base_asin}).")

        # ✅ VariantDetails map banayein
        variant_details_map = {}
        for vd in raw_details:
            if isinstance(vd, dict) and vd.get("asin"):
                variant_details_map[vd["asin"]] = vd

        # ✅ 2. Base Product setup
        existing_shopify_product_id = None
        existing_parent_db = db.query(Product).filter(
            Product.asin == base_asin,
            Product.shopify_product_id.isnot(None)
        ).first()

        if existing_parent_db:
            existing_shopify_product_id = existing_parent_db.shopify_product_id
            logger.info(f"✅ Parent already exists in Shopify: {existing_shopify_product_id}")

        # Markup & Pricing
        user_markup, user_markup_type, user_extra, user_tax_rate = _resolve_markup(store, markup, markup_type, extra_percent)
        user_markup = apply_markup_cap(user_markup, user_markup_type)
        access_token = await _get_valid_access_token(store, db)

        details_fetched_count = 0
        variants_pushed_count = 0
        failure_count = 0
        prepared_variants = []

        # ✅ 3. Har variant ASIN ka data prepare karein
        for index, v_asin in enumerate(variant_asins):
            logger.info(f"🔄 Processing {index+1}/{len(variant_asins)}: ASIN={v_asin}")

            v_data = None
            vd = variant_details_map.get(v_asin) or {}

            if v_asin == base_asin:
                v_data = data
                v_attrs = data.get("variant_attributes") or []
                v_price = data.get("amazon_price")
                v_imgs = data.get("images") or []
                v_thumb = data.get("image_url")
                v_name = data.get("title", "")
            else:
                v_attrs = vd.get("attributes") or []
                v_price = parse_price(vd.get("price"))
                v_imgs = vd.get("images") or []
                v_thumb = vd.get("thumbnail")
                v_name = vd.get("name", "")

                # Fetch individual child ASIN details only when required (missing prices, images, availability, or attrs)
                needs_fetch = (v_price is None or not v_attrs)
                if needs_fetch:
                    v_url = f"https://www.amazon.com/dp/{v_asin}"
                    try:
                        logger.info(f"🌐 Fetching details for child ASIN {v_asin} (missing required data)...")
                        v_data = await loop.run_in_executor(None, fetch_product_from_apify, v_url)
                        details_fetched_count += 1
                        if v_data:
                            if v_data.get("amazon_price") is not None:
                                v_price = v_data["amazon_price"]
                            if v_data.get("variant_attributes"):
                                v_attrs = v_data["variant_attributes"]
                            if v_data.get("images"):
                                v_imgs = v_data["images"]
                            if v_data.get("image_url"):
                                v_thumb = v_data["image_url"]
                            if v_data.get("title"):
                                v_name = v_data["title"]
                    except Exception as e:
                        logger.warning(f"⚠️ Fetch child details failed for {v_asin}: {e}")

                # Handle missing prices safely (fall back to base product price)
                if v_price is None:
                    v_price = data.get("amazon_price")
                    logger.info(f"ℹ️ Fallback to base product price for ASIN={v_asin}: ${v_price}")

            if not v_attrs:
                v_attrs = extract_all_variations(v_data or {"variant_attributes": []})
                if not v_attrs or (len(v_attrs) == 1 and v_attrs[0].get("value") == "Default"):
                    if v_name:
                        v_attrs = [{"name": "Style", "value": v_name}]
                    else:
                        v_attrs = [{"name": "Style", "value": f"Variant {index+1}"}]

            final_price = calculate_final_price(
                amazon_price=v_price,
                markup=user_markup,
                markup_type=user_markup_type,
                extra_percent=user_extra,
                tax_rate=user_tax_rate,
            )

            avail_text = (v_data.get("availability") if v_data else None) or data.get("availability") or "In Stock"
            is_avail = (v_data.get("is_available") if v_data else None)
            if is_avail is None:
                is_avail = data.get("is_available", True)

            stock_qty = (v_data.get("stock_quantity") if v_data else None)
            if stock_qty is None:
                stock_qty = data.get("stock_quantity", 100) if is_avail else 0

            weight_str = _extract_weight(v_data) if v_data else _extract_weight(data)
            img_url = (v_imgs[0] if v_imgs else None) or v_thumb or (v_data.get("image_url") if v_data else None) or data.get("image_url")

            # DB mein save / update
            db_product = db.query(Product).filter(Product.asin == v_asin).first()
            if not db_product:
                db_product = Product(
                    asin=v_asin,
                    parent_asin=base_asin if v_asin != base_asin else None,
                    is_variation=(v_asin != base_asin),
                    title=(v_data.get("title") if v_data else None) or data.get("title"),
                    brand=(v_data.get("brand") if v_data else None) or data.get("brand"),
                    description=(v_data.get("description") if v_data else None) or data.get("description") or "",
                    image_url=img_url,
                    images=v_imgs or data.get("images", []),
                    specifications=(v_data.get("specifications") if v_data else None) or data.get("specifications", {}),
                    rating=(v_data.get("rating") if v_data else None) or data.get("rating"),
                    reviews_count=(v_data.get("reviews_count") if v_data else None) or data.get("reviews_count"),
                    availability=avail_text,
                    is_available=is_avail,
                    stock_quantity=stock_qty,
                    amazon_price=v_price,
                    price=final_price,
                    markup=user_markup,
                    markup_type=user_markup_type,
                    extra_percent=user_extra,
                    tax_rate=user_tax_rate,
                    is_manual_override=False,
                    variant_attributes=v_attrs,
                    categories=data.get("categories", []),
                    tags=data.get("tags", []),
                    feature_bullets=(v_data.get("feature_bullets") if v_data else None) or data.get("feature_bullets", []),
                    shopify_store_id=store.id,
                    shopify_status="active" if is_avail else "draft",
                    shopify_product_id=existing_shopify_product_id,
                )
                db.add(db_product)
                db.commit()
                db.refresh(db_product)
            else:
                db_product.amazon_price = v_price
                db_product.price = final_price
                db_product.variant_attributes = v_attrs
                db_product.availability = avail_text
                db_product.is_available = is_avail
                db_product.stock_quantity = stock_qty
                if existing_shopify_product_id and not db_product.shopify_product_id:
                    db_product.shopify_product_id = existing_shopify_product_id
                db.commit()

            prepared_variants.append({
                "asin": v_asin,
                "title": v_name or v_asin,
                "price": final_price,
                "amazon_price": v_price,
                "stock": stock_qty,
                "weight": weight_str,
                "image_url": img_url,
                "options": v_attrs,
                "db_product": db_product,
            })

        # ✅ 4. Shopify Push: Build ONE Shopify product with multiple variants
        if not existing_shopify_product_id:
            logger.info(f"🚀 Creating new Shopify product with {len(prepared_variants)} variants...")
            base_db_prod = next((vp["db_product"] for vp in prepared_variants if vp["asin"] == base_asin), prepared_variants[0]["db_product"])
            product_data_for_create = _build_product_data_for_shopify(data=data, product=base_db_prod)

            try:
                result = await create_shopify_product_with_variants(
                    shop=shop_domain,
                    access_token=access_token,
                    product_data=product_data_for_create,
                    variants=prepared_variants,
                )

                if "errors" in result or result.get("data", {}).get("productSet", {}).get("userErrors"):
                    logger.error(f"❌ Failed to create product with variants: {result}")
                    failure_count += len(prepared_variants)
                else:
                    new_id = result.get("data", {}).get("productSet", {}).get("product", {}).get("id")
                    if new_id:
                        existing_shopify_product_id = new_id
                        for vp in prepared_variants:
                            vp_p = vp.get("db_product")
                            if vp_p:
                                vp_p.shopify_product_id = new_id
                        db.commit()
                        variants_pushed_count += len(prepared_variants)
                        logger.info(f"✅ Created Shopify product {new_id} with {len(prepared_variants)} variants")

                        if collection_ids:
                            await add_product_to_collections(
                                shop=shop_domain, access_token=access_token,
                                product_id=new_id, collection_ids=collection_ids,
                            )
            except Exception as e:
                logger.error(f"❌ Product creation exception: {e}")
                failure_count += len(prepared_variants)
        else:
            # Parent already exists -> Add/sync each variant
            logger.info(f"🚀 Adding {len(prepared_variants)} variants to existing Shopify product {existing_shopify_product_id}...")
            for vp in prepared_variants:
                try:
                    result = await add_variant_to_existing_product(
                        shop=shop_domain, access_token=access_token,
                        product_id=existing_shopify_product_id,
                        variant_data={
                            "price": vp["price"],
                            "sku": vp["asin"],
                            "stock": vp["stock"],
                            "weight": vp["weight"],
                            "image_url": vp["image_url"],
                        },
                        all_options=vp["options"],
                    )

                    if "errors" not in result and not result.get("userErrors"):
                        variants_pushed_count += 1
                        vp_p = vp.get("db_product")
                        if vp_p:
                            vp_p.shopify_product_id = existing_shopify_product_id
                            db.commit()
                    elif result.get("already_exists"):
                        variants_pushed_count += 1
                        logger.info(f"ℹ️ Variant {vp['asin']} already exists in Shopify")
                    else:
                        failure_count += 1
                        logger.error(f"❌ Failed to add variant {vp['asin']}: {result}")
                except Exception as e:
                    failure_count += 1
                    logger.error(f"❌ Shopify push fail for {vp['asin']}: {e}")

            if collection_ids and existing_shopify_product_id:
                try:
                    await add_product_to_collections(
                        shop=shop_domain, access_token=access_token,
                        product_id=existing_shopify_product_id, collection_ids=collection_ids,
                    )
                except Exception as e:
                    logger.error(f"❌ Failed to add product to collections: {e}")

        logger.info(
            f"🏁 Background job SUMMARY: Variations discovered: {discovered_count}, "
            f"Unique child ASINs: {unique_count}, Details fetched: {details_fetched_count}, "
            f"Shopify variants created/updated: {variants_pushed_count}, Failures: {failure_count}"
        )

    except Exception as e:
        logger.exception(f"❌ Background crashed: {e}")
    finally:
        db.close()