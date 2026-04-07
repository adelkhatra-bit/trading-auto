"""
mt5_bridge.py — Bridge local MetaTrader5 → API REST (port 5001)
Lancer : python mt5_bridge.py
Dépendances : pip install MetaTrader5 flask flask-cors
"""

import json
import time
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

MT5_AVAILABLE = False
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    print("[WARN] MetaTrader5 package not installed. pip install MetaTrader5")

PORT = 5001
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json"
}

# ── State ─────────────────────────────────────────────────────────────────────
_connected = False
_symbols_cache = []
_symbols_ts = 0
SYMBOLS_TTL = 60  # seconds

def ensure_connected():
    global _connected
    if not MT5_AVAILABLE:
        return False
    if not _connected:
        _connected = mt5.initialize()
        if _connected:
            info = mt5.terminal_info()
            print(f"[MT5] Connected — build {info.build if info else '?'}")
        else:
            print(f"[MT5] Connection failed: {mt5.last_error()}")
    return _connected

# ── Handlers ──────────────────────────────────────────────────────────────────

def handle_status():
    if not MT5_AVAILABLE:
        return {"ok": True, "connected": False, "reason": "MetaTrader5 package not installed", "hint": "pip install MetaTrader5"}
    ok = ensure_connected()
    if ok:
        info = mt5.terminal_info()
        acct = mt5.account_info()
        return {
            "ok": True,
            "connected": True,
            "build": info.build if info else None,
            "company": info.company if info else None,
            "account": acct.login if acct else None,
            "server": acct.server if acct else None,
            "currency": acct.currency if acct else None
        }
    return {"ok": False, "connected": False, "error": str(mt5.last_error())}

def handle_symbols(query=""):
    global _symbols_cache, _symbols_ts
    now = time.time()

    if not ensure_connected():
        # Return a useful offline list for testing
        return {"ok": False, "connected": False, "symbols": FALLBACK_SYMBOLS, "source": "fallback"}

    if _symbols_cache and (now - _symbols_ts) < SYMBOLS_TTL:
        filtered = filter_symbols(_symbols_cache, query)
        return {"ok": True, "symbols": filtered, "total": len(_symbols_cache), "cached": True}

    raw = mt5.symbols_get()
    if raw is None:
        return {"ok": False, "error": str(mt5.last_error()), "symbols": FALLBACK_SYMBOLS, "source": "fallback"}

    _symbols_cache = [
        {
            "name": s.name,
            "description": s.description,
            "digits": s.digits,
            "category": categorize(s.name),
            "visible": s.visible,
            "spread": s.spread,
            "point": s.point
        }
        for s in raw
        if s.visible  # only visible symbols
    ]
    _symbols_ts = now

    filtered = filter_symbols(_symbols_cache, query)
    return {"ok": True, "symbols": filtered, "total": len(_symbols_cache)}

def filter_symbols(symbols, query):
    if not query:
        return symbols[:200]  # Cap at 200 if no query
    q = query.upper()
    # Score and sort
    scored = []
    for s in symbols:
        n = s["name"].upper()
        d = s.get("description", "").upper()
        score = 0
        if n == q: score = 100
        elif n.startswith(q): score = 80
        elif q in n: score = 60
        elif q in d: score = 30
        if score > 0:
            scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:20]]

def categorize(name):
    n = name.upper()
    if any(x in n for x in ["XAU", "XAG", "GOLD", "SILVER"]): return "metal"
    if any(x in n for x in ["BTC", "ETH", "LTC", "XRP", "DOGE"]): return "crypto"
    if any(x in n for x in ["US30", "US500", "NAS", "DAX", "GER", "UK100", "JP225", "CAC"]): return "index"
    if any(x in n for x in ["OIL", "BRENT", "WTI", "GAS"]): return "commodity"
    if len(n) == 6 and n[:3].isalpha() and n[3:].isalpha(): return "forex"
    return "other"

def handle_price(symbol):
    if not ensure_connected():
        return {"ok": False, "connected": False, "symbol": symbol}
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {"ok": False, "error": f"No tick for {symbol}", "symbol": symbol}
    info = mt5.symbol_info(symbol)
    return {
        "ok": True,
        "symbol": symbol,
        "bid": tick.bid,
        "ask": tick.ask,
        "price": (tick.bid + tick.ask) / 2,
        "spread": round((tick.ask - tick.bid) / (info.point if info else 0.0001), 1),
        "time": tick.time,
        "ts": datetime.utcnow().isoformat()
    }

def handle_match(name, price_hint=None, category_hint=None):
    """Intelligent symbol matching — returns ranked candidates."""
    symbols_resp = handle_symbols(name)
    candidates = symbols_resp.get("symbols", [])

    # If we have a price hint, score by price proximity too
    if price_hint and candidates:
        def price_score(s):
            tick_resp = handle_price(s["name"]) if MT5_AVAILABLE and _connected else {}
            p = tick_resp.get("price", 0)
            if not p: return 0
            hint = float(price_hint)
            ratio = abs(p - hint) / max(hint, 1)
            return 1 - min(ratio, 1)  # closer = higher score

        # Only price-score top 5 to avoid too many MT5 calls
        for s in candidates[:5]:
            s["price_match_score"] = price_score(s)
        candidates.sort(key=lambda s: -(s.get("price_match_score", 0)))

    return {
        "ok": True,
        "query": name,
        "candidates": candidates[:10]
    }

def handle_klines(symbol, timeframe="H1", count=200):
    """Get OHLCV bars for chart rendering."""
    if not ensure_connected():
        return {"ok": False, "connected": False}

    TF_MAP = {
        "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1
    } if MT5_AVAILABLE else {}

    tf = TF_MAP.get(timeframe.upper(), mt5.TIMEFRAME_H1 if MT5_AVAILABLE else None)
    if tf is None:
        return {"ok": False, "error": f"Unknown timeframe {timeframe}"}

    bars = mt5.copy_rates_from_pos(symbol, tf, 0, min(count, 500))
    if bars is None or len(bars) == 0:
        return {"ok": False, "error": f"No bars for {symbol} {timeframe}"}

    return {
        "ok": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": [
            {
                "time": int(b["time"]),
                "open": float(b["open"]),
                "high": float(b["high"]),
                "low": float(b["low"]),
                "close": float(b["close"]),
                "volume": int(b["tick_volume"])
            }
            for b in bars
        ]
    }

# ── Fallback symbols (when MT5 offline) ──────────────────────────────────────
FALLBACK_SYMBOLS = [
    {"name":"XAUUSD","description":"Gold vs US Dollar","category":"metal","digits":2},
    {"name":"EURUSD","description":"Euro vs US Dollar","category":"forex","digits":5},
    {"name":"GBPUSD","description":"British Pound vs US Dollar","category":"forex","digits":5},
    {"name":"USDJPY","description":"US Dollar vs Japanese Yen","category":"forex","digits":3},
    {"name":"USDCHF","description":"US Dollar vs Swiss Franc","category":"forex","digits":5},
    {"name":"AUDUSD","description":"Australian Dollar vs US Dollar","category":"forex","digits":5},
    {"name":"NZDUSD","description":"New Zealand Dollar vs US Dollar","category":"forex","digits":5},
    {"name":"BTCUSD","description":"Bitcoin vs US Dollar","category":"crypto","digits":2},
    {"name":"ETHUSD","description":"Ethereum vs US Dollar","category":"crypto","digits":2},
    {"name":"US30","description":"Dow Jones 30","category":"index","digits":2},
    {"name":"US500","description":"S&P 500","category":"index","digits":2},
    {"name":"NAS100","description":"Nasdaq 100","category":"index","digits":2},
    {"name":"GER40","description":"DAX 40","category":"index","digits":2},
    {"name":"XAGUSD","description":"Silver vs US Dollar","category":"metal","digits":3},
    {"name":"USOIL","description":"WTI Crude Oil","category":"commodity","digits":2},
]

# ── HTTP Server ───────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress default logging

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        path = parsed.path

        if path == "/mt5/status":
            self.send_json(handle_status())

        elif path == "/mt5/symbols":
            q = params.get("q", [""])[0]
            self.send_json(handle_symbols(q))

        elif path == "/mt5/match":
            name = params.get("name", [""])[0]
            price = params.get("price", [None])[0]
            category = params.get("category", [None])[0]
            self.send_json(handle_match(name, price, category))

        elif path == "/mt5/price":
            sym = params.get("symbol", ["XAUUSD"])[0]
            self.send_json(handle_price(sym))

        elif path == "/mt5/klines":
            sym = params.get("symbol", ["XAUUSD"])[0]
            tf  = params.get("tf", ["H1"])[0]
            cnt = int(params.get("count", ["200"])[0])
            self.send_json(handle_klines(sym, tf, cnt))

        else:
            self.send_json({"ok": False, "error": "Not found", "path": path}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/mt5/send":
            # Push price to server.js /mt5
            import urllib.request
            payload = json.dumps(body).encode()
            req = urllib.request.Request(
                "http://127.0.0.1:4000/mt5",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=3) as resp:
                    resp_data = json.loads(resp.read())
                self.send_json({"ok": True, "forwarded": resp_data})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)})
        else:
            self.send_json({"ok": False, "error": "Not found"}, 404)


def run():
    ensure_connected()
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[MT5 Bridge] Running on http://127.0.0.1:{PORT}")
    print(f"[MT5 Bridge] MT5 available: {MT5_AVAILABLE}, connected: {_connected}")
    print(f"[MT5 Bridge] Endpoints: /mt5/status /mt5/symbols /mt5/match /mt5/price /mt5/klines")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[MT5 Bridge] Stopped.")
        if MT5_AVAILABLE:
            mt5.shutdown()

if __name__ == "__main__":
    run()
