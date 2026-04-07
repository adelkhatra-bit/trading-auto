@echo off
REM ════════════════════════════════════════════════════════════════════════════════
REM  TRADING AUTO - CLEAN STARTUP (Port 4000 only)
REM  Single environment mode
REM ════════════════════════════════════════════════════════════════════════════════

echo.
echo ════════════════════════════════════════════════════════════════════════════════
echo  🚀 TRADING AUTO - DÉMARRAGE COMPLET
echo ════════════════════════════════════════════════════════════════════════════════
echo.
echo ⚠️  PORT UNIQUE UTILISÉ:
echo   • Node.js Studio:    PORT 4000  (http://127.0.0.1:4000/studio/)
echo.

REM Arrêter les anciennes instances
echo 📋 Nettoyage...
taskkill /F /IM node.exe 2>nul
timeout /t 1 /nobreak

REM Vérifier que les ports sont libres
echo.
echo 🔍 Vérification des ports...
netstat -ano | findstr ":4000" >nul
if not errorlevel 1 (
    echo ❌ PORT 4000 déjà utilisé!
    echo    Arrêtez le service qui utilise ce port
    timeout /t 5
    exit /b 1
)

echo ✅ Port 4000 est libre

REM Lancer Node.js Studio (4000)
echo.
echo 🟢 Lancement Studio Server (port 4000)...
start "TradingAuto-Studio-4000" cmd /k "cd /d %~dp0 && node server.js"
timeout /t 2 /nobreak

REM Résumé
echo.
echo ════════════════════════════════════════════════════════════════════════════════
echo  ✅ SERVICES LANCÉS
echo ════════════════════════════════════════════════════════════════════════════════
echo.
echo 📂 ACCÈS:
echo.
echo   Studio:          http://127.0.0.1:4000/studio/
echo   Runtime agents:  http://127.0.0.1:4000/agents/runtime
echo   Agent activity:  http://127.0.0.1:4000/agent-activity
echo.
echo 🔧 NOTES:
echo   • Ne fermez PAS la fenêtre CMD (= arrêt du service)
echo   • Attendez 3-5 secondes que les services démarrent
echo   • Vérifiez que NO ERREURS ne s'affichent
echo.
echo ════════════════════════════════════════════════════════════════════════════════
echo.
