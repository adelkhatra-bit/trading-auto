#!/usr/bin/env python3
"""ALIGN MTF BOT — même logique que l'indicateur TradingView ALIGN MTF PRO.
Prix gratuits Kraken (BTC = XBTUSD, Gold = PAXGUSD), signaux envoyés sur Telegram.
Tourne toutes les 5 minutes (GitHub Actions). Aucune dépendance externe."""
import json, os, time, urllib.request, urllib.parse, datetime

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
ETAT_FICHIER = os.environ.get("STATE_FILE", "state.json")
MARCHES = {"BTC": "XBTUSD", "GOLD": "PAXGUSD"}  # BTC → FTMO (CFD 24/7) • GOLD → Topstep (MGC) / FTMO
MIN_ALIGN, MIN_SQZ, MARGE_ATR, GAIN_MIN = 8, 4, 0.5, 1.5
UT = ["1", "2", "5", "10", "15", "30", "45", "1h", "2h", "4h", "D"]
POIDS = [1, 1, 1, 1, 2, 2, 2, 3, 3, 4, 5]

# ───────── Données ─────────
def http_json(url, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "align-bot"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

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
                grosses=grosses, b15=b[-12:], t=b[-1]["t"], prix=cl, dirs=dirs, sqzs=sqzs, rsis=rsis, bull=bull, bear=bear, comp=comp, rsiOB=rsiOB, rsiOS=rsiOS,
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

def texte_etat(nom_marche, r):
    d = r["dirPlan"]
    lignes = [f"📊 {nom_marche} — prix {px(r['prix'])}",
              "UT 1·2·5·10·15·30·45·1h·2h·4h·D",
              barre(r),
              f"Sens probable : {'HAUSSE' if r['sens'] == 1 else 'BAISSE' if r['sens'] == -1 else 'INDÉCIS'} ({r['pctH']}% hausse)",
              f"{r['bull']} UT hausse • {r['bear']} baisse • {r['comp']} comprimées • RSI surachat {r['rsiOB']} / survente {r['rsiOS']}"]
    if r["retHaut"]: lignes.append("Retournement HAUSSIER en préparation")
    if r["retBas"]: lignes.append("Retournement BAISSIER en préparation")
    al = r["confirme"]
    lignes.append(f"Alignement 15m/1h/4h : {'▲ HAUSSE' if al == 1 else '▼ BAISSE' if al == -1 else 'NON — pas de trade'} • RSI 5m {r['r5'][-1]:.0f}")
    lignes.append(f"Zone Daily : {zone_txt(r['posD'])} • Zone Weekly : {zone_txt(r['posW'])}")
    return "\n".join(lignes)

def telegram(methode, **params):
    url = f"https://api.telegram.org/bot{TOKEN}/{methode}"
    return http_json(url, urllib.parse.urlencode(params).encode())

# ───────── Boutons et jauge ─────────
def boutons(m):
    return json.dumps({"inline_keyboard": [[{"text": "✅ Je suis rentré", "callback_data": f"in:{m}"},
                                            {"text": "❌ Non", "callback_data": f"out:{m}"}]]})

def barre_pct(pct, n=10):
    pct = max(0, min(100, pct)); plein = round(pct / 100 * n)
    return "▓" * plein + "░" * (n - plein) + f" {pct:.0f}%"

def jauge(m, r, cle):
    """Texte de la jauge (un seul message mis à jour toutes les 5 min), ou None."""
    tr = cle.get("trade"); p = r["m1"][-1]["c"]; d = r["confirme"]
    if tr and tr.get("moi"):
        e, t1, t2 = tr["e"], tr["tp1"], tr["tp2"]; cible = t2 if tr["statut"] == "tp1" else t1
        pct = 100 * tr["d"] * (p - e) / max(abs(cible - e), 1e-9)
        vit = abs(r["m1"][-1]["c"] - r["m1"][-31]["c"]) / 30 if len(r["m1"]) > 31 else 0   # vitesse moyenne / minute
        reste = abs(cible - p) / vit if vit > 0 else None
        return (f"📍 {m} en position {'LONG' if tr['d'] == 1 else 'SHORT'}\n{'TP2' if tr['statut'] == 'tp1' else 'TP1'} : {barre_pct(pct)}\n"
                f"Prix {px(p)} → objectif {px(cible)}" + (f" • ≈ {reste:.0f} min" if reste and reste < 600 else ""))
    if not tr and d:
        r5 = r["r5"][-1]; seuil = 30 if d == 1 else 70
        pct = 100 * (50 - r5) / 20 if d == 1 else 100 * (r5 - 50) / 20
        pente = (r["r5"][-1] - r["r5"][0]) / 2   # variation du RSI 5m par bougie de 5 min
        vers = -pente if d == 1 else pente
        reste = (abs(r5 - seuil) / vers * 5) if vers > 0 else None
        return (f"⏱ {m} aligné {'▲' if d == 1 else '▼'} — entrée parfaite\n{barre_pct(pct)}\nRSI 5m {r5:.0f} → {seuil}"
                + (f" • ≈ {reste:.0f} min" if reste and reste < 240 else " • en attente du repli"))
    return None

def maj_jauge(m, r, cle, chats):
    txt = jauge(m, r, cle)
    for cid in chats:
        mid = cle.get("jauge", {}).get(cid)
        try:
            if txt and mid:
                telegram("editMessageText", chat_id=cid, message_id=mid, text=txt)
            elif txt:
                res = telegram("sendMessage", chat_id=cid, text=txt, disable_notification="true")
                cle.setdefault("jauge", {})[cid] = res["result"]["message_id"]
            elif mid:
                telegram("deleteMessage", chat_id=cid, message_id=mid)
                cle["jauge"].pop(cid, None)
        except Exception as ex:
            print("jauge", ex)

# ───────── Agent : suit le trade du début à la fin ─────────
def fmt_trade(m, tr):
    sens = "▲ LONG (achat)" if tr["d"] == 1 else "▼ SHORT (vente)"
    return (f"{sens} {m}\nEntrée : {px(tr['e'])}\nTP1 : {px(tr['tp1'])} ({tr['n1']})\nTP2 : {px(tr['tp2'])} ({tr['n2']})\n"
            f"Stop : {px(tr['sl'])}\nGain/risque ≈ {tr['rr']:.1f}")

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

    # ── Pas de trade : on attend l'alignement, puis le repli en surcharge RSI ──
    if not tr:
        if not d:
            if cle.get("aligne"):
                out.append(f"⚪ {m} : alignement 15m / 1h / 4h perdu. J'attends.")
            cle["aligne"] = 0; cle["prep"] = False
            return out
        # Daily / Weekly : on évite d'acheter tout en haut ou de vendre tout en bas
        bloque = (d == 1 and r["posW"] >= 0.92 and r["posD"] >= 0.9) or (d == -1 and r["posW"] <= 0.08 and r["posD"] <= 0.1)
        if cle.get("aligne") != d:
            cle["aligne"] = d; cle["prep"] = False
            out.append(f"🧭 {m} ALIGNÉ {'▲ HAUSSE' if d == 1 else '▼ BAISSE'} sur 15m, 1h et 4h.\n{ctx}\n"
                       + ("⚠️ Prix collé à l'extrême Daily/Weekly : je ne prendrai pas d'entrée tant qu'il n'y a pas de repli." if bloque else
                          f"J'attends un repli en surcharge RSI pour une entrée parfaite ({'RSI 5m en survente' if d == 1 else 'RSI 5m en surachat'}).")
                       + f"\n\n{barre(r)}{ferme}")
        if bloque:
            return out
        repli = (r5 <= 40) if d == 1 else (r5 >= 60)
        surcharge = (min(r["r5"]) <= 30) if d == 1 else (max(r["r5"]) >= 70)
        reprise = (r5 > r5p and r5 > 30) if d == 1 else (r5 < r5p and r5 < 70)
        if repli and not cle.get("prep"):
            cle["prep"] = True
            pl = plan_entree(r, d, p)
            out.append(f"⏳ {m} : prépare-toi, repli en cours.\n{'Achat' if d == 1 else 'Vente'} probable vers {px(p)} • stop ≈ {px(pl['sl'])} • TP1 ≈ {px(pl['tp1'])}")
        if surcharge and reprise:
            pl = plan_entree(r, d, p)
            if pl["rr"] >= 1.5:
                tr = dict(pl, statut="entree", cree=r["t"], encore=0)
                cle["trade"] = tr; cle["prep"] = False
                out.append((f"✅ ENTRE MAINTENANT — {m}\n{fmt_trade(m, tr)}{ferme}\n\nTu es rentré ?", boutons(m)))
        elif not repli:
            cle["prep"] = False
        return out

    # ── Trade en cours ──
    d, e, sl, t1, t2 = tr["d"], tr["e"], tr["sl"], tr["tp1"], tr["tp2"]
    touche_sl = (lo <= sl) if d == 1 else (hi >= sl)
    touche_t1 = (hi >= t1) if d == 1 else (lo <= t1)
    touche_t2 = (hi >= t2) if d == 1 else (lo <= t2)
    progres = d * (p - e) / max(abs(t1 - e), 1e-9)

    if tr.get("moi") is False:
        cle.pop("trade"); cle["aligne"] = 0; return out
    if tr["statut"] == "entree":
        if touche_sl:
            out.append(f"❌ {m} : stop {px(sl)} touché. On coupe, prochain setup bientôt.")
            cle.pop("trade"); cle["aligne"] = 0; return out
        if touche_t1:
            tr["statut"] = "tp1"; tr["sl"] = e
            out.append(f"🎯 {m} : TP1 {px(t1)} touché !\n→ Sécurise une partie\n→ Stop à l'entrée {px(e)}\n→ On vise TP2 {px(t2)}")
            return out
        if progres < 0.25:
            if tr["encore"] < 1 and r["t"] - tr["cree"] >= 900:
                tr["encore"] += 1
                if tr.get("moi") is None:
                    out.append((f"👍 {m} : tu peux encore rentrer ({px(p)}). Stop {px(sl)} • TP1 {px(t1)}\n\nTu es rentré ?", boutons(m)))
        elif not tr.get("tard"):
            tr["tard"] = True
            if tr.get("moi") is None:
                out.append(f"⛔ {m} : trop tard pour rentrer. On attend le prochain setup.")
                cle.pop("trade"); cle["aligne"] = 0
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
            cle.pop("trade"); cle["aligne"] = 0; return out
        if (lo <= tr["sl"]) if d == 1 else (hi >= tr["sl"]):
            out.append(f"↩️ {m} : sortie au stop sécurisé {px(tr['sl'])}. TP1 encaissé, pas de perte.")
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

    # Messages reçus : /start enregistre ton téléphone, « etat » demande l'état actuel
    demandes = []
    if TOKEN:
        maj = telegram("getUpdates", offset=etat.get("offset", 0), timeout=0)
        for u in maj.get("result", []):
            etat["offset"] = u["update_id"] + 1
            cb = u.get("callback_query")
            if cb:
                choix, _, mk = cb.get("data", "").partition(":")
                trc = etat.get(mk, {}).get("trade")
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"])
                except Exception:
                    pass
                cidc = str(cb["message"]["chat"]["id"])
                if trc:
                    trc["moi"] = choix == "in"
                    telegram("sendMessage", chat_id=cidc, text=(f"👊 OK, on est dedans ensemble sur {mk}. Je te coache jusqu'au TP." if choix == "in"
                                                             else f"👌 OK, pas de position sur {mk}. J'attends le prochain setup."))
                continue
            msg = u.get("message") or {}
            cid = str(msg.get("chat", {}).get("id", ""))
            if cid:
                if cid not in chats:
                    chats.add(cid)
                    telegram("sendMessage", chat_id=cid, text="✅ ALIGN MTF BOT activé. Tu recevras les signaux BTC et Gold ici.\nÉcris « etat » pour voir l'analyse du moment.")
                if "etat" in (msg.get("text", "").lower().replace("é", "e")):
                    demandes.append(cid)

    envois, derniers = [], {}
    for nom_marche, pair in MARCHES.items():
        try:
            r = analyser(pair)
        except Exception as ex:
            print(nom_marche, "erreur", ex); continue
        cle = etat.setdefault(nom_marche, {})
        ferme = "" if nom_marche == "BTC" or cme_ouvert(r["t"]) else "\n⚠️ Futures CME fermés en ce moment (Topstep) : signal à titre indicatif."
        envois += agent(nom_marche, r, cle, ferme)
        derniers[nom_marche] = r
        cle["vu"] = r["t"]
        for cid in demandes:
            telegram("sendMessage", chat_id=cid, text=texte_etat(nom_marche, r))
        print(texte_etat(nom_marche, r), "\n")

    if TOKEN:
        for t in envois:
            texte, clavier = (t if isinstance(t, tuple) else (t, None))
            for cid in chats:
                if clavier:
                    telegram("sendMessage", chat_id=cid, text=texte, reply_markup=clavier)
                else:
                    telegram("sendMessage", chat_id=cid, text=texte)
        for nom_marche in MARCHES:
            if nom_marche in derniers:
                maj_jauge(nom_marche, derniers[nom_marche], etat[nom_marche], chats)
    print(f"{len(envois)} signal(s) envoyé(s) à {len(chats)} téléphone(s)")
    etat["chats"] = sorted(chats)
    json.dump(etat, open(ETAT_FICHIER, "w"))

if __name__ == "__main__":
    main()
