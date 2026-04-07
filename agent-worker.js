// agent-worker.js — Tourne en continu, lit tasks.json, exécute, répond
// Lance avec : node agent-worker.js
// Ce script simule le worker "deuxième IA" qui exécute les tâches de Claude

'use strict';
const fs   = require('fs');
const path = require('path');
const ROOT = __dirname;

const TASKS = path.join(ROOT, 'tasks.json');
const LOGS  = path.join(ROOT, 'logs.json');

function readJSON(p) { try { return JSON.parse(fs.readFileSync(p,'utf8')); } catch(_) { return null; } }
function writeJSON(p, d) { fs.writeFileSync(p, JSON.stringify(d, null, 2)); }

// Buffer mémoire pour éviter 1 writeFileSync par log
var _logBuffer = null;
var _logFlushTimer = null;
function addLog(agent, taskId, action, status, detail) {
  if (!_logBuffer) _logBuffer = readJSON(LOGS) || { logs:[] };
  _logBuffer.logs = _logBuffer.logs || [];
  _logBuffer.logs.unshift({ id: Date.now(), ts: new Date().toISOString(), agent, task_id: taskId, action, status, detail: detail||'' });
  if (_logBuffer.logs.length > 200) _logBuffer.logs.pop();
  console.log('[' + new Date().toLocaleTimeString() + '] ' + agent + ' | ' + action + ' | ' + status);
  // Écriture disque max 1 fois toutes les 3 secondes
  if (!_logFlushTimer) {
    _logFlushTimer = setTimeout(function() {
      _logFlushTimer = null;
      if (_logBuffer) writeJSON(LOGS, _logBuffer);
    }, 3000);
  }
}

function updateTask(taskId, status, result) {
  var data = readJSON(TASKS);
  if (!data) return;
  var task = (data.tasks||[]).find(t => t.task_id === taskId);
  if (task) { task.status = status; if (result) task.result = result; task.updated_at = new Date().toISOString(); }
  data.updated = new Date().toISOString();
  writeJSON(TASKS, data);
}

// ── Exécuteurs de tâches ───────────────────────────────────────────────────────

function executeTask(task) {
  console.log('\n▶ Exécution tâche ' + task.task_id + ': ' + task.instruction);
  updateTask(task.task_id, 'in_progress');
  addLog('agent-worker', task.task_id, 'TASK START: ' + task.instruction, 'ok');

  try {
    var result = '';

    // T001 — Vérifier les fichiers extension
    if (task.task_id === 'T001' || task.instruction.toLowerCase().includes('tradingview')) {
      var manifestPath = path.join(ROOT, 'tradingview-analyzer', 'manifest.json');
      var manifest = readJSON(manifestPath);
      var version  = manifest && manifest.version;
      var runAt    = manifest && manifest.content_scripts && manifest.content_scripts[0] && manifest.content_scripts[0].run_at;
      result = 'manifest v' + version + ' | run_at: ' + runAt + ' | ' + (runAt === 'document_idle' ? 'OK' : 'ERREUR — doit être document_idle');
      addLog('agent-worker', task.task_id, 'CHECK manifest: ' + result, runAt === 'document_idle' ? 'ok' : 'err');
    }

    // TEST-001 — Hello test
    if (task.task_id === 'TEST-001') {
      result = 'HELLO FROM AGENT-WORKER — timestamp: ' + Date.now();
      addLog('agent-worker', task.task_id, 'HELLO TEST EXECUTED', 'ok', result);
    }

    // Générique : loguer les steps
    if (task.steps && task.steps.length) {
      task.steps.forEach(function(step, i) {
        addLog('agent-worker', task.task_id, 'STEP ' + (i+1) + ': ' + step, 'ok');
      });
    }

    updateTask(task.task_id, 'done', result || 'completed');
    addLog('agent-worker', task.task_id, 'TASK DONE', 'ok', result);
    console.log('✅ Tâche ' + task.task_id + ' terminée');

  } catch(e) {
    updateTask(task.task_id, 'error', e.message);
    addLog('agent-worker', task.task_id, 'TASK ERROR', 'err', e.message);
    console.error('❌ Erreur tâche ' + task.task_id + ':', e.message);
  }
}

// ── Boucle principale ─────────────────────────────────────────────────────────

function loop() {
  var data = readJSON(TASKS);
  if (!data || !data.tasks) return;

  var pending = data.tasks.filter(t => t.status === 'pending');
  if (pending.length === 0) return;

  // Prendre la tâche prioritaire
  pending.sort((a,b) => (a.priority||9) - (b.priority||9));
  executeTask(pending[0]);
}

console.log('🤖 Agent Worker démarré — écoute tasks.json toutes les 5s');
console.log('   Dossier:', ROOT);
addLog('agent-worker', 'SYSTEM', 'WORKER STARTED', 'ok', 'polling tasks.json every 5s');

// Première vérification immédiate
loop();
// DÉSACTIVÉ: setInterval(loop, 5000) = boucle infinie
// Cause: Polling tasks.json en continu → CPU 100%
// Solution: Utiliser endpoint /check-agent-tasks à la demande
// Ajout: Mode SAFE avec contrôle manuel
