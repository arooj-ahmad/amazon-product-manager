# ============================================
# app/api/routes/billing_routes.py
# Shopify Billing endpoints
# ============================================

import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import text                              # ✅ NAYA
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ShopifyStore
from app.models.shopify_subscription import ShopifySubscription
from app.services.billing import (
    BILLING_PLANS,
    create_subscription,
    get_active_subscription,
)
from app.services.shopify import verify_id_token, shopify_graphql  # ✅ NAYA

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["Billing"])


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
        raise HTTPException(status_code=401, detail=str(e))

    shop_domain = payload.get("dest", "").replace("https://", "").split("/")[0]

    store = (
        db.query(ShopifyStore)
        .filter(ShopifyStore.shop_domain == shop_domain)
        .first()
    )

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
        raise HTTPException(status_code=401, detail=str(e))

    shop_domain = payload.get("dest", "").replace("https://", "").split("/")[0]

    store = (
        db.query(ShopifyStore)
        .filter(ShopifyStore.shop_domain == shop_domain)
        .first()
    )

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

    return {
        "success": True,
        "confirmation_url": result.get("confirmation_url"),
        "subscription": result.get("subscription"),
    }


# ============================================
# ✅ CANCEL SUBSCRIPTION (Testing + Production)
# ============================================
@router.post("/cancel-subscription")
async def cancel_subscription(
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    """
    Current Shopify subscription cancel karein.
    Testing ke liye useful hai — naya subscribe flow test karne ke liye.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization")

    token = authorization.replace("Bearer ", "").strip()

    try:
        payload = verify_id_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    shop_domain = payload.get("dest", "").replace("https://", "").split("/")[0]

    store = (
        db.query(ShopifyStore)
        .filter(ShopifyStore.shop_domain == shop_domain)
        .first()
    )

    if not store:
        raise HTTPException(status_code=404, detail="Store not connected")

    # Step 1: Active subscription fetch
    query = """
    query {
      currentAppInstallation {
        activeSubscriptions {
          id
          name
          status
        }
      }
    }
    """
    result = await shopify_graphql(shop_domain, store.access_token, query)

    subs = (
        result.get("data", {})
        .get("currentAppInstallation", {})
        .get("activeSubscriptions", [])
    )

    if not subs:
        # DB clean karein anyway
        db.execute(
            text("DELETE FROM shopify_subscriptions WHERE shop_domain = :shop"),
            {"shop": shop_domain},
        )
        db.commit()
        return {
            "success": True,
            "message": "No active subscription found",
            "cancelled": 0,
        }

    # Step 2: Cancel mutation
    sub_id = subs[0]["id"]
    logger.info(f"🗑️ Cancelling subscription: {sub_id}")

    mutation = """
    mutation appSubscriptionCancel($id: ID!) {
      appSubscriptionCancel(id: $id) {
        appSubscription {
          id
          status
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    cancel_result = await shopify_graphql(
        shop_domain, store.access_token, mutation, {"id": sub_id}
    )
    logger.info(f"Cancelled: {cancel_result}")

    user_errors = (
        cancel_result.get("data", {})
        .get("appSubscriptionCancel", {})
        .get("userErrors", [])
    )

    if user_errors:
        logger.error(f"❌ Cancel errors: {user_errors}")
        raise HTTPException(status_code=400, detail=str(user_errors))

    # Step 3: DB clean
    db.execute(
        text("DELETE FROM shopify_subscriptions WHERE shop_domain = :shop"),
        {"shop": shop_domain},
    )
    db.commit()

    return {
        "success": True,
        "message": "Subscription cancelled",
        "cancelled": sub_id,
        "result": cancel_result,
    }