// Agent: fear-index — VIX / market stress indicator
// Yahoo Finance supprimé — retourne une valeur neutre (bridge TV ne fournit pas VIX)

let cachedFear = null;
let cacheTime  = 0;
const CACHE_TTL = 5 * 60 * 1000;

async function getFearIndex() {
  if (cachedFear && Date.now() - cacheTime < CACHE_TTL) return cachedFear;
  // Yahoo Finance supprimé — VIX indisponible sans source externe
  cachedFear = { agent:'fear-index', vix: null, level:'INCONNU', description:'VIX indisponible — Yahoo Finance supprimé', tradingNote:'Prudence', source:'bridge-tv-only', updatedAt: new Date().toISOString() };
  cacheTime = Date.now();
  return cachedFear;
}

module.exports = { getFearIndex };
