// Agent: timeframe-consensus — hierarchical multi-TF decision

// Timeframe weight: higher = more dominant
const TF_WEIGHTS = {
  MN1:25, W1:22, D1:20, H12:16, H8:14, H6:12, H4:10, H3:8, H2:7,
  H1:6, M30:4, M20:3, M15:3, M12:2, M10:2, M6:2, M5:1, M4:1, M3:1, M2:1, M1:1
};

const DOMINANT_TFS    = ['D1','W1','MN1','H12','H8','H6','H4'];
const CONFIRMATION_TFS = ['H3','H2','H1','M30','M20','M15'];
const EXECUTION_TFS   = ['M12','M10','M6','M5','M4','M3','M2','M1'];

function classifyTF(tf) {
  if (DOMINANT_TFS.includes(tf))    return 'dominant';
  if (CONFIRMATION_TFS.includes(tf)) return 'confirmation';
  return 'execution';
}

function scoreTFData(tfData) {
  // tfData: { rsi, ema20, ema50, price, ohlc }
  let bull = 0, bear = 0;
  const { rsi, ema20, ema50, ema200, price } = tfData;
  if (rsi) {
    if (rsi > 55)       bull += 1;
    else if (rsi < 45)  bear += 1;
  }
  if (ema20 && ema50) {
    if (ema20 > ema50)  bull += 1;
    else                bear += 1;
  }
  if (ema200 && price) {
    if (price > ema200) bull += 1;
    else                bear += 1;
  }
  return { bull, bear, bias: bull > bear ? 'BULLISH' : bear > bull ? 'BEARISH' : 'NEUTRAL' };
}

function buildConsensus(multiTFPayload) {
  // multiTFPayload: { M1: {rsi,ema20,...}, M5: {...}, H1: {...}, ... }
  const results   = {};
  let weightedBull = 0, weightedBear = 0, totalWeight = 0;
  const dominantBiases     = [];
  const confirmationBiases = [];
  const executionBiases    = [];

  for (const [tf, data] of Object.entries(multiTFPayload)) {
    if (!data) continue;
    const weight  = TF_WEIGHTS[tf] || 1;
    const { bull, bear, bias } = scoreTFData(data);
    results[tf] = { bias, bull, bear, class: classifyTF(tf), weight };
    weightedBull  += bull * weight;
    weightedBear  += bear * weight;
    totalWeight   += weight;

    const cls = classifyTF(tf);
    if (cls === 'dominant')     dominantBiases.push(bias);
    if (cls === 'confirmation') confirmationBiases.push(bias);
    if (cls === 'execution')    executionBiases.push(bias);
  }

  const dominantBull = dominantBiases.filter(b => b === 'BULLISH').length;
  const dominantBear = dominantBiases.filter(b => b === 'BEARISH').length;
  const dominantBias = dominantBull > dominantBear ? 'BULLISH' : dominantBear > dominantBull ? 'BEARISH' : 'NEUTRAL';

  const execBull     = executionBiases.filter(b => b === 'BULLISH').length;
  const execBear     = executionBiases.filter(b => b === 'BEARISH').length;
  const execBias     = execBull > execBear ? 'BULLISH' : execBear > execBull ? 'BEARISH' : 'NEUTRAL';

  // Conflict detection
  const conflict     = dominantBias !== 'NEUTRAL' && execBias !== 'NEUTRAL' && dominantBias !== execBias;
  const netScore     = totalWeight > 0 ? ((weightedBull - weightedBear) / totalWeight) : 0;
  const globalBias   = netScore > 0.3 ? 'BULLISH' : netScore < -0.3 ? 'BEARISH' : 'NEUTRAL';

  // Decision logic: dominant TFs command
  let decision = 'ATTENDRE';
  let strength = 'FAIBLE';
  if (dominantBias === 'BULLISH' && !conflict)                    { decision = 'LONG';    strength = 'FORT'; }
  else if (dominantBias === 'BEARISH' && !conflict)               { decision = 'SHORT';   strength = 'FORT'; }
  else if (dominantBias === 'BULLISH' && execBias === 'BULLISH')  { decision = 'LONG';    strength = 'MODERE'; }
  else if (dominantBias === 'BEARISH' && execBias === 'BEARISH')  { decision = 'SHORT';   strength = 'MODERE'; }
  else if (conflict)                                               { decision = 'ATTENDRE'; strength = 'CONFLIT'; }

  const summary = [
    `📊 Contexte dominant (${DOMINANT_TFS.filter(t => multiTFPayload[t]).join('/')}): ${dominantBias}`,
    confirmationBiases.length ? `🔍 Confirmation: ${confirmationBiases.join(', ')}` : null,
    executionBiases.length ? `⚡ Exécution (${EXECUTION_TFS.filter(t => multiTFPayload[t]).join('/')}): ${execBias}` : null,
    conflict ? `⚠️ CONFLIT — petites UT (${execBias}) contre grandes UT (${dominantBias}) → rebond probable, pas de vrai retournement` : null,
    `🎯 Décision consensus: ${decision} (${strength})`,
  ].filter(Boolean);

  return {
    agent: 'timeframe-consensus',
    globalBias,
    dominantBias,
    execBias,
    decision,
    strength,
    conflict,
    netScore: netScore.toFixed(3),
    byTimeframe: results,
    summary,
  };
}

module.exports = { buildConsensus };
