import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Search, ChevronRight, ChevronLeft, ArrowUpDown, X, List, TrendingDown } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import './App.css';

const API_BASE = 'http://localhost:8000/api';

interface Product {
  id: string;
  name: string;
  image_url: string;
  vendor: string;
  category: string;
  current_price: number;
  atl: number;
  avg_price: number;
  is_atl: boolean;
  percent_of_avg: number;
  unit_price: number;
  unit_type: string;
}

interface Category {
  name: string;
  count: number;
}

const App = () => {
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState('');
  const [search, setSearch] = useState('');
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [historyData, setHistoryData] = useState<any[]>([]);
  const [isSidebarOpen, setSidebarOpen] = useState(true);
  
  // Sort and Filter States
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [unitFilter, setUnitFilter] = useState<'all' | 'kg' | 'L' | 'piece'>('all');
  const [atlOnly, setAtlOnly] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const fetchCategories = async () => {
    try {
      const res = await axios.get(`${API_BASE}/categories`);
      if (Array.isArray(res.data)) {
        const validCats = res.data.filter((c: any) => c.name && typeof c.name === 'string');
        setCategories(validCats);
        if (validCats.length === 0) setError("DATABASE_EMPTY: Run scraper.py to index sectors.");
      } else {
        setError("API_PAYLOAD_ERROR: Invalid data structure from backend.");
      }
    } catch (err: any) {
      setError(`COMM_LINK_OFFLINE: ${err.message}`);
    }
  };

  const fetchProducts = async () => {
    // If category is not selected, we don't fetch (default behavior)
    // But we want to support 'ALL_SECTORS'
    if (!selectedCategory) return;
    
    setLoading(true);
    setError(null);
    try {
      const params: any = {};
      if (selectedCategory !== 'ALL_SECTORS') {
        params.category = selectedCategory;
      }
      const res = await axios.get(`${API_BASE}/products`, { params });
      setProducts(res.data);
    } catch (err: any) {
      setError(`PRODUCT_FETCH_FAILED: ${err.message}`);
    }
    setLoading(false);
  };

  useEffect(() => { fetchCategories(); }, []);
  useEffect(() => { fetchProducts(); }, [selectedCategory]);

  const handleEsc = useCallback((event: KeyboardEvent) => {
    if (event.key === "Escape") setSelectedProduct(null);
  }, []);

  useEffect(() => {
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [handleEsc]);

  const analyzeProduct = async (product: Product) => {
    try {
      const res = await axios.get(`${API_BASE}/products/${product.id}/history`);
      setHistoryData(res.data.map((h: any) => ({
        ...h,
        timestamp: new Date(h.timestamp).toLocaleDateString()
      })));
      setSelectedProduct(product);
    } catch (err) {}
  };

  const processedProducts = useMemo(() => {
    return products
      .filter(p => p.name.toLowerCase().includes(search.toLowerCase()))
      .filter(p => unitFilter === 'all' || p.unit_type === unitFilter)
      .filter(p => !atlOnly || p.is_atl)
      .sort((a, b) => sortDir === 'asc' ? a.unit_price - b.unit_price : b.unit_price - a.unit_price);
  }, [products, search, unitFilter, atlOnly, sortDir]);

  return (
    <div className="fullscreen-app">
      <aside className={`hud-sidebar ${isSidebarOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-header">
          <List size={18} /> SECTOR_INDEX
          <button className="toggle-btn" onClick={() => setSidebarOpen(!isSidebarOpen)}>
            {isSidebarOpen ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
          </button>
        </div>
        <div className="sidebar-content">
          <div 
            className={`cat-item special ${selectedCategory === 'ALL_SECTORS' ? 'active' : ''}`}
            onClick={() => setSelectedCategory('ALL_SECTORS')}
          >
            <span className="cat-name">{">> ALL_SECTORS <<"}</span>
            <span className="cat-count">[*]</span>
          </div>
          {categories.map((c, idx) => (
            <div 
              key={`${c.name}-${idx}`} 
              className={`cat-item ${selectedCategory === c.name ? 'active' : ''}`}
              onClick={() => setSelectedCategory(c.name)}
            >
              <span className="cat-name">{c.name.toUpperCase()}</span>
              <span className="cat-count">[{c.count}]</span>
            </div>
          ))}
        </div>
      </aside>

      <div className="main-content">
        {error && (
          <div className="error-banner sci-fi-border">
            <div className="error-icon">!</div>
            <div className="error-text">{error}</div>
            <button className="hud-btn" onClick={fetchCategories}>RE_SCAN_LINK</button>
          </div>
        )}
        <header className="hud-header">
          <div className="hud-left">
            <div className="glitch-text title">SCANNER_v1.1.5</div>
            <div className="status-line">
              <span className="pulse"></span> 
              BUFFER: {processedProducts.length} | SECTOR: {selectedCategory || "NONE"}
            </div>
          </div>
          <div className="hud-center">
            <div className="search-box">
              <Search size={14} className="search-icon" />
              <input 
                className="search-hud"
                value={search} 
                onChange={e => setSearch(e.target.value)}
                placeholder="PROBE_SPECIFICATION..." 
              />
            </div>
          </div>
          <div className="hud-right">
            <div className="tool-group">
              <button 
                className={`hud-btn ${atlOnly ? 'active-glow' : ''}`}
                onClick={() => setAtlOnly(!atlOnly)}
                title="Filter All Time Lows"
              >
                <TrendingDown size={14} /> ATL_ONLY
              </button>
              <select className="hud-select" value={unitFilter} onChange={e => setUnitFilter(e.target.value as any)}>
                <option value="all">ALL_UNITS</option>
                <option value="kg">BY_WEIGHT(KG)</option>
                <option value="L">BY_VOLUME(L)</option>
                <option value="piece">BY_PIECE(PC)</option>
              </select>
              <button className="hud-btn" onClick={() => setSortDir(prev => prev === 'asc' ? 'desc' : 'asc')}>
                <ArrowUpDown size={14} /> UNIT_PRICE_{sortDir.toUpperCase()}
              </button>
            </div>
          </div>
        </header>

        <main className="hud-grid-area">
          {loading ? (
            <div className="loader-hud">SYNCING_SECTOR_DATA...</div>
          ) : !selectedCategory ? (
            <div className="loader-hud dim">SYSTEM_IDLE: SELECT SECTOR FROM INDEX</div>
          ) : (
            <div className="ultra-dense-grid">
              {processedProducts.map(p => (
                <div key={p.id} className="micro-card" onClick={() => analyzeProduct(p)}>
                  <div className="card-bg" style={{backgroundImage: `url(${p.image_url})`}}></div>
                  <div className="card-content">
                    <div className="card-price">Tk {p.current_price}</div>
                    <div className="card-unit">Tk{p.unit_price.toFixed(1)}/{p.unit_type}</div>
                    <div className="card-name">{p.name}</div>
                    {p.is_atl && <div className="card-atl">ATL</div>}
                    <div className="card-vendor">{p.vendor}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </main>
      </div>

      <AnimatePresence>
        {selectedProduct && (
          <motion.div 
            className="fullscreen-chart"
            style={{ backgroundImage: `url(${selectedProduct.image_url})` }}
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          >
            <div className="chart-hud-overlay">
              <div className="chart-header">
                <div className="chart-title">
                  <h2>DEEP_DIVE: {selectedProduct.name}</h2>
                  <p>ID: {selectedProduct.id} | VENDOR: {selectedProduct.vendor}</p>
                </div>
                <div className="chart-controls">
                  <div className="esc-hint">PRESS [ESC] TO CLOSE</div>
                  <X className="close-x" onClick={() => setSelectedProduct(null)} />
                </div>
              </div>
              <div className="full-chart-box">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={historyData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1a222d" />
                    <XAxis dataKey="timestamp" stroke="#00f2ff" fontSize={10} />
                    <YAxis stroke="#00f2ff" fontSize={10} />
                    <Tooltip 
                      contentStyle={{ background: '#05070a', border: '1px solid #00f2ff', fontSize: '12px' }}
                      itemStyle={{ color: '#39ff14' }}
                    />
                    <Line 
                      type="stepAfter" 
                      dataKey="price" 
                      stroke="#39ff14" 
                      strokeWidth={3} 
                      dot={{ r: 4, fill: '#39ff14' }} 
                      activeDot={{ r: 8, stroke: '#fff' }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default App;
