# Agents Integration Report — 2026-04-05

## Objectif
- Séparer strictement les contextes:
  - Admin/Supervision: monitor, audit, agent logs
  - Dashboard utilisateur: décisions position + explications
  - Extension TradingView: signal local + coaching + news impact

## Cartographie Agents (runtime)
- Core supervision: `surveillance-agent`, `orchestrator`, `repair-agent`, `verification-agent`, `mirror-agent`, `bridge-agent`, `extension-agent`, `history-agent`
- Trading intelligence: `analysis-agent`, `position-explainer-agent`, `strategy-agent`, `risk-agent`, `execution-coach-agent`, `news-agent`
- Support: `central-guide-agent`, `research-agent`, `human-interface-agent`, `logic-gap-agent`, `ui-test-agent`

## Branchement par surface
- Admin:
  - Pages: `/agents-monitor`, `/agent-log`, `/audit-dashboard`
  - Flux: `/agents/runtime`, `/agent-activity`, `/system-log`, `/audit/state`, `/agents/history`
- Dashboard (utilisateur):
  - Page: `/dashboard.html`
  - Flux principal: `/coach/live?symbol=...&tf=...`
  - Détails: `/instant-trade-live`, `/agents/history`
- Extension:
  - UI: `tradingview-analyzer/popup.html` + `tradingview-analyzer/popup.js`
  - Flux principal: `/coach/live`, `/coach/trade-state`, `/coach/trade-action`, `/extension/sync`

## Boucle 30 minutes
- Agent périodique: `history-agent`
- Intervalle: `AGENT_HISTORY_INTERVAL_MS` (défaut 1800000 ms)
- Persistance:
  - `agent-history.json`
  - `backup/system-live/agent-history.json`
- API lecture: `GET /agents/history?limit=...`

## Spécialiste Explication Position
- Agent: `position-explainer-agent`
- Rôle: expliquer le "pourquoi" d'entrée (RSI, MACD, volume, spread, contexte gold)
- Exposition:
  - Appel interne via `/agents/position-explainer-agent/send`
  - Agrégation dans `/coach/live` -> `agents.explainer`

## News Temps Réel et Impact Symbol
- Source macro: calendrier interne + événements impact
- Source web: CoinGecko, Reuters RSS (commodities), X/Nitter RSS (best effort)
- Agent: `news-agent` via `market-intelligence?symbol=...`
- Résultat: `symbolImpact`, `upcomingEvents`, `warning`, `latestHeadline`

## Garde-fou performance
- Pas de boucle rapide news web: collecte internet agrégée uniquement via appels coach/utilisateur + cycle history lent
- Intervalle history minimum forcé à 10 min
- Runtime agent régulé par CPU (déjà en place)

## Validation attendue
1. Dashboard affiche recommandations + raisons détaillées + impact news symbole.
2. Extension affiche "Pourquoi" (agent spécialiste) + impact news symbole.
3. Admin conserve supervision sans mélanger UI utilisateur.
4. Historique agent visible via `/agents/history` et backup mis à jour.
