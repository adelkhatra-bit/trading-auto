#!/usr/bin/env python3
"""
MT5 Bridge — Connexion réelle MetaTrader 5 pour Trading Auto Extension
Version 2.0 — Real-time price and candlestick data

Requires: pip install metatrader5, Flask, python-dotenv
"""

import os
import sys
import json
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
import threading
import time

try:
    import metatrader5 as mt5
    from flask import Flask, request, jsonify
    from flask_cors import CORS
except ImportError:
    print("❌ Dependencies missing. Install: pip install metatrader5 Flask flask-cors")
    sys.exit(1)

# ─── Configuration ───────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

if os.getenv('ALLOW_LEGACY_BRIDGE', '0') != '1':
    print('Legacy bridge disabled: single environment mode uses only http://127.0.0.1:4000')
    sys.exit(0)

PORT = 4000
MT5_STATUS = {
    "connected": False,
    "initialized": False,
    "account": None,
    "balance": 0,
    "error": None,
    "last_update": None
}

# Cache for symbol data (avoid repeated MT5 calls)
SYMBOL_CACHE = {}
CACHE_TTL = 300  # 5 minutes

# MT5 Symbol mapping (normalization)
SYMBOL_MAP = {
    'XAUUSD': 'XAUUSD',    # Gold
    'GOLD': 'XAUUSD',
    'EURUSD': 'EURUSD',
    'GBPUSD': 'GBPUSD',
    'USDJPY': 'USDJPY',
    'USDCAD': 'USDCAD',
    'NAS100': 'US100',     # Nasdaq 100
    'SPX500': 'US500',     # S&P 500
    'DAX': 'DAX40',
    'BTC': 'BTCUSD',
    'ETH': 'ETHUSD',
    'OIL': 'XTIUSD',       # WTI Crude
    'CRUDE': 'XTIUSD',
    'GAS': 'XNGUSD',       # Natural Gas
}


# ─── MT5 Connection ────────────────────────────────────────────────────────
def connect_mt5():
    """Initialize MT5 connection"""
    global MT5_STATUS
    try:
        if not mt5.initialize():
            raise Exception(f"MT5 initialization failed: {mt5.last_error()}")
        
        account = mt5.account_info()
        if account is None:
            raise Exception("Cannot get account info from MT5")
        
        MT5_STATUS.update({
            "connected": True,
            "initialized": True,
            "account": {
                "name": account.name,
                "server": account.server,
                "login": account.login,
                "leverage": account.leverage
            },
            "balance": float(account.balance),
            "last_update": datetime.now().isoformat(),
            "error": None
        })
        
        logger.info(f"✅ MT5 Connected: {account.server} ({account.login})")
        return True
    except Exception as e:
        MT5_STATUS.update({
            "connected": False,
            "initialized": False,
            "error": str(e),
            "last_update": datetime.now().isoformat()
        })
        logger.error(f"❌ MT5 Connection Error: {e}")
        return False


def normalize_symbol(symbol: str) -> str:
    """Convert user input to MT5 symbol"""
    upper = symbol.upper().strip()
    return SYMBOL_MAP.get(upper, upper)


def get_symbol_info(symbol: str) -> Optional[Dict]:
    """Get symbol info from MT5 with cache"""
    cache_key = f"info_{symbol}"
    
    if cache_key in SYMBOL_CACHE:
        cached, timestamp = SYMBOL_CACHE[cache_key]
        if time.time() - timestamp < CACHE_TTL:
            return cached
    
    if not MT5_STATUS["connected"]:
        logger.warn(f"MT5 not connected, cannot get {symbol}")
        return None
    
    try:
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.warn(f"Symbol not found: {symbol}")
            return None
        
        result = {
            "symbol": info.name,
            "bid": float(info.bid),
            "ask": float(info.ask),
            "last": float(info.last) if info.last else None,
            "volume": int(info.volume) if info.volume else 0,
            "volume_real": float(info.volume_real) if info.volume_real else 0,
            "point": float(info.point),
            "digits": int(info.digits),
            "spread": float(info.spread),
            "spread_real": float(info.spread_real) if hasattr(info, 'spread_real') else None,
            "tick_size": float(info.tick_size),
            "trade_mode": str(info.trade_mode),
            "type": str(info.type),
            "description": info.description,
            "path": info.path
        }
        
        # Cache result
        SYMBOL_CACHE[cache_key] = (result, time.time())
        return result
    except Exception as e:
        logger.error(f"Error getting symbol info {symbol}: {e}")
        return None


def get_quotes(symbol: str) -> Optional[Dict]:
    """Get current bid/ask quotes"""
    info = get_symbol_info(symbol)
    if info is None:
        return None
    
    return {
        "ok": True,
        "symbol": symbol,
        "bid": info["bid"],
        "ask": info["ask"],
        "spread": info["spread"],
        "volume": info["volume"],
        "digits": info["digits"],
        "timestamp": datetime.now().isoformat()
    }


def get_candlesticks(symbol: str, timeframe: str = "H1", count: int = 200) -> Optional[List[Dict]]:
    """Get OHLCV candlestick data from MT5"""
    if not MT5_STATUS["connected"]:
        logger.warn(f"MT5 not connected, cannot get candlesticks for {symbol}")
        return None
    
    try:
        # Map timeframe string to mt5 constants
        tf_map = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H2': mt5.TIMEFRAME_H2,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
            'W1': mt5.TIMEFRAME_W1,
            'MN1': mt5.TIMEFRAME_MN1
        }
        
        mt5_tf = tf_map.get(timeframe.upper(), mt5.TIMEFRAME_H1)
        
        # Fetch rates
        rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, count)
        if rates is None or len(rates) == 0:
            logger.warn(f"No candlestick data for {symbol} {timeframe}")
            return None
        
        # Convert to readable format
        result = []
        for rate in rates:
            result.append({
                "time": int(rate['time']),
                "timestamp": datetime.fromtimestamp(rate['time']).isoformat(),
                "open": float(rate['open']),
                "high": float(rate['high']),
                "low": float(rate['low']),
                "close": float(rate['close']),
                "volume": int(rate['tick_volume']),
                "spread": int(rate['spread']) if 'spread' in rate.dtype.names else 0
            })
        
        return result
    except Exception as e:
        logger.error(f"Error getting candlesticks {symbol} {timeframe}: {e}\n{traceback.format_exc()}")
        return None


# ─── Flask API Routes ────────────────────────────────────────────────────────

@app.route('/mt5/status', methods=['GET'])
def status():
    """Get MT5 connection status"""
    return jsonify(MT5_STATUS)


@app.route('/mt5/price', methods=['GET'])
def get_price():
    """Get current price for symbol
    Query params: ?symbol=GOLD&digits=2
    """
    try:
        symbol = request.args.get('symbol', 'XAUUSD').upper()
        norm_symbol = normalize_symbol(symbol)
        
        quote = get_quotes(norm_symbol)
        if quote is None:
            return jsonify({
                "ok": False,
                "error": f"Symbol {symbol} not found or MT5 not connected",
                "symbol": symbol
            }), 404
        
        return jsonify(quote)
    except Exception as e:
        logger.error(f"Error in /mt5/price: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/mt5/symbols', methods=['GET'])
def get_symbols():
    """Search symbols
    Query params: ?q=EUR (partial match)
    """
    try:
        query = request.args.get('q', '').upper()
        
        if not MT5_STATUS["connected"]:
            return jsonify({
                "ok": False,
                "error": "MT5 not connected",
                "symbols": []
            })
        
        # Get all symbols matching query
        symbols_response = mt5.symbols_get()
        if symbols_response is None:
            return jsonify({"ok": False, "error": "Cannot get symbols", "symbols": []})
        
        # Filter by query
        matching = []
        for sym in symbols_response:
            if query in sym.name or query in (sym.description or ''):
                matching.append({
                    "name": sym.name,
                    "description": sym.description,
                    "type": str(sym.type),
                    "bid": float(sym.bid),
                    "ask": float(sym.ask),
                    "digits": int(sym.digits)
                })
                if len(matching) >= 20:  # Limit results
                    break
        
        return jsonify({
            "ok": True,
            "query": query,
            "count": len(matching),
            "symbols": matching
        })
    except Exception as e:
        logger.error(f"Error in /mt5/symbols: {e}")
        return jsonify({"ok": False, "error": str(e), "symbols": []}), 500


@app.route('/mt5/klines', methods=['GET'])
def get_klines():
    """Get candlestick data
    Query params: ?symbol=EURUSD&tf=H1&count=200
    """
    try:
        symbol = request.args.get('symbol', 'EURUSD').upper()
        timeframe = request.args.get('tf', 'H1').upper()
        count = min(int(request.args.get('count', '200')), 1000)  # Max 1000
        
        norm_symbol = normalize_symbol(symbol)
        klines = get_candlesticks(norm_symbol, timeframe, count)
        
        if klines is None:
            return jsonify({
                "ok": False,
                "error": f"Cannot get klines for {symbol}",
                "symbol": symbol,
                "timeframe": timeframe
            }), 404
        
        return jsonify({
            "ok": True,
            "symbol": symbol,
            "timeframe": timeframe,
            "count": len(klines),
            "klines": klines
        })
    except Exception as e:
        logger.error(f"Error in /mt5/klines: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/mt5/match', methods=['GET'])
def match_symbol():
    """Match user input to MT5 symbol
    Query params: ?name=gold&price=2400&category=metals
    """
    try:
        name = request.args.get('name', '').upper()
        
        # Try direct lookup first
        norm = normalize_symbol(name)
        if norm != name:
            quote = get_quotes(norm)
            if quote:
                return jsonify({
                    "ok": True,
                    "matched": norm,
                    "quote": quote
                })
        
        # Fall back to search
        symbols_response = mt5.symbols_get()
        if symbols_response is None:
            return jsonify({
                "ok": False,
                "error": "Cannot search symbols",
                "candidates": []
            })
        
        candidates = []
        for sym in symbols_response:
            if name in sym.name or name in (sym.description or ''):
                candidates.append({
                    "symbol": sym.name,
                    "description": sym.description,
                    "bid": float(sym.bid),
                    "ask": float(sym.ask),
                    "digits": int(sym.digits)
                })
                if len(candidates) >= 10:
                    break
        
        return jsonify({
            "ok": True,
            "query": name,
            "candidates": candidates,
            "count": len(candidates)
        })
    except Exception as e:
        logger.error(f"Error in /mt5/match: {e}")
        return jsonify({"ok": False, "error": str(e), "candidates": []}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        "status": "ok",
        "mt5_connected": MT5_STATUS["connected"],
        "timestamp": datetime.now().isoformat()
    })


# ─── Startup ─────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    logger.info("🚀 Starting MT5 Bridge...")
    
    # Try to connect to MT5
    logger.info("Attempting MT5 connection...")
    if connect_mt5():
        logger.info("✅ MT5 Bridge ready")
    else:
        logger.warn("⚠️  MT5 not available — Bridge will run in offline mode (no real data)")
    
    # Start Flask server
    logger.info(f"Starting Flask on port {PORT}...")
    app.run(host='127.0.0.1', port=PORT, debug=False)
