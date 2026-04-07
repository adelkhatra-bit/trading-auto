const fs = require('fs');
const path = require('path');

const FILE = path.join(__dirname, '..', 'bridge', 'out', 'result.json');

function analyze() {
  try {
    let raw = fs.readFileSync(FILE, 'utf8').trim();
    if (!raw.startsWith('{')) return;

    const data = JSON.parse(raw);

    let action = "ignore";
    if (data.entry > 120) action = "buy";
    if (data.entry < 120) action = "sell";

    const result = {
      status: "live",
      action,
      entry: data.entry,
      sl: data.sl,
      tp: data.tp,
      confidence: data.confidence,
      size: 0.01,
      timestamp: Date.now()
    };

    fs.writeFileSync(FILE, JSON.stringify(result, null, 2));
    console.log("ANALYSIS OK");

  } catch (e) {
    console.log("ANALYSIS SKIP");
  }
}

// ✋ DISABLED: setInterval(analyze, 2000) was a CPU killer
// RAISON: Polling toutes les 2 secondes = fs.readFileSync + JSON.parse en boucle
// RÉSULTAT: 100% CPU, I/O saturation, système freeze
//
// NOUVELLE APPROCHE: Call analyze() à la demande via HTTP POST
// 
// Mode SAFE (défaut): Aucune analyse automatique
// Mode AUTO (optionnel): enableAutoAnalysis(intervalMs) — l'utilisateur décide

let _autoAnalysisTimer = null;

function enableAutoAnalysis(intervalMs = 5000) {
  if (intervalMs < 1000) {
    console.warn('[ANALYZER] MIN interval is 1000ms, using 1000ms');
    intervalMs = 1000;
  }
  if (_autoAnalysisTimer) clearInterval(_autoAnalysisTimer);
  _autoAnalysisTimer = setInterval(analyze, intervalMs);
  console.log('[ANALYZER] ✓ Auto-analysis ENABLED @ ' + intervalMs + 'ms');
  return { enabled: true, interval: intervalMs };
}

function disableAutoAnalysis() {
  if (_autoAnalysisTimer) {
    clearInterval(_autoAnalysisTimer);
    _autoAnalysisTimer = null;
  }
  console.log('[ANALYZER] ✓ Auto-analysis DISABLED');
  return { enabled: false };
}

function getAnalysisStatus() {
  return { 
    enabled: _autoAnalysisTimer !== null, 
    note: 'Call analyze() via POST /analyze' 
  };
}

// Export pour utilisation en module
module.exports = module.exports || {};
module.exports.analyze = analyze;
module.exports.enableAutoAnalysis = enableAutoAnalysis;
module.exports.disableAutoAnalysis = disableAutoAnalysis;
module.exports.getAnalysisStatus = getAnalysisStatus;
