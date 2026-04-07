#!/usr/bin/env node
/**
 * MT5 Data Pusher (Node.js version)
 * Reads mt5_data.json and pushes it to Node.js server /mt5 endpoint
 */

const fs = require('fs');
const path = require('path');
const http = require('http');

const MT5_DATA_FILE = path.join(__dirname, 'mt5_data.json');
const SERVER_HOST = '127.0.0.1';
const SERVER_PORT = 4000;
const PUSH_INTERVAL = 2000; // 2 seconds
const FILE_RELAY_ALLOWED = process.env.ALLOW_MT5_FILE_RELAY === '1';
const MAX_FILE_AGE_MS = Number(process.env.MT5_FILE_MAX_AGE_MS || 5000);

if (!FILE_RELAY_ALLOWED) {
  console.log('[MT5-PUSH] File relay disabled by default. Use direct MT5 -> /mt5 bridge.');
  console.log('[MT5-PUSH] Set ALLOW_MT5_FILE_RELAY=1 only for temporary diagnostics.');
  process.exit(0);
}

function readMT5Data() {
  try {
    const data = fs.readFileSync(MT5_DATA_FILE, 'utf-8');
    return JSON.parse(data);
  } catch (e) {
    console.log(`[MT5-PUSH] ✗ Error reading ${MT5_DATA_FILE}:`, e.message);
    return null;
  }
}

function pushToServer(data) {
  if (!data) return;

  try {
    const stat = fs.statSync(MT5_DATA_FILE);
    const ageMs = Date.now() - stat.mtimeMs;
    if (ageMs > MAX_FILE_AGE_MS) {
      console.log(`[MT5-PUSH] ✗ Stale mt5_data.json (${Math.round(ageMs/1000)}s) — push blocked`);
      return;
    }
  } catch (e) {
    console.log('[MT5-PUSH] ✗ Unable to stat mt5_data.json:', e.message);
    return;
  }
  
  const sym = data.symbol || {};
  const payload = {
    symbol: sym.name || 'UNKNOWN',
    price: sym.price || 0,
    bid: sym.bid || 0,
    ask: sym.ask || 0,
    volume: sym.volume || 0,
    timeframe: sym.timeframe || 'H1',
    timestamp: sym.timestamp || data.timestamp || new Date().toISOString(),
    source: 'mt5-file-relay'
  };
  
  const indicators = data.indicators || {};
  if (indicators) {
    payload.rsi = indicators.rsi || 0;
    payload.ma20 = indicators.ma20 || 0;
    const macd = indicators.macd || {};
    payload.macd = macd.value || 0;
  }
  
  const postData = JSON.stringify(payload);
  
  const options = {
    hostname: SERVER_HOST,
    port: SERVER_PORT,
    path: '/mt5',
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(postData)
    }
  };
  
  const req = http.request(options, (res) => {
    let body = '';
    res.on('data', d => body += d);
    res.on('end', () => {
      if (res.statusCode === 200) {
        console.log(`[MT5-PUSH] ✓ ${payload.symbol} @ ${payload.price} | Status: ${res.statusCode}`);
      } else {
        console.log(`[MT5-PUSH] ⚠ Status ${res.statusCode}: ${body}`);
      }
    });
  });
  
  req.on('error', err => {
    console.log(`[MT5-PUSH] ✗ Connection failed: ${err.message}`);
  });
  
  req.write(postData);
  req.end();
}

console.log('[MT5-PUSH] Starting MT5 Data Pusher');
console.log(`[MT5-PUSH] Reading from: ${MT5_DATA_FILE}`);
console.log(`[MT5-PUSH] Pushing to: http://${SERVER_HOST}:${SERVER_PORT}/mt5`);
console.log(`[MT5-PUSH] Interval: ${PUSH_INTERVAL}ms\n`);

// Initial push
const initData = readMT5Data();
if (initData) {
  pushToServer(initData);
}

// Continuous push
setInterval(() => {
  const data = readMT5Data();
  if (data) {
    pushToServer(data);
  } else {
    console.log('[MT5-PUSH] ⚠ No data to push');
  }
}, PUSH_INTERVAL);

console.log('[MT5-PUSH] Pusher running. Press Ctrl+C to stop.\n');
