// audit-logger.js — Synchronisation automatique audit.json
// Source de vérité du système en temps réel

'use strict';

const fs = require('fs');
const path = require('path');

const AUDIT_PATH = path.join(__dirname, 'audit.json');

// ─── CORE FUNCTIONS ───────────────────────────────────────────────────────────

class AuditLogger {
  constructor() {
    this.audit = this.readAudit();
    this.eventLog = [];
    this.subscribers = [];
  }

  // Lire audit.json
  readAudit() {
    try {
      const raw = fs.readFileSync(AUDIT_PATH, 'utf8');
      return JSON.parse(raw);
    } catch (e) {
      console.error('[AUDIT] Error reading audit.json:', e.message);
      return { files: [], agents: [], endpoints: [], connections: [], errors: [], tasks: [], metadata: {} };
    }
  }

  // Écrire audit.json
  writeAudit() {
    try {
      fs.writeFileSync(AUDIT_PATH, JSON.stringify(this.audit, null, 2), 'utf8');
      this.notifySubscribers({ type: 'audit-updated', timestamp: new Date().toISOString() });
    } catch (e) {
      console.error('[AUDIT] Error writing audit.json:', e.message);
    }
  }

  // Logger un événement
  logEvent(category, action, details = {}) {
    const event = {
      id: `evt-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      timestamp: new Date().toISOString(),
      category,   // 'task' | 'error' | 'endpoint' | 'connection' | 'file'
      action,     // 'created' | 'updated' | 'completed' | 'failed'
      details,
      severity: details.severity || 'info'
    };

    this.eventLog.push(event);
    if (this.eventLog.length > 500) this.eventLog.shift(); // Limiter à 500 events

    console.log(`[AUDIT] ${category.toUpperCase()} ${action.toUpperCase()}: ${details.name || details.id || ''}`);
    this.notifySubscribers(event);

    return event;
  }

  // ─── TASK MANAGEMENT ───────────────────────────────────────────────

  // Créer ou mettre à jour une tâche
  updateTask(taskId, updates) {
    let task = this.audit.tasks.find(t => t.id === taskId);
    
    if (!task) {
      task = {
        id: taskId,
        name: updates.name || 'Unnamed Task',
        status: 'not-started',
        files: [],
        completeness: 0,
        issues: [],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };
      this.audit.tasks.push(task);
      this.logEvent('task', 'created', { id: taskId, name: task.name });
    } else {
      this.logEvent('task', 'updated', { id: taskId, name: task.name, oldStatus: task.status, newStatus: updates.status });
    }

    // Appliquer les mises à jour
    Object.assign(task, updates);
    task.updatedAt = new Date().toISOString();

    this.writeAudit();
    return task;
  }

  // Marquer une tâche complète
  completeTask(taskId) {
    const task = this.audit.tasks.find(t => t.id === taskId);
    if (task) {
      task.status = 'completed';
      task.completeness = 100;
      task.completedAt = new Date().toISOString();
      task.updatedAt = new Date().toISOString();
      this.logEvent('task', 'completed', { id: taskId, name: task.name, severity: 'success' });
      this.writeAudit();
    }
    return task;
  }

  // Ajouter une tâche en erreur
  failTask(taskId, reason) {
    const task = this.audit.tasks.find(t => t.id === taskId);
    if (task && task.status !== 'completed') {
      task.status = 'error';
      task.failedAt = new Date().toISOString();
      task.failureReason = reason;
      task.updatedAt = new Date().toISOString();
      this.logEvent('task', 'failed', { id: taskId, name: task.name, reason, severity: 'error' });
      this.writeAudit();
    }
    return task;
  }

  // ─── ERROR MANAGEMENT ───────────────────────────────────────────────

  // Ajouter une erreur
  addError(errorId, errorData) {
    let error = this.audit.errors.find(e => e.id === errorId);
    
    if (!error) {
      error = {
        id: errorId,
        type: errorData.type || 'unknown',
        severity: errorData.severity || 'medium',
        description: errorData.description || '',
        affectedFile: errorData.affectedFile || '',
        affectedComponent: errorData.affectedComponent || '',
        detectedAt: new Date().toISOString(),
        status: 'open'
      };
      this.audit.errors.push(error);
      this.logEvent('error', 'detected', { id: errorId, type: errorData.type, severity: errorData.severity });
    } else {
      Object.assign(error, errorData);
      this.logEvent('error', 'updated', { id: errorId, type: errorData.type });
    }

    error.lastUpdated = new Date().toISOString();
    this.writeAudit();
    return error;
  }

  // Résoudre une erreur
  resolveError(errorId, resolution) {
    const error = this.audit.errors.find(e => e.id === errorId);
    if (error) {
      error.status = 'resolved';
      error.resolution = resolution;
      error.resolvedAt = new Date().toISOString();
      this.logEvent('error', 'resolved', { id: errorId, resolution, severity: 'success' });
      this.writeAudit();
    }
    return error;
  }

  // ─── ENDPOINT MANAGEMENT ──────────────────────────────────────────

  // Ajouter/mettre à jour un endpoint
  updateEndpoint(path, updates) {
    let endpoint = this.audit.endpoints.find(e => e.path === path);
    
    if (!endpoint) {
      endpoint = {
        path,
        method: updates.method || 'GET',
        type: updates.type || 'api',
        status: updates.status || 'OK',
        description: updates.description || '',
        file: updates.file || '',
        createdAt: new Date().toISOString()
      };
      this.audit.endpoints.push(endpoint);
      this.logEvent('endpoint', 'created', { path, method: updates.method });
    } else {
      this.logEvent('endpoint', 'updated', { path, oldStatus: endpoint.status, newStatus: updates.status });
      Object.assign(endpoint, updates);
    }

    endpoint.lastUpdated = new Date().toISOString();
    this.writeAudit();
    return endpoint;
  }

  // ─── CONNECTION MANAGEMENT ───────────────────────────────────────

  // Mettre à jour statut d'une connexion
  updateConnection(connId, status, details = {}) {
    let connection = this.audit.connections.find(c => c.id === connId);
    
    if (!connection) {
      connection = {
        id: connId,
        from: details.from || '',
        to: details.to || '',
        type: details.type || 'unknown',
        status,
        createdAt: new Date().toISOString()
      };
      this.audit.connections.push(connection);
    } else {
      this.logEvent('connection', 'status-changed', { id: connId, oldStatus: connection.status, newStatus: status });
      connection.status = status;
    }

    connection.lastChecked = new Date().toISOString();
    Object.assign(connection, details);
    this.writeAudit();
    return connection;
  }

  // ─── FILE MANAGEMENT ──────────────────────────────────────────────

  // Marquer un fichier modifié
  markFileModified(fileId, updates = {}) {
    const file = this.audit.files.find(f => f.id === fileId);
    if (file) {
      file.lastModified = new Date().toISOString();
      file.modificationCount = (file.modificationCount || 0) + 1;
      Object.assign(file, updates);
      this.logEvent('file', 'modified', { id: fileId, name: file.name });
      this.writeAudit();
    }
    return file;
  }

  // ─── METADATA UPDATES ──────────────────────────────────────────────

  updateMetadata() {
    const meta = this.audit.metadata || {};
    meta.totalFiles = this.audit.files.length;
    meta.totalAgents = this.audit.agents.length;
    meta.totalEndpoints = this.audit.endpoints.length;
    meta.totalConnections = this.audit.connections.length;
    meta.completedTasks = this.audit.tasks.filter(t => t.status === 'completed').length;
    meta.incompleteTasks = this.audit.tasks.filter(t => t.status !== 'completed').length;
    meta.criticalErrors = this.audit.errors.filter(e => e.severity === 'high').length;
    meta.lastUpdated = new Date().toISOString();

    this.audit.metadata = meta;
    this.writeAudit();
    return meta;
  }

  // ─── STATE MANAGEMENT ──────────────────────────────────────────────

  // Obtenir l'état complet
  getState() {
    this.updateMetadata();
    return {
      ok: true,
      audit: this.audit,
      eventLog: this.eventLog.slice(-50), // Derniers 50 events
      timestamp: new Date().toISOString()
    };
  }

  // Obtenir les événements récents
  getRecentEvents(limit = 20) {
    return {
      ok: true,
      events: this.eventLog.slice(-limit).reverse(),
      timestamp: new Date().toISOString()
    };
  }

  // ─── NOTIFICATION SYSTEM ──────────────────────────────────────────

  // Abonner à les changements
  subscribe(callback) {
    this.subscribers.push(callback);
    return () => {
      this.subscribers = this.subscribers.filter(c => c !== callback);
    };
  }

  // Notifier les abonnés
  notifySubscribers(event) {
    this.subscribers.forEach(cb => {
      try {
        cb(event);
      } catch (e) {
        console.error('[AUDIT] Subscriber error:', e.message);
      }
    });
  }

  // ─── HEALTH CHECK ─────────────────────────────────────────────────

  // Scan et détection automatique d'erreurs
  scanSystemHealth() {
    const issues = [];

    // Check endpoints OK
    this.audit.endpoints.forEach(ep => {
      if (ep.status === 'MISSING' && ep.severity === 'high') {
        issues.push({
          type: 'missing-endpoint',
          severity: 'high',
          description: `${ep.method} ${ep.path} not implemented`,
          affectedFile: ep.file
        });
      }
    });

    // Check tasks in error
    this.audit.tasks.forEach(task => {
      if (task.status === 'error') {
        issues.push({
          type: 'task-failed',
          severity: 'high',
          description: `Task '${task.name}' failed: ${task.failureReason}`,
          affectedTask: task.id
        });
      }
    });

    return issues;
  }
}

// ─── SINGLETON ─────────────────────────────────────────────────────────────

const auditLogger = new AuditLogger();

module.exports = auditLogger;
