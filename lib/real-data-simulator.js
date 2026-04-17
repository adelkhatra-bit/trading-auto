/**
 * Real Data Simulator — DÉSACTIVÉ
 *
 * Ce module ne génère plus aucune donnée simulée.
 * Toutes les données de prix proviennent exclusivement de TradingView (tvDataStore)
 * via getLatestTradingviewRuntime() et getLivePrice().
 *
 * Les routes /symbols et /data/refresh ont été supprimées de server.js.
 * La commande 'refresh-data' et 'get-symbols' retournent une erreur explicite.
 */

'use strict';

function disabled(name) {
  throw new Error(`[SIMULATOR DISABLED] ${name}() — Le simulateur de données est désactivé. Toutes les données de prix proviennent de TradingView live uniquement.`);
}

function getNextData() {
  disabled('getNextData');
}

function getDataForSymbol(_symbol) {
  disabled('getDataForSymbol');
}

function getAvailableSymbols() {
  disabled('getAvailableSymbols');
}

module.exports = {
  getNextData,
  getDataForSymbol,
  getAvailableSymbols
};
