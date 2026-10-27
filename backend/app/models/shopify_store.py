# ============================================
# app/models/shopify_store.py
# Shopify store tokens database model
# + ✅ FIXED: access_token nullable=True (NULL allow karta hai)
# + ✅ NAYE COLUMNS — Expiring offline tokens ke liye
# + ✅ NAYE COLUMNS — Store default markup (v5)
# + ✅ NAYE COLUMNS — Store default country + tax (v6)
# + ✅ NAYE COLUMNS — Store default compare-at price (v7)
# + ✅ NAYE COLUMNS — Store default compare-at RULE (v8)
# + ✅ FIXED: default_markup default=None (no hidden $2.00)
# + ✅ FIXED: default_compare_at_value default=0.00
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

from app.core.database import Base


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

    # ============================================
    # ✅ FIXED: Store default markup (v5)
    # ============================================
    # ⚠️ Default None rakha gaya hai. Iska matlab:
    # Agar user ne store settings mein markup nahi set kiya,
    # toh `_resolve_markup` 400 Error dega. Isse user force 
    # hoga ke woh explicitly markup set kare, hidden $2.00 nahi lagega.
    default_markup = Column(Numeric(10, 2), nullable=True)
    default_markup_type = Column(String(20), nullable=True)
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
    # ✅ FIXED: Default value 30 ki jagah 0 (taake `none` rule ke sath misleading na ho)
    default_compare_at_value = Column(
        Numeric(10, 2), nullable=True, default=0.00
    )

    # ============================================
    # ✅ NAYA (v8): COMPARE AT RULE — frontend uses this
    # ============================================
    # Values: "none" | "amazon" | "fixed" | "percent"
    # Yeh frontend ke `rule_type` se match karta hai
    default_compare_at_rule = Column(
        String(20), nullable=True, default="none"
    )

    def __repr__(self):
        return f"<ShopifyStore {self.shop_domain}>"