# debug_brightdata.py
# ✅ FIXED: PYTHONPATH + Windows event loop
import sys
import os

# ✅ NAYA: PYTHONPATH fix
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import logging
from app.services.brightdata import fetch_product_from_brightdata

# ✅ Logging ON karo
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def test():
    url = "https://www.amazon.com/dp/B0B2RM68G2"

    print("\n" + "=" * 60)
    print("FETCHING BRIGHT DATA...")
    print("=" * 60 + "\n")

    data = await fetch_product_from_brightdata(url)

    print("\n" + "=" * 60)
    print("PARSED DATA:")
    print("=" * 60)
    for key, value in data.items():
        if key in ["images", "specifications", "variations", "variant_attributes"]:
            print(f"{key}: [{len(value)} items]")
        else:
            print(f"{key}: {value}")
    print("=" * 60)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test())