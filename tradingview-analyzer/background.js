// background.js v3.0 — Service Worker (MT5 Source of Truth - Architecture Complète)
// Centralise toute logique: parle au backend, cache l'état, distribue aux content/popup
'use strict';

const API = 'http://127.0.0.1:4000';  // TRADING AUTO EXCLUSIVE
const POLL_INTERVAL = 1500;  // Poll resserré pour limiter le drift backend/extension
const SCRAPE_INTERVAL = 1000; // Scrape TradingView DOM en quasi temps-réel
const FOREGROUND_ENFORCE_MS = 1200;
const STORAGE_KEY_BG_STATE = 'taa_bg_system_state_v1';

// ── GLOBAL STATE ──────────────────────────────────────────────────────────
let isFetching = false;  // Protection: évite les requêtes parallèles
let lastForegroundEnforceAt = 0;
let foregroundTimer = null;

let systemState = {
  backendReady: false,
  mt5Connected: false,
  lastSnapshot: null,
  lastUpdate: null,
  activeSymbol: null,
  activeTimeframe: 'H1',
  activePrice: null,
  activeTradingViewTabId: null,
  selectedTimeframes: ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1'],
};

const PERSISTENT_POPUP_URL = chrome.runtime.getURL('popup.html?persistent=1');
let persistentPopupWindowId = null;

async function hydratePersistentState() {
  try {
    const stored = await chrome.storage.local.get([STORAGE_KEY_BG_STATE]);
    const saved = stored && stored[STORAGE_KEY_BG_STATE];
    if (saved && typeof saved === 'object') {
      systemState = Object.assign({}, systemState, saved, {
        backendReady: false,
        mt5Connected: false
      });
    }
  } catch (_) {}
}

function persistBackgroundState() {
  try {
    chrome.storage.local.set({
      [STORAGE_KEY_BG_STATE]: {
        lastSnapshot: systemState.lastSnapshot || null,
        lastUpdate: systemState.lastUpdate || null,
        activeSymbol: systemState.activeSymbol || null,
        activeTimeframe: systemState.activeTimeframe || 'H1',
        activePrice: systemState.activePrice || null,
        activeTradingViewTabId: systemState.activeTradingViewTabId || null,
        selectedTimeframes: Array.isArray(systemState.selectedTimeframes) ? systemState.selectedTimeframes : ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1']
      }
    }).catch(() => {});
  } catch (_) {}
}

function scheduleForegroundEnforce() {
  if (persistentPopupWindowId === null) return;
  const now = Date.now();
  if (now - lastForegroundEnforceAt < FOREGROUND_ENFORCE_MS) return;
  if (foregroundTimer) clearTimeout(foregroundTimer);
  foregroundTimer = setTimeout(async () => {
    try {
      const win = await chrome.windows.get(persistentPopupWindowId);
      if (!win || typeof win.id !== 'number') {
        persistentPopupWindowId = null;
        return;
      }
      const updatePatch = win.state === 'minimized'
        ? { state: 'normal', focused: true, drawAttention: false }
        : { focused: true, drawAttention: false };
      await chrome.windows.update(persistentPopupWindowId, updatePatch);
      lastForegroundEnforceAt = Date.now();
    } catch (_) {
      persistentPopupWindowId = null;
    }
  }, 160);
}

async function openPersistentPopupWindow() {
  if (persistentPopupWindowId !== null) {
    try {
      await chrome.windows.update(persistentPopupWindowId, { focused: true, drawAttention: true });
      return;
    } catch (_) {
      persistentPopupWindowId = null;
    }
  }

  const existingTabs = await chrome.tabs.query({ url: PERSISTENT_POPUP_URL });
  if (existingTabs.length > 0) {
    const existingTab = existingTabs[0];
    if (existingTab.windowId !== undefined) {
      persistentPopupWindowId = existingTab.windowId;
      await chrome.windows.update(existingTab.windowId, { focused: true, drawAttention: true });
      return;
    }
  }

  const createdWindow = await chrome.windows.create({
    url: PERSISTENT_POPUP_URL,
    type: 'popup',
    width: 460,
    height: 820,
    focused: true
  });

  persistentPopupWindowId = createdWindow && typeof createdWindow.id === 'number' ? createdWindow.id : null;
  scheduleForegroundEnforce();
}

function isTradingViewUrl(url) {
  return typeof url === 'string' && url.includes('tradingview.com');
}

function rememberTradingViewTab(tab) {
  if (tab && typeof tab.id === 'number' && isTradingViewUrl(tab.url)) {
    systemState.activeTradingViewTabId = tab.id;
  }
}

async function findTradingViewTab() {
  const tabs = await chrome.tabs.query({ url: 'https://*.tradingview.com/*' });
  if (!tabs.length) return null;

  const cached = tabs.find((tab) => tab.id === systemState.activeTradingViewTabId);
  const active = tabs.find((tab) => tab.active);
  const candidate = cached || active || tabs[0];
  rememberTradingViewTab(candidate);
  return candidate;
}

// ── SCRAP REAL TRADINGVIEW PANEL AND SEND TO SERVER ─────────────────────
async function scrapAndSendTradingView() {
  try {
    const tab = await findTradingViewTab();
    if (!tab || typeof tab.id !== 'number') return;

    const response = await chrome.tabs.sendMessage(tab.id, { type: 'SCRAP_PANEL' });
    if (!response || !response.ok || !response.data) {
      console.log('[BG] Scrap failed:', response);
      return;
    }

    const panelData = response.data;
    if (!panelData.symbol) {
      console.log('[BG] Scrap skipped: symbol not detected');
      return;
    }

    rememberTradingViewTab(tab);
    console.log('[BG] Panel scraped:', panelData.symbol, panelData.panelText);

    systemState.activeSymbol = panelData.symbol;
    systemState.activeTimeframe = panelData.timeframe || systemState.activeTimeframe;
    const parsedPanelPrice = Number(panelData.price);
    let resolvedPrice = Number.isFinite(parsedPanelPrice) && parsedPanelPrice > 0 ? parsedPanelPrice : null;

    systemState.activePrice = resolvedPrice;
    systemState.lastPanelData = panelData.panelText;
    systemState.lastUpdate = new Date().toISOString();
    persistBackgroundState();

    if (systemState.activePrice && systemState.activePrice > 0) {
      await fetch(API + '/extension/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          command: 'set-symbol',
          payload: {
            symbol: panelData.symbol,
            timeframe: panelData.timeframe || systemState.activeTimeframe,
            price: systemState.activePrice,
            mode: systemState.activeMode || undefined,
            source: 'tradingview-extension'  // tag so server/popup can recognise TV origin
          }
        }),
        signal: AbortSignal.timeout(3000)
      }).catch((err) => {
        console.log('[TV PUSH][ERROR] Context sync error:', err.message);
      });
    } else {
      console.log('[BG] Skipping /extension/command: no valid price yet');
      return;
    }

    // Correction : push live vers /tradingview/live (backend réel)
    const livePayload = {
      symbol:     panelData.symbol,
      timeframe:  panelData.timeframe || systemState.activeTimeframe,
      price:      systemState.activePrice,
      timestamp:  new Date().toISOString(),
      source:     'tradingview-extension',
      // NOUVEAU
      indicators: panelData.indicators || {},
      legend:     panelData.legend     || {},
      ask:        panelData.ask        || null,
      bid:        panelData.bid        || null
    };
    console.log('[TV PUSH] Envoi TradingView → backend:', livePayload);
    const tvResp = await fetch(API + '/tradingview/live', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(livePayload),
      signal: AbortSignal.timeout(3000)
    });
    if (tvResp.ok) {
      console.log('[TV PUSH OK] /tradingview/live:', livePayload.symbol, livePayload.timeframe, livePayload.price);
    } else {
      console.warn('[TV PUSH ERROR] /tradingview/live:', livePayload.symbol);
    }
  } catch (err) {
    console.log('[TV PUSH][ERROR] Scrap/send error:', err.message);
  }
}
// ── POLL BACKEND STATE ────────────────────────────────────────────────────
async function pollBackendState() {
  // Protection 1 : skip si une requête est déjà en cours
  if (isFetching) return;

  // Protection 2 : skip si aucun onglet actif (utilisateur absent)
  try {
    const activeTabs = await chrome.tabs.query({ active: true, currentWindow: true });
    if (activeTabs.length === 0) return;
  } catch (_) {}

  isFetching = true;
  try {
    // GET /live/state + /extension/data pour miroir strict TradingView
    const healthResp = await fetch(API + '/live/state', {
      signal: AbortSignal.timeout(2000)
    });
    
    if (!healthResp.ok) throw new Error('Backend unreachable');
    
    const health = await healthResp.json();
    systemState.backendReady = health.ok;
    systemState.mt5Connected = health?.bridge?.mt5Enabled === true;

    const extResp = await fetch(API + '/extension/data', {
      signal: AbortSignal.timeout(2000)
    });
    if (extResp.ok) {
      const extData = await extResp.json();
      if (extData && extData.ok) {
        const active = extData.activeSymbol || {};
        const current = extData.currentData || {};
        systemState.activeSymbol = active.symbol || systemState.activeSymbol;
        systemState.activeTimeframe = active.timeframe || systemState.activeTimeframe;
        systemState.activePrice = current.price || active.price || systemState.activePrice;
        systemState.lastSnapshot = current;
        systemState.lastUpdate = new Date().toISOString();
        persistBackgroundState();
      }
    }
    
    // Broadcast à tous les clients
    broadcastStateChange({
      type: 'STATE_UPDATE',
      state: systemState
    });
    
  } catch (err) {
    console.log('[BG] Poll error:', err.message);
    systemState.backendReady = false;
    systemState.mt5Connected = false;
  } finally {
    isFetching = false;  // Libère le verrou dans tous les cas
  }
}

// ── BROADCAST STATE TO CONTENT & POPUP ────────────────────────────────────
async function broadcastStateChange(message) {
  try {
    const tabs = await chrome.tabs.query({});
    tabs.forEach(tab => {
      try {
        chrome.tabs.sendMessage(tab.id, message).catch(() => {});
      } catch (_) {}
    });
  } catch (_) {}
}

// ── MESSAGE LISTENER (From popup / content) ────────────────────────────────
chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
  (async () => {
    try {
      // ─── GET SYSTEM STATE ─────────────────────────────────────────
      if (msg.type === 'GET_STATE') {
        sendResponse({ ok: true, state: systemState });
        return;
      }

      // ─── GET ACTIVE CONTEXT (symbole + TF détectés) ───────────────
      if (msg.type === 'GET_ACTIVE_CONTEXT') {
        if (systemState.activeSymbol) {
          sendResponse({ ok: true, context: {
            symbol:    systemState.activeSymbol,
            timeframe: systemState.activeTimeframe,
            price:     systemState.activePrice
          }});
        } else {
          sendResponse({ ok: false });
        }
        return;
      }

      // ─── SET MODE (SCALPER / SNIPER / SWING) ──────────────────────
      if (msg.type === 'SET_MODE') {
        systemState.activeMode = msg.mode || 'SNIPER';
        persistBackgroundState();
        sendResponse({ ok: true, mode: systemState.activeMode });
        return;
      }
      
      // ─── CHANGE SYMBOL ────────────────────────────────────────────
      if (msg.type === 'SET_SYMBOL') {
        const sym = msg.symbol?.toUpperCase();
        if (!sym) { sendResponse({ ok: false }); return; }
        
        try {
          const resp = await fetch(API + '/extension/command', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              command: 'set-symbol',
              payload: {
                symbol: sym,
                timeframe: systemState.activeTimeframe || 'H1',
                price: systemState.activePrice || null
              }
            }),
            signal: AbortSignal.timeout(3000)
          });
          
          if (resp.ok) {
            const data = await resp.json();
            systemState.activeSymbol = sym;
            systemState.lastSnapshot = data;
            systemState.lastUpdate = new Date().toISOString();
            persistBackgroundState();
            
            broadcastStateChange({ type: 'SYMBOL_CHANGED', symbol: sym });
            sendResponse({ ok: true, data });
          } else {
            sendResponse({ ok: false, error: 'Symbol not found' });
          }
        } catch (err) {
          sendResponse({ ok: false, error: err.message });
        }
        return;
      }
      
      // ─── CHANGE TIMEFRAME ─────────────────────────────────────────
      if (msg.type === 'SET_TIMEFRAME') {
        const tf = msg.timeframe;
        if (!tf) { sendResponse({ ok: false }); return; }
        
        systemState.activeTimeframe = tf;
        
        // Fetch chart data pour ce timeframe depuis le snapshot
        if (systemState.lastSnapshot) {
          broadcastStateChange({
            type: 'TIMEFRAME_CHANGED',
            timeframe: tf,
            snapshot: systemState.lastSnapshot
          });
        }
        
        sendResponse({ ok: true, timeframe: tf });
        return;
      }
      
      // ─── GET CHART DATA ──────────────────────────────────────────
      if (msg.type === 'GET_CHART') {
        try {
          const symbol = msg.symbol || systemState.activeSymbol;
          if (!symbol) { sendResponse({ ok: false, error: 'symbol required for GET_CHART' }); return; }
          const timeframe = msg.tf || systemState.activeTimeframe || 'H1';
          const resp = await fetch(
            API + `/klines?symbol=${encodeURIComponent(symbol)}&tf=${encodeURIComponent(timeframe)}&limit=200`,
            { signal: AbortSignal.timeout(3000) }
          );
          
          if (resp.ok) {
            const data = await resp.json();
            if (data.ok && data.candles && data.candles.length > 0) {
              sendResponse({ ok: true, data: { rates: data.candles } });
            } else {
              sendResponse({ ok: false, error: 'No chart data available' });
            }
          } else {
            sendResponse({ ok: false, error: 'Chart data unavailable' });
          }
        } catch (err) {
          sendResponse({ ok: false, error: err.message });
        }
        return;
      }
      
      // ─── RESOLVE SYMBOL DISABLED ────────────────────────────────────
      // All symbol data must come from real TradingView panel, not mapped database
      
      // ─── GET ECONOMIC EVENTS ─────────────────────────────────────
      if (msg.type === 'GET_ECONOMIC_EVENTS') {
        try {
          const resp = await fetch(API + '/economic-events', {
            signal: AbortSignal.timeout(3000)
          });
          
          const data = await resp.json();
          sendResponse({ ok: data.ok, events: data.events, error: data.error });
        } catch (err) {
          sendResponse({ ok: false, error: err.message });
        }
        return;
      }
      
      // ─── GET ASSET PRICE DISABLED ──────────────────────────────────
      // Prices must come from real TradingView panel only, never hardcoded
      
      // ─── SAVE MAPPING ────────────────────────────────────────────
      if (msg.type === 'SAVE_MAPPING') {
        const userInput = msg.userInput?.toUpperCase();
        const mt5Symbol = msg.mt5Symbol?.toUpperCase();
        
        if (!userInput || !mt5Symbol) {
          sendResponse({ ok: false, error: 'Input and symbol required' });
          return;
        }
        
        // Save to chrome.storage.local
        try {
          const mapObj = {};
          mapObj['mapping_' + userInput] = {
            userInput: userInput,
            mt5Symbol: mt5Symbol,
            price: msg.price || null,
            savedAt: new Date().toISOString()
          };
          
          await chrome.storage.local.set(mapObj);
          console.log('[BG] Mapping saved locally:', userInput, '→', mt5Symbol);
        } catch (storageErr) {
          console.log('[BG] Storage error:', storageErr.message);
        }
        
        // Also try to sync with server (for backup HTML)
        try {
          const resp = await fetch(API + '/studio/mapping-save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              userInput: userInput,
              mt5Symbol: mt5Symbol,
              price: msg.price || null
            }),
            signal: AbortSignal.timeout(2000)
          });
          
          if (resp.ok) {
            const data = await resp.json();
            sendResponse({ ok: true, message: 'Mapping saved and synced', serverResp: data.ok });
          } else {
            // Server sync failed but local save succeeded
            sendResponse({ ok: true, message: 'Mapping saved locally (server sync failed)' });
          }
        } catch (err) {
          // Server unreachable but local save succeeded
          sendResponse({ ok: true, message: 'Mapping saved locally (' + err.message + ')' });
        }
        return;
      }
      
      // ─── CAPTURE SCREENSHOT ──────────────────────────────────────
      if (msg.type === 'CAPTURE_SCREENSHOT') {
        try {
          const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
          if (!tab || !tab.windowId) {
            sendResponse({ ok: false, error: 'No active tab' });
            return;
          }
          
          const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' });
          sendResponse({ ok: true, screenshot: dataUrl });
        } catch (err) {
          sendResponse({ ok: false, error: err.message });
        }
        return;
      }
      
      // ─── GET AVAILABLE SYMBOLS ────────────────────────────────────
      if (msg.type === 'GET_SYMBOLS') {
        try {
          const resp = await fetch(API + '/mt5/symbols', {
            signal: AbortSignal.timeout(3000)
          });
          
          const data = await resp.json();
          sendResponse({ ok: data.ok, symbols: data.symbols, error: data.error });
        } catch (err) {
          sendResponse({ ok: false, error: err.message });
        }
        return;
      }
      
      // ─── PING ────────────────────────────────────────────────────
      if (msg.type === 'PING') {
        sendResponse({ ok: true, pong: true });
        return;
      }
      
      // ─── SET BADGE (for alerts) ──────────────────────────────────
      if (msg.type === 'SET_BADGE') {
        try {
          const count = msg.count || 0;
          if (count > 0) {
            chrome.action.setBadgeText({ text: String(count) });
            chrome.action.setBadgeBackgroundColor({ color: '#ef4444' });  // Red
          } else {
            chrome.action.setBadgeText({ text: '' });
          }
          sendResponse({ ok: true });
        } catch (err) {
          sendResponse({ ok: false, error: err.message });
        }
        return;
      }
      
      sendResponse({ ok: false, error: 'Unknown message type' });
      
    } catch (err) {
      sendResponse({ ok: false, error: err.message });
    }
  })();
  
  return true;  // Async response
});

// ── TAB MANAGEMENT ────────────────────────────────────────────────────────
chrome.action.onClicked.addListener(() => {
  openPersistentPopupWindow().catch((err) => {
    console.log('[BG] Persistent popup open error:', err.message);
  });
});

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  try {
    const tab = await chrome.tabs.get(tabId);
    rememberTradingViewTab(tab);
  } catch (_) {}
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.url && !isTradingViewUrl(changeInfo.url) && systemState.activeTradingViewTabId === tabId) {
    systemState.activeTradingViewTabId = null;
    return;
  }
  rememberTradingViewTab(tab);
});

chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabId === systemState.activeTradingViewTabId) {
    systemState.activeTradingViewTabId = null;
  }
});

chrome.windows.onRemoved.addListener((windowId) => {
  if (windowId === persistentPopupWindowId) {
    persistentPopupWindowId = null;
  }
});

chrome.windows.onFocusChanged.addListener((windowId) => {
  if (persistentPopupWindowId === null) return;
  if (windowId === chrome.windows.WINDOW_ID_NONE) return;
  if (windowId !== persistentPopupWindowId) {
    scheduleForegroundEnforce();
  }
});

// ── START POLLING ────────────────────────────────────────────────────────
function startPolling() {
  console.log('[BG] v3.0 polling started');
  pollBackendState();  // Initial
  setInterval(pollBackendState, POLL_INTERVAL);
  
  // NEW: Scrap real TradingView panel and send to server
  console.log('[BG] Real TradingView panel scraper started');
  scrapAndSendTradingView(); // Initial
  setInterval(scrapAndSendTradingView, SCRAPE_INTERVAL);
}

// ── INIT ──────────────────────────────────────────────────────────────────
console.log('[BG] v3.0 init — Complete MT5 Architecture');
hydratePersistentState().finally(startPolling);
