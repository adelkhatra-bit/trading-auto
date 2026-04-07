@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo.
echo ════════════════════════════════════════════════════════════════════
echo  🚀 TRADING AUTO - DÉMARRAGE DÉFINITIF (Port 4000 UNIQUE)
echo  Configuration ENREGISTRÉE - 100%% EXCLUSIVE
echo ════════════════════════════════════════════════════════════════════
echo.

REM Tuer les anciens processus
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM node.exe >nul 2>&1
timeout /t 1 >nul

echo [1/2] Démarrage Node.js Studio Server (port 4000)...
start "Trading-Auto-Studio-4000" cmd /k "cd /d %%~dp0 && set BROKER_MODE=live && set SAFE_MODE=0 && node server.js"

timeout /t 2 >nul

echo.
echo ════════════════════════════════════════════════════════════════════
echo  ✅ SERVICES LANCÉS
echo ════════════════════════════════════════════════════════════════════
echo.
echo  📂 Studio HTML:     http://127.0.0.1:4000/studio/
echo  🤖 Runtime Agents:  http://127.0.0.1:4000/agents/runtime
echo  💬 Agent Activity:  http://127.0.0.1:4000/agent-activity
echo.
echo  ⏳ Attendez 3-5 secondes que les services démarrent
echo  👁️  Vérifiez qu'AUCUNE ERREUR rouge ne s'affiche
echo.
echo ════════════════════════════════════════════════════════════════════
echo.
echo Extension Chrome : recharger dans chrome://extensions
echo MT5 EA           : doit ecrire dans mt5_data.json
echo.
pause
