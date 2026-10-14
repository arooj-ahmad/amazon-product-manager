# ============================================
# app/api/routes/pricing.py
# Pricing API Routes
# + ✅ NAYA: Shopify par bhi price update karo
# + ✅ NAYA: extra_percent support (Fixed + Percent)
# + ✅ NAYA: Store default markup (GET + PUT) — sidebar settings
# ============================================

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product, ShopifyStore
from app.schemas.pricing import SinglePricingUpdate, BulkPricingUpdate
from app.services.pricing import pricing_service
from app.services.shopify import sync_update_shopify_price

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================
# ✅ NAYA: STORE DEFAULT MARKUP — GET
# ============================================
@router.get("/store-default")
def get_store_default_markup(
    shop_domain: str = Query(..., description="Shopify store domain"),
    db: Session = Depends(get_db),
):
    """
    Store ka saved default markup return karo.
    Ye markup add-product ke waqt use hota hai.
    """
    store = db.query(ShopifyStore).filter(
        ShopifyStore.shop_domain == shop_domain
    ).first()

    if not store:
        raise HTTPException(
            status_code=404,
            detail=f"Store not found: {shop_domain}",
        )

    return {
        "shop_domain": store.shop_domain,
        "markup": float(getattr(store, "default_markup", None) or 2.0),
        "markup_type": getattr(store, "default_markup_type", None) or "fixed",
        "extra_percent": float(
            getattr(store, "default_extra_percent", None) or 0.0
        ),
    }


# ============================================
# ✅ NAYA: STORE DEFAULT MARKUP — PUT
# ============================================
@router.put("/store-default")
def update_store_default_markup(
    shop_domain: str = Body(..., embed=True),
    markup: float = Body(..., embed=True),
    markup_type: str = Body(..., embed=True),
    extra_percent: float = Body(0.0, embed=True),
    db: Session = Depends(get_db),
):
    """
    Store ka default markup save karo.
    Ye markup har naye add-product me use hoga.
    """
    if markup_type not in ("fixed", "percent", "both"):
        raise HTTPException(
            status_code=400,
            detail="markup_type must be one of: fixed, percent, both",
        )

    if markup < 0:
        raise HTTPException(status_code=400, detail="markup must be >= 0")

    if extra_percent < 0:
        raise HTTPException(
            status_code=400, detail="extra_percent must be >= 0"
        )

    store = db.query(ShopifyStore).filter(
        ShopifyStore.shop_domain == shop_domain
    ).first()

    if not store:
        raise HTTPException(
            status_code=404,
            detail=f"Store not found: {shop_domain}",
        )

    store.default_markup = markup
    store.default_markup_type = markup_type
    store.default_extra_percent = extra_percent
    db.commit()
    db.refresh(store)

    logger.info(
        f"✅ Store default markup saved for {shop_domain}: "
        f"{markup} ({markup_type}), extra={extra_percent}%"
    )

    return {
        "success": True,
        "message": "Default markup saved successfully",
        "shop_domain": store.shop_domain,
        "markup": float(store.default_markup),
        "markup_type": store.default_markup_type,
        "extra_percent": float(store.default_extra_percent or 0.0),
    }


# ============================================
# COUNTRIES
# ============================================
@router.get("/countries")
def get_countries():
    """Dropdown ke liye saari countries"""
    try:
        return pricing_service.get_all_countries()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# PRODUCT PRICING
# ============================================
@router.get("/product/{product_id}")
def get_product_pricing(product_id: str):
    """Ek product ki pricing"""
    try:
        return pricing_service.get_pricing_for_product(product_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# SINGLE UPDATE
# ============================================
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
            extra_percent=getattr(data, "extra_percent", 0.0),   # ✅ NAYA
        )

        # ✅ NAYA: Shopify par bhi update karo
        product = db.query(Product).filter(
            Product.id == int(data.product_id)
        ).first()
        if product and product.shopify_product_id:
            store = db.query(ShopifyStore).first()
            if store and store.access_token:
                try:
                    await sync_update_shopify_price(
                        shop_domain=store.shop_domain,
                        access_token=store.access_token,
                        shopify_product_id=product.shopify_product_id,
                        new_price=product.price,
                        refresh_token=store.refresh_token,
                    )
                    logger.info(
                        f"✅ Shopify updated: {product.asin} "
                        f"→ ${product.price}"
                    )
                except Exception as e:
                    logger.error(f"❌ Shopify update failed: {e}")

        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# BULK UPDATE
# ============================================
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
            extra_percent=getattr(data, "extra_percent", 0.0),   # ✅ NAYA
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
                        shop_domain=store.shop_domain,
                        access_token=store.access_token,
                        shopify_product_id=product.shopify_product_id,
                        new_price=product.price,
                        refresh_token=store.refresh_token,
                    )
                    shopify_updated += 1
                except Exception as e:
                    logger.error(
                        f"❌ Shopify update failed for {product.asin}: {e}"
                    )

            logger.info(f"✅ Shopify updated: {shopify_updated} products")
            result["shopify_updated"] = shopify_updated

        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))