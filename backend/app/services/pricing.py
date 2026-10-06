"""
Pricing Service - Business Logic (SQLAlchemy version)
+ Shopify real-time sync (SYNC — no asyncio)
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional, List
from sqlalchemy import text
from app.database import SessionLocal
import logging

logger = logging.getLogger(__name__)


class PricingService:
    """Central pricing logic"""
    
    @staticmethod
    def calculate(amazon_price, markup_type, markup_value, tax_rate):
        amazon = Decimal(str(amazon_price))
        markup = Decimal(str(markup_value))
        tax_pct = Decimal(str(tax_rate))
        
        if markup_type == "fixed":
            subtotal = amazon + markup
        else:
            subtotal = amazon * (Decimal("1") + markup / Decimal("100"))
        
        tax_amount = subtotal * (tax_pct / Decimal("100"))
        
        subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tax_amount = tax_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        final_price = (subtotal + tax_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        return {
            "subtotal": float(subtotal),
            "tax_amount": float(tax_amount),
            "final_price": float(final_price),
        }
    
    @classmethod
    def get_all_countries(cls) -> List[Dict]:
        db = SessionLocal()
        try:
            result = db.execute(text("""
                SELECT id, name, iso_code, currency_code, currency_symbol,
                       default_tax_rate, tax_label, is_active
                FROM countries
                WHERE is_active = TRUE
                ORDER BY name
            """))
            rows = result.fetchall()
            return [
                {
                    "id": r[0],
                    "name": r[1],
                    "iso_code": r[2],
                    "currency_code": r[3],
                    "currency_symbol": r[4],
                    "default_tax_rate": float(r[5] or 0),
                    "tax_label": r[6],
                    "is_active": r[7],
                }
                for r in rows
            ]
        finally:
            db.close()
    
    @classmethod
    def get_pricing_for_product(cls, product_id) -> List[Dict]:
        db = SessionLocal()
        try:
            result = db.execute(text("""
                SELECT pp.*, c.name as country_name, c.iso_code, 
                       c.currency_code, c.currency_symbol
                FROM product_pricing pp
                JOIN countries c ON c.id = pp.country_id
                WHERE pp.product_id = :pid
            """), {"pid": product_id})
            rows = result.fetchall()
            return [dict(r._mapping) for r in rows]
        finally:
            db.close()
    
    @classmethod
    def update_single(
        cls,
        product_id,
        country_id,
        markup_type,
        markup_value,
        tax_rate=None,
    ) -> Dict:
        """Ek product ka pricing update + Shopify sync (synchronous)"""
        db = SessionLocal()
        try:
            # Country fetch
            country = db.execute(text("""
                SELECT default_tax_rate FROM countries WHERE id = :cid
            """), {"cid": country_id}).fetchone()
            
            if not country:
                raise ValueError("Country not found")
            
            if tax_rate is None:
                tax_rate = float(country[0] or 0)
            
            # Product fetch (WITH shopify_product_id)
            product = db.execute(text("""
                SELECT amazon_price, shopify_product_id 
                FROM products WHERE id = :pid
            """), {"pid": product_id}).fetchone()
            
            if not product:
                raise ValueError("Product not found")
            
            amazon_price = float(product[0] or 0)
            shopify_product_id = product[1]
            
            # Calculate
            calc = cls.calculate(
                amazon_price=amazon_price,
                markup_type=markup_type,
                markup_value=markup_value,
                tax_rate=tax_rate,
            )
            
            # Upsert product_pricing
            db.execute(text("""
                INSERT INTO product_pricing 
                    (product_id, country_id, markup_type, markup_value,
                     tax_rate, tax_amount, final_price, updated_at)
                VALUES 
                    (:pid, :cid, :mtype, :mval, :trate, :tamt, :fprice, NOW())
                ON CONFLICT (product_id, country_id) 
                DO UPDATE SET
                    markup_type = EXCLUDED.markup_type,
                    markup_value = EXCLUDED.markup_value,
                    tax_rate = EXCLUDED.tax_rate,
                    tax_amount = EXCLUDED.tax_amount,
                    final_price = EXCLUDED.final_price,
                    updated_at = NOW()
            """), {
                "pid": product_id,
                "cid": country_id,
                "mtype": markup_type,
                "mval": markup_value,
                "trate": tax_rate,
                "tamt": calc["tax_amount"],
                "fprice": calc["final_price"],
            })
            
            # ✅ Products table mein bhi final price update
            db.execute(text("""
                UPDATE products 
                SET price = :fprice 
                WHERE id = :pid
            """), {
                "pid": product_id,
                "fprice": calc["final_price"],
            })
            
            db.commit()
            
            # ✅ SHOPIFY SYNC (synchronous — no asyncio)
            shopify_synced = False
            
            if shopify_product_id:
                try:
                    # Access token fetch from shopify_store
                    store = db.execute(text("""
                        SELECT shop_domain, access_token 
                        FROM shopify_store 
                        LIMIT 1
                    """)).fetchone()
                    
                    if store and store[0] and store[1]:
                        from app.services.shopify import sync_update_shopify_price
                        
                        shopify_synced = sync_update_shopify_price(
                            shop_domain=store[0],
                            access_token=store[1],
                            shopify_product_id=shopify_product_id,
                            new_price=calc["final_price"],
                        )
                        
                        if shopify_synced:
                            logger.info(f"✅ Shopify synced: ${calc['final_price']}")
                        else:
                            logger.warning("⚠️ Shopify sync failed (DB saved)")
                    else:
                        logger.warning("⚠️ No Shopify store connected")
                except Exception as e:
                    logger.error(f"❌ Shopify sync error: {e}")
                    # DB save already ho gaya, sirf sync fail hua
            
            return {
                "product_id": product_id,
                "country_id": country_id,
                "markup_type": markup_type,
                "markup_value": markup_value,
                "tax_rate": tax_rate,
                "tax_amount": calc["tax_amount"],
                "final_price": calc["final_price"],
                "shopify_synced": shopify_synced,
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    
    @classmethod
    def bulk_update(cls, country_id, markup_type, markup_value, tax_rate=None):
        """Saare products par apply (Shopify sync skipped — bulk ke liye)"""
        db = SessionLocal()
        try:
            country = db.execute(text("""
                SELECT default_tax_rate FROM countries WHERE id = :cid
            """), {"cid": country_id}).fetchone()
            
            if not country:
                raise ValueError("Country not found")
            
            if tax_rate is None:
                tax_rate = float(country[0] or 0)
            
            products = db.execute(text("""
                SELECT id, amazon_price FROM products
            """)).fetchall()
            
            if not products:
                return {"updated": 0}
            
            updated = 0
            for p in products:
                calc = cls.calculate(
                    amazon_price=float(p[1] or 0),
                    markup_type=markup_type,
                    markup_value=markup_value,
                    tax_rate=tax_rate,
                )
                
                db.execute(text("""
                    INSERT INTO product_pricing 
                        (product_id, country_id, markup_type, markup_value,
                         tax_rate, tax_amount, final_price, updated_at)
                    VALUES 
                        (:pid, :cid, :mtype, :mval, :trate, :tamt, :fprice, NOW())
                    ON CONFLICT (product_id, country_id) 
                    DO UPDATE SET
                        markup_type = EXCLUDED.markup_type,
                        markup_value = EXCLUDED.markup_value,
                        tax_rate = EXCLUDED.tax_rate,
                        tax_amount = EXCLUDED.tax_amount,
                        final_price = EXCLUDED.final_price,
                        updated_at = NOW()
                """), {
                    "pid": p[0],
                    "cid": country_id,
                    "mtype": markup_type,
                    "mval": markup_value,
                    "trate": tax_rate,
                    "tamt": calc["tax_amount"],
                    "fprice": calc["final_price"],
                })
                
                # ✅ Product price bhi update
                db.execute(text("""
                    UPDATE products SET price = :fprice WHERE id = :pid
                """), {"pid": p[0], "fprice": calc["final_price"]})
                
                updated += 1
            
            db.commit()
            return {"updated": updated}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


pricing_service = PricingService()