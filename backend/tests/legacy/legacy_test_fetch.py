# test_fetch.py
import asyncio
import json
from app.services.brightdata import fetch_product_from_brightdata


async def main():
    asin = "B0FHHNKPFX"
    url = f"https://www.amazon.com/dp/{asin}"

    print(f"🔄 Fetching {asin} from Bright Data...")
    result = await fetch_product_from_brightdata(url)

    print("\n" + "=" * 60)
    print("📦 RESULT")
    print("=" * 60)
    print(f"ASIN:        {result.get('asin')}")
    print(f"Title:       {result.get('title')}")
    print(f"Brand:       {result.get('brand')}")
    print(f"Price:       ${result.get('amazon_price')}")
    print(f"Rating:      {result.get('rating')}")
    print(f"Reviews:     {result.get('reviews_count')}")
    print(f"Available:   {result.get('is_available')}")
    print(f"\n📂 Categories ({len(result.get('categories', []))}):")
    for c in result.get("categories", []):
        print(f"   • {c}")
    print(f"\n🏷️  Tags ({len(result.get('tags', []))}):")
    for t in result.get("tags", []):
        print(f"   • {t}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())