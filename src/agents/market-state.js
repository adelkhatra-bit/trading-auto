// Agent: market-state — is the market clean, choppy, dangerous?

function assess({ atr, atrAvg, spread, price, rsi, volume, recentRange }) {
  const notes = [];
  let dangerScore = 0;

  // ATR relative to average → measures current volatility
  if (atr && atrAvg) {
    const ratio = atr / atrAvg;
    if (ratio > 2.5)      { dangerScore += 3; notes.push(`Volatilité TRÈS ÉLEVÉE (ATR x${ratio.toFixed(1)} vs moyenne) — marché dangereux`); }
    else if (ratio > 1.5) { dangerScore += 1; notes.push(`Volatilité élevée (ATR x${ratio.toFixed(1)}) — prudence`); }
    else if (ratio < 0.5) { dangerScore -= 1; notes.push(`Volatilité faible (ATR x${ratio.toFixed(1)}) — marché calme`); }
  }

  // Spread relative to price
  if (spread && price) {
    const spreadPct = (spread / price) * 100;
    if (spreadPct > 0.1) { dangerScore += 2; notes.push(`Spread large (${spreadPct.toFixed(3)}%) — coût élevé, éviter le scalping`); }
  }

  // RSI extremes → trending or about to reverse
  if (rsi) {
    if (rsi > 75 || rsi < 25) { dangerScore += 1; notes.push(`RSI extrême (${rsi.toFixed(1)}) — risque de retournement`); }
  }

  let state, description;
  if (dangerScore >= 4)      { state = 'DANGEROUS';  description = 'Marché très volatil et dangereux — éviter ou taille minimale'; }
  else if (dangerScore >= 2) { state = 'CAUTION';    description = 'Marché stressé — prudence, réduire exposition'; }
  else if (dangerScore >= 0) { state = 'CLEAN';      description = 'Marché propre et exploitable'; }
  else                       { state = 'QUIET';      description = 'Marché calme — opportunités sur breakouts'; }

  return { agent: 'market-state', state, dangerScore, description, notes };
}

module.exports = { assess };
