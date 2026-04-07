// Agent: trade-logic — explains WHY to enter/wait/avoid

function explain({ symbol, direction, score, levels, rsi, ema, structure, fvgs, liquidity, consensus, marketState, news, profile }) {
  const lines = [];
  const sym   = symbol || '?';
  const dir   = direction || 'NEUTRAL';
  const opp   = dir === 'LONG' ? 'SHORT' : 'LONG';

  if (dir === 'NEUTRAL' || dir === 'ATTENDRE') {
    lines.push(`⏳ ATTENDRE — Pas de setup clair sur ${sym}.`);
    if (consensus?.conflict) lines.push(`Les petites unités de temps contredisent les grandes : ce n'est pas un vrai retournement.`);
    return { agent:'trade-logic', decision:'ATTENDRE', lines, text: lines.join('\n') };
  }

  // Why this direction
  lines.push(`✅ POURQUOI ${dir} SUR ${sym} :`);
  if (consensus?.dominantBias === dir)
    lines.push(`• Les grandes unités de temps (${consensus?.byTimeframe ? Object.entries(consensus.byTimeframe).filter(([,v]) => v.class === 'dominant' && v.bias === dir).map(([k]) => k).join('/') : '?'}) sont alignées ${dir}.`);
  if (rsi?.note) lines.push(`• RSI: ${rsi.note}`);
  if (ema?.signals?.length) ema.signals.slice(0, 2).forEach(s => lines.push(`• EMA: ${s}`));
  if (structure?.bos) lines.push(`• Structure: ${structure.bos}`);
  if (structure?.choch) lines.push(`• ${structure.choch}`);
  if (fvgs?.length) {
    const rf = fvgs.find(f => (dir === 'LONG' && f.type === 'BULLISH_FVG') || (dir === 'SHORT' && f.type === 'BEARISH_FVG'));
    if (rf) lines.push(`• FVG ${rf.type} identifié — zone d'équilibre à ${rf.midpoint?.toFixed?.(profile?.digits || 4) || rf.midpoint}`);
  }
  if (liquidity?.aboveLiquidity && dir === 'LONG')
    lines.push(`• Zone de liquidité above: ${liquidity.aboveLiquidity?.toFixed?.(profile?.digits || 4)} — cible potentielle.`);
  if (liquidity?.belowLiquidity && dir === 'SHORT')
    lines.push(`• Zone de liquidité below: ${liquidity.belowLiquidity?.toFixed?.(profile?.digits || 4)} — cible potentielle.`);

  // Why not the other direction
  lines.push(`\n❌ POURQUOI PAS ${opp} :`);
  if (consensus?.dominantBias === dir) lines.push(`• Le contexte dominant est ${dir} — aller contre imposerait un trade contre tendance haute risque.`);
  if (consensus?.conflict) lines.push(`• Attention: les petites UT montrent un signal ${opp} — mais c'est probablement un rebond technique.`);

  // SL/TP explanation
  if (levels) {
    lines.push(`\n📐 NIVEAUX :`);
    lines.push(`• Entrée: ${levels.entry} — prix actuel de marché.`);
    lines.push(`• Stop Loss: ${levels.sl} (${levels.slPips} pips) — sous/au-dessus de la structure invalidante.`);
    lines.push(`• Take Profit: ${levels.tp} (${levels.tpPips} pips) — vers prochaine zone de liquidité / résistance-support.`);
    lines.push(`• R:R ratio: 1:${levels.rrRatio} — minimum acceptable pour ce type de setup.`);
  }

  // News context
  if (news?.upcomingEvents?.length) {
    const urgent = news.upcomingEvents.find(e => e.minutesAway < 30 && e.impact === 'HIGH');
    if (urgent) lines.push(`\n⚠️ MACRO: Annonce haute impact dans ${urgent.minutesAway} min (${urgent.event}) — prudence sur l'entrée.`);
  }

  // Market state context
  if (marketState?.state === 'DANGEROUS' || marketState?.state === 'CHOPPY')
    lines.push(`\n⚠️ MARCHÉ: ${marketState.description} — réduire la taille de position.`);

  return { agent: 'trade-logic', decision: dir, score, lines, text: lines.join('\n') };
}

module.exports = { explain };
