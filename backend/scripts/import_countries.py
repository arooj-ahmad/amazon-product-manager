"""
Country import script - SQLAlchemy version
Ek dafa chalana hai
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import logging
from typing import List, Dict
from sqlalchemy import text
from app.database import SessionLocal
from app.config import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

TAX_RATES = {
    "US": (0, "Sales Tax"), "GB": (20, "VAT"), "AE": (5, "VAT"),
    "SA": (15, "VAT"), "PK": (18, "GST"), "IN": (18, "GST"),
    "BD": (15, "VAT"), "LK": (18, "VAT"), "NP": (13, "VAT"),
    "DE": (19, "VAT"), "FR": (20, "VAT"), "IT": (22, "VAT"),
    "ES": (21, "VAT"), "NL": (21, "VAT"), "BE": (21, "VAT"),
    "AT": (20, "VAT"), "PT": (23, "VAT"), "IE": (23, "VAT"),
    "GR": (24, "VAT"), "FI": (24, "VAT"), "SE": (25, "VAT"),
    "DK": (25, "VAT"), "NO": (25, "VAT"), "CH": (8.1, "VAT"),
    "PL": (23, "VAT"), "CZ": (21, "VAT"), "HU": (27, "VAT"),
    "RO": (19, "VAT"), "TR": (20, "KDV"), "RU": (20, "NDS"),
    "UA": (20, "PDV"), "CA": (5, "GST"), "MX": (16, "IVA"),
    "BR": (17, "ICMS"), "AR": (21, "IVA"), "CL": (19, "IVA"),
    "CO": (19, "IVA"), "PE": (18, "IGV"), "AU": (10, "GST"),
    "NZ": (15, "GST"), "JP": (10, "Consumption Tax"), "CN": (13, "VAT"),
    "KR": (10, "VAT"), "SG": (9, "GST"), "MY": (8, "SST"),
    "TH": (7, "VAT"), "ID": (11, "PPN"), "VN": (10, "VAT"),
    "PH": (12, "VAT"), "ZA": (15, "VAT"), "NG": (7.5, "VAT"),
    "KE": (16, "VAT"), "EG": (14, "VAT"), "MA": (20, "TVA"),
    "IL": (17, "VAT"), "QA": (0, "No VAT"), "KW": (0, "No VAT"),
    "BH": (10, "VAT"), "OM": (5, "VAT"), "JO": (16, "GST"),
}

CURRENCY_SYMBOLS = {
    "USD": "$", "GBP": "£", "EUR": "€", "PKR": "₨", "INR": "₹",
    "AED": "د.إ", "SAR": "﷼", "JPY": "¥", "CNY": "¥", "KRW": "₩",
    "CAD": "C$", "AUD": "A$", "NZD": "NZ$", "CHF": "CHF",
    "SEK": "kr", "NOK": "kr", "DKK": "kr", "PLN": "zł", "CZK": "Kč",
    "HUF": "Ft", "RON": "lei", "TRY": "₺", "RUB": "₽", "UAH": "₴",
    "BRL": "R$", "MXN": "Mex$", "SGD": "S$", "MYR": "RM",
    "THB": "฿", "IDR": "Rp", "VND": "₫", "PHP": "₱", "ZAR": "R",
    "NGN": "₦", "KES": "KSh", "EGP": "E£", "MAD": "DH", "ILS": "₪",
    "QAR": "﷼", "KWD": "د.ك", "BHD": ".د.ب", "OMR": "﷼", "JOD": "د.ا",
    "BDT": "৳", "LKR": "Rs", "NPR": "Rs",
}


def fetch_countries() -> List[Dict]:
    """countrystatecity.in se countries fetch karein"""
    # ✅ FIX: settings.COUNTRY_STATE_CITY_API_KEY use karein (uppercase)
    api_key = settings.COUNTRY_STATE_CITY_API_KEY
    
    if not api_key:
        raise ValueError("COUNTRY_STATE_CITY_API_KEY missing in .env")
    
    logger.info("🌍 Fetching countries from countrystatecity.in...")
    r = requests.get(
        "https://api.countrystatecity.in/v1/countries",
        headers={"X-CSCAPI-KEY": api_key},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    logger.info(f"✅ Got {len(data)} countries")
    return data


def import_all():
    try:
        data = fetch_countries()
    except Exception as e:
        logger.error(f"❌ Failed to fetch: {e}")
        return
    
    db = SessionLocal()
    imported = 0
    errors = 0
    
    try:
        for raw in data:
            iso = raw.get("iso2", "").upper()
            if not iso:
                continue
            
            curr_code = (raw.get("currency") or "USD").upper()
            curr_symbol = CURRENCY_SYMBOLS.get(curr_code, curr_code)
            tax_rate, tax_label = TAX_RATES.get(iso, (0, "VAT"))
            
            try:
                # Raw SQL upsert (PostgreSQL ON CONFLICT)
                db.execute(text("""
                    INSERT INTO countries 
                        (name, iso_code, currency_code, currency_symbol, 
                         default_tax_rate, tax_label, is_active)
                    VALUES 
                        (:name, :iso, :curr_code, :curr_symbol, 
                         :tax_rate, :tax_label, TRUE)
                    ON CONFLICT (iso_code) 
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        currency_code = EXCLUDED.currency_code,
                        currency_symbol = EXCLUDED.currency_symbol,
                        default_tax_rate = EXCLUDED.default_tax_rate,
                        tax_label = EXCLUDED.tax_label
                """), {
                    "name": raw.get("name", ""),
                    "iso": iso,
                    "curr_code": curr_code,
                    "curr_symbol": curr_symbol,
                    "tax_rate": tax_rate,
                    "tax_label": tax_label,
                })
                imported += 1
                
                if imported % 50 == 0:
                    db.commit()
                    logger.info(f"   ... {imported} imported")
                    
            except Exception as e:
                logger.warning(f"⚠️ {raw.get('name')}: {e}")
                db.rollback()
                errors += 1
        
        db.commit()
    finally:
        db.close()
    
    logger.info(f"\n🎉 Import Complete!")
    logger.info(f"   ✅ Imported: {imported}")
    logger.info(f"   ❌ Errors: {errors}")


if __name__ == "__main__":
    import_all()