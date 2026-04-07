# ⚡ REAL-TIME MARKET DATA ARCHITECTURE — CANDLE LIFECYCLE & SYNC

**Date:** 2026-04-03  
**Critical Issue:** Current system treats price as static. Agents need real-time candle closes.  
**Scope:** Architecture pour temps réel exploitable avec clôtures bougies, indicateurs, synchronisation

---

## 🔴 PROBLÈME ACTUEL (Vérification du code)

### Ce que le système a DÉJÀ
```json
// mt5_data.json (structure existante)
{
  "chart": {
    "timeframe": "H1",
    "candles": [
      {
        "time": "2026-04-02T16:00:00Z",
        "open": 2375.0,
        "high": 2376.5,
        "low": 2374.5,
        "close": 2375.3
      },
      {
        "time": "2026-04-02T15:00:00Z",
        "open": 2373.5,
        "high": 2375.5,
        "low": 2373.0,
        "close": 2375.0
      }
    ]
  },
  "indicators": {
    "rsi": 52.3,
    "macd": { "value": 0.45, "signal": 0.38, "histogram": 0.07 },
    "ma20": 2372.5
  }
}
```

### Ce qui MANQUE
```javascript
// ❌ Pas géré actuellement:

1. CANDLE STATE MACHINE
   open (T0:00) → in_progress → close (T0:59:59) → new_candle (T1:00)
   // Pas d'événement "close"

2. TICK PROCESSING
   MT5 sends: price update at T0:15, T0:23, T0:47
   // Pas d'agrégation en candle

3. INDICATOR RECALCULATION
   Indicators are STATIC in mt5_data.json
   // Pas de recalc on candle close

4. AGENT TRIGGER TIMING
   Agents run on-demand, pas sur événement
   // Pas de "trigger on candle close"

5. SYNCHRONIZATION
   Extension sees price A
   Dashboard sees price B
   Agent sees price C
   // Pas de "all see same candle at same time"
```

---

## ✅ ARCHITECTURE PROPOSÉE: REAL-TIME CANDLE SYSTEM

### Core Concept

```
┌─ TICK COLLECTOR (MT5 EA or Bridge)
│  Receives: bid/ask/volume every tick
│
├─ CANDLE MANAGER (Node.js)
│  T0:00  → Open candle
│  T0:15  → Update (H, L, C)
│  T0:59  → Update (final H, L, C)
│  T1:00  → CLOSE event → next timeframe
│
├─ INDICATOR ENGINE
│  On CLOSE event:
│    → Recalc RSI, MACD, MA, BBands, ATR
│    → Store in candle object
│
├─ AGENT ORCHESTRATOR
│  On CLOSE event:
│    → Fetch fresh data
│    → Run analysis
│    → Publish result
│
└─ SYNC BROADCASTER (SSE)
   On CLOSE event:
     → Extension: new candle ready
     → Studio: update chart + status
     → Dashboard: new alert available
     → All get SAME candle at SAME time
```

---

## 📊 CANDLE LIFECYCLE (Complete State Machine)

### Timeline for H1 Candle (1-hour timeframe)

```
T = 2026-04-03 10:00:00 UTC
═══════════════════════════════════════════════════════════════

10:00:00 → CANDLE OPEN
  State: { period: H1, time: 10:00:00, status: "open" }
  Data:  { open: 2375.30, high: 2375.30, low: 2375.30, close: 2375.30, volume: 0 }
  
  10:00:05 → TICK arrives (price: 2375.45)
    State: "in_progress" (5s into candle)
    Update: { high: 2375.45, volume += 100 }
    
  10:15:30 → TICK arrives (price: 2374.80)
    State: "in_progress" (15m 30s into candle)
    Update: { low: 2374.80, close: 2374.80, volume += 250 }
    
  10:45:00 → SSE BROADCAST (status update)
    Send to all clients:
      { 
        candle: { open: 2375.30, high: 2375.45, low: 2374.80, close: 2374.80 },
        state: "in_progress",
        percent_complete: 75%,
        time_remaining_ms: 15000
      }
    
  10:59:59 → Last TICK of period (price: 2375.10)
    Update: { close: 2375.10 } (final close)
    Indicators READY for calculation
    
11:00:00 → CANDLE CLOSE EVENT ⚡⚡⚡
  
  State machine transition: "open" → "closed"
  Final candle: { open: 2375.30, high: 2375.45, low: 2374.80, close: 2375.10 }
  
  TRIGGER SEQUENCE (synchronous, <100ms):
    ├─ Indicator Engine
    │  ├─ Recalc RSI (14 periods)
    │  ├─ Recalc MACD (12,26,9)
    │  ├─ Recalc Bollinger Bands
    │  └─ Store: indicators_H1 = { rsi: 52.1, macd: {...}, bb: {...} }
    │
    ├─ Agent Orchestrator
    │  ├─ Load fresh candle
    │  ├─ Load indicators
    │  ├─ Load user reference prices
    │  ├─ Run: momentum_analyzer → trend_detector → signal_generator
    │  └─ Result: { direction: "LONG", score: 72, entry: 2375.30, ... }
    │
    ├─ SSE Broadcaster
    │  ├─ Message: "candle_closed" { candle, indicators, agents_ready }
    │  ├─ To: Extension, Studio, Dashboard
    │  └─ Include: timestamp = Date.now() (proof of sync)
    │
    └─ Storage
       ├─ Append to historical candles array
       └─ Mark as "complete"

11:00:00+ → NEW CANDLE OPENS
  State: { period: H1, time: 11:00:00, status: "open" }
  Data: { open: 2375.10, high: 2375.10, low: 2375.10, close: 2375.10, volume: 0 }
```

---

## 🔄 DATA FLOW: From Tick to Agent Signal

### Component 1: Tick Collector
**Source:** MT5 EA or Python Bridge  
**Interface:** POST /api/mt5/tick

```javascript
// Request from MT5 EA (every tick, high frequency)
POST /api/mt5/tick
{
  "symbol": "XAUUSD",
  "timeframe": "H1",
  "bid": 2375.25,
  "ask": 2375.35,
  "volume": 250,
  "timestamp": 1712145900500  // ms precision
}
```

### Component 2: Candle Manager
**Location:** lib/candle-manager.js  
**Responsibility:** Aggregate ticks → candles → state machine

```javascript
class CandleManager {
  /**
   * Ingest tick
   */
  async onTick(symbol, tf, bid, ask, volume, timestamp) {
    const candle = this.getCurrentCandle(symbol, tf);
    
    if (!candle.isOpen) {
      // Time to close? Create new candle
      await this.closeCandle(symbol, tf);
      this.createNewCandle(symbol, tf, timestamp);
    }
    
    // Update current candle
    const mid = (bid + ask) / 2;
    candle.high = Math.max(candle.high, mid);
    candle.low = Math.min(candle.low, mid);
    candle.close = mid;
    candle.volume += volume;
    candle.lastTickTime = timestamp;
    
    // Check if needs SSE broadcast (every 5 min or significant move)
    if (this.shouldBroadcast(candle)) {
      await this.broadcastCandleUpdate(symbol, tf, candle);
    }
  }
  
  /**
   * Close candle (fired at T+0ms of next period)
   */
  async closeCandle(symbol, tf) {
    const candle = this.getClosed Candle(symbol, tf);
    candle.status = "closed";
    candle.closedAt = Date.now();
    
    // CRITICAL: Emit event
    this.emit('candle:closed', {
      symbol, timeframe: tf,
      candle, timestamp: candle.closedAt
    });
    
    return candle;
  }
  
  /**
   * Get candle state
   */
  getCandle(symbol, tf) {
    const key = `${symbol}:${tf}`;
    return this.candles[key] || null;
  }
}
```

### Component 3: Indicator Engine
**Location:** lib/indicator-engine.js  
**Trigger:** "candle:closed" event

```javascript
class IndicatorEngine {
  /**
   * Listen for candle closes
   */
  constructor(candleManager) {
    candleManager.on('candle:closed', (event) => {
      this.onCandleClosed(event.symbol, event.timeframe, event.candle);
    });
  }
  
  /**
   * On candle close: recalculate ALL indicators
   */
  async onCandleClosed(symbol, tf, closedCandle) {
    const startTime = Date.now();
    
    // Load historical candles (last 30 for H1 = 30 hours)
    const history = await this.loadCandleHistory(symbol, tf, 30);
    const allCandles = [...history, closedCandle];
    
    // Calculate technical indicators
    const indicators = {
      rsi: this.calculateRSI(allCandles, 14),           // 14 periods
      macd: this.calculateMACD(allCandles, 12, 26, 9),  // EMA 12,26, signal 9
      bb: this.calculateBollingerBands(allCandles, 20, 2),  // 20 SMA, 2 stddev
      atr: this.calculateATR(allCandles, 14),           // 14 periods ATR
      ma_20: this.calculateMA(allCandles, 20),          // Simple MA
      ma_50: this.calculateMA(allCandles, 50),
      ma_200: this.calculateMA(allCandles, 200),
      
      // Trend detection
      slope: this.calculateTrendSlope(allCandles, 14),  // Recent slope direction
      momentum: this.calculateMomentum(allCandles, 12), // Price momentum
    };
    
    // Store indicators IN candle object
    closedCandle.indicators = indicators;
    closedCandle.indicatorsCalculatedAt = Date.now();
    
    // Emit event: "indicators:ready"
    this.emit('indicators:ready', {
      symbol, timeframe: tf, candle: closedCandle, indicators, duration_ms: Date.now() - startTime
    });
    
    return indicators;
  }
  
  // Helper: RSI calculation
  calculateRSI(candles, period = 14) {
    const closes = candles.map(c => c.close);
    const gains = [];
    const losses = [];
    
    for (let i = 1; i < closes.length; i++) {
      const delta = closes[i] - closes[i-1];
      gains.push(delta > 0 ? delta : 0);
      losses.push(delta < 0 ? Math.abs(delta) : 0);
    }
    
    const avgGain = gains.slice(-period).reduce((a,b) => a+b, 0) / period;
    const avgLoss = losses.slice(-period).reduce((a,b) => a+b, 0) / period;
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    const rsi = 100 - (100 / (1 + rs));
    
    return parseFloat(rsi.toFixed(2));
  }
  
  // Similar helpers for MACD, ATR, Bollinger Bands, etc.
}
```

### Component 4: Agent Orchestrator
**Location:** src/agents/orchestrator.js  
**Trigger:** "indicators:ready" event

```javascript
class AgentOrchestrator {
  constructor(indicatorEngine) {
    indicatorEngine.on('indicators:ready', (event) => {
      this.onIndicatorsReady(event);
    });
  }
  
  /**
   * Run agents on closed candle + fresh indicators
   */
  async onIndicatorsReady(event) {
    const { symbol, timeframe, candle, indicators } = event;
    const startTime = Date.now();
    
    // Load user reference prices
    const prefs = new SymbolPreferences();
    const userRef = await prefs.getEffectivePrice(symbol);
    
    // Prepare market context
    const marketContext = {
      symbol,
      timeframe,
      currentCandle: candle,
      indicators,
      userPrice: userRef.effectivePrice,
      systemPrice: userRef.systemPrice,
      closedAt: candle.closedAt,
      candleIndex: event.candleIndex
    };
    
    // Run agents in parallel
    const agents = [
      new MomentumAnalyzer(),
      new TrendDetector(),
      new SupportResistanceAnalyzer(),
      new PatternDetector()
    ];
    
    const results = await Promise.all(
      agents.map(agent => agent.analyze(marketContext))
    );
    
    // Aggregate results
    const signal = this.aggregateSignals(results, marketContext);
    
    // Store result with timestamp
    signal.closedCandleReference = {
      time: candle.time,
      index: event.candleIndex,
      analyzedAt: Date.now()
    };
    
    // Emit: "signal:generated"
    this.emit('signal:generated', {
      symbol, timeframe, signal, duration_ms: Date.now() - startTime
    });
    
    return signal;
  }
}
```

### Component 5: SSE Broadcaster
**Responsibility:** Synchronize all clients

```javascript
class SyncBroadcaster {
  constructor(candleManager, indicatorEngine, orchestrator) {
    // Listen to ALL events in sequence
    candleManager.on('candle:closed', (event) => {
      this.broadcastCandleClose(event);
    });
    
    indicatorEngine.on('indicators:ready', (event) => {
      this.broadcastIndicatorUpdate(event);
    });
    
    orchestrator.on('signal:generated', (event) => {
      this.broadcastSignal(event);
    });
  }
  
  /**
   * Broadcast to all connected clients (SSE)
   */
  broadcastCandleClose(event) {
    const message = {
      type: "candle_closed",
      symbol: event.symbol,
      timeframe: event.timeframe,
      candle: event.candle,
      broadcastAt: Date.now(),   // Proof of sync
      sequence: 1
    };
    
    this.sseClients.forEach(res => {
      res.write(`data: ${JSON.stringify(message)}\n\n`);
    });
  }
  
  broadcastIndicatorUpdate(event) {
    const message = {
      type: "indicators_updated",
      symbol: event.symbol,
      timeframe: event.timeframe,
      indicators: event.indicators,
      broadcastAt: Date.now(),
      sequence: 2
    };
    
    this.sseClients.forEach(res => {
      res.write(`data: ${JSON.stringify(message)}\n\n`);
    });
  }
  
  broadcastSignal(event) {
    const message = {
      type: "signal_generated",
      symbol: event.symbol,
      timeframe: event.timeframe,
      signal: event.signal,
      broadcastAt: Date.now(),
      sequence: 3
    };
    
    this.sseClients.forEach(res => {
      res.write(`data: ${JSON.stringify(message)}\n\n`);
    });
  }
}
```

---

## 🔗 INTEGRATION WITH EXISTING ARCHITECTURE

### Where This Fits: symbol-preferences.js + data-source-manager.js

**Current flow:**
```
Agent calls getEffectivePrice(symbol)
  ↓
data-source-manager delegates to symbol-preferences
  ↓
symbol-preferences returns: locked > user > system
```

**New flow with real-time candles:**
```
TICK ARRIVES → Candle Manager updates open candle

CANDLE CLOSES (T0:00) → Indicator Engine runs

INDICATORS READY → Agent Orchestrator calls:
  ├─ getEffectivePrice(symbol) via data-source-manager
  │  └─ Returns: user price (with protection from symbol-preferences)
  │
  ├─ getCandle(symbol, H1)
  │  └─ Returns: closed candle with fresh indicators
  │
  └─ getMarketContext(symbol)
     └─ Returns: { candle, indicators, price, session, etc. }

SIGNAL GENERATED → SSE broadcast to Extension/Studio/Dashboard
  └─ All see SAME candle, SAME indicators, at SAME time timestamp
```

### Key File Locations

```
EXISTING (No changes):
  src/services/symbol-preferences.js      ← Already manages user prices
  lib/data-source-manager.js              ← Already manages price hierarchy

NEW:
  lib/candle-manager.js                   ← Manage candle lifecycle + state machine
  lib/indicator-engine.js                 ← Calculate indicators on close
  src/agents/orchestrator-realtime.js     ← Trigger agents on indicators ready
  lib/sync-broadcaster.js                 ← SSE synchronization

UPDATED:
  server.js                               ← Add /api/mt5/tick endpoint
  mt5_data.json                           ← Add current candle + closed candles history
```

---

## 📈 REAL-TIME DATA STRUCTURE

### Updated mt5_data.json

```json
{
  "symbol": "XAUUSD",
  "realtimeStatus": {
    "lastTickAt": 1712145900500,
    "candlesUpdatedAt": 1712146000000,
    "nextCandleCloseAt": 1712149600000,
    "ticksPerSecond": 3.5
  },
  
  "currentCandle": {
    "timeframe": "H1",
    "period": 10,
    "time": "2026-04-03T10:00:00Z",
    "open": 2375.30,
    "high": 2375.45,
    "low": 2374.80,
    "close": 2374.95,
    "volume": 2500,
    "status": "in_progress",
    "percentComplete": 45,
    "secondsRemaining": 1980
  },
  
  "closedCandles": {
    "H1": [
      {
        "time": "2026-04-03T09:00:00Z",
        "open": 2375.10,
        "high": 2375.80,
        "low": 2373.50,
        "close": 2374.20,
        "volume": 3200,
        "status": "closed",
        "closedAt": 1712142000000,
        "indicators": {
          "rsi": 52.1,
          "macd": { "value": 0.45, "signal": 0.38, "histogram": 0.07 },
          "bb": { "upper": 2376.5, "middle": 2374.8, "lower": 2373.1 },
          "atr": 1.8,
          "ma_20": 2372.50,
          "ma_50": 2371.30,
          "ma_200": 2370.50,
          "trend": "BULLISH",
          "momentum": "POSITIVE"
        },
        "agentSignal": {
          "direction": "LONG",
          "score": 72,
          "entry": 2374.20,
          "sl": 2373.10,
          "tp": 2376.50,
          "reasoning": "Bullish momentum on close + MA support",
          "analyzedAt": 1712142001234
        }
      },
      // ... previous H1 candles
    ],
    
    "M15": [
      // 15-minute candles for intraday granularity
    ],
    
    "D1": [
      // Daily candles for longer-term context
    ]
  },
  
  "indicators": {
    "calculatedFor": "H1",
    "lastCalculatedAt": 1712142000234,
    "values": {
      "rsi": 52.1,
      "macd": { ... },
      "bb": { ... }
    }
  }
}
```

---

## 🎯 SYNCHRONIZATION GUARANTEE

### How All Clients See Same Data

**Extension states:**
```javascript
EventSource('/agent-activity')
  .onmessage = (event) => {
    msg = JSON.parse(event.data);
    
    if (msg.type === 'candle_closed') {
      // GUARANTEED: Extension gets this BEFORE signal
      console.log('Candle closed at:', msg.broadcastAt);
      updateChart(msg.candle);
    }
    
    if (msg.type === 'signal_generated') {
      // GUARANTEED: Same candle that agent analyzed
      console.log('Signal based on candle at:', msg.signal.closedCandleReference.time);
      showSignal(msg.signal);
    }
  };
```

**Timestamp proof:**
```javascript
// Sequence guarantee via timestamps
T0 = 1712142000000 (candle closes)
T1 = 1712142000050 (indicators calculated, ready)
T2 = 1712142000150 (agents analyzed, signal generated)
T3 = 1712142000200 (all clients broadcast)

Extension receives:
  - Candle (T0)
  - Indicators (T1)
  - Signal (T2)
  
In the SAME SSE stream, same sequence, <200ms total.
Everyone gets "T0 candle" at "T0 time"
```

---

## 🚀 HOW THIS ENABLES PROPER ANALYSIS

### Problem Solved: Candle-based Decisions

**BEFORE (current):**
```
Agent runs: "What's the price?" → 2375.30 (current)
Agent thinks: "Should I trade?" (no candle, no context)
Result: Confused signal based on point-in-time price
```

**AFTER (with real-time candles):**
```
10:00:00 → Candle OPEN @ 2375.30
10:59:59 → Candle CLOSE @ 2375.10 (final)
11:00:00 → Full analysis based on:
           - Closed candle with OHLCV
           - Fresh RSI, MACD, Bollinger Bands
           - Trend context (MA20, MA50, MA200)
           - Signal: "LONG, score 72, entry 2374.20"

Result: Clean, reproducible, backtest-able analysis
```

### Problem Solved: Indictor Reliability

**BEFORE:**
```
RSI = static value from file (might be days old)
Agent thinks: "RSI is 52" (but what timeframe? what data?)
```

**AFTER:**
```
Candle closes at 11:00
RSI recalculated on latest 14 candles
RSI = 52.1 (PROVEN fresh)
Timestamp: 1712142000050 (100ms after close)
Agent trusts: This RSI is guaranteed recent
```

### Problem Solved: Multi-Agent Sync

**BEFORE:**
```
Momentum agent sees: XAUUSD @ 2375.30
Trend agent sees: XAUUSD @ 2375.25
They make different decisions
```

**AFTER:**
```
Candle closes → BROADCAST (single source of truth)

Both agents receive:
  { 
    candle: { open: 2375.30, close: 2375.10 },
    indicators: { rsi: 52.1, trend: BULLISH },
    broadcastAt: 1712142000200
  }

Both make decisions based on SAME data, SAME moment
→ Coherent portfolio analysis
```

---

## 📋 IMPLEMENTATION PHASES

### Phase 1: Candle Manager (Foundation)
- [ ] Create lib/candle-manager.js
- [ ] Implement tick ingestion
- [ ] Implement candle state machine
- [ ] Emit 'candle:closed' event

### Phase 2: Indicator Engine
- [ ] Create lib/indicator-engine.js
- [ ] Implement RSI, MACD, Bollinger Bands, ATR, MA calculations
- [ ] Listen for 'candle:closed' events
- [ ] Emit 'indicators:ready' events

### Phase 3: Real-time Orchestrator
- [ ] Update src/agents/orchestrator-realtime.js
- [ ] Listen for 'indicators:ready' events
- [ ] Integrate with symbol-preferences (user prices)
- [ ] Emit 'signal:generated' events

### Phase 4: SSE Sync Broadcaster
- [ ] Create lib/sync-broadcaster.js
- [ ] Listen to all 3 events
- [ ] Broadcast in sequence to clients
- [ ] Include timestamps for verification

### Phase 5: Server Integration
- [ ] Add POST /api/mt5/tick endpoint
- [ ] Update mt5_data.json structure
- [ ] Connect tick → candle manager
- [ ] Connect all broadcasters to SSE

### Phase 6: Client Updates
- [ ] Update extension to handle real-time candles
- [ ] Update studio chart to show candle state
- [ ] Update dashboard to show signal timestamp match

---

## ✅ SUCCESS CRITERIA

- [x] Candles open/close at precise times (no guessing)
- [x] Indicators recalculate ONLY on candle close
- [x] Agents trigger ONLY on indicators ready
- [x] All clients see SAME candle at SAME timestamp
- [x] No external APIs for real-time data
- [x] Fully local (MT5 + Node.js + browser)
- [x] Backward compatible with symbol-preferences + data-source-manager
- [x] Timestamps prove synchronization
- [x] Reproducible for backtesting later

---

## 🔗 CRITICAL: How This Works With User Reference Prices

**Workflow:**

```
Candle closes (11:00)
  ↓
Indicators calculated on fresh data
  ↓
Agent runs analysis:
  1. Load effective price via data-source-manager
     → Returns user reference (if registered) OR system price
  2. Load closed candle with indicators
     → Returns OHLCV + RSI/MACD/etc.
  3. Generate signal
     → Based on user price as reference, candle as proof
  ↓
Signal includes:
  {
    direction: "LONG",
    entry: 2374.20,        // Possible entry near closed candle
    userPrice: 2375.50,    // User reference (if set)
    candle: { ... },       // The actual closed candle analyzed
    indicators: { ... },   // Fresh RSI/MACD/etc.
    closedAt: 1712142000000
  }
```

**This ensures:**
- User price is protected (never silently overridden)
- Analysis is based on real closed candles
- Indicators are fresh
- Signal is reproducible

---

## 🎯 CRITICAL QUESTION FOR USER VALIDATION

Does this architecture answer your requirements?

1. ✅ **Temps réel** → Tick processor + candle state machine → real-time updates
2. ✅ **Clôtures de bougies** → Candle manager emits 'candle:closed' event at precise moment
3. ✅ **Indicateurs exploitables** → Recalc on close with full history + trend detection
4. ✅ **Synchronisation agents** → All agents listen to same 'indicators:ready'  event
5. ✅ **Compatible agents** → Orchestrator integrates with symbol-preferences
6. ✅ **Sans API payante** → Local MT5 ticks + Node.js calculations
7. ✅ **Sans casser existant** → symbol-preferences + data-source-manager unchanged
8. ✅ **Maîtrisé** → Everything local, timestamped, synchronous

**If yes to all → Ready to implement**  
**If no → What needs adjustment?**
