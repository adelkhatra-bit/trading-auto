#!/usr/bin/env python3
"""ALIGN MTF BOT — même logique que l'indicateur TradingView ALIGN MTF PRO.
Prix gratuits : BTC = Kraken XBTUSD, Gold = XAUUSD spot (bougies COMEX Yahoo recalées sur le prix spot Swissquote).
Tourne toutes les 5 minutes (GitHub Actions). Aucune dépendance externe."""
import json, os, re, time, hashlib, urllib.request, urllib.error, urllib.parse, datetime, threading
from zoneinfo import ZoneInfo
import sys
try:
    sys.stdout.reconfigure(line_buffering=True)   # les logs GitHub s’affichent tout de suite
except Exception:
    pass
PARIS = ZoneInfo("Europe/Paris")

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
ETAT_FICHIER = os.environ.get("STATE_FILE", "state.json")
MARCHES = {"BTC": "XBTUSD", "GOLD": "XAUUSD"}  # BTC → FTMO (CFD 24/7) • GOLD → Topstep (MGC) / FTMO
MIN_ALIGN, MIN_SQZ, MARGE_ATR, GAIN_MIN = 8, 4, 0.5, 2.0
LIEN_RESULTATS = "https://t.me/+RajFd_hMgl1kNmQ0"     # groupe ALIGN Résultats (lien privé)
RISQUE_MAX = 1.5      # SL jamais plus loin que 1,5 ATR 15 min : pas de gros SL, on attend mieux
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
        except urllib.error.HTTPError as ex:
            # Lire le corps JSON : Telegram y donne la cause exacte (message non modifié,
            # message supprimé, droits insuffisants, etc.). Sans cela urllib ne remonte que
            # « HTTP Error 400: Bad Request » et le réparateur de chronomètre ne peut agir.
            try:
                corps = ex.read().decode("utf-8", errors="replace")
            except Exception:
                corps = ""
            try:
                payload = json.loads(corps) if corps else {}
                description = payload.get("description") or corps or str(ex)
            except Exception:
                description = corps or str(ex)
            raise RuntimeError(f"HTTP Error {ex.code}: {description}") from ex
        except Exception:
            if essai == 2:
                raise
            time.sleep(2 * (essai + 1))

ALIGN_TV_API_URL = os.environ.get("ALIGN_TV_API_URL", "").strip().rstrip("/")
ALIGN_TV_READ_TOKEN = os.environ.get("ALIGN_TV_READ_TOKEN", "").strip()

def fetch_tv_mtf(pair):
    """Lit les snapshots Pine/ROBOT V12 conservés par symbole et timeframe ; jamais de données inventées."""
    if not ALIGN_TV_API_URL or not ALIGN_TV_READ_TOKEN:
        return {"available": False, "reason": "bridge TradingView non configuré", "snapshots": {}}
    symbol = "BTCUSD" if pair == "XBTUSD" else pair.upper()
    url = ALIGN_TV_API_URL + "/bridge/robot-v12/mtf?symbol=" + urllib.parse.quote(symbol)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + ALIGN_TV_READ_TOKEN, "User-Agent": "ALIGN-MTF-BOT"})
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("ok") or not isinstance(payload.get("snapshots"), dict):
            return {"available": False, "reason": "réponse bridge invalide", "snapshots": {}}
        active_tf = str(payload.get("activeTimeframe") or "").upper()
        active_fresh = payload.get("activeTimeframeFresh") is True
        if active_tf not in {"M1", "M5", "M15", "M30", "H1", "H2", "H4", "D1", "W1"} or not active_fresh:
            active_tf = None
        return {
            "available": True,
            "reason": None,
            "symbol": payload.get("symbol"),
            "activeTimeframe": active_tf,
            "activeTimeframeAgeMs": payload.get("activeTimeframeAgeMs"),
            "snapshots": payload["snapshots"],
            "receivedTimeframes": payload.get("receivedTimeframes", [])
        }
    except Exception as ex:
        print("TradingView MTF bridge:", ex, flush=True)
        return {"available": False, "reason": "bridge inaccessible", "snapshots": {}}

def _direction_tv(value):
    text = str(value or "").strip().upper()
    if any(x in text for x in ("LONG", "BULL", "HAUSSIER", "ACHAT", "BUY")):
        return 1
    if any(x in text for x in ("SHORT", "BEAR", "BAISSIER", "VENTE", "SELL")):
        return -1
    if any(x in text for x in ("NEUTRE", "NEUTRAL", "ATTENTE", "WAIT")):
        return 0
    return None


def fusionne_lectures_tradingview(r):
    """Fusionne uniquement les lectures MTF explicitement envoyées par ROBOT V12."""
    bridge = r.get("tv_indicator_mtf") or {}
    snap = (bridge.get("snapshots") or {}).get(bridge.get("activeTimeframe")) or {}
    robot = snap.get("robotV12") or {}
    if not robot or not snap.get("fresh"):
        return r
    for field, index in (("lecture_1m", 0), ("lecture_5m", 2), ("lecture_15m", 4), ("lecture_60m", 7)):
        direction = _direction_tv(robot.get(field))
        if direction is not None:
            r["dirs"][index] = direction
    for field, index in (("rsi_1m", 0), ("rsi_5m", 2), ("rsi_15m", 4), ("rsi_60m", 7)):
        try:
            value = float(robot.get(field))
            if 0 <= value <= 100:
                r["rsis"][index] = value
        except (TypeError, ValueError):
            pass
    # Recompute the existing ALIGN bias/profile from the merged real MTF readings.
    d1h, d4h = r["dirs"][7], r["dirs"][9]
    r["confirme"] = d4h if d4h and d1h == d4h else 0
    r["tv_robot_v12"] = robot
    return r


def plan_indicateur(r):
    """Utilise le plan du timeframe réellement actif sur TradingView, jamais une UT supposée."""
    bridge = r.get("tv_indicator_mtf") or {}
    preferred = str(bridge.get("activeTimeframe") or "").upper()
    snap = (bridge.get("snapshots") or {}).get(preferred) or {}
    robot = snap.get("robotV12") or {}
    try:
        entry, sl, tp = float(robot.get("entry")), float(robot.get("sl")), float(robot.get("tp"))
    except (TypeError, ValueError):
        return {"timeframe": preferred or None, "available": False,
                "reason": "aucun plan ROBOT V12 complet pour l'unité TradingView active"}
    if not snap.get("fresh"):
        return {"timeframe": preferred, "available": False, "reason": "plan ROBOT V12 périmé"}
    signal = str(robot.get("signal") or robot.get("verdict") or "").upper()
    direction = _direction_tv(signal)
    if direction not in (-1, 1) or min(entry, sl, tp) <= 0:
        return {"timeframe": preferred, "available": False, "reason": "direction ou niveaux ROBOT V12 invalides"}
    if (direction == 1 and not sl < entry < tp) or (direction == -1 and not tp < entry < sl):
        return {"timeframe": preferred, "available": False, "reason": "géométrie entrée/SL/TP incohérente"}
    return {"timeframe": preferred, "available": True, "direction": direction, "entry": entry, "sl": sl, "tp": tp,
            "confirmed": snap.get("confirmed") is True, "verdict": robot.get("verdict"),
            "macro_bull": robot.get("macro_bull"), "macro_bear": robot.get("macro_bear"),
            "long_score": robot.get("long_score"), "short_score": robot.get("short_score"),
            "anticipation": robot.get("anticipation"), "anticipation_force": robot.get("anticipation_force"),
            "zone_proche": robot.get("zone_proche"), "liq_haute_active": robot.get("liq_haute_active"),
            "liq_basse_active": robot.get("liq_basse_active"),
            "timestamp": robot.get("receivedAt") or snap.get("timestamp"), "ageMs": snap.get("ageMs")}


TTL_KRAKEN = {1: 5, 5: 10, 15: 30, 30: 60, 60: 120, 240: 300, 1440: 900, 10080: 1800}

def kraken(pair, interval):
    c = _CACHE_K.get((pair, interval))
    if c and time.time() - c[0] < TTL_KRAKEN.get(interval, 60):
        return c[1]
    for essai in range(2):                     # Kraken a parfois un petit raté : on réessaie une fois
        try:
            rows = _kraken(pair, interval)
            _CACHE_K[(pair, interval)] = (time.time(), rows)
            return rows
        except Exception as ex:
            err = ex
            time.sleep(1)
    if c and time.time() - c[0] < 600:          # sinon les dernières bougies connues (moins de 10 min)
        return c[1]
    raise err

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
    if c and time.time() - c[0] < 5:
        return c[1]
    j = http_json("https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD")
    q = j[0]["spreadProfilePrices"][0]
    v = (q["bid"] + q["ask"]) / 2
    _CACHE["spot"] = (time.time(), v)
    h = _CACHE.setdefault("spot_hist", []); h.append((time.time(), v)); del h[:-300]
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
        t = int(time.time()) // 60 * 60
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
        t = int(time.time()) // 60 * 60
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

def regrouper(bars, n, base_sec, now_ts=None):
    """Construit uniquement des bougies agrégées complètes, continues et déjà clôturées.

    Les bougies sources sont horodatées à leur ouverture. Une bougie manquante,
    dupliquée, désalignée ou encore en formation invalide son groupe : on ne
    fabrique jamais une clôture à partir de données partielles.
    """
    if n < 1 or base_sec < 1:
        raise ValueError("n et base_sec doivent être positifs")
    now_ts = time.time() if now_ts is None else float(now_ts)
    buckets = {}
    for b in sorted(bars, key=lambda x: x["t"]):
        ts = int(b["t"])
        if ts % base_sec:
            continue
        debut = ts - (ts % (n * base_sec))
        fin = debut + n * base_sec
        if fin > now_ts:
            continue
        buckets.setdefault(debut, []).append(b)

    out = []
    for debut, groupe in sorted(buckets.items()):
        attendu = [debut + i * base_sec for i in range(n)]
        horodatages = [int(x["t"]) for x in groupe]
        if horodatages != attendu:
            continue
        out.append({
            "t": debut,
            "o": groupe[0]["o"],
            "h": max(x["h"] for x in groupe),
            "l": min(x["l"] for x in groupe),
            "c": groupe[-1]["c"],
        })
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

def fvgs(bars, ut, n=40):
    """FVG (Fair Value Gap) : trou entre la mèche de la bougie 1 et la bougie 3, pas encore comblé.
    Le prix revient souvent dedans et peut y rebondir."""
    z = bars[-n:]; out = []
    for i in range(2, len(z)):
        a_, c_ = z[i - 2], z[i]
        if c_["l"] > a_["h"]:
            lo, hi, dd = a_["h"], c_["l"], 1
        elif c_["h"] < a_["l"]:
            lo, hi, dd = c_["h"], a_["l"], -1
        else:
            continue
        apres = z[i + 1:]
        if (dd == 1 and any(x["l"] <= lo for x in apres)) or (dd == -1 and any(x["h"] >= hi for x in apres)):
            continue                                   # déjà comblé
        out.append((lo, hi, ut, dd))
    return out[-3:]

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
    # ═══ STRATÉGIE : 4h = tendance principale, 1h = confirmation ═══
    d1h, d4h = dirs[7], dirs[9]
    # Le 15m reste informatif et ne bloque jamais un signal.
    confirme = d4h if d4h != 0 and d1h == d4h else 0
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
    try:
        fvg = fvgs(m15, "15m") + fvgs(h1, "1h")
    except Exception:
        fvg = []
    # Niveaux clés que tous les pros regardent : plus haut / plus bas d'hier et de la semaine dernière
    niv_cles = []
    try:
        niv_cles = [(d1[-1]["h"], "plus haut d'hier"), (d1[-1]["l"], "plus bas d'hier"),
                    (w1[-1]["h"], "plus haut de la semaine dernière"), (w1[-1]["l"], "plus bas de la semaine dernière")]
    except Exception:
        pass
    # Range de la session Asie (00:00 → 08:00 heure de Paris, aujourd'hui)
    asie = None
    try:
        auj = datetime.datetime.now(PARIS).replace(hour=0, minute=0, second=0, microsecond=0)
        a0, a1 = auj.timestamp(), auj.timestamp() + 8 * 3600
        za = [x for x in m15 if a0 <= x["t"] < a1]
        if len(za) >= 16:
            asie = (max(x["h"] for x in za), min(x["l"] for x in za))
    except Exception:
        pass
    atr5 = atr(m5, 14)[-1] if len(m5) >= 15 else a
    return dict(fvg=fvg, niv_cles=niv_cles, asie=asie, distrib=distrib, accum=accum, div4h=div4h,
                b5=m5[-30:], b15=m15[-30:], b1h=h1[-30:], b4h=h4[-30:], bd=d1[-30:], bw=w1[-30:],
                atr5=atr5, ema5=ema([x["c"] for x in m5], 20)[-1], m1=m1, confirme=confirme, atr=a, r5=r5[-3:], r15=rC, posD=posD, posW=posW, hautD=hautD, basD=basD, hautW=hautW, basW=basW,
                grosses=grosses, ema15=ema(c, 20)[-1], niveaux=[(v, n) for v, n in zip(niv, noms) if v is not None], t=b[-1]["t"], prix=cl, dirs=dirs, sqzs=sqzs, rsis=rsis, bull=bull, bear=bear, comp=comp, rsiOB=rsiOB, rsiOS=rsiOS,
                pctH=pctH, sens=sens, retHaut=retHaut, retBas=retBas, sigHaut=sigHaut, sigBas=sigBas, nom=nom,
                dirPlan=dirPlan, plan=plan(dirPlan if dirPlan else 1), planH=plan(1), planB=plan(-1), rC=rC)

# ───────── Messages ─────────
def _compacte_prix(valeur):
    """Un prix ne contient jamais de séparateur de milliers ; les décimales nulles sont omises."""
    valeur = re.sub(r"[ \u00a0\u202f]", "", str(valeur))
    if re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?%?", valeur):
        valeur = valeur.replace(".", ",")
        valeur = re.sub(r",0+$", "", valeur)
    return valeur

def px(v):
    # Format français compact : 4075,50 ; 4000 ; aucun séparateur de milliers.
    return _compacte_prix(f"{v:.2f}")

def _normalise_prix_dans_texte(texte):
    """Retire les séparateurs de milliers des prix, même sur une ligne déjà formatée."""
    motif = r"(?<![\w])([+-]?\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?%?)(?!\w)"
    return re.sub(motif, lambda m: _compacte_prix(m.group(1)), texte)

def cme_ouvert(ts):
    """Session CME en heure locale Chicago avec bascule DST automatique."""
    ct = datetime.datetime.fromtimestamp(ts, ZoneInfo("America/Chicago"))
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

# Tampon des messages sortants : transféré dans state.json à chaque sauvegarde.
JOURNAL_SORTANT = []
JOURNAL_MAX = 10000
JOURNAL_PAR_CHAT = 500


def journal_ajouter(etat, entree):
    journal = etat.setdefault("journal_telegram", [])
    if entree.get("direction") == "sortant" and entree.get("type") == "editMessageText":
        for precedent in reversed(journal):
            if (precedent.get("direction") == "sortant"
                    and str(precedent.get("chat_id")) == str(entree.get("chat_id"))
                    and str(precedent.get("message_id")) == str(entree.get("message_id"))):
                precedent.update(entree)
                return
    if entree.get("update_id") is not None and any(
        (x.get("direction"), x.get("update_id")) == (entree.get("direction"), entree.get("update_id"))
        for x in journal[-20:]
    ):
        return
    journal.append(entree)
    cid = str(entree.get("chat_id", ""))
    memes_chat = [i for i, x in enumerate(journal) if str(x.get("chat_id", "")) == cid]
    if len(memes_chat) > JOURNAL_PAR_CHAT:
        a_supprimer = set(memes_chat[:-JOURNAL_PAR_CHAT])
        journal[:] = [x for i, x in enumerate(journal) if i not in a_supprimer]
    del journal[:-JOURNAL_MAX]


def journal_vider_sortants(etat):
    while JOURNAL_SORTANT:
        entree = JOURNAL_SORTANT.pop(0)
        journal_ajouter(etat, entree)


def texte_historique(etat, cid, limite=8, offset=0):
    entrees = [x for x in etat.get("journal_telegram", []) if str(x.get("chat_id")) == str(cid)]
    total = len(entrees)
    fin = max(0, total - max(0, offset))
    debut = max(0, fin - limite)
    page = entrees[debut:fin]
    lignes = ["🗂 HISTORIQUE ALIGN — TES ÉCHANGES",
              "━━━━━━━━━━━━━━━━━━━━",
              f"Messages {debut + 1 if page else 0} à {fin} sur {total} conservé(s)."]
    if not page:
        lignes.append("Aucun message dans cette page. Utilise « Plus récents » pour revenir.")
    for x in page:
        ts = x.get("timestamp")
        try:
            date = datetime.datetime.fromtimestamp(float(ts), PARIS).strftime("%d/%m %H:%M:%S")
        except Exception:
            date = "Date inconnue"
        sens = "📤 ALIGN" if x.get("direction") == "sortant" else "📥 TOI"
        lignes.append(f"\n{date} • {sens}\n{str(x.get('text') or x.get('type') or 'Message')[:400]}")
    lignes += ["━━━━━━━━━━━━━━━━━━━━",
               f"ℹ️ Conservation : {JOURNAL_PAR_CHAT} échanges maximum par conversation, dans une limite globale de {JOURNAL_MAX}.",
               "Les messages antérieurs à l'activation ne sont pas récupérables par le Bot API Telegram."]
    return "\n".join(lignes)

def alignement(r):
    """Biais de fond : H4 donne le sens, H1 le confirme. M15/M5 sont évalués séparément."""
    d1h, d4h = r["dirs"][7], r["dirs"][9]
    maj = d4h if d4h != 0 and d1h == d4h else 0
    return maj, (2 if maj else 0)


def profil_strategie(r):
    """Classe le setup sans confondre alignement directionnel et autorisation d’entrée."""
    D = r["dirs"]
    d5, d15, d1h, d4h = D[2], D[4], D[7], D[9]
    if d4h and d1h == d4h and d15 == -d4h and d5 == d15:
        direction = d15
        mode, horizon = "SCALPING CONTRE-TENDANCE", "court terme ; ne pas transformer en position swing"
        contexte, contre = "M15 et M5 sont alignés contre le biais H4/H1", True
    elif d4h and d1h == d4h:
        direction = d4h
        if d15 == direction:
            mode, horizon = "SWING", "plusieurs séances si la structure H4 reste valide"
            contexte = "H4, H1 et M15 sont alignés"
        elif d15 == -direction:
            mode, horizon = "INTRADAY", "séance en cours ; pas de conservation automatique la nuit"
            contexte = "M15 est en retracement contre le biais H4/H1"
        else:
            mode, horizon = "INTRADAY", "séance en cours ; réévaluer à chaque clôture"
            contexte = "M15 est neutre : attendre une structure exploitable"
        contre = False
    elif d1h and d15 == d1h and d4h in (0, d1h):
        direction = d1h
        mode, horizon = "INTRADAY", "mouvement de séance ; sortie avant invalidation"
        contexte = "H1 et M15 sont alignés"
        contre = False
    elif d15 and d5 == d15:
        direction = d15
        contre = bool(d1h == -direction or d4h == -direction)
        mode = "SCALPING CONTRE-TENDANCE" if contre else "SCALPING"
        horizon = "court terme ; ne pas transformer en position swing"
        contexte = "M15 et M5 sont alignés" + (" mais H1/H4 s’opposent" if contre else "")
    else:
        direction, mode, horizon = 0, "ATTENTE", "aucune durée de position à annoncer"
        contexte, contre = "pas de confluence exploitable entre les unités", False
    m5_aligne = bool(direction and d5 == direction)
    return {"mode": mode, "direction": direction, "horizon": horizon, "contexte": contexte,
            "m5_aligne": m5_aligne, "contre_tendance": contre,
            "statut": "CONFLUENCE M5 — attendre le déclencheur clôturé" if m5_aligne
                      else "PRÉPARATION — attendre l’alignement ou le retournement M5"}


def texte_etat(nom_marche, r, cle=None, vip=True):
    """Carte Telegram complète : mise en page uniquement, aucune rubrique d'analyse supprimée."""
    # Codes visuels constants : vert = hausse, rouge = baisse, orange = neutre.
    fl = lambda d: "🟢⬆️" if d == 1 else "🔴⬇️" if d == -1 else "🟠➖"
    prix = r["m1"][-1]["c"]
    entete = f"{ICONE.get(nom_marche, '📊')}  ALIGN • {nom_marche}\n💹 Prix actuel : {px(prix)}"
    if not vip:
        etat_pos = ("🟢 Une position VIP est actuellement ouverte" if (cle or {}).get("trade") else
                    "🟡 Une opportunité VIP se prépare" if (cle or {}).get("ordre") and r["confirme"] else
                    "⚪ Aucune position VIP pour le moment")
        return "\n".join([entete, "━━━━━━━━━━━━━━━━━━", "📡 POINT DE MARCHÉ",
                            etat_pos, r.get("news") or "📰 Calendrier économique indisponible",
                            "━━━━━━━━━━━━━━━━━━", "🔒 Direction et niveaux de trading réservés aux VIP",
                            "💎 Accès VIP : 49,90 € / mois"])
    tv_plan = plan_indicateur(r)
    D, R = r["dirs"], r["rsis"]
    maj, n_ok = alignement(r)
    ut = [("1m", 0), ("5m", 2), ("15m", 4), ("1h", 7), ("4h", 9), ("Daily", 10)]
    biais = ("🟢 Biais haussier confirmé" if maj == 1 else
             "🔴 Biais baissier confirmé" if maj == -1 else
             "🟠 Pas de biais confirmé en 1h / 4h")
    l = [entete, "━━━━━━━━━━━━━━━━━━", "📡 LECTURE DU MARCHÉ",
         "BIAIS GÉNÉRAL", biais,
         "━━━━━━━━━━━━━━━━━━", "📊 INDICATEURS PAR UNITÉ DE TEMPS",
         "  /  ".join(f"{nom} {fl(D[i])}" for nom, i in ut),
         "━━━━━━━━━━━━━━━━━━", "📈 RSI PAR UNITÉ DE TEMPS",
         "  /  ".join(f"{nom} {R[i]:.0f}" for nom, i in ut)]
    if tv_plan["available"]:
        l += ["━━━━━━━━━━━━━━━━━━", "📡 PLAN DE L'INDICATEUR TRADINGVIEW",
              f"Unité sélectionnée : {tv_plan['timeframe']}",
              f"Entrée indicateur : {px(tv_plan['entry'])} • SL : {px(tv_plan['sl'])} • TP : {px(tv_plan['tp'])}",
              "Clôture confirmée par l'indicateur : " + ("OUI" if tv_plan["confirmed"] else "NON / NON FOURNIE"),
              "⚠️ Plan indicateur séparé du verdict de sécurité ALIGN."]
    elif r.get("tv_indicator_mtf", {}).get("available"):
        l += ["━━━━━━━━━━━━━━━━━━", "📡 PLAN TRADINGVIEW",
              f"{tv_plan['timeframe']} : {tv_plan['reason']}"]
    l += ["━━━━━━━━━━━━━━━━━━", "🧭 CONFIRMATION DE TENDANCE",
          "ALIGNEMENT 1H + 4H", f"{n_ok}/2 {'✅ CONFIRMÉ' if r['confirme'] else '⏳ EN ATTENTE'}",
          "ZONE DAILY", zone_txt(r['posD']),
          "ZONE WEEKLY", zone_txt(r['posW']),
          "━━━━━━━━━━━━━━━━━━", "🧭 PLAN MULTI-TIMEFRAME"] + strategie_mtf(r)
    nc = dict((n, v) for v, n in (r.get("niv_cles") or []))
    ph_, pb_ = nc.get("plus haut d'hier"), nc.get("plus bas d'hier")
    contexte = []
    if ph_:
        contexte.append(f"📏 Plus haut d'hier : {px(ph_)}")
    if pb_:
        contexte.append(f"📏 Plus bas d'hier : {px(pb_)}")
    if r.get("asie"):
        contexte.append(f"🌏 Range Asie - plus haut : {px(r['asie'][0])}")
        contexte.append(f"🌏 Range Asie - plus bas : {px(r['asie'][1])}")
    contexte.extend(r.get("macro") or [])
    p_ = r["m1"][-1]["c"]
    proches = sorted([f for f in r.get("fvg", []) if abs((f[0] + f[1]) / 2 - p_) <= 3 * r["atr"]],
                     key=lambda f: abs((f[0] + f[1]) / 2 - p_))
    for lo, hi, ut_fvg, dd in proches[:2]:
        contexte.append(f"🧲 FVG {ut_fvg} : {'haussière' if dd == 1 else 'baissière'} | Basse {px(lo)} | Haute {px(hi)}")
    if r.get("distrib"):
        contexte.append("⚠️ Distribution possible : essoufflement en zone haute (divergence RSI)")
    if r.get("accum"):
        contexte.append("⚠️ Accumulation possible : soutien en zone basse (divergence RSI)")
    if contexte:
        l += ["━━━━━━━━━━━━━━━━━━", "🌍 NIVEAUX & CONTEXTE"] + contexte
    o = (cle or {}).get("ordre")
    if r["confirme"] and o and not (cle or {}).get("trade"):
        l += ["━━━━━━━━━━━━━━━━━━", "🟨 ZONE DE PRÉPARATION",
              f"Limite basse : {px(o.get('za', o['e']))}",
              f"Limite haute : {px(o.get('zb', o['e']))}"]
    titre, raison = verdict(r, cle)
    l += ["┏━━━━━━━━ 🚦 DÉCISION ALIGN ━━━━━━━━┓", titre, raison,
          "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"]
    tr = (cle or {}).get("trade")
    if tr:
        sens = "🟩 LONG" if tr["d"] == 1 else "🟥 SHORT"
        l.append(f"🎯 POSITION EN COURS : {sens} | Entrée {px(tr['e'])} | SL {px(tr['sl'])} | TP1 {px(tr['tp1'])} | TP2 {px(tr['tp2'])}")
    elif o:
        sens = "🟩 LONG" if o.get("d", r["confirme"]) == 1 else "🟥 SHORT"
        l.append(f"🎯 POINT VISÉ : {sens} | Entrée ≈ {px(o['e'])} | TP1 {px(o['tp1'])} | SL {px(o['sl'])}")
    elif r["confirme"]:
        sens = "🟩 LONG" if r["confirme"] == 1 else "🟥 SHORT"
        l.append(f"🎯 DIRECTION À SURVEILLER : {sens} | Point d'entrée après validation du déclencheur")
    else:
        l.append("🎯 POINT VISÉ : aucun tant que le biais 1h / 4h n'est pas confirmé")
    if r["confirme"] and not tr and len(r["b5"]) >= 22:
        l.append(ligne_cassure(r, r["confirme"]))
    if "Prochaine entrée" not in raison and not tr:
        l.append(prochaine(r, cle))
    return "\n".join(l)
def strategie_mtf(r):
    """H4/H1 = fond, M15 = préparation, M5 = timing ; profil scalp/intraday/swing explicite."""
    fl = lambda x: "🟢⬆️" if x == 1 else "🔴⬇️" if x == -1 else "🟠➖"
    D = r["dirs"]; d5, d15, d1h, d4h, dD = D[2], D[4], D[7], D[9], D[10]
    profil = profil_strategie(r)
    l = ["🧭 STRATÉGIE MULTI-UT",
         f"🏔 Tendance principale 4 h : {fl(d4h)}",
         f"🔁 Confirmation 1 h : {fl(d1h)}",
         f"👀 Préparation 15 min : {fl(d15)}",
         f"🎯 Timing 5 min : {fl(d5)}",
         f"📅 Contexte Daily : {fl(dD)}",
         f"🧩 PROFIL RETENU : {profil['mode']}",
         f"🧭 Lecture : {profil['contexte']}",
         f"⏱ Horizon indicatif : {profil['horizon']}",
         f"🚦 {profil['statut']}"]
    if profil["contre_tendance"]:
        l.append("⚠️ Contre-tendance : objectif court, risque réduit selon les règles, aucune conservation swing.")
    if r.get("confirme") and r.get("repli"):
        l.append(f"✅ Biais H4/H1 validé   {SENS[r['confirme']]}\n⏳ Le 15 min retrace : attendre le retour du M5 dans le sens du biais")
    elif r.get("confirme"):
        l.append(f"✅ Biais de fond H4/H1 validé   {SENS[r['confirme']]}")
    elif profil["mode"].startswith("SCALPING"):
        l.append(f"🟡 Setup court terme détecté   {SENS[profil['direction']]}\n⛔ Ce setup n’est pas un swing et reste soumis au déclencheur clôturé.")
    elif not d4h:
        l.append("➖ Pas de tendance de fond en 4 h\n⏳ Les configurations M15/M5 restent surveillées pour un éventuel scalp.")
    elif d1h == -d4h:
        l.append("↩️ 1 h en opposition à la tendance de fond\n⏳ Pas de swing : surveiller uniquement une configuration courte M15/M5.")
    else:
        l.append(f"⏳ {SENS[d4h]} en préparation — confirmation H1 manquante")
    return l

def bloque_dw(r, d, prix=None):
    """Daily / Weekly : pas de short tout en bas, pas de long tout en haut.
    Avec « prix » : on juge le point d'entrée du repli (acheter plus bas n'est plus « tout en haut »)."""
    if prix is None:
        posD, posW = r["posD"], r["posW"]
    else:
        posD = (prix - r["basD"]) / max(r["hautD"] - r["basD"], 1e-9)
        posW = (prix - r["basW"]) / max(r["hautW"] - r["basW"], 1e-9)
    return (d == -1 and (posD <= 0.15 or (posW <= 0.15 and posD <= 0.35))) or \
           (d == 1 and (posD >= 0.85 or (posW >= 0.85 and posD >= 0.65)))

# ───────── Mémoire du bot : il apprend de ses TP et de ses SL ─────────
MEMOIRE = []          # copie de etat["memoire"] (sauvegardé entre les lancements)

def session_de(ts):
    h = datetime.datetime.fromtimestamp(ts, PARIS).hour
    return "Asie" if h < 8 else "Londres" if h < 14 else "New York" if h < 22 else "Asie"

def profil_trade(m, tr, r):
    return {"m": m, "type": "cassure" if tr.get("src") == "cassure 5 min" else "repli",
            "d": tr["d"], "session": session_de(time.time()), "haut": bool(r["posD"] >= 0.75 if tr["d"] == 1 else r["posD"] <= 0.25)}

def stats_profil(p, cles=("m", "type", "d", "session")):
    proches = [x for x in MEMOIRE if all(x["p"].get(k) == p.get(k) for k in cles)]
    return len(proches), sum(1 for x in proches if x["g"] > 0)

def avis_memoire(p):
    """Ce que le bot a appris sur ce type de position (rien tant qu'il n'a pas assez d'exemples)."""
    n, w = stats_profil(p)
    if n < 5:
        n, w = stats_profil(p, ("m", "type", "d"))
    if n < 5:
        return ""
    return f"🧠 Mémoire du bot : ce type de position a gagné {w}/{n} fois ({round(100 * w / n)} %)\n"

def memoire_refuse(p):
    """Le bot passe son tour si ce type de position perd trop souvent (au moins 8 exemples, moins de 35 % gagnants)."""
    n, w = stats_profil(p, ("m", "type", "d"))
    return n >= 8 and w / n < 0.35, n, w

def apprendre(etat, trf, gain):
    p = trf.get("profil")
    if not p:
        return
    mem = etat.setdefault("memoire", [])
    mem.append({"p": p, "g": round(gain, 3), "t": int(time.time())})
    del mem[:-300]
    MEMOIRE[:] = mem

def texte_memoire(etat):
    mem = etat.get("memoire", [])
    if len(mem) < 3:
        return "🧠 Le bot apprend : il note chaque TP et chaque SL"
    groupes = {}
    for x in mem:
        k = (x["p"]["m"], x["p"]["type"], x["p"]["session"])
        g = groupes.setdefault(k, [0, 0]); g[0] += 1; g[1] += x["g"] > 0
    l = ["🧠 Ce que le bot a appris :"]
    for (m, t, se), (n, w) in sorted(groupes.items(), key=lambda z: -z[1][0])[:4]:
        l.append(f"{'✅' if w / n >= 0.5 else '⚠️'} {m} {t} ({se})   {w}/{n} gagnés")
    return "\n".join(l)

def qualite(o):
    """Étiquette de la position : très belle (gros mouvement ou gain ≥ 3 x le risque), belle, ou rien."""
    try:
        gain = abs(o["tp1"] - o["e"]) / o["e"] * 100
        rr = o.get("rr") or abs(o["tp1"] - o["e"]) / max(abs(o["e"] - o["sl"]), 1e-9)
    except Exception:
        return ""
    if rr >= 3 or gain >= 1.0:
        return f"🔥🔥🔥 TRÈS BELLE POSITION   +{gain:.1f} % visés (x{rr:.1f})\n"
    if rr >= 2.5 or gain >= 0.6:
        return f"🔥 BELLE POSITION   +{gain:.1f} % visés (x{rr:.1f})\n"
    return ""

def alerte_repli(out, m, r, cle, d, p):
    """Le marché commence à revenir contre la tendance : on annonce le repli et jusqu'où il devrait aller (1 fois / 30 min)."""
    recent = r["m1"][-30:]
    extreme = max(x["h"] for x in recent) if d == 1 else min(x["l"] for x in recent)
    recul = d * (extreme - p)
    if (r["dirs"][2] == -d or (r["dirs"][0] == -d and recul >= 0.3 * r["atr"])) and not cle.get("retrace_vu") \
            and r["t"] - cle.get("retrace_t", 0) >= 1800:
        cle["retrace_vu"] = True; cle["retrace_t"] = r["t"]
        zv = point_entree(r, d, p)
        src = zv["src"].split(" + ")[0]
        out.append((f"↩️ {ICONE.get(m, '')} {m} : ÇA RETRACE {'⬇️' if d == 1 else '⬆️'}\n"
                    f"📉 Repli attendu : de ≈ {px(extreme)} vers ≈ {px(zv['za'])} – {px(zv['zb'])}\n" if d == 1 else
                    f"↩️ {ICONE.get(m, '')} {m} : ÇA RETRACE {'⬇️' if d == 1 else '⬆️'}\n"
                    f"📈 Rebond attendu : de ≈ {px(extreme)} vers ≈ {px(zv['za'])} – {px(zv['zb'])}\n")
                   + f"😎 Le repli qu'on attend commence\n🔜 Prochaine entrée   {SENS[d]} dans cette zone\n"
                   + f"🕯 La moitié du dernier grand mouvement (vue 15 min){', ' + src if 'Fibonacci' not in src else ''}\n"
                   + "👀 Sois patient\n🔔 Je te préviens dès qu'on y est")

def rejet(r, d, e, a):
    """Mèche de rejet + clôture : la dernière bougie 5 min (ou 15 min) terminée a piqué dans la zone
    puis CLÔTURÉ en repartant dans le sens (grande mèche du côté de la zone, clôture du bon côté)."""
    for b in r["b5"][-1:]:
        rng = max(b["h"] - b["l"], 1e-9)
        if d == 1:
            meche = min(b["o"], b["c"]) - b["l"]
            if b["l"] <= e + 0.2 * a and meche >= 0.4 * rng and b["c"] >= b["l"] + 0.6 * rng:
                return b
        else:
            meche = b["h"] - max(b["o"], b["c"])
            if b["h"] >= e - 0.2 * a and meche >= 0.4 * rng and b["c"] <= b["h"] - 0.6 * rng:
                return b
    return None

def objectifs(r, d, e, risque):
    """TP1 atteignable (au plus 3 x le risque) puis TP2 sur le grand niveau 4h / Daily. TP2 toujours PLUS LOIN que TP1."""
    a = r["atr"]
    cibles = sorted([z for z in r["grosses"] if z[1] in ("4h", "Daily") and d * (z[0] - e) >= risque * GAIN_MIN], key=lambda z: d * z[0])
    proj3 = (e + d * risque * 3, "projection 3 x le risque")
    if cibles and d * (cibles[0][0] - proj3[0]) > 0.5 * a:
        return proj3, cibles[0]                        # grand niveau loin : on sécurise d'abord à 3 x le risque
    t1 = cibles[0] if cibles else (e + d * risque * 2.5, "projection 2,5 x le risque")
    loin = [z for z in cibles if d * (z[0] - t1[0]) >= 2 * a]
    t2 = loin[0] if loin else (t1[0] + d * max(risque * 2, 2 * a), "projection : on laisse courir")
    return t1, t2

def niveau_cassure(r, d):
    """Plus haut/bas des 20 dernières bougies 5m clôturées."""
    b = r["b5"][-21:-1]
    if len(b) < 20:
        return None
    return max(x["h"] for x in b) if d == 1 else min(x["l"] for x in b)

def plan_cassure(r, d):
    """Entrée sur cassure après clôture d'une bougie 5m au-delà des 20 précédentes."""
    b = r["b5"]; a = r.get("atr5", r["atr"])
    if len(b) < 22:
        return None
    L = niveau_cassure(r, d)
    if L is None:
        return None
    c1, c0 = b[-1]["c"], b[-2]["c"]
    casse = (c1 > L + 0.05 * a and c0 <= L) if d == 1 else (c1 < L - 0.05 * a and c0 >= L)
    rsi5 = r["r5"][-1]
    trop = (rsi5 >= 78) if d == 1 else (rsi5 <= 22)
    if not casse or trop:
        return None
    e = r["m1"][-1]["c"]
    # SL derrière la STRUCTURE (plus bas / plus haut des 3 dernières bougies 15 min), pas juste derrière la bougie de cassure :
    # le retest de la cassure revient souvent chercher ces mèches. Au moins 1 bougie moyenne, jamais plus de 1,5.
    if d == 1:
        sl = min(min(x["l"] for x in b[-3:]), L - 0.5 * a) - 0.35 * a
        sl = min(sl, e - 1.0 * a); sl = max(sl, e - RISQUE_MAX * a)
    else:
        sl = max(max(x["h"] for x in b[-3:]), L + 0.5 * a) + 0.35 * a
        sl = max(sl, e + 1.0 * a); sl = min(sl, e + RISQUE_MAX * a)
    if abs(e - sl) < max(a, e * 0.0008):
        sl = e - d * max(a, e * 0.0008)
    risque = abs(e - sl)
    t1, t2 = objectifs(r, d, e, risque)
    nom = lambda z: (("résistance " if d == 1 else "support ") + z[1]) if z[1] in ("1h", "4h", "Daily") else z[1]
    return dict(d=d, e=e, sl=sl, tp1=t1[0], n1=nom(t1), tp2=t2[0], n2=nom(t2), rr=abs(t1[0] - e) / risque,
                src="cassure 5 min", za=e, zb=e, niveau=L, t15=b[-1]["t"], sl_h=bougie_protegee(b[-3:], d, sl), sl_ut="5 min")

def ligne_cassure(r, d):
    L = niveau_cassure(r, d)
    return (f"🅱️ Ou CASSURE : si une bougie 5 min CLÔTURE {'au-dessus' if d == 1 else 'en dessous'} de ≈ {px(L)}\n"
            f"   → {SENS[d]} après confirmation")

def zone_repli(r, d):
    """Point d'entrée du repli (même calcul que l'agent)."""
    return point_entree(r, d, r["m1"][-1]["c"])

def etire(r, d):
    """Évite de poursuivre un mouvement déjà étiré selon le timing 5m, jamais selon le 15m."""
    p = r["m1"][-1]["c"]; a = r.get("atr5", r["atr"]); e = r.get("ema5", r["ema15"])
    r5 = r["r5"][-1]
    return (r5 >= 80 or p - e > 2 * a) if d == 1 else (r5 <= 20 or e - p > 2 * a)

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
    fond = r["dirs"][9]
    if not maj and fond:
        return f"🔜 Prochaine entrée   {SENS[fond]}   (⛔ 1h non confirmée)"
    return f"🔜 Prochaine entrée   {SENS[maj]}   ({n_ok}/2 • ⛔ pas encore validée)" if maj else "🔜 Prochaine entrée   ➖ pas encore de sens"

def verdict(r, cle):
    """Réponse claire pour l'utilisateur : peut-il entrer maintenant ou non ?"""
    cle = cle or {}
    tr = cle.get("trade")
    if tr:
        p = r["m1"][-1]["c"]
        sens = "⬆️ ACHAT" if tr["d"] == 1 else "⬇️ VENTE"
        prog = tr["d"] * (p - tr["e"]) / max(abs(tr["tp1"] - tr["e"]), 1e-9)
        if tr["statut"] == "entree" and prog < 0.25 and not tr.get("tard"):
            return (f"🟢 TU PEUX ENTRER\n{SENS[tr['d']]}", f"👀 Vue 15 minutes\n🛑 SL un peu {meche_sl(tr)}\n🙅 Jamais pile sur la mèche\n📍 Repère prix : SL ≈ {px(tr['sl'])} • TP1 ≈ {px(tr['tp1'])}\n👉 Puis appuie sur ✅ Je suis rentré")
        return ("🔴🔴 N'ENTRE PAS", f"⏰ Trop tard : la position {sens} est déjà partie\n⏳ J'attends le prochain setup")
    if r.get("annonce"):
        return ("🔴🔴 N'ENTRE PAS", "📰 News dans moins de 15 min\n💥 Le prix peut bouger très fort")
    al = r["confirme"]
    if not al:
        return ("🔴🔴 N'ENTRE PAS", "⏳ Le 1h ne confirme pas la tendance 4h\n🔔 Je te préviens dès que c'est validé")
    if etire(r, al):
        return ("⛔ TROP TARD — le marché est déjà parti", "😎 Patience, on trouve une autre entrée\n" + prochaine(r, cle))
    if bloque_dw(r, al, r["m1"][-1]["c"]) or (not cle.get("ordre") and bloque_dw(r, al, zone_repli(r, al)["e"])):
        return ("🔴🔴 N'ENTRE PAS", f"📍 Prix {zone_txt(r['posD'])} Daily / {zone_txt(r['posW'])} Weekly\n🔄 Pas de poursuite du {'LONG' if al == 1 else 'SHORT'} en zone extrême. Attendre le repli ou une inversion confirmée.")
    zone = bool(cle.get("attente_rsi"))
    return (f"🟡 PATIENCE   {SENS[al]} bientôt\n🚦 ⏳ JE N'ENTRE PAS ENCORE" + (f"\n💰 TP visé ≈ {px(cle['ordre']['tp1'])}" if cle.get("ordre") else ""),
            f"✅ Tendance 4h + confirmation 1h\n{'✅' if zone else '⏳'} Prix dans la zone 🟨\n⏳ Rejet / clôture 5 min requis\n✅ Pas de news proche\n"
            "🚦 Attends mon 🟢 J'ENTRE MAINTENANT")

# ───────── Langue : chaque utilisateur choisit 🇫🇷 / 🇬🇧, tout le système suit ─────────
TRAD = {
# Boutons
"🟠 Analyse BTC": "🟠 BTC Analysis", "🥇 Analyse Gold": "🥇 Gold Analysis",
"📡 Mes marchés": "📡 My markets", "🟠 BTC uniquement": "🟠 BTC only", "🥇 GOLD uniquement": "🥇 GOLD only",
"🟠 BTC + 🥇 GOLD": "🟠 BTC + 🥇 GOLD", "📡 Choisir les marchés suivis": "📡 Choose followed markets",
"✅ Sélection enregistrée": "✅ Selection saved",
"✅ Je suis rentré": "✅ I'm in", "🚪 Je suis sorti": "🚪 I'm out", "📈 Mes résultats": "📈 My results",
"🧩 Indicateur TradingView": "🧩 TradingView indicator", "💎 Devenir VIP": "💎 Become VIP",
"Utilise les boutons 👇": "Use the buttons 👇", "❌ Non": "❌ No",
"📤 Partager à un ami": "📤 Share with a friend", "🎁 Offrir l'accès VIP": "🎁 Gift VIP access",
"🎁 Offrir l'indicateur": "🎁 Gift the indicator", "⛔ Retirer l'accès": "⛔ Remove access",
"✅ C'est fait, accès donné": "✅ Done, access given",
"🔓 Débloquer les positions (49,90 € / mois)": "🔓 Unlock positions (€49.90 / month)",
"🧩 Obtenir l'indicateur (49,90 € / mois)": "🧩 Get the indicator (€49.90 / month)",
# Verdicts / analyse
"📊 INDICATEURS PAR UNITÉ DE TEMPS": "📊 TIMEFRAME INDICATORS",
"📈 RSI PAR UNITÉ DE TEMPS": "📈 RSI BY TIMEFRAME",
"🔴 SIGNAL NON CONFIRMÉ": "🔴 SIGNAL NOT CONFIRMED",
"🟢 SIGNAL CONFIRMÉ": "🟢 SIGNAL CONFIRMED",
"🟠 SIGNAL EN ATTENTE": "🟠 SIGNAL PENDING",
"🚫 N'ENTRE PAS : ATTENDS LE PROCHAIN SIGNAL": "🚫 DO NOT ENTER: WAIT FOR THE NEXT SIGNAL",
"🟢 SIGNAL D'ENTRÉE VALIDÉ : VÉRIFIE LES NIVEAUX": "🟢 ENTRY SIGNAL VALIDATED: CHECK LEVELS",
"🟢 POSITION DÉJÀ OUVERTE : NE RAJOUTE PAS UNE ENTRÉE": "🟢 POSITION ALREADY OPEN: DO NOT ADD ANOTHER ENTRY",
"🟢 SUIVI DE LA POSITION EN COURS": "🟢 OPEN POSITION MONITORING",
"🟡 POSITION À VENIR — ordre en attente, aucune position ouverte": "🟡 UPCOMING POSITION — pending order, no position open",

"🕯 BOUGIE ": "🕯 CANDLE ",
" CLÔTURÉE — ": " CLOSED — ",
"🕒 Heure de clôture de la bougie :": "🕒 Candle close time:",
"⏳ PROCHAINE CLÔTURE ": "⏳ NEXT CANDLE CLOSE ",
"⏱ Temps restant :": "⏱ Time remaining:",
"🕒 Heure prévue :": "🕒 Scheduled time:",
"🟢 CLÔTURE — SIGNAL CONFIRMÉ": "🟢 CANDLE CLOSE — SIGNAL CONFIRMED",
"🔴 CLÔTURE — SIGNAL NON CONFIRMÉ": "🔴 CANDLE CLOSE — SIGNAL NOT CONFIRMED",
"🟢 POSITION EN COURS — SUIVI DU TRADE": "🟢 POSITION OPEN — TRADE MONITORING",
"🟢 Position déjà ouverte : ne rajoute pas une entrée.": "🟢 Position already open: do not add another entry.",
"🟢 Signal validé : vérifie la zone, le stop et les objectifs avant d'agir.": "🟢 Signal confirmed: check the entry zone, stop and targets before acting.",
"🚫 N'ENTRE PAS. Attends une confirmation complète avant toute entrée.": "🚫 DO NOT ENTER. Wait for full confirmation before entering.",
"🟡 POSITION À VENIR — ordre en attente, aucune position ouverte": "🟡 UPCOMING SETUP — pending order, no position is open",
"📍 Zone surveillée :": "📍 Monitored zone:",
"🛑 Stop prévu :": "🛑 Planned stop:",
"🕯 Bougie ": "🕯 Candle ",
" clôturée — ": " closed — ",
"🕒 Heure de clôture :": "🕒 Close time:",
"📊 Bougie haussière": "📊 Bullish candle",
"📊 Bougie baissière": "📊 Bearish candle",
"📊 Bougie neutre": "📊 Neutral candle",
"🧭 Tendance 4 h :": "🧭 4h trend:",
"🧭 Confirmation 1 h :": "🧭 1h confirmation:",
"❓ POURQUOI :": "❓ WHY:",
"➡️ PROCHAINE ACTION :": "➡️ NEXT ACTION:",
"🔜 Prochaine étape :": "🔜 Next step:",
"ℹ️ Une bougie clôturée ne déclenche jamais une entrée à elle seule. Aucun ordre n'est envoyé à ton broker.": "ℹ️ A candle close alone never triggers an entry. No order is sent to your broker.",

"🔴🔴 N'ENTRE PAS": "🔴🔴 DON'T ENTER",
"🟢 TU PEUX ENTRER": "🟢 YOU CAN ENTER", "🟡 PATIENCE": "🟡 BE PATIENT",
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
"🔜 Prochaine entrée   ➖ pas encore de sens": "🔜 Next entry   ➖ no direction yet", "🧭 STRATÉGIE MULTI-UT": "🧭 MULTI-TIMEFRAME STRATEGY", "💵 Dollar (DXY)": "💵 Dollar (DXY)", "💵 DXY ": "💵 DXY ",
"— dollar FORTE HAUSSE — IMPULSION HAUSSIÈRE": "— dollar STRONG RISE — BULLISH IMPULSE",
"— dollar FORTE BAISSE — IMPULSION BAISSIÈRE": "— dollar STRONG FALL — BEARISH IMPULSE",
"— dollar HAUSSIER (BULLISH)": "— dollar BULLISH",
"— dollar BAISSIER (BEARISH)": "— dollar BEARISH",
"💶 EUR/USD :": "💶 EUR/USD:",
"🔀 GOLD / dollar :": "🔀 GOLD / dollar:",
"🔀 BTC / dollar :": "🔀 BTC / dollar:",
"DIVERGENCE HAUSSIÈRE : l'actif résiste malgré un dollar en hausse": "BULLISH DIVERGENCE: the asset holds despite a rising dollar",
"DIVERGENCE BAISSIÈRE : l'actif baisse malgré un dollar en recul": "BEARISH DIVERGENCE: the asset falls despite a weaker dollar",
"CORRÉLATION INVERSE : dollar en hausse, actif en baisse": "INVERSE CORRELATION: dollar up, asset down",
"CORRÉLATION INVERSE : dollar en baisse, actif en hausse": "INVERSE CORRELATION: dollar down, asset up",
"COHÉRENT : DXY et EUR/USD évoluent en sens inverse": "CONSISTENT: DXY and EUR/USD move in opposite directions",
"DIVERGENCE : DXY et EUR/USD évoluent dans le même sens": "DIVERGENCE: DXY and EUR/USD move in the same direction",
"🏦 US10Y : ": "🏦 US10Y: ",
"🏦 US10Y : DONNÉES US10Y INDISPONIBLES": "🏦 US10Y: US10Y DATA UNAVAILABLE",
"🏦 US10Y : US10Y TROP ANCIEN": "🏦 US10Y: DATA TOO OLD",
"📅 Dernière publication officielle :": "📅 Last official publication:",
"points de base": "basis points",
"pression haussière sur les rendements": "upward pressure on yields",
"détente des rendements": "yields easing",
"rendement stable": "yields stable",
"favorable au 🟩 LONG": "favourable to 🟩 LONG", "frein pour le 🟩 LONG": "headwind for 🟩 LONG", "🏦 Taux US 10 ans": "🏦 US 10-year yield", "sur la journée": "on the day", "frein pour le Gold": "headwind for Gold", "favorable au Gold": "favourable to Gold", "📏 Hier : haut": "📏 Yesterday: high", "• bas": "• low", "🌏 Range Asie : haut": "🌏 Asia range: high", "💥 CASSURE": "💥 BREAKOUT", "🧲 NIVEAU CLÉ": "🧲 KEY LEVEL", "📍 Le prix approche le": "📍 Price is approaching the", "🕯 Vue 15 min : ça peut rebondir OU casser": "🕯 15 min view: it can bounce OR break", "⏳ J'attends la clôture de la bougie 15 min": "⏳ Waiting for the 15 min candle close", "plus haut d'hier": "yesterday's high", "plus bas d'hier": "yesterday's low", "plus haut de la semaine dernière": "last week's high", "plus bas de la semaine dernière": "last week's low", "plus haut du range Asie": "Asia range high", "plus bas du range Asie": "Asia range low", "👀 Je vérifie l'alignement 15 min / 1 h / 4 h avant d'entrer": "👀 I check the 15 min / 1 h / 4 h alignment before entering", "💵 DOLLAR EN FORTE BAISSE": "💵 DOLLAR FALLING HARD", "💵 DOLLAR EN FORTE HAUSSE": "💵 DOLLAR RISING HARD", "prudence": "be careful", "🧭 Le bot n'entre toujours qu'avec 15 min / 1 h / 4 h alignées": "🧭 The bot still only enters with 15 min / 1 h / 4 h aligned", "📰 NEWS USA DANS 1 H": "📰 US NEWS IN 1 H", "🛑 Pas de nouvelle position à partir de": "🛑 No new position from", "🔒 En position ? Mets-toi à BE si tu es en gain": "🔒 In a trade? Move to BE if in profit", "📊 Prévu": "📊 Forecast", "• avant": "• previous", "📰 RÉACTION À LA NEWS": "📰 NEWS REACTION", "⏳ J'attends la clôture de la bougie 15 min avant de reprendre": "⏳ Waiting for the 15 min close before resuming", "haussier ≈": "bullish ≈", "baissier ≈": "bearish ≈", ": le prix peut y rebondir": ": price may bounce there", ": le prix peut y buter": ": price may stall there", "🌙 MARCHÉ BIENTÔT FERMÉ": "🌙 MARKET CLOSING SOON", "⏰ Fermeture à": "⏰ Closes at", "🟥 Topstep / prop firms : tout fermé avant": "🟥 Topstep / prop firms: everything closed before", "(sinon fermeture automatique)": "(otherwise auto-flattened)", "🌙 Broker (CFD) / CME : fermeture": "🌙 Broker (CFD) / CME: close", "🔓 Réouverture": "🔓 Reopen", "dimanche": "Sunday", "• réouverture à": "• reopens at", "• réouverture dimanche soir": "• reopens Sunday evening", "(heure de Paris)": "(Paris time)", "🛡 Pas de nouvelle position avant la fermeture": "🛡 No new position before the close", "🔔 Je reprends la recherche après la réouverture": "🔔 I'll resume after the reopen", "🌙 FERMETURE DU GOLD DANS": "🌙 GOLD CLOSES IN", "🚦 🙅 PAS DE NOUVELLE POSITION": "🚦 🙅 NO NEW POSITION", "🔒 Tu es en position : mets-toi à BE si tu es en gain": "🔒 You're in a trade: move to BE if in profit", "🛡 Vérifie que ton SL est bien placé": "🛡 Check your SL is in place", "🛡 Ne pas ouvrir de position avant la fermeture": "🛡 Don't open a position before the close", "💥 Week-end : le prix peut s'ouvrir loin (écart), sécurise tes gains": "💥 Weekend: price may gap at the open, secure your profits", "💥 À la réouverture le prix peut sauter (écart)": "💥 At the reopen price may gap", "🎯 TP1 TOUCHÉ": "🎯 TP1 HIT", "✂️ Prends une partie des gains": "✂️ Take part of the profit", "🔒 Vérifie que ton SL est à BE": "🔒 Check your SL is at BE", "📈 Garde le reste : le marché peut encore pousser": "📈 Keep the rest: the market can push further", "🏁 TP2 visé": "🏁 Target TP2", "🙅 Ne coupe pas tout sur le TP1": "🙅 Don't close everything at TP1", "⏱ Durée estimée": "⏱ Estimated duration", "📅 Position LONGUE : elle peut durer plus d'une journée, garde ton SL en place la nuit": "📅 LONG position: it can last more than a day, keep your SL overnight", "🎁 Ta position gratuite arrive avec le prochain signal": "🎁 Your free position comes with the next signal", "🔒 Cette position est réservée aux VIP": "🔒 This position is VIP-only", "🎉🎉 BRAVO": "🎉🎉 WELL DONE", "💰 Ta position gratuite": "💰 Your free position", "🔥 C'est ça, ALIGN": "🔥 That's ALIGN", "😍 Imagine chaque position comme celle-là": "😍 Imagine every position like this one", "💎 En VIP : toutes les positions + le sens + le coach (BE, TP)": "💎 In VIP: every position + the direction + the coach (BE, TP)", "🔓 VIP 49,90 € / mois 👇": "🔓 VIP €49.90 / month 👇", "📊 Ça fait partie du jeu : on coupe petit, on gagne gros": "📊 It's part of the game: cut small, win big", "💎 En VIP : toutes les positions pour se refaire + le coach": "💎 In VIP: every position to bounce back + the coach", "RÉSULTAT ALIGN": "ALIGN RESULT", "📌 Entrée": "📌 Entry", "🏁 Sortie": "🏁 Exit", "📈 Résultat": "📈 Result", "⏱ Durée": "⏱ Duration", ": bravo !": ": well done!", "📸 N'hésite pas à partager ta capture dans ALIGN Résultats": "📸 Feel free to share your screenshot in ALIGN Results", "👇 Bouton 📸 Partager mon gain": "👇 Button 📸 Share my profit", "🛡 SL respecté, risque maîtrisé": "🛡 SL respected, risk under control", "📸 Voir les résultats ALIGN": "📸 See ALIGN results", ": SL touché, risque maîtrisé": ": SL hit, risk under control", "📊 Tous les résultats (TP et SL) sont publiés en toute transparence": "📊 All results (TP and SL) are published transparently", "👇 Bouton ci-dessous": "👇 Button below", "🔥 Une position VIP est EN COURS": "🔥 A VIP position is RUNNING", "👀 Une position VIP se PRÉPARE": "👀 A VIP position is COMING", "⏳ Pas de position pour l'instant": "⏳ No position right now", "🔒 Sens du marché : VIP": "🔒 Market direction: VIP", "🔒 LONG ou SHORT, entrée, SL, TP : réservés aux VIP": "🔒 LONG or SHORT, entry, SL, TP: VIP only", "Nouvelle info pour les VIP": "New info for VIPs", "🤫 Sens et niveaux cachés": "🤫 Direction and levels hidden", "🌀🌀 MANIPULATION EN COURS": "🌀🌀 MANIPULATION IN PROGRESS", "⚠️ MÈCHE SUSPECTE EN COURS": "⚠️ SUSPICIOUS WICK IN PROGRESS", "⏱ CHRONO EN DIRECT": "⏱ LIVE TIMER", "🚦 🟢 J'ENTRE": "🚦 🟢 I'M ENTERING", "🚦 🟢 ON RESTE EN POSITION": "🚦 🟢 WE STAY IN", "objectifs remis dans l'ordre": "targets put back in order", "🛑 SL inchangé": "🛑 SL unchanged", "🚦 🙅 JE N'ENTRE PAS": "🚦 🙅 I'M NOT ENTERING", "🚦 ⏳ JE N'ENTRE PAS ENCORE": "🚦 ⏳ NOT ENTERING YET", "💰 TP visé": "💰 Target TP", "🎯 Inscrit depuis": "🎯 Registered for", "✅ ENTRÉ": "✅ ENTERED", "🎯 Le coach te suit jusqu'au TP": "🎯 The coach follows you to TP",
"⏸ News dans moins de 15 min : pause": "⏸ News in less than 15 min: pause", "⏳ Reprise juste après la news": "⏳ Resuming right after the news",
": j'attends 15 min + 1 h + 4 h": ": waiting for 15 min + 1 h + 4 h", "⏳ Pas d'estimation tant que ce n'est pas aligné": "⏳ No estimate until aligned",
"🚀 Le marché est parti : j'attends le repli": "🚀 The market ran: waiting for the pullback", "↩️ Repli visé": "↩️ Target pullback",
"🔎 Je calcule la zone d'entrée": "🔎 Calculating the entry zone", "⏳ Quelques instants": "⏳ A few moments",
"🟨 Prix dans la zone : j'entre dès qu'une bougie clôture": "🟨 Price in the zone: I enter as soon as a candle closes", "⚡ Décision à la clôture de la bougie 15 min de": "⚡ Decision at the close of the 15 min candle at", "(clôture à": "(closes at",
"🟨 Le prix approche de la zone": "🟨 Price is approaching the zone", "⏳ Arrivée estimée": "⏳ Estimated arrival", "⏳ Encore loin : ça peut prendre des heures": "⏳ Still far: it may take hours",
"🕯 Prochaine clôture 15 min dans": "🕯 Next 15 min close in", "⌛ Si rien avant": "⌛ If nothing before", ": j'annule ta réservation (pas d'entrée forcée)": ": I cancel your booking (no forced entry)", "😎 RIEN N'A BOUGÉ": "😎 NOTHING HAS CHANGED", "👆 Mon analyse de": "👆 My analysis from", "est juste au-dessus : elle est toujours bonne": "is just above: it's still valid", "🔔 Je te préviens dès que ça change": "🔔 I'll tell you as soon as it changes", "🟨 Le prix est DANS la zone": "🟨 Price is IN the zone", "🕯 J'entre dès qu'une bougie clôture": "🕯 I enter as soon as a candle closes", "⏱ Prochaine décision : clôture de": "⏱ Next decision: close at", "🔔 Tiens-toi prêt, ça peut être tout de suite": "🔔 Get ready, it can be right now", "en remontant": "going up", "en redescendant": "going down", "🔄 Mis à jour à": "🔄 Updated at",
"4 h sans entrée": "4 h without entry", "😎 La position n'est pas venue : pas de mauvaise entrée": "😎 The position didn't come: no bad entry", "🎯 Réappuie sur le bouton pour la prochaine": "🎯 Tap the button again for the next one",
"⏱ Ton chrono en direct arrive juste en dessous 👇": "⏱ Your live timer is right below 👇", "🔄 Démarrage…": "🔄 Starting…", "🕯 Vue 15 min : la bougie de": "🕯 15 min view: the candle at",
"a piqué SOUS le dernier plus bas": "spiked BELOW the last low", "a piqué AU-DESSUS du dernier plus haut": "spiked ABOVE the last high",
"🎣 Les stops viennent d'être pris et le prix revient": "🎣 Stops were just taken and price is coming back", "🙅 N'entre pas maintenant": "🙅 Don't enter now",
"⏳ J'attends la CLÔTURE de cette bougie": "⏳ Waiting for this candle's CLOSE", "pour confirmer la manipulation": "to confirm the manipulation",
": pas de manipulation confirmée": ": manipulation not confirmed", "n'a pas clôturé en revenant": "didn't close back inside",
"⚠️ C'est peut-être une vraie cassure": "⚠️ It may be a real breakout", "vers le bas : prudence": "downwards: be careful", "vers le haut : prudence": "upwards: be careful", "🕯 Vue 15 min : grosse mèche SOUS le dernier plus bas": "🕯 15 min view: big wick BELOW the last low",
"🕯 Vue 15 min : grosse mèche AU-DESSUS du dernier plus haut": "🕯 15 min view: big wick ABOVE the last high", "🎣 Les stops ont été pris, puis la bougie a CLÔTURÉ en revenant": "🎣 Stops were hunted, then the candle CLOSED back inside",
"🙅 On ne court pas après la bougie": "🙅 We don't chase the candle", "📰 C'est l'effet de la news : encore plus de prudence": "📰 It's the news effect: extra caution",
"🧘 Tu es en position : reste cool, ton SL est en place": "🧘 You're in a trade: stay cool, your SL is set", "⚠️ C'est CONTRE ta position : ne bouge pas ton SL, je surveille": "⚠️ It's AGAINST your trade: don't move your SL, I'm watching",
"✅ Dans le sens de la tendance :": "✅ With the trend:", "🎯 Point d'entrée visé : retour vers": "🎯 Target entry: back to", "ancien plus bas": "previous low", "ancien plus haut": "previous high",
"⭐ Encore mieux : milieu de la mèche": "⭐ Even better: middle of the wick", "⏳ Patience : j'entre seulement sur une mèche de rejet + CLÔTURE 5 min": "⏳ Patience: I only enter on a rejection wick + CLOSE (5 / 15 min)",
"🔔 Je t'envoie 🟢 J'ENTRE MAINTENANT au bon moment": "🔔 I'll send 🟢 I'M ENTERING NOW at the right time", "⚠️ CONTRE la tendance de fond": "⚠️ AGAINST the main trend",
"tant que 15 min / 1 h / 4 h ne se retournent pas": "while 15 min / 1 h / 4 h don't turn", "🔔 Je te préviens si ça se retourne": "🔔 I'll tell you if it turns",
"✅ Validé quand 15 min + 1 h + 4 h vont dans le même sens": "✅ Validated when 15 min + 1 h + 4 h agree",
"🌀 Après la manipulation : les stops ont été pris, on rentre dans le bon sens": "🌀 After the manipulation: stops were taken, we enter the right way", "🏔 Fond 4 h + Daily": "🏔 Trend 4 h + Daily", "🔁 Confirmation 1 h": "🔁 Confirmation 1 h",
"🎯 Déclencheur 15 min": "🎯 Trigger 15 min", "⏱ Timing 5 min": "⏱ Timing 5 min", "✅ Tendance VALIDÉE": "✅ Trend VALIDATED", "⏳ Le 15 min fait son repli : l'entrée n'est PAS encore là": "⏳ The 15 min is pulling back: the entry is NOT there yet", "✅ VALIDÉ": "✅ VALIDATED",
"➖ Pas de tendance de fond en 4 h": "➖ No 4 h trend", "⛔ Rien de validé : on ne trade pas": "⛔ Nothing validated: no trade",
"⚖️ 4 h et Daily en désaccord": "⚖️ 4 h and Daily disagree", "⛔ Rien de validé : on attend": "⛔ Nothing validated: we wait",
"↩️ Repli contre la tendance de fond": "↩️ Pullback against the main trend", "↩️ Rebond contre la tendance de fond": "↩️ Bounce against the main trend",
"possible PLUS TARD — ⛔ PAS ENCORE VALIDÉ": "possible LATER — ⛔ NOT VALIDATED YET", "✅ Validé quand le 1 h PUIS le 15 min repassent": "✅ Validated when 1 h THEN 15 min turn",
"en préparation — ⛔ PAS ENCORE VALIDÉ": "building — ⛔ NOT VALIDATED YET", "✅ Il manque": "✅ Missing", "⛔ pas encore validée": "⛔ not validated yet",
"🕯 J'attends une MÈCHE DE REJET + CLÔTURE": "🕯 Waiting for a REJECTION WICK + CLOSE", "🛑 SL serré juste derrière la mèche": "🛑 Tight SL just behind the wick",
": pas de rejet dans la zone": ": no rejection in the zone", "😎 Je recalcule le prochain point": "😎 Recalculating the next point",
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
"💡 TP1 touché → SL à BE": "💡 TP1 hit → SL to BE", "💡 BE : je te dis quand": "💡 BE: I'll tell you when", "(bougie 15 min clôturée bien au-dessus de l'entrée)": "(15 min candle closed well above the entry)", "(bougie 15 min clôturée bien en dessous de l'entrée)": "(15 min candle closed well below the entry)", "(regarde en vue": "(look at the chart", "(vue": "(chart",
"📍 Repère prix": "📍 Price guide", "📍 Repère prix : SL ≈": "📍 Price guide: SL ≈",
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
"✂️ Je coupe ma position": "✂️ I'm closing my position", "News dans": "News in", "🔒 Mets ton SL à BE (prix d'entrée)": "🔒 Move your SL to BE (entry price)", "🔒 METS-TOI À BE": "🔒 MOVE TO BE", "🚦 🙅 JE NE SUIS PLUS EN POSITION": "🚦 🙅 I'M OUT", ": sorti à BE": ": out at BE", "🛡 Aucune perte": "🛡 No loss", "🔎 Je cherche la prochaine entrée": "🔎 Looking for the next entry", "🛑 Nouveau SL : BE": "🛑 New SL: BE", "(ton prix d'entrée)": "(your entry price)", "(prix d'entrée)": "(entry price)", "🕯 Pourquoi : la bougie 15 min de": "🕯 Why: the 15 min candle at", "a CLÔTURÉ bien au-dessus de l'entrée": "CLOSED well above the entry", "a CLÔTURÉ bien en dessous de l'entrée": "CLOSED well below the entry", "🛡 Résultat : plus aucune perte possible": "🛡 Result: no more loss possible",
"✂️ Le trade n'avance pas": "✂️ The trade isn't moving", "✂️ Je coupe avant la news": "✂️ Closing before the news",
"🔁 Mets ton SL à BE (ton prix d'entrée)": "🔁 Move your SL to BE (your entry price)", "a CLÔTURÉ bien au-dessus de ton entrée": "CLOSED well above your entry", "a CLÔTURÉ bien en dessous de ton entrée": "CLOSED well below your entry",
"🕯 La bougie 15 min de": "🕯 The 15 min candle at", ": MAINTENANT, à la clôture de la bougie de rejet": ": NOW, at the close of the rejection candle", "🕯 Repère la mèche basse": "🕯 Find the low wick", "🕯 Repère la mèche haute": "🕯 Find the high wick",
"💥 La bougie 15 min a CLÔTURÉ au-delà du niveau": "💥 The 15 min candle CLOSED beyond the level", ": on protège sans se faire sortir au retest": ": we protect without being stopped on the retest",
"🛡 Comme ça, plus aucune perte possible": "🛡 This way, no loss possible", "🎯 On laisse courir vers le TP": "🎯 We let it run to TP",
"🕯 Repère la mèche du dernier": "🕯 Find the wick of the last", "creux": "low", "sommet": "high",
"⬆️ Monte": "⬆️ Raise", "⬇️ Descends": "⬇️ Lower", "ton SL un peu": "your SL a little", "cette mèche": "this wick",
"🙅 Jamais pile sur la mèche : elle peut être retouchée": "🙅 Never exactly on the wick: it can be retested", "🙅 Jamais pile sur la mèche": "🙅 Never exactly on the wick",
"💰 Ton gain est protégé": "💰 Your profit is protected", "🛡 Ta perte possible est réduite": "🛡 Your possible loss is reduced",
": reste cool": ": stay cool", "🌬 Le marché respire": "🌬 The market is breathing", "🕯 Il peut revenir un peu, c'est normal": "🕯 It may pull back a bit, that's normal",
"🛑 Ne touche pas ton SL": "🛑 Don't touch your SL",
"SOUS la mèche du dernier creux": "BELOW the wick of the last low", "SOUS la mèche basse": "BELOW the low wick", "AU-DESSUS de la mèche haute": "ABOVE the high wick", "• bougie 15 min de": "• 15 min candle at", "• bougie 5 min de": "• 5 min candle at", "(bougie de cassure)": "(breakout candle)", "(sous la structure 15 min)": "(behind the 15 min structure)", "AU-DESSUS de la mèche du dernier sommet": "ABOVE the wick of the last high",
"la mèche du dernier creux": "the wick of the last low", "la mèche du dernier sommet": "the wick of the last high",
"🛑 SL un peu": "🛑 SL a little", "SOUS": "BELOW", "AU-DESSUS de": "ABOVE", "sous la": "below the", "au-dessus du": "above the",
"résistance": "resistance", "support": "support",
# Entrée abonné
"🤖 Coach activé jusqu'au TP": "🤖 Coach on until TP", "🔎 Je surveille toutes les 5 min :": "🔎 I check every 5 min:",
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
"(en cours)": "(now)", ": la zone a été traversée sans rejet": ": the zone was crossed with no rejection", "🙅 Pas d'entrée, heureusement": "🙅 No entry, luckily", "🔎 Je recalcule le prochain point plus bas": "🔎 Recalculating the next point lower", "🔎 Je recalcule le prochain point plus haut": "🔎 Recalculating the next point higher", ": la mèche de rejet est trop grande (SL trop loin)": ": the rejection wick is too big (SL too far)", "😎 Je ne prends pas ce risque, j'attends mieux": "😎 I'm not taking that risk, waiting for better", "🧠 L'avis de l'IA ALIGN": "🧠 ALIGN AI's view", "🧠 L'IA ALIGN sur cette entrée": "🧠 ALIGN AI on this entry", "🧠 La leçon de l'IA ALIGN": "🧠 ALIGN AI's lesson", ": RSI en surcharge ✅ — j'attends la MÈCHE DE REJET et la CLÔTURE ⏳": ": RSI overextended ✅ — waiting for the REJECTION WICK and the CLOSE ⏳",
"👀 Vue 5 min : une bougie qui pique dans la zone puis clôture en remontant": "👀 5 / 15-min chart: a candle that dips into the zone then closes back up",
"👀 Vue 5 min : une bougie qui pique dans la zone puis clôture en redescendant": "👀 5 / 15-min chart: a candle that spikes into the zone then closes back down",
"Mèche de rejet + clôture (5 min)": "Rejection wick + close (5 / 15 min)", "🅰️ Repli vers ≈": "🅰️ Pullback to ≈", "⚠️ Grosses unités en excès : si 15 min / 1 h / 4 h se retournent →": "⚠️ Big timeframes overextended: if 15 min / 1 h / 4 h turn →", " possible": " possible", "📉 Repli attendu : de ≈": "📉 Expected pullback: from ≈", "📈 Rebond attendu : de ≈": "📈 Expected bounce: from ≈", " vers ≈ ": " to ≈ ", "dans cette zone": "in this zone", "🧠 Mémoire du bot : ce type de position a gagné": "🧠 Bot memory: this type of position won",
"cassure vue, mais je passe mon tour": "breakout seen, but I'm skipping", "prix dans la zone, mais je passe mon tour": "price in the zone, but I'm skipping",
"📚 Ce type de position a perdu trop souvent": "📚 This type of position lost too often", " gagnés": " won", ": je note ce": ": I'm noting this",
"en session": "in session", "🧠 Bilan de ce type :": "🧠 Record for this type:", "💡 Leçon : je serai plus prudent sur ce type de position": "💡 Lesson: I'll be more careful with this type of position",
"💪 Je garde ce type de position": "💪 I keep this type of position", "🧠 Le bot apprend : il note chaque TP et chaque SL": "🧠 The bot learns: it records every TP and SL",
"🧠 Ce que le bot a appris :": "🧠 What the bot has learned:", "🔥🔥🔥 TRÈS BELLE POSITION": "🔥🔥🔥 VERY NICE POSITION", "🔥 BELLE POSITION": "🔥 NICE POSITION", "% visés": "% targeted", "CASSURE EN VUE —": "BREAKOUT IN SIGHT —", "👀 Le prix approche ≈": "👀 Price is approaching ≈", "plus haut des dernières bougies 15 min": "high of the last 15-min candles",
"plus bas des dernières bougies 15 min": "low of the last 15-min candles", "🕯 Si une bougie 15 min CLÔTURE au-dessus → j'entre": "🕯 If a 15-min candle CLOSES above → I enter",
"🕯 Si une bougie 15 min CLÔTURE en dessous → j'entre": "🕯 If a 15-min candle CLOSES below → I enter", "🙅 Une mèche qui dépasse ne suffit pas : on attend la clôture": "🙅 A wick poking through isn't enough: we wait for the close", "🔔 Tiens-toi prêt": "🔔 Get ready",
"👍 Like si tu participes": "👍 Like if you're participating",
"ℹ️ Analyse indicative : décision et ordre sous ta responsabilité.": "ℹ️ Indicative analysis: you are responsible for your decision and order.", "la mèche de la bougie de cassure": "the wick of the breakout candle", ": à la clôture de la bougie 15 min qui casse ≈": ": at the close of the 15-min candle breaking ≈", "💥 CASSURE CONFIRMÉE": "💥 BREAKOUT CONFIRMED", "🕯 La bougie 15 min a CLÔTURÉ au-dessus de ≈": "🕯 The 15-min candle CLOSED above ≈",
"🕯 La bougie 15 min a CLÔTURÉ en dessous de ≈": "🕯 The 15-min candle CLOSED below ≈", "la mèche de cette bougie": "the wick of this candle",
"🅱️ Ou CASSURE : si une bougie 15 min CLÔTURE au-dessus de ≈": "🅱️ Or BREAKOUT: if a 15-min candle CLOSES above ≈", "🅱️ Ou CASSURE : si une bougie 15 min CLÔTURE en dessous de ≈": "🅱️ Or BREAKOUT: if a 15-min candle CLOSES below ≈",
"sur la cassure": "on the breakout", "🅰️ Entrée sur le repli dans la zone 🟨": "🅰️ Entry on the pullback in the zone 🟨", "POINT D'ENTRÉE À VENIR —": "ENTRY POINT COMING —", "👀 ÇA ARRIVE": "👀 IT'S COMING", "🎯 Je rentre dans la position (coach)": "🎯 I'm in this position (coach)", "🤖 Mon coach": "🤖 My coach", "👀 Voir plus": "👀 See more", "↩️ Repli en cours sur le 15 min : c'est lui qu'on attend pour entrer": "↩️ 15-min pullback in progress: that's what we wait for to enter", "⬇️ Tes boutons sont là 👇": "⬇️ Your buttons are here 👇", "💡 Clavier caché ? Appuie sur l'icône ⌘ à droite du champ": "💡 Keyboard hidden? Tap the ⌘ icon right of the field", "Prochaines news (heure de Paris) :": "Next news (Paris time):", "aujourd'hui": "today", "demain": "tomorrow",
" — dans ": " — in ", " jours": " days", " — en cours": " — now", "✅ Rien d'ici": "✅ Nothing within", "✅ Plus aucune annonce ni discours cette semaine": "✅ No more news or speeches this week",
"lun. ": "Mon ", "mar. ": "Tue ", "mer. ": "Wed ", "jeu. ": "Thu ", "ven. ": "Fri ", "sam. ": "Sat ", "dim. ": "Sun ", ": ÇA RETRACE": ": IT'S PULLING BACK", "😎 Le repli qu'on attend commence": "😎 The pullback we're waiting for is starting",
"🎯 Zone visée ≈": "🎯 Target zone ≈", "🎯 Il devrait revenir vers ≈": "🎯 It should come back to ≈", "🕯 La moitié du dernier grand mouvement (vue 15 min)": "🕯 Half of the last big move (15-min chart)", "👀 Sois patient": "👀 Be patient", "👀 Vue 15 min, sois patient": "👀 15-min chart, be patient", "🔔 Je te préviens dès qu'on y est": "🔔 I'll tell you as soon as we're there",
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
"🔒 Ensuite : tu sais qu'une position arrive, mais sans le sens ni les niveaux": "🔒 Then: you know a position is coming, but without direction or levels", "👉 Bouton ci-dessous : tu paies et tu entres directement dans le canal ALIGN VIP 💎": "👉 Button below: you pay and go straight into the ALIGN VIP channel 💎",
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
"🎁🎁 POSITION DE BIENVENUE OFFERTE 🎁🎁": "🎁🎁 FREE WELCOME POSITION 🎁🎁", "🎁🎁 TA POSITION GRATUITE DU JOUR 🎁🎁": "🎁🎁 YOUR FREE POSITION OF THE DAY 🎁🎁", "💎 C'est ta position gratuite du jour. Toutes les autres + le coach : VIP 49,90 € / mois": "💎 This is your free position of the day. All the others + the coach: VIP €49.90 / month", "🎁 Ta position gratuite du jour est déjà utilisée": "🎁 Your free position of the day is already used", "🎁 1 POSITION OFFERTE CHAQUE JOUR": "🎁 1 FREE POSITION EVERY DAY", "👋 Bienvenue sur ALIGN Gratuit 🎁 (BTC + Gold)": "👋 Welcome to ALIGN Free 🎁 (BTC + Gold)", "🎁 1 position offerte chaque jour": "🎁 1 free position every day",
"👀 Suis-la en vue 15 minutes, tout est expliqué en bougies": "👀 Follow it on the 15-min chart, everything is explained in candles",
"💎 C'est ta position offerte. Les suivantes + le coach : VIP 49,90 € / mois": "💎 This is your free position. Next ones + the coach: VIP €49.90 / month",
"🔒 Position réservée aux VIP": "🔒 VIP-only position", "🎁 Ta position de bienvenue est déjà utilisée": "🎁 Your welcome position is already used",
"💎 VIP 49,90 € / mois : toutes les positions + le coach en direct": "💎 VIP €49.90 / month: all positions + live coach",
"💎 VIP 49,90 € / mois : toutes les positions + le coach": "💎 VIP €49.90 / month: all positions + the coach",
"🎁 Ta 1re POSITION est OFFERTE": "🎁 Your 1st POSITION is FREE", "🕯 Expliquée en bougies (vue 15 min) + coach jusqu'au TP": "🕯 Explained in candles (15-min chart) + coach to TP",
"📰 Alertes news et discours gratuites": "📰 Free news and speech alerts", "🔔 Ouvertures de marché gratuites": "🔔 Free market-open alerts",
"🔒 Ensuite les positions arrivent MASQUÉES": "🔒 After that, positions arrive HIDDEN", "👉 Bouton ci-dessous, puis reviens ici et tape /start": "👉 Button below, then come back and type /start",
"🔒 Les positions en direct sont réservées aux VIP": "🔒 Live positions are VIP-only", "🎁 Ta position gratuite du jour est encore dispo": "🎁 Your free position of the day is still available", "🎁 Ta position de bienvenue reste offerte": "🎁 Your welcome position is still free",
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
"🤖 Appuie sur ✅ Je suis rentré : ton coach te suit jusqu'au TP": "🤖 Tap ✅ I'm in: your coach follows you to TP",
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

# Analyse Telegram complète — libellés et plan multi-timeframe
"🚫 N'ENTRE PAS : ATTENDS LE PROCHAIN SIGNAL": "🚫 DON'T ENTER: WAIT FOR THE NEXT SIGNAL",
"🟢 SIGNAL D'ENTRÉE VALIDÉ : VÉRIFIE LES NIVEAUX": "🟢 ENTRY SIGNAL VALIDATED: CHECK THE LEVELS",
"🟢 POSITION DÉJÀ OUVERTE : NE RAJOUTE PAS UNE ENTRÉE": "🟢 POSITION ALREADY OPEN: DO NOT ADD ANOTHER ENTRY",
"⏸ PAS D'ENTRÉE POUR LE MOMENT : ATTENDS": "⏸ NO ENTRY FOR NOW: WAIT",
"🕯 CLÔTURE ": "🕯 CANDLE CLOSE ",
"SIGNAL CONFIRMÉ": "SIGNAL CONFIRMED",
"SIGNAL NON CONFIRMÉ": "SIGNAL NOT CONFIRMED",
"🕒 Bougie clôturée à": "🕒 Candle closed at",
"📊 RÉSULTAT DE LA BOUGIE": "📊 CANDLE RESULT",
"Bougie ": "Candle ",
"Ouverture :": "Open:",
"Clôture :": "Close:",
"🧭 TENDANCE MULTI-UNITÉS": "🧭 MULTI-TIMEFRAME TREND",
"Confirmation 1 h :": "1h confirmation:",
"🟢 alignement confirmé": "🟢 alignment confirmed",
"alignement non confirmé": "alignment not confirmed",
"🚦 DÉCISION ALIGN": "🚦 ALIGN DECISION",
"⏳ POURQUOI": "⏳ WHY",
"➡️ PROCHAINE ÉTAPE": "➡️ NEXT STEP",
"ℹ️ À RETENIR": "ℹ️ IMPORTANT",
"Une clôture seule ne déclenche pas une entrée.": "A candle close alone does not trigger an entry.",
"Aucun ordre n'est envoyé à ton broker.": "No order is sent to your broker.",
"📡 LECTURE DU MARCHÉ": "📡 MARKET OVERVIEW",
"🟢 Biais haussier confirmé": "🟢 Bullish bias confirmed",
"🔴 Biais baissier confirmé": "🔴 Bearish bias confirmed",
"🟠 Pas de biais confirmé en 1h / 4h": "🟠 No confirmed 1h / 4h bias",
"📊 INDICATEURS PAR UNITÉ DE TEMPS": "📊 TIMEFRAME INDICATORS",
"📊 INDICATEURS / UNITÉS DE TEMPS": "📊 INDICATORS / TIMEFRAMES",
"📈 RSI :": "📈 RSI:",
"RSI :": "RSI:",
"🧭 CONFIRMATION DE TENDANCE": "🧭 TREND CONFIRMATION",
"Alignement 1h + 4h :": "1h + 4h alignment:",
"CONFIRMÉ": "CONFIRMED",
"EN ATTENTE": "PENDING",
"Zone Daily :": "Daily zone:",
"Zone Weekly :": "Weekly zone:",
"🧭 PLAN MULTI-TIMEFRAME": "🧭 MULTI-TIMEFRAME PLAN",
"🧭 STRATÉGIE MULTI-UT": "🧭 MULTI-TIMEFRAME STRATEGY",
"🏔 Tendance principale 4 h :": "🏔 Main 4h trend:",
"📅 Tendance Daily :": "📅 Daily trend:",
"🔁 Confirmation 1 h :": "🔁 1h confirmation:",
"ℹ️ Contexte 15 min": "ℹ️ 15m context",
"🎯 Déclencheur 5 min": "🎯 5m trigger",
"✅ Tendance VALIDÉE": "✅ Trend CONFIRMED",
"Le 15 min fait son repli : l'entrée n'est PAS encore là": "The 15m is pulling back: entry is NOT confirmed yet",
"✅ VALIDÉ": "✅ CONFIRMED",
"➖ Pas de tendance de fond en 4 h": "➖ No primary 4h trend",
"⛔ Rien de validé : on ne trade pas": "⛔ Nothing confirmed: no trade",
"↩️ 1 h en opposition à la tendance de fond": "↩️ 1h conflicts with the main trend",
"⛔ On attend la confirmation 1 h": "⛔ Waiting for 1h confirmation",
"en préparation — ⛔ PAS ENCORE VALIDÉ": "preparing — ⛔ NOT CONFIRMED YET",
"Il manque la confirmation 1 h": "1h confirmation is still missing",
"━━━━━━━━━━━━━━━━━━": "━━━━━━━━━━━━━━━━━━",
"🌍 NIVEAUX & CONTEXTE": "🌍 LEVELS & CONTEXT",
"📏 Plus haut d'hier :": "📏 Yesterday's high:",
"📏 Plus bas d'hier :": "📏 Yesterday's low:",
"🌏 Range Asie - plus haut :": "🌏 Asia range - high:",
"🌏 Range Asie - plus bas :": "🌏 Asia range - low:",
"🧲 FVG": "🧲 FVG",
"haussière": "bullish",
"baissière": "bearish",
"Basse": "Low",
"Haute": "High",
"🟨 ZONE DE PRÉPARATION": "🟨 PREPARATION ZONE",
"Limite basse :": "Lower limit:",
"Limite haute :": "Upper limit:",
"┏━━━━━━━━ 🚦 DÉCISION ALIGN ━━━━━━━━┓": "┏━━━━━━━━ 🚦 ALIGN DECISION ━━━━━━━━┓",
"🎯 POSITION EN COURS :": "🎯 OPEN POSITION:",
"🎯 POINT VISÉ :": "🎯 TARGET SETUP:",
"🎯 DIRECTION À SURVEILLER :": "🎯 DIRECTION TO WATCH:",
"🎯 POINT D'ENTRÉE": "🎯 ENTRY POINT",
"aucun tant que le biais 1h / 4h n'est pas confirmé": "none until the 1h / 4h bias is confirmed",
"Déclencheur : clôture": "Trigger: candle close",
"Prochaine entrée :": "Next entry:",
"heure de Paris": "Paris time",
"Annonces importantes aujourd'hui": "Important announcements today",
"Aucune annonce majeure US aujourd'hui.": "No major US announcements today.",
"NEWS USA DANS 1 H": "US NEWS IN 1 HOUR",
"⚠️⚠️ NEWS USA dans": "⚠️⚠️ US NEWS in",
"🚨🚨🚨 NEWS DANS": "🚨🚨🚨 NEWS IN",
"RÉACTION À LA NEWS": "REACTION TO NEWS",
"Pas de nouvelle position": "No new position",
"Ne touche à rien": "Do not touch anything",
"News passée": "News passed",
"Le bot reprend la recherche d'entrées.": "The bot is resuming its search for entries.",
"Plus aucune annonce ni discours cette semaine": "No more announcements or speeches this week",
"Prochaines news": "Upcoming news",
"Rien d'ici": "Nothing in the next",
"Calendrier économique indisponible": "Economic calendar unavailable",
"📰 News : calendrier indisponible": "📰 News: calendar unavailable",

}

TRAD.update({
    "🔴 PAS D'ENTRÉE — SIGNAL NON CONFIRMÉ": "🔴 NO ENTRY — SIGNAL NOT CONFIRMED",
    "🟢 POSITION EN COURS": "🟢 POSITION OPEN",
    "🟢 SIGNAL VALIDÉ — VÉRIFIE LES NIVEAUX": "🟢 SIGNAL CONFIRMED — CHECK LEVELS",
    "🟡 EN ATTENTE — PAS D'ENTRÉE": "🟡 WAITING — NO ENTRY",
    "clôturée": "closed",
    "CLÔTURES MULTI-UT": "MULTI-TF CLOSES",
    "Prochaine validation : clôture": "Next confirmation: candle close",
    "HAUSSE": "UP",
    "BAISSE": "DOWN",
    "NEUTRE": "NEUTRAL",
    "🚫 Aucun ordre envoyé au broker.": "🚫 No order is sent to the broker."
})


# Libellés des claviers inline et règle de risque : traduction explicite, sans changer les callbacks.
TRAD.update({
    "❓ Pourquoi cette décision ?": "❓ Why this decision?",
    "📊 Analyse complète": "📊 Full analysis",
    "🎯 Niveaux / prix": "🎯 Levels / prices",
    "⏱ Toutes les unités": "⏱ All timeframes",
    "🗂 Historique des messages": "🗂 Message history",
    "🟢 Je suis rentré": "🟢 I'm in",
    "🔔 Suivre la prochaine position": "🔔 Follow the next position",
    "📌 Revoir l'analyse ": "📌 Review analysis: ",
    "📍 Ma position • SL / TP": "📍 My position • SL / TP",
    "🗂 Historique": "🗂 History",
    "🔔 Suivre le prochain setup": "🔔 Follow the next setup",
    "Choisis une action ALIGN": "Choose an ALIGN action",
    "7️⃣ ⚖️ Risque conseillé : 0,5 à 1 % du compte par position ; jamais sans SL": "7️⃣ ⚖️ Suggested risk: 0.5 to 1% of the account per position; never trade without an SL",

    "🎯 Suivre la prochaine position": "🎯 Follow the next position",
    "✅ Publier": "✅ Publish",
    "❌ Refuser": "❌ Decline",
    "✅ Accepter": "✅ Accept",
    "👀 Voir son profil": "👀 View profile",
    "⬅️ Plus récents": "⬅️ Newer",
    "Plus anciens ➡️": "Older ➡️",
    "↩️ Retour à l'analyse": "↩️ Back to analysis",
    "🎯 Voir les niveaux": "🎯 View levels",
    "ℹ️ Comprendre l'analyse": "ℹ️ Understand the analysis",
    "📡 Mes marchés": "📡 My markets",
    "🟠 BTC uniquement": "🟠 BTC only",
    "🥇 GOLD uniquement": "🥇 GOLD only",
    "🟠 BTC + 🥇 GOLD": "🟠 BTC + 🥇 GOLD",
    "✅ 🟠 BTC uniquement": "✅ 🟠 BTC only",
    "✅ 🥇 GOLD uniquement": "✅ 🥇 GOLD only",
    "✅ 🟠 BTC + 🥇 GOLD": "✅ 🟠 BTC + 🥇 GOLD",
    "📡 CHOISIS LES MARCHÉS QUE TU SOUHAITES SUIVRE": "📡 CHOOSE THE MARKETS YOU WANT TO FOLLOW",
    "Les analyses et alertes privées seront filtrées selon ton choix.": "Private analyses and alerts will be filtered according to your choice.",
    "Les positions déjà ouvertes restent suivies jusqu'à leur clôture.": "Already-open positions will continue to be monitored until closed.",
})

TRAD.update({
    "🧭 STRATÉGIE MULTI-UT": "🧭 MULTI-TIMEFRAME STRATEGY",
    "🏔 Tendance principale 4 h : ": "🏔 Main 4h trend: ",
    "🔁 Confirmation 1 h : ": "🔁 1h confirmation: ",
    "👀 Préparation 15 min : ": "👀 15m setup: ",
    "🎯 Timing 5 min : ": "🎯 5m timing: ",
    "📅 Contexte Daily : ": "📅 Daily context: ",
    "🧩 PROFIL RETENU : ": "🧩 SELECTED PROFILE: ",
    "🧭 Lecture : ": "🧭 Reading: ",
    "⏱ Horizon indicatif : ": "⏱ Indicative horizon: ",
    "H4, H1 et M15 sont alignés": "H4, H1 and M15 are aligned",
    "M15 est en retracement contre le biais H4/H1": "M15 is pulling back against the H4/H1 bias",
    "M15 est neutre : attendre une structure exploitable": "M15 is neutral: wait for a usable structure",
    "H1 et M15 sont alignés": "H1 and M15 are aligned",
    "M15 et M5 sont alignés": "M15 and M5 are aligned",
    " mais H1/H4 s’opposent": " but H1/H4 oppose it",
    "plusieurs séances si la structure H4 reste valide": "several sessions while H4 structure remains valid",
    "séance en cours ; pas de conservation automatique la nuit": "current session; no automatic overnight hold",
    "séance en cours ; réévaluer à chaque clôture": "current session; reassess at every close",
    "mouvement de séance ; sortie avant invalidation": "session move; exit before invalidation",
    "court terme ; ne pas transformer en position swing": "short term; do not turn into a swing position",
    "aucune durée de position à annoncer": "no holding period to announce",
    "SCALPING CONTRE-TENDANCE": "COUNTER-TREND SCALPING",
    "SWING": "SWING", "INTRADAY": "INTRADAY", "SCALPING": "SCALPING", "ATTENTE": "WAIT",
    "🚦 CONFLUENCE M5 — attendre le déclencheur clôturé": "🚦 M5 CONFLUENCE — wait for the confirmed trigger",
    "🚦 PRÉPARATION — attendre l’alignement ou le retournement M5": "🚦 SETUP FORMING — wait for M5 alignment or reversal",
    "⚠️ Contre-tendance : objectif court, risque réduit selon les règles, aucune conservation swing.": "⚠️ Counter-trend: short target, reduced risk per rules, never hold as a swing.",
    "🟡 Setup court terme détecté": "🟡 Short-term setup detected",
    "⛔ Ce setup n’est pas un swing et reste soumis au déclencheur clôturé.": "⛔ This is not a swing setup and still requires a confirmed trigger.",
    "➖ Pas de tendance de fond en 4 h": "➖ No higher-timeframe trend on 4h",
    "⏳ Les configurations M15/M5 restent surveillées pour un éventuel scalp.": "⏳ M15/M5 setups remain monitored for a possible scalp.",
    "↩️ 1 h en opposition à la tendance de fond": "↩️ 1h opposes the higher-timeframe trend",
    "⏳ Pas de swing : surveiller uniquement une configuration courte M15/M5.": "⏳ No swing: monitor only a short-term M15/M5 setup.",
    "⏳ confirmation H1 manquante": "⏳ H1 confirmation missing",
    "Profil proposé : ": "Suggested profile: ",
    "Préparation M15 : ": "M15 setup: ",
    "Timing M5 : ": "M5 timing: ",
    "alignée": "aligned",
    "en attente / retracement": "waiting / pullback",
    "direction alignée ; déclencheur clôturé à vérifier": "direction aligned; confirm the candle-close trigger",
    "attendre la confirmation dans le sens du setup": "wait for confirmation in the setup direction",
    "🔁 1 h : confirme ou contredit le biais de fond H4": "🔁 1h: confirms or contradicts the H4 bias",
    "👀 15 min : préparation, retracement, cassure et retest": "👀 15m: setup, pullback, breakout and retest",
    "🎯 5 min : timing ; clôture, rejet ou retest confirmé obligatoire": "🎯 5m: timing; confirmed close, rejection or retest required",
    "⚖️ SCALPING : M15 + M5 • INTRADAY : H1 + M15 + M5 • SWING : H4 + H1 + M15": "⚖️ SCALPING: M15 + M5 • INTRADAY: H1 + M15 + M5 • SWING: H4 + H1 + M15",
    "⚠️ Un setup contre H4/H1 reste un scalp contre-tendance, jamais un swing": "⚠️ A setup against H4/H1 remains counter-trend scalping, never a swing",
    "📍 1 min : suivi du prix et de la position": "📍 1m: price and position monitoring",
    "ℹ️ 2, 10, 30 et 45 min + 2 h et Daily : confirmations et contexte complémentaires.": "ℹ️ 2m, 10m, 30m, 45m, 2h and Daily: additional context and confirmation.",
    "⚠️ Une unité haussière ou baissière ne constitue jamais, seule, une autorisation d’entrée.": "⚠️ A bullish or bearish timeframe alone never authorizes an entry.",
    "🧭 Fond H4 • confirmation H1 • préparation M15 • timing M5": "🧭 H4 bias • H1 confirmation • M15 setup • M5 timing",
    "M15 = préparation, M5 = timing après clôture confirmée": "M15 = setup, M5 = timing after confirmed close",
    "Biais H4/H1 validé": "H4/H1 bias confirmed",
    "Le 15 min retrace : attendre le retour du M5 dans le sens du biais": "15m is pulling back: wait for M5 to turn back with the bias",
    "Biais de fond H4/H1 validé": "H4/H1 higher-timeframe bias confirmed",
    "📈 TradingView 5 min": "📈 TradingView 5 min",
    "📈 TradingView 15 min": "📈 TradingView 15 min",
    "📈 TradingView 1 h": "📈 TradingView 1 h",
    "📈 TradingView 4 h": "📈 TradingView 4 h",
})
LANG_EN = set()                                   # téléphones qui ont choisi l'anglais
_CLES = sorted(TRAD, key=len, reverse=True)
BOUTONS_FR = ["🤖 Mon bot", "📸 Partager mon gain", "🟠 Analyse BTC", "🥇 Analyse Gold", "✅ Je suis rentré", "🚪 Je suis sorti", "📈 Mes résultats",
              "🧩 Indicateur TradingView", "💎 Devenir VIP", "📡 Mes marchés", "❌ Non"]
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

STATUT_LIB = {"🚦 🙅 PAS DE NOUVELLE POSITION": ("🚦 Statut", "🙅 Pas de nouvelle position"), "🚦 🙅 NO NEW POSITION": ("🚦 Status", "🙅 No new position"),"🚦 🟢 J'ENTRE": ("🚦 Statut", "🟢 J'entre"), "🚦 🙅 JE N'ENTRE PAS": ("🚦 Statut", "🙅 Je n'entre pas"),
              "🚦 ⏳ JE N'ENTRE PAS ENCORE": ("🚦 Statut", "⏳ Je n'entre pas encore"), "🚦 🟢 ON RESTE EN POSITION": ("🚦 Statut", "🟢 On reste en position"),
              "🚦 🟢 I'M ENTERING": ("🚦 Status", "🟢 I'm entering"), "🚦 🙅 I'M NOT ENTERING": ("🚦 Status", "🙅 I'm not entering"),
              "🚦 ⏳ NOT ENTERING YET": ("🚦 Status", "⏳ Not entering yet"), "🚦 🙅 JE NE SUIS PLUS EN POSITION": ("🚦 Statut", "🙅 Je ne suis plus en position"), "🚦 🙅 I'M OUT": ("🚦 Status", "🙅 I'm out"), "🚦 🟢 WE STAY IN": ("🚦 Status", "🟢 We stay in")}

def mise_en_forme(t):
    """Tous les messages rangés pareil : le titre au-dessus, l'info en dessous, une ligne vide entre chaque bloc."""
    if not isinstance(t, str) or not t:
        return t
    # Idempotent : les messages peuvent repasser ici après une première mise en forme.
    t = _normalise_prix_dans_texte(t)
    lignes = t.split("\n")
    titre2 = " — " in lignes[0]
    if titre2:
        g, d_ = lignes[0].split(" — ", 1)
        lignes = [g.strip(), d_.strip()] + lignes[1:]
    plat = []
    for l in lignes:
        l = re.sub(r" {2,}", " ", l.strip())
        # Une ligne ne doit jamais contenir plusieurs informations indépendantes.
        if " • " in l and not l.startswith(("ALIGN •", "📍 RÉCAPITULATIF •")):
            parts = [x.strip() for x in l.split(" • ") if x.strip()]
            if len(parts) > 1:
                plat.extend(parts)
            else:
                plat.append(l)
        elif " | " in l and not l.startswith(("http", "🔗")):
            parts = [x.strip() for x in l.split(" | ") if x.strip()]
            plat.extend(parts if len(parts) > 1 else [l])
        else:
            plat.append(l)
    # Le statut (j'entre / je n'entre pas + TP visé) passe TOUT EN HAUT, juste sous le titre
    i = next((k for k, l in enumerate(plat) if l in STATUT_LIB), None)
    if i is not None and i > 1:
        bloc = [plat[i]] + ([plat[i + 1]] if i + 1 < len(plat) and plat[i + 1].startswith("💰 T") else [])
        reste = plat[:i] + plat[i + len(bloc):]
        tete = 2 if titre2 else 1
        plat = reste[:tete] + bloc + reste[tete:]
    # Titre au-dessus / info en dessous
    out = []
    for k, l in enumerate(plat):
        if not l:
            if out and out[-1]:
                out.append("")
            continue
        if l in STATUT_LIB:
            out += (["", *STATUT_LIB[l], ""] if out and out[-1] else [*STATUT_LIB[l], ""])
            continue
        # Les niveaux chiffrés sont toujours présentés en carte :
        # intitulé, valeur seule, puis explication (mèche / structure / unité de temps).
        niveau = re.match(
            r"^(?P<label>.*?\b(?:TP\s*[12]|SL|STOP(?: LOSS)?|ENTR[ÉE]E?|ENTRY|SORTIE|EXIT|OBJECTIF(?: FINAL)?|TARGET|BREAK EVEN|BE)\b[^:：]*?)"
            r"\s*(?::|：|≈|=)\s*(?P<value>[+-]?(?:\d{1,3}(?:[ \u202f]\d{3})+|\d+)(?:[.,]\d+)?%?)"
            r"(?:\s*(?P<detail>.*))?$", l, re.IGNORECASE)
        if niveau and len(niveau.group("label").strip()) <= 48:
            label = niveau.group("label").strip().rstrip(" :：≈=")
            value = _compacte_prix(niveau.group("value"))
            detail = (niveau.group("detail") or "").strip()
            detail = re.sub(r"^[()\[\]—–,:; ]+|[()\[\] ]+$", "", detail)
            if out and out[-1]:
                out.append("")
            out.append(label)
            out.append(value)
            if detail:
                out.append(detail)
            out.append("")
            continue
        mesure = re.match(
            r"^(?P<label>(?:Basse|Haute|Bas|Haut|Low|High|Support|Résistance|Resistance))\s+"
            r"(?P<value>[+-]?(?:\d{1,3}(?:[ \u202f]\d{3})+|\d+)(?:[.,]\d+)?%?)$",
            l, re.IGNORECASE)
        if mesure:
            if out and out[-1]:
                out.append("")
            value = _compacte_prix(mesure.group("value"))
            out += [mesure.group("label"), value, ""]
            continue
        mt = re.search(r" ?: | ≈ ", l)
        if mt and not l.startswith(("ℹ️", "RSI")):
            g, d_ = l[:mt.start()], l[mt.end():]
            if 2 < len(g) <= 34 and d_.strip():
                if out and out[-1]:
                    out.append("")
                valeur = d_.strip()
                # Ne compacter que les valeurs numériques pures : une durée ou une heure
                # (ex. « 1 h 00 min 05 s », « 04:30:00 ») doit garder ses espaces.
                if re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?%?", valeur):
                    valeur = _compacte_prix(valeur)
                out += [g.strip(), ("≈ " if "≈" in mt.group() else "") + valeur, ""]
                continue
        if l.endswith(" :") or l.endswith(":"):
            l = l.rstrip(" :")
        out.append(l)
    txt = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", txt).strip()

def telegram(methode, **params):
    if methode in ("sendMessage", "editMessageText", "sendPhoto") and str(params.get("chat_id")) in LANG_EN:
        if "text" in params:
            params["text"] = traduire(params["text"])
        if "caption" in params:
            params["caption"] = traduire(params["caption"])
        if params.get("reply_markup"):
            params["reply_markup"] = traduire_clavier(params["reply_markup"])
    if methode in ("sendMessage", "editMessageText", "sendPhoto"):      # traduit d'abord, rangé ensuite
        for k in ("text", "caption"):
            if k in params:
                params[k] = mise_en_forme(params[k])
    url = f"https://api.telegram.org/bot{TOKEN}/{methode}"
    resultat = http_json(url, urllib.parse.urlencode(params).encode())
    if methode in ("sendMessage", "editMessageText", "sendPhoto", "copyMessage") and resultat.get("ok"):
        payload = resultat.get("result") or {}
        texte = params.get("text") or params.get("caption")
        if methode == "copyMessage":
            texte = f"Message copié depuis le message Telegram {params.get('message_id', '?')}"
        JOURNAL_SORTANT.append({
            "direction": "sortant", "timestamp": time.time(),
            "chat_id": str(params.get("chat_id", "")),
            "message_id": payload.get("message_id") or params.get("message_id"),
            "type": methode, "text": str(texte or "")[:4096]
        })
        del JOURNAL_SORTANT[:-JOURNAL_MAX]
    return resultat

# ───────── Boutons et jauge ─────────
CLAVIER = json.dumps({"keyboard": [[{"text": "🟠 Analyse BTC"}, {"text": "🥇 Analyse Gold"}],
                                   [{"text": "🤖 Mon bot"}, {"text": "📈 Mes résultats"}],
                                   [{"text": "📸 Partager mon gain"}, {"text": "🧩 Indicateur TradingView"}],
                                   [{"text": "🌐 English"}]],
                      "resize_keyboard": True, "is_persistent": True, "input_field_placeholder": "Choisis une action ALIGN"})
CLAVIER_VISITEUR = json.dumps({"keyboard": [[{"text": "🟠 Analyse BTC"}, {"text": "🥇 Analyse Gold"}],
                                            [{"text": "💎 Devenir VIP"}],
                                            [{"text": "📸 Partager mon gain"}],
                                            [{"text": "🌐 English"}]],
                               "resize_keyboard": True, "is_persistent": True, "input_field_placeholder": "Choisis une action ALIGN"})
AVERTISSEMENT = ("ℹ️ Ce sont MES positions personnelles, partagées à titre informatif et éducatif. "
                 "Ce n'est pas un conseil en investissement ni une recommandation personnalisée. "
                 "Le trading (CFD, futures, crypto) peut faire perdre tout le capital investi : chacun décide seul et reste responsable de ses choix.")
MINI_AVERT = "ℹ️ Analyse indicative : décision et ordre sous ta responsabilité."
REGLES = ("📌 RÈGLES — ALIGN Signaux\n"
          "━━━━━━━━━━━━\n"
          "1️⃣ Ce sont MES positions perso, ma vision du marché\n"
          "❗ Pas un conseil en investissement\n"
          "2️⃣ Les prix changent selon la plateforme (FTMO, Topstep, broker…)\n"
          "👉 Suis les mèches et les %, pas le prix exact\n"
          "3️⃣ ⏱ Tendance 4h • confirmation 1h • entrée après clôture 5m\n"
          "4️⃣ 🛑 Toujours un SL, derrière la mèche indiquée. Ne jamais l'élargir\n"
          "5️⃣ 📰 Pas de nouvelle entrée 15 min avant/après une news majeure détectée\n"
          "6️⃣ 💰 TP1 touché → stop à l'entrée\n"
          "7️⃣ ⚖️ Risque conseillé : 0,5 à 1 % du compte par position ; jamais sans SL\n"
          "8️⃣ ⚠️ Le trading peut faire perdre tout le capital\n"
          "━━━━━━━━━━━━\n"
          "📰 Je t'envoie les news : pas de trade juste avant ni juste après\n"
          "🤖 Appuie sur ✅ Je suis rentré : ton coach te suit jusqu'au TP\n"
          "📈 Tes gains et tes pertes sont calculés tout seuls\n"
          "🧩 Indicateur TradingView : bouton 🧩 en bas (ne signifie pas que ses signaux sont reçus automatiquement)\n"
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
PAUSE_SEC = int(os.environ.get("PAUSE_SEC", "5"))    # surveillance des setups toutes les 5 s ; les sources de marché restent mises en cache

def marche_demande(txt):
    """Marché demandé : Gold par défaut ; BTC seul si cité ; les deux si BTC et Gold sont cités."""
    t = str(txt or "").lower()
    t = t.replace("é", "e").replace("è", "e").replace("ê", "e")
    btc = "btc" in t or "bitcoin" in t
    gold = "gold" in t or " xau" in t or "xauusd" in t or "or" in t.split()
    if btc and gold:
        return None                 # demande explicite des deux marchés
    if btc:
        return "BTC"
    return "GOLD"                   # demande générale = Gold uniquement

def tendance_armee(r, cle):
    """Une fois 4h + 1h alignées, la tendance reste armée pendant le repli 5m tant que les deux UT ne s'inversent pas."""
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
    try:
        r["macro"] = contexte_macro(etat or {}, m, r)
    except Exception:
        pass
    return r

def boutons_canal(etat, texte):
    """Boutons sous chaque message de la chaîne VIP : ils ouvrent le coach en privé, au bon endroit."""
    bot = etat.get("bot") or "align_mtf_adel_bot"
    m = next((x for x in MARCHES if x in texte.split("\n")[0]), None)
    lien = lambda p: f"https://t.me/{bot}?start={p}"
    lignes = []
    if m and any(k in texte for k in ("JE PRÉPARE", "ÇA ARRIVE", "CASSURE", "PRÉPARE-TOI", "J'ENTRE MAINTENANT", "REPLI", "RETRACE", "parti", "MANIPULATION", "zone")):
        lignes.append([{"text": "🎯 Je rentre dans la prochaine position", "url": lien(f"auto_{m.lower()}")}])
    # Mêmes boutons, même ordre que le clavier du bot ALIGN Coach
    lignes.append([{"text": "🟠 Analyse BTC", "url": lien("analyse_btc")}, {"text": "🥇 Analyse Gold", "url": lien("analyse_gold")}])
    lignes.append([{"text": "✅ Je suis rentré", "url": lien("rentre")}, {"text": "🚪 Je suis sorti", "url": lien("sorti")}])
    lignes.append([{"text": "🤖 Mon bot", "url": lien("mon_bot")}, {"text": "📈 Mes résultats", "url": lien("resultats")}])
    lignes.append([{"text": "📸 Partager mon gain", "url": lien("gain")}, {"text": "🧩 Indicateur TradingView", "url": lien("indicateur")}])
    return json.dumps({"inline_keyboard": lignes})

# ───────── IA (GitHub Models, gratuite avec le jeton GitHub du workflow) ─────────
# IA : Google Gemini (gratuit). GitHub Models a été fermé le 30/07/2026 → clé GEMINI_API_KEY dans les secrets GitHub.
# IA : plusieurs IA GRATUITES à la suite — si l'une tombe, la suivante répond (aucune clé obligatoire).
# 1) Google Gemini (si la clé GEMINI_API_KEY existe)  2) OVHcloud Llama 3.3 70B (sans clé)  3) OVHcloud Mistral (sans clé)
# 4) Pollinations (sans clé)  5) LLM7 (sans clé). Et si TOUT tombe : l'analyse interne du bot répond quand même.
IA_FOURNISSEURS = [
    ("OpenAI", "https://api.openai.com/v1/chat/completions", os.environ.get("OPENAI_MODEL") or "chat-latest", os.environ.get("OPENAI_API_KEY", ""), True),
    ("Gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-flash-latest", os.environ.get("GEMINI_API_KEY", ""), True),
    ("OVH Llama", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions", "Meta-Llama-3_3-70B-Instruct", "", False),
    ("OVH Mistral", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions", "Mistral-Small-3.2-24B-Instruct", "", False),
    ("Pollinations", "https://text.pollinations.ai/openai", "openai", "", False),
    ("LLM7", "https://api.llm7.io/v1/chat/completions", "default", "", False),
]
IA_MAX_JOUR = int(os.environ.get("IA_MAX_JOUR", "300"))
IA_REGLES = ("Tu es l'analyste de marché du bot ALIGN. Tu reçois des données chiffrées réelles calculées par le moteur ; tu dois les interpréter, pas les remplacer. "
             "Architecture : H4 = biais directeur, H1 = confirmation, M15 = structure/retracement, M5 = déclencheur après clôture ; M1 = suivi du prix. "
             "Sépare tendance, scénario privilégié, scénario alternatif, validation, invalidation et prochaine action. "
             "Utilise UNIQUEMENT les données fournies : aucun prix, niveau, indicateur, événement ou horaire inventé. "
             "Ne transforme jamais une probabilité en certitude. N'annonce jamais une entrée avant confirmation. Respecte le verdict interne ALIGN. "
             "Un setup M15/M5 contre H4/H1 est un scalp contre-tendance, jamais un swing. Une mèche seule ne confirme pas une entrée. "
             "Le prochain horaire de clôture fourni est une heure de réévaluation, PAS une promesse d'entrée. "
             "DXY, EUR/USD et US10Y sont du contexte uniquement ; si les données sont absentes ou anciennes, signale-le. "
             "US10Y est une donnée officielle quotidienne, jamais une cotation intraday. Pas de promesse de gain. Langage direct, concret et sans remplissage.")

def _appel_ia(url, modele, cle, messages):
    corps = json.dumps({"model": modele, "temperature": 0.4, "max_tokens": 1000, "messages": messages}).encode()
    h = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "align-bot"}
    if cle:
        h["Authorization"] = f"Bearer {cle}"
    with urllib.request.urlopen(urllib.request.Request(url, data=corps, headers=h), timeout=25) as rep_:
        j = json.loads(rep_.read().decode())
    txt = (j["choices"][0]["message"].get("content") or "").strip()
    if len(txt) < 8:
        raise ValueError("réponse vide")
    return txt

def ia(etat, consigne, donnees, cle_cache=None, duree=600):
    """Commentaire court d'une vraie IA. Essaie chaque IA gratuite à la suite ; '' seulement si toutes sont tombées."""
    cache = etat.setdefault("ia_cache", {})
    if cle_cache and cle_cache in cache and time.time() - cache[cle_cache][0] < duree:
        return cache[cle_cache][1]
    jour = datetime.datetime.now(PARIS).strftime("%Y-%m-%d")
    compte = etat.setdefault("ia_jour", {})
    if compte.get(jour, 0) >= IA_MAX_JOUR:
        etat["ia_dernier_fournisseur"] = "INTERNAL_FALLBACK"
        etat["ia_dernier_modele"] = None
        etat["ia_dernier_statut"] = "DAILY_LIMIT_INTERNAL_FALLBACK"
        print("AI_PROVIDER_USED=INTERNAL_FALLBACK reason=DAILY_LIMIT", flush=True)
        return ""
    messages = [{"role": "system", "content": IA_REGLES},
                {"role": "user", "content": consigne + "\n\nDonnées :\n" + json.dumps(donnees, ensure_ascii=False)}]
    txt, erreurs = "", []
    for nom, url, modele, cle, besoin_cle in IA_FOURNISSEURS:
        if besoin_cle and not cle:
            continue
        if time.time() < etat.get("ia_pause", {}).get(nom, 0):
            continue                                   # IA en panne récemment : on passe à la suivante
        try:
            txt = _appel_ia(url, modele, cle, messages)
            etat.setdefault("ia_ok", {})[nom] = int(time.time())
            etat["ia_dernier_fournisseur"] = nom
            etat["ia_dernier_modele"] = modele
            etat["ia_dernier_statut"] = "CONNECTED"
            print(f"AI_PROVIDER_USED={nom} model={modele}", flush=True)
            break
        except Exception as ex:
            erreurs.append(f"{nom}: {str(ex)[:80]}")
            etat.setdefault("ia_pause", {})[nom] = time.time() + 300   # on la laisse souffler 5 min
            print("ia", nom, ex, flush=True)
    if not txt:
        etat["ia_dernier_fournisseur"] = "INTERNAL_FALLBACK"
        etat["ia_dernier_statut"] = "ALL_EXTERNAL_PROVIDERS_FAILED"
        print("AI_PROVIDER_USED=INTERNAL_FALLBACK", flush=True)
        etat["ia_err"] = " | ".join(erreurs)
        if time.time() - etat.get("ia_err_t", 0) > 21600:        # le propriétaire est prévenu (1 fois / 6 h)
            etat["ia_err_t"] = time.time()
            for pid in proprio(etat):
                try:
                    _envoi_sur(pid, text=f"⚠️ Toutes les IA gratuites sont tombées (l'analyse interne prend le relais)\n{etat['ia_err'][:250]}")
                except Exception:
                    pass
        return ""
    for k in list(compte):
        if k != jour:
            compte.pop(k)
    compte[jour] = compte.get(jour, 0) + 1
    if cle_cache:
        cache[cle_cache] = (time.time(), txt)
        for k in [k for k, v in cache.items() if time.time() - v[0] > 3600]:
            cache.pop(k)
    return txt

def donnees_ia(m, r, cle):
    titre, raison = verdict(r, cle)
    o = (cle or {}).get("ordre") or {}
    data = {"marché": m, "prix": round(r["m1"][-1]["c"], 2),
            "sens 1m/5m/15m/1h/4h/Daily": [r["dirs"][i] for i in (0, 2, 4, 7, 9, 10)],
            "RSI 5m/15m/1h/4h": [round(r["rsis"][i]) for i in (2, 4, 7, 9)],
            "profil_strategie": profil_strategie(r),
            "plan_indicateur_tradingview": plan_indicateur(r),
            "snapshots_indicateur_tradingview": (r.get("tv_indicator_mtf") or {}).get("snapshots", {}),
            "lecture_multi_unites": {"M5": r["dirs"][2], "M15": r["dirs"][4], "H1": r["dirs"][7], "H4": r["dirs"][9]},
            "position Daily (0 bas, 1 haut)": round(r["posD"], 2), "position Weekly": round(r["posW"], 2),
            "verdict du bot": titre + " / " + raison.replace("\n", " "),
            "zone d'entrée": [round(o["za"], 2), round(o["zb"], 2)] if o.get("za") else None,
            "niveau de cassure 5 min": round(niveau_cassure(r, r["confirme"]), 2) if r["confirme"] and len(r["b5"]) >= 22 else None,
            "contexte_macro_dollar": r.get("macro_data") or {}, 
            "news": (r.get("news") or "").replace("\n", " "), "distribution": bool(r.get("distrib")), "accumulation": bool(r.get("accum"))}
    tf = timeframe_attendu(r, cle or {})
    close_ts = prochaine_cloture_bougie(r, tf, time.time())
    data["prochaine_reevaluation"] = {
        "unite_bloquante": tf,
        "heure_locale": datetime.datetime.fromtimestamp(close_ts, PARIS).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "secondes_restantes": max(0, int(close_ts - time.time())),
        "signification": "réévaluation à la clôture, pas une prévision d'entrée"
    }
    return data

def avis_ia(etat, m, r, cle, anglais=False):
    r["macro_data"] = macro_confluence(etat, m, r)
    consigne = (
        "Write in clear English, maximum 8 compact sections: (1) market direction now; (2) H4/H1 primary bias and conflicts; (3) M15 pullback/setup and intended direction; (4) M5 trigger and exact candle-close condition; (5) entry zone, SL and TP only if supplied, otherwise unavailable; (6) invalidation; (7) next review time from the supplied blocking timeframe; (8) what to do now, including when to check again or rest. Never predict an exact entry time or tick count. The next candle close is a review time, not an entry promise. Countertrend M15/M5 is scalp-only. Never override the internal verdict."
        if anglais else
        "Rédige en français clair, 8 rubriques courtes maximum : (1) sens actuel du marché ; (2) biais directeur H4/H1 et conflits ; (3) retracement/setup M15 et direction visée ; (4) déclencheur M5 et condition exacte de clôture ; (5) zone d'entrée, SL et TP uniquement si les données les fournissent ; (6) invalidation ; (7) prochaine heure de réévaluation selon l'unité bloquante ; (8) action maintenant, y compris quand revenir vérifier ou se reposer. Ne prédis jamais une heure exacte d'entrée ni un nombre de ticks. La prochaine clôture est une heure de réévaluation, pas une promesse d'entrée. Un setup M15/M5 contre H4/H1 reste un scalp contre-tendance. Ne contredis jamais le verdict interne."
    )
    langue_cache = "en" if anglais else "fr"
    donnees = donnees_ia(m, r, cle)
    empreinte = dict(donnees)
    reevaluation = dict(empreinte.get("prochaine_reevaluation") or {})
    reevaluation.pop("secondes_restantes", None)
    empreinte["prochaine_reevaluation"] = reevaluation
    signature = hashlib.sha256(json.dumps(empreinte, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    t = ia(etat, consigne, donnees,
           cle_cache=f"analyse_{m}_{langue_cache}_{signature}")
    if t:
        titre = "🧠 ALIGN AI opinion" if anglais else "🧠 L'avis de l'IA ALIGN"
        fournisseur = etat.get("ia_dernier_fournisseur")
        modele = etat.get("ia_dernier_modele")
        # Le fournisseur n'est affiché que si un appel externe réel a abouti.
        if etat.get("ia_dernier_statut") == "CONNECTED" and fournisseur:
            origine = f" • {fournisseur}" + (f" / {modele}" if modele else "")
            titre += origine
        return f"{titre}\n{t}"
    # Toutes les IA en panne : l'analyse interne du bot répond (jamais de silence)
    titre, raison = verdict(r, cle)
    if anglais:
        return "🧠 ALIGN internal analysis\n" + "\n".join(strategie_mtf(r)[-2:]) + f"\n{titre}"
    return "🧠 L'avis ALIGN (analyse interne)\n" + "\n".join(strategie_mtf(r)[-2:]) + f"\n{titre}"

def url_tradingview(m, timeframe):
    """Ouvre le bon instrument et la bonne unité ; ne pilote pas le graphique déjà ouvert."""
    symbole = "KRAKEN:XBTUSD" if m == "BTC" else "FOREXCOM:XAUUSD"
    return "https://www.tradingview.com/chart/?symbol=" + urllib.parse.quote(symbole, safe="") + "&interval=" + str(timeframe)

def bouton_auto(m):
    return json.dumps({"inline_keyboard": [[{"text": "🎯 Suivre la prochaine position", "callback_data": f"auto:{m}"}]]})

def menu_suivi(etat, cid):
    """Demande quels marchés l'utilisateur veut suivre avant l'inscription."""
    anglais = str(cid) in LANG_EN
    texte = ("🎯 CHOOSE THE MARKETS TO FOLLOW\nSelect BTC, GOLD or both. You'll be alerted when an entry is confirmed."
             if anglais else
             "🎯 CHOISIS LES MARCHÉS À SUIVRE\nSélectionne BTC, GOLD ou les deux. Je t'alerterai lorsqu'un point d'entrée sera confirmé.")
    labels = ["🟠 BTC", "🥇 GOLD", "🟠 BTC + 🥇 GOLD"]
    choix = ["BTC", "GOLD", "BOTH"]
    lignes = [[{"text": label, "callback_data": f"followmarket:{market}"}]
              for label, market in zip(labels, choix)]
    _envoi_sur(cid, text=texte, reply_markup=json.dumps({"inline_keyboard": lignes}))

def bouton_rappel(m):
    """Rappelle la bonne analyse de marché, même si un autre marché a envoyé des messages depuis."""
    return json.dumps({"inline_keyboard": [
        [{"text": f"📌 Revoir l'analyse {m}", "callback_data": f"previous:{m}"}],
        [{"text": "🎯 Suivre la prochaine position", "callback_data": f"auto:{m}"}]
    ]})

def markup_analyse(etat, m, r):
    """Clavier progressif : décision, explication, analyse complète et niveaux."""
    cle = etat.get(m, {})
    lignes = [
        [{"text": "❓ Pourquoi cette décision ?", "callback_data": f"why:{m}"},
         {"text": "📊 Analyse complète", "callback_data": f"details:{m}"}],
        [{"text": "🎯 Niveaux / prix", "callback_data": f"levels:{m}"},
         {"text": "⏱ Toutes les unités", "callback_data": f"timeframes:{m}"}],
        [{"text": "🗂 Historique des messages", "callback_data": f"history:{m}"}]
    ]
    if cle.get("trade"):
        lignes.append([{"text": "🟢 Je suis rentré", "callback_data": f"in:{m}"},
                       {"text": "🚪 Je suis sorti", "callback_data": f"out:{m}"}])
    else:
        lignes.append([{"text": "🔔 Suivre la prochaine position", "callback_data": f"auto:{m}"}])
    return json.dumps({"inline_keyboard": lignes})


def markup_position(m):
    return json.dumps({"inline_keyboard": [
        [{"text": "📍 Ma position • SL / TP", "callback_data": f"position:{m}"},
         {"text": "⏱ Toutes les unités", "callback_data": f"timeframes:{m}"}],
        [{"text": "🗂 Historique des messages", "callback_data": f"history:{m}"}],
        [{"text": "⏸ Arrêter mon bot", "callback_data": "botoff:x"}]
    ]})


def markup_cloture(m):
    return json.dumps({"inline_keyboard": [
        [{"text": "📈 Mes résultats", "callback_data": "results:x"},
         {"text": "🗂 Historique", "callback_data": f"history:{m}"}],
        [{"text": "🔔 Suivre le prochain setup", "callback_data": f"auto:{m}"}]
    ]})


def texte_position(m, r, cle, cid):
    """Résumé opérationnel individuel : prix, stop réellement conseillé et objectifs."""
    tr = (cle or {}).get("trade")
    if not tr:
        return f"📍 Aucune position ALIGN ouverte sur {m}.\n🔔 J'attends le prochain signal confirmé."
    pos = tr.get("qui", {}).get(str(cid), {})
    prix = (r or {}).get("m1", [{}])[-1].get("c", tr["e"])
    entree = pos.get("e", tr["e"]) if isinstance(pos, dict) else tr["e"]
    sl = (pos.get("sl_conseil") or pos.get("sl") or tr["sl"]) if isinstance(pos, dict) else tr["sl"]
    tp1 = (pos.get("tp1") or tr["tp1"]) if isinstance(pos, dict) else tr["tp1"]
    tp2 = tr["tp2"]
    sens = "🟩 LONG ⬆️" if tr["d"] == 1 else "🟥 SHORT ⬇️"
    protege = tr["d"] * (sl - entree) >= 0
    gain_pct = tr["d"] * (prix - entree) / max(abs(entree), 1e-9) * 100
    return "\n".join([
        f"📍 TA POSITION — {m}",
        "━━━━━━━━━━━━━━━━━━━━",
        sens,
        f"💹 Prix actuel : {px(prix)}",
        f"📌 Ton entrée : {px(entree)}",
        f"🛑 Ton SL actuel : {px(sl)}",
        f"💰 TP1 : {px(tp1)}",
        f"🏁 TP2 : {px(tp2)}",
        f"📈 Évolution depuis ton entrée : {gain_pct:+.2f} %",
        "━━━━━━━━━━━━━━━━━━━━",
        ("🔒 STOP À BE / GAIN PROTÉGÉ" if protege else "🛡 STOP DE PROTECTION À CONSERVER"),
        ("Le stop est au niveau ou au-delà de ton entrée dans le sens du trade." if protege else
         "Ne retire pas le stop et ne l'élargis pas."),
        "🎯 Le coach surveille les clôtures, le SL, le BE et les objectifs.",
        "ℹ️ ALIGN ne passe aucun ordre sur ton broker : toute modification se fait sur ta plateforme."
    ])


def texte_timeframes(m, r):
    """Lecture pédagogique de toutes les unités réellement calculées par ALIGN."""
    noms = ["1 min", "2 min", "5 min", "10 min", "15 min", "30 min", "45 min",
            "1 heure", "2 heures", "4 heures", "Daily"]
    directions = ["🟩 HAUSSIER ⬆️" if d == 1 else "🟥 BAISSIER ⬇️" if d == -1 else "⬜ NEUTRE ➖"
                  for d in r["dirs"]]
    lignes = [
        f"⏱ TOUTES LES UNITÉS — {m}",
        "━━━━━━━━━━━━━━━━━━━━",
        "Lecture technique : direction + RSI",
        f"Profil proposé : {profil_strategie(r)['mode']} — {profil_strategie(r)['horizon']}",
        f"Préparation M15 : {'alignée' if r['dirs'][4] == profil_strategie(r)['direction'] and profil_strategie(r)['direction'] else 'en attente / retracement'}",
        f"Timing M5 : {'direction alignée ; déclencheur clôturé à vérifier' if profil_strategie(r)['m5_aligne'] else 'attendre la confirmation dans le sens du setup'}",
    ]
    for nom, direction, valeur in zip(noms, directions, r["rsis"]):
        lignes.append(f"{nom} : {direction} • RSI {valeur:.0f}")
    lignes += [
        "━━━━━━━━━━━━━━━━━━━━",
        "🧭 COMMENT ALIGN PREND SA DÉCISION",
        "🏔 4 h : tendance principale",
        "🔁 1 h : confirme ou contredit le biais de fond H4",
        "👀 15 min : préparation, retracement, cassure et retest",
        "🎯 5 min : timing ; clôture, rejet ou retest confirmé obligatoire",
        "⚖️ SCALPING : M15 + M5 • INTRADAY : H1 + M15 + M5 • SWING : H4 + H1 + M15",
        "⚠️ Un setup contre H4/H1 reste un scalp contre-tendance, jamais un swing",
        "📍 1 min : suivi du prix et de la position",
        "ℹ️ 2, 10, 30 et 45 min + 2 h et Daily : confirmations et contexte complémentaires.",
        "⚠️ Une unité haussière ou baissière ne constitue jamais, seule, une autorisation d'entrée."
    ]
    return "\n".join(lignes)


def texte_pourquoi(m, r, cle):
    """Explication courte de la décision, sans transformer le biais en signal d'entrée."""
    titre, raison = verdict(r, cle)
    maj, n_ok = alignement(r)
    direction = "LONG ⬆️" if maj == 1 else "SHORT ⬇️" if maj == -1 else "AUCUNE DIRECTION CONFIRMÉE"
    tr = (cle or {}).get("trade")
    if tr:
        autorisation = "POSITION DÉJÀ OUVERTE"
    elif titre.startswith("🟢 TU PEUX ENTRER"):
        autorisation = "ENTRÉE AUTORISÉE PAR ALIGN"
    elif titre.startswith("⛔ TROP TARD"):
        autorisation = "NE PAS ENTRER — MOUVEMENT DÉJÀ PARTI"
    elif titre.startswith("🟡 PATIENCE"):
        autorisation = "ATTENDRE — PAS ENCORE D'AUTORISATION"
    else:
        autorisation = "NE PAS ENTRER"
    return "\n".join([
        f"❓ POURQUOI ALIGN ? — {m}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🚦 {autorisation}",
        f"🧭 Direction à surveiller : {direction}",
        f"📡 Confirmation 1 h + 4 h : {n_ok}/2",
        "━━━━━━━━━━━━━━━━━━━━",
        "⛔ MOTIF",
        str(raison or "Aucun motif supplémentaire disponible."),
        "━━━━━━━━━━━━━━━━━━━━",
        "➡️ ACTION",
        "Attendre une nouvelle validation explicite d'ALIGN. Le biais LONG/SHORT n'est pas, à lui seul, un ordre d'entrée.",
        "ℹ️ Aucun ordre n'est envoyé au broker."
    ])

def texte_apercu(m, r, cle):
    """Carte d'abordage : autorisation d'entrée en premier, détails derrière les boutons."""
    cle = cle or {}
    maj, n_ok = alignement(r)
    titre, raison = verdict(r, cle)
    prix = r["m1"][-1]["c"]
    tr = cle.get("trade")
    if tr:
        decision = "📍 POSITION EN COURS"
        direction = "LONG ⬆️" if tr["d"] == 1 else "SHORT ⬇️"
    elif titre.startswith("🟢 TU PEUX ENTRER"):
        decision = "🟢 ENTRÉE AUTORISÉE"
        direction = "LONG ⬆️" if maj == 1 else "SHORT ⬇️" if maj == -1 else "À confirmer"
    elif titre.startswith("⛔ TROP TARD"):
        decision = "⛔ NE PAS ENTRER — TROP TARD"
        direction = "LONG ⬆️" if maj == 1 else "SHORT ⬇️" if maj == -1 else "Non confirmée"
    elif titre.startswith("🟡 PATIENCE"):
        decision = "🟡 ATTENDRE — PAS D'ENTRÉE"
        direction = "LONG ⬆️" if maj == 1 else "SHORT ⬇️" if maj == -1 else "Non confirmée"
    else:
        decision = "⛔ NE PAS ENTRER"
        direction = "LONG ⬆️" if maj == 1 else "SHORT ⬇️" if maj == -1 else "AUCUNE DIRECTION CONFIRMÉE"

    lignes = [
        f"{ICONE.get(m, '📊')} ALIGN • {m}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🚦 {decision}",
        f"🧭 Biais à surveiller : {direction}",
        "⚠️ Le biais n'est pas une autorisation d'entrée.",
        "━━━━━━━━━━━━━━━━━━━━",
        "❗ POURQUOI ?",
        str(raison or "Aucune entrée autorisée pour le moment."),
        "━━━━━━━━━━━━━━━━━━━━",
        "➡️ CE QUE TU DOIS FAIRE",
        ("Gérer la position déjà ouverte et suivre les alertes de sortie." if tr else
         "Attendre un nouveau message explicite « ENTRÉE AUTORISÉE »."),
        "━━━━━━━━━━━━━━━━━━━━",
        f"💹 Prix actuel : {px(prix)}",
        f"📡 Confirmation 1 h + 4 h : {n_ok}/2",
    ]
    if cle.get("ordre") and not tr:
        o = cle["ordre"]
        lignes += ["🟨 Zone surveillée (pas un ordre) :",
                   f"{px(o.get('za', o['e']))} → {px(o.get('zb', o['e']))}"]
    if r.get("news"):
        lignes += [f"📰 Actualité : {r['news']}"]
    lignes += [
        "━━━━━━━━━━━━━━━━━━━━",
        "👇 Besoin d'aller plus loin ? Utilise les boutons ci-dessous.",
        "ℹ️ Aucun ordre n'est envoyé automatiquement à ton broker."
    ]
    return "\n".join(lignes)

DERNIERS = {}               # dernière analyse de chaque marché (pour le chrono)
CHRONO_MAX = 4 * 3600        # délai max d'attente d'une position réservée
CHRONO_REFRESH_SEC = 5       # édition du compte à rebours toutes les 5 s pour limiter les rafales Telegram
CHRONO_LOCK = threading.RLock()  # un seul éditeur Telegram par chronomètre, même pendant l'analyse réseau

def prochaine_cloture(ts, interval_sec=300):
    """Retourne la prochaine clôture strictement future (horodatage UTC)."""
    if interval_sec < 1:
        raise ValueError("interval_sec doit être positif")
    return (int(ts) // interval_sec + 1) * interval_sec


def mmss(sec):
    """Affichage compact Telegram : MM:SS, sans texte ni chiffres parasites."""
    total = max(0, int(sec))
    minutes, secondes = divmod(total, 60)
    return f"{minutes:02d}:{secondes:02d}"


TF_SECONDES = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "D": 86400, "W": 604800}
TF_CHAMPS = {"5m": "b5", "15m": "b15", "1h": "b1h", "4h": "b4h", "D": "bd", "W": "bw"}


def prochaine_cloture_bougie(r, tf, now_ts=None):
    """Prochaine clôture alignée sur l'horodatage des bougies réellement reçues."""
    if tf not in TF_SECONDES:
        raise ValueError(f"Unité de temps inconnue : {tf}")
    now_ts = time.time() if now_ts is None else float(now_ts)
    interval = TF_SECONDES[tf]
    bars = r.get(TF_CHAMPS[tf], []) or []
    if not bars:
        return prochaine_cloture(now_ts, interval)
    derniere_ouverture = int(bars[-1]["t"])
    # Le dernier timestamp désigne l'ouverture de la dernière bougie déjà clôturée.
    pas = max(1, int((now_ts - derniere_ouverture) // interval) + 1)
    return derniere_ouverture + pas * interval


def raison_attente(r, cle):
    """Explique en langage utilisateur le vrai blocage, sans jargon ni zone fictive."""
    cle = cle or {}
    tr, o = cle.get("trade"), cle.get("ordre")
    if tr:
        return "Une position est déjà ouverte : le coach surveille le stop et les objectifs."
    if r.get("annonce"):
        return "Une annonce économique approche : aucune nouvelle entrée pendant cette période de risque."
    dirs = r.get("dirs", [0] * 11)
    d4h, d1h = dirs[9], dirs[7]
    if not d4h:
        return "La bougie 4 h ne donne pas de direction nette : le marché est neutre. Aucun LONG ni SHORT n'est proposé."
    sens = "LONG" if d4h == 1 else "SHORT"
    if d1h != d4h:
        etat_1h = "neutre" if not d1h else "dans le sens opposé"
        return f"La tendance 4 h est {sens}, mais la 1 h est {etat_1h}. J'attends une clôture 1 h qui confirme la 4 h."
    d = r.get("confirme") or d4h
    if etire(r, d):
        return f"La tendance {sens} est confirmée, mais le mouvement est déjà trop étendu. Je n'achète/vends pas au prix actuel : j'attends un repli."
    if bloque_dw(r, d, r.get("m1", [{}])[-1].get("c") if r.get("m1") else None):
        return f"La tendance {sens} existe, mais le prix est dans une zone Daily/Weekly extrême. J'attends un meilleur prix ou un retournement confirmé."
    if not o:
        return f"La direction {sens} est confirmée, mais aucun point d'entrée propre n'est encore validé. J'attends que le prix construise un repli exploitable."
    d = o.get("d", d)
    p = r.get("m1", [{}])[-1].get("c") if r.get("m1") else None
    bas, haut = sorted((o.get("za", o["e"]), o.get("zb", o["e"])))
    if p is not None and d == 1 and p > haut:
        return f"Le biais LONG est confirmé. Le prix est à {px(p)}, au-dessus de la zone {px(bas)}–{px(haut)}. Je n'achète pas au prix actuel : j'attends qu'il redescende dans cette zone."
    if p is not None and d == 1 and p < bas:
        return f"Le biais LONG est confirmé, mais le prix est déjà passé sous la zone {px(bas)}–{px(haut)}. Je n'achète pas en retard : j'attends un nouveau point d'entrée."
    if p is not None and d == -1 and p < bas:
        return f"Le biais SHORT est confirmé. Le prix est à {px(p)}, sous la zone {px(bas)}–{px(haut)}. Je ne vends pas au prix actuel : j'attends qu'il remonte dans cette zone."
    if p is not None and d == -1 and p > haut:
        return f"Le biais SHORT est confirmé, mais le prix est déjà passé au-dessus de la zone {px(bas)}–{px(haut)}. Je ne vends pas en retard : j'attends un nouveau point d'entrée."
    if cle.get("traverse"):
        return f"Le prix a traversé la zone {px(bas)}–{px(haut)} sans rejet valide. Pas d'entrée : j'attends une mèche de rejet puis une clôture 5 min dans le sens {sens}."
    return f"Le prix travaille la zone d'entrée {px(bas)}–{px(haut)}, mais je n'ai pas encore de rejet confirmé par une clôture 5 min. Une mèche seule ne suffit pas."


def chrono_txt(m, r, cle, t0):
    """Chronomètre calé sur les bougies reçues et sur l'unité de temps qui bloque réellement."""
    now = time.time()
    p = r["m1"][-1]["c"] if r.get("m1") else r.get("prix", 0)
    tr = cle.get("trade")
    if tr:
        return "\n".join([
            f"⏱ SUIVI EN DIRECT — {ICONE.get(m, '')} {m}  {px(p)}",
            f"🎯 Suivi démarré depuis {mmss(now - t0)}",
            f"🟢 POSITION OUVERTE — {SENS[tr['d']]}",
            statut_txt(1, tr).strip(),
            "🎯 Le coach surveille le SL, le passage à BE et les TP."
        ])
    tf = timeframe_attendu(r, cle)
    cible = prochaine_cloture_bougie(r, tf, now)
    restant = max(0, cible - now)
    d4h = r.get("dirs", [0] * 11)[9]
    d1h = r.get("dirs", [0] * 11)[7]
    if r.get("annonce"):
        direction = "PAUSE — annonce économique proche"
    elif d4h == 0:
        direction = "NEUTRE — aucun sens LONG/SHORT validé"
    elif d1h != d4h:
        direction = f"4 h {('LONG' if d4h == 1 else 'SHORT')} — confirmation 1 h manquante"
    elif r.get("confirme"):
        direction = SENS[r["confirme"]]
    else:
        direction = f"4 h {('LONG' if d4h == 1 else 'SHORT')} — validation complète en attente"
    l = [
        f"⏱ SUIVI EN DIRECT — {ICONE.get(m, '')} {m}  {px(p)}",
        f"🎯 Suivi démarré depuis {mmss(now - t0)}",
        f"🧭 DIRECTION : {direction}",
        f"⏳ POURQUOI J'ATTENDS : {raison_attente(r, cle)}",
    ]
    o = cle.get("ordre")
    if o:
        bas, haut = sorted((o.get("za", o["e"]), o.get("zb", o["e"])))
        l += [
            f"📍 ZONE D'ENTRÉE SURVEILLÉE : {px(bas)} à {px(haut)}",
            f"🛑 Stop calculé : {px(o['sl'])} — {meche_sl(o)}"
        ]
    l += [
        f"⏳ PROCHAINE CLÔTURE {tf}",
        f"⏱ Temps restant : {mmss(restant)}",
        f"🕒 Heure prévue : {datetime.datetime.fromtimestamp(cible, PARIS).strftime('%H:%M:%S')} (heure de Paris)",
        f"⌛ Fin du suivi si aucun setup avant {heure(t0 + CHRONO_MAX)} — aucune entrée forcée",
        f"🔄 Actualisé à {datetime.datetime.fromtimestamp(now, PARIS).strftime('%H:%M:%S')}"
    ]
    return "\n".join(l)

def _editer_chrono_ou_recreer(cid, chrono, texte):
    """Répare un chronomètre dont le message Telegram a été supprimé ou n'est plus éditable."""
    try:
        telegram("editMessageText", chat_id=cid, message_id=chrono["mid"], text=texte)
        return True
    except Exception as ex:
        erreur = str(ex).lower()
        if "message is not modified" in erreur or "message not modified" in erreur:
            return True
        if any(x in erreur for x in ("message to edit not found", "message can't be edited",
                                     "message_id_invalid", "message identifier is not specified")):
            try:
                nouveau = telegram("sendMessage", chat_id=cid, text=texte, disable_notification="true")
                chrono["mid"] = nouveau["result"]["message_id"]
                chrono["maj"] = time.time()
                print("chrono réparé", cid, chrono["mid"])
                return True
            except Exception as remplacement:
                print("chrono remplacement", cid, remplacement)
                return False
        if any(x in erreur for x in ("bot was blocked", "chat not found", "user is deactivated")):
            print("chrono destinataire indisponible", cid, ex)
            return False
        raise


def _maj_chronos_verrouille(etat, m, r):
    """Actualise le compte à rebours et recrée son message si Telegram l'a rendu invalide."""
    ch = etat.setdefault("chrono", {}).setdefault(m, {})
    cle = etat.get(m, {})
    for cid, c in list(ch.items()):
        now = time.time()
        try:
            if cle.get("trade") and c.get("fini") is None:
                c["fini"] = True
                _editer_chrono_ou_recreer(cid, c, chrono_txt(m, r, cle, c["t0"]))
                ch.pop(cid, None)
                continue
            if now - c["t0"] > CHRONO_MAX:
                ch.pop(cid, None)
                suivis_auto = etat.setdefault("auto", {})
                suivis_auto[m] = [x for x in suivis_auto.get(m, []) if str(x) != str(cid)]
                texte = (f"⌛ {ICONE.get(m, '')} {m} : 4 h sans entrée\n"
                         "😎 La position n'est pas venue : pas de mauvaise entrée\n"
                         "🎯 Réappuie sur le bouton pour la prochaine")
                _editer_chrono_ou_recreer(cid, c, texte)
                continue
            if now - c.get("maj", 0) >= CHRONO_REFRESH_SEC:
                c["maj"] = now
                if not _editer_chrono_ou_recreer(cid, c, chrono_txt(m, r, cle, c["t0"])):
                    ch.pop(cid, None)
        except Exception as ex:
            print("chrono", cid, ex)

def maj_chronos(etat, m, r):
    """Sérialise les éditions du chrono entre la boucle principale et le worker indépendant."""
    with CHRONO_LOCK:
        return _maj_chronos_verrouille(etat, m, r)


def _lancer_chrono_verrouille(etat, cid, m, r=None):
    ch = etat.setdefault("chrono", {}).setdefault(m, {})
    if str(cid) in ch:                     # déjà un chrono : on le redescend en bas de la conversation
        try:
            telegram("deleteMessage", chat_id=cid, message_id=ch[str(cid)]["mid"])
        except Exception:
            pass
        t_garde = ch.pop(str(cid))["t0"]
    else:
        t_garde = None
    t0 = t_garde or time.time()
    txt = chrono_txt(m, r, etat.get(m, {}), t0) if r else f"⏱ CHRONO EN DIRECT — {ICONE.get(m, '')} {m}\n🔄 Démarrage…"
    try:
        res = telegram("sendMessage", chat_id=cid, text=txt, disable_notification="true")
        ch[str(cid)] = {"mid": res["result"]["message_id"], "t0": t0, "maj": t0}
    except Exception as ex:
        print("chrono", ex)

def lancer_chrono(etat, cid, m, r=None):
    """Crée le message de suivi sous le même verrou que son rafraîchissement."""
    with CHRONO_LOCK:
        return _lancer_chrono_verrouille(etat, cid, m, r)


def tick_chronos(etat):
    """Un tick indépendant de l'analyse des marchés et des appels aux IA."""
    for marche, derniere in list(DERNIERS.items()):
        try:
            maj_chronos(etat, marche, derniere)
        except Exception as ex:
            print("worker chrono", marche, ex)


def boucle_chronos(etat):
    """Garde les chronomètres Telegram vivants même si un flux de marché ou une IA ralentit."""
    while True:
        tick_chronos(etat)
        time.sleep(1)


def inscrire_auto(etat, cid, m, notifier=True):
    """Active le suivi de la prochaine position sans faire croire qu'un ordre broker est placé."""
    liste = etat.setdefault("auto", {}).setdefault(m, [])
    if cid not in liste:
        liste.append(cid)
    r = (DERNIERS or {}).get(m)
    cle = etat.get(m, {})
    o = cle.get("ordre")
    d = (o or {}).get("d") or cle.get("aligne") or (r or {}).get("confirme") or 0
    decision = raison_attente(r, cle) if r else "J'attends les premières bougies complètes pour établir le contexte."
    direction = SENS[d] if d in SENS else "⚪ NEUTRE — aucun sens confirmé"
    lignes = [
        f"🎯 SUIVI ACTIVÉ — {ICONE.get(m, '')} {m}",
        f"🧭 Direction actuelle : {direction}",
        f"⏳ Décision actuelle : {decision}"
    ]
    if o:
        bas, haut = sorted((o.get("za", o["e"]), o.get("zb", o["e"])))
        lignes += [
            f"📍 Zone d'entrée surveillée : {px(bas)} à {px(haut)}",
            f"🛑 Stop calculé : {px(o['sl'])} — {meche_sl(o)}",
            f"🎯 Objectifs : TP1 {px(o['tp1'])} • TP2 {px(o['tp2'])}",
            "⚠️ Cette zone est un repère, pas un ordre à placer maintenant."
        ]
    else:
        lignes += [
            "📍 Aucune zone d'entrée validée pour le moment.",
            "🙅 Ne place pas d'ordre sur une zone qui n'a pas encore été calculée."
        ]
    lignes += [
        "🔔 Je t'alerterai à la prochaine clôture utile pour débloquer la décision. Toutes les unités restent consultables avec le bouton « Toutes les unités ».",
        "🤖 Si ALIGN déclenche une position, ton suivi interne sera activé automatiquement.",
        "ℹ️ Aucun ordre n'est envoyé à ta plateforme : tu gardes la main sur l'exécution.",
        "🎯 Le coach suit ensuite le SL, le passage à BE et les TP.",
        "⏱ Le chronomètre réel est affiché dans le message juste en dessous."
    ]
    if notifier:
        _envoi_sur(cid, reply_markup=CLAVIER, text="\n".join(lignes))
    if r:
        armer_clotures_multi(etat, cid, m, r)
    lancer_chrono(etat, cid, m, r)

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
    auto = [c for c in chats if bot_on(etat, c) and marche_autorise(etat, c, m) and c not in etat.get("prospects", []) and c != etat.get("canal")]
    for cid in list(dict.fromkeys(etat.get("auto", {}).pop(m, []) + auto)):
        if isinstance(tr.setdefault("qui", {}).get(cid), dict):
            continue
        tr["qui"][cid] = {"e": tr["e"], "sl": tr["sl"], "tp1": tr["tp1"], "d": tr["d"], "t": int(time.time())}
        if cid in etat.get("prospects", []):
            etat.setdefault("bienvenue", {}).setdefault(cid, m)
        stats_bot(etat, cid)["auto"] += 1
        _envoi_sur(cid, reply_markup=markup_position(m), text=(
            f"🤖 {ICONE.get(m, '')} {m} : JE SUIS RENTRÉ, SUIS-MOI\n{SENS[tr['d']]}\n"
            "👀 Mets-toi en vue 15 minutes\n"
            f"🛑 SL un peu {meche_sl(tr)}\n"
            f"📍 Repère prix : entrée ≈ {px(tr['e'])} • SL ≈ {px(tr['sl'])} • TP1 ≈ {px(tr['tp1'])}\n"
            "🛑 Mets ton SL TOUT DE SUITE\n🎯 Coach activé jusqu'au TP\n📈 Résultat compté dans Mes résultats"),
            )

def signature_analyse(m, r, cle):
    """Ce qui compte pour l'utilisateur : verdict, sens, zone. Si rien de tout ça n'a changé, inutile de tout renvoyer."""
    titre, _ = verdict(r, cle)
    o = cle.get("ordre") or {}
    return "|".join([titre, str(r["confirme"]), str(bool(cle.get("trade"))), str(round(o.get("e", 0) / max(r["atr"], 1e-9)))])

def timeframe_attendu(r, cle):
    """Retourne l'unité qui bloque réellement la décision, avant les déclencheurs d'entrée."""
    dirs = r.get("dirs") or []
    d1h = dirs[7] if len(dirs) > 7 else 0
    d4h = dirs[9] if len(dirs) > 9 else 0

    # La tendance 4h est le filtre directeur : si elle est neutre, seule sa clôture
    # peut changer ce constat. Une zone d'entrée existante ne doit pas masquer ce blocage.
    if not d4h:
        return "4h"

    # Tant que la 1h n'est pas dans le même sens que la 4h, la prochaine décision
    # appartient à la clôture 1h, même si un ancien ordre/plan est encore mémorisé.
    if d1h != d4h or not r.get("confirme"):
        return "1h"

    # Une fois le biais 4h + 1h confirmé, les états d'exécution attendent le déclencheur M5.
    if cle.get("trade") or cle.get("ordre") or cle.get("prep") or cle.get("attente_rsi") or cle.get("attente_rejet"):
        return "5m"
    return "15m"


def armer_cloture(etat, cid, m, r, cle):
    """Mémorise la prochaine clôture attendue après une demande explicite d'analyse."""
    tf = timeframe_attendu(r, cle)
    champs = {"5m": "b5", "15m": "b15", "1h": "b1h", "4h": "b4h", "D": "bd", "W": "bw"}
    bars = r.get(champs[tf], [])
    if not bars:
        return
    surveillances = etat.setdefault("veille_cloture", {}).setdefault(m, {})
    existant = surveillances.get(str(cid), {})
    if existant.get("multi"):
        return
    surveillances[str(cid)] = {"tf": tf, "dernier_t": int(bars[-1]["t"]), "restants": 3}


def armer_clotures_multi(etat, cid, m, r):
    """Suit les clôtures 5m, 15m, 1h et 4h pendant la réservation, sans compteur de trois alertes."""
    surveillances = etat.setdefault("veille_cloture", {}).setdefault(m, {})
    derniers = {}
    for tf in ("5m", "15m", "1h", "4h"):
        bars = r.get(TF_CHAMPS[tf], []) or []
        if bars:
            derniers[tf] = int(bars[-1]["t"])
    surveillances[str(cid)] = {
        "multi": True,
        "derniers_t": derniers,
        # Le suivi peut attendre une clôture H4 presque 4 h plus tard.
        # Une marge évite que l'expiration et la clôture soient traitées dans le mauvais ordre.
        "expire": time.time() + CHRONO_MAX + 300,
        "h4_close_grace_v1": True
    }


def synchroniser_veille_auto(etat, m, r):
    """Migre aussi les réservations déjà enregistrées vers le suivi multi-UT."""
    surveillances = etat.setdefault("veille_cloture", {}).setdefault(m, {})
    for cid in list(etat.get("auto", {}).get(m, [])):
        suivi = surveillances.get(str(cid), {})
        if not suivi.get("multi"):
            armer_clotures_multi(etat, cid, m, r)
        elif not suivi.get("h4_close_grace_v1"):
            # Migration unique des suivis déjà actifs : ne pas prolonger leur durée à chaque tour.
            suivi["expire"] = float(suivi.get("expire", time.time())) + 300
            suivi["h4_close_grace_v1"] = True


def texte_cloture(m, tf, bougie, r, cle):
    """Alerte courte : marché/prix d'abord ; détails et historique restent dans les boutons."""
    cle = cle or {}
    duree = TF_SECONDES[tf]
    prix = (r.get("m1") or [bougie])[-1].get("c", bougie["c"])
    titre, _ = verdict(r, cle)
    titre = str(titre).upper()
    dirs = r.get("dirs", [0] * 11)
    d4h = dirs[9] if len(dirs) > 9 else 0
    d1h = dirs[7] if len(dirs) > 7 else 0
    sens = lambda x: "LONG" if x == 1 else "SHORT" if x == -1 else "NEUTRE"
    _, n_ok = alignement(r)
    if cle.get("trade"):
        statut = "🟢 POSITION EN COURS"
    elif "N'ENTRE PAS" in titre or "TROP TARD" in titre or "ATTEND" in titre or "PATIENCE" in titre:
        statut = "🔴 PAS D'ENTRÉE — SIGNAL NON CONFIRMÉ"
    elif "TU PEUX ENTRER" in titre or "J'ENTRE MAINTENANT" in titre:
        statut = "🟢 SIGNAL VALIDÉ — VÉRIFIE LES NIVEAUX"
    else:
        statut = "🟡 EN ATTENTE — PAS D'ENTRÉE"
    bougie_sens = "HAUSSE" if bougie["c"] > bougie["o"] else "BAISSE" if bougie["c"] < bougie["o"] else "NEUTRE"
    lignes = [
        f"{ICONE.get(m, '📊')} {m}  ·  {px(prix)}",
        statut,
        f"🕯 {tf} clôturée {heure(bougie['t'] + duree)} · {bougie_sens} · O {px(bougie['o'])} → C {px(bougie['c'])}",
        f"H4 {sens(d4h)}  ·  H1 {sens(d1h)}  ·  ALIGN {n_ok}/2",
    ]
    profil = profil_strategie(r) if len(dirs) > 9 else {"mode": "ATTENTE", "direction": 0}
    if profil.get("mode") not in ("ATTENTE", None):
        lignes.append(f"🎯 {profil['mode']} {sens(profil.get('direction', 0))}")
    tv_plan = plan_indicateur(r)
    if tv_plan.get("available"):
        sens_tv = "LONG" if tv_plan["direction"] == 1 else "SHORT"
        etat_tv = "snapshot confirmé" if tv_plan.get("confirmed") else "snapshot non confirmé"
        lignes.append(f"📡 PLAN TV {tv_plan.get('timeframe') or '?'} {sens_tv} · E {px(tv_plan['entry'])} · SL {px(tv_plan['sl'])} · TP {px(tv_plan['tp'])} · {etat_tv}")
    tr = cle.get("trade")
    ordre = cle.get("ordre")
    niveau = lambda value: px(value) if value is not None else "—"
    if tr:
        lignes.append(f"📍 Entrée {niveau(tr.get('e'))} · SL {niveau(tr.get('sl'))} · TP1 {niveau(tr.get('tp1'))} · TP2 {niveau(tr.get('tp2'))}")
        lignes.append("👀 Suivi actif : SL / BE / TP")
    elif ordre:
        entree = ordre.get("e", prix)
        bas, haut = sorted((ordre.get("za", entree), ordre.get("zb", entree)))
        lignes.append(f"🟡 Zone {px(bas)}–{px(haut)} · SL {niveau(ordre.get('sl'))} · TP1 {niveau(ordre.get('tp1'))} · TP2 {niveau(ordre.get('tp2'))}")
    else:
        attente = "4h" if not d4h else "1h" if d1h != d4h else "15m" if not r.get("confirme") else "5m"
        lignes.append(f"⏳ Prochaine validation : clôture {attente}")
    if not tr:
        lignes.append("🚫 Aucun ordre envoyé au broker.")
    return "\n".join(lignes)


def notifier_clotures(etat, m, r, cle):
    """Envoie les clôtures nouvelles une fois chacune, sur les UT suivies par l'utilisateur."""
    champs = TF_CHAMPS
    for cid, suivi in list(etat.get("veille_cloture", {}).get(m, {}).items()):
        if not marche_autorise(etat, cid, m):
            etat["veille_cloture"][m].pop(cid, None)
            continue
        if suivi.get("multi"):
            if cle.get("trade") or time.time() >= float(suivi.get("expire", 0)):
                etat["veille_cloture"][m].pop(cid, None)
                continue
            # Une seule UT déclenche la prochaine notification : celle qui bloque réellement la décision.
            # H4 neutre -> attendre H4 ; H4 directionnel/H1 manquant -> H1 ;
            # biais H4+H1 confirmé -> M15 ; ordre/préparation active -> M5.
            tf = timeframe_attendu(r, cle)
            bars = r.get(champs.get(tf, ""), []) or []
            derniers = suivi.setdefault("derniers_t", {})
            nouveaux = [b for b in bars if int(b["t"]) > int(derniers.get(tf, 0))]
            if nouveaux:
                bougie = nouveaux[-1]
                resultat = _envoi_sur(cid, text=texte_cloture(m, tf, bougie, r, cle),
                                     reply_markup=markup_analyse(etat, m, r))
                # Ne consommer la clôture que si Telegram a accepté l'envoi : sinon réessayer au tour suivant.
                if resultat is not None and not (isinstance(resultat, dict) and resultat.get("ok") is False):
                    derniers[tf] = int(bougie["t"])
            continue
        tf = suivi.get("tf")
        bars = r.get(champs.get(tf, ""), []) or []
        if not bars:
            continue
        close = next((b for b in bars if int(b["t"]) > int(suivi.get("dernier_t", 0))), None)
        if not close:
            continue
        resultat = _envoi_sur(cid, text=texte_cloture(m, tf, close, r, cle),
                               reply_markup=markup_analyse(etat, m, r))
        if resultat is None or (isinstance(resultat, dict) and resultat.get("ok") is False):
            continue
        suivi["dernier_t"] = int(close["t"])
        suivi["restants"] = int(suivi.get("restants", 1)) - 1
        if suivi["restants"] <= 0 or cle.get("trade"):
            etat["veille_cloture"][m].pop(cid, None)

def envoyer_analyse_a(etat, cid, m, r, cle):
    """Analyse à la demande ; le rappel est lié au bon marché et au message d'origine."""
    vu = etat.setdefault("vu_analyse", {}).setdefault(m, {})
    sig = signature_analyse(m, r, cle); der = vu.get(str(cid))
    if der and der["sig"] == sig and time.time() - der["t"] < 1200:
        armer_cloture(etat, cid, m, r, cle)
        lignes = chrono_txt(m, r, cle, time.time()).split("\n")
        utile = [l for l in lignes if l.startswith(("1️⃣", "2️⃣", "3️⃣", "4️⃣", "⏸", "⏳", "↩️", "⚡", "🕯 Prochaine"))]
        _envoi_sur(cid, reply_markup=bouton_rappel(m), text="\n".join(
            [f"😎 RIEN N'A BOUGÉ — {ICONE.get(m, '')} {m}   {px(r['m1'][-1]['c'])}",
             f"🕒 Analyse de référence : {heure(der['t'])}",
             "📌 Le bouton ci-dessous réaffiche cette analyse ici, même si d'autres marchés ont parlé depuis."] + utile + [statut_txt(1 if cle.get("trade") else 0, cle.get("trade") or cle.get("ordre")).strip(), "🔔 Je te préviens dès que ça change"]))
        # Même traitement pour BTC et GOLD : une analyse répétée conserve aussi son avis IA.
        avis = avis_ia(etat, m, r, cle, anglais=str(cid) in LANG_EN)
        if avis:
            _envoi_sur(cid, text=avis, reply_markup=CLAVIER)
        return
    vu[str(cid)] = {"sig": sig, "t": time.time()}
    armer_cloture(etat, cid, m, r, cle)
    res = telegram("sendMessage", chat_id=cid, text=texte_apercu(m, r, cle),
                   reply_markup=markup_analyse(etat, m, r))
    try:
        vu[str(cid)]["mid"] = res["result"]["message_id"]
    except (KeyError, TypeError):
        pass
    # L'avis IA reste envoyé séparément : aucune information existante n'est supprimée.
    a_ = avis_ia(etat, m, r, cle, anglais=str(cid) in LANG_EN)
    if a_:
        _envoi_sur(cid, text=a_, reply_markup=CLAVIER)

def envoyer_analyse(cid, etat=None, mq=None):
    for nom_marche, pair in MARCHES.items():
        if mq and mq != nom_marche:
            continue
        try:
            r = analyse_marche(etat, pair)
            envoyer_analyse_a(etat if etat is not None else {}, cid, nom_marche, r, (etat or {}).get(nom_marche) or {})
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
    """Enregistre la clôture réelle et distingue TP/SL et sortie manuelle."""
    pts = pos["d"] * (sortie - pos["e"])
    pct = pts / pos["e"] * 100
    motif_haut = str(motif).upper()
    nature = "TP" if "TP" in motif_haut else "SL" if "SL" in motif_haut or "STOP" in motif_haut else "SORTIE MANUELLE"
    st = etat.setdefault("stats", {}).setdefault(cid, {"tp": 0, "sl": 0, "pts": {}, "pct": 0.0, "hist": []})
    if nature == "TP":
        st["tp"] += 1
    elif nature == "SL":
        st["sl"] += 1
    st["pts"][m] = st["pts"].get(m, 0) + pts
    st["pct"] += pct
    st["hist"] = (st["hist"] + [[m, round(pts, 2), round(pct, 2), motif, int(time.time()), pos["e"], sortie]])[-20:]
    pos["fini"] = True
    resultat = "GAIN" if pts > 0 else "PERTE" if pts < 0 else "ÉGALITÉ"
    titre = f"🏁 CLÔTURE CONFIRMÉE — {nature} — {m}"
    _envoi_sur(cid, reply_markup=markup_cloture(m), text=(
        f"{titre}\n"
        f"{'✅' if pts > 0 else '❌' if pts < 0 else '➖'} Résultat : {resultat}\n"
        f"📌 Entrée : {px(pos['e'])}\n"
        f"🚪 Sortie confirmée : {px(sortie)}\n"
        f"📊 Performance : {pts:+,.2f} pts • {pct:+.2f} %\n".replace(",", " ")
        + f"🧾 Motif : {motif}\n"
        + ("🎉 Objectif positif enregistré." if pts > 0 else "🛡 Risque clôturé. Le prochain signal sera traité séparément." if pts < 0 else "Position clôturée à l’équilibre.")))

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
            + texte_bilan(etat) + "\n━━━━━━━━━━━━\n" + texte_memoire(etat))

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
    CLAVIER = CLAVIER_VISITEUR if cid in etat.get("prospects", []) else globals()["CLAVIER"]
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
            f"🤖 Coach activé jusqu'au TP\n"
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
             "/english": "🌐 English", "/francais": "🌐 Français", "/rentre": "✅ Je suis rentré", "/sorti": "🚪 Je suis sorti",
             "/indicateur": "🧩 Indicateur TradingView"}

def installer_menu(etat):
    """Bouton « Menu » à gauche du champ + description du bot (une seule fois par version)."""
    if etat.get("menu") == 4:
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
        try:
            telegram("setMyName", name="ALIGN Gratuit 🎁 BTC & Gold")
        except Exception as ex:
            print("nom", ex)
        telegram("setMyShortDescription", short_description="🎁 1 position BTC / Gold offerte chaque jour • 💎 Tout le reste dans ALIGN VIP")
        telegram("setMyDescription", description=("🎁 ALIGN Gratuit — BTC & Gold\n\n🎁 1 position offerte chaque jour, expliquée en bougies\n"
                                                  "🔒 Les autres : tu sais qu'elles arrivent, sans le sens\n📰 News et discours Fed gratuits\n\n"
                                                  "💎 ALIGN VIP 49,90 € / mois : toutes les positions, le sens, les niveaux, le coach (BE, TP)\n\n"
                                                  "ℹ️ Mes positions perso, pas un conseil. Le trading comporte un risque de perte."))
        etat["menu"] = 4
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
    legende = f"🔥🔥 GAIN D'UN MEMBRE ALIGN 🔥🔥\n👤 {ph['nom']}\n📈 Positions BTC + Gold\n🎁 1 position offerte chaque jour\n👉 @{etat.get('bot') or 'align_mtf_adel_bot'}"
    cibles = [etat["canal_preuves"]] if etat.get("canal_preuves") else list(etat.get("prospects", []))
    for c in cibles:
        try:
            telegram("sendPhoto", chat_id=c, photo=ph["file"], caption=legende,
                     **({"reply_markup": bouton_payer(etat)} if etat.get("lien") and c != etat.get("canal_preuves") else {}))
        except Exception as ex:
            print("publier gain", ex)
    _envoi_sur(ph["cid"], text="✅ Ton gain est publié 🔥\n🙏 Merci, ça motive tout le monde !")

def publier_resultat(etat, m, tr, sortie, motif, gain):
    """Chaque TP ou SL du bot part aussi dans ALIGN Résultats (transparence), + invitation à partager sa capture."""
    duree = int((time.time() - tr.get("cree", time.time())) // 60)
    nature = "TP ATTEINT" if "TP" in str(motif).upper() or "OBJECTIF" in str(motif).upper() else "STOP TOUCHÉ" if "SL" in str(motif).upper() or "STOP" in str(motif).upper() else "CLÔTURE DU SIGNAL"
    txt = (f"🏁 CLÔTURE CONFIRMÉE — {nature} — {ICONE.get(m, '')} {m}\n"
           f"🚦 {motif}\n{SENS[tr['d']]}\n"
           f"📌 Entrée ≈ {px(tr['e'])}\n🏁 Sortie ≈ {px(sortie)}\n"
           f"📈 Résultat : {gain:+.2f} %\n⏱ Durée : {duree // 60} h {duree % 60:02d}\n"
           + ("📸 Tu étais dedans ? Partage ta capture ici avec le bouton 📸 Partager mon gain" if gain > 0 else "🛡 SL respecté, risque maîtrisé"))
    if etat.get("canal_preuves"):
        try:
            telegram("sendMessage", chat_id=etat["canal_preuves"], text=txt)
        except Exception as ex:
            print("résultat", ex)
    # Le lien du groupe des résultats n'apparaît QUE après un TP ou un SL
    lien = lien_validation(etat)
    kb = json.dumps({"inline_keyboard": [[{"text": "📸 Voir les résultats ALIGN", "url": lien}]]})
    for c, pos in (tr.get("qui") or {}).items():
        if isinstance(pos, dict) and c in etat.get("prospects", []):
            g_ = pos["d"] * (sortie - pos["e"]) / pos["e"] * 100
            pay = bouton_payer(etat) or kb
            _envoi_sur(c, reply_markup=pay, text=(
                f"🎉🎉 BRAVO — {ICONE.get(m, '')} {m}\n💰 Ta position gratuite : {g_:+.2f} %\n🔥 C'est ça, ALIGN\n"
                "😍 Imagine chaque position comme celle-là\n💎 En VIP : toutes les positions + le sens + le coach (BE, TP)\n🔓 VIP 49,90 € / mois 👇"
                if g_ > 0 else
                f"🛡 {ICONE.get(m, '')} {m} : SL touché, risque maîtrisé\n📊 Ça fait partie du jeu : on coupe petit, on gagne gros\n"
                "💎 En VIP : toutes les positions pour se refaire + le coach\n🔓 VIP 49,90 € / mois 👇"))
        elif isinstance(pos, dict):
            kb_fin = json.dumps({"inline_keyboard": [
                [{"text": "📈 Mes résultats", "callback_data": "results:x"},
                 {"text": "🗂 Historique", "callback_data": f"history:{m}"}]
            ]})
            _envoi_sur(c, reply_markup=kb_fin, text=(
                f"🔥 {ICONE.get(m, '')} {m} : bravo !\n📸 N'hésite pas à partager ta capture dans ALIGN Résultats\n👇 Bouton 📸 Partager mon gain"
                if gain > 0 else
                f"🛡 {ICONE.get(m, '')} {m} : SL touché, risque maîtrisé\n📊 Tous les résultats (TP et SL) sont publiés en toute transparence\n👇 Bouton ci-dessous"))

def demande_entree(etat, jr):
    """Quelqu'un demande à rejoindre un groupe / canal ALIGN : c'est TOI qui valides (anti-bots, anti-faux profils)."""
    ch, us = jr["chat"], jr["from"]
    cle_d = f"{ch['id']}_{us['id']}"
    etat.setdefault("demandes_entree", {})[cle_d] = {"chat": ch["id"], "user": us["id"], "t": int(time.time())}
    nom = (us.get("first_name", "") + " " + us.get("last_name", "")).strip() or "?"
    pseudo = f"@{us['username']}" if us.get("username") else "pas de pseudo"
    louche = us.get("is_bot") or not us.get("username")
    txt = (f"🚪 DEMANDE D'ENTRÉE — {ch.get('title', 'groupe ALIGN')}\n👤 Nom : {nom}\n🔖 Pseudo : {pseudo}\n🆔 ID : {us['id']}\n"
           f"🌐 Langue : {us.get('language_code', '?')}\n"
           + ("⚠️ Attention : compte sans pseudo ou robot, vérifie bien" if louche else "✅ Profil normal") + "\n🚦 À toi de décider")
    kb = json.dumps({"inline_keyboard": [[{"text": "✅ Accepter", "callback_data": f"jok:{cle_d}"}, {"text": "❌ Refuser", "callback_data": f"jno:{cle_d}"}],
                                        ] + ([[{"text": "👀 Voir son profil", "url": f"https://t.me/{us['username']}"}]] if us.get("username") else [])})
    for pid in proprio(etat):
        _envoi_sur(pid, text=txt, reply_markup=kb)

def decider_entree(etat, cb, ok, cle_d):
    d = etat.setdefault("demandes_entree", {}).pop(cle_d, None)
    try:
        telegram("answerCallbackQuery", callback_query_id=cb["id"], text="✅ Accepté" if ok else "❌ Refusé")
    except Exception:
        pass
    if not d:
        _envoi_sur(str(cb["message"]["chat"]["id"]), text="ℹ️ Demande déjà traitée"); return
    try:
        telegram("approveChatJoinRequest" if ok else "declineChatJoinRequest", chat_id=d["chat"], user_id=d["user"])
        _envoi_sur(str(cb["message"]["chat"]["id"]), text=("✅ Accepté : il est entré" if ok else "❌ Refusé : il n'entre pas"))
    except Exception as ex:
        _envoi_sur(str(cb["message"]["chat"]["id"]), text=f"⚠️ Impossible : {str(ex)[:120]}")

def lien_validation(etat):
    """Lien d'entrée du groupe ALIGN Résultats AVEC validation (chaque entrée passe par toi)."""
    if etat.get("canal_preuves") and not etat.get("lien_preuves_valid"):
        try:
            res = telegram("createChatInviteLink", chat_id=etat["canal_preuves"], name="ALIGN Résultats (validation)", creates_join_request="true")
            etat["lien_preuves_valid"] = res["result"]["invite_link"]
        except Exception as ex:
            print("lien validation", ex)
    return etat.get("lien_preuves_valid") or etat.get("lien_preuves") or LIEN_RESULTATS

def traiter(etat, chats, updates):
    """Boutons cliqués et messages reçus. Renvoie la liste des téléphones qui demandent une analyse."""
    demandes = []
    for u in updates:
        etat["offset"] = u["update_id"] + 1
        message_recu = (u.get("message") or u.get("edited_message") or
                        u.get("channel_post") or u.get("edited_channel_post") or {})
        callback_recu = u.get("callback_query") or {}
        demande_recue = u.get("chat_join_request") or {}
        statut_recu = u.get("my_chat_member") or {}
        chat_recu = (message_recu.get("chat") or
                     (callback_recu.get("message") or {}).get("chat") or
                     demande_recue.get("chat") or statut_recu.get("chat") or {})
        type_message = next((k for k in ("photo", "document", "video", "voice", "audio",
                                         "sticker", "animation", "video_note", "location",
                                         "contact", "poll", "dice", "venue") if k in message_recu), "message")
        contenu_recu = (message_recu.get("text") or message_recu.get("caption") or
                        callback_recu.get("data") or
                        ("[" + type_message + "]" if message_recu else
                         "Demande d'entrée dans un canal" if demande_recue else
                         "Mise à jour du statut du bot" if statut_recu else ""))
        expediteur = (message_recu.get("from") or callback_recu.get("from") or
                      demande_recue.get("from") or {})
        journal_ajouter(etat, {
            "direction": "entrant", "timestamp": time.time(),
            "update_id": u.get("update_id"), "chat_id": str(chat_recu.get("id", "")),
            "user_id": str(expediteur.get("id", "")),
            "type": "callback" if callback_recu else type_message if message_recu else
                    "chat_join_request" if demande_recue else "my_chat_member" if statut_recu else "update",
            "text": str(contenu_recu or "")[:4096]
        })
        mcm = u.get("my_chat_member")
        if mcm and mcm["chat"].get("type") in ("channel", "supergroup"):
            connecter_canal(etat, mcm)
            continue
        jr = u.get("chat_join_request")
        if jr:
            demande_entree(etat, jr)
            continue
        cb = u.get("callback_query")
        if cb:
            cb_chat = (cb.get("message") or {}).get("chat") or {}
            cb_user = str((cb.get("from") or {}).get("id", ""))
            # Actions du coach uniquement en conversation privée appartenant au demandeur.
            if cb_chat.get("type") != "private" or str(cb_chat.get("id", "")) != cb_user:
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="🔒 Ouvre le bot en conversation privée.")
                except Exception:
                    pass
                continue
            choix, _, mk = cb.get("data", "").partition(":")
            qui = str(cb_chat["id"])
            if choix == "markets" and mk in ("BTC", "GOLD", "BOTH"):
                selectionner_marches_suivi(etat, qui, mk)
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="✅ Sélection enregistrée")
                except Exception:
                    pass
                menu_marches(etat, qui)
                continue
            if choix == "followmarket" and mk in ("BTC", "GOLD", "BOTH"):
                if not (autorise(etat, qui, cb.get("from", {}).get("id")) or qui not in etat.get("bienvenue", {})):
                    try:
                        telegram("answerCallbackQuery", callback_query_id=cb["id"], text="🔒 Réservé aux VIP")
                    except Exception:
                        pass
                    _envoi_sur(qui, text="🔒 Réservé aux VIP\\n🎁 Ta position gratuite du jour est déjà utilisée\\n💎 VIP 49,90 € / mois 👇",
                               **({"reply_markup": bouton_payer(etat)} if etat.get("lien") else {}))
                    continue
                # La sélection explicite est aussi la préférence de distribution privée.
                # Supprimer les anciennes réservations en attente sur l'autre marché évite
                # qu'un ancien abonnement BTC survive à un nouveau choix GOLD (et inversement).
                selectionner_marches_suivi(etat, qui, mk)
                marches = ("BTC", "GOLD") if mk == "BOTH" else (mk,)
                for marche in marches:
                    inscrire_auto(etat, qui, marche, notifier=False)
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="✅ Suivi activé")
                except Exception:
                    pass
                noms = "BTC + GOLD" if mk == "BOTH" else mk
                _envoi_sur(qui, text=(f"✅ FOLLOW ACTIVATED: {noms}\nI'll alert you when an entry is confirmed."
                                      if qui in LANG_EN else
                                      f"✅ SUIVI ACTIVÉ : {noms}\nJe t'alerterai lorsqu'un point d'entrée sera confirmé."))
                continue
            if choix == "results":
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="📈 Tes résultats")
                except Exception:
                    pass
                _envoi_sur(qui, text=texte_resultats(etat, qui))
                continue
            if choix == "history":
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="🗂 Historique")
                except Exception:
                    pass
                morceaux = mk.split(":")
                marche = morceaux[0] if morceaux and morceaux[0] in MARCHES else None
                try:
                    offset = max(0, int(morceaux[1])) if len(morceaux) > 1 else 0
                except (TypeError, ValueError):
                    offset = 0
                total = sum(1 for x in etat.get("journal_telegram", []) if str(x.get("chat_id")) == qui)
                boutons = []
                if offset > 0:
                    boutons.append([{"text": "⬅️ Plus récents", "callback_data": f"history:{marche or 'x'}:{max(0, offset - 8)}"}])
                if offset + 8 < total:
                    boutons.append([{"text": "Plus anciens ➡️", "callback_data": f"history:{marche or 'x'}:{offset + 8}"}])
                if marche:
                    boutons.append([{"text": "↩️ Retour à l'analyse", "callback_data": f"resume:{marche}"}])
                _envoi_sur(qui, text=texte_historique(etat, qui, limite=8, offset=offset),
                           reply_markup=json.dumps({"inline_keyboard": boutons}) if boutons else None)
                continue
            if choix == "previous" and mk in MARCHES:
                if not autorise(etat, qui, cb.get("from", {}).get("id")):
                    try:
                        telegram("answerCallbackQuery", callback_query_id=cb["id"], text="🔒 Analyse réservée aux VIP")
                    except Exception:
                        pass
                    _envoi_sur(qui, text="🔒 Le rappel de l'analyse complète est réservé aux VIP.",
                               **({"reply_markup": bouton_payer(etat)} if etat.get("lien") else {"reply_markup": CLAVIER_VISITEUR}))
                    continue
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text=f"📌 Analyse {mk}")
                except Exception:
                    pass
                reference = etat.get("vu_analyse", {}).get(mk, {}).get(qui, {})
                mid = reference.get("mid")
                if mid:
                    try:
                        telegram("copyMessage", chat_id=qui, from_chat_id=qui, message_id=mid)
                    except Exception as ex:
                        print("rappel analyse", qui, mk, ex)
                        r_ref = DERNIERS.get(mk)
                        if r_ref:
                            _envoi_sur(qui, text=texte_apercu(mk, r_ref, etat.get(mk, {})),
                                      reply_markup=markup_analyse(etat, mk, r_ref))
                        else:
                            _envoi_sur(qui, text=f"⚠️ L'analyse {mk} n'est plus disponible. Relance l'analyse du marché.")
                else:
                    r_ref = DERNIERS.get(mk)
                    if r_ref:
                        res = _envoi_sur(qui, text=texte_apercu(mk, r_ref, etat.get(mk, {})),
                                         reply_markup=markup_analyse(etat, mk, r_ref))
                        if res and res.get("ok"):
                            etat.setdefault("vu_analyse", {}).setdefault(mk, {}).setdefault(qui, {})["mid"] = res["result"]["message_id"]
                    else:
                        _envoi_sur(qui, text=f"⚠️ L'analyse {mk} n'est pas encore disponible. Appuie sur Analyse {mk}.")
                continue
            if choix in ("why", "details", "rawdetails", "levels", "timeframes", "position") and mk in MARCHES:
                if not autorise(etat, qui, cb.get("from", {}).get("id")):
                    try:
                        telegram("answerCallbackQuery", callback_query_id=cb["id"], text="🔒 Détails réservés aux VIP")
                    except Exception:
                        pass
                    _envoi_sur(qui, text="🔒 Les détails complets et les niveaux sont réservés aux VIP.",
                               **({"reply_markup": bouton_payer(etat)} if etat.get("lien") else {"reply_markup": CLAVIER_VISITEUR}))
                    continue
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="📊 Informations")
                except Exception:
                    pass
                r_detail = DERNIERS.get(mk)
                if r_detail is None:
                    try:
                        r_detail = analyse_marche(etat, MARCHES[mk])
                    except Exception as ex:
                        print("détails analyse", ex)
                        _envoi_sur(qui, text="⚠️ Les détails sont momentanément indisponibles. Réessaie avec le bouton Analyse.")
                        continue
                cle_detail = etat.get(mk, {})
                if choix == "position":
                    _envoi_sur(qui, text=texte_position(mk, r_detail, cle_detail, qui),
                               reply_markup=markup_position(mk))
                elif choix == "why":
                    _envoi_sur(qui, text=texte_pourquoi(mk, r_detail, cle_detail),
                               reply_markup=json.dumps({"inline_keyboard": [[{"text": "📊 Analyse complète", "callback_data": f"details:{mk}"},
                                                                             {"text": "🎯 Niveaux / prix", "callback_data": f"levels:{mk}"}],
                                                                            [{"text": "↩️ Retour à l'analyse", "callback_data": f"resume:{mk}"}]]}))
                elif choix == "rawdetails":
                    _envoi_sur(qui, text=texte_etat(mk, r_detail, cle_detail, vip=True),
                               reply_markup=json.dumps({"inline_keyboard": [[{"text": "↩️ Retour à l'analyse", "callback_data": f"resume:{mk}"}]]}))
                elif choix == "timeframes":
                    _envoi_sur(qui, text=texte_timeframes(mk, r_detail),
                               reply_markup=json.dumps({"inline_keyboard": [[{"text": "❓ Pourquoi cette décision ?", "callback_data": f"why:{mk}"},
                                                                             {"text": "↩️ Retour à l'analyse", "callback_data": f"resume:{mk}"}]]}))
                elif choix == "details":
                    rapport = avis_ia(etat, mk, r_detail, cle_detail, anglais=str(qui) in LANG_EN)
                    _envoi_sur(qui, text=rapport,
                               reply_markup=json.dumps({"inline_keyboard": [[{"text": "🎯 Voir les niveaux", "callback_data": f"levels:{mk}"}],
                                                                                 [{"text": "📊 Données techniques complètes", "callback_data": f"rawdetails:{mk}"}],
                                                                                 [{"text": "↩️ Retour à l'analyse", "callback_data": f"resume:{mk}"}]]}))
                else:
                    tr_detail = cle_detail.get("trade")
                    if tr_detail:
                        txt_niveaux = fmt_trade(mk, tr_detail, r_detail["m1"][-1]["c"])
                    elif cle_detail.get("ordre"):
                        txt_niveaux = ("🟨 ZONE DE PRÉPARATION\n" + statut_txt(0, cle_detail["ordre"]).strip()
                                       + "\n⏳ Aucun déclenchement confirmé : attendre la clôture prévue.")
                    else:
                        txt_niveaux = ("📊 NIVEAUX ALIGN\n⏳ Aucun plan d'entrée confirmé pour le moment.\n"
                                       "Le bot attend les confirmations de sa stratégie avant de publier des niveaux.")
                    _envoi_sur(qui, text=txt_niveaux,
                               reply_markup=json.dumps({"inline_keyboard": [[{"text": "ℹ️ Comprendre l'analyse", "callback_data": f"details:{mk}"},
                                                                             {"text": "↩️ Retour à l'analyse", "callback_data": f"resume:{mk}"}]]}))
                continue
            if choix == "resume" and mk in MARCHES:
                if not autorise(etat, qui, cb.get("from", {}).get("id")):
                    try:
                        telegram("answerCallbackQuery", callback_query_id=cb["id"], text="🔒 Réservé aux VIP")
                    except Exception:
                        pass
                    continue
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="Analyse")
                except Exception:
                    pass
                r_resume = DERNIERS.get(mk)
                if r_resume is None:
                    try:
                        r_resume = analyse_marche(etat, MARCHES[mk])
                    except Exception as ex:
                        print("retour analyse", mk, ex)
                        _envoi_sur(qui, text="⚠️ L'analyse n'est pas disponible pour le moment. Réessaie avec le bouton Analyse.")
                        continue
                _envoi_sur(qui, text=texte_apercu(mk, r_resume, etat.get(mk, {})),
                           reply_markup=markup_analyse(etat, mk, r_resume))
                continue
            if choix in ("jok", "jno") and qui in proprio(etat):
                decider_entree(etat, cb, choix == "jok", mk)
                continue
            if choix in ("tvoffre", "tvok") and qui in proprio(etat):
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="OK")
                except Exception:
                    pass
                if choix == "tvoffre":
                    offerts = etat.setdefault("indic_offert", [])
                    if mk not in offerts:
                        offerts.append(mk)
                    _envoi_sur(mk, text="🎁 L'indicateur t'est offert !\n👉 Appuie sur 🧩 Indicateur TradingView", reply_markup=CLAVIER)
                    _envoi_sur(qui, text="✅ Indicateur offert. J'attends son pseudo TradingView.")
                else:
                    info = etat.setdefault("indic", {}).setdefault(mk, {})
                    if not info.get("tv"):
                        _envoi_sur(qui, text="⚠️ Aucun pseudo TradingView enregistré pour cet utilisateur.")
                        continue
                    info["ok"] = True
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
            if choix == "auto" and mk in MARCHES:
                # Le marché est déjà connu depuis le bouton de l'analyse : activation en un seul appui.
                if autorise(etat, qui, cb["from"]["id"]) or qui not in etat.get("bienvenue", {}):
                    selectionner_marches_suivi(etat, qui, mk)
                    inscrire_auto(etat, qui, mk, notifier=False)
                    try:
                        telegram("answerCallbackQuery", callback_query_id=cb["id"], text="🔔 Suivi activé pour " + mk)
                    except Exception:
                        pass
                    _envoi_sur(qui, text=(f"🔔 SUIVI ACTIVÉ : {mk}\\nJe t'alerterai dès qu'une entrée sera confirmée."
                                          if qui not in LANG_EN else
                                          f"🔔 FOLLOWING {mk}\\nI'll alert you when an entry is confirmed."))
                else:
                    try:
                        telegram("answerCallbackQuery", callback_query_id=cb["id"], text="🔒 Réservé aux VIP")
                    except Exception:
                        pass
                    _envoi_sur(qui, text="🔒 Réservé aux VIP\\n🎁 Ta position gratuite du jour est déjà utilisée\\n⏰ Une nouvelle demain\\n💎 VIP 49,90 € / mois 👇",
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
                if choix == "offrir":
                    if mk in off:
                        _envoi_sur(qui, text=f"ℹ️ {etat.get('noms', {}).get(mk, mk)} possède déjà l'accès offert.")
                        continue
                    off.append(mk); chats.add(mk)
                    if mk in etat.get("prospects", []):
                        etat["prospects"].remove(mk)
                    _envoi_sur(mk, text="🎁 Accès VIP offert !\n✅ Tu reçois maintenant toutes mes positions\n⬇️ Utilise les boutons en bas\n\n" + AVERTISSEMENT, reply_markup=CLAVIER)
                    _envoi_sur(qui, text=f"✅ Accès VIP offert à {etat.get('noms', {}).get(mk, mk)}",
                               reply_markup=json.dumps({"inline_keyboard": [[{"text": "⛔ Retirer l'accès", "callback_data": f"retirer:{mk}"}]]}))
                elif choix == "retirer":
                    if mk not in off:
                        _envoi_sur(qui, text=f"ℹ️ {etat.get('noms', {}).get(mk, mk)} n'a pas d'accès offert actif.")
                        continue
                    off.remove(mk); chats.discard(mk)
                    _envoi_sur(qui, text=f"⛔ Accès retiré à {etat.get('noms', {}).get(mk, mk)}")
                continue
            # Ne jamais interpréter un callback inconnu comme une sortie manuelle.
            # Seuls les boutons explicites in:<marché> et out:<marché> peuvent modifier une position.
            if choix not in ("in", "out") or mk not in MARCHES:
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="Action inconnue ou expirée")
                except Exception:
                    pass
                continue
            bienvenue = etat.get("bienvenue", {}).get(qui) == mk and etat.get(mk, {}).get("trade")
            if not bienvenue and not autorise(etat, qui, cb["from"]["id"]):
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="🔒 Réservé aux VIP")
                except Exception:
                    pass
                _envoi_sur(qui, text="🔒 Cette position est réservée aux VIP\n" + ("🎁 Ta position gratuite du jour est déjà utilisée\n⏰ Une nouvelle demain\n" if qui in etat.get("bienvenue", {}) else "🎁 Ta position gratuite arrive avec le prochain signal\n") + "💎 VIP 49,90 € / mois 👇",
                           **({"reply_markup": bouton_payer(etat)} if etat.get("lien") else {"reply_markup": CLAVIER_VISITEUR}))
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
            # Inscription silencieuse : aucun message d'activation n'est envoyé.
            chats.add(cid)
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
        if "mes marches" in txt or "my markets" in txt or txt.startswith("/marches"):
            menu_marches(etat, cid)
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
        # Pas de conversation libre : seuls les boutons et retours explicitement sollicités
        # (photo de gain ou pseudo TradingView après demande) sont traités.
        # Tout texte libre est ignoré, pour les visiteurs comme pour les abonnés.
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
    return json.dumps({"inline_keyboard": [[{"text": "👀 Voir plus", "url": lien}], [{"text": "🔓 Débloquer les positions (49,90 € / mois)", "url": lien}]]}) if lien else None

def analyse_visiteur(etat, cid, mq=None):
    """Visiteur : jamais le sens ni les niveaux. Juste l'état (position en cours / en préparation) + bouton VIP."""
    kw = {"reply_markup": bouton_payer(etat)} if etat.get("lien") else {"reply_markup": CLAVIER_VISITEUR}
    for nom_marche, pair in MARCHES.items():
        if mq and mq != nom_marche:
            continue
        try:
            r = analyse_marche(etat, pair); cle = etat.get(nom_marche, {})
            _envoi_sur(cid, text=texte_etat(nom_marche, r, cle, vip=False), **kw)
        except Exception as ex:
            print("analyse visiteur", ex)

def refuser(etat, cid):
    _envoi_sur(cid, text="👋 ALIGN Signaux — BTC + Gold\n⬆️⬇️ Les positions arrivent ici en direct", reply_markup=CLAVIER_VISITEUR)
    kw = {"reply_markup": bouton_payer(etat)} if etat.get("lien") else {}
    _envoi_sur(cid, text=("👋 Bienvenue sur ALIGN Gratuit 🎁 (BTC + Gold)\n\n"
                          "🎁 1 POSITION OFFERTE CHAQUE JOUR\n"
                          "🕯 Expliquée en bougies (vue 15 min) + coach jusqu'au TP\n"
                          "📰 Alertes news et discours gratuites\n"
                          "🔔 Ouvertures de marché gratuites\n\n"
                          "🔒 Ensuite : tu sais qu'une position arrive, mais sans le sens ni les niveaux\n"
                          "💎 VIP 49,90 € / mois : toutes les positions + le coach en direct\n"
                          "👉 Bouton ci-dessous : tu paies et tu entres directement dans le canal ALIGN VIP 💎\n\n" + AVERTISSEMENT), **kw)

def masquer(texte):
    """Cache tous les prix (entrée, stop, TP) pour les visiteurs non abonnés."""
    texte = re.sub(r"[+-]\d+,\d+ %", "🔒 %", texte)
    return re.sub(r"(?<!\w)\d{1,3}(?: \d{3})*\.\d+", "🔒🔒🔒", texte).replace("\n\nTu es rentré ?", "")

def envoyer_prospects(etat, texte, signal, clavier=None):
    """Visiteurs : news en clair ; UNE position de bienvenue complète (bougies + coach) ;
    ensuite tout est caché, avec des messages courts « tu loupes ça » et le bouton VIP."""
    entree = signal and "J'ENTRE MAINTENANT" in texte
    kw = {"reply_markup": bouton_payer(etat)} if etat.get("lien") else {}
    jour = datetime.datetime.now(PARIS).strftime("%Y-%m-%d")
    if etat.get("offerte_jour") != jour:           # 1 position GRATUITE par jour : on remet les compteurs à zéro
        etat["bienvenue"] = {c: mk for c, mk in etat.get("bienvenue", {}).items() if etat.get(mk, {}).get("trade")}
        etat["offerte_jour"] = jour
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
    elif m and ("ÇA ARRIVE" in tete or "POINT D'ENTRÉE À VENIR" in tete or "CASSURE EN VUE" in tete or "PRÉPARE-TOI" in tete or "RETRACE" in tete or "REPLI EST LÀ" in tete):
        fomo = f"👀 {ICONE.get(m, '')} {m} : une position VIP arrive 🔥\n🔒 Zone cachée\n😬 Tu vas la louper ?\n💎 VIP 👇"
    for cid in list(etat.get("prospects", [])):
        if m and not marche_autorise(etat, cid, m):
            continue
        sa_bienvenue = m and deja.get(cid) == m and tr is not None
        if signal and cid not in deja:
            txt = ("🎁🎁 TA POSITION GRATUITE DU JOUR 🎁🎁\n"
                   "👀 Suis-la en vue 15 minutes, tout est expliqué en bougies\n\n" + texte)
            k = {"reply_markup": clavier} if (entree and clavier) else {}
            if entree:
                deja[cid] = m
                txt += "\n\n💎 C'est ta position gratuite du jour. Toutes les autres + le coach : VIP 49,90 € / mois"
        elif sa_bienvenue and not signal:
            txt, k = texte, {}          # sa position offerte est en cours : il suit tout en clair
        elif signal:
            txt = (f"🔒 {ICONE.get(m, '')} {m} : les VIP viennent de recevoir une position\n"
                   + ("🟩 LONG ⬆️ ou 🟥 SHORT ⬇️ ? 🤫\n" if entree else "👀 Elle se prépare 🤫\n")
                   + "😬 Tu vas louper ce move ?\n💎 VIP 49,90 € / mois : toutes les positions + le coach 👇")
            k = kw
        elif fomo:
            txt, k = fomo, kw
        elif news:
            txt, k = texte, {}
        else:
            # Jamais le sens ni les niveaux : un simple teaser, 1 fois / 30 min / marché
            tz = etat.setdefault("teaser_t", {})
            cle_t = f"{cid}_{m}"
            if not m or time.time() - tz.get(cle_t, 0) < 1800:
                continue
            tz[cle_t] = time.time()
            txt, k = (f"🔒 {ICONE.get(m, '')} {m}\nNouvelle info pour les VIP\n🤫 Sens et niveaux cachés\n💎 VIP 49,90 € / mois 👇"), kw
        try:
            telegram("sendMessage", chat_id=cid, text=txt, **k)
        except Exception as ex:
            print("prospect", cid, ex)
            if "403" in str(ex):
                etat["prospects"].remove(cid)

def _envoi_sur(cid, **kw):
    try:
        return telegram("sendMessage", chat_id=cid, **kw)
    except Exception as ex:
        print("envoi", cid, ex)
        return None

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

def selectionner_marches_suivi(etat, cid, choix):
    """Enregistre le choix explicite et retire uniquement les suivis en attente des autres marchés."""
    cid = str(cid)
    if choix not in ("BTC", "GOLD", "BOTH"):
        raise ValueError("Marché de suivi invalide")
    etat.setdefault("marches_par_chat", {})[cid] = choix
    autorises = {"BTC", "GOLD"} if choix == "BOTH" else {choix}
    for marche in MARCHES:
        if marche in autorises:
            continue
        attente = etat.setdefault("auto", {}).setdefault(marche, [])
        etat["auto"][marche] = [x for x in attente if str(x) != cid]
        veilles = etat.setdefault("veille_cloture", {}).setdefault(marche, {})
        veilles.pop(cid, None)


def marche_selection(etat, cid):
    """Préférence personnelle persistante ; les anciens abonnés gardent les deux marchés."""
    choix = etat.setdefault("marches_par_chat", {}).get(str(cid), "BOTH")
    return choix if choix in ("BTC", "GOLD", "BOTH") else "BOTH"

def marche_autorise(etat, cid, marche):
    choix = marche_selection(etat, cid)
    return choix == "BOTH" or choix == marche

def menu_marches(etat, cid):
    choix = marche_selection(etat, cid)
    anglais = str(cid) in LANG_EN
    labels = ({
        "BTC": "🟠 BTC only",
        "GOLD": "🥇 GOLD only",
        "BOTH": "🟠 BTC + 🥇 GOLD",
    } if anglais else {
        "BTC": "🟠 BTC uniquement",
        "GOLD": "🥇 GOLD uniquement",
        "BOTH": "🟠 BTC + 🥇 GOLD",
    })
    lignes = [[{"text": ("✅ " if choix == "BTC" else "") + labels["BTC"], "callback_data": "markets:BTC"}],
              [{"text": ("✅ " if choix == "GOLD" else "") + labels["GOLD"], "callback_data": "markets:GOLD"}],
              [{"text": ("✅ " if choix == "BOTH" else "") + labels["BOTH"], "callback_data": "markets:BOTH"}]]
    texte = ("📡 CHOOSE THE MARKETS YOU WANT TO FOLLOW\n\nPrivate analyses and alerts will follow your choice.\nAlready-open positions will continue to be monitored until they close."
             if anglais else
             "📡 CHOISIS LES MARCHÉS QUE TU SOUHAITES SUIVRE\n\nLes analyses et alertes privées seront filtrées selon ton choix.\nLes positions déjà ouvertes restent suivies jusqu'à leur clôture.")
    _envoi_sur(cid, text=texte, reply_markup=json.dumps({"inline_keyboard": lignes}))

def marche_du_message(texte):
    """Détecte le marché dans l'en-tête d'une notification ; les messages macro mixtes exigent BOTH."""
    tete = " ".join(str(texte or "").splitlines()[:3]).upper()
    btc = bool(re.search(r"\bBTC\b|BITCOIN", tete))
    gold = bool(re.search(r"\bGOLD\b|XAUUSD", tete))
    if btc and gold:
        return "BOTH"
    if btc:
        return "BTC"
    if gold:
        return "GOLD"
    return None

def destinataires_message(etat, chats, texte):
    marche = marche_du_message(texte)
    cibles = [str(c) for c in chats if marche is None or (marche == "BOTH" and marche_selection(etat, c) == "BOTH") or
              (marche in ("BTC", "GOLD") and marche_autorise(etat, c, marche))]
    # La chaîne VIP reste commune et reçoit les deux marchés, sans préférence individuelle.
    if etat.get("canal"):
        cibles.append(str(etat["canal"]))
    return list(dict.fromkeys(cibles))

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
    if not cle.get("ordre") and bloque_dw(r, d, zone_repli(r, d)["e"]):
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

def maj_jauge(etat, m, r, cle, chats, canal=None):
    for cid in list(chats) + ([canal] if canal else []):
        if cid != canal and not marche_autorise(etat, cid, m):
            mid = cle.get("jauge", {}).pop(cid, None)
            cle.get("jauge_txt", {}).pop(cid, None)
            if mid:
                try: telegram("deleteMessage", chat_id=cid, message_id=mid)
                except Exception: pass
            continue
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

def meche_sl(o):
    """Quelle mèche regarder pour le SL : la bougie précise (unité de temps + heure de Paris, comme sur TradingView)."""
    d = o.get("d", 1); h = o.get("sl_h")
    if not h:
        return "SOUS la mèche du dernier creux" if d == 1 else "AU-DESSUS de la mèche du dernier sommet"
    return (f"SOUS la mèche basse • bougie {o.get('sl_ut', '15 min')} de {h}" if d == 1 else
            f"AU-DESSUS de la mèche haute • bougie {o.get('sl_ut', '15 min')} de {h}")

def bougie_protegee(b, d, sl):
    """La bougie dont la mèche est protégée par le SL : le plus bas (LONG) / plus haut (SHORT) juste devant le SL."""
    if d == 1:
        c = [x for x in b if x["l"] >= sl] or b
        x = min(c, key=lambda y: y["l"])
    else:
        c = [x for x in b if x["h"] <= sl] or b
        x = max(c, key=lambda y: y["h"])
    return heure(x["t"])

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
        if 55 * 60 < reste <= 60 * 60 and f"ev60{e['t']}{e['titre']}" not in vus:
            vus.append(f"ev60{e['t']}{e['titre']}")
            out.append(f"📰 NEWS USA DANS 1 H — {heure(e['t'])}\n🗞 {e['titre']}\n🚦 ⏳ JE N'ENTRE PAS ENCORE\n"
                       f"🛑 Pas de nouvelle position à partir de {heure(e['t'] - 15 * 60)}\n🔒 En position ? Mets-toi à BE si tu es en gain\n"
                       f"📊 Prévu : {e.get('prev') or '?'} • avant : {e.get('avant') or '?'}")
        if 35 * 60 < reste <= 40 * 60 and f"ev40{e['t']}{e['titre']}" not in vus:
            vus.append(f"ev40{e['t']}{e['titre']}")
            out.append(f"⚠️ NEWS USA DANS 40 MIN — {heure(e['t'])}\n📰 {e['titre']}\n🛡 Évite toute nouvelle entrée à l’approche de l’annonce. Vérifie ton SL si tu es déjà en position.")
        if 5 * 60 <= -reste <= 8 * 60 and f"evr{e['t']}{e['titre']}" not in vus:
            vus.append(f"evr{e['t']}{e['titre']}")
            lr = []
            for mk, rr in (derniers or {}).items():
                apres = [x for x in rr.get("m1", []) if x["t"] >= e["t"]]
                if apres:
                    o0 = apres[0]["o"]; c1 = apres[-1]["c"]; hh = max(x["h"] for x in apres); ll = min(x["l"] for x in apres)
                    lr.append(f"{ICONE.get(mk, '')} {mk} : {c1 - o0:+.1f} $ en {len(apres)} min {'⬆️' if c1 > o0 else '⬇️'} (écart haut-bas {hh - ll:.1f} $)")
            if lr:
                avis_apres = ia(
                    etat,
                    "Après cette annonce économique, interprète uniquement la réaction de prix observée sur BTC et Gold. Dis si le mouvement est net ou limité, rappelle que les deux sens restent possibles et indique d'attendre la clôture 15 min avant toute reprise. N'invente aucun chiffre et ne donne pas d'ordre d'entrée.",
                    {"annonce": e["titre"], "réaction observée": lr, "consigne": "aucune entrée avant clôture 15 min"},
                    cle_cache=f"newsreaction{e['t']}{e['titre']}", duree=3600)
                message = f"📰 RÉACTION À LA NEWS — {e['titre']}\n" + "\n".join(lr)
                message += "\n⏳ J'attends la clôture de la bougie 15 min avant de reprendre"
                if avis_apres:
                    message += "\n\n🧠 L'analyse de l'IA ALIGN après l'annonce\n" + avis_apres
                out.append(message)
        if 6 * 60 < reste <= 30 * 60 and f"ev{e['t']}{e['titre']}" not in vus:
            vus.append(f"ev{e['t']}{e['titre']}")
            avis = ia(etat, "Explique en 2 lignes très simples ce que cette annonce peut faire au Gold et au BTC (sans donner de sens à trader, juste le risque).",
                      {"annonce": e["titre"], "prévu": e.get("prev"), "avant": e.get("avant")}, cle_cache=f"news{e['t']}{e['titre']}", duree=3600)
            out.append(f"⚠️⚠️ NEWS USA dans {round(reste / 60)} min ({heure(e['t'])})\n📰 {e['titre']}\n\n"
                       f"🟥 N'ouvre AUCUN trade\n🛡 Déjà en position ? Vérifie que ton STOP est bien placé\n"
                       f"💥 Le prix peut bouger très fort dans les 2 sens\n⏳ On reprend à {fin}" + (f"\n\n🧠 L'avis de l'IA ALIGN\n{avis}" if avis else ""))
        if 0 <= reste <= 6 * 60 and f"ev5{e['t']}{e['titre']}" not in vus:
            vus.append(f"ev5{e['t']}{e['titre']}")
            out.append(f"🚨🚨🚨 NEWS DANS {max(1, round(reste / 60))} MIN — {e['titre']}\n🟥 Ne touche à rien\n🛡 Stop en place ? OK, on attend")
        if 15 * 60 <= -reste <= 25 * 60 and f"evfin{e['t']}{e['titre']}" not in vus:
            vus.append(f"evfin{e['t']}{e['titre']}")
            out.append(f"✅ News passée ({e['titre']}). 🟩 Le bot reprend la recherche d'entrées.")
    # Fermeture du Gold : 1 h avant et 40 min avant (jours de semaine)
    if jour.weekday() < 5:
        f_ = minutes_avant_fermeture_gold(maintenant)
        tp_, cme_, rouv_ = horaires_gold(maintenant)
        for avant, cle_f in ((60, "f60"), (40, "f40")):
            if avant - 5 < f_ <= avant and f"{cle_f}{cle_j}" not in vus:
                vus.append(f"{cle_f}{cle_j}")
                tr_g = (etat.get("GOLD") or {}).get("trade")
                week = jour.weekday() == 4
                out.append(f"🌙 FERMETURE DU GOLD DANS {avant} MIN — 🥇 GOLD\n🚦 🙅 PAS DE NOUVELLE POSITION\n"
                           f"🟥 Topstep / prop firms : tout fermé avant {heure(tp_)} (sinon fermeture automatique)\n"
                           f"🌙 Broker (CFD) / CME : fermeture {heure(cme_)}\n"
                           f"🔓 Réouverture : {'dimanche ' if week else ''}{heure(rouv_)} (heure de Paris)\n"
                           + ("🔒 Tu es en position : mets-toi à BE si tu es en gain\n🛡 Vérifie que ton SL est bien placé\n" if tr_g else "🛡 Ne pas ouvrir de position avant la fermeture\n")
                           + ("💥 Week-end : le prix peut s'ouvrir loin (écart), sécurise tes gains" if week else "💥 À la réouverture le prix peut sauter (écart)"))
    # Ouvertures de marché (jours de semaine)
    if jour.weekday() < 5:
        for nom, zone, h, mn in (("Sydney", "Australia/Sydney", 10, 0), ("Tokyo", "Asia/Tokyo", 9, 0), ("Londres", "Europe/London", 8, 0), ("New York (Wall Street)", "America/New_York", 9, 30)):
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

def horaires_gold(ts=None):
    """Horaires du Gold, calculés en heure de Chicago (gère tout seul heure d'été / d'hiver) :
    Topstep (prop firm futures) : tout fermer avant 15:10 CT • CME / CFD : fermeture 16:00 CT • réouverture 17:00 CT."""
    ct = datetime.datetime.fromtimestamp(ts or time.time(), ZoneInfo("America/Chicago"))
    h = lambda hh, mm: ct.replace(hour=hh, minute=mm, second=0, microsecond=0).timestamp()
    return h(15, 10), h(16, 0), h(17, 0)

def minutes_avant_fermeture_gold(ts=None):
    """Minutes avant la clôture Topstep (15:10 CT, la plus tôt) — négatif après."""
    t = ts or time.time()
    return (horaires_gold(t)[0] - t) / 60

def annonce_proche(etat, maintenant):
    return any(abs(e["t"] - maintenant) <= 15 * 60 for e in etat.get("cal", {}).get("ev", []))

# ───────── Agent : suit le trade du début à la fin ─────────
def duree_txt(tr):
    """Combien de temps la position peut durer (TP1 et TP2), pour savoir si elle passe la nuit."""
    a = tr.get("atr_e") or abs(tr["e"] - tr["sl"])            # à défaut : le risque comme repère
    v = max(a * 0.5 / 15, 1e-9)                               # ≈ ½ bougie moyenne toutes les 15 min
    t1 = abs(tr["tp1"] - tr["e"]) / v; t2 = abs(tr["tp2"] - tr["e"]) / v
    f = lambda mn: f"≈ {round(mn / 60)} h" if mn >= 90 else f"≈ {round(mn)} min"
    long_ = t2 >= 8 * 60 or "Daily" in str(tr.get("n2", ""))
    return (f"⏱ Durée estimée : TP1 {f(t1)} • TP2 {f(t2)}\n"
            + ("📅 Position LONGUE : elle peut durer plus d'une journée, garde ton SL en place la nuit\n" if long_ else ""))

def fmt_trade(m, tr, p=None):
    """Carte visuelle pour débutant : couleurs + échelle des prix dessinée de haut en bas."""
    d = tr["d"]
    tete = ("🟩🟩🟩  LONG ⬆️  " if d == 1 else "🟥🟥🟥  SHORT ⬇️  ") + m
    za, zb = tr.get("za", tr["e"]), tr.get("zb", tr["e"])
    bougie = "en dessous de la dernière bougie basse" if d == 1 else "au-dessus de la dernière bougie haute"
    risque = abs(tr["e"] - tr["sl"]); gain = abs(tr["tp1"] - tr["e"])
    risque_pct = risque / max(abs(tr["e"]), 1e-9) * 100
    barres = lambda x: "▮" * max(1, min(10, round(x / max(risque, 1e-9) * 2)))
    # Échelle des prix, du plus haut au plus bas
    pts = [(tr["sl"], "🛑", "STOP"), (tr["tp1"], "💰", "TP1"), (tr["tp2"], "🏁", "TP2")]
    pts += [(zb, "🟨", "ENTRÉE haut"), (za, "🟨", "ENTRÉE bas")] if abs(zb - za) > 1e-9 else [(tr["e"], "🟨", "ENTRÉE")]
    if p is not None:
        pts.append((p, "👉", "PRIX ACTUEL"))
    echelle = "\n".join(f"{ic} {px(v)}  {nom}" for v, ic, nom in sorted(pts, key=lambda z: -z[0]))
    pct = lambda v: f"{(v - tr['e']) / tr['e'] * 100:+.2f} %".replace(".", ",")
    meche = "la mèche du dernier creux" if d == 1 else "la mèche du dernier sommet"
    resume = (f"📌 PLAN D'EXÉCUTION — {'🟩 LONG' if d == 1 else '🟥 SHORT'}\n"
              f"🟨 Entrée : {px(tr['e'])}\n"
              f"🛑 Stop Loss : {px(tr['sl'])}\n"
              f"💰 TP1 : {px(tr['tp1'])}\n"
              f"🏁 TP2 : {px(tr['tp2'])}\n"
              f"⚖️ Ratio gain/risque TP1 : 1:{tr['rr']:.1f}\n")
    decision = (f"\n━━━━━━━━━━━━\n📍 RÉCAPITULATIF — {m}\n"
                f"{'🟩 LONG ⬆️' if d == 1 else '🟥 SHORT ⬇️'}\n"
                f"Entrée {px(tr['e'])} • SL {px(tr['sl'])}\n"
                f"TP1 {px(tr['tp1'])} • TP2 {px(tr['tp2'])}\n"
                "⛔ Ne pas anticiper la clôture de confirmation. Le SL reste obligatoire.\n")
    return (f"{tete}\n"
            + resume +
            f"🧭 Fond H4 • confirmation H1 • préparation M15 • timing M5\n"
            f"⏱ Vue d'entrée : 5 minutes (15M = préparation, M5 = timing après clôture confirmée)\n\n"
            f"🕯 EN BOUGIES (marche sur toutes les plateformes) :\n"
            f"1️⃣ 👀 Mets-toi en vue 5 minutes pour l'entrée\n"
            + (f"2️⃣ 🛑 SL : un tout petit peu {meche_sl(tr)} (structure 5 min)\n"
               f"3️⃣ 🟨 Entrée {SENS[d]} : après clôture 5 min au-delà de ≈ {px(tr.get('niveau', tr['e']))}\n"
               if tr.get("src") == "cassure 5 min" else
               f"2️⃣ 🛑 SL : un tout petit peu {meche_sl(tr)}\n" +
               (f"3️⃣ 🟨 Entrée {SENS[d]} : MAINTENANT, à la clôture de la bougie de rejet ({tr.get('sl_ut', '5 min')} de {tr.get('sl_h', '')})\n" if tr.get("rejet") else
                f"3️⃣ 🟨 Entrée {SENS[d]} : sur le {'repli' if d == 1 else 'rebond'}, vers la moitié de la dernière grande bougie {'verte' if d == 1 else 'rouge'}\n"))
            + (f"4️⃣ 💰 TP1 : juste {'sous la' if d == 1 else 'au-dessus du'} {tr['n1']} (regarde en vue {vue(tr['n1'])})\n"
               if "projection" not in tr["n1"] else f"4️⃣ 💰 TP1 : environ {tr['rr']:.1f} fois ton risque\n")
            + (f"5️⃣ 🏁 TP2 : {tr['n2']} (vue {vue(tr['n2'])})\n" if "projection" not in tr["n2"] else "5️⃣ 🏁 TP2 : on laisse courir, je te guide\n")
            + duree_txt(tr) +
            f"📉 Distance entrée → SL : {risque_pct:.2f} % du prix (pas le % du capital risqué)\n"
            f"🛑 SL obligatoire : ne jamais l'élargir ni l'enlever. Respecte le niveau indiqué.\n"
            f"💡 BE : alerte après confirmation de clôture, pas sur une mèche\n\n"
            f"📍 Repère prix {m} ({'XAUUSD spot' if m == 'GOLD' else 'BTC/USD'}) :\n{echelle}\n\n"
            f"Risque {barres(risque)}\nGain   {barres(gain)}  (x{tr['rr']:.1f})\n"
            + decision + f"\n{MINI_AVERT}\n👍 Like si tu participes")

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
    """Zone limite basée sur le dernier mouvement 5m ; niveaux 1h/4h et FVG restent des confluences."""
    a = r.get("atr5", r["atr"]); b = r["b5"][-24:]
    H = max(x["h"] for x in b); L = min(x["l"] for x in b)
    if d == -1:   # SHORT : on vend un rebond vers une résistance
        z50, z618, z786 = L + 0.5 * (H - L), L + 0.618 * (H - L), L + 0.786 * (H - L)
        cand = [(v, n) for v, n in r["niveaux"] if z50 - 0.3 * a <= v <= z786 + 0.3 * a and n in ("15m", "1h", "4h")]
        cand += [((lo + hi) / 2, "FVG " + ut) for lo, hi, ut, dd in r.get("fvg", []) if dd == -1 and z50 - 0.3 * a <= (lo + hi) / 2 <= z786 + 0.3 * a]
        if cand:
            e, src = min(cand, key=lambda z: abs(z[0] - z618)); src = f"résistance {src} + retracement Fibonacci"
        elif z50 <= r.get("ema5", r["ema15"]) <= z786:
            e, src = r.get("ema5", r["ema15"]), "EMA 20 (5m) + retracement Fibonacci"
        else:
            e, src = z618, "retracement Fibonacci 61,8 %"
        e = max(e, p)
        res4h = [v for v, n in r["grosses"] if n == "4h" and e < v < e + 3 * a]
        res1h = res4h or [v for v, n in r["grosses"] if n == "1h" and e < v < e + 3 * a]   # résistance la plus costaud d'abord (4h)
        sl = max(H, min(res1h) if res1h else H) + 0.3 * a
    else:         # LONG : on achète un repli vers un support
        z50, z618, z786 = H - 0.5 * (H - L), H - 0.618 * (H - L), H - 0.786 * (H - L)
        cand = [(v, n) for v, n in r["niveaux"] if z786 - 0.3 * a <= v <= z50 + 0.3 * a and n in ("15m", "1h", "4h")]
        cand += [((lo + hi) / 2, "FVG " + ut) for lo, hi, ut, dd in r.get("fvg", []) if dd == 1 and z786 - 0.3 * a <= (lo + hi) / 2 <= z50 + 0.3 * a]
        if cand:
            e, src = min(cand, key=lambda z: abs(z[0] - z618)); src = f"support {src} + retracement Fibonacci"
        elif z786 <= r.get("ema5", r["ema15"]) <= z50:
            e, src = r.get("ema5", r["ema15"]), "EMA 20 (5m) + retracement Fibonacci"
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
    t1, t2 = objectifs(r, d, e, risque)
    nom = lambda z: (("résistance " if d == 1 else "support ") + z[1]) if z[1] in ("1h", "4h", "Daily") else z[1]
    # Zone d'entrée : du retracement 50 % jusqu'au 78,6 %, jamais à moins de 25 % du risque avant le stop
    if d == -1:
        za, zb = min(e, max(z50, p)), max(e, z786); zb = min(zb, sl - 0.25 * (sl - e))
    else:
        zb, za = max(e, min(z50, p)), min(e, z786); za = max(za, sl + 0.25 * (e - sl))
    za, zb = min(za, zb), max(za, zb)
    # SL serré : juste derrière le bas (LONG) / le haut (SHORT) de la zone, là où se fera la mèche de rejet
    sl_serre = za - 0.6 * a if d == 1 else zb + 0.6 * a
    if d * (sl_serre - sl) > 0:
        sl = sl_serre
    # Jamais de gros SL : si le risque dépasse 1,5 ATR, on attend un repli plus profond (entrée plus près du SL)
    if abs(e - sl) > RISQUE_MAX * a:
        e = sl + d * RISQUE_MAX * a
        if d == 1: zb = max(za, min(zb, e))
        else: za = min(zb, max(za, e))
    risque = max(abs(e - sl), 1e-9)
    return dict(d=d, e=e, sl=sl, tp1=t1[0], n1=nom(t1), tp2=t2[0], n2=nom(t2), rr=abs(t1[0] - e) / risque, src=src,
                za=za, zb=zb, f50=z50, f618=z618, f786=z786, sl_h=bougie_protegee(b, d, sl), sl_ut="5 min")

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
            _envoi_sur(c, text=t, reply_markup=markup_position(m))
        gerer_stop(etat, m, r, tr, c)

def gerer_stop(etat, m, r, tr, c):
    """Vrai agent : monte le stop de l'abonné derrière chaque support (long) / résistance (short) franchi,
    stop à l'entrée dès que le trade avance, et « reste cool » quand le marché respire."""
    pos = tr["qui"][c]; d = tr["d"]; a = r["atr"]; p = r["m1"][-1]["c"]
    e = pos["e"]; sl = pos.get("sl_conseil", pos["sl"]); risque = max(abs(e - pos["sl"]), 1e-9)
    # Stop conseillé touché : on clôture le résultat de l'abonné à ce niveau
    if pos.get("sl_conseil") is not None:
        extreme = min(x["l"] for x in r["m1"][-6:]) if d == 1 else max(x["h"] for x in r["m1"][-6:])
        if m == "GOLD" and r.get("spot_lo") is not None:     # même règle que le bot : le vrai prix spot fait foi
            extreme = min(r["spot_lo"], extreme + 0.3 * a) if d == 1 else max(r["spot_hi"], extreme - 0.3 * a)
        if d * (extreme - sl) <= 0:
            noter(etat, c, m, pos, sl, "🔒 Stop protégé touché" if d * (sl - e) >= 0 else "🛡 Stop remonté touché")
            return
    gain = d * (p - e)
    if gain <= 0:
        return
    # Niveaux franchis entre l'entrée et le prix : le stop se cache juste derrière le plus proche du prix
    # Pas de manque à gagner : on ne bouge le SL que quand une bougie 15 min a CLÔTURÉ au-delà (pas sur une mèche),
    # et on le place assez loin derrière le niveau cassé pour survivre au retest (le prix revient souvent tester la cassure)
    clot = r["b15"][-1]["c"]
    murs = [v for v, n in r["niveaux"] if n in ("15m", "1h", "4h") and d * (p - v) > 0.6 * a and d * (clot - v) > 0.3 * a
            and d * (v - (e - d * 0.6 * a)) > 0]
    nouveau, pourquoi = None, ""
    if murs:
        v = max(murs) if d == 1 else min(murs)
        nouveau, pourquoi = v - d * 0.5 * a, "mèche"
    if gain >= 1.2 * risque and d * (clot - e) >= 1.0 * a and (nouveau is None or d * (nouveau - e) < 0) \
            and not any(abs(v - e) < 0.6 * a for v in murs):
        nouveau, pourquoi = e + d * 0.05 * a, "be"
    if nouveau is not None and d * (nouveau - sl) > 0.3 * a and d * (p - nouveau) > 0.5 * a:
        pos["sl_conseil"] = nouveau
        if pourquoi == "be" or abs(nouveau - e) < 0.2 * a:
            texte = (f"🔒 METS-TOI À BE — {ICONE.get(m, '')} {m}\n🚦 🟢 ON RESTE EN POSITION\n{SENS[d]}\n"
                     f"🛑 Nouveau SL : BE ≈ {px(e)} (ton prix d'entrée)\n"
                     f"🕯 Pourquoi : la bougie 15 min de {heure(r['b15'][-1]['t'])} a CLÔTURÉ bien {'au-dessus' if d == 1 else 'en dessous'} de ton entrée\n"
                     "🛡 Résultat : plus aucune perte possible\n"
                     f"💰 TP visé ≈ {px(pos.get('tp1', tr['tp1']))}")
        else:
            texte = (f"🔒 {ICONE.get(m, '')} {m}   {SENS[d]}\n"
                     "👀 Mets-toi en vue 15 minutes\n"
                     f"🕯 Repère la mèche {'basse' if d == 1 else 'haute'} • bougie 15 min de {bougie_protegee(r['b15'][-24:], d, nouveau)}\n"
                     f"💥 La bougie 15 min a CLÔTURÉ au-delà du niveau ≈ {px(v)} : on protège sans se faire sortir au retest\n"
                     f"{'⬆️ Monte' if d == 1 else '⬇️ Descends'} ton SL un peu {'SOUS' if d == 1 else 'AU-DESSUS de'} cette mèche\n"
                     "🙅 Jamais pile sur la mèche : elle peut être retouchée\n"
                     + ("💰 Ton gain est protégé" if d * (nouveau - e) > 0 else "🛡 Ta perte possible est réduite")
                     + f"\n📍 Repère prix   ≈ {px(nouveau)}")
        _envoi_sur(c, reply_markup=markup_position(m), text=texte)
        return
    # Le marché respire : petit retour vers l'entrée, on ne bouge rien
    r5 = r["r5"][-1]
    excès = (r5 >= 70) if d == 1 else (r5 <= 30)
    tps = pos.setdefault("cool_t", 0)
    if excès and time.time() - tps >= 45 * 60:
        pos["cool_t"] = time.time()
        _envoi_sur(c, reply_markup=markup_position(m), text=(
            f"😎 {ICONE.get(m, '')} {m} : reste cool\n🌬 Le marché respire\n"
            "🕯 Il peut revenir un peu, c'est normal\n"
            "🛑 Ne touche pas ton SL\n🎯 Cap sur le TP"))

def meche_suspecte(out, m, r, cle):
    """PRÉ-ALERTE pendant la bougie 15 min EN COURS : la mèche vient de passer sous le dernier plus bas
    (ou au-dessus du dernier plus haut) puis le prix revient. Confirmation (ou non) à la clôture."""
    b = r["b15"]; a = r["atr"]
    if len(b) < 21 or a < 0.0005 * b[-1]["c"]:
        return
    debut = b[-1]["t"] + 900                       # début de la bougie 15 min en cours
    en_cours = [x for x in r["m1"] if x["t"] >= debut]
    pa = cle.get("pre_manip")
    # À la clôture : la bougie suspecte n'a PAS été confirmée comme manipulation → on le dit
    if pa and pa["t15"] < debut and cle.get("manip_t") != pa["t15"]:
        cle.pop("pre_manip", None)
        out.append(f"❌ {ICONE.get(m, '')} {m} : pas de manipulation confirmée\n🕯 La bougie 15 min de {heure(pa['t15'])} n'a pas clôturé en revenant\n"
                   f"⚠️ C'est peut-être une vraie cassure {'vers le bas' if pa['d'] == 1 else 'vers le haut'} : prudence")
        return
    if len(en_cours) < 5 or (pa and pa["t15"] == debut):
        return
    z = b[-20:]
    H = max(y["h"] for y in z); L = min(y["l"] for y in z)
    h = max(x["h"] for x in en_cours); l = min(x["l"] for x in en_cours); o = en_cours[0]["o"]; c = en_cours[-1]["c"]
    rng = max(h - l, 1e-9)
    dm = 0
    if l < L - 0.15 * a and c > L + 0.1 * a and (min(o, c) - l) >= 0.6 * rng and rng >= 1.0 * a:
        dm, niv = 1, L
    elif h > H + 0.15 * a and c < H - 0.1 * a and (h - max(o, c)) >= 0.6 * rng and rng >= 1.0 * a:
        dm, niv = -1, H
    if not dm:
        return
    cle["pre_manip"] = {"t15": debut, "d": dm}
    out.append(f"⚠️ MÈCHE SUSPECTE EN COURS — {ICONE.get(m, '')} {m}\n"
               f"🕯 Vue 15 min : la bougie de {heure(debut)} a piqué {'SOUS le dernier plus bas' if dm == 1 else 'AU-DESSUS du dernier plus haut'} ≈ {px(niv)}\n"
               f"🎣 Les stops viennent d'être pris et le prix revient\n"
               f"🙅 N'entre pas maintenant\n⏳ J'attends la CLÔTURE de cette bougie ({heure(debut + 900)}) pour confirmer la manipulation")

def macro(etat):
    """Contexte macro GRATUIT : Dollar (DXY recalculé depuis 6 paires Swissquote, toutes les 4 min)
    et taux US 10 ans (Trésor américain, 1 fois / 3 h). Le Gold bouge souvent à l'INVERSE des deux."""
    mc = etat.setdefault("macro", {"dxy": [], "us10": None, "us10_t": 0})
    now = time.time()
    if not mc["dxy"] or now - mc["dxy"][-1][0] >= 240:
        try:
            v = {}
            for a_, b_ in (("EUR", "USD"), ("USD", "JPY"), ("GBP", "USD"), ("USD", "CAD"), ("USD", "SEK"), ("USD", "CHF")):
                q = http_json(f"https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/{a_}/{b_}")[0]["spreadProfilePrices"][0]
                v[a_ + b_] = (q["bid"] + q["ask"]) / 2
            dx = (50.14348112 * v["EURUSD"] ** -0.576 * v["USDJPY"] ** 0.136 * v["GBPUSD"] ** -0.119
                  * v["USDCAD"] ** 0.091 * v["USDSEK"] ** 0.042 * v["USDCHF"] ** 0.036)
            mc["dxy"].append((now, round(dx, 3)))
            mc["dxy"] = [x for x in mc["dxy"] if now - x[0] <= 3 * 3600 + 600]
            # EUR/USD est la paire majeure de référence du panier DXY : on la conserve
            # au même instant pour contrôler la relation inverse sans mélanger les horaires.
            mc.setdefault("eurusd", []).append((now, round(v["EURUSD"], 6)))
            mc["eurusd"] = [x for x in mc["eurusd"] if now - x[0] <= 3 * 3600 + 600]
        except Exception as ex:
            print("dxy", ex)
    if now - mc.get("us10_t", 0) >= 3 * 3600:
        try:
            an = datetime.datetime.now(PARIS).year
            req = urllib.request.Request(f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{an}/all?type=daily_treasury_yield_curve&field_tdr_date_value={an}&page&_format=csv",
                                         headers={"User-Agent": "align-bot"})
            lignes = urllib.request.urlopen(req, timeout=30).read().decode().splitlines()
            tete = [x.strip().strip('"') for x in lignes[0].split(",")]; i10 = tete.index("10 Yr")
            l0 = [x.strip().strip('"') for x in lignes[1].split(",")]
            l1 = [x.strip().strip('"') for x in lignes[2].split(",")]
            mc["us10"] = (float(l0[i10]), float(l1[i10]), l0[0])
            mc["us10_t"] = now
        except Exception as ex:
            mc["us10_t"] = now - 3 * 3600 + 600  # nouvel essai dans 10 minutes
            print("taux US", ex)
    return mc

def variation_une_heure(historique):
    """Variation 1h seulement si un échantillon existe entre 40 et 80 minutes."""
    if len(historique) < 2:
        return None
    now_t, valeur = historique[-1]
    candidats = [x for x in historique[:-1] if 2400 <= now_t - x[0] <= 4800 and x[1]]
    if not candidats or not valeur:
        return None
    ref = min(candidats, key=lambda x: abs((now_t - x[0]) - 3600))
    return (valeur - ref[1]) / ref[1] * 100, round((now_t - ref[0]) / 60)


def dxy_info(etat, maintenant=None):
    h = (etat.get("macro") or {}).get("dxy") or []
    if not h:
        return None
    maintenant = time.time() if maintenant is None else maintenant
    dernier_ts, dernier_prix = h[-1]
    # Une cotation de plus de 15 minutes ou horodatée dans le futur est rejetée.
    if maintenant - dernier_ts > 15 * 60 or dernier_ts > maintenant + 60:
        return None
    variation = variation_une_heure(h)
    if variation is None:
        return None
    ch, mn = variation
    return dernier_prix, ch, mn

def us10_info(etat):
    """Dernier rendement US Treasury 10 ans publié, avec date et fraîcheur contrôlées."""
    us = (etat.get("macro") or {}).get("us10")
    if not us:
        return {"disponible": False, "statut": "DONNÉES US10Y INDISPONIBLES"}
    try:
        valeur, precedente, date_txt = us
        date_pub = None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d-%b-%Y"):
            try:
                date_pub = datetime.datetime.strptime(str(date_txt), fmt).date()
                break
            except ValueError:
                continue
        if date_pub is None:
            return {"disponible": False, "statut": "DATE US10Y ILLISIBLE"}
        age_jours = (datetime.datetime.now(PARIS).date() - date_pub).days
        if age_jours < 0 or age_jours > 5:
            return {"disponible": False, "statut": "US10Y TROP ANCIEN", "date_publication": str(date_pub), "age_jours": age_jours}
        return {
            "disponible": True, "rendement_pct": float(valeur),
            "precedent_pct": float(precedente),
            "variation_points_base": round((float(valeur) - float(precedente)) * 100, 1),
            "date_publication": str(date_pub), "age_jours": age_jours,
            "frequence": "QUOTIDIENNE — PAS UNE DONNÉE INTRADAY"
        }
    except (TypeError, ValueError, IndexError):
        return {"disponible": False, "statut": "FORMAT US10Y INVALIDE"}


def macro_confluence(etat, m, r=None, maintenant=None):
    """Biais DXY, contrôle EUR/USD, US10Y officiel et divergences avec l'actif."""
    mc = etat.get("macro") or {}
    di = dxy_info(etat, maintenant=maintenant)
    taux = us10_info(etat)
    if not di:
        return {"disponible": False, "statut": "DONNÉES DXY INSUFFISANTES", "us10y": taux}
    dxy, variation, age_min = di
    hist_eur = mc.get("eurusd") or []
    eur_change = None
    # EUR/USD et DXY doivent avoir des cotations récentes et synchronisées.
    hist_dxy = mc.get("dxy") or []
    instant_reference = time.time() if maintenant is None else maintenant
    eur_synchrone = bool(hist_eur and hist_dxy and
                         abs(hist_eur[-1][0] - hist_dxy[-1][0]) <= 8 * 60 and
                         instant_reference - hist_eur[-1][0] <= 15 * 60 and
                         hist_eur[-1][0] <= instant_reference + 60)
    eur_variation = variation_une_heure(hist_eur) if eur_synchrone else None
    if eur_variation is not None:
        eur_change = eur_variation[0]
    if variation >= 0.25:
        dollar_state = "FORTE HAUSSE — IMPULSION HAUSSIÈRE"
    elif variation <= -0.25:
        dollar_state = "FORTE BAISSE — IMPULSION BAISSIÈRE"
    elif variation > 0.03:
        dollar_state = "HAUSSIER (BULLISH)"
    elif variation < -0.03:
        dollar_state = "BAISSIER (BEARISH)"
    else:
        dollar_state = "NEUTRE"
    fx_check = "INDISPONIBLE"
    if eur_change is not None:
        if variation > 0.03 and eur_change < -0.03 or variation < -0.03 and eur_change > 0.03:
            fx_check = "COHÉRENT : DXY et EUR/USD évoluent en sens inverse"
        elif abs(variation) <= 0.03 or abs(eur_change) <= 0.03:
            fx_check = "MIXTE : mouvement faible"
        else:
            fx_check = "DIVERGENCE : DXY et EUR/USD évoluent dans le même sens"
    asset_change = None
    if r and r.get("b15") and len(r["b15"]) >= 5:
        b = r["b15"]
        ref_close = b[-5]["c"]
        if ref_close:
            asset_change = (b[-1]["c"] - ref_close) / ref_close * 100
    divergence = "NON ÉVALUABLE"
    if asset_change is not None and abs(variation) > 0.03 and abs(asset_change) > 0.03:
        if variation > 0 and asset_change > 0:
            divergence = "DIVERGENCE HAUSSIÈRE : l'actif résiste malgré un dollar en hausse"
        elif variation < 0 and asset_change < 0:
            divergence = "DIVERGENCE BAISSIÈRE : l'actif baisse malgré un dollar en recul"
        elif variation > 0 and asset_change < 0:
            divergence = "CORRÉLATION INVERSE : dollar en hausse, actif en baisse"
        else:
            divergence = "CORRÉLATION INVERSE : dollar en baisse, actif en hausse"
    return {
        "disponible": True, "dxy": dxy, "dxy_variation_1h_pct": round(variation, 4),
        "age_reference_min": age_min, "dollar_direction": dollar_state,
        "eurusd_variation_1h_pct": round(eur_change, 4) if eur_change is not None else None,
        "controle_dxy_eurusd": fx_check, "actif": m,
        "actif_variation_1h_pct": round(asset_change, 4) if asset_change is not None else None,
        "divergence_actif_dollar": divergence,
        "us10y": taux,
        "regle": "Contexte macro uniquement : ne jamais inverser LONG/SHORT ni autoriser une entrée sans confirmations 4h/1h/15m/5m."
    }


def contexte_macro(etat, m, r=None):
    """Lignes macro vérifiables et propres à chaque marché."""
    l = []
    mc = macro_confluence(etat, m, r)
    if mc["disponible"]:
        d = mc["dxy_variation_1h_pct"]
        fleche = "⬆️" if d > 0.03 else "⬇️" if d < -0.03 else "➖"
        l.append(f"💵 DXY {mc['dxy']:.2f} {fleche} {d:+.2f} % / 1 h — dollar {mc['dollar_direction']}")
        l.append(f"💶 EUR/USD : {mc['controle_dxy_eurusd']}" +
                 (f" ({mc['eurusd_variation_1h_pct']:+.2f} % / 1 h)" if mc["eurusd_variation_1h_pct"] is not None else " (historique en constitution)"))
        l.append(f"🔀 {m} / dollar : {mc['divergence_actif_dollar']}")
    taux = mc.get("us10y") or {}
    if taux.get("disponible"):
        bp = taux["variation_points_base"]
        effet = "pression haussière sur les rendements" if bp > 0 else "détente des rendements" if bp < 0 else "rendement stable"
        l.append(f"🏦 US10Y : {taux['rendement_pct']:.2f} % — variation {bp:+.1f} points de base")
        l.append(f"📅 Dernière publication officielle : {taux['date_publication']} ({taux['frequence']}) — {effet}")
    else:
        l.append("🏦 US10Y : " + taux.get("statut", "DONNÉES INDISPONIBLES"))
    return l

def niveaux_cles(out, m, r, cle):
    """Plus haut / plus bas d'hier et de la semaine + range Asie : approche, puis cassure (clôture 15 min)."""
    p = r["m1"][-1]["c"]; a = r["atr"]; x15 = r["b15"][-1]; prev = r["b15"][-2]["c"] if len(r["b15"]) > 1 else x15["c"]
    jour = datetime.datetime.now(PARIS).strftime("%Y-%m-%d")
    vu = cle.setdefault("nivc", {})
    for k in [k for k in vu if not k.endswith(jour)]:
        vu.pop(k)
    niv = list(r.get("niv_cles") or [])
    h_ = datetime.datetime.now(PARIS).hour
    if r.get("asie") and 8 <= h_ < 14:
        niv += [(r["asie"][0], "plus haut du range Asie"), (r["asie"][1], "plus bas du range Asie")]
    for v, nom in niv:
        haut = "haut" in nom
        casse = (x15["c"] > v + 0.05 * a and prev <= v) if haut else (x15["c"] < v - 0.05 * a and prev >= v)
        if casse and f"c{nom}{jour}" not in vu:
            vu[f"c{nom}{jour}"] = 1
            out.append(f"💥 CASSURE — {ICONE.get(m, '')} {m}\n🕯 La bougie 15 min de {heure(x15['t'])} a CLÔTURÉ {'au-dessus du' if haut else 'sous le'} {nom} ≈ {px(v)}\n"
                       f"{'⬆️ Le mouvement peut continuer vers le haut' if haut else '⬇️ Le mouvement peut continuer vers le bas'}\n👀 Je vérifie l'alignement 15 min / 1 h / 4 h avant d'entrer")
        elif abs(p - v) <= 0.3 * a and f"a{nom}{jour}" not in vu and f"c{nom}{jour}" not in vu:
            vu[f"a{nom}{jour}"] = 1
            out.append(f"🧲 NIVEAU CLÉ — {ICONE.get(m, '')} {m}\n📍 Le prix approche le {nom} ≈ {px(v)}\n🕯 Vue 15 min : ça peut rebondir OU casser\n⏳ J'attends la clôture de la bougie 15 min")

def manipulation(out, m, r, cle):
    """MANIPULATION (chasse aux stops) vue 15 min : une grosse bougie pique AU-DELÀ du dernier plus bas / plus haut
    des 20 bougies 15 min (elle prend les stops) puis CLÔTURE en revenant à l'intérieur. 1 message par bougie."""
    b = r["b15"]; a = r["atr"]
    if len(b) < 22 or b[-1]["t"] == cle.get("manip_t"):
        return
    x = b[-1]; z = b[-21:-1]
    if a < 0.0005 * x["c"]:
        return                                 # marché endormi (week-end / nuit) : pas de fausse alerte
    H = max(y["h"] for y in z); L = min(y["l"] for y in z)
    rng = max(x["h"] - x["l"], 1e-9)
    bas = min(x["o"], x["c"]) - x["l"]; haut = x["h"] - max(x["o"], x["c"])
    dm = 0
    if x["l"] < L - 0.15 * a and x["c"] > L and bas >= 0.5 * rng and rng >= 1.3 * a:
        dm, niv, meche = 1, L, x["l"]          # stops pris SOUS le plus bas → les gros acheteurs entrent
    elif x["h"] > H + 0.15 * a and x["c"] < H and haut >= 0.5 * rng and rng >= 1.3 * a:
        dm, niv, meche = -1, H, x["h"]         # stops pris AU-DESSUS du plus haut → les gros vendeurs entrent
    if not dm:
        return
    cle["manip_t"] = x["t"]; cle["manip"] = {"d": dm, "t": r["t"], "niv": niv, "meche": meche, "t15": x["t"]}
    l = [f"🌀🌀 MANIPULATION EN COURS — {ICONE.get(m, '')} {m}",
         f"🕯 Vue 15 min : grosse mèche {'SOUS le dernier plus bas' if dm == 1 else 'AU-DESSUS du dernier plus haut'} ≈ {px(niv)}",
         "🎣 Les stops ont été pris, puis la bougie a CLÔTURÉ en revenant",
         "🙅 On ne court pas après la bougie"]
    if r.get("annonce"):
        l.append("📰 C'est l'effet de la news : encore plus de prudence")
    tr = cle.get("trade")
    if tr:
        l.append("🧘 Tu es en position : reste cool, ton SL est en place" if tr["d"] == dm else
                 "⚠️ C'est CONTRE ta position : ne bouge pas ton SL, je surveille")
    elif r["confirme"] == dm:
        mid = (niv + meche) / 2
        l += [f"✅ Dans le sens de la tendance : {SENS[dm]}",
              f"🎯 Point d'entrée visé : retour vers ≈ {px(niv)} ({'ancien plus bas' if dm == 1 else 'ancien plus haut'} 15 min)",
              f"⭐ Encore mieux : milieu de la mèche ≈ {px(mid)}",
              f"🛑 SL un peu {'SOUS' if dm == 1 else 'AU-DESSUS de'} la mèche ≈ {px(meche - dm * 0.2 * a)} • bougie 15 min de {heure(x['t'])}",
              "⏳ Patience : j'entre seulement sur une mèche de rejet + CLÔTURE 5 min",
              "🔔 Je t'envoie 🟢 J'ENTRE MAINTENANT au bon moment"]
    elif r["confirme"] == -dm:
        l += [f"⚠️ CONTRE la tendance de fond ({SENS[-dm]})",
              f"⛔ Pas de {SENS[dm]} tant que 15 min / 1 h / 4 h ne se retournent pas",
              "🔔 Je te préviens si ça se retourne"]
    else:
        l += [f"⏳ {SENS[dm]} possible — ⛔ PAS ENCORE VALIDÉ",
              "✅ Validé quand 15 min + 1 h + 4 h vont dans le même sens",
              "🔔 Je te préviens dès que c'est bon"]
    if not tr:
        l.append(statut_txt(0 if r["confirme"] == dm else -1, cle.get("ordre") if r["confirme"] == dm else None).strip())
    out.append(("\n".join(l), bouton_auto(m)) if not tr else "\n".join(l))

def statut_txt(entre, o=None):
    """Toujours clair : est-ce que j'entre ou pas, et quel TP on vise."""
    l = ["🚦 " + ("🟢 J'ENTRE" if entre == 1 else "🙅 JE N'ENTRE PAS" if entre == -1 else "⏳ JE N'ENTRE PAS ENCORE")]
    if o and o.get("tp1"):
        l.append(f"💰 TP visé ≈ {px(o['tp1'])} ({o.get('n1', 'TP1')})")
    return "\n" + "\n".join(l)

def manip_txt(cle, d, r):
    mp = cle.get("manip")
    return "🌀 Après la manipulation : les stops ont été pris, on rentre dans le bon sens\n" if mp and mp["d"] == d and r["t"] - mp["t"] <= 10800 else ""

def agent(m, r, cle, ferme):
    """Agent : tendance 4h + confirmation 1h → déclenchement sur bougie 5m clôturée."""
    out = []
    tr = cle.get("trade")
    depuis = cle.get("t1m", 0)
    bougies = ([x for x in r["m1"] if x["t"] > depuis][-10:] if depuis else []) or r["m1"][-1:]   # seulement les minutes depuis le dernier tour
    cle["t1m"] = r["m1"][-1]["t"]
    p = r["m1"][-1]["c"]
    hi = max(x["h"] for x in bougies); lo = min(x["l"] for x in bougies)
    d = r["confirme"]
    r5, r5p = r["r5"][-1], r["r5"][-2]
    ctx = f"Contexte : {zone_txt(r['posD'])} Daily, {zone_txt(r['posW'])} Weekly."
    try:
        manipulation(out, m, r, cle)
        meche_suspecte(out, m, r, cle)
        niveaux_cles(out, m, r, cle)
    except Exception as ex:
        print("manipulation", ex)

    # ── Pas de trade : tendance 4h confirmée par 1h, puis timing d'entrée en 5m ──
    if not tr and r.get("fermeture"):
        if r["t"] - cle.get("ferm_dit", 0) > 3 * 3600:
            cle["ferm_dit"] = r["t"]
            tp_, cme_, rouv_ = horaires_gold()
            out.append(f"🌙 MARCHÉ BIENTÔT FERMÉ — {ICONE.get(m, '')} {m}\n🚦 🙅 JE N'ENTRE PAS\n"
                       f"🟥 Topstep / prop firms : tout fermé avant {heure(tp_)}\n🌙 Broker (CFD) / CME : fermeture {heure(cme_)}\n"
                       f"🔓 Réouverture : {heure(rouv_)} (heure de Paris)\n"
                       "🛡 Pas de nouvelle position avant la fermeture\n🔔 Je reprends la recherche après la réouverture")
        return out
    if not tr:
        if not d:
            if cle.get("aligne"):
                out.append(f"⚪ {m} : confirmation 1h / tendance 4h perdue. Ordre annulé, j'attends.")
            cle["aligne"] = 0; cle["prep"] = False; cle.pop("ordre", None)
            return out
        # Extrême Daily/Weekly : aucune poursuite dans le sens de la tendance.
        # On attend une correction ou un retournement confirmé ; on ne vend pas à découvert sans signal opposé validé.
        if bloque_dw(r, d, p):
            cle["prep"] = False
            cle.pop("ordre", None)
            if r["t"] - cle.get("extreme_warn_t", 0) >= 1800:
                cle["extreme_warn_t"] = r["t"]
                out.append(f"⚠️ {m} : marché en zone extrême Daily/Weekly ({zone_txt(r['posD'])} / {zone_txt(r['posW'])}).\n⛔ Je ne poursuis pas le {('LONG' if d == 1 else 'SHORT')}.\n⏳ J'attends un repli ou un retournement confirmé en 1h + clôture 5m.")
            cle["aligne"] = d
            return out
        # ── Entrée sur CASSURE confirmée (clôture 5 min au-delà du niveau) ──
        pc = plan_cassure(r, d)
        if pc and pc["t15"] != cle.get("cassure_t") and not r.get("annonce"):
            cle["cassure_t"] = pc["t15"]
            tr = dict(pc, statut="entree", cree=r["t"], encore=0, atr_e=r["atr"])
            tr["profil"] = profil_trade(m, tr, r)
            non, n_, w_ = memoire_refuse(tr["profil"])
            if non:
                out.append(f"🧠 {ICONE.get(m, '')} {m} : cassure vue, mais je passe mon tour\n📚 Ce type de position a perdu trop souvent ({w_}/{n_} gagnés)")
                return out
            cle["trade"] = tr; cle["prep"] = False; cle["attente_rsi"] = False; cle["parti"] = False; cle.pop("ordre", None)
            out.append((f"🟢🟢🟢 J'ENTRE MAINTENANT — {ICONE.get(m, '')} {m}\n{SENS[d]}   💥 CASSURE CONFIRMÉE\n{qualite(tr)}{manip_txt(cle, d, r)}{avis_memoire(tr['profil'])}"
                        f"🕯 La bougie 5 min a CLÔTURÉ {'au-dessus' if d == 1 else 'en dessous'} de ≈ {px(pc['niveau'])}\n"
                        f"🛑 SL un peu {'SOUS' if d == 1 else 'AU-DESSUS de'} la mèche de cette bougie\n\n"
                        f"{fmt_trade(m, tr, p)}{ferme}\n\nTu es rentré ?", boutons(m)))
            return out
        # Le prix approche du niveau de cassure : on l'annonce AVANT (1 fois par niveau)
        if len(r["b5"]) >= 22 and not r.get("annonce"):
            L = niveau_cassure(r, d)
            nouveau_niv = abs(L - cle.get("cassure_vue", 0)) > 1.0 * r["atr"]
            if 0 <= d * (L - p) <= 0.35 * r["atr"] and (nouveau_niv or (abs(L - cle.get("cassure_vue", 0)) > 0.2 * r["atr"]
                                                                     and time.time() - cle.get("cassure_vue_t", 0) > 1800)):
                cle["cassure_vue"] = L; cle["cassure_vue_t"] = time.time()
                out.append((f"{'🟩🟩' if d == 1 else '🟥🟥'} CASSURE EN VUE — {ICONE.get(m, '')} {m}\n{SENS[d]}\n"
                            f"👀 Le prix approche ≈ {px(L)} ({'plus haut' if d == 1 else 'plus bas'} des 20 dernières bougies 5 min)\n"
                            f"🕯 Si une bougie 5 min CLÔTURE {'au-dessus' if d == 1 else 'en dessous'} → confirmation {SENS[d]}\n"
                            f"🙅 Une mèche qui dépasse ne suffit pas : on attend la clôture\n🔔 Tiens-toi prêt", bouton_auto(m)))
        # Daily / Weekly : pas de short tout en bas, pas de long tout en haut
        o = point_entree(r, d, p)
        # Refuser de poursuivre un mouvement déjà en haut/bas de sa zone, même si le repli projeté semble acceptable.
        bloque = bloque_dw(r, d, o["e"]) or bloque_dw(r, d, p)
        # Marché déjà parti (trop étiré) : on ne court pas après, on attend le repli ou le retournement
        p_ = r["m1"][-1]["c"]
        calme = ((r["r5"][-1] < 70 and p_ - r.get("ema5", r["ema15"]) < 1.5 * r.get("atr5", r["atr"])) if d == 1 else (r["r5"][-1] > 30 and r.get("ema5", r["ema15"]) - p_ < 1.5 * r.get("atr5", r["atr"])))
        if not cle.get("prep") and (etire(r, d) or (cle.get("parti") and not calme)):   # hystérésis : pas de va-et-vient
            if not cle.get("parti"):
                cle["parti"] = True; cle["attente_rsi"] = False; cle.pop("ordre", None)
                if time.time() - cle.get("parti_t", 0) > 7200:      # pas de répétition (2 h)
                    cle["parti_t"] = time.time()
                    out.append(f"🚀 {ICONE.get(m, '')} {m} est déjà parti {'⬆️' if d == 1 else '⬇️'}\n😎 On ne court pas après le prix\n"
                               f"🅰️ Repli vers ≈ {px(r['ema15'])} → {SENS[d]}\n{ligne_cassure(r, d)}"
                               + ("\n⚠️ Grosses unités en excès : si 15 min / 1 h / 4 h se retournent → " + SENS[-d] + " possible"
                                  if "Si 15 min" in prochaine(r, cle) else ""))
            # Le prix commence à revenir (5 min dans l'autre sens) : on le dit, comme si on regardait le graphique ensemble
            alerte_repli(out, m, r, cle, d, p_)
            if r["dirs"][2] == d and r["dirs"][0] == d:
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
                out.append(f"🧭 {m} : 4h + 1h alignées {'▲' if d == 1 else '▼'}, MAIS prix {zone_txt(r['posD'])} Daily / {zone_txt(r['posW'])} Weekly.\n"
                           f"⛔ Pas de {'long' if d == 1 else 'short'} ici : risque de rebond. J'attends un meilleur prix.")
            else:
                cle["ordre"] = o
                out.append((f"🔔 JE PRÉPARE UNE POSITION — {ICONE.get(m, '')} {m}\n{SENS[d]}   {'monte' if d == 1 else 'descend'} sur 15m, 1h et 4h ✅✅✅\n{qualite(o)}"
                           f"⏳ Je n'entre pas encore : j'attends que le prix vienne dans la zone 🟨\n"
                           f"👀 Mets-toi en vue 15 minutes\n"
                           f"🕯 Repère {'le dernier creux (mèche du bas)' if d == 1 else 'le dernier sommet (mèche du haut)'}\n"
                           f"🟨 L'entrée sera à peu près {'au-dessus de ce creux' if d == 1 else 'sous ce sommet'}\n"
                           f"🚦 Attends mon feu vert 🟢\n"
                           f"🅰️ Entrée sur le repli dans la zone 🟨\n{ligne_cassure(r, d)}\n\n"
                           f"{fmt_trade(m, o, p)}\n\n"
                           f"📐 Zone = Fibonacci 50 → 78,6 % + {o['src'].split(' + ')[0]}{ferme}", bouton_auto(m)))
        if (bloque and not cle.get("ordre")) or o["rr"] < GAIN_MIN:
            return out
        # Petit repli en cours avant d'arriver dans la zone : on le dit tout de suite
        if not cle.get("prep") and d * (p - o["e"]) > 0:
            alerte_repli(out, m, r, cle, d, p)
        elif r["dirs"][2] == d:
            cle["retrace_vu"] = False
        # On ajuste le point tant que le prix n'est pas encore arrivé (les niveaux bougent)
        if not cle.get("prep"):
            cle["ordre"] = o
        ancien = cle.get("ordre")
        if ancien and (not ancien.get("sl_h") or abs(ancien["e"] - ancien["sl"]) > RISQUE_MAX * r["atr"] * 1.05):
            cle["ordre"] = o                     # ancien ordre (SL trop grand ou sans heure de bougie) remplacé
        o = cle.get("ordre", o)
        if not cle.get("prep"):
            cle.pop("traverse", None)
        dist = d * (p - o["e"])       # < 0 = le prix n'est pas encore arrivé au point d'entrée
        touche = (lo <= o["e"]) if d == 1 else (hi >= o["e"])
        if not cle.get("prep") and abs(p - o["e"]) <= max(0.6 * r["atr"], abs(o["e"] - o["sl"]) * 0.5):
            cle["prep"] = True
            if r["t"] - cle.get("recalc_t", 0) >= 1800:
                out.append((f"{'🟩🟩' if d == 1 else '🟥🟥'} POINT D'ENTRÉE À VENIR — {ICONE.get(m, '')} {m}\n{SENS[d]}\n{qualite(o)}👀 ÇA ARRIVE\n🟨 Le prix entre dans la zone\n⚡ Tiens-toi prêt\n🔔 Cloche activée ? Ne rate pas le feu vert\n📍 Zone ≈ {px(o.get('za', o['e']))} – {px(o.get('zb', o['e']))}{statut_txt(0, o)}", bouton_auto(m)))
        # À quelques pips de l'entrée : « PRÉPARE-TOI » + rappel SL / TP (1 fois par point d'entrée)
        seuil = max(5 * PIP.get(m, 0.1), 0.05 * r["atr"])
        if cle.get("prep") and (abs(p - o["e"]) <= seuil or touche) and time.time() - cle.get("pret_t", 0) > 1800:
            cle["pret_t"] = time.time()
            if r["t"] - cle.get("recalc_t", 0) >= 1800:
                out.append((f"⚡⚡ PRÉPARE-TOI — {ICONE.get(m, '')} {m}\n{SENS[d]}\n{qualite(o)}🎯 On est à quelques pips de l'entrée\n👀 Vue 15 minutes\n"
                        f"🛑 Dès que tu es dedans : SL un peu {meche_sl(o)}\n"
                        f"💰 TP1 juste {'sous la' if d == 1 else 'au-dessus du'} {o['n1']}\n🙅 Jamais de position sans SL{statut_txt(0, o)}",
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
        if touche:
            cle["touche_t"] = r["t"]
        sl_touche = (lo <= o["sl"]) if d == 1 else (hi >= o["sl"])
        if sl_touche and cle.get("prep") and not cle.get("traverse"):
            # Zone traversée : on N'ENTRE PAS, mais on garde la zone et on attend la mèche de rejet + clôture
            cle["traverse"] = True; cle["touche_t"] = r["t"]
            if r["t"] - cle.get("recalc_t", 0) >= 1800:
                cle["recalc_t"] = r["t"]
                out.append(f"↩️ {ICONE.get(m, '')} {m} : la zone a été traversée sans rejet\n🙅 Pas d'entrée, heureusement\n"
                           f"🕯 J'attends une MÈCHE DE REJET + CLÔTURE {'en remontant' if d == 1 else 'en redescendant'} (vue 5 / 15 min)\n🛑 SL serré juste derrière la mèche{statut_txt(0, o)}")
        loin = d * (o["e"] - p) > 2.5 * r["atr"]          # le prix s'est enfoncé beaucoup trop loin
        expire = cle.get("touche_t") and r["t"] - cle["touche_t"] > 3600
        if cle.get("prep") and (loin or (expire and cle.get("traverse"))):
            cle.pop("touche_t", None); cle.pop("traverse", None); cle["prep"] = False; cle["attente_rsi"] = False
            cle.pop("attente_rejet", None); cle.pop("ordre", None)
            if r["t"] - cle.get("recalc_t", 0) >= 1800:
                out.append(f"🔎 {ICONE.get(m, '')} {m} : pas de rejet dans la zone\n😎 Je recalcule le prochain point {'plus bas' if d == 1 else 'plus haut'}{statut_txt(-1)}")
            cle["recalc_t"] = r["t"]
            return out
        recent_zone = cle.get("touche_t") and r["t"] - cle["touche_t"] <= 3600 and d * (p - o["e"]) <= 0.6 * r["atr"]
        if cle.get("traverse"):
            sl_touche = False          # l'ancien SL est remplacé par celui derrière la mèche de rejet
        if (touche or recent_zone) and not sl_touche:
            if r.get("annonce"):
                if not cle.get("pause"):
                    out.append(f"⏸ {m} : prix sur le point d'entrée, mais annonce économique dans moins de 15 min. On ne rentre pas.")
                cle["pause"] = True
                return out
            cle["pause"] = False
            # Entrée DIRECTE dès qu'un de ces 3 signaux apparaît dans la zone (plus d'attente dans le vide) :
            # 1) mèche de rejet + clôture  2) manipulation confirmée dans notre sens  3) bougie 15 min qui clôture dans le bon sens
            a_ = r.get("atr5", r["atr"]); bj = rejet(r, d, o["e"], a_); raison = "Mèche de rejet + clôture 5 min"
            # Une manipulation repérée en 15m reste informative ; elle ne déclenche jamais une entrée.
            x5 = r["b5"][-1]; rg = max(x5["h"] - x5["l"], 1e-9)
            if not bj and x5["t"] != cle.get("conf_t") and (
                    (d == 1 and x5["l"] <= o["zb"] + 0.1 * a_ and x5["c"] > x5["o"] and x5["c"] >= x5["l"] + 0.55 * rg and x5["c"] > o["za"] and r5 > r5p) or
                    (d == -1 and x5["h"] >= o["za"] - 0.1 * a_ and x5["c"] < x5["o"] and x5["c"] <= x5["h"] - 0.55 * rg and x5["c"] < o["zb"] and r5 < r5p)):
                bj = x5; raison = f"Bougie 5 min qui clôture {'en remontant' if d == 1 else 'en redescendant'}"
            if bj and r["t"] - cle.get("stop_t", 0) < 2700:
                bj = None                          # 45 min de calme après un stop : pas de revanche sur le marché
            if bj:
                cle["conf_t"] = x5["t"]
            if False and surcharge and not bj and not cle.get("attente_rejet"):
                cle["attente_rejet"] = True
                if r["t"] - cle.get("recalc_t", 0) >= 1800:
                    out.append(f"🕯 {ICONE.get(m, '')} {m} : RSI en surcharge ✅ — j'attends la MÈCHE DE REJET et la CLÔTURE ⏳\n"
                           f"👀 Vue 5 / 15 min : une bougie qui pique dans la zone puis clôture {'en remontant' if d == 1 else 'en redescendant'}")
            if bj:
                cle.pop("attente_rejet", None); cle.pop("touche_t", None); cle.pop("traverse", None)
                sl_m = (bj["l"] - 0.2 * a_) if d == 1 else (bj["h"] + 0.2 * a_)   # SL derrière la mèche 5m
                # SL derrière la mèche ET derrière le bas de la zone (le marché respire dans la zone), jamais plus de 1,5 ATR
                sl_m = min(sl_m, o["sl"], p - 1.0 * a_) if d == 1 else max(sl_m, o["sl"], p + 1.0 * a_)
                sl_m = max(sl_m, p - RISQUE_MAX * a_) if d == 1 else min(sl_m, p + RISQUE_MAX * a_)
                o = dict(o, e=p, sl=sl_m, za=p, zb=p, rr=abs(o["tp1"] - p) / max(abs(p - sl_m), 1e-9), rejet=True,
                         sl_h=heure(bj["t"]), sl_ut="5 min" if r["b5"] and bj is r["b5"][-1] else "15 min")
                tr = dict(o, statut="entree", cree=r["t"], encore=0, atr_e=a_)
                tr["profil"] = profil_trade(m, tr, r)
                non, n_, w_ = memoire_refuse(tr["profil"])
                if non:
                    cle["prep"] = False; cle.pop("ordre", None)
                    out.append(f"🧠 {ICONE.get(m, '')} {m} : prix dans la zone, mais je passe mon tour\n📚 Ce type de position a perdu trop souvent ({w_}/{n_} gagnés)")
                    return out
                cle["trade"] = tr; cle["prep"] = False; cle["attente_rsi"] = False; cle.pop("ordre", None)
                niveau = "Fibonacci" not in o["src"] or "+" in o["src"]   # confluence avec un niveau 15m / 1h / 4h ou l'EMA
                checks = [("4 h + 1 h alignées", bool(r["confirme"] == d)),
                          ("Daily / Weekly hors zone extrême", not bloque_dw(r, d, p)),
                          ("Zone Fibonacci 50 – 78,6 %", "Fibonacci" in o["src"]),
                          ("Niveau 15m / 1h / 4h ou EMA", niveau),
                          ("RSI de repli confirmé", surcharge), ("Contexte 1 h cohérent", conf1h),
                          (raison, bool(bj)),
                          ("Pas de news proche", not bool(r.get("annonce"))),
                          (f"Gain / risque x{o['rr']:.1f}", o["rr"] >= GAIN_MIN)]
                score = sum(ok for _, ok in checks)
                liste = "\n".join(f"{'✅' if ok else '➖'} {t}" for t, ok in checks)
                pct_conf = round(100 * score / len(checks))
                out.append((f"🟢🟢🟢 J'ENTRE MAINTENANT — {ICONE.get(m, '')} {m}\n{SENS[d]}\n{qualite(tr)}{manip_txt(cle, d, r)}{avis_memoire(tr['profil'])}🎯 Confluence : {pct_conf}% ({score}/{len(checks)} critères, pas une probabilité de gain)\n{liste}\n\n{fmt_trade(m, tr, p)}{ferme}\n\nTu es rentré ?", boutons(m)))
            elif not cle.get("attente_rsi"):
                cle["attente_rsi"] = True
                if r["t"] - cle.get("recalc_t", 0) >= 1800:
                    fin = r["b5"][-1]["t"] + 300
                    out.append(f"🟨 {ICONE.get(m, '')} {m} : prix DANS la zone\n{SENS[d]}\n"
                               f"🕯 J'entre dès qu'une bougie clôture {'en remontant' if d == 1 else 'en redescendant'}\n"
                               f"⏱ Prochaine décision : clôture de {heure(fin)}\n🔔 Tiens-toi prêt, ça peut être tout de suite{statut_txt(0, o)}")
        elif d * (p - o["e"]) > 0.35 * abs(o["tp1"] - o["e"]) and cle.get("prep"):
            out.append(f"⛔ {ICONE.get(m, '')} {m} : le prix est reparti {'⬆️' if d == 1 else '⬇️'} sans signal d'entrée\n😎 Pas de position forcée\n🔎 Je calcule le prochain point{statut_txt(-1)}")
            cle["prep"] = False; cle["attente_rsi"] = False; cle.pop("ordre", None)
        return out

    # ── Trade en cours ──
    # GOLD : les mèches PAXG (marché 24/7, peu liquide le soir) peuvent dépasser le vrai prix XAUUSD.
    # Le SL / TP ne compte que si le VRAI prix spot l'a touché (ou si PAXG l'a nettement dépassé).
    if m == "GOLD" and r.get("spot_lo") is not None:
        lo = min(r["spot_lo"], lo + 0.3 * r["atr"])
        hi = max(r["spot_hi"], hi - 0.3 * r["atr"])
    if tr["statut"] == "entree" and tr["d"] * (tr["tp2"] - tr["tp1"]) <= 0 and not tr.get("tp_corrige"):
        # TP2 avant TP1 (ancienne version) : on remet de l'ordre — TP1 atteignable, TP2 sur le grand niveau
        (n1v, n1n), (n2v, n2n) = objectifs(r, tr["d"], tr["e"], abs(tr["e"] - tr["sl"]))
        nm_ = lambda n: (("résistance " if tr["d"] == 1 else "support ") + n) if n in ("1h", "4h", "Daily") else n
        n1n, n2n = nm_(n1n), nm_(n2n)
        tr.update(tp1=n1v, n1=n1n, tp2=n2v, n2=n2n, tp_corrige=True, rr=abs(n1v - tr["e"]) / max(abs(tr["e"] - tr["sl"]), 1e-9))
        for c_, pos in tr.get("qui", {}).items():
            if isinstance(pos, dict):
                pos["tp1"] = n1v
        out.append(f"🎯 {ICONE.get(m, '')} {m} : objectifs remis dans l'ordre\n🚦 🟢 ON RESTE EN POSITION\n💰 TP1 ≈ {px(n1v)} ({n1n})\n🏁 TP2 ≈ {px(n2v)} ({n2n})\n🛑 SL inchangé ≈ {px(tr['sl'])}")
    d, e, sl, t1, t2 = tr["d"], tr["e"], tr["sl"], tr["tp1"], tr["tp2"]
    touche_sl = (lo <= sl) if d == 1 else (hi >= sl)
    touche_t1 = (hi >= t1) if d == 1 else (lo <= t1)
    touche_t2 = (hi >= t2) if d == 1 else (lo <= t2)
    progres = d * (p - e) / max(abs(t1 - e), 1e-9)

    if tr["statut"] == "entree":
        if touche_sl:
            if tr.get("be_dit"):
                out.append(f"🔒 {ICONE.get(m, '')} {m} : sorti à BE\n🚦 🙅 JE NE SUIS PLUS EN POSITION\n🛡 Aucune perte\n🔎 Je cherche la prochaine entrée")
            else:
                out.append(f"❌ {ICONE.get(m, '')} {m} : stop {px(sl)} touché\n🚦 🙅 JE NE SUIS PLUS EN POSITION\n😎 On coupe, prochain setup bientôt")
            cle["fin"] = [tr, sl, "🔒 Sorti à BE" if tr.get("be_dit") else "🛑 Stop touché"]; cle["stop_t"] = r["t"]
            cle.pop("trade"); cle["aligne"] = 0; return out
        if touche_t1:
            tr["statut"] = "tp1"; tr["sl"] = e
            out.append(f"🎯 TP1 TOUCHÉ — {ICONE.get(m, '')} {m}\n🚦 🟢 ON RESTE EN POSITION\n{SENS[d]}\n"
                       f"💰 TP1 ≈ {px(t1)} ✅\n✂️ Prends une partie des gains\n🔒 Vérifie que ton SL est à BE ≈ {px(e)}\n"
                       f"📈 Garde le reste : le marché peut encore pousser\n🏁 TP2 visé ≈ {px(t2)}\n🙅 Ne coupe pas tout sur le TP1")
            return out
        risque_ = abs(e - sl)
        if not tr.get("be_dit") and risque_ > 0 and d * (p - e) >= 1.2 * risque_ and d * (r["b15"][-1]["c"] - e) >= r["atr"]:
            tr["be_dit"] = True; tr["sl"] = e + d * 0.05 * r["atr"]
            out.append(f"🔒 METS-TOI À BE — {ICONE.get(m, '')} {m}\n🚦 🟢 ON RESTE EN POSITION\n{SENS[d]}\n"
                       f"🛑 Nouveau SL : BE ≈ {px(e)} (prix d'entrée)\n"
                       f"🕯 Pourquoi : la bougie 15 min de {heure(r['b15'][-1]['t'])} a CLÔTURÉ bien {'au-dessus' if d == 1 else 'en dessous'} de l'entrée\n"
                       f"🛡 Résultat : plus aucune perte possible\n💰 TP visé ≈ {px(t1)}")
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
    MEMOIRE[:] = etat.get("memoire", [])
    if TOKEN:
        installer_menu(etat)
    demandes = []
    if TOKEN:
        demandes = traiter(etat, chats, telegram("getUpdates", offset=etat.get("offset", 0), timeout=0).get("result", []))
        if etat.get("clavier") != 9:
            # Le nouveau clavier sera joint au prochain vrai message du bot.
            # Aucun message vide, promotionnel ou de démarrage n'est envoyé.
            etat["clavier"] = 9
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
                        + ("🎁 Ta position gratuite du jour est encore dispo\n" if cid not in etat.get("bienvenue", {}) else "")
                        + "💎 VIP 49,90 € / mois : toutes les positions + le coach"
                        + (f"\n👉 {etat['lien']}" if etat.get("lien") else "")))

    envois, derniers = [], {}
    calendrier(etat, int(time.time()))
    try:
        macro(etat)
    except Exception as ex:
        print("macro", ex)
    for nom_marche, pair in MARCHES.items():
        try:
            r = analyser(pair)
            r["tv_indicator_mtf"] = fetch_tv_mtf(pair)
            fusionne_lectures_tradingview(r)
        except Exception as ex:
            print(nom_marche, "erreur", ex); continue
        cle = etat.setdefault(nom_marche, {})
        tendance_armee(r, cle)
        r["annonce"] = annonce_proche(etat, int(time.time()))
        if nom_marche == "GOLD":
            ech = [v for t_, v in _CACHE.get("spot_hist", []) if t_ > cle.get("spot_t", 0)]
            cle["spot_t"] = time.time()
            if ech:
                r["spot_lo"], r["spot_hi"] = min(ech), max(ech)
        f_ = minutes_avant_fermeture_gold()
        r["fermeture"] = nom_marche == "GOLD" and (0 < f_ <= 35 or -120 <= f_ <= 0)   # jusqu'à 10 min après la réouverture
        r["news"] = news_txt(etat)
        try:
            r["macro_data"] = macro_confluence(etat, nom_marche, r)
            r["macro"] = contexte_macro(etat, nom_marche, r)
        except Exception as ex:
            print("macro analyse", nom_marche, ex)
            r["macro_data"] = {"disponible": False, "statut": "DONNÉES MACRO INDISPONIBLES"}
        ferme = "" if nom_marche == "BTC" or cme_ouvert(r["t"]) else "\n⚠️ Futures CME fermés en ce moment (Topstep) : signal à titre indicatif."
        envois += agent(nom_marche, r, cle, ferme)
        if TOKEN and cle.get("trade") and not cle["trade"].get("auto_fait"):
            cle["trade"]["auto_fait"] = True
            trx = cle["trade"]
            t_ = ia(etat, "Le bot vient d'entrer en position. Explique en bougies pourquoi c'est une bonne entrée et rappelle de mettre le SL tout de suite.",
                    dict(donnees_ia(nom_marche, r, cle), position={"sens": "LONG" if trx["d"] == 1 else "SHORT", "entrée": round(trx["e"], 2),
                                                                    "SL": round(trx["sl"], 2), "TP1": round(trx["tp1"], 2), "type": trx.get("src")}))
            if t_:
                envois.append(f"🧠 L'IA ALIGN sur cette entrée {ICONE.get(nom_marche, '')} {nom_marche}\n{t_}")
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
                apprendre(etat, trf, gain)
                publier_resultat(etat, nom_marche, trf, sortie, motif, gain)
                pr = trf.get("profil") or {}
                n_, w_ = stats_profil(pr, ("m", "type", "d")) if pr else (0, 0)
                envois.append(f"🧠 {ICONE.get(nom_marche, '')} {nom_marche} : je note ce {'TP ✅' if gain > 0 else 'SL ❌'}\n"
                              f"📚 {pr.get('type', 'position')} {'LONG' if pr.get('d') == 1 else 'SHORT'} en session {pr.get('session', '?')}\n"
                              f"🧠 Bilan de ce type : {w_}/{n_} gagnés\n"
                              + ("💡 Leçon : je serai plus prudent sur ce type de position" if gain <= 0 else "💪 Je garde ce type de position"))
                t_ = ia(etat, "La position est terminée. Tire UNE leçon simple et utile pour la prochaine fois (pourquoi TP ou pourquoi SL).",
                        {"marché": nom_marche, "résultat %": round(gain, 2), "motif": motif, "profil": pr, "bilan de ce type": f"{w_}/{n_}"})
                if t_:
                    envois.append(f"🧠 La leçon de l'IA ALIGN\n{t_}")
        derniers[nom_marche] = r; DERNIERS[nom_marche] = r
        synchroniser_veille_auto(etat, nom_marche, r)
        notifier_clotures(etat, nom_marche, r, cle)
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
                envoyer_analyse_a(etat, cid, nom_marche, r, cle)
        print(texte_etat(nom_marche, r), "\n")

    try:
        di = dxy_info(etat)
        if di and abs(di[1]) >= 0.25 and time.time() - etat.get("dxy_alerte_t", 0) > 7200:
            etat["dxy_alerte_t"] = time.time()
            bas_ = di[1] < 0
            envois.append(f"💵 DOLLAR EN FORTE {'BAISSE' if bas_ else 'HAUSSE'} — DXY {di[0]:.2f} ({di[1]:+.2f} % en {di[2]} min)\n"
                          f"🥇 GOLD : {'vent favorable au 🟩 LONG' if bas_ else 'frein pour le 🟩 LONG, prudence'}\n"
                          f"🟠 BTC : {'vent favorable au 🟩 LONG' if bas_ else 'frein pour le 🟩 LONG, prudence'}\n"
                          "🧭 Le bot n'entre toujours qu'avec 15 min / 1 h / 4 h alignées")
    except Exception as ex:
        print("alerte dxy", ex)
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
            for cid in destinataires_message(etat, chats, texte):
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
                maj_jauge(etat, nom_marche, derniers[nom_marche], etat[nom_marche], chats, etat.get("canal"))
                try:
                    maj_chronos(etat, nom_marche, derniers[nom_marche])
                except Exception as ex:
                    print("chronos", ex)
    journal_vider_sortants(etat)
    print(f"{len(envois)} signal(s) envoyé(s) à {len(chats)} téléphone(s)")
    sauver_etat(etat, chats)

STATE_SCHEMA_VERSION = 2

def charger_etat():
    """Charge l'état sans jamais repartir à zéro silencieusement si le fichier est abîmé."""
    if not os.path.exists(ETAT_FICHIER):
        return {"schema_version": STATE_SCHEMA_VERSION}
    try:
        with open(ETAT_FICHIER, "r", encoding="utf-8") as f:
            etat = json.load(f)
    except Exception as ex:
        raise RuntimeError(f"ÉTAT ALIGN ILLISIBLE — arrêt préventif, aucune donnée écrasée : {ex}") from ex
    if not isinstance(etat, dict):
        raise RuntimeError("ÉTAT ALIGN INVALIDE — arrêt préventif, aucune donnée écrasée")
    version = int(etat.get("schema_version", 1) or 1)
    if version > STATE_SCHEMA_VERSION:
        raise RuntimeError(f"ÉTAT ALIGN version {version} plus récente que ce bot ({STATE_SCHEMA_VERSION})")
    # Migration additive : on conserve toutes les clés historiques (positions, abonnés,
    # offset Telegram, suivis, résultats et journal) sans réinitialiser les instructions.
    etat.setdefault("journal_telegram", [])
    etat.setdefault("chats", [])
    etat["schema_version"] = STATE_SCHEMA_VERSION
    if version < STATE_SCHEMA_VERSION:
        print(f"STATE_MIGRATION={version}->{STATE_SCHEMA_VERSION} (conservation des données)", flush=True)
    return etat


def _sauver_etat_sous_verrou(etat, chats=None):
    """Écriture atomique : un arrêt du runner ne laisse pas un state.json tronqué."""
    if chats is not None:
        etat["chats"] = sorted(str(x) for x in chats)
    etat["schema_version"] = STATE_SCHEMA_VERSION
    journal_vider_sortants(etat)
    dossier = os.path.dirname(os.path.abspath(ETAT_FICHIER))
    temporaire = ETAT_FICHIER + ".tmp"
    with open(temporaire, "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False, separators=(",", ":"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporaire, ETAT_FICHIER)

def sauver_etat(etat, chats=None):
    """Empêche le worker du chronomètre de modifier l'état pendant l'écriture atomique."""
    with CHRONO_LOCK:
        return _sauver_etat_sous_verrou(etat, chats)


def main():
    etat = charger_etat()
    maintenant_paris = datetime.datetime.now(PARIS)
    print(f"ALIGN_TZ=Europe/Paris LOCAL_NOW={maintenant_paris.isoformat()} UTC_NOW={datetime.datetime.now(datetime.timezone.utc).isoformat()}", flush=True)
    chats = set(etat.get("chats", []))
    if os.environ.get("TELEGRAM_CHAT_ID"):
        chats.add(os.environ["TELEGRAM_CHAT_ID"].strip())
    if "proprio" not in etat:           # les téléphones déjà inscrits = le propriétaire (accès gratuit et permanent)
        etat["proprio"] = sorted(chats)
    if POSITIONS_GRATUITES and etat.get("prospects"):
        chats |= set(etat["prospects"]); etat["prospects"] = []

    # Worker indépendant : le chronomètre ne dépend plus de la durée d'un tour
    # d'analyse BTC/Gold, d'un appel IA ou d'une requête réseau lente.
    if TOKEN:
        threading.Thread(target=boucle_chronos, args=(etat,), name="ALIGN-Telegram-Chrono", daemon=True).start()

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
                maj = telegram("getUpdates", offset=etat.get("offset", 0), timeout=1).get("result", [])
            except Exception as ex:
                print("ecoute", ex); time.sleep(5); continue
            # Priorité au chronomètre : l'édition Telegram passe AVANT les callbacks
            # qui peuvent lancer une analyse IA ou une requête réseau plus lente.
            for marche, derniere in list(DERNIERS.items()):
                try:
                    maj_chronos(etat, marche, derniere)
                except Exception as ex:
                    print("tick chrono", marche, ex)
            for cid, mq in traiter(etat, chats, maj):
                envoyer_analyse(cid, etat, mq)
            # Le polling Telegram reste à 1 s ; l'horloge n'attend plus le traitement
            # des demandes d'analyse avant d'actualiser le message du compte à rebours.
            sauver_etat(etat, chats)
        if time.time() >= debut + DUREE_SEC:
            break
        if not TOKEN:
            time.sleep(max(0, prochain - time.time()))
    sauver_etat(etat, chats)

if __name__ == "__main__":
    main()
