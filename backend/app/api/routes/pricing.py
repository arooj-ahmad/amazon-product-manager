# ============================================
# app/api/routes/pricing.py
# Pricing API Routes
# + ✅ NAYA: Shopify par bhi price update karo
# + ✅ NAYA: extra_percent support (Fixed + Percent)
# + ✅ NAYA: Store default markup (GET + PUT)
# + ✅ NAYA: Store default country + tax
# + ✅ NAYA v7: Compare At Price settings (GET + PUT)
# + ✅ NAYA v8: /store-compare-price endpoints (frontend match)
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
# ✅ STORE DEFAULT — GET (markup + country + tax)
# ============================================
@router.get("/store-default")
def get_store_default_markup(
    shop_domain: str = Query(..., description="Shopify store domain"),
    db: Session = Depends(get_db),
):
    """
    Store ka saved default markup + country + tax return karo.
    Ye sab naye products par apply hoga.
    """
    store = db.query(ShopifyStore).filter(
        ShopifyStore.shop_domain == shop_domain
    ).first()

    if not store:
        raise HTTPException(
            status_code=404,
            detail=f"Store not found: {shop_domain}",
        )

    # ✅ Country name nikaalo (agar country_id set hai)
    country_name = None
    country_id = getattr(store, "default_country_id", None)
    if country_id:
        try:
            countries = pricing_service.get_all_countries()
            country = next(
                (c for c in countries if c.get("id") == country_id),
                None,
            )
            if country:
                country_name = country.get("name")
        except Exception as e:
            logger.warning(f"⚠️ Could not fetch country name: {e}")

    return {
        "shop_domain": store.shop_domain,
        # Markup
        "markup": float(getattr(store, "default_markup", None) or 2.0),
        "markup_type": getattr(store, "default_markup_type", None) or "fixed",
        "extra_percent": float(
            getattr(store, "default_extra_percent", None) or 0.0
        ),
        # ✅ Country + Tax
        "country_id": country_id,
        "country_name": country_name,
        "tax_rate": float(
            getattr(store, "default_tax_rate", None) or 0.0
        ),
        # ✅ NAYA: Compare At Price
        "compare_at_enabled": bool(
            getattr(store, "default_compare_at_enabled", False)
        ),
        "compare_at_type": (
            getattr(store, "default_compare_at_type", None) or "percent"
        ),
        "compare_at_value": float(
            getattr(store, "default_compare_at_value", None) or 30.0
        ),
        # ✅ NAYA v8: Rule (frontend field)
        "compare_at_rule": (
            getattr(store, "default_compare_at_rule", None) or "none"
        ),
    }


# ============================================
# ✅ STORE DEFAULT — PUT (markup + country + tax)
# ============================================
@router.put("/store-default")
def update_store_default_markup(
    shop_domain: str = Body(..., embed=True),
    markup: float = Body(..., embed=True),
    markup_type: str = Body(..., embed=True),
    extra_percent: float = Body(0.0, embed=True),
    country_id: int = Body(None, embed=True),
    tax_rate: float = Body(0.0, embed=True),
    db: Session = Depends(get_db),
):
    """
    Store ka default markup + country + tax save karo.
    Ye sab har naye add-product me use hoga.
    """
    # Validation
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

    if tax_rate < 0 or tax_rate > 100:
        raise HTTPException(
            status_code=400, detail="tax_rate must be between 0 and 100"
        )

    store = db.query(ShopifyStore).filter(
        ShopifyStore.shop_domain == shop_domain
    ).first()

    if not store:
        raise HTTPException(
            status_code=404,
            detail=f"Store not found: {shop_domain}",
        )

    # Save markup
    store.default_markup = markup
    store.default_markup_type = markup_type
    store.default_extra_percent = extra_percent

    # ✅ Save country + tax
    store.default_country_id = country_id
    store.default_tax_rate = tax_rate

    db.commit()
    db.refresh(store)

    logger.info(
        f"✅ Store defaults saved for {shop_domain}: "
        f"markup={markup} ({markup_type}), extra={extra_percent}%, "
        f"country_id={country_id}, tax_rate={tax_rate}%"
    )

    # Country name nikaalo
    country_name = None
    if country_id:
        try:
            countries = pricing_service.get_all_countries()
            country = next(
                (c for c in countries if c.get("id") == country_id),
                None,
            )
            if country:
                country_name = country.get("name")
        except Exception:
            pass

    return {
        "success": True,
        "message": "Store defaults saved successfully",
        "shop_domain": store.shop_domain,
        # Markup
        "markup": float(store.default_markup or 0.0),
        "markup_type": store.default_markup_type or "fixed",
        "extra_percent": float(store.default_extra_percent or 0.0),
        # Country + Tax
        "country_id": store.default_country_id,
        "country_name": country_name,
        "tax_rate": float(store.default_tax_rate or 0.0),
        # ✅ Compare At Price
        "compare_at_enabled": bool(
            getattr(store, "default_compare_at_enabled", False)
        ),
        "compare_at_type": (
            getattr(store, "default_compare_at_type", None) or "percent"
        ),
        "compare_at_value": float(
            getattr(store, "default_compare_at_value", None) or 30.0
        ),
        "compare_at_rule": (
            getattr(store, "default_compare_at_rule", None) or "none"
        ),
    }


# ============================================
# ✅ NAYA v8: STORE COMPARE PRICE — GET
# Yeh endpoint frontend (`ComparePriceSettings.jsx`) use karta hai
# ============================================
@router.get("/store-compare-price")
def get_store_compare_price(
    shop_domain: str = Query(..., description="Shopify store domain"),
    db: Session = Depends(get_db),
):
    """
    Store ki compare-at price rule return karo.
    Frontend ke liye response shape:
      { rule_type, fixed_amount, percent }
    """
    store = db.query(ShopifyStore).filter(
        ShopifyStore.shop_domain == shop_domain
    ).first()

    if not store:
        raise HTTPException(
            status_code=404,
            detail=f"Store not found: {shop_domain}",
        )

    # ✅ Rule: pehle naya field check karo, phir purane se derive karo
    rule_type = getattr(store, "default_compare_at_rule", None)

    if not rule_type:
        # Fallback — purane fields se derive
        enabled = bool(
            getattr(store, "default_compare_at_enabled", False)
        )
        compare_type = (
            getattr(store, "default_compare_at_type", None) or "percent"
        )

        if not enabled:
            rule_type = "none"
        elif compare_type == "amazon":
            rule_type = "amazon"
        elif compare_type == "fixed":
            rule_type = "fixed"
        else:
            rule_type = "percent"

    compare_value = float(
        getattr(store, "default_compare_at_value", None) or 0.0
    )

    # Frontend response shape
    return {
        "shop_domain": store.shop_domain,
        "rule_type": rule_type,
        "fixed_amount": compare_value if rule_type == "fixed" else 0,
        "percent": compare_value if rule_type == "percent" else 0,
        # Backward compat
        "enabled": rule_type not in ("none",),
        "compare_at_type": (
            getattr(store, "default_compare_at_type", None) or "percent"
        ),
        "compare_at_value": compare_value,
    }


# ============================================
# ✅ NAYA v8: STORE COMPARE PRICE — PUT
# Frontend sends: rule_type, fixed_amount, percent
# ============================================
@router.put("/store-compare-price")
def update_store_compare_price(
    shop_domain: str = Body(..., embed=True),
    rule_type: str = Body("none", embed=True),
    fixed_amount: float = Body(0.0, embed=True),
    percent: float = Body(0.0, embed=True),
    db: Session = Depends(get_db),
):
    """
    Store ki compare-at price rule save karo.
    Frontend sends: rule_type, fixed_amount, percent

    rule_type options:
      "none"     → do not set compare price
      "amazon"   → compare = amazon price
      "fixed"    → compare = final_price + fixed_amount
      "percent"  → compare = final_price × (1 + percent/100)
    """
    # Validation
    if rule_type not in ("none", "amazon", "fixed", "percent"):
        raise HTTPException(
            status_code=400,
            detail="rule_type must be one of: none, amazon, fixed, percent",
        )

    if rule_type == "fixed" and fixed_amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="fixed_amount must be > 0 when rule_type='fixed'",
        )

    if rule_type == "percent" and (percent <= 0 or percent > 500):
        raise HTTPException(
            status_code=400,
            detail="percent must be between 0 and 500 when rule_type='percent'",
        )

    store = db.query(ShopifyStore).filter(
        ShopifyStore.shop_domain == shop_domain
    ).first()

    if not store:
        raise HTTPException(
            status_code=404,
            detail=f"Store not found: {shop_domain}",
        )

    # ✅ Save rule
    store.default_compare_at_rule = rule_type
    store.default_compare_at_enabled = rule_type != "none"

    if rule_type == "fixed":
        store.default_compare_at_type = "fixed"
        store.default_compare_at_value = fixed_amount
    elif rule_type == "percent":
        store.default_compare_at_type = "percent"
        store.default_compare_at_value = percent
    elif rule_type == "amazon":
        store.default_compare_at_type = "amazon"
        store.default_compare_at_value = 0.0
    else:  # none
        store.default_compare_at_type = "none"
        store.default_compare_at_value = 0.0

    db.commit()
    db.refresh(store)

    logger.info(
        f"✅ Compare price rule saved for {shop_domain}: "
        f"rule_type={rule_type}, fixed={fixed_amount}, percent={percent}"
    )

    return {
        "success": True,
        "message": "Compare price rule saved successfully",
        "shop_domain": store.shop_domain,
        "rule_type": store.default_compare_at_rule or "none",
        "fixed_amount": fixed_amount if rule_type == "fixed" else 0,
        "percent": percent if rule_type == "percent" else 0,
    }


# ============================================
# ✅ v7 (backward compat): COMPARE AT PRICE — GET
# ============================================
@router.get("/compare-at-settings")
def get_compare_at_settings(
    shop_domain: str = Query(..., description="Shopify store domain"),
    db: Session = Depends(get_db),
):
    """Store ki compare-at price settings return karo (old endpoint)."""
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
        "enabled": bool(
            getattr(store, "default_compare_at_enabled", False)
        ),
        "type": (
            getattr(store, "default_compare_at_type", None) or "percent"
        ),
        "value": float(
            getattr(store, "default_compare_at_value", None) or 30.0
        ),
    }


# ============================================
# ✅ v7 (backward compat): COMPARE AT PRICE — PUT
# ============================================
@router.put("/compare-at-settings")
def update_compare_at_settings(
    shop_domain: str = Body(..., embed=True),
    enabled: bool = Body(..., embed=True),
    compare_at_type: str = Body("percent", embed=True),
    compare_at_value: float = Body(30.0, embed=True),
    db: Session = Depends(get_db),
):
    """Store ki compare-at price settings save karo (old endpoint)."""
    if compare_at_type not in ("percent", "fixed", "amazon", "none"):
        raise HTTPException(
            status_code=400,
            detail="compare_at_type must be one of: percent, fixed, amazon, none",
        )

    if compare_at_value < 0:
        raise HTTPException(
            status_code=400,
            detail="compare_at_value must be >= 0",
        )

    store = db.query(ShopifyStore).filter(
        ShopifyStore.shop_domain == shop_domain
    ).first()

    if not store:
        raise HTTPException(
            status_code=404,
            detail=f"Store not found: {shop_domain}",
        )

    store.default_compare_at_enabled = enabled
    store.default_compare_at_type = compare_at_type
    store.default_compare_at_value = compare_at_value

    db.commit()
    db.refresh(store)

    return {
        "success": True,
        "message": "Compare-at settings saved",
        "shop_domain": store.shop_domain,
        "enabled": bool(store.default_compare_at_enabled),
        "type": store.default_compare_at_type or "percent",
        "value": float(store.default_compare_at_value or 30.0),
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
            extra_percent=getattr(data, "extra_percent", 0.0),
        )

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
            extra_percent=getattr(data, "extra_percent", 0.0),
        )

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