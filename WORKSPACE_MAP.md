# WORKSPACE MAP — TRADING AUTO

## POINT D’ENTRÉE RÉELS
- Backend : server.js
- Dashboard : dashboard.html
- Extension : tradingview-analyzer/

## EXTENSION
- tradingview-analyzer/content.js
  Rôle : lire TradingView / détecter symbole / timeframe / prix live
- tradingview-analyzer/background.js
  Rôle : transmettre les données live au backend
- tradingview-analyzer/popup.js
  Rôle : logique du popup / affichage / analyse / agent

## BACKEND
- server.js
  Rôle : recevoir TradingView live, stocker, exposer au dashboard et au popup

## DASHBOARD
- dashboard.html
  Rôle : afficher les données live existantes sans changer le design

## DOSSIERS À IGNORER SAUF DEMANDE EXPLICITE
- backup/
- studio/
- store_test_v2/
- tests/
- logs historiques
- docs d’analyse anciennes

## CHAÎNE CIBLE
TradingView
-> content.js
-> background.js
-> POST /tradingview/live
-> server.js
-> dashboard / popup
