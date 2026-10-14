# ============================================
# app/models/shopify_store.py
# Shopify store tokens database model
# + ✅ FIXED: access_token nullable=True (NULL allow karta hai)
# + ✅ NAYE COLUMNS — Expiring offline tokens ke liye
# + ✅ NAYE COLUMNS — Store default markup (v5)
# + ✅ NAYE COLUMNS — Store default country + tax (v6)
# ============================================

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,        # ✅ NAYA — country_id ke liye
    Numeric,        # decimal values ke liye
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
    # Ye markup har naye product par apply hoga
    default_markup = Column(Numeric(10, 2), nullable=True, default=2.00)
    default_markup_type = Column(String(20), nullable=True, default="fixed")
    default_extra_percent = Column(Numeric(10, 2), nullable=True, default=0.00)

    # ✅ NAYE COLUMNS — Store default country + tax (v6)
    # Ye country + tax har naye product par apply hoga
    default_country_id = Column(Integer, nullable=True)
    default_tax_rate = Column(Numeric(5, 2), nullable=True, default=0.00)

    def __repr__(self):
        return f"<ShopifyStore {self.shop_domain}>"