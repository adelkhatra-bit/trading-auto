// Agent: news-intelligence — news, macro events, symbol impact (real web sources)

const RSS_SOURCES = {
  FOREX: 'https://www.forexlive.com/feed/news',
  GOLD:  'https://www.kitco.com/rss/KitcoNewsAll.xml',
  MACRO: 'https://feeds.reuters.com/reuters/businessNews',
  FX2:   'https://www.fxstreet.com/rss/news'
};

const FOREX_FACTORY_FALLBACK = [
  { time:'08:30', currency:'USD', event:'CPI m/m',                    impact:'HIGH' },
  { time:'08:30', currency:'USD', event:'Core CPI m/m',               impact:'HIGH' },
  { time:'10:00', currency:'USD', event:'Confiance consommateurs',     impact:'MEDIUM' },
  { time:'14:00', currency:'USD', event:'Procès-verbal FOMC',          impact:'HIGH' },
  { time:'08:30', currency:'USD', event:'NFP',                         impact:'HIGH' },
  { time:'07:45', currency:'EUR', event:'Décision de taux BCE',        impact:'HIGH' },
  { time:'07:00', currency:'GBP', event:'PIB mensuel UK',              impact:'MEDIUM' },
  { time:'04:30', currency:'AUD', event:'Décision de taux RBA',        impact:'HIGH' },
  { time:'09:30', currency:'GBP', event:'CPI Royaume-Uni',             impact:'HIGH' },
  { time:'13:30', currency:'CAD', event:'Ventes au détail Canada',     impact:'MEDIUM' },
];

async function getUpcomingEvents() {
  const now = new Date();
  const currentHHMM = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
  return FOREX_FACTORY_FALLBACK.map(ev => {
    const [h, m] = ev.time.split(':').map(Number);
    const evDate = new Date(now);
    evDate.setHours(h, m, 0, 0);
    if (evDate < now) evDate.setDate(evDate.getDate() + 1); // next occurrence
    const minutesAway = Math.round((evDate - now) / 60000);
    return { ...ev, minutesAway, isUrgent: minutesAway < 30 && ev.impact === 'HIGH' };
  }).sort((a, b) => a.minutesAway - b.minutesAway);
}

function detectNewsBias(title = '') {
  const t = String(title || '').toLowerCase();
  const positive = ['surge', 'rally', 'beats', 'growth', 'bull', 'rebound', 'strong'];
  const negative = ['drops', 'fall', 'miss', 'cuts', 'bear', 'weak', 'risk', 'war', 'inflation'];
  const p = positive.some((k) => t.includes(k));
  const n = negative.some((k) => t.includes(k));
  if (p && !n) return 'Bullish';
  if (n && !p) return 'Bearish';
  return 'Neutral';
}

function extractRssItems(xml = '', limit = 8) {
  const items = [];
  const blocks = String(xml).match(/<item>[\s\S]*?<\/item>/gi) || [];
  for (let i = 0; i < Math.min(blocks.length, limit); i++) {
    const b = blocks[i];
    const title = (b.match(/<title><!\[CDATA\[([\s\S]*?)\]\]><\/title>/i) || b.match(/<title>([\s\S]*?)<\/title>/i) || [null, ''])[1]
      .replace(/<[^>]+>/g, '')
      .trim();
    const link = (b.match(/<link>([\s\S]*?)<\/link>/i) || [null, ''])[1].trim();
    if (!title) continue;
    items.push({ title, url: link || null });
  }
  return items;
}

async function fetchCoinGeckoNews() {
  try {
    const resp = await fetch('https://api.coingecko.com/api/v3/news', { signal: AbortSignal.timeout(4000) });
    if (!resp.ok) throw new Error('coingecko');
    const raw = await resp.json();
    return (Array.isArray(raw) ? raw : []).slice(0, 6).map((n) => ({
      title: n.title,
      source: n.news_site || 'CoinGecko',
      url: n.url || null,
      sentiment: detectNewsBias(n.title)
    }));
  } catch {
    return [];
  }
}

async function fetchReutersCommoditiesRss() {
  try {
    const resp = await fetch('https://www.reutersagency.com/feed/?best-topics=commodities&post_type=best', { signal: AbortSignal.timeout(5000) });
    if (!resp.ok) throw new Error('reuters');
    const xml = await resp.text();
    return extractRssItems(xml, 6).map((n) => ({
      ...n,
      source: 'Reuters',
      sentiment: detectNewsBias(n.title)
    }));
  } catch {
    return [];
  }
}

async function fetchXSignalRss(symbol = 'XAUUSD') {
  const query = encodeURIComponent(String(symbol || 'XAUUSD'));
  const url = 'https://nitter.net/search/rss?f=tweets&q=' + query;
  try {
    const resp = await fetch(url, { signal: AbortSignal.timeout(5000) });
    if (!resp.ok) throw new Error('nitter');
    const xml = await resp.text();
    return extractRssItems(xml, 4).map((n) => ({
      ...n,
      source: 'X/Nitter',
      sentiment: detectNewsBias(n.title)
    }));
  } catch {
    return [];
  }
}

function isNewsRelevantForSymbol(symbol = '', title = '') {
  const s = String(symbol || '').toUpperCase();
  const t = String(title || '').toUpperCase();
  const map = {
    XAUUSD: ['GOLD', 'XAU', 'FED', 'USD', 'TREASURY', 'RATE'],
    BTCUSD: ['BTC', 'BITCOIN', 'CRYPTO', 'ETF'],
    ETHUSD: ['ETH', 'ETHEREUM', 'CRYPTO'],
    NAS100: ['NASDAQ', 'TECH', 'US STOCK', 'FED', 'USD'],
    EURUSD: ['EUR', 'ECB', 'USD', 'FED'],
    GBPUSD: ['GBP', 'BOE', 'USD', 'FED']
  };
  const keys = map[s] || [s.slice(0, 3), s.slice(3, 6), 'USD'];
  return keys.some((k) => k && t.includes(k));
}

async function fetchLiveNews(symbol) {
  const [cg, reuters, xSignals] = await Promise.all([
    fetchCoinGeckoNews(),
    fetchReutersCommoditiesRss(),
    fetchXSignalRss(symbol)
  ]);
  const merged = [...cg, ...reuters, ...xSignals]
    .filter((n) => n && n.title)
    .filter((n) => isNewsRelevantForSymbol(symbol, n.title) || n.source === 'Reuters')
    .slice(0, 10);
  return merged;
}

async function fetchRssHeadlines(symbol) {
  const assetSources = {
    XAUUSD:  [RSS_SOURCES.GOLD,  RSS_SOURCES.MACRO, RSS_SOURCES.FOREX],
    XAGUSD:  [RSS_SOURCES.GOLD,  RSS_SOURCES.MACRO],
    BTCUSD:  [RSS_SOURCES.FOREX, RSS_SOURCES.MACRO],
    ETHUSD:  [RSS_SOURCES.FOREX, RSS_SOURCES.MACRO],
    NAS100:  [RSS_SOURCES.MACRO, RSS_SOURCES.FOREX],
    US30:    [RSS_SOURCES.MACRO, RSS_SOURCES.FOREX],
    EURUSD:  [RSS_SOURCES.FX2,   RSS_SOURCES.FOREX],
    GBPUSD:  [RSS_SOURCES.FX2,   RSS_SOURCES.FOREX],
    DEFAULT: [RSS_SOURCES.FOREX, RSS_SOURCES.FX2]
  };

  const sources = assetSources[symbol] || assetSources.DEFAULT;
  const headlines = [];

  await Promise.allSettled(sources.map(async (url) => {
    try {
      const res = await fetch(url, {
        signal: AbortSignal.timeout(4000),
        headers: { 'User-Agent': 'Mozilla/5.0 (compatible; TradingBot/1.0)' }
      });
      if (!res.ok) return;
      const xml = await res.text();
      // Parse RSS items (title + pubDate)
      const items = [...xml.matchAll(/<item[^>]*>([\s\S]*?)<\/item>/gi)];
      for (const item of items.slice(0, 8)) {
        const titleMatch = item[1].match(/<title[^>]*>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?<\/title>/i);
        const dateMatch  = item[1].match(/<pubDate[^>]*>([\s\S]*?)<\/pubDate>/i);
        const linkMatch  = item[1].match(/<link[^>]*>([\s\S]*?)<\/link>/i);
        if (!titleMatch) continue;
        const title = titleMatch[1].trim().replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>');
        const pubDate = dateMatch ? new Date(dateMatch[1].trim()) : new Date();
        const ageMs = Date.now() - pubDate.getTime();
        if (ageMs > 6 * 3600 * 1000) continue; // ignorer > 6h
        headlines.push({
          title,
          source: new URL(url).hostname,
          pubDate: pubDate.toISOString(),
          ageMinutes: Math.round(ageMs / 60000),
          link: linkMatch ? linkMatch[1].trim() : null
        });
      }
    } catch (_) {}
  }));

  // Déduplique par titre similaire + trie par récence
  const seen = new Set();
  return headlines
    .filter(h => { const k = h.title.slice(0,40); if (seen.has(k)) return false; seen.add(k); return true; })
    .sort((a,b) => a.ageMinutes - b.ageMinutes)
    .slice(0, 10)
    .map(h => ({
      ...h,
      bias: detectNewsBias(h.title),
      relevant: isNewsRelevantForSymbol(symbol, h.title),
      stars: h.ageMinutes < 30 ? 5 : h.ageMinutes < 120 ? 4 : h.ageMinutes < 240 ? 3 : 2
    }))
    .filter(h => h.relevant);
}

async function analyze(symbol) {
  const [upcomingEvents, liveNews, rssHeadlines] = await Promise.all([
    getUpcomingEvents(),
    fetchLiveNews(symbol),
    fetchRssHeadlines(symbol).catch(() => [])
  ]);

  // Filter events relevant to the symbol
  const symbolCurrency = symbol?.substring(0, 3) || '';
  const relevantEvents = upcomingEvents.filter(e =>
    e.currency === symbolCurrency || e.currency === 'USD' || e.impact === 'HIGH'
  ).slice(0, 5);

  const urgentEvent    = relevantEvents.find(e => e.isUrgent);
  const macroWarning   = urgentEvent
    ? `⚠️ ${urgentEvent.event} (${urgentEvent.currency}) dans ${urgentEvent.minutesAway} min — volatilité imminente`
    : null;
  const normalizedNews = liveNews.length > 0
    ? liveNews
    : relevantEvents.slice(0, 3).map((e) => ({
      title: `Événement à surveiller: ${e.event} (${e.currency})`,
      source: 'Economic Calendar',
      url: null,
      sentiment: 'Neutral'
    }));

  return {
    agent: 'news-intelligence',
    symbol,
    upcomingEvents: relevantEvents,
    news: normalizedNews,
    headlines: rssHeadlines,
    headlinesCount: rssHeadlines.length,
    macroWarning,
    symbolImpact: relevantEvents.some((e) => e.impact === 'HIGH')
      ? 'Risque macro élevé détecté pour ' + symbol
      : 'Pas de risque macro majeur immédiat pour ' + symbol,
    tradingSuggestion: urgentEvent ? 'ÉVITER entrée — annonce imminente haute impact' : 'Pas d\'annonce urgente',
  };
}

module.exports = { analyze, getUpcomingEvents };
