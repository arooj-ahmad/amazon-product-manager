"""
Pricing Service - Business Logic (SQLAlchemy version)
+ Shopify real-time sync (handled by routes — async)
+ ✅ NAYA: "both" markup type (Fixed + Percent)
+ ✅ NAYA: extra_percent support
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
    def calculate(amazon_price, markup_type, markup_value, tax_rate, extra_percent=0):
        """
        Calculate final price.
        
        Types:
        - fixed:    amazon + markup
        - percent:  amazon * (1 + markup/100)
        - both:     (amazon + markup) * (1 + extra_percent/100)
        """
        amazon = Decimal(str(amazon_price or 0))
        markup = Decimal(str(markup_value or 0))
        tax_pct = Decimal(str(tax_rate or 0))
        extra_pct = Decimal(str(extra_percent or 0))
        
        if markup_type == "fixed":
            subtotal = amazon + markup
        elif markup_type == "percent":
            subtotal = amazon * (Decimal("1") + markup / Decimal("100"))
        elif markup_type == "both":
            # ✅ Fixed add karo, phir percent apply
            base = amazon + markup
            subtotal = base * (Decimal("1") + extra_pct / Decimal("100"))
        else:
            subtotal = amazon + markup
        
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
        extra_percent=0.0,   # ✅ NAYA
    ) -> Dict:
        """Ek product ka pricing update (Shopify sync routes se hoga)"""
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
            
            # Product fetch
            product = db.execute(text("""
                SELECT amazon_price, shopify_product_id 
                FROM products WHERE id = :pid
            """), {"pid": product_id}).fetchone()
            
            if not product:
                raise ValueError("Product not found")
            
            amazon_price = float(product[0] or 0)
            shopify_product_id = product[1]
            
            # Calculate (with extra_percent)
            calc = cls.calculate(
                amazon_price=amazon_price,
                markup_type=markup_type,
                markup_value=markup_value,
                tax_rate=tax_rate,
                extra_percent=extra_percent,   # ✅ NAYA
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
            
            # ✅ Products table update (markup, markup_type, extra_percent, price)
            db.execute(text("""
                UPDATE products 
                SET price = :fprice,
                    markup = :mval,
                    markup_type = :mtype,
                    extra_percent = :epercent
                WHERE id = :pid
            """), {
                "pid": product_id,
                "fprice": calc["final_price"],
                "mval": markup_value,
                "mtype": markup_type,
                "epercent": extra_percent,
            })
            
            db.commit()
            
            return {
                "product_id": product_id,
                "country_id": country_id,
                "markup_type": markup_type,
                "markup_value": markup_value,
                "extra_percent": extra_percent,   # ✅ NAYA
                "tax_rate": tax_rate,
                "tax_amount": calc["tax_amount"],
                "final_price": calc["final_price"],
                "shopify_product_id": shopify_product_id,   # ✅ Route ko pass karo
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    
    @classmethod
    def bulk_update(
        cls,
        country_id,
        markup_type,
        markup_value,
        tax_rate=None,
        extra_percent=0.0,   # ✅ NAYA
    ):
        """Saare products par apply (Shopify sync routes se hoga)"""
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
                    extra_percent=extra_percent,   # ✅ NAYA
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
                
                # ✅ Products table update
                db.execute(text("""
                    UPDATE products 
                    SET price = :fprice,
                        markup = :mval,
                        markup_type = :mtype,
                        extra_percent = :epercent
                    WHERE id = :pid
                """), {
                    "pid": p[0],
                    "fprice": calc["final_price"],
                    "mval": markup_value,
                    "mtype": markup_type,
                    "epercent": extra_percent,
                })
                
                updated += 1
            
            db.commit()
            return {"updated": updated}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


pricing_service = PricingService()