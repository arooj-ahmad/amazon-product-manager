# backfill_publishing.py
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal
from app.models import Product, ShopifyStore
from app.services.shopify import publish_product_to_channels


async def backfill_publishing():
    db = SessionLocal()
    try:
        store = db.query(ShopifyStore).filter(
            ShopifyStore.shop_domain == "test-store-ispfraip.myshopify.com"
        ).first()

        if not store:
            print("❌ No store")
            return

        products = db.query(Product).filter(
            Product.shopify_product_id.isnot(None)
        ).all()

        print(f"📦 Found {len(products)} products")

        for product in products:
            if not product.shopify_product_id:
                continue

            success = await publish_product_to_channels(
                shop=store.shop_domain,
                access_token=store.access_token,
                shopify_product_id=product.shopify_product_id,
            )

            if success:
                print(f"✅ {product.asin}: published")
            else:
                print(f"❌ {product.asin}: failed")

            await asyncio.sleep(0.5)

    finally:
        db.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(backfill_publishing())