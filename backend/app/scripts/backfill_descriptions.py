# backfill_descriptions.py
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal
from app.models import Product, ShopifyStore
from app.services.shopify import _build_description_with_metafields
from app.services.shopify.helpers import shopify_graphql


async def backfill_descriptions():
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

            # Product data dict banao
            product_data = {
                "description": product.description or "",
                "rating": product.rating,
                "amazon_price": product.amazon_price,
                "asin": product.asin,
                "reviews_count": product.reviews_count,
                "availability": product.availability,
            }

            description_html = _build_description_with_metafields(product_data)

            # Shopify update
            mutation = """
            mutation productUpdate($input: ProductInput!) {
              productUpdate(input: $input) {
                product { id title }
                userErrors { field message }
              }
            }
            """

            result = await shopify_graphql(
                store.shop_domain,
                store.access_token,
                mutation,
                {"input": {"id": product.shopify_product_id, "descriptionHtml": description_html}},
            )

            if "errors" in result:
                print(f"❌ {product.asin}: {result['errors']}")
            else:
                print(f"✅ {product.asin}: description updated")

            await asyncio.sleep(0.5)

    finally:
        db.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(backfill_descriptions())