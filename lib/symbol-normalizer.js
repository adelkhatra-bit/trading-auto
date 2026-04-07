// Symbol normalizer — handles broker variants (XAUUSD.a, GOLDmicro, etc.)

const PROFILES = {
  // ─── GOLD / METALS ────────────────────────────────────────────────────────
  XAUUSD:  { canonical:'XAUUSD',  type:'metal',  category:'gold',   digits:2, contractSize:100,   tickSize:0.01,  tickValue:1.00,  pip:0.1,  slPct:0.004, tpPct:0.012 },
  XAGUSD:  { canonical:'XAGUSD',  type:'metal',  category:'silver', digits:3, contractSize:5000,  tickSize:0.001, tickValue:5.00,  pip:0.01, slPct:0.006, tpPct:0.018 },
  // ─── INDICES ──────────────────────────────────────────────────────────────
  NAS100:  { canonical:'NAS100',  type:'index',  category:'nasdaq', digits:1, contractSize:1,     tickSize:0.25,  tickValue:0.25,  pip:1,    slPct:0.005, tpPct:0.015 },
  US500:   { canonical:'US500',   type:'index',  category:'sp500',  digits:1, contractSize:1,     tickSize:0.25,  tickValue:0.25,  pip:1,    slPct:0.005, tpPct:0.015 },
  US30:    { canonical:'US30',    type:'index',  category:'dow',    digits:1, contractSize:1,     tickSize:1,     tickValue:1,     pip:1,    slPct:0.005, tpPct:0.015 },
  DE40:    { canonical:'DE40',    type:'index',  category:'dax',    digits:1, contractSize:1,     tickSize:0.25,  tickValue:0.25,  pip:1,    slPct:0.005, tpPct:0.015 },
  // ─── CRYPTO ───────────────────────────────────────────────────────────────
  BTCUSD:  { canonical:'BTCUSD',  type:'crypto', category:'btc',    digits:2, contractSize:1,     tickSize:0.01,  tickValue:0.01,  pip:1,    slPct:0.012, tpPct:0.030 },
  ETHUSD:  { canonical:'ETHUSD',  type:'crypto', category:'eth',    digits:2, contractSize:1,     tickSize:0.01,  tickValue:0.01,  pip:0.1,  slPct:0.015, tpPct:0.040 },
  // ─── FOREX MAJORS ─────────────────────────────────────────────────────────
  EURUSD:  { canonical:'EURUSD',  type:'forex',  category:'major',  digits:5, contractSize:100000,tickSize:0.00001,tickValue:1.00, pip:0.0001,slPct:0.002, tpPct:0.006 },
  GBPUSD:  { canonical:'GBPUSD',  type:'forex',  category:'major',  digits:5, contractSize:100000,tickSize:0.00001,tickValue:1.00, pip:0.0001,slPct:0.002, tpPct:0.006 },
  USDJPY:  { canonical:'USDJPY',  type:'forex',  category:'major',  digits:3, contractSize:100000,tickSize:0.001, tickValue:0.01,  pip:0.01,  slPct:0.002, tpPct:0.006 },
  AUDUSD:  { canonical:'AUDUSD',  type:'forex',  category:'major',  digits:5, contractSize:100000,tickSize:0.00001,tickValue:1.00, pip:0.0001,slPct:0.002, tpPct:0.006 },
  USDCAD:  { canonical:'USDCAD',  type:'forex',  category:'major',  digits:5, contractSize:100000,tickSize:0.00001,tickValue:0.75, pip:0.0001,slPct:0.002, tpPct:0.006 },
  USDCHF:  { canonical:'USDCHF',  type:'forex',  category:'major',  digits:5, contractSize:100000,tickSize:0.00001,tickValue:1.10, pip:0.0001,slPct:0.002, tpPct:0.006 },
  NZDUSD:  { canonical:'NZDUSD',  type:'forex',  category:'major',  digits:5, contractSize:100000,tickSize:0.00001,tickValue:1.00, pip:0.0001,slPct:0.002, tpPct:0.006 },
  EURGBP:  { canonical:'EURGBP',  type:'forex',  category:'cross',  digits:5, contractSize:100000,tickSize:0.00001,tickValue:1.25, pip:0.0001,slPct:0.002, tpPct:0.006 },
  EURJPY:  { canonical:'EURJPY',  type:'forex',  category:'cross',  digits:3, contractSize:100000,tickSize:0.001, tickValue:0.01,  pip:0.01,  slPct:0.002, tpPct:0.006 },
  GBPJPY:  { canonical:'GBPJPY',  type:'forex',  category:'cross',  digits:3, contractSize:100000,tickSize:0.001, tickValue:0.01,  pip:0.01,  slPct:0.002, tpPct:0.006 },
};

// Broker suffix patterns → canonical base
const CANONICAL_PATTERNS = [
  { test: s => /XAU|GOLD/i.test(s) && !/XAGUSD/.test(s),     canonical: 'XAUUSD' },
  { test: s => /XAG|SILVER/i.test(s),                         canonical: 'XAGUSD' },
  { test: s => /NAS100|NASDAQ|US100/i.test(s),                 canonical: 'NAS100' },
  { test: s => /US500|SPX|SP500|S&P/i.test(s),                canonical: 'US500'  },
  { test: s => /US30|DOW|DJI/i.test(s),                       canonical: 'US30'   },
  { test: s => /DE40|DAX|GER40/i.test(s),                     canonical: 'DE40'   },
  { test: s => /^BTC/i.test(s),                               canonical: 'BTCUSD' },
  { test: s => /^ETH/i.test(s),                               canonical: 'ETHUSD' },
  { test: s => /EURUSD/i.test(s),                             canonical: 'EURUSD' },
  { test: s => /GBPUSD/i.test(s),                             canonical: 'GBPUSD' },
  { test: s => /USDJPY/i.test(s),                             canonical: 'USDJPY' },
  { test: s => /AUDUSD/i.test(s),                             canonical: 'AUDUSD' },
  { test: s => /USDCAD/i.test(s),                             canonical: 'USDCAD' },
  { test: s => /USDCHF/i.test(s),                             canonical: 'USDCHF' },
  { test: s => /NZDUSD/i.test(s),                             canonical: 'NZDUSD' },
  { test: s => /EURGBP/i.test(s),                             canonical: 'EURGBP' },
  { test: s => /EURJPY/i.test(s),                             canonical: 'EURJPY' },
  { test: s => /GBPJPY/i.test(s),                             canonical: 'GBPJPY' },
];

const DEFAULT_PROFILE = { canonical: null, type: 'unknown', category: 'unknown', digits: 5, contractSize: 100000, tickSize: 0.00001, tickValue: 1, pip: 0.0001, slPct: 0.003, tpPct: 0.009 };

function normalizeSymbol(rawSymbol) {
  if (!rawSymbol) return { ...DEFAULT_PROFILE, broker_symbol: rawSymbol, canonical: rawSymbol };
  const clean = rawSymbol.toString().trim();
  // Direct lookup (exact match after stripping common broker suffixes)
  const stripped = clean.replace(/[._\-](a|b|c|pro|micro|mini|nano|cash|ecn|stp|raw|vip|m|n|x)$/i, '').toUpperCase();
  if (PROFILES[stripped]) {
    return { ...PROFILES[stripped], broker_symbol: clean };
  }
  // Pattern match
  for (const p of CANONICAL_PATTERNS) {
    if (p.test(clean)) {
      const profile = PROFILES[p.canonical] || DEFAULT_PROFILE;
      return { ...profile, canonical: p.canonical, broker_symbol: clean };
    }
  }
  return { ...DEFAULT_PROFILE, canonical: stripped, broker_symbol: clean };
}

function formatPrice(price, profile) {
  if (!profile || !price) return Number(price).toFixed(5);
  return Number(price).toFixed(profile.digits);
}

// Calculate proper SL/TP distances based on ATR or profile
function calcLevels(price, direction, profile, atr = null) {
  const p = profile || DEFAULT_PROFILE;
  // Use ATR*1.5 for SL, ATR*3.5 for TP if available; else use % from profile
  const slDist = atr ? atr * 1.5 : price * p.slPct;
  const tpDist = atr ? atr * 3.5 : price * p.tpPct;
  const sl = direction === 'LONG' ? price - slDist : price + slDist;
  const tp = direction === 'LONG' ? price + tpDist : price - tpDist;
  return {
    entry: formatPrice(price, p),
    sl:    formatPrice(sl, p),
    tp:    formatPrice(tp, p),
    slPips: (slDist / p.pip).toFixed(0),
    tpPips: (tpDist / p.pip).toFixed(0),
    rrRatio: (tpDist / slDist).toFixed(1),
  };
}

module.exports = { normalizeSymbol, formatPrice, calcLevels, PROFILES };
