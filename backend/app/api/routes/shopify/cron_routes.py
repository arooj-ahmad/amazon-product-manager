# ============================================
# app/api/routes/shopify/cron_routes.py
# ============================================

import asyncio
from fastapi import APIRouter, Header, HTTPException
from app.services.shopify import verify_id_token
from app.services.scheduler import (
    run_price_update_now,
    run_inventory_update_now,
    last_run_status,
)

router = APIRouter(tags=["Shopify Cron"])


# ✅ 1. PRICE UPDATE (Only Price)
@router.post("/trigger-price-update-async")
async def trigger_price_update_async(authorization: str = Header(...)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization")

    token = authorization.replace("Bearer ", "").strip()
    try:
        payload = verify_id_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid ID token: {str(e)}")

    shop_domain = payload.get("dest", "").replace("https://", "").split("/")[0]
    if not shop_domain:
        raise HTTPException(status_code=401, detail="Shop domain missing")

    if last_run_status.get("running"):
        return {"success": True, "message": "Price update already running"}

    asyncio.create_task(run_price_update_now())
    return {"success": True, "message": "Price update started in background"}


# ✅ 2. INVENTORY UPDATE (Only Inventory)
@router.post("/trigger-inventory-update-async")
async def trigger_inventory_update_async(authorization: str = Header(...)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization")

    token = authorization.replace("Bearer ", "").strip()
    try:
        payload = verify_id_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid ID token: {str(e)}")

    shop_domain = payload.get("dest", "").replace("https://", "").split("/")[0]
    if not shop_domain:
        raise HTTPException(status_code=401, detail="Shop domain missing")

    if last_run_status.get("running"):
        return {"success": True, "message": "Inventory update already running"}

    asyncio.create_task(run_inventory_update_now())
    return {"success": True, "message": "Inventory update started in background"}


# ✅ 3. STATUS CHECK (Dono ke liye same)
@router.get("/price-update-status")
async def get_price_update_status():
    return {
        "success": True,
        "running": last_run_status.get("running", False),
        "summary": last_run_status.get("summary"),
    }