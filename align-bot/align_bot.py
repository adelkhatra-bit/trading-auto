#!/usr/bin/env python3
"""ALIGN MTF BOT — même logique que l'indicateur TradingView ALIGN MTF PRO.
Prix gratuits : BTC = Kraken XBTUSD, Gold = XAUUSD spot (bougies COMEX Yahoo recalées sur le prix spot Swissquote).
Tourne toutes les 5 minutes (GitHub Actions). Aucune dépendance externe."""
import json, os, re, time, urllib.request, urllib.error, urllib.parse, datetime
from zoneinfo import ZoneInfo
PARIS = ZoneInfo("Europe/Paris")

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
ETAT_FICHIER = os.environ.get("STATE_FILE", "state.json")
MARCHES = {"BTC": "XBTUSD", "GOLD": "XAUUSD"}  # BTC → FTMO (CFD 24/7) • GOLD → Topstep (MGC) / FTMO
MIN_ALIGN, MIN_SQZ, MARGE_ATR, GAIN_MIN = 8, 4, 0.5, 2.0
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

TTL_KRAKEN = {1: 15, 5: 30, 15: 45, 30: 90, 60: 120, 240: 300, 1440: 900, 10080: 1800}

def kraken(pair, interval):
    c = _CACHE_K.get((pair, interval))
    if c and time.time() - c[0] < TTL_KRAKEN.get(interval, 60):
        return c[1]
    rows = _kraken(pair, interval)
    _CACHE_K[(pair, interval)] = (time.time(), rows)
    return rows

_CACHE_K = {}

def _kraken(pair, interval):
    j = http_json(f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval}")
    if j.get("error"):
        raise RuntimeError(j["error"])
    rows = next(v for k, v in j["result"].items() if k != "last")
    rows = rows[:-1]  # on enlève la bougie en cours : calcul à la clôture, comme l'alerte TradingView
    return [dict(t=int(r[0]), o=float(r[1]), h=float(r[2]), l=float(r[3]), c=float(r[4])) for r in rows]

# ───────── Gold = XAUUSD spot (même prix que FOREXCOM:XAUUSD sur TradingView) ─────────
_CACHE = {}
YAHOO = {1: ("1m", "5d", 50), 5: ("5m", "1mo", 50), 15: ("15m", "1mo", 50), 30: ("30m", "1mo", 120),
         60: ("60m", "3mo", 300), 1440: ("1d", "2y", 1800), 10080: ("1wk", "10y", 3600)}

def or_spot():
    """Prix spot XAUUSD en direct (Swissquote, gratuit) : milieu achat / vente."""
    c = _CACHE.get("spot")
    if c and time.time() - c[0] < 20:
        return c[1]
    j = http_json("https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD")
    q = j[0]["spreadProfilePrices"][0]
    v = (q["bid"] + q["ask"]) / 2
    _CACHE["spot"] = (time.time(), v)
    return v

def yahoo_or(interval):
    """Bougies de l'or (COMEX GC=F) recalées sur le spot XAUUSD : mêmes mèches, mêmes prix que le graphique XAUUSD."""
    if interval == 240:
        return regrouper(yahoo_or(60), 4, 3600)
    ui, rg, ttl = YAHOO[interval]
    c = _CACHE.get(("gc", interval))
    if not c or time.time() - c[0] > ttl:
        j = None
        for hote in ("query1", "query2"):
            try:
                j = http_json(f"https://{hote}.finance.yahoo.com/v8/finance/chart/GC=F?interval={ui}&range={rg}")
                break
            except Exception as ex:
                print("yahoo", hote, ex)
        if j is None:
            raise RuntimeError("Yahoo indisponible")
        res = j["chart"]["result"][0]; q = res["indicators"]["quote"][0]
        rows = [dict(t=int(t), o=o, h=h, l=l, c=cl) for t, o, h, l, cl in zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"])
                if None not in (o, h, l, cl)]
        _CACHE[("gc", interval)] = (time.time(), rows[:-1][-720:], res["meta"].get("regularMarketPrice") or rows[-1]["c"])
        c = _CACHE[("gc", interval)]
    # Écart futures / spot (les futures Yahoo ont ~10 min de retard) : moyenne lissée pour rester stable
    spot = None
    try:
        spot = or_spot()
        brut = spot - _CACHE.get(("gc", 1), c)[2]
        ancien = _CACHE.get("ecart")
        _CACHE["ecart"] = brut if ancien is None or abs(brut - ancien) > 40 else ancien * 0.9 + brut * 0.1
    except Exception as ex:
        print("spot or", ex)
    ecart = _CACHE.get("ecart", 0.0)
    out = [dict(t=b["t"], o=b["o"] + ecart, h=b["h"] + ecart, l=b["l"] + ecart, c=b["c"] + ecart) for b in c[1]]
    if interval == 1 and spot and out:
        # Dernière minute = prix spot EN DIRECT (comme le graphique XAUUSD), pour ne pas avoir 10 min de retard
        t = int(time.time()) // 60 * 60 - 60
        if t > out[-1]["t"]:
            out.append(dict(t=t, o=out[-1]["c"], h=max(out[-1]["c"], spot), l=min(out[-1]["c"], spot), c=spot))
    return out

def paxg_or(interval):
    """Bougies de l'or : PAXG (Kraken, fiable, sans limite) recalées sur le prix spot XAUUSD (Swissquote).
    Mêmes mouvements, mêmes mèches, au prix du graphique XAUUSD."""
    c = _CACHE.get(("paxg", interval))
    if not c or time.time() - c[0] > 50:
        rows = kraken("PAXGUSD", interval)
        _CACHE[("paxg", interval)] = c = (time.time(), rows)
        if interval == 1 and rows:
            _CACHE["paxg_dernier"] = rows[-1]["c"]
    spot = None
    try:
        spot = or_spot()
        if "paxg_dernier" not in _CACHE:
            _CACHE["paxg_dernier"] = kraken("PAXGUSD", 1)[-1]["c"]
        brut = spot - _CACHE["paxg_dernier"]
        ancien = _CACHE.get("ecart_paxg")
        _CACHE["ecart_paxg"] = brut if ancien is None or abs(brut - ancien) > 60 else ancien * 0.8 + brut * 0.2
    except Exception as ex:
        print("spot or", ex)
    e = _CACHE.get("ecart_paxg", 0.0)
    out = [dict(t=b["t"], o=b["o"] + e, h=b["h"] + e, l=b["l"] + e, c=b["c"] + e) for b in c[1]]
    if interval == 1 and spot and out:
        t = int(time.time()) // 60 * 60 - 60
        if t > out[-1]["t"]:
            out.append(dict(t=t, o=out[-1]["c"], h=max(out[-1]["c"], spot), l=min(out[-1]["c"], spot), c=spot))
    return out

def bougies(pair, interval):
    """Source des bougies : Kraken pour le BTC ; pour le Gold, PAXG recalé sur le spot XAUUSD (secours : bougies COMEX)."""
    if pair == "XAUUSD":
        try:
            return paxg_or(interval)
        except Exception as ex:
            print("or PAXG -> secours COMEX", ex)
            return yahoo_or(interval)
    return kraken(pair, interval)

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

def divergence(bars, g=3, recent=12):
    """Divergence RSI sur les derniers sommets / creux : (baissière, haussière)."""
    c = [x["c"] for x in bars]; rr = [v or 50 for v in rsi(c)]
    hs = [i for i in range(g, len(bars) - g) if bars[i]["h"] == max(x["h"] for x in bars[i - g:i + g + 1])]
    ls = [i for i in range(g, len(bars) - g) if bars[i]["l"] == min(x["l"] for x in bars[i - g:i + g + 1])]
    baisse = len(hs) >= 2 and len(bars) - hs[-1] <= recent and bars[hs[-1]]["h"] >= bars[hs[-2]]["h"] * 0.999 and rr[hs[-1]] < rr[hs[-2]] - 3
    hausse = len(ls) >= 2 and len(bars) - ls[-1] <= recent and bars[ls[-1]]["l"] <= bars[ls[-2]]["l"] * 1.001 and rr[ls[-1]] > rr[ls[-2]] + 3
    return baisse, hausse

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
def direct_btc(m1, pair):
    """Ajoute la minute en cours au prix réel du moment (pas d'attente de la clôture de la bougie)."""
    try:
        j = http_json(f"https://api.kraken.com/0/public/Ticker?pair={pair}")
        v = float(next(iter(j["result"].values()))["c"][0])
        t = int(time.time()) // 60 * 60
        if m1 and t > m1[-1]["t"]:
            return m1 + [dict(t=t, o=m1[-1]["c"], h=max(m1[-1]["c"], v), l=min(m1[-1]["c"], v), c=v)]
    except Exception as ex:
        print("direct", ex)
    return m1

def analyser(pair):
    m1, m5, m15, h1, h4, d1 = (bougies(pair, i) for i in (1, 5, 15, 60, 240, 1440))
    if pair != "XAUUSD":
        m1 = direct_btc(m1, pair)
    series = {"1": m1, "2": regrouper(m1, 2, 60), "5": m5, "10": regrouper(m5, 2, 300), "15": m15,
              "30": bougies(pair, 30), "45": regrouper(m15, 3, 900), "1h": h1, "2h": regrouper(h1, 2, 3600), "4h": h4, "D": d1}
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
    w1 = bougies(pair, 10080)
    def position(bars, n):
        z = bars[-n:]; haut = max(x["h"] for x in z); bas = min(x["l"] for x in z)
        return (cl - bas) / max(haut - bas, 1e-9), haut, bas
    posD, hautD, basD = position(d1, 5)
    posW, hautW, basW = position(w1, 4)
    # RSI 5 min (déclencheur de l'entrée parfaite) et RSI 15 min
    r5 = rsi([x["c"] for x in m5])
    # Distribution (sommet qui s'essouffle) / accumulation (creux qui se charge) : divergences 1h + 4h en haut / en bas de zone
    div1h, div4h = divergence(h1), divergence(h4)
    distrib = (div1h[0] or div4h[0]) and (posD >= 0.65 or posW >= 0.75)
    accum = (div1h[1] or div4h[1]) and (posD <= 0.35 or posW <= 0.25)
    return dict(distrib=distrib, accum=accum, div4h=div4h,m1=m1, confirme=confirme, atr=a, r5=r5[-3:], r15=rC, posD=posD, posW=posW, hautD=hautD, basD=basD, hautW=hautW, basW=basW,
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
PIP = {"BTC": 1.0, "GOLD": 0.1}      # 1 pip : 1 $ sur le BTC, 0,10 $ sur l'or
SENS = {1: "🟩 LONG ⬆️", -1: "🟥 SHORT ⬇️"}

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
    prix = r["m1"][-1]["c"]
    sens_txt = ("📈 Le marché MONTE" if maj == 1 else "📉 Le marché DESCEND" if maj == -1 else "➖ Le marché hésite")
    coches = " ".join("✅" if x == maj and maj else "⏳" for x in (D[4], D[7], D[9]))
    if not vip:
        return "\n".join([f"{ICONE.get(nom_marche, '📊')} {nom_marche}   {px(prix)}",
                          f"{sens_txt}   ({coches})", r.get("news") or "",
                          "━━━━━━━━━━━━",
                          "🔒 Entrée : VIP", "🔒 SL : VIP", "🔒 TP : VIP", "🔒 Prochaine entrée : VIP",
                          "━━━━━━━━━━━━",
                          "👀 Les VIP savent déjà où rentrer", "😬 Tu vas louper le prochain move ?", "💎 VIP 49,90 € / mois 👇"])
    l = [f"{ICONE.get(nom_marche, '📊')} {nom_marche}   {px(prix)}", f"{sens_txt}   ({coches})", "━━━━━━━━━━━━"]
    l += [f"{nom:<7} {fl(D[i])}   RSI {R[i]:.0f}" for nom, i in ut]
    l += ["━━━━━━━━━━━━",
          f"🧭 Alignement   {n_ok}/3 {'✅' if r['confirme'] else '⏳'} {fl(maj) if maj else ''}".rstrip(),
          f"📍 Daily {zone_txt(r['posD'])} • Weekly {zone_txt(r['posW'])}",
          r.get("news") or "📰 News : calendrier indisponible"]
    if r.get("repli"):
        l.append(f"↩️ Repli en cours sur le 15 min : c'est lui qu'on attend pour entrer {SENS[r['confirme']]}")
    if r.get("distrib"):
        l.append("⚠️ Distribution possible : le haut s'essouffle (divergence RSI)")
    if r.get("accum"):
        l.append("⚠️ Accumulation possible : le bas se charge (divergence RSI)")
    o = (cle or {}).get("ordre")
    if r["confirme"] and o and not (cle or {}).get("trade"):
        l.append(f"🟨 Zone   {px(o.get('za', o['e']))} – {px(o.get('zb', o['e']))}" if vip else "🟨 Zone   🔒🔒🔒")
    titre, raison = verdict(r, cle)
    l += ["━━━━━━━━━━━━", titre, raison]
    if "Prochaine entrée" not in raison and not (cle or {}).get("trade"):
        l.append(prochaine(r, cle))
    return "\n".join(l)

def bloque_dw(r, d):
    """Daily / Weekly : pas de short tout en bas, pas de long tout en haut."""
    return (d == -1 and (r["posD"] <= 0.15 or (r["posW"] <= 0.15 and r["posD"] <= 0.35))) or \
           (d == 1 and (r["posD"] >= 0.85 or (r["posW"] >= 0.85 and r["posD"] >= 0.65)))

def etire(r, d):
    """Le prix est déjà parti loin (RSI 15 min en excès ou trop loin de l'EMA 20) : entrée loupée."""
    p = r["m1"][-1]["c"]
    return (r["r15"] >= 70 or p - r["ema15"] > 2 * r["atr"]) if d == 1 else (r["r15"] <= 30 or r["ema15"] - p > 2 * r["atr"])

def prochaine(r, cle):
    """Prochaine entrée attendue, avec la flèche et la couleur."""
    d = r["confirme"]; R = dict(zip(UT, r["rsis"]))
    if d and etire(r, d):
        # Grosses UT en excès : le retournement est possible
        if (d == 1 and R["1h"] >= 70 and R["4h"] >= 65) or (d == -1 and R["1h"] <= 30 and R["4h"] <= 35):
            return f"🔜 Prochaine entrée   {SENS[-d]}\n👀 Si 15 min / 1 h / 4 h se retournent"
        return f"🔜 Prochaine entrée   {SENS[d]}\n↩️ Sur le repli vers   {px(r['ema15'])}"
    if d:
        return f"🔜 Prochaine entrée   {SENS[d]}"
    maj, n_ok = alignement(r)
    return f"🔜 Prochaine entrée   {SENS[maj]}   ({n_ok}/3)" if maj else "🔜 Prochaine entrée   ➖ pas encore de sens"

def verdict(r, cle):
    """Réponse claire pour l'utilisateur : peut-il entrer maintenant ou non ?"""
    cle = cle or {}
    tr = cle.get("trade")
    if tr:
        p = r["m1"][-1]["c"]
        sens = "⬆️ ACHAT" if tr["d"] == 1 else "⬇️ VENTE"
        prog = tr["d"] * (p - tr["e"]) / max(abs(tr["tp1"] - tr["e"]), 1e-9)
        if tr["statut"] == "entree" and prog < 0.25 and not tr.get("tard"):
            return (f"🟢 TU PEUX ENTRER\n{SENS[tr['d']]}", f"👀 Vue 15 minutes\n🛑 SL un peu {'SOUS la mèche du dernier creux' if tr['d'] == 1 else 'AU-DESSUS de la mèche du dernier sommet'}\n🙅 Jamais pile sur la mèche\n📍 Repère prix : SL ≈ {px(tr['sl'])} • TP1 ≈ {px(tr['tp1'])}\n👉 Puis appuie sur ✅ Je suis rentré")
        return ("🔴🔴 N'ENTRE PAS", f"⏰ Trop tard : la position {sens} est déjà partie\n⏳ J'attends le prochain setup")
    if r.get("annonce"):
        return ("🔴🔴 N'ENTRE PAS", "📰 News dans moins de 15 min\n💥 Le prix peut bouger très fort")
    al = r["confirme"]
    if not al:
        return ("🔴🔴 N'ENTRE PAS", "⏳ 15 min / 1 h / 4 h pas alignées\n🔔 Je te préviens dès que c'est bon")
    if etire(r, al):
        return ("⛔ TROP TARD — le marché est déjà parti", "😎 Patience, on trouve une autre entrée\n" + prochaine(r, cle))
    if bloque_dw(r, al) and not cle.get("ordre"):      # une position déjà préparée n'est pas annulée par un petit va-et-vient du Daily
        return ("🔴🔴 N'ENTRE PAS", f"📍 Prix {zone_txt(r['posD'])} Daily / {zone_txt(r['posW'])} Weekly\n🔄 Risque de rebond : pas de {'long' if al == 1 else 'short'} ici")
    zone = bool(cle.get("attente_rsi"))
    return (f"🟡 PATIENCE   {SENS[al]} bientôt",
            f"✅ 15 min / 1 h / 4 h alignées\n{'✅' if zone else '⏳'} Prix dans la zone 🟨\n⏳ Surcharge RSI 5 min\n✅ Pas de news proche\n"
            "🚦 Attends mon 🟢 J'ENTRE MAINTENANT")

# ───────── Langue : chaque utilisateur choisit 🇫🇷 / 🇬🇧, tout le système suit ─────────
TRAD = {
# Boutons
"🟠 Analyse BTC": "🟠 BTC Analysis", "🥇 Analyse Gold": "🥇 Gold Analysis",
"✅ Je suis rentré": "✅ I'm in", "🚪 Je suis sorti": "🚪 I'm out", "📈 Mes résultats": "📈 My results",
"🧩 Indicateur TradingView": "🧩 TradingView indicator", "💎 Devenir VIP": "💎 Become VIP",
"Utilise les boutons 👇": "Use the buttons 👇", "❌ Non": "❌ No",
"📤 Partager à un ami": "📤 Share with a friend", "🎁 Offrir l'accès VIP": "🎁 Gift VIP access",
"🎁 Offrir l'indicateur": "🎁 Gift the indicator", "⛔ Retirer l'accès": "⛔ Remove access",
"✅ C'est fait, accès donné": "✅ Done, access given",
"🔓 Débloquer les positions (49,90 € / mois)": "🔓 Unlock positions (€49.90 / month)",
"🧩 Obtenir l'indicateur (49,90 € / mois)": "🧩 Get the indicator (€49.90 / month)",
# Verdicts / analyse
"🔴🔴 N'ENTRE PAS": "🔴🔴 DON'T ENTER", "🟢 TU PEUX ENTRER": "🟢 YOU CAN ENTER", "🟡 PATIENCE": "🟡 BE PATIENT",
"⛔ TROP TARD — le marché est déjà parti": "⛔ TOO LATE — the market has already moved",
"😎 Patience, on trouve une autre entrée": "😎 Be patient, we'll find another entry",
"⏳ 15 min / 1 h / 4 h pas alignées": "⏳ 15 min / 1 h / 4 h not aligned",
"✅ 15 min / 1 h / 4 h alignées": "✅ 15 min / 1 h / 4 h aligned",
"🔔 Je te préviens dès que c'est bon": "🔔 I'll tell you when it's ready",
"🔔 Je te préviens dès qu'il y en a une": "🔔 I'll tell you as soon as there is one",
"🔔 Je te préviens": "🔔 I'll let you know",
"📰 News dans moins de 15 min": "📰 News in less than 15 min",
"💥 Le prix peut bouger très fort dans les 2 sens": "💥 Price can move very hard both ways",
"💥 Le prix peut bouger très fort": "💥 Price can move very hard",
"🔄 Risque de rebond : pas de": "🔄 Bounce risk: no",
"Prix dans la zone 🟨": "Price in the zone 🟨", "⏳ Surcharge RSI 5 min": "⏳ RSI 5 min overextension",
"✅ Pas de news proche": "✅ No news nearby", "Pas de news proche": "No news nearby",
"🚦 Attends mon 🟢 J'ENTRE MAINTENANT": "🚦 Wait for my 🟢 I'M ENTERING NOW",
"👉 Puis appuie sur ✅ Je suis rentré": "👉 Then tap ✅ I'm in",
"⏰ Trop tard : la position": "⏰ Too late: the position", "est déjà partie": "has already gone",
"⏳ J'attends le prochain setup": "⏳ Waiting for the next setup",
"🔜 Prochaine entrée   ➖ pas encore de sens": "🔜 Next entry   ➖ no direction yet",
"🔜 Prochaine entrée": "🔜 Next entry", "↩️ Sur le repli vers": "↩️ On the pullback to",
"👀 Si 15 min / 1 h / 4 h se retournent": "👀 If 15 min / 1 h / 4 h turn",
"🧭 Alignement": "🧭 Alignment", 
"tout en HAUT": "at the very TOP", "tout en BAS": "at the very BOTTOM", "en haut": "high", "en bas": "low", "au milieu": "in the middle",
"✅ Aucune annonce ni discours d'ici": "✅ No news or speech within",
"📰 News : calendrier indisponible": "📰 News: calendar unavailable",
"Pas de news majeure prévue cette semaine": "No major news this week",
"bientôt": "soon",
# Jauge
"🔌 Prochaine position": "🔌 Next position", "🔌 EN POSITION": "🔌 IN POSITION", "🔌 Position ouverte": "🔌 Position open",
"🚀 Déjà parti : patience": "🚀 Already gone: patience", "⏳ Je calcule la zone": "⏳ Computing the zone",
"⚡ Dans la zone : j'attends le RSI": "⚡ In the zone: waiting for RSI",
"⏱ Le prix approche doucement": "⏱ Price is slowly getting closer", "⏱ Arrivée ≈": "⏱ Arrival ≈",
"🛑 Ton stop": "🛑 Your SL", "bloqué : prix": "blocked: price",
# Agent / signaux
"🔔 JE PRÉPARE UNE POSITION —": "🔔 PREPARING A POSITION —",
"⏳ Je n'entre pas encore : j'attends que le prix vienne dans la zone 🟨": "⏳ Not entering yet: waiting for price to reach the zone 🟨",
"👀 Mets-toi en vue 15 minutes": "👀 Switch to the 15-minute chart", "⏱ Mets-toi en vue 15 minutes": "⏱ Switch to the 15-minute chart",
"👀 Vue 15 minutes": "👀 15-minute chart", "⏱ Vue 15 minutes": "⏱ 15-minute chart",
"🕯 Repère le dernier creux (mèche du bas)": "🕯 Find the last low (bottom wick)",
"🕯 Repère le dernier sommet (mèche du haut)": "🕯 Find the last high (top wick)",
"le dernier creux (mèche du bas)": "the last low (bottom wick)", "le dernier sommet (mèche du haut)": "the last high (top wick)",
"🟨 L'entrée sera à peu près": "🟨 Entry will be roughly", "au-dessus de ce creux": "above this low", "sous ce sommet": "below this high",
"🚦 Attends mon feu vert 🟢": "🚦 Wait for my green light 🟢",
"monte sur 15m, 1h et 4h ✅✅✅": "is rising on 15m, 1h and 4h ✅✅✅", "descend sur 15m, 1h et 4h ✅✅✅": "is falling on 15m, 1h and 4h ✅✅✅",
"🟡🟡 TIENS-TOI PRÊT —": "🟡🟡 GET READY —", "arrive dans la zone 🟨": "is reaching the zone 🟨",
"📲 Je prépare mon ordre": "📲 Preparing my order", "⏳ J'attends le signal 🟢": "⏳ Waiting for the 🟢 signal",
"🟢🟢🟢 J'ENTRE MAINTENANT —": "🟢🟢🟢 I'M ENTERING NOW —", "J'ENTRE MAINTENANT": "I'M ENTERING NOW",
"🎯 Confiance": "🎯 Confidence", "15 min • 1 h • 4 h alignées": "15 min • 1 h • 4 h aligned",
"Daily / Weekly favorables": "Daily / Weekly favourable", "Zone Fibonacci 50 – 78,6 %": "Fibonacci zone 50 – 78.6 %",
"Niveau 15m / 1h / 4h ou EMA": "15m / 1h / 4h level or EMA", "RSI en surcharge (": "RSI overextended (",
"Confirmé en 1 h": "Confirmed on 1 h", "Gain / risque x": "Reward / risk x", "Tu es rentré ?": "Are you in?",
"🕯 EN BOUGIES (marche sur toutes les plateformes) :": "🕯 IN CANDLES (works on every platform):",
"1️⃣ 👀 Mets-toi en vue 15 minutes": "1️⃣ 👀 Switch to the 15-minute chart",
"2️⃣ 🛑 SL : un tout petit peu": "2️⃣ 🛑 SL: just a little", "3️⃣ 🟨 Entrée": "3️⃣ 🟨 Entry",
"sur le repli": "on the pullback", "sur le rebond": "on the bounce",
"vers la moitié de la dernière grande bougie verte": "around the middle of the last big green candle",
"vers la moitié de la dernière grande bougie rouge": "around the middle of the last big red candle",
"4️⃣ 💰 TP1 : juste": "4️⃣ 💰 TP1: just", "4️⃣ 💰 TP1 : environ": "4️⃣ 💰 TP1: about", "fois ton risque": "times your risk",
"5️⃣ 🏁 TP2 : on laisse courir, je te guide": "5️⃣ 🏁 TP2: we let it run, I'll guide you", "5️⃣ 🏁 TP2 :": "5️⃣ 🏁 TP2:",
"💡 TP1 touché → SL à BE": "💡 TP1 hit → SL to BE", "(regarde en vue": "(look at the chart", "(vue": "(chart",
"📍 Repère prix (XAUUSD / Kraken BTC) :": "📍 Price guide (XAUUSD / Kraken BTC):", "📍 Repère prix : SL ≈": "📍 Price guide: SL ≈",
"📍 Repère prix   ≈": "📍 Price guide   ≈", "PRIX ACTUEL": "CURRENT PRICE", "ENTRÉE haut": "ENTRY top", "ENTRÉE bas": "ENTRY bottom", "ENTRÉE": "ENTRY",
"Risque": "Risk", "Gain   ": "Reward ",
"ℹ️ Ma position perso • pas un conseil • risque de perte": "ℹ️ My personal position • not advice • risk of loss",
"📐 Zone = Fibonacci 50 → 78,6 % +": "📐 Zone = Fibonacci 50 → 78.6 % +",
"est déjà parti": "has already moved", "😎 On ne court pas après le prix": "😎 We don't chase the price",
": alignement 15m / 1h / 4h perdu. Ordre annulé, j'attends.": ": 15m / 1h / 4h alignment lost. Order cancelled, waiting.",
"aligné": "aligned", "sur 15m/1h/4h, MAIS prix": "on 15m/1h/4h, BUT price",
"ici : risque de rebond. J'attends un meilleur prix.": "here: bounce risk. Waiting for a better price.", "⛔ Pas de": "⛔ No",
": le prix est parti sans toucher le point d'entrée. Trop tard, je recalcule le prochain point.": ": price left without touching the entry. Too late, recalculating the next one.",
": prix DANS la zone 🟨 — j'attends la confirmation RSI ⏳": ": price IN the zone 🟨 — waiting for RSI confirmation ⏳",
": prix sur le point d'entrée, mais annonce économique dans moins de 15 min. On ne rentre pas.": ": price at entry, but economic news in less than 15 min. Not entering.",
": tu peux encore rentrer (": ": you can still enter (", ": trop tard pour rentrer. On attend le prochain setup.": ": too late to enter. Waiting for the next setup.",
": trop tard pour rentrer maintenant. Ceux qui sont dedans : on continue vers le TP1": ": too late to enter now. Those already in: we keep going to TP1",
"touché. On coupe, prochain setup bientôt.": "hit. We close, next setup soon.", "touché !": "hit!",
"→ Sécurise une partie": "→ Secure part of it", "→ Mets ton SL à BE (prix d'entrée)": "→ Move your SL to BE (entry price)", "→ On vise TP2": "→ Aiming for TP2",
": TP2 touché, la tendance continue.": ": TP2 hit, the trend continues.", "→ Stop au TP1": "→ SL at TP1", "→ Nouvel objectif": "→ New target",
"objectif final": "final target", "atteint. Trade terminé, bravo !": "reached. Trade done, well done!",
": sortie au stop sécurisé": ": exit at the protected SL", ". TP1 encaissé, pas de perte.": ". TP1 banked, no loss.",
# Coach
"Tiens bon, presque arrivé": "Hold on, almost there", "🎯 Objectif": "🎯 Target", "Ça part dans le bon sens": "Moving the right way",
"Le prix revient contre nous": "Price is coming back against us", "🙅 On ne le déplace pas": "🙅 We don't move it",
"Petite perturbation, c'est normal": "Small wobble, that's normal", "(surcharge)": "(overextended)", "🎯 Cap sur le TP": "🎯 Heading for TP",
"⏸ Pause normale, patience": "⏸ Normal pause, be patient", "🎯 S'il casse : cap sur le TP": "🎯 If it breaks: heading for TP",
"Résistance": "Resistance", "Plan annulé": "Plan cancelled", "Les unités de temps se retournent": "Timeframes are turning",
"✂️ Je coupe ma position": "✂️ I'm closing my position", "News dans": "News in", "🔒 Mets ton SL à BE (prix d'entrée)": "🔒 Move your SL to BE (entry price)",
"✂️ Le trade n'avance pas": "✂️ The trade isn't moving", "✂️ Je coupe avant la news": "✂️ Closing before the news",
"🔁 Mets ton SL à BE (ton prix d'entrée)": "🔁 Move your SL to BE (your entry price)",
"🛡 Comme ça, plus aucune perte possible": "🛡 This way, no loss possible", "🎯 On laisse courir vers le TP": "🎯 We let it run to TP",
"🕯 Repère la mèche du dernier": "🕯 Find the wick of the last", "creux": "low", "sommet": "high",
"⬆️ Monte": "⬆️ Raise", "⬇️ Descends": "⬇️ Lower", "ton SL un peu": "your SL a little", "cette mèche": "this wick",
"🙅 Jamais pile sur la mèche : elle peut être retouchée": "🙅 Never exactly on the wick: it can be retested", "🙅 Jamais pile sur la mèche": "🙅 Never exactly on the wick",
"💰 Ton gain est protégé": "💰 Your profit is protected", "🛡 Ta perte possible est réduite": "🛡 Your possible loss is reduced",
": reste cool": ": stay cool", "🌬 Le marché respire": "🌬 The market is breathing", "🕯 Il peut revenir un peu, c'est normal": "🕯 It may pull back a bit, that's normal",
"🛑 Ne touche pas ton SL": "🛑 Don't touch your SL",
"SOUS la mèche du dernier creux": "BELOW the wick of the last low", "AU-DESSUS de la mèche du dernier sommet": "ABOVE the wick of the last high",
"la mèche du dernier creux": "the wick of the last low", "la mèche du dernier sommet": "the wick of the last high",
"🛑 SL un peu": "🛑 SL a little", "SOUS": "BELOW", "AU-DESSUS de": "ABOVE", "sous la": "below the", "au-dessus du": "above the",
"résistance": "resistance", "support": "support",
# Entrée abonné
"🤖 Coach IA activé jusqu'au TP": "🤖 AI coach on until TP", "🔎 Je surveille toutes les 5 min :": "🔎 I check every 5 min:",
"🧭 15 min / 1 h / 4 h • ⚡ RSI • 🧱 niveaux • 🎤 news": "🧭 15 min / 1 h / 4 h • ⚡ RSI • 🧱 levels • 🎤 news",
"📈 Résultat calculé tout seul": "📈 Result calculated automatically", "📌 Entrée": "📌 Entry", "🛑 Stop": "🛑 SL", "(surcharge, normal)": "(overextended, normal)",
"🔴 Le bot n'a pas de position ouverte": "🔴 The bot has no open position", "👉 Attends 🟢 J'ENTRE MAINTENANT": "👉 Wait for 🟢 I'M ENTERING NOW",
"🟠 / 🥇 Ou appuie sur Analyse BTC / Gold": "🟠 / 🥇 Or tap BTC / Gold Analysis",
"👌 Pas de position ouverte. J'attends le prochain setup.": "👌 No open position. Waiting for the next setup.",
"clôturé": "closed", "🚪 Sortie": "🚪 Exit", "🎉 Bravo !": "🎉 Well done!", "💪 On repart au prochain": "💪 On to the next one",
"🚪 Sortie manuelle": "🚪 Manual exit", "🛑 Stop touché": "🛑 SL hit", "🔒 Stop protégé touché": "🔒 Protected SL hit", "🛡 Stop remonté touché": "🛡 Raised SL hit",
"💰 TP1 encaissé": "💰 TP1 banked", "🏆 Objectif final": "🏆 Final target",
# Résultats
"Aucun trade clôturé pour l'instant.": "No closed trade yet.", "👉 Appuie sur ✅ Je suis rentré quand tu prends une position.": "👉 Tap ✅ I'm in when you take a position.",
"✅ TP gagnés": "✅ TP won", "❌ Stops touchés": "❌ SL hit", "🎯 Réussite": "🎯 Win rate", "💰 Total": "💰 Total", "Derniers trades :": "Last trades:",
"🤖 Bilan du bot   en cours de construction": "🤖 Bot record   being built", "🤖 Bilan du bot": "🤖 Bot record",
# News / sessions
"📅 Annonces importantes aujourd'hui (heure de Paris) :": "📅 Important news today (Paris time):", "(prévu": "(forecast", ", avant": ", previous",
"→ Pas de nouvelle entrée 15 min avant et après. Volatilité forte possible.": "→ No new entry 15 min before and after. Strong volatility possible.",
"📅 Aucune annonce majeure US aujourd'hui.": "📅 No major US news today.", "⚠️⚠️ NEWS USA dans": "⚠️⚠️ US NEWS in",
"🟥 N'ouvre AUCUN trade": "🟥 Open NO trade", "🛡 Déjà en position ? Vérifie que ton STOP est bien placé": "🛡 Already in? Check your SL is in place",
"⏳ On reprend à": "⏳ We resume at", "🚨🚨🚨 NEWS DANS": "🚨🚨🚨 NEWS IN", "🟥 Ne touche à rien": "🟥 Don't touch anything",
"🛡 Stop en place ? OK, on attend": "🛡 SL in place? OK, we wait", "✅ News passée (": "✅ News passed (",
"). 🟩 Le bot reprend la recherche d'entrées.": "). 🟩 The bot is looking for entries again.", "🔔 Ouverture de": "🔔 Opening of",
"min). Volatilité forte attendue.": "min). Strong volatility expected.", "(dans": "(in", "Londres": "London",
"comprimé sur plusieurs UT : explosion probable à l'ouverture, attends la direction.": "compressed on several timeframes: likely breakout at the open, wait for direction.",
"⚠️ Futures CME fermés en ce moment (Topstep) : signal à titre indicatif.": "⚠️ CME futures closed right now (Topstep): signal for information only.",
"(en cours)": "(now)", "🎯 Je rentre dans la position (coach)": "🎯 I'm in this position (coach)", "🤖 Mon coach": "🤖 My coach", "↩️ Repli en cours sur le 15 min : c'est lui qu'on attend pour entrer": "↩️ 15-min pullback in progress: that's what we wait for to enter", "⬇️ Tes boutons sont là 👇": "⬇️ Your buttons are here 👇", "💡 Clavier caché ? Appuie sur l'icône ⌘ à droite du champ": "💡 Keyboard hidden? Tap the ⌘ icon right of the field", "Prochaines news (heure de Paris) :": "Next news (Paris time):", "aujourd'hui": "today", "demain": "tomorrow",
" — dans ": " — in ", " jours": " days", " — en cours": " — now", "✅ Rien d'ici": "✅ Nothing within", "✅ Plus aucune annonce ni discours cette semaine": "✅ No more news or speeches this week",
"lun. ": "Mon ", "mar. ": "Tue ", "mer. ": "Wed ", "jeu. ": "Thu ", "ven. ": "Fri ", "sam. ": "Sat ", "dim. ": "Sun ", ": ÇA RETRACE": ": IT'S PULLING BACK", "😎 Le repli qu'on attend commence": "😎 The pullback we're waiting for is starting",
"🎯 Zone visée ≈": "🎯 Target zone ≈", "👀 Vue 15 min, sois patient": "👀 15-min chart, be patient", "🔔 Je te préviens dès qu'on y est": "🔔 I'll tell you as soon as we're there",
": LE REPLI EST LÀ": ": THE PULLBACK IS HERE", "se prépare": "is building", "👀 Vue 15 min, tiens-toi prêt": "👀 15-min chart, get ready", "🔔 Prochaine alerte : ÇA ARRIVE": "🔔 Next alert: IT'S COMING", "⚡⚡ PRÉPARE-TOI —": "⚡⚡ GET READY —", "🎯 On est à quelques pips de l'entrée": "🎯 We're a few pips from the entry",
"🛑 Dès que tu es dedans : SL un peu": "🛑 As soon as you're in: SL a little", "💰 TP1 juste": "💰 TP1 just", "🙅 Jamais de position sans SL": "🙅 Never a position without SL",
"🚦 Feu vert 🟢 dans un instant": "🚦 Green light 🟢 in a moment", "🛑 Mets ton SL TOUT DE SUITE": "🛑 Set your SL RIGHT NOW", "✅ Ton bot t'a déjà mis dedans 🤖": "✅ Your bot already put you in 🤖", "🤖 Mon bot": "🤖 My bot", "🤖 MON BOT": "🤖 MY BOT",
"✅ Il entre tout seul dans chaque position": "✅ It enters every position by itself", "👀 Vue 15 min • SL un peu sous / au-dessus de la mèche": "👀 15-min chart • SL a little below / above the wick",
"🎯 Le coach te suit jusqu'au TP": "🎯 The coach follows you to TP", "⏸ Il n'entre plus pour toi": "⏸ It no longer enters for you", "🔔 Tu reçois quand même les positions": "🔔 You still get the positions",
"🤖 Positions prises par ton bot": "🤖 Positions taken by your bot", "🤖 Positions prises par mon bot": "🤖 Positions taken by my bot", "⏸ Arrêts manuels": "⏸ Manual stops",
"⏸ Arrêter mon bot": "⏸ Stop my bot", "▶️ Relancer mon bot": "▶️ Restart my bot", "▶️ Ton bot est relancé": "▶️ Your bot is restarted",
"🤖 Il entre tout seul dans la prochaine position": "🤖 It will enter the next position by itself", "⏸ Ton bot est arrêté": "⏸ Your bot is stopped",
"🔔 Tu reçois toujours les positions": "🔔 You still get the positions", "▶️ Relance-le avec 🤖 Mon bot": "▶️ Restart it with 🤖 My bot",
": JE SUIS RENTRÉ, SUIS-MOI": ": I'M IN, FOLLOW ME", "📍 Repère prix : entrée ≈": "📍 Price guide: entry ≈", "🎯 Je rentre dans la prochaine position": "🎯 I'm in for the next position",
"✅ Noté ! Prochaine position": "✅ Got it! Next position", "📲 Place ton ordre limite dans la zone 🟨 (vue 15 min)": "📲 Place your limit order in the zone 🟨 (15-min chart)",
"🤖 Dès que j'entre, tu es compté dedans automatiquement": "🤖 As soon as I enter, you're counted in automatically", "🎯 Le coach te suit : SL à BE, SL remonté, TP": "🎯 The coach follows you: SL to BE, raised SL, TP",
"ℹ️ Le bot ne passe pas d'ordre à ta place sur ta plateforme": "ℹ️ The bot doesn't place orders on your platform for you", ": TU ES DEDANS": ": YOU'RE IN",
"🎯 Coach activé jusqu'au TP": "🎯 Coach on until TP", "📈 Résultat compté dans Mes résultats": "📈 Result counted in My results", "📍 Repère prix : zone ≈": "📍 Price guide: zone ≈",
"🔒 Réservé aux VIP": "🔒 VIP only", "🎁 Ta position offerte est déjà utilisée": "🎁 Your free position is already used", "📸 Partager mon gain": "📸 Share my profit",
"📸 Envoie la capture de ton gain": "📸 Send a screenshot of your profit", "🖼 Une image seulement": "🖼 One image only", "🙅 Que du trading, rien d'autre": "🙅 Trading only, nothing else",
"✅ Je la vérifie avant de la publier": "✅ I check it before publishing", "🙅 Seulement une image de ton gain (capture d'écran)": "🙅 Only an image of your profit (screenshot)",
"⏳ 3 captures max par jour. Reviens demain 🙏": "⏳ 3 screenshots max per day. Come back tomorrow 🙏", "👌 Capture reçue": "👌 Screenshot received",
"👀 Je la vérifie avant de la publier": "👀 I'm checking it before publishing", "🙏 Merci !": "🙏 Thanks!",
"🙏 Merci ! Cette capture ne sera pas publiée": "🙏 Thanks! This screenshot won't be published", "📸 Envoie une capture claire de ton gain de trading": "📸 Send a clear screenshot of your trading profit",
"✅ Ton gain est publié 🔥": "✅ Your profit is published 🔥", "🙏 Merci, ça motive tout le monde !": "🙏 Thanks, it motivates everyone!",
"🔥🔥 GAIN D'UN MEMBRE ALIGN 🔥🔥": "🔥🔥 ALIGN MEMBER PROFIT 🔥🔥", "📈 Positions BTC + Gold": "📈 BTC + Gold positions", "🎁 Ta 1re position est offerte": "🎁 Your 1st position is free",
"📸 Partage ton gain : bouton 📸 en bas": "📸 Share your profit: 📸 button below",
"🎁 TON ANALYSE GRATUITE DU JOUR": "🎁 YOUR FREE ANALYSIS OF THE DAY", "⏳ Attends que le prix vienne dans la zone 🟨": "⏳ Wait for price to reach the zone 🟨",
"✅ Analyse gratuite du jour utilisée": "✅ Free analysis of the day used", "⏰ Une nouvelle demain": "⏰ A new one tomorrow",
"💎 En VIP, plus besoin d'appuyer sur Analyse": "💎 With VIP, no need to tap Analysis", "🤖 Les positions arrivent toutes seules": "🤖 Positions arrive automatically",
"👀 Alerte « ÇA ARRIVE » juste avant chaque entrée": "👀 « IT'S COMING » alert right before each entry", "🔔 Active la cloche du bot pour ne rien louper": "🔔 Turn on the bot's bell so you miss nothing",
"🔒 Ton analyse gratuite du jour est déjà utilisée": "🔒 Your free analysis of the day is already used", "⏰ Reviens demain": "⏰ Come back tomorrow",
"💎 VIP 49,90 € / mois : plus besoin d'appuyer sur Analyse": "💎 VIP €49.90 / month: no need to tap Analysis", "🔔 Active la cloche pour ne rien louper": "🔔 Turn on the bell so you miss nothing",
"🔔 Cloche activée ? Ne rate pas le feu vert": "🔔 Bell on? Don't miss the green light", "🔔 Active la cloche (notifications) pour ne rien louper": "🔔 Turn on the bell (notifications) so you miss nothing",
"🔍 + 1 analyse complète GRATUITE par jour (bouton Analyse)": "🔍 + 1 FREE full analysis per day (Analysis button)",
"📈 Le marché MONTE": "📈 The market is RISING", "📉 Le marché DESCEND": "📉 The market is FALLING", "➖ Le marché hésite": "➖ The market is hesitating",
"🔒 Entrée : VIP": "🔒 Entry: VIP", "🔒 SL : VIP": "🔒 SL: VIP", "🔒 TP : VIP": "🔒 TP: VIP", "🔒 Prochaine entrée : VIP": "🔒 Next entry: VIP",
"👀 Les VIP savent déjà où rentrer": "👀 VIPs already know where to enter", "😬 Tu vas louper le prochain move ?": "😬 Gonna miss the next move?",
"💎 VIP 49,90 € / mois 👇": "💎 VIP €49.90 / month 👇", "👀👀 ÇA ARRIVE —": "👀👀 IT'S COMING —", "🟨 Le prix entre dans la zone": "🟨 Price is entering the zone",
"⚡ Tiens-toi prêt": "⚡ Get ready", "🚦 Feu vert 🟢 très bientôt": "🚦 Green light 🟢 very soon", "📍 Zone ≈": "📍 Zone ≈",
": TP1 TOUCHÉ 🔥🔥🔥": ": TP1 HIT 🔥🔥🔥", "pour les VIP": "for VIPs", "😬 Tu n'étais pas dedans ?": "😬 You weren't in?", "💎 Les prochaines : VIP 👇": "💎 Next ones: VIP 👇",
": OBJECTIF ATTEINT 🔥🔥🔥": ": TARGET REACHED 🔥🔥🔥", "😬 Tu as loupé ça": "😬 You missed this", "💎 Rejoins le VIP 👇": "💎 Join VIP 👇",
": SL touché": ": SL hit", "🛡 Risque maîtrisé, on repart": "🛡 Risk under control, we go again", "💎 Toutes les positions et les résultats : VIP 👇": "💎 All positions and results: VIP 👇",
": une position VIP arrive 🔥": ": a VIP position is coming 🔥", "🔒 Zone cachée": "🔒 Zone hidden", "😬 Tu vas la louper ?": "😬 Gonna miss it?", "💎 VIP 👇": "💎 VIP 👇",
": les VIP viennent de recevoir une position": ": VIPs just got a position", "🟩 LONG ⬆️ ou 🟥 SHORT ⬇️ ? 🤫": "🟩 LONG ⬆️ or 🟥 SHORT ⬇️ ? 🤫", "👀 Elle se prépare 🤫": "👀 It's building 🤫",
"😬 Tu vas louper ce move ?": "😬 Gonna miss this move?", "💎 VIP 49,90 € / mois : toutes les positions + le coach 👇": "💎 VIP €49.90 / month: all positions + the coach 👇",
"🔒 Réservé aux VIP 💎": "🔒 VIP only 💎",
"🎁🎁 POSITION DE BIENVENUE OFFERTE 🎁🎁": "🎁🎁 FREE WELCOME POSITION 🎁🎁",
"👀 Suis-la en vue 15 minutes, tout est expliqué en bougies": "👀 Follow it on the 15-min chart, everything is explained in candles",
"💎 C'est ta position offerte. Les suivantes + le coach : VIP 49,90 € / mois": "💎 This is your free position. Next ones + the coach: VIP €49.90 / month",
"🔒 Position réservée aux VIP": "🔒 VIP-only position", "🎁 Ta position de bienvenue est déjà utilisée": "🎁 Your welcome position is already used",
"💎 VIP 49,90 € / mois : toutes les positions + le coach en direct": "💎 VIP €49.90 / month: all positions + live coach",
"💎 VIP 49,90 € / mois : toutes les positions + le coach": "💎 VIP €49.90 / month: all positions + the coach",
"🎁 Ta 1re POSITION est OFFERTE": "🎁 Your 1st POSITION is FREE", "🕯 Expliquée en bougies (vue 15 min) + coach jusqu'au TP": "🕯 Explained in candles (15-min chart) + coach to TP",
"📰 Alertes news et discours gratuites": "📰 Free news and speech alerts", "🔔 Ouvertures de marché gratuites": "🔔 Free market-open alerts",
"🔒 Ensuite les positions arrivent MASQUÉES": "🔒 After that, positions arrive HIDDEN", "👉 Bouton ci-dessous, puis reviens ici et tape /start": "👉 Button below, then come back and type /start",
"🔒 Les positions en direct sont réservées aux VIP": "🔒 Live positions are VIP-only", "🎁 Ta position de bienvenue reste offerte": "🎁 Your welcome position is still free",
"⚠️ Distribution possible : le haut s'essouffle (divergence RSI)": "⚠️ Possible distribution: the top is fading (RSI divergence)",
"⚠️ Accumulation possible : le bas se charge (divergence RSI)": "⚠️ Possible accumulation: the bottom is loading (RSI divergence)",
": DISTRIBUTION possible": ": possible DISTRIBUTION", ": ACCUMULATION possible": ": possible ACCUMULATION",
"🕯 Le haut s'essouffle (divergence RSI": "🕯 The top is fading (RSI divergence", "🕯 Le bas se charge (divergence RSI": "🕯 The bottom is loading (RSI divergence",
"🙅 Prudence sur les": "🙅 Careful with", "👀 Un 🟥 SHORT ⬇️ peut se préparer": "👀 A 🟥 SHORT ⬇️ may be building", "👀 Un 🟩 LONG ⬆️ peut se préparer": "👀 A 🟩 LONG ⬆️ may be building", "(regarde en vue Daily)": "(check the Daily chart)", "(regarde en vue 4 heures)": "(check the 4h chart)",
"(regarde en vue 1 heure)": "(check the 1h chart)", "(regarde en vue 15 minutes)": "(check the 15-min chart)",
"(vue Daily)": "(Daily chart)", "(vue 4 heures)": "(4h chart)", "(vue 1 heure)": "(1h chart)", "(vue 15 minutes)": "(15-min chart)", "(dans": "(in", "🌐 English": "🌐 Français",
# Règles / accueil / indicateur
"📌 RÈGLES — ALIGN Signaux": "📌 RULES — ALIGN Signals", "1️⃣ Ce sont MES positions perso, ma vision du marché": "1️⃣ These are MY personal positions, my view of the market",
"❗ Pas un conseil en investissement": "❗ Not investment advice", "2️⃣ Les prix changent selon la plateforme (FTMO, Topstep, broker…)": "2️⃣ Prices differ between platforms (FTMO, Topstep, broker…)",
"👉 Suis les mèches et les %, pas le prix exact": "👉 Follow the wicks and %, not the exact price", "3️⃣ ⏱ Mets-toi en vue 15 minutes": "3️⃣ ⏱ Use the 15-minute chart",
"4️⃣ 🛑 Toujours un stop, derrière la mèche indiquée": "4️⃣ 🛑 Always an SL, behind the given wick", "5️⃣ 📰 Pas de trade 15 min avant et après une news": "5️⃣ 📰 No trade 15 min before and after news",
"6️⃣ 💰 TP1 touché → stop à l'entrée": "6️⃣ 💰 TP1 hit → SL to entry", "7️⃣ ⚖️ Petit risque : 1 à 2 % du compte maximum par position": "7️⃣ ⚖️ Small risk: 1 to 2 % of the account max per position",
"8️⃣ ⚠️ Le trading peut faire perdre tout le capital": "8️⃣ ⚠️ Trading can lose all your capital",
"📰 Je t'envoie les news : pas de trade juste avant ni juste après": "📰 I send you the news: no trade right before or after",
"🤖 Appuie sur ✅ Je suis rentré : ton coach IA te suit jusqu'au TP": "🤖 Tap ✅ I'm in: your AI coach follows you to TP",
"📈 Tes gains et tes pertes sont calculés tout seuls": "📈 Your wins and losses are calculated automatically",
"🧩 L'indicateur TradingView : bouton 🧩 en bas": "🧩 The TradingView indicator: 🧩 button below", "🤝 Partage à tes amis :": "🤝 Share with your friends:",
"ℹ️ Ce sont MES positions personnelles, partagées à titre informatif et éducatif. Ce n'est pas un conseil en investissement ni une recommandation personnalisée. Le trading (CFD, futures, crypto) peut faire perdre tout le capital investi : chacun décide seul et reste responsable de ses choix.":
 "ℹ️ These are MY personal positions, shared for information and education. This is not investment advice or a personal recommendation. Trading (CFDs, futures, crypto) can lose all invested capital: everyone decides alone and is responsible for their choices.",
"✅ ALIGN MTF BOT activé. Mes positions BTC et Gold arrivent ici.": "✅ ALIGN MTF BOT activated. My BTC and Gold positions arrive here.",
"⬇️ Utilise les boutons en bas.": "⬇️ Use the buttons below.", "⬇️ Utilise les boutons en bas": "⬇️ Use the buttons below", "⌨️ Utilise les boutons en bas 👇": "⌨️ Use the buttons below 👇",
"🤝 Tu aimes ALIGN Signaux ?": "🤝 Like ALIGN Signals?", "📤 Partage-le à tes amis, fais-les en profiter": "📤 Share it with your friends",
"🎁 Positions gratuites": "🎁 Free positions", "🧩 Indicateur TradingView 49,90 € / mois": "🧩 TradingView indicator €49.90 / month",
"📈 Signaux BTC + Gold en direct, simples et clairs 👇": "📈 Live BTC + Gold signals, simple and clear 👇",
"🧩 Indicateur ALIGN MTF PRO — TradingView": "🧩 ALIGN MTF PRO indicator — TradingView", "🧩 Indicateur ALIGN MTF PRO": "🧩 ALIGN MTF PRO indicator",
"✅ Ton accès est actif": "✅ Your access is active", "👤 Pseudo": "👤 Username", "📍 TradingView → Indicateurs → Sur invitation": "📍 TradingView → Indicators → Invite-only",
"✅ Tu y as droit": "✅ You're entitled to it", "✍️ Écris ton pseudo TradingView": "✍️ Type your TradingView username", "(exemple : adel_khatra)": "(example: adel_khatra)",
"📊 Alignement des 11 unités de temps": "📊 Alignment of 11 timeframes", "🟨 Zone d'entrée + Fibonacci": "🟨 Entry zone + Fibonacci",
"🛑 Stop derrière la mèche": "🛑 SL behind the wick", "💰 TP sur les grosses unités de temps": "💰 TP on the big timeframes", "⚡ Surcharge RSI + explosions": "⚡ RSI overextension + breakouts",
"🎁 Les positions restent gratuites ici": "🎁 Positions stay free here", "💎 Indicateur 49,90 € / mois": "💎 Indicator €49.90 / month",
"👉 Après paiement, reviens appuyer sur 🧩": "👉 After paying, come back and tap 🧩", "👌 Pseudo reçu": "👌 Username received",
"⏳ Ton accès arrive très vite": "⏳ Your access is coming very soon", "✅ Accès indicateur ouvert !": "✅ Indicator access open!",
"🎁 L'indicateur t'est offert !": "🎁 The indicator is a gift for you!", "👉 Appuie sur 🧩 Indicateur TradingView": "👉 Tap 🧩 TradingView indicator",
"🎁 Accès VIP offert !": "🎁 VIP access gifted!", "✅ Tu reçois maintenant toutes mes positions": "✅ You now get all my positions",
"⏸ Ton abonnement indicateur n'est plus actif.": "⏸ Your indicator subscription is no longer active.",
"⏸ Ton abonnement VIP n'est plus actif. Les signaux sont en pause.": "⏸ Your VIP subscription is no longer active. Signals are paused.", "Renouveler :": "Renew:",
"👋 ALIGN Signaux — BTC + Gold": "👋 ALIGN Signals — BTC + Gold", "⬆️⬇️ Les positions arrivent ici en direct": "⬆️⬇️ Positions arrive here live",
"👋 Bienvenue sur ALIGN Signaux (BTC + Gold)": "👋 Welcome to ALIGN Signals (BTC + Gold)", "🎁 Tu reçois GRATUITEMENT :": "🎁 You get for FREE:",
"• les alertes news 📰": "• news alerts 📰", "• les ouvertures de marché 🔔": "• market opens 🔔", "• 1 signal complet offert de temps en temps": "• 1 full free signal now and then",
"🔒 Les autres positions arrivent MASQUÉES.": "🔒 Other positions arrive HIDDEN.",
"🔓 Pour tout voir (entrée, stop, TP, coaching Oui / Non, bouton Analyse) : abonne-toi avec le bouton ci-dessous, puis reviens ici et tape /start.": "🔓 To see everything (entry, SL, TP, coaching, Analysis button): subscribe with the button below, then come back and type /start.",
"🔒 Entrée, stop, TP et coaching en direct : réservés aux VIP 💎": "🔒 Entry, SL, TP and live coaching: VIP only 💎",
"🔒 Position masquée — réservée aux abonnés VIP": "🔒 Hidden position — VIP subscribers only", "🔓 Tous les signaux + coaching en direct : bouton ci-dessous": "🔓 All signals + live coaching: button below",
"🎁🎁 SIGNAL OFFERT — pour te montrer que ça marche": "🎁🎁 FREE SIGNAL — to show you it works",
"🆕 Nouveaux boutons": "🆕 New buttons", "🚦 Chaque analyse te dit si tu peux entrer ou pas": "🚦 Each analysis tells you if you can enter or not",
"👉 Coaching perso : @": "👉 Personal coaching: @", "Contexte :": "Context:", "de la zone Daily,": "of the Daily range,", "de la zone Weekly.": "of the Weekly range.",
"au marché": "at market", "ordre limite": "limit order", "Entrée :": "Entry:", "Stop :": "SL:", "Gain/risque ≈": "Reward/risk ≈",
"⬆️ ACHAT": "⬆️ BUY", "⬇️ VENTE": "⬇️ SELL", "Prochaine news": "Next news", "📍 Prix": "📍 Price", "👉 Prix": "👉 Price",
", stop": ", SL", 
}

LANG_EN = set()                                   # téléphones qui ont choisi l'anglais
_CLES = sorted(TRAD, key=len, reverse=True)
BOUTONS_FR = ["🤖 Mon bot", "📸 Partager mon gain", "🟠 Analyse BTC", "🥇 Analyse Gold", "✅ Je suis rentré", "🚪 Je suis sorti", "📈 Mes résultats",
              "🧩 Indicateur TradingView", "💎 Devenir VIP", "❌ Non"]
INVERSE = {TRAD[b]: b for b in BOUTONS_FR}        # bouton anglais reçu → même action qu'en français

def traduire(t):
    for k in _CLES:
        if k in t:
            t = t.replace(k, TRAD[k])
    return t

def traduire_clavier(kb):
    """Traduit le texte des boutons (clavier du bas ou boutons sous un message)."""
    try:
        j = json.loads(kb)
    except Exception:
        return kb
    for cle in ("keyboard", "inline_keyboard"):
        for ligne in j.get(cle, []):
            for b in ligne:
                b["text"] = traduire(b["text"])
    if "input_field_placeholder" in j:
        j["input_field_placeholder"] = traduire(j["input_field_placeholder"])
    return json.dumps(j)

def telegram(methode, **params):
    if methode in ("sendMessage", "editMessageText", "sendPhoto") and str(params.get("chat_id")) in LANG_EN:
        if "text" in params:
            params["text"] = traduire(params["text"])
        if "caption" in params:
            params["caption"] = traduire(params["caption"])
        if params.get("reply_markup"):
            params["reply_markup"] = traduire_clavier(params["reply_markup"])
    url = f"https://api.telegram.org/bot{TOKEN}/{methode}"
    return http_json(url, urllib.parse.urlencode(params).encode())

# ───────── Boutons et jauge ─────────
CLAVIER = json.dumps({"keyboard": [[{"text": "🟠 Analyse BTC"}, {"text": "🥇 Analyse Gold"}], [{"text": "✅ Je suis rentré"}, {"text": "🚪 Je suis sorti"}],
                                   [{"text": "🤖 Mon bot"}, {"text": "📈 Mes résultats"}], [{"text": "📸 Partager mon gain"}, {"text": "🧩 Indicateur TradingView"}],
                                   [{"text": "🌐 English"}]],
                      "resize_keyboard": True, "is_persistent": True, "input_field_placeholder": "Utilise les boutons 👇"})
CLAVIER_VISITEUR = json.dumps({"keyboard": [[{"text": "🟠 Analyse BTC"}, {"text": "🥇 Analyse Gold"}], [{"text": "💎 Devenir VIP"}], [{"text": "📸 Partager mon gain"}, {"text": "🌐 English"}]],
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
           "🎁 Positions gratuites\n🧩 Indicateur TradingView 49,90 € / mois")
    url = "https://t.me/share/url?" + urllib.parse.urlencode({"url": lien, "text": "📈 Signaux BTC + Gold en direct, simples et clairs 👇"})
    return txt, json.dumps({"inline_keyboard": [[{"text": "📤 Partager à un ami", "url": url}]]})

OFFERT_JOURS = int(os.environ.get("OFFERT_JOURS", "7"))   # 1 signal complet offert aux visiteurs tous les X jours
POSITIONS_GRATUITES = os.environ.get("POSITIONS_GRATUITES", "0") == "1"   # 0 = positions VIP (49,90 €/mois), 1 position de bienvenue offerte
LIEN_INDICATEUR = os.environ.get("LIEN_INDICATEUR", "")   # lien du script TradingView « invite-only » (à remplir après publication)
PRIX_STARS = int(os.environ.get("PRIX_STARS", "2500"))   # abonnement VIP mensuel : 2 500 ⭐ ≈ 49,90 €
ECOUTE_SEC = int(os.environ.get("ECOUTE_SEC", "200"))   # (ancien réglage, gardé pour compatibilité)
DUREE_SEC = int(os.environ.get("DUREE_SEC", str(ECOUTE_SEC)))   # durée d'un lancement (5 h 40 sur GitHub = bot toujours allumé)
PAUSE_SEC = int(os.environ.get("PAUSE_SEC", "30"))   # une analyse complète BTC + Gold toutes les 30 s

def marche_demande(txt):
    """« Analyse BTC » → BTC, « Analyse Gold » → GOLD, « Analyse » seul → les deux (None)."""
    t = txt.lower()
    return "BTC" if "btc" in t else "GOLD" if ("gold" in t or "or" in t.split()) else None

def tendance_armee(r, cle):
    """Une fois 15m + 1h + 4h alignés, la tendance reste « armée » pendant le repli :
    le 15 min peut se retourner (c'est le repli qu'on attend) tant que le 4 h reste dans le sens et que le 1 h n'est pas contre."""
    d = r["confirme"]
    if d:
        cle["arme"] = d
        return r
    a = cle.get("arme")
    if a and r["dirs"][9] == a and r["dirs"][7] != -a:
        r["confirme"] = a; r["repli"] = True
    elif a:
        cle["arme"] = 0
    return r

def analyse_marche(etat, pair):
    r = analyser(pair)
    m = next((k for k, v in MARCHES.items() if v == pair), None)
    if m:
        tendance_armee(r, (etat or {}).setdefault(m, {}))
    r["annonce"] = annonce_proche(etat or {}, int(time.time()))
    r["news"] = news_txt(etat or {})
    return r

def boutons_canal(etat, texte):
    """Boutons sous chaque message de la chaîne VIP : ils ouvrent le coach en privé, au bon endroit."""
    bot = etat.get("bot") or "align_mtf_adel_bot"
    m = next((x for x in MARCHES if x in texte.split("\n")[0]), None)
    lien = lambda p: f"https://t.me/{bot}?start={p}"
    lignes = []
    if m and any(k in texte for k in ("JE PRÉPARE", "ÇA ARRIVE", "PRÉPARE-TOI", "J'ENTRE MAINTENANT", "REPLI", "RETRACE", "parti")):
        lignes.append([{"text": "🎯 Je rentre dans la position (coach)", "url": lien(f"auto_{m.lower()}")}])
    lignes.append([{"text": "🟠 Analyse BTC", "url": lien("analyse_btc")}, {"text": "🥇 Analyse Gold", "url": lien("analyse_gold")}])
    lignes.append([{"text": "🤖 Mon coach", "url": lien("mon_bot")}, {"text": "📈 Mes résultats", "url": lien("resultats")}])
    return json.dumps({"inline_keyboard": lignes})

def bouton_auto(m):
    return json.dumps({"inline_keyboard": [[{"text": "🎯 Je rentre dans la prochaine position", "callback_data": f"auto:{m}"}]]})

def markup_analyse(etat, m, r):
    """Sous l'analyse : bouton « Je rentre dans la prochaine position » quand une entrée se prépare."""
    cle = etat.get(m, {}); d = r["confirme"]
    if d and not cle.get("trade") and cle.get("ordre") and not etire(r, d):
        return bouton_auto(m)
    return CLAVIER

def inscrire_auto(etat, cid, m):
    """L'utilisateur réserve sa place : dès que le bot entre, il est compté dedans au même prix (coach + résultats)."""
    liste = etat.setdefault("auto", {}).setdefault(m, [])
    if cid not in liste:
        liste.append(cid)
    o = etat.get(m, {}).get("ordre")
    d = (o or {}).get("d") or etat.get(m, {}).get("aligne") or 1
    _envoi_sur(cid, reply_markup=CLAVIER, text=(
        f"✅ Noté ! Prochaine position {ICONE.get(m, '')} {m}\n{SENS[d]}\n"
        "📲 Place ton ordre limite dans la zone 🟨 (vue 15 min)\n"
        f"🛑 SL un peu {'SOUS la mèche du dernier creux' if d == 1 else 'AU-DESSUS de la mèche du dernier sommet'}\n"
        + (f"📍 Repère prix : zone ≈ {px(o.get('za', o['e']))} – {px(o.get('zb', o['e']))} • SL ≈ {px(o['sl'])}\n" if o else "")
        + "🤖 Dès que j'entre, tu es compté dedans automatiquement\n🎯 Le coach te suit : SL à BE, SL remonté, TP\n"
          "ℹ️ Le bot ne passe pas d'ordre à ta place sur ta plateforme"))

def bot_on(etat, cid):
    return cid not in etat.get("bot_off", [])

def stats_bot(etat, cid):
    return etat.setdefault("stats_bot", {}).setdefault(cid, {"arrets": 0, "auto": 0})

def menu_bot(etat, cid):
    on = bot_on(etat, cid); st = stats_bot(etat, cid)
    _envoi_sur(cid, text=(f"🤖 MON BOT   {'▶️ ON' if on else '⏸ OFF'}\n━━━━━━━━━━━━\n"
                          + ("✅ Il entre tout seul dans chaque position\n👀 Vue 15 min • SL un peu sous / au-dessus de la mèche\n🎯 Le coach te suit jusqu'au TP\n"
                             if on else "⏸ Il n'entre plus pour toi\n🔔 Tu reçois quand même les positions\n")
                          + f"━━━━━━━━━━━━\n🤖 Positions prises par ton bot   {st['auto']}\n⏸ Arrêts manuels   {st['arrets']}"),
               reply_markup=json.dumps({"inline_keyboard": [[{"text": "⏸ Arrêter mon bot", "callback_data": "botoff:x"} if on
                                                            else {"text": "▶️ Relancer mon bot", "callback_data": "boton:x"}]]}))

def regler_bot(etat, cid, on):
    off = etat.setdefault("bot_off", [])
    if on and cid in off:
        off.remove(cid)
    elif not on and cid not in off:
        off.append(cid); stats_bot(etat, cid)["arrets"] += 1
    _envoi_sur(cid, reply_markup=CLAVIER, text=("▶️ Ton bot est relancé\n🤖 Il entre tout seul dans la prochaine position" if on
                                                else "⏸ Ton bot est arrêté\n🔔 Tu reçois toujours les positions\n▶️ Relance-le avec 🤖 Mon bot"))

def entrer_inscrits(etat, m, tr, chats=()):
    """Le bot vient d'entrer : il fait entrer automatiquement tous les membres dont le bot est ON,
    plus ceux qui ont appuyé sur 🎯, au prix d'entrée du bot (coach + résultats comptés)."""
    auto = [c for c in chats if bot_on(etat, c) and c not in etat.get("prospects", []) and c != etat.get("canal")]
    for cid in list(dict.fromkeys(etat.get("auto", {}).pop(m, []) + auto)):
        if isinstance(tr.setdefault("qui", {}).get(cid), dict):
            continue
        tr["qui"][cid] = {"e": tr["e"], "sl": tr["sl"], "tp1": tr["tp1"], "d": tr["d"], "t": int(time.time())}
        if cid in etat.get("prospects", []):
            etat.setdefault("bienvenue", {}).setdefault(cid, m)
        stats_bot(etat, cid)["auto"] += 1
        _envoi_sur(cid, text=(
            f"🤖 {ICONE.get(m, '')} {m} : JE SUIS RENTRÉ, SUIS-MOI\n{SENS[tr['d']]}\n"
            "👀 Mets-toi en vue 15 minutes\n"
            f"🛑 SL un peu {'SOUS la mèche du dernier creux' if tr['d'] == 1 else 'AU-DESSUS de la mèche du dernier sommet'}\n"
            f"📍 Repère prix : entrée ≈ {px(tr['e'])} • SL ≈ {px(tr['sl'])} • TP1 ≈ {px(tr['tp1'])}\n"
            "🛑 Mets ton SL TOUT DE SUITE\n🎯 Coach activé jusqu'au TP\n📈 Résultat compté dans Mes résultats"),
            reply_markup=json.dumps({"inline_keyboard": [[{"text": "⏸ Arrêter mon bot", "callback_data": "botoff:x"}]]}))

def envoyer_analyse(cid, etat=None, mq=None):
    for nom_marche, pair in MARCHES.items():
        if mq and mq != nom_marche:
            continue
        try:
            r = analyse_marche(etat, pair)
            telegram("sendMessage", chat_id=cid, text=texte_etat(nom_marche, r, (etat or {}).get(nom_marche)), reply_markup=markup_analyse(etat or {}, nom_marche, r))
        except Exception as ex:
            print("analyse", ex)

def prix_actuel(m):
    """Dernier prix du marché (pour figer l'entrée ou la sortie d'un abonné) : XAUUSD spot pour le Gold, Kraken pour le BTC."""
    try:
        if MARCHES[m] == "XAUUSD":
            return or_spot()
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
    st["hist"] = (st["hist"] + [[m, round(pts, 2), round(pct, 2), motif, int(time.time()), pos["e"], sortie]])[-20:]
    pos["fini"] = True
    _envoi_sur(cid, reply_markup=CLAVIER, text=(
        f"{'✅' if pts > 0 else '❌'} {m} clôturé\n"
        f"{motif}\n"
        f"📌 Entrée   {px(pos['e'])}\n"
        f"🚪 Sortie   {px(sortie)}\n"
        f"{'⬆️' if pts > 0 else '⬇️'} {pts:+,.2f} pts\n".replace(",", " ")
        + f"📊 {pct:+.2f} %\n"
        + ("🎉 Bravo !\n📸 Partage ton gain : bouton 📸 en bas" if pts > 0 else "💪 On repart au prochain")))

def texte_bilan(etat):
    b = etat.get("bilan")
    if not b or not (b["tp"] + b["sl"]):
        return "🤖 Bilan du bot   en cours de construction"
    n = b["tp"] + b["sl"]
    return (f"🤖 Bilan du bot\n✅ TP   {b['tp']}\n❌ SL   {b['sl']}\n"
            f"🎯 Réussite   {round(100 * b['tp'] / n)} %\n💰 Total   {b['pct']:+.2f} %")

def texte_resultats(etat, cid):
    sb = stats_bot(etat, cid)
    return (_texte_resultats(etat, cid) + "\n━━━━━━━━━━━━\n"
            + f"🤖 Mon bot   {'▶️ ON' if bot_on(etat, cid) else '⏸ OFF'}\n🤖 Positions prises par mon bot   {sb['auto']}\n⏸ Arrêts manuels   {sb['arrets']}\n━━━━━━━━━━━━\n"
            + texte_bilan(etat))

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
    l += [f"{'✅ TP' if h[1] > 0 else '❌ SL'} {ICONE.get(h[0], '')} {h[0]}   {h[2]:+.2f} %"
          + (f"\n     📌 {px(h[5])} → 🚪 {px(h[6])}" if len(h) > 6 else "") for h in st["hist"][-5:]]
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
        if not cands and trades:
            _envoi_sur(cid, text="✅ Ton bot t'a déjà mis dedans 🤖\n🎯 Le coach te suit jusqu'au TP", reply_markup=CLAVIER)
            return
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

def changer_langue(etat, cid, anglais, membre_ok):
    langues = etat.setdefault("en", [])
    if anglais and cid not in langues:
        langues.append(cid)
    if not anglais and cid in langues:
        langues.remove(cid)
    LANG_EN.clear(); LANG_EN.update(langues)
    kb = CLAVIER if membre_ok else CLAVIER_VISITEUR
    _envoi_sur(cid, reply_markup=kb, text=("✅ Language: English 🇬🇧\nThe whole bot now speaks English\n🌐 Tap 🌐 Français to switch back"
                                         if anglais else "✅ Langue : Français 🇫🇷\nTout le bot parle maintenant français\n🌐 Appuie sur 🌐 English pour changer"))
    try:   # règles épinglées dans la nouvelle langue
        res = telegram("sendMessage", chat_id=cid, text=REGLES, disable_notification="true")
        telegram("pinChatMessage", chat_id=cid, message_id=res["result"]["message_id"], disable_notification="true")
    except Exception as ex:
        print("regles langue", ex)

COMMANDES = {"/analyse_btc": "🟠 Analyse BTC", "/analyse_gold": "🥇 Analyse Gold", "/mon_bot": "🤖 Mon bot",
             "/resultats": "📈 Mes résultats", "/gain": "📸 Partager mon gain", "/vip": "💎 Devenir VIP",
             "/english": "🌐 English", "/francais": "🌐 Français"}

def installer_menu(etat):
    """Bouton « Menu » à gauche du champ + description du bot (une seule fois par version)."""
    if etat.get("menu") == 2:
        return
    fr = [("analyse_btc", "🟠 Analyse BTC"), ("analyse_gold", "🥇 Analyse Gold"), ("mon_bot", "🤖 Mon bot ON / OFF"),
          ("resultats", "📈 Mes résultats"), ("gain", "📸 Partager mon gain"), ("vip", "💎 Devenir VIP"),
          ("boutons", "⌨️ Faire revenir les boutons"), ("english", "🌐 English")]
    en = [("analyse_btc", "🟠 BTC Analysis"), ("analyse_gold", "🥇 Gold Analysis"), ("mon_bot", "🤖 My bot ON / OFF"),
          ("resultats", "📈 My results"), ("gain", "📸 Share my profit"), ("vip", "💎 Become VIP"),
          ("boutons", "⌨️ Bring back the buttons"), ("francais", "🌐 Français")]
    try:
        telegram("setMyCommands", commands=json.dumps([{"command": c, "description": d} for c, d in fr]))
        telegram("setMyCommands", commands=json.dumps([{"command": c, "description": d} for c, d in en]), language_code="en")
        telegram("setChatMenuButton", menu_button=json.dumps({"type": "commands"}))
        telegram("setMyShortDescription", short_description="📈 Positions BTC & Gold en direct • 🤖 Coach jusqu'au TP • 🎁 1re position offerte")
        telegram("setMyDescription", description=("🤖 ALIGN Coach — BTC & Gold\n\n🟩 LONG / 🟥 SHORT expliqués en bougies (vue 15 min)\n"
                                                  "👀 Alertes ÇA ARRIVE • PRÉPARE-TOI • J'ENTRE\n🎯 Coach : SL à BE, SL remonté, TP\n"
                                                  "📰 News et discours Fed à l'heure de Paris\n🎁 Ta 1re position est offerte\n\n"
                                                  "ℹ️ Mes positions perso, pas un conseil. Le trading comporte un risque de perte."))
        etat["menu"] = 2
    except Exception as ex:
        print("menu", ex)

def recevoir_gain(etat, cid, msg):
    """📸 Partager mon gain : seulement une IMAGE, vérifiée par le propriétaire avant publication. Renvoie True si traité."""
    tx = (msg.get("text") or "").lower()
    if "partager mon gain" in tx or tx.startswith("/gain"):
        etat.setdefault("attente_photo", {})[cid] = time.time()
        _envoi_sur(cid, text="📸 Envoie la capture de ton gain\n🖼 Une image seulement\n🙅 Que du trading, rien d'autre\n✅ Je la vérifie avant de la publier")
        return True
    autre = any(k in msg for k in ("video", "document", "sticker", "animation", "video_note", "voice", "audio"))
    if not msg.get("photo") and not (autre and cid in etat.get("attente_photo", {})):
        return False
    if autre:
        _envoi_sur(cid, text="🙅 Seulement une image de ton gain (capture d'écran)")
        return True
    jour = datetime.datetime.now(PARIS).strftime("%Y-%m-%d")
    compte = etat.setdefault("photos_jour", {})
    if compte.get(cid, [None, 0])[0] == jour and compte[cid][1] >= 3:
        _envoi_sur(cid, text="⏳ 3 captures max par jour. Reviens demain 🙏")
        return True
    compte[cid] = [jour, (compte.get(cid, [jour, 0])[1] if compte.get(cid, [None])[0] == jour else 0) + 1]
    etat.get("attente_photo", {}).pop(cid, None)
    fr = msg.get("from", {})
    nom = fr.get("first_name", "Membre")
    pid = str(msg.get("message_id", int(time.time())))
    etat.setdefault("photos", {})[pid] = {"cid": cid, "file": msg["photo"][-1]["file_id"], "nom": nom}
    for p in proprio(etat):
        try:
            telegram("sendPhoto", chat_id=p, photo=msg["photo"][-1]["file_id"],
                     caption=f"📸 Gain envoyé par {nom}" + (f" @{fr['username']}" if fr.get("username") else "") + "\n👀 Vérifie l'image avant de publier",
                     reply_markup=json.dumps({"inline_keyboard": [[{"text": "✅ Publier", "callback_data": f"pub:{pid}"},
                                                                   {"text": "❌ Refuser", "callback_data": f"refus:{pid}"}]]}))
        except Exception as ex:
            print("photo proprio", ex)
    _envoi_sur(cid, text="👌 Capture reçue\n👀 Je la vérifie avant de la publier\n🙏 Merci !")
    return True

def valider_gain(etat, chats, pid, publier, cb):
    ph = etat.get("photos", {}).pop(pid, None)
    try:
        telegram("answerCallbackQuery", callback_query_id=cb["id"], text="✅ Publié" if publier else "❌ Refusé")
    except Exception:
        pass
    if not ph:
        return
    if not publier:
        _envoi_sur(ph["cid"], text="🙏 Merci ! Cette capture ne sera pas publiée\n📸 Envoie une capture claire de ton gain de trading")
        return
    legende = f"🔥🔥 GAIN D'UN MEMBRE ALIGN 🔥🔥\n👤 {ph['nom']}\n📈 Positions BTC + Gold\n🎁 Ta 1re position est offerte\n👉 @{etat.get('bot') or 'align_mtf_adel_bot'}"
    cibles = [etat["canal_preuves"]] if etat.get("canal_preuves") else list(etat.get("prospects", []))
    for c in cibles:
        try:
            telegram("sendPhoto", chat_id=c, photo=ph["file"], caption=legende,
                     **({"reply_markup": bouton_payer(etat)} if etat.get("lien") and c != etat.get("canal_preuves") else {}))
        except Exception as ex:
            print("publier gain", ex)
    _envoi_sur(ph["cid"], text="✅ Ton gain est publié 🔥\n🙏 Merci, ça motive tout le monde !")

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
            if choix in ("boton", "botoff"):
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="▶️ ON" if choix == "boton" else "⏸ OFF")
                except Exception:
                    pass
                regler_bot(etat, qui, choix == "boton")
                continue
            if choix == "auto":
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="✅ Noté")
                except Exception:
                    pass
                if autorise(etat, qui, cb["from"]["id"]) or qui not in etat.get("bienvenue", {}):
                    inscrire_auto(etat, qui, mk)
                else:
                    _envoi_sur(qui, text="🔒 Réservé aux VIP\n🎁 Ta position offerte est déjà utilisée\n💎 VIP 49,90 € / mois 👇",
                               **({"reply_markup": bouton_payer(etat)} if etat.get("lien") else {}))
                continue
            if choix in ("pub", "refus") and qui in proprio(etat):
                valider_gain(etat, chats, mk, choix == "pub", cb)
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
            bienvenue = etat.get("bienvenue", {}).get(qui) == mk and etat.get(mk, {}).get("trade")
            if not bienvenue and not autorise(etat, qui, cb["from"]["id"]):
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
        tx = msg.get("text", "")
        mots = tx.split() if tx.startswith("/") else []
        cmd = mots[0].split("@")[0].lower() if mots else ""
        charge = mots[1].lower() if len(mots) > 1 else ""
        if cmd == "/start" and charge:
            if charge.startswith("auto_") and charge[5:].upper() in MARCHES:
                if cid not in chats and cid not in etat.get("prospects", []) and not autorise(etat, cid, msg.get("from", {}).get("id")):
                    etat.setdefault("prospects", []).append(cid); refuser(etat, cid)
                inscrire_auto(etat, cid, charge[5:].upper())
                continue
            if "/" + charge in COMMANDES:
                cmd = "/" + charge
        if cmd in COMMANDES:
            msg["text"] = tx = COMMANDES[cmd]
        if cmd in ("/start", "/boutons"):
            # Les boutons reviennent toujours (si le clavier du téléphone les a cachés)
            _envoi_sur(cid, text="⬇️ Tes boutons sont là 👇\n💡 Clavier caché ? Appuie sur l'icône ⌘ à droite du champ",
                       reply_markup=CLAVIER if autorise(etat, cid, msg.get("from", {}).get("id")) else CLAVIER_VISITEUR)
            if cid in etat.get("prospects", []) or cid in proprio(etat):
                continue
        if tx in INVERSE:
            msg["text"] = tx = INVERSE[tx]
        bas = tx.lower()
        if recevoir_gain(etat, cid, msg):
            continue
        if "english" in bas or "français" in bas or "francais" in bas:
            changer_langue(etat, cid, "english" in bas, autorise(etat, cid, msg.get("from", {}).get("id")))
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
            telegram("sendMessage", chat_id=cid, text="✅ ALIGN MTF BOT activé. Mes positions BTC et Gold arrivent ici.\n🔔 Active la cloche (notifications) pour ne rien louper\n⬇️ Utilise les boutons en bas.\n\n" + AVERTISSEMENT, reply_markup=CLAVIER)
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
        if "mon bot" in txt or "mon_bot" in txt:
            menu_bot(etat, cid)
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
    return json.dumps({"inline_keyboard": [[{"text": "🧩 Obtenir l'indicateur (49,90 € / mois)", "url": lien}]]}) if lien else None

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
        "🎁 Les positions restent gratuites ici\n💎 Indicateur 49,90 € / mois\n"
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
    return json.dumps({"inline_keyboard": [[{"text": "🔓 Débloquer les positions (49,90 € / mois)", "url": lien}]]}) if lien else None

def analyse_visiteur(etat, cid, mq=None):
    """Visiteur : 1 analyse COMPLÈTE gratuite par jour (sens, verdict, point d'entrée en bougies).
    Les suivantes du même jour : sens du marché seulement + invitation au VIP (positions automatiques)."""
    kw = {"reply_markup": bouton_payer(etat)} if etat.get("lien") else {"reply_markup": CLAVIER_VISITEUR}
    jour = datetime.datetime.now(PARIS).strftime("%Y-%m-%d")
    utilise = etat.setdefault("analyse_gratuite", {}).get(cid) == jour
    for nom_marche, pair in MARCHES.items():
        if mq and mq != nom_marche:
            continue
        try:
            r = analyse_marche(etat, pair); cle = etat.get(nom_marche, {})
            if utilise:
                _envoi_sur(cid, text=texte_etat(nom_marche, r, cle, vip=False), **kw)
                continue
            txt = "🎁 TON ANALYSE GRATUITE DU JOUR\n\n" + texte_etat(nom_marche, r, cle)
            d = r["confirme"]; p = r["m1"][-1]["c"]
            if not cle.get("trade") and d and not etire(r, d) and not bloque_dw(r, d) and not r.get("annonce"):
                o = cle.get("ordre") or point_entree(r, d, p)
                txt += "\n\n" + fmt_trade(nom_marche, o, p) + "\n⏳ Attends que le prix vienne dans la zone 🟨"
            _envoi_sur(cid, text=txt, reply_markup=CLAVIER_VISITEUR)
        except Exception as ex:
            print("analyse visiteur", ex)
    if not utilise:
        etat["analyse_gratuite"][cid] = jour
        _envoi_sur(cid, text=("✅ Analyse gratuite du jour utilisée\n⏰ Une nouvelle demain\n━━━━━━━━━━━━\n"
                              "💎 En VIP, plus besoin d'appuyer sur Analyse\n🤖 Les positions arrivent toutes seules\n"
                              "👀 Alerte « ÇA ARRIVE » juste avant chaque entrée\n🔔 Active la cloche du bot pour ne rien louper"), **kw)
    else:
        _envoi_sur(cid, text=("🔒 Ton analyse gratuite du jour est déjà utilisée\n⏰ Reviens demain\n━━━━━━━━━━━━\n"
                              "💎 VIP 49,90 € / mois : plus besoin d'appuyer sur Analyse\n🤖 Les positions arrivent toutes seules\n"
                              "👀 Alerte « ÇA ARRIVE » juste avant chaque entrée\n🔔 Active la cloche pour ne rien louper"), **kw)

def refuser(etat, cid):
    _envoi_sur(cid, text="👋 ALIGN Signaux — BTC + Gold\n⬆️⬇️ Les positions arrivent ici en direct", reply_markup=CLAVIER_VISITEUR)
    kw = {"reply_markup": bouton_payer(etat)} if etat.get("lien") else {}
    _envoi_sur(cid, text=("👋 Bienvenue sur ALIGN Signaux (BTC + Gold)\n\n"
                          "🎁 Ta 1re POSITION est OFFERTE\n"
                          "🔍 + 1 analyse complète GRATUITE par jour (bouton Analyse)\n"
                          "🕯 Expliquée en bougies (vue 15 min) + coach jusqu'au TP\n"
                          "📰 Alertes news et discours gratuites\n"
                          "🔔 Ouvertures de marché gratuites\n\n"
                          "🔒 Ensuite les positions arrivent MASQUÉES\n"
                          "💎 VIP 49,90 € / mois : toutes les positions + le coach en direct\n"
                          "👉 Bouton ci-dessous, puis reviens ici et tape /start\n\n" + AVERTISSEMENT), **kw)

def masquer(texte):
    """Cache tous les prix (entrée, stop, TP) pour les visiteurs non abonnés."""
    texte = re.sub(r"[+-]\d+,\d+ %", "🔒 %", texte)
    return re.sub(r"(?<!\w)\d{1,3}(?: \d{3})*\.\d+", "🔒🔒🔒", texte).replace("\n\nTu es rentré ?", "")

def envoyer_prospects(etat, texte, signal, clavier=None):
    """Visiteurs : news en clair ; UNE position de bienvenue complète (bougies + coach) ;
    ensuite tout est caché, avec des messages courts « tu loupes ça » et le bouton VIP."""
    entree = signal and "J'ENTRE MAINTENANT" in texte
    kw = {"reply_markup": bouton_payer(etat)} if etat.get("lien") else {}
    deja = etat.setdefault("bienvenue", {})
    tete = texte.split("\n")[0]
    m = next((x for x in MARCHES if x in tete), None)
    chiffres = bool(re.search(r"(?<!\w)\d{1,3}(?: \d{3})*\.\d+", texte))
    news = tete.startswith(("📅", "⚠️⚠️", "🚨", "✅ News", "🔔 Ouverture")) or "NEWS" in tete
    tr = etat.get(m, {}).get("trade") if m else None
    pct_tp = (tr["d"] * (tr["tp1"] - tr["e"]) / tr["e"] * 100) if tr else None
    fomo = None
    if m and ("TP1" in tete and "touché" in tete) and pct_tp:
        fomo = f"🔥🔥🔥 {ICONE.get(m, '')} {m} : TP1 TOUCHÉ 🔥🔥🔥\n💰 +{pct_tp:.2f} % pour les VIP\n😬 Tu n'étais pas dedans ?\n💎 Les prochaines : VIP 👇"
    elif m and ("objectif final" in tete or "TP2 touché" in tete):
        g = etat.get(m, {}).get("dernier")
        fomo = f"🔥🔥🔥 {ICONE.get(m, '')} {m} : OBJECTIF ATTEINT 🔥🔥🔥\n" + (f"💰 +{g:.2f} % pour les VIP\n" if g else "") + "😬 Tu as loupé ça\n💎 Rejoins le VIP 👇"
    elif m and "stop" in tete.lower() and "touché" in tete:
        fomo = f"❌ {ICONE.get(m, '')} {m} : SL touché pour les VIP\n🛡 Risque maîtrisé, on repart\n💎 Toutes les positions et les résultats : VIP 👇"
    elif m and ("ÇA ARRIVE" in tete or "PRÉPARE-TOI" in tete or "RETRACE" in tete or "REPLI EST LÀ" in tete):
        fomo = f"👀 {ICONE.get(m, '')} {m} : une position VIP arrive 🔥\n🔒 Zone cachée\n😬 Tu vas la louper ?\n💎 VIP 👇"
    for cid in list(etat.get("prospects", [])):
        sa_bienvenue = m and deja.get(cid) == m and tr is not None
        if signal and cid not in deja:
            txt = ("🎁🎁 POSITION DE BIENVENUE OFFERTE 🎁🎁\n"
                   "👀 Suis-la en vue 15 minutes, tout est expliqué en bougies\n\n" + texte)
            k = {"reply_markup": clavier} if (entree and clavier) else {}
            if entree:
                deja[cid] = m
                txt += "\n\n💎 C'est ta position offerte. Les suivantes + le coach : VIP 49,90 € / mois"
        elif sa_bienvenue and not signal:
            txt, k = texte, {}          # sa position offerte est en cours : il suit tout en clair
        elif signal:
            txt = (f"🔒 {ICONE.get(m, '')} {m} : les VIP viennent de recevoir une position\n"
                   + ("🟩 LONG ⬆️ ou 🟥 SHORT ⬇️ ? 🤫\n" if entree else "👀 Elle se prépare 🤫\n")
                   + "😬 Tu vas louper ce move ?\n💎 VIP 49,90 € / mois : toutes les positions + le coach 👇")
            k = kw
        elif fomo:
            txt, k = fomo, kw
        elif news or not chiffres:
            txt, k = texte, {}
        else:
            txt, k = masquer(texte) + "\n🔒 Réservé aux VIP 💎", kw
        try:
            telegram("sendMessage", chat_id=cid, text=txt, **k)
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
    titre = chat.get("title", "")
    if st == "administrator" and any(k in titre.lower() for k in ("résultat", "resultat", "preuve", "gain", "result")):
        etat["canal_preuves"] = cid; etat["canal_preuves_nom"] = titre
        etat["lien_preuves"] = f"https://t.me/{chat['username']}" if chat.get("username") else etat.get("lien_preuves", "")
        for p in proprio(etat):
            _envoi_sur(p, text=f"✅ Chaîne publique « {titre} » connectée.\n📸 Les gains que tu valides y seront publiés.")
        return
    if etat.get("canal_preuves") == cid and st in ("left", "kicked", "member"):
        etat.pop("canal_preuves", None); return
    if st == "administrator":
        etat["canal"] = cid; etat["canal_nom"] = chat.get("title", "")
        texte = f"✅ Bot connecté à la chaîne « {etat['canal_nom']} ». Les signaux y seront publiés automatiquement."
        try:
            if chat.get("type") == "channel" and (not etat.get("lien") or etat.get("prix_lien", 500) != PRIX_STARS):
                res = telegram("createChatSubscriptionInviteLink", chat_id=cid, name="Abonnement VIP",
                               subscription_period=2592000, subscription_price=PRIX_STARS)["result"]
                etat["lien"] = res["invite_link"]; etat["prix_lien"] = PRIX_STARS
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
                + (f"\n🛑 Ton stop   {px(pos.get('sl_conseil', pos['sl']))}" if isinstance(pos, dict) else "")
                + f"\n{r.get('news', '')}")
    if tr:
        titre, _ = verdict(r, cle)
        return f"{tete}\n🔌 Position ouverte   {SENS[tr['d']]}\n{titre.splitlines()[0]}"
    maj, n_ok = alignement(r)
    if not d:   # étape 1 : l'alignement se charge (0 → 40 %)
        return (f"{tete}\n{prochaine(r, cle)}\n{barre_pct(40 * n_ok / 3)}\n🧭 Alignement   {n_ok}/3 ⏳")
    if etire(r, d):
        return f"{tete}\n🚀 Déjà parti : patience\n{barre_pct(40)}\n{prochaine(r, cle)}"
    if bloque_dw(r, d) and not cle.get("ordre"):
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
                           for x in brut if x.get("country") == "USD" and (x.get("impact") == "High" or (
                               x.get("impact") == "Medium" and any(k in x.get("title", "") for k in ("Speaks", "FOMC", "Fed", "Powell", "PCE", "PPI", "CPI", "Jobless", "Claims",
                                                                        "Retail", "GDP", "ISM", "Payrolls", "JOLTS", "Sentiment", "Employment"))))]
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

JOURS_FR = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]

def quand_txt(t):
    """« aujourd'hui 14:30 », « demain 10:00 », « mar. 10/11 14:30 » — toujours à l'heure de Paris."""
    d = datetime.datetime.fromtimestamp(t, PARIS); auj = datetime.datetime.now(PARIS).date()
    jour = "aujourd'hui" if d.date() == auj else "demain" if (d.date() - auj).days == 1 else f"{JOURS_FR[d.weekday()]} {d.strftime('%d/%m')}"
    return f"{jour} {d.strftime('%H:%M')}"

def dans_txt(sec):
    mn = round(sec / 60)
    if mn <= 0:
        return "en cours"
    if mn < 60:
        return f"dans {mn} min"
    if mn < 2880:
        return f"dans {mn // 60} h {mn % 60:02d}"
    return f"dans {mn // 1440} jours"

def news_txt(etat, heures=4, n=2):
    """Les prochaines annonces ET discours USA (Fed, CPI, NFP…) à l'heure de Paris, avec le compte à rebours."""
    maintenant = time.time()
    cal = etat.get("cal", {})
    if not cal.get("t"):
        return "📰 News : calendrier indisponible"
    ev = sorted((e for e in cal.get("ev", []) if e["t"] - maintenant >= -15 * 60), key=lambda e: e["t"])
    if not ev:
        return "✅ Plus aucune annonce ni discours cette semaine"
    proche = ev[0]["t"] - maintenant <= heures * 3600
    lignes = [("⚠️ " if proche else "📰 ") + "Prochaines news (heure de Paris) :"]
    for e in ev[:n]:
        ic = "🎤" if "speak" in e["titre"].lower() else "📰"
        lignes.append(f"{ic} {quand_txt(e['t'])} {e['titre']} — {dans_txt(e['t'] - maintenant)}")
    if not proche:
        lignes.append(f"✅ Rien d'ici {heures} h")
    return "\n".join(lignes)

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
    tete = ("🟩🟩🟩  LONG ⬆️  " if d == 1 else "🟥🟥🟥  SHORT ⬇️  ") + m
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
            f"🕯 EN BOUGIES (marche sur toutes les plateformes) :\n"
            f"1️⃣ 👀 Mets-toi en vue 15 minutes\n"
            f"2️⃣ 🛑 SL : un tout petit peu {'SOUS' if d == 1 else 'AU-DESSUS de'} {meche}\n"
            f"3️⃣ 🟨 Entrée {SENS[d]} : sur le {'repli' if d == 1 else 'rebond'}, vers la moitié de la dernière grande bougie {'verte' if d == 1 else 'rouge'}\n"
            + (f"4️⃣ 💰 TP1 : juste {'sous la' if d == 1 else 'au-dessus du'} {tr['n1']} (regarde en vue {vue(tr['n1'])})\n"
               if "projection" not in tr["n1"] else f"4️⃣ 💰 TP1 : environ {tr['rr']:.1f} fois ton risque\n")
            + (f"5️⃣ 🏁 TP2 : {tr['n2']} (vue {vue(tr['n2'])})\n" if "projection" not in tr["n2"] else "5️⃣ 🏁 TP2 : on laisse courir, je te guide\n")
            + 
            f"💡 TP1 touché → SL à BE\n\n"
            f"📍 Repère prix (XAUUSD / Kraken BTC) :\n{echelle}\n\n"
            f"Risque {barres(risque)}\nGain   {barres(gain)}  (x{tr['rr']:.1f})\n\n{MINI_AVERT}")

def vue(nom_niveau):
    """Unité de temps à regarder pour voir le niveau (4h, Daily, 1h…)."""
    for u, t in (("Daily", "Daily"), ("4h", "4 heures"), ("1h", "1 heure"), ("15m", "15 minutes")):
        if u in nom_niveau:
            return t
    return "4 heures"

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
    # Grands objectifs : niveaux 4h / Daily uniquement (on vise les grosses unités de temps)
    cibles = sorted([z for z in r["grosses"] if z[1] in ("4h", "Daily") and d * (z[0] - e) >= risque * GAIN_MIN], key=lambda z: d * z[0])
    t1 = cibles[0] if cibles else (e + d * risque * 2.5, "projection 2,5 x le risque")
    loin = [z for z in cibles if d * (z[0] - t1[0]) >= 2 * a]
    t2 = loin[0] if loin else (e + d * risque * 5, "projection 5 x le risque")
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
                        + ("🔒 Mets ton SL à BE (prix d'entrée)" if prog > 0.2 else "✂️ Le trade n'avance pas\n✂️ Je coupe avant la news"))
    for c in dedans:
        for t in msgs:
            _envoi_sur(c, text=t, reply_markup=CLAVIER)
        gerer_stop(etat, m, r, tr, c)

def gerer_stop(etat, m, r, tr, c):
    """Vrai agent : monte le stop de l'abonné derrière chaque support (long) / résistance (short) franchi,
    stop à l'entrée dès que le trade avance, et « reste cool » quand le marché respire."""
    pos = tr["qui"][c]; d = tr["d"]; a = r["atr"]; p = r["m1"][-1]["c"]
    e = pos["e"]; sl = pos.get("sl_conseil", pos["sl"]); risque = max(abs(e - pos["sl"]), 1e-9)
    # Stop conseillé touché : on clôture le résultat de l'abonné à ce niveau
    if pos.get("sl_conseil") is not None:
        extreme = min(x["l"] for x in r["m1"][-6:]) if d == 1 else max(x["h"] for x in r["m1"][-6:])
        if d * (extreme - sl) <= 0:
            noter(etat, c, m, pos, sl, "🔒 Stop protégé touché" if d * (sl - e) >= 0 else "🛡 Stop remonté touché")
            return
    gain = d * (p - e)
    if gain <= 0:
        return
    # Niveaux franchis entre l'entrée et le prix : le stop se cache juste derrière le plus proche du prix
    murs = [v for v, n in r["niveaux"] if n in ("15m", "1h", "4h") and d * (p - v) > 0.6 * a and d * (v - (e - d * 0.6 * a)) > 0]
    nouveau, pourquoi = None, ""
    if murs:
        v = max(murs) if d == 1 else min(murs)
        n = next(n for vv, n in r["niveaux"] if vv == v)
        nouveau, pourquoi = v - d * 0.3 * a, "mèche"
    if gain >= 0.8 * risque and (nouveau is None or d * (nouveau - e) < 0) and not any(abs(v - e) < 0.6 * a for v in murs):
        nouveau, pourquoi = e + d * 0.05 * a, "be"
    if nouveau is not None and d * (nouveau - sl) > 0.3 * a and d * (p - nouveau) > 0.5 * a:
        pos["sl_conseil"] = nouveau
        if pourquoi == "be" or abs(nouveau - e) < 0.2 * a:
            texte = (f"🔒 {ICONE.get(m, '')} {m}   {SENS[d]}\n"
                     "🔁 Mets ton SL à BE (ton prix d'entrée)\n"
                     "🛡 Comme ça, plus aucune perte possible\n"
                     "🎯 On laisse courir vers le TP")
        else:
            texte = (f"🔒 {ICONE.get(m, '')} {m}   {SENS[d]}\n"
                     "👀 Mets-toi en vue 15 minutes\n"
                     f"🕯 Repère la mèche du dernier {'creux' if d == 1 else 'sommet'}\n"
                     f"{'⬆️ Monte' if d == 1 else '⬇️ Descends'} ton SL un peu {'SOUS' if d == 1 else 'AU-DESSUS de'} cette mèche\n"
                     "🙅 Jamais pile sur la mèche : elle peut être retouchée\n"
                     + ("💰 Ton gain est protégé" if d * (nouveau - e) > 0 else "🛡 Ta perte possible est réduite")
                     + f"\n📍 Repère prix   ≈ {px(nouveau)}")
        _envoi_sur(c, reply_markup=CLAVIER, text=texte)
        return
    # Le marché respire : petit retour vers l'entrée, on ne bouge rien
    r5 = r["r5"][-1]
    excès = (r5 >= 70) if d == 1 else (r5 <= 30)
    tps = pos.setdefault("cool_t", 0)
    if excès and time.time() - tps >= 45 * 60:
        pos["cool_t"] = time.time()
        _envoi_sur(c, reply_markup=CLAVIER, text=(
            f"😎 {ICONE.get(m, '')} {m} : reste cool\n🌬 Le marché respire\n"
            "🕯 Il peut revenir un peu, c'est normal\n"
            "🛑 Ne touche pas ton SL\n🎯 Cap sur le TP"))

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
        # Marché déjà parti (trop étiré) : on ne court pas après, on attend le repli ou le retournement
        p_ = r["m1"][-1]["c"]
        calme = ((r["r15"] < 62 and p_ - r["ema15"] < 1.5 * r["atr"]) if d == 1 else (r["r15"] > 38 and r["ema15"] - p_ < 1.5 * r["atr"]))
        if not cle.get("prep") and (etire(r, d) or (cle.get("parti") and not calme)):   # hystérésis : pas de va-et-vient
            if not cle.get("parti"):
                cle["parti"] = True; cle["attente_rsi"] = False; cle.pop("ordre", None)
                if time.time() - cle.get("parti_t", 0) > 7200:      # pas de répétition (2 h)
                    cle["parti_t"] = time.time()
                    out.append(f"🚀 {ICONE.get(m, '')} {m} est déjà parti {'⬆️' if d == 1 else '⬇️'}\n😎 On ne court pas après le prix\n{prochaine(r, cle)}")
            # Le prix commence à revenir (5 min dans l'autre sens) : on le dit, comme si on regardait le graphique ensemble
            recent = r["m1"][-30:]
            recul = (max(x["h"] for x in recent) - p_) if d == 1 else (p_ - min(x["l"] for x in recent))
            if (r["dirs"][2] == -d or (r["dirs"][0] == -d and recul >= 0.3 * r["atr"])) and not cle.get("retrace_vu") \
                    and r["t"] - cle.get("retrace_t", 0) >= 1800:        # 1 alerte « ça retrace » par 30 min maximum
                cle["retrace_vu"] = True; cle["retrace_t"] = r["t"]
                out.append(f"↩️ {ICONE.get(m, '')} {m} : ÇA RETRACE {'⬇️' if d == 1 else '⬆️'}\n😎 Le repli qu'on attend commence\n"
                           f"🔜 Prochaine entrée   {SENS[d]}\n🎯 Zone visée ≈ {px(r['ema15'])}\n👀 Vue 15 min, sois patient\n🔔 Je te préviens dès qu'on y est")
            elif r["dirs"][2] == d:
                cle["retrace_vu"] = False
            cle["aligne"] = d
            return out
        if cle.get("parti"):
            # Il n'est plus trop loin : le repli est là, l'entrée se prépare (1 fois / 2 h, et pas si le Daily bloque)
            cle["parti"] = False; cle["retrace_vu"] = False
            if not bloque and time.time() - cle.get("repli_t", 0) > 7200:
                cle["repli_t"] = time.time()
                out.append(    f"↩️ {ICONE.get(m, '')} {m} : LE REPLI EST LÀ {'⬇️' if d == 1 else '⬆️'}\n{SENS[d]} se prépare\n👀 Vue 15 min, tiens-toi prêt\n🔔 Prochaine alerte : ÇA ARRIVE")
        if cle.get("aligne") != d:
            cle["aligne"] = d; cle["prep"] = False
            if bloque:
                out.append(f"🧭 {m} aligné {'▲' if d == 1 else '▼'} sur 15m/1h/4h, MAIS prix {zone_txt(r['posD'])} Daily / {zone_txt(r['posW'])} Weekly.\n"
                           f"⛔ Pas de {'long' if d == 1 else 'short'} ici : risque de rebond. J'attends un meilleur prix.")
            else:
                cle["ordre"] = o
                out.append((f"🔔 JE PRÉPARE UNE POSITION — {m} {'monte' if d == 1 else 'descend'} sur 15m, 1h et 4h ✅✅✅\n"
                           f"⏳ Je n'entre pas encore : j'attends que le prix vienne dans la zone 🟨\n"
                           f"👀 Mets-toi en vue 15 minutes\n"
                           f"🕯 Repère {'le dernier creux (mèche du bas)' if d == 1 else 'le dernier sommet (mèche du haut)'}\n"
                           f"🟨 L'entrée sera à peu près {'au-dessus de ce creux' if d == 1 else 'sous ce sommet'}\n"
                           f"🚦 Attends mon feu vert 🟢\n\n"
                           f"{fmt_trade(m, o, p)}\n\n"
                           f"📐 Zone = Fibonacci 50 → 78,6 % + {o['src'].split(' + ')[0]}{ferme}", bouton_auto(m)))
        if (bloque and not cle.get("ordre")) or o["rr"] < GAIN_MIN:
            return out
        # On ajuste le point tant que le prix n'est pas encore arrivé (les niveaux bougent)
        if not cle.get("prep"):
            cle["ordre"] = o
        o = cle.get("ordre", o)
        dist = d * (p - o["e"])       # < 0 = le prix n'est pas encore arrivé au point d'entrée
        touche = (lo <= o["e"]) if d == 1 else (hi >= o["e"])
        if not cle.get("prep") and abs(p - o["e"]) <= max(0.6 * r["atr"], abs(o["e"] - o["sl"]) * 0.5):
            cle["prep"] = True
            out.append((f"👀👀 ÇA ARRIVE — {ICONE.get(m, '')} {m}\n{SENS[d]}\n🟨 Le prix entre dans la zone\n⚡ Tiens-toi prêt\n🚦 Feu vert 🟢 très bientôt\n🔔 Cloche activée ? Ne rate pas le feu vert\n📍 Zone ≈ {px(o.get('za', o['e']))} – {px(o.get('zb', o['e']))}", bouton_auto(m)))
        # À quelques pips de l'entrée : « PRÉPARE-TOI » + rappel SL / TP (1 fois par point d'entrée)
        seuil = max(5 * PIP.get(m, 0.1), 0.05 * r["atr"])
        if cle.get("prep") and (abs(p - o["e"]) <= seuil or touche) and time.time() - cle.get("pret_t", 0) > 1800:
            cle["pret_t"] = time.time()
            out.append((f"⚡⚡ PRÉPARE-TOI — {ICONE.get(m, '')} {m}\n{SENS[d]}\n🎯 On est à quelques pips de l'entrée\n👀 Vue 15 minutes\n"
                        f"🛑 Dès que tu es dedans : SL un peu {'SOUS la mèche du dernier creux' if d == 1 else 'AU-DESSUS de la mèche du dernier sommet'}\n"
                        f"💰 TP1 juste {'sous la' if d == 1 else 'au-dessus du'} {o['n1']}\n🙅 Jamais de position sans SL\n🚦 Feu vert 🟢 dans un instant",
                        bouton_auto(m)))
        # Surcharge sur PLUSIEURS UT : 5m obligatoire + au moins 1 parmi 10m/15m/30m + confirmation 1h
        R = dict(zip(UT, r["rsis"]))
        if d == 1:
            r5ok = min(r["r5"]) <= 35
            petites = [u for u in ("10", "15", "30") if R[u] <= 40]
            conf1h = R["1h"] < 65 and r["dirs"][9] == d      # 1 h pas en excès, 4 h toujours dans le sens
        else:
            r5ok = max(r["r5"]) >= 65
            petites = [u for u in ("10", "15", "30") if R[u] >= 60]
            conf1h = R["1h"] > 35 and r["dirs"][9] == d
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
                          ("Pas de news proche", True), (f"Gain / risque x{o['rr']:.1f}", o["rr"] >= GAIN_MIN)]
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
            out.append(f"🎯 {m} : TP1 {px(t1)} touché !\n→ Sécurise une partie\n→ Mets ton SL à BE (prix d'entrée)\n→ On vise TP2 {px(t2)}")
            return out
        if progres < 0.25:
            if tr["encore"] < 1 and r["t"] - tr["cree"] >= 900:
                tr["encore"] += 1
                if True:
                    out.append((f"👍 {m} : tu peux encore rentrer ({px(p)}). Stop {px(sl)} • TP1 {px(t1)}\n\nTu es rentré ?", boutons(m)))
        elif not tr.get("tard"):
            tr["tard"] = True
            # Le bot reste en position jusqu'au TP ou au SL (son bilan compte toutes ses positions)
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
def un_tour(etat, chats):
    """Un tour complet : messages reçus, analyse BTC + Gold, envois, jauges, sauvegarde."""
    LANG_EN.clear(); LANG_EN.update(etat.get("en", []))
    if TOKEN:
        installer_menu(etat)
    demandes = []
    if TOKEN:
        demandes = traiter(etat, chats, telegram("getUpdates", offset=etat.get("offset", 0), timeout=0).get("result", []))
        if etat.get("clavier") != 8:
            for cid in chats:
                _envoi_sur(cid, text="🆕 Nouveaux boutons\n🟠 Analyse BTC\n🥇 Analyse Gold\n🚦 Chaque analyse te dit si tu peux entrer ou pas\n🌐 English : le bot en anglais\n📸 Partager mon gain : ta capture publiée\n🤖 Mon bot : il entre tout seul pour toi (ON / OFF)", reply_markup=CLAVIER)
            for cid in etat.get("prospects", []):
                _envoi_sur(cid, text="🆕 Boutons : 🟠 Analyse BTC • 🥇 Analyse Gold • 💎 Devenir VIP", reply_markup=CLAVIER_VISITEUR)
            etat["clavier"] = 8
        if not etat.get("bot"):
            try:
                etat["bot"] = telegram("getMe")["result"]["username"]
            except Exception as ex:
                print("getMe", ex)
        # Chaîne VIP : lien d'abonnement absent OU ancien prix → nouveau lien au bon prix (1 essai par heure max)
        if etat.get("canal") and (not etat.get("lien") or etat.get("prix_lien", 500) != PRIX_STARS) \
                and time.time() - etat.get("essai_lien", 0) > 3600:
            etat["essai_lien"] = time.time()
            try:
                etat["lien"] = telegram("createChatSubscriptionInviteLink", chat_id=etat["canal"], name="Abonnement VIP",
                                        subscription_period=2592000, subscription_price=PRIX_STARS)["result"]["invite_link"]
                etat["prix_lien"] = PRIX_STARS
                for p in proprio(etat):
                    telegram("sendMessage", chat_id=p, text=f"💳 Lien d'abonnement VIP créé ({PRIX_STARS} ⭐ / mois ≈ 49,90 €) :\n{etat['lien']}\n\n👉 C'est ce lien que tu partages pour vendre l'accès.")
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
                    if cid not in etat.setdefault("prospects", []):
                        etat["prospects"].append(cid)
                    _envoi_sur(cid, reply_markup=CLAVIER_VISITEUR, text=(
                        "🔒 Les positions en direct sont réservées aux VIP\n"
                        + ("🎁 Ta position de bienvenue reste offerte\n" if cid not in etat.get("bienvenue", {}) else "")
                        + "💎 VIP 49,90 € / mois : toutes les positions + le coach"
                        + (f"\n👉 {etat['lien']}" if etat.get("lien") else "")))

    envois, derniers = [], {}
    calendrier(etat, int(time.time()))
    for nom_marche, pair in MARCHES.items():
        try:
            r = analyser(pair)
        except Exception as ex:
            print(nom_marche, "erreur", ex); continue
        cle = etat.setdefault(nom_marche, {})
        tendance_armee(r, cle)
        r["annonce"] = annonce_proche(etat, int(time.time()))
        r["news"] = news_txt(etat)
        ferme = "" if nom_marche == "BTC" or cme_ouvert(r["t"]) else "\n⚠️ Futures CME fermés en ce moment (Topstep) : signal à titre indicatif."
        envois += agent(nom_marche, r, cle, ferme)
        if TOKEN and cle.get("trade") and not cle["trade"].get("auto_fait"):
            cle["trade"]["auto_fait"] = True
            entrer_inscrits(etat, nom_marche, cle["trade"], chats)
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
                cle["dernier"] = round(gain, 2)
        derniers[nom_marche] = r
        for cle_p, oui, txt in (("distrib_vu", r.get("distrib"),
                                 f"⚠️ {ICONE.get(nom_marche, '')} {nom_marche} : DISTRIBUTION possible\n🕯 Le haut s'essouffle (divergence RSI {'4h' if r['div4h'][0] else '1h'})\n"
                                 f"📍 Prix {zone_txt(r['posD'])} Daily\n🙅 Prudence sur les 🟩 LONG\n👀 Un 🟥 SHORT ⬇️ peut se préparer"),
                                ("accum_vu", r.get("accum"),
                                 f"⚠️ {ICONE.get(nom_marche, '')} {nom_marche} : ACCUMULATION possible\n🕯 Le bas se charge (divergence RSI {'4h' if r['div4h'][1] else '1h'})\n"
                                 f"📍 Prix {zone_txt(r['posD'])} Daily\n🙅 Prudence sur les 🟥 SHORT\n👀 Un 🟩 LONG ⬆️ peut se préparer")):
            if oui and not cle.get(cle_p):
                envois.append(txt)
            cle[cle_p] = bool(oui)
        cle["vu"] = r["t"]
        for cid, mq in demandes:
            if mq in (None, nom_marche):
                _envoi_sur(cid, text=texte_etat(nom_marche, r, cle), reply_markup=markup_analyse(etat, nom_marche, r))
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
                        # Chaîne VIP : pas de clavier possible dans une chaîne → boutons sous le message (ils ouvrent le bot)
                        txt = texte.replace("\n\nTu es rentré ?", "")
                        telegram("sendMessage", chat_id=cid, text=txt, reply_markup=boutons_canal(etat, texte))
                    elif clavier:
                        telegram("sendMessage", chat_id=cid, text=texte, reply_markup=clavier)
                    else:
                        telegram("sendMessage", chat_id=cid, text=texte)
                except Exception as ex:
                    print("envoi", cid, ex)
                    if "403" in str(ex) and cid not in proprio(etat):
                        chats.discard(cid)   # l'abonné a bloqué le bot
            # Visiteurs non abonnés : teaser (positions masquées + bouton de paiement)
            envoyer_prospects(etat, texte, bool(re.search(r"(?<!\w)\d{1,3}(?: \d{3})*\.\d+", texte)) and any(k in texte for k in ("JE PRÉPARE", "J'ENTRE MAINTENANT")), clavier)
        for nom_marche in MARCHES:
            if nom_marche in derniers:
                maj_jauge(nom_marche, derniers[nom_marche], etat[nom_marche], chats, etat.get("canal"))
    print(f"{len(envois)} signal(s) envoyé(s) à {len(chats)} téléphone(s)")
    json.dump(dict(etat, chats=sorted(chats)), open(ETAT_FICHIER, "w"))

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

    # Bot toujours allumé : un tour toutes les PAUSE_SEC secondes pendant DUREE_SEC,
    # et entre deux tours il écoute Telegram en continu (réponse immédiate aux boutons).
    debut = time.time()
    while True:
        try:
            un_tour(etat, chats)
        except Exception as ex:
            print("tour", ex)
        prochain = time.time() + PAUSE_SEC
        while TOKEN and time.time() < min(prochain, debut + DUREE_SEC):
            reste = int(min(prochain, debut + DUREE_SEC) - time.time())
            try:
                maj = telegram("getUpdates", offset=etat.get("offset", 0), timeout=max(1, min(50, reste))).get("result", [])
            except Exception as ex:
                print("ecoute", ex); time.sleep(5); continue
            for cid, mq in traiter(etat, chats, maj):
                envoyer_analyse(cid, etat, mq)
            etat["chats"] = sorted(chats)
            json.dump(etat, open(ETAT_FICHIER, "w"))
        if time.time() >= debut + DUREE_SEC:
            break
        if not TOKEN:
            time.sleep(max(0, prochain - time.time()))
    etat["chats"] = sorted(chats)
    json.dump(etat, open(ETAT_FICHIER, "w"))

if __name__ == "__main__":
    main()
