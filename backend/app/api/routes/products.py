# ============================================
# app/api/routes/products.py
# Product CRUD + Variation grouping + Slug
# ============================================

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_admin
from app.database import get_db
from app.models import Admin, Product
from app.schemas import (
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

router = APIRouter(prefix="/api", tags=["Products"])


# ============================================
# USER ROUTES (PUBLIC)
# ============================================

@router.get("/products", response_model=VariantGroupListResponse)
def get_all_products(db: Session = Depends(get_db)):
    """
    Saare products — variations ko GROUP karke.
    Ek group = ek card on home page.
    """
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


# ⚠️ SLUG ENDPOINT — numeric se PEHLE
@router.get("/products/slug/{slug}", response_model=ProductResponse)
def get_product_by_slug(slug: str, db: Session = Depends(get_db)):
    """
    Product ko slug se fetch karo.
    Multiple fallback methods — exact match → word match → partial match.
    """
    import re

    # ========================================
    # METHOD 1: Full phrase match
    # "eky-16-inch-laptop" -> "%eky 16 inch laptop%"
    # ========================================
    search_phrase = slug.replace('-', ' ').lower()
    product = (
        db.query(Product)
        .filter(Product.title.ilike(f'%{search_phrase}%'))
        .order_by(Product.id.desc())
        .first()
    )
    if product:
        return product

    # ========================================
    # METHOD 2: Word-by-word match
    # "eky-16-inch-laptop" -> "%eky%16%inch%laptop%"
    # ========================================
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

    # ========================================
    # METHOD 3: First 6 words only (long slugs ke liye)
    # ========================================
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

    # ========================================
    # METHOD 4: First 3 words only (loose match)
    # ========================================
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
    """Ek product ki detail (numeric ID se)."""
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
    """Ek product ke saare variants (poore group ke)."""
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
    """Admin dashboard ke liye — flat list."""
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
    """Admin Amazon URL submit karta hai."""
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

    markup = data.get("markup", 2.0) or 2.0
    final_price = calculate_final_price(
        amazon_price=data["amazon_price"],
        markup=markup,
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
        amazon_price=data["amazon_price"],
        price=final_price,
        markup=markup,
        is_manual_override=False,
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
    """Product update karo."""
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
    """Product delete karo."""
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    db.delete(product)
    db.commit()

    return None