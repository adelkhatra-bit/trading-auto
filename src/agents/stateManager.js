/**
 * Agent: State Manager
 * 
 * Responsabilité:
 * - Sauvegarder état du système (localStorage)
 * - Persister paramètres utilisateur
 * - Restaurer contexte au reload
 * - Synchroniser entre onglets
 */

const DEFAULT_STATE = {
  symbol: 'EUR/USD',
  timeframe: 'H1',
  strategy: 'intraday',
  mode: 'manual', // manual ou auto
  brokerMode: 'live', // paper ou live
  accountBalance: 100000,
  riskPercent: 1,
  lastPrices: {},
  selectedSetup: null,
  theme: 'dark',
  notifications: true
};

const STORAGE_KEY = 'trading-auto-state';

/**
 * Initialiser state manager
 */
function init() {
  // Vérifie localStorage disponible
  if (typeof localStorage === 'undefined') {
    console.warn('[StateManager] localStorage indisponible');
    return { ...DEFAULT_STATE };
  }

  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const state = JSON.parse(saved);
      return { ...DEFAULT_STATE, ...state };
    }
  } catch (err) {
    console.error('[StateManager] Erreur parsing état:', err);
  }

  return { ...DEFAULT_STATE };
}

/**
 * Sauvegarder state
 */
function save(state) {
  if (typeof localStorage === 'undefined') {
    console.warn('[StateManager] localStorage non disponible');
    return false;
  }

  try {
    const toSave = {
      symbol: state.symbol,
      timeframe: state.timeframe,
      strategy: state.strategy,
      mode: state.mode,
      brokerMode: state.brokerMode,
      accountBalance: state.accountBalance,
      riskPercent: state.riskPercent,
      theme: state.theme,
      notifications: state.notifications,
      savedAt: Date.now()
    };

    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
    return true;
  } catch (err) {
    console.error('[StateManager] Erreur sauvegarde:', err);
    return false;
  }
}

/**
 * Mettre à jour un champ
 */
function update(key, value) {
  if (!DEFAULT_STATE.hasOwnProperty(key)) {
    console.warn(`[StateManager] Clé inconnue: ${key}`);
    return false;
  }

  const state = init();
  state[key] = value;
  state.updatedAt = Date.now();

  return save(state);
}

/**
 * Mettre à jour plusieurs champs
 */
function updateMultiple(updates) {
  const state = init();
  
  for (const [key, value] of Object.entries(updates)) {
    if (DEFAULT_STATE.hasOwnProperty(key)) {
      state[key] = value;
    }
  }

  state.updatedAt = Date.now();
  return save(state);
}

/**
 * Récupérer une valeur
 */
function get(key) {
  const state = init();
  return state[key] !== undefined ? state[key] : DEFAULT_STATE[key];
}

/**
 * Récupérer tout l'état
 */
function getAll() {
  return init();
}

/**
 * Réinitialiser à defaut
 */
function reset() {
  try {
    localStorage.removeItem(STORAGE_KEY);
    return true;
  } catch (err) {
    console.error('[StateManager] Erreur reset:', err);
    return false;
  }
}

/**
 * Exporter état (pour backup)
 */
function export_state() {
  const state = init();
  return {
    state,
    exported: new Date().toISOString(),
    version: '1.0'
  };
}

/**
 * Importer état (depuis backup)
 */
function import_state(backup) {
  if (!backup || !backup.state) {
    console.error('[StateManager] Backup invalide');
    return false;
  }

  try {
    const state = { ...DEFAULT_STATE, ...backup.state };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    return true;
  } catch (err) {
    console.error('[StateManager] Erreur import:', err);
    return false;
  }
}

/**
 * Écouter changements (pour sync entre onglets)
 */function onStateChange(callback) {
  if (typeof window !== 'undefined') {
    window.addEventListener('storage', (event) => {
      if (event.key === STORAGE_KEY && event.newValue) {
        try {
          const newState = JSON.parse(event.newValue);
          callback(newState);
        } catch (err) {
          console.error('[StateManager] Erreur parsing event:', err);
        }
      }
    });
  }
}

/**
 * Historique des changements
 */
const HISTORY_KEY = 'trading-auto-history';
const MAX_HISTORY = 50;

function recordHistory(action, data) {
  if (typeof localStorage === 'undefined') return;

  try {
    let history = [];
    const saved = localStorage.getItem(HISTORY_KEY);
    if (saved) {
      history = JSON.parse(saved);
    }

    history.unshift({
      action,
      data,
      timestamp: Date.now()
    });

    if (history.length > MAX_HISTORY) {
      history = history.slice(0, MAX_HISTORY);
    }

    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  } catch (err) {
    console.error('[StateManager] Erreur history:', err);
  }
}

function getHistory() {
  if (typeof localStorage === 'undefined') return [];

  try {
    const saved = localStorage.getItem(HISTORY_KEY);
    return saved ? JSON.parse(saved) : [];
  } catch (err) {
    console.error('[StateManager] Erreur read history:', err);
    return [];
  }
}

module.exports = {
  init,
  save,
  update,
  updateMultiple,
  get,
  getAll,
  reset,
  export_state,
  import_state,
  onStateChange,
  recordHistory,
  getHistory,
  DEFAULT_STATE,
  STORAGE_KEY
};
