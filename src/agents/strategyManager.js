/**
 * Agent: Strategy Manager
 * 
 * Responsabilité:
 * - Gérer 4 modes de trading distincts
 * - Adapter TP / SL / logique selon mode
 * - Personnaliser chaque signal
 */

const STRATEGIES = {
  SNIPER: 'sniper',       // Précision, entrée zone exacte
  SCALPING: 'scalping',   // Rapide, petits TP
  INTRADAY: 'intraday',   // Positio journée
  SWING: 'swing'          // Position longues (SwingTrading)
};

const STRATEGY_CONFIG = {
  [STRATEGIES.SNIPER]: {
    name: 'Sniper',
    description: 'Entrée précise, zone liquidité, timing serré',
    slPercent: 0.002,      // 20 pips (ser ré)
    tpPercent: 0.006,      // 60 pips (moyen)
    timeTarget: '5-30min',
    riskReward: 1.5,
    maxSlippage: 0.5,      // Entrée flexible 0.5%
    notes: 'Attendre confirmation au niveau exact'
  },

  [STRATEGIES.SCALPING]: {
    name: 'Scalping',
    description: 'Très rapide, entrée zone, TP court',
    slPercent: 0.001,      // 10 pips (très serré)
    tpPercent: 0.003,      // 30 pips (court)
    timeTarget: '30sec-2min',
    riskReward: 1.0,
    maxSlippage: 0.2,      // Très strict
    notes: 'A faire que si setup TRES clair, market maker waiting'
  },

  [STRATEGIES.INTRADAY]: {
    name: 'Intraday',
    description: 'Position journalière, structure complète',
    slPercent: 0.005,      // 50 pips
    tpPercent: 0.015,      // 150 pips
    timeTarget: '1h-8h',
    riskReward: 2.0,
    maxSlippage: 1.0,      // Plus flexible
    notes: 'Déclôturer avant fin jour'
  },

  [STRATEGIES.SWING]: {
    name: 'Swing',
    description: 'Position multi-jours, très structurée',
    slPercent: 0.015,      // 150 pips
    tpPercent: 0.045,      // 450 pips
    timeTarget: '1d-7d',
    riskReward: 3.0,
    maxSlippage: 2.0,      // Très flexible
    notes: 'Gestion des tiers / attendre réaction'
  }
};

/**
 * Adapter un trade au mode stratégique
 */
function adaptTrade(trade, strategy = STRATEGIES.INTRADAY) {
  if (!STRATEGY_CONFIG[strategy]) {
    console.warn(`[StrategyManager] Stratégie inconnue: ${strategy}, fallback INTRADAY`);
    strategy = STRATEGIES.INTRADAY;
  }

  const config = STRATEGY_CONFIG[strategy];
  const entry = parseFloat(trade.entry);
  const direction = trade.direction || 'LONG';

  // Calculer SL / TP adaptés
  const slPct = config.slPercent;
  const tpPct = config.tpPercent;

  let sl, tp;
  if (direction === 'LONG') {
    sl = (entry * (1 - slPct)).toFixed(5);
    tp = (entry * (1 + tpPct)).toFixed(5);
  } else {
    sl = (entry * (1 + slPct)).toFixed(5);
    tp = (entry * (1 - tpPct)).toFixed(5);
  }

  return {
    ...trade,
    strategy,
    entry: entry.toFixed(5),
    sl: parseFloat(sl),
    tp: parseFloat(tp),
    riskReward: config.riskReward,
    timeTarget: config.timeTarget,
    maxSlippage: config.maxSlippage,
    note: config.notes,
    setupType: strategy,
    estimatedDuration: config.timeTarget
  };
}

/**
 * Vérifier si trade respecte règles stratégiques
 */
function validateForStrategy(trade, strategy = STRATEGIES.INTRADAY) {
  const config = STRATEGY_CONFIG[strategy];
  if (!config) {
    return { valid: false, reason: 'Stratégie inconnue' };
  }

  const entry = parseFloat(trade.entry);
  const sl = parseFloat(trade.sl);
  const tp = parseFloat(trade.tp);

  // Vérifier RR
  const slDist = Math.abs(entry - sl);
  const tpDist = Math.abs(entry - tp);
  const actualRR = tpDist / slDist;

  if (actualRR < config.riskReward * 0.8) {
    return {
      valid: false,
      reason: `RR insuffisant pour ${strategy} (${actualRR.toFixed(1)} < ${config.riskReward})`,
      actualRR
    };
  }

  // Vérifier SL distance
  const slPct = Math.abs(entry - sl) / entry * 100;
  if (slPct > config.slPercent * 200) {
    return {
      valid: false,
      reason: `SL trop loin pour ${strategy}`,
      slPercent: slPct.toFixed(2)
    };
  }

  return {
    valid: true,
    actualRR: actualRR.toFixed(2),
    slPercent: slPct.toFixed(2),
    strategy
  };
}

/**
 * Générer signal avec adaptations stratégiques
 */
function generateSignalForStrategy(symbol, price, direction, strategy = STRATEGIES.INTRADAY) {
  const config = STRATEGY_CONFIG[strategy];

  // Position de base
  const entry = parseFloat(price).toFixed(5);
  let sl, tp;

  if (direction === 'LONG') {
    sl = (parseFloat(entry) * (1 - config.slPercent)).toFixed(5);
    tp = (parseFloat(entry) * (1 + config.tpPercent)).toFixed(5);
  } else {
    sl = (parseFloat(entry) * (1 + config.slPercent)).toFixed(5);
    tp = (parseFloat(entry) * (1 - config.tpPercent)).toFixed(5);
  }

  return {
    symbol,
    direction,
    entry: parseFloat(entry),
    sl: parseFloat(sl),
    tp: parseFloat(tp),
    strategy,
    setupType: strategy,
    timeTarget: config.timeTarget,
    estimatedDuration: config.timeTarget,
    riskReward: config.riskReward,
    maxSlippage: config.maxSlippage,
    confidence: 'medium',
    note: config.notes,
    createdAt: Date.now()
  };
}

/**
 * Liste tous les modes disponibles
 */
function getStrategies() {
  return Object.keys(STRATEGY_CONFIG).map(key => ({
    id: key,
    ...STRATEGY_CONFIG[key]
  }));
}

/**
 * Obtenir config d'une stratégie
 */
function getStrategyConfig(strategy) {
  return STRATEGY_CONFIG[strategy] || null;
}

/**
 * Recommander stratégie basée sur contexte
 */
function recommendStrategy(market_volatility, time_available, account_size) {
  // Logique recommandation
  if (market_volatility > 2.0) {
    return STRATEGIES.INTRADAY; // Volatilité haute → play plus court
  }
  
  if (time_available < 30) {
    return STRATEGIES.SCALPING; // Peu de temps → scalp rapide
  }
  
  if (time_available > 480) {
    return STRATEGIES.SWING; // Toute la journée → swing
  }
  
  return STRATEGIES.INTRADAY; // Default
}

module.exports = {
  adaptTrade,
  validateForStrategy,
  generateSignalForStrategy,
  getStrategies,
  getStrategyConfig,
  recommendStrategy,
  STRATEGIES
};
