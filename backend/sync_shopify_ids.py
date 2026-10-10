# sync_shopify_ids.py
import sys
import os

# ✅ NAYA: PYTHONPATH fix — script ke folder ko add karo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import logging
from app.database import SessionLocal
from app.models import Product, ShopifyStore
from app.services.shopify import get_shopify_product_by_sku

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


async def sync_ids():
    db = SessionLocal()
    store = db.query(ShopifyStore).first()
    
    if not store or not store.access_token:
        print("❌ No Shopify store in DB")
        db.close()
        return
    
    shop = store.shop_domain
    access_token = store.access_token
    
    # ✅ Saare products jinke paas shopify_product_id nahi hai
    products = db.query(Product).filter(
        Product.shopify_product_id.is_(None),
        Product.asin.isnot(None),
    ).all()
    
    print(f"Total products without shopify_id: {len(products)}")
    
    synced = 0
    not_found = 0
    errors = 0
    
    for p in products:
        try:
            shopify_id = await get_shopify_product_by_sku(
                shop=shop,
                access_token=access_token,
                sku=p.asin,
            )
            
            if shopify_id:
                p.shopify_product_id = shopify_id
                db.commit()
                print(f"✅ {p.asin} → {shopify_id}")
                synced += 1
            else:
                print(f"⚠️ {p.asin} not found in Shopify (SKU check karo)")
                not_found += 1
            
            await asyncio.sleep(0.5)
        
        except Exception as e:
            print(f"❌ {p.asin}: {e}")
            errors += 1
    
    db.close()
    print(f"\n{'='*50}")
    print(f"✅ Synced: {synced}")
    print(f"⚠️ Not found: {not_found}")
    print(f"❌ Errors: {errors}")
    print(f"{'='*50}")
    print("Done!")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(sync_ids())