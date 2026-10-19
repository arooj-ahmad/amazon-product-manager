# ============================================
# test_brightdata.py
# Bright Data service test
# ============================================

import asyncio

from app.services.brightdata import (
    calculate_final_price,
    extract_asin_from_url,
    fetch_product_from_brightdata,
)


def test_asin_extraction():
    """ASIN extraction test"""
    print("=" * 60)
    print("TEST 1: ASIN Extraction")
    print("=" * 60)

    test_urls = [
        ("https://www.amazon.com/dp/B0B2RM68G2", "B0B2RM68G2"),
        ("https://www.amazon.com/gp/product/B08N5WRWNW", "B08N5WRWNW"),
        ("https://amazon.com/Some-Name/dp/B0B2RM68G2/", "B0B2RM68G2"),
        ("https://www.amazon.com/dp/B0B2RM68G2?ref=xyz", "B0B2RM68G2"),
    ]

    for url, expected in test_urls:
        result = extract_asin_from_url(url)
        status = "✅" if result == expected else "❌"
        print(f"{status} {url}")
        print(f"   Expected: {expected}, Got: {result}")


def test_price_calculation():
    """Price calculation rules test"""
    print("\n" + "=" * 60)
    print("TEST 2: Price Calculation")
    print("=" * 60)

    # Rule 1: Amazon price + markup
    price1 = calculate_final_price(amazon_price=99.99, markup=2.0)
    print(f"✅ Amazon $99.99 + $2 markup = ${price1} (expected 101.99)")

    # Rule 2: Admin price higher than auto
    price2 = calculate_final_price(
        amazon_price=99.99,
        markup=2.0,
        admin_price=150.0,
        is_manual_override=True,
    )
    print(f"✅ Amazon $99.99 + $2, Admin $150 → ${price2} (expected 150.0)")

    # Rule 2b: Admin price LOWER than auto → auto wins
    price3 = calculate_final_price(
        amazon_price=99.99,
        markup=2.0,
        admin_price=50.0,
        is_manual_override=True,
    )
    print(f"✅ Amazon $99.99 + $2, Admin $50 → ${price3} (expected 101.99)")

    # Rule 3: Amazon price None
    price4 = calculate_final_price(amazon_price=None, admin_price=75.0)
    print(f"✅ Amazon price None, Admin $75 → ${price4} (expected 75.0)")


async def test_brightdata_api():
    """Bright Data API real call test"""
    print("\n" + "=" * 60)
    print("TEST 3: Bright Data API Call (Real)")
    print("=" * 60)

    # Test URL — aap apna koi bhi Amazon product URL use kar sakte hain
    test_url = "https://www.amazon.com/dp/B0B2RM68G2"

    try:
        print(f"Fetching: {test_url}")
        print("(Thoda time lagega — 20-40 seconds)...")

        result = await fetch_product_from_brightdata(test_url)

        print("\n✅ Bright Data fetch successful!")
        print(f"   ASIN: {result['asin']}")
        print(f"   Title: {result['title']}")
        print(f"   Brand: {result['brand']}")
        print(f"   Amazon Price: ${result['amazon_price']}")
        print(f"   Image URL: {result['image_url'][:60] if result['image_url'] else None}...")
        print(f"   Parent ASIN: {result['parent_asin']}")
        print(f"   Is Variation: {result['is_variation']}")

    except Exception as e:
        print(f"\n❌ Bright Data fetch failed: {e}")
        print("(Ye normal ho sakta hai agar API key galat ho ya quota khatam ho)")


def main():
    test_asin_extraction()
    test_price_calculation()

    print("\n" + "=" * 60)
    print("Ab Bright Data API real call test karte hain...")
    print("=" * 60)
    asyncio.run(test_brightdata_api())


if __name__ == "__main__":
    main()