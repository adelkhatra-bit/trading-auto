/**
 * Agent: Data Source Manager
 * 
 * Responsabilité:
 * - Gérer et valider TOUTES les sources de données
 * - Règle stricte: TradingView bridge UNIQUEMENT
 * - Yahoo Finance et MT5 : SUPPRIMÉS
 * - Synchroniser les sources
 * - Garantir l'intégrité des prix
 */

// Sources disponibles
const SOURCES = {
  MT5: 'mt5',           // Priorité 1 - Données temps réel broker
  TRADINGVIEW: 'tradingview', // Priorité 2 - Fallback
  NONE: 'none'          // Aucune donnée live
};

// PRIX HARDCODÉS SUPPRIMÉS — plus aucun cache simulé.
// Ce fichier n'est pas importé dans server.js (qui utilise directement tvDataStore + marketStore).
// Conservé pour compatibilité avec supervisor.js / syncManager.js dans src/agents/.
const mt5PriceCache = {}; // vide — pas de données simulées
const tvPriceCache = {};  // vide — pas de données simulées

/**
 * Normalize symbole (EURUSD → EUR/USD)
 */
function normalizeSymbol(symbol) {
  if (!symbol) return null;
  
  // Déjà au bon format
  if (symbol.includes('/')) return symbol;
  
  // Métaux
  if (symbol.toUpperCase() === 'GOLD' || symbol.toUpperCase() === 'XAUUSD') return 'XAU/USD';
  if (symbol.toUpperCase() === 'SILVER' || symbol.toUpperCase() === 'XAGUSD') return 'XAG/USD';
  
  // Crypto
  if (symbol.toUpperCase() === 'BTCUSD') return 'BTC/USD';
  if (symbol.toUpperCase() === 'ETHUSD') return 'ETH/USD';
  
  // Forex standard (4 chars → ajouter /)
  if (symbol.length === 6) {
    return `${symbol.substring(0, 3)}/${symbol.substring(3)}`;
  }
  
  return symbol;
}

/**
 * Récupérer prix d'une source
 * @param {string} symbol - EURUSD ou EUR/USD
 * @param {string} source - mt5, tradingview, ou "auto" (priorité définie)
 * @returns {Object} { price, bid, ask, source, timestamp, valid }
 */
async function getPrice(symbol, source = 'auto') {
  const normalized = normalizeSymbol(symbol);
  
  if (!normalized) {
    return {
      valid: false,
      error: 'Symbol invalide',
      source: SOURCES.NONE
    };
  }

  // Mode auto: chercher MT5 d'abord, puis TradingView
  if (source === 'auto') {
    const mt5Result = await getPriceFromMT5(normalized);
    if (mt5Result.valid) return mt5Result;
    
    const tvResult = await getPriceFromTradingView(normalized);
    if (tvResult.valid) return tvResult;
    
    // Fallback: return invalid (pas de Yahoo!)
    return {
      valid: false,
      error: 'Aucune source disponible (MT5 offline, TradingView indisponible)',
      source: SOURCES.NONE,
      symbol: normalized
    };
  }

  // Mode spécifique
  if (source === SOURCES.MT5) {
    return await getPriceFromMT5(normalized);
  }
  if (source === SOURCES.TRADINGVIEW) {
    return await getPriceFromTradingView(normalized);
  }

  return {
    valid: false,
    error: 'Source invalide',
    source: SOURCES.NONE
  };
}

/**
 * MT5 - Source prioritaire
 * NOTE: Ce fichier n'est pas importé dans server.js.
 * Dans server.js, les prix MT5 viennent de marketStore.getLatestForSymbol() (startMT5Polling).
 */
async function getPriceFromMT5(symbol) {
  // mt5PriceCache est vide — plus de simulation hardcodée.
  return {
    valid: false,
    error: `MT5: aucune donnée disponible pour ${symbol} — connecter le polling MT5 réel`,
    source: SOURCES.MT5
  };
}

/**
 * TradingView - Fallback uniquement
 * NOTE: Dans server.js, les prix TradingView viennent de tvDataStore via getLatestTradingviewRuntime().
 */
async function getPriceFromTradingView(symbol) {
  // tvPriceCache est vide — plus de simulation hardcodée.
  return {
    valid: false,
    error: `TradingView: aucune donnée disponible pour ${symbol} — en attente flux live tvDataStore`,
    source: SOURCES.TRADINGVIEW
  };
}

/**
 * Valider qu'une source est acceptable
 */
function isValidSource(source) {
  return Object.values(SOURCES).includes(source);
}

/**
 * Retourner liste sources actives
 */
function getActiveSources() {
  return [
    { name: 'MT5', priority: 1, status: 'active' },
    { name: 'TradingView', priority: 2, status: 'fallback' }
    // Yahoo: DELETED
  ];
}

/**
 * Status global du manager
 */
function getStatus() {
  return {
    active: true,
    primarySource: SOURCES.MT5,
    fallbackSource: SOURCES.TRADINGVIEW,
    yahooEnabled: false, // ✅ Explicitement désactivé
    message: 'Data Source Manager operationnel (MT5 > TradingView only)'
  };
}

module.exports = {
  getPrice,
  getPriceFromMT5,
  getPriceFromTradingView,
  normalizeSymbol,
  isValidSource,
  getActiveSources,
  getStatus,
  SOURCES
};
