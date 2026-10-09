# ============================================
# app/api/routes/pricing.py
# Pricing API Routes
# + ✅ NAYA: Shopify par bhi price update karo
# ============================================

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product, ShopifyStore
from app.schemas.pricing import SinglePricingUpdate, BulkPricingUpdate
from app.services.pricing import pricing_service
from app.services.shopify import sync_update_shopify_price

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/countries")
def get_countries():
    """Dropdown ke liye saari countries"""
    try:
        return pricing_service.get_all_countries()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/product/{product_id}")
def get_product_pricing(product_id: str):
    """Ek product ki pricing"""
    try:
        return pricing_service.get_pricing_for_product(product_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update")
async def update_pricing(
    data: SinglePricingUpdate,
    db: Session = Depends(get_db),
):
    """Ek product ka pricing update + Shopify par bhi update"""
    try:
        result = pricing_service.update_single(
            product_id=data.product_id,
            country_id=data.country_id,
            markup_type=data.markup_type,
            markup_value=data.markup_value,
            tax_rate=data.tax_rate,
        )

        # ✅ NAYA: Shopify par bhi update karo
        product = db.query(Product).filter(Product.id == int(data.product_id)).first()
        if product and product.shopify_product_id:
            store = db.query(ShopifyStore).first()
            if store and store.access_token:
                try:
                    await sync_update_shopify_price(
                        shop=store.shop_domain,
                        access_token=store.access_token,
                        shopify_product_id=product.shopify_product_id,
                        new_price=product.price,
                    )
                    logger.info(f"✅ Shopify updated: {product.asin} → ${product.price}")
                except Exception as e:
                    logger.error(f"❌ Shopify update failed: {e}")

        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk-update")
async def bulk_update(
    data: BulkPricingUpdate,
    db: Session = Depends(get_db),
):
    """Bulk update - saare products par apply + Shopify par bhi update"""
    try:
        result = pricing_service.bulk_update(
            country_id=data.country_id,
            markup_type=data.markup_type,
            markup_value=data.markup_value,
            tax_rate=data.tax_rate,
        )

        # ✅ NAYA: Shopify par bhi update karo
        store = db.query(ShopifyStore).first()
        if store and store.access_token:
            products = db.query(Product).filter(
                Product.shopify_product_id != None  # noqa: E711
            ).all()

            shopify_updated = 0
            for product in products:
                try:
                    await sync_update_shopify_price(
                        shop=store.shop_domain,
                        access_token=store.access_token,
                        shopify_product_id=product.shopify_product_id,
                        new_price=product.price,
                    )
                    shopify_updated += 1
                except Exception as e:
                    logger.error(f"❌ Shopify update failed for {product.asin}: {e}")

            logger.info(f"✅ Shopify updated: {shopify_updated} products")
            result["shopify_updated"] = shopify_updated

        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))