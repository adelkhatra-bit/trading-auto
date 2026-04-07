// chart-renderer.js - Rendu de graphiques dans la popup extension
// Utilise Chart.js pour afficher l'analyse technique

'use strict';

let chart = null;
let chartElement = null;

/**
 * Initialiser le rendu du graphique
 */
function initChart(containerId = 'price-chart') {
  chartElement = document.getElementById(containerId);
  if (!chartElement) {
    console.error('[CHART] Élément', containerId, 'non trouvé');
    return false;
  }
  
  console.log('[CHART] ✓ Initialisation graphique');
  return true;
}

/**
 * Dessiner un graphique de prix OHLC simple
 */
function drawPriceChart(ohlcData, signalData = null) {
  if (!chartElement) {
    console.error('[CHART] Chart non initialisé');
    return;
  }
  
  if (!ohlcData || ohlcData.length === 0) {
    console.warn('[CHART] Pas de données OHLC');
    return;
  }
  
  console.log('[CHART] Dessiner graphique avec', ohlcData.length, 'bougies');
  
  // Extraire les labels et valeurs
  const labels = ohlcData.map(c => c.time || c.date);
  const closes = ohlcData.map(c => parseFloat(c.close));
  const highs = ohlcData.map(c => parseFloat(c.high));
  const lows = ohlcData.map(c => parseFloat(c.low));
  
  // Dataset principal - prix de clôture
  const datasets = [{
    label: 'Close',
    data: closes,
    borderColor: '#3b82f6',
    backgroundColor: 'rgba(59, 130, 246, 0.1)',
    borderWidth: 2,
    fill: true,
    tension: 0.4,
    pointRadius: 3,
    pointBackgroundColor: '#3b82f6',
  }];
  
  // Ajouter signal si présent
  if (signalData) {
    if (signalData.direction === 'LONG') {
      datasets.push({
        label: '↑ ACHAT',
        data: [null, signalData.price, null],  // Afficher au milieu
        borderColor: '#10b981',
        backgroundColor: 'rgba(16, 185, 129, 0.2)',
        borderWidth: 3,
        pointRadius: 8,
        pointBackgroundColor: '#10b981',
      });
    } else if (signalData.direction === 'SHORT') {
      datasets.push({
        label: '↓ VENTE',
        data: [null, signalData.price, null],
        borderColor: '#ef4444',
        backgroundColor: 'rgba(239, 68, 68, 0.2)',
        borderWidth: 3,
        pointRadius: 8,
        pointBackgroundColor: '#ef4444',
      });
    }
    
    // Ajouter SL et TP
    if (signalData.sl) {
      datasets.push({
        label: 'SL',
        data: Array(closes.length).fill(parseFloat(signalData.sl)),
        borderColor: '#ef4444',
        borderDash: [5, 5],
        borderWidth: 1,
        pointRadius: 0,
        fill: false,
      });
    }
    
    if (signalData.tp) {
      datasets.push({
        label: 'TP',
        data: Array(closes.length).fill(parseFloat(signalData.tp)),
        borderColor: '#10b981',
        borderDash: [5, 5],
        borderWidth: 1,
        pointRadius: 0,
        fill: false,
      });
    }
  }
  
  // Détruire ancien graphique s'il existe
  if (chart) {
    chart.destroy();
  }
  
  // Créer nouveau graphique
  const ctx = chartElement.getContext('2d');
  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          labels: {
            color: '#e2e8f0',
            font: { size: 10 },
          },
        },
        tooltip: {
          backgroundColor: 'rgba(15, 23, 42, 0.9)',
          titleColor: '#e2e8f0',
          bodyColor: '#cbd5e1',
          borderColor: '#1e3a5f',
          borderWidth: 1,
        },
      },
      scales: {
        y: {
          ticks: {
            color: '#94a3b8',
            font: { size: 10 },
          },
          grid: {
            color: 'rgba(30, 58, 95, 0.3)',
          },
          title: {
            display: true,
            text: 'Prix',
            color: '#94a3b8',
          },
        },
        x: {
          ticks: {
            color: '#94a3b8',
            font: { size: 10 },
            maxRotation: 45,
            minRotation: 0,
          },
          grid: {
            color: 'rgba(30, 58, 95, 0.3)',
          },
        },
      },
    },
  });
  
  console.log('[CHART] ✓ Graphique drawn');
}

/**
 * Dessiner graphique simple d'analyse technique
 */
function drawTechnicalAnalysis(analysisData) {
  if (!chartElement) {
    console.error('[CHART] Chart non initialisé');
    return;
  }
  
  console.log('[CHART] Dessiner analyse technique');
  
  const categories = ['Trend', 'Support', 'Resistance', 'Volatility', 'Momentum'];
  const values = [
    analysisData.trend || 50,
    analysisData.support || 40,
    analysisData.resistance || 60,
    analysisData.volatility || 45,
    analysisData.momentum || 55,
  ];
  
  const colors = values.map(v => v > 60 ? '#10b981' : (v > 40 ? '#f59e0b' : '#ef4444'));
  
  // Détruire ancien graphique
  if (chart) {
    chart.destroy();
  }
  
  // Créer une jauge
  const ctx = chartElement.getContext('2d');
  chart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: categories,
      datasets: [{
        label: 'Score Technique',
        data: values,
        backgroundColor: colors,
        borderColor: '#1e3a5f',
        borderWidth: 1,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(15, 23, 42, 0.9)',
          titleColor: '#e2e8f0',
          bodyColor: '#cbd5e1',
        },
      },
      scales: {
        x: {
          max: 100,
          ticks: { color: '#94a3b8' },
          grid: { color: 'rgba(30, 58, 95, 0.3)' },
        },
        y: {
          ticks: { color: '#94a3b8' },
        },
      },
    },
  });
  
  console.log('[CHART] ✓ Analyse technique graphique');
}

/**
 * Afficher signal visuel sur le graphique
 */
function addSignalOverlay(signal) {
  if (!signal) return;
  
  console.log('[CHART] Ajouter overlay signal:', signal.direction);
  
  // Ajouter une annotation
  if (chart && chart.data.datasets) {
    const signalDataset = {
      label: signal.direction === 'LONG' ? '🟢 ACHAT' : '🔴 VENTE',
      data: Array(chart.data.labels.length).fill(signal.entry),
      borderColor: signal.direction === 'LONG' ? '#10b981' : '#ef4444',
      borderWidth: 2,
      pointRadius: 0,
      fill: false,
    };
    
    chart.data.datasets.push(signalDataset);
    chart.update();
  }
}

/**
 * Effacer le graphique
 */
function clearChart() {
  if (chart) {
    chart.destroy();
    chart = null;
  }
  console.log('[CHART] ✓ Chart cleared');
}

/**
 * Charger Chart.js si pas déjà chargé
 */
function ensureChartLib() {
  if (typeof Chart !== 'undefined') {
    return true;
  }
  
  console.warn('[CHART] Chart.js pas chargé - injection du script');
  
  // Charger Chart.js en ligne depuis CDN
  const script = document.createElement('script');
  script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
  script.onload = () => {
    console.log('[CHART] ✓ Chart.js chargé');
  };
  script.onerror = () => {
    console.error('[CHART] ✗ Impossible de charger Chart.js');
  };
  document.head.appendChild(script);
  
  return false;
}

// Export
module.exports = {
  initChart,
  drawPriceChart,
  drawTechnicalAnalysis,
  addSignalOverlay,
  clearChart,
  ensureChartLib,
};
