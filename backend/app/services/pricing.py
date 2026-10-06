"""
Pricing Service - Business Logic (SQLAlchemy version)
Yeh service pricing calculation handle karti hai
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional, List
from sqlalchemy import text
from app.database import SessionLocal


class PricingService:
    """Central pricing logic"""
    
    @staticmethod
    def calculate(
        amazon_price: float,
        markup_type: str,
        markup_value: float,
        tax_rate: float,
    ) -> Dict[str, float]:
        """
        Industry-standard calculation using Decimal (no float errors)
        """
        amazon = Decimal(str(amazon_price))
        markup = Decimal(str(markup_value))
        tax_pct = Decimal(str(tax_rate))
        
        if markup_type == "fixed":
            subtotal = amazon + markup
        else:  # percentage
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
        """Saari active countries"""
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
        """Ek product ki saari pricing"""
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
        """Ek product ka pricing update"""
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
                SELECT amazon_price FROM products WHERE id = :pid
            """), {"pid": product_id}).fetchone()
            
            if not product:
                raise ValueError("Product not found")
            
            # Calculate
            calc = cls.calculate(
                amazon_price=float(product[0] or 0),
                markup_type=markup_type,
                markup_value=markup_value,
                tax_rate=tax_rate,
            )
            
            # Upsert
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
            db.commit()
            
            return {
                "product_id": product_id,
                "country_id": country_id,
                "markup_type": markup_type,
                "markup_value": markup_value,
                "tax_rate": tax_rate,
                "tax_amount": calc["tax_amount"],
                "final_price": calc["final_price"],
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
    ) -> Dict:
        """Saare products par apply"""
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
            
            # Saare products
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
                updated += 1
            
            db.commit()
            return {"updated": updated}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


pricing_service = PricingService()