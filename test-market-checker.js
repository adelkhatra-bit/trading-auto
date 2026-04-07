// Quick test: market-hours-checker.js
const checker = require('./lib/market-hours-checker');

console.log('\n=== MARKET HOURS CHECKER TEST ===\n');

// Test symbols
const testSymbols = ['EURUSD', 'XAUUSD', 'AAPL', 'BTC', 'UNKNOWN_SYMBOL'];

testSymbols.forEach(symbol => {
  const status = checker.getStatus(symbol);
  console.log(`${symbol}:`);
  console.log(`  - Marché: ${status.market}`);
  console.log(`  - Ouvert: ${status.isOpen ? 'OUI' : 'NON'}`);
  console.log(`  - Session: ${status.session}`);
  console.log(`  - Raison: ${status.reason}`);
  if (status.isOpen) {
    console.log(`  - Ferme dans: ${status.closesInFormatted}`);
  } else {
    console.log(`  - Ouvre dans: ${status.opensInFormatted}`);
  }
  console.log();
});

console.log('✅ Test complet');
