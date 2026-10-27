import asyncio
import json
from app.services.brightdata import fetch_product_from_brightdata


async def main():
    # ✅ Avidlove Dress — variations wala product (same as Shopify test)
    url = "https://www.amazon.com/dp/B0H8CTZTYM"

    print(f"Fetching: {url}\n")

    try:
        result = await fetch_product_from_brightdata(url)
    except Exception as e:
        print(f"❌ Error: {e}")
        return

    # Poora response dekho
    print("=" * 60)
    print("FULL RESPONSE:")
    print("=" * 60)
    print(json.dumps(result, indent=2, default=str))

    # Variations check karo
    print("\n" + "=" * 60)
    print("VARIATIONS CHECK:")
    print("=" * 60)

    parent_asin = result.get("parent_asin")
    print(f"Parent ASIN: {parent_asin}")

    # ✅ variations list
    variations = result.get("variations", [])
    print(f"\nTotal variations found: {len(variations)}")
    for v in variations:
        print(f"  • {v.get('name')} = {v.get('value')}")

    # ✅ variant_attributes
    variant_attrs = result.get("variant_attributes", [])
    print(f"\nTotal variant attributes: {len(variant_attrs)}")
    for attr in variant_attrs:
        print(f"  • {attr.get('name')} = {attr.get('value')}")

    # ✅ ASIN + Parent ASIN check
    print("\n" + "=" * 60)
    print("KEY FIELDS:")
    print("=" * 60)
    print(f"ASIN:        {result.get('asin')}")
    print(f"Parent ASIN: {result.get('parent_asin')}")
    print(f"Title:       {result.get('title')}")
    print(f"Price:       {result.get('amazon_price')}")
    print(f"Rating:      {result.get('rating')}")
    print(f"Reviews:     {result.get('reviews_count')}")
    print(f"Available:   {result.get('is_available')}")


if __name__ == "__main__":
    asyncio.run(main())