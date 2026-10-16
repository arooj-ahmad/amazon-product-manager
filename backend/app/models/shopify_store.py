# ============================================
# app/models/shopify_store.py
# Shopify store tokens database model
# + ✅ FIXED: access_token nullable=True (NULL allow karta hai)
# + ✅ NAYE COLUMNS — Expiring offline tokens ke liye
# + ✅ NAYE COLUMNS — Store default markup (v5)
# + ✅ NAYE COLUMNS — Store default country + tax (v6)
# + ✅ NAYE COLUMNS — Store default compare-at price (v7)
# + ✅ NAYE COLUMNS — Store default compare-at RULE (v8)
# ============================================

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    func,
)

from app.database import Base


class ShopifyStore(Base):
    """Shopify store access tokens"""

    __tablename__ = "shopify_stores"

    id = Column(BigInteger, primary_key=True, index=True)
    shop_domain = Column(String(255), unique=True, nullable=False, index=True)

    # ✅ FIXED: nullable=True — SQL se token clear kar sakte ho
    access_token = Column(Text, nullable=True)

    scopes = Column(Text, nullable=True)
    installed_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ✅ NAYE COLUMNS — Expiring offline tokens ke liye
    refresh_token = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    refresh_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # ✅ NAYE COLUMNS — Store default markup (v5)
    default_markup = Column(Numeric(10, 2), nullable=True, default=2.00)
    default_markup_type = Column(String(20), nullable=True, default="fixed")
    default_extra_percent = Column(Numeric(10, 2), nullable=True, default=0.00)

    # ✅ NAYE COLUMNS — Store default country + tax (v6)
    default_country_id = Column(Integer, nullable=True)
    default_tax_rate = Column(Numeric(5, 2), nullable=True, default=0.00)

    # ============================================
    # ✅ NAYE COLUMNS — Compare At Price (v7)
    # ============================================
    # Agar enable = False → compare at price set NAHI hoga
    default_compare_at_enabled = Column(
        Boolean, nullable=True, default=False
    )
    # Type: "percent" | "fixed" | "amazon" | "none"
    # percent → final_price × (1 + value/100)
    # fixed   → final_price + value
    # amazon  → compare = amazon_price (from metafield)
    # none    → not set
    default_compare_at_type = Column(
        String(20), nullable=True, default="percent"
    )
    default_compare_at_value = Column(
        Numeric(10, 2), nullable=True, default=30.00
    )

    # ============================================
    # ✅ NAYA (v8): COMPARE AT RULE — frontend uses this
    # ============================================
    # Values: "none" | "amazon" | "fixed" | "percent"
    # Yeh frontend ke `rule_type` se match karta hai
    #
    # Rule → type + value mapping:
    #   "none"     → enabled=False, type="none",    value=0
    #   "amazon"   → enabled=True,  type="amazon",  value=0
    #   "fixed"    → enabled=True,  type="fixed",   value=fixed_amount
    #   "percent"  → enabled=True,  type="percent", value=percent
    default_compare_at_rule = Column(
        String(20), nullable=True, default="none"
    )

    def __repr__(self):
        return f"<ShopifyStore {self.shop_domain}>"