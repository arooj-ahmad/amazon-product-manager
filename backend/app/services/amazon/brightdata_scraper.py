# ============================================
# app/services/amazon/brightdata_scraper.py
# Scheduler ke liye sirf Price aur Stock fetch karta hai
# ============================================

import httpx
import logging

from app.config import settings
from .exceptions import BrightDataError
from .helpers import extract_asin_from_url, parse_price
from .inventory import check_availability_brightdata

logger = logging.getLogger(__name__)

async def fetch_product_from_brightdata(amazon_url: str) -> dict:
    api_url = (
        f"{settings.BRIGHT_DATA_API_URL}"
        f"?dataset_id={settings.BRIGHT_DATA_DATASET_ID}"
        f"&include_errors=true"
    )
    headers = {
        "Authorization": f"Bearer {settings.BRIGHT_DATA_API_KEY}",
        "Content-Type": "application/json",
    }
    body = [{"url": amazon_url}]

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(api_url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        raise BrightDataError(f"Bright Data API Error: {str(e)}")

    raw = data[0] if isinstance(data, list) and len(data) > 0 else data
    if "error" in raw:
        raise BrightDataError(f"Bright Data error: {raw['error']}")

    asin = raw.get("asin") or extract_asin_from_url(amazon_url)
    if not asin:
        raise BrightDataError("ASIN nahi mila")

    # =====================================================
    # ✅ SIRF STOCK CHECK KARO (Bright Data Logic)
    # =====================================================
    is_available, availability_text, reason = check_availability_brightdata(raw)
    stock_quantity = 100 if is_available else 0
    
    logger.info(f"   BrightData Inventory: {availability_text} (Reason: {reason}) -> Stock: {stock_quantity}")

    # =====================================================
    # ✅ SIRF PRICE CHECK KARO
    # =====================================================
    amazon_price = parse_price(raw.get("final_price") or raw.get("price"))

    # =====================================================
    # RETURN SIRF ZAROORI DATA (Scheduler ke liye)
    # =====================================================
    return {
        "asin": asin,
        "amazon_price": amazon_price,
        "is_available": is_available,
        "availability": availability_text,
        "stock_quantity": stock_quantity,
    }