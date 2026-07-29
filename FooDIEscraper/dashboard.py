"""
FoodiBD Dashboard - FastAPI frontend for product data and analytics.
Usage: python dashboard.py
"""

import json
import os
import subprocess
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).parent
with open(BASE / "config.yaml") as f:
    CFG = yaml.safe_load(f)

DB_PATH = str(BASE / CFG["output"]["sqlite_path"])
PARQUET_DIR = BASE / CFG["output"]["parquet_dir"]
app = FastAPI(title="FoodiBD Dashboard")

app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

# Scraper state
_scraper_status = {"running": False, "last_output": "", "pid": None, "started_at": None}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.get("/api/products")
def list_products(
    q: Optional[str] = None,
    category: Optional[int] = None,
    sort: Optional[str] = "name",
    order: Optional[str] = "asc",
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock: Optional[bool] = None,
    page: int = 1,
    per_page: int = 50,
):
    db = get_db()
    where, params = [], []

    if q:
        where.append("(p.name LIKE ? OR p.sku LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    if category is not None:
        where.append("p.category_id = ?")
        params.append(category)
    if min_price is not None:
        where.append("p.discounted_price >= ?")
        params.append(min_price)
    if max_price is not None:
        where.append("p.discounted_price <= ?")
        params.append(max_price)
    if in_stock is not None:
        where.append("p.has_stock = ?")
        params.append(int(in_stock))

    w = f"WHERE {' AND '.join(where)}" if where else ""
    allowed_sorts = {"name", "base_price", "discounted_price", "discount", "product_id", "category_name"}
    s = sort if sort in allowed_sorts else "name"
    o = "DESC" if order == "desc" else "ASC"

    total = db.execute(f"SELECT COUNT(*) FROM products p {w}", params).fetchone()[0]
    offset = (page - 1) * per_page
    rows = db.execute(
        f"SELECT p.*, c.name as _cat FROM products p LEFT JOIN (SELECT DISTINCT category_id, category_name as name FROM products) c ON p.category_id = c.category_id {w} ORDER BY p.{s} {o} LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()
    db.close()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "data": [dict(r) for r in rows],
    }


@app.get("/api/categories")
def list_categories():
    db = get_db()
    rows = db.execute(
        "SELECT category_id, category_name, COUNT(*) as product_count, AVG(discounted_price) as avg_price, SUM(CASE WHEN discount > 0 THEN 1 ELSE 0 END) as discounted_count FROM products GROUP BY category_id ORDER BY category_name"
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


@app.get("/api/price-history/{product_id}")
def price_history(product_id: int, days: int = 90):
    db = get_db()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    rows = db.execute(
        "SELECT scraped_at, base_price, discount, is_discount_in_perc, discounted_price, has_stock FROM price_history WHERE product_id = ? AND scraped_at >= ? ORDER BY scraped_at",
        (product_id, cutoff),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


@app.get("/api/price-changes")
def price_changes():
    db = get_db()
    # Products whose price changed between last two scrape runs
    rows = db.execute("""
        SELECT a.product_id, a.name, a.category_name,
               a.discounted_price as old_price, b.discounted_price as new_price,
               a.scraped_at as old_date, b.scraped_at as new_date,
               ROUND(b.discounted_price - a.discounted_price, 2) as price_diff
        FROM price_history a
        JOIN price_history b ON a.product_id = b.product_id AND b.scraped_at > a.scraped_at
        WHERE a.scraped_at = (SELECT MAX(scraped_at) FROM price_history WHERE scraped_at < (SELECT MAX(scraped_at) FROM price_history))
          AND b.scraped_at = (SELECT MAX(scraped_at) FROM price_history)
          AND a.discounted_price != b.discounted_price
        ORDER BY ABS(b.discounted_price - a.discounted_price) DESC
        LIMIT 50
    """).fetchall()
    db.close()
    return [dict(r) for r in rows]


@app.get("/api/analytics")
def analytics():
    db = get_db()
    stats = {}
    stats["total_products"] = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    stats["total_categories"] = db.execute("SELECT COUNT(DISTINCT category_id) FROM products").fetchone()[0]
    stats["avg_price"] = db.execute("SELECT ROUND(AVG(discounted_price), 2) FROM products").fetchone()[0]
    stats["max_price"] = db.execute("SELECT MAX(discounted_price) FROM products").fetchone()[0]
    stats["min_price"] = db.execute("SELECT MIN(discounted_price) FROM products").fetchone()[0]
    stats["total_discounted"] = db.execute("SELECT COUNT(*) FROM products WHERE discount > 0").fetchone()[0]
    stats["in_stock"] = db.execute("SELECT COUNT(*) FROM products WHERE has_stock = 1").fetchone()[0]
    stats["out_of_stock"] = db.execute("SELECT COUNT(*) FROM products WHERE has_stock = 0").fetchone()[0]

    # Top 10 most expensive
    stats["top_expensive"] = [dict(r) for r in db.execute(
        "SELECT product_id, name, category_name, discounted_price, sku FROM products ORDER BY discounted_price DESC LIMIT 10"
    ).fetchall()]

    # Top 10 biggest discounts
    stats["top_discounts"] = [dict(r) for r in db.execute(
        "SELECT product_id, name, category_name, base_price, discounted_price, discount, is_discount_in_perc FROM products WHERE discount > 0 ORDER BY discount DESC LIMIT 10"
    ).fetchall()]

    # Category price distribution
    stats["category_stats"] = [dict(r) for r in db.execute(
        """SELECT category_name,
                  COUNT(*) as count,
                  ROUND(AVG(discounted_price), 2) as avg_price,
                  ROUND(MIN(discounted_price), 2) as min_price,
                  ROUND(MAX(discounted_price), 2) as max_price,
                  ROUND(SUM(discounted_price), 2) as total_value,
                  SUM(CASE WHEN discount > 0 THEN 1 ELSE 0 END) as discounted
           FROM products GROUP BY category_id ORDER BY count DESC"""
    ).fetchall()]

    # Price buckets
    stats["price_buckets"] = [dict(r) for r in db.execute(
        """SELECT
             CASE
               WHEN discounted_price < 50 THEN '0-50'
               WHEN discounted_price < 100 THEN '50-100'
               WHEN discounted_price < 200 THEN '100-200'
               WHEN discounted_price < 500 THEN '200-500'
               WHEN discounted_price < 1000 THEN '500-1K'
               ELSE '1K+'
             END as bucket,
             COUNT(*) as count
           FROM products GROUP BY bucket ORDER BY MIN(discounted_price)"""
    ).fetchall()]

    # Scrape runs
    stats["scrape_runs"] = [dict(r) for r in db.execute(
        "SELECT * FROM scrape_runs ORDER BY id DESC LIMIT 10"
    ).fetchall()]

    # Historical product count per day
    stats["daily_counts"] = [dict(r) for r in db.execute(
        "SELECT DATE(scraped_at) as day, COUNT(DISTINCT product_id) as count FROM price_history GROUP BY day ORDER BY day"
    ).fetchall()]

    db.close()
    return stats


@app.get("/api/search")
def search_products(q: str = "", limit: int = 20):
    db = get_db()
    rows = db.execute(
        "SELECT product_id, name, sku, category_name, discounted_price, image_path FROM products WHERE name LIKE ? OR sku LIKE ? LIMIT ?",
        (f"%{q}%", f"%{q}%", limit),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Scraper trigger
# ---------------------------------------------------------------------------

def _run_scraper():
    """Run scraper.py in a subprocess (background thread)."""
    _scraper_status["running"] = True
    _scraper_status["started_at"] = datetime.utcnow().isoformat()
    try:
        proc = subprocess.run(
            ["python", str(BASE / "scraper.py")],
            capture_output=True, text=True, timeout=600,
            cwd=str(BASE),
        )
        _scraper_status["last_output"] = proc.stdout[-2000:] + "\n" + proc.stderr[-2000:]
        _scraper_status["returncode"] = proc.returncode
    except Exception as e:
        _scraper_status["last_output"] = f"ERROR: {e}"
        _scraper_status["returncode"] = -1
    finally:
        _scraper_status["running"] = False


@app.post("/api/scrape")
def trigger_scrape():
    if _scraper_status["running"]:
        return {"status": "already_running", "pid": _scraper_status.get("pid")}
    t = threading.Thread(target=_run_scraper, daemon=True)
    t.start()
    return {"status": "started"}


@app.get("/api/scrape/status")
def scrape_status():
    return _scraper_status


# ---------------------------------------------------------------------------
# Deal classification — computes per-product signals from price_history
# ---------------------------------------------------------------------------

@app.get("/api/deal-classification")
def deal_classification(
    new_days: int = 7,
    great_pct: float = 15.0,
    good_pct: float = 5.0,
):
    """
    Classify every product into deal buckets:
      great_deal: current price < mean_price * (1 - great_pct/100)
      good_buy:   current price < mean_price * (1 - good_pct/100)
      wait:       current price > mean_price * 1.05
      all_time_low: current price == min historical price
      new_item:   first seen within new_days
      price_change: price changed vs last run
    """
    db = get_db()
    cutoff = (datetime.utcnow() - timedelta(days=new_days)).isoformat()

    rows = db.execute("""
        SELECT p.product_id, p.name, p.category_name, p.discounted_price,
               p.base_price, p.has_stock, p.image_path,
               ph.h_mean, ph.h_min, ph.h_count, ph.first_seen
        FROM products p
        LEFT JOIN (
            SELECT product_id,
                   ROUND(AVG(discounted_price), 2) as h_mean,
                   ROUND(MIN(discounted_price), 2) as h_min,
                   COUNT(*) as h_count,
                   MIN(scraped_at) as first_seen
            FROM price_history
            GROUP BY product_id
        ) ph ON p.product_id = ph.product_id
    """).fetchall()

    # Price changes between last two runs
    changes = db.execute("""
        SELECT a.product_id,
               a.discounted_price as old_price,
               b.discounted_price as new_price
        FROM price_history a
        JOIN price_history b ON a.product_id = b.product_id AND b.scraped_at > a.scraped_at
        WHERE a.scraped_at = (SELECT MAX(scraped_at) FROM price_history WHERE scraped_at < (SELECT MAX(scraped_at) FROM price_history))
          AND b.scraped_at = (SELECT MAX(scraped_at) FROM price_history)
    """).fetchall()
    price_changes = {r["product_id"]: r for r in changes}

    now = datetime.utcnow()
    result = []
    for r in rows:
        d = dict(r)
        price = d["discounted_price"] or 0
        mean_p = d["h_mean"] or price
        min_p = d["h_min"] or price
        first_seen = d["first_seen"]

        # Deal classification
        deal = "none"
        deal_pct = 0
        if mean_p > 0:
            deal_pct = round((1 - price / mean_p) * 100, 1) if price < mean_p else 0
            if price < mean_p * (1 - great_pct / 100):
                deal = "great_deal"
            elif price < mean_p * (1 - good_pct / 100):
                deal = "good_buy"
            elif price > mean_p * 1.05:
                deal = "wait"

        # All time low
        is_atl = price <= min_p + 0.01 and (d["h_count"] or 0) > 1

        # New item
        is_new = False
        if first_seen:
            try:
                fs = datetime.fromisoformat(first_seen.replace("Z", "+00:00")).replace(tzinfo=None)
                is_new = (now - fs).days <= new_days
            except (ValueError, TypeError):
                pass

        # Price change
        pc = price_changes.get(d["product_id"])
        pc_diff = None
        pc_pct = None
        if pc and pc["old_price"] and pc["new_price"] and pc["old_price"] != pc["new_price"]:
            pc_diff = round(pc["new_price"] - pc["old_price"], 2)
            pc_pct = round(pc_diff / pc["old_price"] * 100, 1) if pc["old_price"] else 0

        d["deal"] = deal
        d["deal_pct"] = deal_pct
        d["is_atl"] = is_atl
        d["is_new"] = is_new
        d["pc_diff"] = pc_diff
        d["pc_pct"] = pc_pct
        d["h_mean"] = mean_p
        d["h_min"] = min_p
        d["h_count"] = d["h_count"] or 0
        result.append(d)

    db.close()
    return result


# ---------------------------------------------------------------------------
# Mean analysis — price stats within a date range
# ---------------------------------------------------------------------------

@app.get("/api/mean-analysis")
def mean_analysis(
    start_date: str = "",
    end_date: str = "",
):
    """
    Compute mean/min/max/std price per product within a date range.
    """
    db = get_db()
    where = []
    params = []
    if start_date:
        where.append("scraped_at >= ?")
        params.append(start_date)
    if end_date:
        where.append("scraped_at <= ?")
        params.append(end_date + "T23:59:59")

    w = f"WHERE {' AND '.join(where)}" if where else ""

    rows = db.execute(f"""
        SELECT product_id, name, category_name,
               ROUND(AVG(discounted_price), 2) as mean_price,
               ROUND(MIN(discounted_price), 2) as min_price,
               ROUND(MAX(discounted_price), 2) as max_price,
               COUNT(*) as data_points,
               MIN(scraped_at) as period_start,
               MAX(scraped_at) as period_end
        FROM price_history
        {w}
        GROUP BY product_id
        HAVING COUNT(*) >= 2
        ORDER BY mean_price DESC
    """, params).fetchall()

    db.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Parquet-based API endpoints — faster bulk reads for price histories
# ---------------------------------------------------------------------------

@app.get("/api/parquet/products")
def parquet_products(category: Optional[int] = None, limit: int = 500):
    """Read latest product snapshot from Parquet (faster than SQLite for bulk reads)."""
    try:
        import pyarrow.parquet as pq
        snap_path = PARQUET_DIR / "latest_snapshot.parquet"
        if not snap_path.exists():
            return JSONResponse({"error": "No parquet snapshot found", "data": []}, status_code=404)
        table = pq.read_table(snap_path)
        df = table.to_pandas()
        if category is not None:
            df = df[df["category_id"] == category]
        df = df.head(limit)
        return {"total": len(df), "source": "parquet", "data": df.to_dict(orient="records")}
    except Exception as e:
        return JSONResponse({"error": str(e), "data": []}, status_code=500)


@app.get("/api/parquet/price-history/{product_id}")
def parquet_price_history(product_id: int, days: int = 90):
    """Read price history from Parquet partitions — much faster than SQLite for date-range scans."""
    try:
        import pyarrow.parquet as pq
        import pyarrow.compute as pc
        ph_dir = PARQUET_DIR / "price_history"
        if not ph_dir.exists():
            return JSONResponse({"error": "No parquet price history found", "data": []}, status_code=404)

        cutoff = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
        tables = []
        for f in sorted(ph_dir.glob("date=*.parquet")):
            date_str = f.stem.split("=")[1] if "=" in f.stem else ""
            if date_str < cutoff:
                continue
            t = pq.read_table(f, filters=[("product_id", "=", product_id)])
            if len(t) > 0:
                tables.append(t)

        if not tables:
            return {"product_id": product_id, "source": "parquet", "data": []}

        combined = pq.concat_tables(tables)
        df = combined.to_pandas().sort_values("scraped_at")
        return {"product_id": product_id, "source": "parquet", "data": df.to_dict(orient="records")}
    except Exception as e:
        return JSONResponse({"error": str(e), "data": []}, status_code=500)


@app.get("/api/parquet/stats")
def parquet_stats():
    """Summary stats from Parquet files on disk."""
    try:
        import pyarrow.parquet as pq
        snap_path = PARQUET_DIR / "latest_snapshot.parquet"
        ph_dir = PARQUET_DIR / "price_history"

        info = {"source": "parquet", "snapshot": None, "price_history_files": [], "total_rows": 0}

        if snap_path.exists():
            meta = pq.read_metadata(snap_path)
            info["snapshot"] = {
                "path": str(snap_path.relative_to(BASE)),
                "rows": meta.num_rows,
                "size_bytes": snap_path.stat().st_size,
                "created": datetime.fromtimestamp(snap_path.stat().st_ctime).isoformat(),
            }
            info["total_rows"] = meta.num_rows

        if ph_dir.exists():
            for f in sorted(ph_dir.glob("date=*.parquet")):
                meta = pq.read_metadata(f)
                date_str = f.stem.split("=")[1] if "=" in f.stem else f.stem
                info["price_history_files"].append({
                    "date": date_str,
                    "rows": meta.num_rows,
                    "size_bytes": f.stat().st_size,
                })
                info["total_rows"] += meta.num_rows

        return info
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/parquet/export")
def parquet_export(format: str = "json"):
    """Export all price history from Parquet as JSON or CSV."""
    try:
        import pyarrow.parquet as pq
        from fastapi.responses import StreamingResponse
        import io

        ph_dir = PARQUET_DIR / "price_history"
        if not ph_dir.exists():
            return JSONResponse({"error": "No parquet price history found"}, status_code=404)

        tables = []
        for f in sorted(ph_dir.glob("date=*.parquet")):
            tables.append(pq.read_table(f))

        if not tables:
            return JSONResponse({"error": "No data"}, status_code=404)

        combined = pq.concat_tables(tables)
        df = combined.to_pandas()

        if format == "csv":
            buf = io.StringIO()
            df.to_csv(buf, index=False)
            buf.seek(0)
            return StreamingResponse(iter([buf.getvalue()]),
                                     media_type="text/csv",
                                     headers={"Content-Disposition": "attachment; filename=price_history.csv"})
        else:
            return {"source": "parquet", "total_rows": len(df), "data": df.head(5000).to_dict(orient="records")}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return (BASE / "static" / "index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=CFG["frontend"]["host"], port=CFG["frontend"]["port"])
