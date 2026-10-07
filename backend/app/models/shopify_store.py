# ============================================
# app/models/shopify_store.py
# Shopify store tokens database model
# ============================================

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
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
    access_token = Column(Text, nullable=False)
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

    def __repr__(self):
        return f"<ShopifyStore {self.shop_domain}>"