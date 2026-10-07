# ============================================
# app/api/routes/billing_routes.py
# Shopify Billing endpoints
# ============================================

import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ShopifyStore
from app.models.shopify_subscription import ShopifySubscription   # ✅ NAYA
from app.services.billing import (
    BILLING_PLANS,
    create_subscription,
    get_active_subscription,
)
from app.services.shopify import (
    exchange_id_token_for_offline_token,
    verify_id_token,
)
from app.config import settings

logger = logging.getLogger(__name__)

# ⚠️⚠️⚠️ YE LINE ZAROORI HAI — ISKE BINA ROUTER KAAM NAHI KAREGA
router = APIRouter(prefix="/api/billing", tags=["Billing"])
# ⚠️⚠️⚠️


# ============================================
# HELPER: STORE DHUNDO YA TOKEN EXCHANGE SE INSTALL KARO
# ============================================
async def get_or_install_store(
    db: Session,
    shop_domain: str,
    id_token: str,
    force_refresh: bool = False,
):
    """DB mein store ho to return, warna (ya force_refresh par) token
    exchange karke naya offline token Supabase mein save karta hai."""
    store = (
        db.query(ShopifyStore)
        .filter(ShopifyStore.shop_domain == shop_domain)
        .first()
    )

    if store and store.access_token and not force_refresh:
        return store

    token_data = await exchange_id_token_for_offline_token(shop_domain, id_token)
    if not token_data or not token_data.get("access_token"):
        return store  # exchange fail — jo hai wahi (ya None)

    scopes = token_data.get("scope") or settings.SHOPIFY_SCOPES

    if store:
        store.access_token = token_data["access_token"]
        store.scopes = scopes
        logger.info(f"🔄 Token refreshed via token exchange: {shop_domain}")
    else:
        store = ShopifyStore(
            shop_domain=shop_domain,
            access_token=token_data["access_token"],
            scopes=scopes,
        )
        db.add(store)
        logger.info(f"🆕 Store saved via token exchange: {shop_domain}")

    db.commit()
    db.refresh(store)
    return store


# ============================================
# GET AVAILABLE PLANS
# ============================================
@router.get("/plans")
def get_plans():
    """Saare available billing plans"""
    return {
        "plans": [
            {
                "key": key,
                "name": plan["name"],
                "price": plan["price"],
                "currency": plan["currency"],
                "interval": plan["interval"],
                "trial_days": plan["trial_days"],
                "features": plan["features"],
            }
            for key, plan in BILLING_PLANS.items()
        ]
    }


# ============================================
# CHECK SUBSCRIPTION STATUS
# ============================================
@router.get("/status")
async def subscription_status(
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    """Merchant ka subscription status check karta hai."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization")

    token = authorization.replace("Bearer ", "").strip()

    try:
        payload = verify_id_token(token)
    except ValueError as e:
        logger.warning(f"/billing/status token rejected: {e}")
        raise HTTPException(status_code=401, detail=str(e))

    shop_domain = payload.get("dest", "").replace("https://", "").split("/")[0]

    store = await get_or_install_store(db, shop_domain, token)

    if not store:
        raise HTTPException(status_code=404, detail="Store not connected")

    sub_status = await get_active_subscription(
        shop=shop_domain,
        access_token=store.access_token,
    )

    return {
        "shop_domain": shop_domain,
        "active": sub_status.get("active", False),
        "subscription": sub_status.get("subscription"),
    }


# ============================================
# SUBSCRIBE TO PLAN
# ============================================
@router.post("/subscribe/{plan_key}")
async def subscribe(
    plan_key: str,
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    """Merchant ko subscription par bhejta hai."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization")

    token = authorization.replace("Bearer ", "").strip()

    try:
        payload = verify_id_token(token)
    except ValueError as e:
        logger.warning(f"/billing/subscribe token rejected: {e}")
        raise HTTPException(status_code=401, detail=str(e))

    shop_domain = payload.get("dest", "").replace("https://", "").split("/")[0]

    store = await get_or_install_store(db, shop_domain, token)

    if not store:
        raise HTTPException(status_code=404, detail="Store not connected")

    return_url = (
        f"https://amazon-product-manager-asev.vercel.app/shopify-app"
        f"?subscription=success"
    )

    result = await create_subscription(
        shop=shop_domain,
        access_token=store.access_token,
        plan_key=plan_key,
        return_url=return_url,
    )

    # ✅ Purana "Shop-owned" token ho to naya token lekar ek baar retry
    if "owned by a Shop" in str(result.get("errors", "")):
        logger.warning(f"Stale shop-owned token for {shop_domain}, refreshing...")
        store = await get_or_install_store(
            db, shop_domain, token, force_refresh=True
        )
        if store:
            result = await create_subscription(
                shop=shop_domain,
                access_token=store.access_token,
                plan_key=plan_key,
                return_url=return_url,
            )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    if "errors" in result:
        raise HTTPException(status_code=400, detail=str(result["errors"]))

    # ✅ Subscription record DB mein save karein (status: pending)
    subscription = result.get("subscription", {})
    if subscription:
        try:
            existing = (
                db.query(ShopifySubscription)
                .filter(ShopifySubscription.shop_domain == shop_domain)
                .first()
            )

            if existing:
                existing.subscription_id = subscription.get("id")
                existing.subscription_status = "pending"
                existing.plan_name = subscription.get("name")
            else:
                new_sub = ShopifySubscription(
                    shop_domain=shop_domain,
                    subscription_id=subscription.get("id"),
                    subscription_status="pending",
                    plan_name=subscription.get("name"),
                )
                db.add(new_sub)

            db.commit()
            logger.info(f"✅ Subscription saved to DB: {shop_domain} → pending")
        except Exception as e:
            logger.error(f"❌ Failed to save subscription to DB: {e}")
            db.rollback()
            # Don't fail the request — Shopify subscription already created

    return {
        "success": True,
        "confirmation_url": result.get("confirmation_url"),
        "subscription": result.get("subscription"),
    }