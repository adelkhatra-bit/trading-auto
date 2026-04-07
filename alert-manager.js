/**
 * Alert Manager — Centralized alert system with filtering and SSE support
 * Role: Create, filter, and broadcast alerts to clients
 * 
 * Features:
 * - createAlert(type, severity, symbol, data) — Create alert
 * - filterBySymbol(symbols) — Get alerts for specific symbols
 * - getRecent(limit) — Get recent alerts
 * - subscribe(res) — SSE client subscription
 * - broadcast(alert) — Send to all subscribed clients
 */

class AlertManager {
  constructor() {
    this.alerts = [];
    this.subscribers = [];
    this.maxAlerts = 500;  // Keep last 500 alerts
    this.monitoredSymbols = new Set();
  }

  /**
   * Create a new alert
   * @param {string} type - Alert type (e.g. "SIGNAL", "INDICATOR", "ERROR")
   * @param {string} severity - HIGH | MEDIUM | LOW
   * @param {string} symbol - Asset symbol
   * @param {object} data - Alert data (direction, score, etc)
   */
  createAlert(type, severity, symbol, data = {}) {
    const alert = {
      id: Date.now(),
      timestamp: new Date().toISOString(),
      type,
      severity,
      symbol,
      data
    };

    this.alerts.push(alert);
    if (this.alerts.length > this.maxAlerts) {
      this.alerts = this.alerts.slice(-this.maxAlerts);
    }

    this.broadcast(alert);
    return alert;
  }

  /**
   * Register monitored symbols for filtering
   * @param {array} symbols - Symbols to monitor
   */
  setMonitored(symbols = []) {
    this.monitoredSymbols = new Set(symbols.map(s => (s || '').toUpperCase()));
  }

  /**
   * Filter alerts by monitored symbols
   */
  filterByMonitored() {
    if (this.monitoredSymbols.size === 0) {
      return this.alerts;  // No filtering if empty
    }
    return this.alerts.filter(a => this.monitoredSymbols.has((a.symbol || '').toUpperCase()));
  }

  /**
   * Get recent alerts
   * @param {number} limit - Number of alerts to return
   */
  getRecent(limit = 50) {
    return this.alerts.slice(-limit).reverse();
  }

  /**
   * Get all alerts for a specific symbol
   * @param {string} symbol - Asset symbol
   */
  getBySymbol(symbol) {
    return this.alerts.filter(a => (a.symbol || '').toUpperCase() === (symbol || '').toUpperCase());
  }

  /**
   * Subscribe to SSE alerts
   * @param {express.Response} res - Express response object (for SSE)
   */
  subscribe(res) {
    if (!res || typeof res.write !== 'function') {
      console.warn('[ALERT] Invalid SSE client');
      return;
    }

    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive'
    });

    this.subscribers.push(res);

    res.on('close', () => {
      this.subscribers = this.subscribers.filter(s => s !== res);
    });

    res.on('error', () => {
      this.subscribers = this.subscribers.filter(s => s !== res);
    });
  }

  /**
   * Broadcast alert to all subscribed clients
   * @param {object} alert - Alert object
   */
  broadcast(alert) {
    if (this.subscribers.length === 0) return;

    // Only send alerts for monitored symbols (if any)
    if (this.monitoredSymbols.size > 0) {
      if (!this.monitoredSymbols.has((alert.symbol || '').toUpperCase())) {
        return;
      }
    }

    const data = `data: ${JSON.stringify(alert)}\n\n`;
    this.subscribers = this.subscribers.filter(res => {
      try {
        res.write(data);
        return true;
      } catch (e) {
        return false;
      }
    });
  }

  /**
   * Get alert manager state
   */
  getState() {
    return {
      totalAlerts: this.alerts.length,
      recentAlerts: this.getRecent(10),
      monitoredSymbols: Array.from(this.monitoredSymbols),
      subscribers: this.subscribers.length
    };
  }

  /**
   * Clear all alerts
   */
  clear() {
    this.alerts = [];
  }
}

module.exports = new AlertManager();
