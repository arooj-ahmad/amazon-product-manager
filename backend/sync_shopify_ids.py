# ============================================
# sync_shopify_ids.py
# 2-in-1 script:
#   1. Shopify se saare products pull karo → DB mein save
#   2. Existing products ke shopify_product_id update karo
#
# ✅ FIXED: Sahi store selection + token check
# ✅ NAYA: Naye products bhi Shopify se pull karo
# ============================================

import sys
import os

# ✅ PYTHONPATH fix — script ke folder ko add karo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import logging
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import Product, ShopifyStore
from app.services.shopify import shopify_graphql
from app.services.brightdata import calculate_final_price

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================
# SHOPIFY SE SAARE PRODUCTS FETCH KARO
# ============================================
async def fetch_all_shopify_products(shop: str, access_token: str) -> list:
    """
    Shopify se saare active products fetch karo — paginated.
    """
    query = """
    query getProducts($cursor: String) {
      products(first: 50, after: $cursor, query: "status:active") {
        pageInfo {
          hasNextPage
          endCursor
        }
        edges {
          node {
            id
            title
            handle
            status
            vendor
            productType
            tags
            category {
              id
              name
              fullName
            }
            variants(first: 10) {
              edges {
                node {
                  id
                  title
                  sku
                  price
                  inventoryQuantity
                  selectedOptions {
                    name
                    value
                  }
                }
              }
            }
            images(first: 5) {
              edges {
                node {
                  url
                }
              }
            }
          }
        }
      }
    }
    """

    all_products = []
    cursor = None
    has_next = True

    while has_next:
        result = await shopify_graphql(
            shop, access_token, query, {"cursor": cursor}
        )

        if "errors" in result:
            logger.error(f"❌ Shopify error: {result['errors']}")
            break

        products_data = result.get("data", {}).get("products", {})
        edges = products_data.get("edges", [])
        page_info = products_data.get("pageInfo", {})

        for edge in edges:
            all_products.append(edge["node"])

        has_next = page_info.get("hasNextPage", False)
        cursor = page_info.get("endCursor")

    return all_products


# ============================================
# MAIN SYNC FUNCTION
# ============================================
async def sync_ids():
    """
    2 kaam:
    1. Shopify se products pull karo → DB mein save/update
    2. Existing products ke shopify_product_id update karo
    """
    db = SessionLocal()

    try:
        # ✅ Sahi store explicitly
        store = db.query(ShopifyStore).filter(
            ShopifyStore.shop_domain == "test-store-ispfraip.myshopify.com"
        ).first()

        if not store:
            store = db.query(ShopifyStore).order_by(
                ShopifyStore.installed_at.desc()
            ).first()  # Fallback — latest store

        if not store:
            print("❌ No Shopify store in DB")
            return

        if not store.access_token:
            print(f"❌ No access_token for store: {store.shop_domain}")
            print("   Please reinstall the app first.")
            return

        shop = store.shop_domain
        access_token = store.access_token

        print(f"✅ Using store: {shop}")
        print(f"✅ Token: {access_token[:15]}...")
        print(f"✅ Expires at: {store.expires_at}")
        print()

        # ═══════════════════════════════════════════
        # STEP 1: Shopify se saare products fetch karo
        # ═══════════════════════════════════════════
        print("=" * 60)
        print("STEP 1: Fetching products from Shopify...")
        print("=" * 60)

        shopify_products = await fetch_all_shopify_products(shop, access_token)
        print(f"📦 Found {len(shopify_products)} products in Shopify")
        print()

        # ═══════════════════════════════════════════
        # STEP 2: Har product ko DB mein save/update karo
        # ═══════════════════════════════════════════
        print("=" * 60)
        print("STEP 2: Saving to DB (add or update)...")
        print("=" * 60)

        added = 0
        updated = 0
        skipped = 0

        for sp in shopify_products:
            shopify_id = sp["id"]
            title = (sp.get("title") or "Untitled")[:500]
            handle = sp.get("handle")
            status = (sp.get("status") or "ACTIVE").lower()
            vendor = sp.get("vendor") or ""
            product_type = sp.get("productType") or ""
            tags = sp.get("tags") or []
            category = sp.get("category") or {}
            category_name = category.get("fullName") if category else None

            variants_edges = sp.get("variants", {}).get("edges", [])
            images_edges = sp.get("images", {}).get("edges", [])

            # Pehla variant se data
            sku = None
            price = None
            inventory = 0
            variant_attributes = []

            if variants_edges:
                first_variant = variants_edges[0]["node"]
                sku = first_variant.get("sku")
                price = first_variant.get("price")
                inventory = first_variant.get("inventoryQuantity", 0)

                variant_attributes = [
                    {"name": opt["name"], "value": opt["value"]}
                    for opt in first_variant.get("selectedOptions", [])
                    if opt.get("name") and opt.get("value")
                ]

            # SKU nahi to Shopify ID se banao
            if not sku:
                numeric_id = shopify_id.replace("gid://shopify/Product/", "")
                sku = f"SHOPIFY_{numeric_id}"
            else:
                sku = str(sku).strip()[:255]

            # Images
            image_urls = [
                img["node"]["url"]
                for img in images_edges
                if img.get("node", {}).get("url")
            ]

            price_float = None
            try:
                price_float = float(price) if price else None
            except (ValueError, TypeError):
                price_float = None

            # ✅ DB mein dhundho
            existing = db.query(Product).filter(Product.asin == sku).first()

            if existing:
                # ✅ UPDATE
                existing.shopify_product_id = shopify_id
                existing.shopify_handle = handle
                existing.shopify_status = status
                existing.shopify_store_id = store.id

                if not existing.title:
                    existing.title = title
                if not existing.brand:
                    existing.brand = vendor

                existing.tags = tags
                existing.categories = [category_name] if category_name else []
                existing.variant_attributes = variant_attributes

                if image_urls:
                    existing.images = image_urls
                    if not existing.image_url:
                        existing.image_url = image_urls[0]

                if price_float:
                    existing.amazon_price = price_float
                    existing.price = calculate_final_price(
                        amazon_price=price_float,
                        markup=existing.markup or 2.0,
                        markup_type=existing.markup_type or "fixed",
                    )

                existing.stock_quantity = inventory
                existing.last_synced_at = datetime.now(timezone.utc)

                updated += 1
                print(f"🔄 Updated: {sku} → {title[:50]}")
            else:
                # ✅ ADD
                final_price = calculate_final_price(
                    amazon_price=price_float,
                    markup=2.0,
                    markup_type="fixed",
                )

                new_product = Product(
                    asin=sku,
                    title=title,
                    brand=vendor,
                    shopify_product_id=shopify_id,
                    shopify_handle=handle,
                    shopify_status=status,
                    shopify_store_id=store.id,
                    amazon_price=price_float,
                    price=final_price,
                    is_available=True,
                    stock_quantity=inventory,
                    tags=tags,
                    categories=[category_name] if category_name else [],
                    variant_attributes=variant_attributes,
                    images=image_urls,
                    image_url=image_urls[0] if image_urls else None,
                    last_synced_at=datetime.now(timezone.utc),
                )
                db.add(new_product)
                added += 1
                print(f"➕ Added: {sku} → {title[:50]}")

        db.commit()

        # ═══════════════════════════════════════════
        # STEP 3: Purane products ke shopify_product_id update karo
        # ═══════════════════════════════════════════
        print()
        print("=" * 60)
        print("STEP 3: Updating missing shopify_product_id...")
        print("=" * 60)

        missing_products = db.query(Product).filter(
            Product.shopify_product_id.is_(None),
            Product.asin.isnot(None),
        ).all()

        if missing_products:
            print(f"Found {len(missing_products)} products without shopify_id")

            # Shopify ID lookup build karo
            shopify_lookup = {}
            for sp in shopify_products:
                for edge in sp.get("variants", {}).get("edges", []):
                    sku = edge["node"].get("sku")
                    if sku:
                        shopify_lookup[str(sku).strip()] = sp["id"]

            fixed_ids = 0
            for p in missing_products:
                if p.asin in shopify_lookup:
                    p.shopify_product_id = shopify_lookup[p.asin]
                    fixed_ids += 1
                    print(f"  ✅ {p.asin} → {shopify_lookup[p.asin]}")

            db.commit()
            print(f"✅ Fixed {fixed_ids} product IDs")
        else:
            print("✅ All products have shopify_product_id")

        # ═══════════════════════════════════════════
        # SUMMARY
        # ═══════════════════════════════════════════
        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"📦 Shopify products found: {len(shopify_products)}")
        print(f"➕ Added to DB: {added}")
        print(f"🔄 Updated in DB: {updated}")
        print(f"⏭️ Skipped: {skipped}")
        print("=" * 60)
        print("✅ Done!")

    finally:
        db.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(sync_ids())