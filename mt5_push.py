#!/usr/bin/env python3
"""
MT5 Data Pusher
Reads mt5_data.json and pushes it to Node.js server /mt5 endpoint
This bridges the EA data → Node.js real-time system
"""

import json
import time
import os
import requests
from pathlib import Path
from datetime import datetime

MT5_DATA_FILE = Path(__file__).parent / "mt5_data.json"
SERVER_URL = "http://127.0.0.1:4000/mt5"
PUSH_INTERVAL = 2  # seconds
MAX_FILE_AGE_SECONDS = int(os.getenv('MT5_FILE_MAX_AGE_SECONDS', '5'))

if os.getenv('ALLOW_MT5_FILE_RELAY', '0') != '1':
    print('[MT5-PUSH] File relay disabled by default. Use direct MT5 -> /mt5 bridge.')
    print('[MT5-PUSH] If you really need file relay, set ALLOW_MT5_FILE_RELAY=1.')
    raise SystemExit(0)

def read_mt5_data():
    """Read mt5_data.json"""
    if not MT5_DATA_FILE.exists():
        print(f"[ERROR] {MT5_DATA_FILE} not found")
        return None
    try:
        with open(MT5_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] Reading {MT5_DATA_FILE}: {e}")
        return None

def push_to_server(data):
    """Push MT5 data to Node.js server /mt5 endpoint"""
    if not data:
        return False
    
    sym = data.get('symbol', {})
    file_age = time.time() - MT5_DATA_FILE.stat().st_mtime
    if file_age > MAX_FILE_AGE_SECONDS:
      print(f"[MT5-PUSH] ✗ Stale mt5_data.json ({file_age:.1f}s) — push blocked")
      return False

    payload = {
        'symbol': sym.get('name', 'UNKNOWN'),
        'price': sym.get('price', 0),
        'bid': sym.get('bid', 0),
        'ask': sym.get('ask', 0),
        'volume': sym.get('volume', 0),
        'timeframe': sym.get('timeframe', 'H1'),
        'timestamp': sym.get('timestamp') or data.get('timestamp') or datetime.utcnow().isoformat() + 'Z',
        'source': 'mt5-file-relay'
    }
    
    # Add indicators if present
    indicators = data.get('indicators', {})
    if indicators:
        payload['rsi'] = indicators.get('rsi', 0)
        payload['ma20'] = indicators.get('ma20', 0)
        macd = indicators.get('macd', {})
        payload['macd'] = macd.get('value', 0)
    
    try:
        resp = requests.post(SERVER_URL, json=payload, timeout=5)
        if resp.status_code == 200:
            print(f"[MT5-PUSH] ✓ {payload['symbol']} @ {payload['price']} | Status: {resp.status_code}")
            return True
        else:
            print(f"[MT5-PUSH] ✗ Server returned {resp.status_code}")
            return False
    except Exception as e:
        print(f"[MT5-PUSH] ✗ Error: {e}")
        return False

def main():
    print("[MT5-PUSH] Starting MT5 Data Pusher")
    print(f"[MT5-PUSH] Reading from: {MT5_DATA_FILE}")
    print(f"[MT5-PUSH] Pushing to: {SERVER_URL}")
    print(f"[MT5-PUSH] Interval: {PUSH_INTERVAL}s\n")
    
    consecutive_fails = 0
    
    while True:
        data = read_mt5_data()
        if data:
            if push_to_server(data):
                consecutive_fails = 0
            else:
                consecutive_fails += 1
                if consecutive_fails > 3:
                    print("[MT5-PUSH] ⚠ Server unreachable for 3+ attempts")
        else:
            print("[MT5-PUSH] ⚠ No data to push")
        
        time.sleep(PUSH_INTERVAL)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n[MT5-PUSH] Stopped")
