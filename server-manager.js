#!/usr/bin/env node
/**
 * Server Manager — NovaLuce Trading Auto
 * Usage: node server-manager.js [start|stop|restart|status]
 */

const { exec, spawn } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');

const PORT = 4000;
const PID_FILE = path.join(__dirname, '.server.pid');
const SERVER_FILE = path.join(__dirname, 'server.js');

function checkHealth(cb) {
  const req = http.get(`http://127.0.0.1:${PORT}/health`, { timeout: 2000 }, (res) => {
    cb(true, res.statusCode);
  });
  req.on('error', () => cb(false, null));
  req.on('timeout', () => { req.destroy(); cb(false, null); });
}

function readPid() {
  try {
    return parseInt(fs.readFileSync(PID_FILE, 'utf8').trim());
  } catch { return null; }
}

function writePid(pid) {
  fs.writeFileSync(PID_FILE, String(pid));
}

function clearPid() {
  try { fs.unlinkSync(PID_FILE); } catch {}
}

function status() {
  checkHealth((alive, code) => {
    const pid = readPid();
    if (alive) {
      console.log(`[STATUS] ✅ Serveur actif sur port ${PORT} (HTTP ${code})${pid ? ` — PID ${pid}` : ''}`);
    } else {
      console.log(`[STATUS] ❌ Serveur inactif (port ${PORT} ne répond pas)`);
    }
  });
}

function start() {
  checkHealth((alive) => {
    if (alive) {
      console.log(`[START] Serveur déjà actif sur port ${PORT}`);
      return;
    }
    console.log(`[START] Démarrage du serveur...`);
    const child = spawn('node', [SERVER_FILE], {
      detached: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      cwd: __dirname
    });
    child.stdout.on('data', (d) => process.stdout.write(d));
    child.stderr.on('data', (d) => process.stderr.write(d));
    child.unref();
    writePid(child.pid);
    console.log(`[START] Serveur lancé — PID ${child.pid}`);
    // Vérification après 3s
    setTimeout(() => {
      checkHealth((alive, code) => {
        if (alive) console.log(`[START] ✅ Serveur opérationnel (HTTP ${code})`);
        else console.log(`[START] ⚠️ Serveur lancé mais /health ne répond pas encore`);
      });
    }, 3000);
  });
}

function stop() {
  const pid = readPid();
  if (!pid) {
    // Essai via port kill
    exec(`for /f "tokens=5" %a in ('netstat -aon ^| find ":${PORT}"') do taskkill /F /PID %a`, (err) => {
      if (err) console.log('[STOP] Aucun process trouvé sur port', PORT);
      else { console.log('[STOP] ✅ Process tué via port', PORT); clearPid(); }
    });
    return;
  }
  exec(`taskkill /F /PID ${pid}`, (err, stdout) => {
    if (err) console.log(`[STOP] Impossible de tuer PID ${pid}:`, err.message);
    else { console.log(`[STOP] ✅ PID ${pid} arrêté`); clearPid(); }
  });
}

function restart() {
  console.log('[RESTART] Arrêt en cours...');
  const pid = readPid();
  const doStart = () => setTimeout(start, 1500);
  if (pid) {
    exec(`taskkill /F /PID ${pid}`, () => { clearPid(); doStart(); });
  } else {
    exec(`for /f "tokens=5" %a in ('netstat -aon ^| find ":${PORT}"') do taskkill /F /PID %a`, () => doStart());
  }
}

const cmd = process.argv[2];
switch (cmd) {
  case 'start':   start();   break;
  case 'stop':    stop();    break;
  case 'restart': restart(); break;
  case 'status':  status();  break;
  default:
    console.log('Usage: node server-manager.js [start|stop|restart|status]');
}
