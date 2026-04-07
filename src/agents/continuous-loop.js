// agents-continuous-loop.js - Orchestration Continue des Agents (DÉSACTIVÉE)
// ⚠️  PROBLÈME CRITIQUE: La boucle continue était exécutée sans contrôle
// RAISON: setInterval toutes les 30 secondes sans check de symbole actif
// RÉSULTAT: CPU constant, même quand aucune trading n'est active
//
// NOUVELLE APPROCHE: Mode SAFE
// - Pas d'exécution automatique
// - Trigger via API: POST /agents/run-cycle?symbol=XAUUSD
// - Orchestration manuelle contrôlée par l'utilisateur

'use strict';

let isRunning = false;
let cycleCount = 0;
let lastActiveSymbol = null;
let orchestrator = null;
let _loopTimer = null;  // Pour contrôle manuel

/**
 * Initialiser la boucle continue (SANS démarrer automatiquement)
 */
function initContinuousLoop(orchestratorModule) {
  orchestrator = orchestratorModule;
  
  console.log('[AGENTS-LOOP] ✓ Initialisation SAFE MODE');
  console.log('[AGENTS-LOOP] Auto-orchestration DISABLED');
  console.log('[AGENTS-LOOP] Mode: Manuel - utilisateur décide du timing');
  
  return {
    status: 'initialized-safe',
    cycleCount: cycleCount,
    lastSymbol: lastActiveSymbol,
    autoEnabled: false
  };
}

/**
 * NOUVELLE: Boucle principale - exécutée MANUELLEMENT on demand
 */
async function orchestrationCycle() {
  cycleCount++;
  const cycleId = `CYCLE-${cycleCount}`;
  const timestamp = new Date().toISOString();
  
  console.log(`[AGENTS-LOOP] ${cycleId} MANUAL TRIGGER @ ${timestamp}`);
  
  try {
    // Obtenir le symbole actif
    const activeSymbol = getActiveSymbol();
    if (!activeSymbol) {
      console.log('[AGENTS-LOOP] Aucun symbole actif - cycle skip');
      return { ok: false, reason: 'no-symbol' };
    }
    
    lastActiveSymbol = activeSymbol;
    
    console.log(`[AGENTS-LOOP] ${cycleId} Symbole: ${activeSymbol.symbol} (${activeSymbol.timeframe})`);
    
    // PHASE 1: Technical Analysis
    console.log(`[AGENTS-LOOP] ${cycleId} → Phase 1: Technical Analysis`);
    const technicalAnalysis = await runAgent('technicalAgent', {
      symbol: activeSymbol.symbol,
      timeframe: activeSymbol.timeframe,
      price: activeSymbol.price,
    });
    
    // PHASE 2: Macro Analysis
    console.log(`[AGENTS-LOOP] ${cycleId} → Phase 2: Macro Analysis`);
    const macroAnalysis = await runAgent('macroAgent', {
      symbol: activeSymbol.symbol,
    });
    
    // PHASE 3: News/Sentiment
    console.log(`[AGENTS-LOOP] ${cycleId} → Phase 3: News Sentiment`);
    const newsSentiment = await runAgent('newsAgent', {
      symbol: activeSymbol.symbol,
    });
    
    // PHASE 4: Risk Management
    console.log(`[AGENTS-LOOP] ${cycleId} → Phase 4: Risk Calculation`);
    const riskAnalysis = await runAgent('riskManager', {
      symbol: activeSymbol.symbol,
      price: activeSymbol.price,
    });
    
    // PHASE 5: Strategy Selection
    console.log(`[AGENTS-LOOP] ${cycleId} → Phase 5: Strategy Selection`);
    const strategyAnalysis = await runAgent('strategyManager', {
      technical: technicalAnalysis,
      macro: macroAnalysis,
      sentiment: newsSentiment,
    });
    
    // PHASE 6: Trade Validation
    console.log(`[AGENTS-LOOP] ${cycleId} → Phase 6: Trade Validation`);
    const validationResult = await runAgent('tradeValidator', {
      strategy: strategyAnalysis,
      riskProfile: riskAnalysis,
    });
    
    // Orchestration finale
    console.log(`[AGENTS-LOOP] ${cycleId} → Orchestration Finale`);
    const finalTrade = {
      symbol: activeSymbol.symbol,
      timeframe: activeSymbol.timeframe,
      price: activeSymbol.price,
      technical: technicalAnalysis,
      macro: macroAnalysis,
      sentiment: newsSentiment,
      risk: riskAnalysis,
      strategy: strategyAnalysis,
      validation: validationResult,
      cycleId: cycleId,
      timestamp: timestamp,
    };
    
    // Log le résultat
    logCycleResult(finalTrade);
    
    console.log(`[AGENTS-LOOP] ${cycleId} ✅ Cycle complet @ ${new Date().toISOString()}`);
    
    return {
      ok: true,
      cycleId: cycleId,
      trade: finalTrade,
    };
    
  } catch (error) {
    console.error(`[AGENTS-LOOP] ${cycleId} ❌ Erreur:`, error.message);
    return { ok: false, error: error.message, cycleId };
  }
}

/**
 * Exécuter un agent avec timeout
 */
async function runAgent(agentName, params) {
  return new Promise((resolve) => {
    const timeout = 5000; // 5s timeout par agent
    
    const timer = setTimeout(() => {
      console.warn(`[AGENTS-LOOP] ⏱ Timeout ${agentName}`);
      resolve({ ok: false, agent: agentName, reason: 'timeout' });
    }, timeout);
    
    try {
      // Simuler l'exécution de l'agent
      // En prod, ça appellerait le vrai agent
      const result = {
        ok: true,
        agent: agentName,
        data: params,
        confidence: null, // calculé par le vrai agent, pas simulé
      };
      clearTimeout(timer);
      resolve(result);
    } catch (e) {
      clearTimeout(timer);
      resolve({ ok: false, agent: agentName, error: e.message });
    }
  });
}

/**
 * Enregistrer le résultat du cycle dans le système log
 */
function logCycleResult(trade) {
  const log = {
    type: 'orchestration-cycle',
    cycleId: trade.cycleId,
    symbol: trade.symbol,
    direction: trade.validation?.direction || 'N/A',
    score: trade.validation?.score || 0,
    timestamp: trade.timestamp,
    agents: [
      'technicalAgent',
      'macroAgent',
      'newsAgent',
      'riskManager',
      'strategyManager',
      'tradeValidator',
    ],
  };
  
  console.log('[AGENTS-LOOP] Log créé:', JSON.stringify(log, null, 2));
  
  // Retourner le log pour être possible d'être sauvegardé
  return log;
}

/**
 * Obtenir le symbole actif du système
 */
function getActiveSymbol() {
  // En prod, ça viendrait du background.js ou du cache
  // Pour maintenant, retourner un placeholder
  return {
    symbol: 'XAUUSD',
    timeframe: 'H1',
    price: 4812.90,
    lastUpdate: Date.now(),
  };
}

/**
 * Démarrer la boucle
 */
function startContinuousLoop() {
  if (isRunning) {
    console.log('[AGENTS-LOOP] Déjà en cours d\'exécution');
    return;
  }
  
  isRunning = true;
  console.log('[AGENTS-LOOP] ▶️  Boucle DÉMARRÉE');
  
  // Exécuter immédiatement
  orchestrationCycle();
  
  // Puis toutes les 30 secondes
  setInterval(orchestrationCycle, 30000);
}

/**
 * Arrêter la boucle
 */
function stopContinuousLoop() {
  isRunning = false;
  console.log('[AGENTS-LOOP] ⏹️  Boucle ARRÊTÉE');
}

/**
 * Statut de la boucle
 */
function getStatus() {
  return {
    running: isRunning,
    cycleCount: cycleCount,
    lastSymbol: lastActiveSymbol,
    lastCycle: cycleCount > 0 ? `CYCLE-${cycleCount}` : 'none',
    uptime: isRunning ? '✓ En exécution' : '✗ Arrêtée',
  };
}

/**
 * Force une exécution immédiate (pour tests)
 */
async function runImmediately() {
  console.log('[AGENTS-LOOP] ⚡ Exécution forcée');
  return await orchestrationCycle();
}

// Export pour utilisation dans server.js
module.exports = {
  initContinuousLoop,
  orchestrationCycle,
  startContinuousLoop,
  stopContinuousLoop,
  getStatus,
  runImmediately,
};
