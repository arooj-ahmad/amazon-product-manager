# ============================================
# app/api/routes/products.py
# + ✅ FIXED: Frontend se aayi value direct save hogi
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
    delete_shopify_product,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Products"])


def _get_store_defaults(store: ShopifyStore) -> tuple:
    if not store:
        return None, None, 0.0, 0.0
    markup = getattr(store, "default_markup", None)
    markup_type = getattr(store, "default_markup_type", None)
    extra_percent = float(getattr(store, "default_extra_percent", None) or 0.0)
    tax_rate = float(getattr(store, "default_tax_rate", None) or 0.0)
    if markup is not None: markup = float(markup)
    if markup_type is not None and markup_type not in ("fixed", "percent", "both"): markup_type = "fixed"
    return markup, markup_type, extra_percent, tax_rate


def _get_store_for_product(db: Session, product: Product, fallback_store_id: int = None) -> ShopifyStore:
    store = None
    if product.shopify_store_id:
        store = db.query(ShopifyStore).filter(ShopifyStore.id == product.shopify_store_id).first()
    if not store and fallback_store_id:
        store = db.query(ShopifyStore).filter(ShopifyStore.id == fallback_store_id).first()
    if not store:
        store = db.query(ShopifyStore).first()
    return store


async def _ensure_valid_store_token(db: Session, store: ShopifyStore) -> bool:
    if not store or not store.access_token:
        logger.warning("No store or access_token")
        return False
    if not store.expires_at: return True
    now = datetime.now(timezone.utc)
    buffer = timedelta(minutes=5)
    if store.expires_at > now + buffer: return True
    logger.info(f"🔄 Token expiring for {store.shop_domain}, refreshing...")
    if not store.refresh_token:
        logger.error(f"❌ No refresh_token for {store.shop_domain}")
        return False
    new_data = await refresh_shopify_token(store.shop_domain, store.refresh_token)
    if not new_data or not new_data.get("access_token"):
        logger.error(f"❌ Refresh failed for {store.shop_domain}")
        return False
    store.access_token = new_data["access_token"]
    if new_data.get("refresh_token"): store.refresh_token = new_data["refresh_token"]
    expires_in = new_data.get("expires_in")
    if expires_in: store.expires_at = now + timedelta(seconds=int(expires_in))
    refresh_expires_in = new_data.get("refresh_token_expires_in")
    if refresh_expires_in: store.refresh_token_expires_at = now + timedelta(seconds=int(refresh_expires_in))
    db.commit()
    db.refresh(store)
    logger.info(f"✅ Refreshed for {store.shop_domain}")
    return True


@router.get("/products", response_model=VariantGroupListResponse)
def get_all_products(db: Session = Depends(get_db)):
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
        if parent is None: continue
        all_variants_map = {parent.id: parent}
        for v in variants: all_variants_map[v.id] = v
        all_variants = list(all_variants_map.values())
        variant_groups.append(
            VariantGroup(
                parent_product=ProductResponse.model_validate(parent),
                variants=[ProductResponse.model_validate(v) for v in all_variants],
                total_variants=len(all_variants),
            )
        )
    return VariantGroupListResponse(total=len(variant_groups), groups=variant_groups)


@router.get("/products/{product_id}/availability")
async def get_product_availability(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product: raise HTTPException(status_code=404, detail="Product not found")
    if not product.shopify_product_id:
        return {"available": product.is_available, "quantity": product.stock_quantity or 0, "source": "supabase"}
    availability = await check_product_availability(shopify_product_id=product.shopify_product_id)
    if availability.get("source") == "none":
        return {"available": product.is_available, "quantity": product.stock_quantity or 0, "source": "supabase", "fallback_reason": availability.get("error")}
    return availability


@router.get("/products/slug/{slug}", response_model=ProductResponse)
def get_product_by_slug(slug: str, db: Session = Depends(get_db)):
    import re
    search_phrase = slug.replace('-', ' ').lower()
    product = db.query(Product).filter(Product.title.ilike(f'%{search_phrase}%')).order_by(Product.id.desc()).first()
    if product: return product
    parts = [p.strip() for p in slug.lower().split('-') if p.strip()]
    parts = [re.escape(p) for p in parts if len(p) >= 2]
    if parts:
        pattern = '%' + '%'.join(parts) + '%'
        product = db.query(Product).filter(Product.title.ilike(pattern)).order_by(Product.id.desc()).first()
        if product: return product
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")


@router.get("/products/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product: raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/products/{product_id}/variants", response_model=list[ProductResponse])
def get_product_variants(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product: raise HTTPException(status_code=404, detail="Product not found")
    group_key = product.parent_asin if product.parent_asin else product.asin
    variants = db.query(Product).filter(or_(Product.asin == group_key, Product.parent_asin == group_key)).all()
    return variants


@router.get("/admin/products", response_model=ProductListResponse)
def get_all_products_admin(db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)):
    products = db.query(Product).order_by(Product.created_at.desc()).all()
    return ProductListResponse(total=len(products), products=products)


@router.post("/admin/fetch", response_model=ProductFetchResponse, status_code=201)
async def admin_fetch_product(payload: ProductCreate, db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)):
    amazon_url = payload.amazon_url
    try:
        data = await fetch_product_from_brightdata(amazon_url)
    except BrightDataError as e:
        raise HTTPException(status_code=400, detail=f"Bright Data fetch fail: {str(e)}")
    asin = data["asin"]
    existing = db.query(Product).filter(Product.asin == asin).first()
    if existing: raise HTTPException(status_code=409, detail=f"Product already exists (ASIN: {asin})")

    default_store = db.query(ShopifyStore).first()
    store_markup, store_markup_type, store_extra_pct, store_tax_rate = _get_store_defaults(default_store)

    if payload.markup is not None:
        user_markup, user_markup_type = payload.markup, payload.markup_type or "fixed"
        user_extra_percent = getattr(payload, "extra_percent", 0.0) or 0.0
    elif store_markup is not None:
        user_markup, user_markup_type = store_markup, store_markup_type or "fixed"
        user_extra_percent = store_extra_pct
    else:
        raise HTTPException(status_code=400, detail="Markup required")

    # ✅ FIX: Hamesha Settings wala Tax uthayen
    user_tax_rate = store_tax_rate if store_tax_rate is not None else 0.0

    final_price = calculate_final_price(
        amazon_price=data["amazon_price"], 
        markup=user_markup, 
        markup_type=user_markup_type, 
        extra_percent=user_extra_percent, 
        tax_rate=user_tax_rate
    )

    new_product = Product(
        asin=asin, parent_asin=data["parent_asin"], is_variation=data["is_variation"],
        title=data["title"], brand=data["brand"], description=data["description"],
        image_url=data["image_url"], images=data.get("images", []), specifications=data.get("specifications", {}),
        rating=data.get("rating"), reviews_count=data.get("reviews_count"), amazon_price=data["amazon_price"],
        price=final_price, markup=user_markup, markup_type=user_markup_type,
        extra_percent=user_extra_percent, tax_rate=user_tax_rate, is_manual_override=False,
        availability=data.get("availability", "In Stock"), is_available=data.get("is_available", True),
        stock_quantity=data.get("stock_quantity", 0), last_synced_at=datetime.now(timezone.utc),
        variant_attributes=data.get("variant_attributes", []), categories=data.get("categories", []),
        tags=data.get("tags", []), shopify_store_id=default_store.id if default_store else None,
        shopify_status="active",
    )
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    return ProductFetchResponse(success=True, message=f"Product added (ASIN: {asin})", product=new_product)


@router.put("/admin/products/{product_id}", response_model=ProductResponse)
def admin_update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product: raise HTTPException(status_code=404, detail="Product not found")
    update_data = payload.model_dump(exclude_unset=True)
    price_changed = "price" in update_data
    for field, value in update_data.items(): setattr(product, field, value)
    if price_changed: product.is_manual_override = True
    db.commit()
    db.refresh(product)
    return product


@router.delete("/admin/products/{product_id}", status_code=204)
async def admin_delete_product(product_id: int, db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product: raise HTTPException(status_code=404, detail="Product not found")
    asin = product.asin
    shopify_id = product.shopify_product_id
    if shopify_id:
        store = _get_store_for_product(db, product)
        if store and store.access_token:
            try:
                token_ok = await _ensure_valid_store_token(db, store)
                if token_ok:
                    success = await delete_shopify_product(shop_domain=store.shop_domain, access_token=store.access_token, shopify_product_id=shopify_id, refresh_token=store.refresh_token)
            except Exception as e: logger.error(f"❌ Shopify delete exception: {e}")
    db.delete(product)
    db.commit()
    return None


@router.get("/markup/products", response_model=list[ProductResponse])
def list_products_for_markup(store_id: int = None, db: Session = Depends(get_db)):
    query = db.query(Product).filter(Product.shopify_status == "active")
    if store_id: query = query.filter(Product.shopify_store_id == store_id)
    return query.order_by(Product.created_at.desc()).all()


# ============================================
# ✅ FIXED: SINGLE PRODUCT UPDATE
# ============================================
@router.patch("/markup/{product_id}", response_model=ProductResponse)
async def update_product_markup(product_id: int, payload: MarkupUpdate, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product: raise HTTPException(status_code=404, detail="Product not found")

    store = _get_store_for_product(db, product)
    _, _, _, store_tax = _get_store_defaults(store)

    extra_pct = payload.extra_percent if payload.extra_percent is not None else 0.0
    tax_rate = payload.tax_rate if payload.tax_rate is not None else store_tax

    new_price = calculate_final_price(amazon_price=product.amazon_price, markup=payload.markup, markup_type=payload.markup_type, extra_percent=extra_pct, tax_rate=tax_rate)

    product.markup = payload.markup
    product.markup_type = payload.markup_type
    product.extra_percent = extra_pct
    product.price = new_price
    product.is_manual_override = True

    # ✅ YEH LINE ADD KAREIN (Direct Database Update)
    db.query(Product).filter(Product.id == product.id).update({"tax_rate": tax_rate})

    db.commit()
    db.refresh(product)

    if store and store.access_token and product.shopify_product_id:
        token_ok = await _ensure_valid_store_token(db, store)
        if token_ok:
            try:
                await sync_update_shopify_price(shop_domain=store.shop_domain, access_token=store.access_token, shopify_product_id=product.shopify_product_id, new_price=new_price, refresh_token=store.refresh_token, tags=product.tags or [], product_type=(product.categories[0] if product.categories else ""))
            except Exception as e: logger.error(f"❌ Shopify update exception: {e}")

    return product


# ============================================
# ✅ FIXED: BULK UPDATE
# ============================================
@router.post("/markup/bulk-update")
async def bulk_update_markup(payload: MarkupUpdate, store_id: int = None, db: Session = Depends(get_db)):
    query = db.query(Product).filter(Product.shopify_status == "active")
    if store_id: query = query.filter(Product.shopify_store_id == store_id)

    products = query.all()
    updated, shopify_updated, shopify_failed = 0, 0, 0
    token_refreshed_stores = set()
    
    extra_pct = payload.extra_percent if payload.extra_percent is not None else 0.0

    for product in products:
        product_store = _get_store_for_product(db, product, fallback_store_id=store_id)
        _, _, _, store_tax = _get_store_defaults(product_store)

        tax_rate = payload.tax_rate if payload.tax_rate is not None else store_tax

        new_price = calculate_final_price(amazon_price=product.amazon_price, markup=payload.markup, markup_type=payload.markup_type, extra_percent=extra_pct, tax_rate=tax_rate)
        
        product.markup = payload.markup
        product.markup_type = payload.markup_type
        product.extra_percent = extra_pct
        product.price = new_price
        product.is_manual_override = True
        
        # ✅ YEH LINE ADD KAREIN (Yeh bulk update mein missing thi)
        db.query(Product).filter(Product.id == product.id).update({"tax_rate": tax_rate})
        
        updated += 1

        if product_store and product_store.access_token and product.shopify_product_id:
            if product_store.shop_domain not in token_refreshed_stores:
                token_ok = await _ensure_valid_store_token(db, product_store)
                if not token_ok:
                    shopify_failed += 1
                    continue
                token_refreshed_stores.add(product_store.shop_domain)

            try:
                ok = await sync_update_shopify_price(shop_domain=product_store.shop_domain, access_token=product_store.access_token, shopify_product_id=product.shopify_product_id, new_price=new_price, refresh_token=product_store.refresh_token, tags=product.tags or [], product_type=(product.categories[0] if product.categories else ""))
                if ok: shopify_updated += 1
                else: shopify_failed += 1
            except Exception as e:
                shopify_failed += 1
                logger.error(f"❌ Shopify update exception for {product.asin}: {e}")

    db.commit()
    return {"success": True, "updated": updated, "shopify_updated": shopify_updated, "shopify_failed": shopify_failed}


@router.post("/markup/sync-from-shopify")
async def sync_products_from_shopify(store_id: int = None, db: Session = Depends(get_db)):
    if store_id: store = db.query(ShopifyStore).filter(ShopifyStore.id == store_id).first()
    else: store = db.query(ShopifyStore).first()

    if not store or not store.access_token: raise HTTPException(status_code=400, detail="Shopify store not configured")
    token_ok = await _ensure_valid_store_token(db, store)
    if not token_ok: raise HTTPException(status_code=401, detail=f"Token invalid for {store.shop_domain}. Please reinstall the app.")

    shop, access_token = store.shop_domain, store.access_token
    store_markup, store_markup_type, store_extra_pct, store_tax = _get_store_defaults(store)

    query = """
    query getProducts($cursor: String) {
      products(first: 50, after: $cursor, query: "status:active") {
        pageInfo { hasNextPage endCursor }
        edges { node { id title handle status variants(first: 1) { edges { node { sku price inventoryQuantity } } } } }
      }
    }
    """
    all_products, cursor, has_next = [], None, True
    while has_next:
        result = await shopify_graphql(shop, access_token, query, {"cursor": cursor})
        products_data = result.get("data", {}).get("products", {})
        edges, page_info = products_data.get("edges", []), products_data.get("pageInfo", {})
        for edge in edges:
            node = edge["node"]
            variants = node.get("variants", {}).get("edges", [])
            sku, price, inventory = None, None, 0
            if variants:
                variant = variants[0]["node"]
                sku, price, inventory = variant.get("sku"), variant.get("price"), variant.get("inventoryQuantity", 0)
            all_products.append({"shopify_id": node["id"], "title": node["title"], "handle": node.get("handle"), "status": node.get("status", "").lower(), "sku": sku, "price": price, "inventory": inventory})
        has_next, cursor = page_info.get("hasNextPage", False), page_info.get("endCursor")

    existing_products = db.query(Product).filter(Product.shopify_store_id == store.id).all()
    for p in existing_products: p.shopify_status = "draft"
    db.commit()

    added, updated, skipped = 0, 0, 0
    for sp in all_products:
        sku, shopify_id, title, shopify_price = sp.get("sku"), sp.get("shopify_id"), sp.get("title"), float(sp["price"]) if sp.get("price") else None
        if not sku: sku = f"SHOPIFY_{shopify_id.replace('gid://shopify/Product/', '')}"
        else: sku = str(sku).strip()[:255]
        if title: title = title[:500]

        product = db.query(Product).filter(Product.asin == sku).first()
        if product:
            product.shopify_product_id, product.shopify_handle, product.shopify_status, product.shopify_store_id = shopify_id, sp.get("handle"), sp.get("status", "active"), store.id
            if not product.title: product.title = title
            if shopify_price:
                product.amazon_price = shopify_price
                p_markup = product.markup or store_markup
                p_markup_type = product.markup_type or store_markup_type
                p_extra = getattr(product, "extra_percent", None) or store_extra_pct
                p_tax = getattr(product, "tax_rate", None) or store_tax
                if p_markup is not None and p_markup_type is not None:
                    product.price = calculate_final_price(amazon_price=shopify_price, markup=p_markup, markup_type=p_markup_type, extra_percent=p_extra, tax_rate=p_tax)
            updated += 1
        else:
            final_price = None
            if shopify_price and store_markup is not None and store_markup_type is not None:
                final_price = calculate_final_price(amazon_price=shopify_price, markup=store_markup, markup_type=store_markup_type, extra_percent=store_extra_pct, tax_rate=store_tax)
            new_product = Product(asin=sku, title=title, shopify_product_id=shopify_id, shopify_handle=sp.get("handle"), shopify_status=sp.get("status", "active"), shopify_store_id=store.id, amazon_price=shopify_price, price=final_price, is_available=True, stock_quantity=sp.get("inventory", 0))
            db.add(new_product)
            added += 1

    db.commit()
    return {"success": True, "total_shopify_products": len(all_products), "added": added, "updated": updated, "skipped": skipped}