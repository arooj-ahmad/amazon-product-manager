import asyncio
import httpx
from app.core.config import settings
from app.services.amazon.helpers import extract_asin_from_url, parse_price

async def test_zip(amazon_url: str, zip_code: str):
    api_url = f"{settings.BRIGHT_DATA_API_URL}?dataset_id={settings.BRIGHT_DATA_DATASET_ID}&include_errors=true"
    headers = {"Authorization": f"Bearer {settings.BRIGHT_DATA_API_KEY}", "Content-Type": "application/json"}
    
    # ✅ NAYA: Zip code pass kar rahe hain
    body = [{"url": amazon_url, "zipcode": zip_code}]

    print(f"\nTesting Zip Code: {zip_code} ...")
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(api_url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()

        raw = data[0] if isinstance(data, list) and len(data) > 0 else data
        if "error" in raw: 
            print(f"❌ Error: {raw['error']}")
            return

        price = parse_price(raw.get("final_price") or raw.get("price"))
        
        # Debug: Check karein ke response mein zip code aaya ya nahi
        returned_zip = raw.get("zipcode") or raw.get("zip_code") or raw.get("delivery_zip") or "Not in response"
        
        print(f"  Zip in response: {returned_zip}")
        print(f"  Price:           ${price}")
        print(f"  Availability:    {raw.get('availability', 'N/A')}")
        
        # Check ke kya 'add to cart' ya 'in_stock' field mein farq aaya
        in_stock = raw.get("in_stock") or raw.get("add_to_cart_available") or raw.get("buybox_available")
        print(f"  In Stock field:  {in_stock}")

    except Exception as e:
        print(f"❌ Error: {e}")

async def main():
    url = "https://www.amazon.com/dp/B0F9FG4XNY"  # LED Drawing Board
    
    # 3 different zip codes test karein
    zips = ["30024", "10001", "90210"] # Georgia (Default), New York, California
    
    for z in zips:
        await test_zip(url, z)
        print("-" * 40)

if __name__ == "__main__":
    asyncio.run(main())
