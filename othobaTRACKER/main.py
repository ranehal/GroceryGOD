from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
import models
from database import SessionLocal, init_db
import uvicorn

app = FastAPI(title="Othoba Price Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/categories")
def get_categories(db: Session = Depends(get_db)):
    print(f"[DEBUG] Fetching categories...")
    try:
        counts = db.query(
            models.Product.category_name, 
            func.count(models.Product.id)
        ).group_by(models.Product.category_name).all()
        
        print(f"[DEBUG] Found {len(counts)} categories.")
        return [
            {"name": str(c[0]), "count": int(c[1])} 
            for c in counts if c[0]
        ]
    except Exception as e:
        print(f"[ERROR] Failed to fetch categories: {e}")
        raise e

@app.get("/api/products")
def get_products(
    db: Session = Depends(get_db),
    category: str = Query(None)
):
    print(f"[DEBUG] Fetching products for category: {category}")
    try:
        # 1. Get products in category first (fast)
        p_query = db.query(models.Product)
        if category and category != "ALL_SECTORS":
            p_query = p_query.filter(models.Product.category_name == category)
        
        # If ALL_SECTORS or no category, limit results to prevent timeout/CORS crash
        if not category or category == "ALL_SECTORS":
            target_products = p_query.limit(500).all()
        else:
            target_products = p_query.all()
            
        p_ids = [p.id for p in target_products]
        print(f"[DEBUG] Found {len(p_ids)} target products.")

        if not p_ids:
            return []

        # 2. Get latest price for these products
        latest_ts = db.query(
            models.PriceHistory.product_id,
            func.max(models.PriceHistory.timestamp).label("max_ts")
        ).filter(models.PriceHistory.product_id.in_(p_ids))\
         .filter(models.PriceHistory.price_amount > 0)\
         .group_by(models.PriceHistory.product_id).subquery()

        # 3. Get stats for these products
        stats = db.query(
            models.PriceHistory.product_id,
            func.min(models.PriceHistory.price_amount).label("atl"),
            func.avg(models.PriceHistory.price_amount).label("avg_p")
        ).filter(models.PriceHistory.product_id.in_(p_ids))\
         .filter(models.PriceHistory.price_amount > 0)\
         .group_by(models.PriceHistory.product_id).subquery()

        # 4. Final join (much smaller set)
        results = db.query(
            models.Product,
            models.PriceHistory.price_amount,
            stats.c.atl,
            stats.c.avg_p
        ).filter(models.Product.id.in_(p_ids))\
         .join(latest_ts, models.Product.id == latest_ts.c.product_id)\
         .join(models.PriceHistory, (models.PriceHistory.product_id == latest_ts.c.product_id) & (models.PriceHistory.timestamp == latest_ts.c.max_ts))\
         .join(stats, models.Product.id == stats.c.product_id)\
         .all()

        print(f"[DEBUG] Successfully joined {len(results)} results.")
        output = []
        for p, curr, atl, avg in results:
            u_val = p.extracted_unit_value or 1.0
            output.append({
                "id": p.id,
                "name": p.name,
                "image_url": p.image_url,
                "vendor": p.vendor_name,
                "current_price": curr,
                "atl": atl,
                "is_atl": curr <= atl,
                "unit_price": curr / u_val,
                "unit_type": p.extracted_unit_type
            })
        return output
    except Exception as e:
        print(f"[ERROR] Failed to fetch products: {e}")
        import traceback
        traceback.print_exc()
        raise e

@app.get("/api/products/{pid}/history")
def get_history(pid: str, db: Session = Depends(get_db)):
    h = db.query(models.PriceHistory)\
          .filter(models.PriceHistory.product_id == pid)\
          .filter(models.PriceHistory.price_amount > 0)\
          .order_by(models.PriceHistory.timestamp).all()
    return [{"timestamp": x.timestamp, "price": x.price_amount} for x in h]

if __name__ == "__main__":
    init_db()
    uvicorn.run(app, host="0.0.0.0", port=8000)
