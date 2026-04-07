/**
 * Agent: Trade Validator
 * 
 * Responsabilité:
 * - Classer chaque trade: LIVE / CONDITIONNEL / OBSOLÈTE
 * - Valider cohérence entry/SL/TP
 * - Vérifier distance entrée vs prix actuel
 * - Bloquer trades impossibles
 */

const TRADE_STATUS = {
  LIVE: 'live',           // Exécutable maintenant
  CONDITIONNEL: 'conditionnel', // En attente
  OBSOLETE: 'obsolete',   // À ignorer
  INVALID: 'invalid'      // Incohérent
};

/**
 * Valider et classer un trade
 */
function validateTrade(trade, currentPrice) {
  const result = {
    trade,
    status: TRADE_STATUS.INVALID,
    issues: [],
    warnings: [],
    valid: false
  };

  // Vérifications de base
  if (!trade || typeof trade !== 'object') {
    result.issues.push('Trade object invalide');
    return result;
  }

  const entry = parseFloat(trade.entry);
  const sl = parseFloat(trade.sl);
  const tp = parseFloat(trade.tp);
  const current = parseFloat(currentPrice);
  const direction = trade.direction || 'LONG';

  // Vérifier que les valeurs existent
  if (isNaN(entry) || isNaN(sl) || isNaN(tp)) {
    result.issues.push('Entry/SL/TP invalides');
    return result;
  }

  // Vérifier SL/TP cohérents avec direction
  if (direction === 'LONG') {
    if (sl >= entry) {
      result.issues.push(`SL (${sl}) >= Entry (${entry}) pour LONG`);
    }
    if (tp <= entry) {
      result.issues.push(`TP (${tp}) <= Entry (${entry}) pour LONG`);
    }
  } else {
    if (sl <= entry) {
      result.issues.push(`SL (${sl}) <= Entry (${entry}) pour SHORT`);
    }
    if (tp >= entry) {
      result.issues.push(`TP (${tp}) >= Entry (${entry}) pour SHORT`);
    }
  }

  // Si y'a des issues critiques
  if (result.issues.length > 0) {
    return result;
  }

  // Classer le trade
  const distancePercent = Math.abs((entry - current) / current) * 100;
  const maxDistanceLive = 0.5; // 0.5%
  const maxDistanceConditionnel = 2.0; // 2%

  if (distancePercent <= maxDistanceLive) {
    result.status = TRADE_STATUS.LIVE;
    result.valid = true;
    result.note = 'Exécutable maintenant';
  } else if (distancePercent <= maxDistanceConditionnel) {
    result.status = TRADE_STATUS.CONDITIONNEL;
    result.valid = true;
    result.note = `En attente d'un retour vers ${entry.toFixed(5)}`;
  } else if (distancePercent > maxDistanceConditionnel && distancePercent < 10) {
    result.status = TRADE_STATUS.CONDITIONNEL;
    result.valid = true;
    result.warnings.push(`Distance: ${distancePercent.toFixed(2)}% — attendre setup plus confirmé`);
  } else {
    result.status = TRADE_STATUS.OBSOLETE;
    result.note = `Entrée trop loin (${distancePercent.toFixed(2)}%) — setup pass\u00e9`;
  }

  // Calculer propriétés supplémentaires
  const slDistance = Math.abs(entry - sl);
  const tpDistance = Math.abs(entry - tp);
  const riskReward = tpDistance / slDistance;
  const probability = calculateProbability(trade);

  result.distance = {
    toEntry: distancePercent.toFixed(2) + '%',
    slDistance: slDistance.toFixed(5),
    tpDistance: tpDistance.toFixed(5),
    riskReward: riskReward.toFixed(2)
  };

  result.probability = probability;
  result.confidence = calculateConfidence(result);

  return result;
}

/**
 * Calculer probabilité d'un trade
 */
function calculateProbability(trade) {
  let score = 50; // Baseline

  // Vérifier cohérence avec direction
  if (trade.direction && (trade.direction === 'LONG' || trade.direction === 'SHORT')) {
    score += 10;
  }

  // Vérifier si score du trade est bon
  if (trade.score && trade.score >= 70) {
    score += 15;
  } else if (trade.score && trade.score >= 60) {
    score += 8;
  }

  // Vérifier source
  if (trade.source === 'live' || trade.source === 'decision-engine') {
    score += 5;
  }

  return Math.min(100, score);
}

/**
 * Calculer confiance
 */
function calculateConfidence(validationResult) {
  let confidence = {
    level: 'low',
    percent: 0
  };

  if (validationResult.issues.length > 0) {
    confidence.percent = 0;
    confidence.level = 'invalid';
  } else if (validationResult.warnings.length > 0) {
    confidence.percent = 40;
    confidence.level = 'low';
  } else if (validationResult.status === TRADE_STATUS.LIVE) {
    confidence.percent = 85;
    confidence.level = 'high';
  } else if (validationResult.status === TRADE_STATUS.CONDITIONNEL) {
    confidence.percent = 60;
    confidence.level = 'medium';
  } else if (validationResult.status === TRADE_STATUS.OBSOLETE) {
    confidence.percent = 20;
    confidence.level = 'low';
  }

  return confidence;
}

/**
 * Filtrer trades exécutables
 */
function filterLiveTrades(trades, currentPrice) {
  return trades
    .map(t => validateTrade(t, currentPrice))
    .filter(v => v.status === TRADE_STATUS.LIVE || v.status === TRADE_STATUS.CONDITIONNEL)
    .sort((a, b) => b.probability - a.probability);
}

/**
 * Vérifier si entrée est "cassée" (trop loin)
 */
function isEntryBroken(trade, currentPrice) {
  const entry = parseFloat(trade.entry);
  const current = parseFloat(currentPrice);
  const distancePercent = Math.abs((entry - current) / current) * 100;

  return distancePercent > 5.0; // Plus de 5% = cassé
}

module.exports = {
  validateTrade,
  filterLiveTrades,
  isEntryBroken,
  calculateProbability,
  calculateConfidence,
  TRADE_STATUS
};
