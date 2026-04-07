# TradingView Real-Time Flow Test Plan

**Status:** Phase 11 Complete - Ready for Testing
**Date:** April 4, 2026
**Focus:** Verify Extension Chrome + HTML popup receive TradingView data in real-time via SSE

---

## Pre-Test Verification

### Server Status
```bash
# Start the server
node server.js

# Expected output:
# [EXTENSION-SYNC] SSE endpoint ready at /extension/sync
# [CANDLE] CandleManager loaded
# Server listening on port 4000
```

### Endpoint Verification
```bash
# Test 1: Verify /extension/sync is accessible
curl -N http://127.0.0.1:4000/extension/sync
# Expected: Initial SSE message with type: 'initial-sync'
# Should show: Content-Type: text/event-stream
# Should NOT close - keeps connection open

# Cancel with Ctrl+C after seeing first message
```

### HTTP Fallback Check
```bash
# Test 2: Verify /extension/data works
curl http://127.0.0.1:4000/extension/data
# Expected: JSON response with:
# {
#   "ok": true,
#   "systemStatus": { "source": "offline", "fluxStatus": "OFFLINE" },
#   "currentData": null
# }
```

---

## Phase 1: Manual Test Data Injection

### Test 1a: Send to /tv-webhook (Rich Data)
```bash
curl -X POST http://127.0.0.1:4000/tv-webhook \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EURUSD",
    "price": 1.0870,
    "bid": 1.0869,
    "ask": 1.0871,
    "volume": 1000000,
    "rsi": 65.5,
    "macd": 0.0045,
    "ma20": 1.0850,
    "ma50": 1.0820,
    "ma200": 1.0790,
    "bb_upper": 1.0920,
    "bb_middle": 1.0860,
    "bb_lower": 1.0800,
    "timestamp": '$(date +%s)'000
  }'

# Expected response:
# {
#   "ok": true,
#   "symbol": "EURUSD",
#   "source": "tradingview",
#   "price": 1.087,
#   "indicators": { "rsi": 65.5, "macd": 0.0045, ... }
# }

# Watch server console for:
# [TV-WEBHOOK] DATA RECEIVED: {...}
# [EXTENSION-SYNC] 📤 Broadcasting tradingview-data to N clients
```

### Test 1b: Send to /tv-bridge (Simple Data)
```bash
curl -X POST http://127.0.0.1:4000/tv-bridge \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "GBPUSD",
    "tf": "H1",
    "price": 1.2795,
    "url": "https://tradingview.com/chart/GBPUSD",
    "title": "GBP Alert"
  }'

# Expected: Same broadcast behavior as /tv-webhook
```

---

## Phase 2: Verify Client Reception

### In-Browser Test (HTML Popup)

**Step 1:** Open browser to http://127.0.0.1:4000/popup.html

**Step 2:** Open browser console (F12 → Console tab)

**Step 3:** Send test data from terminal:
```bash
curl -X POST http://127.0.0.1:4000/tv-webhook \
  -H "Content-Type: application/json" \
  -d '{"symbol":"EURUSD","price":1.0870,"bid":1.0869,"ask":1.0871,"rsi":65.5}'
```

**Expected in console (within 100ms):**
- `[POPUP-SSE] Received: tradingview-data`
- HTML should update:
  - Header shows: symbol = "EURUSD"
  - Header shows: price = "1.08700"
  - Status shows: "Live: EURUSD"

### Extension Chrome Test

**Step 1:** Open Extension popup (click Extension icon)

**Step 2:** Open popup console (right-click → Inspect)

**Step 3:** Send test data from terminal:
```bash
curl -X POST http://127.0.0.1:4000/tv-webhook \
  -H "Content-Type: application/json" \
  -d '{"symbol":"GBPUSD","price":1.2795,"bid":1.2794,"ask":1.2796,"rsi":52.3}'
```

**Expected in console (within 100ms):**
- `[EXTENSION-SSE] Received: tradingview-data`
- Popup should update:
  - Status shows: "SSE Connected"
  - Header shows: symbol = "GBPUSD"
  - Header shows: price = "1.27950"

---

## Phase 3: Dual Client Test (Both Simultaneously)

**Step 1:** Open HTML popup in browser
- Console should show: `[POPUP-SSE] Connected`

**Step 2:** Open Extension Chrome popup
- Console should show: `[EXTENSION-SSE] Connected`

**Step 3:** From terminal, send data:
```bash
curl -X POST http://127.0.0.1:4000/tv-webhook \
  -H "Content-Type: application/json" \
  -d '{"symbol":"XAUUSD","price":2375.25,"bid":2375.20,"ask":2375.30,"rsi":58.2,"macd":0.015}'
```

**Expected (within 100ms):**
- **Server Console:** 
  ```
  [TV-WEBHOOK] DATA RECEIVED: {...}
  [EXTENSION-SYNC] 📤 Broadcasting tradingview-data to 2 clients: XAUUSD
  ```

- **HTML Console:**
  ```
  [POPUP-SSE] Received: tradingview-data
  ```
  - Header updates: XAUUSD | 2375.25

- **Extension Console:**
  ```
  [EXTENSION-SSE] Received: tradingview-data
  ```
  - Header updates: XAUUSD | 2375.25

**NOTE:** Both should update simultaneously (within 100ms) - proof of real-time SSE broadcast

---

## Phase 4: Real TradingView Integration

### Setup PineScript Alert

```pinescript
//@version=5
strategy("TradingView Alert to Backend", overlay=true)

// Alert every 1 minute
alertfreq() =>
    ta.barssince(true)

if barstate.islast
    close_price = close
    rsi_value = ta.rsi(close, 14)
    macd_macd = ta.macd(close, 12, 26, 9)[0]
    ma20_value = ta.sma(close, 20)
    
    webhook_url = "http://your-ip:4000/tv-webhook"
    
    message = "symbol=EURUSD&price=" + str.tostring(close_price) + 
              "&bid=" + str.tostring(close_price - 0.0001) +
              "&ask=" + str.tostring(close_price + 0.0001) +
              "&rsi=" + str.tostring(rsi_value) +
              "&macd=" + str.tostring(macd_macd) +
              "&ma20=" + str.tostring(ma20_value)
    
    alert(message)
```

### Configure Alert

1. In TradingView chart, go to **Alerts**
2. Set up new alert for strategy
3. Select **Webhook URL** notification type
4. Use: `http://your-public-ip:4000/tv-webhook`
5. Format message as JSON:
```json
{
  "symbol": "{{exchange}}:{{ticker}}",
  "price": {{close}},
  "bid": {{close}} - 0.0001,
  "ask": {{close}} + 0.0001,
  "volume": {{volume}},
  "rsi": 65.5,
  "macd": 0.0045,
  "ma20": {{sma20}},
  "timestamp": {{time}}
}
```

6. Enable alert and set frequency (e.g., every 1 minute)

### Monitor Real Flow

**Terminal 1:** Watch server logs
```bash
tail -f SYSTEM_LOG.json | grep EXTENSION-SYNC
```

**Terminal 2:** Watch network
```bash
curl -N http://127.0.0.1:4000/extension/sync | grep tradingview
```

**Browser:** Open HTML popup and monitor console
- Should see new data every alert trigger

---

## Troubleshooting

### If /extension/sync shows no data:

**Check 1:** Server is still running?
```bash
ps aux | grep node
```

**Check 2:** /tv-webhook endpoint exists?
```bash
curl -X POST http://127.0.0.1:4000/tv-webhook \
  -H "Content-Type: application/json" \
  -d '{"symbol":"TEST","price":1234}'
```

**Check 3:** Clients are connected?
```bash
curl http://127.0.0.1:4000/extension/data | jq '.systemStatus'
```

### If Extension/HTML don't receive data:

**Check 1:** Browser console for errors?
- Open F12 → Console
- Look for JavaScript errors
- Check: `[EXTENSION-SSE] Connected` or `[POPUP-SSE] Connected`?

**Check 2:** Network tab?
- Open F12 → Network tab
- Look for `/extension/sync` request
- Should show status: **pending** (keeps connection open)
- Check message stream: should see `data: {...}`

**Check 3:** EventSource connected?
```javascript
// In browser console:
console.log(_eventSource?.readyState);
// 0 = CONNECTING, 1 = OPEN, 2 = CLOSED
```

### If response shows empty data:

**Likely cause:** No clients connected when data arrived
- Solution: Connect HTML/Extension popup BEFORE sending test data
- Watch server logs for `[EXTENSION-SYNC] Client connecté (total: N)`

---

## Success Criteria

✅ **Test Passed IF:**
1. HTML popup receives and displays test data
2. Extension Chrome receives and displays test data
3. Both receive data simultaneously (within 100ms)
4. Server logs show broadcast confirmation
5. Data persists in browser until updated
6. Auto-reconnect works when server restarts
7. New clients (late joiners) receive current state immediately

✅ **System Ready For Production IF:**
1. All above criteria met
2. Real TradingView alerts can reach /tv-webhook
3. Indicators correctly calculated (RSI, MACD, MA20, etc.)
4. Multi-timeframe support working (M1, M5, M15, H1, H4, D1)
5. Extension + HTML both maintain connection under load

---

## Performance Targets

- **Latency:** < 100ms from webhook POST to UI update
- **Clients:** Support 10+ simultaneous connections
- **Reliability:** 99.9% uptime (auto-reconnect)
- **Data:** No loss (SSE guarantees delivery)
- **CPU:** < 5% usage at idle (heartbeat only)

---

## Log Analysis

### Expected Normal Logs

```
[SERVER] Server running on port 4000
[EXTENSION-SYNC] Client connecté (total: 2)  // Extension + HTML
[EXTENSION-SYNC] Client connecté (total: 1)  // Late joiner

[TV-WEBHOOK] DATA RECEIVED: {"symbol":"EURUSD",...}
[EXTENSION-SYNC] 📤 Broadcasting tradingview-data to 2 clients: EURUSD | Bid:1.0869 | Ask:1.0871 | Price:1.0870

[POPUP-SSE] Received: tradingview-data        // In Extension console
[POPUP-SSE] Received: tradingview-data        // In HTML console

[EXTENSION-SYNC] Client déconnecté (total: 1) // User closed popup
```

### If Tests Fail

Enable verbose logging:
```javascript
// Add to server.js after broadcastToExtension():
console.log('BROADCAST_FAILED:', message);
```

Check for:
- `TypeError: broadcastToExtension is not defined`
- `extensionSyncClients.splice error`
- `Cannot read property 'write' of undefined`

---

## Next Steps After Verification

1. **If all tests pass:** System ready for live TradingView
   - Configure TradingView alerts with webhook
   - Monitor first 24 hours for stability
   - Adjust intervals if needed

2. **If tests fail:** Debug based on error type
   - SSE connection issues → Check CORS headers
   - Data not arriving → Check /tv-webhook reception
   - Broadcast fails → Check extensionSyncClients array

3. **After TradingView stable:** Add MT5 integration
   - Activate MT5 EA (Bridge_MT5_Studio.mq5 v3.0)
   - Same SSE broadcast system
   - Both sources feed same /extension/sync endpoint

---

## Quick Commands Reference

```bash
# Monitor SSE in real-time
curl -N http://127.0.0.1:4000/extension/sync

# Send test webhook
curl -X POST http://127.0.0.1:4000/tv-webhook \
  -H "Content-Type: application/json" \
  -d '{"symbol":"EURUSD","price":1.0870,"bid":1.0869,"ask":1.0871,"rsi":65}'

# Check current state
curl http://127.0.0.1:4000/extension/data | jq

# View all TradingView data stored
curl http://127.0.0.1:4000/tv/data | jq

# Monitor server logs (if running in background)
tail -f /path/to/logs/server.log | grep EXTENSION-SYNC
```

---

## Documentation References

- **Server Code:** `server.js` lines 1300-1380 (SSE implementation)
- **Extension Popup:** `tradingview-analyzer/popup.js` (SSE client)
- **HTML Popup:** `popup.js` (SSE client)
- **Webhook Endpoint:** `server.js` line 3284 (/tv-webhook)
- **Test File:** This document (TEST_REAL_TIME_FLOW.md)

---

**Ready to test!** Follow the phases in order. Good luck! 🚀
