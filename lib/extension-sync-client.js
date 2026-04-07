/**
 * ═══════════════════════════════════════════════════════════════════════════════
 * EXTENSION SYNC CLIENT
 * ═══════════════════════════════════════════════════════════════════════════════
 * 
 * SINGLE SOURCE OF TRUTH for Extension Chrome + HTML Popup
 * 
 * Use:
 *   - Browser (Extension): import { ExtensionSyncClient } from 'extension-sync-client.js'
 *   - HTML Popup: <script src="/lib/extension-sync-client.js"></script>
 *   
 *   const client = new ExtensionSyncClient('http://localhost:4000');
 *   client.connect();
 *   
 *   client.onData((data) => {
 *     console.log('Unified data:', data);
 *     // Update Extension + HTML UI with EXACT same data
 *   });
 */

class ExtensionSyncClient {
  constructor(serverURL = 'http://localhost:4000') {
    this.serverURL = serverURL.replace(/\/$/, '');
    this.eventSource = null;
    this.isConnected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 10;
    this.reconnectDelay = 2000; // 2s
    
    // Unified state (same for Extension + HTML)
    this.state = {
      systemStatus: { source: 'offline', fluxStatus: 'OFFLINE' },
      activeSymbol: { symbol: null, timeframe: 'H1', price: null },
      agentStates: {},
      currentData: null,
      mt5Data: {},
      tradingViewData: {}
    };
    
    // Callbacks
    this.callbacks = {
      onConnect: null,
      onDisconnect: null,
      onData: null,
      onMT5Data: null,
      onTradingViewData: null,
      onActiveSymbol: null,
      onAgentState: null,
      onError: null
    };
    
    // Request cache (for delayed subscribers)
    this.lastStateSnapshot = null;
    
    console.log('[ExtensionSyncClient] Initialized:', this.serverURL);
  }
  
  /**
   * Connect to unified SSE stream
   */
  connect() {
    if (this.isConnected) {
      console.warn('[ExtensionSyncClient] Already connected');
      return;
    }
    
    console.log('[ExtensionSyncClient] Connecting to', this.serverURL + '/extension/sync');
    
    try {
      this.eventSource = new EventSource(this.serverURL + '/extension/sync');
      
      // Handle all message types
      this.eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this._handleMessage(data);
        } catch (e) {
          console.error('[ExtensionSyncClient] Parse error:', e.message);
        }
      };
      
      this.eventSource.onopen = () => {
        this.isConnected = true;
        this.reconnectAttempts = 0;
        console.log('[ExtensionSyncClient] ✅ Connected');
        if (this.callbacks.onConnect) this.callbacks.onConnect();
      };
      
      this.eventSource.onerror = (err) => {
        this.isConnected = false;
        console.error('[ExtensionSyncClient] ❌ Connection error:', err.message);
        if (this.callbacks.onError) this.callbacks.onError(err);
        this._attemptReconnect();
      };
      
    } catch (e) {
      console.error('[ExtensionSyncClient] Failed to create EventSource:', e.message);
      this._attemptReconnect();
    }
  }
  
  /**
   * Disconnect from SSE stream
   */
  disconnect() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    this.isConnected = false;
    console.log('[ExtensionSyncClient] Disconnected');
    if (this.callbacks.onDisconnect) this.callbacks.onDisconnect();
  }
  
  /**
   * Request current state (HTTP fallback for late-joining clients)
   */
  async fetchCurrentState() {
    try {
      const response = await fetch(this.serverURL + '/extension/data');
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      if (data.ok) {
        this._updateState(data);
        this.lastStateSnapshot = data;
      }
      return data;
    } catch (e) {
      console.error('[ExtensionSyncClient] Failed to fetch state:', e.message);
      if (this.callbacks.onError) this.callbacks.onError(e);
      return null;
    }
  }
  
  /**
   * Register callback for unified data updates
   */
  onData(callback) {
    this.callbacks.onData = callback;
  }
  
  /**
   * Register callback for MT5 data specifically
   */
  onMT5Data(callback) {
    this.callbacks.onMT5Data = callback;
  }
  
  /**
   * Register callback for TradingView data specifically
   */
  onTradingViewData(callback) {
    this.callbacks.onTradingViewData = callback;
  }
  
  /**
   * Register callback for active symbol changes
   */
  onActiveSymbol(callback) {
    this.callbacks.onActiveSymbol = callback;
  }
  
  /**
   * Register callback for agent state changes
   */
  onAgentState(callback) {
    this.callbacks.onAgentState = callback;
  }
  
  /**
   * Register callback for connection errors
   */
  onError(callback) {
    this.callbacks.onError = callback;
  }
  
  /**
   * Register callback for connection established
   */
  onConnect(callback) {
    this.callbacks.onConnect = callback;
  }
  
  /**
   * Register callback for disconnection
   */
  onDisconnect(callback) {
    this.callbacks.onDisconnect = callback;
  }
  
  /**
   * Get current state (synchronous access to unified data)
   */
  getState() {
    return JSON.parse(JSON.stringify(this.state));
  }
  
  /**
   * Get specific symbol data
   */
  getSymbolData(symbol) {
    return this.state.mt5Data[symbol] || this.state.tradingViewData[symbol] || null;
  }
  
  /**
   * Send command to server (Extension → Server)
   */
  async sendCommand(command, payload) {
    try {
      const response = await fetch(this.serverURL + '/extension/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command, payload })
      });
      const data = await response.json();
      return data;
    } catch (e) {
      console.error(`[ExtensionSyncClient] Command '${command}' failed:`, e.message);
      return { ok: false, error: e.message };
    }
  }
  
  // ─────────────────────────────────────────────────────────────────────────────
  // INTERNAL METHODS
  // ─────────────────────────────────────────────────────────────────────────────
  
  /**
   * Handle unified SSE messages
   */
  _handleMessage(data) {
    const type = data.type || 'unknown';
    
    // Update state
    this._updateState(data);
    
    // Type-specific callbacks
    switch (type) {
      case 'initial-sync':
        console.log('[ExtensionSyncClient] Initial sync received');
        if (this.callbacks.onData) this.callbacks.onData(data);
        break;
        
      case 'mt5-data':
        console.log('[ExtensionSyncClient] MT5 data:', data.symbol, '@', data.price);
        this.state.mt5Data[data.symbol] = data;
        if (this.callbacks.onMT5Data) this.callbacks.onMT5Data(data);
        if (this.callbacks.onData) this.callbacks.onData(data);
        break;
        
      case 'tradingview-data':
        console.log('[ExtensionSyncClient] TradingView data:', data.symbol);
        this.state.tradingViewData[data.symbol] = data;
        if (this.callbacks.onTradingViewData) this.callbacks.onTradingViewData(data);
        if (this.callbacks.onData) this.callbacks.onData(data);
        break;
        
      case 'active-symbol':
        console.log('[ExtensionSyncClient] Active symbol:', data.symbol);
        this.state.activeSymbol = data;
        if (this.callbacks.onActiveSymbol) this.callbacks.onActiveSymbol(data);
        if (this.callbacks.onData) this.callbacks.onData(data);
        break;
        
      case 'agent-state-update':
        console.log('[ExtensionSyncClient] Agent state:', data.agent, data.status);
        this.state.agentStates[data.agent] = data;
        if (this.callbacks.onAgentState) this.callbacks.onAgentState(data);
        if (this.callbacks.onData) this.callbacks.onData(data);
        break;
        
      default:
        console.log('[ExtensionSyncClient] Message type:', type);
        if (this.callbacks.onData) this.callbacks.onData(data);
    }
  }
  
  /**
   * Update internal state from message
   */
  _updateState(data) {
    if (data.systemStatus) this.state.systemStatus = data.systemStatus;
    if (data.activeSymbol) this.state.activeSymbol = data.activeSymbol;
    if (data.agentStates) this.state.agentStates = data.agentStates;
    if (data.currentData) this.state.currentData = data.currentData;
    if (data.symbol) {
      // For mt5-data and tradingview-data messages
      const key = data.source?.includes('tradingview') ? 'tradingViewData' : 'mt5Data';
      this.state[key][data.symbol] = data;
    }
  }
  
  /**
   * Attempt reconnection
   */
  _attemptReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[ExtensionSyncClient] Max reconnection attempts reached');
      return;
    }
    
    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1);
    console.log(`[ExtensionSyncClient] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    setTimeout(() => {
      this.connect();
    }, delay);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Export for Module Systems
// ═══════════════════════════════════════════════════════════════════════════════

if (typeof module !== 'undefined' && module.exports) {
  module.exports = ExtensionSyncClient;
}

// Make available globally in browser
if (typeof window !== 'undefined') {
  window.ExtensionSyncClient = ExtensionSyncClient;
}
