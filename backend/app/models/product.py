# ============================================
# app/models/product.py
# Product model — Amazon product data
# + Out of Stock tracking
# + Variant attributes (Shopify options ke liye)
# + Shopify status tracking (active/draft)
# + ✅ NAYA: shopify_store_id (multi-store support)
# + ✅ NAYA: categories (Collections) + tags (Shopify tags)
# ============================================

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(BigInteger, primary_key=True, index=True)

    # ----------------------------------------
    # Amazon Identifiers
    # ----------------------------------------
    asin = Column(String(255), unique=True, nullable=False, index=True)
    parent_asin = Column(String(255), nullable=True)
    is_variation = Column(Boolean, default=False, nullable=False)

    # ----------------------------------------
    # Product Details
    # ----------------------------------------
    title = Column(String(500), nullable=True)
    brand = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    image_url = Column(String(1000), nullable=True)
    images = Column(JSON, default=list)
    specifications = Column(JSON, default=dict)
    rating = Column(Float, nullable=True)
    reviews_count = Column(BigInteger, nullable=True)

    # ----------------------------------------
    # ✅ NAYA: Collections + Tags
    # ----------------------------------------
    # Amazon categories — Shopify collections ke liye
    # Format: ["Books", "Romance", "Fantasy"]
    categories = Column(JSONB, default=list, nullable=False)

    # Amazon features/specs — Shopify tags ke liye
    # Format: ["Paperback: 366 pages", "Language: English", "Books"]
    tags = Column(JSONB, default=list, nullable=False)

    # ----------------------------------------
    # Stock Tracking
    # ----------------------------------------
    availability = Column(String(100), default="In Stock")
    is_available = Column(Boolean, default=True)
    stock_quantity = Column(Integer, default=0)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)

    # ----------------------------------------
    # Variant Attributes
    # Shopify options ke liye
    # Format: [{"name": "Size", "value": "Large"}, ...]
    # ----------------------------------------
    variant_attributes = Column(JSON, default=list)

    # ----------------------------------------
    # ✅ NAYA: Shopify Store Link (multi-store support)
    # Kis store ki product hai
    # ----------------------------------------
    shopify_store_id = Column(
        BigInteger,
        ForeignKey("shopify_stores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ----------------------------------------
    # Shopify Product ID (for updates)
    # ----------------------------------------
    shopify_product_id = Column(String(255), nullable=True)
    shopify_handle = Column(String(255), nullable=True)

    # ✅ Shopify status track karne ke liye
    # Values: "active" ya "draft"
    shopify_status = Column(String(20), default="draft", nullable=True)

    # ----------------------------------------
    # Pricing
    # ----------------------------------------
    amazon_price = Column(Float, nullable=True)
    price = Column(Float, nullable=True)
    markup = Column(Float, default=2.0)
    markup_type = Column(String(20), default="fixed")

    # ----------------------------------------
    # Manual Override
    # ----------------------------------------
    is_manual_override = Column(Boolean, default=False, nullable=False)

    # ----------------------------------------
    # Timestamps
    # ----------------------------------------
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self):
        return f"<Product id={self.id} asin={self.asin}>"