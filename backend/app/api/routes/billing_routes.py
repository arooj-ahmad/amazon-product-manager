# ============================================
# app/api/routes/billing_routes.py
# Shopify Billing endpoints
# ============================================

import logging
from datetime import datetime, timedelta  # ✅ NAYA

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ShopifyStore
from app.models.shopify_subscription import ShopifySubscription
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

router = APIRouter(prefix="/api/billing", tags=["Billing"])


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
    exchange karke naya expiring offline token Supabase mein save karta hai."""
    store = (
        db.query(ShopifyStore)
        .filter(ShopifyStore.shop_domain == shop_domain)
        .first()
    )

    if store and store.access_token and not force_refresh:
        return store

    token_data = await exchange_id_token_for_offline_token(shop_domain, id_token)
    if not token_data or not token_data.get("access_token"):
        return store

    scopes = token_data.get("scope") or settings.SHOPIFY_SCOPES

    # ✅ Expiry calculate karo
    expires_at = None
    if token_data.get("expires_in"):
        expires_at = datetime.utcnow() + timedelta(
            seconds=int(token_data["expires_in"])
        )

    refresh_token_expires_at = None
    if token_data.get("refresh_token_expires_in"):
        refresh_token_expires_at = datetime.utcnow() + timedelta(
            seconds=int(token_data["refresh_token_expires_in"])
        )

    if store:
        store.access_token = token_data["access_token"]
        store.scopes = scopes
        store.refresh_token = token_data.get("refresh_token")
        store.expires_at = expires_at
        store.refresh_token_expires_at = refresh_token_expires_at
        logger.info(f"🔄 Token refreshed via token exchange: {shop_domain}")
    else:
        store = ShopifyStore(
            shop_domain=shop_domain,
            access_token=token_data["access_token"],
            scopes=scopes,
            refresh_token=token_data.get("refresh_token"),
            expires_at=expires_at,
            refresh_token_expires_at=refresh_token_expires_at,
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

    # 1. Shopify Admin API se check karein
    sub_status = await get_active_subscription(
        shop=shop_domain,
        access_token=store.access_token,
    )

    is_active = sub_status.get("active", False)
    subscription_info = sub_status.get("subscription")

    # 2. Supabase DB record check karein
    db_sub = (
        db.query(ShopifySubscription)
        .filter(ShopifySubscription.shop_domain == shop_domain)
        .first()
    )

    if not is_active and db_sub and db_sub.subscription_status == "active":
        is_active = True
        subscription_info = {
            "id": db_sub.subscription_id,
            "name": db_sub.plan_name or "Basic Plan",
            "status": "ACTIVE",
            "trial_days": 7,
        }
    elif is_active and db_sub:
        if db_sub.subscription_status != "active":
            db_sub.subscription_status = "active"
            if subscription_info and subscription_info.get("name"):
                db_sub.plan_name = subscription_info.get("name")
            db.commit()

    return {
        "shop_domain": shop_domain,
        "active": is_active,
        "subscription": subscription_info,
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

    # ✅ Return URL: Post-billing callback endpoint
    # Shopify charge approve hone ke baad yahan redirect karega,
    # jahan se user seedha Shopify Admin ke andar app page par redirect hoga!
    return_url = (
        f"https://amazon-product-manager-production.up.railway.app/api/billing/callback"
        f"?shop={shop_domain}&plan={plan_key}"
    )

    result = await create_subscription(
        shop=shop_domain,
        access_token=store.access_token,
        plan_key=plan_key,
        return_url=return_url,
    )

    # ✅ Agar "owned by a Shop" error aaye to naya token lekar retry karo
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

    return {
        "success": True,
        "confirmation_url": result.get("confirmation_url"),
        "subscription": result.get("subscription"),
    }


# ============================================
# BILLING CALLBACK (Shopify Approval Ke Baad Redirect)
# ============================================
@router.get("/callback")
async def billing_callback(
    shop: str = Query(...),
    plan: str = Query("basic"),
    charge_id: str = Query(None),
    db: Session = Depends(get_db),
):
    """
    Shopify subscription approve hone ke baad merchant ko yahan redirect karta hai.
    1. DB mein subscription 'active' mark karta hai
    2. Merchant ko seedha Shopify Admin ke andar app page par redirect kar deta hai
    """
    logger.info(
        f"✅ Billing callback received: shop={shop}, plan={plan}, charge_id={charge_id}"
    )

    try:
        existing = (
            db.query(ShopifySubscription)
            .filter(ShopifySubscription.shop_domain == shop)
            .first()
        )
        if existing:
            existing.subscription_status = "active"
            if charge_id:
                existing.subscription_id = charge_id
            existing.plan_name = plan
        else:
            new_sub = ShopifySubscription(
                shop_domain=shop,
                subscription_id=charge_id,
                subscription_status="active",
                plan_name=plan,
            )
            db.add(new_sub)
        db.commit()
        logger.info(f"✅ Subscription set to ACTIVE in DB for {shop}")
    except Exception as e:
        logger.error(f"❌ Failed to update subscription in callback: {e}")
        db.rollback()

    # Shopify Admin embedded app URL:
    # Format: https://admin.shopify.com/store/{shop_slug}/apps/stock-sync-partner
    shop_slug = shop.replace(".myshopify.com", "")
    admin_url = f"https://admin.shopify.com/store/{shop_slug}/apps/stock-sync-partner"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Redirecting to Shopify Admin...</title>
    <meta http-equiv="refresh" content="1; url={admin_url}">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            background: #f6f6f7;
        }}
        .card {{
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.08);
            text-align: center;
            max-width: 440px;
            width: 90%;
        }}
        h2 {{ color: #008060; margin-top: 0; font-size: 22px; }}
        p {{ color: #6d7175; font-size: 15px; margin-bottom: 24px; line-height: 1.5; }}
        .btn {{
            display: inline-block;
            background: #008060;
            color: white;
            padding: 12px 28px;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 600;
            transition: background 0.2s;
        }}
        .btn:hover {{ background: #006e52; }}
    </style>
</head>
<body>
    <div class="card">
        <h2>✅ Subscription Activated!</h2>
        <p>Aapki subscription active ho chuki hai.<br>Shopify Admin ke andar redirect kiya ja raha hai...</p>
        <a class="btn" href="{admin_url}">Shopify Admin Kholein</a>
    </div>
    <script>
        setTimeout(function() {{
            window.location.href = "{admin_url}";
        }}, 800);
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)


# ============================================
# INSTANT TEST ACTIVATION (Testing ke liye bypass)
# ============================================
@router.post("/activate-test")
def activate_test_subscription(
    shop_domain: str = Body(..., embed=True),
    plan_name: str = Body("Basic Plan", embed=True),
    db: Session = Depends(get_db),
):
    """
    Testing / dev ke liye store ko direct active subscription assign karta hai
    taaki merchant dashboard (Amazon product import) foran open ho sake.
    """
    existing = (
        db.query(ShopifySubscription)
        .filter(ShopifySubscription.shop_domain == shop_domain)
        .first()
    )
    if existing:
        existing.subscription_status = "active"
        existing.plan_name = plan_name
    else:
        new_sub = ShopifySubscription(
            shop_domain=shop_domain,
            subscription_id="test_sub_active",
            subscription_status="active",
            plan_name=plan_name,
        )
        db.add(new_sub)

    db.commit()
    logger.info(f"✅ Dev active subscription set for {shop_domain}")
    return {"success": True, "message": f"Active subscription enabled for {shop_domain}"}