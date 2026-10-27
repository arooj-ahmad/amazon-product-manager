# backfill_skus.py
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal
from app.models import Product, ShopifyStore
from app.services.shopify import update_variant_with_tracked
from app.services.shopify.helpers import shopify_graphql


async def backfill_skus():
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
            if not product.asin:
                continue

            query = """
            query getVariants($id: ID!) {
              product(id: $id) {
                variants(first: 10) {
                  edges {
                    node {
                      id
                      inventoryItem { id sku }
                    }
                  }
                }
              }
            }
            """

            result = await shopify_graphql(
                store.shop_domain,
                store.access_token,
                query,
                {"id": product.shopify_product_id},
            )

            if "errors" in result:
                print(f"❌ {product.asin}: {result['errors']}")
                continue

            edges = (
                result.get("data", {})
                .get("product", {})
                .get("variants", {})
                .get("edges", [])
            )

            if not edges:
                continue

            for edge in edges:
                variant = edge["node"]
                variant_id = variant["id"]
                current_sku = variant.get("inventoryItem", {}).get("sku")

                if current_sku == product.asin:
                    print(f"✅ {product.asin}: SKU already set")
                    continue

                # SKU update karo
                success = await update_variant_with_tracked(
                    shop=store.shop_domain,
                    access_token=store.access_token,
                    product_id=product.shopify_product_id,
                    variant_id=variant_id,
                    price=product.price or 0,
                    sku=product.asin,
                )

                if success:
                    print(f"✅ {product.asin}: SKU updated")
                else:
                    print(f"❌ {product.asin}: Failed")

                await asyncio.sleep(0.5)

    finally:
        db.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(backfill_skus())