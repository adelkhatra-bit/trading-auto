// ==UserScript==
// @name         ALIGN Bande Live
// @namespace    align-live
// @version      3.9
// @description  Bande du live ALIGN sur TradingView : messages Telegram, bulles, télécommande 15 s, infobulles roses
// @match        https://*.tradingview.com/chart/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==
(function () {
  'use strict';
  if (window.__ALIGN_BANDE__) { try { window.__ALIGN_BANDE__.stop(); } catch (e) {} }
  const VERSION = '3.9';
  const SUJET = 'align-live-2a4bccafd9548d93';
  const BASE = [
    '🔴 LIVE ALIGN • BTC • GOLD • NASDAQ',
    '👉 ABONNE-TOI • PARTAGE • TAPOTE L\'ÉCRAN',
    '📲 Le coach ALIGN est sur Telegram • lien en bio',
    '⚠️ Le trading comporte un risque de perte • ceci n\'est pas un conseil financier'
  ];
  const DUREE_MAIN = 15000, DUREE_MSG = 8000;

  // ───── style ─────
  const css = document.createElement('style');
  css.id = 'align-bande-css';
  css.textContent = `
  #align-bande{position:fixed;z-index:9999;height:54px;overflow:hidden;pointer-events:none;
    background:linear-gradient(90deg,#ff2d95,#8a2be2 50%,#1e90ff);border-radius:0 0 10px 10px;
    box-shadow:0 4px 14px rgba(0,0,0,.5);font:900 26px/54px system-ui,Segoe UI,Arial,sans-serif;color:#fff;
    text-shadow:0 2px 3px rgba(0,0,0,.45);transition:opacity .2s}
  #align-bande .piste{position:absolute;white-space:nowrap;will-change:transform}
  #align-bande .piste span{margin-right:70px}
  #align-bande .flash{position:absolute;inset:0;display:none;align-items:center;justify-content:center;
    padding:0 14px;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
    background:linear-gradient(90deg,#ff4fa3,#ffd400);color:#000;font-size:25px}
  #align-bande .flash.bulle{background:linear-gradient(90deg,#ffc0dc,#fff);color:#000}
  #align-bande.on .piste{visibility:hidden} #align-bande.on .flash{display:flex}
  [class*="common-tooltip__body"]{background:#ffc0dc!important;color:#000!important;max-width:330px!important;
    width:330px!important;font-weight:600!important;border:2px solid #ff4fa3!important;border-radius:10px!important}
  [class*="common-tooltip__body"] *{color:#000!important}`;
  document.head.appendChild(css);

  // ───── bande ─────
  const bande = document.createElement('div');
  bande.id = 'align-bande';
  bande.innerHTML = '<div class="piste"></div><div class="flash"></div>';
  document.body.appendChild(bande);
  const piste = bande.querySelector('.piste'), flash = bande.querySelector('.flash');
  let extra = [];
  function remplir() {
    const items = BASE.concat(extra.slice(-3));
    const html = items.map(t => '<span>' + esc(t) + '</span>').join('');
    piste.innerHTML = html + html;
  }
  function esc(s) { return String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])); }
  remplir();

  function zoneGraphique() {
    const c = document.querySelector('.chart-markup-table') || document.querySelector('.chart-container');
    return c ? c.getBoundingClientRect() : { left: 0, top: 0, width: innerWidth };
  }
  let x = 0, last = performance.now(), raf;
  function anim(now) {
    const r = zoneGraphique();
    const axe = 70;    // à droite : la bande s'arrête au début des prix
    const marge = 60;  // à gauche : commence plus à droite pour rester dans la zone filmée par TikTok
    bande.style.left = (r.left + marge) + 'px';
    bande.style.top = r.top + 'px';
    bande.style.width = Math.max(200, r.width - axe - marge) + 'px';
    const dt = Math.min(64, now - last); last = now;
    x -= dt * 0.09;
    const demi = piste.scrollWidth / 2;
    if (demi > 0 && -x >= demi) x += demi;
    piste.style.transform = 'translateX(' + x + 'px)';
    raf = requestAnimationFrame(anim);
  }
  raf = requestAnimationFrame(anim);

  // ───── messages (dans la bande, plus de fenêtre au centre) ─────
  const file = []; let occupe = false;
  function montrer(texte, bulle) { file.push({ texte, bulle }); suivant(); }
  function suivant() {
    if (occupe || !file.length) return;
    occupe = true;
    const m = file.shift();
    flash.textContent = m.texte;
    flash.classList.toggle('bulle', !!m.bulle);
    bande.classList.add('on');
    setTimeout(() => { bande.classList.remove('on'); occupe = false; suivant(); }, DUREE_MSG);
  }

  // ───── télécommande 15 s ─────
  let retour = null;
  function chart() { try { return window.TradingViewApi.activeChart(); } catch (e) { return null; } }
  function commande(sorte, valeur, prenom) {
    const c = chart(); if (!c) return;
    if (!retour) retour = { tf: c.resolution(), sym: c.symbol() };
    const nom = prenom ? prenom + ' a demandé ' : 'Vue ';
    const fin = ' • ⏳ 15 s • 📸 fais ta capture';
    const zoom = () => setTimeout(() => { try { chart().executeActionById('timeScaleReset'); } catch (e) {} }, 900);
    if (sorte === 'tf') { c.setResolution(valeur); montrer('🎮 ' + nom + (valeur === '60' ? '1 h' : valeur + ' min') + fin, true); }
    else if (sorte === 'sym') { c.setSymbol(valeur); montrer('🎮 ' + nom + valeur.split(':').pop() + fin, true); }
    else return;
    zoom();
    clearTimeout(commande.t);
    commande.t = setTimeout(() => {
      const c2 = chart(); if (c2 && retour) { const r0 = retour; c2.setSymbol(r0.sym, () => { c2.setResolution(r0.tf); zoom(); }); }
      retour = null;
    }, DUREE_MAIN);
  }

  function recu(txt) {
    txt = String(txt || '').trim(); if (!txt) return;
    if (txt.startsWith('CMD:')) {
      const p = txt.split(':');               // CMD:sorte:valeur(:avec:deux-points):prénom
      const sorte = p[1], prenom = p[p.length - 1], valeur = p.slice(2, -1).join(':');
      commande(sorte, valeur, prenom); return;
    }
    const bulle = txt.startsWith('BULLE:');
    if (bulle) txt = txt.slice(6).trim();
    montrer(txt, bulle);
    if (!bulle) { extra.push(txt); remplir(); }
  }

  // ───── écoute du canal ntfy (reconnexion automatique) ─────
  let es;
  function ecouter() {
    try { es && es.close(); } catch (e) {}
    es = new EventSource('https://ntfy.sh/' + SUJET + '/sse');
    es.onmessage = e => { try { const d = JSON.parse(e.data); if (d.event === 'message') recu(d.message); } catch (er) {} };
    es.onerror = () => { try { es.close(); } catch (e) {} setTimeout(ecouter, 5000); };
  }
  ecouter();

  // ───── infobulles : baissier → en haut, haussier → en bas, collées à gauche ─────
  const obs = new MutationObserver(() => {
    let survol = false;
    document.querySelectorAll('[class*="common-tooltip-"][class*="common-tooltip--"]').forEach(t => {
      const txt = t.innerText || '';
      if (!/[━]|ENTRÉE|SL|TP|ZONE|RETOURNEMENT|CONFIRMATION/.test(txt)) return;
      survol = true;
      const r = zoneGraphique();
      const baissier = /SHORT|baiss/i.test(txt) && !/LONG/.test(txt.split('\n')[0]);
      t.style.left = (r.left + 12) + 'px';
      t.style.right = 'auto';
      if (baissier) { t.style.top = (r.top + 56) + 'px'; t.style.bottom = 'auto'; }
      else { t.style.top = 'auto'; t.style.bottom = (innerHeight - (r.top + r.height) + 40) + 'px'; }
    });
    bande.style.opacity = survol ? '0' : '1';   // la bande s'efface pendant le survol d'une infobulle
  });
  obs.observe(document.body, { childList: true, subtree: true });

  window.__ALIGN_BANDE__ = {
    version: VERSION, recu,
    stop() { cancelAnimationFrame(raf); obs.disconnect(); try { es.close(); } catch (e) {} bande.remove(); css.remove(); }
  };
})();
