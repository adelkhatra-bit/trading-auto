/**
 * Agent Bus — Central registry and messaging system for all agents
 * Role: Agent discovery, registration, and inter-agent communication
 * 
 * Features:
 * - registerAgent(name, metadata) — Register an agent
 * - sendMessage(fromAgent, toAgent, message) — Send message between agents
 * - getAgent(name) — Retrieve agent metadata
 * - subscribe(agentName, callback) — Listen for messages sent to agent
 * - getRegistry() — Return all registered agents
 */

class AgentBus {
  constructor() {
    this.agents = {};        // Registry: {agentName: {metadata}}
    this.subscribers = {};   // Message listeners: {agentName: [callbacks]}
    this.messageQueue = [];  // Queue for messages if subscriber not ready
    this.maxQueueSize = 1000;
  }

  /**
   * Register an agent in the bus
   * @param {string} name - Agent name (e.g. "orchestrator", "test-agent")
   * @param {object} metadata - Agent info (role, file, status, etc)
   */
  registerAgent(name, metadata = {}) {
    if (!name || typeof name !== 'string') {
      throw new Error('Agent name must be a non-empty string');
    }

    this.agents[name] = {
      name,
      registeredAt: new Date().toISOString(),
      ...metadata
    };

    if (!this.subscribers[name]) {
      this.subscribers[name] = [];
    }

    console.log(`✅ Agent registered: ${name}`);
    return this.agents[name];
  }

  /**
   * Send a message from one agent to another
   * @param {string} fromAgent - Sender agent name
   * @param {string} toAgent - Recipient agent name
   * @param {string} messageType - Type of message (e.g. "request", "response", "alert")
   * @param {object} data - Message payload
   */
  sendMessage(fromAgent, toAgent, messageType, data = {}) {
    if (!fromAgent || !toAgent || !messageType) {
      throw new Error('fromAgent, toAgent, and messageType are required');
    }

    const message = {
      timestamp: new Date().toISOString(),
      from: fromAgent,
      to: toAgent,
      type: messageType,
      data
    };

    // Deliver immediately if subscribers exist
    if (this.subscribers[toAgent] && this.subscribers[toAgent].length > 0) {
      this.subscribers[toAgent].forEach(callback => {
        try {
          callback(message);
        } catch (err) {
          console.error(`❌ Subscriber error for ${toAgent}:`, err.message);
        }
      });
    } else {
      // Queue message if no subscribers yet
      this.messageQueue.push(message);
      // Prevent queue explosion
      if (this.messageQueue.length > this.maxQueueSize) {
        this.messageQueue = this.messageQueue.slice(-this.maxQueueSize);
      }
    }

    return message;
  }

  /**
   * Subscribe to messages for an agent
   * @param {string} agentName - Agent to listen for
   * @param {function} callback - Function to call when message arrives
   */
  subscribe(agentName, callback) {
    if (!agentName || typeof callback !== 'function') {
      throw new Error('agentName and callback function are required');
    }

    if (!this.subscribers[agentName]) {
      this.subscribers[agentName] = [];
    }

    this.subscribers[agentName].push(callback);

    // Deliver queued messages to this new subscriber
    const queue = this.messageQueue.filter(msg => msg.to === agentName);
    queue.forEach(msg => {
      try {
        callback(msg);
      } catch (err) {
        console.error(`❌ Error delivering queued message to ${agentName}:`, err.message);
      }
    });

    // Remove delivered messages from queue
    this.messageQueue = this.messageQueue.filter(msg => msg.to !== agentName);

    console.log(`✅ Subscriber added for ${agentName}`);
    return () => {
      // Return unsubscribe function
      const idx = this.subscribers[agentName].indexOf(callback);
      if (idx > -1) this.subscribers[agentName].splice(idx, 1);
      console.log(`✅ Unsubscribed from ${agentName}`);
    };
  }

  /**
   * Get agent metadata
   * @param {string} name - Agent name
   */
  getAgent(name) {
    return this.agents[name] || null;
  }

  /**
   * Get all registered agents
   */
  getRegistry() {
    return {
      timestamp: new Date().toISOString(),
      agents: Object.values(this.agents),
      totalAgents: Object.keys(this.agents).length,
      queuedMessages: this.messageQueue.length
    };
  }

  /**
   * Get pending messages (for debugging)
   */
  getPendingMessages() {
    return this.messageQueue;
  }

  /**
   * Clear message queue (careful!)
   */
  clearQueue() {
    const count = this.messageQueue.length;
    this.messageQueue = [];
    console.log(`✅ Cleared ${count} queued messages`);
    return count;
  }
}

// Singleton instance
const agentBus = new AgentBus();

module.exports = agentBus;
