@echo off
REM ═══════════════════════════════════════════════════════════════════════════
REM  DÉMARRAGE COMPLET - TRADING-AUTO
REM  ✅ Node.js Server (studio)
REM  ✅ Environnement unique: Node.js only (port 4000)
REM ═══════════════════════════════════════════════════════════════════════════

setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║  🚀  TRADING-AUTO - DÉMARRAGE COMPLET                         ║
echo ║     Studio + Agents Runtime                                  ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo [1/2] Vérification Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Node.js n'est pas installé ou pas dans PATH
    pause
    exit /b 1
)
echo ✅ Node.js détecté
echo.

REM ───────────────────────────────────────────────────────────────────────────
REM 3. DÉMARRAGE SERVICES
REM ───────────────────────────────────────────────────────────────────────────
echo [2/2] Démarrage du serveur...
echo.

REM Tuer les anciens processus
taskkill /F /IM node.exe >nul 2>&1
timeout /t 1 >nul

REM Démarrer Node.js Server
echo ▶️  Démarrage Studio Server (port 4000)...
start "Trading Studio" cmd /k "set BROKER_MODE=live && set SAFE_MODE=0 && node server.js"
timeout /t 2 >nul

echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║  ✅ SERVICES DÉMARRÉS                                          ║
echo ╠═══════════════════════════════════════════════════════════════╣
echo ║  🌐 STUDIO                                                     ║
echo ║     http://127.0.0.1:4000/studio/                             ║
echo ║                                                               ║
echo ║  📊 AGENT LOG                                                  ║
echo ║     http://127.0.0.1:4000/agent-log                           ║
echo ║                                                               ║
echo ║  🤖 AGENTS RUNTIME                                             ║
echo ║     http://127.0.0.1:4000/agents/runtime                       ║
echo ║                                                               ║
echo ║ Attendez 10-15 secondes que tout s'initialise, puis ouvrez   ║
echo ║ l'URL Studio dans votre navigateur.                           ║
echo ║                                                               ║
echo ║ Pour arrêter: Fermez la fenêtre de terminal                   ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.
