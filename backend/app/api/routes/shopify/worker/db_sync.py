# app/api/routes/shopify/worker/db_sync.py
import logging
from app.models import Product
from app.services.amazon import calculate_final_price

logger = logging.getLogger(__name__)

def save_or_update_db_product(db, data, base_asin, vp, user_markup, user_markup_type, user_extra, user_tax_rate, store_id, existing_shopify_product_id):
    """Product ko DB mein save ya update karta hai."""
    v_asin = vp["asin"]
    v_data = vp["raw_v_data"]
    final_price = calculate_final_price(
        amazon_price=vp["amazon_price"], markup=user_markup,
        markup_type=user_markup_type, extra_percent=user_extra, tax_rate=user_tax_rate
    )
    vp["price"] = final_price

    db_product = db.query(Product).filter(Product.asin == v_asin).first()
    if not db_product:
        db_product = Product(
            asin=v_asin, parent_asin=base_asin if v_asin != base_asin else None,
            is_variation=(v_asin != base_asin),
            title=(v_data.get("title") if v_data else None) or data.get("title"),
            brand=(v_data.get("brand") if v_data else None) or data.get("brand"),
            description=(v_data.get("description") if v_data else None) or data.get("description") or "",
            image_url=vp["image_url"], images=vp["images"],
            specifications=(v_data.get("specifications") if v_data else None) or data.get("specifications", {}),
            rating=(v_data.get("rating") if v_data else None) or data.get("rating"),
            reviews_count=(v_data.get("reviews_count") if v_data else None) or data.get("reviews_count"),
            availability=vp["availability"], is_available=vp["is_available"], stock_quantity=vp["stock_quantity"],
            amazon_price=vp["amazon_price"], price=final_price,
            markup=user_markup, markup_type=user_markup_type, extra_percent=user_extra, tax_rate=user_tax_rate,
            is_manual_override=False, variant_attributes=vp["attributes"],
            categories=data.get("categories", []), tags=data.get("tags", []),
            feature_bullets=(v_data.get("feature_bullets") if v_data else None) or data.get("feature_bullets", []),
            shopify_store_id=store_id, shopify_status="active" if vp["is_available"] else "draft",
            shopify_product_id=existing_shopify_product_id,
        )
        db.add(db_product)
        db.commit()
        db.refresh(db_product)
    else:
        db_product.amazon_price = vp["amazon_price"]
        db_product.price = final_price
        db_product.variant_attributes = vp["attributes"]
        db_product.availability = vp["availability"]
        db_product.is_available = vp["is_available"]
        db_product.stock_quantity = vp["stock_quantity"]
        if existing_shopify_product_id and not db_product.shopify_product_id:
            db_product.shopify_product_id = existing_shopify_product_id
        db.commit()

    vp["db_product"] = db_product
    return vp
