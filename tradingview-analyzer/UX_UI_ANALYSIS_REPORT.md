# 📊 RAPPORT COMPLET UX/UI — Trading Auto Extension v2.0

**Date:** 2 Avril 2026 | **Analyst:** Expert UX/UI Design | **Status:** ✓ Analyse Complète

---

## 📋 TABLE DES MATIÈRES
1. [Inventaire UI Complet](#-inventaire-ui-complet)
2. [Architecture Visuelle](#-architecture-visuelle)
3. [Analyse Ergonomique](#-analyse-ergonomique)
4. [Points Forts & Points Faibles](#-points-forts--points-faibles)
5. [Recommandations Précises](#-recommandations-précises)
6. [Priorités d'Implémentation](#-priorités-dimlémentation)

---

## 1️⃣ INVENTAIRE UI COMPLET

### 📦 DIMENSIONS DE L'EXTENSION
```
Largeur:   420px (fixe)
Hauteur:   600px (fixe)
Zones:     Header (36px) + Tabs (30px) + Content (482px) + Actions (52px)
```

### 🔴 ALERT BANNER (Critique)
**Classe:** `#alert-banner`
- **État:** Masqué par défaut (`display:none`)
- **Activation:** News critique détectée
- **Style:** Fond rouge (#ef4444), texte blanc
- **Contenu:** 🚨 + message dynamique
- **Comportement:** Sticky (top:0, z-index:1000) → Cliquable = Redirection vers onglet News

**Problème:** Pas de fermeture explicite (utilisateur doit aller à News)

---

### 🎛️ HEADER (36px)
**Classe:** `.header`

#### Côté Gauche (`.hdr-left`)
- **3 Dots statut** (`.dot`) : Serveur, MT5, Extension
  - États: `.ok` (vert #10b981), `.err` (rouge #ef4444), `.warn` (orange #f59e0b)
  - Taille: 7px × 7px
- **Symbol** (`.hdr-sym`): Couleur bleu (#3b82f6), monospace, gras
- **Timeframe** (`.hdr-tf`): Gris (#64748b), 10px, monospace
- **Price** (`.hdr-price`): Vert (#10b981), 11px, monospace

#### Côté Droit (`.hdr-right`)
- **Heure UTC** (`.hdr-time`): Gris #475569, monospace, 10px
- **Volatility Pill** (`.vol-pill`): Badge avec contexte
  - `.LOW`: Gris clair (background #1e293b)
  - `.MEDIUM`: Orange clair (#f59e0b)
  - `.HIGH`: Rouge clair (#ef4444)

---

### 📑 TABS (30px)
**Classe:** `.tabs` → `.tab`

**5 Onglets:**
1. **Actif** (data-tab="context") — Symbole, recherche MT5, statuts
2. **Graphique** (data-tab="chart") — Lightweight Charts + sélecteur timeframe
3. **Marches** (data-tab="market") — Sessions, volatilité, chevauchements
4. **News** (data-tab="news") — Évenements économiques (24h)
5. **Signal** (data-tab="signal") — Modes (SCALPER/SNIPER/SWING) + résultats analyse

**Visuel actif:**
- Border-bottom bleu (#3b82f6)
- Couleur texte bleu (#3b82f6)
- Background léger bleu (rgba(59,130,246,.04))

**Visuel inactif:**
- Gris (#64748b)
- Hover → Bleu clair (#93c5fd)

---

### 🔘 BOUTONS — INVENTAIRE COMPLET

#### **Classe `.btn-a`** (Boutons d'action) — 5 boutons
```
Grid: 28px | 1fr | 28px | 28px | 28px
```

1. **Refresh** (`#btn-refresh`)
   - Symbole: ↻ (U+21BA)
   - Titre: "Rafraichir"
   - Fonction: Raffraichir données système

2. **ANALYSER** (`#btn-analyze`) ⭐ BOUTON PRINCIPAL
   - Classe additionnelle: `.btn-ana`
   - Fond bleu (#2563eb)
   - Texte blanc et gras (12px)
   - Hover: Fond plus sombre (#1d4ed8) + scale 1.02
   - Padding: 8px 12px
   - Fonction: Lance analyse complète avec mode actif

3. **News Context** (`#btn-news-ctx`)
   - Symbole: 📰 (U+1F4F0)
   - Titre: "News"
   - Fonction: Affiche contexte news

4. **Screenshot** (`#btn-shoot`)
   - Symbole: 📸 (U+1F4F8)
   - Titre: "Screenshot TV"
   - Fonction: Capture graphique TradingView

5. **AI Debug** (`#btn-ai-dbg2`)
   - Symbole: "AI"
   - Titre: "Debug IA"
   - Font-size: 10px
   - Fonction: Lancer diagnostic IA

**Style commun `.btn-a`:**
- Border: 1px solid #334155
- Border-radius: 4px
- Background: #1e293b
- Couleur texte: #e2e8f0
- Cursor: pointer
- Transition: all 0.2s
- Hover: Background #334155, couleur #fff, border #475569
- Disabled: opacity 0.4, cursor not-allowed

---

#### **Classe `.btn-sm`** (Petits boutons)
**Styles:** Padding 4px 8px, border-radius 4px, font-size 11px

**Boutons trouvés:**
1. **Rechercher MT5** (`#btn-search-mt5`) — Recherche symbole + prix
2. **Refresh Graphique** (`#btn-chart-refresh`) — Symbole: ↻ (2px 6px)

---

#### **Classe `.tf-btn`** (Timeframe buttons)
```
21 boutons: M1, M2, M3...M30 | H1, H2...H12 | D1, W1, MN1
Layout: flex, gap 3px, scrollable horizontal
```

**Styles:**
- Default: transparent bg, gris (#64748b), border #334155, 10px, whitespace:nowrap
- Active: bg #1e3a5f, couleur #93c5fd, border #3b82f6
- Padding: 2px 6px

---

#### **Classe `.mb`** (Mode buttons)
```
Grid: 1fr 1fr 1fr (3 colonnes)
```

**3 Boutons:**
1. **SCALPER** (data-m="SCALPER") — Couleur: #f59e0b (orange)
2. **SNIPER** (data-m="SNIPER") — Couleur: #a78bfa (violet) — **Active par défaut**
3. **SWING** (data-m="SWING") — Couleur: #6ee7b7 (vert)

**Active state:**
- Border-width: 2px (vs 1px)
- Border-color: couleur dédiée
- Background: transparent

---

#### **Classe `.btn-ana`** (Analyser principal)
- Background: #2563eb (bleu primaire)
- Couleur: white
- Border: none
- Hover: #1d4ed8
- Transform: scale(1.02) on hover
- Font-weight: 700

---

#### **Classe `.ai-dbg-btn`** (AI Debug section)
```
Styles:
- Width: 100%
- Padding: 6px
- Border: 1px solid #7c3aed (violet)
- Background: rgba(124,58,237,.08)
- Couleur: #a78bfa (violet clair)
- Font-size: 10px, font-weight 700
- Hover: background rgba(124,58,237,.15)
```

---

### 🔍 CHAMPS DE RECHERCHE

#### **Recherche MT5** (Contexte → Recherche MT5)
```html
<div class='search-row'>
  <input type='text' id='map-query' 
         placeholder='gold, XAUUSD, NAS100...' autocomplete='off'>
  <input type='number' id='map-price' 
         placeholder='Prix' autocomplete='off' step='0.01'>
  <button class='btn-sm' id='btn-search-mt5'>Rechercher</button>
</div>
```

**Styles Input:**
- Background: #0f172a
- Border: 1px solid #1e3a5f
- Border-radius: 4px
- Couleur texte: #e2e8f0
- Padding: 5px 7px
- Font-size: 11px
- Focus: border-color #3b82f6

**Recherche:**
- Lance `searchMT5()` on Enter
- Auto-fetch prix when `length >= 2`
- Auto-fill prix depuis storage

---

### 📊 SECTIONS DE CONTENU

#### **Status Grid** (Contexte)
```
3 colonnes: Serveur | MT5 Bridge | Source
Classe: .si (status item)
```

Chaque item:
- Dot (`.si-dot`) : 8x8px, colored
- Label (`.si-lbl`): Gris, uppercase, 9px
- Value (`.si-val`): Monospace, couleur variable

---

#### **Status Rows** (Current Asset)
```
Classe: .row (flex, space-between)
- Label (.r-lbl): 11px, gris
- Value (.r-val): Monospace, 11px
  - .blue: #3b82f6
  - .green: #10b981
  - .muted: #475569
```

Affiche:
- Symbole MT5
- Bid / Ask
- Spread (pts)
- Timeframe
- Type (spot/CFD/etc)
- Source TV

---

#### **Chart Tab Structure**
```
Chart Bar (34px):
  - Symbole label (.chart-sym-label)
  - Timeframe scroll (.tf-scroll) [21 buttons]
  - Refresh button

Chart Container (448px):
  - Lightweight Charts instance
  - Fallback: message "Sélectionnez un actif..."
  - Loader spinner (24x24px) quand chargement
```

---

#### **News Items** (Onglet News)
```
Classe: .news-item
```

Affiche pour chaque événement:
- **Header** (`.news-hdr`):
  - Titre (`.news-title`): gras, #e2e8f0, 11px
  - Heure (`.news-time`): monospace, 10px
    - `.soon`: orange (#f59e0b)
    - `.recent`: vert (#86efac)
    - `.later`: gris (#475569)

- **Meta** (`.news-meta`):
  - Pays (`.n-country`): Badge bleu #1e3a5f, couleur #93c5fd
  - Impact (`.n-impact`):
    - `.High`: Rouge (#ef4444)
    - `.Medium`: Orange (#f59e0b)
    - `.Low`: Gris (#64748b)

- **Bias/Direction** (`.news-bias-dir`): #93c5fd, 10px
- **Why** (`.news-why`): Gris, 9px, line-height 1.4
- **Confiance** (`.news-conf`): Violet, 9px

---

#### **Sessions** (Onglet Marches)
```
Classe: .sess-item

Affiche:
- Nom session (.sess-name): #cbd5e1, gras
- Badge (.sess-badge):
  - .open: Vert rgba(16,185,129,.15), #86efac
  - .closed: Gris rgba(51,65,85,.2), #475569
```

---

#### **Overlap Banner** (Onglet Marches)
```
Classe: .overlap-banner
Background: rgba(124,58,237,.1)
Border: 1px solid #7c3aed
Couleur: #a78bfa (violet)
Font-size: 11px, gras
Affiche: Chevauchements de sessions (ex: "London + NewYork")
```

---

#### **Signal Section** (Onglet Signal)
```
Classe: .signal

3 Types:
- .signal.long: Bordure verte (#10b981), bg rgba(16,185,129,.05)
- .signal.short: Bordure rouge (#ef4444), bg rgba(239,68,68,.05)
- .signal.wait: Bordure orange (#f59e0b), bg rgba(245,158,11,.05)

Contenu:
- h2: Titre (LONG/SHORT/WAIT)
- Score: 0-100%
- Entry, SL (Stop Loss), TP (Take Profit)
- Confiance: bar avec pourcentage

Classe .conf-row:
- Bar gradient: #3b82f6 → #7c3aed
- Hauteur: 3px
- Width: transition 0.4s
- Pourcentage: monospace, #a78bfa
```

---

#### **Volatility Box** (Onglet Marches)
```
Classe: .vol-box

- LOW: bg rgba(100,116,139,.06), couleur #64748b
- MEDIUM: bg rgba(245,158,11,.08), couleur #fde68a
- HIGH: bg rgba(239,68,68,.08), couleur #fca5a5

Texte: label (LOW/MEDIUM/HIGH) + description
```

---

#### **User Note Area** (Onglet Signal)
```
Classe: textarea

<textarea id='user-note' rows='3' 
          placeholder='Contexte, scenario...'>

Styles:
- Width: 100%
- Background: #0f172a
- Border: 1px solid #1e3a5f
- Border-radius: 4px
- Couleur: #e2e8f0
- Padding: 6px
- Font-size: 11px
- Focus: border-color #3b82f6
- Placeholder couleur: #334155
```

---

#### **Map Results** (Candidats MT5)
```
Classe: .map-cand

Affiche:
- Nom (.cand-name): Bleu, 12px, monospace, gras
- Description (.cand-desc): Gris, 10px, truncate
- Catégorie (.cand-cat):
  - .forex: Bleu
  - .metal: Orange
  - .crypto: Violet
  - .index: Vert
  - .commodity: Rouge
  - .other: Gris

Hover: background #1e3a5f
```

---

#### **AI Debugger Output** (Contexte)
```
Classe: .ai-dbg-result

- Max-height: 120px
- Overflow-y: auto
- Background: #0d1526
- Padding: 7px
- Border-radius: 4px
- Font-size: 10px
- Couleur: #cbd5e1
- Line-height: 1.5

Scrollbar: 3px, thumb #334155
```

---

#### **AI Diagnostic Sections**
```
Classe: .diagnostic-section

Types:
- Default (bleu): border-left #3b82f6, bg rgba(30,58,95,.3)
- .fix (vert): border-left #10b981, bg rgba(16,185,129,.05)
- .code (violet): border-left #a78bfa, bg rgba(124,58,237,.05), monospace, 10px
- .raw (orange): border-left #f59e0b, bg rgba(245,158,11,.05), 10px

Strong: Bloc titre, gras, couleur dédiée, margin-bottom 3px
Pre: Overflow-x auto, padding 4px, bg #0a0f1e, border-radius 2px
```

---

## 2️⃣ ARCHITECTURE VISUELLE

### 🎨 PALETTE COULEURS

| Rôle | Couleur | Hex | Usage |
|------|---------|-----|-------|
| **Primaire** | Bleu | #3b82f6 | Symboles, onglet actif, principal |
| **Succès** | Vert | #10b981 | Statut OK, LONG, prix haussiers |
| **Danger** | Rouge | #ef4444 | Erreurs, COURT, alertes critiques |
| **Attention** | Orange | #f59e0b | Avertissements, SCALPER, MEDIUM |
| **Secondaire** | Violet | #7c3aed | SNIPER mode, AI debug, liens |
| **Fond Primaire** | #0a0f1e | — | Body background |
| **Fond Secondary** | #0d1220 | — | Header, action bar |
| **Fond Tertiary** | #0f172a | — | Inputs, cards |
| **Bordures** | #1e3a5f | — | Dividers, borders |
| **Texte Primaire** | #e2e8f0 | — | Main text |
| **Texte Secondary** | #94a3b8 | — | Muted, hints |
| **Texte Tertiary** | #64748b | — | Labels, small text |
| **Texte Desactivé** | #475569 | — | Disabled, placeholder |

### 🔤 TYPOGRAPHIE

| Élément | Font | Size | Weight | Color |
|---------|------|------|--------|-------|
| **Body** | Segoe UI, sans-serif | 12px | 400 | #e2e8f0 |
| **Headers** | Segoe UI | 12px | 700 | Variée |
| **Labels** | Segoe UI | 9-11px | 600 | #64748b |
| **Monospace** | Monospace | 10-12px | 600 | #3b82f6 |
| **Tabs** | Segoe UI | 10px | 600 | Variable |
| **Buttons** | Segoe UI | 10-12px | 700 | Variée |

### 📏 SPACING SYSTEM

```
Unité: 4px

xs:  2px
sm:  4px/5px
md:  6px/8px
lg:  12px
xl:  20px+

Gaps courants:
- Card padding: 8px 12px
- Section margin-bottom: 1px solid border
- Button padding: 4px-8px (sm) → 8px 12px (lg)
```

### 🎭 Z-INDEX LEVELS
```
1000: Alert banner (top sticky)
11: Chart loader spinner
10: Chart message placeholder
3: Scrollbar thumb
1: onglet-content elements
0: Base
```

### 🔘 BORDER RADIUS
```
2px: Subtle (scrollbar)
3px: Tags, badges
4px: Cards, inputs, buttons (standard)
5px: Sections, major elements
7px: Badges (sessions)
8px: Volatility pill (header)
50%: Dots (circulaires)
```

---

## 3️⃣ ANALYSE ERGONOMIQUE

### ✅ POINTS FORTS

#### **1. Hiérarchie Visuelle Claire**
- Header informatif avec statuts visuels (dots)
- Onglets bien définis, changement instantané
- Bouton principal "ANALYSER" bien en vue (bleu, large)
- Couleurs intentionnelles par type (succès/danger/info)

#### **2. Accessibilité Couleur**
- Palette à contraste élevé sur fond sombre (#0a0f1e)
- Codes de couleur cohérents (vert=OK, rouge=erreur, orange=attention)
- Pas de dépendance pure sur la couleur (+ symboles, text)

#### **3. Design System Cohérent**
- Spacing régulier (multiples de 4px)
- Border-radius cohérent (4px standard)
- Typographie unifiée (Segoe UI)
- Transitions smoothes (0.2s)

#### **4. Densité Informationnelle Optimale**
- Compacte (420px × 600px) mais aérée
- Scrolling minimal pour contextes rapides
- Layout fixed pour stabilité
- Pas de débordements

#### **5. Modes d'Interaction Intuitifs**
- Tabs classiques (pattern Web standard)
- Buttons iconiques + texte (clarity)
- Mode selection visual (border-width change)
- Timeframes scrollables (pattern trading)

#### **6. Responsivité aux États**
- Hover states clairs (.btn-a:hover)
- Active states visuels (tabs, timeframes, modes)
- Disabled states dimmed (opacity 0.4)
- Loading spinners (chart), messages placeholders

#### **7. Micro-interactions**
- Scale(1.02) on "ANALYSER" hover (feedback)
- Smooth scrollbar thumb (#1e3a5f)
- Transition 0.4s sur confidence bar
- Border color change on input focus

---

### ❌ POINTS FAIBLES

#### **1. Alert Banner — Pas de Fermeture**
**Problème:** Banner seulement fermable en allant à News tab
```
Impact: Utilisateur frustré si news non pertinente
Solution: Bouton ✕ pour fermer banner
```

#### **2. Boutons d'Action Peu Distincts**
**Problème:** `.btn-a` tous similaires (gris #1e293b)
```
Exceptions: Seulement "ANALYSER" est bleu
Impact: Hiérarchie faible, pas clair quel bouton est secondaire
Solution: Différencier par style (primary/secondary/tertiary)
```

#### **3. Onglet Graphique — UX Scrolling**
**Problème:** Timeframes scrollable horizontale cache boutons début/fin
```
Impact: Mobile/trackpad difficile à naviguer
Solution: Boutons < > pour navigation, ou horizontal scroll bar
```

#### **4. Pas de Feedback sur Recherche MT5**
**Problème:** Pas de loader/spinner quand on clique "Rechercher"
```
Impact: Utilisateur ne sait pas si recherche est lancée
Solution: Spinner quand recherche en cours, désactiver bouton
```

#### **5. Signal/Confiance — Format Peu Lisible**
**Problème:** Confidence bar + % mélangés visuellement
```
Affichage actuel: Gradient bar + texte à côté
Impact: Moins impactant que possible
Solution: Label "Confidence: 72%" plus visible, bar plus épaisse
```

#### **6. Volatility Pill Statut Ambigu**
**Problème:** Couleurs changent mais label reste "LOW/MEDIUM/HIGH"
```
Impact: "LOW" en gris peut sembler "indisponible"
Solution: Description textuelle + couleur (ex: "📉 Faible activité")
```

#### **7. Responsive à 420px — Saturation Visuelle**
**Problème:** Beaucoup de texte + dots + badges en petit espace
```
Impact: En détail, écran peut sembler chaotique
Solution: Progressive disclosure, collapsible sections
```

#### **8. News List — Pas de Tri/Filtre**
**Problème:** Affiche max 10 événements, pas de filtre par impact
```
Impact: Utilisateur doit scroller si beaucoup d'événements
Solution: Filtre par impact (High/Medium/Low), sort by time
```

#### **9. Input Placeholders — Contraste Faible**
**Problème:** Placeholder #334155 sur background #0f172a
```Ratio: ~3.5:1 (A AA standard)
Impact: Faible lisibilité pour malvoyants
Solution: Placeholder #475569 (ratio 5:1)
```

#### **10. Mode Buttons — Border Style Inconsistant**
**Problème:** Actif = border 2px, inactif = 1px
```
Impact: Tremble visuellement quand on clique
Solution: Border toujours 2px, couleur opaque/transparent
```

---

## 4️⃣ ÉLÉMENTS MANQUANTS / BESOINS

### 🔴 MANQUES CRITIQUES

1. **Close Button sur Alert Banner**
   - Urgent pour UX
   - Devrait être ✕ ou "Fermer"

2. **Search Loading State**
   - Spinner pendant recherche MT5
   - Désactiver bouton pendant requête
   - Timeout avec message d'erreur

3. **Bottom Padding en Chart Tab**
   - Chart peut être caché par overscroll
   - Besoin padding-bottom sur #tab-chart

4. **News Filter/Sort UI**
   - Boutons "Impact: High/Medium/Low"
   - Tri "Prochains" vs "Récents"

5. **Mobile-Like Indicators**
   - Sur petit écran, onglets deviennent cramped
   - Icônes seules + hover pour label?

### 🟡 AMÉLIORATIONS SOUHAITÉES

6. **Confidence Score Format**
   - Afficher "72 %" plus gros (14px vs 10px)
   - Label "Confiance:"

7. **Session Overlap Animation**
   - Pulse animation quand session overlap?
   - Attire l'attention sur événement important

8. **Symbol Mapper Feedback**
   - Message "Symbole détecté: XAUUSD ✓"
   - Pas juste silencieux mapping

9. **Error Messages Styling**
   - Classe `.error-box`, `.warning-box`
   - Icônes ⚠️ / ❌ consistantes

10. **Dark Mode Toggle** (Futur)
    - Switch simple light/dark?
    - Actuellement hard-coded dark

---

## 5️⃣ RECOMMANDATIONS PRÉCISES

### 🎨 A. AMÉLIORATIONS VISUELLES

#### **1. HIERARCHIE BOUTONS — 3 Niveaux**

```css
/* PRIMARY — Action majeure */
.btn-primary {
  background: #2563eb;   /* Bleu vif */
  color: white;
  border: none;
  padding: 10px 16px;
  border-radius: 6px;
  font-weight: 700;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3);
}

.btn-primary:hover {
  background: #1d4ed8;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.4);
  transform: translateY(-1px);
}

.btn-primary:active {
  transform: translateY(0);
  box-shadow: 0 1px 4px rgba(37, 99, 235, 0.2);
}

/* SECONDARY — Actions secondaires */
.btn-secondary {
  background: transparent;
  border: 2px solid #3b82f6;
  color: #3b82f6;
  padding: 8px 12px;
  border-radius: 4px;
  font-weight: 600;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-secondary:hover {
  background: rgba(59, 130, 246, 0.1);
  border-color: #1d4ed8;
  color: #1d4ed8;
}

/* TERTIARY — Actions mineures */
.btn-tertiary {
  background: transparent;
  border: 1px solid #475569;
  color: #94a3b8;
  padding: 6px 10px;
  border-radius: 3px;
  font-size: 10px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-tertiary:hover {
  background: rgba(100, 116, 139, 0.1);
  border-color: #64748b;
  color: #cbd5e1;
}

/* DANGER — Actions destructrices */
.btn-danger {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid #ef4444;
  color: #fca5a5;
  padding: 6px 12px;
  border-radius: 4px;
  font-weight: 600;
  font-size: 11px;
}

.btn-danger:hover {
  background: rgba(239, 68, 68, 0.2);
  border-color: #dc2626;
  color: #ff9999;
}

/* SUCCESS — Actions positives */
.btn-success {
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid #10b981;
  color: #86efac;
  padding: 6px 12px;
  border-radius: 4px;
  font-weight: 600;
  font-size: 11px;
}

.btn-success:hover {
  background: rgba(16, 185, 129, 0.2);
  border-color: #059669;
  color: #a7f3d0;
}
```

**Application:**
```html
<!-- Actuel -->
<button class='btn-a btn-ana' id='btn-analyze'>Analyser</button>

<!-- Futur -->
<button class='btn-primary' id='btn-analyze'>
  🔍 Analyser
</button>
<button class='btn-tertiary' id='btn-refresh'>↻</button>
<button class='btn-tertiary' id='btn-shoot'>📸</button>
```

---

#### **2. ALERT BANNER — Close Button**

```css
#alert-banner {
  display: none;
  background: #ef4444;
  color: white;
  padding: 10px 12px;
  border-bottom: 2px solid #dc2626;
  font-weight: bold;
  font-size: 12px;
  text-align: center;
  cursor: pointer;
  position: sticky;
  top: 0;
  z-index: 1000;
  
  /* Flexbox pour fermeture */
  display: flex;
  align-items: center;
  justify-content: space-between;
  
  animation: slideDown 0.3s ease;
}

#alert-banner.active {
  display: flex;
}

@keyframes slideDown {
  from {
    transform: translateY(-100%);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

#alert-close {
  background: none;
  border: none;
  color: white;
  font-size: 18px;
  cursor: pointer;
  padding: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s;
}

#alert-close:hover {
  transform: scale(1.2);
}

#alert-text {
  flex: 1;
}</
```

```html
<div id='alert-banner' class='active'>
  <span id='alert-text'>🚨 News importante détectée</span>
  <button id='alert-close'>✕</button>
</div>
```

---

#### **3. CONFIDENCE SCORE — Format Visible**

```css
.conf-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  padding: 6px;
  background: rgba(59, 130, 246, 0.08);
  border-radius: 4px;
}

.conf-label {
  font-size: 11px;
  color: #94a3b8;
  font-weight: 600;
  white-space: nowrap;
}

.conf-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
}

.conf-bar {
  flex: 1;
  height: 6px;  /* Plus épais */
  background: #1e293b;
  border-radius: 3px;
  overflow: hidden;
  min-width: 100px;
}

.conf-fill {
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, #3b82f6, #10b981);  /* Plus coloré */
  transition: width 0.4s ease;
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.5);
}

.conf-pct {
  font-size: 12px;  /* + gros (10px → 12px) */
  color: #3b82f6;
  font-weight: 700;
  font-family: monospace;
  min-width: 35px;
  text-align: right;
}
```

```html
<div class='conf-row'>
  <span class='conf-label'>Confiance</span>
  <div class='conf-wrapper'>
    <div class='conf-bar'>
      <div class='conf-fill' style='width: 72%'></div>
    </div>
    <span class='conf-pct'>72%</span>
  </div>
</div>
```

---

#### **4. TIMEFRAME SELECTOR — Navigation**

```css
.chart-bar {
  height: 34px;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 0 10px;
  background: #0d1220;
  border-bottom: 1px solid #1e3a5f;
  flex-shrink: 0;
}

#chart-sym-label {
  font-size: 11px;
  font-weight: 700;
  color: #3b82f6;
  font-family: monospace;
  flex: 1;
  white-space: nowrap;
}

.tf-nav {
  display: flex;
  gap: 4px;
  align-items: center;
}

.tf-btn-prev, .tf-btn-next {
  background: transparent;
  border: 1px solid #334155;
  color: #64748b;
  width: 20px;
  height: 20px;
  border-radius: 3px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  transition: all 0.2s;
}

.tf-btn-prev:hover, .tf-btn-next:hover {
  background: #1e3a5f;
  border-color: #3b82f6;
  color: #93c5fd;
}

.tf-scroll {
  display: flex;
  gap: 3px;
  overflow-x: auto;
  flex: 2;
  scroll-behavior: smooth;
  scroll-padding: 5px;
}

.tf-scroll::-webkit-scrollbar {
  height: 4px;
}

.tf-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.tf-scroll::-webkit-scrollbar-thumb {
  background: #334155;
  border-radius: 2px;
}

.tf-scroll::-webkit-scrollbar-thumb:hover {
  background: #475569;
}

.tf-btn {
  padding: 4px 8px;
  border: 1px solid #334155;
  border-radius: 3px;
  background: transparent;
  color: #64748b;
  font-size: 10px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  transition: all 0.2s;
}

.tf-btn:hover {
  border-color: #475569;
  color: #cbd5e1;
  background: rgba(59, 130, 246, 0.08);
}

.tf-btn.active {
  background: #1e3a5f;
  color: #93c5fd;
  border-color: #3b82f6;
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.3);
}
```

```html
<div class='chart-bar'>
  <span id='chart-sym-label'>--</span>
  <div class='tf-nav'>
    <button class='tf-btn-prev' id='tf-prev'>←</button>
    <div class='tf-scroll' id='tf-scroll'>
      <!-- buttons -->
    </div>
    <button class='tf-btn-next' id='tf-next'>→</button>
  </div>
  <button class='btn-tertiary' id='btn-chart-refresh'>↻</button>
</div>
```

**Script:**
```javascript
const scroll = document.getElementById('tf-scroll');
const prevBtn = document.getElementById('tf-prev');
const nextBtn = document.getElementById('tf-next');

prevBtn.addEventListener('click', () => {
  scroll.scrollBy({ left: -100, behavior: 'smooth' });
});

nextBtn.addEventListener('click', () => {
  scroll.scrollBy({ left: 100, behavior: 'smooth' });
});
```

---

#### **5. SEARCH STATE — Loading Indicator**

```css
#btn-search-mt5 {
  position: relative;
  transition: all 0.2s;
}

#btn-search-mt5.loading {
  opacity: 0.6;
  cursor: not-allowed;
}

#btn-search-mt5.loading::after {
  content: '';
  position: absolute;
  width: 12px;
  height: 12px;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border: 2px solid #475569;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: translate(-50%, -50%) rotate(360deg); }
}

.search-result {
  margin-top: 8px;
  padding: 8px;
  border-radius: 4px;
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid #10b981;
  color: #86efac;
  font-size: 10px;
}

.search-error {
  background: rgba(239, 68, 68, 0.1);
  border-color: #ef4444;
  color: #fca5a5;
}
```

```javascript
// Ajouter feedback
function searchMT5() {
  const btn = document.getElementById('btn-search-mt5');
  btn.classList.add('loading');
  btn.disabled = true;
  
  // ... recherche ...
  
  btn.classList.remove('loading');
  btn.disabled = false;
  
  // Afficher résultat
  const resultDiv = document.createElement('div');
  resultDiv.className = 'search-result';
  resultDiv.textContent = 'Symbole trouvé: XAUUSD ✓';
  document.getElementById('map-results').innerHTML = '';
  document.getElementById('map-results').appendChild(resultDiv);
}
```

---

#### **6. INPUT PLACEHOLDER — Contraste**

```css
input[type=text],
input[type=number] {
  background: #0f172a;
  border: 1px solid #1e3a5f;
  border-radius: 4px;
  color: #e2e8f0;
  padding: 5px 7px;
  font-size: 11px;
  outline: none;
  transition: all 0.2s;
}

input[type=text]::placeholder,
input[type=number]::placeholder {
  color: #475569;  /* ← Plus clair (was #334155) */
}

input[type=text]:focus,
input[type=number]:focus {
  border-color: #3b82f6;
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.2);
}

input[type=text]:hover:not(:focus),
input[type=number]:hover:not(:focus) {
  border-color: #334155;
}
```

---

#### **7. MODE BUTTONS — Border Consistency**

```css
.mb {
  padding: 8px;
  border-radius: 4px;
  border: 2px solid transparent;  /* Always 2px */
  background: transparent;
  color: #64748b;
  font-size: 10px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s ease;
}

.mb[data-m="SCALPER"] {
  color: #f59e0b;
}

.mb[data-m="SNIPER"] {
  color: #a78bfa;
}

.mb[data-m="SWING"] {
  color: #6ee7b7;
}

.mb:hover {
  background: rgba(59, 130, 246, 0.08);
  border-color: rgba(59, 130, 246, 0.3);
}

.mb.active {
  border-color: currentColor;  /* Utiliser couleur du mode */
  background: rgba(59, 130, 246, 0.1);
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.3);
}
```

---

#### **8. NEWS FILTER UI**

```css
.news-filter {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
  padding: 8px;
  background: #0d1526;
  border-radius: 4px;
}

.filter-btn {
  padding: 4px 8px;
  border-radius: 3px;
  border: 1px solid #334155;
  background: transparent;
  color: #64748b;
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-btn:hover {
  border-color: #475569;
  color: #cbd5e1;
}

.filter-btn.active {
  border-color: #3b82f6;
  background: #1e3a5f;
  color: #93c5fd;
}

.filter-btn.high { --accent: #ef4444; }
.filter-btn.medium { --accent: #f59e0b; }
.filter-btn.low { --accent: #64748b; }

.filter-btn.active.high { border-color: #ef4444; background: rgba(239, 68, 68, 0.15); }
.filter-btn.active.medium { border-color: #f59e0b; background: rgba(245, 158, 11, 0.15); }
.filter-btn.active.low { border-color: #64748b; background: rgba(100, 116, 139, 0.15); }
```

```html
<div class='news-filter'>
  <button class='filter-btn high active'>High Impact</button>
  <button class='filter-btn medium active'>Medium</button>
  <button class='filter-btn low'>Low</button>
  <button class='filter-btn'>Sort: Prochains</button>
</div>
```

---

#### **9. ERROR MESSAGES — Styling Unifié**

```css
.message-box {
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 11px;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0;
  animation: slideIn 0.3s ease;
}

.message-box.error {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid #ef4444;
  border-left: 3px solid #ef4444;
  color: #fca5a5;
}

.message-box.warning {
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid #f59e0b;
  border-left: 3px solid #f59e0b;
  color: #fde68a;
}

.message-box.success {
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid #10b981;
  border-left: 3px solid #10b981;
  color: #86efac;
}

.message-box.info {
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid #3b82f6;
  border-left: 3px solid #3b82f6;
  color: #93c5fd;
}

.message-icon {
  font-size: 14px;
  flex-shrink: 0;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

---

### 🎯 B. MICRO-INTERACTIONS RECOMMANDÉES

#### **1. Button Feedback Enhancement**

```css
.btn-primary {
  position: relative;
  overflow: hidden;
}

.btn-primary::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  width: 0;
  height: 0;
  background: radial-gradient(circle, rgba(255,255,255,0.3), transparent);
  border-radius: 50%;
  transform: translate(-50%, -50%);
  transition: width 0.6s, height 0.6s;
}

.btn-primary:active::before {
  width: 300px;
  height: 300px;
}
```

#### **2. Chart Loading State**

```css
.chart-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 5;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid #1e3a5f;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.spinner::after {
  content: '';
  position: absolute;
  width: 18px;
  height: 18px;
  border: 2px solid #1e3a5f;
  border-right-color: #7c3aed;
  border-radius: 50%;
  top: 3px;
  left: 3px;
  animation: spin 1.2s linear infinite reverse;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
```

#### **3. Toast Notification (News Alert)**

```css
.toast {
  position: fixed;
  bottom: 20px;
  right: 20px;
  background: #1e293b;
  border: 1px solid #334155;
  border-left: 3px solid #3b82f6;
  border-radius: 4px;
  padding: 12px 16px;
  color: #e2e8f0;
  font-size: 11px;
  z-index: 999;
  
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(100%);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

---

### 🎨 C. ACCESSIBILITÉ — WCAG AA

#### **1. Contrast Ratio Improvements**

| Élément | Contraste Actuel | Recommandé | Status |
|---------|------------------|-----------|---------|
| Text sur bg primaire | 11:1 | 4.5:1 AA | ✓ OK |
| Placeholder input | 3.5:1 | 4.5:1 | ❌ FIX → 5:1 |
| Muted text (#64748b) | ~5.5:1 | ≥4.5:1 | ✓ OK |
| Button labels | 5.8:1 | ≥3:1 | ✓✓ OK |
| Tab inactive | ~4.2:1 | ≥3:1 | ⚠️ OK (limite) |

#### **2. Focus States**

```css
/* IMPORTANT: Keyboard navigation */
.tab:focus,
.btn-a:focus,
.btn-primary:focus,
input:focus {
  outline: 2px solid #3b82f6;
  outline-offset: 2px;
}

/* Pour les utilisateurs qui préfèrent pas d'outline */
@media (prefers-reduced-motion: reduce) {
  * {
    animation: none !important;
    transition: none !important;
  }
}
```

#### **3. ARIA Labels**

```html
<!-- Current: Buttons without labels -->
<button class='btn-a' id='btn-shoot'>📸</button>

<!-- Better: -->
<button class='btn-a' id='btn-shoot' aria-label='Capturer screenshot TradingView'>
  📸
</button>

<!-- News impact icon: -->
<span class='n-impact High' aria-label='Impact: Important'>⬆️</span>
```

#### **4. Semantic HTML**

```html
<!-- Status section: use proper list -->
<section aria-label='Statut système'>
  <dl class='status-grid'>
    <dt class='si-lbl'>Serveur</dt>
    <dd class='si-val' id='sv-srv'>offline</dd>
  </dl>
</section>

<!-- Mode selection: fieldset -->
<fieldset>
  <legend class='sect-title'>Mode</legend>
  <div class='modes' role='group'>
    <input type='radio' id='mode-scalper' name='mode' value='SCALPER'>
    <label for='mode-scalper' class='mb'>SCALPER</label>
    ...
  </div>
</fieldset>
```

---

## 6️⃣ PRIORITÉS D'IMPLÉMENTATION

### 🔴 **PHASE 1 — CRITIQUE** (Semaine 1)

```
1. ✓ Alert Banner — Ajouter Close button (✕)
   Impact: Frustration utilisateur élevée
   Effort: 30 min
   
2. ✓ Buttons Hierarchie — .btn-primary vs .btn-secondary
   Impact: UX clarity majeure
   Effort: 1-2h (CSS + HTML updates)
   
3. ✓ Input Placeholder Contrast — #334155 → #475569
   Impact: Accessibilité (3.5 → 5:1)
   Effort: 15 min
   
4. ✓ Search State — Loading indicator
   Impact: Feedback utilisateur essentiel
   Effort: 1h (JS + CSS)
```

### 🟡 **PHASE 2 — IMPORTANTS** (Semaine 2-3)

```
5. ★ Timeframe Navigator — Buttons < >
   Impact: UX mobile/trackpad
   Effort: 1-2h
   
6. ★ Confidence Score Format — Augmenter visibilité
   Impact: Signal clarity
   Effort: 1h
   
7. ★ Mode Buttons Border — 2px consistent
   Impact: Visual stability
   Effort: 30 min
   
8. ★ News Filter — High/Medium/Low buttons
   Impact: Discoverability news
   Effort: 2-3h
```

### 🟢 **PHASE 3 — POLISH** (Semaine 4+)

```
9. ◐ Micro-interactions — Ripple effects, spinners
   Impact: Polishness perçue
   Effort: 2-3h
   
10. ◐ Error Messages Styling — Classes .error, .warning
    Impact: Consistency
    Effort: 1-2h
    
11. ◐ ARIA Labels + Semantic HTML
    Impact: Accessibilité avancée
    Effort: 3-4h
    
12. ◐ Dark Mode Toggle (Optional)
    Impact: User preference
    Effort: 3-4h
```

---

## 📝 RÉSUMÉ EXÉCUTIF

### 🎯 État Actuel
L'extension **Trading Auto Analyzer v2.0** possède une base visuelle **solide et cohérente** avec un design system dark mode bien appliqué. La hiérarchie et l'accessibilité couleur sont généralement bonnes.

### 🔧 Principaux Problèmes
1. **UX Friction:** Alert banner sans fermeture, pas de feedback recherche
2. **Hiérarchie faible:** Tous boutons gris sauf "ANALYSER"
3. **Polish:** Border width tremblant sur mode buttons, confidence score peu visible
4. **Navigation:** Timeframes scrollables sans chevrons de navigation

### ✨ Recommandations Prioritaires
| Rang | Action | Impact | Effort |
|------|--------|--------|--------|
| 1️⃣ | Alert + Close button | Critique UX | 30 min |
| 2️⃣ | Button Hierarchy (3 levels) | Clarity++ | 2h |
| 3️⃣ | Search loading state | Feedback | 1h |
| 4️⃣ | Timeframe navigation | Usability | 2h |
| 5️⃣ | Confidence score redesign | Clarity | 1h |

### 📊 Scoring UX Global

```
Ergonomie:        8/10  ★★★★★★★★☆☆
Design System:   9/10  ★★★★★★★★★☆
Accessibilité:   7/10  ★★★★★★★☆☆☆
Cohérence:       8.5/10 ★★★★★★★★☆☆
Responsivité:    7.5/10 ★★★★★★★☆☆☆
─────────────────────────────────────
MOYENNE:        7.9/10 ★★★★★★★★☆☆
```

### 🚀 Prochaines Étapes
1. Implémenter Phase 1 dans la sprint actuelle
2. Tester sur écrans < 500px (mobile response)
3. Audit WCAG AA complet
4. User testing avec traders réels
5. Itérations basées sur feedback

---

## 📎 ANNEXES

### CSS UTILITIES À AJOUTER

```css
/* Utility classes pour future maintenance */
.text-overflow-ellipsis {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scrollable-x {
  overflow-x: auto;
  scroll-behavior: smooth;
}

.skeleton {
  background: linear-gradient(90deg, #1e293b 0%, #334155 50%, #1e293b 100%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
```

### ACCESSIBILITY CHECKLIST

- [ ] Tab order logique (0 = premier element cliquable)
- [ ] Tous les inputs ont des labels (ou aria-label)
- [ ] Contraste ≥4.5:1 pour texte normal
- [ ] Contraste ≥3:1 pour UI components
- [ ] Focus visible sur tous les buttons
- [ ] Messages d'erreur associés aux inputs
- [ ] Icons accompagnées de texte
- [ ] Pas de couleur seule pour info

---

**Rapport compilé:** 2 Avril 2026
**Analysé par:** Expert UX/UI Design
**Version:** 1.0 — COMPLET

