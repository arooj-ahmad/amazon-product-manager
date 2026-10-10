# ============================================
# app/api/routes/webhooks.py
# Shopify Webhooks — subscription events + product events
# + ✅ NAYA: products/delete webhook handler
# + ✅ FIXED: Universal match (GID + numeric + LIKE query)
# ============================================

import base64
import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Product, ShopifyStore
from app.models.shopify_subscription import ShopifySubscription

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])


# ============================================
# VERIFY SHOPIFY WEBHOOK HMAC
# ============================================
def verify_webhook_hmac(body: bytes, hmac_header: str) -> bool:
    """Shopify webhook signature verify karein"""
    if not hmac_header:
        return False

    computed = hmac.new(
        settings.SHOPIFY_API_SECRET.encode(),
        body,
        hashlib.sha256,
    ).digest()

    computed_b64 = base64.b64encode(computed).decode()

    return hmac.compare_digest(computed_b64, hmac_header)


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
    body = await request.body()

    # 1. Verify HMAC
    if not verify_webhook_hmac(body, x_shopify_hmac_sha256):
        logger.warning(f"❌ Invalid webhook HMAC from {x_shopify_shop_domain}")
        raise HTTPException(401, "Invalid HMAC")

    # 2. Parse payload
    try:
        payload = json.loads(body)
    except Exception as e:
        logger.error(f"❌ Invalid JSON: {e}")
        raise HTTPException(400, "Invalid JSON")

    logger.info(f"📥 Webhook: {x_shopify_topic} from {x_shopify_shop_domain}")

    # 3. Handle based on topic
    try:
        # ── Subscription events ──
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
        # ── Product events ──
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
# ✅ PRODUCT DELETE HANDLER — Universal Match
# ============================================
async def _handle_product_delete(shop_domain, payload, db):
    """
    Shopify se product delete hone par DB se bhi delete karo.

    DB mein format: gid://shopify/Product/15407641821220
    Webhook payload: { "id": 15407641821220 }

    3 strategies try karta hai:
    1. GID format match
    2. Numeric format match
    3. LIKE query (universal — koi bhi format match kare)
    """
    shopify_id = payload.get("id")
    product_title = payload.get("title", "Unknown")

    if not shopify_id:
        logger.warning("⚠️ Product delete webhook: no id")
        return

    logger.info(
        f"🗑️ Shopify product deleted: {product_title} "
        f"(id={shopify_id})"
    )

    product = None

    # ── Strategy 1: GID format (DB mein yahi saved hai) ──
    product_gid = f"gid://shopify/Product/{shopify_id}"
    product = (
        db.query(Product)
        .filter(Product.shopify_product_id == product_gid)
        .first()
    )

    if product:
        logger.info(f"   ✅ Matched via GID: {product_gid}")

    # ── Strategy 2: Numeric format ──
    if not product:
        product = (
            db.query(Product)
            .filter(Product.shopify_product_id == str(shopify_id))
            .first()
        )
        if product:
            logger.info(f"   ✅ Matched via numeric: {shopify_id}")

    # ── Strategy 3: LIKE query (universal fallback) ──
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

    # ── Delete if found ──
    if product:
        asin = product.asin
        db.delete(product)
        db.commit()
        logger.info(f"✅ Product deleted from DB via webhook: {asin}")
    else:
        logger.info(
            f"ℹ️ Webhook: product not found in DB "
            f"(shopify_id={shopify_id}, tried GID + numeric + LIKE)"
        )


# ============================================
# ✅ PRODUCT UPDATE HANDLER
# ============================================
async def _handle_product_update(shop_domain, payload, db):
    """
    Shopify se product update hone par DB update karo.
    Sirf title, status, price update karta hai.
    """
    shopify_id = payload.get("id")
    if not shopify_id:
        return

    product = None

    # GID format
    product_gid = f"gid://shopify/Product/{shopify_id}"
    product = (
        db.query(Product)
        .filter(Product.shopify_product_id == product_gid)
        .first()
    )

    # Numeric format
    if not product:
        product = (
            db.query(Product)
            .filter(Product.shopify_product_id == str(shopify_id))
            .first()
        )

    # LIKE query
    if not product:
        product = (
            db.query(Product)
            .filter(Product.shopify_product_id.like(f"%{shopify_id}%"))
            .first()
        )

    if not product:
        return

    # Update fields
    new_title = payload.get("title")
    if new_title and new_title != product.title:
        product.title = new_title[:500]

    new_status = payload.get("status", "").lower()
    if new_status:
        product.shopify_status = new_status

    # Variants se price update karo
    variants = payload.get("variants", [])
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