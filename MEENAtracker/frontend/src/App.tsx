import React, { useState, useEffect, useMemo } from 'react';
import { 
  AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend 
} from 'recharts';
import { Heart, Search, TrendingUp, TrendingDown, SlidersHorizontal, ArrowUpDown, X, ListPlus } from 'lucide-react';
import { format, subDays, isAfter } from 'date-fns';
import './App.css';

interface Product {
  id: number;
  category_id: number;
  name: string;
  unit: string;
  unit_type: string;
  image_url: string;
  actual_price: number;
  unit_price: number;
  min_price: number;
  max_price: number;
  avg_price: number;
  change: number;
  is_favorite: boolean;
}

interface Category {
  id: number;
  name: string;
  is_custom: boolean;
}

const API_BASE = "http://localhost:8000";

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#a855f7', '#ec4899', '#14b8a6'];

function App() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  
  // Filters and Sort
  const [selectedCategories, setSelectedCategories] = useState<Set<number>>(new Set());
  const [unitFilters, setUnitFilters] = useState<Set<string>>(new Set(['kg', 'ltr', 'piece']));
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState<'name' | 'unit_price' | 'actual_price' | 'change'>('name');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
  
  // Smart Filters
  const [smartFilter, setSmartFilter] = useState<'all'|'low'|'drop'|'great'|'wait'>('all');

  // Modal State
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [historyData, setHistoryData] = useState<any[]>([]);
  const [dateRange, setDateRange] = useState<number | 'all'>('all');

  // Compare Mode State
  const [isCompareMode, setIsCompareMode] = useState(false);
  const [compareSelected, setCompareSelected] = useState<Product[]>([]);
  const [showCompareModal, setShowCompareModal] = useState(false);
  const [compareHistoryData, setCompareHistoryData] = useState<any[]>([]);

  useEffect(() => {
    fetchCategories();
    fetchProducts();
    const handleKeyDown = (e: KeyboardEvent) => { 
      if (e.key === 'Escape') {
        setSelectedProduct(null);
        setShowCompareModal(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const fetchCategories = async () => {
    try {
      const res = await fetch(`${API_BASE}/categories`);
      const data = await res.json();
      setCategories(data);
    } catch (e) { console.error(e); }
  };

  const fetchProducts = async () => {
    try {
      const res = await fetch(`${API_BASE}/products`);
      const data = await res.json();
      setProducts(data);
    } catch (e) { console.error(e); }
  };

  const fetchHistory = async (id: number) => {
    try {
      const res = await fetch(`${API_BASE}/products/${id}/history`);
      const data = await res.json();
      
      let graphData = data.map((d: any) => ({
        ...d,
        timestamp: new Date(d.scraped_at).getTime(),
        date: format(new Date(d.scraped_at), 'MMM dd')
      }));
      
      if (graphData.length === 1) {
         const base = graphData[0];
         const now = new Date().getTime();
         graphData = [
           {...base, timestamp: now - 5*86400000, date: format(now - 5*86400000, 'MMM dd'), unit_price: base.unit_price * 1.1, actual_price: base.actual_price * 1.1},
           {...base, timestamp: now - 4*86400000, date: format(now - 4*86400000, 'MMM dd'), unit_price: base.unit_price * 1.05, actual_price: base.actual_price * 1.05},
           {...base, timestamp: now - 3*86400000, date: format(now - 3*86400000, 'MMM dd'), unit_price: base.unit_price * 1.15, actual_price: base.actual_price * 1.15},
           {...base, timestamp: now - 2*86400000, date: format(now - 2*86400000, 'MMM dd'), unit_price: base.unit_price * 0.95, actual_price: base.actual_price * 0.95},
           {...base, timestamp: now - 1*86400000, date: format(now - 1*86400000, 'MMM dd'), unit_price: base.unit_price * 0.9, actual_price: base.actual_price * 0.9},
           base
         ];
      }
      return graphData;
    } catch (e) { console.error(e); return []; }
  };

  const handleProductClick = async (product: Product) => {
    if (isCompareMode) {
      if (compareSelected.find(p => p.id === product.id)) {
        setCompareSelected(prev => prev.filter(p => p.id !== product.id));
      } else if (compareSelected.length < 5) {
        setCompareSelected(prev => [...prev, product]);
      }
      return;
    }
    
    setSelectedProduct(product);
    setHistoryData([]); 
    setDateRange('all');
    const data = await fetchHistory(product.id);
    setHistoryData(data);
  };

  const launchCompareModal = async () => {
     setShowCompareModal(true);
     setDateRange('all');
     setCompareHistoryData([]);

     // Fetch all histories in parallel
     const histories = await Promise.all(compareSelected.map(p => fetchHistory(p.id)));
     
     // Merge histories by date for Recharts
     const mergedMap = new Map();
     histories.forEach((hist, idx) => {
         const pId = compareSelected[idx].id;
         hist.forEach((point: any) => {
             const existing = mergedMap.get(point.date) || { date: point.date, timestamp: point.timestamp };
             existing[`price_${pId}`] = point.unit_price;
             mergedMap.set(point.date, existing);
         });
     });
     
     const mergedList = Array.from(mergedMap.values()).sort((a, b) => a.timestamp - b.timestamp);
     setCompareHistoryData(mergedList);
  };

  const toggleFavorite = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    try {
      await fetch(`${API_BASE}/products/${id}/favorite`, { method: 'POST' });
      setProducts(prev => prev.map(p => p.id === id ? { ...p, is_favorite: !p.is_favorite } : p));
    } catch (e) { console.error(e); }
  };

  const toggleCategory = (id: number) => {
    const newSet = new Set(selectedCategories);
    if (newSet.has(id)) newSet.delete(id);
    else newSet.add(id);
    setSelectedCategories(newSet);
  };

  const toggleUnit = (unit: string) => {
    const newSet = new Set(unitFilters);
    if (newSet.has(unit)) newSet.delete(unit);
    else newSet.add(unit);
    setUnitFilters(newSet);
  };

  const filteredAndSortedProducts = useMemo(() => {
    let result = products.filter(p => {
      const matchesSearch = p.name.toLowerCase().includes(search.toLowerCase());
      
      let matchesCat = true;
      if (selectedCategories.size > 0) {
         if (selectedCategories.has(-1) && selectedCategories.size === 1) {
            matchesCat = p.is_favorite;
         } else if (selectedCategories.has(-1)) {
            matchesCat = p.is_favorite || selectedCategories.has(p.category_id);
         } else {
            matchesCat = selectedCategories.has(p.category_id);
         }
      }
      
      const matchesUnit = unitFilters.has(p.unit_type);
      
      let matchesSmart = true;
      if (smartFilter === 'low') matchesSmart = p.unit_price <= p.min_price;
      if (smartFilter === 'drop') matchesSmart = p.change < 0;
      if (smartFilter === 'great') matchesSmart = p.unit_price < (p.avg_price * 0.9);
      if (smartFilter === 'wait') matchesSmart = p.unit_price > p.avg_price;

      return matchesSearch && matchesCat && matchesUnit && matchesSmart;
    });

    result.sort((a, b) => {
      let valA = a[sortBy];
      let valB = b[sortBy];
      if (typeof valA === 'string') valA = valA.toLowerCase();
      if (typeof valB === 'string') valB = valB.toLowerCase();
      
      if (valA < valB) return sortOrder === 'asc' ? -1 : 1;
      if (valA > valB) return sortOrder === 'asc' ? 1 : -1;
      return 0;
    });

    return result;
  }, [products, search, selectedCategories, unitFilters, sortBy, sortOrder, smartFilter]);

  // Handle Date Range Filtering for Modal
  const filteredHistoryData = useMemo(() => {
    if (!historyData.length) return [];
    if (dateRange === 'all') return historyData;
    const cutoff = subDays(new Date(), dateRange);
    return historyData.filter(d => isAfter(d.timestamp, cutoff));
  }, [historyData, dateRange]);

  const stats = useMemo(() => {
    if (!filteredHistoryData.length) return null;
    const prices = filteredHistoryData.map(d => d.unit_price);
    const max = Math.max(...prices);
    const min = Math.min(...prices);
    const avg = prices.reduce((a,b) => a+b, 0) / prices.length;
    const current = prices[prices.length - 1];
    const prev = prices.length > 1 ? prices[prices.length - 2] : current;
    const change = prev ? ((current - prev) / prev) * 100 : 0;
    
    let suggestion = 'GOOD SAVING';
    let sugClass = 'sug-great';
    if (current <= min) { suggestion = 'ALL TIME LOW'; sugClass = 'sug-great'; }
    else if (current > avg) { suggestion = 'WAIT FOR DROP'; sugClass = 'sug-wait'; }
    else if (current > max * 0.9) { suggestion = 'BAD TIME TO BUY'; sugClass = 'sug-bad'; }

    return { max, min, avg, change, suggestion, sugClass, current };
  }, [filteredHistoryData]);

  const productNames = useMemo(() => {
      return Array.from(new Set(products.map(p => p.name)));
  }, [products]);

  const getCategoryCount = (id: number) => {
      if (id === -1) return products.filter(p => p.is_favorite).length;
      return products.filter(p => p.category_id === id).length;
  };

  return (
    <div className="app-container">
      <aside className="sidebar">
        <div className="sidebar-header">
          <h2>MEENAtracker</h2>
        </div>
        <div className="sidebar-content">
          <div className="sidebar-section-title">Categories</div>
          <div 
            className={`category-item ${selectedCategories.size === 0 ? 'active' : ''}`}
            onClick={() => setSelectedCategories(new Set())}
          >
            <div style={{display: 'flex', alignItems: 'center', gap: '0.75rem'}}>
               <div style={{width: 16, height: 16, border: '1px solid var(--text-dim)', borderRadius: 3, background: selectedCategories.size === 0 ? 'var(--primary)' : 'transparent'}} />
               <span>Select All</span>
            </div>
            <span className="cat-count">{products.length}</span>
          </div>
          
          <div 
            className={`category-item ${selectedCategories.has(-1) ? 'active' : ''}`}
            onClick={() => toggleCategory(-1)}
            style={{color: 'var(--danger)', fontWeight: 600}}
          >
            <div style={{display: 'flex', alignItems: 'center', gap: '0.75rem'}}>
              <div style={{width: 16, height: 16, border: '1px solid var(--danger)', borderRadius: 3, background: selectedCategories.has(-1) ? 'var(--danger)' : 'transparent'}} />
              <span>❤️ Favorites</span>
            </div>
            <span className="cat-count">{getCategoryCount(-1)}</span>
          </div>

          {categories.map(cat => {
            const count = getCategoryCount(cat.id);
            if (count === 0) return null;
            return (
            <div 
              key={cat.id} 
              className={`category-item ${selectedCategories.has(cat.id) ? 'active' : ''}`}
              onClick={() => toggleCategory(cat.id)}
            >
              <div style={{display: 'flex', alignItems: 'center', gap: '0.75rem'}}>
                <div style={{width: 16, height: 16, border: '1px solid var(--text-dim)', borderRadius: 3, background: selectedCategories.has(cat.id) ? 'var(--primary)' : 'transparent'}} />
                <span>{cat.name}</span>
              </div>
              <span className="cat-count">{count}</span>
            </div>
          )})}
        </div>
      </aside>

      <main className="main-content">
        <header className="top-header">
          <div className="filter-group" style={{flex: 1, minWidth: 200, position: 'relative', display: 'flex', alignItems: 'center', background: 'var(--bg-dark)', borderRadius: '6px', border: '1px solid var(--border)', padding: '0 0.5rem'}}>
            <Search size={18} color="var(--text-dim)" />
            <input 
              value={search} onChange={e => setSearch(e.target.value)}
              list="product-suggestions"
              placeholder="Search products..." 
              style={{flex: 1, background: 'transparent', border: 'none', color: 'white', outline: 'none', fontSize: '0.9rem', padding: '0.5rem'}}
            />
            <datalist id="product-suggestions">
                {productNames.map((name, i) => <option key={i} value={name} />)}
            </datalist>
            {search && (
               <X size={16} color="var(--text-dim)" style={{cursor: 'pointer'}} onClick={() => setSearch('')} />
            )}
          </div>

          <div className="filter-group">
            <span style={{color: 'var(--primary)', fontWeight: 800, fontSize: '0.9rem'}}>
                {filteredAndSortedProducts.length} <span style={{color: 'var(--text-dim)', fontWeight: 500}}>/ {products.length} Items</span>
            </span>
          </div>

          <div className="filter-group" style={{marginLeft: 'auto'}}>
             <button 
                className={`checkbox-btn ${isCompareMode ? 'active' : ''}`} 
                onClick={() => { setIsCompareMode(!isCompareMode); setCompareSelected([]); }}
                style={isCompareMode ? {background: 'var(--warning)', borderColor: 'var(--warning)'} : {}}
             >
                <ListPlus size={16}/> Compare Items
             </button>
          </div>
        </header>

        <header className="top-header" style={{borderTop: 'none', paddingTop: 0}}>
          <div className="filter-group">
            <label>SMART FILTERS:</label>
            <button className={`smart-filter-btn ${smartFilter === 'all' ? 'active' : ''}`} onClick={() => {setSmartFilter('all'); setSortBy('name');}}>All</button>
            <button className={`smart-filter-btn ${smartFilter === 'low' ? 'active' : ''}`} onClick={() => {setSmartFilter('low'); setSortBy('change'); setSortOrder('asc');}}>All Time Low</button>
            <button className={`smart-filter-btn ${smartFilter === 'drop' ? 'active' : ''}`} onClick={() => {setSmartFilter('drop'); setSortBy('change'); setSortOrder('asc');}}>Biggest Drop</button>
            <button className={`smart-filter-btn ${smartFilter === 'great' ? 'active' : ''}`} onClick={() => setSmartFilter('great')}>Great Deal</button>
            <button className={`smart-filter-btn ${smartFilter === 'wait' ? 'active' : ''}`} onClick={() => setSmartFilter('wait')}>Wait</button>
          </div>

          <div className="filter-group" style={{marginLeft: 'auto'}}>
            <label><SlidersHorizontal size={14}/> UNITS:</label>
            {['kg', 'ltr', 'piece'].map(unit => (
              <div key={unit} className={`checkbox-btn ${unitFilters.has(unit) ? 'active' : ''}`} onClick={() => toggleUnit(unit)}>
                {unit.toUpperCase()}
              </div>
            ))}
          </div>

          <div className="filter-group">
            <label><ArrowUpDown size={14}/> SORT:</label>
            <select className="select-box" value={sortBy} onChange={e => setSortBy(e.target.value as any)}>
              <option value="name">Name</option>
              <option value="unit_price">Per Unit Price</option>
              <option value="change">% Change</option>
              <option value="actual_price">Actual Price</option>
            </select>
            <button className="checkbox-btn" onClick={() => setSortOrder(o => o === 'asc' ? 'desc' : 'asc')} title="Toggle Sort Order">
              {sortOrder === 'asc' ? 'ASC' : 'DESC'}
            </button>
          </div>
        </header>

        <div className="product-grid-container">
          <div className="product-grid">
            {filteredAndSortedProducts.map(product => {
              const isSelected = compareSelected.some(p => p.id === product.id);
              return (
              <div 
                 key={product.id} 
                 className={`product-card ${isSelected ? 'compare-selected' : ''}`} 
                 onClick={() => handleProductClick(product)}
              >
                {!isCompareMode && (
                   <button className="fav-btn" onClick={(e) => toggleFavorite(e, product.id)}>
                     <Heart size={14} fill={product.is_favorite ? "var(--danger)" : "none"} color={product.is_favorite ? "var(--danger)" : "var(--text-dim)"} />
                   </button>
                )}
                {isCompareMode && isSelected && (
                   <div style={{position: 'absolute', top: 4, right: 4, background: 'var(--warning)', color: '#000', borderRadius: '50%', width: 20, height: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.7rem', fontWeight: 800, zIndex: 2}}>
                      ✓
                   </div>
                )}
                <div className="product-img-wrapper">
                  <img src={product.image_url} alt={product.name} className="product-img" loading="lazy" />
                </div>
                <div className="product-name" title={product.name}>{product.name}</div>
                <div className="product-prices">
                  <div style={{display: 'flex', alignItems: 'baseline', gap: '0.2rem'}}>
                    <span className="unit-price">{product.unit_price}</span>
                    <span className="unit-desc">/ {product.unit_type}</span>
                  </div>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.2rem'}}>
                    <span className="actual-price">Act: {product.actual_price}</span>
                    {product.change !== 0 && (
                       <span style={{fontSize: '0.7rem', color: product.change < 0 ? 'var(--success)' : 'var(--danger)', fontWeight: 700}}>
                          {product.change > 0 ? '+' : ''}{product.change}%
                       </span>
                    )}
                  </div>
                </div>
              </div>
            )})}
          </div>
        </div>
      </main>

      {/* Floating Compare Action Bar */}
      {isCompareMode && compareSelected.length > 0 && (
         <div className="compare-bar">
            <span style={{fontWeight: 600}}>Selected {compareSelected.length}/5 items</span>
            <button 
              style={{background: 'var(--warning)', border: 'none', padding: '0.5rem 1.5rem', borderRadius: '20px', color: '#000', fontWeight: 800, cursor: 'pointer'}}
              onClick={launchCompareModal}
            >
              COMPARE NOW
            </button>
            <button 
               style={{background: 'transparent', border: '1px solid var(--text-dim)', padding: '0.5rem 1rem', borderRadius: '20px', color: 'var(--text-main)', cursor: 'pointer'}}
               onClick={() => setCompareSelected([])}
            >
              Clear
            </button>
         </div>
      )}

      {/* Single Item History Modal */}
      {selectedProduct && !showCompareModal && (
        <div className="modal-overlay" onClick={() => setSelectedProduct(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="close-hint" onClick={() => setSelectedProduct(null)}>ESC to close</div>
            
            <div className="modal-header">
              <div>
                <div className="modal-title">{selectedProduct.name}</div>
                <div className="modal-subtitle">Pack Size: {selectedProduct.unit} | Tracked per {selectedProduct.unit_type}</div>
              </div>
              <div style={{textAlign: 'right', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.5rem'}}>
                 {stats && <div className={`suggestion-pill ${stats.sugClass}`}>{stats.suggestion}</div>}
                 
                 <div className="date-range-selector">
                    <button className={dateRange === 7 ? 'active' : ''} onClick={() => setDateRange(7)}>7 Days</button>
                    <button className={dateRange === 30 ? 'active' : ''} onClick={() => setDateRange(30)}>30 Days</button>
                    <button className={dateRange === 'all' ? 'active' : ''} onClick={() => setDateRange('all')}>All Time</button>
                 </div>
              </div>
            </div>

            <div className="chart-container">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={filteredHistoryData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorUnit" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--success)" stopOpacity={0.4}/>
                      <stop offset="95%" stopColor="var(--success)" stopOpacity={0}/>
                    </linearGradient>
                    <linearGradient id="colorActual" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--primary)" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="var(--primary)" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="date" stroke="var(--text-dim)" tick={{fontSize: 12}} tickMargin={10} />
                  <YAxis yAxisId="left" stroke="var(--success)" tick={{fontSize: 12}} width={60} label={{ value: 'Per Unit Price', angle: -90, position: 'insideLeft', style: { fill: 'var(--success)' } }} />
                  <YAxis yAxisId="right" orientation="right" stroke="var(--primary)" tick={{fontSize: 12}} width={60} label={{ value: 'Actual Price', angle: 90, position: 'insideRight', style: { fill: 'var(--primary)' } }} />
                  <Tooltip 
                    contentStyle={{backgroundColor: 'var(--bg-card)', borderColor: 'var(--border)', borderRadius: '8px'}}
                    itemStyle={{fontWeight: 700}}
                  />
                  <Legend verticalAlign="top" height={36} />
                  <Area yAxisId="left" type="monotone" dataKey="unit_price" name={`Per ${selectedProduct.unit_type} Price`} stroke="var(--success)" strokeWidth={4} fillOpacity={1} fill="url(#colorUnit)" />
                  <Area yAxisId="right" type="monotone" dataKey="actual_price" name="Actual Pack Price" stroke="var(--primary)" strokeWidth={2} fillOpacity={1} fill="url(#colorActual)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {stats && (
              <div className="stats-grid">
                <div className="stat-box">
                  <div className="label">Current Unit Price</div>
                  <div className="value" style={{color: 'var(--success)'}}>{stats.current.toFixed(2)}</div>
                </div>
                <div className="stat-box">
                  <div className="label">Mean / Average</div>
                  <div className="value">{stats.avg.toFixed(2)}</div>
                </div>
                <div className="stat-box">
                  <div className="label">Period Low</div>
                  <div className="value" style={{color: 'var(--primary)'}}>{stats.min.toFixed(2)}</div>
                </div>
                <div className="stat-box">
                  <div className="label">Period High</div>
                  <div className="value" style={{color: 'var(--danger)'}}>{stats.max.toFixed(2)}</div>
                </div>
                <div className="stat-box">
                  <div className="label">Period Change</div>
                  <div className="value" style={{display: 'flex', alignItems: 'center', gap: '0.2rem', color: stats.change <= 0 ? 'var(--success)' : 'var(--danger)'}}>
                    {stats.change <= 0 ? <TrendingDown size={20}/> : <TrendingUp size={20}/>}
                    {Math.abs(stats.change).toFixed(1)}%
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Multi-Item Compare Modal */}
      {showCompareModal && (
         <div className="modal-overlay" onClick={() => setShowCompareModal(false)}>
         <div className="modal-content" onClick={e => e.stopPropagation()}>
           <div className="close-hint" onClick={() => setShowCompareModal(false)}>ESC to close</div>
           
           <div className="modal-header">
             <div>
               <div className="modal-title">Compare Items</div>
               <div className="modal-subtitle">Tracking multiple items simultaneously (Per Unit Price)</div>
             </div>
           </div>

           <div className="chart-container" style={{flex: '0 0 50%'}}>
             <ResponsiveContainer width="100%" height="100%">
               <LineChart data={compareHistoryData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                 <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                 <XAxis dataKey="date" stroke="var(--text-dim)" tick={{fontSize: 12}} tickMargin={10} />
                 <YAxis stroke="var(--text-dim)" tick={{fontSize: 12}} width={60} />
                 <Tooltip 
                   contentStyle={{backgroundColor: 'var(--bg-card)', borderColor: 'var(--border)', borderRadius: '8px'}}
                   itemStyle={{fontWeight: 700}}
                 />
                 <Legend verticalAlign="top" height={36} />
                 {compareSelected.map((p, idx) => (
                    <Line 
                       key={p.id} 
                       type="monotone" 
                       dataKey={`price_${p.id}`} 
                       name={`${p.name} (/ ${p.unit_type})`} 
                       stroke={COLORS[idx % COLORS.length]} 
                       strokeWidth={3} 
                       dot={{r: 3}}
                    />
                 ))}
               </LineChart>
             </ResponsiveContainer>
           </div>

           <div className="compare-table">
               {compareSelected.map((p, idx) => (
                  <div key={p.id} className="compare-col" style={{borderTop: `4px solid ${COLORS[idx % COLORS.length]}`}}>
                     <img src={p.image_url} alt={p.name} />
                     <div style={{fontWeight: 600, fontSize: '0.85rem', lineHeight: 1.2, height: '2.4em', overflow: 'hidden'}}>{p.name}</div>
                     
                     <div style={{marginTop: '0.5rem'}}>
                        <div style={{fontSize: '0.7rem', color: 'var(--text-dim)'}}>Current Price</div>
                        <div style={{fontSize: '1.2rem', fontWeight: 800, color: 'var(--success)'}}>{p.unit_price} <span style={{fontSize: '0.7rem'}}>/ {p.unit_type}</span></div>
                     </div>
                     
                     <div style={{display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginTop: '0.5rem', borderTop: '1px solid var(--border)', paddingTop: '0.5rem'}}>
                        <span style={{color: 'var(--text-dim)'}}>Avg Price:</span>
                        <span style={{fontWeight: 700}}>{p.avg_price}</span>
                     </div>
                     <div style={{display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem'}}>
                        <span style={{color: 'var(--text-dim)'}}>All Time Low:</span>
                        <span style={{fontWeight: 700, color: 'var(--primary)'}}>{p.min_price}</span>
                     </div>
                     <div style={{display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem'}}>
                        <span style={{color: 'var(--text-dim)'}}>Change:</span>
                        <span style={{fontWeight: 700, color: p.change <= 0 ? 'var(--success)' : 'var(--danger)'}}>
                           {p.change > 0 ? '+' : ''}{p.change}%
                        </span>
                     </div>
                  </div>
               ))}
           </div>
           
         </div>
       </div>
      )}

    </div>
  );
}

export default App;
