// Agent: orchestrator — master coordinator, fuses all agent outputs

const tradingCore          = require('./trading-core');
const tfConsensus          = require('./timeframe-consensus');
const tradeLogic           = require('./trade-logic');
const marketState          = require('./market-state');
const newsIntelligence     = require('./news-intelligence');
const fearIndex            = require('./fear-index');
const { normalizeSymbol }  = require('../../lib/symbol-normalizer');

function withTimeout(promise, ms, agentName) {
  const timeout = new Promise((_, reject) =>
    setTimeout(() => reject(new Error(`Agent ${agentName} timeout après ${ms}ms`)), ms)
  );
  return Promise.race([promise, timeout]).catch(err => {
    console.warn(`[ORCHESTRATOR] ${err.message} — agent ignoré`);
    return null; // agent ignoré, pas de blocage global
  });
}

async function run(mt5Payload) {
  const startMs = Date.now();
  const raw     = mt5Payload;

  // 1. Normalize symbol
  const profile = normalizeSymbol(raw.symbol || raw.broker_symbol || 'EURUSD');
  const symbol  = profile.canonical;

  // 2. Extract current TF data
  const currentTF = raw.timeframe || 'H1';
  const price      = parseFloat(raw.price || raw.bid || 0);
  const bid        = parseFloat(raw.bid  || price);
  const ask        = parseFloat(raw.ask  || price);

  // Build unified MT5 data object for current TF
  const currentTFData = {
    symbol, price, bid, ask, timeframe: currentTF,
    rsi:   raw.rsi,
    ema20: raw.ema20, ema50: raw.ema50, ema200: raw.ema200,
    atr:   raw.atr,
    ohlc:  raw.ohlc || raw.bars || [],
    volume: raw.volume,
  };

  // 3. Build multi-TF map from MT5 payload (MT5 sends all TFs)
  const multiTF = raw.timeframes || {};
  if (!multiTF[currentTF]) multiTF[currentTF] = currentTFData;

  // 4. Run agents in parallel (non-blocking)
  const results = await Promise.all([
    withTimeout(tradingCore.analyze(currentTFData, profile), 3000, 'tradingCore'),
    withTimeout(Promise.resolve(tfConsensus.buildConsensus(multiTF)), 3000, 'tfConsensus'),
    withTimeout(fearIndex.getFearIndex(), 3000, 'fearIndex'),
    withTimeout(newsIntelligence.analyze(symbol), 3000, 'newsIntelligence'),
  ]);

  // Si un agent a timeout, son résultat est null — gérer proprement
  const coreResult = results[0] || { direction: 'ATTENDRE', score: 0, levels: null, rsi: null, ema: null, structure: null, fvgs: null, liquidity: null };
  const consensus  = results[1] || { decision: 'ATTENDRE', strength: 'FAIBLE', conflict: false };
  const fearData   = results[2] || { agent: 'fear-index', vix: null, level: 'INCONNU' };
  const newsData   = results[3] || { agent: 'news-intelligence', upcomingEvents: [], news: [], macroWarning: null };

  // 5. Market state
  const mState = marketState.assess({
    atr:    currentTFData.atr,
    atrAvg: raw.atrAvg,
    spread: ask - bid,
    price,
    rsi:    currentTFData.rsi,
  });

  // 6. Trade logic explanation
  const logic = tradeLogic.explain({
    symbol, profile,
    direction:   coreResult.direction,
    score:       coreResult.score,
    levels:      coreResult.levels,
    rsi:         coreResult.rsi,
    ema:         coreResult.ema,
    structure:   coreResult.structure,
    fvgs:        coreResult.fvgs,
    liquidity:   coreResult.liquidity,
    consensus,
    marketState: mState,
    news:        newsData,
  });

  // 7. Final decision (dominant TFs override core if conflict)
  const finalDirection = consensus.conflict ? 'ATTENDRE' : (consensus.decision !== 'ATTENDRE' ? consensus.decision : coreResult.direction);
  const finalScore     = Math.round((coreResult.score || 60) * 0.6 + (consensus.strength === 'FORT' ? 40 : consensus.strength === 'MODERE' ? 25 : 10));

  const result = {
    ok: true,
    orchestrator: true,
    symbol,
    brokerSymbol: profile.broker_symbol,
    assetType:    profile.type,
    timeframe:    currentTF,
    price:        price || null,
    bid, ask,
    spread:       (ask - bid) || null,
    direction:    finalDirection,
    score:        finalScore,
    strength:     consensus.strength,
    trade:        finalDirection !== 'ATTENDRE' && coreResult.levels ? {
      symbol,
      direction: finalDirection,
      ...coreResult.levels,
      score:     finalScore,
      risk:      finalScore > 80 ? 'Low' : finalScore > 65 ? 'Medium' : 'High',
      technical: [coreResult.rsi?.note, coreResult.structure?.bos].filter(Boolean).join(' | '),
      macro:     newsData?.macroWarning || 'Pas d\'annonce urgente',
      sentiment: fearData?.level || 'INCONNU',
      explanation: logic.text?.substring(0, 200),
      source:    'mt5-live',
      accuracy:  'live',
    } : null,
    agents: {
      tradingCore:   coreResult,
      consensus,
      marketState:   mState,
      news:          newsData,
      fear:          fearData,
      tradeLogic:    logic,
    },
    computedInMs: Date.now() - startMs,
  };

  return result;
}

module.exports = { run };
