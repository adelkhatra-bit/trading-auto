/**
 * Agent: Setup Classifier
 * 
 * Responsabilité:
 * - Identifier le TYPE de setup
 * - Donner structure au trade
 * - Expliquer logique d'entrée
 * - Prévoir durée estimée
 */

const SETUP_TYPES = {
  LIQUIDITY_SWEEP: 'liquidity_sweep',  // Bris de liquidité + retour
  BREAK_OF_STRUCTURE: 'bos',            // Break Of Structure
  FAIR_VALUE_GAP: 'fvg',               // Fair Value Gap fill
  SUPPORT_RESISTANCE: 'sr',            // Support/Resistance touch
  TREND_CONTINUATION: 'trend_cont',    // Continuation dans tendance
  REVERSAL: 'reversal',                // Reversal pattern
  CONSOLIDATION: 'consolidation',      // Breakout consolidation
  UNKNOWN: 'unknown'
};

const SETUP_DETAILS = {
  [SETUP_TYPES.LIQUIDITY_SWEEP]: {
    name: 'Liquidity Sweep',
    description: 'Sweep de stops + retour vers liquidité',
    riskProfile: 'medium',
    timeTarget: '15min-4h',
    confidence: 'high',
    markers: ['Break levels', 'Retour rapide', 'Volume', 'Confluence']
  },

  [SETUP_TYPES.BREAK_OF_STRUCTURE]: {
    name: 'Break Of Structure (BoS)',
    description: 'Casse de structure haussière/baissière',
    riskProfile: 'high',
    timeTarget: '1h-1d',
    confidence: 'medium-high',
    markers: ['Higher High/Low break', 'Impulsion', 'Confirmation MTF']
  },

  [SETUP_TYPES.FAIR_VALUE_GAP]: {
    name: 'Fair Value Gap (FVG)',
    description: 'Écart de valide équitable à combler',
    riskProfile: 'low',
    timeTarget: '30min-4h',
    confidence: 'high',
    markers: ['Gap OHLC clair', 'Retour logique', 'Support/Résistance']
  },

  [SETUP_TYPES.SUPPORT_RESISTANCE]: {
    name: 'Support/Résistance',
    description: 'Touch de niveau majeur',
    riskProfile: 'medium',
    timeTarget: '1h-1d',
    confidence: 'medium',
    markers: ['Niveau testé', 'Réaction', 'Confluence']
  },

  [SETUP_TYPES.TREND_CONTINUATION]: {
    name: 'Trend Continuation',
    description: 'Continuation dans tendance établie',
    riskProfile: 'low',
   timeTarget: '4h-1d',
    confidence: 'high',
    markers: ['Trend clair', 'Pullback mineur', 'EMA alignment']
  },

  [SETUP_TYPES.REVERSAL]: {
    name: 'Reversal Pattern',
    description: 'Pattern de retournement (pin bar, engulfing...)',
    riskProfile: 'high',
    timeTarget: '1h-4h',
    confidence: 'medium',
    markers: ['Pattern clair', 'Volume', 'Confluence', 'Rejection']
  },

  [SETUP_TYPES.CONSOLIDATION]: {
    name: 'Consolidation Breakout',
    description: 'Breakout de consolidation',
    riskProfile: 'medium',
    timeTarget: '30min-4h',
    confidence: 'high',
    markers: ['Consolidation LH/LL', 'Breakout', 'Volume']
  },

  [SETUP_TYPES.UNKNOWN]: {
    name: 'Unknown Setup',
    description: 'Type non déterminé — à analyser manuellement',
    riskProfile: 'unknown',
    timeTarget: 'TBD',
    confidence: 'low'
  }
};

/**
 * Classifier un trade
 */
function classifySetup(trade, context = {}) {
  const result = {
    trade,
    setupType: SETUP_TYPES.UNKNOWN,
    details: SETUP_DETAILS[SETUP_TYPES.UNKNOWN],
    confidence: 'low',
    reasoning: [],
    markers: []
  };

  if (!trade) return result;

  // Analyser signal technique
  const technicalSignals = analyzeTechnical(trade);
  const structureSignals = analyzeStructure(trade, context);
  const liquiditySignals = analyzeLiquidity(trade);
  
  // Scoring
  const scores = {};
  for (const setupType of Object.keys(SETUP_TYPES)) {
    scores[setupType] = 0;
  }

  // Score basé sur technical
  if (technicalSignals.rsi_oversold) {
    scores[SETUP_TYPES.REVERSAL] += 2;
    scores[SETUP_TYPES.LIQUIDITY_SWEEP] += 1;
  }
  if (technicalSignals.ema_bullish) {
    scores[SETUP_TYPES.TREND_CONTINUATION] += 3;
    scores[SETUP_TYPES.LIQUIDITY_SWEEP] += 2;
  }

  // Score basé sur structure
  if (structureSignals.bos_detected) {
    scores[SETUP_TYPES.BREAK_OF_STRUCTURE] += 3;
  }
  if (structureSignals.fvg_detected) {
    scores[SETUP_TYPES.FAIR_VALUE_GAP] += 3;
  }
  if (structureSignals.sr_touch) {
    scores[SETUP_TYPES.SUPPORT_RESISTANCE] += 2;
  }

  // Score basé sur liquidité
  if (liquiditySignals.sweep_likely) {
    scores[SETUP_TYPES.LIQUIDITY_SWEEP] += 3;
  }

  // Trouver meilleure correspondance
  let bestSetup = SETUP_TYPES.UNKNOWN;
  let bestScore = 0;

  for (const [setupType, score] of Object.entries(scores)) {
    if (score > bestScore && setupType !== SETUP_TYPES.UNKNOWN) {
      bestSetup = setupType;
      bestScore = score;
    }
  }

  if (bestSetup !== SETUP_TYPES.UNKNOWN) {
    result.setupType = bestSetup;
    result.details = SETUP_DETAILS[bestSetup];
    result.confidence = bestScore >= 7 ? 'high' : bestScore >= 4 ? 'medium' : 'low';
  }

  result.reasoning = generateReasoning(result.setupType, technicalSignals, structureSignals, liquiditySignals);
  result.score = bestScore;

  return result;
}

/**
 * Analyser signaux techniques
 */
function analyzeTechnical(trade) {
  const rsi = trade.rsi || 50;
  const ema20 = trade.ema20;
  const ema50 = trade.ema50;

  return {
    rsi: rsi,
    rsi_overbought: rsi > 70,
    rsi_oversold: rsi < 30,
    rsi_bullish: rsi > 50,
    ema_bullish: ema20 && ema50 && ema20 > ema50
  };
}

/**
 * Analyser structure de prix
 */
function analyzeStructure(trade, context = {}) {
  return {
    bos_detected: false, // À déterminer depuis chart
    choch_detected: false,
    fvg_detected: !!context.fvg,
    sr_touch: !!context.support_resistance,
    trend: context.trend || 'unknown'
  };
}

/**
 * Analyser liquidité
 */
function analyzeLiquidity(trade) {
  const entry = parseFloat(trade.entry);
  const sl = parseFloat(trade.sl);

  // Sweep likely si SL serré
  const slPercent = Math.abs(entry - sl) / entry * 100;

  return {
    sl_tight: slPercent < 0.5,
    sweep_likely: slPercent < 0.7,
    liquidityScore: slPercent < 0.5 ? 'high' : 'medium'
  };
}

/**
 * Générer explication
 */
function generateReasoning(setupType, technical, structure, liquidity) {
  const reasons = [];

  if (setupType === SETUP_TYPES.LIQUIDITY_SWEEP) {
    reasons.push('Sweep de liquidité détecté');
    if (liquidity.sweep_likely) reasons.push('SL aligné avec liquidité');
  }

  if (setupType === SETUP_TYPES.TREND_CONTINUATION) {
    if (technical.ema_bullish) reasons.push('EMA alignment bullish');
    reasons.push('Continuation dans trend existant');
  }

  if (setupType === SETUP_TYPES.FAIR_VALUE_GAP) {
    reasons.push('FVG identifié — retour logique vers équilibre');
  }

  return reasons.length > 0 ? reasons : ['Setup analysé'];
}

/**
 * Obtenir tous les types
 */
function getSetupTypes() {
  return Object.keys(SETUP_TYPES).map(key => ({
    id: key,
    ...SETUP_DETAILS[key]
  }));
}

module.exports = {
  classifySetup,
  analyzeTechnical,
  analyzeStructure,
  analyzeLiquidity,
  generateReasoning,
  getSetupTypes,
  SETUP_TYPES
};
