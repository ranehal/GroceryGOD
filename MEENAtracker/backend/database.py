from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from datetime import datetime

DATABASE_URL = "sqlite+aiosqlite:///./meenatracker.db"

Base = declarative_base()

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    url = Column(String, nullable=True)
    is_custom = Column(Boolean, default=False)
    products = relationship("Product", back_populates="category")

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True) # ID from Meena Bazar if available
    name = Column(String, index=True)
    unit = Column(String)
    unit_type = Column(String) # kg, ltr, piece
    image_url = Column(String)
    category_id = Column(Integer, ForeignKey("categories.id"))
    is_favorite = Column(Boolean, default=False)
    
    category = relationship("Category", back_populates="products")
    price_history = relationship("PriceHistory", back_populates="product")

class PriceHistory(Base):
    __tablename__ = "price_history"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    actual_price = Column(Float)
    unit_price = Column(Float)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    
    product = relationship("Product", back_populates="price_history")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
