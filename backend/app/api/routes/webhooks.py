# ============================================
# app/api/routes/webhooks.py
# Shopify Webhooks — subscription events + product events
# + ✅ NAYA: products/delete webhook handler
# + ✅ FIXED: ASIN/SKU match (primary) + GID + numeric + LIKE (fallback)
# + ✅ FIXED: Multiple secrets tried for HMAC (webhook + api secret)
# + ✅ FIXED: ClientDisconnect gracefully handled
# ============================================

import base64
import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from starlette.requests import ClientDisconnect  # ✅ ADDED
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models import Product, ShopifyStore
from app.models.shopify_subscription import ShopifySubscription

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])


# ============================================
# VERIFY SHOPIFY WEBHOOK HMAC — Multiple Secrets
# ============================================
def verify_webhook_hmac(body: bytes, hmac_header: str) -> bool:
    """
    Shopify webhook signature verify karein.
    Multiple secrets try karta hai:
    1. SHOPIFY_WEBHOOK_SECRET
    2. SHOPIFY_API_SECRET
    """
    if not hmac_header:
        return False

    secrets_to_try = list({
        s for s in [
            settings.SHOPIFY_WEBHOOK_SECRET,
            settings.SHOPIFY_API_SECRET,
        ] if s
    })

    if not secrets_to_try:
        logger.error("❌ No webhook secret configured in settings!")
        return False

    for secret in secrets_to_try:
        computed = hmac.new(
            secret.encode(),
            body,
            hashlib.sha256,
        ).digest()
        computed_b64 = base64.b64encode(computed).decode()

        if hmac.compare_digest(computed_b64, hmac_header):
            logger.debug("   ✅ HMAC verified")
            return True

    logger.warning(
        f"   ❌ HMAC failed (tried {len(secrets_to_try)} secret(s), "
        f"header_len={len(hmac_header) if hmac_header else 0})"
    )
    return False


# ============================================
# SHOPIFY WEBHOOK HANDLER
# ============================================
@router.post("/shopify")
async def shopify_webhook(
    request: Request,
    x_shopify_hmac_sha256: str = Header(None),
    x_shopify_topic: str = Header(None),
    x_shopify_shop_domain: str = Header(None),
    db: Session = Depends(get_db),
):
    """Shopify webhook receiver — subscriptions + app events + product events"""
    
    # ✅ FIX: ClientDisconnect handle karein
    try:
        body = await request.body()
    except ClientDisconnect:
        logger.warning(
            f"⚠️ Shopify webhook client disconnected before body received "
            f"(topic={x_shopify_topic}, shop={x_shopify_shop_domain})"
        )
        return {"ok": True, "ignored": True, "reason": "client_disconnect"}

    if not verify_webhook_hmac(body, x_shopify_hmac_sha256):
        logger.warning(f"❌ Invalid webhook HMAC from {x_shopify_shop_domain}")
        raise HTTPException(401, "Invalid HMAC")

    try:
        payload = json.loads(body)
    except Exception as e:
        logger.error(f"❌ Invalid JSON: {e}")
        raise HTTPException(400, "Invalid JSON")

    logger.info(f"📥 Webhook: {x_shopify_topic} from {x_shopify_shop_domain}")

    try:
        if x_shopify_topic == "app_subscriptions/update":
            await _handle_subscription_update(
                shop_domain=x_shopify_shop_domain,
                payload=payload,
                db=db,
            )
        elif x_shopify_topic == "app_subscriptions/cancelled":
            await _handle_subscription_cancelled(
                shop_domain=x_shopify_shop_domain,
                payload=payload,
                db=db,
            )
        elif x_shopify_topic == "app/uninstalled":
            await _handle_app_uninstalled(
                shop_domain=x_shopify_shop_domain,
                db=db,
            )
        elif x_shopify_topic == "products/delete":
            await _handle_product_delete(
                shop_domain=x_shopify_shop_domain,
                payload=payload,
                db=db,
            )
        elif x_shopify_topic == "products/update":
            await _handle_product_update(
                shop_domain=x_shopify_shop_domain,
                payload=payload,
                db=db,
            )
        else:
            logger.info(f"ℹ️ Unhandled topic: {x_shopify_topic}")
    except Exception as e:
        logger.error(f"❌ Webhook handler error: {e}")

    return {"ok": True}


# ============================================
# SUBSCRIPTION UPDATE HANDLER
# ============================================
async def _handle_subscription_update(shop_domain, payload, db):
    """Subscription created / renewed / changed"""
    subscription = payload.get("app_subscription", {})

    sub_id = subscription.get("admin_graphql_api_id") or subscription.get("id")
    sub_name = subscription.get("name")
    sub_status = subscription.get("status", "").lower()

    logger.info(f"📦 Subscription update: {shop_domain} → {sub_name} ({sub_status})")

    existing = (
        db.query(ShopifySubscription)
        .filter(ShopifySubscription.shop_domain == shop_domain)
        .first()
    )

    if existing:
        existing.subscription_id = str(sub_id)
        existing.subscription_status = sub_status
        existing.plan_name = sub_name
        if subscription.get("current_period_end"):
            existing.current_period_end = subscription["current_period_end"]
    else:
        new_sub = ShopifySubscription(
            shop_domain=shop_domain,
            subscription_id=str(sub_id),
            subscription_status=sub_status,
            plan_name=sub_name,
            current_period_end=subscription.get("current_period_end"),
        )
        db.add(new_sub)

    db.commit()
    logger.info(f"✅ Subscription DB updated: {shop_domain}")


# ============================================
# SUBSCRIPTION CANCELLED HANDLER
# ============================================
async def _handle_subscription_cancelled(shop_domain, payload, db):
    """Merchant ne subscription cancel ki"""
    logger.info(f"❌ Subscription cancelled: {shop_domain}")

    existing = (
        db.query(ShopifySubscription)
        .filter(ShopifySubscription.shop_domain == shop_domain)
        .first()
    )

    if existing:
        existing.subscription_status = "cancelled"
        db.commit()


# ============================================
# APP UNINSTALLED HANDLER
# ============================================
async def _handle_app_uninstalled(shop_domain, db):
    """Merchant ne app uninstall kar diya"""
    logger.info(f"🗑️ App uninstalled: {shop_domain}")

    existing = (
        db.query(ShopifySubscription)
        .filter(ShopifySubscription.shop_domain == shop_domain)
        .first()
    )

    if existing:
        existing.subscription_status = "uninstalled"
        db.commit()


# ============================================
# ✅ PRODUCT DELETE HANDLER — ASIN/SKU Primary Match
# ============================================
async def _handle_product_delete(shop_domain, payload, db):
    """
    Shopify se product delete hone par DB se bhi delete karo.
    Priority: ASIN/SKU → GID → numeric → LIKE
    """
    shopify_id = payload.get("id")
    product_title = payload.get("title", "Unknown")

    if not shopify_id:
        logger.warning("⚠️ Product delete webhook: no id")
        return

    variants = payload.get("variants") or []
    sku_from_webhook = None
    if isinstance(variants, list):
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            sku = variant.get("sku")
            if sku and str(sku).strip() and str(sku).strip() != "None":
                sku_from_webhook = str(sku).strip()
                break

    logger.info(
        f"🗑️ Shopify product deleted: {product_title} "
        f"(id={shopify_id}, sku={sku_from_webhook})"
    )

    product = None

    # Strategy 1: ASIN/SKU match
    if sku_from_webhook:
        product = (
            db.query(Product)
            .filter(Product.asin == sku_from_webhook)
            .first()
        )
        if product:
            logger.info(f"   ✅ Matched via ASIN/SKU: {sku_from_webhook}")

    # Strategy 2: GID format
    if not product:
        product_gid = f"gid://shopify/Product/{shopify_id}"
        product = (
            db.query(Product)
            .filter(Product.shopify_product_id == product_gid)
            .first()
        )
        if product:
            logger.info(f"   ✅ Matched via GID: {product_gid}")

    # Strategy 3: Numeric format
    if not product:
        product = (
            db.query(Product)
            .filter(Product.shopify_product_id == str(shopify_id))
            .first()
        )
        if product:
            logger.info(f"   ✅ Matched via numeric: {shopify_id}")

    # Strategy 4: LIKE query
    if not product:
        product = (
            db.query(Product)
            .filter(Product.shopify_product_id.like(f"%{shopify_id}%"))
            .first()
        )
        if product:
            logger.info(
                f"   ✅ Matched via LIKE: %{shopify_id}% "
                f"→ {product.shopify_product_id}"
            )

    # Delete if found
    if product:
        asin = product.asin
        db.delete(product)
        db.commit()
        logger.info(f"✅ Product deleted from DB via webhook: {asin}")
    else:
        logger.info(
            f"ℹ️ Webhook: product not found in DB "
            f"(shopify_id={shopify_id}, sku={sku_from_webhook})"
        )


# ============================================
# ✅ PRODUCT UPDATE HANDLER — ASIN/SKU Primary Match
# ============================================
async def _handle_product_update(shop_domain, payload, db):
    """
    Shopify se product update hone par DB update karo.
    Priority: ASIN/SKU → GID → numeric → LIKE
    """
    shopify_id = payload.get("id")
    if not shopify_id:
        return

    variants = payload.get("variants") or []
    sku_from_webhook = None
    if isinstance(variants, list):
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            sku = variant.get("sku")
            if sku and str(sku).strip() and str(sku).strip() != "None":
                sku_from_webhook = str(sku).strip()
                break

    product = None

    if sku_from_webhook:
        product = (
            db.query(Product)
            .filter(Product.asin == sku_from_webhook)
            .first()
        )

    if not product:
        product_gid = f"gid://shopify/Product/{shopify_id}"
        product = (
            db.query(Product)
            .filter(Product.shopify_product_id == product_gid)
            .first()
        )

    if not product:
        product = (
            db.query(Product)
            .filter(Product.shopify_product_id == str(shopify_id))
            .first()
        )

    if not product:
        product = (
            db.query(Product)
            .filter(Product.shopify_product_id.like(f"%{shopify_id}%"))
            .first()
        )

    if not product:
        return

    new_title = payload.get("title")
    if new_title and new_title != product.title:
        product.title = new_title[:500]

    new_status = payload.get("status", "").lower()
    if new_status:
        product.shopify_status = new_status

    if variants:
        first_variant = variants[0]
        new_price = first_variant.get("price")
        if new_price:
            try:
                product.price = float(new_price)
            except (ValueError, TypeError):
                pass

    db.commit()
    logger.info(f"✅ Product updated from webhook: {product.asin}")