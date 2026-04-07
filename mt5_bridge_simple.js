// mt5_bridge_simple.js - Minimal MT5 data server
// Just reads mt5_data.json and serves it to the extension
'use strict';

const fs = require('fs');
const http = require('http');
const path = require('path');

if (process.env.ALLOW_LEGACY_BRIDGE !== '1') {
  console.log('Legacy bridge disabled: single environment mode uses only http://127.0.0.1:4000');
  process.exit(0);
}

const PORT = 4000;
const DATA_FILE = path.join(__dirname, 'mt5_data.json');

const server = http.createServer((req, res) => {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  
  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }
  
  try {
    const data = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
    
    if (req.url === '/data') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        ok: true,
        data: data,
        timestamp: new Date().toISOString()
      }));
    } else if (req.url === '/symbol') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        ok: true,
        symbol: data.symbol,
        timestamp: new Date().toISOString()
      }));
    } else if (req.url.startsWith('/chart')) {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        ok: true,
        chart: data.chart,
        timestamp: new Date().toISOString()
      }));
    } else if (req.url === '/health') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        ok: true,
        status: 'running',
        port: PORT,
        file: DATA_FILE,
        timestamp: new Date().toISOString()
      }));
    } else {
      res.writeHead(404);
      res.end('Not found');
    }
  } catch (err) {
    res.writeHead(500, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: false, error: err.message }));
  }
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`MT5 Data Bridge running on http://127.0.0.1:${PORT}`);
  console.log(`Reading from: ${DATA_FILE}`);
  console.log('Routes: /data /symbol /chart /health');
});
