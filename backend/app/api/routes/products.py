# ============================================
# app/api/routes/products.py
# Product CRUD + Variation grouping + Slug
# + Markup Settings endpoints
# + Out of Stock tracking (NEW)
# + Real-time availability check (Storefront API)
# ============================================

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_admin
from app.database import get_db
from app.models import Admin, Product
from app.schemas import (
    MarkupUpdate,
    ProductCreate,
    ProductFetchResponse,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
    VariantGroup,
    VariantGroupListResponse,
)
from app.services.brightdata import (
    BrightDataError,
    calculate_final_price,
    fetch_product_from_brightdata,
)

# ✅ NAYA — Storefront availability check import
from app.services.shopify import check_product_availability


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Products"])


# ============================================
# USER ROUTES (PUBLIC)
# ============================================

@router.get("/products", response_model=VariantGroupListResponse)
def get_all_products(db: Session = Depends(get_db)):
    """Saare products — variations ko GROUP karke."""
    all_products = db.query(Product).order_by(Product.created_at.desc()).all()

    groups = {}

    for p in all_products:
        group_key = p.parent_asin if p.parent_asin else p.asin

        if group_key not in groups:
            groups[group_key] = {"parent": None, "variants": []}

        if p.parent_asin is None:
            groups[group_key]["parent"] = p
        else:
            if groups[group_key]["parent"] is None:
                groups[group_key]["parent"] = p
                groups[group_key]["variants"].append(p)
            else:
                groups[group_key]["variants"].append(p)

    variant_groups = []

    for group_key, group_data in groups.items():
        parent = group_data["parent"]
        variants = group_data["variants"]

        if parent is None:
            continue

        all_variants_map = {parent.id: parent}
        for v in variants:
            all_variants_map[v.id] = v

        all_variants = list(all_variants_map.values())

        variant_groups.append(
            VariantGroup(
                parent_product=ProductResponse.model_validate(parent),
                variants=[
                    ProductResponse.model_validate(v) for v in all_variants
                ],
                total_variants=len(all_variants),
            )
        )

    return VariantGroupListResponse(
        total=len(variant_groups),
        groups=variant_groups,
    )


# ============================================
# ✅ NAYA — AVAILABILITY CHECK (Storefront API)
# ⚠️ IMPORTANT: Ye {product_id} route se PEHLE hona chahiye
# ============================================
@router.get("/products/{product_id}/availability")
async def get_product_availability(
    product_id: int,
    db: Session = Depends(get_db),
):
    """
    Product ki real-time availability check karta hai.
    Pehle Shopify Storefront API try karta hai,
    fail hone par Supabase (local DB) fallback.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Agar Shopify ID nahi hai → Supabase fallback
    if not product.shopify_product_id:
        return {
            "available": product.is_available,
            "quantity": product.stock_quantity or 0,
            "source": "supabase",
        }

    # Storefront API se check
    availability = await check_product_availability(
        shopify_product_id=product.shopify_product_id,
    )

    # Agar API fail ho jaye → Supabase fallback
    if availability.get("source") == "none":
        logger.warning(
            f"Storefront API failed for product {product_id}, "
            f"using Supabase fallback"
        )
        return {
            "available": product.is_available,
            "quantity": product.stock_quantity or 0,
            "source": "supabase",
            "fallback_reason": availability.get("error"),
        }

    return availability


# ⚠️ SLUG ENDPOINT — numeric se PEHLE
@router.get("/products/slug/{slug}", response_model=ProductResponse)
def get_product_by_slug(slug: str, db: Session = Depends(get_db)):
    import re

    # METHOD 1: Full phrase
    search_phrase = slug.replace('-', ' ').lower()
    product = (
        db.query(Product)
        .filter(Product.title.ilike(f'%{search_phrase}%'))
        .order_by(Product.id.desc())
        .first()
    )
    if product:
        return product

    # METHOD 2: Word-by-word
    parts = [p.strip() for p in slug.lower().split('-') if p.strip()]
    parts = [re.escape(p) for p in parts if len(p) >= 2]

    if parts:
        pattern = '%' + '%'.join(parts) + '%'
        product = (
            db.query(Product)
            .filter(Product.title.ilike(pattern))
            .order_by(Product.id.desc())
            .first()
        )
        if product:
            return product

    # METHOD 3: First 6 words
    if len(parts) > 6:
        short_pattern = '%' + '%'.join(parts[:6]) + '%'
        product = (
            db.query(Product)
            .filter(Product.title.ilike(short_pattern))
            .order_by(Product.id.desc())
            .first()
        )
        if product:
            return product

    # METHOD 4: First 3 words
    if len(parts) > 3:
        loose_pattern = '%' + '%'.join(parts[:3]) + '%'
        product = (
            db.query(Product)
            .filter(Product.title.ilike(loose_pattern))
            .order_by(Product.id.desc())
            .first()
        )
        if product:
            return product

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Product not found",
    )


@router.get("/products/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    return product


@router.get(
    "/products/{product_id}/variants",
    response_model=list[ProductResponse],
)
def get_product_variants(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    group_key = product.parent_asin if product.parent_asin else product.asin

    variants = (
        db.query(Product)
        .filter(
            or_(
                Product.asin == group_key,
                Product.parent_asin == group_key,
            )
        )
        .all()
    )

    return variants


# ============================================
# ADMIN ROUTES (PROTECTED)
# ============================================

@router.get("/admin/products", response_model=ProductListResponse)
def get_all_products_admin(
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    products = db.query(Product).order_by(Product.created_at.desc()).all()
    return ProductListResponse(
        total=len(products),
        products=products,
    )


@router.post(
    "/admin/fetch",
    response_model=ProductFetchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def admin_fetch_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    """Admin Amazon URL submit karta hai + apna markup bhej sakta hai."""
    amazon_url = payload.amazon_url

    try:
        data = await fetch_product_from_brightdata(amazon_url)
    except BrightDataError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bright Data fetch fail: {str(e)}",
        )

    asin = data["asin"]

    existing = db.query(Product).filter(Product.asin == asin).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Product already exists (ASIN: {asin})",
        )

    # Admin ka markup use karo
    user_markup = payload.markup if payload.markup is not None else 2.0
    user_markup_type = payload.markup_type or "fixed"

    final_price = calculate_final_price(
        amazon_price=data["amazon_price"],
        markup=user_markup,
        markup_type=user_markup_type,
    )

    new_product = Product(
        asin=asin,
        parent_asin=data["parent_asin"],
        is_variation=data["is_variation"],
        title=data["title"],
        brand=data["brand"],
        description=data["description"],
        image_url=data["image_url"],
        images=data.get("images", []),
        specifications=data.get("specifications", {}),
        rating=data.get("rating"),
        reviews_count=data.get("reviews_count"),
        amazon_price=data["amazon_price"],
        price=final_price,
        markup=user_markup,
        markup_type=user_markup_type,
        is_manual_override=False,
        # NAYA — Out of Stock tracking
        availability=data.get("availability", "In Stock"),
        is_available=data.get("is_available", True),
        stock_quantity=data.get("stock_quantity", 0),
        last_synced_at=datetime.now(timezone.utc),
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    return ProductFetchResponse(
        success=True,
        message=f"Product added successfully (ASIN: {asin})",
        product=new_product,
    )


@router.put("/admin/products/{product_id}", response_model=ProductResponse)
def admin_update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    update_data = payload.model_dump(exclude_unset=True)
    price_changed = "price" in update_data

    for field, value in update_data.items():
        setattr(product, field, value)

    if price_changed:
        product.is_manual_override = True

    db.commit()
    db.refresh(product)

    return product


@router.delete(
    "/admin/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def admin_delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    db.delete(product)
    db.commit()

    return None


# ============================================
# 🆕 MARKUP SETTINGS ROUTES (Settings Page ke liye)
# ============================================

@router.get("/markup/products", response_model=list[ProductResponse])
def list_products_for_markup(
    db: Session = Depends(get_db),
):
    """
    Markup Settings page ke liye saare products.
    Public rakha hai taake Shopify iframe se easily access ho.
    """
    products = db.query(Product).order_by(Product.created_at.desc()).all()
    return products


@router.patch("/markup/{product_id}", response_model=ProductResponse)
def update_product_markup(
    product_id: int,
    payload: MarkupUpdate,
    db: Session = Depends(get_db),
):
    """
    Ek product ka markup update karo.
    Price automatically recalculate hoti hai.
    """
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # Naya price calculate karo
    new_price = calculate_final_price(
        amazon_price=product.amazon_price,
        markup=payload.markup,
        markup_type=payload.markup_type,
    )

    product.markup = payload.markup
    product.markup_type = payload.markup_type
    product.price = new_price
    product.is_manual_override = True

    db.commit()
    db.refresh(product)

    return product


@router.post("/markup/bulk-update")
def bulk_update_markup(
    payload: MarkupUpdate,
    db: Session = Depends(get_db),
):
    """Saare products ka markup ek saath update karo."""
    products = db.query(Product).all()
    updated = 0

    for product in products:
        product.markup = payload.markup
        product.markup_type = payload.markup_type
        product.price = calculate_final_price(
            amazon_price=product.amazon_price,
            markup=payload.markup,
            markup_type=payload.markup_type,
        )
        product.is_manual_override = True
        updated += 1

    db.commit()

    return {"success": True, "updated": updated}