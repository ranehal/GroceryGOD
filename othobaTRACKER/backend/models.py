from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import datetime

Base = declarative_base()

class Product(Base):
    __tablename__ = "products"
    
    id = Column(String, primary_key=True) # dl-product-id
    name = Column(String)
    sku = Column(String) # dl-product-sku
    vendor_name = Column(String)
    category_name = Column(String, index=True)
    image_url = Column(String)
    
    # Unit parsing fields
    extracted_unit_type = Column(String) # 'kg', 'L', 'piece', etc.
    extracted_unit_value = Column(Float) # The numeric value in standard units
    
    history = relationship("PriceHistory", back_populates="product")

class PriceHistory(Base):
    __tablename__ = "price_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String, ForeignKey("products.id"), index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    price_amount = Column(Float)
    is_out_of_stock = Column(Boolean, default=False)
    
    product = relationship("Product", back_populates="history")
