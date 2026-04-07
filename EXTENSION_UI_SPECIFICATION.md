# 🎨 EXTENSION POPUP UI — SPÉCIFICATION DÉTAILLÉE

**Date:** 2026-04-03  
**Status:** DESIGN (avant implémentation)  
**Localisation:** `public/popup.html` + `public/popup.js`  
**Approche:** Ajouter onglet "Price Settings" au popup existant (pas de page séparée)

---

## 📐 UI Structure Overview

**Current popup.html structure:**
```html
<div class="popup-tabs">
  <button class="tab-btn" data-tab="symbols">Symbols</button>
  <button class="tab-btn" data-tab="analysis">Analysis</button>
  <button class="tab-btn" data-tab="signals">Signals</button>
  <button class="tab-btn" data-tab="alerts">Alerts</button>
  ...
</div>

<div class="tab-content" id="symbols-tab">...</div>
<div class="tab-content" id="analysis-tab">...</div>
<div class="tab-content" id="signals-tab">...</div>
<div class="tab-content" id="alerts-tab">...</div>
```

**New addition:**
```html
<button class="tab-btn" data-tab="prices">Prices</button>
<div class="tab-content" id="prices-tab">...</div>
```

---

## 🎯 "Prices" Tab — Complete HTML

**Location:** Add to `public/popup.html` (after other tabs)

```html
<!-- TAB: USER REFERENCE PRICES -->
<div class="tab-content" id="prices-tab" style="display: none;">
  <div class="popup-section">
    <h2>User Reference Prices</h2>
    
    <!-- FORM: Register/Update Price -->
    <div class="price-registration-form">
      <h3>Register Price</h3>
      
      <div class="form-group">
        <label for="price-symbol-select">Symbol:</label>
        <select id="price-symbol-select" class="form-input">
          <option value="">-- Select Symbol --</option>
          <option value="XAUUSD" data-class="metals">Gold (XAUUSD)</option>
          <option value="XAGUSD" data-class="metals">Silver (XAGUSD)</option>
          <option value="EURUSD" data-class="forex">EUR/USD</option>
          <option value="GBPUSD" data-class="forex">GBP/USD</option>
          <option value="USDJPY" data-class="forex">USD/JPY</option>
          <option value="AUDUSD" data-class="forex">AUD/USD</option>
          <option value="BTCUSD" data-class="crypto">Bitcoin (BTCUSD)</option>
          <option value="ETHUSD" data-class="crypto">Ethereum (ETHUSD)</option>
          <option value="USOIL" data-class="commodities">WTI Oil (USOIL)</option>
          <option value="SPX500" data-class="indices">S&P 500 (SPX500)</option>
        </select>
      </div>
      
      <!-- System Price Display -->
      <div class="form-group system-price-display" id="system-price-display" style="display: none;">
        <label>System Price:</label>
        <div class="price-info">
          <span class="price-value" id="system-price-value">—</span>
          <span class="price-age" id="system-price-age">(fetching...)</span>
        </div>
      </div>
      
      <!-- User Price Input -->
      <div class="form-group">
        <label for="price-input">Your Reference Price:</label>
        <input 
          type="number" 
          id="price-input" 
          class="form-input" 
          placeholder="Enter price"
          step="0.01"
          min="0"
          disabled
        >
        <small class="hint">Enter the price you want to use as reference</small>
      </div>
      
      <!-- Tolerance Display (Dynamic) -->
      <div class="form-group tolerance-display" id="tolerance-display" style="display: none;">
        <div class="tolerance-info">
          <div class="tolerance-row">
            <span class="label">Divergence:</span>
            <span class="value" id="tolerance-absolute">—</span>
            (<span id="tolerance-percent">—</span>%)
          </div>
          <div class="tolerance-row">
            <span class="label">Max Allowed:</span>
            <span class="value" id="tolerance-max">±0.5%</span>
          </div>
          <div class="tolerance-row">
            <span class="label">Status:</span>
            <span class="status-badge" id="tolerance-status">—</span>
          </div>
        </div>
      </div>
      
      <!-- Action Buttons -->
      <div class="form-actions">
        <button id="register-price-btn" class="btn btn-primary" disabled>
          Register Price
        </button>
        <button id="clear-price-btn" class="btn btn-secondary" style="display: none;">
          Clear Reference
        </button>
        <button id="cancel-price-btn" class="btn btn-cancel">
          Cancel
        </button>
      </div>
      
      <!-- Validation Messages -->
      <div class="validation-messages">
        <div id="tolerance-warning" class="message message-warning" style="display: none;">
          <strong>⚠️ Price Divergence Warning</strong>
          <p id="warning-text"></p>
          <div class="warning-options">
            <button id="btn-use-system" class="option-btn">Use System Price Instead</button>
            <button id="btn-force-override" class="option-btn btn-override">Force This Price</button>
          </div>
        </div>
        
        <div id="tolerance-error" class="message message-error" style="display: none;">
          <strong>❌ Error</strong>
          <p id="error-text"></p>
        </div>
        
        <div id="tolerance-success" class="message message-success" style="display: none;">
          <strong>✓ Success</strong>
          <p id="success-text"></p>
        </div>
      </div>
    </div>
    
    <!-- REGISTERED PRICES LIST -->
    <div class="registered-prices-list">
      <h3>Registered Prices</h3>
      <div id="prices-list-container" class="prices-list" style="display: none;">
        <!-- Dynamic: Populated by JS -->
      </div>
      <div id="no-prices-message" class="empty-state">
        <p>No user reference prices registered yet.</p>
        <p class="hint">Select a symbol and register your first price above.</p>
      </div>
    </div>
    
  </div>
</div>

<!-- CSS Styling (add to popup.html style section) -->
<style>
  /* Price Settings Tab */
  .popup-section {
    padding: 12px;
    margin-bottom: 10px;
  }
  
  .popup-section h2 {
    font-size: 16px;
    font-weight: 600;
    margin: 0 0 12px 0;
    color: #fff;
  }
  
  .popup-section h3 {
    font-size: 13px;
    font-weight: 500;
    margin: 12px 0 8px 0;
    color: #ddd;
  }
  
  /* Form Layout */
  .price-registration-form {
    background: #1e1e1e;
    border: 1px solid #333;
    border-radius: 6px;
    padding: 10px;
    margin-bottom: 15px;
  }
  
  .form-group {
    margin-bottom: 10px;
    display: flex;
    flex-direction: column;
  }
  
  .form-group label {
    font-size: 12px;
    font-weight: 500;
    color: #aaa;
    margin-bottom: 4px;
  }
  
  .form-input {
    padding: 6px 8px;
    background: #2d2d2d;
    border: 1px solid #444;
    border-radius: 4px;
    color: #fff;
    font-size: 12px;
    font-family: 'Courier New', monospace;
  }
  
  .form-input:disabled {
    background: #1a1a1a;
    color: #666;
    cursor: not-allowed;
  }
  
  .form-input:focus {
    outline: none;
    border-color: #4a9eff;
    box-shadow: 0 0 4px rgba(74, 158, 255, 0.3);
  }
  
  .hint {
    font-size: 11px;
    color: #666;
    margin-top: 2px;
    font-style: italic;
  }
  
  /* System Price Display */
  .system-price-display {
    background: #252525;
    padding: 8px;
    border-left: 3px solid #666;
    border-radius: 3px;
  }
  
  .price-info {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  
  .price-value {
    font-size: 14px;
    font-weight: 600;
    color: #4a9eff;
    font-family: 'Courier New', monospace;
  }
  
  .price-age {
    font-size: 11px;
    color: #888;
  }
  
  /* Tolerance Display */
  .tolerance-display {
    background: #252525;
    padding: 8px;
    border-radius: 3px;
    border-left: 3px solid #666;
  }
  
  .tolerance-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  
  .tolerance-row {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
  }
  
  .tolerance-row .label {
    color: #888;
    flex: 1;
  }
  
  .tolerance-row .value {
    color: #fff;
    font-weight: 500;
    font-family: 'Courier New', monospace;
  }
  
  .status-badge {
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 11px;
    font-weight: 600;
  }
  
  .status-badge.ok {
    background: rgba(76, 175, 80, 0.3);
    color: #4caf50;
  }
  
  .status-badge.warning {
    background: rgba(255, 152, 0, 0.3);
    color: #ff9800;
  }
  
  .status-badge.error {
    background: rgba(244, 67, 54, 0.3);
    color: #f44336;
  }
  
  /* Buttons */
  .form-actions {
    display: flex;
    gap: 6px;
    margin: 12px 0 8px 0;
  }
  
  .btn {
    flex: 1;
    padding: 6px 8px;
    border: none;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .btn-primary {
    background: #4a9eff;
    color: #fff;
  }
  
  .btn-primary:hover:not(:disabled) {
    background: #2a7edf;
  }
  
  .btn-primary:disabled {
    background: #333;
    color: #666;
    cursor: not-allowed;
  }
  
  .btn-secondary {
    background: #ff6b6b;
    color: #fff;
  }
  
  .btn-secondary:hover {
    background: #ff5252;
  }
  
  .btn-cancel {
    background: #333;
    color: #aaa;
  }
  
  .btn-cancel:hover {
    background: #444;
  }
  
  /* Messages */
  .validation-messages {
    margin: 8px 0;
  }
  
  .message {
    padding: 8px;
    border-radius: 4px;
    font-size: 12px;
    margin-bottom: 6px;
    display: none;
  }
  
  .message strong {
    display: block;
    margin-bottom: 4px;
  }
  
  .message p {
    margin: 0;
    line-height: 1.4;
  }
  
  .message-warning {
    background: rgba(255, 152, 0, 0.1);
    border: 1px solid #ff9800;
    color: #ffb74d;
  }
  
  .message-error {
    background: rgba(244, 67, 54, 0.1);
    border: 1px solid #f44336;
    color: #ef5350;
  }
  
  .message-success {
    background: rgba(76, 175, 80, 0.1);
    border: 1px solid #4caf50;
    color: #66bb6a;
  }
  
  .warning-options,
  .error-options {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-top: 6px;
  }
  
  .option-btn {
    padding: 4px 8px;
    border: 1px solid #ff9800;
    background: transparent;
    color: #ff9800;
    border-radius: 3px;
    cursor: pointer;
    font-size: 11px;
    transition: all 0.2s;
  }
  
  .option-btn:hover {
    background: rgba(255, 152, 0, 0.1);
  }
  
  .option-btn.btn-override {
    border-color: #f44336;
    color: #f44336;
  }
  
  .option-btn.btn-override:hover {
    background: rgba(244, 67, 54, 0.1);
  }
  
  /* Registered Prices List */
  .registered-prices-list {
    border-top: 1px solid #333;
    padding-top: 12px;
    margin-top: 12px;
  }
  
  .registered-prices-list h3 {
    margin-top: 0;
  }
  
  .prices-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  
  .price-item {
    background: #252525;
    border: 1px solid #333;
    border-radius: 4px;
    padding: 8px;
    font-size: 12px;
  }
  
  .price-item-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  
  .price-item-symbol {
    font-weight: 600;
    color: #4a9eff;
  }
  
  .price-item-status {
    font-size: 11px;
    padding: 2px 6px;
    border-radius: 3px;
    background: rgba(76, 175, 80, 0.2);
    color: #4caf50;
  }
  
  .price-item-status.warning {
    background: rgba(255, 152, 0, 0.2);
    color: #ff9800;
  }
  
  .price-item-content {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    font-family: 'Courier New', monospace;
    color: #888;
    margin-bottom: 6px;
  }
  
  .price-item-row {
    display: flex;
    justify-content: space-between;
  }
  
  .price-item-label {
    color: #666;
  }
  
  .price-item-value {
    color: #fff;
    font-weight: 500;
  }
  
  .price-item-actions {
    display: flex;
    gap: 4px;
    justify-content: flex-end;
  }
  
  .price-item-btn {
    padding: 3px 6px;
    border: 1px solid #444;
    background: transparent;
    color: #888;
    border-radius: 2px;
    cursor: pointer;
    font-size: 10px;
    transition: all 0.2s;
  }
  
  .price-item-btn:hover {
    border-color: #666;
    color: #fff;
  }
  
  .price-item-btn.delete:hover {
    border-color: #f44336;
    color: #f44336;
  }
  
  .empty-state {
    text-align: center;
    padding: 20px 10px;
    color: #666;
    font-size: 12px;
  }
  
  .empty-state p {
    margin: 4px 0;
  }
  
  .empty-state .hint {
    font-size: 11px;
    color: #555;
  }
</style>
```

---

## 🔧 JavaScript Logic (popup.js)

**Add to `public/popup.js`:**

```javascript
/**
 * User Reference Price Management
 * ================================
 * Handles register, update, clear of user reference prices
 */

class PriceManager {
  constructor() {
    this.currentSymbol = null;
    this.systemPrice = null;
    this.userPrice = null;
    this.toleranceRules = {
      'XAUUSD': 0.5,
      'XAGUSD': 0.5,
      'EURUSD': 0.1,
      'GBPUSD': 0.1,
      'USDJPY': 0.1,
      'AUDUSD': 0.1,
      'NZDUSD': 0.1,
      'BTCUSD': 2.0,
      'ETHUSD': 2.0,
      'USOIL': 0.8,
      'UKOIL': 0.8,
      'SPX500': 0.3,
      'US100': 0.3,
      'default': 0.5
    };
  }

  /**
   * Initialize event listeners
   */
  init() {
    this.attachSymbolChangeListener();
    this.attachPriceInputListener();
    this.attachButtonListeners();
    this.loadAndDisplayPrices();
  }

  /**
   * When user selects a symbol
   */
  attachSymbolChangeListener() {
    const symbolSelect = document.getElementById('price-symbol-select');
    if (!symbolSelect) return;

    symbolSelect.addEventListener('change', async (e) => {
      const canonical = e.target.value;
      if (!canonical) {
        this.resetForm();
        return;
      }

      this.currentSymbol = canonical;
      await this.loadSymbolData(canonical);
    });
  }

  /**
   * Fetch system price for selected symbol
   */
  async loadSymbolData(canonical) {
    try {
      const response = await fetch(`/api/user-reference/${canonical}`, {
        method: 'GET'
      });

      const data = await response.json();

      if (response.ok) {
        // User reference exists
        this.displayExistingReference(data);
      } else {
        // User reference doesn't exist, show system price
        this.displaySystemPrice(data.fallback || null);
      }
    } catch (error) {
      console.error('Error loading symbol data:', error);
      this.showError('Failed to load symbol data');
      this.disableForm();
    }
  }

  /**
   * Display system price when no user reference exists
   */
  displaySystemPrice(fallback) {
    if (!fallback) {
      this.showError('System price not available for this symbol');
      this.disableForm();
      return;
    }

    const systemDisplay = document.getElementById('system-price-display');
    const systemValue = document.getElementById('system-price-value');
    const systemAge = document.getElementById('system-price-age');
    const priceInput = document.getElementById('price-input');
    const registerBtn = document.getElementById('register-price-btn');
    const clearBtn = document.getElementById('clear-price-btn');

    systemDisplay.style.display = 'flex';
    systemValue.textContent = fallback.price.toFixed(4);
    
    const ageMs = Date.now() - fallback.timestamp;
    const ageSec = Math.floor(ageMs / 1000);
    systemAge.textContent = `${ageSec}s ago`;

    this.systemPrice = fallback.price;
    priceInput.disabled = false;
    registerBtn.disabled = true;
    clearBtn.style.display = 'none';

    // Hide tolerance initially
    document.getElementById('tolerance-display').style.display = 'none';
  }

  /**
   * Display existing user reference
   */
  displayExistingReference(data) {
    const systemDisplay = document.getElementById('system-price-display');
    const systemValue = document.getElementById('system-price-value');
    const systemAge = document.getElementById('system-price-age');
    const priceInput = document.getElementById('price-input');
    const registerBtn = document.getElementById('register-price-btn');
    const clearBtn = document.getElementById('clear-price-btn');

    const userRef = data.userReference;
    const systemRef = data.systemPrice;

    systemDisplay.style.display = 'flex';
    systemValue.textContent = systemRef.price.toFixed(4);
    
    const ageMs = Date.now() - systemRef.timestamp;
    const ageSec = Math.floor(ageMs / 1000);
    systemAge.textContent = `${ageSec}s ago`;

    this.systemPrice = systemRef.price;
    this.userPrice = userRef.price;

    priceInput.value = userRef.price.toFixed(4);
    priceInput.disabled = false;
    registerBtn.disabled = true;
    clearBtn.style.display = 'inline-block';

    // Show tolerance
    this.displayTolerance(userRef.price, systemRef.price);
  }

  /**
   * When user enters/modifies price
   */
  attachPriceInputListener() {
    const priceInput = document.getElementById('price-input');
    if (!priceInput) return;

    priceInput.addEventListener('input', () => {
      const value = parseFloat(priceInput.value);

      if (!value || value <= 0 || !this.systemPrice) {
        document.getElementById('register-price-btn').disabled = true;
        document.getElementById('tolerance-display').style.display = 'none';
        return;
      }

      this.displayTolerance(value, this.systemPrice);
      document.getElementById('register-price-btn').disabled = false;
    });
  }

  /**
   * Display tolerance info
   */
  displayTolerance(userPrice, systemPrice) {
    const toleranceDisplay = document.getElementById('tolerance-display');
    const absolute = Math.abs(userPrice - systemPrice);
    const percent = (absolute / systemPrice) * 100;
    const maxAllowed = this.toleranceRules[this.currentSymbol] || this.toleranceRules['default'];
    const withinLimit = percent <= maxAllowed;

    document.getElementById('tolerance-absolute').textContent = absolute.toFixed(4);
    document.getElementById('tolerance-percent').textContent = percent.toFixed(4);
    document.getElementById('tolerance-max').textContent = `±${maxAllowed}%`;

    const statusBadge = document.getElementById('tolerance-status');
    if (withinLimit) {
      statusBadge.textContent = `✓ OK (${percent.toFixed(4)}% < ±${maxAllowed}%)`;
      statusBadge.className = 'status-badge ok';
    } else {
      statusBadge.textContent = `⚠️ WARNING (${percent.toFixed(4)}% > ±${maxAllowed}%)`;
      statusBadge.className = 'status-badge warning';
    }

    toleranceDisplay.style.display = 'block';
  }

  /**
   * Button event listeners
   */
  attachButtonListeners() {
    const registerBtn = document.getElementById('register-price-btn');
    const clearBtn = document.getElementById('clear-price-btn');
    const cancelBtn = document.getElementById('cancel-price-btn');
    const useSystemBtn = document.getElementById('btn-use-system');
    const forceOverrideBtn = document.getElementById('btn-force-override');

    if (registerBtn) {
      registerBtn.addEventListener('click', () => this.registerPrice());
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', () => this.clearPrice());
    }

    if (cancelBtn) {
      cancelBtn.addEventListener('click', () => this.cancelForm());
    }

    if (useSystemBtn) {
      useSystemBtn.addEventListener('click', () => this.useSystemPrice());
    }

    if (forceOverrideBtn) {
      forceOverrideBtn.addEventListener('click', () => this.registerPrice(true));
    }
  }

  /**
   * Register or update user price
   */
  async registerPrice(forceOverride = false) {
    const priceInput = document.getElementById('price-input');
    const userPrice = parseFloat(priceInput.value);

    if (!this.currentSymbol || !userPrice || userPrice <= 0) {
      this.showError('Invalid input');
      return;
    }

    try {
      const response = await fetch('/api/user-reference', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          canonical: this.currentSymbol,
          userPrice: userPrice,
          force_override: forceOverride
        })
      });

      const data = await response.json();

      if (!data.ok) {
        // Tolerance exceeded
        if (data.error.includes('divergence exceeds tolerance')) {
          this.showToleranceWarning(data);
        } else {
          this.showError(data.error);
        }
        return;
      }

      // Success
      this.showSuccess(`Price registered: ${userPrice.toFixed(4)}`);
      this.hideMessageBox();
      this.loadAndDisplayPrices();
      this.resetForm();

    } catch (error) {
      console.error('Error registering price:', error);
      this.showError('Failed to register price');
    }
  }

  /**
   * Show tolerance warning with options
   */
  showToleranceWarning(data) {
    const warningBox = document.getElementById('tolerance-warning');
    const warningText = document.getElementById('warning-text');

    const divergence = data.details.divergence;
    const tolerance = data.tolerance;

    warningText.innerHTML = `
      Price diverges <strong>${divergence.percent.toFixed(4)}%</strong> 
      from system price (tolerance: ±${tolerance}%).
      <br><br>
      System: ${divergence.system_price.toFixed(4)}<br>
      Your price: ${divergence.user_price.toFixed(4)}<br>
      Difference: ${divergence.absolute.toFixed(4)}
    `;

    this.hideMessageBox();
    warningBox.style.display = 'block';
  }

  /**
   * Use system price instead
   */
  useSystemPrice() {
    const priceInput = document.getElementById('price-input');
    priceInput.value = this.systemPrice.toFixed(4);
    this.hideMessageBox();
    document.getElementById('tolerance-display').style.display = 'none';
    document.getElementById('register-price-btn').disabled = true;
  }

  /**
   * Clear user reference (revert to system)
   */
  async clearPrice() {
    if (!this.currentSymbol) return;

    if (!confirm(`Clear user reference for ${this.currentSymbol}?`)) {
      return;
    }

    try {
      const response = await fetch(`/api/user-reference/${this.currentSymbol}`, {
        method: 'DELETE'
      });

      const data = await response.json();

      if (!data.ok) {
        this.showError(data.message || 'Failed to clear price');
        return;
      }

      this.showSuccess(`Cleared ${this.currentSymbol}. Using system price.`);
      this.hideMessageBox();
      this.resetForm();
      this.loadAndDisplayPrices();

    } catch (error) {
      console.error('Error clearing price:', error);
      this.showError('Failed to clear price');
    }
  }

  /**
   * Cancel form and reset
   */
  cancelForm() {
    this.resetForm();
    this.hideMessageBox();
  }

  /**
   * Reset form to initial state
   */
  resetForm() {
    document.getElementById('price-symbol-select').value = '';
    document.getElementById('price-input').value = '';
    document.getElementById('price-input').disabled = true;
    document.getElementById('register-price-btn').disabled = true;
    document.getElementById('clear-price-btn').style.display = 'none';
    document.getElementById('system-price-display').style.display = 'none';
    document.getElementById('tolerance-display').style.display = 'none';
    
    this.currentSymbol = null;
    this.systemPrice = null;
    this.userPrice = null;
  }

  /**
   * Disable entire form
   */
  disableForm() {
    document.getElementById('price-symbol-select').disabled = true;
    document.getElementById('price-input').disabled = true;
    document.getElementById('register-price-btn').disabled = true;
  }

  /**
   * Show/hide messages
   */
  showError(message) {
    const errorBox = document.getElementById('tolerance-error');
    const errorText = document.getElementById('error-text');
    errorText.textContent = message;
    this.hideMessageBox();
    errorBox.style.display = 'block';
  }

  showSuccess(message) {
    const successBox = document.getElementById('tolerance-success');
    const successText = document.getElementById('success-text');
    successText.textContent = message;
    this.hideMessageBox();
    successBox.style.display = 'block';
  }

  hideMessageBox() {
    document.getElementById('tolerance-warning').style.display = 'none';
    document.getElementById('tolerance-error').style.display = 'none';
    document.getElementById('tolerance-success').style.display = 'none';
  }

  /**
   * Load and display all registered user prices
   */
  async loadAndDisplayPrices() {
    try {
      const response = await fetch('/api/user-references');
      const data = await response.json();

      if (!data.ok || data.count === 0) {
        document.getElementById('prices-list-container').style.display = 'none';
        document.getElementById('no-prices-message').style.display = 'block';
        return;
      }

      this.renderPricesList(data.userReferences);

    } catch (error) {
      console.error('Error loading prices:', error);
    }
  }

  /**
   * Render list of registered prices
   */
  renderPricesList(prices) {
    const container = document.getElementById('prices-list-container');
    const noMessage = document.getElementById('no-prices-message');

    if (prices.length === 0) {
      container.style.display = 'none';
      noMessage.style.display = 'block';
      return;
    }

    container.style.display = 'flex';
    noMessage.style.display = 'none';

    container.innerHTML = prices.map(price => `
      <div class="price-item">
        <div class="price-item-header">
          <span class="price-item-symbol">${price.canonical}</span>
          <span class="price-item-status ${price.tolerance.withinLimit ? '' : 'warning'}">
            ${price.tolerance.withinLimit ? '✓ OK' : '⚠️ WARNING'}
          </span>
        </div>
        
        <div class="price-item-content">
          <div class="price-item-row">
            <span class="price-item-label">User:</span>
            <span class="price-item-value">${price.userPrice.toFixed(4)}</span>
          </div>
          <div class="price-item-row">
            <span class="price-item-label">System:</span>
            <span class="price-item-value">${price.systemPrice.toFixed(4)}</span>
          </div>
          <div class="price-item-row">
            <span class="price-item-label">Diff:</span>
            <span class="price-item-value">${price.tolerance.percent.toFixed(4)}%</span>
          </div>
          <div class="price-item-row">
            <span class="price-item-label">Max:</span>
            <span class="price-item-value">±${price.tolerance.maxAllowed}%</span>
          </div>
        </div>
        
        <div class="price-item-actions">
          <button class="price-item-btn delete" onclick="priceManager.editPrice('${price.canonical}')">
            Edit
          </button>
          <button class="price-item-btn delete" onclick="priceManager.deletePriceItem('${price.canonical}')">
            Delete
          </button>
        </div>
      </div>
    `).join('');
  }

  /**
   * Edit existing price
   */
  editPrice(canonical) {
    document.getElementById('price-symbol-select').value = canonical;
    document.getElementById('price-symbol-select').dispatchEvent(new Event('change'));
  }

  /**
   * Delete price item (from list)
   */
  deletePriceItem(canonical) {
    if (confirm(`Delete user reference for ${canonical}?`)) {
      this.currentSymbol = canonical;
      this.clearPrice();
    }
  }
}

// Initialize on tab show
function initPricesTab() {
  if (typeof priceManager === 'undefined') {
    window.priceManager = new PriceManager();
    window.priceManager.init();
  }
}

// Attach to tab click event
document.addEventListener('DOMContentLoaded', () => {
  const pricesTabBtn = document.querySelector('[data-tab="prices"]');
  if (pricesTabBtn) {
    pricesTabBtn.addEventListener('click', initPricesTab);
  }
});
```

---

## 🎬 UI Flow Diagram

```
User opens Extension Popup
    ↓
Clicks "Prices" tab
    ↓
priceManager.init() runs
    ↓
Selects symbol from dropdown
    ↓
priceManager.loadSymbolData(XAUUSD)
    ├─ Fetch /api/user-reference/XAUUSD
    ├─ Display system price 2375.30
    └─ Enable price input
    ↓
User enters reference price: 2375.50
    ↓
On input change:
    ├─ Calculate tolerance: 0.0085%
    ├─ Display status: "✓ OK (0.0085% < ±0.5%)"
    └─ Enable "Register Price" button
    ↓
User clicks "Register Price"
    ↓
POST /api/user-reference
    ├─ { canonical: XAUUSD, userPrice: 2375.50 }
    ↓
Server validates tolerance
    ├─ If OK → Return 200, show success message
    └─ If exceeds → Return 400, show warning with options
    ↓
Reload registered prices list
    ├─ Fetch /api/user-references
    └─ Display all registered prices
    ↓
User sees registered price in list below form
    ├─ Can click "Edit" to modify
    └─ Can click "Delete" to clear
```

---

## ✅ Implementation Checklist

- [ ] Add HTML "Prices" tab to popup.html
- [ ] Add CSS styling for price form
- [ ] Add PriceManager JavaScript class
- [ ] Implement symbol selection logic
- [ ] Implement price input + tolerance display
- [ ] Implement register/update functionality
- [ ] Implement clear/delete functionality
- [ ] Implement registered prices list display
- [ ] Test with server endpoints
- [ ] Test tolerance validation (OK, warning, error cases)
- [ ] Test persistence (reload popup, prices still there)

---

## 📝 Integration Points

**With server.js:**
- POST /api/user-reference
- GET /api/user-reference/:canonical
- DELETE /api/user-reference/:canonical
- GET /api/user-references

**With symbol-preferences.js:**
- Uses registerUserReference()
- Uses updateUserReference()
- Uses clearUserReference()
- Uses getAllUserReferences()

**With data-source-manager.js:**
- Agent automatically uses user prices (no extension changes needed)
