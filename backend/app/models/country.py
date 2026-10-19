"""
Country and ProductPricing SQLAlchemy Models
"""
from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, ForeignKey, UniqueConstraint, Index, CHAR
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Country(Base):
    __tablename__ = "countries"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    iso_code = Column(CHAR(2), unique=True, nullable=False, index=True)
    currency_code = Column(CHAR(3), nullable=False)
    currency_symbol = Column(String(10))
    default_tax_rate = Column(Numeric(5, 2), default=0)
    tax_label = Column(String(50), default="VAT")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship
    pricing = relationship("ProductPricing", back_populates="country")
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "iso_code": self.iso_code,
            "currency_code": self.currency_code,
            "currency_symbol": self.currency_symbol,
            "default_tax_rate": float(self.default_tax_rate or 0),
            "tax_label": self.tax_label,
            "is_active": self.is_active,
        }


class ProductPricing(Base):
    __tablename__ = "product_pricing"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, nullable=False, index=True)  # ⚠️ Agar product.id UUID hai toh String(36) karein
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False)
    markup_type = Column(String(20), default="fixed")
    markup_value = Column(Numeric(10, 2), default=2.00)
    tax_rate = Column(Numeric(5, 2), default=0)
    tax_amount = Column(Numeric(10, 2), default=0)
    final_price = Column(Numeric(10, 2), default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationship
    country = relationship("Country", back_populates="pricing")
    
    __table_args__ = (
        UniqueConstraint("product_id", "country_id", name="unique_product_country"),
    )
    
    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "country_id": self.country_id,
            "markup_type": self.markup_type,
            "markup_value": float(self.markup_value),
            "tax_rate": float(self.tax_rate),
            "tax_amount": float(self.tax_amount),
            "final_price": float(self.final_price),
        }