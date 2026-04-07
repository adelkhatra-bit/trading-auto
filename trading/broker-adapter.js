const fs = require('fs');
const path = require('path');

const LOG = path.join(__dirname, 'orders.log');

function logOrder(record) {
  fs.appendFileSync(LOG, JSON.stringify(record) + "\n");
  console.log("ORDER:", record);
}

async function sendToBrokerEndpoint(order) {
  if (typeof fetch !== 'function') {
    throw new Error('Fetch API non disponible, utilisez Node 18+ ou installez un polyfill pour fetch.');
  }

  const endpoint = process.env.BROKER_ENDPOINT;
  if (!endpoint) {
    throw new Error('BROKER_ENDPOINT non configuré pour le mode live.');
  }

  const apiKey = process.env.BROKER_API_KEY || '';
  const apiSecret = process.env.BROKER_API_SECRET || '';

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-KEY': apiKey,
      'X-API-SECRET': apiSecret
    },
    body: JSON.stringify(order),
    timeout: 20000
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Broker live request failed (${response.status}): ${body}`);
  }

  const data = await response.json();
  return data;
}

function createPaperOrder(order) {
  return {
    ...order,
    status: 'filled',
    orderId: `paper-${Date.now()}`,
    timestamp: Date.now(),
    mode: 'paper'
  };
}

/**
 * placeOrder(order)
 * - mode master: process.env.BROKER_MODE: 'paper' (default) / 'live'
 * - MUST pass order object { symbol, direction, quantity, price, sl, tp }
 */
async function placeOrder(order) {
  const mode = (process.env.BROKER_MODE || 'live').toLowerCase();
  const normalized = {
    symbol: order.symbol,
    direction: order.direction,
    quantity: order.quantity || order.qty || 1,
    price: order.price || 0,
    sl: order.sl || order.stopLoss || null,
    tp: order.tp || order.takeProfit || null,
    createdAt: new Date().toISOString()
  };

  if (mode === 'live') {
    const record = {
      ...normalized,
      mode: 'live',
      requestAt: Date.now()
    };
    const liveResult = await sendToBrokerEndpoint(record);
    const result = {
      ...record,
      status: 'submitted',
      orderId: liveResult.orderId || `live-${Date.now()}`,
      brokerResponse: liveResult
    };
    logOrder(result);
    return result;
  }

  // default/paper mode: simulate immediate fill
  const record = createPaperOrder(normalized);
  logOrder(record);
  return record;
}

module.exports = { placeOrder };

