// Agent: fear-index — VIX / market stress indicator

let cachedFear = null;
let cacheTime  = 0;
const CACHE_TTL = 5 * 60 * 1000; // 5 min

async function getFearIndex() {
  if (cachedFear && Date.now() - cacheTime < CACHE_TTL) return cachedFear;

  try {
    // VIX from Yahoo Finance (no API key needed)
    const resp = await fetch(
      'https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=5d',
      { signal: AbortSignal.timeout(5000) }
    );
    if (!resp.ok) throw new Error('Yahoo VIX error');
    const d = await resp.json();
    const vix = d?.chart?.result?.[0]?.meta?.regularMarketPrice;
    if (!vix) throw new Error('VIX data empty');

    let level, description, tradingNote;
    if      (vix < 13)  { level = 'TRÈS_BAS';   description = 'Marché extrêmement complaisant — risque de retournement'; tradingNote = 'Prudence — compacité extrême'; }
    else if (vix < 20)  { level = 'BAS';         description = 'Marché calme — sessions exploitables'; tradingNote = 'Conditions favorables'; }
    else if (vix < 30)  { level = 'MODERE';      description = 'Volatilité normale'; tradingNote = 'Sessions normales'; }
    else if (vix < 40)  { level = 'ELEVE';       description = 'Marché stressé — mouvements amplifiés'; tradingNote = 'Réduire la taille'; }
    else                { level = 'EXTREME';      description = 'Marché en panique — très dangereux'; tradingNote = 'Éviter les positions directionnelles'; }

    cachedFear = { agent:'fear-index', vix: parseFloat(vix.toFixed(2)), level, description, tradingNote, source: 'yahoo-vix', updatedAt: new Date().toISOString() };
    cacheTime  = Date.now();
    return cachedFear;
  } catch {
    return { agent:'fear-index', vix: null, level:'INCONNU', description:'Données de peur indisponibles', tradingNote:'Prudence', source:'offline' };
  }
}

module.exports = { getFearIndex };
