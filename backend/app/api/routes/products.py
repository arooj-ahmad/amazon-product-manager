# ============================================
# app/api/routes/products.py
# + ✅ FIXED: shop= → shop_domain=
# + ✅ FIXED: Store selection per product
# + ✅ NAYA: refresh_token pass karo auto-refresh ke liye
# + ✅ NAYA: Refresh ke baad DB mein naya token save karo
# + ✅ NAYA: Proactive token refresh (_ensure_valid_store_token)
# ============================================

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_admin
from app.database import get_db
from app.models import Admin, Product, ShopifyStore
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
from app.services.shopify import (
    check_product_availability,
    shopify_graphql,
    sync_update_shopify_price,
    refresh_shopify_token,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Products"])


# ============================================
# HELPER: Product ke liye sahi store dhoondho
# ============================================
def _get_store_for_product(
    db: Session,
    product: Product,
    fallback_store_id: int = None,
) -> ShopifyStore:
    """Product ke shopify_store_id se store dhoondho."""
    store = None
    if product.shopify_store_id:
        store = (
            db.query(ShopifyStore)
            .filter(ShopifyStore.id == product.shopify_store_id)
            .first()
        )
    if not store and fallback_store_id:
        store = (
            db.query(ShopifyStore)
            .filter(ShopifyStore.id == fallback_store_id)
            .first()
        )
    if not store:
        store = db.query(ShopifyStore).first()
    return store


# ============================================
# ✅ NAYA: Proactive Token Refresh
# ============================================
async def _ensure_valid_store_token(
    db: Session,
    store: ShopifyStore,
) -> bool:
    """
    Token ko proactively refresh karo agar expire hone wala hai (5 min ke andar).
    Returns: True agar token valid hai, False agar nahi.
    """
    if not store or not store.access_token:
        logger.warning("No store or access_token")
        return False

    # Agar expires_at NULL hai -> permanent token (valid)
    if not store.expires_at:
        logger.debug(f"Permanent token (no expiry) for {store.shop_domain}")
        return True

    now = datetime.now(timezone.utc)
    buffer = timedelta(minutes=5)

    # Abhi bhi valid hai
    if store.expires_at > now + buffer:
        logger.debug(
            f"Token valid for {store.shop_domain} "
            f"(expires_at={store.expires_at}, now={now})"
        )
        return True

    # Token expire hone wala hai (ya ho gaya) - refresh karo
    logger.info(
        f"🔄 Token expiring/expired for {store.shop_domain} "
        f"(expires_at={store.expires_at}), refreshing proactively..."
    )

    if not store.refresh_token:
        logger.error(f"❌ No refresh_token for {store.shop_domain}")
        return False

    new_data = await refresh_shopify_token(
        store.shop_domain, store.refresh_token
    )
    if not new_data or not new_data.get("access_token"):
        logger.error(f"❌ Proactive refresh failed for {store.shop_domain}")
        return False

    # Naya token save karo
    store.access_token = new_data["access_token"]
    if new_data.get("refresh_token"):
        store.refresh_token = new_data["refresh_token"]

    expires_in = new_data.get("expires_in")
    if expires_in:
        store.expires_at = now + timedelta(seconds=int(expires_in))

    refresh_expires_in = new_data.get("refresh_token_expires_in")
    if refresh_expires_in:
        store.refresh_token_expires_at = now + timedelta(
            seconds=int(refresh_expires_in)
        )

    db.commit()
    db.refresh(store)

    logger.info(
        f"✅ Proactive refresh success for {store.shop_domain} "
        f"(new expires_at={store.expires_at})"
    )
    return True


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
# AVAILABILITY CHECK
# ============================================
@router.get("/products/{product_id}/availability")
async def get_product_availability(
    product_id: int,
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if not product.shopify_product_id:
        return {
            "available": product.is_available,
            "quantity": product.stock_quantity or 0,
            "source": "supabase",
        }

    availability = await check_product_availability(
        shopify_product_id=product.shopify_product_id,
    )

    if availability.get("source") == "none":
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

    search_phrase = slug.replace('-', ' ').lower()
    product = (
        db.query(Product)
        .filter(Product.title.ilike(f'%{search_phrase}%'))
        .order_by(Product.id.desc())
        .first()
    )
    if product:
        return product

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
# ADMIN ROUTES
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

    user_markup = payload.markup if payload.markup is not None else 2.0
    user_markup_type = payload.markup_type or "fixed"

    final_price = calculate_final_price(
        amazon_price=data["amazon_price"],
        markup=user_markup,
        markup_type=user_markup_type,
    )

    default_store = db.query(ShopifyStore).first()

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
        availability=data.get("availability", "In Stock"),
        is_available=data.get("is_available", True),
        stock_quantity=data.get("stock_quantity", 0),
        last_synced_at=datetime.now(timezone.utc),
        variant_attributes=data.get("variant_attributes", []),
        shopify_store_id=default_store.id if default_store else None,
        shopify_status="active",
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
# MARKUP SETTINGS ROUTES
# ============================================

@router.get("/markup/products", response_model=list[ProductResponse])
def list_products_for_markup(
    store_id: int = None,
    db: Session = Depends(get_db),
):
    query = db.query(Product).filter(
        Product.shopify_status == "active",
    )

    if store_id:
        query = query.filter(Product.shopify_store_id == store_id)

    products = query.order_by(Product.created_at.desc()).all()
    return products


@router.patch("/markup/{product_id}", response_model=ProductResponse)
async def update_product_markup(
    product_id: int,
    payload: MarkupUpdate,
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

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

    # ✅ Product ke store se
    store = _get_store_for_product(db, product)

    if store and store.access_token and product.shopify_product_id:
        # ✅ NAYA: Token ko pehle ensure karo (proactive refresh)
        token_ok = await _ensure_valid_store_token(db, store)

        if not token_ok:
            logger.warning(
                f"⚠️ Token invalid for {store.shop_domain}, "
                f"price update skipped. Reinstall app: "
                f"https://amazon-product-manager-production.up.railway.app"
                f"/api/shopify/install?shop={store.shop_domain}"
            )
            return product

        logger.info(
            f"🔄 Syncing price: shop={store.shop_domain}, "
            f"product={product.shopify_product_id}, price=${new_price}"
        )
        try:
            ok = await sync_update_shopify_price(
                shop_domain=store.shop_domain,
                access_token=store.access_token,
                shopify_product_id=product.shopify_product_id,
                new_price=new_price,
                refresh_token=store.refresh_token,
            )
            if ok:
                logger.info(
                    f"✅ Shopify price updated: {product.asin} → ${new_price}"
                )
            else:
                logger.warning(
                    f"⚠️ Shopify price update FAILED: {product.asin}"
                )
        except Exception as e:
            logger.error(f"❌ Shopify update exception: {e}")

    return product


@router.post("/markup/bulk-update")
async def bulk_update_markup(
    payload: MarkupUpdate,
    store_id: int = None,
    db: Session = Depends(get_db),
):
    query = db.query(Product).filter(
        Product.shopify_status == "active",
    )

    if store_id:
        query = query.filter(Product.shopify_store_id == store_id)

    products = query.all()
    updated = 0
    shopify_updated = 0
    shopify_failed = 0
    token_refreshed_stores = set()

    for product in products:
        new_price = calculate_final_price(
            amazon_price=product.amazon_price,
            markup=payload.markup,
            markup_type=payload.markup_type,
        )
        product.markup = payload.markup
        product.markup_type = payload.markup_type
        product.price = new_price
        product.is_manual_override = True
        updated += 1

        # ✅ Per-product store
        product_store = _get_store_for_product(
            db, product, fallback_store_id=store_id
        )

        if (
            product_store
            and product_store.access_token
            and product.shopify_product_id
        ):
            # ✅ NAYA: Ek store ka token ek baar hi refresh karo
            if product_store.shop_domain not in token_refreshed_stores:
                token_ok = await _ensure_valid_store_token(db, product_store)
                if not token_ok:
                    logger.warning(
                        f"⚠️ Token invalid for {product_store.shop_domain}, "
                        f"skipping products of this store"
                    )
                    shopify_failed += 1
                    continue
                token_refreshed_stores.add(product_store.shop_domain)

            try:
                ok = await sync_update_shopify_price(
                    shop_domain=product_store.shop_domain,
                    access_token=product_store.access_token,
                    shopify_product_id=product.shopify_product_id,
                    new_price=new_price,
                    refresh_token=product_store.refresh_token,
                )
                if ok:
                    shopify_updated += 1
                else:
                    shopify_failed += 1
                    logger.warning(
                        f"⚠️ Shopify update FAILED: {product.asin}"
                    )
            except Exception as e:
                shopify_failed += 1
                logger.error(
                    f"❌ Shopify update exception for {product.asin}: {e}"
                )

    db.commit()

    return {
        "success": True,
        "updated": updated,
        "shopify_updated": shopify_updated,
        "shopify_failed": shopify_failed,
    }


# ============================================
# SHOPIFY SE PRODUCTS SYNC KARO
# ============================================

@router.post("/markup/sync-from-shopify")
async def sync_products_from_shopify(
    store_id: int = None,
    db: Session = Depends(get_db),
):
    if store_id:
        store = db.query(ShopifyStore).filter(ShopifyStore.id == store_id).first()
    else:
        store = db.query(ShopifyStore).first()

    if not store or not store.access_token:
        raise HTTPException(
            status_code=400,
            detail="Shopify store not configured",
        )

    # ✅ NAYA: Sync se pehle token ensure karo
    token_ok = await _ensure_valid_store_token(db, store)
    if not token_ok:
        raise HTTPException(
            status_code=401,
            detail=(
                f"Token invalid for {store.shop_domain}. "
                f"Please reinstall the app: "
                f"https://amazon-product-manager-production.up.railway.app"
                f"/api/shopify/install?shop={store.shop_domain}"
            ),
        )

    shop = store.shop_domain
    access_token = store.access_token

    query = """
    query getProducts($cursor: String) {
      products(first: 50, after: $cursor, query: "status:active") {
        pageInfo {
          hasNextPage
          endCursor
        }
        edges {
          node {
            id
            title
            handle
            status
            variants(first: 1) {
              edges {
                node {
                  sku
                  price
                  inventoryQuantity
                }
              }
            }
          }
        }
      }
    }
    """

    all_products = []
    cursor = None
    has_next = True

    while has_next:
        result = await shopify_graphql(
            shop, access_token, query, {"cursor": cursor}
        )

        products_data = result.get("data", {}).get("products", {})
        edges = products_data.get("edges", [])
        page_info = products_data.get("pageInfo", {})

        for edge in edges:
            node = edge["node"]
            variants = node.get("variants", {}).get("edges", [])

            sku = None
            price = None
            inventory = 0

            if variants:
                variant = variants[0]["node"]
                sku = variant.get("sku")
                price = variant.get("price")
                inventory = variant.get("inventoryQuantity", 0)

            all_products.append({
                "shopify_id": node["id"],
                "title": node["title"],
                "handle": node.get("handle"),
                "status": node.get("status", "").lower(),
                "sku": sku,
                "price": price,
                "inventory": inventory,
            })

        has_next = page_info.get("hasNextPage", False)
        cursor = page_info.get("endCursor")

    logger.info(f"Shopify se {len(all_products)} active products mile")

    existing_products = db.query(Product).filter(
        Product.shopify_store_id == store.id
    ).all()

    for p in existing_products:
        p.shopify_status = "draft"

    db.commit()

    added = 0
    updated = 0
    skipped = 0

    for sp in all_products:
        sku = sp.get("sku")
        shopify_id = sp.get("shopify_id")
        title = sp.get("title")
        shopify_price = float(sp["price"]) if sp.get("price") else None

        if not sku:
            numeric_id = shopify_id.replace("gid://shopify/Product/", "")
            sku = f"SHOPIFY_{numeric_id}"
        else:
            sku = str(sku).strip()[:255]

        if title:
            title = title[:500]

        product = db.query(Product).filter(Product.asin == sku).first()

        if product:
            product.shopify_product_id = shopify_id
            product.shopify_handle = sp.get("handle")
            product.shopify_status = sp.get("status", "active")
            product.shopify_store_id = store.id
            if not product.title:
                product.title = title
            if shopify_price:
                product.amazon_price = shopify_price
                product.price = calculate_final_price(
                    amazon_price=shopify_price,
                    markup=product.markup or 2.0,
                    markup_type=product.markup_type or "fixed",
                )
            updated += 1
        else:
            final_price = calculate_final_price(
                amazon_price=shopify_price,
                markup=2.0,
                markup_type="fixed",
            )
            new_product = Product(
                asin=sku,
                title=title,
                shopify_product_id=shopify_id,
                shopify_handle=sp.get("handle"),
                shopify_status=sp.get("status", "active"),
                shopify_store_id=store.id,
                amazon_price=shopify_price,
                price=final_price,
                is_available=True,
                stock_quantity=sp.get("inventory", 0),
            )
            db.add(new_product)
            added += 1

    db.commit()

    return {
        "success": True,
        "total_shopify_products": len(all_products),
        "added": added,
        "updated": updated,
        "skipped": skipped,
    }