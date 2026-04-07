@echo off
REM ============================================================
REM QUICK START: Démarre tout et teste automatiquement
REM ============================================================

echo.
echo ════════════════════════════════════════════════════════════
echo  🚀 TRADING AUTO — QUICK START
echo ════════════════════════════════════════════════════════════
echo.

REM Arrêter les services précédents
echo 📋 Arrêt des services précédents...
taskkill /F /IM node.exe 2>nul
taskkill /F /IM python.exe 2>nul
timeout /t 1 /nobreak

echo.
echo ✅ Services arrêtés

REM Lancer Node.js (Studio)
echo.
echo 🟢 Lancement Studio (port 4000)
start "Studio Server" cmd /k "set BROKER_MODE=live && set SAFE_MODE=0 && node server.js"
timeout /t 2 /nobreak

echo.
echo ════════════════════════════════════════════════════════════
echo  ✅ TOUS LES SERVICES LANCÉS
echo ════════════════════════════════════════════════════════════
echo.
echo 📂 URLS À OUVRIR (dans votre navigateur):
echo.
echo   Studio Dashboard:   http://127.0.0.1:4000/studio/
echo   Runtime Agents:     http://127.0.0.1:4000/agents/runtime
echo   Agent Activity:     http://127.0.0.1:4000/agent-activity
echo.
echo 🧪 POUR TESTS RAPIDES (en PowerShell):
echo.
echo   python quick-check.py        [Vérification endpoints]
echo   pwsh start-and-verify.ps1    [Démarrage + vérification]
echo.
echo 📝 EXTENSION CHROME:
echo.
echo   1. Ouvrir chrome://extensions
echo   2. Activer "Mode développeur" (haut-droit)
echo   3. Cliquer "Charger l'extension non emballée"
echo   4. Sélectionner: c:\Users\97156\OneDrive\Desktop\trading-auto\tradingview-analyzer\
echo   5. Ouvrir extension → Test tous les onglets
echo.
echo 📋 CHECKLIST COMPLÈTE:
echo.
echo   Voir: EXTENSION_TEST_CHECKLIST.md
echo.
echo ════════════════════════════════════════════════════════════
echo.
echo 💡 Fenêtres actives:
echo   • Studio Server    (port 4000)
echo.
echo 👁️  Gardez ces fenêtres ouvertes. Fermer = arrêt des services.
echo.
echo ════════════════════════════════════════════════════════════
timeout /t 10 /nobreak
