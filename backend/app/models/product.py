# ============================================
# app/models/product.py
# Product model (SQLAlchemy)
# ============================================

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.sql import func

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    asin = Column(String(20), unique=True, index=True, nullable=False)
    parent_asin = Column(String(20), index=True, nullable=True)
    is_variation = Column(Boolean, default=False)

    title = Column(String(500))
    brand = Column(String(200))
    description = Column(Text)
    image_url = Column(String(1000))
    images = Column(JSON, default=list)
    specifications = Column(JSON, default=dict)

    amazon_price = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    markup = Column(Float, default=2.0, nullable=False)
    markup_type = Column(String(10), default="fixed", nullable=False)  # ✅ NAYA

    is_manual_override = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())