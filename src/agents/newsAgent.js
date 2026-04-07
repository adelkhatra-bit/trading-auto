/**
 * NEWS AGENT — Intelligence de marché temps réel
 * 
 * Surveillance des événements financiers et géopolitiques
 * Détection d'impact sur les décisions trading
 * Intégration avec la logique de position
 * 
 * Sources :
 * - Calendrier macro (NFP, CPI, BOE, Fed, ECB)
 * - News financières agrégées
 * - Sentiment X/Twitter (simul)
 * - Alertes géopolitiques
 * - Volatilité implicite
 */

const newsAgent = {
  // ─── STATE ────────────────────────────────────────────────────────────────
  newsCache: [],
  importantDates: new Map(),
  riskLevel: 'NORMAL', // NORMAL, ELEVATED, CRITICAL
  
  // ─── MACRO CALENDAR (Events that move markets) ────────────────────────────
  CRITICAL_INDICATORS: {
    'NFP': { symbol: 'USD', impact: 'CRITICAL', volatility: 150 },
    'CPI': { symbol: 'USD', impact: 'CRITICAL', volatility: 120 },
    'BOE-RATE': { symbol: 'GBP', impact: 'CRITICAL', volatility: 100 },
    'ECB-RATE': { symbol: 'EUR', impact: 'CRITICAL', volatility: 110 },
    'FED-RATE': { symbol: 'USD', impact: 'CRITICAL', volatility: 140 },
    'PPI': { symbol: 'USD', impact: 'HIGH', volatility: 90 },
    'RETAIL-SALES': { symbol: 'USD', impact: 'HIGH', volatility: 80 },
    'JOBS': { symbol: 'USD', impact: 'HIGH', volatility: 100 },
    'UNEMPLOYMENT': { symbol: 'USD', impact: 'HIGH', volatility: 95 },
    'GDP': { symbol: 'USD,EUR,GBP', impact: 'HIGH', volatility: 85 },
    'MANUFACTURING': { symbol: 'USD,EUR', impact: 'MEDIUM', volatility: 70 }
  },

  // ─── SENTIMENT KEYWORDS (Words that indicate market movements) ────────────
  BULLISH_KEYWORDS: [
    'rally', 'surge', 'gains', 'sharp rise', 'upbeat', 'optimism', 
    'strong data', 'recovery', 'bullish', 'beat expectations', 'positive',
    'growth', 'expansion', 'buy signal', 'upgrade'
  ],

  BEARISH_KEYWORDS: [
    'selloff', 'decline', 'weakness', 'plunge', 'recession', 'bearish',
    'concern', 'miss', 'disappointing', 'inflation', 'hawkish', 'tightening',
    'downside', 'support breach', 'sell signal', 'downgrade'
  ],

  VOLATILITY_KEYWORDS: [
    'geopolitical', 'war', 'sanctions', 'crisis', 'emergency', 'shock',
    'surprise', 'unexpected', 'surge in volatility', 'vix spike'
  ],

  // ─── UPCOMING MACRO EVENTS (Simulated next 7 days) ─────────────────────
  getUpcomingEvents() {
    const today = new Date();
    const events = [
      {
        date: new Date(today.getTime() + 1*24*3600*1000), // Tomorrow
        event: 'Consumer Confidence (US)',
        indicator: 'CONSUMER_CONF',
        symbol: 'USD',
        time: '14:00 GMT',
        impact: 'MEDIUM',
        expected: '102.5',
        previous: '102.6',
        forecast: 'Mixed signals expected'
      },
      {
        date: new Date(today.getTime() + 2*24*3600*1000),
        event: 'Jobless Claims (US)',
        indicator: 'JOBLESS',
        symbol: 'USD',
        time: '13:30 GMT',
        impact: 'HIGH',
        expected: '205K',
        previous: '214K',
        forecast: 'May support USD if lower than expected'
      },
      {
        date: new Date(today.getTime() + 4*24*3600*1000),
        event: 'NFP (Non-Farm Payroll)',
        indicator: 'NFP',
        symbol: 'USD',
        time: '13:30 GMT',
        impact: 'CRITICAL',
        expected: '+180K',
        previous: '+275K',
        forecast: 'Major volatility expected. All pairs sensitive. Avoid 30min before/after.'
      },
      {
        date: new Date(today.getTime() + 5*24*3600*1000),
        event: 'ECB Interest Rate Decision',
        indicator: 'ECB-RATE',
        symbol: 'EUR',
        time: '13:45 GMT',
        impact: 'CRITICAL',
        expected: '4.00%',
        previous: '4.00%',
        forecast: 'Hawkish hold expected. EUR could benefit if guidance is stronger.'
      }
    ];
    return events;
  },

  // ─── NEWS FEED (Simulated / Real-time) ─────────────────────────────────
  getLatestNews(symbol = null, limit = 10) {
    const baseNews = [
      {
        source: 'FT Finance',
        timestamp: new Date(Date.now() - 30*60*1000), // 30 min ago
        title: 'Gold reaches 6-month high amid growth concerns',
        sentiment: 'BULLISH',
        targetSymbol: 'XAU',
        impactScore: 85,
        keywords: ['rally', 'growth concerns'],
        category: 'COMMODITIES',
        summary: 'XAU/USD breaks above 2400 as investors flee risk assets'
      },
      {
        source: 'Bloomberg',
        timestamp: new Date(Date.now() - 60*60*1000),
        title: 'Fed officials signal data-dependent approach for rates',
        sentiment: 'NEUTRAL',
        targetSymbol: 'USD',
        impactScore: 70,
        keywords: ['data-dependent', 'rates'],
        category: 'MACRO',
        summary: 'Mixed signals on future rate path support USD stability'
      },
      {
        source: 'Reuters',
        timestamp: new Date(Date.now() - 90*60*1000),
        title: 'EUR/USD tests 1.10 support amid ECB hawkish expectations',
        sentiment: 'BEARISH',
        targetSymbol: 'EUR',
        impactScore: 75,
        keywords: ['weak', 'support breach'],
        category: 'FOREX',
        summary: 'Technical weakness in EUR as markets price in rate cuts pressure'
      },
      {
        source: 'CoinDesk',
        timestamp: new Date(Date.now() - 120*60*1000),
        title: 'Bitcoin surges as macro concerns ease',
        sentiment: 'BULLISH',
        targetSymbol: 'BTC',
        impactScore: 80,
        keywords: ['surge', 'bullish'],
        category: 'CRYPTO',
        summary: 'BTC/USDT breaks key resistance at 68K'
      }
    ];

    // Filter by symbol if requested
    let news = symbol 
      ? baseNews.filter(n => n.targetSymbol === symbol || n.targetSymbol.includes(symbol))
      : baseNews;

    return news.slice(0, limit);
  },

  // ─── ANALYZE NEWS IMPACT ON TRADE ──────────────────────────────────────
  analyzeNewsImpact(symbol, trade, timeframe) {
    const news = this.getLatestNews(symbol, 5);
    
    let impactSummary = {
      symbol,
      timeframe,
      newsCount: news.length,
      sentiment: 'NEUTRAL',
      impactLevel: 'NORMAL',
      recommendedAction: 'PROCEED',
      warnings: [],
      bullishFactors: [],
      bearishFactors: [],
      volatilityRisk: 'LOW',
      macroEventSoon: false,
      confidence: 0
    };

    if (news.length === 0) {
      impactSummary.recommendations = 'No recent news for this symbol';
      return impactSummary;
    }

    // Aggregate sentiment
    let bullishCount = 0, bearishCount = 0, volatilityCount = 0;
    let totalImpact = 0;

    news.forEach(n => {
      totalImpact += n.impactScore;
      if (n.sentiment === 'BULLISH') bullishCount++;
      if (n.sentiment === 'BEARISH') bearishCount++;
      
      const hasVolatility = this.VOLATILITY_KEYWORDS.some(k => 
        n.title.toLowerCase().includes(k) || n.summary.toLowerCase().includes(k)
      );
      if (hasVolatility) volatilityCount++;
      
      if (n.sentiment === 'BULLISH') {
        impactSummary.bullishFactors.push(n.title);
      } else if (n.sentiment === 'BEARISH') {
        impactSummary.bearishFactors.push(n.title);
      }
    });

    // Determine sentiment
    if (bullishCount > bearishCount) {
      impactSummary.sentiment = 'BULLISH';
      impactSummary.confidence = (bullishCount / news.length) * 100;
    } else if (bearishCount > bullishCount) {
      impactSummary.sentiment = 'BEARISH';
      impactSummary.confidence = (bearishCount / news.length) * 100;
    }

    // Impact level
    const avgImpact = totalImpact / news.length;
    if (avgImpact >= 80) {
      impactSummary.impactLevel = 'CRITICAL';
      impactSummary.volatilityRisk = 'VERY_HIGH';
    } else if (avgImpact >= 60) {
      impactSummary.impactLevel = 'HIGH';
      impactSummary.volatilityRisk = 'HIGH';
    } else if (avgImpact >= 40) {
      impactSummary.impactLevel = 'MEDIUM';
      impactSummary.volatilityRisk = 'MEDIUM';
    }

    // Macro event check
    const upcomingEvents = this.getUpcomingEvents();
    const relevantEvent = upcomingEvents.find(e => 
      e.symbol.includes(symbol.substring(0, 3)) && 
      (new Date() - e.date) < 24*3600*1000
    );
    if (relevantEvent) {
      impactSummary.macroEventSoon = true;
      impactSummary.warnings.push(`⚠️ ${relevantEvent.event} in ${relevantEvent.time}`);
    }

    // Recommendations
    if (impactSummary.sentiment === trade.direction.toUpperCase()) {
      impactSummary.recommendedAction = 'PROCEED_WITH_CONFIRMATION';
    } else if (impactSummary.sentiment === 'NEUTRAL') {
      impactSummary.recommendedAction = 'PROCEED_WITH_CAUTION';
    } else {
      impactSummary.recommendedAction = 'RECONSIDER';
      impactSummary.warnings.push('⚠️ News sentiment contradicts signal');
    }

    if (volatilityCount > 0 && timeframe.match(/M[1-5]/)) {
      impactSummary.warnings.push('⚠️ Volatility risk high on small timeframe');
    }

    return impactSummary;
  },

  // ─── REAL-TIME ALERT SYSTEM ───────────────────────────────────────────
  checkForBreakingNews() {
    const breakingNews = [
      {
        type: 'CRITICAL',
        message: '🚨 ECB President speech: "Rates may need adjustment"',
        timestamp: new Date(),
        impact: 'EUR at risk',
        action: 'Monitor EUR pairs closely'
      },
      {
        type: 'HIGH',
        message: '📢 China GDP beat expectations by 0.5%',
        timestamp: new Date(Date.now() - 5*60*1000),
        impact: 'Asian markets rallying',
        action: 'Indices may continue upward'
      }
    ];
    return breakingNews;
  },

  // ─── SOCIAL SENTIMENT (X/Twitter simulation) ───────────────────────────
  getSocialSentiment(symbol) {
    const mentions = {
      'BTC': { bullish: 75, bearish: 15, neutral: 10, volume: 15000 },
      'EUR': { bullish: 35, bearish: 45, neutral: 20, volume: 8000 },
      'XAU': { bullish: 60, bearish: 25, neutral: 15, volume: 5000 },
      'USD': { bullish: 55, bearish: 30, neutral: 15, volume: 12000 }
    };
    return mentions[symbol] || { bullish: 50, bearish: 50, neutral: 0, volume: 0 };
  },

  // ─── VOLATILITY SPIKE DETECTION ───────────────────────────────────────
  detectVolatilitySpike(symbol, recentVols) {
    if (!recentVols || recentVols.length < 2) return null;
    
    const avgVol = recentVols.reduce((a, b) => a + b) / recentVols.length;
    const lastVol = recentVols[recentVols.length - 1];
    const spike = (lastVol - avgVol) / avgVol;

    return {
      symbol,
      currentVolatility: lastVol.toFixed(2),
      averageVolatility: avgVol.toFixed(2),
      spikePercent: (spike * 100).toFixed(1),
      isSpiking: spike > 0.3,
      recommendation: spike > 0.3 ? 'CAUTION_INCREASED_VOLATILITY' : 'NORMAL'
    };
  },

  // ─── COMPREHENSIVE MARKET INTELLIGENCE ──────────────────────────────────
  getMarketIntelligence(symbol = 'EUR/USD', timeframe = 'H1') {
    const events = this.getUpcomingEvents();
    const news = this.getLatestNews(symbol, 5);
    const social = this.getSocialSentiment(symbol.substring(0, 3));
    const breaking = this.checkForBreakingNews();

    return {
      symbol,
      timeframe,
      timestamp: new Date().toISOString(),
      overview: {
        sentiment: news[0]?.sentiment || 'NEUTRAL',
        impactLevel: 'MEDIUM',
        riskLevel: this.riskLevel,
        volatilityExpectation: 'ELEVATED'
      },
      upcoming: events.slice(0, 3),
      latestNews: news,
      socialSentiment: social,
      breakingNews: breaking,
      tradingRecommendation: {
        symbol,
        shouldTrade: true,
        condition: 'Proceed with caution on major events',
        exitStrategy: 'Close 15 min before macro events',
        maxRisk: '2% account max'
      }
    };
  }
};

module.exports = newsAgent;
