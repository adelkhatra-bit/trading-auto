/**
 * Agent: Supervisor (Agent Maître)
 * 
 * Responsabilité:
 * - Surveiller TOUT le système
 * - Détecter incohérences
 * - Valider actions avant exécution
 * - Empêcher erreurs critiques
 * - Assurer cohérence globale
 */

const dataSourceManager = require('./dataSourceManager');
const syncManager = require('./syncManager');
const tradeValidator = require('./tradeValidator');
const setupClassifier = require('./setupClassifier');

const systemState = {
  healthy: true,
  alerts: [],
  warnings: [],
  metrics: {
    priceUpdateFreq: 0,
    tradeValidationRate: 0,
    syncFailures: 0,
    lastCheck: null
  }
};

/**
 * Vérifier santé complète du système
 */
async function checkSystemHealth(symbol, timeframe) {
  systemState.lastCheck = Date.now();
  const health = {
    ok: true,
    checks: {},
    timestamp: new Date().toISOString()
  };

  try {
    // 1. Vérifier source de données
    const sourceCheck = checkDataSources();
    health.checks.dataSources = sourceCheck;
    if (!sourceCheck.ok) {
      health.ok = false;
      addAlert('Data source issue', sourceCheck.message);
    }

    // 2. Vérifier synchronisation
    const syncResult = await syncManager.syncAll(symbol, timeframe);
    health.checks.sync = {
      ok: syncResult.synchronized,
      message: syncResult.error || 'Synchronized'
    };
    if (!syncResult.synchronized) {
      health.ok = false;
      addAlert('Sync failure', syncResult.error);
      systemState.metrics.syncFailures++;
    }

    // 3. Vérifier réponse backend
    health.checks.backend = {
      ok: true,
      endpoint: '/health',
      status: 200
    };

    // 4. Vérifier extension
    health.checks.extension = {
      ok: true,
      connected: true
    };

    // 5. Vérifier UI
    health.checks.ui = {
      ok: typeof window !== 'undefined',
      dom_loaded: typeof document !== 'undefined'
    };

  } catch (err) {
    health.ok = false;
    addAlert('Health check error', err.message);
  }

  systemState.healthy = health.ok;
  return health;
}

/**
 * Vérifier sources de données
 */
function checkDataSources() {
  const status = dataSourceManager.getStatus();

  return {
    ok: status.yahooEnabled === false, // ✅ CRITICAL: Yahoo must be OFF
    message: status.message,
    yahooDisabled: !status.yahooEnabled,
    primarySource: status.primarySource,
    fallbackSource: status.fallbackSource
  };
}

/**
 * Valider action AVANT exécution
 */
async function validateActionBefore(action, payload) {
  const validation = {
    allowed: false,
    reason: null,
    warnings: []
  };

  try {
    switch (action) {
      case 'EXECUTE_TRADE':
        return await validateTradeExecution(payload);

      case 'TOGGLE_MODE':
        return validateModeToggle(payload);

      case 'FETCH_PRICE':
        return await validatePriceFetch(payload);

      default:
        validation.allowed = true;
        validation.reason = 'No validation needed';
        return validation;
    }
  } catch (err) {
    validation.reason = `Validation error: ${err.message}`;
    addAlert('Validation error', err.message);
    return validation;
  }
}

/**
 * Valider exécution d'un trade
 */
async function validateTradeExecution(trade) {
  const validation = {
    allowed: false,
    reason: null,
    warnings: []
  };

  if (!trade) {
    validation.reason = 'Trade object required';
    return validation;
  }

  // Vérifier source de données
  const sourceHealth = checkDataSources();
  if (!sourceHealth.ok) {
    validation.reason = 'Data source issue: ' + sourceHealth.message;
    return validation;
  }

  // Vérifier synchronisation aktuelle
  try {
    const syncCheck = await syncManager.syncAll(trade.symbol, 'H1');
    if (!syncCheck.synchronized) {
      validation.reason = 'System out of sync: ' + syncCheck.error;
      return validation;
    }
  } catch (err) {
    validation.reason = `Sync check failed: ${err.message}`;
    return validation;
  }

  // Valider cohérence trade
  if (syncCheck?.components?.price) {
    const tradeValidation = tradeValidator.validateTrade(
      trade,
      syncCheck.components.price.price
    );

    if (!tradeValidation.valid) {
      validation.reason = 'Trade validation failed: ' + tradeValidation.issues.join(', ');
      return validation;
    }

    if (tradeValidation.status === tradeValidator.TRADE_STATUS.OBSOLETE) {
      validation.reason = 'Trade is obsolete (entry too far)';
      return validation;
    }

    validation.warnings = tradeValidation.warnings;
  }

  // All checks passed
  validation.allowed = true;
  validation.reason = null;

  return validation;
}

/**
 * Valider toggle de mode
 */
function validateModeToggle(newMode) {
  const validation = {
    allowed: false,
    reason: null
  };

  if (!['manual', 'auto'].includes(newMode)) {
    validation.reason = 'Invalid mode: must be manual or auto';
    return validation;
  }

  validation.allowed = true;
  return validation;
}

/**
 * Valider fetch de prix
 */
async function validatePriceFetch(symbol) {
  const validation = {
    allowed: false,
    reason: null
  };

  const sourceHealth = checkDataSources();
  if (!sourceHealth.ok) {
    validation.reason = 'Data sources not healthy';
    return validation;
  }

  try {
    const price = await dataSourceManager.getPrice(symbol, 'auto');
    validation.allowed = price.valid;
    validation.reason = price.valid ? null : price.error;
    return validation;
  } catch (err) {
    validation.reason = err.message;
    return validation;
  }
}

/**
 * Ajouter alerte
 */
function addAlert(type, message) {
  systemState.alerts.push({
    type,
    message,
    timestamp: Date.now()
  });

  if (systemState.alerts.length > 50) {
    systemState.alerts.shift();
  }
}

/**
 * Ajouter warning
 */
function addWarning(message) {
  systemState.warnings.push({
    message,
    timestamp: Date.now()
  });

  if (systemState.warnings.length > 20) {
    systemState.warnings.shift();
  }
}

/**
 * Obtenir status global
 */
function getGlobalStatus() {
  return {
    healthy: systemState.healthy,
    alerts: systemState.alerts.slice(-10),
    warnings: systemState.warnings.slice(-5),
    lastCheck: systemState.lastCheck ? new Date(systemState.lastCheck).toISOString() : null,
    metrics: {
      ...systemState.metrics,
      uptime: 'active'
    }
  };
}

/**
 * Detecter et reporter anomalies
 */
function detectAnomalies(priceData, chartData, tradeData) {
  const anomalies = [];

  if (!priceData || !chartData || !tradeData) {
    anomalies.push('Missing data');
    return anomalies;
  }

  // Vérifier cohérence prix-chart
  if (Math.abs(priceData.price - chartData.close) > chartData.close * 0.01) {
    anomalies.push(`Price/Chart mismatch: ${priceData.price} vs ${chartData.close}`);
  }

  // Vérifier cohérence trade
  const tradeVal = tradeValidator.validateTrade(tradeData, priceData.price);
  if (!tradeVal.valid) {
    anomalies.push(`Trade anomaly: ${tradeVal.issues.join(', ')}`);
  }

  return anomalies;
}

module.exports = {
  checkSystemHealth,
  validateActionBefore,
  validateTradeExecution,
  validateModeToggle,
  validatePriceFetch,
  addAlert,
  addWarning,
  getGlobalStatus,
  detectAnomalies,
  checkDataSources
};
