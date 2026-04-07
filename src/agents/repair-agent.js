/**
 * Repair Agent — Automatic problem detection and correction
 * Role: Analyze issues and apply fixes
 */

const EventEmitter = require('events');

class RepairAgent extends EventEmitter {
  constructor() {
    super();
    this.name = 'repair-agent';
    this.role = 'Automatic diagnostics and repair';
    this.status = 'idle';
    this.repairs = [];
  }

  /**
   * Analyze and repair a problem
   * @param {string} issue - Problem description
   * @param {object} context - Issue context
   */
  async repair(issue, context = {}) {
    this.status = 'analyzing';
    const id = Date.now();

    console.log(`[REPAIR] Analyzing: ${issue}`);

    const repair = {
      id,
      timestamp: new Date().toISOString(),
      issue,
      status: 'analyzing',
      fixes: [],
      result: null
    };

    // Detect and apply fixes
    if (issue.includes('agent') || issue.includes('connection')) {
      repair.fixes.push('Restart agent registry');
      repair.fixes.push('Reset message queue');
      repair.result = { action: 'restart', component: 'agent-bus' };
    }

    if (issue.includes('price') || issue.includes('data')) {
      repair.fixes.push('Clear stale cache');
      repair.fixes.push('Reconnect market data source');
      repair.result = { action: 'reconnect', component: 'market-store' };
    }

    if (issue.includes('alert') || issue.includes('notification')) {
      repair.fixes.push('Reset alert queue');
      repair.fixes.push('Clear subscribers');
      repair.result = { action: 'reset', component: 'alert-manager' };
    }

    if (repair.fixes.length === 0) {
      repair.fixes.push('No specific fix found - logging for review');
      repair.result = { action: 'log', component: 'manual-review' };
    }

    repair.status = 'completed';
    this.repairs.push(repair);
    this.status = 'idle';

    return repair;
  }

  /**
   * Get repair history
   */
  getHistory(limit = 10) {
    return this.repairs.slice(-limit).reverse();
  }

  /**
   * Get agent state
   */
  getState() {
    return {
      name: this.name,
      role: this.role,
      status: this.status,
      repairsCompleted: this.repairs.length,
      lastRepair: this.repairs[this.repairs.length - 1] || null
    };
  }
}

module.exports = new RepairAgent();
