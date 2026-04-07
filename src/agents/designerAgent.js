/**
 * DESIGNER AGENT — UI/UX Optimization
 * 
 * Responsable de :
 * - Layout responsif
 * - Hiérarchie visuelle
 * - Optimisation de la lisibilité
 * - Mise en avant des éléments critiques
 * - Design cohérent studio + extension
 * - Accessibility
 * - Performance visuelle
 */

const designerAgent = {
  // ─── RESPONSIVE BREAKPOINTS ───────────────────────────────────────────
  BREAKPOINTS: {
    MOBILE: 480,
    TABLET: 768,
    LAPTOP: 1024,
    DESKTOP: 1440,
    ULTRAWIDE: 1920
  },

  // ─── COLOR SCHEME (Professional Trading) ───────────────────────────────
  COLORS: {
    primary: '#1e40af',      // Strong blue
    success: '#10b981',      // Green (bullish)
    danger: '#ef4444',       // Red (bearish)
    warning: '#f59e0b',      // Orange
    neutral: '#64748b',      // Gray
    background: '#0f172a',   // Dark blue
    surface: '#1e293b',      // Slightly lighter
    border: '#334155',       // Border gray
    text: '#e0f2fe',         // Light text
    textMuted: '#94a3b8'     // Muted text
  },

  // ─── TYPOGRAPHY (Hierarchy) ───────────────────────────────────────────
  TYPOGRAPHY: {
    h1: { size: '2rem', weight: 700, lineHeight: 1.2 },
    h2: { size: '1.5rem', weight: 700, lineHeight: 1.3 },
    h3: { size: '1.1rem', weight: 600, lineHeight: 1.4 },
    body: { size: '0.95rem', weight: 400, lineHeight: 1.6 },
    small: { size: '0.85rem', weight: 400, lineHeight: 1.5 },
    micro: { size: '0.75rem', weight: 400, lineHeight: 1.4 }
  },

  // ─── LAYOUT RULES ─────────────────────────────────────────────────────
  getLayoutForDevice(width) {
    if (width < this.BREAKPOINTS.MOBILE) {
      return { type: 'MOBILE', cols: 1, gaps: '0.75rem' };
    } else if (width < this.BREAKPOINTS.TABLET) {
      return { type: 'TABLET_PORTRAIT', cols: 1, gaps: '1rem' };
    } else if (width < this.BREAKPOINTS.LAPTOP) {
      return { type: 'TABLET_LANDSCAPE', cols: 2, gaps: '1.25rem' };
    } else if (width < this.BREAKPOINTS.DESKTOP) {
      return { type: 'LAPTOP', cols: 3, gaps: '1.5rem' };
    } else {
      return { type: 'DESKTOP', cols: 4, gaps: '1.75rem' };
    }
  },

  // ─── CRITICAL INFO FIRST (Above the fold) ──────────────────────────────
  getCriticalZoneLayout() {
    return {
      priority: ['ACTIVE_SYMBOL', 'TIMEFRAME', 'LIVE_PRICE', 'CANDLE_TIMER', 'SIGNAL_STATUS'],
      layout: {
        ACTIVE_SYMBOL: {
          prominence: 'VERY_HIGH',
          size: 'LARGE',
          position: 'TOP_LEFT',
          refreshRate: '1s'
        },
        TIMEFRAME: {
          prominence: 'VERY_HIGH',
          size: 'MEDIUM',
          position: 'TOP_CENTER',
          refreshRate: '1s'
        },
        LIVE_PRICE: {
          prominence: 'CRITICAL',
          size: 'XLARGE',
          position: 'TOP_RIGHT',
          refreshRate: 'LIVE',
          highlight: true
        },
        CANDLE_TIMER: {
          prominence: 'CRITICAL',
          size: 'MEDIUM',
          position: 'CENTER',
          refreshRate: '100ms',
          animate: true,
          color: 'WARNING_IF_LOW'
        },
        SIGNAL_STATUS: {
          prominence: 'VERY_HIGH',
          size: 'LARGE',
          position: 'MAIN',
          refreshRate: 'EVENT',
          highlight: true
        }
      }
    };
  },

  // ─── CARD DESIGN SYSTEM ───────────────────────────────────────────────
  getCardDesign(type) {
    const designs = {
      HERO: {
        padding: '1.5rem',
        borderRadius: '0.75rem',
        border: '2px solid #2563eb',
        background: 'linear-gradient(135deg, rgba(15,23,42,0.9), rgba(30,58,95,0.9))',
        shadow: 'lg',
        minHeight: '200px'
      },
      SIGNAL: {
        padding: '1.25rem',
        borderRadius: '0.75rem',
        border: '2px solid #10b981',
        background: 'rgba(15,23,42,0.8)',
        shadow: 'md',
        animation: 'pulse-highlight 2s'
      },
      STATUS: {
        padding: '1rem',
        borderRadius: '0.5rem',
        border: '1px solid #334155',
        background: 'rgba(15,23,42,0.6)',
        shadow: 'sm'
      },
      WARNING: {
        padding: '1rem',
        borderRadius: '0.5rem',
        border: '2px solid #f59e0b',
        background: 'rgba(245,158,11,0.1)',
        shadow: 'md',
        animation: 'blink 1s infinite'
      }
    };
    return designs[type];
  },

  // ─── BUTTON HIERARCHY ─────────────────────────────────────────────────
  getButtonDesign(category, state = 'normal') {
    const states = {
      normal: { opacity: 1, transform: 'scale(1)' },
      hover: { opacity: 0.9, transform: 'scale(1.02)' },
      active: { opacity: 1, transform: 'scale(0.98)' },
      disabled: { opacity: 0.5, transform: 'scale(1)' }
    };

    const designs = {
      PRIMARY: {
        background: '#1e40af',
        text: '#ffffff',
        border: '1px solid #1e3a8a',
        padding: '0.75rem 1.25rem',
        fontSize: '0.95rem',
        weight: 600
      },
      SECONDARY: {
        background: '#334155',
        text: '#e0f2fe',
        border: '1px solid #475569',
        padding: '0.75rem 1.25rem',
        fontSize: '0.9rem',
        weight: 500
      },
      DANGER: {
        background: '#dc2626',
        text: '#ffffff',
        border: '1px solid #b91c1c',
        padding: '0.75rem 1.25rem',
        fontSize: '0.9rem',
        weight: 600
      },
      SUCCESS: {
        background: '#059669',
        text: '#ffffff',
        border: '1px solid #047857',
        padding: '0.75rem 1.25rem',
        fontSize: '0.95rem',
        weight: 600
      }
    };

    return {
      ...designs[category],
      state: states[state]
    };
  },

  // ─── RESPONSIVE GRID SYSTEM ───────────────────────────────────────────
  getResponsiveGrid(itemCount, maxCols = 4) {
    return {
      small: { cols: 1, gap: '0.75rem' },
      medium: { cols: Math.min(2, itemCount), gap: '1rem' },
      large: { cols: Math.min(3, itemCount, maxCols), gap: '1.25rem' },
      xlarge: { cols: Math.min(4, itemCount, maxCols), gap: '1.5rem' }
    };
  },

  // ─── ANIMATION SYSTEM ─────────────────────────────────────────────────
  getAnimations() {
    return {
      pulse: {
        keyframes: '@keyframes pulse { 0% { opacity: 1 } 50% { opacity: 0.5 } 100% { opacity: 1 } }',
        duration: '2s',
        timing: 'infinite'
      },
      slideIn: {
        keyframes: '@keyframes slideIn { from { opacity: 0; transform: translateX(-20px) } to { opacity: 1; transform: translateX(0) } }',
        duration: '0.3s',
        timing: 'ease-out'
      },
      fadeIn: {
        keyframes: '@keyframes fadeIn { from { opacity: 0 } to { opacity: 1 } }',
        duration: '0.5s',
        timing: 'ease-in'
      },
      highlight: {
        keyframes: '@keyframes highlight { 0% { background: transparent } 50% { background: rgba(59,130,246,0.2) } 100% { background: transparent } }',
        duration: '1s',
        timing: 'ease-in-out'
      }
    };
  },

  // ─── ACCESSIBILITY RULES ──────────────────────────────────────────────
  getAccessibilityRules() {
    return {
      minClickSize: '44px',  // Mobile touch target
      minContrastRatio: 4.5,  // WCAG AA
      focusIndicator: '2px solid #60a5fa',
      reducedMotionSupport: true,
      ariaLabels: true,
      keyboardNavigation: true
    };
  },

  // ─── EXTENSION COPILOT UI ──────────────────────────────────────────────
  getExtensionDesign() {
    return {
      popup: {
        width: '350px',
        maxHeight: '600px',
        padding: '1rem',
        background: `linear-gradient(135deg, ${this.COLORS.background}, ${this.COLORS.surface})`,
        border: `1px solid ${this.COLORS.border}`,
        borderRadius: '8px',
        boxShadow: '0 10px 40px rgba(0,0,0,0.5)'
      },
      header: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '0.75rem 0',
        borderBottom: `1px solid ${this.COLORS.border}`,
        marginBottom: '1rem'
      },
      section: {
        marginBottom: '1rem',
        padding: '0.75rem',
        background: `rgba(30, 41, 59, 0.5)`,
        borderRadius: '0.5rem',
        border: `1px solid ${this.COLORS.border}`
      },
      button: {
        width: '100%',
        padding: '0.65rem',
        marginBottom: '0.5rem',
        borderRadius: '0.375rem',
        border: 'none',
        fontSize: '0.85rem',
        fontWeight: 500,
        cursor: 'pointer',
        transition: 'all 0.2s ease'
      },
      alert: {
        padding: '0.75rem',
        borderRadius: '0.375rem',
        marginBottom: '0.5rem',
        fontSize: '0.8rem',
        lineHeight: 1.4
      }
    };
  },

  // ─── STUDIO LAYOUT OPTIMIZATION ───────────────────────────────────────
  getStudioLayout(screenWidth) {
    const layout = this.getLayoutForDevice(screenWidth);

    return {
      screenWidth,
      layout,
      structure: {
        HEADER: {
          height: '80px',
          sticky: true,
          zIndex: 1000,
          content: ['STATUS', 'INDICATORS', 'HELP']
        },
        CRITICAL_ZONE: {
          height: '150px',
          background: this.COLORS.background,
          grid: {
            columns: '1fr 1fr 1fr 1fr',
            gap: '1rem'
          },
          items: ['SYMBOL', 'TIMEFRAME', 'PRICE', 'CANDLE_TIMER'],
          sticky: true,
          zIndex: 900
        },
        MAIN_CHART: {
          height: layout.type.includes('MOBILE') ? '300px' : '450px',
          width: '100%',
          border: `1px solid ${this.COLORS.border}`,
          padding: '1rem'
        },
        SIGNALS: {
          height: 'auto',
          minHeight: '150px',
          multiColumn: layout.cols >= 2,
          cards: 'responsive'
        },
        SIDEBAR: {
          display: layout.cols >= 3 ? 'block' : 'none',
          width: '300px',
          position: 'right',
          sticky: true,
          content: ['OPPORTUNITIES', 'NEWS', 'ALERTS']
        },
        LOGS: {
          height: 'auto',
          collapsed: true,
          toggleable: true
        }
      }
    };
  },

  // ─── CHROME EXTENSION POPUP BLUEPRINT ──────────────────────────────────
  getExtensionPopupHTML() {
    return `
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: linear-gradient(135deg, #0f172a, #1e293b);
      color: #e0f2fe;
      width: 350px;
      padding: 1rem;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1rem;
      padding-bottom: 0.75rem;
      border-bottom: 1px solid #334155;
    }
    .title { font-size: 1.1rem; font-weight: 600; }
    .status-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: #10b981;
      animation: pulse 2s infinite;
    }
    @keyframes pulse { 0%, 100% { opacity: 1 } 50% { opacity: 0.5 } }
    .asset-info {
      background: rgba(30, 41, 59, 0.7);
      padding: 0.75rem;
      border-radius: 0.5rem;
      margin-bottom: 0.75rem;
      border-left: 3px solid #3b82f6;
    }
    .asset-name {
      font-size: 1.25rem;
      font-weight: 700;
      color: #60a5fa;
    }
    .asset-tf {
      font-size: 0.85rem;
      color: #94a3b8;
      margin-top: 0.25rem;
    }
    .button {
      width: 100%;
      padding: 0.65rem;
      margin-bottom: 0.5rem;
      background: #1e40af;
      color: #fff;
      border: none;
      border-radius: 0.375rem;
      cursor: pointer;
      font-weight: 500;
      font-size: 0.85rem;
      transition: all 0.2s;
    }
    .button:hover { background: #1e3a8a; }
    .button.secondary { background: #334155; color: #e0f2fe; }
    .button.danger { background: #dc2626; }
    .alert {
      padding: 0.65rem;
      margin-bottom: 0.75rem;
      border-radius: 0.375rem;
      font-size: 0.8rem;
      border-left: 3px solid #f59e0b;
      background: rgba(245, 158, 11, 0.1);
    }
    .section-title {
      font-size: 0.8rem;
      text-transform: uppercase;
      color: #64748b;
      margin: 0.75rem 0 0.5rem 0;
      font-weight: 600;
    }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <div class="title">📊 Trading Copilot</div>
    </div>
    <div class="status-dot"></div>
  </div>

  <div class="asset-info">
    <div class="asset-name" id="asset-name">--</div>
    <div class="asset-tf" id="asset-tf">Timeframe: --</div>
  </div>

  <div id="alerts-container"></div>

  <div class="section-title">Actions</div>
  <button class="button" id="btn-analyze">📈 Analyze Now</button>
  <button class="button secondary" id="btn-info">ℹ️ Details</button>
  <button class="button secondary" id="btn-monitor">👁️ Monitor</button>
  <button class="button secondary" id="btn-studio">🎯 Open Studio</button>
  <button class="button secondary" id="btn-refresh">🔄 Refresh</button>

  <div class="section-title">Status</div>
  <div id="status-msg" style="font-size: 0.8rem; color: #94a3b8; line-height: 1.5;">
    Waiting for TradingView data...
  </div>

  <script src="popup.js"></script>
</body>
</html>
    `;
  }
};

module.exports = designerAgent;
