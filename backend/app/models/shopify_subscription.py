# ============================================
# app/models/shopify_subscription.py
# Shopify Billing subscriptions
# ============================================

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    String,
    func,
)

from app.database import Base


class ShopifySubscription(Base):
    """Shopify merchant subscriptions"""

    __tablename__ = "shopify_subscriptions"

    id = Column(BigInteger, primary_key=True, index=True)
    shop_domain = Column(String(255), unique=True, nullable=False, index=True)
    subscription_id = Column(String(255), nullable=True)
    subscription_status = Column(String(50), default="pending")
    plan_name = Column(String(100), nullable=True)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self):
        return f"<Subscription {self.shop_domain} - {self.subscription_status}>"