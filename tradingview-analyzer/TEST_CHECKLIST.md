# Extension Testing Checklist

## Pre-Flight Checks (Before Testing)

- [ ] Backend running: Open terminal, run `node server.js` in workspace root
- [ ] Extension loaded in Chrome: Check extension icon in top-right
- [ ] TradingView tab open: Have a chart visible in another tab
- [ ] DevTools ready: Press F12 to open, keep Console visible during tests

---

## 1. Popup Opens & Status Indicators (1 min)

**Steps:**
1. Click extension icon
2. Popup should open showing "Actif" tab
3. Look at header (top-left):
   - 3 colored dots should appear
   - Symbol should show (e.g., "XAUUSD")
   - Price and time should display

**Expected Results:**
- ✅ All 3 dots GREEN (all dots green = everything online)
- ✅ Status grid shows: "online", "MT5 live", "Extension"
- ✅ Zero RED errors in Console

**Failure Signs:**
- ❌ Red dots = backend/MT5 offline
- ❌ Red text in Console
- ❌ "Offline" in status area

---

## 2. Symbol Search & Mapping (2 min)

**Steps:**
1. Go to "Actif" tab
2. Type "GOLD" in search box
3. Press Enter
4. Wait for suggestions to appear
5. Click on first suggestion

**Expected Results:**
- ✅ Suggestions appear after typing (dark cards with %)
- ✅ Clicking suggestion updates header symbol
- ✅ Status changes to "ok" (green)
- ✅ "Current: XAUUSD" appears below search box

**Failure Signs:**
- ❌ "No results" message
- ❌ Search box doesn't respond to Enter key
- ❌ No suggestions appear
- ❌ Red error in Console

---

## 3. Chart Loading (2 min)

**Steps:**
1. Click "Graphique" tab
2. Wait for chart to load
3. Click different timeframe buttons (1M, 5M, 15M, H1, D1)
4. Watch price in header update

**Expected Results:**
- ✅ Chart loads in <1 second
- ✅ Candles visible (green for up, red for down)
- ✅ Price updates every 2-3 seconds in header
- ✅ Chart refreshes when changing timeframe
- ✅ LightweightCharts visible (professional-looking chart)

**Failure Signs:**
- ❌ "Loading..." forever
- ❌ Chart area empty/gray
- ❌ No price changes
- ❌ Buttons unresponsive

---

## 4. News Tab & Auto-Alerts (5 min wait)

**Steps:**
1. Click "Marches" tab → verify sessions show (London, NY, Tokyo, Sydney)
2. Click "News" tab
3. Verify economic calendar loads
4. **Wait 2-5 minutes** for alert trigger
5. When you see 🔴 red badge in top-right: SUCCESS

**Expected Results (News Tab):**
- ✅ List of events with impact levels (High=red, Medium=orange, Low=gray)
- ✅ Event times showing "Soon", "Recent", or "Later"
- ✅ Country codes visible
- ✅ Bias predictions visible for some events

**Expected Results (Auto-Alert):**
- ✅ Red badge appears: "🔴 News Importante: [event name]"
- ✅ Appears in top-right corner of screen
- ✅ Auto-disappears after 10 seconds
- ✅ May appear multiple times if multiple HIGH events

**Failure Signs:**
- ❌ "NewsEngine absent" in Console
- ❌ No events showing
- ❌ Badge never appears (wait longer or different news)
- ❌ Badge doesn't disappear after 10s

---

## 5. Analysis (Trade Signal) (2 min)

**Steps:**
1. Click "Analyser" button on action bar
2. Button shows "..." while loading
3. Wait for Signal tab to populate (max 5 seconds)
4. Verify direction shown (LONG/SHORT/WAIT)

**Expected Results:**
- ✅ Button disables while processing
- ✅ Status bar shows "Analyse XAUUSD [SNIPER]..."
- ✅ Signal tab auto-opens
- ✅ Large direction text appears (green for LONG, red for SHORT)
- ✅ Shows confidence % (0-100)
- ✅ Entry/SL/TP prices visible
- ✅ "Pourquoi:" section has reasoning

**Result Format Example:**
```
LONG (green text)
Entry: 2045.50  SL: 2040.00  TP: 2055.00
Pourquoi: Bullish bounce from support, RSI oversold
Confiance: ████████░░ 82%
```

**Failure Signs:**
- ❌ "Erreur: backend offline"
- ❌ Signal tab stays empty
- ❌ Red error text in Console
- ❌ Button doesn't re-enable

---

## 6. Mode Switching (1 min)

**Steps:**
1. Scroll down to see mode buttons (SCALPER, SNIPER, SWING)
2. Click each one
3. Notice border color changes
4. Click "Analyser" after changing mode

**Expected Results:**
- ✅ SNIPER has purple border (default)
- ✅ SCALPER has orange border
- ✅ SWING has green border
- ✅ Selected mode shows thicker border
- ✅ Analysis recalculates with different mode
- ✅ Confidence % may differ per mode

**Failure Signs:**
- ❌ Buttons unresponsive
- ❌ No visual feedback when clicking
- ❌ Analysis unchanged when mode changes

---

## 7. Screenshot & Visual Analysis (3 min)

**Steps:**
1. Click "Screenshot" button (📷 icon)
2. Button shows "..."
3. Wait 2-3 seconds for processing
4. Check Signal tab for "Analyse Visuelle" result

**Expected Results:**
- ✅ Status shows "Screenshot TV..."
- ✅ Button disables while sending
- ✅ Backend processes image (may take 3-5 sec)
- ✅ Signal tab shows visual analysis result
- ✅ Confidence % displayed
- ✅ Button re-enables

**Result Format Example:**
```
Analyse Visuelle
The chart shows a bullish flag pattern at resistance...
Confiance: ██████░░░░ 65%
```

**Failure Signs:**
- ❌ "Capture échouée" message
- ❌ "serveur offline" (backend not responding)
- ❌ No analysis appears in Signal tab
- ❌ Button stays disabled

---

## 8. Refresh Button (1 min)

**Steps:**
1. Click "Rafraichir" button (↻ icon)
2. Wait for action to complete

**Expected Results:**
- ✅ Re-detects symbol from TradingView
- ✅ Reloads news list
- ✅ Reloads sessions
- ✅ Status updates
- ✅ Takes ~1 second total

**Failure Signs:**
- ❌ Status doesn't update
- ❌ News not reloaded

---

## 9. Console Check (Final Step)

**Steps:**
1. Open DevTools (F12)
2. Click "Console" tab
3. Look for errors (red text with X icon)

**Expected Results:**
- ✅ **ZERO RED ERRORS**
- ✅ May see blue "INFO" messages (normal)
- ✅ May see yellow "WARN" messages (normal)
- ✅ No "Uncaught" errors
- ✅ No "TypeError" messages

**Failure Signs:**
- ❌ Any RED error messages
- ❌ Uncaught exceptions
- ❌ TypeError: undefined is not a function

---

## 10. Memory & Performance Check

**Steps:**
1. Leave popup open for 1 minute
2. Keep switching tabs and clicking buttons
3. Open DevTools → Performance tab
4. No noticeable lag/stuttering

**Expected Results:**
- ✅ Popup remains responsive (no freezing)
- ✅ Buttons click immediately
- ✅ No memory spike
- ✅ Fan doesn't spin up (not CPU-intensive)

**Failure Signs:**
- ❌ Popup becomes sluggish
- ❌ Buttons delay in responding
- ❌ High CPU usage (fan spins)

---

## Summary Table

| Feature | Test Time | Status | Notes |
|---------|-----------|--------|-------|
| Popup opens | 30s | [ ] |  |
| Status indicators | 30s | [ ] | 3 green dots = healthy |
| Symbol search | 2min | [ ] | Try "GOLD" or "EUR" |
| Chart loads | 2min | [ ] | Check LightweightCharts |
| News tab | 5min | [ ] | Wait for 🔴 red alert badge |
| Analysis button | 2min | [ ] | Shows LONG/SHORT/WAIT signal |
| Mode switching | 1min | [ ] | SNIPER/SCALPER/SWING |
| Screenshot | 3min | [ ] | Visual analysis in Signal |
| Refresh button | 1min | [ ] | Re-detects everything |
| Console errors | 1min | [ ] | Must be ZERO red errors |
| Performance | 2min | [ ] | Stays responsive |

## Scoring

- **10/10** = All tests passed, zero issues ✅ PRODUCTION READY
- **9/10** = 1 minor issue, still usable
- **7/10** = 2-3 issues, needs fixes
- **<7/10** = Multiple failures, not ready

---

## Emergency Troubleshooting

**If "Extension context invalidated" appears:**
1. Close entire Chrome browser
2. Reload the extension: chrome://extensions
3. Disable and re-enable
4. Reload TradingView tab
5. Re-open popup

**If backend shows "offline":**
1. Check server.js is running
2. Look for error messages in terminal
3. Verify http://127.0.0.1:4000/health returns success
4. Restart server: `node server.js`

**If no chart loads:**
1. Check TradingView tab is open
2. Verify MT5 Bridge is sending data
3. Wait 2-3 seconds for initial load
4. Try different timeframe button

**If news doesn't load:**
1. Check internet connection
2. Wait for next auto-refresh cycle (5 min max)
3. Click "News" tab button forcefully
4. Check backend: `curl http://127.0.0.1:4000/health`

---

## Notes
- First popup load may take 1-2 seconds (modules loading)
- Analysis may take 5 seconds (depends on backend processing)
- News alerts appear every 2-5 minutes (if high-impact events exist)
- All times are approximate (may vary with system speed)

Good luck! Report any errors found. 🚀
