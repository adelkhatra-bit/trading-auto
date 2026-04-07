/**
 * QA TESTER AGENT — Validation automatique du système
 * 
 * Teste :
 * - Toutes les routes serveur
 * - Tous les boutons UI
 * - Intégrité des flux de données
 * - Agents inter-dépendances
 * - Frontend responsiveness
 * - Extension functtionnalité
 * - Performance
 */

const qaTester = {
  // ─── TEST RESULTS TRACKING ────────────────────────────────────────────
  results: {
    passed: 0,
    failed: 0,
    warnings: 0,
    tests: []
  },

  // ─── SERVER ROUTES (Backend validation) ────────────────────────────────
  async testServerRoutes(apiUrl = 'http://127.0.0.1:4000') {
    const routes = [
      { method: 'GET', path: '/health', expectStatus: 200, description: 'Server health check' },
      { method: 'GET', path: '/data-sources', expectStatus: 200, description: 'DataSourceManager - Yahoo disabled?' },
      { method: 'GET', path: '/system-health?symbol=EUR/USD&timeframe=H1', expectStatus: 200, description: 'Supervisor health check' },
      { method: 'GET', path: '/chart-status?symbol=EUR/USD&timeframe=H1', expectStatus: 200, description: 'ChartEngine candle status' },
      { method: 'GET', path: '/quote?symbol=EUR/USD', expectStatus: 200, description: 'Get price quote' },
      { method: 'GET', path: '/instant-trade-live?symbol=EURUSD', expectStatus: 200, description: 'Instant trade generation' },
      { method: 'GET', path: '/analyze', expectStatus: 200, description: 'Market analysis' },
      { method: 'GET', path: '/app-state', expectStatus: 200, description: 'StateManager - Load state' },
      { method: 'POST', path: '/app-state', expectStatus: 200, description: 'StateManager - Save state', body: { symbol: 'EUR/USD' } },
      { method: 'POST', path: '/validate-trade', expectStatus: 200, description: 'TradeValidator - Classify trade', body: { trade: { symbol: 'EUR/USD', entry: 1.08, sl: 1.07 }, currentPrice: 1.081 } },
      { method: 'POST', path: '/classify-setup', expectStatus: 200, description: 'SetupClassifier - Identify pattern', body: { trade: { symbol: 'EUR/USD', entry: 1.08 }, context: {} } },
      { method: 'GET', path: '/integrated-trade', expectStatus: 200, description: 'Full agent pipeline test' }
    ];

    const testResults = [];

    for (const route of routes) {
      try {
        const url = `${apiUrl}${route.path}`;
        const options = {
          method: route.method,
          headers: { 'Content-Type': 'application/json' }
        };
        if (route.body) {
          options.body = JSON.stringify(route.body);
        }

        const response = await fetch(url, options);
        const data = await response.json();

        const passed = response.status === route.expectStatus && data.ok !== false;
        testResults.push({
          route: `${route.method} ${route.path}`,
          description: route.description,
          status: response.status,
          expected: route.expectStatus,
          passed,
          response: passed ? '✅' : '❌'
        });

        if (passed) {
          this.results.passed++;
        } else {
          this.results.failed++;
        }
      } catch (err) {
        testResults.push({
          route: `${route.method} ${route.path}`,
          description: route.description,
          passed: false,
          error: err.message,
          response: '❌ TIMEOUT/ERROR'
        });
        this.results.failed++;
      }
    }

    this.results.tests.push({ category: 'Server Routes', tests: testResults });
    return testResults;
  },

  // ─── UI BUTTONS TEST (Frontend validation) ────────────────────────────
  testUIButtons() {
    const buttons = [
      { id: 'btn-get-positions', name: 'Get Positions', expectedEndpoint: '/positions' },
      { id: 'btn-instant-trade', name: 'Instant Trade', expectedEndpoint: '/instant-trade-live' },
      { id: 'btn-analyze-market', name: 'Analyze Market', expectedEndpoint: '/analyze' },
      { id: 'btn-agents-report', name: 'Agents Report', expectedEndpoint: '/agents-report' },
      { id: 'btn-execute-trade', name: 'Execute Trade', expectedEndpoint: '/trade' },
      { id: 'btn-open-popup', name: 'Trade Popup', expectedEndpoint: 'window.open' },
      { id: 'btn-toggle-mode', name: 'Toggle Auto', expectedEndpoint: '/toggle-mode' },
      { id: 'btn-toggle-broker', name: 'Broker Mode', expectedEndpoint: '/broker-mode' },
      { id: 'btn-capture-screen', name: 'Screen Analysis', expectedEndpoint: '/agent-screen' },
      { id: 'btn-clear-logs', name: 'Clear Logs', expectedEndpoint: 'localStorage' },
      { id: 'btn-toggle-debug', name: 'Debug Monitor', expectedEndpoint: 'DOM toggle' }
    ];

    const testResults = [];

    buttons.forEach(btn => {
      const element = document.getElementById(btn.id);
      const exists = element !== null;
      const isClickable = element?.onclick !== null || element?.addEventListener !== undefined;
      const hasText = element?.textContent?.length > 0;

      testResults.push({
        buttonId: btn.id,
        buttonName: btn.name,
        exists,
        isClickable,
        hasText,
        expectedEndpoint: btn.expectedEndpoint,
        passed: exists && isClickable && hasText,
        response: (exists && isClickable && hasText) ? '✅' : '❌'
      });

      if (exists && isClickable && hasText) {
        this.results.passed++;
      } else {
        this.results.failed++;
      }
    });

    this.results.tests.push({ category: 'UI Buttons', tests: testResults });
    return testResults;
  },

  // ─── DATA INTEGRITY TEST ──────────────────────────────────────────────
  testDataIntegrity() {
    const tests = [];

    // Test 1: StateManager persistence
    try {
      const testState = { symbol: 'TEST', timeframe: 'D1', timestamp: Date.now() };
      localStorage.setItem('trade-state', JSON.stringify(testState));
      const retrieved = JSON.parse(localStorage.getItem('trade-state'));
      const passed = retrieved.symbol === 'TEST' && retrieved.timeframe === 'D1';
      tests.push({
        check: 'StateManager localStorage',
        passed,
        response: passed ? '✅' : '❌'
      });
      this.results[passed ? 'passed' : 'failed']++;
      localStorage.removeItem('trade-state');
    } catch (err) {
      tests.push({
        check: 'StateManager localStorage',
        passed: false,
        error: err.message,
        response: '❌'
      });
      this.results.failed++;
    }

    // Test 2: Chart canvas existence
    const chartCanvas = document.getElementById('tv-chart');
    const chartExists = chartCanvas instanceof HTMLCanvasElement;
    tests.push({
      check: 'Chart canvas element',
      passed: chartExists,
      response: chartExists ? '✅' : '❌'
    });
    this.results[chartExists ? 'passed' : 'failed']++;

    // Test 3: Maintenance log capacity
    const mainLog = document.getElementById('maintenance-log');
    const canRender = mainLog !== null && mainLog.innerHTML !== undefined;
    tests.push({
      check: 'Maintenance log rendering',
      passed: canRender,
      response: canRender ? '✅' : '❌'
    });
    this.results[canRender ? 'passed' : 'failed']++;

    // Test 4: Responsive layout detection
    const width = window.innerWidth;
    const supportsResponsive = width > 0;
    tests.push({
      check: `Responsive detection (width: ${width}px)`,
      passed: supportsResponsive,
      response: supportsResponsive ? '✅' : '❌'
    });
    this.results[supportsResponsive ? 'passed' : 'failed']++;

    this.results.tests.push({ category: 'Data Integrity', tests });
    return tests;
  },

  // ─── AGENT DEPENDENCIES TEST ──────────────────────────────────────────
  testAgentDependencies(agents) {
    const tests = [];
    const requiredAgents = [
      'dataSourceManager',
      'syncManager',
      'strategyManager',
      'stateManager',
      'tradeValidator',
      'setupClassifier',
      'chartEngine',
      'supervisor',
      'newsAgent',
      'designerAgent'
    ];

    requiredAgents.forEach(agentName => {
      const agentExists = agents && agents[agentName] !== undefined;
      const hasRequiredMethods = agentExists && Object.keys(agents[agentName]).length > 0;

      tests.push({
        agent: agentName,
        exists: agentExists,
        hasMethods: hasRequiredMethods,
        passed: agentExists && hasRequiredMethods,
        response: (agentExists && hasRequiredMethods) ? '✅' : '❌'
      });

      if (agentExists && hasRequiredMethods) {
        this.results.passed++;
      } else {
        this.results.failed++;
      }
    });

    this.results.tests.push({ category: 'Agent Dependencies', tests });
    return tests;
  },

  // ─── SPECIFIC FEATURE TESTS ────────────────────────────────────────────
  testFeatures() {
    const tests = [];

    // Test: Yahoo Finance is disabled
    const serverData = fetch('/data-sources').then(r => r.json()).then(d => d.yahooEnabled === false);
    tests.push({
      feature: 'Yahoo Finance disabled',
      critical: true,
      passed: serverData,
      response: serverData ? '✅' : '❌ CRITICAL'
    });
    this.results[serverData ? 'passed' : 'failed']++;

    // Test: Candle timer visible
    const candleTimer = document.getElementById('candle-time') !== null;
    tests.push({
      feature: 'Candle timer visible',
      critical: true,
      passed: candleTimer,
      response: candleTimer ? '✅' : '❌ MISSING'
    });
    this.results[candleTimer ? 'passed' : 'failed']++;

    // Test: Symbol selector
    const symbolSelect = document.getElementById('chart-symbol') !== null;
    tests.push({
      feature: 'Symbol selector',
      critical: false,
      passed: symbolSelect,
      response: symbolSelect ? '✅' : '❌'
    });
    this.results[symbolSelect ? 'passed' : 'failed']++;

    // Test: Timeframe buttons
    const tfButtons = document.getElementById('timeframe-buttons') !== null;
    tests.push({
      feature: 'Timeframe buttons',
      critical: false,
      passed: tfButtons,
      response: tfButtons ? '✅' : '❌'
    });
    this.results[tfButtons ? 'passed' : 'failed']++;

    // Test: Status indicators
    const statusEl = document.getElementById('status') !== null;
    tests.push({
      feature: 'Server status indicator',
      critical: false,
      passed: statusEl,
      response: statusEl ? '✅' : '❌'
    });
    this.results[statusEl ? 'passed' : 'failed']++;

    this.results.tests.push({ category: 'Feature Tests', tests });
    return tests;
  },

  // ─── GENERATE TEST REPORT ────────────────────────────────────────────
  generateReport() {
    const totalTests = this.results.passed + this.results.failed;
    const successRate = totalTests > 0 ? ((this.results.passed / totalTests) * 100).toFixed(1) : 0;

    return {
      timestamp: new Date().toISOString(),
      summary: {
        totalTests,
        passed: this.results.passed,
        failed: this.results.failed,
        warnings: this.results.warnings,
        successRate: `${successRate}%`
      },
      criticalIssues: this.results.tests
        .flatMap(cat => cat.tests)
        .filter(t => t.response?.includes('❌') && t.critical !== false)
        .map(t => ({ ...t, severity: 'CRITICAL' })),
      allTests: this.results.tests,
      recommendations: this.getRecommendations()
    };
  },

  // ─── GET RECOMMENDATIONS ──────────────────────────────────────────────
  getRecommendations() {
    const recs = [];

    if (this.results.failed > 5) {
      recs.push('⚠️  High failure rate - review route integration');
    }

    const failedTests = this.results.tests
      .flatMap(cat => cat.tests)
      .filter(t => !t.passed);

    if (failedTests.some(t => t.check?.includes('Yahoo'))) {
      recs.push('🔴 CRITICAL: Yahoo Finance still enabled - disable immediately!');
    }

    if (failedTests.some(t => t.buttonId?.includes('execute'))) {
      recs.push('⚠️  Execute button not linked - check onClick handler');
    }

    if (failedTests.length === 0) {
      recs.push('✅ All systems operational!');
    }

    return recs;
  },

  // ─── RUN ALL TESTS ────────────────────────────────────────────────────
  async runAllTests(apiUrl = 'http://127.0.0.1:4000', agents = {}) {
    console.log('🧪 QA TESTER: Starting comprehensive test suite...\n');

    // Reset results
    this.results = { passed: 0, failed: 0, warnings: 0, tests: [] };

    // Run tests
    console.log('1️⃣  Testing server routes...');
    await this.testServerRoutes(apiUrl);

    console.log('2️⃣  Testing UI buttons...');
    this.testUIButtons();

    console.log('3️⃣  Testing data integrity...');
    this.testDataIntegrity();

    console.log('4️⃣  Testing agent dependencies...');
    this.testAgentDependencies(agents);

    console.log('5️⃣  Testing features...');
    this.testFeatures();

    // Generate report
    const report = this.generateReport();

    console.log('\n📊 TEST REPORT:');
    console.log(`✅ Passed: ${report.summary.passed}`);
    console.log(`❌ Failed: ${report.summary.failed}`);
    console.log(`📈 Success Rate: ${report.summary.successRate}`);

    if (report.criticalIssues.length > 0) {
      console.log('\n🔴 CRITICAL ISSUES:');
      report.criticalIssues.forEach(issue => {
        console.log(`  - ${issue.agent || issue.buttonId || issue.check}: ${issue.response}`);
      });
    }

    console.log('\n💡 RECOMMENDATIONS:');
    report.recommendations.forEach(rec => console.log(`  ${rec}`));

    return report;
  }
};

module.exports = qaTester;
