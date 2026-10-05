import asyncio
import json
from app.services.brightdata import fetch_product_from_brightdata


async def main():
    # ✅ Real variations wala product — Gildan T-Shirt
    url = "https://www.amazon.com/dp/B0787P86ZZ"

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

    # ✅ FIX: variations list — name/value format
    variations = result.get("variations", [])
    print(f"\nTotal variations found: {len(variations)}")
    for v in variations:
        print(f"  • {v.get('name')} = {v.get('value')}")

    # ✅ NAYA: variant_attributes bhi check karo
    variant_attrs = result.get("variant_attributes", [])
    print(f"\nTotal variant attributes: {len(variant_attrs)}")
    for attr in variant_attrs:
        print(f"  • {attr.get('name')} = {attr.get('value')}")


if __name__ == "__main__":
    asyncio.run(main())