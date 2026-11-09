#!/usr/bin/env python3
"""ALIGN MTF BOT — même logique que l'indicateur TradingView ALIGN MTF PRO.
Prix gratuits Kraken (BTC = XBTUSD, Gold = PAXGUSD), signaux envoyés sur Telegram.
Tourne toutes les 5 minutes (GitHub Actions). Aucune dépendance externe."""
import json, os, re, time, urllib.request, urllib.error, urllib.parse, datetime
from zoneinfo import ZoneInfo
PARIS = ZoneInfo("Europe/Paris")

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
ETAT_FICHIER = os.environ.get("STATE_FILE", "state.json")
MARCHES = {"BTC": "XBTUSD", "GOLD": "PAXGUSD"}  # BTC → FTMO (CFD 24/7) • GOLD → Topstep (MGC) / FTMO
MIN_ALIGN, MIN_SQZ, MARGE_ATR, GAIN_MIN = 8, 4, 0.5, 1.5
UT = ["1", "2", "5", "10", "15", "30", "45", "1h", "2h", "4h", "D"]
POIDS = [1, 1, 1, 1, 2, 2, 2, 3, 3, 4, 5]

# ───────── Données ─────────
def http_json(url, data=None):
    """Appel HTTP avec 3 essais en cas de coupure réseau (ex. « Connection reset by peer »)."""
    for essai in range(3):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "align-bot"})
            with urllib.request.urlopen(req, timeout=70) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError:
            raise                      # vraie réponse d'erreur de l'API : inutile de réessayer
        except Exception:
            if essai == 2:
                raise
            time.sleep(2 * (essai + 1))

def kraken(pair, interval):
    j = http_json(f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval}")
    if j.get("error"):
        raise RuntimeError(j["error"])
    rows = next(v for k, v in j["result"].items() if k != "last")
    rows = rows[:-1]  # on enlève la bougie en cours : calcul à la clôture, comme l'alerte TradingView
    return [dict(t=int(r[0]), o=float(r[1]), h=float(r[2]), l=float(r[3]), c=float(r[4])) for r in rows]

def regrouper(bars, n, base_sec):
    """Construit une UT plus grande (ex : 2m depuis 1m) en respectant les bornes horaires."""
    out, cur = [], None
    for b in bars:
        debut = b["t"] - (b["t"] % (n * base_sec))
        if cur is None or cur["t"] != debut:
            if cur and cur["k"] == n:
                out.append(cur)
            cur = dict(t=debut, o=b["o"], h=b["h"], l=b["l"], c=b["c"], k=1)
        else:
            cur["h"] = max(cur["h"], b["h"]); cur["l"] = min(cur["l"], b["l"]); cur["c"] = b["c"]; cur["k"] += 1
    if cur and cur["k"] == n:
        out.append(cur)
    return out

# ───────── Indicateurs (identiques à Pine) ─────────
def ema(x, n):
    a, out, e = 2 / (n + 1), [], None
    for i, v in enumerate(x):
        e = (sum(x[:n]) / n if i == n - 1 else None) if e is None else a * v + (1 - a) * e
        out.append(e)
    return out

def rma(x, n):
    out, r = [], None
    for i, v in enumerate(x):
        if r is None:
            r = sum(x[:n]) / n if i == n - 1 else None
        else:
            r = (r * (n - 1) + v) / n
        out.append(r)
    return out

def sma(x, n):
    return [None if i < n - 1 else sum(x[i - n + 1:i + 1]) / n for i in range(len(x))]

def stdev(x, n):
    out = []
    for i in range(len(x)):
        if i < n - 1:
            out.append(None); continue
        w = x[i - n + 1:i + 1]; m = sum(w) / n
        out.append((sum((v - m) ** 2 for v in w) / n) ** 0.5)
    return out

def atr(b, n):
    tr = [b[0]["h"] - b[0]["l"]] + [max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - b[i - 1]["c"]), abs(b[i]["l"] - b[i - 1]["c"])) for i in range(1, len(b))]
    return rma(tr, n)

def rsi(c, n=14):
    up = [0] + [max(c[i] - c[i - 1], 0) for i in range(1, len(c))]
    dn = [0] + [max(c[i - 1] - c[i], 0) for i in range(1, len(c))]
    ru, rd = rma(up, n), rma(dn, n)
    return [None if u is None or d is None else (100 if d == 0 else 100 - 100 / (1 + u / d)) for u, d in zip(ru, rd)]

def linreg_fin(y):
    n = len(y); xs = range(n); mx = (n - 1) / 2; my = sum(y) / n
    pente = sum((i - mx) * (v - my) for i, v in zip(xs, y)) / sum((i - mx) ** 2 for i in xs)
    return my + pente * (n - 1 - mx)

def etat_ut(b):
    c = [x["c"] for x in b]
    ef, es = ema(c, 20)[-1], ema(c, 50)[-1]
    basis, dev = sma(c, 20)[-1], 2 * stdev(c, 20)[-1]
    kc, rng = ema(c, 20)[-1], 1.5 * atr(b, 20)[-1]
    d = 1 if c[-1] > ef > es else -1 if c[-1] < ef < es else 0
    sqz = (basis + dev) < (kc + rng) and (basis - dev) > (kc - rng)
    return d, 1 if sqz else 0, rsi(c)[-1]

def pivots(b, g=5):
    hs, ls = [], []
    for i in range(g, len(b) - g):
        if b[i]["h"] == max(x["h"] for x in b[i - g:i + g + 1]):
            hs.append(b[i]["h"])
        if b[i]["l"] == min(x["l"] for x in b[i - g:i + g + 1]):
            ls.append(b[i]["l"])
    return (hs[-1] if hs else None, ls[-1] if ls else None, hs[-2] if len(hs) > 1 else None, ls[-2] if len(ls) > 1 else None)

# ───────── Analyse complète d'un marché ─────────
def analyser(pair):
    m1, m5, m15, h1, h4, d1 = (kraken(pair, i) for i in (1, 5, 15, 60, 240, 1440))
    series = {"1": m1, "2": regrouper(m1, 2, 60), "5": m5, "10": regrouper(m5, 2, 300), "15": m15,
              "30": kraken(pair, 30), "45": regrouper(m15, 3, 900), "1h": h1, "2h": regrouper(h1, 2, 3600), "4h": h4, "D": d1}
    et = {k: etat_ut(v) for k, v in series.items()}
    dirs = [et[k][0] for k in UT]; sqzs = [et[k][1] for k in UT]; rsis = [et[k][2] or 50 for k in UT]
    bull, bear, comp = dirs.count(1), dirs.count(-1), sum(sqzs)
    rsiOB = sum(r >= 70 for r in rsis); rsiOS = sum(r <= 30 for r in rsis)
    sw = sum(POIDS); trendS = sum(w * d for w, d in zip(POIDS, dirs)) / sw
    rsiS = max(-1, min(1, sum(w * (r - 50) / 50 for w, r in zip(POIDS, rsis)) / sw * 2))
    court, longT = sum(dirs[:5]), sum(dirs[8:])

    # UT de référence = 15 minutes (comme le graphique)
    b = m15; c = [x["c"] for x in b]; r = rsi(c); rs = ema([v or 50 for v in r], 9)
    a = atr(b, 14)[-1]
    hh = [max(x["h"] for x in b[i - 19:i + 1]) for i in range(19, len(b))]
    ll = [min(x["l"] for x in b[i - 19:i + 1]) for i in range(19, len(b))]
    sm = sma(c, 20)[19:]
    base = [c[19 + i] - ((hh[i] + ll[i]) / 2 + sm[i]) / 2 for i in range(len(hh))]
    mom, mom1 = linreg_fin(base[-20:]), linreg_fin(base[-21:-1])
    momS = (1.0 if mom > mom1 else 0.4) if mom > 0 else (-1.0 if mom < mom1 else -0.4)
    sqzC, sqzC1 = etat_ut(b)[1], etat_ut(b[:-1])[1]
    croise = lambda x1, x0, y1, y0: x0 <= y0 and x1 > y1
    rC, rC1 = r[-1], r[-2]
    rsiAchat = (croise(rC, rC1, rs[-1], rs[-2]) and rC < 50) or croise(rC, rC1, 30, 30) or croise(rC, rC1, 50, 50)
    rsiVente = (croise(rs[-1], rs[-2], rC, rC1) and rC > 50) or croise(70, 70, rC, rC1) or croise(50, 50, rC, rC1)

    score = 0.45 * trendS + 0.30 * rsiS + 0.25 * momS
    pctH = round(50 + 50 * score); sens = 1 if score > 0.15 else -1 if score < -0.15 else 0
    retHaut = court >= 3 and longT <= -1 and momS > 0
    retBas = court <= -3 and longT >= 1 and momS < 0

    # Niveaux : pivots 15m, 1h, 4h, Daily
    niv, noms = [], []
    for nom, s in (("15m", m15), ("1h", h1), ("4h", h4), ("Daily", d1)):
        for v in pivots(s):
            niv.append(v); noms.append(nom)
    cl, hi, lo, op = b[-1]["c"], b[-1]["h"], b[-1]["l"], b[-1]["o"]
    zone_niv = [(v, n) for v, n in zip(niv, noms) if v is not None and n != "Daily"]
    dessus = sorted([z for z in zone_niv if z[0] > cl + a * 0.3])
    dessous = sorted([z for z in zone_niv if z[0] < cl - a * 0.3], reverse=True)
    hau1 = dessus[0] if dessus else None; bas1 = dessous[0] if dessous else None
    surR = hau1 and hi >= hau1[0] - a * MARGE_ATR and cl < hau1[0]
    surS = bas1 and lo <= bas1[0] + a * MARGE_ATR and cl > bas1[0]
    zBas0 = bool(surR and (rC > 58 or rsiOB >= 3) and momS < 1 and cl < op)
    zHaut0 = bool(surS and (rC < 42 or rsiOS >= 3) and momS > -1 and cl > op)
    zoneBas = zBas0 and not (zHaut0 and rC < 50); zoneHaut = zHaut0 and not zoneBas

    grosses = [(v, n) for v, n in zip(niv, noms) if v is not None and n != "15m"]
    def plan(d):
        cote = [v for v, n in grosses if n in ("1h", "4h") and d * (cl - v) > a * 0.3]
        sb = (max(cote) if d == 1 else min(cote)) if cote else (bas1[0] if d == 1 and bas1 else hau1[0] if d == -1 and hau1 else cl - d * 1.5 * a)
        swing = min(x["l"] for x in b[-10:]) - a * 0.2 if d == 1 else max(x["h"] for x in b[-10:]) + a * 0.2
        sl = min(sb - a * 0.3, swing) if d == 1 else max(sb + a * 0.3, swing)
        e_lim = sb + a * 0.3 if d == 1 else sb - a * 0.3
        e = min(cl, max(e_lim, sl + a * 1.0)) if d == 1 else max(cl, min(e_lim, sl - a * 1.0))
        # Risque minimum : 1 ATR ou 0,08 % du prix (évite les stops collés quand le marché dort, ex. le week-end)
        mini = max(a, cl * 0.0008)
        if abs(e - sl) < mini:
            sl = e - d * mini
        risque = abs(e - sl)
        cibles = sorted([(v, n) for v, n in grosses if d * (v - e) >= risque * GAIN_MIN], key=lambda z: d * z[0])
        t1 = cibles[0] if cibles else (e + d * risque * GAIN_MIN, f"projection {GAIN_MIN} x le risque")
        loin = [z for z in grosses if d * (z[0] - e) >= abs(t1[0] - e) + a]
        loin.sort(key=lambda z: d * z[0])
        t2 = loin[0] if loin else (e + d * risque * (GAIN_MIN + 2), "projection")
        return dict(e=e, sl=sl, tp1=t1[0], n1=t1[1], tp2=t2[0], n2=t2[1], rr=abs(t1[0] - e) / risque, marche=e == cl)

    fortHaut = rsiAchat and rsiOB < 3 and bull > bear and bull >= MIN_ALIGN - 2 and (comp >= MIN_SQZ or bull >= MIN_ALIGN)
    fortBas = rsiVente and rsiOS < 3 and bear > bull and bear >= MIN_ALIGN - 2 and (comp >= MIN_SQZ or bear >= MIN_ALIGN)
    explHaut = sqzC1 == 1 and sqzC == 0 and mom > 0 and bull > bear
    explBas = sqzC1 == 1 and sqzC == 0 and mom < 0 and bear > bull
    sigHaut = ((fortHaut or explHaut) and longT >= 1) or (zoneHaut and longT >= 0)
    sigBas = ((fortBas or explBas) and longT <= -1) or (zoneBas and longT <= 0)
    dirPlan = 1 if zoneHaut else -1 if zoneBas else 1 if longT >= 2 else -1 if longT <= -2 else 1 if retHaut else -1 if retBas else sens
    nom = ("★ ACHAT FORT" if fortHaut else "EXPLOSION ▲" if explHaut else "ZONE DE REBOND ▲") if sigHaut else \
          ("★ VENTE FORTE" if fortBas else "EXPLOSION ▼" if explBas else "ZONE DE RETOURNEMENT ▼") if sigBas else ""
    # ═══ STRATÉGIE : alignement 15m + 1h + 4h ═══
    d15, d1h, d4h = dirs[4], dirs[7], dirs[9]
    confirme = d15 if d15 != 0 and d15 == d1h == d4h else 0
    # Contexte Daily / Weekly : où est le prix dans sa zone (0 = tout en bas, 1 = tout en haut)
    w1 = kraken(pair, 10080)
    def position(bars, n):
        z = bars[-n:]; haut = max(x["h"] for x in z); bas = min(x["l"] for x in z)
        return (cl - bas) / max(haut - bas, 1e-9), haut, bas
    posD, hautD, basD = position(d1, 5)
    posW, hautW, basW = position(w1, 4)
    # RSI 5 min (déclencheur de l'entrée parfaite) et RSI 15 min
    r5 = rsi([x["c"] for x in m5])
    return dict(m1=m1, confirme=confirme, atr=a, r5=r5[-3:], r15=rC, posD=posD, posW=posW, hautD=hautD, basD=basD, hautW=hautW, basW=basW,
                grosses=grosses, b15=b[-30:], ema15=ema(c, 20)[-1], niveaux=[(v, n) for v, n in zip(niv, noms) if v is not None], t=b[-1]["t"], prix=cl, dirs=dirs, sqzs=sqzs, rsis=rsis, bull=bull, bear=bear, comp=comp, rsiOB=rsiOB, rsiOS=rsiOS,
                pctH=pctH, sens=sens, retHaut=retHaut, retBas=retBas, sigHaut=sigHaut, sigBas=sigBas, nom=nom,
                dirPlan=dirPlan, plan=plan(dirPlan if dirPlan else 1), planH=plan(1), planB=plan(-1), rC=rC)

# ───────── Messages ─────────
def px(v):
    return f"{v:,.2f}".replace(",", " ")

def cme_ouvert(ts):
    ct = datetime.datetime.fromtimestamp(ts, datetime.timezone(datetime.timedelta(hours=-6)))  # heure de Chicago (approx. hiver)
    if ct.weekday() == 5 or (ct.weekday() == 4 and ct.hour >= 16) or (ct.weekday() == 6 and ct.hour < 17):
        return False
    return ct.hour != 16

def barre(r):
    s = ""
    for d, q, rv in zip(r["dirs"], r["sqzs"], r["rsis"]):
        s += ("🟧" if q else "🟩" if d == 1 else "🟥" if d == -1 else "⬜")
    return s

def texte_plan(nom_marche, r, p, d):
    sens = "▲ LONG" if d == 1 else "▼ SHORT"
    return (f"{sens}  {nom_marche}\n"
            f"Entrée : {px(p['e'])} ({'au marché' if p['marche'] else 'ordre limite'})\n"
            f"TP1 : {px(p['tp1'])} ({p['n1']})\nTP2 : {px(p['tp2'])} ({p['n2']})\n"
            f"Stop : {px(p['sl'])}\nGain/risque ≈ {p['rr']:.1f}")

ICONE = {"BTC": "🟠", "GOLD": "🥇"}
SENS = {1: "🟩🟩 TRÈS LONG ⬆️", -1: "🟥🟥 TRÈS SHORT ⬇️"}

def alignement(r):
    """Sens majoritaire sur 15m / 1h / 4h et nombre d'UT d'accord (0 à 3)."""
    trio = [r["dirs"][4], r["dirs"][7], r["dirs"][9]]
    maj = 1 if trio.count(1) >= 2 else -1 if trio.count(-1) >= 2 else 0
    return maj, (trio.count(maj) if maj else 0)

def texte_etat(nom_marche, r, cle=None, vip=True):
    """Analyse courte : 1 info par ligne, verdict clair à la fin."""
    fl = lambda d: "⬆️" if d == 1 else "⬇️" if d == -1 else "➖"
    D, R = r["dirs"], r["rsis"]
    maj, n_ok = alignement(r)
    ut = [("1 min", 0), ("5 min", 2), ("15 min", 4), ("1 h", 7), ("4 h", 9), ("Daily", 10)]
    l = [f"{ICONE.get(nom_marche, '📊')} {nom_marche}   {px(r['prix'])}", "━━━━━━━━━━━━"]
    l += [f"{nom:<7} {fl(D[i])}   RSI {R[i]:.0f}" for nom, i in ut]
    l += ["━━━━━━━━━━━━",
          f"🧭 Alignement   {n_ok}/3 {'✅' if r['confirme'] else '⏳'} {fl(maj) if maj else ''}".rstrip(),
          f"📍 Daily {zone_txt(r['posD'])} • Weekly {zone_txt(r['posW'])}",
          r.get("news") or "📰 News : calendrier indisponible"]
    o = (cle or {}).get("ordre")
    if r["confirme"] and o and not (cle or {}).get("trade"):
        l.append(f"🟨 Zone   {px(o.get('za', o['e']))} – {px(o.get('zb', o['e']))}" if vip else "🟨 Zone   🔒🔒🔒")
    titre, raison = verdict(r, cle)
    l += ["━━━━━━━━━━━━", titre, raison]
    return "\n".join(l)

def bloque_dw(r, d):
    """Daily / Weekly : pas de short tout en bas, pas de long tout en haut."""
    return (d == -1 and (r["posD"] <= 0.15 or (r["posW"] <= 0.15 and r["posD"] <= 0.35))) or \
           (d == 1 and (r["posD"] >= 0.85 or (r["posW"] >= 0.85 and r["posD"] >= 0.65)))

def verdict(r, cle):
    """Réponse claire pour l'utilisateur : peut-il entrer maintenant ou non ?"""
    cle = cle or {}
    tr = cle.get("trade")
    if tr:
        p = r["m1"][-1]["c"]
        sens = "⬆️ ACHAT" if tr["d"] == 1 else "⬇️ VENTE"
        prog = tr["d"] * (p - tr["e"]) / max(abs(tr["tp1"] - tr["e"]), 1e-9)
        if tr["statut"] == "entree" and prog < 0.25 and not tr.get("tard"):
            return (f"🟢 TU PEUX ENTRER\n{SENS[tr['d']]}", f"🛑 Stop   {px(tr['sl'])}\n💰 TP1   {px(tr['tp1'])}\n👉 Puis appuie sur ✅ Je suis rentré")
        return ("🔴🔴 N'ENTRE PAS", f"⏰ Trop tard : la position {sens} est déjà partie\n⏳ J'attends le prochain setup")
    if r.get("annonce"):
        return ("🔴🔴 N'ENTRE PAS", "📰 News dans moins de 15 min\n💥 Le prix peut bouger très fort")
    al = r["confirme"]
    if not al:
        return ("🔴🔴 N'ENTRE PAS", "⏳ 15 min / 1 h / 4 h pas alignées\n🔔 Je te préviens dès que c'est bon")
    if bloque_dw(r, al):
        return ("🔴🔴 N'ENTRE PAS", f"📍 Prix {zone_txt(r['posD'])} Daily / {zone_txt(r['posW'])} Weekly\n🔄 Risque de rebond : pas de {'long' if al == 1 else 'short'} ici")
    return (f"🟡 PAS ENCORE — bientôt\n{SENS[al]}", "🟨 J'attends le prix dans la zone\n🚦 Je t'envoie 🟢 J'ENTRE MAINTENANT")

def telegram(methode, **params):
    url = f"https://api.telegram.org/bot{TOKEN}/{methode}"
    return http_json(url, urllib.parse.urlencode(params).encode())

# ───────── Boutons et jauge ─────────
CLAVIER = json.dumps({"keyboard": [[{"text": "🟠 Analyse BTC"}, {"text": "🥇 Analyse Gold"}], [{"text": "✅ Je suis rentré"}, {"text": "🚪 Je suis sorti"}],
                                   [{"text": "📈 Mes résultats"}, {"text": "🧩 Indicateur TradingView"}]],
                      "resize_keyboard": True, "is_persistent": True, "input_field_placeholder": "Utilise les boutons 👇"})
CLAVIER_VISITEUR = json.dumps({"keyboard": [[{"text": "🟠 Analyse BTC"}, {"text": "🥇 Analyse Gold"}], [{"text": "💎 Devenir VIP"}]],
                               "resize_keyboard": True, "is_persistent": True, "input_field_placeholder": "Utilise les boutons 👇"})
AVERTISSEMENT = ("ℹ️ Ce sont MES positions personnelles, partagées à titre informatif et éducatif. "
                 "Ce n'est pas un conseil en investissement ni une recommandation personnalisée. "
                 "Le trading (CFD, futures, crypto) peut faire perdre tout le capital investi : chacun décide seul et reste responsable de ses choix.")
MINI_AVERT = "ℹ️ Ma position perso • pas un conseil • risque de perte"
REGLES = ("📌 RÈGLES — ALIGN Signaux\n"
          "━━━━━━━━━━━━\n"
          "1️⃣ Ce sont MES positions perso, ma vision du marché\n"
          "❗ Pas un conseil en investissement\n"
          "2️⃣ Les prix changent selon la plateforme (FTMO, Topstep, broker…)\n"
          "👉 Suis les mèches et les %, pas le prix exact\n"
          "3️⃣ ⏱ Mets-toi en vue 15 minutes\n"
          "4️⃣ 🛑 Toujours un stop, derrière la mèche indiquée\n"
          "5️⃣ 📰 Pas de trade 15 min avant et après une news\n"
          "6️⃣ 💰 TP1 touché → stop à l'entrée\n"
          "7️⃣ ⚖️ Petit risque : 1 à 2 % du compte maximum par position\n"
          "8️⃣ ⚠️ Le trading peut faire perdre tout le capital\n"
          "━━━━━━━━━━━━\n"
          "📰 Je t'envoie les news : pas de trade juste avant ni juste après\n"
          "🤖 Appuie sur ✅ Je suis rentré : ton coach IA te suit jusqu'au TP\n"
          "📈 Tes gains et tes pertes sont calculés tout seuls\n"
          "🧩 L'indicateur TradingView : bouton 🧩 en bas\n"
          "━━━━━━━━━━━━\n"
          "🤝 Partage à tes amis :\n"
          "👉 https://t.me/align_mtf_adel_bot")

def epingler(etat, cid):
    """Envoie les règles et les épingle en haut de la conversation (une seule fois par conversation)."""
    if cid in etat.setdefault("epingles_v4", []):
        return
    try:
        res = telegram("sendMessage", chat_id=cid, text=REGLES, disable_notification="true")
        telegram("pinChatMessage", chat_id=cid, message_id=res["result"]["message_id"], disable_notification="true")
        etat["epingles_v4"].append(cid)
    except Exception as ex:
        print("epingler", cid, ex)

PARTAGE_JOURS = int(os.environ.get("PARTAGE_JOURS", "3"))  # rappel « partage à tes amis » tous les X jours

def message_partage(etat):
    """Invitation à partager le bot (texte court + bouton de partage Telegram)."""
    lien = f"https://t.me/{etat.get('bot') or 'align_mtf_adel_bot'}"
    txt = ("🤝 Tu aimes ALIGN Signaux ?\n"
           "📤 Partage-le à tes amis, fais-les en profiter\n"
           f"👉 {lien}\n"
           "🎁 Positions gratuites\n🧩 Indicateur TradingView ≈ 10 € / mois")
    url = "https://t.me/share/url?" + urllib.parse.urlencode({"url": lien, "text": "📈 Signaux BTC + Gold en direct, simples et clairs 👇"})
    return txt, json.dumps({"inline_keyboard": [[{"text": "📤 Partager à un ami", "url": url}]]})

OFFERT_JOURS = int(os.environ.get("OFFERT_JOURS", "7"))   # 1 signal complet offert aux visiteurs tous les X jours
POSITIONS_GRATUITES = os.environ.get("POSITIONS_GRATUITES", "1") == "1"   # positions gratuites pour tous, on vend l'indicateur
LIEN_INDICATEUR = os.environ.get("LIEN_INDICATEUR", "")   # lien du script TradingView « invite-only » (à remplir après publication)
PRIX_STARS = int(os.environ.get("PRIX_STARS", "500"))   # abonnement mensuel de la chaîne VIP (≈ 10 €)
ECOUTE_SEC = int(os.environ.get("ECOUTE_SEC", "200"))   # le bot reste à l'écoute entre deux analyses

def marche_demande(txt):
    """« Analyse BTC » → BTC, « Analyse Gold » → GOLD, « Analyse » seul → les deux (None)."""
    t = txt.lower()
    return "BTC" if "btc" in t else "GOLD" if ("gold" in t or "or" in t.split()) else None

def analyse_marche(etat, pair):
    r = analyser(pair)
    r["annonce"] = annonce_proche(etat or {}, int(time.time()))
    r["news"] = news_txt(etat or {})
    return r

def envoyer_analyse(cid, etat=None, mq=None):
    for nom_marche, pair in MARCHES.items():
        if mq and mq != nom_marche:
            continue
        try:
            telegram("sendMessage", chat_id=cid, text=texte_etat(nom_marche, analyse_marche(etat, pair), (etat or {}).get(nom_marche)), reply_markup=CLAVIER)
        except Exception as ex:
            print("analyse", ex)

def prix_actuel(m):
    """Dernier prix Kraken du marché (pour figer l'entrée ou la sortie d'un abonné)."""
    try:
        j = http_json(f"https://api.kraken.com/0/public/Ticker?pair={MARCHES[m]}")
        return float(next(iter(j["result"].values()))["c"][0])
    except Exception as ex:
        print("prix", ex); return None

def noter(etat, cid, m, pos, sortie, motif):
    """Enregistre le résultat d'un abonné : points, %, TP ou SL."""
    pts = pos["d"] * (sortie - pos["e"])
    pct = pts / pos["e"] * 100
    st = etat.setdefault("stats", {}).setdefault(cid, {"tp": 0, "sl": 0, "pts": {}, "pct": 0.0, "hist": []})
    st["tp" if pts > 0 else "sl"] += 1
    st["pts"][m] = st["pts"].get(m, 0) + pts
    st["pct"] += pct
    st["hist"] = (st["hist"] + [[m, round(pts, 2), round(pct, 2), motif, int(time.time())]])[-20:]
    pos["fini"] = True
    _envoi_sur(cid, reply_markup=CLAVIER, text=(
        f"{'✅' if pts > 0 else '❌'} {m} clôturé\n"
        f"{motif}\n"
        f"📌 Entrée   {px(pos['e'])}\n"
        f"🚪 Sortie   {px(sortie)}\n"
        f"{'⬆️' if pts > 0 else '⬇️'} {pts:+,.2f} pts\n".replace(",", " ")
        + f"📊 {pct:+.2f} %\n"
        + ("🎉 Bravo !" if pts > 0 else "💪 On repart au prochain")))

def texte_bilan(etat):
    b = etat.get("bilan")
    if not b or not (b["tp"] + b["sl"]):
        return "🤖 Bilan du bot   en cours de construction"
    n = b["tp"] + b["sl"]
    return (f"🤖 Bilan du bot\n✅ TP   {b['tp']}\n❌ SL   {b['sl']}\n"
            f"🎯 Réussite   {round(100 * b['tp'] / n)} %\n💰 Total   {b['pct']:+.2f} %")

def texte_resultats(etat, cid):
    return _texte_resultats(etat, cid) + "\n━━━━━━━━━━━━\n" + texte_bilan(etat)

def _texte_resultats(etat, cid):
    st = etat.get("stats", {}).get(cid)
    if not st:
        return "📈 Mes résultats\n━━━━━━━━━━━━\nAucun trade clôturé pour l'instant.\n👉 Appuie sur ✅ Je suis rentré quand tu prends une position."
    n = st["tp"] + st["sl"]
    l = ["📈 Mes résultats", "━━━━━━━━━━━━",
         f"✅ TP gagnés   {st['tp']}", f"❌ Stops touchés   {st['sl']}",
         f"🎯 Réussite   {round(100 * st['tp'] / n) if n else 0} %"]
    l += [f"{'⬆️' if v >= 0 else '⬇️'} {k}   {v:+,.2f} pts".replace(",", " ") for k, v in st["pts"].items()]
    l += [f"💰 Total   {st['pct']:+.2f} %", "━━━━━━━━━━━━", "Derniers trades :"]
    l += [f"{'✅' if h[1] > 0 else '❌'} {h[0]}   {h[2]:+.2f} %" for h in st["hist"][-5:]]
    return "\n".join(l)

def controle_entree(etat, m, d):
    """Vérification en direct au moment où l'abonné dit « Je suis rentré »."""
    try:
        r = analyse_marche(etat, MARCHES[m])
    except Exception as ex:
        print("controle", ex); return news_txt(etat)
    fl = lambda x: "✅" if x == d else "⚠️"
    r5 = r["r5"][-1]
    return (f"{fl(r['dirs'][4])} 15 min   {fl(r['dirs'][7])} 1 h   {fl(r['dirs'][9])} 4 h\n"
            f"⚡ RSI 5 min   {r5:.0f}{' (surcharge, normal)' if (r5 >= 65 if d == -1 else r5 <= 35) else ''}\n"
            f"{r['news']}")

def repondre(etat, cid, oui, mk=None):
    """✅ Je suis rentré : l'entrée et le stop sont FIGÉS pour cet abonné. 🚪 Je suis sorti : calcul automatique du résultat."""
    trades = [m for m in MARCHES if etat.get(m, {}).get("trade") and (mk is None or m == mk)]
    if oui:
        cands = [m for m in trades if not isinstance(etat[m]["trade"].get("qui", {}).get(cid), dict)]
        if not cands:
            _envoi_sur(cid, text=("🔴 Le bot n'a pas de position ouverte\n"
                                  "👉 Attends 🟢 J'ENTRE MAINTENANT\n"
                                  "🟠 / 🥇 Ou appuie sur Analyse BTC / Gold\n"
                                  "🔔 Je te préviens dès qu'il y en a une"), reply_markup=CLAVIER)
            return
        m = cands[0]; tr = etat[m]["trade"]
        e = prix_actuel(m) or tr["e"]
        tr.setdefault("qui", {})[cid] = {"e": e, "sl": tr["sl"], "tp1": tr["tp1"], "d": tr["d"], "t": int(time.time())}
        _envoi_sur(cid, reply_markup=CLAVIER, text=(
            f"👊 {ICONE.get(m, '')} {m}\n{SENS[tr['d']]}\n"
            f"📌 Entrée   {px(e)}\n"
            f"🛑 Stop   {px(tr['sl'])}\n"
            f"💰 TP1   {px(tr['tp1'])}\n"
            f"━━━━━━━━━━━━\n"
            f"🤖 Coach IA activé jusqu'au TP\n"
            f"{controle_entree(etat, m, tr['d'])}\n"
            f"━━━━━━━━━━━━\n"
            f"🔎 Je surveille toutes les 5 min :\n"
            f"🧭 15 min / 1 h / 4 h • ⚡ RSI • 🧱 niveaux • 🎤 news\n"
            f"📈 Résultat calculé tout seul"))
        return
    ouverts = [m for m in trades if isinstance(etat[m]["trade"].get("qui", {}).get(cid), dict) and not etat[m]["trade"]["qui"][cid].get("fini")]
    if not ouverts:
        for m in trades:
            etat[m]["trade"].setdefault("qui", {}).setdefault(cid, False)
        _envoi_sur(cid, text="👌 Pas de position ouverte. J'attends le prochain setup.", reply_markup=CLAVIER)
        return
    m = ouverts[0]; pos = etat[m]["trade"]["qui"][cid]
    noter(etat, cid, m, pos, prix_actuel(m) or pos["e"], "🚪 Sortie manuelle")

def cloturer_abonnes(etat, m, tr, sortie, motif):
    """Fin du trade : chaque abonné encore dedans est clôturé au même niveau (stop ou TP)."""
    for cid, pos in tr.get("qui", {}).items():
        if isinstance(pos, dict) and not pos.get("fini"):
            noter(etat, cid, m, pos, sortie, motif)

def traiter(etat, chats, updates):
    """Boutons cliqués et messages reçus. Renvoie la liste des téléphones qui demandent une analyse."""
    demandes = []
    for u in updates:
        etat["offset"] = u["update_id"] + 1
        mcm = u.get("my_chat_member")
        if mcm and mcm["chat"].get("type") in ("channel", "supergroup"):
            connecter_canal(etat, mcm)
            continue
        cb = u.get("callback_query")
        if cb:
            choix, _, mk = cb.get("data", "").partition(":")
            qui = str(cb["message"]["chat"]["id"])
            if choix in ("tvoffre", "tvok") and qui in proprio(etat):
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="OK")
                except Exception:
                    pass
                if choix == "tvoffre":
                    etat.setdefault("indic_offert", []).append(mk)
                    _envoi_sur(mk, text="🎁 L'indicateur t'est offert !\n👉 Appuie sur 🧩 Indicateur TradingView", reply_markup=CLAVIER)
                    _envoi_sur(qui, text="✅ Indicateur offert. J'attends son pseudo TradingView.")
                else:
                    etat.setdefault("indic", {}).setdefault(mk, {})["ok"] = True
                    _envoi_sur(mk, reply_markup=CLAVIER, text=(
                        "✅ Accès indicateur ouvert !\n📍 TradingView → Indicateurs → Sur invitation\n🧩 ALIGN MTF PRO\n"
                        + (f"🔗 {LIEN_INDICATEUR}\n" if LIEN_INDICATEUR else "") + "⏱ Mets-toi en vue 15 minutes"))
                    _envoi_sur(qui, text="👍 Abonné prévenu.")
                continue
            if choix in ("offrir", "retirer") and qui in proprio(etat):
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="OK")
                except Exception:
                    pass
                off = etat.setdefault("offerts", [])
                if choix == "offrir" and mk not in off:
                    off.append(mk); chats.add(mk)
                    if mk in etat.get("prospects", []):
                        etat["prospects"].remove(mk)
                    _envoi_sur(mk, text="🎁 Accès VIP offert !\n✅ Tu reçois maintenant toutes mes positions\n⬇️ Utilise les boutons en bas\n\n" + AVERTISSEMENT, reply_markup=CLAVIER)
                    _envoi_sur(qui, text=f"✅ Accès VIP offert à {etat.get('noms', {}).get(mk, mk)}",
                               reply_markup=json.dumps({"inline_keyboard": [[{"text": "⛔ Retirer l'accès", "callback_data": f"retirer:{mk}"}]]}))
                elif choix == "retirer" and mk in off:
                    off.remove(mk); chats.discard(mk)
                    _envoi_sur(qui, text=f"⛔ Accès retiré à {etat.get('noms', {}).get(mk, mk)}")
                continue
            if not autorise(etat, qui, cb["from"]["id"]):
                continue
            try:
                telegram("answerCallbackQuery", callback_query_id=cb["id"])
            except Exception:
                pass
            repondre(etat, str(cb["message"]["chat"]["id"]), choix == "in", mk)
            continue
        msg = u.get("message") or {}
        cid = str(msg.get("chat", {}).get("id", ""))
        if not cid:
            continue
        if msg.get("chat", {}).get("type") != "private":
            continue
        if not autorise(etat, cid, msg.get("from", {}).get("id")):
            chats.discard(cid)
            txtv = msg.get("text", "").lower()
            if cid not in etat.setdefault("prospects", []):
                etat["prospects"].append(cid)       # visiteur : signaux masqués en direct + 1 signal offert de temps en temps
                refuser(etat, cid)
                fr = msg.get("from", {})
                nom = (fr.get("first_name", "") + (" @" + fr["username"] if fr.get("username") else "")).strip() or cid
                etat.setdefault("noms", {})[cid] = nom
                for p in proprio(etat):    # le propriétaire peut offrir l'accès en 1 clic
                    _envoi_sur(p, text=f"👤 Nouveau visiteur : {nom}",
                               reply_markup=json.dumps({"inline_keyboard": [[{"text": "🎁 Offrir l'accès VIP", "callback_data": f"offrir:{cid}"}]]}))
            elif "analyse" in txtv:
                analyse_visiteur(etat, cid, marche_demande(txtv))
            elif "vip" in txtv or "/start" in txtv:
                refuser(etat, cid)
            else:
                _envoi_sur(cid, text="⌨️ Utilise les boutons en bas 👇", reply_markup=CLAVIER_VISITEUR)
            continue
        if cid in etat.get("prospects", []):
            etat["prospects"].remove(cid)
        if cid not in chats:
            chats.add(cid)
            telegram("sendMessage", chat_id=cid, text="✅ ALIGN MTF BOT activé. Mes positions BTC et Gold arrivent ici.\n⬇️ Utilise les boutons en bas.\n\n" + AVERTISSEMENT, reply_markup=CLAVIER)
        txt = msg.get("text", "").lower().replace("é", "e")
        if cid in etat.get("attente_tv", []) and msg.get("text") and not any(k in txt for k in ("analyse", "resultat", "rentre", "sorti", "indicateur")):
            recevoir_pseudo(etat, cid, msg["text"])
            continue
        if "indicateur" in txt:
            fr = msg.get("from", {})
            nom = (fr.get("first_name", "") + (" @" + fr["username"] if fr.get("username") else "")).strip() or cid
            etat.setdefault("noms", {})[cid] = nom
            menu_indicateur(etat, cid, nom)
            continue
        if "analyse" in txt or "etat" in txt:
            demandes.append((cid, marche_demande(txt)))
        elif "rentre" in txt or txt.strip() == "oui":
            repondre(etat, cid, True)
        elif "sorti" in txt or "non" in txt:
            repondre(etat, cid, False)
        elif "resultat" in txt:
            _envoi_sur(cid, text=texte_resultats(etat, cid), reply_markup=CLAVIER)
        elif cid not in proprio(etat) and not txt.startswith("/start"):
            _envoi_sur(cid, text="⌨️ Utilise les boutons en bas 👇", reply_markup=CLAVIER)
    return demandes
def proprio(etat):
    return set(etat.get("proprio", []))

def membre(etat, user_id):
    """Abonné à jour = membre de la chaîne VIP (Telegram retire automatiquement ceux qui ne paient plus)."""
    if not etat.get("canal") or not user_id:
        return False
    try:
        st = telegram("getChatMember", chat_id=etat["canal"], user_id=user_id)["result"]["status"]
        return st in ("member", "administrator", "creator")
    except Exception as ex:
        print("membre", ex); return False

def autorise(etat, cid, user_id):
    if POSITIONS_GRATUITES:
        return True
    return cid in proprio(etat) or cid in etat.get("offerts", []) or membre(etat, user_id)

def a_indicateur(etat, cid):
    """L'abonné a droit à l'indicateur : abonné payant à la chaîne, ou offert par le propriétaire."""
    return cid in proprio(etat) or cid in etat.get("indic_offert", []) or membre(etat, int(cid))

def bouton_indicateur(etat):
    lien = etat.get("lien")
    return json.dumps({"inline_keyboard": [[{"text": "🧩 Obtenir l'indicateur (≈ 10 € / mois)", "url": lien}]]}) if lien else None

def menu_indicateur(etat, cid, user):
    """Bouton 🧩 Indicateur : présentation, ou demande du pseudo TradingView si l'abonné y a droit."""
    info = etat.setdefault("indic", {}).get(cid, {})
    if a_indicateur(etat, cid):
        if info.get("ok"):
            _envoi_sur(cid, reply_markup=CLAVIER, text=(
                "🧩 Indicateur ALIGN MTF PRO\n✅ Ton accès est actif\n"
                f"👤 Pseudo   {info.get('tv', '?')}\n"
                "📍 TradingView → Indicateurs → Sur invitation\n" + (f"🔗 {LIEN_INDICATEUR}" if LIEN_INDICATEUR else "")))
            return
        etat.setdefault("attente_tv", [])
        if cid not in etat["attente_tv"]:
            etat["attente_tv"].append(cid)
        _envoi_sur(cid, reply_markup=CLAVIER, text=(
            "🧩 Indicateur ALIGN MTF PRO\n✅ Tu y as droit\n✍️ Écris ton pseudo TradingView\n(exemple : adel_khatra)"))
        return
    kw = {"reply_markup": bouton_indicateur(etat)} if etat.get("lien") else {}
    _envoi_sur(cid, text=(
        "🧩 Indicateur ALIGN MTF PRO — TradingView\n━━━━━━━━━━━━\n"
        "📊 Alignement des 11 unités de temps\n🟨 Zone d'entrée + Fibonacci\n🛑 Stop derrière la mèche\n"
        "💰 TP sur les grosses unités de temps\n⚡ Surcharge RSI + explosions\n━━━━━━━━━━━━\n"
        "🎁 Les positions restent gratuites ici\n💎 Indicateur ≈ 10 € / mois\n"
        "👉 Après paiement, reviens appuyer sur 🧩"), **kw)
    for p in proprio(etat):
        _envoi_sur(p, text=f"🧩 {user} s'intéresse à l'indicateur",
                   reply_markup=json.dumps({"inline_keyboard": [[{"text": "🎁 Offrir l'indicateur", "callback_data": f"tvoffre:{cid}"}]]}))

def recevoir_pseudo(etat, cid, pseudo):
    pseudo = pseudo.strip().lstrip("@")[:40]
    etat["attente_tv"].remove(cid)
    etat.setdefault("indic", {})[cid] = {"tv": pseudo, "ok": False}
    _envoi_sur(cid, text=f"👌 Pseudo reçu   {pseudo}\n⏳ Ton accès arrive très vite\n🔔 Je te préviens", reply_markup=CLAVIER)
    for p in proprio(etat):
        _envoi_sur(p, text=(f"🧩 Accès indicateur à donner\n👤 {etat.get('noms', {}).get(cid, cid)}\n📛 Pseudo TradingView   {pseudo}\n"
                            "👉 TradingView → ton script → Gérer l'accès → ajoute ce pseudo"),
                   reply_markup=json.dumps({"inline_keyboard": [[{"text": "✅ C'est fait, accès donné", "callback_data": f"tvok:{cid}"}]]}))

def bouton_payer(etat):
    lien = etat.get("lien")
    return json.dumps({"inline_keyboard": [[{"text": "🔓 Débloquer les positions (≈ 10 € / mois)", "url": lien}]]}) if lien else None

def analyse_visiteur(etat, cid, mq=None):
    """Analyse gratuite pour les visiteurs : tendance visible, plan de trade réservé VIP."""
    for nom_marche, pair in MARCHES.items():
        if mq and mq != nom_marche:
            continue
        try:
            _envoi_sur(cid, text=texte_etat(nom_marche, analyse_marche(etat, pair), etat.get(nom_marche), vip=False), reply_markup=CLAVIER_VISITEUR)
        except Exception as ex:
            print("analyse visiteur", ex)
    kw = {"reply_markup": bouton_payer(etat)} if etat.get("lien") else {}
    _envoi_sur(cid, text="🔒 Entrée, stop, TP et coaching en direct : réservés aux VIP 💎", **kw)

def refuser(etat, cid):
    _envoi_sur(cid, text="👋 ALIGN Signaux — BTC + Gold\n⬆️⬇️ Les positions arrivent ici en direct", reply_markup=CLAVIER_VISITEUR)
    kw = {"reply_markup": bouton_payer(etat)} if etat.get("lien") else {}
    _envoi_sur(cid, text=("👋 Bienvenue sur ALIGN Signaux (BTC + Gold)\n\n"
                          "🎁 Tu reçois GRATUITEMENT :\n• les alertes news 📰\n• les ouvertures de marché 🔔\n• 1 signal complet offert de temps en temps\n\n"
                          "🔒 Les autres positions arrivent MASQUÉES.\n"
                          "🔓 Pour tout voir (entrée, stop, TP, coaching Oui / Non, bouton Analyse) : abonne-toi avec le bouton ci-dessous, "
                          "puis reviens ici et tape /start.\n\n" + AVERTISSEMENT), **kw)

def masquer(texte):
    """Cache tous les prix (entrée, stop, TP) pour les visiteurs non abonnés."""
    texte = re.sub(r"[+-]\d+,\d+ %", "🔒 %", texte)
    return re.sub(r"(?<!\w)\d{1,3}(?: \d{3})*\.\d+", "🔒🔒🔒", texte).replace("\n\nTu es rentré ?", "")

def envoyer_prospects(etat, texte, signal):
    """Visiteurs : news en clair, positions masquées, sauf 1 signal offert par jour."""
    offert = signal and time.time() - etat.get("offert_t", 0) >= OFFERT_JOURS * 86400
    if offert:
        etat["offert_t"] = time.time()
        txt = "🎁🎁 SIGNAL OFFERT — pour te montrer que ça marche\n\n" + texte.replace("\n\nTu es rentré ?", "") + "\n\n🔓 Tous les signaux + coaching en direct : bouton ci-dessous"
    elif signal:
        txt = masquer(texte) + "\n\n🔒 Position masquée — réservée aux abonnés VIP"
    else:
        txt = texte
    kw = {"reply_markup": bouton_payer(etat)} if etat.get("lien") else {}
    for cid in list(etat.get("prospects", [])):
        try:
            telegram("sendMessage", chat_id=cid, text=txt, **kw)
        except Exception as ex:
            print("prospect", cid, ex)
            if "403" in str(ex):
                etat["prospects"].remove(cid)

def _envoi_sur(cid, **kw):
    try:
        telegram("sendMessage", chat_id=cid, **kw)
    except Exception as ex:
        print("envoi", cid, ex)

def connecter_canal(etat, mcm):
    """Le bot vient d'être ajouté (ou retiré) comme administrateur d'une chaîne : il la prend comme chaîne VIP."""
    chat, st = mcm["chat"], mcm["new_chat_member"]["status"]
    cid = str(chat["id"])
    if st == "administrator":
        etat["canal"] = cid; etat["canal_nom"] = chat.get("title", "")
        texte = f"✅ Bot connecté à la chaîne « {etat['canal_nom']} ». Les signaux y seront publiés automatiquement."
        try:
            if chat.get("type") == "channel" and not etat.get("lien"):
                res = telegram("createChatSubscriptionInviteLink", chat_id=cid, name="Abonnement VIP",
                               subscription_period=2592000, subscription_price=PRIX_STARS)["result"]
                etat["lien"] = res["invite_link"]
            if etat.get("lien"):
                texte += f"\n💳 Lien d'abonnement ({PRIX_STARS} ⭐ / mois) : {etat['lien']}\nC'est ce lien que tu partages pour vendre l'accès."
        except Exception as ex:
            texte += f"\n⚠️ Lien d'abonnement non créé automatiquement ({ex}). Crée-le dans la chaîne : Liens d'invitation → Abonnement mensuel."
        for p in proprio(etat):
            telegram("sendMessage", chat_id=p, text=texte)
    elif etat.get("canal") == cid and st in ("left", "kicked", "member"):
        etat.pop("canal", None)

def destinataires(etat, chats):
    """Téléphones qui reçoivent les signaux + la chaîne VIP."""
    return list(chats) + ([etat["canal"]] if etat.get("canal") else [])

def boutons(m):
    return json.dumps({"inline_keyboard": [[{"text": "✅ Je suis rentré", "callback_data": f"in:{m}"},
                                            {"text": "❌ Non", "callback_data": f"out:{m}"}]]})

def barre_pct(pct, n=10):
    pct = max(0, min(100, pct)); plein = round(pct / 100 * n)
    return "▓" * plein + "░" * (n - plein) + f" {pct:.0f}%"

def jauge(m, r, cle, cid=None, canal=False):
    """Jauge connectée (1 message mis à jour toutes les 5 min) : elle se charge quand la position approche."""
    tr = cle.get("trade"); p = r["m1"][-1]["c"]; d = r["confirme"]
    vit = abs(r["m1"][-1]["c"] - r["m1"][-31]["c"]) / 30 if len(r["m1"]) > 31 else 0   # vitesse moyenne / minute
    tete = f"{ICONE.get(m, '📊')} {m}   {px(p)}"
    pos = tr.get("qui", {}).get(cid) if tr else None
    if tr and (canal or (isinstance(pos, dict) and not pos.get("fini"))):
        e, t1, t2 = tr["e"], tr["tp1"], tr["tp2"]; cible = t2 if tr["statut"] == "tp1" else t1
        pct = 100 * tr["d"] * (p - e) / max(abs(cible - e), 1e-9)
        reste = abs(cible - p) / vit if vit > 0 else None
        return (f"{tete}\n🔌 EN POSITION   {SENS[tr['d']]}\n{barre_pct(pct)}\n"
                f"🎯 {'TP2' if tr['statut'] == 'tp1' else 'TP1'}   {px(cible)}" + (f"   ⏱ ≈ {reste:.0f} min" if reste and reste < 600 else "")
                + f"\n{r.get('news', '')}")
    if tr:
        titre, _ = verdict(r, cle)
        return f"{tete}\n🔌 Position ouverte   {SENS[tr['d']]}\n{titre.splitlines()[0]}"
    maj, n_ok = alignement(r)
    if not d:   # étape 1 : l'alignement se charge (0 → 40 %)
        return (f"{tete}\n🔌 Prochaine position\n{barre_pct(40 * n_ok / 3)}\n"
                f"🧭 Alignement   {n_ok}/3 ⏳" + (f"   {SENS[maj].split()[-2]} {SENS[maj].split()[-1]}" if maj else ""))
    if bloque_dw(r, d):
        return f"{tete}\n🔌 Prochaine position\n{barre_pct(40)}\n⛔ {SENS[d]} bloqué : prix {zone_txt(r['posD'])} Daily"
    o = cle.get("ordre")
    if not o:
        return f"{tete}\n🔌 Prochaine position   {SENS[d]}\n{barre_pct(40)}\n⏳ Je calcule la zone"
    # étape 2 : le prix approche de la zone (40 → 90 %), étape 3 : surcharge RSI (90 → 100 %)
    dep = abs(o["sl"] - o["e"]) * 3
    approche = 1 - min(abs(p - o["e"]) / max(dep, 1e-9), 1)
    pct = 95 if cle.get("attente_rsi") else 40 + 50 * approche
    reste = abs(p - o["e"]) / vit if vit > 0 else None
    etape = "⚡ Dans la zone : j'attends le RSI" if cle.get("attente_rsi") else \
            (f"⏱ Arrivée ≈ {reste:.0f} min" if reste and reste < 300 else "⏱ Le prix approche doucement")
    return (f"{tete}\n🔌 Prochaine position   {SENS[d]}\n{barre_pct(pct)}\n"
            f"🟨 Zone   {px(o.get('za', o['e']))} – {px(o.get('zb', o['e']))}\n{etape}")

def maj_jauge(m, r, cle, chats, canal=None):
    for cid in list(chats) + ([canal] if canal else []):
        txt = jauge(m, r, cle, cid, cid == canal)
        mid = cle.get("jauge", {}).get(cid)
        try:
            if txt and mid:
                if cle.setdefault("jauge_txt", {}).get(cid) != txt:
                    telegram("editMessageText", chat_id=cid, message_id=mid, text=txt)
            elif txt:
                res = telegram("sendMessage", chat_id=cid, text=txt, disable_notification="true")
                cle.setdefault("jauge", {})[cid] = res["result"]["message_id"]
            if txt:
                cle.setdefault("jauge_txt", {})[cid] = txt
            elif mid:
                telegram("deleteMessage", chat_id=cid, message_id=mid)
                cle["jauge"].pop(cid, None)
        except Exception as ex:
            print("jauge", ex)

# ───────── Annonces économiques et ouvertures de marché ─────────
def calendrier(etat, maintenant):
    """Calendrier gratuit (Forex Factory), rafraîchi toutes les heures. Annonces à fort impact USD (BTC et Gold y réagissent)."""
    cache = etat.setdefault("cal", {})
    if maintenant - cache.get("t", 0) > 3600:
        try:
            brut = http_json("https://nfs.faireconomy.media/ff_calendar_thisweek.json")
            cache["ev"] = [dict(titre=x["title"], pays=x["country"], t=int(datetime.datetime.fromisoformat(x["date"]).timestamp()),
                                prev=x.get("forecast", ""), avant=x.get("previous", ""))
                           for x in brut if x.get("impact") == "High" and x.get("country") in ("USD",)]
            cache["t"] = maintenant
        except Exception as ex:
            print("calendrier", ex)
    return cache.get("ev", [])

def heure(ts):
    return datetime.datetime.fromtimestamp(ts, PARIS).strftime("%H:%M")

def annonces_et_sessions(etat, maintenant, derniers):
    """Messages : programme du jour, annonce dans 30 min, ouvertures Londres / New York (avec alerte compression)."""
    out = []; vus = etat.setdefault("vus", [])
    jour = datetime.datetime.fromtimestamp(maintenant, PARIS)
    ev = calendrier(etat, maintenant)
    cle_j = jour.strftime("%Y-%m-%d")
    # Programme du jour (une fois, après 7 h à Paris)
    if jour.hour >= 7 and f"prog{cle_j}" not in vus:
        vus.append(f"prog{cle_j}")
        aujourdhui = [e for e in ev if datetime.datetime.fromtimestamp(e["t"], PARIS).date() == jour.date()]
        if aujourdhui:
            out.append("📅 Annonces importantes aujourd'hui (heure de Paris) :\n" + "\n".join(
                f"• {heure(e['t'])} {e['titre']} (prévu {e['prev'] or '?'}, avant {e['avant'] or '?'})" for e in aujourdhui)
                + "\n→ Pas de nouvelle entrée 15 min avant et après. Volatilité forte possible.")
        elif jour.weekday() < 5:
            out.append("📅 Aucune annonce majeure US aujourd'hui.")
    # Rappel 30 min avant chaque annonce
    for e in ev:
        reste = e["t"] - maintenant
        fin = heure(e["t"] + 15 * 60)
        if 6 * 60 < reste <= 30 * 60 and f"ev{e['t']}{e['titre']}" not in vus:
            vus.append(f"ev{e['t']}{e['titre']}")
            out.append(f"⚠️⚠️ NEWS USA dans {round(reste / 60)} min ({heure(e['t'])})\n📰 {e['titre']}\n\n"
                       f"🟥 N'ouvre AUCUN trade\n🛡 Déjà en position ? Vérifie que ton STOP est bien placé\n"
                       f"💥 Le prix peut bouger très fort dans les 2 sens\n⏳ On reprend à {fin}")
        if 0 <= reste <= 6 * 60 and f"ev5{e['t']}{e['titre']}" not in vus:
            vus.append(f"ev5{e['t']}{e['titre']}")
            out.append(f"🚨🚨🚨 NEWS DANS {max(1, round(reste / 60))} MIN — {e['titre']}\n🟥 Ne touche à rien\n🛡 Stop en place ? OK, on attend")
        if 15 * 60 <= -reste <= 25 * 60 and f"evfin{e['t']}{e['titre']}" not in vus:
            vus.append(f"evfin{e['t']}{e['titre']}")
            out.append(f"✅ News passée ({e['titre']}). 🟩 Le bot reprend la recherche d'entrées.")
    # Ouvertures de marché (jours de semaine)
    if jour.weekday() < 5:
        for nom, zone, h, mn in (("Londres", "Europe/London", 8, 0), ("New York (Wall Street)", "America/New_York", 9, 30)):
            loc = datetime.datetime.now(ZoneInfo(zone)).replace(hour=h, minute=mn, second=0, microsecond=0)
            t_ouv = int(loc.timestamp())
            if 0 <= t_ouv - maintenant <= 15 * 60 and f"ouv{nom}{cle_j}" not in vus:
                vus.append(f"ouv{nom}{cle_j}")
                comp = [m for m, r in derniers.items() if sum(r["sqzs"][4:10]) >= 3]
                out.append(f"🔔 Ouverture de {nom} à {heure(t_ouv)} (dans {round((t_ouv - maintenant) / 60)} min). Volatilité forte attendue."
                           + (f"\n⚡ {', '.join(comp)} comprimé sur plusieurs UT : explosion probable à l'ouverture, attends la direction." if comp else ""))
    del vus[:-200]
    return out

def news_txt(etat, heures=4):
    """Annonces ET discours USA à fort impact (Fed, CPI, NFP…) : BTC et Gold y réagissent."""
    maintenant = time.time()
    ev = sorted((e for e in etat.get("cal", {}).get("ev", []) if -15 * 60 <= e["t"] - maintenant <= heures * 3600), key=lambda e: e["t"])
    if not etat.get("cal", {}).get("ev") and not etat.get("cal", {}).get("t"):
        return "📰 News : calendrier indisponible"
    if not ev:
        return f"✅ Aucune annonce ni discours d'ici {heures} h"
    e = ev[0]; mn = round((e["t"] - maintenant) / 60)
    ic = "🎤" if "speak" in e["titre"].lower() else "📰"
    quand = f"en cours" if mn <= 0 else f"dans {mn} min" if mn < 60 else f"dans {mn // 60} h {mn % 60:02d}"
    return f"⚠️ {ic} {e['titre']} {heure(e['t'])} ({quand})"

def prochaine_news(etat):
    """Prochaine annonce ou discours USA à fort impact (BTC et Gold y réagissent)."""
    maintenant = time.time()
    ev = sorted((e for e in etat.get("cal", {}).get("ev", []) if e["t"] >= maintenant - 15 * 60), key=lambda e: e["t"])
    if not ev:
        return "Pas de news majeure prévue cette semaine"
    e = ev[0]
    jour = datetime.datetime.fromtimestamp(e["t"], PARIS).strftime("%d/%m")
    return f"Prochaine news   {jour} {heure(e['t'])} {e['titre']}"

def annonce_proche(etat, maintenant):
    return any(abs(e["t"] - maintenant) <= 15 * 60 for e in etat.get("cal", {}).get("ev", []))

# ───────── Agent : suit le trade du début à la fin ─────────
def fmt_trade(m, tr, p=None):
    """Carte visuelle pour débutant : couleurs + échelle des prix dessinée de haut en bas."""
    d = tr["d"]
    tete = ("🟩🟩🟩  TRÈS LONG " if d == 1 else "🟥🟥🟥  TRÈS SHORT ") + m + ("  🟩🟩🟩" if d == 1 else "  🟥🟥🟥")
    za, zb = tr.get("za", tr["e"]), tr.get("zb", tr["e"])
    bougie = "en dessous de la dernière bougie basse" if d == 1 else "au-dessus de la dernière bougie haute"
    risque = abs(tr["e"] - tr["sl"]); gain = abs(tr["tp1"] - tr["e"])
    barres = lambda x: "▮" * max(1, min(10, round(x / max(risque, 1e-9) * 2)))
    # Échelle des prix, du plus haut au plus bas
    pts = [(tr["sl"], "🛑", "STOP"), (tr["tp1"], "💰", "TP1"), (tr["tp2"], "🏁", "TP2")]
    pts += [(zb, "🟨", "ENTRÉE haut"), (za, "🟨", "ENTRÉE bas")] if abs(zb - za) > 1e-9 else [(tr["e"], "🟨", "ENTRÉE")]
    if p is not None:
        pts.append((p, "👉", "PRIX ACTUEL"))
    echelle = "\n".join(f"{ic} {px(v)}  {nom}" for v, ic, nom in sorted(pts, key=lambda z: -z[0]))
    pct = lambda v: f"{(v - tr['e']) / tr['e'] * 100:+.2f} %".replace(".", ",")
    meche = "la mèche du dernier creux" if d == 1 else "la mèche du dernier sommet"
    return (f"{tete}\n"
            f"⏱ Vue 15 minutes\n\n"
            f"📍 Prix de référence (Kraken) :\n{echelle}\n\n"
            f"📐 Sur TA plateforme (les prix peuvent être différents) :\n"
            f"🟨 Entrée : {'repli' if d == 1 else 'rebond'} vers la moitié du dernier mouvement\n"
            f"🛑 Stop : juste {'sous' if d == 1 else 'au-dessus de'} {meche} ({pct(tr['sl'])})\n"
            f"💰 TP1 : {tr['n1']} ({pct(tr['tp1'])}) → stop à l'entrée\n"
            f"🏁 TP2 : {tr['n2']} ({pct(tr['tp2'])})\n\n"
            f"Risque {barres(risque)}\nGain   {barres(gain)}  (x{tr['rr']:.1f})\n\n{MINI_AVERT}")

def zone_txt(pos):
    return "tout en HAUT" if pos >= 0.85 else "en haut" if pos >= 0.65 else "tout en BAS" if pos <= 0.15 else "en bas" if pos <= 0.35 else "au milieu"

def plan_entree(r, d, p):
    """Entrée au prix actuel, stop derrière le dernier creux/sommet 15m et le niveau 1h, TP sur 1h / 4h / Daily."""
    a = r["atr"]; b = r["b15"]
    if d == 1:
        swing = min(x["l"] for x in b) - a * 0.2
        sup1h = [v for v, n in r["grosses"] if n == "1h" and v < p - a * 0.3]
        sl = min(swing, max(sup1h) - a * 0.3) if sup1h and p - max(sup1h) < 3 * a else swing
    else:
        swing = max(x["h"] for x in b) + a * 0.2
        res1h = [v for v, n in r["grosses"] if n == "1h" and v > p + a * 0.3]
        sl = max(swing, min(res1h) + a * 0.3) if res1h and min(res1h) - p < 3 * a else swing
    mini = max(a, p * 0.0008)
    if abs(p - sl) < mini:
        sl = p - d * mini
    risque = abs(p - sl)
    cibles = sorted([z for z in r["grosses"] if d * (z[0] - p) >= risque * GAIN_MIN], key=lambda z: d * z[0])
    t1 = cibles[0] if cibles else (p + d * risque * 2, "projection 2 x le risque")
    loin = [z for z in cibles if d * (z[0] - t1[0]) >= a]
    t2 = loin[0] if loin else (p + d * risque * 3.5, "projection 3,5 x le risque")
    return dict(d=d, e=p, sl=sl, tp1=t1[0], n1=(("résistance " if d == 1 else "support ") + t1[1]) if t1[1] in ("1h", "4h", "Daily") else t1[1],
                tp2=t2[0], n2=(("résistance " if d == 1 else "support ") + t2[1]) if t2[1] in ("1h", "4h", "Daily") else t2[1],
                rr=abs(t1[0] - p) / risque)

def point_entree(r, d, p):
    """Ordre limite au point le plus précis : confluence retracement 50-61,8 % du dernier mouvement 15m
    + résistance/support 15m/1h/4h + EMA 20 (15m). Stop derrière le sommet/creux du mouvement."""
    a = r["atr"]; b = r["b15"][-24:]
    H = max(x["h"] for x in b); L = min(x["l"] for x in b)
    if d == -1:   # SHORT : on vend un rebond vers une résistance
        z50, z618, z786 = L + 0.5 * (H - L), L + 0.618 * (H - L), L + 0.786 * (H - L)
        cand = [(v, n) for v, n in r["niveaux"] if z50 - 0.3 * a <= v <= z786 + 0.3 * a and n in ("15m", "1h", "4h")]
        if cand:
            e, src = min(cand, key=lambda z: abs(z[0] - z618)); src = f"résistance {src} + retracement Fibonacci"
        elif z50 <= r["ema15"] <= z786:
            e, src = r["ema15"], "EMA 20 (15m) + retracement Fibonacci"
        else:
            e, src = z618, "retracement Fibonacci 61,8 %"
        e = max(e, p)
        res4h = [v for v, n in r["grosses"] if n == "4h" and e < v < e + 3 * a]
        res1h = res4h or [v for v, n in r["grosses"] if n == "1h" and e < v < e + 3 * a]   # résistance la plus costaud d'abord (4h)
        sl = max(H, min(res1h) if res1h else H) + 0.3 * a
    else:         # LONG : on achète un repli vers un support
        z50, z618, z786 = H - 0.5 * (H - L), H - 0.618 * (H - L), H - 0.786 * (H - L)
        cand = [(v, n) for v, n in r["niveaux"] if z786 - 0.3 * a <= v <= z50 + 0.3 * a and n in ("15m", "1h", "4h")]
        if cand:
            e, src = min(cand, key=lambda z: abs(z[0] - z618)); src = f"support {src} + retracement Fibonacci"
        elif z786 <= r["ema15"] <= z50:
            e, src = r["ema15"], "EMA 20 (15m) + retracement Fibonacci"
        else:
            e, src = z618, "retracement Fibonacci 61,8 %"
        e = min(e, p)
        sup4h = [v for v, n in r["grosses"] if n == "4h" and e - 3 * a < v < e]
        sup1h = sup4h or [v for v, n in r["grosses"] if n == "1h" and e - 3 * a < v < e]   # support le plus costaud d'abord (4h)
        sl = min(L, max(sup1h) if sup1h else L) - 0.3 * a
    if abs(e - sl) < max(a, e * 0.0008):
        sl = e - d * max(a, e * 0.0008)
    risque = abs(e - sl)
    cibles = sorted([z for z in r["grosses"] if d * (z[0] - e) >= risque * GAIN_MIN], key=lambda z: d * z[0])
    t1 = cibles[0] if cibles else (e + d * risque * 2, "projection 2 x le risque")
    loin = [z for z in cibles if d * (z[0] - t1[0]) >= a]
    t2 = loin[0] if loin else (e + d * risque * 3.5, "projection 3,5 x le risque")
    nom = lambda z: (("résistance " if d == 1 else "support ") + z[1]) if z[1] in ("1h", "4h", "Daily") else z[1]
    # Zone d'entrée : du retracement 50 % jusqu'au 78,6 %, jamais à moins de 25 % du risque avant le stop
    if d == -1:
        za, zb = min(e, max(z50, p)), max(e, z786); zb = min(zb, sl - 0.25 * (sl - e))
    else:
        zb, za = max(e, min(z50, p)), min(e, z786); za = max(za, sl + 0.25 * (e - sl))
    return dict(d=d, e=e, sl=sl, tp1=t1[0], n1=nom(t1), tp2=t2[0], n2=nom(t2), rr=abs(t1[0] - e) / risque, src=src,
                za=min(za, zb), zb=max(za, zb), f50=z50, f618=z618, f786=z786)

def coach(etat, m, r, cle):
    """Agent individuel : messages courts envoyés UNIQUEMENT aux abonnés qui ont dit « Je suis rentré »."""
    tr = cle.get("trade")
    if not tr:
        return
    dedans = [c for c, pos in tr.get("qui", {}).items() if isinstance(pos, dict) and not pos.get("fini")]
    if not dedans:
        return
    d, e = tr["d"], tr["e"]; p = r["m1"][-1]["c"]
    cible = tr["tp2"] if tr["statut"] == "tp1" else tr["tp1"]
    prog = d * (p - e) / max(abs(cible - e), 1e-9)        # 1 = objectif atteint
    perte = d * (e - p) / max(abs(e - tr["sl"]), 1e-9)    # 1 = stop touché
    vu = tr.setdefault("coach", [])
    msgs = []
    fleche = "⬆️" if d == 1 else "⬇️"
    if prog >= 0.7 and f"presque{tr['statut']}" not in vu:
        vu.append(f"presque{tr['statut']}")
        msgs.append(f"💪 {m}\nTiens bon, presque arrivé\n{fleche} {barre_pct(prog * 100)}\n🎯 Objectif   {px(cible)}")
    if 0.3 <= prog < 0.7 and "bon" not in vu and tr["statut"] == "entree":
        vu.append("bon")
        msgs.append(f"✅ {m}\nÇa part dans le bon sens\n{fleche} {barre_pct(prog * 100)}")
    if perte >= 0.6 and "danger" not in vu:
        vu.append("danger")
        msgs.append(f"⚠️ {m}\nLe prix revient contre nous\n🛑 Stop   {px(tr['sl'])}\n🙅 On ne le déplace pas")
    # Petites perturbations pendant le trade (messages rassurants, 1 fois toutes les 30-45 min max)
    tps = tr.setdefault("coach_t", {})
    def libre(cle_m, minutes):
        if time.time() - tps.get(cle_m, 0) >= minutes * 60:
            tps[cle_m] = time.time(); return True
        return False
    r5 = r["r5"][-1]
    surcharge5 = (r5 >= 65) if d == -1 else (r5 <= 35)
    grandes_ok = r["dirs"][7] == d and r["dirs"][9] == d
    if 0.25 <= perte < 0.6 and grandes_ok and libre("perturb", 30):
        msgs.append(f"😌 {m}\nPetite perturbation, c'est normal\n"
                    + (f"⚡ RSI 5 min   {r5:.0f} (surcharge)\n" if surcharge5 else "")
                    + f"✅ 1 h   {fleche}\n✅ 4 h   {fleche}\n"
                    f"🎯 Cap sur le TP\n🛑 Stop   {px(tr['sl'])}")
    if 0 < prog < 0.7:
        a = r["atr"]
        obstacle = [(v, n) for v, n in r["niveaux"] if n in ("15m", "1h", "4h") and abs(v - p) <= 0.3 * a and d * (cible - v) > 0]
        if obstacle and libre("mur", 45):
            v, n = obstacle[0]
            msgs.append(f"🧱 {m}\n{'Résistance' if d == 1 else 'Support'} {n}   {px(v)}\n"
                        f"⏸ Pause normale, patience\n🎯 S'il casse : cap sur le TP")
    # Plan annulé : la 4h se retourne, ou la 15m ET la 1h passent contre nous
    dirs = r["dirs"]
    if (dirs[9] == -d or (dirs[4] == -d and dirs[7] == -d)) and "annule" not in vu and tr["statut"] == "entree":
        vu.append("annule")
        msgs.append(f"❌ {m}\nPlan annulé\n{'⬇️' if d == 1 else '⬆️'} Les unités de temps se retournent\n✂️ Je coupe ma position")
    # Annonce économique pendant la position
    for ev in etat.get("cal", {}).get("ev", []):
        reste = ev["t"] - time.time()
        if 0 <= reste <= 30 * 60 and f"news{ev['t']}" not in vu:
            vu.append(f"news{ev['t']}")
            msgs.append(f"📰 {m}\nNews dans   {round(reste / 60)} min\n"
                        + (f"🔒 Stop à l'entrée   {px(e)}" if prog > 0.2 else "✂️ Le trade n'avance pas\n✂️ Je coupe avant la news"))
    for c in dedans:
        for t in msgs:
            _envoi_sur(c, text=t, reply_markup=CLAVIER)

def agent(m, r, cle, ferme):
    """Agent : alignement 15m/1h/4h → repli en surcharge RSI → entrée parfaite → suivi jusqu'au TP2."""
    out = []
    tr = cle.get("trade")
    depuis = cle.get("t1m", 0)
    bougies = [x for x in r["m1"] if x["t"] > depuis] or r["m1"][-1:]
    cle["t1m"] = r["m1"][-1]["t"]
    p = r["m1"][-1]["c"]
    hi = max(x["h"] for x in bougies); lo = min(x["l"] for x in bougies)
    d = r["confirme"]
    r5, r5p = r["r5"][-1], r["r5"][-2]
    ctx = f"Contexte : {zone_txt(r['posD'])} de la zone Daily, {zone_txt(r['posW'])} de la zone Weekly."

    # ── Pas de trade : alignement 15m + 1h + 4h obligatoire, puis ordre limite au point précis ──
    if not tr:
        if not d:
            if cle.get("aligne"):
                out.append(f"⚪ {m} : alignement 15m / 1h / 4h perdu. Ordre annulé, j'attends.")
            cle["aligne"] = 0; cle["prep"] = False; cle.pop("ordre", None)
            return out
        # Daily / Weekly : pas de short tout en bas, pas de long tout en haut
        bloque = bloque_dw(r, d)
        o = point_entree(r, d, p)
        if cle.get("aligne") != d:
            cle["aligne"] = d; cle["prep"] = False
            if bloque:
                out.append(f"🧭 {m} aligné {'▲' if d == 1 else '▼'} sur 15m/1h/4h, MAIS prix {zone_txt(r['posD'])} Daily / {zone_txt(r['posW'])} Weekly.\n"
                           f"⛔ Pas de {'long' if d == 1 else 'short'} ici : risque de rebond. J'attends un meilleur prix.")
            else:
                cle["ordre"] = o
                out.append(f"🔔 JE PRÉPARE UNE POSITION — {m} {'monte' if d == 1 else 'descend'} sur 15m, 1h et 4h ✅✅✅\n"
                           f"⏳ Je n'entre pas encore : j'attends que le prix vienne dans la zone 🟨\n"
                           f"👀 Mets-toi en vue 15 minutes\n"
                           f"🕯 Repère {'le dernier creux (mèche du bas)' if d == 1 else 'le dernier sommet (mèche du haut)'}\n"
                           f"🟨 L'entrée sera à peu près {'au-dessus de ce creux' if d == 1 else 'sous ce sommet'}\n"
                           f"🚦 Attends mon feu vert 🟢\n\n"
                           f"{fmt_trade(m, o, p)}\n\n"
                           f"📐 Zone = Fibonacci 50 → 78,6 % + {o['src'].split(' + ')[0]}{ferme}")
        if bloque or o["rr"] < 1.5:
            return out
        # On ajuste le point tant que le prix n'est pas encore arrivé (les niveaux bougent)
        if not cle.get("prep"):
            cle["ordre"] = o
        o = cle.get("ordre", o)
        dist = d * (p - o["e"])       # < 0 = le prix n'est pas encore arrivé au point d'entrée
        touche = (lo <= o["e"]) if d == 1 else (hi >= o["e"])
        if not cle.get("prep") and abs(p - o["e"]) <= max(0.6 * r["atr"], abs(o["e"] - o["sl"]) * 0.5):
            cle["prep"] = True
            out.append(f"🟡🟡 BIENTÔT — {m} approche de la zone 🟨\n👉 Prix {px(p)}  →  zone {px(o.get('za', o['e']))} – {px(o.get('zb', o['e']))}\n📲 Je prépare mon ordre {SENS[d]}, stop {px(o['sl'])}\n⏳ J'attends le signal 🟢")
        # Surcharge sur PLUSIEURS UT : 5m obligatoire + au moins 1 parmi 10m/15m/30m + confirmation 1h
        R = dict(zip(UT, r["rsis"]))
        if d == 1:
            r5ok = min(r["r5"]) <= 35
            petites = [u for u in ("10", "15", "30") if R[u] <= 40]
            conf1h = R["1h"] <= 48
        else:
            r5ok = max(r["r5"]) >= 65
            petites = [u for u in ("10", "15", "30") if R[u] >= 60]
            conf1h = R["1h"] >= 52
        surcharge = r5ok and len(petites) >= 1 and conf1h
        detail = f"RSI 5m {r5:.0f} • " + " • ".join(f"{u}m {R[u]:.0f}" for u in ("10", "15", "30")) + f" • 1h {R['1h']:.0f}"
        if touche and not ((lo <= o["sl"]) if d == 1 else (hi >= o["sl"])):
            if r.get("annonce"):
                if not cle.get("pause"):
                    out.append(f"⏸ {m} : prix sur le point d'entrée, mais annonce économique dans moins de 15 min. On ne rentre pas.")
                cle["pause"] = True
                return out
            cle["pause"] = False
            if surcharge:
                tr = dict(o, statut="entree", cree=r["t"], encore=0)
                cle["trade"] = tr; cle["prep"] = False; cle["attente_rsi"] = False; cle.pop("ordre", None)
                niveau = "Fibonacci" not in o["src"] or "+" in o["src"]   # confluence avec un niveau 15m / 1h / 4h ou l'EMA
                checks = [("15 min • 1 h • 4 h alignées", True), ("Daily / Weekly favorables", True),
                          ("Zone Fibonacci 50 – 78,6 %", True), ("Niveau 15m / 1h / 4h ou EMA", niveau),
                          (f"RSI en surcharge ({', '.join(['5m'] + [u + 'm' for u in petites])})", True), ("Confirmé en 1 h", True),
                          ("Pas de news proche", True), (f"Gain / risque x{o['rr']:.1f}", o["rr"] >= 1.5)]
                score = sum(ok for _, ok in checks)
                liste = "\n".join(f"{'✅' if ok else '➖'} {t}" for t, ok in checks)
                out.append((f"🟢🟢🟢 J'ENTRE MAINTENANT — {m} 🟢🟢🟢\n🎯 Confiance   {score}/{len(checks)}\n{liste}\n\n{fmt_trade(m, tr, p)}{ferme}\n\nTu es rentré ?", boutons(m)))
            elif not cle.get("attente_rsi"):
                cle["attente_rsi"] = True
                out.append(f"👀 {m} : prix DANS la zone 🟨 — j'attends la confirmation RSI ⏳\n{detail}")
        elif d * (p - o["e"]) > 0.35 * abs(o["tp1"] - o["e"]) and cle.get("prep"):
            out.append(f"⛔ {m} : le prix est parti sans toucher le point d'entrée. Trop tard, je recalcule le prochain point.")
            cle["prep"] = False; cle["attente_rsi"] = False; cle.pop("ordre", None)
        return out

    # ── Trade en cours ──
    d, e, sl, t1, t2 = tr["d"], tr["e"], tr["sl"], tr["tp1"], tr["tp2"]
    touche_sl = (lo <= sl) if d == 1 else (hi >= sl)
    touche_t1 = (hi >= t1) if d == 1 else (lo <= t1)
    touche_t2 = (hi >= t2) if d == 1 else (lo <= t2)
    progres = d * (p - e) / max(abs(t1 - e), 1e-9)

    if tr["statut"] == "entree":
        if touche_sl:
            out.append(f"❌ {m} : stop {px(sl)} touché. On coupe, prochain setup bientôt.")
            cle["fin"] = [tr, sl, "🛑 Stop touché"]
            cle.pop("trade"); cle["aligne"] = 0; return out
        if touche_t1:
            tr["statut"] = "tp1"; tr["sl"] = e
            out.append(f"🎯 {m} : TP1 {px(t1)} touché !\n→ Sécurise une partie\n→ Stop à l'entrée {px(e)}\n→ On vise TP2 {px(t2)}")
            return out
        if progres < 0.25:
            if tr["encore"] < 1 and r["t"] - tr["cree"] >= 900:
                tr["encore"] += 1
                if True:
                    out.append((f"👍 {m} : tu peux encore rentrer ({px(p)}). Stop {px(sl)} • TP1 {px(t1)}\n\nTu es rentré ?", boutons(m)))
        elif not tr.get("tard"):
            tr["tard"] = True
            if not any(isinstance(v, dict) for v in tr.get("qui", {}).values()):
                out.append(f"⛔ {m} : trop tard pour rentrer. On attend le prochain setup.")
                cle.pop("trade"); cle["aligne"] = 0
            else:
                out.append(f"⛔ {m} : trop tard pour rentrer maintenant. Ceux qui sont dedans : on continue vers le TP1 {px(t1)}.")
        return out

    if tr["statut"] == "tp1":
        if touche_t2:
            # Déplacement du TP : tendance 4h toujours dans le bon sens et RSI 15m pas en excès → on vise plus loin
            suivants = sorted([z for z in r["grosses"] if d * (z[0] - t2) >= r["atr"]], key=lambda z: d * z[0])
            excès = (r["r15"] >= 70) if d == 1 else (r["r15"] <= 30)
            if r["dirs"][9] == d and not excès and suivants and not tr.get("etendu"):
                tr["etendu"] = True; tr["sl"] = t1; tr["tp2"] = suivants[0][0]
                out.append(f"📈 {m} : TP2 touché, la tendance continue.\n→ Stop au TP1 {px(t1)}\n→ Nouvel objectif {px(suivants[0][0])}")
                return out
            out.append(f"🏆 {m} : objectif final {px(t2)} atteint. Trade terminé, bravo !")
            cle["fin"] = [tr, t2, "🏆 Objectif final"]
            cle.pop("trade"); cle["aligne"] = 0; return out
        if (lo <= tr["sl"]) if d == 1 else (hi >= tr["sl"]):
            out.append(f"↩️ {m} : sortie au stop sécurisé {px(tr['sl'])}. TP1 encaissé, pas de perte.")
            cle["fin"] = [tr, t1 if d * (tr["sl"] - t1) < 0 else tr["sl"], "💰 TP1 encaissé"]
            cle.pop("trade"); cle["aligne"] = 0; return out
    return out

# ───────── Programme ─────────
def main():
    etat = {}
    if os.path.exists(ETAT_FICHIER):
        etat = json.load(open(ETAT_FICHIER))
    chats = set(etat.get("chats", []))
    if os.environ.get("TELEGRAM_CHAT_ID"):
        chats.add(os.environ["TELEGRAM_CHAT_ID"].strip())
    if "proprio" not in etat:           # les téléphones déjà inscrits = le propriétaire (accès gratuit et permanent)
        etat["proprio"] = sorted(chats)
    if POSITIONS_GRATUITES and etat.get("prospects"):
        chats |= set(etat["prospects"]); etat["prospects"] = []

    # Messages reçus et boutons
    debut = time.time()
    demandes = []
    if TOKEN:
        demandes = traiter(etat, chats, telegram("getUpdates", offset=etat.get("offset", 0), timeout=0).get("result", []))
        if etat.get("clavier") != 5:
            for cid in chats:
                _envoi_sur(cid, text="🆕 Nouveaux boutons\n🟠 Analyse BTC\n🥇 Analyse Gold\n🚦 Chaque analyse te dit si tu peux entrer ou pas", reply_markup=CLAVIER)
            for cid in etat.get("prospects", []):
                _envoi_sur(cid, text="🆕 Boutons : 🟠 Analyse BTC • 🥇 Analyse Gold • 💎 Devenir VIP", reply_markup=CLAVIER_VISITEUR)
            etat["clavier"] = 5
        if not etat.get("bot"):
            try:
                etat["bot"] = telegram("getMe")["result"]["username"]
            except Exception as ex:
                print("getMe", ex)
        # Chaîne VIP connectée mais lien d'abonnement pas encore créé : on réessaie à chaque lancement
        if etat.get("canal") and not etat.get("lien"):
            try:
                etat["lien"] = telegram("createChatSubscriptionInviteLink", chat_id=etat["canal"], name="Abonnement VIP",
                                        subscription_period=2592000, subscription_price=PRIX_STARS)["result"]["invite_link"]
                for p in proprio(etat):
                    telegram("sendMessage", chat_id=p, text=f"💳 Lien d'abonnement VIP créé ({PRIX_STARS} ⭐ / mois, ≈ 10 €) :\n{etat['lien']}\n\n👉 C'est ce lien que tu partages pour vendre l'accès.")
            except Exception as ex:
                print("lien abonnement", ex)
        # Toutes les heures : on retire les abonnés qui n'ont pas renouvelé
        if etat.get("canal") and time.time() - etat.get("purge", 0) > 3600:
            etat["purge"] = time.time()
            for cid, info in list(etat.get("indic", {}).items()):
                if info.get("ok") and not a_indicateur(etat, cid):
                    info["ok"] = False
                    _envoi_sur(cid, text="⏸ Ton abonnement indicateur n'est plus actif.", reply_markup=bouton_indicateur(etat))
                    for p in proprio(etat):
                        _envoi_sur(p, text=f"⛔ Retire l'accès TradingView de   {info.get('tv')}\n(abonnement non renouvelé)")
            for cid in [c for c in chats if c not in proprio(etat) and c not in etat.get("offerts", []) and not POSITIONS_GRATUITES]:
                if not membre(etat, int(cid)):
                    chats.discard(cid)
                    try:
                        telegram("sendMessage", chat_id=cid, text="⏸ Ton abonnement VIP n'est plus actif. Les signaux sont en pause."
                                 + (f"\nRenouveler : {etat['lien']}" if etat.get("lien") else ""))
                    except Exception:
                        pass

    envois, derniers = [], {}
    calendrier(etat, int(time.time()))
    for nom_marche, pair in MARCHES.items():
        try:
            r = analyser(pair)
        except Exception as ex:
            print(nom_marche, "erreur", ex); continue
        cle = etat.setdefault(nom_marche, {})
        r["annonce"] = annonce_proche(etat, int(time.time()))
        r["news"] = news_txt(etat)
        ferme = "" if nom_marche == "BTC" or cme_ouvert(r["t"]) else "\n⚠️ Futures CME fermés en ce moment (Topstep) : signal à titre indicatif."
        envois += agent(nom_marche, r, cle, ferme)
        if TOKEN:
            coach(etat, nom_marche, r, cle)
            if cle.get("fin"):
                trf, sortie, motif = cle.pop("fin")
                cloturer_abonnes(etat, nom_marche, trf, sortie, motif)
                # Bilan du bot (toutes ses positions, que des abonnés soient rentrés ou non)
                bil = etat.setdefault("bilan", {"tp": 0, "sl": 0, "pct": 0.0})
                gain = trf["d"] * (sortie - trf["e"]) / trf["e"] * 100
                bil["tp" if gain > 0 else "sl"] += 1
                bil["pct"] += gain
        derniers[nom_marche] = r
        cle["vu"] = r["t"]
        for cid, mq in demandes:
            if mq in (None, nom_marche):
                _envoi_sur(cid, text=texte_etat(nom_marche, r, cle), reply_markup=CLAVIER)
        print(texte_etat(nom_marche, r), "\n")

    try:
        envois += annonces_et_sessions(etat, int(time.time()), derniers)
        if TOKEN:
            for cid in set(destinataires(etat, chats)) | set(etat.get("prospects", [])):
                epingler(etat, cid)
        # Rappel de partage (jamais la nuit) : abonnés, visiteurs et chaîne VIP
        h = datetime.datetime.now(PARIS).hour
        if TOKEN and 11 <= h <= 20 and time.time() - etat.get("partage_t", 0) >= PARTAGE_JOURS * 86400:
            etat["partage_t"] = time.time()
            txt, kb = message_partage(etat)
            for cid in set(destinataires(etat, chats)) | set(etat.get("prospects", [])):
                _envoi_sur(cid, text=txt, reply_markup=kb)
    except Exception as ex:
        print("annonces", ex)
    if TOKEN:
        for t in envois:
            texte, clavier = (t if isinstance(t, tuple) else (t, None))
            for cid in destinataires(etat, chats):
                try:
                    if cid == etat.get("canal"):
                        # Chaîne VIP : texte seul, le coaching Oui / Non se fait en privé avec le bot
                        txt = texte.replace("\n\nTu es rentré ?", "") + (f"\n\n👉 Coaching perso : @{etat['bot']}" if clavier and etat.get("bot") else "")
                        telegram("sendMessage", chat_id=cid, text=txt)
                    elif clavier:
                        telegram("sendMessage", chat_id=cid, text=texte, reply_markup=clavier)
                    else:
                        telegram("sendMessage", chat_id=cid, text=texte)
                except Exception as ex:
                    print("envoi", cid, ex)
                    if "403" in str(ex) and cid not in proprio(etat):
                        chats.discard(cid)   # l'abonné a bloqué le bot
            # Visiteurs non abonnés : teaser (positions masquées + bouton de paiement)
            envoyer_prospects(etat, texte, bool(re.search(r"(?<!\w)\d{1,3}(?: \d{3})*\.\d+", texte)) and any(k in texte for k in ("JE PRÉPARE", "J'ENTRE MAINTENANT")))
        for nom_marche in MARCHES:
            if nom_marche in derniers:
                maj_jauge(nom_marche, derniers[nom_marche], etat[nom_marche], chats, etat.get("canal"))
    print(f"{len(envois)} signal(s) envoyé(s) à {len(chats)} téléphone(s)")
    json.dump(dict(etat, chats=sorted(chats)), open(ETAT_FICHIER, "w"))
    # Écoute en continu jusqu'au prochain lancement : réponses presque immédiates aux boutons
    while TOKEN and time.time() - debut < ECOUTE_SEC:
        reste = int(ECOUTE_SEC - (time.time() - debut))
        try:
            maj = telegram("getUpdates", offset=etat.get("offset", 0), timeout=max(1, min(50, reste))).get("result", [])
        except Exception as ex:
            print("ecoute", ex); break
        for cid, mq in traiter(etat, chats, maj):
            envoyer_analyse(cid, etat, mq)
    etat["chats"] = sorted(chats)
    json.dump(etat, open(ETAT_FICHIER, "w"))

if __name__ == "__main__":
    main()
