// news-engine.js v1.0 — News économiques, biais directionnel, score de confiance
var NewsEngine = (function () {
  'use strict';

  var _cache = null;
  var _cacheTs = 0;
  var TTL = 5 * 60 * 1000;

  var IMPACT_COL = { High: '#ef4444', Medium: '#f59e0b', Low: '#64748b' };

  // Patterns → biais (avant news = prévision, après = interprétation)
  var PATTERNS = [
    {
      keys: ['CPI', 'INFLATION', 'PPI', 'PCE'],
      currency: 'USD',
      before: { high: { dir: 'USD ↑ · Or ↓ · Indices ↓', why: 'Inflation forte = politique monétaire restrictive, dollar haussier' },
                low:  { dir: 'USD ↓ · Or ↑ · Indices ↑', why: 'Inflation faible = assouplissement probable, dollar baissier' } },
      after:  { surprise_high: 'Surprise haussière: USD probable hausse immédiate', surprise_low: 'Surprise baissière: USD sous pression, or en hausse potentielle' }
    },
    {
      keys: ['NFP', 'NON-FARM', 'PAYROLL', 'EMPLOYMENT', 'JOBS', 'UNEMPLOYMENT'],
      currency: 'USD',
      before: { high: { dir: 'USD ↑ · Indices ↑', why: 'Emploi fort = croissance, optimisme, Fed moins dovish' },
                low:  { dir: 'USD ↓ · Or ↑', why: 'Emploi faible = Fed dovish probable, dollar affaibli' } },
      after:  { surprise_high: 'Emploi meilleur que prévu: USD haussier, risk-on probable', surprise_low: 'Emploi décevant: risk-off, valeurs refuge haussières' }
    },
    {
      keys: ['FED', 'FOMC', 'INTEREST RATE', 'RATE DECISION', 'FEDERAL RESERVE'],
      currency: 'USD',
      before: { high: { dir: 'USD ↑ · Or ↓', why: 'Hausse de taux = dollar fort, or sous pression' },
                low:  { dir: 'USD ↓ · Or ↑', why: 'Baisse/pause taux = dollar affaibli, or et indices en hausse' } },
      after:  { surprise_high: 'Hawkish: USD en hausse, or et indices sous pression', surprise_low: 'Dovish: USD sous pression, or et indices haussiers' }
    },
    {
      keys: ['GDP', 'PIB', 'GROWTH', 'GROSS DOMESTIC'],
      currency: 'USD',
      before: { high: { dir: 'Risk-on · USD mixte', why: 'Croissance forte = optimisme, mais impact USD variable' },
                low:  { dir: 'Risk-off · Or ↑', why: 'Croissance faible = récession risk, valeurs refuge' } },
      after:  { surprise_high: 'GDP meilleur: confiance économique, risk-on', surprise_low: 'GDP décevant: risk-off, or potentiellement haussier' }
    },
    {
      keys: ['PMI', 'ISM', 'MANUFACTURING', 'SERVICES'],
      currency: 'USD',
      before: { high: { dir: 'Indices ↑ · USD ↑', why: 'PMI élevé = activité économique forte' },
                low:  { dir: 'Risk-off', why: 'PMI < 50 = contraction, sentiment négatif' } },
      after:  { surprise_high: 'PMI au-dessus des attentes: sentiment positif', surprise_low: 'PMI décevant: crainte de ralentissement' }
    },
    {
      keys: ['ECB', 'EUROPEAN CENTRAL', 'BCE'],
      currency: 'EUR',
      before: { high: { dir: 'EUR ↑', why: 'BCE hawkish = euro haussier' },
                low:  { dir: 'EUR ↓', why: 'BCE dovish = euro sous pression' } },
      after:  { surprise_high: 'BCE hawkish surprise: EUR en hausse forte', surprise_low: 'BCE dovish: EUR sous pression' }
    }
  ];

  function inferBias(event) {
    if (!event) return null;
    var title = (event.title || event.name || '').toUpperCase();
    for (var i = 0; i < PATTERNS.length; i++) {
      var p = PATTERNS[i];
      if (p.keys.some(function (k) { return title.includes(k); })) {
        var impact = (event.impact || 'Low');
        var conf = impact === 'High' ? 72 : impact === 'Medium' ? 58 : 40;
        return {
          currency: p.currency,
          impact: impact,
          conf: conf,
          before: p.before,
          after: p.after
        };
      }
    }
    return null;
  }

  function parseTs(e) {
    // ForexFactory: date "04-01-2026", time "8:30am"
    try {
      if (!e.date) return null;
      // Try ISO first
      if (e.date.includes('T')) return new Date(e.date).getTime();
      // MM-DD-YYYY + time
      var parts = e.date.split('-');
      var timeStr = (e.time || '12:00am').replace(/[^0-9:apm]/gi, '');
      var dateStr = parts[0] + '/' + parts[1] + '/' + parts[2] + ' ' + timeStr;
      var d = new Date(dateStr);
      return isNaN(d) ? null : d.getTime();
    } catch (_) { return null; }
  }

  function timeLabel(minsUntil) {
    if (minsUntil === null) return '';
    if (minsUntil < 0) return 'Il y a ' + Math.abs(minsUntil) + 'min';
    if (minsUntil < 1) return 'Maintenant';
    if (minsUntil < 60) return 'Dans ' + minsUntil + 'min';
    return 'Dans ' + Math.floor(minsUntil / 60) + 'h' + (minsUntil % 60 ? (minsUntil % 60) + 'm' : '');
  }

  async function fetchNews() {
    var now = Date.now();
    if (_cache && (now - _cacheTs) < TTL) return _cache;
    try {
      var r = await fetch('http://127.0.0.1:4000/economic-events', { signal: AbortSignal.timeout(5000) });
      if (r.ok) {
        var d = await r.json();
        if (d.ok && d.events && d.events.length) {
          _cache = d.events;
          _cacheTs = now;
          return _cache;
        }
      }
    } catch (_) {}
    return _cache || [];
  }

  async function getUpcoming(symbol) {
    var all = await fetchNews();
    var now = Date.now();
    return all
      .filter(function (e) {
        var ts = parseTs(e);
        if (!ts) return false;
        var diff = (ts - now) / 60000;
        return diff > -60 && diff < 24 * 60;
      })
      .map(function (e) {
        var ts = parseTs(e);
        var mins = ts ? Math.round((ts - now) / 60000) : null;
        var bias = inferBias(e);
        return {
          title:    e.title || e.name || '?',
          country:  e.country || '?',
          impact:   e.impact || 'Low',
          time:     e.time || '',
          mins:     mins,
          timeLabel: timeLabel(mins),
          bias:     bias,
          isRecent: mins !== null && mins < 0 && mins > -60,
          isSoon:   mins !== null && mins >= 0 && mins < 60
        };
      })
      .sort(function (a, b) {
        var da = a.mins === null ? 9999 : a.mins;
        var db = b.mins === null ? 9999 : b.mins;
        return da - db;
      })
      .slice(0, 10);
  }

  return {
    getUpcoming: getUpcoming,
    inferBias:   inferBias,
    IMPACT_COL:  IMPACT_COL
  };
})();
