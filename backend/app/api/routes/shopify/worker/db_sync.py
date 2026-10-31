# app/api/routes/shopify/worker/db_sync.py
import logging
from app.models import Product
from app.services.amazon import calculate_final_price
from sqlalchemy.orm.attributes import flag_modified

logger = logging.getLogger(__name__)

def save_or_update_db_product(
    db, data, base_asin, vp, 
    user_markup, user_markup_type, user_extra, user_tax_rate, 
    store_id, existing_shopify_product_id
):
    """Product ko DB mein save ya update karta hai."""
    v_asin = vp["asin"]
    v_data = vp.get("raw_v_data") or {}
    
    final_price = calculate_final_price(
        amazon_price=vp["amazon_price"], 
        markup=user_markup,
        markup_type=user_markup_type, 
        extra_percent=user_extra, 
        tax_rate=user_tax_rate
    )
    vp["price"] = final_price

    # ✅ Rating aur Reviews extract karein (Safe handling)
    rating_val = v_data.get("rating") or data.get("rating")
    reviews_val = v_data.get("reviews_count") or data.get("reviews_count")

    try:
        # ✅ FIX 1: Store ID ko query mein shamil karein taake multi-store conflict na ho
        db_product = db.query(Product).filter(
            Product.asin == v_asin,
            Product.shopify_store_id == store_id
        ).first()
        
        if not db_product:
            # Naya product banayein
            db_product = Product(
                asin=v_asin, 
                parent_asin=base_asin if v_asin != base_asin else None,
                is_variation=(v_asin != base_asin),
                title=v_data.get("title") or data.get("title"),
                brand=v_data.get("brand") or data.get("brand"),
                description=v_data.get("description") or data.get("description") or "",
                image_url=vp.get("image_url"), 
                images=vp.get("images", []),
                specifications=v_data.get("specifications") or data.get("specifications", {}),
                
                # ✅ Physical Attrs & Specs
                product_details=v_data.get("product_details") or data.get("product_details", []),
                item_dimensions=v_data.get("item_dimensions") or data.get("item_dimensions"),
                item_weight=v_data.get("item_weight") or data.get("item_weight"),
                package_dimensions=v_data.get("package_dimensions") or data.get("package_dimensions"),
                size=v_data.get("size") or data.get("size"),
                color=v_data.get("color") or data.get("color"),
                material_type=v_data.get("material_type") or data.get("material_type"),
                model_number=v_data.get("model_number") or data.get("model_number"),
                
                rating=rating_val,              
                reviews_count=reviews_val,      
                availability=vp.get("availability"), 
                is_available=vp.get("is_available", True), 
                stock_quantity=vp.get("stock_quantity", 0),
                amazon_price=vp["amazon_price"], 
                price=final_price,
                markup=user_markup, 
                markup_type=user_markup_type, 
                extra_percent=user_extra, 
                tax_rate=user_tax_rate,
                is_manual_override=False, 
                variant_attributes=vp.get("attributes", {}),
                categories=data.get("categories", []), 
                tags=data.get("tags", []),
                feature_bullets=v_data.get("feature_bullets") or data.get("feature_bullets", []),
                shopify_store_id=store_id, 
                shopify_status="active" if vp.get("is_available") else "draft",
                shopify_product_id=existing_shopify_product_id,
            )
            db.add(db_product)
            db.commit()
            db.refresh(db_product)
            logger.info(f"✅ Created new product: {v_asin} (Rating: {rating_val}, Reviews: {reviews_val})")
            
        else:
            # Purana product update karein
            db_product.amazon_price = vp["amazon_price"]
            db_product.price = final_price
            db_product.variant_attributes = vp.get("attributes", {})
            db_product.availability = vp.get("availability")
            db_product.is_available = vp.get("is_available", True)
            db_product.stock_quantity = vp.get("stock_quantity", 0)
            
            # ✅ FIX 2: Update hote waqt basic details bhi update karein
            if v_data.get("title"): db_product.title = v_data["title"]
            if v_data.get("brand"): db_product.brand = v_data["brand"]
            if v_data.get("description"): db_product.description = v_data["description"]
            if vp.get("image_url"): db_product.image_url = vp["image_url"]
            if vp.get("images"): db_product.images = vp["images"]
            if v_data.get("feature_bullets"): db_product.feature_bullets = v_data["feature_bullets"]
            if data.get("tags"): db_product.tags = data["tags"]
            if data.get("categories"): db_product.categories = data["categories"]
            
            # ✅ Update karte waqt specs fields update karein
            if v_data.get("product_details") or data.get("product_details"):
                db_product.product_details = v_data.get("product_details") or data.get("product_details")
                flag_modified(db_product, "product_details") # PostgreSQL JSONB safety
                
            if v_data.get("item_dimensions") or data.get("item_dimensions"): 
                db_product.item_dimensions = v_data.get("item_dimensions") or data.get("item_dimensions")
            if v_data.get("item_weight") or data.get("item_weight"): 
                db_product.item_weight = v_data.get("item_weight") or data.get("item_weight")
            if v_data.get("package_dimensions") or data.get("package_dimensions"): 
                db_product.package_dimensions = v_data.get("package_dimensions") or data.get("package_dimensions")
            if v_data.get("size") or data.get("size"): 
                db_product.size = v_data.get("size") or data.get("size")
            if v_data.get("color") or data.get("color"): 
                db_product.color = v_data.get("color") or data.get("color")
            if v_data.get("material_type") or data.get("material_type"): 
                db_product.material_type = v_data.get("material_type") or data.get("material_type")
            if v_data.get("model_number") or data.get("model_number"): 
                db_product.model_number = v_data.get("model_number") or data.get("model_number")

            # ✅ Update karte waqt rating aur reviews update karein
            if rating_val is not None: db_product.rating = rating_val
            if reviews_val is not None: db_product.reviews_count = reviews_val
                
            if existing_shopify_product_id and not db_product.shopify_product_id:
                db_product.shopify_product_id = existing_shopify_product_id
                
            db.commit()
            logger.info(f"✅ Updated existing product: {v_asin}")

        vp["db_product"] = db_product
        return vp

    except Exception as e:
        # ✅ Error handling (Rollback) taake app crash na ho
        db.rollback()
        logger.error(f"❌ DB error for {v_asin}: {e}", exc_info=True)
        vp["db_product"] = None
        return vp