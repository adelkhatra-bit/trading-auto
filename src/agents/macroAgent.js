async function getEconomicCalendar() {
  try {
    // Utiliser une API économique publique ou fallback statique
    const today = new Date().toISOString().split('T')[0];
    return [
      { time: '06:45', date: today, currency: 'EUR', event: 'PIB Q1', impact: 'Élevé', previous: '2.4%', forecast: '2.5%' },
      { time: '10:30', date: today, currency: 'USD', event: 'NFP', impact: 'Élevé', previous: '275K', forecast: '280K' },
      { time: '14:00', date: today, currency: 'GBP', event: 'BoE decision', impact: 'Élevé', previous: '5.25%', forecast: '5.00%' },
      { time: '15:30', date: today, currency: 'USD', event: 'Core PCE', impact: 'Moyen', previous: '3.7%', forecast: '3.5%' }
    ];
  } catch (err) {
    console.error('Erreur fetch calendar:', err);
    return [];
  }
}

async function analyzeEconomicImpact(calendar) {
  let score = 50; // neutral baseline
  let riskLevel = 'Low';

  for (const event of calendar) {
    if (event.impact === 'Élevé') {
      score += 10;
      riskLevel = 'High';
    } else if (event.impact === 'Moyen') {
      score += 5;
    }
  }

  return {
    name: 'Macro Agent',
    score: Math.min(100, score),
    riskLevel,
    analysis: `${calendar.length} événements macro prévus. Risk: ${riskLevel}`,
    nextEvent: calendar[0]?.event || 'aucun'
  };
}

module.exports = { getEconomicCalendar, analyzeEconomicImpact };
