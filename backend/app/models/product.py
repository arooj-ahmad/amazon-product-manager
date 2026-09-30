# ============================================
# app/models/product.py
# Product model — Supabase ke "products" table se map
# ============================================

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    String,
    Text,
    func,
)

from app.database import Base


class Product(Base):
    """
    Amazon product ka SQLAlchemy model.
    Supabase table: products
    """

    __tablename__ = "products"

    # Primary Key
    id = Column(BigInteger, primary_key=True, index=True)

    # Amazon Identifiers
    asin = Column(String(20), unique=True, nullable=False, index=True)
    parent_asin = Column(String(20), nullable=True)
    is_variation = Column(Boolean, default=False, nullable=False)

    # Product Details
    title = Column(String(500), nullable=True)
    brand = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    image_url = Column(String(1000), nullable=True)
    images = Column(JSON, default=list)
    specifications = Column(JSON, default=dict)   # ← NEW

    # Pricing
    amazon_price = Column(Float, nullable=True)
    price = Column(Float, nullable=True)
    markup = Column(Float, default=2.0)

    # Manual Override
    is_manual_override = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self):
        return f"<Product id={self.id} asin={self.asin}>"