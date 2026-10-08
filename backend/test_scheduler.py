# test_scheduler.py
import asyncio
import logging

# ✅ Logging ON karo — taake saare logs dikhein
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

from app.services.scheduler import run_price_update_now
from app.database import SessionLocal
from app.models import Product


async def test():
    # Pehle check karo kitne Active products hain
    db = SessionLocal()
    
    # ✅ Sirf Active products count karo (Draft skip)
    active_products = db.query(Product).filter(
        Product.is_available == True
    ).all()
    
    all_products = db.query(Product).all()
    
    print(f"Total products: {len(all_products)}")
    print(f"Active products: {len(active_products)}")
    print(f"Draft/Inactive: {len(all_products) - len(active_products)}")
    
    print("\n--- Active Products (first 5) ---")
    for p in active_products[:5]:
        print(
            f"ASIN: {p.asin}, "
            f"Amazon: ${p.amazon_price}, "
            f"Final: ${p.price}, "
            f"Available: {p.is_available}"
        )
    
    db.close()
    
    # Ab scheduler job chalao
    print("\n--- Running price update ---")
    await run_price_update_now()
    print("--- Done ---")


if __name__ == "__main__":
    asyncio.run(test())