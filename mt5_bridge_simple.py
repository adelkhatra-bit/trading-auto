#!/usr/bin/env python3
"""
MT5 Data Bridge - Minimal
Lit mt5_data.json et le sert à l'extension Chrome
Architecture legacy: disabled by default in single-environment mode
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
import time

# Fichier de données MT5 (écrit par l'EA MetaTrader 5)
MT5_DATA_FILE = Path(__file__).parent / "mt5_data.json"
if os.getenv('ALLOW_LEGACY_BRIDGE', '0') != '1':
    print('Legacy bridge disabled: single environment mode uses only http://127.0.0.1:4000')
    raise SystemExit(0)

PORT = 4000
FILE_STALE_SECONDS = 60  # Fichier considéré périmé après 60s sans mise à jour

def read_mt5_data():
    """Lit et retourne le contenu de mt5_data.json, None si absent."""
    if not MT5_DATA_FILE.exists():
        return None
    with open(MT5_DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def is_file_fresh():
    """Retourne True si mt5_data.json a été mis à jour dans la dernière minute."""
    if not MT5_DATA_FILE.exists():
        return False
    age = time.time() - os.path.getmtime(MT5_DATA_FILE)
    return age < FILE_STALE_SECONDS

def candles_to_rates(candles):
    """Convertit les bougies MT5 en format lightweight-charts (timestamp Unix)."""
    rates = []
    for c in candles:
        try:
            t_str = c.get('time', '')
            # Accepte ISO 8601 avec ou sans Z
            t_str_clean = t_str.replace('Z', '+00:00')
            ts = int(datetime.fromisoformat(t_str_clean).timestamp())
            rates.append({
                'time':  ts,
                'open':  float(c['open']),
                'high':  float(c['high']),
                'low':   float(c['low']),
                'close': float(c['close'])
            })
        except Exception:
            pass
    return rates


class MT5DataHandler(BaseHTTPRequestHandler):
    """Handler HTTP pour servir les données MT5 à l'extension Chrome."""

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path   = parsed.path
            params = parse_qs(parsed.query)

            # ── /health ──────────────────────────────────────────────────────
            if path == '/health':
                fresh = is_file_fresh()
                mt5_status = 'offline'
                active_context = None
                if fresh:
                    try:
                        mt5_data = read_mt5_data()
                        if mt5_data:
                            mt5_status = 'mt5'
                            sym = mt5_data.get('symbol', {})
                            state = mt5_data.get('state', {})
                            active_context = {
                                'symbol':    sym.get('name'),
                                'timeframe': sym.get('timeframe', 'H1'),
                                'price':     sym.get('price'),
                                'market':    state.get('market_status', 'unknown')
                            }
                    except Exception:
                        pass
                self._send_json({
                    'ok':           True,
                    'status':       'running',
                    'mt5Status':    mt5_status,
                    'activeContext': active_context,
                    'fileFresh':    fresh,
                    'timestamp':    datetime.now(timezone.utc).isoformat()
                })
                return

            # Routes suivantes nécessitent le fichier de données
            if not MT5_DATA_FILE.exists():
                self._send_json({'ok': False, 'error': 'mt5_data.json introuvable'}, status=404)
                return

            mt5_data = read_mt5_data()

            # ── /data  (toutes les données brutes) ───────────────────────────
            if path == '/data':
                self._send_json({'ok': True, 'data': mt5_data,
                                 'timestamp': datetime.now(timezone.utc).isoformat()})

            # ── /mt5/latest  (alias de /data — pour background.js) ──────────
            elif path == '/mt5/latest':
                self._send_json({'ok': True, 'data': mt5_data,
                                 'timestamp': datetime.now(timezone.utc).isoformat()})

            # ── /symbol ───────────────────────────────────────────────────────
            elif path == '/symbol':
                self._send_json({'ok': True, 'symbol': mt5_data.get('symbol'),
                                 'session': mt5_data.get('session'),
                                 'timestamp': datetime.now(timezone.utc).isoformat()})

            # ── /mt5/price?symbol=X ──────────────────────────────────────────
            elif path == '/mt5/price':
                sym_data = mt5_data.get('symbol', {})
                self._send_json({
                    'ok':    True,
                    'price': sym_data.get('price'),
                    'bid':   sym_data.get('bid'),
                    'ask':   sym_data.get('ask'),
                    'symbol': sym_data.get('name'),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })

            # ── /mt5/klines?symbol=X&tf=Y&count=N ───────────────────────────
            elif path == '/mt5/klines':
                candles = mt5_data.get('chart', {}).get('candles', [])
                count_param = params.get('count', ['200'])[0]
                try:
                    count = int(count_param)
                except ValueError:
                    count = 200
                rates = candles_to_rates(candles)[-count:]
                self._send_json({
                    'ok':    True,
                    'rates': rates,
                    'symbol': mt5_data.get('symbol', {}).get('name'),
                    'tf':    mt5_data.get('chart', {}).get('timeframe', 'H1'),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })

            # ── /mt5/current-chart?tf=H1  (alias pour chart-module.js) ──────
            elif path == '/mt5/current-chart':
                candles = mt5_data.get('chart', {}).get('candles', [])
                rates = candles_to_rates(candles)
                self._send_json({
                    'ok':    True,
                    'rates': rates,
                    'tf':    mt5_data.get('chart', {}).get('timeframe', 'H1'),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })

            # ── /mt5/symbols ─────────────────────────────────────────────────
            elif path == '/mt5/symbols':
                sym = mt5_data.get('symbol', {}).get('name')
                self._send_json({
                    'ok':      True,
                    'symbols': [sym] if sym else [],
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })

            # ── /chart  (legacy) ─────────────────────────────────────────────
            elif path.startswith('/chart'):
                self._send_json({
                    'ok':       True,
                    'timeframe': mt5_data.get('chart', {}).get('timeframe', 'H1'),
                    'candles':   mt5_data.get('chart', {}).get('candles', []),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })

            # ── /indicators ──────────────────────────────────────────────────
            elif path == '/indicators':
                self._send_json({'ok': True, 'indicators': mt5_data.get('indicators', {}),
                                 'timestamp': datetime.now(timezone.utc).isoformat()})

            # ── /analysis ────────────────────────────────────────────────────
            elif path == '/analysis':
                self._send_json({'ok': True, 'analysis': mt5_data.get('analysis', {}),
                                 'timestamp': datetime.now(timezone.utc).isoformat()})

            # ── /economic-events  (retourne session MT5 en attendant calendrier) ─
            elif path == '/economic-events':
                self._send_json({'ok': True, 'events': [],
                                 'timestamp': datetime.now(timezone.utc).isoformat()})

            # ── /mapping/list  (GET — liste des mappings) ─────────────────────
            elif path == '/mapping/list':
                self._send_json({'ok': True, 'mappings': {}, 'count': 0,
                                 'timestamp': datetime.now(timezone.utc).isoformat()})

            # ── /dashboard  (HTML - monitoring page) ──────────────────────────
            elif path == '/dashboard' or path == '/':
                try:
                    with open('dashboard.html', 'r', encoding='utf-8') as f:
                        html = f.read()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', len(html.encode('utf-8')))
                    self.send_header('Cache-Control', 'no-cache')
                    self.end_headers()
                    self.wfile.write(html.encode('utf-8'))
                except FileNotFoundError:
                    self._send_json({'ok': False, 'error': 'dashboard.html not found'}, status=404)

            else:
                self._send_json({'ok': False, 'error': f'Route inconnue: {path}'}, status=404)

        except Exception as e:
            self._send_json({'ok': False, 'error': str(e)}, status=500)

    def do_POST(self):
        """POST — mapping local (résolution symbole)."""
        try:
            parsed = urlparse(self.path)
            path   = parsed.path
            length = int(self.headers.get('Content-Length', 0))
            body   = json.loads(self.rfile.read(length)) if length > 0 else {}

            # /mapping/resolve → retourne le symbole MT5 courant comme suggestion
            if path == '/mapping/resolve':
                mt5_data = read_mt5_data() if MT5_DATA_FILE.exists() else {}
                current_sym = mt5_data.get('symbol', {}).get('name', '') if mt5_data else ''
                name = (body.get('name') or '').upper()
                suggestions = []
                if current_sym:
                    suggestions.append({
                        'symbol':       current_sym,
                        'description':  'Symbole actif MT5',
                        'confidence':   100 if current_sym.startswith(name) else 50,
                        'priceMatch':   False
                    })
                self._send_json({'ok': True, 'suggestions': suggestions})

            # /mapping/save → accepté silencieusement (pas de stockage serveur)
            elif path == '/mapping/save':
                self._send_json({'ok': True, 'message': 'Mapping enregistré localement'})

            # /system-log → reçoit les logs du diagnostic IA de l'extension
            elif path == '/system-log':
                entry = {
                    'ts':     datetime.now(timezone.utc).isoformat(),
                    'from':   body.get('from', 'extension'),
                    'action': body.get('action', ''),
                    'data':   body.get('data') or body.get('prompt', '')[:500]
                }
                print(f"[LOG] {entry['from']} | {entry['action']}")
                self._send_json({'ok': True, 'id': entry['ts']})

            else:
                self._send_json({'ok': False, 'error': f'Route POST inconnue: {path}'}, status=404)

        except Exception as e:
            self._send_json({'ok': False, 'error': str(e)}, status=500)

    def do_OPTIONS(self):
        self.send_response(204)
        self._add_cors_headers()
        self.end_headers()

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._add_cors_headers()
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def _add_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def log_message(self, format, *args):
        pass  # Silencieux


if __name__ == '__main__':
    import sys
    # Force UTF-8 sur Windows pour eviter les erreurs d'encodage console
    if sys.platform == 'win32' and sys.stdout and sys.stderr:
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except:
            pass  # Silencieux si stdout/stderr redirectionné
    try:
        server = HTTPServer(('127.0.0.1', PORT), MT5DataHandler)
        print(f"MT5 Bridge OK  http://127.0.0.1:{PORT}")
        print(f"Source         {MT5_DATA_FILE}")
        print("GET  : /health /data /mt5/latest /mt5/price /mt5/klines /mt5/symbols /analysis /indicators /economic-events")
        print("POST : /mapping/resolve /mapping/save /system-log")
        print("Ctrl+C pour arreter\n")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBridge arrete.")
    except Exception as e:
        print(f"Erreur: {e}")
