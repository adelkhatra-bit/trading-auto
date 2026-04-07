// mt5-symbols.js — Complete MT5 Symbol Library with Real-Time Data Generator
'use strict';

const MT5Symbols = {
  // Category: FOREX MAJORS (14)
  MAJORS: [
    { code: 'EURUSD', name: 'EUR/USD', cat: 'Forex', decimal: 5, minSize: 0.01, spread: 0.00015 },
    { code: 'GBPUSD', name: 'GBP/USD', cat: 'Forex', decimal: 5, minSize: 0.01, spread: 0.00025 },
    { code: 'USDCAD', name: 'USD/CAD', cat: 'Forex', decimal: 5, minSize: 0.01, spread: 0.00020 },
    { code: 'USDJPY', name: 'USD/JPY', cat: 'Forex', decimal: 3, minSize: 0.01, spread: 0.015 },
    { code: 'AUDUSD', name: 'AUD/USD', cat: 'Forex', decimal: 5, minSize: 0.01, spread: 0.00025 },
    { code: 'NZDUSD', name: 'NZD/USD', cat: 'Forex', decimal: 5, minSize: 0.01, spread: 0.00030 },
    { code: 'USDCHF', name: 'USD/CHF', cat: 'Forex', decimal: 5, minSize: 0.01, spread: 0.00020 },
    { code: 'EURJPY', name: 'EUR/JPY', cat: 'Forex', decimal: 3, minSize: 0.01, spread: 0.020 },
    { code: 'GBPJPY', name: 'GBP/JPY', cat: 'Forex', decimal: 3, minSize: 0.01, spread: 0.030 },
    { code: 'EURGBP', name: 'EUR/GBP', cat: 'Forex', decimal: 5, minSize: 0.01, spread: 0.00015 },
    { code: 'EURCHF', name: 'EUR/CHF', cat: 'Forex', decimal: 5, minSize: 0.01, spread: 0.00020 },
    { code: 'AUDNZD', name: 'AUD/NZD', cat: 'Forex', decimal: 5, minSize: 0.01, spread: 0.00040 },
    { code: 'AUDCAD', name: 'AUD/CAD', cat: 'Forex', decimal: 5, minSize: 0.01, spread: 0.00040 },
    { code: 'AUDCHF', name: 'AUD/CHF', cat: 'Forex', decimal: 5, minSize: 0.01, spread: 0.00035 }
  ],
  
  // Category: COMMODITIES (8)
  COMMODITIES: [
    { code: 'XAUUSD', name: 'Gold (XAU/USD)', cat: 'Commodity', decimal: 2, minSize: 0.01, spread: 0.30 },
    { code: 'XAGUSD', name: 'Silver (XAG/USD)', cat: 'Commodity', decimal: 3, minSize: 0.01, spread: 0.005 },
    { code: 'XPTUSD', name: 'Platinum (XPT/USD)', cat: 'Commodity', decimal: 2, minSize: 0.01, spread: 0.50 },
    { code: 'XPDUSD', name: 'Palladium (XPD/USD)', cat: 'Commodity', decimal: 2, minSize: 0.01, spread: 2.00 },
    { code: 'UKOUSD', name: 'Oil Brent (UKO/USD)', cat: 'Commodity', decimal: 3, minSize: 0.01, spread: 0.02 },
    { code: 'WTIUSD', name: 'Oil WTI (WTI/USD)', cat: 'Commodity', decimal: 3, minSize: 0.01, spread: 0.02 },
    { code: 'NATGAS', name: 'Natural Gas', cat: 'Commodity', decimal: 3, minSize: 0.01, spread: 0.010 },
    { code: 'COPPER', name: 'Copper', cat: 'Commodity', decimal: 4, minSize: 0.01, spread: 0.00050 }
  ],
  
  // Category: INDICES (10)
  INDICES: [
    { code: 'US30', name: 'Dow Jones 30', cat: 'Index', decimal: 1, minSize: 0.01, spread: 2.0 },
    { code: 'SPX500', name: 'S&P 500', cat: 'Index', decimal: 1, minSize: 0.01, spread: 1.0 },
    { code: 'NAS100', name: 'Nasdaq 100', cat: 'Index', decimal: 1, minSize: 0.01, spread: 2.0 },
    { code: 'UK100', name: 'FTSE 100', cat: 'Index', decimal: 1, minSize: 0.01, spread: 2.0 },
    { code: 'GER30', name: 'DAX 30', cat: 'Index', decimal: 1, minSize: 0.01, spread: 1.0 },
    { code: 'FRA40', name: 'CAC 40', cat: 'Index', decimal: 1, minSize: 0.01, spread: 3.0 },
    { code: 'HK50', name: 'Hang Seng', cat: 'Index', decimal: 0, minSize: 1, spread: 5 },
    { code: 'JP225', name: 'Nikkei 225', cat: 'Index', decimal: 0, minSize: 0.01, spread: 10 },
    { code: 'CN50', name: 'Shanghai Composite', cat: 'Index', decimal: 0, minSize: 0.01, spread: 20 },
    { code: 'INDIA50', name: 'SENSEX 50', cat: 'Index', decimal: 0, minSize: 0.01, spread: 50 }
  ],
  
  // Category: CRYPTOCURRENCIES (6)
  CRYPTO: [
    { code: 'BTCUSD', name: 'Bitcoin', cat: 'Crypto', decimal: 2, minSize: 0.001, spread: 1.0 },
    { code: 'ETHUSD', name: 'Ethereum', cat: 'Crypto', decimal: 2, minSize: 0.01, spread: 0.10 },
    { code: 'LTCUSD', name: 'Litecoin', cat: 'Crypto', decimal: 2, minSize: 0.01, spread: 0.05 },
    { code: 'BCHUSD', name: 'Bitcoin Cash', cat: 'Crypto', decimal: 2, minSize: 0.01, spread: 0.10 },
    { code: 'RIPPLE', name: 'Ripple', cat: 'Crypto', decimal: 5, minSize: 1, spread: 0.0001 },
    { code: 'DOGEUSD', name: 'Dogecoin', cat: 'Crypto', decimal: 5, minSize: 1, spread: 0.00001 }
  ],
  
  // Get all symbols flat
  getAllSymbols() {
    return [
      ...this.MAJORS,
      ...this.COMMODITIES,
      ...this.INDICES,
      ...this.CRYPTO
    ];
  },
  
  // Find symbol by code
  getSymbol(code) {
    const all = this.getAllSymbols();
    return all.find(s => s.code === code);
  },
  
  // Get symbols by category
  getByCategory(category) {
    return this[category] || [];
  },
  
  // Generate realistic real-time data for symbol
  generateRealtimeData(symbolCode, basePrice) {
    const sym = this.getSymbol(symbolCode);
    if (!sym) return null;
    
    // Realistic price with slight volatility
    const volatility = Math.random() * 0.02 - 0.01;  // ±1%
    const price = basePrice * (1 + volatility);
    const bid = price - sym.spread;
    const ask = price + sym.spread;
    
    // Generate 24 candlesticks (H1)
    const candles = [];
    const now = Date.now();
    for (let i = 23; i >= 0; i--) {
      const time = new Date(now - i * 3600000);
      const open = basePrice + (Math.random() - 0.5) * basePrice * 0.005;
      const close = open + (Math.random() - 0.5) * basePrice * 0.005;
      const high = Math.max(open, close) + Math.abs(Math.random() - 0.5) * basePrice * 0.003;
      const low = Math.min(open, close) - Math.abs(Math.random() - 0.5) * basePrice * 0.003;
      
      candles.push({
        time: time.toISOString(),
        open: parseFloat(open.toFixed(sym.decimal)),
        high: parseFloat(high.toFixed(sym.decimal)),
        low: parseFloat(low.toFixed(sym.decimal)),
        close: parseFloat(close.toFixed(sym.decimal)),
        volume: Math.floor(Math.random() * 1000000 + 100000)
      });
    }
    
    return {
      code: symbolCode,
      name: sym.name,
      category: sym.cat,
      price: parseFloat(price.toFixed(sym.decimal)),
      bid: parseFloat(bid.toFixed(sym.decimal)),
      ask: parseFloat(ask.toFixed(sym.decimal)),
      spread: sym.spread,
      volume: Math.floor(Math.random() * 5000000 + 500000),
      decimal: sym.decimal,
      minSize: sym.minSize,
      candles: candles,
      timestamp: new Date().toISOString()
    };
  }
};

// Export
window.MT5Symbols = MT5Symbols;
