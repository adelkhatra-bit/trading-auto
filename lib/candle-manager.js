const EventEmitter = require('events');
const fs = require('fs').promises;
const path = require('path');

/**
 * CandleManager - Real-time candle aggregation engine
 * 
 * Responsibility:
 * - Aggregate ticks into OHLC candles
 * - Manage candle state machine (open → in_progress → closed)
 * - Detect candle close events (time-based)
 * - Persist closed candles to storage
 * - Emit events: candle:opened, candle:update, candle:closed
 * 
 * Architecture:
 * Store in-memory current candle for fast updates
 * Store closed candle history in mt5_data.json for persistence
 * 
 * Timeframes supported: D1, H1, M15, M5, M1
 * Frequency of ticks: 1-2 seconds (POST /api/mt5/tick)
 * Latency: <50ms from tick to candle state update
 */

class CandleManager extends EventEmitter {
  constructor(options = {}) {
    super();
    
    this.dataDir = options.dataDir || path.join(__dirname, '../store');
    this.dataFile = path.join(this.dataDir, 'mt5_data.json');
    
    // In-memory candle state
    // Key: 'SYMBOL:TIMEFRAME' (e.g., 'XAUUSD:H1')
    this.candleState = {};
    
    // Timeframe definitions (in milliseconds)
    this.timeframes = {
      'D1': 24 * 60 * 60 * 1000,
      'H1': 60 * 60 * 1000,
      'M15': 15 * 60 * 1000,
      'M5': 5 * 60 * 1000,
      'M1': 60 * 1000
    };
    
    // Timer for detecting candle closes
    // Check every 50ms if any candle should close
    this.closeCheckInterval = null;
    this.closeCheckFrequency = 50; // milliseconds
    
    // Track last update time per symbol for deduping
    this.lastUpdateTime = {};
    
    // Config
    this.enablePersistence = options.enablePersistence !== false;
    this.maxCandlesInMemory = options.maxCandlesInMemory || 1000;
    
    this.initialized = false;
  }

  /**
   * Initialize: Load existing candles from storage
   */
  async initialize() {
    try {
      const data = await fs.readFile(this.dataFile, 'utf-8');
      const parsed = JSON.parse(data);
      
      // Restore candle history per symbol
      if (parsed.candleHistory) {
        for (const [symbolTimeframe, candles] of Object.entries(parsed.candleHistory)) {
          // Keep only last N candles in memory
          this.candleState[symbolTimeframe] = {
            closedCandles: candles.slice(-this.maxCandlesInMemory),
            currentCandle: null,
            status: 'ready'
          };
        }
      }
      
      this.initialized = true;
      console.log(`[CandleManager] Initialized. Loaded ${Object.keys(this.candleState).length} symbol-timeframe pairs.`);
    } catch (err) {
      // File doesn't exist yet, start fresh
      console.log(`[CandleManager] Starting fresh (no existing data).`);
      this.initialized = true;
    }
    
    // Start close detection timer
    this._startCloseDetection();
  }

  /**
   * Process incoming tick
   * Called from POST /api/mt5/tick
   * 
   * Tick format: { symbol, price, bid, ask, volume, timestamp }
   */
  async onTick(symbol, price, bid, ask, volume, timestamp) {
    if (!this.initialized) {
      console.warn(`[CandleManager] Not initialized, ignoring tick for ${symbol}`);
      return;
    }

    // Process for all supported timeframes
    for (const [tf, tfMillis] of Object.entries(this.timeframes)) {
      await this._processTickForTimeframe(symbol, tf, tfMillis, price, bid, ask, volume, timestamp);
    }
  }

  /**
   * Internal: Process tick for a specific timeframe
   * 
   * State machine:
   * 1. If no current candle: create new one (open)
   * 2. If current candle active: update OHLC (in_progress)
   * 3. If timestamp crosses candle boundary: close old, open new (closed + opened)
   */
  async _processTickForTimeframe(symbol, tf, tfMillis, price, bid, ask, volume, timestamp) {
    const key = `${symbol}:${tf}`;
    const alignedTime = this._alignToTimeframe(timestamp, tfMillis);
    
    // Ensure state exists
    if (!this.candleState[key]) {
      this.candleState[key] = {
        closedCandles: [],
        currentCandle: null,
        status: 'ready'
      };
    }

    const state = this.candleState[key];
    
    // Case 1: No current candle OR time crosses boundary
    if (!state.currentCandle || alignedTime > state.currentCandle.timeOpen) {
      // Close previous candle if exists
      if (state.currentCandle) {
        state.currentCandle.status = 'closed';
        state.currentCandle.closeTime = state.currentCandle.timeOpen + tfMillis;
        state.closedCandles.push(state.currentCandle);
        
        // Keep only recent candles in memory
        if (state.closedCandles.length > this.maxCandlesInMemory) {
          state.closedCandles = state.closedCandles.slice(-this.maxCandlesInMemory);
        }
        
        // Emit candle:closed event
        this.emit('candle:closed', {
          symbol,
          timeframe: tf,
          candle: state.currentCandle,
          timestamp: Date.now()
        });
      }
      
      // Open new candle
      state.currentCandle = {
        timeOpen: alignedTime,
        open: price,
        high: price,
        low: price,
        close: price,
        volume: volume,
        status: 'open',
        bid,
        ask,
        tickCount: 1,
        firstTickTime: timestamp,
        lastTickTime: timestamp
      };
      
      // Emit candle:opened event
      this.emit('candle:opened', {
        symbol,
        timeframe: tf,
        candle: state.currentCandle,
        timestamp: Date.now()
      });
    } 
    // Case 2: Update existing current candle
    else {
      state.currentCandle.high = Math.max(state.currentCandle.high, price);
      state.currentCandle.low = Math.min(state.currentCandle.low, price);
      state.currentCandle.close = price;
      state.currentCandle.volume += volume;
      state.currentCandle.tickCount += 1;
      state.currentCandle.lastTickTime = timestamp;
      state.currentCandle.status = 'in_progress';
      state.currentCandle.bid = bid;
      state.currentCandle.ask = ask;
      
      // Emit candle:update event (throttled to avoid spam)
      const now = Date.now();
      if (!this.lastUpdateTime[key] || now - this.lastUpdateTime[key] > 100) {
        this.emit('candle:update', {
          symbol,
          timeframe: tf,
          candle: state.currentCandle,
          timestamp: now
        });
        this.lastUpdateTime[key] = now;
      }
    }
  }

  /**
   * Timer-based close detection
   * Runs every 50ms to check if any candles should close
   * (In case ticks have gaps)
   */
  _startCloseDetection() {
    if (this.closeCheckInterval) {
      clearInterval(this.closeCheckInterval);
    }

    this.closeCheckInterval = setInterval(() => {
      const now = Date.now();
      
      for (const [key, state] of Object.entries(this.candleState)) {
        if (!state.currentCandle) continue;
        
        const [symbol, tf] = key.split(':');
        const tfMillis = this.timeframes[tf];
        
        // Check if current candle time window has passed
        const candle = state.currentCandle;
        const expectedCloseTime = candle.timeOpen + tfMillis;
        
        if (now >= expectedCloseTime) {
          // Auto-close the candle
          candle.status = 'closed';
          candle.closeTime = expectedCloseTime;
          state.closedCandles.push(candle);
          
          if (state.closedCandles.length > this.maxCandlesInMemory) {
            state.closedCandles = state.closedCandles.slice(-this.maxCandlesInMemory);
          }
          
          // Emit close event
          this.emit('candle:closed', {
            symbol,
            timeframe: tf,
            candle: candle,
            timestamp: now,
            reason: 'timeout' // Distinguish from tick-driven close
          });
          
          // Clear current candle so next tick opens new one
          state.currentCandle = null;
        }
      }
    }, this.closeCheckFrequency);
  }

  /**
   * Get current candle for symbol + timeframe
   */
  getCurrentCandle(symbol, timeframe) {
    const key = `${symbol}:${timeframe}`;
    const state = this.candleState[key];
    return state?.currentCandle || null;
  }

  /**
   * Get closed candles history for symbol + timeframe
   * Returns last N candles
   */
  getClosedCandles(symbol, timeframe, limit = 100) {
    const key = `${symbol}:${timeframe}`;
    const state = this.candleState[key];
    
    if (!state || !state.closedCandles) return [];
    
    return state.closedCandles.slice(-limit);
  }

  /**
   * Get complete candle set (current + historical)
   */
  getCandles(symbol, timeframe, limit = 100) {
    const closed = this.getClosedCandles(symbol, timeframe, limit - 1);
    const current = this.getCurrentCandle(symbol, timeframe);
    
    if (current && current.status !== 'closed') {
      return [...closed, current];
    }
    return closed;
  }

  /**
   * Get candle state overview for UI
   */
  getStateOverview(symbol, timeframe) {
    const key = `${symbol}:${timeframe}`;
    const state = this.candleState[key];
    
    if (!state) {
      return { status: 'MISSING', symbol, timeframe };
    }

    return {
      symbol,
      timeframe,
      status: state.currentCandle ? 'ACTIVE' : 'WAITING_FOR_TICK',
      currentCandle: state.currentCandle || null,
      closedCandleCount: state.closedCandles?.length || 0,
      lastClosedCandle: state.closedCandles?.at(-1) || null,
      updatedAt: Date.now()
    };
  }

  /**
   * Persist candle state to storage
   * Called periodically or on demand
   */
  async persist() {
    if (!this.enablePersistence) return;

    try {
      const data = {
        version: '1.0',
        lastSaved: Date.now(),
        candleHistory: {}
      };

      // Build history object
      for (const [key, state] of Object.entries(this.candleState)) {
        data.candleHistory[key] = state.closedCandles || [];
      }

      // Create directory if needed
      await fs.mkdir(this.dataDir, { recursive: true });

      // Write file
      await fs.writeFile(this.dataFile, JSON.stringify(data, null, 2), 'utf-8');
      
      console.log(`[CandleManager] Persisted ${Object.keys(this.candleState).length} candle sets to storage.`);
    } catch (err) {
      console.error(`[CandleManager] Persistence error:`, err.message);
    }
  }

  /**
   * Align timestamp to timeframe boundary
   * 
   * Example:
   * - timestamp: 1713158567890 (arbitrary time)
   * - H1 millis: 3600000
   * - Returns: aligned time (beginning of current hour)
   */
  _alignToTimeframe(timestamp, tfMillis) {
    // For daily: align to midnight UTC
    if (tfMillis === 24 * 60 * 60 * 1000) {
      const date = new Date(timestamp);
      date.setUTCHours(0, 0, 0, 0);
      return date.getTime();
    }

    // For others: align to multiples of timeframe duration
    return Math.floor(timestamp / tfMillis) * tfMillis;
  }

  /**
   * Health check
   */
  getHealth() {
    return {
      initialized: this.initialized,
      activeCandles: Object.keys(this.candleState).length,
      timerRunning: !!this.closeCheckInterval,
      timestamp: Date.now()
    };
  }

  /**
   * Cleanup
   */
  async shutdown() {
    if (this.closeCheckInterval) {
      clearInterval(this.closeCheckInterval);
    }
    
    // Final persistence
    await this.persist();
    
    console.log(`[CandleManager] Shutdown complete.`);
  }
}

module.exports = CandleManager;
