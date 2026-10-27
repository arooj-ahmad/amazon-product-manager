import sys
import json
from app.services.amazon import fetch_product_from_apify

def main():
    # Agar command line se URL diya hai to wo use karo, warna default PAWZ boots URL
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = "https://www.amazon.com/dp/B0H2G36YMB"

    print(f"\n🔍 Fetching from Apify: {url}\n" + "=" * 60)

    try:
        data = fetch_product_from_apify(url)
    except Exception as e:
        print(f"❌ Error during fetch: {e}")
        return

    if not data or not data.get("asin"):
        print("❌ Product data not found.")
        return

    print("✅ SUCCESS! Product Fetched:")
    print(f"   ASIN:         {data.get('asin')}")
    print(f"   Title:        {data.get('title')}")
    print(f"   Brand:        {data.get('brand')}")
    print(f"   Price:        ${data.get('amazon_price')}")
    print(f"   List Price:   ${data.get('list_price')}")
    print(f"   Available:    {data.get('is_available')} ({data.get('availability')})")
    print(f"   Total Images: {len(data.get('images', []))}")

    # Variations info
    variant_asins = data.get("variant_asins") or []
    variant_details = data.get("variant_details") or []

    print("\n" + "=" * 60)
    print(f"📦 VARIATIONS ({len(variant_asins)} unique ASINs discovered):")
    print("=" * 60)

    for i, asin in enumerate(variant_asins):
        vd = next((d for d in variant_details if d.get("asin") == asin), {})
        attrs = vd.get("attributes") or []
        attrs_str = ", ".join(f"{a['name']}={a['value']}" for a in attrs) if attrs else vd.get("name", "N/A")
        price_str = f"${vd.get('price')}" if vd.get("price") is not None else "(Inherits base price)"
        print(f"  {i+1:2d}. ASIN: {asin} | {attrs_str} | Price: {price_str}")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
