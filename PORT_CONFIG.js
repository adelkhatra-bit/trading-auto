/**
 * ⚠️ PORT CONFIGURATION - AVOID CONFLICTS
 * 
 * DO NOT CHANGE THESE PORTS WITHOUT COORDINATING
 * This project uses DIFFERENT ports to avoid conflicts with other services
 * 
 * ✅ TRADING AUTO PROJECT (this folder)
 *    - Studio Node.js Server:  PORT 4000 (single environment)
 *    - Python Bridge MT5:      DISABLED in single-environment mode
 * 
 * ❌ ALL OTHER SERVICES
 *    - Any legacy secondary port is forbidden in this mode
 * 
 * ═══════════════════════════════════════════════════════════
 */

// Configuration object for easy import
const PORT_CONFIG = {
  // Node.js Express server running Studio HTML
  STUDIO_SERVER_PORT: 4000,
  STUDIO_URL: 'http://127.0.0.1:4000/studio/',
  
  // Legacy bridge endpoints are intentionally disabled
  BRIDGE_PORT: null,
  BRIDGE_URL: null,
  
  // Dashboard endpoint
  DASHBOARD_URL: 'http://127.0.0.1:4000/dashboard',
  
  // Health check
  HEALTH_URL: 'http://127.0.0.1:4000/healthz',
  
  // Data endpoint
  DATA_URL: 'http://127.0.0.1:4000/data',
};

// For Node.js require()
if (typeof module !== 'undefined' && module.exports) {
  module.exports = PORT_CONFIG;
}

// For browser console debugging
if (typeof window !== 'undefined') {
  window.PORT_CONFIG = PORT_CONFIG;
}

console.log('✅ PORT_CONFIG loaded:', PORT_CONFIG);
