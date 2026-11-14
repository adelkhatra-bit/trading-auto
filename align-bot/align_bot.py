#!/usr/bin/env python3
"""ALIGN MTF BOT — même logique que l'indicateur TradingView ALIGN MTF PRO.
Prix gratuits : BTC = Kraken XBTUSD, Gold = XAUUSD spot (bougies COMEX Yahoo recalées sur le prix spot Swissquote).
Tourne toutes les 5 minutes (GitHub Actions). Aucune dépendance externe."""
import json, os, re, time, hashlib, urllib.request, urllib.error, urllib.parse, datetime, threading, queue, signal
from zoneinfo import ZoneInfo
import sys
try:
    sys.stdout.reconfigure(line_buffering=True)   # les logs GitHub s’affichent tout de suite
except Exception:
    pass
PARIS = ZoneInfo("Europe/Paris")

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
ETAT_FICHIER = os.environ.get("STATE_FILE", "state.json")
TELEGRAM_UPDATES = queue.Queue()
TELEGRAM_POLL_STOP = threading.Event()
SHUTDOWN_REQUESTED = threading.Event()
CALLBACKS_ACKNOWLEDGED = set()
MARCHES = {"BTC": "XBTUSD", "GOLD": "XAUUSD", "NASDAQ": "NAS100"}  # BTC → FTMO (CFD 24/7) • GOLD → Topstep (MGC) / FTMO • NASDAQ → FX:NAS100 (TradingView)
MIN_ALIGN, MIN_SQZ, MARGE_ATR, GAIN_MIN = 8, 4, 0.5, 1.5   # = réglages par défaut de l'indicateur ALIGN MTF PRO v24
LIEN_RESULTATS = "https://t.me/+RajFd_hMgl1kNmQ0"     # groupe ALIGN Résultats (lien privé)
RISQUE_MAX = 1.5      # SL jamais plus loin que 1,5 ATR 15 min : pas de gros SL, on attend mieux
UT = ["1", "3", "5", "10", "15", "30", "45", "1h", "2h", "4h", "D"]   # 3 min comme l'indicateur TradingView (unité standard)
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
    symbol = {"XBTUSD": "BTCUSD"}.get(pair, pair.upper())
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
    return [dict(t=int(r[0]), o=float(r[1]), h=float(r[2]), l=float(r[3]), c=float(r[4]),
                 v=float(r[6]) if len(r) > 6 and r[6] not in (None, "") else None,
                 trades=int(r[7]) if len(r) > 7 and r[7] not in (None, "") else None,
                 volume_source=f"Kraken {pair}") for r in rows]

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
        volumes = q.get("volume") or []
        rows = [dict(t=int(t), o=o, h=h, l=l, c=cl,
                     v=float(volumes[i]) if i < len(volumes) and volumes[i] is not None else None,
                     volume_source="COMEX GC=F Yahoo proxy")
                for i, (t, o, h, l, cl) in enumerate(zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"]))
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
    out = [dict(t=b["t"], o=b["o"] + ecart, h=b["h"] + ecart, l=b["l"] + ecart, c=b["c"] + ecart,
                v=b.get("v"), trades=b.get("trades"),
                volume_source=b.get("volume_source") or "COMEX GC=F Yahoo proxy") for b in c[1]]
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
    out = [dict(t=b["t"], o=b["o"] + e, h=b["h"] + e, l=b["l"] + e, c=b["c"] + e,
                v=b.get("v"), trades=b.get("trades"),
                volume_source=b.get("volume_source") or "Kraken PAXG proxy") for b in c[1]]
    if interval == 1 and spot and out:
        t = int(time.time()) // 60 * 60
        if t > out[-1]["t"]:
            out.append(dict(t=t, o=out[-1]["c"], h=max(out[-1]["c"], spot), l=min(out[-1]["c"], spot), c=spot))
    return out

def yahoo_nasdaq(interval):
    """Bougies Nasdaq 100 (comme FX:NAS100 sur TradingView) : futures NQ=F Yahoo, recalés sur l'indice ^NDX.
    Le prix peut différer de quelques points selon le broker : les messages expliquent tout en bougies (mèches)."""
    if interval == 240:
        return regrouper(yahoo_nasdaq(60), 4, 3600)
    ui, rg, ttl = YAHOO[interval]
    c = _CACHE.get(("nq", interval))
    if not c or time.time() - c[0] > ttl:
        j = None
        for hote in ("query1", "query2"):
            try:
                j = http_json(f"https://{hote}.finance.yahoo.com/v8/finance/chart/NQ=F?interval={ui}&range={rg}")
                break
            except Exception as ex:
                print("yahoo nasdaq", hote, ex)
        if j is None:
            raise RuntimeError("Yahoo Nasdaq indisponible")
        res = j["chart"]["result"][0]; q = res["indicators"]["quote"][0]
        volumes = q.get("volume") or []
        rows = [dict(t=int(t), o=o, h=h, l=l, c=cl,
                     v=float(volumes[i]) if i < len(volumes) and volumes[i] is not None else None,
                     volume_source="CME NQ=F Yahoo proxy")
                for i, (t, o, h, l, cl) in enumerate(zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"]))
                if None not in (o, h, l, cl)]
        _CACHE[("nq", interval)] = (time.time(), rows[:-1][-720:], res["meta"].get("regularMarketPrice") or rows[-1]["c"])
        c = _CACHE[("nq", interval)]
    # Écart futures / indice (comme le NAS100 de TradingView) : mesuré en direct pendant la séance US, gardé ensuite
    nq_live = nasdaq_direct()
    maintenant_paris = datetime.datetime.now(PARIS)
    seance = maintenant_paris.weekday() < 5 and (15, 35) <= (maintenant_paris.hour, maintenant_paris.minute) <= (21, 55)
    if seance and nq_live and time.time() - _CACHE.get("ndx_t", 0) > 300:
        _CACHE["ndx_t"] = time.time()
        try:
            ndx = float(http_json("https://scanner.tradingview.com/symbol?symbol=NASDAQ:NDX&fields=close")["close"])
            brut = ndx - nq_live
            ancien = _CACHE.get("ecart_ndx")
            _CACHE["ecart_ndx"] = brut if ancien is None or abs(brut - ancien) > 150 else ancien * 0.8 + brut * 0.2
        except Exception as ex:
            print("indice ndx", ex)
    e = _CACHE.get("ecart_ndx", 0.0)
    out = [dict(t=b["t"], o=b["o"] + e, h=b["h"] + e, l=b["l"] + e, c=b["c"] + e, v=b.get("v"),
                volume_source=b.get("volume_source") or "CME NQ=F Yahoo proxy") for b in c[1]]
    if interval == 1 and nq_live and out:
        # Dernière minute = prix EN DIRECT (Yahoo a ~10 min de retard)
        t = int(time.time()) // 60 * 60
        p_ = nq_live + e
        if t > out[-1]["t"]:
            out.append(dict(t=t, o=out[-1]["c"], h=max(out[-1]["c"], p_), l=min(out[-1]["c"], p_), c=p_))
    return out

def nasdaq_direct():
    """Prix NQ en direct (gratuit, sans clé), mis en cache 5 s ; None si indisponible."""
    c = _CACHE.get("nq_live")
    if c and time.time() - c[0] < 5:
        return c[1]
    try:
        v = float(http_json("https://scanner.tradingview.com/symbol?symbol=CME_MINI:NQ1%21&fields=close")["close"])
    except Exception as ex:
        print("nasdaq direct", ex)
        return c[1] if c else None
    _CACHE["nq_live"] = (time.time(), v)
    return v

def bougies(pair, interval):
    """Source des bougies : Kraken pour le BTC ; pour le Gold, PAXG recalé sur le spot XAUUSD (secours : bougies COMEX)."""
    if pair == "NAS100":
        return yahoo_nasdaq(interval)
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
            "v": sum(float(x.get("v") or 0) for x in groupe) if any(x.get("v") is not None for x in groupe) else None,
            "trades": sum(int(x.get("trades") or 0) for x in groupe) if any(x.get("trades") is not None for x in groupe) else None,
            "volume_source": next((x.get("volume_source") for x in groupe if x.get("volume_source")), None),
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
    """RSI de Wilder identique à ta.rsi : la 1re variation est la barre 1 (change() = na sur la barre 0), graine = moyenne simple."""
    if len(c) < 2:
        return [None] * len(c)
    up = [max(c[i] - c[i - 1], 0) for i in range(1, len(c))]
    dn = [max(c[i - 1] - c[i], 0) for i in range(1, len(c))]
    ru, rd = rma(up, n), rma(dn, n)
    return [None] + [None if u is None or d is None else (100 if d == 0 else 100 - 100 / (1 + u / d)) for u, d in zip(ru, rd)]

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

# ═══ v24.3 — jumeau EXACT de f_struct() de l'indicateur « ALIGN MTF PRO (Inside) » : FVG non comblées + mèches, sur UNE unité de temps ═══
# Le bot donne la même entrée / le même SL / les mêmes TP que le graphique quand on se met sur cette unité (1 min → structure 3 min, comme le Pine).
UT_FVG = {"SCALPING": "3"}   # PLAN UNIQUE : structure 5 min (SCALP : 3 min, vue 1 min comme le Pine) — fini les plans 1h aux zones de 600 points
PLAN_VUE = {"SCALPING": "1 min"}   # vue à mettre sur TradingView (sinon 5 min)
# La vue à mettre sur TradingView = HB_UNITE_VALIDATION (SWING 1h, DAY 5 min, SCALPING 1 min) : même zone, même trait « Clôture … », même entrée / SL / TP.
UT_FVG_NOM = {"1h": "1h", "5": "5 min", "3": "3 min", "15": "15 min"}
UT_FVG_BARS = {"1h": "b1h", "5": "b5", "3": "b3", "15": "b15"}

def structure_fvg(bars):
    """(rTop, rBot, gTop, gBot, dernier plus haut, dernier plus bas, ATR, clôture) — même calcul que f_struct() du Pine v24.3 :
    FVG ≥ 0,3 ATR gardées tant qu'une clôture ne les a pas traversées (30 max par côté), la plus proche de chaque côté ;
    plus haut / plus bas = dernier pivot 5-5 (ou les 4 dernières bougies si elles vont plus loin)."""
    if not bars or len(bars) < 20:
        return None
    at = atr(bars, 14)
    rT, rB, gT, gB, rO, gO = [], [], [], [], [], []      # rO / gO = ORDER BLOCK (haut, bas) de chaque FVG (v24.4, comme le Pine)
    haussiere = lambda y: y["c"] > y["o"]
    for i in range(len(bars)):
        x = bars[i]; aF = at[i]
        if i >= 2 and aF is not None:
            if x["h"] < bars[i - 2]["l"] and bars[i - 2]["l"] - x["h"] >= 0.3 * aF:
                rT.append(bars[i - 2]["l"]); rB.append(x["h"])
                k_ = 2 if haussiere(bars[i - 2]) else 3 if i >= 3 and haussiere(bars[i - 3]) else 2
                rO.append((bars[i - k_]["h"], bars[i - k_]["l"]))
            if x["l"] > bars[i - 2]["h"] and x["l"] - bars[i - 2]["h"] >= 0.3 * aF:
                gT.append(x["l"]); gB.append(bars[i - 2]["h"])
                k_ = 2 if bars[i - 2]["c"] < bars[i - 2]["o"] else 3 if i >= 3 and bars[i - 3]["c"] < bars[i - 3]["o"] else 2
                gO.append((bars[i - k_]["h"], bars[i - k_]["l"]))
        for k in range(len(rT) - 1, -1, -1):
            if x["c"] > rT[k]:
                del rT[k], rB[k], rO[k]
        for k in range(len(gB) - 1, -1, -1):
            if x["c"] < gB[k]:
                del gT[k], gB[k], gO[k]
        del rT[:-30], rB[:-30], rO[:-30], gT[:-30], gB[:-30], gO[:-30]
    rTop = rBot = gTop = gBot = None
    rOb = gOb = (None, None)
    for t_, b_, o_ in zip(rT, rB, rO):
        if rBot is None or b_ < rBot:
            rBot, rTop, rOb = b_, t_, o_
    for t_, b_, o_ in zip(gT, gB, gO):
        if gTop is None or t_ > gTop:
            gTop, gBot, gOb = t_, b_, o_
    ph = pl = None
    for i in range(5, len(bars) - 5):
        fen = bars[i - 5:i + 6]
        if bars[i]["h"] == max(y["h"] for y in fen):
            ph = bars[i]["h"]
        if bars[i]["l"] == min(y["l"] for y in fen):
            pl = bars[i]["l"]
    hH = max(ph if ph is not None else bars[-1]["h"], max(y["h"] for y in bars[-4:]))
    lL = min(pl if pl is not None else bars[-1]["l"], min(y["l"] for y in bars[-4:]))
    return (rTop, rBot, gTop, gBot, hH, lL, at[-1], bars[-1]["c"], rOb[0], rOb[1], gOb[0], gOb[1])

SL_FVG_MARGE = 0.3   # SL un peu plus large derrière la mèche (0,15 → 0,3 ATR) : moins de SL touchés de justesse — identique au Pine
SL_FVG_MIN = 1.0     # distance mini entrée → SL (0,8 → 1 ATR)

def plan_fvg(d, st, ent, sl, tp1, tp2, ut_nom="", tick=0.01):
    """Entrée / SL / TP1 / TP2 de l'indicateur v24.3 sur l'unité affichée (règle identique au Pine). None = le Pine garde son plan d'origine.
    SHORT : entrée = bas de la FVG rouge la plus proche ; SL = au-dessus de la mèche du dernier plus haut / du haut de la FVG (≥ 0,8 ATR) ;
    TP1 = FVG verte ou dernier plus bas (≥ 1,5 x le risque), TP2 = le niveau suivant. LONG : l'inverse."""
    if d not in (1, -1) or not st:
        return None
    rTop, rBot, gTop, gBot, swH, swL, aS, cl = st[:8]
    obRH, obRL, obGH, obGL = (tuple(st[8:12]) + (None,) * 4)[:4]
    if not aS:
        return None
    m = max(SL_FVG_MARGE * aS, 3 * tick)
    if d == -1:
        if rBot is None or rBot < cl - 0.5 * aS:
            return None
        e = rBot if obRL is None else max(rBot, obRL)                   # entrée sur l'ORDER BLOCK (bord proche) au-dessus de la FVG
        s = max(max(swH, rTop, obRH if obRH is not None else rTop) + m, e + SL_FVG_MIN * aS)
        rq = 1.5 * (s - e)
        c1 = gTop if gTop is not None and e - gTop >= rq else None
        c2 = swL if e - swL >= rq else None
        if c1 is None and c2 is None:
            t1, n1 = (tp1, "objectif du plan") if tp1 is not None and e - tp1 >= rq else (e - 2 * (s - e), "2 x le risque")
        elif c1 is None or c2 is None:
            t1, n1 = (c1, f"FVG verte {ut_nom}") if c1 is not None else (c2, f"dernier plus bas {ut_nom}")
        else:
            t1, n1 = (c1, f"FVG verte {ut_nom}") if c1 >= c2 else (c2, f"dernier plus bas {ut_nom}")
        if c1 is None or c2 is None:
            t2 = min(t1, tp1) if tp1 is not None else t1
            n2 = "objectif du plan" if t2 != t1 else n1
        else:
            t2 = min(c1, c2); n2 = f"FVG verte {ut_nom}" if t2 == c1 else f"dernier plus bas {ut_nom}"
        src = f"{'FVG rouge' if obRL is None else 'Order block + FVG rouge'} {ut_nom}"
    else:
        if gTop is None or gTop > cl + 0.5 * aS:
            return None
        e = gTop if obGH is None else min(gTop, obGH)
        s = min(min(swL, gBot, obGL if obGL is not None else gBot) - m, e - SL_FVG_MIN * aS)
        rq = 1.5 * (e - s)
        c1 = rBot if rBot is not None and rBot - e >= rq else None
        c2 = swH if swH - e >= rq else None
        if c1 is None and c2 is None:
            t1, n1 = (tp1, "objectif du plan") if tp1 is not None and tp1 - e >= rq else (e + 2 * (e - s), "2 x le risque")
        elif c1 is None or c2 is None:
            t1, n1 = (c1, f"FVG rouge {ut_nom}") if c1 is not None else (c2, f"dernier plus haut {ut_nom}")
        else:
            t1, n1 = (c1, f"FVG rouge {ut_nom}") if c1 <= c2 else (c2, f"dernier plus haut {ut_nom}")
        if c1 is None or c2 is None:
            t2 = max(t1, tp1) if tp1 is not None else t1
            n2 = "objectif du plan" if t2 != t1 else n1
        else:
            t2 = max(c1, c2); n2 = f"FVG rouge {ut_nom}" if t2 == c1 else f"dernier plus haut {ut_nom}"
        src = f"{'FVG verte' if obGH is None else 'Order block + FVG verte'} {ut_nom}"
    if d * (t2 - t1) < 0:
        t2, n2 = t1, n1
    if d * (e - s) <= 0 or d * (t1 - e) <= 0:
        return None                                         # sécurité du Pine : SL / TP du mauvais côté → plan d'origine
    za, zb = (e, s - 0.25 * (s - e)) if d == -1 else (s + 0.25 * (e - s), e)
    return dict(e=e, sl=s, tp1=t1, n1=n1, tp2=t2, n2=n2, za=za, zb=zb, src=src)

# ═══ Même prix que le graphique de l'utilisateur : le dernier prix de SON symbole TradingView sert d'étalon ═══
# Les bougies gratuites (Kraken, PAXG / COMEX, NQ futures) gardent leur forme ; on les décale de l'écart mesuré en direct avec le symbole
# TradingView (CRYPTO:BTCUSD, FOREXCOM:XAUUSD, FX:NAS100 — liste de secours si un symbole ne répond pas). Écart lissé, plafonné à 2 %.
TV_ETALON = {"XBTUSD": ("CRYPTO:BTCUSD",), "XAUUSD": ("FOREXCOM:XAUUSD", "FX:XAUUSD", "OANDA:XAUUSD"),
             "NAS100": ("FX:NAS100", "CAPITALCOM:US100", "PEPPERSTONE:NAS100", "OANDA:NAS100USD")}
TV_ETALON_TTL = 30

def prix_tradingview(pair):
    """Dernier prix du symbole TradingView de l'utilisateur (cache 30 s) ; None si aucun symbole ne répond."""
    c = _CACHE.get(("tv_prix", pair))
    if c and time.time() - c[0] < TV_ETALON_TTL:
        return c[1]
    v = None
    for sym in TV_ETALON.get(pair, ()):
        try:
            v = float(http_json("https://scanner.tradingview.com/symbol?symbol=" + urllib.parse.quote(sym, safe="") + "&fields=close")["close"])
            break
        except Exception:
            continue
    _CACHE[("tv_prix", pair)] = (time.time(), v)
    return v

def ecart_tradingview(pair, dernier):
    """Écart lissé (prix TradingView − prix de nos bougies). 0 si indisponible ou aberrant (> 2 %)."""
    ref = prix_tradingview(pair)
    ancien = _CACHE.get(("tv_ecart", pair))
    if ref is None or not dernier:
        return ancien or 0.0
    brut = ref - dernier
    if abs(brut) > 0.02 * abs(ref):
        return ancien or 0.0
    lisse = brut if ancien is None else 0.7 * ancien + 0.3 * brut
    _CACHE[("tv_ecart", pair)] = lisse
    return lisse

def decaler(bars, e):
    if not e:
        return bars
    return [dict(b, o=b["o"] + e, h=b["h"] + e, l=b["l"] + e, c=b["c"] + e) for b in bars]

def analyser(pair, mem=None):
    """Télécharge les bougies puis calcule l'analyse (logique identique à l'indicateur Pine ALIGN MTF PRO v24).
    mem = mémoire persistante du marché (sens stable, plan figé, retournement) ; sans mémoire : calcul instantané."""
    m1, m5, m15, h1, h4, d1 = (bougies(pair, i) for i in (1, 5, 15, 60, 240, 1440))
    if pair == "XBTUSD":
        m1 = direct_btc(m1, pair)
    S = dict(m1=m1, m5=m5, m15=m15, m30=bougies(pair, 30), h1=h1, h4=h4, d1=d1, w1=bougies(pair, 10080))
    try:
        e = ecart_tradingview(pair, m1[-1]["c"] if m1 else None)
    except Exception as ex:
        print("étalon TradingView", pair, type(ex).__name__)
        e = 0.0
    if e:
        S = {k: decaler(v, e) for k, v in S.items()}
    r = analyser_avec_memoire(S, mem)
    r["ecart_tv"] = e
    return r

def dir_stable_pas(stable, brut, d15, d60):
    """Anti-parasites de l'indicateur : le sens ne change qu'à la clôture d'une bougie 15 min, et seulement si le 15 min ou la 1h confirme."""
    if stable == 0:
        return brut
    if brut != 0 and brut != stable and (d15 == brut or d60 == brut):
        return brut
    if brut == 0 and d15 != stable and d60 != stable:
        return 0
    return stable

def zone_pine(b15, d, e, sl):
    """Zone verte + Fibonacci de l'indicateur : 24 bougies 15 min CLÔTURÉES avant la courante, entrée et stop figés."""
    z = b15[-25:-1]
    if len(z) < 24:
        return None
    fH, fL = max(x["h"] for x in z), min(x["l"] for x in z)
    fR = fH - fL
    if fR <= 0 or e is None or sl is None:
        return None
    f = (lambda k: fL + k * fR) if d == -1 else (lambda k: fH - k * fR)
    f50, f618, f786 = f(0.5), f(0.618), f(0.786)
    if d == -1:
        zmin, zmax = min(e, f50), min(max(e, f786), sl - 0.25 * (sl - e))
    else:
        zmin, zmax = max(min(e, f786), sl + 0.25 * (e - sl)), max(e, f50)
    za, zb = min(zmin, zmax), max(zmin, zmax)
    return dict(za=za, zb=zb, f50=f50, f618=f618, f786=f786, zmil=(za + zb) / 2)

def plan_pine(d, cl, a, a15, tous_niv, hau1, bas1, bas10, haut10, ut_sl, ut_tp):
    """Plan entrée / TP1 / TP2 / SL : transcription de f_plan() de l'indicateur Pine v24.
    a = ATR 14 de la vue 15 min ; a15 = ATR 14 de la bougie 15 min précédente."""
    cote = [v for v, n in tous_niv if n in ut_sl and d * (cl - v) > a * 0.3]
    sb = (max(cote) if d == 1 else min(cote)) if cote else (bas1[0] if d == 1 and bas1 else hau1[0] if d == -1 and hau1 else cl - d * 1.5 * a)
    swing = bas10 - a * 0.35 if d == 1 else haut10 + a * 0.35
    sl = min(sb - a * 0.3, swing) if d == 1 else max(sb + a * 0.3, swing)
    e_lim = sb + a * 0.3 if d == 1 else sb - a * 0.3
    e = min(cl, max(e_lim, sl + a * 0.5)) if d == 1 else max(cl, min(e_lim, sl - a * 0.5))
    aP = max(a, a15 if a15 is not None else a)
    e = min(e, sl + aP * 1.5) if d == 1 else max(e, sl - aP * 1.5)          # jamais un SL de plus de 1,5 bougie moyenne
    mini = max(SL_RISQUE_MIN_ATR * aP, cl * SL_RISQUE_MIN_PCT)
    sl = min(sl, e - mini) if d == 1 else max(sl, e + mini)
    risque = abs(e - sl)
    cibles_niv = [(v, n) for v, n in tous_niv if n in ut_tp]
    cibles = sorted([(v, n) for v, n in cibles_niv if d * (v - e) >= risque * GAIN_MIN], key=lambda z: d * z[0])
    t1 = cibles[0] if cibles else (e + d * risque * GAIN_MIN, f"projection {GAIN_MIN} x le risque")
    loin = sorted([z for z in cibles_niv if d * (z[0] - e) >= abs(t1[0] - e) + a], key=lambda z: d * z[0])
    t2 = loin[0] if loin else (e + d * risque * (GAIN_MIN + 2), f"projection {GAIN_MIN + 2} x le risque")
    return dict(e=e, sl=sl, tp1=t1[0], n1=t1[1], tp2=t2[0], n2=t2[1], rr=abs(t1[0] - e) / max(risque, 1e-9), marche=e == cl)

def _structures_ut(series):
    out = {}
    for k in UT_FVG_NOM:
        try:
            out[k] = structure_fvg(series.get(k) or [])
        except Exception as ex:
            print("structure_fvg", k, type(ex).__name__, ex)
            out[k] = None
    return out

def calculer_analyse(S, stable=None, comp_prev=None):
    """Calcul pur à partir des bougies S (m1, m5, m15, m30, h1, h4, d1, w1). Aucun accès réseau."""
    m1, m5, m15, h1, h4, d1, w1 = (S[k] for k in ("m1", "m5", "m15", "h1", "h4", "d1", "w1"))
    series = {"1": m1, "3": regrouper(m1, 3, 60), "5": m5, "10": regrouper(m5, 2, 300), "15": m15,
              "30": S["m30"], "45": regrouper(m15, 3, 900), "1h": h1, "2h": regrouper(h1, 2, 3600), "4h": h4, "D": d1}
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
    tous_niv = [(v, n) for v, n in zip(niv, noms) if v is not None]
    dW_ = etat_ut(w1)[0] if len(w1) >= 50 else 0
    a15 = atr(b, 14)[-2] if len(b) >= 16 else None
    bas10, haut10 = min(x["l"] for x in b[-10:]), max(x["h"] for x in b[-10:])
    def plan(d, strat_rng=None):
        ut_sl, ut_tp = niveaux_strategie(strat_rng or "")
        return plan_pine(d, cl, a, a15, tous_niv, hau1, bas1, bas10, haut10, ut_sl, ut_tp)

    fortHaut = rsiAchat and rsiOB < 3 and bull > bear and bull >= MIN_ALIGN - 2 and (comp >= MIN_SQZ or bull >= MIN_ALIGN)
    fortBas = rsiVente and rsiOS < 3 and bear > bull and bear >= MIN_ALIGN - 2 and (comp >= MIN_SQZ or bear >= MIN_ALIGN)
    explHaut = sqzC1 == 1 and sqzC == 0 and mom > 0 and bull > bear
    explBas = sqzC1 == 1 and sqzC == 0 and mom < 0 and bear > bull
    sigHaut = ((fortHaut or explHaut) and longT >= 1) or (zoneHaut and longT >= 0)
    sigBas = ((fortBas or explBas) and longT <= -1) or (zoneBas and longT <= 0)
    # v24.1 (= indicateur) : la tendance des grosses UT passe AVANT une zone de retournement isolée
    dirBrut = 1 if longT >= 2 else -1 if longT <= -2 else 1 if zoneHaut else -1 if zoneBas else 1 if retHaut else -1 if retBas else sens
    dirPlan = dirBrut if stable is None else stable
    strat_plan = strategie_alignement(dirs, dirPlan, etat_ut(w1)[0] if len(w1) >= 50 else 0)[0]
    nom = ("★ ACHAT FORT" if fortHaut else "EXPLOSION ▲" if explHaut else "ZONE DE REBOND ▲") if sigHaut else \
          ("★ VENTE FORTE" if fortBas else "EXPLOSION ▼" if explBas else "ZONE DE RETOURNEMENT ▼") if sigBas else ""
    # ═══ STRATÉGIE : 4h = tendance principale, 1h = confirmation ═══
    d1h, d4h = dirs[7], dirs[9]
    # Le 15m reste informatif et ne bloque jamais un signal.
    confirme = d4h if d4h != 0 and d1h == d4h else 0
    # Contexte Daily / Weekly : où est le prix dans sa zone (0 = tout en bas, 1 = tout en haut)
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
                dirPlan=dirPlan, dirBrut=dirBrut, strat=strat_plan,
                plan=plan(dirPlan if dirPlan else 1, strat_plan), planH=plan(1), planB=plan(-1), rC=rC,
                dirW=dW_, ohlc15=b[-30:], b3=series["3"][-80:], atr3=(atr(series["3"], 14)[-1] if len(series["3"]) >= 16 else None),
                struct_ut=_structures_ut(series))

def analyser_avec_memoire(S, mem=None):
    """Sens stable, plan figé et retournement exactement comme l'indicateur (vue 15 min = unité de référence du bot).
    À chaque clôture 15 min : le sens stable avance, puis le plan est recalculé (entrée / TP1 / TP2 / SL figés
    jusqu'à la clôture suivante). Le SL franchi à la clôture annule la position et ouvre un RETOURNEMENT."""
    m15 = S["m15"]
    if mem is None or len(m15) < 3:
        r = calculer_analyse(S)
        r["pine"] = None
        return r
    t = m15[-1]["t"]
    if mem.get("bar_t") is None:
        r0 = calculer_analyse(S)
        mem.update(bar_t=t, stable=r0["dirBrut"], comp=r0["comp"], comp_prev=None, ret_dir=0, ret_age=0)
        mem.update(figer_plan(r0, r0["dirBrut"]))
    elif t != mem["bar_t"]:
        # une bougie 15 min vient de se clôturer : on relit l'état à sa clôture (dernier instant de cette bougie)
        S2 = dict(S, m15=m15[:-1])
        rc = calculer_analyse(S2, stable=mem["stable"], comp_prev=mem.get("comp_prev"))
        sl_old, dir_fig = mem.get("sl"), mem.get("dir_fig") or 0
        franchi = sl_old is not None and ((dir_fig == -1 and rc["prix"] > sl_old) or (dir_fig == 1 and rc["prix"] < sl_old))
        stable = dir_stable_pas(mem["stable"], rc["dirBrut"], rc["dirs"][4], rc["dirs"][7])
        mem["comp_prev"] = rc["comp"]
        if franchi:
            mem["ret_dir"], mem["ret_age"] = -dir_fig, 0
        elif mem.get("ret_dir"):
            mem["ret_age"] = mem.get("ret_age", 0) + 1
            if mem["ret_age"] > 40:
                mem["ret_dir"] = 0
        mem["stable"], mem["comp"], mem["bar_t"] = stable, rc["comp"], t
        rc = calculer_analyse(S2, stable=stable, comp_prev=mem["comp_prev"])
        mem.update(figer_plan(rc, stable))
    r = calculer_analyse(S, stable=mem["stable"], comp_prev=mem.get("comp_prev"))
    mem["comp"] = r["comp"]
    r["plan_fige"] = dict(e=mem["ent"], sl=mem["sl"], tp1=mem["tp1"], tp2=mem["tp2"], n1=mem["n1"], n2=mem["n2"],
                          rr=abs(mem["tp1"] - mem["ent"]) / max(abs(mem["ent"] - mem["sl"]), 1e-9),
                          marche=mem["ent"] == r["prix"], d=mem["dir_fig"], strat=mem["strat_fig"])
    r["plan"] = r["plan_fige"]
    r["zone_pine"] = zone_pine(S["m15"], r["dirPlan"], mem["ent"], mem["sl"])
    r["ret_dir"] = mem.get("ret_dir", 0)
    r["ret_conf"] = bool(r["ret_dir"]) and r["dirPlan"] == r["ret_dir"]
    r["nVoy"] = sum(1 for k in range(5) if r["dirPlan"] != 0 and r["dirs"][k] == -r["dirPlan"])
    r["pine"] = mem
    r["niveaux_ut"] = [(v[0], nom) for nom, quatre in niveaux_structure_ut(r).items() for v in quatre if v]      # visibles, mais jamais mélangés à r["niveaux"] (TP / plan)
    r["sniper"] = entree_sniper(r)
    return r

# ───────── ENTRÉE SNIPER EN CASCADE (M1 → M3 → M5 → M15) ─────────
# Quand le prix entre dans la zone d'entrée du plan (SWING / INTRADAY…), on descend en UT : pour chaque UT le niveau d'entrée est le DERNIER PLUS HAUT
# de structure de CETTE UT (vente) / le dernier plus bas (achat), pas le haut de la zone. Cascade : la plus petite UT dont le dernier plus haut est SOUS celui
# de l'UT supérieure. Alignement d'entrée = rejet confirmé sous ce niveau sur M1 ET M3 (M5 en plus si possible) : mèche + clôture sous le niveau et sous la bande
# de Bollinger haute (ou chandelle de retournement). Une clôture au-dessus du niveau l'annule : on remonte d'une UT. Le plan n'est jamais remplacé : message en plus.
SNIPER_MARGE_ATR3 = 0.5         # marge du SL derrière la mèche (en ATR M3)

def niveaux_ut(bars, g=5):
    """Niveaux de structure d'une UT, calculés comme les niveaux 15 min / 1 h / 4 h / Daily de l'indicateur (pivots 5-5, deux derniers hauts et deux derniers bas) :
    (dernier plus haut, dernier plus bas, avant-dernier plus haut, avant-dernier plus bas), chacun (niveau, indice de bougie) ou None."""
    hs, ls = [], []
    for i in range(g, len(bars) - g):
        if bars[i]["h"] == max(x["h"] for x in bars[i - g:i + g + 1]):
            hs.append((bars[i]["h"], i))
        if bars[i]["l"] == min(x["l"] for x in bars[i - g:i + g + 1]):
            ls.append((bars[i]["l"], i))
    return (hs[-1] if hs else None, ls[-1] if ls else None, hs[-2] if len(hs) > 1 else None, ls[-2] if len(ls) > 1 else None)

def niveaux_structure_ut(r):
    """Niveaux M1 / M3 / M5 (même méthode que les niveaux existants) : UNIQUEMENT pour l'entrée sniper et son SL — jamais pour les TP ni le plan."""
    m1 = (r.get("m1") or [])[:-1]
    uts = {"M1": m1, "M3": r.get("b3") or [], "M5": (r.get("b5") or [])[:-1]}
    return {nom: niveaux_ut(bars) for nom, bars in uts.items()}

def _rejet(bars, d, niveau, a):
    """Rejet confirmé sur les 3 dernières bougies clôturées : mèche qui touche (ou frôle) le niveau, CLÔTURE du bon côté, et (mèche franche OU
    clôture hors de la bande de Bollinger OU chandelle de retournement). Retourne la bougie de rejet la plus récente ou None."""
    cl = [x["c"] for x in bars[-20:]]
    bb = None
    if len(cl) == 20:
        m = sum(cl) / 20
        sd = (sum((v - m) ** 2 for v in cl) / 20) ** 0.5
        bb = m + 2 * sd if d == -1 else m - 2 * sd
    for k in range(len(bars) - 1, max(len(bars) - 4, 0), -1):
        x, pre = bars[k], bars[k - 1]
        rng = max(x["h"] - x["l"], 1e-9)
        if d == -1:
            ok = x["h"] >= niveau - 0.5 * a and x["c"] < niveau
            meche = (x["h"] - max(x["o"], x["c"])) >= 0.4 * rng
            hors_bb = bb is not None and x["c"] < bb
            retour = x["c"] < x["o"] and x["o"] >= pre["c"] and x["c"] < pre["o"]
        else:
            ok = x["l"] <= niveau + 0.5 * a and x["c"] > niveau
            meche = (min(x["o"], x["c"]) - x["l"]) >= 0.4 * rng
            hors_bb = bb is not None and x["c"] > bb
            retour = x["c"] > x["o"] and x["o"] <= pre["c"] and x["c"] > pre["o"]
        if ok and (meche or hors_bb or retour):
            return x
    return None

def entree_sniper(r):
    return _sniper(r)[0]

def _sniper(r):
    """(proposition ou None, raison du refus) : la raison sert au diagnostic du rejeu, jamais à Telegram."""
    d = r.get("dirPlan") or 0
    dirs, a3, a15, a5, zp = r.get("dirs") or [], r.get("atr3"), r.get("atr"), r.get("atr5") or r.get("atr"), r.get("zone_pine")
    m1, b3 = r.get("m1") or [], r.get("b3") or []
    b5, b15 = (r.get("b5") or [])[:-1], (r.get("b15") or [])[:-1]          # la dernière bougie M5 / M15 est en formation
    if d not in (1, -1) or len(dirs) < 11 or not a3 or not a15 or not zp or len(m1) < 40 or len(b3) < 12 or len(b5) < 8 or len(b15) < 5:
        return None, f"DONNEES/PLAN absents (dirPlan={d}, zone={'oui' if zp else 'non'}, b3={len(b3)}, b5={len(b5)}, b15={len(b15)})"
    if (r["bull"] if d == 1 else r["bear"]) < MIN_ALIGN or r.get("sens") != d or dirs[9] == -d or dirs[7] == -d:
        return None, f"CONTEXTE_HTF refusé (UT alignées {(r['bull'] if d == 1 else r['bear'])}/11, sens={r.get('sens')}, 4h={dirs[9]}, 1h={dirs[7]})"
    prix = m1[-1]["c"]
    if not (zp["za"] - 0.5 * a15 <= prix <= zp["zb"] + 0.5 * a15):
        return None, f"HORS_ZONE : prix {prix:.2f} hors zone du plan {zp['za']:.2f}–{zp['zb']:.2f}"
    m1c = m1[:-1]
    a1 = atr(m1c, 14)[-1] if len(m1c) >= 16 else None
    if not a1:
        return None, "ATR_M1 indisponible"
    uts = [("M1", m1c, a1), ("M3", b3, a3), ("M5", b5, a5), ("M15", b15, a15)]
    niv, structure = [], niveaux_structure_ut(dict(r, m1=m1))
    for nom, bars, a in uts:
        quatre = structure[nom] if nom in structure else niveaux_ut(bars)
        piv = quatre[0] if d == -1 else quatre[1]
        L, i = piv if piv else (None, None)
        valide = L is not None and (L - prix) * (-d) >= 0 and not any((y["c"] - L) * (-d) > 0 for y in bars[i + 1:])    # pas de clôture au-delà : sinon annulé
        niv.append((nom, L if valide else None, bars, a))
    choisi = None
    for k, (nom, L, bars, a) in enumerate(niv):                              # cascade : la plus petite UT sous le dernier plus haut de l'UT supérieure
        if L is None:
            continue
        sup = next((x[1] for x in niv[k + 1:] if x[1] is not None), None)
        if sup is None or (sup - L) * (-d) >= 0:                       # sous (ou sur) le dernier plus haut de l'UT supérieure : même structure
            choisi = (nom, L, a)
            break
    if not choisi:
        return None, "CASCADE : aucun dernier plus haut/bas valide sur M1/M3/M5/M15 (cascade)"
    ut, L, a_ut = choisi
    rej = {nom: _rejet(bars, d, L, a) for nom, _, bars, a in niv if nom in ("M1", "M3", "M5")}
    if rej["M1"] is None or rej["M3"] is None:
        return None, f"REJET : pas de rejet confirmé sous {L:.2f} ({ut}) : M1={'oui' if rej['M1'] else 'non'} M3={'oui' if rej['M3'] else 'non'}"
    e = rej["M1"]["c"]
    meche = max([y["h"] if d == -1 else -y["l"] for y in m1c[-12:] + list(b3[-4:]) if abs((y["h"] if d == -1 else y["l"]) - L) <= 3 * a3] + [L if d == -1 else -L])
    meche = meche if d == -1 else -meche
    sl = meche - d * SNIPER_MARGE_ATR3 * a3
    mini = max(a3, e * SL_RISQUE_MIN_PCT)
    if abs(sl - e) < mini:
        sl = e - d * mini
    risque = abs(e - sl)
    if (prix - sl) * d <= 0:
        return None, "SL_FRANCHI"
    plan = r.get("plan") or {}
    tp_plan = plan.get("tp1") if plan.get("d", d) == d and plan.get("tp1") is not None and d * (plan["tp1"] - e) > 0 else None
    cibles = sorted([(v, n) for v, n in (r.get("niveaux") or []) if n in ("15m", "1h", "4h", "Daily") and d * (v - e) >= risque * GAIN_MIN and (tp_plan is None or d * (tp_plan - v) >= 0)],
                    key=lambda z: d * z[0])
    tp1, n1 = cibles[0] if cibles else (e + d * risque * GAIN_MIN, f"projection {GAIN_MIN} x le risque")      # TP1 intermédiaire réaliste
    tp_final = tp_plan if tp_plan is not None else (cibles[1][0] if len(cibles) > 1 else e + d * risque * (GAIN_MIN + 2))
    za, zb = sorted((e, L))
    return (dict(d=d, ut=ut, e=e, za=za, zb=zb, sl=sl, tp1=tp1, n1=n1, tp2=tp_final, n2=("plan " + (r.get("strat") or "")).strip() if tp_plan is not None else "projection",
                rr=abs(tp1 - e) / risque, rr_plan=abs(tp_final - e) / risque, niveau=L, src="dernier " + ("plus haut " if d == -1 else "plus bas ") + ut, meche=meche,
                rejets=[n for n, x in rej.items() if x is not None], marche=True, t=m1[-1]["t"]), "")

def simuler_sniper(sn, m1_futur, duree_min=240):
    """Que serait-il arrivé ? Entrée « au rejet » (marché) rempli à l'ouverture de la bougie suivante ; sinon ordre limite touché ; SL prioritaire si SL et TP1 dans la même bougie."""
    d, rempli, t_fill = sn["d"], False, None
    touche = lambda b, v: (b["h"] >= v) if d == -1 else (b["l"] <= v)
    tp_touche = lambda b: (b["l"] <= sn["tp1"]) if d == -1 else (b["h"] >= sn["tp1"])
    for b in m1_futur:
        if b["t"] - sn["t"] > duree_min * 60:
            break
        if not rempli:
            if sn.get("marche") or touche(b, sn["e"]):
                rempli, t_fill = True, b["t"]
            else:
                continue
        if touche(b, sn["sl"]):
            return dict(etat="SL", t_fill=t_fill, t_exit=b["t"], pnl=-abs(sn["sl"] - sn["e"]))
        if tp_touche(b):
            return dict(etat="TP1", t_fill=t_fill, t_exit=b["t"], pnl=abs(sn["tp1"] - sn["e"]))
    return dict(etat="en cours" if rempli else "non rempli", t_fill=t_fill, pnl=0.0)

def figer_plan(r, stable):
    """Valeurs de plan à mémoriser (ent, tp1, tp2, sl, sens et stratégie figés)."""
    p = r["plan"]
    return dict(ent=p["e"], tp1=p["tp1"], tp2=p["tp2"], sl=p["sl"], n1=p["n1"], n2=p["n2"], dir_fig=stable, strat_fig=r["strat"])

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

ICONE = {"BTC": "🟠", "GOLD": "🥇", "NASDAQ": "💠"}
PIP = {"BTC": 1.0, "GOLD": 0.1, "NASDAQ": 1.0}      # 1 pip : 1 $ sur le BTC, 0,10 $ sur l'or
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
    # Source unique : le nom de stratégie vient du moteur SCALPING / DAY / SWING (identique à TradingView).
    strat_, etat_s, motif_s = strategie_alignement(D, direction, r.get("dirW") or 0) if direction else ("", "", "")
    if strat_:
        mode = {"SWING": "SWING", "DAY": "DAY TRADING", "SCALPING": "SCALPING"}[strat_] + (" CONTRE-TENDANCE" if contre and strat_ == "SCALPING" else "")
        horizon = {"SWING": "plusieurs jours si la structure H4 / D1 reste valide",
                   "DAY": "séance en cours ; pas de conservation automatique la nuit",
                   "SCALPING": "court terme ; ne pas transformer en position swing"}[strat_]
        contexte = motif_s
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
# Unité regardée sur TradingView → fenêtre d'alignement et type de position (UT = 1,2,5,10,15,30,45,1h,2h,4h,D).
FENETRES_UT = {
    "M1": ("SCALPING", [0, 2, 4], "1 min + 5 min + 15 min", "quelques minutes"),
    "M5": ("SCALPING / INTRADAY", [2, 4, 7], "5 min + 15 min + 1 h", "dans la séance"),
    "M15": ("INTRADAY", [4, 7, 9], "15 min + 1 h + 4 h", "dans la journée"),
    "M30": ("INTRADAY", [5, 7, 9], "30 min + 1 h + 4 h", "dans la journée"),
    "H1": ("SWING", [7, 9, 10], "1 h + 4 h + Daily", "plusieurs jours"),
    "H2": ("SWING", [8, 9, 10], "2 h + 4 h + Daily", "plusieurs jours"),
    "H4": ("SWING", [9, 10], "4 h + Daily", "plusieurs jours à semaines"),
    "D1": ("POSITION", [10], "Daily (Weekly non lu)", "semaines"),
    "W1": ("POSITION", [10], "Daily (Weekly non lu)", "semaines"),
}


def strategie_alignement(dirs, d, dW=0):
    """Règles SCALPING / DAY / SWING, identiques à l'indicateur TradingView v12.
    SWING : W1/D1 contexte, H4 retracement ou aligné, H1 confirmation.
    DAY : H4 contexte, H1 direction, M15 retracement, M5 déclenchement.
    SCALPING : H1 contexte, M15 direction, M5 structure, M1 déclenchement."""
    if not d:
        return "", "AUCUNE", "Pas de direction exploitable"
    D = list(dirs or []) + [0] * 11
    u = lambda i: D[i] == d
    o = lambda i: D[i] == -d
    uW, oW = dW == d, dW == -d
    uD, u4, u1h, u15, u5, u1 = u(10), u(9), u(7), u(4), u(2), u(0)
    o4, o1h = o(9), o(7)
    swOk = uD and not oW and u1h and not o4
    swAtt = uD and not oW and not u4 and not u1h
    dyOk = not o4 and u1h and u5
    dyAtt = not o4 and u1h and not u15 and not u5
    scOk = not o1h and u15 and u5 and u1
    scAtt = not o1h and u15 and u5 and not u1
    if swOk:
        return "SWING", "CONFIRMÉ", "D1 ✔ H1 ✔ " + ("H4 ✔" if u4 else "H4 en retracement") + " : reprise confirmée"
    if dyOk:
        return "DAY", "CONFIRMÉ", "H1 ✔ M5 ✔ " + ("M15 ✔" if u15 else "M15 en retracement") + (" H4 ✔" if u4 else " H4 neutre")
    if scOk:
        return "SCALPING", "CONFIRMÉ", "M15 ✔ M5 ✔ M1 ✔" + (" H1 ✔" if u1h else " H1 neutre")
    if swAtt:
        return "SWING", "EN ATTENTE", "Retracement H4 détecté, H1 non confirmé : aucune entrée pour le moment"
    if dyAtt:
        return "DAY", "EN ATTENTE", "Retracement M15 en cours, M5 non confirmé : attendre la clôture 5 min"
    if scAtt:
        return "SCALPING", "EN ATTENTE", "M15 et M5 alignés, déclenchement M1 manquant"
    return "", "AUCUNE", "Pas d'alignement conforme aux règles SCALPING / DAY / SWING"


DUREE_STRATEGIE = {"SWING": "position de plusieurs jours", "DAY": "position dans la journée",
                   "SCALPING": "position courte, quelques minutes à 1-2 h"}
CALE_STRATEGIE = {"SWING": "SL derrière la zone 1h / 4h • TP 4h / Daily • validation clôture 1h",
                  "DAY": "SL derrière la zone 1h • TP 1h / 4h • validation clôture 5 min",
                  "SCALPING": "SL derrière la zone 15 min • TP 15 min / 1h • validation clôture 1 min"}


def retournement_confirme(cle, d, r):
    """Vrai si cette entrée suit un SL touché dans l'autre sens (moins de 4 h) : le retournement est confirmé."""
    rt = (cle or {}).get("retournement") or {}
    ok = rt.get("d") == d and r.get("t", 0) - rt.get("t", 0) <= 4 * 3600
    if rt:
        cle.pop("retournement", None)
    return ok


def strategie_trade(r, d):
    """Fige sur la position le type (SWING / DAY / SCALPING) lu au moment de l'entrée."""
    strat, etat_, motif = strategie_alignement(r.get("dirs"), d, r.get("dirW") or 0)
    return {"strat": strat, "strat_etat": etat_, "strat_motif": motif} if strat else {}


def niveaux_strategie(strat):
    """Unités du SL et des TP selon la stratégie (identique à l'indicateur v12)."""
    if strat == "SWING":
        return ("1h", "4h"), ("4h", "Daily")
    if strat == "DAY":
        return ("1h",), ("1h", "4h")
    if strat == "SCALPING":
        return ("15m",), ("15m", "1h")
    return ("1h", "4h"), ("1h", "4h", "Daily")


def score_validation(strat, etat, dirs, d, dW, prix, plan, atr_, rsis, sens, volumes):
    """Score /100 mesuré (pas une probabilité), mêmes critères que l'indicateur v12."""
    if not strat or not d or not plan:
        return 0, {}, "AUCUNE ENTRÉE"
    D = list(dirs or []) + [0] * 11
    u = lambda i: D[i] == d
    tfs = {"SWING": [dW == d, u(10), u(9), u(7)], "DAY": [u(9), u(7), u(4), u(2)],
           "SCALPING": [u(7), u(4), u(2), u(0)]}[strat]
    p = {"alignement": round(25 * sum(tfs) / 4)}
    ctxU = {"SWING": u(10), "DAY": u(9), "SCALPING": u(7)}[strat]
    ctxO = {"SWING": dW == -d, "DAY": D[9] == -d, "SCALPING": D[7] == -d}[strat]
    p["structure"] = 20 if ctxU else 0 if ctxO else 10
    dist = abs(prix - plan["e"])
    p["zone"] = 20 if dist <= 0.5 * atr_ else 10 if dist <= 1.5 * atr_ else 0
    dernier = list(volumes or [])[-20:]
    if len(dernier) == 20 and all(v is not None for v in dernier) and dernier[-1] > 0 and sum(dernier) > 0:
        ratio = dernier[-1] / (sum(dernier) / 20)          # ta.sma(volume, 20) inclut la bougie courante
        p["volume"] = 15 if ratio >= 1.0 else 7 if ratio >= 0.7 else 0
    else:
        p["volume"] = 0
        p["volume_indisponible"] = True
    R = list(rsis or []) + [50] * 11
    rsiT = {"SWING": R[7], "DAY": R[2], "SCALPING": R[0]}[strat] or 50
    sain = rsiT < 70 if d == 1 else rsiT > 30
    p["indicateurs"] = (10 if sens == d else 5) if sain else 0
    rr = abs(plan["tp1"] - plan["e"]) / max(abs(plan["e"] - plan["sl"]), 1e-9)
    p["rr"] = 10 if rr >= 2 else 7 if rr >= 1.5 else 0
    total = p["alignement"] + p["structure"] + p["zone"] + p["volume"] + p["indicateurs"] + p["rr"]
    if total < 60:
        dec = "AUCUNE ENTRÉE : configuration insuffisante"
    elif etat != "CONFIRMÉ":
        dec = "À SURVEILLER : confirmation manquante"
    elif total >= 85:
        dec = "ENTRÉE POSSIBLE : fortement aligné"
    elif total >= 75:
        dec = "INTÉRESSANT : attendre les conditions finales"
    else:
        dec = "À SURVEILLER : confirmation manquante"
    return total, p, dec


def ligne_retournement(r):
    """Étiquette RETOURNEMENT de l'indicateur : SL franchi à la clôture 15 min, puis confirmation du nouveau sens."""
    rd = r.get("ret_dir") or 0
    if not rd:
        return []
    if r.get("ret_conf"):
        strat = r.get("strat") or ""
        return [f"✅ RETOURNEMENT CONFIRMÉ : {'LONG' if rd == 1 else 'SHORT'}" + (f" • {strat}" if strat else "")]
    return [f"⛔ SL cassé à la clôture : {'SHORT' if rd == 1 else 'LONG'} annulé ↩ RETOURNEMENT en cours (attendre la confirmation 15 min / 1h)"]

def ligne_strategie(r):
    """Même lecture que la barre TradingView v24 : stratégie, état, score /100, motif."""
    d = r.get("dirPlan") or 0
    strat, etat, motif = strategie_alignement(r.get("dirs"), d, r.get("dirW") or 0)
    if not strat:
        return ligne_retournement(r) + [f"🏷 Stratégie : aucune — {motif}"]
    total, p, dec = score_validation(strat, etat, r.get("dirs"), d, r.get("dirW") or 0, r.get("prix", 0),
                                     r.get("plan"), r.get("atr", 0) or 0, r.get("rsis"), r.get("sens"),
                                     [x.get("v") for x in (r.get("b15") or [])])
    ic = "✅" if etat == "CONFIRMÉ" and total >= 75 else "⏳"
    vol = " (volume indisponible)" if p.get("volume_indisponible") else ""
    return ligne_retournement(r) + [f"🏷 Stratégie : {strat} {ic} {etat} • score {total}/100",
            f"📊 Alignement {p['alignement']}/25 • structure {p['structure']}/20 • zone {p['zone']}/20 • volume {p['volume']}/15{vol} • indicateurs {p['indicateurs']}/10 • R/R {p['rr']}/10",
            f"🧭 {motif}",
            f"🚦 {dec}"]


def lecture_unite_active(r):
    """Adapte la lecture à l'unité ouverte sur TradingView ; rien n'est affiché si le bridge ne la fournit pas."""
    tf = str((r.get("tv_indicator_mtf") or {}).get("activeTimeframe") or "").upper()
    if tf not in FENETRES_UT:
        return None
    mode, idx, noms, duree = FENETRES_UT[tf]
    D = r.get("dirs") or []
    vals = [D[i] for i in idx if i < len(D)]
    if vals and all(v == 1 for v in vals):
        etat_ = "🟢 alignement LONG"
    elif vals and all(v == -1 for v in vals):
        etat_ = "🔴 alignement SHORT"
    else:
        etat_ = "🟠 pas d'alignement complet : attendre"
    return f"📺 Ton graphique {tf} → {mode} ({duree})\n🧩 {noms} : {etat_}"


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
         *ligne_strategie(r),
         f"🧭 Lecture : {profil['contexte']}",
         f"⏱ Horizon indicatif : {profil['horizon']}",
         f"🚦 {profil['statut']}"]
    vue = lecture_unite_active(r)
    if vue:
        l.append(vue)
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
    extreme = (d == -1 and (posD <= 0.15 or (posW <= 0.15 and posD <= 0.35))) or \
              (d == 1 and (posD >= 0.85 or (posW >= 0.85 and posD >= 0.65)))
    if not extreme:
        return False
    # Jour de TENDANCE (Daily, 4 h, 1 h et 15 min dans le même sens, aucun voyant de retournement sur les petites UT) :
    # le prix est forcément « en bas » (baisse) ou « en haut » (hausse) du Daily — ce n'est pas une raison de rater le mouvement.
    dirs = r.get("dirs") or []
    if len(dirs) >= 11 and dirs[10] == d and dirs[9] == d and dirs[7] == d and dirs[4] == d \
            and sum(1 for x in dirs[:5] if x == -d) == 0:
        return False
    return True

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
        if zv is None:
            return
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
    # Règle d'Adel : déclencheur M5 → SL juste derrière la mèche du dernier plus haut / plus bas 5 min ; structure 15 min en secours.
    sl, sl_ut = stop_meche_5m(r, d, e), "5 min"
    if sl is None:
        sl, sl_ut = stop_structure_15m(r, d, e), "15 min"
    if sl is None:
        return None
    risque = abs(e - sl)
    t1, t2 = objectifs(r, d, e, risque)
    nom = lambda z: (("résistance " if d == 1 else "support ") + z[1]) if z[1] in ("1h", "4h", "Daily") else z[1]
    return dict(d=d, e=e, sl=sl, tp1=t1[0], n1=nom(t1), tp2=t2[0], n2=nom(t2), rr=abs(t1[0] - e) / risque,
                src="cassure 5 min", za=e, zb=e, niveau=L, t15=b[-1]["t"],
                sl_h=bougie_protegee((r["b5"][:-1][-4:] if sl_ut == "5 min" else r["b15"][-3:]), d, sl), sl_ut=sl_ut)

def stop_structure_15m(r, d, entry):
    """SL derrière la structure M15, pas derrière une seule mèche M5.
    Si la structure exige un risque supérieur au plafond, on refuse l'entrée au lieu de resserrer artificiellement le stop.
    """
    bars = (r.get("b15") or [])[-3:]
    atr15 = float(r.get("atr") or 0)
    if len(bars) < 3 or atr15 <= 0 or d not in (-1, 1):
        return None
    extreme = min(x["l"] for x in bars) if d == 1 else max(x["h"] for x in bars)
    sl = extreme - d * 0.25 * atr15
    distance = d * (entry - sl)
    minimum = max(0.8 * atr15, entry * 0.0008)
    if distance <= 0:
        return None
    if distance < minimum:
        sl = entry - d * minimum
        distance = minimum
    if distance > RISQUE_MAX * atr15:
        return None
    return sl


def stop_meche_5m(r, d, entry):
    """Règle d'Adel : l'entrée est vue en 5 min → SL juste derrière la MÈCHE du dernier plus haut (SHORT) / plus bas (LONG) des bougies 5 min
    clôturées (là où le marché s'est retourné), avec une petite marge. Si cette mèche est cassée, le cycle suivant reprend le nouveau dernier plus haut / bas."""
    bars = (r.get("b5") or [])[:-1][-4:]                 # la dernière bougie M5 est en formation
    a5 = float(r.get("atr5") or r.get("atr") or 0)
    if len(bars) < 2 or a5 <= 0 or d not in (-1, 1):
        return None
    meche = min(x["l"] for x in bars) if d == 1 else max(x["h"] for x in bars)
    sl = meche - d * 0.4 * a5            # un peu plus large (0,25 → 0,4 ATR 5 min) : moins de SL touchés de justesse
    distance = d * (entry - sl)
    if distance <= 0:
        return None
    minimum = max(0.5 * a5, entry * 0.0004)               # jamais un SL collé au prix (bruit d'une seule bougie)
    if distance < minimum:
        sl = entry - d * minimum
    return sl

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
            return (f"🟢 TU PEUX ENTRER\n{SENS[tr['d']]}", f"👀 Vue {tr.get('sl_ut', '5 min')}\n🛑 SL un peu {meche_sl(tr)}\n🙅 Jamais pile sur la mèche\n📍 Repère prix : SL ≈ {px(tr['sl'])} • TP1 ≈ {px(tr['tp1'])}\n📍 Si tu prends cette position, active son suivi avec le bouton ci-dessous.")
        return ("🔴🔴 N'ENTRE PAS", f"⏰ Trop tard : la position {sens} est déjà partie\n⏳ J'attends le prochain setup")
    if r.get("annonce"):
        return ("🔴🔴 N'ENTRE PAS", "📰 News dans moins de 15 min\n💥 Le prix peut bouger très fort")
    al = r["confirme"]
    if not al:
        # Même lecture que le chrono : 4 h neutre ≠ 1 h qui ne confirme pas.
        if not (r.get("dirs") or [0] * 11)[9]:
            return ("🔴🔴 N'ENTRE PAS", "⏳ La 4 h est neutre : pas de direction LONG ni SHORT\n🔔 Je te préviens dès que c'est validé")
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
"🟠 Analyse BTC": "🟠 BTC Analysis", "🥇 Analyse Gold": "🥇 Gold Analysis", "💠 Analyse Nasdaq": "💠 Nasdaq Analysis", "📡 Choisir mes marchés": "📡 Choose my markets", "📡 Mes marchés cochés": "📡 My ticked markets", "📊 Faire une analyse": "📊 Run an analysis",
"📡 Mes marchés": "📡 My markets", "🔔 Son pièce": "🔔 Coin sound", "🔔 Son envoyé": "🔔 Sound sent",
"📍 Suivre cette position": "📍 Follow this position", "📍 Ma position • SL / TP": "📍 My position • SL / TP", "📍 Si tu prends cette position, active son suivi avec le bouton ci-dessous.": "📍 If you take this position, activate its tracking with the button below.",
 "🟠 BTC uniquement": "🟠 BTC only", "🥇 GOLD uniquement": "🥇 GOLD only",
"🟠 BTC + 🥇 GOLD": "🟠 BTC + 🥇 GOLD", "🏷 Type :": "🏷 Type:", "position de plusieurs jours": "multi-day position", "position dans la journée": "intraday position", "position courte, quelques minutes à 1-2 h": "short position, a few minutes to 1-2 h", "validation clôture": "confirmation close", "SL derrière la zone": "SL behind the zone", "💎 TU ES DÉJÀ VIP": "💎 YOU ARE ALREADY VIP", "✅ Toutes les positions, les niveaux et le coach sont actifs pour toi": "✅ All positions, levels and the coach are active for you", "📲 Le canal ALIGN VIP 💎 est accessible avec le bouton ci-dessous": "📲 Open the ALIGN VIP 💎 channel with the button below", "📲 Ouvrir le canal ALIGN VIP 💎": "📲 Open ALIGN VIP 💎 channel", "📡 Choisir les marchés suivis": "📡 Choose followed markets",
"✅ Sélection enregistrée": "✅ Selection saved", "🥇 + 🟠 Les deux": "🥇 + 🟠 Both",
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
"🕒 Heure prévue :": "🕒 Scheduled time:", "🏷 Barre TradingView :": "🏷 TradingView bar:", "retracement 15 min": "15m pullback", "SIGNAL FAIBLE": "WEAK SIGNAL", "ATTENDRE": "WAIT", "📺 Ton graphique": "📺 Your chart", "alignement LONG": "LONG alignment", "alignement SHORT": "SHORT alignment", "pas d'alignement complet : attendre": "no full alignment: wait", "plusieurs jours à semaines": "several days to weeks", "plusieurs jours": "several days", "dans la séance": "within the session", "dans la journée": "within the day", "quelques minutes": "a few minutes", "⛔ Le prix est déjà collé au stop : je ne lance pas le suivi.": "⛔ Price is already right at the stop: I am not starting tracking.", "⏳ N'entre pas maintenant, attends le prochain signal.": "⏳ Do not enter now, wait for the next signal.", "⚠️ Latence : le prix s'est rapproché du stop depuis le signal.": "⚠️ Latency: price has moved closer to the stop since the signal.", "ne le resserre pas ; réduis la taille si tu entres.": "do not tighten it; reduce size if you enter.", "Garde le SL du plan": "Keep the plan SL", "⚠️ Latence : le prix a déjà fait une bonne partie du chemin.": "⚠️ Latency: price has already covered much of the move.", "🎯 Le gain restant vers le TP1 est faible : entrée peu intéressante.": "🎯 Remaining gain to TP1 is small: entry not attractive.", "🕯 Clôture 5 min :": "🕯 5m close:", "🕯 Clôture 15 min :": "🕯 15m close:", "POURQUOI J'ATTENDS": "WHY I'M WAITING", "↩ RETOURNEMENT EN PRÉPARATION": "↩ REVERSAL BUILDING", "petites unités ont tourné contre le": "small timeframes turned against the", "🔒 Sécurise : stop à BE": "🔒 Secure: stop at BE", "si tu es en gain": "if you are in profit", "✅ Retournement confirmé si le 15 min ET la 1 h clôturent vers le": "✅ Reversal confirmed if the 15m AND the 1h close towards", "🙅 Aucune entrée en sens inverse avant cette confirmation": "🙅 No entry the other way before this confirmation", "⚡ Petites unités": "⚡ Small timeframes", "🏔 Grandes unités": "🏔 Big timeframes", "⏳ La 4 h est neutre : pas de direction LONG ni SHORT": "⏳ 4h is neutral: no LONG or SHORT direction", "⏳ Le 1h ne confirme pas la tendance 4h": "⏳ 1h does not confirm the 4h trend", "🔔 Je te préviens dès que c'est validé": "🔔 I'll tell you as soon as it's validated", "aucun sens LONG/SHORT validé": "no LONG/SHORT direction validated", "La bougie 4 h ne donne pas de direction nette : le marché est neutre. Aucun LONG ni SHORT n'est proposé.": "The 4h candle gives no clear direction: the market is neutral. No LONG or SHORT is proposed.", "Fin du suivi si aucun setup avant": "Tracking ends if no setup before", "aucune entrée forcée": "no forced entry", "Actualisé à": "Updated at", "confirmation 1 h manquante": "1h confirmation missing", "validation complète en attente": "full validation pending", "Suivi en cours depuis": "Tracking for", "À la clôture 4 h : je regarde si la 4 h donne enfin un sens LONG ou SHORT.": "At the 4h close: I check whether 4h finally gives a LONG or SHORT direction.", "À la clôture 1 h : je vérifie que la 1 h confirme la 4 h.": "At the 1h close: I check that 1h confirms 4h.", "À la clôture 15 min : je cherche un repli propre pour préparer l'entrée.": "At the 15m close: I look for a clean pullback to prepare the entry.", "À la clôture 5 min : si la bougie clôture dans le bon sens, l'entrée est validée.": "At the 5m close: if the candle closes in the right direction, the entry is validated.",
"🟢 CLÔTURE — SIGNAL CONFIRMÉ": "🟢 CANDLE CLOSE — SIGNAL CONFIRMED",
"🔴 CLÔTURE — SIGNAL NON CONFIRMÉ": "🔴 CANDLE CLOSE — SIGNAL NOT CONFIRMED",
"🟢 POSITION EN COURS — SUIVI DU TRADE": "🟢 POSITION OPEN — TRADE MONITORING",
"🟢 Position déjà ouverte : ne rajoute pas une entrée.": "🟢 Position already open: do not add another entry.",
"🟢 Signal validé : vérifie la zone, le stop et les objectifs avant d'agir.": "🟢 Signal confirmed: check the entry zone, stop and targets before acting.",
"🚫 N'ENTRE PAS. Attends une confirmation complète avant toute entrée.": "🚫 DO NOT ENTER. Wait for full confirmation before entering.",
"🟡 POSITION À VENIR — ordre en attente, aucune position ouverte": "🟡 UPCOMING SETUP — pending order, no position is open",
"📍 Zone surveillée :": "📍 Monitored zone:",
"🔁 Zone de retournement visée :": "🔁 Targeted reversal zone:", " attendu": " expected", "📍 Le prix est dans la zone : j'attends le rejet et la clôture": "📍 Price is inside the zone: waiting for the rejection and the close",
"🔁 Zone de retournement : pas encore définie (le plan n'est pas fixé)": "🔁 Reversal zone: not defined yet (the plan is not fixed)", "📏 Prix à": "📏 Price is", "de la zone (elle est au-dessus)": "from the zone (it is above)", "de la zone (elle est en dessous)": "from the zone (it is below)",
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
"📍 Si tu prends cette position, active son suivi avec le bouton ci-dessous.": "📍 If you take this position, activate its tracking with the button below.",
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
"favorable au 🟩 LONG": "favourable to 🟩 LONG", "frein pour le 🟩 LONG": "headwind for 🟩 LONG", "🏦 Taux US 10 ans": "🏦 US 10-year yield", "sur la journée": "on the day", "frein pour le Gold": "headwind for Gold", "favorable au Gold": "favourable to Gold", "📏 Hier : haut": "📏 Yesterday: high", "• bas": "• low", "🌏 Range Asie : haut": "🌏 Asia range: high", "💥 CASSURE": "💥 BREAKOUT", "🧲 NIVEAU CLÉ": "🧲 KEY LEVEL", "📍 Le prix approche le": "📍 Price is approaching the", "🕯 Vue 15 min : ça peut rebondir OU casser": "🕯 15 min view: it can bounce OR break", "⏳ J'attends la clôture de la bougie 15 min": "⏳ Waiting for the 15 min candle close", "plus haut d'hier et de la semaine dernière": "yesterday's and last week's high", "plus bas d'hier et de la semaine dernière": "yesterday's and last week's low", "plus haut d'hier": "yesterday's high", "plus bas d'hier": "yesterday's low", "plus haut de la semaine dernière": "last week's high", "plus bas de la semaine dernière": "last week's low", "plus haut du range Asie": "Asia range high", "plus bas du range Asie": "Asia range low", "👀 Je vérifie l'alignement 15 min / 1 h / 4 h avant d'entrer": "👀 I check the 15 min / 1 h / 4 h alignment before entering", "💵 DOLLAR EN FORTE BAISSE": "💵 DOLLAR FALLING HARD", "💵 DOLLAR EN FORTE HAUSSE": "💵 DOLLAR RISING HARD", "prudence": "be careful", "🧭 Le bot n'entre toujours qu'avec 15 min / 1 h / 4 h alignées": "🧭 The bot still only enters with 15 min / 1 h / 4 h aligned", "📰 NEWS USA DANS 1 H": "📰 US NEWS IN 1 H", "🛑 Pas de nouvelle position à partir de": "🛑 No new position from", "🔒 En position ? Mets-toi à BE si tu es en gain": "🔒 In a trade? Move to BE if in profit", "📊 Prévu": "📊 Forecast", "• avant": "• previous", "📰 RÉACTION À LA NEWS": "📰 NEWS REACTION", "⏳ J'attends la clôture de la bougie 15 min avant de reprendre": "⏳ Waiting for the 15 min close before resuming", "haussier ≈": "bullish ≈", "baissier ≈": "bearish ≈", ": le prix peut y rebondir": ": price may bounce there", ": le prix peut y buter": ": price may stall there", "🌙 MARCHÉ BIENTÔT FERMÉ": "🌙 MARKET CLOSING SOON", "⏰ Fermeture à": "⏰ Closes at", "🟥 Topstep / prop firms : tout fermé avant": "🟥 Topstep / prop firms: everything closed before", "(sinon fermeture automatique)": "(otherwise auto-flattened)", "🌙 Broker (CFD) / CME : fermeture": "🌙 Broker (CFD) / CME: close", "🔓 Réouverture": "🔓 Reopen", "dimanche": "Sunday", "• réouverture à": "• reopens at", "• réouverture dimanche soir": "• reopens Sunday evening", "(heure de Paris)": "(Paris time)", "🛡 Pas de nouvelle position avant la fermeture": "🛡 No new position before the close", "🔔 Je reprends la recherche après la réouverture": "🔔 I'll resume after the reopen", "🌙 FERMETURE DU GOLD DANS": "🌙 GOLD CLOSES IN", "🚦 🙅 PAS DE NOUVELLE POSITION": "🚦 🙅 NO NEW POSITION", "🔒 Tu es en position : mets-toi à BE si tu es en gain": "🔒 You're in a trade: move to BE if in profit", "🛡 Vérifie que ton SL est bien placé": "🛡 Check your SL is in place", "🛡 Ne pas ouvrir de position avant la fermeture": "🛡 Don't open a position before the close", "💥 Week-end : le prix peut s'ouvrir loin (écart), sécurise tes gains": "💥 Weekend: price may gap at the open, secure your profits", "💥 À la réouverture le prix peut sauter (écart)": "💥 At the reopen price may gap", "🎯 TP1 TOUCHÉ": "🎯 TP1 HIT", "✂️ Prends une partie des gains": "✂️ Take part of the profit", "🔒 Vérifie que ton SL est à BE": "🔒 Check your SL is at BE", "📈 Garde le reste : le marché peut encore pousser": "📈 Keep the rest: the market can push further", "🏁 TP2 visé": "🏁 Target TP2", "🙅 Ne coupe pas tout sur le TP1": "🙅 Don't close everything at TP1", "⏱ Durée estimée": "⏱ Estimated duration", "📅 Position de LONGUE DURÉE : elle peut durer plus d'une journée, garde ton SL en place la nuit": "📅 Long-DURATION position: it can last more than a day, keep your SL overnight", "🎁 Ta position gratuite arrive avec le prochain signal": "🎁 Your free position comes with the next signal", "🔒 Cette position est réservée aux VIP": "🔒 This position is VIP-only", "🎉🎉 BRAVO": "🎉🎉 WELL DONE", "💰 Ta position gratuite": "💰 Your free position", "🔥 C'est ça, ALIGN": "🔥 That's ALIGN", "😍 Imagine chaque position comme celle-là": "😍 Imagine every position like this one", "💎 En VIP : toutes les positions + le sens + le coach (BE, TP)": "💎 In VIP: every position + the direction + the coach (BE, TP)", "🔓 VIP 49,90 € / mois 👇": "🔓 VIP €49.90 / month 👇", "📊 Ça fait partie du jeu : on coupe petit, on gagne gros": "📊 It's part of the game: cut small, win big", "💎 En VIP : toutes les positions pour se refaire + le coach": "💎 In VIP: every position to bounce back + the coach", "RÉSULTAT ALIGN": "ALIGN RESULT", "📌 Entrée": "📌 Entry", "🏁 Sortie": "🏁 Exit", "📈 Résultat": "📈 Result", "⏱ Durée": "⏱ Duration", ": bravo !": ": well done!", "📸 N'hésite pas à partager ta capture dans ALIGN Résultats": "📸 Feel free to share your screenshot in ALIGN Results", "👇 Bouton 📸 Partager mon gain": "👇 Button 📸 Share my profit", "🛡 SL respecté, risque maîtrisé": "🛡 SL respected, risk under control", "📸 Voir les résultats ALIGN": "📸 See ALIGN results", ": SL touché, risque maîtrisé": ": SL hit, risk under control", "📊 Tous les résultats (TP et SL) sont publiés en toute transparence": "📊 All results (TP and SL) are published transparently", "👇 Bouton ci-dessous": "👇 Button below", "🔥 Une position VIP est EN COURS": "🔥 A VIP position is RUNNING", "👀 Une position VIP se PRÉPARE": "👀 A VIP position is COMING", "⏳ Pas de position pour l'instant": "⏳ No position right now", "🔒 Sens du marché : VIP": "🔒 Market direction: VIP", "🔒 LONG ou SHORT, entrée, SL, TP : réservés aux VIP": "🔒 LONG or SHORT, entry, SL, TP: VIP only", "Nouvelle info pour les VIP": "New info for VIPs", "🤫 Sens et niveaux cachés": "🤫 Direction and levels hidden", "🌀🌀 MANIPULATION EN COURS": "🌀🌀 MANIPULATION IN PROGRESS", "⚠️ MÈCHE SUSPECTE EN COURS": "⚠️ SUSPICIOUS WICK IN PROGRESS", "⏱ CHRONO EN DIRECT": "⏱ LIVE TIMER", "🚦 🟢 J'ENTRE": "🚦 🟢 I'M ENTERING", "🚦 🟢 ON RESTE EN POSITION": "🚦 🟢 WE STAY IN", "objectifs remis dans l'ordre": "targets put back in order", "🛑 SL inchangé": "🛑 SL unchanged", "🚦 🙅 JE N'ENTRE PAS": "🚦 🙅 I'M NOT ENTERING", "🚦 ⏳ JE N'ENTRE PAS ENCORE": "🚦 ⏳ NOT ENTERING YET", "💰 TP visé": "💰 Target TP", "🎯 Inscrit depuis": "🎯 Registered for", "✅ ENTRÉ": "✅ ENTERED", "🎯 Le coach te suit jusqu'au TP": "🎯 The coach follows you to TP",
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
"Confirmé en 1 h": "Confirmed on 1 h", "Gain / risque x": "Reward / risk x", "📍 POSITION SUIVIE AUTOMATIQUEMENT": "📍 POSITION AUTOMATICALLY TRACKED",
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
": tu peux encore rentrer (": ": you can still enter (", "✅ ENTRÉE ENCORE POSSIBLE": "✅ ENTRY STILL POSSIBLE", "❌ STOP TOUCHÉ": "❌ STOP HIT", "📈 TP2 TOUCHÉ": "📈 TP2 HIT", "🔥 La tendance continue": "🔥 The trend continues", "🛑 Nouveau stop": "🛑 New stop", "(au TP1)": "(at TP1)", "🎯 Nouvel objectif": "🎯 New target", "🏆 OBJECTIF FINAL ATTEINT": "🏆 FINAL TARGET REACHED", "✅ Trade terminé, bravo !": "✅ Trade closed, well done!", "↩️ SORTIE AU STOP SÉCURISÉ": "↩️ EXIT AT SECURED STOP", "🛑 Sortie": "🛑 Exit", "✅ TP1 encaissé, pas de perte": "✅ TP1 banked, no loss", "🎯 OBJECTIFS REMIS DANS L'ORDRE": "🎯 TARGETS PUT BACK IN ORDER", "📍 Tu prends la position ? Active le suivi avec le bouton ci-dessous": "📍 Taking the trade? Turn on tracking with the button below", "⛔ TROP TARD POUR ENTRER": "⛔ TOO LATE TO ENTER", "🙅 N'entre plus maintenant : le prix est trop loin de l'entrée": "🙅 Don't enter now: price is too far from the entry", "🟢 Déjà en position : on continue": "🟢 Already in: we carry on", ": trop tard pour rentrer. On attend le prochain setup.": ": too late to enter. Waiting for the next setup.",
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
"🚪 Sortie manuelle": "🚪 Manual exit", "🛑 Stop touché": "🛑 SL hit", "✅ RETOURNEMENT CONFIRMÉ :": "✅ REVERSAL CONFIRMED:", "↩ RETOURNEMENT possible vers le": "↩ Possible REVERSAL to", ": j'entre seulement si le 15 min et la 1 h le confirment": ": I only enter if 15 min and 1 h confirm it", "🔒 Stop protégé touché": "🔒 Protected SL hit", "🛡 Stop remonté touché": "🛡 Raised SL hit",
"💰 TP1 encaissé": "💰 TP1 banked", "🏆 Objectif final": "🏆 Final target",
# Résultats
"Aucun trade clôturé pour l'instant.": "No closed trade yet.", "Les résultats apparaîtront après la première clôture réellement enregistrée.": "Results will appear after the first actually recorded close.",
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
": POSITION SUIVIE AUTOMATIQUEMENT": ": POSITION AUTOMATICALLY TRACKED", "📍 Repère prix : entrée ≈": "📍 Price guide: entry ≈", "🎯 Je rentre dans la prochaine position": "🎯 I'm in for the next position",
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
"🤖 Les abonnés au suivi sont enregistrés automatiquement à l'ouverture du signal.": "🤖 Follow subscribers are registered automatically when a signal opens.",
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
    "📊 Analyse complète": "📊 Full analysis", "🧠 En savoir plus": "🧠 Learn more",
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
    "SWING": "SWING", "INTRADAY": "INTRADAY", "DAY TRADING": "DAY TRADING", "SCALPING": "SCALPING", "ATTENTE": "WAIT",
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
    "⚖️ SCALPING : H1 + M15 + M5 + M1 • DAY : H4 + H1 + M15 + M5 • SWING : W1/D1 + H4 + H1": "⚖️ SCALPING: H1 + M15 + M5 + M1 • DAY: H4 + H1 + M15 + M5 • SWING: W1/D1 + H4 + H1",
    "⚠️ Un setup contre H4/H1 reste un scalp contre-tendance, jamais un swing": "⚠️ A setup against H4/H1 remains counter-trend scalping, never a swing",
    "📍 1 min : suivi du prix et de la position": "📍 1m: price and position monitoring",
    "ℹ️ 3, 10, 30 et 45 min + 2 h et Daily : confirmations et contexte complémentaires.": "ℹ️ 2m, 10m, 30m, 45m, 2h and Daily: additional context and confirmation.",
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
TRAD.update({
    "⛔ SL cassé à la clôture :": "⛔ SL broken at the close:", "annulé ↩ RETOURNEMENT en cours (attendre la confirmation 15 min / 1h)": "cancelled ↩ REVERSAL in progress (wait for the 15 min / 1h confirmation)",
    "✅ RETOURNEMENT CONFIRMÉ :": "✅ REVERSAL CONFIRMED:", "petites unités contre le plan": "small timeframes against the plan", ": le retournement se prépare": ": a reversal is building",
})
_CLES = sorted(TRAD, key=len, reverse=True)
BOUTONS_FR = ["🤖 Mon bot", "📸 Partager mon gain", "🟠 Analyse BTC", "🥇 Analyse Gold", "💠 Analyse Nasdaq", "✅ Je suis rentré", "🚪 Je suis sorti", "📈 Mes résultats",
              "🧩 Indicateur TradingView", "💎 Devenir VIP", "📡 Mes marchés", "❌ Non"]
INVERSE = {TRAD[b]: b for b in BOUTONS_FR}        # bouton anglais reçu → même action qu'en français

TRAD.update({
    " - EN ATTENTE": " - WAITING", "📉 Raison :": "📉 Reason:", "🚀 Déclencheur :": "🚀 Trigger:",
    "Clôture 5 min au-dessus de": "5 min close above", "Clôture 5 min sous": "5 min close below", "Clôture 15 min au-dessus de": "15 min close above",
    "Clôture 15 min sous": "15 min close below", "Clôture 1h au-dessus de": "1h close above", "Clôture 1h sous": "1h close below",
    "Clôture 5 min": "5 min close", "Clôture 15 min": "15 min close", "Clôture 1h": "1h close", "Clôture 4h": "4h close",
    "🎯 Entrée :": "🎯 Entry:", "🛑 Stop :": "🛑 Stop:", "📊 Contexte :": "📊 Context:", "⏱ Validité :": "⏱ Validity:",
    "jusqu'à la clôture 15 min": "until the 15 min close", "jusqu'à la clôture 5 min": "until the 5 min close", "Cassure confirmée, clôture 5 min au-dessus": "Breakout confirmed, 5 min close above",
    "Cassure confirmée, clôture 5 min sous": "Breakout confirmed, 5 min close below", "Prix hors zone": "Price outside the zone",
    "Le prix doit revenir en zone": "Price must return to the zone",
    "⏳ Raison :": "⏳ Reason:", "🔑 Zone :": "🔑 Zone:", "⏱ Valide :": "⏱ Valid:", "🔹 Signal :": "🔹 Signal:", "🤖 Agent Auto-Trade :": "🤖 Auto-Trade agent:",
    "Action : NE PAS RENTRER": "Action: DO NOT ENTER", "Action : ENTRER": "Action: ENTER", "Action : Prêt à entrer": "Action: Ready to enter",
    "🔔 OUVERTURE MARCHÉ :": "🔔 MARKET OPEN:", "⏰ Ouverture :": "⏰ Opening:", "📈 Tendance H4 :": "📈 H4 trend:", "📈 Tendance H1 :": "📈 H1 trend:",
    "🔑 Niveaux clés :": "🔑 Key levels:", "· Résistance :": "· Resistance:", "· Support :": "· Support:", "⚠️ News :": "⚠️ News:",
    "Haussier": "Bullish", "Baissier": "Bearish", "Neutre": "Neutral",
    # carte d'entrée (ordre du graphique, règle mèche 5 min) : même format propre en anglais
    "📊 Contexte": "📊 Context", "🔹 Niveaux :": "🔹 Levels:", "🔹 News : Aucune": "🔹 News: None", "🔹 News :": "🔹 News:",
    "🔹 DXY : n/d": "🔹 DXY: n/a", "🔹 DXY :": "🔹 DXY:", "(mèche 5 min)": "(5 min wick)", "(vue 5 min)": "(5 min chart)",
    "(vue 15 min)": "(15 min chart)", "⚠️ Prix en zone extrême Daily/Weekly :": "⚠️ Price in extreme Daily/Weekly zone:",
    "⛔ Je ne poursuis pas le SHORT : risque de rebond": "⛔ I don't chase the SHORT: bounce risk", "⛔ Je ne poursuis pas le LONG : risque de repli": "⛔ I don't chase the LONG: pullback risk",
    "⏳ J'attends : repli ou retournement confirmé en 1h + clôture 5m, ou meilleur prix": "⏳ Waiting for: pullback or reversal confirmed on 1h + 5m close, or a better price",
    "4h + 1h alignées": "4h + 1h aligned", " - EN ATTENTE": " - WAITING", "🕯 Prix encore près de l'entrée du bot": "🕯 Price still close to the bot's entry", "🛑 SL :": "🛑 SL:", "💰 TP1 :": "💰 TP1:", "🏁 TP2 :": "🏁 TP2:", "⚖️ R:R :": "⚖️ R:R:",
})
TRAD.update({   # v24.3 : cartes coach FVG, scalp, suivi, ouvertures — même format propre en anglais
    "ENTRÉE ENCORE POSSIBLE": "ENTRY STILL POSSIBLE", "TROP TARD POUR ENTRER": "TOO LATE TO ENTER", "TP1 TOUCHÉ": "TP1 HIT", "TP2 TOUCHÉ": "TP2 HIT", "TP3 TOUCHÉ": "TP3 HIT", "TP4 TOUCHÉ": "TP4 HIT", "TP5 TOUCHÉ": "TP5 HIT",
    "TP touchés sur ce trade": "TPs hit on this trade", "avant le retournement": "before the reversal", "TP encaissés": "TPs banked", "TP encaissé": "TP banked",
    "🚀 La tendance continue, on laisse courir": "🚀 The trend continues, we let it run", "✅ Aucune perte": "✅ No loss", "Nouveau SL": "New SL",
    "OBJECTIF FINAL ATTEINT": "FINAL TARGET REACHED", "METS-TOI À BE": "MOVE TO BE", "SORTIE AU STOP SÉCURISÉ": "EXIT AT PROTECTED SL",
    "SORTI À BE": "OUT AT BE", "STOP TOUCHÉ": "SL HIT", "OBJECTIFS REMIS DANS L'ORDRE": "TARGETS REORDERED",
    "🕯 Prix actuel": "🕯 Current price", ": encore près de l'entrée du bot": ": still close to the bot's entry",
    "✅ 5 min + 15 min alignés": "✅ 5 min + 15 min aligned", "⏳ Alignement :": "⏳ Alignment:", "pour l'instant": "for now",
    "ni 5 min ni 15 min": "neither 5 min nor 15 min", "FVG rouge": "Red FVG", "FVG verte": "Green FVG",
    ": elle bloque la hausse": ": it blocks the rise", ": elle bloque la baisse": ": it blocks the drop",
    "protégé derrière la FVG et la mèche": "protected behind the FVG and the wick", "protégé derrière l’order block, la FVG et la mèche": "protected behind the order block, the FVG and the wick",
    "🎣 Mèche qui dépasse puis revient = manipulation (chasse aux stops), c'est normal": "🎣 Wick that pokes through then comes back = manipulation (stop hunt), it's normal",
    "⏳ Patiente : j'entre quand une bougie": "⏳ Be patient: I enter when a", " clôture sous ": " candle closes below ", " clôture au-dessus de ": " candle closes above ", "🧘 Ça peut piquer un peu, t'inquiète pas tant que le SL tient": "🧘 It can sting a bit, don't worry as long as the SL holds",
    "📍 Prix DANS la zone d'entrée": "📍 Price IN the entry zone",
    "🚀 Ça continue vers le TP2 tant que le SL tient": "🚀 It keeps going to TP2 as long as the SL holds",
    "🛡️ Si tu suis la position, je te dis quand remonter ton SL": "🛡️ If you follow the position, I'll tell you when to move your SL",
    "LONDRES": "LONDON", "Londres": "London", ": pas de FVG / order block exploitable en vue 5 min": ": no usable FVG / order block on the 5 min chart", "😎 Je ne force rien : j'attends un vrai setup": "😎 I don't force anything: waiting for a real setup", "👀 Mets-toi en vue 5 min": "👀 Switch to the 5 min chart", "👀 Vue 5 min": "👀 5 min chart", ": MARCHÉ FERMÉ": ": MARKET CLOSED", "😴 Je ne t'envoie plus rien sur ce marché": "😴 No more messages on this market", "⏰ Réouverture :": "⏰ Reopens:", "lundi": "Monday", "dimanche": "Sunday", "⬆️ HAUSSIER 🟢": "⬆️ BULLISH 🟢", "⬇️ BAISSIER 🔴": "⬇️ BEARISH 🔴",
})
TRAD.update({   # cartes d'analyse avec les couleurs du graphique
    "(ligne jaune)": "(yellow line)", "(ligne rouge)": "(red line)", "(ligne bleue)": "(blue line)",
    "🔒 SL protégé :": "🔒 Protected SL:", "(plus de perte possible)": "(no more loss possible)",
})
TRAD.update({   # lecture au TP1
    "⚠️ RISQUE DE RETOUR VERS L'ENTRÉE": "⚠️ RISK OF A PULLBACK TO THE ENTRY", "petites unités repartent contre la position": "small timeframes turning against the trade",
    ": le marché s'essouffle": ": the market is running out of steam", "✂️ Encaisse une grosse partie maintenant": "✂️ Take a big part of the profit now",
    "🛡 SL à BE : plus aucune perte possible": "🛡 SL to BE: no more loss possible", "🚀 ÇA PEUT CONTINUER VERS LE TP2": "🚀 IT CAN GO ON TO TP2",
    "petites unités dans le sens de la position": "small timeframes in the trade direction", "du TP1 = cap sur le TP2": "TP1 = heading for TP2",
    "en compression : ça peut accélérer": "compressed: it can speed up", "🟨 LE MARCHÉ HÉSITE AU TP1": "🟨 THE MARKET HESITATES AT TP1",
    "du TP1 = ça continue vers le TP2": "TP1 = it goes on to TP2", "↩ Mèche qui touche puis revient = on sécurise (SL à BE)": "↩ Wick that touches then comes back = secure (SL to BE)",
    ": essoufflé": ": out of steam", "Bougie 15 min qui CLÔTURE": "15-min candle CLOSING", "Clôture 15 min": "15-min close",
})
TRAD.update({   # cartes reliées au graphique (mêmes mots que l'indicateur)
    "🟩 Le prix entre dans la ZONE du graphique": "🟩 Price is entering the chart ZONE",
    "🟨 Ligne jaune ENTRÉE : attends la CLÔTURE 15 min AU-DESSUS": "🟨 Yellow ENTRY line: wait for the 15-min CLOSE ABOVE",
    "🟨 Ligne jaune ENTRÉE : attends la CLÔTURE 15 min EN DESSOUS": "🟨 Yellow ENTRY line: wait for the 15-min CLOSE BELOW",
    "🙅 Une mèche seule ne suffit pas": "🙅 A wick alone is not enough",
    "🛑 SL = ligne rouge du graphique": "🛑 SL = red line on the chart",
})
_CLES = sorted(TRAD, key=len, reverse=True)

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

# ───────── Charte des messages : zéro blabla, 3 modèles stricts (signal · en attente · ouverture de marché) ─────────
_BLABLA = re.compile("|".join((
    r"je n'entre pas encore", r"heureusement", r"analyse de référence", r"\bmaître\b", r"tiens-toi prêt", r"ne rate pas le feu vert",
    r"cloche activée", r"like si tu participes", r"pas de position forcée", r"on ne court pas après", r"ça peut être tout de suite",
    r"attends mon feu vert", r"attends mon 🟢", r"mets-toi en vue", r"je te préviens dès que c'est validé", r"je (?:re)?calcule le prochain point",
    r"^😎", r"\bbravo\b", r"i'm not entering yet", r"luckily", r"stay ready", r"don't miss the green light", r"like if you")), re.I)

def epurer_blabla(lignes):
    """Retire les phrases de remplissage (jamais la première ligne : le titre). Les avertissements de risque (SL obligatoire, analyse indicative) restent."""
    return [l for k, l in enumerate(lignes) if k == 0 or not _BLABLA.search(l)]

_ENTREE_RE = re.compile(r"^(?:[🟢🔴]|📍) [A-Z0-9]+ - (?:LONG|SHORT)\s*$")

def est_entree(texte):
    """Vrai pour un message de signal d'entrée : ancien titre « J'ENTRE MAINTENANT » ou modèle « 🟢 GOLD - LONG »."""
    t = str(texte or "")
    return "J'ENTRE MAINTENANT" in t or bool(_ENTREE_RE.match(t.split("\n", 1)[0].strip()))

_RAISONS = (   # (mots-clés, abréviation de 2 mots) — la première qui correspond gagne
    (("zone extrême", "daily / weekly", "daily/weekly"), "Zone extrême D/W"), (("4 h est neutre", "4h est neutre", "4 h neutre"), "4h neutre"),
    (("ne confirme pas", "1 h doit confirmer", "1h doit confirmer"), "1h non confirmé"), (("news", "annonce"), "News proche"),
    (("revenir en zone", "pas encore dans la zone", "hors zone"), "Hors zone"), (("trop tard", "déjà parti", "étiré"), "Trop tard"),
    (("alignement", "unités"), "Alignement <8"), (("stop trop", "risque trop", "sl trop"), "Stop trop loin"), (("rejet", "mèche"), "Attente rejet"),
    (("neutre",), "Marché neutre"))

def raison_2_mots(texte):
    """Raison de l'attente en 2 mots (abréviation), jamais une phrase : « Hors zone », « 1h non confirmé », « News proche »…"""
    t = str(texte or "").lower()
    for mots, court in _RAISONS:
        if any(k in t for k in mots):
            return court
    mots = re.sub(r"[^\w' /<>-]", " ", str(texte or "")).split()
    return " ".join(mots[:3]) or "Pas de signal"

def dxy_court(macro):
    """DXY en 2-3 mots, issu de macro_confluence (variation réelle sur 1 h) : « Haussier ⚠️ +0,13 %/1h »."""
    if not macro or not macro.get("disponible"):
        return "n/d"
    d, v = str(macro.get("dollar_direction", "")), macro.get("dxy_variation_1h_pct") or 0.0
    base = "Haussier ⚠️" if "HAUSS" in d else "Baissier" if "BAISS" in d else "Stable"
    return f"{base} {v:+.2f} %/1h".replace(".", ",")

def news_prochaine_courte(etat, now=None):
    """Prochaine annonce (24 h) : « CPI USA 14:30 (dans 15 min) » ou « Aucune »."""
    now = time.time() if now is None else now
    ev = sorted((e for e in ((etat or {}).get("cal", {}) or {}).get("ev", []) if now - 15 * 60 <= e["t"] <= now + 24 * 3600), key=lambda e: e["t"])
    if not ev:
        return "Aucune"
    e = ev[0]
    dans = int((e["t"] - now) // 60)
    return f"{e['titre']} {heure(e['t'])}" + (f" (dans {dans} min)" if 0 < dans <= 60 else " (en cours)" if dans <= 0 else "")

def niveaux_rs(r):
    """(résistance, support) les plus proches parmi les niveaux 1h / 4h / Daily — jamais inventés."""
    if not r.get("m1"):
        return None, None
    prix = r["m1"][-1]["c"]
    niv = [v for v, n in (r.get("niveaux") or []) if n in ("1h", "4h", "Daily", "D") and v is not None]
    return min((v for v in niv if v > prix), default=None), max((v for v in niv if v < prix), default=None)

def statut_sys(etat, r, now=None):
    """Micro-ligne de preuve : chaque ✅ / ❌ vient d'un état réel (TradingView, news, DXY, agent)."""
    now = time.time() if now is None else now
    tv = bool(((r or {}).get("tv_indicator_mtf") or {}).get("available"))
    news = bool([e for e in ((etat or {}).get("cal", {}) or {}).get("ev", []) if e["t"] >= now - 15 * 60])
    dxy = bool(((r or {}).get("macro_data") or {}).get("disponible"))
    ok = lambda b: "✅" if b else "❌"
    return f"🔌 Sys: TV{ok(tv)} News{ok(news)} DXY{ok(dxy)} Agent✅"

def carte_coach(m, r, cle, genre, tr=None, raison=None, declencheur=None, signal=None, validite=None, etat=None):
    """Carte unique (charte du propriétaire) : titre, [raison], ordre, contexte (DXY, news, niveaux), agent auto-trade, action, statut système.
    genre « signal » (trade validé) ou « attente ». Aucune donnée supprimée : tout est compressé en abréviations, une information par ligne."""
    etat = etat if etat is not None else DERNIER_ETAT
    macro = r.get("macro_data")
    res, sup = niveaux_rs(r)
    if genre == "signal":
        d = tr["d"]
        l = [f"{'🟢' if d == 1 else '🔴'} {m} - {'LONG' if d == 1 else 'SHORT'}", ""]      # sens en PREMIER, en couleur (vert LONG / rouge SHORT)
        rr = abs(tr["tp1"] - tr["e"]) / max(abs(tr["e"] - tr["sl"]), 1e-9)
        tps = px(tr["tp1"]) + (f" / {px(tr['tp2'])}" if tr.get("tp2") is not None and tp2_affichable(d, tr["tp1"], tr["tp2"]) else "")
        # Ordre du GRAPHIQUE (du plus haut au plus bas) : SHORT = SL, entrée, TP1, TP2 ; LONG = TP2, TP1, entrée, SL
        vue_ = f" (vue {tr['sl_ut']})" if tr.get("sl_ut") else ""
        niv = [(f"🛑 SL : {px(tr['sl'])}" + (" (mèche 5 min)" if tr.get("sl_ut") == "5 min" else ""), tr["sl"]),
               (f"🎯 Entrée : {px(tr['e'])}{vue_}", tr["e"]), (f"💰 TP1 : {px(tr['tp1'])}", tr["tp1"])]
        if tr.get("tp2") is not None and tp2_affichable(d, tr["tp1"], tr["tp2"]):
            niv.append((f"🏁 TP2 : {px(tr['tp2'])}", tr["tp2"]))
        l += [x for x, _ in sorted(niv, key=lambda z: -z[1])] + [f"⚖️ R:R : 1:{rr:.1f}".replace(".", ",")]
        if validite:
            l.append(f"⏱ Valide : {validite}")
        try:
            co = coach_fvg(r, d, r["m1"][-1]["c"], attente=False) if r.get("m1") else []
            l += [""] + co if co else []
        except Exception:
            pass
        action = "ENTRER"
    else:
        l = [f"📍 {m} - ATTENTE", "", f"⏳ Raison : {raison}"]
        if declencheur:
            l.append(f"🚀 Déclencheur : {declencheur}")
        zp = r.get("zone_pine") if r.get("dirPlan") else None
        o = (cle or {}).get("ordre")
        if o or zp:
            za, zb = (min(o.get("za", o["e"]), o.get("zb", o["e"])), max(o.get("za", o["e"]), o.get("zb", o["e"]))) if o else (min(zp["za"], zp["zb"]), max(zp["za"], zp["zb"]))
            l.append(f"🔑 Zone : {px(za)} → {px(zb)}")
        try:
            l += coach_fvg(r, r.get("dirPlan") or 0, r["m1"][-1]["c"]) if r.get("m1") and not o else []
        except Exception:
            pass
        action = "NE PAS RENTRER"
        try:
            pr = proximite_marche(m, r, cle, time.time())
            if 0 <= pr["rang"] <= 1 and _radar_n_ut(r, pr.get("d")) >= MIN_ALIGN and not r.get("annonce"):
                action = "Prêt à entrer"
        except Exception:
            pass
    l += ["", "📊 Contexte :"]
    if signal:
        l.append(f"🔹 Signal : {signal}")
    l += [f"🔹 DXY : {dxy_court(macro)}", f"🔹 News : {news_prochaine_courte(etat)}",
          f"🔹 Niveaux : R: {px(res) if res is not None else '—'} | S: {px(sup) if sup is not None else '—'}",
          "", f"🤖 Agent Auto-Trade : %%AGENT:{genre}%%", f"🛡️ Action : {action}", "", statut_sys(etat, r)]
    return "\n".join(l)

def carte_suivi(m, titre, lignes, action, r=None, genre="signal", d=None):
    """Carte compressée du suivi de position (TP, stop, BE…) : même charte que la carte signal. Rien n'est supprimé (niveaux, raison), les formules en moins."""
    fete = bool(re.search(r"TP\d TOUCHÉ|OBJECTIF FINAL", titre))
    if d is None:                                         # sens de la position en cours : LONG / SHORT toujours en PREMIER (demande d'Adel)
        d = (((DERNIER_ETAT or {}).get(m) or {}).get("trade") or {}).get("d")
    sens_ = (f"{'🟢 LONG' if d == 1 else '🔴 SHORT'} " if d in (1, -1) else "")     # UNE seule ligne de titre : le sens en premier, en couleur
    tete = [f"🎉🥳 {sens_}{m} - {titre} 🎯💰", "🎊🎊🎊🎊🎊"] if fete else [f"{sens_ or '📍 '}{m} - {titre}"]   # un TP se fête
    return "\n".join(tete + [""] + list(lignes) + ["", f"🤖 Agent Auto-Trade : %%AGENT:{genre}%%", f"🛡️ Action : {action}", "", statut_sys(DERNIER_ETAT, r or {})])

def agent_pour(etat, cid, marche, genre):
    """Statut « Agent Auto-Trade » PAR COMPTE (réglage « Mon bot ») : OFF · Attente · ON. Chaîne commune : « Actif »."""
    cid = str(cid)
    if cid == str(etat.get("canal") or ""):
        return "Actif"
    if not bot_on(etat, cid):
        return "OFF"
    return "ON" if genre == "signal" or ((etat.get(marche) or {}).get("trade")) else "Attente"

def erreur_technique(connexion):
    """Une donnée manquante n'est jamais un pavé : une ligne."""
    return f"⚠️ [Erreur technique : {connexion}]"

def notifier_erreur_technique(etat, nom, now=None):
    """Charte : une donnée manquante ou buguée = UNE ligne « ⚠️ [Erreur technique : …] », au propriétaire, au plus une fois par 30 min et par source."""
    now = time.time() if now is None else now
    mem = etat.setdefault("err_tech", {})
    if now - mem.get(nom, 0) < 1800:
        return False
    mem[nom] = now
    for cid in sorted(str(x) for x in proprio(etat)):
        _envoi_sur(cid, text=erreur_technique(nom))
    return True

def validite_cloture(r, unite="15m"):
    """« jusqu'à la clôture 15 min (HH:MM) » à partir de la vraie horloge de bougie."""
    try:
        fin = prochaine_cloture_bougie(r, unite, time.time())
        return f"jusqu'à la clôture {unite.replace('m', ' min')} ({datetime.datetime.fromtimestamp(fin, PARIS).strftime('%H:%M')})"
    except Exception:
        return f"clôture {unite.replace('m', ' min')}"

def mise_en_forme(t):
    """Tous les messages rangés pareil pour mobile : titre en haut, puis une info par ligne « intitulé : valeur »."""
    if not isinstance(t, str) or not t:
        return t
    # Idempotent : les messages peuvent repasser ici après une première mise en forme.
    t = _normalise_prix_dans_texte(t)
    lignes = epurer_blabla(t.split("\n"))
    titre2 = False                       # le titre « X — 🟠 BTC » reste sur une seule ligne
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
        elif " | " in l and not l.startswith(("http", "🔗", "🎯 Entrée :", "💰 TP :", "🔹 Niveaux :")):      # paires compressées de la carte coach
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
    # Présentation mobile compacte : une info par ligne « intitulé : valeur »,
    # titre seul en haut puis une ligne vide, pas de ligne vide entre chaque info.
    out = []
    for k, l in enumerate(plat):
        if not l:
            if out and out[-1]:
                out.append("")
            continue
        if l in STATUT_LIB:
            out.append("🚦 " + STATUT_LIB[l][1])
            continue
        if l.startswith("🚦 ") and k + 1 < len(plat) and l in [v[0] for v in STATUT_LIB.values()]:
            continue
        niveau = re.match(
            r"^(?P<label>.*?\b(?:TP\s*[12]|SL|STOP(?: LOSS)?|ENTR[ÉE]E?|ENTRY|SORTIE|EXIT|OBJECTIF(?: FINAL)?|TARGET|BREAK EVEN|BE)\b[^:：]*?)"
            r"\s*(?::|：|≈|=)\s*(?P<value>[+-]?(?:\d{1,3}(?:[ \u202f]\d{3})+|\d+)(?:[.,]\d+)?%?"
            r"(?:\s*[–—→]\s*(?:\d{1,3}(?:[ \u202f]\d{3})+|\d+)(?:[.,]\d+)?%?)?)"           # plage « A – B » : les deux bornes restent ensemble
            r"(?:\s*(?P<detail>.*))?$", l, re.IGNORECASE)
        # Un détail qui continue la phrase (« 5 minutes (… », « 0,12 % du prix », « 1:2.1 ») n'est pas un détail entre parenthèses :
        # reformater couperait la ligne et déséquilibrerait les parenthèses. Seuls « (… », « — … », « , … » sont des détails.
        if niveau:
            reste = (niveau.group("detail") or "").strip()
            if reste and not reste.startswith(("(", "—", "–", "-", ",", ";", "•", "→", "[")):
                niveau = None
        if niveau and len(niveau.group("label").strip()) <= 48:
            label = niveau.group("label").strip().rstrip(" :：≈=")
            bornes = re.split(r"\s*([–—→])\s*", niveau.group("value"))
            value = (" → ".join(_compacte_prix(b) for b in bornes[0::2]) if len(bornes) == 3 else _compacte_prix(niveau.group("value")))   # toujours « A → B » : lisible, jamais confondu avec une parenthèse
            detail = (niveau.group("detail") or "").strip()
            plage = re.match(r"^[—–-]\s*([+-]?(?:\d{1,3}(?:[ \u202f]\d{3})+|\d+)(?:[.,]\d+)?)\s*(.*)$", detail)
            if plage:                    # « zone 3981,48 – 4012,15 » : la 2e borne reste une borne, pas un détail entre parenthèses
                value = f"{value} → {_compacte_prix(plage.group(1))}"
                detail = plage.group(2).strip()
            detail = re.sub(r"^[()\[\]—–,:; ]+|[()\[\] ]+$", "", detail)
            out.append(f"{label} : {value}" + (f" ({detail})" if detail and len(detail) <= 40 else ""))
            if detail and len(detail) > 40:
                out.append(f"   ↳ {detail}")
            continue
        if l.endswith(" :") or l.endswith(":"):
            l = l.rstrip(" :")
        out.append(l)
        if k == 0:
            out.append("")
    txt = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", txt).strip()

TELEGRAM_HTML = os.environ.get("TELEGRAM_HTML", "1") == "1"   # 0 = retour à l'ancien rendu texte brut
SEPARATEUR = "━━━━━━━━━━━━━━━"
_UNITE_RE = re.compile(r"(?<![\w<])(1m|2m|3m|5m|10m|15m|30m|45m|1h|2h|4h|D)(?= (?:⬆️|⬇️|➖))")

def _majuscule(l):
    lettres = [c for c in l if c.isalpha()]
    return len(lettres) >= 5 and sum(c.isupper() for c in lettres) / len(lettres) >= 0.8

NIVEAUX_GRAS = ("🎯 Entrée", "🛑 Stop", "🛑 SL", "💰 TP", "· Résistance", "· Support", "🎯 Entry")

def rendu_html(t):
    """Design Telegram (parse_mode HTML) : titre en gras + séparateur, sections MAJUSCULES en gras
    entre séparateurs, intitulés en gras, unités en monospace (fond gris), notes ℹ️ en italique."""
    if not isinstance(t, str) or not t.strip():
        return t
    esc = lambda x: x.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    lignes = t.split("\n")
    out = []
    sep = lambda: out and out[-1] != SEPARATEUR and out.append(SEPARATEUR)
    for k, brut in enumerate(lignes):
        l = brut.strip()
        if not l:
            if out and out[-1] not in ("", SEPARATEUR):        # charte : un saut de ligne entre les blocs (jamais deux, jamais juste sous le titre)
                out.append("")
            continue
        if re.fullmatch(r"[━─➖=\-]{6,}", l):
            sep(); continue
        if k == 0:
            out.append(f"<b>{esc(l)}</b>"); out.append(SEPARATEUR); continue
        if l.startswith(("ℹ️", "Aucun ordre", "⚠️ Cette zone est un repère")):
            out.append(f"<i>{esc(l)}</i>"); continue
        if l.startswith(("http", "👉 http")):
            out.append(esc(l)); continue
        m = re.match(r"^(.{2,34}?) : (.+)$", l)
        if m and "http" not in m.group(1):
            lab, val = esc(m.group(1)), esc(m.group(2))
            if _majuscule(m.group(1)) and len(l) <= 40 and not re.search(r"\d", m.group(2)):
                sep()
            val = _UNITE_RE.sub(lambda u: f"<code>{u.group(1)}</code>", val)
            if lab.startswith(("⚡", "🏔")) and _UNITE_RE.search(m.group(2) or ""):
                out.append(f"<b>{lab} :</b>"); out.append(val); continue
            if m.group(1).startswith(NIVEAUX_GRAS):            # niveaux importants en gras (charte)
                val = f"<b>{val}</b>"
            out.append(f"<b>{lab} :</b> {val}"); continue
        if _majuscule(l) and len(l) <= 60:
            sep(); out.append(f"<b>{esc(l)}</b>"); continue
        out.append(_UNITE_RE.sub(lambda u: f"<code>{u.group(1)}</code>", esc(l)))
    while out and out[-1] in ("", SEPARATEUR):
        out.pop()
    return "\n".join(out)

# Telegram peut imposer un délai de plusieurs heures après un dépassement de quota.
# Le cooldown est isolé par chat pour ne pas bloquer les autres destinataires.
TELEGRAM_RETRY_UNTIL = {}


def _telegram_cooldown_restant(chat_id, maintenant=None):
    cle = str(chat_id) if chat_id is not None else "__global__"
    maintenant = time.time() if maintenant is None else float(maintenant)
    restant = max(0.0, float(TELEGRAM_RETRY_UNTIL.get(cle, 0)) - maintenant)
    if restant <= 0:
        TELEGRAM_RETRY_UNTIL.pop(cle, None)
    return restant


def _telegram_verifie_cooldown(chat_id, maintenant=None):
    restant = _telegram_cooldown_restant(chat_id, maintenant)
    if restant > 0:
        raise RuntimeError(
            f"Telegram cooldown actif pour {chat_id}: réessai dans {int(restant + 0.999)} s; "
            "aucune requête réseau répétée"
        )


def _telegram_enregistre_429(chat_id, erreur, maintenant=None):
    match = re.search(r"retry after\s+(\d+)", str(erreur), re.IGNORECASE)
    if not match:
        return 0
    delai = max(1, int(match.group(1)))
    cle = str(chat_id) if chat_id is not None else "__global__"
    maintenant = time.time() if maintenant is None else float(maintenant)
    TELEGRAM_RETRY_UNTIL[cle] = max(float(TELEGRAM_RETRY_UNTIL.get(cle, 0)), maintenant + delai)
    return delai


def telegram(methode, **params):
    if methode == "answerCallbackQuery":
        callback_id = str(params.get("callback_query_id", ""))
        if callback_id and callback_id in CALLBACKS_ACKNOWLEDGED:
            CALLBACKS_ACKNOWLEDGED.discard(callback_id)
            return {"ok": True, "result": True}
    if methode in ("sendMessage", "editMessageText") and "%%AGENT:" in str(params.get("text", "")):
        t_ = str(params["text"]); mk_ = re.search(r"📍 (\w+) - ", t_)
        params["text"] = re.sub(r"%%AGENT:(\w+)%%", lambda g: agent_pour(DERNIER_ETAT or {}, params.get("chat_id"), mk_.group(1) if mk_ else "", g.group(1)), t_)
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
        if TELEGRAM_HTML and "parse_mode" not in params and any(k in params for k in ("text", "caption")):
            for k in ("text", "caption"):
                if k in params:
                    params[k] = rendu_html(params[k])
            params["parse_mode"] = "HTML"
    chat_id = params.get("chat_id")
    # Sans chat (getUpdates, setMyName…) : blocage PAR MÉTHODE. Un 429 de plusieurs heures sur setMyName
    # ne doit jamais rendre le bot sourd (getUpdates bloqué = boutons sans réponse).
    cle_cooldown = chat_id if chat_id is not None else f"__{methode}__"
    _telegram_verifie_cooldown(cle_cooldown)
    url = f"https://api.telegram.org/bot{TOKEN}/{methode}"
    try:
        resultat = http_json(url, urllib.parse.urlencode(params).encode())
    except Exception as ex:
        if "HTTP Error 429" in str(ex):
            delai = _telegram_enregistre_429(cle_cooldown, ex)
            if delai:
                print(f"telegram rate limit chat={chat_id}: pause {delai}s; envoi suspendu sans nouvel appel")
        raise
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
CLAVIER = json.dumps({"keyboard": [[{"text": "🥇 Analyse Gold"}, {"text": "🟠 Analyse BTC"}, {"text": "💠 Analyse Nasdaq"}],
                                   [{"text": "📊 Faire une analyse"}, {"text": "📡 Mes marchés"}],
                                   [{"text": "🤖 Mon bot"}, {"text": "📈 Mes résultats"}],
                                   [{"text": "📸 Partager mon gain"}, {"text": "🧩 Indicateur TradingView"}],
                                   [{"text": "🔴 Live TikTok"}, {"text": "🌐 English"}]],
                      "resize_keyboard": True, "is_persistent": True, "input_field_placeholder": "Choisis une action ALIGN"})
CLAVIER_VISITEUR = json.dumps({"keyboard": [[{"text": "🥇 Analyse Gold"}, {"text": "🟠 Analyse BTC"}, {"text": "💠 Analyse Nasdaq"}],
                                            [{"text": "📊 Faire une analyse"}, {"text": "📡 Mes marchés"}],
                                            [{"text": "🤖 Mon bot"}, {"text": "💎 Devenir VIP"}],
                                            [{"text": "📸 Partager mon gain"}],
                                            [{"text": "🔴 Live TikTok"}, {"text": "🌐 English"}]],
                               "resize_keyboard": True, "is_persistent": True, "input_field_placeholder": "Choisis une action ALIGN"})
AVERTISSEMENT = ("ℹ️ Ce sont MES positions personnelles, partagées à titre informatif et éducatif. "
                 "Ce n'est pas un conseil en investissement ni une recommandation personnalisée. "
                 "Le trading (CFD, futures, crypto) peut faire perdre tout le capital investi : chacun décide seul et reste responsable de ses choix.")
MINI_AVERT = "ℹ️ Analyse indicative : décision et ordre sous ta responsabilité."
REGLES = ("📌 RÈGLES — ALIGN Signaux\n"
          "━━━━━━━━━━━━\n"
          "📡 Marchés : 🟠 BTC (BTCUSD) • 🥇 GOLD (XAUUSD) • 💠 NASDAQ (NAS100)\n"
          "👉 Choisis les tiens : bouton 📡 Mes marchés (tu ne reçois que ceux cochés)\n"
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
          "📰 News et IA en direct : dans ALIGN VIP 💎\n"
          "🤖 Les abonnés au suivi sont enregistrés automatiquement à l'ouverture du signal.\n"
          "📈 Les résultats sont calculés à la clôture réellement constatée.\n"
          "🧩 Indicateur TradingView : bouton 🧩 en bas (ne signifie pas que ses signaux sont reçus automatiquement)\n"
          "━━━━━━━━━━━━\n"
          "🤝 Partage à tes amis :\n"
          "👉 https://t.me/align_mtf_adel_bot")

def epingler(etat, cid):
    """Envoie les règles et les épingle en haut de la conversation (une seule fois par conversation)."""
    if cid in etat.setdefault("epingles_v5", []):
        return
    try:                                  # mémoire perdue (redémarrage) : on regarde ce qui est DÉJÀ épinglé — jamais deux fois les mêmes règles
        pm = ((telegram("getChat", chat_id=cid) or {}).get("result") or {}).get("pinned_message") or {}
        if str(pm.get("text") or "").startswith(REGLES.split("\n")[0].strip()[:18]):
            etat["epingles_v5"].append(cid)
            return
    except Exception as ex:
        print("epingler getChat", cid, ex)
    try:
        res = telegram("sendMessage", chat_id=cid, text=REGLES, disable_notification="true")
        telegram("pinChatMessage", chat_id=cid, message_id=res["result"]["message_id"], disable_notification="true")
        etat["epingles_v5"].append(cid)
    except Exception as ex:
        print("epingler", cid, ex)

PARTAGE_JOURS = int(os.environ.get("PARTAGE_JOURS", "3"))  # rappel « partage à tes amis » tous les X jours
PARTAGE_HEURE = int(os.environ.get("PARTAGE_HEURE", "18"))  # heure de Paris du rappel de partage
PROPRIO_VUE_GRATUITE = os.environ.get("PROPRIO_VUE_GRATUITE", "0") == "1"  # 1 = propriétaire toujours en vue gratuite

def vue_gratuite(etat, cid):
    """Conversation privée côté GRATUIT : visiteurs + propriétaire (pour voir exactement ce que reçoit un gratuit).
    Le VIP complet (news, analyses, toutes les positions) ne part QUE dans la chaîne ALIGN VIP."""
    cid = str(cid)
    return cid in [str(c) for c in etat.get("prospects", [])] or (
        (PROPRIO_VUE_GRATUITE or etat.get("proprio_gratuit")) and cid in {str(x) for x in proprio(etat)})

def destinataires_gratuits(etat):
    return list(dict.fromkeys([str(c) for c in etat.get("prospects", [])]
                              + ([str(x) for x in sorted(proprio(etat))] if (PROPRIO_VUE_GRATUITE or etat.get("proprio_gratuit")) else [])))

def partage_du(etat, maintenant=None):
    """Le rappel de partage part au plus une fois par jour prévu, à heure fixe : jamais deux fois de suite."""
    now = maintenant or datetime.datetime.now(PARIS)
    jour = now.strftime("%Y-%m-%d")
    if now.hour != PARTAGE_HEURE or now.date().toordinal() % max(1, PARTAGE_JOURS) or etat.get("partage_jour") == jour:
        return False
    etat["partage_jour"] = jour
    etat["partage_t"] = time.time()
    return True

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
    nasdaq = "nasdaq" in t or "nas100" in t or "nq" in t.split()
    if btc + gold + nasdaq > 1:
        return None                 # demande explicite de plusieurs marchés
    if btc:
        return "BTC"
    if nasdaq:
        return "NASDAQ"
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
    m = next((k for k, v in MARCHES.items() if v == pair), None)
    r = analyser(pair, (etat or {}).setdefault(m, {}).setdefault("pine", {}) if m else None)
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
    position = m and (est_entree(texte) or any(k in texte for k in ("TP1", "TP2", "BE", "STOP", "Stop", "SL", "parti")))
    # Chaîne VIP épurée : Telegram n'autorise pas le bouton bleu « Menu » ni le clavier dans une chaîne.
    # → 1 seul bouton sous chaque message : il ouvre le bot, où le VIP retrouve le MÊME menu que le gratuit.
    if position and est_entree(texte):
        lignes.append([{"text": "📍 Je prends cette position", "url": lien("rentre")}])
    lignes.append([{"text": "🤖 Ouvrir mon menu ALIGN", "url": lien("boutons")}])
    return json.dumps({"inline_keyboard": lignes})

def menu_canal_vip(etat):
    """Chaîne VIP : Telegram n'autorise pas le clavier du bas dans une chaîne → menu à boutons épinglé en haut (1 seule fois)."""
    if not etat.get("canal") or etat.get("menu_vip_v1"):
        return
    try:                                  # déjà épinglé (mémoire perdue au redémarrage) : on ne le renvoie pas
        pm = ((telegram("getChat", chat_id=etat["canal"]) or {}).get("result") or {}).get("pinned_message") or {}
        if "MENU ALIGN VIP" in str(pm.get("text") or ""):
            etat["menu_vip_v1"] = pm.get("message_id") or 1
            return
    except Exception as ex:
        print("menu VIP getChat", ex)
    bot = etat.get("bot") or "align_mtf_adel_bot"
    lien = lambda p: f"https://t.me/{bot}?start={p}"
    kb = json.dumps({"inline_keyboard": [
        [{"text": "🥇 Analyse Gold", "url": lien("analyse_gold")}, {"text": "🟠 Analyse BTC", "url": lien("analyse_btc")}],
        [{"text": "📊 Faire une analyse", "url": lien("faire_analyse")}, {"text": "📡 Mes marchés", "url": lien("marches")}],
        [{"text": "🤖 Mon bot", "url": lien("mon_bot")}, {"text": "📈 Mes résultats", "url": lien("resultats")}],
        [{"text": "📸 Partager mon gain", "url": lien("gain")}, {"text": "🧩 Indicateur TradingView", "url": lien("indicateur")}]]})
    try:
        res = telegram("sendMessage", chat_id=etat["canal"], text="💎 MENU ALIGN VIP\n👇 Touche un bouton : il s'ouvre dans ton bot", reply_markup=kb, disable_notification="true")
        telegram("pinChatMessage", chat_id=etat["canal"], message_id=res["result"]["message_id"], disable_notification="true")
        etat["menu_vip_v1"] = res["result"]["message_id"]
    except Exception as ex:
        print("menu VIP", ex)

# ───────── IA (GitHub Models, gratuite avec le jeton GitHub du workflow) ─────────
# IA : Google Gemini (gratuit). GitHub Models a été fermé le 30/07/2026 → clé GEMINI_API_KEY dans les secrets GitHub.
# IA : plusieurs IA GRATUITES à la suite — si l'une tombe, la suivante répond (aucune clé obligatoire).
# 1) Google Gemini (si la clé GEMINI_API_KEY existe)  2) OVHcloud Llama 3.3 70B (sans clé)  3) OVHcloud Mistral (sans clé)
# 4) Pollinations (sans clé)  5) LLM7 (sans clé). Et si TOUT tombe : l'analyse interne du bot répond quand même.
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
IA_FOURNISSEURS = [
    # 1) Gemini (niveau gratuit, API native). « Gemini 3.8 » = modèle recommandé par Google (gemini-2.5-flash est refusé aux nouveaux comptes, 404 constaté) : essayé en premier pour la recherche Google ; si le grounding gratuit est refusé, repli silencieux sur la chaîne.
    ("Gemini", GEMINI_BASE, os.environ.get("GEMINI_MODEL") or "gemini-3.6-flash", _GEMINI_KEY, True),
    ("Gemini 3.8", GEMINI_BASE, "gemini-3.8-flash", _GEMINI_KEY, True),
    # 2) Groq (plan gratuit, ~8K tokens/min : prompts courts + intervalle minimal)
    ("Groq", "https://api.groq.com/openai/v1/chat/completions", os.environ.get("GROQ_MODEL") or "openai/gpt-oss-120b", os.environ.get("GROQ_API_KEY", ""), True),
    # 3) IA sans clé
    ("OVH Llama", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions", "Meta-Llama-3_3-70B-Instruct", "", False),
    ("OVH Mistral", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions", "Mistral-Small-3.2-24B-Instruct", "", False),
    ("Pollinations", "https://text.pollinations.ai/openai", "openai", "", False),
    ("LLM7", "https://api.llm7.io/v1/chat/completions", "default", "", False),
    # 4) Payants : seulement sans aucune IA gratuite disponible (OpenAI n'est actif que si une clé est fournie)
    ("OpenAI", "https://api.openai.com/v1/chat/completions", os.environ.get("OPENAI_MODEL") or "chat-latest", os.environ.get("OPENAI_API_KEY", ""), True),
    # Claude Haiku : dernier recours, moments clés VIP seulement (premium=True), plafond/jour ANTHROPIC_MAX_JOUR, ignoré sans crédit.
    ("Anthropic", "https://api.anthropic.com/v1/messages", os.environ.get("ANTHROPIC_MODEL") or "claude-haiku-5-5", os.environ.get("ANTHROPIC_API_KEY", ""), True),
]
# Limites gratuites : appels par jour et intervalle minimal entre deux appels (secondes)
IA_PLAFOND_JOUR = {"Gemini": int(os.environ.get("GEMINI_MAX_JOUR") or "250"), "Gemini 3.8": int(os.environ.get("GEMINI_MAX_JOUR") or "250"),
                   "Groq": int(os.environ.get("GROQ_MAX_JOUR") or "500")}
IA_INTERVALLE_MIN = {"Groq": 20}
IA_RESUME_CAR = {"Groq": 3500, "Anthropic": 2500}         # entrée courte : Groq (8K tokens/min), Claude (coût)
GEMINI_RECHERCHE_MAX_JOUR = int(os.environ.get("GEMINI_SEARCH_MAX_JOUR") or "100")   # recherches Google/jour (quota gratuit : 500)
CLAUDE_CACHE_SEC = 600                                    # Claude : au plus 1 appel / 10 min par marché et par type de moment
CLAUDE_PAUSE_CREDIT_SEC = 6 * 3600                        # sans crédit : on n'insiste pas avant 6 h
IA_MAX_JOUR = int(os.environ.get("IA_MAX_JOUR", "300"))
ANTHROPIC_MAX_JOUR = int(os.environ.get("ANTHROPIC_MAX_JOUR") or "100")     # appels Claude par jour (au-delà : IA gratuites)
ANTHROPIC_MAX_TOKENS = 300                                                  # réponse courte : 4 lignes
IA_REGLES = ("Tu es l'analyste de marché du bot ALIGN. Tu reçois des données chiffrées réelles calculées par le moteur ; tu dois les interpréter, pas les remplacer. "
             "Architecture : H4 = biais directeur, H1 = confirmation, M15 = structure/retracement, M5 = déclencheur après clôture ; M1 = suivi du prix. "
             "Sépare tendance, scénario privilégié, scénario alternatif, validation, invalidation et prochaine action. "
             "Utilise UNIQUEMENT les données fournies : aucun prix, niveau, indicateur, événement ou horaire inventé. "
             "Ne transforme jamais une probabilité en certitude. N'annonce jamais une entrée avant confirmation. Respecte le verdict interne ALIGN. "
             "Un setup M15/M5 contre H4/H1 est un scalp contre-tendance, jamais un swing. Une mèche seule ne confirme pas une entrée. "
             "Le prochain horaire de clôture fourni est une heure de réévaluation, PAS une promesse d'entrée. "
             "DXY, EUR/USD et US10Y sont du contexte uniquement ; si les données sont absentes ou anciennes, signale-le. "
             "US10Y est une donnée officielle quotidienne, jamais une cotation intraday. Pas de promesse de gain. Langage direct, concret et sans remplissage. "
             "Les niveaux (entrée, TP1, TP2, SL, zone) sont calculés par l'indicateur : tu les ANALYSES, tu ne les changes JAMAIS et tu n'en proposes pas d'autres. "
             "Si le plan te semble risqué ou incohérent avec le contexte, dis clairement « je déconseille » et pourquoi ; sinon dis ce qui valide ou invalide le plan. "
             "N'écris aucun prix, niveau ou chiffre de marché absent des données fournies (même si une recherche web en donne).")

def detail_erreur_ia(ex, cle=""):
    """Code HTTP exact + message du fournisseur, sans jamais afficher la clé."""
    if isinstance(ex, urllib.error.HTTPError):
        msg = ""
        try:
            corps = json.loads(ex.read().decode("utf-8", "replace"))
            corps = corps[0] if isinstance(corps, list) and corps else corps
            err = corps.get("error", {}) if isinstance(corps, dict) else {}
            if isinstance(err, str):
                msg = err
            else:
                msg = f"{err.get('status') or err.get('type') or ''} {err.get('message', '')}".strip()
        except Exception:
            pass
        texte = f"HTTP {ex.code} {msg}".strip()
    else:
        texte = f"{type(ex).__name__} {ex}".strip()
    if cle:
        texte = texte.replace(cle, "***")
    return re.sub(r"(AIza|sk-ant-|gsk_)[0-9A-Za-z_\-]{20,}", "***", texte)[:200]

def erreur_sans_credit(detail):
    """Compte Anthropic sans crédit : erreur attendue, traitée sans bruit (pas une panne)."""
    d = str(detail).lower()
    return "credit balance" in d or "billing" in d or "insufficient" in d and "credit" in d

def resumer_donnees(obj, limite):
    """Entrée courte : listes raccourcies (8 derniers éléments), textes tronqués, nombres arrondis, JSON compact."""
    def r(o):
        if isinstance(o, dict):
            return {k: r(v) for k, v in list(o.items())[:40]}
        if isinstance(o, (list, tuple)):
            return [r(v) for v in list(o)[-8:]]
        if isinstance(o, float):
            return round(o, 4)
        return o[:200] if isinstance(o, str) else o
    t = json.dumps(r(obj), ensure_ascii=False, separators=(",", ":"))
    return t if len(t) <= limite else t[:limite] + "…(résumé)"

def prix_inventes(texte, donnees):
    """Nombres de type prix (≥ 100, hors années et pourcentages) absents des données fournies : l'IA n'a pas le droit de les écrire."""
    connus = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", json.dumps(donnees, ensure_ascii=False))]
    inventes = []
    for m in re.finditer(r"(?<![\w.])(\d{3,}(?:[.,]\d+)?)(?![\w]|\s?%)", str(texte)):
        n = float(m.group(1).replace(",", "."))
        if n < 100 or (n == int(n) and 1990 <= n <= 2100 and "." not in m.group(1) and "," not in m.group(1)):
            continue
        if not any(abs(n - c) <= max(0.5, 0.003 * abs(c)) for c in connus):
            inventes.append(m.group(1))
    return inventes

_SOURCES_IA = []        # sources de la dernière réponse avec recherche Google (noms de sites)

def _appel_ia(url, modele, cle, messages, recherche=False):
    h = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "align-bot"}
    anthropic = "api.anthropic.com" in url
    gemini = "generativelanguage.googleapis.com" in url
    if gemini:                                      # API native Gemini (seule à offrir la recherche Google), clé dans l'en-tête
        systeme = "\n".join(m["content"] for m in messages if m.get("role") == "system")
        utilisateur = "\n".join(m["content"] for m in messages if m.get("role") != "system")
        corps_ = {"systemInstruction": {"parts": [{"text": systeme}]}, "contents": [{"role": "user", "parts": [{"text": utilisateur}]}],
                  "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1000}}
        if recherche:
            corps_["tools"] = [{"google_search": {}}]
        corps = json.dumps(corps_).encode()
        h["x-goog-api-key"] = cle
        url = f"{url}/{modele}:generateContent"
    elif anthropic:                                 # API Messages d'Anthropic : consigne système séparée, clé dans x-api-key
        systeme = "\n".join(m["content"] for m in messages if m.get("role") == "system")
        corps = json.dumps({"model": modele, "temperature": 0.4, "max_tokens": ANTHROPIC_MAX_TOKENS, "system": systeme,
                            "messages": [m for m in messages if m.get("role") != "system"]}).encode()
        h["x-api-key"] = cle; h["anthropic-version"] = "2023-06-01"
    else:
        corps = json.dumps({"model": modele, "temperature": 0.4, "max_tokens": 1000, "messages": messages}).encode()
        if cle:
            h["Authorization"] = f"Bearer {cle}"
    with urllib.request.urlopen(urllib.request.Request(url, data=corps, headers=h), timeout=25) as rep_:
        j = json.loads(rep_.read().decode())
    if gemini:
        cand = (j.get("candidates") or [{}])[0]
        txt = "".join(p_.get("text", "") for p_ in (cand.get("content") or {}).get("parts", [])).strip()
        _SOURCES_IA.clear()
        if recherche:
            for ch in (cand.get("groundingMetadata") or {}).get("groundingChunks", []):
                web = ch.get("web") or {}
                nom = (web.get("title") or urllib.parse.urlparse(web.get("uri", "")).hostname or "").strip()
                if nom and nom not in _SOURCES_IA:
                    _SOURCES_IA.append(nom)
    elif anthropic:
        txt = "".join(b.get("text", "") for b in j.get("content", []) if b.get("type") == "text").strip()
    else:
        txt = (j["choices"][0]["message"].get("content") or "").strip()
    if len(txt) < 8:
        raise ValueError("réponse vide")
    return txt

def ligne_sources(etat, cle_cache):
    """« 🔎 Sources : … » si la réponse vient d'une recherche Google (jamais de source inventée)."""
    src = (etat.get("ia_sources") or {}).get(cle_cache) or []
    return ("\n🔎 Sources : " + ", ".join(src[:4])) if src else ""

def ia(etat, consigne, donnees, cle_cache=None, duree=600, premium=False, recherche=False):
    """Commentaire court d'une vraie IA. Ordre : Gemini -> Groq -> IA sans clé -> (payants) -> Claude en dernier recours.
    premium = moment clé VIP (seul cas où Claude peut être appelé) ; recherche = Google Search (analyse « En savoir plus » et news seulement).
    Compteurs par jour, intervalle minimal, pause croissante après échec, cache : jamais de boucle d'appels. '' si tout est tombé."""
    cache = etat.setdefault("ia_cache", {})
    if cle_cache and cle_cache in cache and time.time() - cache[cle_cache][0] < duree:
        return cache[cle_cache][1]
    maintenant = time.time()
    jour = datetime.datetime.now(PARIS).strftime("%Y-%m-%d")
    compte = etat.setdefault("ia_jour", {})
    if compte.get(jour, 0) >= IA_MAX_JOUR:
        etat["ia_dernier_fournisseur"] = "INTERNAL_FALLBACK"
        etat["ia_dernier_modele"] = None
        etat["ia_dernier_statut"] = "DAILY_LIMIT_INTERNAL_FALLBACK"
        print("AI_PROVIDER_USED=INTERNAL_FALLBACK reason=DAILY_LIMIT", flush=True)
        return ""
    txt, erreurs = "", []
    par_jour = etat.setdefault("ia_fournisseur_jour", {})
    claude_t = etat.setdefault("ia_claude_t", {})
    ordre = list(IA_FOURNISSEURS)
    if recherche:                                       # la recherche Google gratuite n'existe que sur Gemini 3.8 : on l'essaie d'abord
        ordre.sort(key=lambda f: 0 if f[0] == "Gemini 3.8" else 1)
    for nom, url, modele, cle, besoin_cle in ordre:
        if besoin_cle and not cle:
            continue
        compteur = par_jour.setdefault(nom, {})
        if nom == "Anthropic":
            if not premium or compteur.get(jour, 0) >= ANTHROPIC_MAX_JOUR:
                continue                                # Claude : moments clés VIP seulement, dans la limite du plafond du jour
            if cle_cache and maintenant - claude_t.get(cle_cache, 0) < CLAUDE_CACHE_SEC:
                continue                                # au plus 1 appel Claude / 10 min par marché et par type de moment
        elif nom in IA_PLAFOND_JOUR and compteur.get(jour, 0) >= IA_PLAFOND_JOUR[nom]:
            continue                                    # quota gratuit du jour atteint
        if maintenant < etat.get("ia_pause", {}).get(nom, 0):
            continue                                    # IA en panne récemment : on passe à la suivante
        if maintenant - etat.setdefault("ia_dernier_appel", {}).get(nom, 0) < IA_INTERVALLE_MIN.get(nom, 0):
            continue                                    # limite par minute du plan gratuit
        avec_recherche = bool(recherche and nom == "Gemini 3.8" and compteur.get(jour + "_recherche", 0) < GEMINI_RECHERCHE_MAX_JOUR)
        limite = IA_RESUME_CAR.get(nom)
        contexte = resumer_donnees(donnees, limite) if limite else json.dumps(donnees, ensure_ascii=False)
        messages = [{"role": "system", "content": IA_REGLES},
                    {"role": "user", "content": consigne + "\n\nDonnées :\n" + contexte}]
        etat["ia_dernier_appel"][nom] = maintenant
        try:
            brut = _appel_ia(url, modele, cle, messages, recherche=avec_recherche) if avec_recherche else _appel_ia(url, modele, cle, messages)
            faux = prix_inventes(brut, donnees)
            if faux:
                raise ValueError("prix absents des données : " + ", ".join(faux[:3]))      # l'IA n'invente jamais un prix
            txt = brut
            etat.setdefault("ia_ok", {})[nom] = int(maintenant)
            etat.setdefault("ia_echecs", {}).pop(nom, None)
            etat["ia_dernier_fournisseur"] = nom
            etat["ia_dernier_modele"] = modele
            etat["ia_dernier_statut"] = "CONNECTED"
            compteur[jour] = compteur.get(jour, 0) + 1
            if avec_recherche:
                compteur[jour + "_recherche"] = compteur.get(jour + "_recherche", 0) + 1
            for k in [k for k in compteur if not k.startswith(jour)]:
                compteur.pop(k)
            if nom == "Anthropic" and cle_cache:
                claude_t[cle_cache] = maintenant
            if cle_cache:
                srcs = etat.setdefault("ia_sources", {})
                if avec_recherche and _SOURCES_IA:
                    srcs[cle_cache] = list(_SOURCES_IA)
                else:
                    srcs.pop(cle_cache, None)
                for k in list(srcs)[:-20]:
                    srcs.pop(k)
            print(f"AI_PROVIDER_USED={nom} model={modele}" + (" search=google" if avec_recherche else ""), flush=True)
            break
        except Exception as ex:
            detail = detail_erreur_ia(ex, cle)
            erreurs.append(f"{nom}: {detail[:80]}")
            if nom == "Anthropic" and erreur_sans_credit(detail):
                etat.setdefault("ia_pause", {})[nom] = maintenant + CLAUDE_PAUSE_CREDIT_SEC   # sans crédit : silence, repli gratuit
                etat["ia_claude_credit"] = "NO_CREDIT"
            else:
                echecs = etat.setdefault("ia_echecs", {})
                echecs[nom] = min(echecs.get(nom, 0) + 1, 4)
                etat.setdefault("ia_pause", {})[nom] = maintenant + min(300 * 2 ** (echecs[nom] - 1), 3600)   # 5 min, 10, 20, 40… max 1 h
            print("ia", nom, modele, detail, flush=True)
    if not txt:
        etat["ia_dernier_fournisseur"] = "INTERNAL_FALLBACK"
        etat["ia_dernier_statut"] = "ALL_EXTERNAL_PROVIDERS_FAILED"
        print("AI_PROVIDER_USED=INTERNAL_FALLBACK", flush=True)
        etat["ia_err"] = " | ".join(erreurs)
        # Panne IA : uniquement dans les journaux techniques, jamais dans Telegram (rien à voir avec le trading).
        print("AI_ALL_PROVIDERS_FAILED", etat["ia_err"][:250], flush=True)
        return ""
    for k in list(compte):
        if k != jour:
            compte.pop(k)
    compte[jour] = compte.get(jour, 0) + 1
    if cle_cache:
        cache[cle_cache] = (maintenant, txt)
        for k in [k for k, v in cache.items() if maintenant - v[0] > 3600]:
            cache.pop(k)
    return txt

IA_TON_JEUNE = ("Réponds TOUJOURS en français. Ton : coach trading jeune et cool, tutoiement, phrases très simples, motivant, jamais vulgaire, "
                "jamais de promesse de gain. FORMAT : 4 lignes courtes maximum, une info par ligne, "
                "chaque ligne commence par un emoji, 12 mots maximum par ligne, aucun paragraphe.")

MOMENTS_IA = (
    ("prep", ("JE PRÉPARE UNE POSITION", "PRÉPARE-TOI", "ÇA ARRIVE"), 7200,
     "Une position se prépare. Dis à l'abonné de se tenir prêt, ce que tu vois en bougies maintenant, et ce qui validera l'entrée."),
    ("tp", ("TP1 TOUCHÉ", "TP2 TOUCHÉ", "TP3 TOUCHÉ", "TP4 TOUCHÉ", "TP5 TOUCHÉ", "OBJECTIF FINAL"), 3600,
     "Un objectif vient d'être touché. Félicite simplement, dis quoi faire maintenant (sécuriser, BE) et ce que le marché peut faire ensuite."),
    ("sl", ("STOP TOUCHÉ", "SORTI À BE", "SORTIE AU STOP SÉCURISÉ"), 1800,
     "La position vient de se fermer au stop (ou à BE). Dis-le clairement : on n'est plus en position. Explique simplement "
     "ce que les bougies ont fait, rassure (risque maîtrisé), et dis ce qu'on surveille maintenant (retournement confirmé ou pas). Jamais de reproche."),
    ("danger", ("RETOURNEMENT EN PRÉPARATION", "METS-TOI À BE"), 1800,
     "On est en position et la situation change (retournement possible ou passage à BE). Analyse les bougies maintenant, "
     "dis clairement si on reste en position, où est le SL et quoi faire tout de suite."),
    ("turbulence", ("MANIPULATION", "MOUVEMENT FORT", "RÉACTION À LA NEWS", "NEWS USA DANS", "MÈCHE SUSPECTE"), 1800,
     "Grosse turbulence ou news. Explique simplement ce qui se passe, le risque, et quoi faire (patience, SL, BE)."),
)

REGLE_SENS_IA = (" Ne prédis JAMAIS un sens à venir (ni haussier, ni baissier, ni LONG, ni SHORT) : décris seulement ce qui vient de se passer "
                 "et ce qu'il faut surveiller. Le sens vient uniquement de l'indicateur.")
_IA_BAISSIER = re.compile(r"baissi(?:er|ère)|\bvente\s+à\s+venir|va\s+(?:baisser|chuter|plonger|s'effondrer)|chute\s+à\s+venir", re.I)
_IA_HAUSSIER = re.compile(r"haussi(?:er|ère)|va\s+(?:monter|grimper)|hausse\s+à\s+venir", re.I)

def sens_ia_contradictoire(texte, sens):
    """Vrai si l'IA annonce un sens (haussier / baissier / LONG / SHORT) CONTRAIRE à celui de l'indicateur (et n'annonce pas aussi le bon).
    Les descriptions du passé (« forte baisse », « rebond ») ne sont pas des annonces de sens et ne déclenchent rien."""
    if sens not in (1, -1):
        return False
    t = str(texte or "")
    bear = bool(_IA_BAISSIER.search(t) or re.search(r"\bSHORT\b", t))
    bull = bool(_IA_HAUSSIER.search(t) or re.search(r"\bLONG\b", t))
    return (bear and not bull) if sens == 1 else (bull and not bear)

def commentaires_ia_temps_reel(etat, m, r, cle, nouveaux):
    """La vraie IA revient aux moments clés : préparation de l'entrée, TP touché, turbulence / news (1 fois par moment)."""
    out = []
    vus = etat.setdefault("ia_moments", {})
    for t in nouveaux or []:
        texte = t[0] if isinstance(t, tuple) else t
        if doublon_message(etat, str(texte), enregistrer=False):      # message principal supprimé (doublon) : pas de commentaire IA orphelin
            continue
        tete = str(texte).split("\n")[0].upper()
        for nom, cles, delai, consigne in MOMENTS_IA:
            if not any(k in tete for k in cles):
                continue
            k = f"{m}:{nom}"
            if time.time() - vus.get(k, 0) < delai:
                break
            vus[k] = time.time()
            try:
                avis = ia(etat, consigne + REGLE_SENS_IA + " " + IA_TON_JEUNE, dict(donnees_ia(m, r, cle), evenement=str(texte)[:600]),
                          cle_cache=f"moment:{k}", duree=delai, premium=True)
            except Exception as ex:
                print("ia moment", ex); avis = ""
            if avis and sens_ia_contradictoire(avis, r.get("sens")):
                print(f"IA_SENS_CONTRADICTOIRE {m} : commentaire IA non envoyé (annonce un sens contraire à l'indicateur)")
                avis = ""
            if avis:
                out.append(f"🧠 L'IA ALIGN EN DIRECT — {ICONE.get(m, '')} {m}\n{compacter_ia(avis)}")
            break
    return out

def resume_volume(bars, provenance, timeframe_sec=0, now_ts=None):
    """Résumé du volume sur bougies entièrement clôturées, jamais sur une bougie encore en formation."""
    bars = bars or []
    now_ts = time.time() if now_ts is None else now_ts
    if timeframe_sec:
        bars = [b for b in bars if int(b.get("t", 0)) + timeframe_sec <= now_ts]
    provenance = next((b.get("volume_source") for b in reversed(bars) if b.get("volume_source")), provenance)
    valeurs = [float(b["v"]) for b in bars if b.get("v") is not None and float(b["v"]) >= 0]
    if not valeurs:
        return {"disponible": False, "provenance": provenance, "interpretation": "volume indisponible : ne pas en tirer de confirmation"}
    recent = valeurs[-1]
    reference = valeurs[-21:-1]
    moyenne = sum(reference) / len(reference) if reference else 0.0
    ratio = recent / moyenne if moyenne > 0 else None
    return {
        "disponible": True, "provenance": provenance, "derniere_bougie": round(recent, 4),
        "moyenne_20_bougies": round(moyenne, 4) if reference else None,
        "ratio_vs_moyenne": round(ratio, 2) if ratio is not None else None,
        "etat": ("pic" if ratio is not None and ratio >= 1.5 else "faible" if ratio is not None and ratio <= 0.7 else "normal" if ratio is not None else "reference_insuffisante"),
        "nb_bougies": len(valeurs),
        "interpretation": "volume indicatif du flux source ; ne confirme jamais seul une entrée"
    }


def donnees_ia(m, r, cle):
    titre, raison = verdict(r, cle)
    o = (cle or {}).get("ordre") or {}
    dirs = r.get("dirs") or [0] * 11
    rsis = r.get("rsis") or [50] * 11
    data = {"marché": m, "prix": round(r["m1"][-1]["c"], 2),
            "sens 1m/5m/15m/1h/4h/Daily": [dirs[i] if len(dirs) > i else 0 for i in (0, 2, 4, 7, 9, 10)],
            "RSI 5m/15m/1h/4h": [round(rsis[i]) if len(rsis) > i else 50 for i in (2, 4, 7, 9)],
            "profil_strategie": profil_strategie(r),
            "plan_indicateur_tradingview": plan_indicateur(r),
            "snapshots_indicateur_tradingview": (r.get("tv_indicator_mtf") or {}).get("snapshots", {}),
            "lecture_multi_unites": {"M5": dirs[2] if len(dirs) > 2 else 0, "M15": dirs[4] if len(dirs) > 4 else 0, "H1": dirs[7] if len(dirs) > 7 else 0, "H4": dirs[9] if len(dirs) > 9 else 0},
            "position Daily (0 bas, 1 haut)": round(r.get("posD", 0.5), 2), "position Weekly": round(r.get("posW", 0.5), 2),
            "verdict du bot": titre + " / " + raison.replace("\n", " "),
            "zone d'entrée": [round(o["za"], 2), round(o["zb"], 2)] if o.get("za") else None,
            "niveau de cassure 5 min": round(niveau_cassure(r, r["confirme"]), 2) if r["confirme"] and len(r["b5"]) >= 22 else None,
            "contexte_macro_dollar": r.get("macro_data") or {},
            "volume": {
                "M5": resume_volume(r.get("b5"), {"BTC": "Kraken BTC spot", "NASDAQ": "CME NQ futures (proxy)"}.get(m, "Volume proxy GOLD (PAXG ou COMEX selon la source active)"), 300),
                "M15": resume_volume(r.get("b15"), {"BTC": "Kraken BTC spot", "NASDAQ": "CME NQ futures (proxy)"}.get(m, "Volume proxy GOLD (PAXG ou COMEX selon la source active)"), 900),
                "H1": resume_volume(r.get("b1h"), {"BTC": "Kraken BTC spot", "NASDAQ": "CME NQ futures (proxy)"}.get(m, "Volume proxy GOLD (PAXG ou COMEX selon la source active)"), 3600),
                "H4": resume_volume(r.get("b4h"), {"BTC": "Kraken BTC spot", "NASDAQ": "CME NQ futures (proxy)"}.get(m, "Volume proxy GOLD (PAXG ou COMEX selon la source active)"), 14400)
            },
            "news": (r.get("news") or "").replace("\n", " "), "distribution": bool(r.get("distrib")), "accumulation": bool(r.get("accum"))}
    # Position déjà ouverte : l'IA la commente (jamais « aucun prix d'entrée » pendant un trade).
    trx = (cle or {}).get("trade")
    if trx:
        data["position_ouverte"] = {"sens": "LONG" if trx["d"] == 1 else "SHORT", "entrée": round(trx["e"], 2),
                                    "SL": round(trx["sl"], 2), "TP1": round(trx["tp1"], 2),
                                    "TP2": round(trx["tp2"], 2) if trx.get("tp2") else None, "statut": trx.get("statut")}
    # Distance réelle au plan d'entrée et rythme observé : aide à décider si l'attente vaut la peine.
    prix_actuel = float(r["m1"][-1]["c"])
    plan = plan_indicateur(r)
    cible_entree = None
    origine_plan = None
    if plan.get("available"):
        cible_entree, origine_plan = float(plan["entry"]), "TradingView ROBOT V12 frais"
    elif o.get("e") is not None:
        cible_entree, origine_plan = float(o["e"]), "ordre ALIGN actif"
    if cible_entree is not None:
        distance = abs(cible_entree - prix_actuel)
        data["distance_plan_entree"] = {
            "prix_actuel": round(prix_actuel, 5), "entree_visee": round(cible_entree, 5),
            "distance_prix": round(distance, 5), "sens_du_deplacement": "hausse" if cible_entree > prix_actuel else "baisse" if cible_entree < prix_actuel else "au niveau actuel",
            "origine": origine_plan,
            "distance_en_ATR_15m": round(distance / max(float(r.get("atr") or 0), 1e-9), 2) if r.get("atr") else None
        }
    else:
        data["distance_plan_entree"] = {"disponible": False, "raison": "aucun ordre ALIGN ni plan TradingView frais avec prix d'entrée exploitable"}
    # Rythme des dernières bougies 5m : estimation indicative, jamais un compte à rebours garanti.
    b5 = r.get("b5") or []
    ranges = [max(float(b.get("h", 0)) - float(b.get("l", 0)), abs(float(b.get("h", 0)) - float(b.get("c", 0))), abs(float(b.get("l", 0)) - float(b.get("c", 0)))) for b in b5[-12:] if b.get("h") is not None and b.get("l") is not None and b.get("c") is not None]
    moyenne_5m = sum(ranges) / len(ranges) if ranges else 0
    if cible_entree is not None and moyenne_5m > 0:
        bougies = distance / moyenne_5m
        data["estimation_approche_entree"] = {
            "mouvement_moyen_5m": round(moyenne_5m, 5),
            "bougies_5m_indicatives": round(bougies, 1),
            "minutes_indicatives": round(bougies * 5),
            "avertissement": "projection mécanique fondée sur les 12 dernières bougies, non prédictive et à ne pas traiter comme heure d'entrée"
        }
    else:
        data["estimation_approche_entree"] = {"disponible": False, "raison": "pas de plan d'entrée exploitable ou historique 5m insuffisant"}
    # Les dernières bougies fournissent à l'IA une vraie lecture de structure (rebond, retracement, range).
    structure = {}
    for label, key in (("M5", "b5"), ("M15", "b15"), ("H1", "b1h"), ("H4", "b4h")):
        bars = (r.get(key) or [])[-4:]
        structure[label] = [
            {"o": round(float(b["o"]), 5), "h": round(float(b["h"]), 5),
             "l": round(float(b["l"]), 5), "c": round(float(b["c"]), 5)}
            for b in bars if all(b.get(k) is not None for k in ("o", "h", "l", "c"))
        ]
    data["structure_bougies_recentes"] = structure
    data["ATR_15m"] = round(float(r.get("atr") or 0), 5) or None
    tf = timeframe_attendu(r, cle or {})
    close_ts = prochaine_cloture_bougie(r, tf, time.time())
    data["prochaine_reevaluation"] = {
        "unite_bloquante": tf,
        "heure_locale": datetime.datetime.fromtimestamp(close_ts, PARIS).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "secondes_restantes": max(0, int(close_ts - time.time())),
        "signification": "réévaluation à la clôture, pas une prévision d'entrée"
    }
    return data

IA_LIGNES_MAX = 6
IA_LIGNE_MAX_CAR = 110


def compacter_ia(t):
    """Réponse IA rangée comme le reste : lignes courtes, une info par ligne, pas de pavé ni de conclusion."""
    if not isinstance(t, str) or not t.strip():
        return t
    lignes = []
    for brut in t.replace("**", "").split("\n"):
        l = re.sub(r"^[\s\-*•#>]+", "", brut).strip()
        if not l or re.match(r"(?i)^(en conclusion|in conclusion|en résumé|in summary|pour conclure|to conclude)\b", l):
            continue
        # Un paragraphe devient des phrases, une par ligne
        for phrase in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ0-9🟩🟥📈📉🎯🛑⏱📊🧭⚡])", l):
            phrase = phrase.strip()
            if not phrase or re.match(r"(?i)^(en conclusion|in conclusion|en résumé|in summary)\b", phrase):
                continue
            if len(phrase) > IA_LIGNE_MAX_CAR:
                coupe = phrase[:IA_LIGNE_MAX_CAR].rsplit(" ", 1)[0].rstrip(",;: ")
                phrase = coupe + "…"
            lignes.append(phrase)
    return "\n".join(lignes[:IA_LIGNES_MAX])


def avis_ia(etat, m, r, cle, anglais=False):
    r["macro_data"] = macro_confluence(etat, m, r)
    consigne = (
        "Give a concise, decision-ready desk brief in English: current move (rising/falling/ranging/rebound/pullback), H4/H1 bias, M15 structure and intended direction, M5 entry trigger, volume context on M5/M15/H1/H4 including source provenance and relative spike/weakness when available (never treat GOLD proxy volume as actual XAUUSD spot volume), exact planned entry/SL/TP only from supplied live plan, distance from current price to entry, indicative minutes based on observed 5m candle ranges, and what to do now. If the target is far, say plainly whether it is worth waiting and give the indicative check-back window; never tell the user to wait for hours when the supplied distance/range data show otherwise. Label the time estimate as mechanical and uncertain, never a promise. If 'position_ouverte' is supplied, comment on that open trade (direction, entry, SL, TP, what to do now) instead of looking for an entry. With no open position and no fresh entry plan, say NO VALID ENTRY PRICE and do not invent one. Mention the next blocking candle close only as the next review, not an entry time. No broker, macro filler, generic warnings, or indicator dump. Never override ALIGN's internal verdict. FORMAT: at most 6 short lines, one fact per line, each line starts with an emoji then 'Label: value' (e.g. '📈 Move: falling'), max 12 words per line, no paragraph, no conclusion sentence."
        if anglais else
        "Fais un briefing de trading court et directement exploitable : mouvement actuel (hausse, baisse, range, rebond ou retracement), biais H4/H1, structure M15 et direction visée, déclencheur d'entrée M5, lecture des volumes M5/M15/H1/H4 avec provenance et comparaison à la moyenne lorsqu'elle est disponible (ne jamais présenter le volume proxy GOLD comme le volume réel du spot XAUUSD), prix d'entrée/SL/TP exacts uniquement s'ils viennent d'un plan actif et frais, distance entre prix actuel et entrée, estimation indicative en minutes fondée sur les amplitudes réellement observées des bougies 5 min, puis quoi faire maintenant. Si l'entrée est loin, dis clairement si cela vaut la peine d'attendre et dans combien de temps revenir vérifier ; ne demande pas d'attendre des heures si la distance et le rythme observé indiquent le contraire. Présente le délai comme une projection mécanique incertaine, jamais comme une promesse. Si « position_ouverte » est fournie, commente cette position (sens, entrée, SL, TP, que faire maintenant) au lieu de chercher une entrée. Sans position ouverte ni plan d'entrée frais, écris AUCUN PRIX D'ENTRÉE VALIDE et n'invente rien. La prochaine clôture de l'unité bloquante est une réévaluation, pas une heure d'entrée. Aucun broker, remplissage macro, avertissement générique ou catalogue d'indicateurs. Ne contredis jamais le verdict interne. FORMAT : 6 lignes courtes au maximum, une seule info par ligne, chaque ligne commence par un emoji puis « Intitulé : valeur » (ex. « 📈 Mouvement : baisse »), 12 mots maximum par ligne, aucun paragraphe, aucune phrase de conclusion."
    )
    langue_cache = "en" if anglais else "fr"
    donnees = donnees_ia(m, r, cle)
    empreinte = dict(donnees)
    reevaluation = dict(empreinte.get("prochaine_reevaluation") or {})
    reevaluation.pop("secondes_restantes", None)
    empreinte["prochaine_reevaluation"] = reevaluation
    signature = hashlib.sha256(json.dumps(empreinte, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    cle_c = f"analyse_{m}_{langue_cache}_{signature}"
    t = ia(etat, consigne, donnees, cle_cache=cle_c, premium=True, recherche=True)
    t = compacter_ia(t)
    if t:
        titre = "🧠 ALIGN AI opinion" if anglais else "🧠 L'avis de l'IA ALIGN"
        fournisseur = etat.get("ia_dernier_fournisseur")
        modele = etat.get("ia_dernier_modele")
        # Le fournisseur n'est affiché que si un appel externe réel a abouti.
        # Le nom du fournisseur IA reste dans les journaux : rien de technique dans Telegram.
        if etat.get("ia_dernier_statut") == "CONNECTED" and fournisseur:
            print(f"AI_OPINION_PROVIDER={fournisseur}/{modele or ''}", flush=True)
        return f"{titre}\n{t}{ligne_sources(etat, cle_c)}"
    # Toutes les IA en panne : l'analyse interne du bot répond (jamais de silence)
    titre, raison = verdict(r, cle)
    if anglais:
        return "🧠 ALIGN internal analysis\n" + "\n".join(strategie_mtf(r)[-2:]) + f"\n{titre}"
    return "🧠 L'avis ALIGN (analyse interne)\n" + "\n".join(strategie_mtf(r)[-2:]) + f"\n{titre}"

def url_tradingview(m, timeframe):
    """Ouvre le bon instrument et la bonne unité ; ne pilote pas le graphique déjà ouvert."""
    symbole = {"BTC": "KRAKEN:XBTUSD", "GOLD": "FOREXCOM:XAUUSD", "NASDAQ": "FX:NAS100"}.get(m, "FOREXCOM:XAUUSD")
    return "https://www.tradingview.com/chart/?symbol=" + urllib.parse.quote(symbole, safe="") + "&interval=" + str(timeframe)

def bouton_auto(m):
    return json.dumps({"inline_keyboard": [[{"text": "🎯 Suivre la prochaine position", "callback_data": f"auto:{m}"}]]})

def menu_suivi(etat, cid):
    """Demande quels marchés l'utilisateur veut suivre avant l'inscription."""
    anglais = str(cid) in LANG_EN
    texte = ("🎯 CHOOSE THE MARKETS TO FOLLOW\nSelect BTC, GOLD or both. You'll be alerted when an entry is confirmed."
             if anglais else
             "🎯 CHOISIS LES MARCHÉS À SUIVRE\nSélectionne BTC, GOLD ou les deux. Je t'alerterai lorsqu'un point d'entrée sera confirmé.")
    labels = ["🟠 BTC", "🥇 GOLD", "💠 NASDAQ", "🟠 BTC + 🥇 GOLD"]
    choix = ["BTC", "GOLD", "NASDAQ", "BOTH"]
    lignes = [[{"text": label, "callback_data": f"followmarket:{market}"}]
              for label, market in zip(labels, choix)]
    _envoi_sur(cid, text=texte, reply_markup=json.dumps({"inline_keyboard": lignes}))

def bouton_rappel(m):
    """Rappelle la bonne analyse de marché, même si un autre marché a envoyé des messages depuis."""
    return json.dumps({"inline_keyboard": [
        [{"text": f"📌 Revoir l'analyse {m}", "callback_data": f"previous:{m}"}],
        [{"text": "🎯 Suivre la prochaine position", "callback_data": f"auto:{m}"}]
    ]})

def markup_analyse(etat, m, r, cid=None):
    """Carte compacte : les détails et toutes les actions restent visibles sans masquer les fonctions."""
    cle = etat.get(m, {})
    tr = cle.get("trade") or {}
    pos = (tr.get("qui") or {}).get(str(cid)) if cid is not None else None
    lignes = []
    if tr and (cid is None or (isinstance(pos, dict) and not pos.get("fini"))):
        lignes.append([
            {"text": "📍 Ma position • SL / TP", "callback_data": f"position:{m}"},
            {"text": "🚪 Je suis sorti", "callback_data": f"out:{m}"},
        ])
    elif tr:
        lignes.append([{"text": "📍 Suivre cette position", "callback_data": f"in:{m}"}])
    lignes.extend([
        [
            {"text": "❓ Pourquoi cette décision ?", "callback_data": f"why:{m}"},
            {"text": "🧠 En savoir plus", "callback_data": f"details:{m}"},
        ],
        [
            {"text": "🎯 Niveaux / prix", "callback_data": f"levels:{m}"},
            {"text": "⏱ Toutes les unités", "callback_data": f"timeframes:{m}"},
        ],
    ])
    actions = [
        {"text": "🗂 Historique des messages", "callback_data": f"history:{m}"},
    ]
    if not tr:
        actions.append({"text": "🔔 Suivre la prochaine position", "callback_data": f"auto:{m}"})
    lignes.append(actions)
    return json.dumps({"inline_keyboard": lignes})


def markup_position(m):
    return json.dumps({"inline_keyboard": [
        [{"text": "📍 Ma position • SL / TP", "callback_data": f"position:{m}"},
         {"text": "⏱ Toutes les unités", "callback_data": f"timeframes:{m}"}],
        [{"text": "🚪 Je suis sorti", "callback_data": f"out:{m}"}],
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
    pos = tr.get("qui", {}).get(str(cid))
    if not isinstance(pos, dict) or pos.get("fini"):
        return (f"📍 SIGNAL ALIGN EN COURS — {m}\n"
                "Tu n'es pas encore enregistré sur cette position.\n"
                "Utilise « Suivre cette position » si tu l'as prise.\n"
                "Aucun résultat personnel ne sera compté avant ton inscription.")
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


UT_VISION = (("1m", 0), ("3m", 1), ("5m", 2), ("15m", 4), ("1h", 7), ("4h", 9), ("D", 10))

def texte_vision(m, r, cle, anglais=False):
    """Pas encore de plan confirmé : le bot donne quand même SA VISION (sens probable, UT alignées, zone, ce qu'il attend),
    à partir des vraies données du dernier cycle. Jamais « aucune vision » quand les unités de temps sont calculées."""
    r = r or {}
    dirs = r.get("dirs") or []
    if len(dirs) < 11:
        return ("📊 ALIGN VISION\n⏳ Data still loading, try again in a minute." if anglais
                else "📊 VISION ALIGN\n⏳ Données en cours de chargement, réessaie dans une minute.")
    h = hb_etat_surveille(r)
    sens = {1: "LONG ⬆️", -1: "SHORT ⬇️"}.get(h["d"] or r.get("sens") or 0, "neutre ➖" if not anglais else "neutral ➖")
    ut = " ".join(f"{n}{'🟩' if dirs[i] == 1 else '🟥' if dirs[i] == -1 else '⬜'}" for n, i in UT_VISION)
    lignes = [f"📊 {'ALIGN VISION' if anglais else 'VISION ALIGN'} — {ICONE.get(m, '')} {m}", "━━━━━━━━━━━━━━━",
              (f"🧭 Likely direction: {sens} ({h['pct']} %)" if anglais else f"🧭 Sens probable : {sens} ({h['pct']} %)"),
              (f"📊 Timeframes aligned: {h['n']}/11" if anglais else f"📊 UT alignées : {h['n']}/11") + f" (seuil {MIN_ALIGN})",
              f"⏱ {ut}"]
    if h["strat"]:
        lignes.append(f"🎯 Profil : {h['strat']}")
    zp = h["zp"]
    if zp and h["prix"]:
        bas, haut = sorted((zp["za"], zp["zb"]))
        dedans = bas <= h["prix"] <= haut
        dist = 0 if dedans else min(abs(h["prix"] - bas), abs(h["prix"] - haut))
        lignes.append((f"📍 Entry zone: {px(bas)} → {px(haut)} " if anglais else f"📍 Zone d'entrée : {px(bas)} → {px(haut)} ")
                      + (("(price in the zone)" if anglais else "(prix dans la zone)") if dedans
                         else (f"(price {px(dist)} away)" if anglais else f"(prix à {px(dist)})")))
    try:
        lignes.append("⏳ " + raison_attente(r, cle))
    except Exception:
        pass
    lignes.append("🔔 No confirmed entry yet: I'll alert you at the confirmation close" if anglais
                  else "🔔 Pas encore d'entrée confirmée : je te préviens à la clôture de confirmation")
    return "\n".join(lignes)

def texte_timeframes(m, r):
    """Lecture pédagogique de toutes les unités réellement calculées par ALIGN."""
    noms = ["1 min", "3 min", "5 min", "10 min", "15 min", "30 min", "45 min",
            "1 heure", "2 heures", "4 heures", "Daily"]
    directions = ["🟩 HAUSSIER ⬆️" if d == 1 else "🟥 BAISSIER ⬇️" if d == -1 else "⬜ NEUTRE ➖"
                  for d in r["dirs"]]
    prof = profil_strategie(r) if len(r.get("dirs") or []) >= 11 else {}
    lignes = [f"⏱ TOUTES LES UNITÉS — {ICONE.get(m, '')} {m}"]
    if prof.get("mode"):
        lignes.append(f"🏷 Profil : {prof['mode']}")
    lignes.append("")
    for nom, direction, valeur in zip(noms, directions, r["rsis"]):
        lignes.append(f"{nom} : {direction} — RSI {valeur:.0f}")
    lignes += [
        "",
        "🏔 4 h : tendance principale",
        "🔁 1 h : confirme ou contredit la 4 h",
        "👀 15 min : préparation et cassure",
        "🎯 5 min : timing de l'entrée (clôture obligatoire)",
        "⚖️ SCALP : 1h + 15m + 5m + 1m — DAY : 4h + 1h + 15m + 5m — SWING : D/W + 4h + 1h",
        "⚠️ Une unité seule n'autorise jamais une entrée.",
    ]
    return "\n".join(lignes)


def texte_pourquoi(m, r, cle):
    """Explication courte de la décision, sans transformer le biais en signal d'entrée."""
    titre, raison = verdict(r, cle)
    maj, n_ok = alignement(r)
    direction = "LONG ⬆️" if maj == 1 else "SHORT ⬇️" if maj == -1 else direction_attente(r)
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

def news_courte(news):
    """Une seule ligne d'actualité dans la carte : la prochaine annonce, ou rien d'important d'ici 4 h."""
    lignes = [re.sub(r"^[^\wÀ-ÿ]+", "", x).strip() for x in str(news).split("\n") if x.strip()]
    evts = [x for x in lignes if re.search(r"\d{1,2}:\d{2}", x) and "Prochaines news" not in x]
    calme = any("Rien d'ici" in x for x in lignes)
    if evts:
        return (f"📰 Pas de news d'ici 4 h — prochaine : {court(evts[0], 70)}" if calme
                else f"📰 News : {court(evts[0], 80)}")
    return f"📰 {court(lignes[0] if lignes else news, 80)}"


def direction_attente(r):
    """Pas de direction validée : on dit quand même ce que fait la 4 h (même lecture que le chrono)."""
    dirs = r.get("dirs") or []
    d4 = dirs[9] if len(dirs) > 9 else 0
    if d4 == 1:
        return "AUCUNE DIRECTION CONFIRMÉE (4 h LONG, 1 h pas encore d'accord)"
    if d4 == -1:
        return "AUCUNE DIRECTION CONFIRMÉE (4 h SHORT, 1 h pas encore d'accord)"
    return "AUCUNE DIRECTION CONFIRMÉE (4 h neutre)"


def alerte_retournement(m, r, tr):
    """Même voyant que l'indicateur (↩ 3/5) : les petites unités 1 / 3 / 5 / 10 / 15 min tournent contre la position.
    Une seule alerte par position ; elle se réarme si les unités repartent dans le bon sens."""
    dirs = r.get("dirs") or []
    if len(dirs) < 8 or not tr:
        return None
    d = tr["d"]
    n = sum(1 for k in range(5) if dirs[k] == -d)
    if n < 3:
        if n <= 1:
            tr.pop("ret_dit", None)
        return None
    if tr.get("ret_dit"):
        return None
    tr["ret_dit"] = True
    inverse = "LONG ⬆️" if d == -1 else "SHORT ⬇️"
    return (f"↩ RETOURNEMENT EN PRÉPARATION — {ICONE.get(m, '')} {m}\n"
            f"⚠️ {n}/5 petites unités ont tourné contre le {'LONG' if d == 1 else 'SHORT'}\n"
            + "\n".join(voyants_unites(r)) + "\n"
            f"🔒 Sécurise : stop à BE ≈ {px(tr['e'])} si tu es en gain\n"
            f"✅ Retournement confirmé si le 15 min ET la 1 h clôturent vers le {inverse}\n"
            "🙅 Aucune entrée en sens inverse avant cette confirmation")


def retournement_marche(m, r, cle):
    """v71 = Pine « RETOURNEMENT PAR MARCHÉ » (mesuré sur 60 jours de bougies 5 min) :
    GOLD : 5m + 15m retournés contre le 1h • NASDAQ : idem + gros volume 15 min • BTC : 5m + 15m + 1h retournés contre le 4h.
    Cibles : haut/bas des 6 dernières bougies 1h puis 4h ; SL : dernier creux/sommet 5 min ; BE dès que le gain = le risque.
    Une alerte par nouveau sens (comme alert() du Pine), jamais deux fois de suite."""
    dirs = r.get("dirs") or []
    b5, b15 = (r.get("b5") or [])[:-1], (r.get("b15") or [])[:-1]
    b1, b4 = r.get("b1h") or [], r.get("b4h") or []
    if len(dirs) < 10 or len(b5) < 6 or len(b15) < 41 or len(b1) < 6 or len(b4) < 6:
        return None
    d5, d15, d60, d240 = dirs[2], dirs[4], dirs[7], dirs[9]
    vols = [x.get("v") or 0 for x in b15]
    vma = sum(vols[-41:-1]) / 40
    vol_fort = vma > 0 and vols[-1] > 1.3 * vma
    p = r["m1"][-1]["c"] if r.get("m1") else b15[-1]["c"]
    h1, l1 = max(x["h"] for x in b1[-6:]), min(x["l"] for x in b1[-6:])
    h4, l4 = max(x["h"] for x in b4[-6:]), min(x["l"] for x in b4[-6:])
    def ok(s):
        casc = d5 == s and d15 == s
        if m == "BTC":
            return casc and d60 == s and d240 == -s
        if m == "NASDAQ":
            return casc and d60 == -s and vol_fort
        return casc and d60 == -s
    sens = 1 if ok(1) and p < h1 else -1 if ok(-1) and p > l1 else 0
    avant = cle.get("rv_sens", 0)
    cle["rv_sens"] = sens
    if sens == 0 or sens == avant or r.get("t", 0) - cle.get("rv_t", {}).get(str(sens), 0) < 3600:
        return None
    cle.setdefault("rv_t", {})[str(sens)] = r.get("t", 0)
    sl = min(x["l"] for x in b5[-6:]) if sens == 1 else max(x["h"] for x in b5[-6:])
    be = p + sens * abs(p - sl)
    haut = "haut" if sens == 1 else "bas"
    camp, autre = ("acheteurs", "vendeurs") if sens == 1 else ("vendeurs", "acheteurs")
    if m == "BTC":
        vu = f"le 5 min, le 15 min et même le 1h ont tourné {'à la hausse' if sens == 1 else 'à la baisse'}, alors que le 4h va encore dans l'autre sens"
        pq = "Sur le BTC je n'entre jamais sur le 5 min seul : c'est souvent un piège. Là, le 1h a suivi, donc c'est sérieux"
    else:
        vu = f"le 5 min et le 15 min ont tourné {'à la hausse' if sens == 1 else 'à la baisse'}, alors que le 1h va encore dans l'autre sens"
        pq = ("Et la bougie 15 min a un gros volume : les " + camp + " sont vraiment là") if m == "NASDAQ" else \
             f"Sur le Gold, quand les petites unités tournent comme ça, les {autre} s'essoufflent"
    st = {"GOLD": (47, 24), "NASDAQ": (70, 30), "BTC": (62, 38)}.get(m, (0, 0))
    return (f"↩️ RETOURNEMENT {'LONG ⬆️' if sens == 1 else 'SHORT ⬇️'} — {ICONE.get(m, '')} {m}\n"
            f"👀 Regarde ton graphique : {vu}.\n"
            f"💡 {pq}. Le prix peut aller chercher le {haut} de la 1h, voire de la 4h.\n"
            f"📊 Sur mes 60 derniers jours, ce signal a atteint le {haut} 1h {st[0]} % du temps, le {haut} 4h {st[1]} %.\n"
            f"🎯 Cible 1 : {px(h1 if sens == 1 else l1)} ({haut} 1h)\n"
            f"🚀 Cible 2 : {px(h4 if sens == 1 else l4)} ({haut} 4h)\n"
            f"🛑 SL : {px(sl)}, juste {'sous le dernier creux' if sens == 1 else 'au-dessus du dernier sommet'} 5 min. S'il casse, je me suis trompé et on sort.\n"
            f"🛡 Dès que le prix touche {px(be)}, mets-toi à BE : il ne doit plus revenir à ton entrée. Là, on encaisse sans risque 💰\n"
            "📺 Tu retrouves la même explication sur le graphique (infobulle ↩️)")


def court(texte, n=120):
    texte = re.sub(r"\s+", " ", str(texte or "")).strip()
    return texte if len(texte) <= n else texte[:n].rsplit(" ", 1)[0].rstrip(",;: ") + "…"


def voyants_unites(r):
    """Voyants des unités : ⬆️ hausse, ⬇️ baisse, ➖ neutre (plus lisible que des carrés sur téléphone)."""
    dirs = r.get("dirs") or []
    ic = lambda d: "⬆️" if d == 1 else "⬇️" if d == -1 else "➖"
    def u(i, nom):
        return f"{nom} {ic(dirs[i])}" if i < len(dirs) else ""
    petites = "  ".join(x for x in (u(0, "1m"), u(1, "3m"), u(2, "5m"), u(4, "15m")) if x)
    grandes = "  ".join(x for x in (u(7, "1h"), u(9, "4h"), u(10, "D")) if x)
    nv = r.get("nVoy") or 0
    retour = [f"↩ {nv}/5 petites unités contre le plan" + (" : le retournement se prépare" if nv >= 3 else "")] if nv else []
    return ([f"⚡ Petites unités : {petites}"] if petites else []) + retour + ([f"🏔 Grandes unités : {grandes}"] if grandes else [])


def objectifs_marche(r, d):
    """Où le mouvement peut aller : cible probable (prochain niveau 1h/4h/D), zone d'essoufflement
    (niveau majeur suivant) et trajet indicatif selon l'amplitude réelle des bougies 5 min."""
    if d not in (1, -1) or not r.get("m1"):
        return []
    p = r["m1"][-1]["c"]; a = r.get("atr") or 0
    cand = [(v, f"niveau {n}") for v, n in (r.get("niveaux") or []) if n in ("1h", "4h", "D", "1D", "W")]
    cand += [(v, n) for v, n in (r.get("niv_cles") or [])]
    devant = sorted({(round(v, 2), n) for v, n in cand if v is not None and d * (v - p) >= 0.5 * a}, key=lambda z: d * (z[0] - p))
    if not devant:
        return []
    cible = devant[0]
    suite = next((z for z in devant[1:] if d * (z[0] - cible[0]) >= 0.5 * a), None)
    l = [f"🎯 Cible probable : ≈ {px(cible[0])} ({cible[1]})"]
    if suite:
        l.append(f"🪫 Essoufflement possible : ≈ {px(suite[0])} ({suite[1]})")
    a5 = r.get("atr5") or 0
    if a5 > 0:
        minutes = max(5, int(round(abs(cible[0] - p) / a5 * 5 * 1.5 / 5.0)) * 5)
        duree = f"≈ {minutes} min" if minutes < 120 else f"≈ {minutes // 60} h" if minutes <= 480 else "plusieurs heures à jours"
        l.append(f"⏱ Trajet estimé : {duree} (indicatif, pas une promesse)")
    return l


def zone_retournement_visee(r, cle):
    """Où le bot pense que le prix va se retourner : zone d'entrée du plan (ordre surveillé, sinon zone de l'indicateur), sens attendu, distance au prix.
    Reprend les chiffres de l'ancienne ligne « Zone surveillée ». Jamais inventée : « pas encore définie » si le plan n'est pas fixé."""
    prix = r["m1"][-1]["c"]
    o = (cle or {}).get("ordre")
    zp = r.get("zone_pine") if r.get("dirPlan") else None
    if o:
        za, zb = min(o.get("za", o["e"]), o.get("zb", o["e"])), max(o.get("za", o["e"]), o.get("zb", o["e"]))
        d = o.get("d") or r.get("dirPlan") or r.get("confirme") or 0
    elif zp:
        za, zb, d = min(zp["za"], zp["zb"]), max(zp["za"], zp["zb"]), r.get("dirPlan") or 0
    else:
        return ["🔁 Zone de retournement : pas encore définie (le plan n'est pas fixé)"]
    sens = f" — {SENS[d]} attendu" if d in (1, -1) else ""
    l = [f"🔁 Zone de retournement visée : ≈ {px(za)} → {px(zb)}{sens}"]
    if za <= prix <= zb:
        l.append("📍 Le prix est dans la zone : j'attends le rejet et la clôture")
    else:
        dist = min(abs(prix - za), abs(prix - zb))
        l.append(f"📏 Prix à {px(dist)} de la zone ({'elle est au-dessus' if prix < za else 'elle est en dessous'})")
    return l

def texte_apercu(m, r, cle, vip=True):
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
        direction = "LONG ⬆️" if maj == 1 else "SHORT ⬇️" if maj == -1 else direction_attente(r)

    prof = profil_strategie(r) if r.get("dirs") and len(r.get("dirs")) >= 11 else {}
    # Même sens que la décision : pas de cible tant que la 4 h + 1 h ne donnent pas de direction.
    sens = (tr or {}).get("d") or maj or 0
    type_ = prof.get("mode") or ""
    lignes = [
        f"{ICONE.get(m, '📊')} {m} — {px(prix)}",
        f"🚦 {decision}",
        f"🧭 Biais à surveiller : {direction}" + (f" ({type_})" if type_ and not direction.startswith(('AUCUNE', 'Non confirmée', 'À confirmer')) else ""),
        "⚠️ Le biais n'est pas une autorisation d'entrée." if not tr else "📍 Position ouverte : suis les alertes du coach.",
        "",
    ] + voyants_unites(r) + [""]
    # Position ouverte : les niveaux du trade font foi (pas de cible différente du TP).
    obj = ([f"🟨 Entrée : {px(tr['e'])} (ligne jaune)",
            (f"🔒 SL protégé : {px(tr['sl'])} (plus de perte possible)" if tr.get("d") and tr["d"] * (tr["e"] - tr["sl"]) <= 0
             else f"🛑 SL : {px(tr['sl'])} (ligne rouge)"),
            f"🎯 TP1 : {px(tr['tp1'])} (ligne bleue)"]
           + ([f"🏁 TP2 : {px(tr['tp2'])}"] if tr.get("tp2") else [])) if tr else objectifs_marche(r, sens)
    if obj:
        lignes += obj + [""]
    if not tr:
        lignes.append(f"❓ Pourquoi : {court(raison or 'Aucune entrée autorisée pour le moment.', 150)}")
    lignes += [
        "➡️ À faire : " + ("gérer la position ouverte et suivre les alertes de sortie." if tr else
                         "Attendre un nouveau message explicite « ENTRÉE AUTORISÉE »."),
    ]
    if not tr:
        lignes += zone_retournement_visee(r, cle)
    jour_ = news_du_jour(DERNIER_ETAT) if (DERNIER_ETAT and vip) else []      # news : VIP uniquement (règle gratuit/VIP)
    if jour_:
        lignes += [""] + jour_
    elif r.get("news") and vip:
        lignes += [news_courte(r["news"])]
    lignes += ["", "👇 Détails : boutons ci-dessous", "ℹ️ Aucun ordre n'est envoyé automatiquement à ton broker."]
    return "\n".join(lignes)

DERNIERS = {}               # dernière analyse de chaque marché (pour le chrono)
DERNIER_ETAT = {}           # état courant (calendrier des news) lu par les cartes d'analyse
CHRONO_MAX = 4 * 3600        # délai max d'attente d'une position réservée
SL_RISQUE_MIN_ATR = 1.4      # stop jamais plus serré que 1,4 ATR 15 min (évite les SL pris par une simple mèche)
SL_RISQUE_MIN_PCT = 0.0012   # ni plus serré que 0,12 % du prix
CHRONO_REFRESH_SEC = 30      # 1 édition / 30 s par chrono : au-delà, Telegram bloque le chat pendant des heures (429)
JAUGE_REFRESH_SEC = 60       # la jauge de prix n'est rééditée qu'une fois par minute au maximum
CHRONO_LOCK = threading.RLock()  # un seul éditeur Telegram par chronomètre, même pendant l'analyse réseau

def prochaine_cloture(ts, interval_sec=300):
    """Retourne la prochaine clôture strictement future (horodatage UTC)."""
    if interval_sec < 1:
        raise ValueError("interval_sec doit être positif")
    return (int(ts) // interval_sec + 1) * interval_sec


def duree_humaine(sec):
    """9 min 30 s · 1 h 05 : jamais confondu avec une heure de l'horloge (ancien « depuis 09:30 »)."""
    sec = max(0, int(sec))
    h, reste = divmod(sec, 3600)
    mi, se = divmod(reste, 60)
    return f"{h} h {mi:02d}" if h else f"{mi} min {se:02d} s" if mi else f"{se} s"

def mmss(sec):
    """Affichage compact Telegram : MM:SS, sans texte ni chiffres parasites."""
    total = max(0, int(sec))
    minutes, secondes = divmod(total, 60)
    return f"{minutes:02d}:{secondes:02d}"


def duree_cloture(sec):
    """MM:SS jusqu'à 1 h ; au-delà « 2 h 42 » (lisible) au lieu de « 162:25 »."""
    total = max(0, int(sec))
    if total > 3600:
        heures, reste = divmod(total, 3600)
        return f"{heures} h {reste // 60:02d}"
    return mmss(total)


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


CLOTURE_EXPLICATION = {
    "4h": "À la clôture 4 h : je regarde si la 4 h donne enfin un sens LONG ou SHORT.",
    "1h": "À la clôture 1 h : je vérifie que la 1 h confirme la 4 h.",
    "15m": "À la clôture 15 min : je cherche un repli propre pour préparer l'entrée.",
    "5m": "À la clôture 5 min : si la bougie clôture dans le bon sens, l'entrée est validée.",
}


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
            f"🎯 Suivi en cours depuis {duree_humaine(now - t0)}",
            f"🟢 POSITION OUVERTE — {SENS[tr['d']]}",
            f"🟨 Entrée {px(tr['e'])} • 🛑 SL {px(tr['sl'])} • 🎯 TP1 {px(tr['tp1'])}",
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
        f"🎯 Suivi en cours depuis {duree_humaine(now - t0)}",
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
        f"⏱ Temps restant : {duree_cloture(restant)}",
        f"🕒 Heure prévue : {datetime.datetime.fromtimestamp(cible, PARIS).strftime('%H:%M')} (heure de Paris)",
        f"👉 {CLOTURE_EXPLICATION.get(tf, '')}",
        f"🕯 Clôture 5 min : {mmss(prochaine_cloture_bougie(r, '5m', now) - now)}",
        f"🕯 Clôture 15 min : {mmss(prochaine_cloture_bougie(r, '15m', now) - now)}",
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

def en_position(etat, cid):
    return [m for m in MARCHES if isinstance(((etat.get(m) or {}).get("trade") or {}).get("qui", {}).get(str(cid)), dict)
            and not etat[m]["trade"]["qui"][str(cid)].get("fini")]

SON_PIECE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "son_piece.mp3")

def envoyer_son_piece(cid):
    """Envoie le son « pièce » (créé pour ALIGN, libre de droits). Le bot ne peut pas imposer une sonnerie :
    la personne l'enregistre elle-même comme son de notification de ce chat."""
    anglais = str(cid) in LANG_EN
    legende = ("🔔 ALIGN coin sound\n👆 Long-press this sound → Save for notifications\n⚙️ Then pick it in this chat's notification settings"
               if anglais else
               "🔔 Son pièce ALIGN\n👆 Appuie longuement sur ce son → Enregistrer pour les notifications\n⚙️ Puis choisis-le dans les réglages de ce chat")
    with open(SON_PIECE, "rb") as f:
        audio = f.read()
    borne = "----align" + hashlib.md5(audio).hexdigest()[:16]
    champs = {"chat_id": str(cid), "caption": legende, "title": "ALIGN pièce", "performer": "ALIGN"}
    corps = b""
    for k, v in champs.items():
        corps += f'--{borne}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    corps += (f'--{borne}\r\nContent-Disposition: form-data; name="audio"; filename="align_piece.mp3"\r\n'
              f'Content-Type: audio/mpeg\r\n\r\n').encode() + audio + f"\r\n--{borne}--\r\n".encode()
    _telegram_verifie_cooldown(cid)
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendAudio", data=corps,
                                 headers={"Content-Type": f"multipart/form-data; boundary={borne}"})
    with urllib.request.urlopen(req, timeout=30) as rep_:
        return json.loads(rep_.read().decode())

def menu_bot_gratuit(etat, cid):
    on = bot_on(etat, cid)
    dedans = en_position(etat, cid)
    utilise = str(cid) in etat.get("bienvenue", {})
    lignes = [f"🤖 MON BOT : {'▶️ ON' if on else '⏸ OFF'}", "━━━━━━━━━━━━", "🔔 Souhaites-tu encore des positions ?"]
    if dedans:
        lignes.append(f"🎯 En position : {', '.join(dedans)} (suivi jusqu'au TP / SL)")
    lignes += (["✅ Je te propose la prochaine position", "🙋 Tu choisis : tu la prends ou non"] if on else
               ["⏸ Aucune position proposée", "🔒 Tu sais juste qu'une position VIP sort"])
    lignes += ["━━━━━━━━━━━━", "🎁 Position du jour : " + ("déjà utilisée (nouvelle demain)" if utilise else "disponible"),
               "📡 Marchés : " + " + ".join(NOMS_MARCHES[m] for m in MARCHES if m in marches_choisis(etat, cid))]
    _envoi_sur(cid, text="\n".join(lignes) + "\n\n" + texte_suivi(etat, cid), reply_markup=json.dumps({"inline_keyboard": [
        [{"text": "⏸ Non, plus de positions", "callback_data": "botoff:x"} if on else
         {"text": "✅ Oui, je veux des positions", "callback_data": "boton:x"}],
        [{"text": "📡 Choisir mes marchés", "callback_data": "marketsmenu:x"}],
        [{"text": "🔔 Son pièce", "callback_data": "son:piece"}]]
        + ([[{"text": "💎 Revenir en vue VIP (propriétaire)", "callback_data": "vuegratuit:off"}]] if str(cid) in {str(x) for x in proprio(etat)} else [])}))

def menu_bot(etat, cid):
    if vue_gratuite(etat, cid):
        return menu_bot_gratuit(etat, cid)
    on = bot_on(etat, cid)
    # Lecture sans écriture : ce menu peut être affiché pendant une analyse en cours.
    st = etat.get("stats_bot", {}).get(str(cid), {"arrets": 0, "auto": 0})
    _envoi_sur(cid, text=(f"🤖 MON BOT   {'▶️ ON' if on else '⏸ OFF'}\n━━━━━━━━━━━━\n"
                          + ("✅ Il entre tout seul dans chaque position\n👀 Vue 15 min • SL un peu sous / au-dessus de la mèche\n🎯 Le coach te suit jusqu'au TP\n"
                             if on else "⏸ Il n'entre plus pour toi\n🔔 Tu reçois quand même les positions\n")
                          + f"━━━━━━━━━━━━\n🤖 Positions prises par ton bot   {st['auto']}\n⏸ Arrêts manuels   {st['arrets']}"
                          + "\n\n" + texte_suivi(etat, cid)),
               reply_markup=json.dumps({"inline_keyboard": [[{"text": "⏸ Arrêter mon bot", "callback_data": "botoff:x"} if on
                                                            else {"text": "▶️ Relancer mon bot", "callback_data": "boton:x"}],
                                                           [{"text": "📡 Choisir mes marchés", "callback_data": "marketsmenu:x"}],
                                                           [{"text": "🔔 Son pièce", "callback_data": "son:piece"}]]
                                       + ([[{"text": "👁 Tester la version gratuite", "callback_data": "vuegratuit:on"}]] if str(cid) in {str(x) for x in proprio(etat)} else [])}))

def regler_bot(etat, cid, on):
    off = etat.setdefault("bot_off", [])
    if on and cid in off:
        off.remove(cid)
    elif not on and cid not in off:
        off.append(cid); stats_bot(etat, cid)["arrets"] += 1
    if vue_gratuite(etat, cid):
        dedans = en_position(etat, cid)
        txt = (("✅ C'est noté : je te propose la prochaine position" if str(cid) not in etat.get("bienvenue", {})
                else "✅ C'est noté\n🎁 Ta position du jour est déjà utilisée : la prochaine demain") if on else
               "⏸ C'est noté : plus de position proposée\n▶️ Réactive quand tu veux : 🤖 Mon bot")
        if dedans:
            txt += f"\n🎯 Ta position {', '.join(dedans)} reste suivie jusqu'au TP / SL"
        _envoi_sur(cid, reply_markup=CLAVIER_VISITEUR, text=txt)
        return
    _envoi_sur(cid, reply_markup=CLAVIER, text=("▶️ Ton bot est relancé\n🤖 Il entre tout seul dans la prochaine position" if on
                                                else "⏸ Ton bot est arrêté\n🔔 Tu reçois toujours les positions\n▶️ Relance-le avec 🤖 Mon bot"))

def entrer_inscrits(etat, m, tr, chats=()):
    """Le bot vient d'entrer : il fait entrer automatiquement tous les membres dont le bot est ON,
    plus ceux qui ont appuyé sur 🎯, au prix d'entrée du bot (coach + résultats comptés)."""
    auto = [c for c in chats if bot_on(etat, c) and marche_autorise(etat, c, m) and not vue_gratuite(etat, c) and c != etat.get("canal")]
    for cid in list(dict.fromkeys(etat.get("auto", {}).pop(m, []) + auto)):
        if isinstance(tr.setdefault("qui", {}).get(cid), dict):
            continue
        if vue_gratuite(etat, cid):
            deja = etat.get("bienvenue", {}).get(cid)
            if not bot_on(etat, cid) or not marche_autorise(etat, cid, m) or (deja and deja != m):
                continue      # gratuit : bot éteint, marché non choisi ou position du jour déjà prise
        tr["qui"][cid] = {"e": tr["e"], "sl": tr["sl"], "tp1": tr["tp1"], "d": tr["d"], "t": int(time.time())}
        if vue_gratuite(etat, cid):
            etat.setdefault("bienvenue", {}).setdefault(cid, m)
        stats_bot(etat, cid)["auto"] += 1
        _envoi_sur(cid, reply_markup=markup_position(m), text=humaniser(etat, cid,
            f"🤖 {ICONE.get(m, '')} {m} : POSITION SUIVIE AUTOMATIQUEMENT\n{SENS[tr['d']]}\n"
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


def ligne_raison_attente(raison, titre=""):
    """Une ligne : pourquoi on n'entre pas (première ligne du verdict qui dit ce qui manque), sans emoji ni formule."""
    lignes = [x.strip() for x in str(raison or "").split("\n") if x.strip()]
    pref = next((x for x in lignes if x.startswith(("⏳", "📍", "🔄", "📰", "⏰"))), lignes[0] if lignes else "")
    pref = re.sub(r"^[^\w(«\"']+", "", pref).strip()
    return pref or str(titre).title().strip() or "Pas de signal validé"

def declencheur_attente(r, cle, prix, d4h, d1h):
    """Une ligne : ce qui déclenchera l'entrée (clôture, niveau)."""
    o = (cle or {}).get("ordre")
    if o and o.get("d") in (1, -1):
        return f"Clôture 5 min {'au-dessus de' if o['d'] == 1 else 'sous'} {px(o['e'])}"
    zp, d = r.get("zone_pine"), r.get("dirPlan") or 0
    zp = trait_indicateur(r, d) or zp
    if zp and d in (1, -1) and zp.get("zmil"):
        return f"Clôture {HB_UNITE_VALIDATION.get(r.get('strat') or '', '15 min')} {'au-dessus de' if d == 1 else 'sous'} {px(zp['zmil'])}"
    attente = "4h" if not d4h else "1h" if d1h != d4h else "15m" if not r.get("confirme") else "5m"
    try:
        now_ = time.time(); fin_ = prochaine_cloture_bougie(r, attente, now_)
        return f"Clôture {attente.replace('m', ' min')} ({datetime.datetime.fromtimestamp(fin_, PARIS).strftime('%H:%M')})"
    except Exception:
        return f"Clôture {attente.replace('m', ' min')}"

def texte_cloture(m, tf, bougie, r, cle):
    """Alerte courte : marché/prix d'abord ; détails et historique restent dans les boutons."""
    cle = cle or {}
    duree = TF_SECONDES[tf]
    prix = (r.get("m1") or [bougie])[-1].get("c", bougie["c"])
    titre, raison_v = verdict(r, cle)
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
    ] + [
        f"🕯 {tf} clôturée {heure(bougie['t'] + duree)} · {bougie_sens} · O {px(bougie['o'])} → C {px(bougie['c'])}",
        f"H4 {sens(d4h)}  ·  H1 {sens(d1h)}  ·  ALIGN {n_ok}/2 (4h + 1h d'accord)" if n_ok == 2 else f"H4 {sens(d4h)}  ·  H1 {sens(d1h)}  ·  ALIGN {n_ok}/2 (4h + 1h)",
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
        tp2_ = f" · TP2 {niveau(ordre.get('tp2'))}" if tp2_affichable(ordre.get("d"), ordre.get("tp1"), ordre.get("tp2")) else ""
        lignes.append(f"🟡 Zone {px(bas)} → {px(haut)} · Entrée {niveau(ordre.get('e'))} · SL {niveau(ordre.get('sl'))} · TP1 {niveau(ordre.get('tp1'))}{tp2_}")
    else:
        attente = "4h" if not d4h else "1h" if d1h != d4h else "15m" if not r.get("confirme") else "5m"
        try:
            now_ = time.time(); fin_ = prochaine_cloture_bougie(r, attente, now_)
            chrono_ = f" dans {duree_cloture(fin_ - now_)} (à {datetime.datetime.fromtimestamp(fin_, PARIS).strftime('%H:%M')})"
        except Exception:
            chrono_ = ""
        lignes.append(f"⏳ Prochaine validation : clôture {attente}{chrono_}")
    if not tr and not statut.startswith("🟢"):
        return carte_coach(m, r, cle, "attente", raison=raison_2_mots(ligne_raison_attente(raison_v, titre)),
                           declencheur=declencheur_attente(r, cle, prix, d4h, d1h))      # carte unique : raison en 2 mots + déclencheur
    if not tr:
        lignes.append("🚫 Aucun ordre envoyé au broker.")
    return "\n".join(lignes)


def signature_cloture(texte):
    """Ce qui fait la DÉCISION d'une carte de clôture (sans le prix, la bougie ni le chrono) : sert à ne pas répéter la même carte."""
    garde = []
    for l in str(texte).splitlines()[1:]:
        if l.startswith(("🕯", "⏳ Prochaine", "━")) or not l.strip():
            continue
        garde.append(re.sub(r"[\d.,]+", "#", l.strip()))          # les niveaux qui bougent de quelques points ne changent pas la décision
    return "|".join(garde)

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
                texte_cl = texte_cloture(m, tf, bougie, r, cle)
                # Anti-bruit : même décision qu'à la dernière carte (statut, alignement, profil) et moins de 30 min → on ne renvoie pas
                sig = signature_cloture(texte_cl)
                if sig == suivi.get("sig_cl"):                       # même décision : jamais renvoyée (le RADAR montre l'état en continu)
                    derniers[tf] = int(bougie["t"])
                    continue
                resultat = _envoi_sur(cid, text=texte_cl,
                                     reply_markup=markup_analyse(etat, m, r, cid))
                if resultat is not None and not (isinstance(resultat, dict) and resultat.get("ok") is False):
                    suivi["sig_cl"], suivi["sig_t"] = sig, time.time()
                # Ne consommer la clôture que si Telegram a accepté l'envoi : sinon réessayer au tour suivant.
                if resultat is not None and not (isinstance(resultat, dict) and resultat.get("ok") is False):
                    derniers[tf] = int(bougie["t"])
                    suivi["hb_t"] = time.time()           # évite un battement de cœur juste après cette alerte
            continue
        tf = suivi.get("tf")
        bars = r.get(champs.get(tf, ""), []) or []
        if not bars:
            continue
        close = next((b for b in bars if int(b["t"]) > int(suivi.get("dernier_t", 0))), None)
        if not close:
            continue
        resultat = _envoi_sur(cid, text=texte_cloture(m, tf, close, r, cle),
                               reply_markup=markup_analyse(etat, m, r, cid))
        if resultat is None or (isinstance(resultat, dict) and resultat.get("ok") is False):
            continue
        suivi["dernier_t"] = int(close["t"])
        suivi["restants"] = int(suivi.get("restants", 1)) - 1
        if suivi["restants"] <= 0 or cle.get("trade"):
            etat["veille_cloture"][m].pop(cid, None)


def prochaine_ouverture_cme(ts):
    """Prochaine réouverture CME/CFD (Gold, Nasdaq), cherchée par pas de 5 min avec la même règle que cme_ouvert."""
    t = int(ts) // 300 * 300
    for _ in range(12 * 80):
        t += 300
        if cme_ouvert(t):
            return t
    return None


def etat_marche_hb(m, r, now):
    """(« ferme » | « perime » | « ouvert »), réouverture. Uniquement à partir des vraies horloges et des vraies bougies."""
    if m != "BTC" and not cme_ouvert(now):
        return "ferme", prochaine_ouverture_cme(now)
    derniere = (r.get("m1") or [{}])[-1].get("t")
    if not derniere or now - float(derniere) > 900:
        return "perime", None
    return "ouvert", None

HB_UNITE_VALIDATION = {"SWING": "1h", "DAY": "5 min", "SCALPING": "1 min"}        # unité de validation de l'indicateur (15 min sans stratégie)

def hb_etat_surveille(r):
    """Ce que l'indicateur surveille, uniquement à partir des vraies données : sens, UT alignées, zone, profil, trait de décision."""
    d = r.get("dirPlan") or 0
    strat = r.get("strat") or ""
    etat_s = strategie_alignement(r.get("dirs"), d, r.get("dirW") or 0)[1] if d else "AUCUNE"
    n = r.get("bull", 0) if d == 1 else r.get("bear", 0) if d == -1 else max(r.get("bull", 0), r.get("bear", 0))
    zp = r.get("zone_pine") if d else None
    a = float(r.get("atr") or 0) or 1.0
    prix = r.get("prix") or (r.get("m1") or [{}])[-1].get("c")
    sens = r.get("sens", 0)
    pct = r.get("pctH", 50)
    return dict(d=d, strat=strat, etat=etat_s, n=n, zp=zp, a=a, prix=prix, sens=sens, pct=pct if sens >= 0 else 100 - pct,
                sig=(d, n, strat, etat_s, sens, round(float(zp["zmil"]), 4) if zp else None, round(a, 4)))




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
             f"🕒 Analyse de référence : {heure(der['t'])}"] + voyants_unites(r) + utile + [statut_txt(1 if cle.get("trade") else 0, cle.get("trade") or cle.get("ordre")).strip(), "🔔 Je te préviens dès que ça change"]))
        # Un seul message (voyants inclus) ; l'avis IA complet reste derrière « 🧠 En savoir plus ».
        return
    armer_cloture(etat, cid, m, r, cle)
    # Toutes les analyses passent par le même garde-fou 429 que les autres messages.
    # Une analyse refusée par Telegram n'est pas marquée comme livrée et pourra être retentée.
    res = _envoi_sur(cid, text=texte_apercu(m, r, cle, vip=bool(autorise(etat, str(cid), str(cid)))),
                     reply_markup=markup_analyse(etat, m, r, cid))
    if not isinstance(res, dict) or res.get("ok") is not True:
        print(f"ANALYSE_NON_LIVREE market={m} chat={cid} reason=telegram_send_not_confirmed")
        return
    vu[str(cid)] = {"sig": sig, "t": time.time()}
    try:
        vu[str(cid)]["mid"] = res["result"]["message_id"]
    except (KeyError, TypeError):
        pass
    # L'avis IA reste envoyé séparément ; aucune information existante n'est supprimée.
    # Les voyants sont déjà dans la carte ; l'avis IA complet est derrière « 🧠 En savoir plus ».

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
        return "📈 Mes résultats\n━━━━━━━━━━━━\nAucun trade clôturé pour l'instant.\nLes résultats apparaîtront après la première clôture réellement enregistrée."
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
    """Vérifie les confirmations du marché au moment de l'activation du suivi personnel."""
    try:
        r = analyse_marche(etat, MARCHES[m])
    except Exception as ex:
        print("controle", ex); return news_txt(etat)
    fl = lambda x: "✅" if x == d else "⚠️"
    r5 = r["r5"][-1]
    return (f"{fl(r['dirs'][4])} 15 min   {fl(r['dirs'][7])} 1 h   {fl(r['dirs'][9])} 4 h\n"
            f"⚡ RSI 5 min   {r5:.0f}{' (surcharge, normal)' if (r5 >= 65 if d == -1 else r5 <= 35) else ''}\n"
            f"{r['news']}")

def alerte_latence_entree(tr, prix):
    """Latence Telegram/marché : compare le prix réel au moment du clic avec le plan du signal.
    Renvoie "" si l'entrée reste saine, un avertissement ⚠️, ou un refus ⛔ si le stop est trop proche."""
    try:
        d, e0, sl = int(tr["d"]), float(tr["e"]), float(tr["sl"])
        tp1 = float(tr.get("tp1", e0))
        prix = float(prix)
    except (KeyError, TypeError, ValueError):
        return ""
    risque0 = abs(e0 - sl)
    if risque0 <= 0:
        return ""
    reste = d * (prix - sl)                       # distance réelle jusqu'au stop
    if reste <= 0.25 * risque0:
        return ("⛔ Le prix est déjà collé au stop : je ne lance pas le suivi.\n"
                "⏳ N'entre pas maintenant, attends le prochain signal.")
    if reste < 0.6 * risque0:
        return ("⚠️ Latence : le prix s'est rapproché du stop depuis le signal.\n"
                f"🛑 Garde le SL du plan ({px(sl)}), ne le resserre pas ; réduis la taille si tu entres.")
    gain_dispo = d * (tp1 - prix)
    if gain_dispo < 0.5 * risque0:
        return ("⚠️ Latence : le prix a déjà fait une bonne partie du chemin.\n"
                "🎯 Le gain restant vers le TP1 est faible : entrée peu intéressante.")
    return ""


def repondre(etat, cid, oui, mk=None):
    """Active le suivi personnel d'une position en cours ou enregistre une sortie manuelle."""
    trades = [m for m in MARCHES if etat.get(m, {}).get("trade") and (mk is None or m == mk)]
    CLAVIER = CLAVIER_VISITEUR if cid in etat.get("prospects", []) else globals()["CLAVIER"]
    if oui:
        cands = [m for m in trades if not isinstance(etat[m]["trade"].get("qui", {}).get(cid), dict)]
        if not cands and trades:
            m = trades[0]
            _envoi_sur(cid, text="✅ Ton suivi personnel est déjà actif.\n🎯 Le coach surveille ton SL, BE et TP.", reply_markup=markup_position(m))
            return
        if not cands:
            _envoi_sur(cid, text=("🔴 Aucune position ouverte à suivre pour le moment.\n"
                                  "🔔 Choisis « Suivre la prochaine position » pour recevoir le prochain signal confirmé."), reply_markup=CLAVIER)
            return
        m = cands[0]; tr = etat[m]["trade"]
        e = prix_actuel(m) or tr["e"]
        alerte = alerte_latence_entree(tr, e)
        if alerte.startswith("⛔"):
            # Le prix est déjà collé au stop (ou l'a dépassé) : on n'ouvre pas de suivi perdant d'avance.
            _envoi_sur(cid, text=f"{ICONE.get(m, '')} {m}\n{alerte}", reply_markup=markup_position(m))
            return
        tr.setdefault("qui", {})[cid] = {"e": e, "sl": tr["sl"], "tp1": tr["tp1"], "d": tr["d"], "t": int(time.time())}
        live_suivi(etat, cid, m)
        _envoi_sur(cid, reply_markup=markup_position(m), text=(
            f"👊 SUIVI PERSONNEL ACTIVÉ — {ICONE.get(m, '')} {m}\n{SENS[tr['d']]}\n"
            f"📌 Entrée   {px(e)}\n"
            f"🛑 Stop   {px(tr['sl'])}\n"
            f"💰 TP1   {px(tr['tp1'])}\n"
            f"━━━━━━━━━━━━\n"
            f"🤖 Coach activé jusqu'au TP\n"
            + (f"{alerte}\n" if alerte else "") +
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

COMMANDES = {"/faire_analyse": "📊 Faire une analyse", "/analyse_btc": "🟠 Analyse BTC", "/analyse_gold": "🥇 Analyse Gold", "/mon_bot": "🤖 Mon bot",
             "/resultats": "📈 Mes résultats", "/gain": "📸 Partager mon gain", "/vip": "💎 Devenir VIP",
             "/english": "🌐 English", "/francais": "🌐 Français", "/rentre": "✅ Je suis rentré", "/sorti": "🚪 Je suis sorti",
             "/indicateur": "🧩 Indicateur TradingView", "/focus": "🎯 Où me concentrer ?"}

def installer_menu(etat):
    """Bouton « Menu » à gauche du champ + description du bot (une seule fois par version)."""
    if etat.get("menu") == 8:
        return
    fr = [("faire_analyse", "📊 Faire une analyse"), ("mon_bot", "🤖 Mon bot ON / OFF"),
          ("resultats", "📈 Mes résultats"), ("gain", "📸 Partager mon gain"), ("vip", "💎 Devenir VIP"),
          ("boutons", "⌨️ Faire revenir les boutons"), ("english", "🌐 English")]
    en = [("faire_analyse", "📊 Run an analysis"), ("mon_bot", "🤖 My bot ON / OFF"),
          ("resultats", "📈 My results"), ("gain", "📸 Share my profit"), ("vip", "💎 Become VIP"),
          ("boutons", "⌨️ Bring back the buttons"), ("francais", "🌐 Français")]
    try:
        telegram("setMyCommands", commands=json.dumps([{"command": c, "description": d} for c, d in fr]))
        telegram("setMyCommands", commands=json.dumps([{"command": c, "description": d} for c, d in en]), language_code="en")
        telegram("setChatMenuButton", menu_button=json.dumps({"type": "commands"}))
        try:
            # RÈGLE OBLIGATOIRE : le nom du bot ne se change JAMAIS depuis le code.
            # Telegram bloque setMyName pendant des heures : c'est ce qui a rendu le bot sourd le 11/11/2026.
            # Nom définitif, posé une fois : « ALIGN Gratuit 🎁 BTC & Gold ».
            pass
        except Exception as ex:
            print("nom", ex)
        telegram("setMyShortDescription", short_description="🎁 ALIGN Gratuit : 1 position BTC / Gold proposée chaque jour • 💎 Tout le reste dans ALIGN VIP")
        telegram("setMyDescription", description=("🎁 ALIGN Gratuit — BTC & Gold\n\n🎁 1 position proposée chaque jour, expliquée en bougies\n"
                                                  "🔒 Les autres : tu sais qu'elles arrivent, sans le sens\n\n"
                                                  "💎 ALIGN VIP 49,90 € / mois : toutes les positions, le sens, les niveaux et le coach (BE, TP)\n"
                                                  "🤖 Les abonnés au suivi sont enregistrés automatiquement à l'ouverture du signal.\n"
                                                  "📍 Suivi personnel : SL, BE, TP et sortie manuelle depuis Telegram.\n\n"
                                                  "ℹ️ Mes positions perso, pas un conseil. Le trading comporte un risque de perte."))
        etat["menu"] = 8
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
        if isinstance(pos, dict) and vue_gratuite(etat, c):
            g_ = pos["d"] * (sortie - pos["e"]) / pos["e"] * 100
            pay = bouton_payer(etat) or kb
            off = etat.setdefault("bot_off", [])
            if c not in off:
                off.append(c)      # position du jour terminée : le bot gratuit s'éteint tout seul
            _envoi_sur(c, reply_markup=CLAVIER_VISITEUR, text=(
                "⏸ Position du jour terminée : ton bot s'est éteint\n"
                "▶️ Pour la prochaine : 🤖 Mon bot → ✅ Oui, je veux des positions"))
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
        # Le poller indépendant a déjà répondu aux actions de lecture seule.
        if u.get("_align_fast_handled"):
            continue
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
            retenir_prenom(etat, qui, cb.get("from"))
            if live_callback(etat, chats, cb, choix, mk, qui):
                continue
            if choix == "analysechoice" and (mk in MARCHES or mk == "BOTH"):
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="📊 Analyse en cours")
                except Exception:
                    pass
                if not autorise(etat, qui, (cb.get("from") or {}).get("id")):
                    # Visiteur : jamais les niveaux VIP, seulement l'état du marché + bouton VIP
                    analyse_visiteur(etat, qui, None if mk == "BOTH" else mk)
                    continue
                for marche in (tuple(sorted(marches_choisis(etat, qui))) if mk == "BOTH" else (mk,)):
                    demandes.append((qui, marche))
                continue
            if choix == "vuegratuit" and qui in {str(x) for x in proprio(etat)}:
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"])
                except Exception:
                    pass
                etat["proprio_gratuit"] = mk == "on"
                _envoi_sur(qui, text=("👁 VUE GRATUITE ACTIVÉE\n🎁 Tu reçois maintenant exactement ce que reçoit un gratuit\n💎 Retour : 🤖 Mon bot → Revenir en vue VIP"
                                      if mk == "on" else "💎 VUE VIP RÉTABLIE\n📲 Tout le flux complet est dans la chaîne ALIGN VIP"))
                continue
            if choix == "botmenu":
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"])
                except Exception:
                    pass
                menu_bot(etat, qui)
                continue
            if choix == "son":
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="🔔 Son envoyé")
                except Exception:
                    pass
                try:
                    envoyer_son_piece(qui)
                except Exception as ex:
                    print("son pièce", ex)
                continue
            if choix == "marketsmenu":
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"])
                except Exception:
                    pass
                menu_marches(etat, qui)
                continue
            if choix == "markets" and mk == "OK":
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="✅ Marchés enregistrés")
                except Exception:
                    pass
                valider_et_suivre_marches(etat, qui, cb.get("from", {}).get("id"), (cb.get("message") or {}).get("message_id"))
                continue
            if choix == "markets" and (mk in MARCHES or mk in ("BOTH", "ALL")):
                if mk in MARCHES:
                    basculer_marche(etat, qui, mk)
                else:
                    selectionner_marches_suivi(etat, qui, mk)
                try:
                    telegram("answerCallbackQuery", callback_query_id=cb["id"], text="✅ Sélection enregistrée")
                except Exception:
                    pass
                menu_marches(etat, qui, (cb.get("message") or {}).get("message_id"))
                continue
            if choix == "followmarket" and (mk in MARCHES or mk == "BOTH"):
                if not (autorise(etat, qui, cb.get("from", {}).get("id")) or qui not in etat.get("bienvenue", {})):
                    try:
                        telegram("answerCallbackQuery", callback_query_id=cb["id"], text="🔒 Réservé aux VIP")
                    except Exception:
                        pass
                    _envoi_sur(qui, text="🔒 Réservé aux VIP\n🎁 Ta position gratuite du jour est déjà utilisée\n💎 VIP 49,90 € / mois 👇",
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
                            _envoi_sur(qui, text=texte_apercu(mk, r_ref, etat.get(mk, {}), vip=bool(autorise(etat, qui, qui))),
                                      reply_markup=markup_analyse(etat, mk, r_ref, qui))
                        else:
                            _envoi_sur(qui, text=f"⚠️ L'analyse {mk} n'est plus disponible. Relance l'analyse du marché.")
                else:
                    r_ref = DERNIERS.get(mk)
                    if r_ref:
                        res = _envoi_sur(qui, text=texte_apercu(mk, r_ref, etat.get(mk, {}), vip=bool(autorise(etat, qui, qui))),
                                         reply_markup=markup_analyse(etat, mk, r_ref, qui))
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
                               reply_markup=json.dumps({"inline_keyboard": [[{"text": "🧠 En savoir plus", "callback_data": f"details:{mk}"},
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
                        txt_niveaux = texte_vision(mk, r_detail, cle_detail, anglais=str(qui) in LANG_EN)
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
                _envoi_sur(qui, text=texte_apercu(mk, r_resume, etat.get(mk, {}), vip=bool(autorise(etat, qui, qui))),
                           reply_markup=markup_analyse(etat, mk, r_resume, qui))
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
                    # Un abonné BTC + GOLD garde les deux marchés : suivre BTC ne doit pas couper GOLD.
                    if etat.get("marches_par_chat", {}).get(str(qui)) is not None and mk not in marches_choisis(etat, qui):
                        basculer_marche(etat, qui, mk)
                    inscrire_auto(etat, qui, mk, notifier=False)
                    try:
                        telegram("answerCallbackQuery", callback_query_id=cb["id"], text="🔔 Suivi activé pour " + mk)
                    except Exception:
                        pass
                    _envoi_sur(qui, text=(f"🔔 SUIVI ACTIVÉ : {mk}\nJe t'alerterai dès qu'une entrée sera confirmée."
                                          if qui not in LANG_EN else
                                          f"🔔 FOLLOWING {mk}\nI'll alert you when an entry is confirmed."))
                else:
                    try:
                        telegram("answerCallbackQuery", callback_query_id=cb["id"], text="🔒 Réservé aux VIP")
                    except Exception:
                        pass
                    _envoi_sur(qui, text="🔒 Réservé aux VIP\n🎁 Ta position gratuite du jour est déjà utilisée\n⏰ Une nouvelle demain\n💎 VIP 49,90 € / mois 👇",
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
        retenir_prenom(etat, cid, msg.get("from"))
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
        if "live tiktok" in bas or cmd == "/live":
            menu_live(etat, cid)
            continue
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
                live_bande(etat, f"🎉 BIENVENUE À {(fr.get('first_name') or 'un nouveau').split(' ')[0][:20].upper()} DANS ALIGN ! Rejoins le Telegram 👉 lien en bio")
                for p in proprio(etat):    # le propriétaire peut offrir l'accès en 1 clic
                    _envoi_sur(p, text=f"👤 Nouveau visiteur : {nom}",
                               reply_markup=json.dumps({"inline_keyboard": [[{"text": "🎁 Offrir l'accès VIP", "callback_data": f"offrir:{cid}"}]]}))
            elif "mon bot" in txtv or "my bot" in txtv:
                menu_bot(etat, cid)
            elif "mes march" in txtv or "my markets" in txtv:
                menu_marches(etat, cid)
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
        if "devenir vip" in txt or "become vip" in txt:
            lien = etat.get("lien")
            _envoi_sur(cid, text=("💎 TU ES DÉJÀ VIP\n✅ Toutes les positions, les niveaux et le coach sont actifs pour toi"
                                  + ("\n📲 Le canal ALIGN VIP 💎 est accessible avec le bouton ci-dessous" if lien else "")),
                       reply_markup=json.dumps({"inline_keyboard": [[{"text": "📲 Ouvrir le canal ALIGN VIP 💎", "url": lien}]]}) if lien else CLAVIER)
            continue
        if "mes marches" in txt or "my markets" in txt or txt.startswith("/marches"):
            menu_marches(etat, cid)
            continue
        if txt.startswith("/statut") and str(cid) in {str(x) for x in proprio(etat)}:
            _envoi_sur(cid, text=texte_statut(etat, DERNIERS))
            continue
        if "me concentrer" in txt or "where to focus" in txt or txt.startswith("/focus") or txt.strip() == "focus":
            props = classer_marches(DERNIERS, etat, marches_choisis(etat, cid))
            msg = texte_radar(props, DERNIERS, bool(autorise(etat, cid, cid)), cid in LANG_EN) if len(props) >= 1 else None   # même logique que le RADAR (aucun doublon)
            _envoi_sur(cid, text=msg or ("🎯 Aucun de tes marchés n'a de plan exploitable pour l'instant : je te préviens dès que l'un se rapproche."
                                         if cid not in LANG_EN else "🎯 None of your markets has a usable plan right now: I will warn you as soon as one gets close."))
            continue
        if "mon bot" in txt or "mon_bot" in txt:
            menu_bot(etat, cid)
            continue
        if "faire une analyse" in txt or "run an analysis" in txt:
            _envoi_sur(cid, text=("📊 Quel marché veux-tu analyser ?" if cid not in LANG_EN else "📊 Which market do you want to analyse?"),
                       reply_markup=json.dumps({"inline_keyboard": [
                           [{"text": "🥇 GOLD", "callback_data": "analysechoice:GOLD"}],
                           [{"text": "🟠 BTC", "callback_data": "analysechoice:BTC"}],
                           [{"text": "🥇 + 🟠 Les deux", "callback_data": "analysechoice:BOTH"}]
                       ]}))
        elif "analyse" in txt or "etat" in txt:
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

# ───────── ALERTES COURTES : sessions de marché + évènements de l'indicateur Pine ─────────
# Existait déjà (réutilisé, jamais dupliqué) : entrée / TP1 / TP2 / SL / BE / « prépare-toi » (agent), retournement en préparation x/5,
# essoufflement (distribution / accumulation), manipulation, news à 1 h / 40 / 15 / 5 min, fermeture du Gold à 60 / 40 min.
# Ajouté ici : ouvertures et fermetures (préavis 15 et 5 min), alignement qui monte / baisse, SURCHARGE, compression relâchée,
# impulsion, RETOURNEMENT CONFIRMÉ, SL cassé, CONFIRMATION ; alerte de préparation réduite pour le gratuit.
SESSIONS = (   # code, nom FR, nom EN, fuseau, ouverture, fermeture, jours d'ouverture, jours de fermeture, marchés concernés
    ("tokyo", "Tokyo", "Tokyo", "Asia/Tokyo", (9, 0), (15, 30), range(0, 5), range(0, 5), "BTC et GOLD", "BTC and GOLD"),
    ("londres", "Londres", "London", "Europe/London", (8, 0), (16, 30), range(0, 5), range(0, 5), "GOLD et BTC", "GOLD and BTC"),
    ("wall", "Wall Street / Nasdaq", "Wall Street / Nasdaq", "America/New_York", (9, 30), (16, 0), range(0, 5), range(0, 5), "NASDAQ, GOLD et BTC", "NASDAQ, GOLD and BTC"),
    ("gold", "Gold (CME)", "Gold (CME)", "America/Chicago", (17, 0), (16, 0), (6, 0, 1, 2, 3), range(0, 5), "GOLD", "GOLD"),
    ("btc", "BTC (bougie Daily)", "BTC (Daily candle)", "UTC", None, (0, 0), (), range(0, 7), "BTC", "BTC"),
)
SESSIONS_GRATUIT = {("londres", "ouvre"), ("wall", "ouvre")}      # gratuit : seulement le préavis 15 min des deux grandes ouvertures
_ALERTES_SESSION = {
    ("ouvre", 15): (("⏰ Ouverture {nom} dans 15 min ({h})", "💥 Volatilité attendue sur {mk}"), ("🔔 {nom} ouvre dans 15 min ({h})", "👀 {mk} peuvent bouger fort"),
                    ("🕘 Plus que 15 min avant {nom} ({h})", "🎢 Ça peut secouer sur {mk}"), ("📣 {nom} s'ouvre à {h}, dans 15 min", "⚡ Prépare-toi à du mouvement sur {mk}")),
    ("ouvre", 5): (("🚨 {nom} ouvre dans 5 min", "💥 Attention à la volatilité sur {mk}"), ("⏱ 5 min avant {nom} ({h})", "🛡 Pas d'entrée précipitée sur {mk}"),
                   ("🔔 {nom} dans 5 min", "🎢 {mk} : ça va bouger"), ("⏰ Dernière ligne droite avant {nom} ({h})", "👀 Garde un œil sur {mk}")),
    ("ferme", 15): (("🌙 Fermeture {nom} dans 15 min ({h})", "🛡 Évite de te lancer maintenant"), ("⏳ {nom} ferme dans 15 min ({h})", "👀 La liquidité baisse sur {mk}"),
                    ("🕓 Plus que 15 min avant la fin de {nom}", "🔒 Sécurise tes positions sur {mk}"), ("📉 {nom} se termine à {h}, dans 15 min", "😎 Pas de précipitation sur {mk}")),
    ("ferme", 5): (("🚨 {nom} ferme dans 5 min", "🔒 Stop en place sur {mk} ?"), ("⏱ 5 min avant la fermeture de {nom} ({h})", "🛡 Rien de nouveau sur {mk}"),
                   ("🌙 {nom} : fin dans 5 min", "💥 Les prix peuvent bouger vite sur {mk}"), ("⏰ Dernier quart d'heure passé : {nom} ferme à {h}", "👀 Reste prudent sur {mk}")),
}
_ALERTES_SESSION_EN = {
    ("ouvre", 15): (("⏰ {nom} opens in 15 min ({h})", "💥 Volatility expected on {mk}"), ("🔔 {nom} opening in 15 min ({h})", "👀 {mk} can move fast"),
                    ("🕘 15 min left before {nom} ({h})", "🎢 Expect some shaking on {mk}"), ("📣 {nom} opens at {h}, in 15 min", "⚡ Get ready for movement on {mk}")),
    ("ouvre", 5): (("🚨 {nom} opens in 5 min", "💥 Watch the volatility on {mk}"), ("⏱ 5 min before {nom} ({h})", "🛡 No rushed entries on {mk}"),
                   ("🔔 {nom} in 5 min", "🎢 {mk}: movement incoming"), ("⏰ Final stretch before {nom} ({h})", "👀 Keep an eye on {mk}")),
    ("ferme", 15): (("🌙 {nom} closes in 15 min ({h})", "🛡 Avoid jumping in now"), ("⏳ {nom} closing in 15 min ({h})", "👀 Liquidity drops on {mk}"),
                    ("🕓 15 min left before {nom} ends", "🔒 Secure your positions on {mk}"), ("📉 {nom} wraps up at {h}, in 15 min", "😎 No rush on {mk}")),
    ("ferme", 5): (("🚨 {nom} closes in 5 min", "🔒 Is your stop in place on {mk}?"), ("⏱ 5 min before {nom} closes ({h})", "🛡 Nothing new on {mk}"),
                   ("🌙 {nom}: ending in 5 min", "💥 Prices can jump on {mk}"), ("⏰ Last stretch: {nom} closes at {h}", "👀 Stay careful on {mk}")),
}

def _tournante(etat, cle, n):
    """Indice de variante qui tourne : jamais deux fois la même formulation de suite pour un même type d'alerte."""
    rot = etat.setdefault("al_rot", {})
    rot[cle] = (rot.get(cle, -1) + 1) % n
    return rot[cle]

def evenements_sessions(etat, now, derniers=None):
    """Préavis 15 puis 5 min : une seule alerte par évènement et par palier (mémoire al_mem), jamais de rattrapage en rafale."""
    mem, out = etat.setdefault("al_mem", {}).setdefault("sessions", {}), []
    comp = [m for m, r in (derniers or {}).items() if sum((r.get("sqzs") or [0] * 11)[4:10]) >= 3]
    for code, nom_fr, nom_en, zone, ouv, fer, j_ouv, j_fer, mk_fr, mk_en in SESSIONS:
        tz = ZoneInfo(zone)
        auj = datetime.datetime.fromtimestamp(now, tz).date()
        for jour in (auj - datetime.timedelta(days=1), auj, auj + datetime.timedelta(days=1)):
            for kind, hm, jours in (("ouvre", ouv, j_ouv), ("ferme", fer, j_fer)):
                if not hm or jour.weekday() not in jours:
                    continue
                t = datetime.datetime(jour.year, jour.month, jour.day, hm[0], hm[1], tzinfo=tz).timestamp()
                d = t - now
                palier = 15 if 300 < d <= 900 else 5 if 0 < d <= 300 else None
                cle = f"{code}:{kind}:{jour.isoformat()}:{palier}"
                if palier is None or cle in mem:
                    continue
                mem[cle] = int(now)
                out.append(dict(kind="session", code=code, evt=kind, palier=palier, t=t, nom=(nom_fr, nom_en), mk=(mk_fr, mk_en), marches=comp))
    for k in [k for k, v in mem.items() if now - v > 2 * 86400]:
        mem.pop(k)
    return out

def texte_session(etat, ev, anglais=False):
    var = (_ALERTES_SESSION_EN if anglais else _ALERTES_SESSION)[(ev["evt"], ev["palier"])]
    lignes = var[_tournante(etat, f"s:{ev['evt']}:{ev['palier']}", len(var))]
    h = heure(ev["t"])
    out = [l.format(nom=ev["nom"][1 if anglais else 0], h=h, mk=ev["mk"][1 if anglais else 0]) for l in lignes]
    if ev["evt"] == "ouvre" and ev["palier"] == 15 and ev.get("marches"):
        out.append(("⚡ " + ", ".join(ev["marches"]) + (" squeezed: breakout possible" if anglais else " comprimé : explosion possible")))
    return out[:3]

_PINE_TEXTES = {   # type -> variantes (FR, EN) ; {ic} {m} {n} {c} {seuil} {sens} {strat} {u} {niv} {fleche} {ratio}
    "align_haut": (("📈 {ic} {m} : {n}/11 UT alignées", "🎯 Seuil {seuil} {etat_seuil}"), ("🧲 {ic} {m} : l'alignement monte ({n}/11)", "🎯 {etat_seuil_court}"),
                   ("⬆️ {ic} {m} : {n} unités dans le même sens", "🎯 {etat_seuil_court}")),
    "align_bas": (("📉 {ic} {m} : alignement qui baisse ({n}/11)", "⏳ Il en faut {seuil}"), ("⬇️ {ic} {m} : {n}/11 UT, ça se disperse", "🙅 Pas de validation"),
                  ("🌫 {ic} {m} : moins d'unités d'accord ({n}/11)", "👀 Seuil {seuil}")),
    "surcharge": (("⚡ {ic} {m} : SURCHARGE, {c}/11 UT comprimées", "👀 Explosion possible, attends la direction"), ("🔋 {ic} {m} : le ressort se comprime ({c}/11)", "🧭 La clôture donnera le sens"),
                  ("💤 {ic} {m} : marché très comprimé ({c}/11)", "⚠️ Ça peut partir d'un coup")),
    "relache": (("💥 {ic} {m} : compression relâchée", "🧭 Sens à confirmer à la clôture"), ("🚀 {ic} {m} : ça se libère après la compression", "👀 Pas de précipitation, on attend la bougie"),
                ("🎆 {ic} {m} : la compression saute", "🕯 Lis la clôture avant d'agir")),
    "impulsion": (("🚀 {ic} {m} : impulsion {fleche}", "🕯 Bougie 15 min x{ratio} l'ATR"), ("💥 {ic} {m} : mouvement fort {fleche}", "😮 Grosse bougie 15 min (x{ratio})"),
                  ("⚡ {ic} {m} : pulsion {fleche}", "🧘 Ne cours pas après, attends le repli")),
    "ret_conf": (("✅ {ic} {m} : RETOURNEMENT CONFIRMÉ {sens}", "🎯 {strat}"), ("🔁 {ic} {m} : le retournement est validé ({sens})", "🎯 Profil {strat}"),
                 ("🏁 {ic} {m} : retournement confirmé, direction {sens}", "🧭 {strat}")),
    "ret_cancel": (("⛔ {ic} {m} : SL cassé à la clôture", "↩ Retournement en cours, j'attends 15 min / 1h"), ("🛑 {ic} {m} : le stop du plan est franchi", "🔄 Je guette la confirmation 15 min / 1h"),
                   ("🚧 {ic} {m} : plan annulé (stop cassé)", "👀 Retournement possible, rien n'est validé")),
    "sniper": (("🎯 Entrée sniper {ic} {m} : {ordre} {za}–{zb} ({ut})", "🛑 SL {sl} • TP1 {tp1} • TP plan {tp}", "📐 R/R {rr} (plan {rrp}) • rejet {rejets}"),
               ("🔫 {ic} {m} : {ordre} sniper {za}–{zb} sur {ut}", "🛑 Stop {sl} • 🎯 TP1 {tp1}, puis {tp}", "📐 x{rr} le risque (plan x{rrp})"),
               ("🎯 Sniper {ic} {m} : rejet confirmé {rejets}, {ordre} {za}–{zb}", "🛑 SL {sl} • TP1 {tp1}", "🗺 Plan {tp} conservé, R/R plan {rrp}")),
    "confirmation": (("✅ {ic} {m} : CONFIRMATION {sens}", "🕯 Clôture {u} {pos} {niv}"), ("🔔 {ic} {m} : confirmation {sens} validée", "🕯 {u} clôturée {pos} {niv}"),
                     ("🎯 {ic} {m} : {sens} confirmé à la clôture {u}", "📍 Ligne de décision {niv}")),
}
_PINE_TEXTES_EN = {
    "align_haut": (("📈 {ic} {m}: {n}/11 timeframes aligned", "🎯 Threshold {seuil} {etat_seuil}"), ("🧲 {ic} {m}: alignment is rising ({n}/11)", "🎯 {etat_seuil_court}"),
                   ("⬆️ {ic} {m}: {n} timeframes agree", "🎯 {etat_seuil_court}")),
    "align_bas": (("📉 {ic} {m}: alignment dropping ({n}/11)", "⏳ Need {seuil}"), ("⬇️ {ic} {m}: {n}/11, it's scattering", "🙅 No validation"),
                  ("🌫 {ic} {m}: fewer timeframes agree ({n}/11)", "👀 Threshold {seuil}")),
    "surcharge": (("⚡ {ic} {m}: OVERLOAD, {c}/11 timeframes squeezed", "👀 Breakout possible, wait for the direction"), ("🔋 {ic} {m}: the spring is tightening ({c}/11)", "🧭 The close will give the way"),
                  ("💤 {ic} {m}: very tight market ({c}/11)", "⚠️ It can go all at once")),
    "relache": (("💥 {ic} {m}: squeeze released", "🧭 Direction to confirm at the close"), ("🚀 {ic} {m}: it's freeing up after the squeeze", "👀 No rush, wait for the candle"),
                ("🎆 {ic} {m}: the squeeze pops", "🕯 Read the close before acting")),
    "impulsion": (("🚀 {ic} {m}: impulse {fleche}", "🕯 15 min candle x{ratio} the ATR"), ("💥 {ic} {m}: strong move {fleche}", "😮 Big 15 min candle (x{ratio})"),
                  ("⚡ {ic} {m}: surge {fleche}", "🧘 Don't chase it, wait for the pullback")),
    "ret_conf": (("✅ {ic} {m}: REVERSAL CONFIRMED {sens}", "🎯 {strat}"), ("🔁 {ic} {m}: the reversal is validated ({sens})", "🎯 Profile {strat}"),
                 ("🏁 {ic} {m}: reversal confirmed, direction {sens}", "🧭 {strat}")),
    "ret_cancel": (("⛔ {ic} {m}: SL broken at the close", "↩ Reversal in progress, waiting for 15 min / 1h"), ("🛑 {ic} {m}: the plan's stop is crossed", "🔄 Watching for the 15 min / 1h confirmation"),
                   ("🚧 {ic} {m}: plan cancelled (stop broken)", "👀 Reversal possible, nothing validated")),
    "sniper": (("🎯 Sniper entry {ic} {m}: {ordre} {za}–{zb} ({ut})", "🛑 SL {sl} • TP1 {tp1} • plan TP {tp}", "📐 R/R {rr} (plan {rrp}) • rejection {rejets}"),
               ("🔫 {ic} {m}: sniper {ordre} {za}–{zb} on {ut}", "🛑 Stop {sl} • 🎯 TP1 {tp1}, then {tp}", "📐 x{rr} the risk (plan x{rrp})"),
               ("🎯 Sniper {ic} {m}: rejection confirmed {rejets}, {ordre} {za}–{zb}", "🛑 SL {sl} • TP1 {tp1}", "🗺 Plan {tp} kept, plan R/R {rrp}")),
    "confirmation": (("✅ {ic} {m}: CONFIRMATION {sens}", "🕯 {u} close {pos} {niv}"), ("🔔 {ic} {m}: {sens} confirmation validated", "🕯 {u} closed {pos} {niv}"),
                     ("🎯 {ic} {m}: {sens} confirmed at the {u} close", "📍 Decision line {niv}")),
}
_PINE_PRIO = {"ret_conf": 0, "sniper": 1, "scalp_inv": 1, "confirmation": 1, "ret_cancel": 2, "impulsion": 3, "surcharge": 4, "relache": 5, "align_haut": 6, "align_bas": 7}

CONF_REPIT = {"SWING": 4 * 3600, "DAY": 3600, "SCALPING": 900}   # même confirmation (même sens) : une seule fois par période — la zone qui bouge ne la relance pas

def evenements_pine(etat, m, r, cle, now):
    """Évènements de l'indicateur au moment où ils arrivent : chacun une seule fois (fronts montants mémorisés par marché)."""
    mem = etat.setdefault("al_mem", {}).setdefault("pine", {}).setdefault(m, {})
    statut, _ = etat_marche_hb(m, r, now)
    ev, e = [], hb_etat_surveille(r)
    d, n, comp = e["d"], e["n"], int(r.get("comp", 0))
    base = dict(m=m, ic=ICONE.get(m, ""), seuil=MIN_ALIGN, n=n, c=comp)
    if statut != "ouvert":
        mem.update(n=n, comp=comp)
        return ev                                      # marché fermé ou données périmées : aucune alerte inventée
    prev_n, prev_c = mem.get("n"), mem.get("comp")
    if prev_n is not None and not cle.get("trade") and now - mem.get("t_align", 0) >= 1800:   # 7↔8 qui clignote : au plus 1 alerte / 30 min
        franchit_haut, franchit_bas = n >= MIN_ALIGN > prev_n, n < MIN_ALIGN <= prev_n
        # Seulement le franchissement du seuil : la montée « 6/11 → il en faut 8 » est déjà affichée dans le RADAR (pas de doublon).
        if franchit_haut:
            ev.append(dict(kind="align_haut", **base, etat_seuil="atteint ✅", etat_seuil_court="Seuil atteint")); mem["t_align"] = now
        elif franchit_bas:
            ev.append(dict(kind="align_bas", **base)); mem["t_align"] = now
    if prev_c is not None:
        if comp >= MIN_SQZ > prev_c:
            ev.append(dict(kind="surcharge", **base))
        elif prev_c >= MIN_SQZ and comp <= MIN_SQZ - 2:
            ev.append(dict(kind="relache", **base))
    mem.update(n=n, comp=comp)
    b15, atr_ = r.get("b15") or [], float(r.get("atr") or 0)
    if len(b15) >= 3 and atr_ > 0:                      # impulsion : dernière bougie 15 min CLÔTURÉE, grande et pleine
        x = b15[-2]; rng = x["h"] - x["l"]
        if rng >= 1.5 * atr_ and abs(x["c"] - x["o"]) >= 0.6 * rng and mem.get("imp_t") != x["t"]:
            mem["imp_t"] = x["t"]
            ev.append(dict(kind="impulsion", **base, fleche=("⬆️ HAUSSIER 🟢" if x["c"] > x["o"] else "⬇️ BAISSIER 🔴"), ratio=str(round(rng / atr_, 1)).replace(".", ",")))
    rd, rc = int(r.get("ret_dir") or 0), bool(r.get("ret_conf"))
    if rd and rc and not mem.get("rc"):
        ev.append(dict(kind="ret_conf", **base, sens="LONG" if rd == 1 else "SHORT", strat=r.get("strat") or "—"))
    elif rd and not rc and not mem.get("rd"):
        ev.append(dict(kind="ret_cancel", **base))
    mem["rc"], mem["rd"] = rc, bool(rd)
    sn = r.get("sniper")
    if sn and not cle.get("trade"):                      # entrée sniper en cascade : une fois par UT et par niveau, 30 min mini ; s'ajoute au plan, ne le remplace pas
        cle_sn = f"{sn['d']}:{sn['ut']}:{round(sn['niveau'] / max(sn['niveau'] * 0.0004, 1e-9))}"
        if mem.get("sn_cle") != cle_sn and now - mem.get("sn_t", 0) >= 1800:
            mem["sn_cle"], mem["sn_t"] = cle_sn, now
            f = lambda v: px(v)
            ev.append(dict(kind="sniper", **base, ordre="vente" if sn["d"] == -1 else "achat", za=f(sn["za"]), zb=f(sn["zb"]), sl=f(sn["sl"]), tp1=f(sn["tp1"]),
                           tp=f(sn["tp2"]), ut=sn["ut"], rejets="+".join(sn["rejets"]), rr=str(round(sn["rr"], 1)).replace(".", ","), rrp=str(round(sn["rr_plan"], 1)).replace(".", ",")))
    if d and not cle.get("trade"):                       # ↩ SCALP INVERSE : une fois par niveau, 30 min mini (même règle que le sniper)
        try:
            si = scalp_inverse(r, d)
        except Exception:
            si = None
        if si:
            cle_si = f"{si['d']}:{round(si['e'] / max(si['e'] * 0.0005, 1e-9))}"
            if mem.get("si_cle") != cle_si and now - mem.get("si_t", 0) >= 1800:
                mem["si_cle"], mem["si_t"] = cle_si, now
                ev.append(dict(kind="scalp_inv", **base, si=si, dp=d))
    zp, strat = r.get("zone_pine"), r.get("strat") or ""
    zp = trait_indicateur(r, d) or zp                  # v24.3 : trait blanc « Clôture … ce trait » de l'indicateur sur la vue de validation
    if d and zp and strat and not cle.get("trade") and strategie_alignement(r.get("dirs"), d, r.get("dirW") or 0)[1] == "CONFIRMÉ":
        barres = (r.get("m1") if strat == "SCALPING" else r.get("b5")) or []           # même bougie que le trait de l'indicateur (vue du plan)
        if len(barres) >= 3:
            c1, c0, t1 = barres[-2]["c"], barres[-3]["c"], barres[-2]["t"]
            au_dessus = lambda c: c > zp["zmil"] if d == 1 else c < zp["zmil"]
            deja = mem.get("conf_sens") == d and now - float(mem.get("conf_at", 0)) < CONF_REPIT.get(strat, 3600)
            if au_dessus(c1) and not au_dessus(c0) and mem.get("conf_t") != t1 and not deja:
                mem["conf_t"], mem["conf_sens"], mem["conf_at"] = t1, d, now
                ev.append(dict(kind="confirmation", **base, sens="LONG" if d == 1 else "SHORT", u=PLAN_VUE.get(strat, "5 min"),
                               pos="au-dessus de" if d == 1 else "sous", niv=px(zp["zmil"])))
    return ev

def texte_pine(etat, ev, anglais=False):
    var = (_PINE_TEXTES_EN if anglais else _PINE_TEXTES)[ev["kind"]]
    lignes = var[_tournante(etat, f"p:{ev['kind']}:{ev['m']}", len(var))]
    ev = dict(ev)
    if anglais:
        ev["pos"] = {"au-dessus de": "above", "sous": "below"}.get(ev.get("pos"), ev.get("pos"))
        ev["etat_seuil"] = "reached ✅" if "atteint" in str(ev.get("etat_seuil", "")) else "almost"
        ev["etat_seuil_court"] = "Threshold reached" if "atteint" in str(ev.get("etat_seuil_court", "")) else "Almost at the threshold"
        ev["ordre"] = {"vente": "sell", "achat": "buy"}.get(ev.get("ordre"), ev.get("ordre"))
        ev["fleche"] = str(ev.get("fleche", "")).replace("HAUSSIER", "BULLISH").replace("BAISSIER", "BEARISH")
    return [l.format(**{k: v for k, v in ev.items() if k != "kind"}) for l in lignes]

def regrouper_alertes(blocs):
    """Plusieurs alertes dans la même minute = UN seul message de 4 lignes max : titre + première ligne de chacune."""
    if len(blocs) == 1:
        return blocs[0][:4]
    lignes = [b[0] for b in blocs[:3]]
    return ([f"⚡ {len(blocs)} infos"] + lignes)[:4]

def diffuser_alerte(etat, chats, fr, en):
    """VIP (chaîne + privés qui ont coché le marché) : langue de chaque destinataire ; l'en-tête sert au filtre par marché."""
    for cid in destinataires_message(etat, chats, "\n".join(fr)):
        _envoi_sur(cid, text="\n".join(en if str(cid) in LANG_EN else fr))

def _liste_marches(noms, anglais=False):
    """« GOLD » · « GOLD et NASDAQ » · « NASDAQ, GOLD et BTC » (anglais : and)."""
    et = " and " if anglais else " et "
    return noms[0] if len(noms) == 1 else ", ".join(noms[:-1]) + et + noms[-1]

def adapter_marches_session(lignes, mk, choisis, anglais=False):
    """Remplace la liste de marchés d'une session (« GOLD et BTC ») par les marchés de la personne ; None si aucun n'est concerné."""
    if not mk or not choisis:
        return lignes
    cites = [m for m in re.findall(r"BTC|GOLD|NASDAQ", mk)]
    a_garder = [m for m in cites if m in choisis]
    if not a_garder:
        return None
    nouveau = _liste_marches(a_garder, anglais)
    return [l.replace(mk, nouveau) for l in lignes]

# ───────── Coach de concentration : sur quel marché se concentrer ? ─────────
FOCUS_NOMS = {"dans_zone": "dans la zone d'entrée", "proche": "proche de la zone", "en_approche": "en approche", "loin": "loin de la zone",
              "bloque": "bloqué (zone extrême Daily/Weekly)", "sans_plan": "pas de plan fixé", "ferme": "marché fermé", "position": "déjà en position"}

def proximite_marche(m, r, cle, now=None):
    """Distance à l'entrée d'un marché, en ATR 15 min. rang : 0 dans la zone • 1 proche (≤ 1,5 ATR) • 2 en approche (≤ 4) • 3 loin
    • 4 bloqué par le Daily/Weekly • 5 pas de plan • 6 marché fermé • -1 déjà en position. Rien n'est inventé : zone du plan ou ordre surveillé."""
    now = time.time() if now is None else now
    cle = cle or {}
    prix = r["m1"][-1]["c"]
    base = dict(m=m, prix=prix, atr_n=99.0)
    if cle.get("trade"):
        return dict(base, classe="position", rang=-1, d=cle["trade"].get("d"))
    if m != "BTC" and not cme_ouvert(int(now)):
        return dict(base, classe="ferme", rang=6)
    o, d = cle.get("ordre"), r.get("dirPlan") or 0
    zp = r.get("zone_pine") if d else None
    if o:
        za, zb = min(o.get("za", o["e"]), o.get("zb", o["e"])), max(o.get("za", o["e"]), o.get("zb", o["e"]))
        d = o.get("d") or d
    elif zp:
        za, zb = min(zp["za"], zp["zb"]), max(zp["za"], zp["zb"])
    else:
        return dict(base, classe="sans_plan", rang=5)
    pe = None
    if not o and d in (1, -1):
        try:
            pe = pine_entree(r, d) if r.get("b15") and "planH" in r else None
        except Exception:
            pe = None
        if pe and pe.get("fvg_ut"):                           # v24.3 : même zone que l'indicateur sur la vue 5 min (bande verte)
            za, zb = min(pe["za"], pe["zb"]), max(pe["za"], pe["zb"])
        else:
            pe = None
    if d not in (1, -1):
        return dict(base, classe="sans_plan", rang=5)
    if bloque_dw(r, d, prix):
        return dict(base, classe="bloque", rang=4, d=d, za=za, zb=zb)
    a = float(r.get("atr") or 0)
    dist = 0.0 if za <= prix <= zb else min(abs(prix - za), abs(prix - zb))
    atr_n = dist / a if a > 0 else 99.0
    classe, rang = (("dans_zone", 0) if dist == 0 else ("proche", 1) if atr_n <= 1.5 else ("en_approche", 2) if atr_n <= 4 else ("loin", 3))
    unite = pe["sl_ut"] if pe else HB_UNITE_VALIDATION.get(r.get("strat") or "", "15 min")
    mil = pe["zmil"] if pe else (zp or {}).get("zmil")
    action = (f"clôture {unite} {'sous' if d == -1 else 'au-dessus de'} {px(mil)}" if mil else f"rejet + clôture {unite} dans la zone")
    return dict(base, classe=classe, rang=rang, d=d, za=za, zb=zb, dist=dist, atr_n=atr_n, action=action, au_dessus=prix < za)

def classer_marches(derniers, etat, choisis, now=None):
    """Marchés suivis par la personne, du plus proche d'une entrée au plus loin."""
    props = [proximite_marche(m, r, etat.get(m, {}), now) for m, r in (derniers or {}).items() if m in choisis and r.get("m1")]
    return sorted(props, key=lambda p: (p["rang"] if p["rang"] >= 0 else 9, p["atr_n"]))


# ───────── RADAR ALIGN : UN seul message par personne, mis à jour sur place ─────────
# Remplace la veille « je surveille » marché par marché et le message « OÙ TE CONCENTRER » : le marché le plus proche
# d'une entrée en tête (niveaux du plan de l'indicateur), les autres en une ligne. Nouveau message (avec son) seulement
# quand un marché devient « prépare-toi » ; sinon le message existant est édité (sans notification).
RADAR_REFRESH_SEC = 120       # au plus une édition toutes les 2 min par personne (Telegram : pas de 429)
RADAR_ALERTE_MIN_SEC = 900    # au plus une alerte « prépare-toi » (avec son) toutes les 15 min par personne
RADAR_ALERTE_RANG = 1         # rang ≤ 1 (dans la zone ou à ≤ 1,5 ATR) : « prépare-toi » → nouveau message avec son
SENS_COURT = {1: "LONG ⬆️", -1: "SHORT ⬇️"}

def _radar_n_ut(r, d):
    return r.get("bull", 0) if d == 1 else r.get("bear", 0) if d == -1 else max(r.get("bull", 0), r.get("bear", 0))

def _radar_pret(p, derniers):
    """« Prépare-toi » seulement si le prix est proche (rang ≤ 1) ET que l'alignement a atteint le seuil (8/11) : sinon c'est juste « proche »."""
    return 0 <= p["rang"] <= RADAR_ALERTE_RANG and _radar_n_ut((derniers or {}).get(p["m"]) or {}, p.get("d")) >= MIN_ALIGN

def _radar_ordre(props, derniers):
    """Marchés prêts (proches + alignés) d'abord, puis l'ordre de proximité habituel."""
    return sorted(props, key=lambda p: 0 if _radar_pret(p, derniers) else 1)

def radar_entree_sl(r, d, za=None, zb=None):
    """Entrée / SL / TP1 du RADAR = plan de l'indicateur (même plan que l'ordre Telegram : pine_entree), jamais un mini-SL M5 (trop dangereux).
    L'entrée et le SL visent le même sommet / creux de structure du plan ; la zone affichée est réduite à sa partie rentable."""
    pe = pine_entree(r, d) if r.get("b15") and "planH" in r else None
    if pe:
        return dict(e=pe["e"], sl=pe["sl"], tp1=pe["tp1"], za=pe["za"], zb=pe["zb"],
                    src=(pe["src"].replace(" (indicateur ALIGN)", "") if pe.get("fvg_ut") else "plan de l'indicateur"),
                    tp2=pe.get("tp2"), ut=pe.get("sl_ut"), fvg=bool(pe.get("fvg_ut")), d=d)
    plan = r.get("plan_fige") or {}
    if plan.get("d") == d and plan.get("sl") is not None:
        a_, b_ = zone_rentable(d, za, zb, plan["sl"], plan["tp1"]) if za is not None else (None, None)
        return dict(e=plan["e"], sl=plan["sl"], tp1=plan["tp1"], za=a_, zb=b_, src="plan de l'indicateur")
    return None

def texte_radar(props, derniers, vip=True, anglais=False, now=None, intro=None):
    """Texte du RADAR, construit uniquement à partir des vraies données (classer_marches + plan figé de l'indicateur).
    Gratuit : marché favori, sens et état — jamais l'entrée, le SL ni le TP (réservés aux VIP)."""
    if not props:
        return None
    now = time.time() if now is None else now
    ic = lambda p: ICONE.get(p["m"], "")
    props = _radar_ordre(props, derniers)
    actifs = [p for p in props if 0 <= p["rang"] <= 3]
    en_pos = [p for p in props if p["rang"] == -1]
    t = actifs[0] if actifs else None
    l = []
    if t:
        etat_t = ("get ready" if anglais else "prépare-toi") if _radar_pret(t, derniers) else \
                 ("close, alignment not reached yet" if anglais else "proche, alignement pas encore atteint") if t["rang"] <= RADAR_ALERTE_RANG else \
                 ("approaching" if anglais else "en approche") if t["rang"] == 2 else ("least far, nothing close" if anglais else "le moins loin, rien de proche")
        l.append(f"🎯 FOCUS : {ic(t)} {t['m']} — {etat_t}")
        if intro and vip:
            l += [x for x in str(intro).split("\n") if x.strip()][:3]      # phrases de l'IA (jamais les mêmes), niveaux toujours calculés par le bot
        r = (derniers or {}).get(t["m"]) or {}
        d = t.get("d")
        prof = {"SWING": "SWING", "DAY": "INTRADAY", "SCALPING": "SCALP"}.get(r.get("strat") or "", "")
        l.append(("📉 " if d == -1 else "📈 ") + (f"Direction : {SENS_COURT.get(d, '?')}" if anglais else f"Sens : {SENS_COURT.get(d, '?')}") + (f" · {prof}" if prof else ""))
        if vip:
            es = radar_entree_sl(r, d, t["za"], t["zb"])
            za_, zb_ = (es.get("za"), es.get("zb")) if es and es.get("za") is not None else (t["za"], t["zb"])
            l.append((f"📍 Entry zone : {px(za_)} → {px(zb_)}" if anglais else f"📍 Zone d'entrée : {px(za_)} → {px(zb_)}"))
            if es:
                l.append((f"🎯 Entry : {px(es['e'])}" if anglais else f"🎯 Entrée : {px(es['e'])}") + f" ({es['src']})")
                l.append(f"🛑 SL : {px(es['sl'])} · {px(abs(es['e'] - es['sl']))} pts")
                l.append(f"🏁 TP1 : {px(es['tp1'])} · R/R {abs(es['tp1'] - es['e']) / max(abs(es['e'] - es['sl']), 1e-9):.1f}".replace(".", ","))
                if es.get("fvg") and tp2_affichable(d, es["tp1"], es.get("tp2")):
                    l.append(f"🏁 TP2 : {px(es['tp2'])}" + (" (if TP1 breaks, it keeps going)" if anglais else " (si le TP1 casse, ça continue)"))
                if es.get("fvg"):
                    l.append((f"👀 TradingView : {es['ut']} view = same levels" if anglais else f"👀 TradingView : vue {es['ut']} = mêmes niveaux"))
                    if anglais:
                        l.append("🧘 It's an FVG: it can sting a bit before turning, don't panic while the SL holds")
                    else:
                        l += [x for x in coach_fvg(r, d, r["m1"][-1]["c"]) if not x.startswith("📍")] if r.get("m1") else []
            if t["rang"] == 0:
                l.append("🟨 Price is IN the zone" if anglais else "🟨 Le prix est DANS la zone")
            else:
                l.append((f"📏 Price {px(t['dist'])} away (≈ {t['atr_n']:.1f} ATR 15 min)" if anglais else
                          f"📏 Prix à {px(t['dist'])} de la zone (≈ {t['atr_n']:.1f} ATR 15 min)".replace(".", ",")))
            l.append(("⏳ Waiting for: " if anglais else "⏳ J'attends : ") + t["action"])
        else:
            l.append("🔒 Entry, SL, TP : VIP" if anglais else "🔒 Entrée, SL, TP : VIP")
        n = _radar_n_ut(r, d)
        l.append((f"🧭 Aligned timeframes : {n}/11" if anglais else f"🧭 UT alignées : {n}/11") + (" ✅" if n >= MIN_ALIGN else f" ({'need' if anglais else 'il en faut'} {MIN_ALIGN})"))
    else:
        l.append("📡 RADAR ALIGN — " + ("no entry close" if anglais else "aucune entrée proche"))
    autres = [p for p in props if p is not t]
    if autres:
        l.append("━━━━━━━━━━━━━━━")
        for k, p in enumerate(autres, start=2 if t else 1):
            sens = SENS_COURT.get(p.get("d"), "")
            etat_p = FOCUS_NOMS.get(p["classe"], p["classe"])
            suite = f" (≈ {p['atr_n']:.1f} ATR)".replace(".", ",") if 0 <= p["rang"] <= 3 and p["atr_n"] < 90 else ""
            l.append(f"{k}️⃣ {ic(p)} {p['m']} : " + (f"{sens} · " if sens and p["rang"] not in (5, 6) else "") + etat_p + suite)
    if en_pos:
        l.append("📍 " + ("In a trade: follow the coach" if anglais else "En position : suis les alertes du coach"))
    l.append(("🔔 New message only when it's time to get ready" if anglais else "🔔 Nouveau message seulement quand il faut se préparer"))
    l.append(f"🔄 {'Updated' if anglais else 'Mis à jour'} {datetime.datetime.fromtimestamp(now, PARIS).strftime('%H:%M')}")
    return "\n".join(l)

def _radar_fond(txt):
    """Contenu du radar sans l'heure ni les distances (qui bougent à chaque tick) : on n'édite que si le fond change."""
    lignes = [x for x in str(txt).split("\n") if not x.startswith("🔄")]
    return re.sub(r"[\d.,]+", "#", "\n".join(x for x in lignes if not x.startswith("📏")))

def destinataires_radar(etat, chats):
    """Personnes qui suivent au moins un marché (« Valider et suivre ») + VIP qui ont coché au moins 2 marchés. Jamais la chaîne."""
    canal = str(etat.get("canal") or "")
    out = set()
    for m, suivis in (etat.get("veille_cloture") or {}).items():
        for cid, s in (suivis or {}).items():
            if isinstance(s, dict) and s.get("multi"):
                out.add(str(cid))
    for cid in {str(c) for c in chats}:
        try:
            if autorise(etat, cid, cid) and len(marches_choisis(etat, cid)) >= 2:
                out.add(cid)
        except Exception:
            pass
    return sorted(out - {canal})

def _radar_supprimer(cid, mid):
    if not mid:
        return
    try:
        telegram("deleteMessage", chat_id=cid, message_id=mid)
    except Exception:
        pass                                      # déjà supprimé ou trop ancien : sans gravité

IA_RADAR = os.environ.get("IA_RADAR", "1") == "1"   # coupe-circuit : 0 = RADAR sans IA
RADAR_IA_CACHE_SEC = 900      # une seule rédaction IA par marché et par niveau visé (partagée entre abonnés) : coût minimal

def intro_ia_radar(etat, m, r, cle, p, es):
    """L'IA rédige l'annonce « prépare-toi » (3 lignes, formulation toujours différente) UNIQUEMENT au moment où un marché devient prêt.
    Les chiffres viennent du bot (ia() refuse tout prix absent des données) ; sens contraire à l'indicateur = commentaire jeté."""
    try:
        unite = HB_UNITE_VALIDATION.get(r.get("strat") or "", "15 min")
        data = dict(donnees_ia(m, r, cle), radar={
            "sens": "LONG" if p.get("d") == 1 else "SHORT", "entrée visée": round(es["e"], 2) if es else None,
            "SL": round(es["sl"], 2) if es else None, "TP1": round(es["tp1"], 2) if es else None,
            "niveau": (es or {}).get("src"), "unité à regarder": unite, "ce que j'attends": p.get("action")})
        cle_c = f"radar:{m}:{round((es or {}).get('e') or p.get('za') or 0, 1)}"
        avis = ia(etat, "Un marché approche de son point d'entrée. Écris EXACTEMENT 3 lignes courtes, chacune commence par un emoji, 12 mots max : "
                        "1) dis de se préparer sur ce marché, 2) le niveau visé (entrée) et le sens, 3) l'unité de temps à regarder et ce qu'on attend. "
                        "Utilise uniquement les chiffres fournis, n'invente aucun niveau, varie la formulation à chaque fois. "
                        "Le sens est UNIQUEMENT celui fourni dans radar.sens (il vient de l'indicateur) : ne le change jamais. " + IA_TON_JEUNE,
                  data, cle_cache=cle_c, duree=RADAR_IA_CACHE_SEC, premium=True)
    except Exception as ex:
        print("ia radar", m, type(ex).__name__, ex)
        return None
    if not avis or sens_ia_contradictoire(avis, p.get("d")):
        return None
    return compacter_ia(avis)

def radar_tick(etat, chats, derniers, now=None):
    """Un RADAR par personne : édité sur place ; nouveau message (son) seulement quand un marché devient « prépare-toi »
    ou quand le marché en tête change (l'ancien radar est alors supprimé : jamais deux radars dans la conversation)."""
    now = time.time() if now is None else now
    mem_all = etat.setdefault("radar_mem", {})
    for cid in destinataires_radar(etat, chats):
        try:
            anglais = cid in LANG_EN
            vip = bool(autorise(etat, cid, cid))
            props = classer_marches(derniers, etat, marches_choisis(etat, cid), now)
            mem = mem_all.setdefault(cid, {})
            actifs = [p for p in _radar_ordre(props, derniers) if 0 <= p["rang"] <= 3]
            focus = actifs[0]["m"] if actifs else ""
            pret = bool(actifs) and _radar_pret(actifs[0], derniers)
            rang = (actifs[0]["rang"] if pret else max(actifs[0]["rang"], RADAR_ALERTE_RANG + 1)) if actifs else 9
            alerte = (bool(focus) and pret and now - float(mem.get("t_alerte", 0)) >= RADAR_ALERTE_MIN_SEC
                      and (mem.get("focus") != focus or int(mem.get("rang", 9)) > RADAR_ALERTE_RANG))
            if not (pret and mem.get("ia_focus") == focus):
                mem.pop("ia", None); mem.pop("ia_focus", None)          # plus prêt ou autre marché : les phrases IA ne valent plus
            if alerte and vip and not anglais and IA_RADAR:
                t0 = actifs[0]; r0 = (derniers or {}).get(focus) or {}
                intro = intro_ia_radar(etat, focus, r0, etat.get(focus, {}), t0, radar_entree_sl(r0, t0.get("d"), t0["za"], t0["zb"]))
                if intro:
                    mem.update(ia=intro, ia_focus=focus)
            txt = texte_radar(props, derniers, vip, anglais, now, intro=mem.get("ia"))
            if not txt:
                continue
            change_tete = mem.get("mid") and focus != mem.get("focus", "") and now - float(mem.get("t", 0)) >= RADAR_REFRESH_SEC
            if alerte or change_tete or not mem.get("mid"):
                res = _envoi_sur(cid, text=txt, **({} if alerte else {"disable_notification": "true"}))
                if isinstance(res, dict) and res.get("ok"):
                    _radar_supprimer(cid, mem.get("mid"))
                    mem.update(mid=res["result"]["message_id"], t=now, fond=_radar_fond(txt), focus=focus, rang=rang)
                    if alerte:
                        mem["t_alerte"] = now
                continue
            mem["rang"] = rang
            if now - float(mem.get("t", 0)) < RADAR_REFRESH_SEC or _radar_fond(txt) == mem.get("fond"):
                continue                          # rien de nouveau sur le fond, ou édition trop récente
            try:
                telegram("editMessageText", chat_id=cid, message_id=mem["mid"], text=txt)
                mem.update(t=now, fond=_radar_fond(txt))
            except Exception as ex:
                e = str(ex).lower()
                if "not modified" in e:
                    mem.update(t=now, fond=_radar_fond(txt))
                elif any(x in e for x in ("not found", "can't be edited", "message_id_invalid")):
                    mem.pop("mid", None)          # recréé au prochain tick
                else:
                    raise
        except Exception as ex:
            print("radar", cid, type(ex).__name__, ex)

# ───────── /statut : tout est-il opérationnel ? (lu sur l'état réel du worker, jamais supposé) ─────────
def prochaine_session(now):
    """(nom, heure) de la prochaine ouverture de session de marché (Tokyo, Londres, Wall Street, Gold CME)."""
    meilleur = None
    for code, nom_fr, nom_en, zone, ouv, fer, j_ouv, j_fer, mk_fr, mk_en in SESSIONS:
        if not ouv:
            continue
        tz = ZoneInfo(zone)
        auj = datetime.datetime.fromtimestamp(now, tz).date()
        for k in range(0, 8):
            jour = auj + datetime.timedelta(days=k)
            if jour.weekday() not in j_ouv:
                continue
            t = datetime.datetime(jour.year, jour.month, jour.day, ouv[0], ouv[1], tzinfo=tz).timestamp()
            if t > now:
                if meilleur is None or t < meilleur[1]:
                    meilleur = (nom_fr, t)
                break
    return meilleur

def controles_statut(etat, derniers, now=None):
    """Liste de (état, texte) : état = « ok » · « attention » · « veille » (normal, p. ex. marché fermé). Chaque ligne vient d'une donnée réelle."""
    now = time.time() if now is None else now
    out = [("ok", "📡 Telegram : connecté (je te réponds)")]
    for m in MARCHES:
        r = (derniers or {}).get(m)
        ic = ICONE.get(m, "")
        if not r or not r.get("m1"):
            out.append(("attention", f"{ic} {m} : pas encore d'analyse (premier tour en cours ou données indisponibles)"))
            continue
        age = now - float(r["m1"][-1]["t"])
        if m != "BTC" and not cme_ouvert(int(now)):
            out.append(("veille", f"{ic} {m} : marché fermé (normal)"))
            continue
        if age > 600:
            out.append(("attention", f"{ic} {m} : données en retard de {int(age // 60)} min"))
            continue
        d = r.get("dirPlan") or 0
        n = r.get("bull", 0) if d == 1 else r.get("bear", 0) if d == -1 else max(r.get("bull", 0), r.get("bear", 0))
        plan = f"plan {'LONG' if d == 1 else 'SHORT'}" if d else "pas de plan fixé"
        out.append(("ok", f"{ic} {m} : analyse de l'indicateur à jour ({n}/11 UT, {plan}, données de {int(age)} s)"))
    ia_st, ia_f = etat.get("ia_dernier_statut"), etat.get("ia_dernier_fournisseur")
    if ia_st == "CONNECTED" and ia_f:
        out.append(("ok", f"🧠 IA : connectée ({ia_f})"))
    elif ia_st:
        out.append(("attention", f"🧠 IA externe indisponible ({ia_st.lower().replace('_', ' ')}) : le moteur interne ALIGN continue, sans avis IA"))
    else:
        out.append(("veille", "🧠 IA : pas encore sollicitée depuis le démarrage"))
    futurs = [e for e in etat.get("cal", {}).get("ev", []) if e["t"] >= now - 15 * 60]
    if futurs:
        out.append(("ok", "📅 News / annonces : calendrier chargé. " + prochaine_news(etat)))
    else:
        out.append(("attention", "📅 News / annonces : aucune annonce dans le calendrier (vide ou non chargé)"))
    sess = prochaine_session(now)
    if sess:
        out.append(("ok", f"⏰ Ouvertures de marché : prochaine = {sess[0]}, {quand_txt(sess[1])}"))
    sv = etat.get("sauve_t")
    if sv and now - sv < 1800:
        out.append(("ok", f"💾 Mémoire : sauvegardée il y a {int((now - sv) // 60)} min"))
    else:
        out.append(("attention", "💾 Mémoire : aucune sauvegarde récente"))
    return out

def texte_statut(etat, derniers, now=None):
    now = time.time() if now is None else now
    ctl = controles_statut(etat, derniers, now)
    ico = {"ok": "✅", "attention": "⚠️", "veille": "💤"}
    pb = [t for e, t in ctl if e == "attention"]
    l = ["🩺 STATUT ALIGN", ("✅ Tout est opérationnel" if not pb else f"⚠️ {len(pb)} point(s) à surveiller")]
    l += [f"{ico[e]} {t}" for e, t in ctl]
    sha = os.environ.get("GITHUB_SHA", "")[:7]
    l.append(f"🔧 Version {sha or 'inconnue'} • en route depuis {int((now - DEMARRE_T) // 60)} min")
    return "\n".join(l)

# ───────── Modèle 3 : ouverture de marché ─────────
def donnees_ouverture(etat, m, r, now):
    """Données RÉELLES d'un marché à l'ouverture d'une session : tendance H4 / H1, résistance et support les plus proches (niveaux 1h / 4h / Daily), prochaine annonce."""
    prix = r["m1"][-1]["c"]
    dirs = r.get("dirs") or [0] * 11
    tend = lambda d: "Haussier" if d == 1 else "Baissier" if d == -1 else "Neutre"
    niv = [v for v, n in (r.get("niveaux") or []) if n in ("1h", "4h", "Daily", "D") and v is not None]
    res = min((v for v in niv if v > prix), default=None)
    sup = max((v for v in niv if v < prix), default=None)
    ev = sorted((e for e in (etat.get("cal", {}) or {}).get("ev", []) if now - 15 * 60 <= e["t"] <= now + 12 * 3600), key=lambda e: e["t"])
    news = f"{ev[0]['titre']} à {heure(ev[0]['t'])}" if ev else "aucune annonce majeure"
    return dict(m=m, h4=tend(dirs[9] if len(dirs) > 9 else 0), h1=tend(dirs[7] if len(dirs) > 7 else 0), res=res, sup=sup, news=news)

def texte_ouverture(nom, heure_txt, minutes, dn, vip=True, compression=False):
    """Modèle 3 — « 🔔 OUVERTURE MARCHÉ : NOM », heure, tendance H4 / H1, niveaux clés (VIP), news. Une information par ligne."""
    l = [f"🔔 OUVERTURE MARCHÉ : {str(nom).upper()}", "", f"{ICONE.get(dn['m'], '')} {dn['m']}",
         f"⏰ Ouverture : {heure_txt} (dans {minutes} min)", f"📈 Tendance H4 : {dn['h4']}", f"📈 Tendance H1 : {dn['h1']}"]
    if vip:
        l += ["🔑 Niveaux clés :", f"· Résistance : {px(dn['res']) if dn['res'] is not None else '—'}", f"· Support : {px(dn['sup']) if dn['sup'] is not None else '—'}"]
    else:
        l.append("🔒 Niveaux clés : VIP")
    l.append(f"⚠️ News : {dn['news']}")
    if compression:
        l.append("⚡ Compression : explosion possible")
    return "\n".join(l)

def messages_ouverture(etat, ev, derniers, now, vip=True):
    """[(marché, texte)] pour une ouverture de session (préavis 15 min) : un message par marché concerné qui a des données ; [] sinon."""
    concernes = re.findall(r"BTC|GOLD|NASDAQ", ev["mk"][0])
    out = []
    for m in dict.fromkeys(concernes):
        r = (derniers or {}).get(m)
        if r and r.get("m1"):
            out.append((m, texte_ouverture(ev["nom"][0], heure(ev["t"]), int(ev["palier"]), donnees_ouverture(etat, m, r, now), vip, m in (ev.get("marches") or []))))
    return out

def fusion_ouvertures(textes):
    """Plusieurs fiches « 🔔 OUVERTURE MARCHÉ » de la MÊME session → UN seul message : titre, heure et news une seule fois, puis un bloc par marché."""
    if len(textes) <= 1:
        return textes[0] if textes else ""
    lignes = [t.split("\n") for t in textes]
    titre = lignes[0][0]
    commun = lambda pre: [x for x in lignes[0] if x.startswith(pre)] if all(any(y == x for y in l) for l in lignes for x in lignes[0] if x.startswith(pre)) else []
    heure_l, news_l = commun("⏰"), commun("⚠️")
    out = [titre] + heure_l
    for l in lignes:
        corps = [x for x in l[1:] if x.strip() and x not in heure_l and x not in news_l]
        out += ["━━━━━━━━━━━━━━━"] + corps
    out += ["━━━━━━━━━━━━━━━"] + news_l if news_l else []
    return "\n".join(out)

def diffuser_messages(etat, chats, msgs):
    """msgs = [(marché, texte)] routés selon le marché de chacun ; chaque personne reçoit UN seul message par session (ses marchés seulement)."""
    par_cid = {}
    for m, texte in msgs:
        t = Msg(texte); t.marches = frozenset({m})
        for cid in destinataires_message(etat, chats, t):
            par_cid.setdefault(cid, []).append(texte)
    for cid, textes in par_cid.items():
        groupes = {}
        for tx in textes:
            groupes.setdefault(tx.split("\n")[0], []).append(tx)
        for g in groupes.values():
            _envoi_sur(cid, text=fusion_ouvertures(g))

def diffuser_evenements(etat, chats, evts):
    """evts = [(marches, lignes_fr, lignes_en[, (mk_fr, mk_en)])] : marches = {"GOLD"} pour un évènement de marché, {"*"} pour une session (global).
    Chaque évènement est routé selon SON marché ; chaque personne reçoit un seul message regroupé, limité à ses marchés cochés
    (liste de marchés d'une session et ligne « comprimé » réduites à ses marchés ; session sans aucun de ses marchés : non envoyée)."""
    evts = [tuple(e) + (None,) * (4 - len(e)) for e in evts]
    dest_evt = []
    for marches, fr, en, _mk in evts:
        t = Msg("\n".join(fr)); t.marches = frozenset(marches)
        dest_evt.append(set(destinataires_message(etat, chats, t)))
    canal = str(etat.get("canal") or "")
    for cid in sorted(set().union(*dest_evt) if dest_evt else set()):
        choix = etat.get("marches_par_chat", {}).get(str(cid))
        choisis = marches_choisis(etat, cid) if (choix is not None and cid != canal) else None
        anglais = str(cid) in LANG_EN
        blocs = []
        for (marches, fr, en, mk), dests in zip(evts, dest_evt):
            if cid not in dests:
                continue
            lignes = en if anglais else fr
            if choisis:
                lignes = ajuster_squeeze(lignes, choisis)
                if mk:
                    lignes = adapter_marches_session(lignes, mk[1] if anglais else mk[0], choisis, anglais)
            if lignes:
                blocs.append(lignes)
        if blocs:
            _envoi_sur(cid, text="\n".join(regrouper_alertes(blocs)))

def alertes_courtes(etat, chats, derniers, now=None):
    """Appelé à chaque tour : sessions + évènements Pine du moment. Gratuit : préavis 15 min des grandes ouvertures seulement."""
    now = now or time.time()
    evts, libres = [], []
    modele3 = []
    for ev in evenements_sessions(etat, now, derniers):
        if ev["evt"] == "ouvre" and ev["palier"] == 15:
            msgs = messages_ouverture(etat, ev, derniers, now, True)
            if msgs:                                       # Modèle 3 (un message complet par marché) ; sinon repli sur l'ancienne alerte
                modele3 += msgs
                if (ev["code"], ev["evt"]) in SESSIONS_GRATUIT:
                    libres.append(ev)
                continue
        evts.append(({"*"}, texte_session(etat, ev), texte_session(etat, ev, True), ev["mk"]))
        if (ev["code"], ev["evt"]) in SESSIONS_GRATUIT and ev["palier"] == 15:
            libres.append(ev)
    if modele3 and TOKEN:
        diffuser_messages(etat, chats, modele3)
    for m, r in derniers.items():
        if m != "BTC" and not cme_ouvert(int(now)):          # marché fermé : aucune alerte de l'indicateur
            continue
        for ev in sorted(evenements_pine(etat, m, r, etat.get(m, {}), now), key=lambda x: _PINE_PRIO[x["kind"]]):
            if ev["kind"] == "scalp_inv":              # carte complète à part (jamais coupée à 4 lignes par le regroupement)
                if TOKEN:
                    diffuser_alerte(etat, chats, texte_scalp(m, ev["si"], ev["dp"]), texte_scalp(m, ev["si"], ev["dp"], True))
                continue
            evts.append(({m}, texte_pine(etat, ev), texte_pine(etat, ev, True)))
    if evts and TOKEN:
        diffuser_evenements(etat, chats, evts)
    if libres and TOKEN:
        for cid in destinataires_gratuits(etat):
            for ev in libres:
                msgs = messages_ouverture(etat, ev, derniers, now, False) if ev["evt"] == "ouvre" and ev["palier"] == 15 else []
                if msgs:
                    mes = [texte for m, texte in msgs if marche_autorise(etat, cid, m)]
                    if mes:
                        _envoi_sur(cid, text=fusion_ouvertures(mes))
                else:
                    fr, en = texte_session(etat, ev), texte_session(etat, ev, True)
                    _envoi_sur(cid, text="\n".join(regrouper_alertes([en if str(cid) in LANG_EN else fr])))

def alerte_gratuite_preparation(etat, texte, now=None):
    """Gratuit : version réduite d'une alerte de préparation VIP (« JE PRÉPARE UNE POSITION », « PRÉPARE-TOI », « POINT D'ENTRÉE À VENIR ») :
    jamais de sens ni de niveaux, une fois par marché toutes les 30 min, seulement si son bot est sur ON et le marché coché."""
    tete = texte.split("\n")[0].upper()
    if not any(k in tete for k in ("JE PRÉPARE UNE POSITION", "PRÉPARE-TOI", "POINT D'ENTRÉE À VENIR")):
        return
    m = next((x for x in MARCHES if x in tete), None)
    now = now or time.time()
    sens_txt = ("bullish", "haussier") if "LONG" in texte[:300] else ("bearish", "baissier") if "SHORT" in texte[:300] else None
    vus = etat.setdefault("al_mem", {}).setdefault("prep_gratuit", {})
    if not m or now - vus.get(m, 0) < 1800:
        return
    vus[m] = now
    ic = ICONE.get(m, "")
    for cid in destinataires_gratuits(etat):
        if not marche_autorise(etat, cid, m) or not bot_on(etat, cid):
            continue
        v = _tournante(etat, f"g:{cid}", 3)
        fr = (("🔔 {ic} {m} : une position se prépare", "🔒 Niveaux : VIP"), ("👀 {ic} {m} : quelque chose se met en place", "🔒 Détails réservés aux VIP"),
              ("⏳ {ic} {m} : préparation en cours", "🔒 Niveaux : VIP"))[v]
        en = (("🔔 {ic} {m}: a position is getting ready", "🔒 Levels: VIP"), ("👀 {ic} {m}: something is setting up", "🔒 Details are VIP-only"),
              ("⏳ {ic} {m}: setup in progress", "🔒 Levels: VIP"))[v]
        lignes = [l.format(ic=ic, m=m) for l in (en if str(cid) in LANG_EN else fr)]
        if sens_txt:                                    # le biais reste visible dans le gratuit (demande d'Adel), jamais les niveaux
            lignes.insert(1, f"🧭 Bias: {sens_txt[0]}" if str(cid) in LANG_EN else f"🧭 Biais : {sens_txt[1]}")
        _envoi_sur(cid, text="\n".join(lignes))

# ───────── ALIGN LIVE : état PUBLIC (niveau gratuit) pour la page TikTok LIVE ─────────
# Fichier unique sur la branche « live-data » (jamais main : aucun redémarrage du bot). Aucune donnée VIP : ni prix, ni entrée, ni SL, ni TP.
LIVE_DEPOT = os.environ.get("GITHUB_REPOSITORY") or "adelkhatra-bit/trading-auto"
LIVE_BRANCHE, LIVE_FICHIER = "live-data", "live.json"
LIVE_INTERVALLE, LIVE_RAFRAICHIR = 120, 300      # tentative toutes les 2 min ; republication forcée au plus toutes les 5 min

def construire_live(etat, derniers, now=None):
    """Contenu public : marché, biais probable, UT alignées x/11, profil, état, heure. Rien d'autre."""
    now = now or time.time()
    marches = []
    for m in MARCHES:
        r = derniers.get(m)
        if not r:
            continue
        cle = etat.get(m, {})
        statut, _ = etat_marche_hb(m, r, now)
        e = hb_etat_surveille(r)
        etat_l = ("ferme" if statut == "ferme" else "perime" if statut == "perime" else "entree" if cle.get("trade") else
                  "preparation" if (cle.get("ordre") or cle.get("prep") or e["strat"]) else "calme")
        marches.append({"m": m, "etat": etat_l, "biais": {1: "haussier", -1: "baissier", 0: "indecis"}[e["sens"]],
                        "ut": int(e["n"]), "seuil": MIN_ALIGN,
                        "profil": {"SWING": "SWING", "DAY": "INTRADAY", "SCALPING": "SCALP"}.get(e["strat"], "aucun")})
    return {"v": 1, "maj": int(now), "bot": "@" + str(etat.get("bot") or "align_mtf_adel_bot"), "marches": marches}

def _api_github(chemin, methode="GET", corps=None):
    req = urllib.request.Request(f"https://api.github.com/repos/{LIVE_DEPOT}{chemin}",
                                 data=json.dumps(corps).encode() if corps is not None else None, method=methode,
                                 headers={"Authorization": "Bearer " + os.environ.get("GITHUB_TOKEN", ""), "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "align-live", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as rep_:
        return json.loads(rep_.read().decode() or "{}")

def publier_live(etat, derniers, now=None):
    """Publie le JSON public sur la branche live-data (commit léger, 1 fichier). Aucun jeton dans les journaux ni dans le fichier."""
    now = now or time.time()
    if not os.environ.get("GITHUB_TOKEN") or now - etat.get("live_t", 0) < LIVE_INTERVALLE:
        return False
    etat["live_t"] = now                          # même en cas d'erreur : pas de rafale d'appels
    data = construire_live(etat, derniers, now)
    if not data["marches"]:
        return False
    stable = json.dumps(data["marches"], sort_keys=True)
    if stable == etat.get("live_sig") and now - etat.get("live_pub", 0) < LIVE_RAFRAICHIR:
        return False                              # rien n'a changé : pas de commit
    try:
        try:
            sha = _api_github(f"/contents/{LIVE_FICHIER}?ref={LIVE_BRANCHE}").get("sha")
        except urllib.error.HTTPError as ex:
            if ex.code != 404:
                raise
            sha = None
            try:
                _api_github(f"/git/ref/heads/{LIVE_BRANCHE}")
            except urllib.error.HTTPError as ex2:
                if ex2.code != 404:
                    raise
                base = _api_github("/git/ref/heads/main")["object"]["sha"]
                _api_github("/git/refs", "POST", {"ref": f"refs/heads/{LIVE_BRANCHE}", "sha": base})
        corps = {"message": "live: mise à jour", "branch": LIVE_BRANCHE,
                 "content": __import__("base64").b64encode(json.dumps(data, ensure_ascii=False).encode()).decode()}
        if sha:
            corps["sha"] = sha
        _api_github(f"/contents/{LIVE_FICHIER}", "PUT", corps)
        etat["live_sig"], etat["live_pub"] = stable, now
        return True
    except Exception as ex:
        print("live public", type(ex).__name__, getattr(ex, "code", ""))      # jamais le jeton
        etat["live_t"] = now + 180                # erreur : on réessaie dans 5 min
        return False

def notifier_securite_vip(etat):
    """Message « SÉCURITÉ VIP » : une seule fois par utilisateur, avec le bouton « Rejoindre le VIP » (lien d'abonnement payant Stars
    déjà utilisé par le bot, etat['lien'] créé avec createChatSubscriptionInviteLink) et le prix réellement configuré."""
    if not etat.get("lien_primaire_revoque_v1") or not etat.get("lien"):
        return                                    # pas de bouton sans lien payant : on attend qu'il existe
    vus = etat.setdefault("secu_vip_vu", [])
    for p in proprio(etat):
        if str(p) in vus:
            continue
        anglais = str(p) in LANG_EN
        texte = ("🔐 VIP SECURITY\n⛔ The old free link to the VIP channel is revoked\n💳 Only the paid link lets people in\n"
                 f"💎 VIP subscription: {PRIX_STARS} ⭐ / month" if anglais else
                 "🔐 SÉCURITÉ VIP\n⛔ L'ancien lien gratuit de la chaîne VIP est révoqué\n💳 Seul le lien payant permet d'entrer\n"
                 f"💎 Abonnement VIP : {PRIX_STARS} ⭐ / mois")
        kb = json.dumps({"inline_keyboard": [[{"text": "💎 Join VIP" if anglais else "💎 Rejoindre le VIP", "url": etat["lien"]}]]})
        res = _envoi_sur(p, text=texte, reply_markup=kb)
        if isinstance(res, dict) and res.get("ok") is not False:
            vus.append(str(p))

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
    _envoi_sur(cid, text=("👋 Bienvenue sur ALIGN Gratuit 🎁\n"
                          "🟠 BTC • 🥇 GOLD • 💠 NASDAQ\n\n"
                          "🎁 1 POSITION PROPOSÉE CHAQUE JOUR\n"
                          "🙋 Tu choisis de la prendre ou non\n"
                          "🕯 Expliquée en bougies (vue 15 min) + coach jusqu'au TP\n"
                          "📡 Bouton Mes marchés : coche seulement ceux que tu trades\n"
                          "🤖 Bouton Mon bot : ON / OFF quand tu veux\n\n"
                          "🔒 Ensuite : tu sais qu'une position arrive, mais sans le sens ni les niveaux\n"
                          "💎 VIP 49,90 € / mois : toutes les positions + le coach en direct\n"
                          "👉 Bouton ci-dessous : tu paies et tu entres directement dans le canal ALIGN VIP 💎\n\n" + AVERTISSEMENT), **kw)

def masquer(texte):
    """Cache tous les prix (entrée, stop, TP) pour les visiteurs non abonnés."""
    texte = re.sub(r"[+-]\d+,\d+ %", "🔒 %", texte)
    return re.sub(r"(?<!\w)\d{1,3}(?: \d{3})*\.\d+", "🔒🔒🔒", texte).replace("\n\n📍 Si tu prends cette position, active son suivi avec le bouton ci-dessous.", "")

def envoyer_prospects(etat, texte, signal, clavier=None):
    """GRATUIT (visiteurs + propriétaire en vue gratuite) : 1 position proposée par jour si le bot est ON,
    sinon un simple avis masqué quand une position sort. Jamais de news ni d'analyse : c'est le VIP."""
    entree = signal and est_entree(texte)
    jour = datetime.datetime.now(PARIS).strftime("%Y-%m-%d")
    if etat.get("offerte_jour") != jour:           # 1 position GRATUITE par jour : on remet les compteurs à zéro
        etat["bienvenue"] = {c: mk for c, mk in etat.get("bienvenue", {}).items() if etat.get(mk, {}).get("trade")}
        etat["offerte_jour"] = jour
    deja = etat.setdefault("bienvenue", {})
    tete = texte.split("\n")[0]
    m = next((x for x in MARCHES if x in tete), None)
    tr = etat.get(m, {}).get("trade") if m else None
    # GRATUIT = même bot que le VIP, mais 1 seule position par jour et options bridées.
    # Plus de news, de teasers ni d'alertes « ça arrive » : uniquement quand une position sort.
    if not (m and entree):
        return
    vus = etat.setdefault("masque_vu", {})
    ref = f"{m}:{(tr or {}).get('cree') or int(time.time() // 1800)}"
    for cid in destinataires_gratuits(etat):
        if not marche_autorise(etat, cid, m):
            continue
        if bot_on(etat, cid) and cid not in deja:
            deja[cid] = m      # la position du jour est PROPOSÉE : il choisit de la prendre ou non
            txt = ("🎁 TA POSITION GRATUITE DU JOUR\n"
                   "🙋 Tu la prends ? Bouton 📍 ci-dessous (tu n'es pas obligé)\n━━━━━━━━━━━━\n" + texte
                   + "\n━━━━━━━━━━━━\n💎 Toutes les autres + le coach : VIP 49,90 € / mois")
            k = {"reply_markup": json.dumps({"inline_keyboard": [
                [{"text": "📍 Je la prends", "callback_data": f"in:{m}"}],
                [{"text": "⏸ Plus de positions", "callback_data": "botoff:x"}]]})}
        else:
            if vus.get(cid) == ref or (deja.get(cid) == m and tr and isinstance(tr.get("qui", {}).get(cid), dict)):
                continue
            vus[cid] = ref
            txt = (f"🔒 {ICONE.get(m, '')} {m} : une position VIP vient de sortir\n"
                   "🤫 Sens et niveaux : réservés aux VIP\n"
                   + ("🎁 Ta position du jour est déjà utilisée\n" if cid in deja else "⏸ Ton bot est sur OFF\n")
                   + "💎 VIP 49,90 € / mois 👇")
            rang = [[{"text": "💎 Devenir VIP", "url": etat["lien"]}]] if etat.get("lien") else []
            k = {"reply_markup": json.dumps({"inline_keyboard": rang + [[{"text": "🤖 Mon bot", "callback_data": "botmenu:x"}]]})}
        try:
            telegram("sendMessage", chat_id=cid, text=txt, **k)
        except Exception as ex:
            print("prospect", cid, ex)
            if "403" in str(ex) and cid in etat.get("prospects", []):
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

def _vers_ensemble(choix):
    """BTC / GOLD / NASDAQ, liste de marchés, ancien « BOTH » (= BTC + GOLD) ou « ALL » (= tout)."""
    if isinstance(choix, (list, tuple, set, frozenset)):
        return {m for m in choix if m in MARCHES}
    if choix == "BOTH":
        return {"BTC", "GOLD"}
    if choix == "ALL":
        return set(MARCHES)
    return {choix} if choix in MARCHES else set()

def selectionner_marches_suivi(etat, cid, choix):
    """Enregistre le choix explicite et retire uniquement les suivis en attente des autres marchés."""
    cid = str(cid)
    autorises = _vers_ensemble(choix)
    if not autorises:
        raise ValueError("Marché de suivi invalide")
    etat.setdefault("marches_par_chat", {})[cid] = choix if isinstance(choix, str) else sorted(autorises)
    for marche in MARCHES:
        if marche in autorises:
            continue
        attente = etat.setdefault("auto", {}).setdefault(marche, [])
        etat["auto"][marche] = [x for x in attente if str(x) != cid]
        veilles = etat.setdefault("veille_cloture", {}).setdefault(marche, {})
        veilles.pop(cid, None)

def valider_et_suivre_marches(etat, cid, user_id, message_id=None):
    """« ✅ Valider et suivre » : enregistre les marchés cochés puis lance leur suivi.
    Même règle d'accès que le bouton de suivi existant (followmarket) : le gratuit n'a qu'une position."""
    cid = str(cid)
    anglais = cid in LANG_EN
    if not (autorise(etat, cid, user_id) or cid not in etat.get("bienvenue", {})):
        _envoi_sur(cid, text=("🔒 VIP only\n🎁 Your free position of the day is already used\n💎 VIP 49,90 € / month 👇" if anglais
                              else "🔒 Réservé aux VIP\n🎁 Ta position gratuite du jour est déjà utilisée\n💎 VIP 49,90 € / mois 👇"),
                   **({"reply_markup": bouton_payer(etat)} if etat.get("lien") else {}))
        return False
    choisis = [m for m in MARCHES if m in marches_choisis(etat, cid)]
    selectionner_marches_suivi(etat, cid, choisis)
    for m in choisis:
        inscrire_auto(etat, cid, m, notifier=False)
    noms = " + ".join(m for m in choisis)
    if message_id:                      # ferme le menu : plus de cases ni de bouton à l'écran
        try:
            telegram("deleteMessage", chat_id=cid, message_id=message_id)
        except Exception:
            try:
                telegram("editMessageReplyMarkup", chat_id=cid, message_id=message_id, reply_markup=json.dumps({"inline_keyboard": []}))
            except Exception as ex:
                print("fermeture menu marchés", ex)
    _envoi_sur(cid, text=(f"✅ Tracking on: {noms}" if anglais else f"✅ Suivi activé : {noms}") + "\n\n" + texte_suivi(etat, cid))
    return True

def basculer_marche(etat, cid, marche):
    """Coche / décoche un marché (au moins 1 reste coché)."""
    actuels = set(marches_choisis(etat, cid))
    actuels = actuels - {marche} if marche in actuels and len(actuels) > 1 else actuels | {marche}
    selectionner_marches_suivi(etat, cid, sorted(actuels))

def marches_choisis(etat, cid):
    """Marchés cochés par la personne ; sans choix : tous les marchés."""
    brut = etat.setdefault("marches_par_chat", {}).get(str(cid))
    return _vers_ensemble(brut) or set(MARCHES)

def marche_selection(etat, cid):
    """Compatibilité : « BTC », « GOLD », « BOTH » (BTC + GOLD) ou la liste des marchés cochés."""
    brut = etat.setdefault("marches_par_chat", {}).get(str(cid), "BOTH")
    if isinstance(brut, str) and brut in ("BTC", "GOLD", "NASDAQ", "BOTH"):
        return brut
    ens = _vers_ensemble(brut)
    return "BOTH" if ens == {"BTC", "GOLD"} else (next(iter(ens)) if len(ens) == 1 else sorted(ens) or "BOTH")

def marche_autorise(etat, cid, marche):
    brut = etat.get("marches_par_chat", {}).get(str(cid))
    if brut is None:
        return True                     # pas encore de choix : tous les marchés
    return marche in _vers_ensemble(brut)

NOMS_MARCHES = {"BTC": "🟠 BTC", "GOLD": "🥇 GOLD", "NASDAQ": "💠 NASDAQ"}

def _ou_en_est(etat, m, anglais=False):
    """Une ligne « où ça en est » à partir des vraies données du dernier cycle (jamais inventée)."""
    try:
        tr = (etat.get(m) or {}).get("trade")
        r = (DERNIERS or {}).get(m) or {}
        prix = r.get("prix") or (r.get("m1") or [{}])[-1].get("c")
        if isinstance(tr, dict) and tr.get("sl") is not None:
            base = (f"price {px(prix)} • " if anglais else f"prix {px(prix)} • ") if prix else ""
            return base + f"SL {px(tr['sl'])} • TP1 {px(tr['tp1'])}"
        if not r:
            return ""
        h = hb_etat_surveille(r)
        if not h["d"]:
            return "no clear direction yet" if anglais else "pas encore de sens clair"
        profil = f" • {h['strat']}" if h["strat"] else ""
        minutes = {"SWING": 60, "DAY": 5, "SCALPING": 1}.get(h["strat"], 15)     # unité de validation (comme l'indicateur)
        reste = minutes * 60 - int(time.time()) % (minutes * 60)
        unite = {60: "1h", 5: "5 min", 1: "1 min"}.get(minutes, "15 min")
        quand = (f" • next {unite} close in {reste // 60:02d}:{reste % 60:02d}" if anglais
                 else f" • prochaine clôture {unite} dans {reste // 60:02d}:{reste % 60:02d}")
        return (f"{h['n']}/11 timeframes aligned{profil}" if anglais else f"{h['n']}/11 UT alignées{profil}") + quand
    except Exception as ex:
        print("où en est", m, ex)
        return ""

def texte_suivi(etat, cid):
    """Bloc « 📡 JE SURVEILLE POUR TOI » : marché par marché, ce que le bot suit pour cette personne.
    Une seule source de vérité (marches_choisis / en_position / etat['auto']) réutilisée partout."""
    cid = str(cid)
    anglais = cid in LANG_EN
    dedans = set(en_position(etat, cid))
    choisis = marches_choisis(etat, cid)
    lignes = ["📡 I'M WATCHING FOR YOU" if anglais else "📡 JE SURVEILLE POUR TOI", "━━━━━━━━━━━━━━━"]
    for m in MARCHES:
        if m in dedans:
            etat_m = "🎯 in a position (followed to TP / SL)" if anglais else "🎯 en position (suivi jusqu'au TP / SL)"
        elif m in choisis:
            etat_m = "⏳ waiting for a confirmed entry" if anglais else "⏳ j'attends une entrée confirmée"
        else:
            etat_m = "⬜ not followed" if anglais else "⬜ non suivi"
        lignes.append(f"{NOMS_MARCHES[m]} : {etat_m}")
        if m in dedans or m in choisis:
            detail = _ou_en_est(etat, m, anglais)
            if detail:
                lignes.append(f"   ↳ {detail}")
    if not bot_on(etat, cid):
        lignes.append("⏸ Your bot is paused: 🤖 My bot to restart" if anglais
                      else "⏸ Ton bot est en pause : 🤖 Mon bot pour le relancer")
    else:
        lignes.append("🔔 I'll alert you as soon as an entry is confirmed" if anglais
                      else "🔔 Je te préviens dès qu'une entrée est confirmée")
    return "\n".join(lignes)

def menu_marches(etat, cid, message_id=None):
    """Cases à cocher : chaque personne choisit ses marchés (ex. GOLD + NASDAQ, rien du BTC).
    Avec message_id, le même menu est mis à jour sur place (pas de nouveau message à chaque case)."""
    choisis = marches_choisis(etat, cid)
    anglais = str(cid) in LANG_EN
    tout = set(MARCHES) <= set(choisis)
    lignes = [[{"text": ("✅ " if m in choisis else "⬜ ") + NOMS_MARCHES[m], "callback_data": f"markets:{m}"}] for m in MARCHES]
    lignes.append([{"text": ("✅ " if tout else "⬜ ") + ("Everything" if anglais else "Tout recevoir"), "callback_data": "markets:ALL"}])
    lignes.append([{"text": ("✅ Confirm & follow" if anglais else "✅ Valider et suivre"), "callback_data": "markets:OK"}])
    coches = " + ".join(NOMS_MARCHES[m] for m in MARCHES if m in choisis)
    texte = ("📡 MY MARKETS\n━━━━━━━━━━━━━━━\n👆 Tap to tick / untick\n"
             f"☑️ Ticked now: {coches}\n🔔 You only get alerts for ticked markets\n"
             "📍 Prices can differ by a few points from your broker: follow the candles (wicks)"
             if anglais else
             "📡 MES MARCHÉS\n━━━━━━━━━━━━━━━\n👆 Touche pour cocher / décocher\n"
             f"☑️ Cochés en ce moment : {coches}\n🔔 Tu reçois uniquement les marchés cochés\n"
             "📍 Le prix peut différer de quelques points selon ton broker : suis les bougies (mèches)")
    clavier = json.dumps({"inline_keyboard": lignes})
    if message_id:
        try:
            return telegram("editMessageText", chat_id=cid, message_id=message_id, text=texte, reply_markup=clavier)
        except Exception as ex:
            if "not modified" in str(ex).lower():
                return None
            print("menu marchés (édition)", ex)
    return _envoi_sur(cid, text=texte, reply_markup=clavier)

def marches_du_message(texte):
    """Marchés cités dans l'en-tête d'une notification."""
    tete = " ".join(str(texte or "").splitlines()[:3]).upper()
    ens = set()
    if re.search(r"\bBTC\b|BITCOIN", tete):
        ens.add("BTC")
    if re.search(r"\bGOLD\b|XAUUSD", tete):
        ens.add("GOLD")
    if re.search(r"\bNASDAQ\b|NAS100|\bNQ\b", tete):
        ens.add("NASDAQ")
    return ens

class Msg(str):
    """Texte de message tagué avec le(s) marché(s) CONNUS à la création : le routage ne devine plus le marché en lisant le texte."""
    marches = frozenset()

def taguer(x, marche):
    """Tague un message (ou un couple message + clavier) avec son marché."""
    def un(t):
        m = Msg(t); m.marches = frozenset(getattr(t, "marches", ())) | {marche}
        return m
    return (un(x[0]),) + tuple(x[1:]) if isinstance(x, tuple) else un(x)

def marches_message(texte):
    """Marchés d'un message : le tag posé à la création d'abord, sinon l'en-tête."""
    tag = set(getattr(texte, "marches", ()) or ())
    return (tag - {"*"}) if tag else marches_du_message(texte)           # tag {"*"} = message global (sessions) : aucun marché imposé

def filtrer_texte_par_marches(texte, choisis):
    """Version du message pour UNE personne : None si le message ne concerne aucun de ses marchés ; sinon le texte sans les lignes qui ne parlent
    que de marchés qu'elle n'a pas cochés (ex. « réaction à la news » BTC + GOLD + NASDAQ → seulement ses marchés). Sans choix : tout."""
    if not choisis or set(choisis) >= set(MARCHES):
        return texte
    choisis = set(choisis)
    ens = marches_message(texte)
    if ens and not (ens & choisis):
        return None
    gardees = []
    for l in str(texte).split("\n"):
        lm = marches_du_message(l)
        if lm and not (lm & choisis):
            continue
        gardees.append(l)
    return "\n".join(gardees)

def ajuster_squeeze(lignes, choisis):
    """Ligne « ⚡ BTC, GOLD comprimé : explosion possible » : ne garde que les marchés cochés (ligne supprimée s'il n'en reste aucun)."""
    out = []
    for l in lignes:
        if l.startswith("⚡ ") and ("comprimé : explosion possible" in l or "squeezed: breakout possible" in l):
            tete = l[2:].split(" comprimé")[0].split(" squeezed")[0]
            noms = [x for x in tete.split(", ") if not choisis or x in choisis]
            if not noms:
                continue
            l = "⚡ " + ", ".join(noms) + l[2 + len(tete):]
        out.append(l)
    return out

def marche_du_message(texte):
    """Compatibilité : un marché, « BOTH » si plusieurs, None si aucun."""
    ens = marches_du_message(texte)
    return None if not ens else (next(iter(ens)) if len(ens) == 1 else "BOTH")

def destinataires_message(etat, chats, texte):
    # Le flux complet (news, analyses, toutes les positions) part dans la chaîne VIP (commune : tous les marchés).
    # Chaque personne ne reçoit EN PRIVÉ que les marchés qu'elle a cochés (filtrage ligne par ligne au moment de l'envoi, voir filtrer_texte_par_marches).
    ens = marches_message(texte)
    if etat.get("canal"):
        prives = [str(c) for c in chats if not vue_gratuite(etat, c) and str(c) != str(etat["canal"])
                  and etat.get("marches_par_chat", {}).get(str(c)) is not None and ens
                  and ens & marches_choisis(etat, c)]
        return sorted(set([str(etat["canal"])] + prives))
    cibles = [str(c) for c in chats if not ens or bool(ens & marches_choisis(etat, c))]
    return sorted(set(cibles))

def destinataires(etat, chats):
    """Téléphones qui reçoivent les signaux + la chaîne VIP."""
    return list(chats) + ([etat["canal"]] if etat.get("canal") else [])

def boutons(m):
    """Sur une alerte d'entrée, le seul choix proposé est de suivre cette position."""
    return json.dumps({"inline_keyboard": [[
        {"text": "📍 Suivre cette position", "callback_data": f"in:{m}"}
    ]]})

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
                derniere_maj = cle.setdefault("jauge_t", {}).get(cid, 0)
                if cle.setdefault("jauge_txt", {}).get(cid) != txt and time.time() - derniere_maj >= JAUGE_REFRESH_SEC:
                    telegram("editMessageText", chat_id=cid, message_id=mid, text=txt)
                    cle["jauge_t"][cid] = time.time()
                else:
                    continue
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
            # Toutes les annonces USD du jour (même faibles) : affichées dans l'analyse pour montrer le sérieux
            cache["jour"] = [dict(titre=x["title"], t=int(datetime.datetime.fromisoformat(x["date"]).timestamp()),
                                  impact=x.get("impact", ""), prev=x.get("forecast", ""), avant=x.get("previous", ""))
                             for x in brut if x.get("country") == "USD" and x.get("impact") in ("High", "Medium", "Low")]
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
                    cle_cache=f"newsreaction{e['t']}{e['titre']}", duree=3600, premium=True, recherche=True)
                message = f"📰 RÉACTION À LA NEWS — {e['titre']}\n" + "\n".join(lr)
                message += "\n⏳ J'attends la clôture de la bougie 15 min avant de reprendre"
                if avis_apres:
                    message += "\n\n🧠 L'analyse de l'IA ALIGN après l'annonce\n" + avis_apres + ligne_sources(etat, f"newsreaction{e['t']}{e['titre']}")
                out.append(message)
        if 6 * 60 < reste <= 15 * 60 and f"ev{e['t']}{e['titre']}" not in vus:        # préavis 15 min (VIP : le gratuit ne reçoit aucune news)
            vus.append(f"ev{e['t']}{e['titre']}")
            cle_news = f"news{e['t']}{e['titre']}"
            avis = ia(etat, "Explique en 2 lignes très simples ce que cette annonce peut faire au Gold et au BTC (sans donner de sens à trader, juste le risque).",
                      {"annonce": e["titre"], "prévu": e.get("prev"), "avant": e.get("avant")}, cle_cache=cle_news, duree=3600, premium=True, recherche=True)
            out.append(f"⚠️⚠️ NEWS USA dans {round(reste / 60)} min ({heure(e['t'])})\n📰 {e['titre']}\n\n"
                       f"🟥 N'ouvre AUCUN trade\n🛡 Déjà en position ? Vérifie que ton STOP est bien placé\n"
                       f"💥 Le prix peut bouger très fort dans les 2 sens\n⏳ On reprend à {fin}" + (f"\n\n🧠 L'avis de l'IA ALIGN\n{avis}{ligne_sources(etat, cle_news)}" if avis else ""))
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
    # Ouvertures / fermetures de marché : voir alertes_courtes() (préavis 15 et 5 min, FR/EN, regroupées)
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

IMPACT_IC = {"High": "🔴", "Medium": "🟠", "Low": "🟡"}

def news_du_jour(etat, n=3, maintenant=None):
    """Les annonces et discours USA d'AUJOURD'HUI (heure de Paris), déjà sortis ou à venir, même les petites."""
    now = maintenant or time.time()
    jour = datetime.datetime.fromtimestamp(now, PARIS).date()
    cal = etat.get("cal", {})
    evs = sorted((e for e in (cal.get("jour") or cal.get("ev") or [])
                  if datetime.datetime.fromtimestamp(e["t"], PARIS).date() == jour), key=lambda e: e["t"])
    if not evs:
        return []
    passes = [e for e in evs if e["t"] <= now][-n:]
    avenir = [e for e in evs if e["t"] > now][:max(1, n - len(passes))]
    lignes = ["📰 NEWS USA DU JOUR"]
    for e in passes + avenir:
        ic = "🎤" if "speak" in e["titre"].lower() else IMPACT_IC.get(e.get("impact"), "📰")
        etat_ = "sortie ✅" if e["t"] <= now else dans_txt(e["t"] - now)
        prevu = f" (prévu {e['prev']})" if e.get("prev") else ""
        lignes.append(f"{ic} {heure(e['t'])} {court(e['titre'], 40)}{prevu} — {etat_}")
    return lignes

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
            + ("📅 Position de LONGUE DURÉE : elle peut durer plus d'une journée, garde ton SL en place la nuit\n" if long_ else ""))

def resume_ordre(tr):
    """Une ligne, tout en haut du message d'entrée : sens, entrée, SL, TP1, TP2 (l'essentiel avant le détail)."""
    vue_ = f" • vue {tr['sl_ut']}" if tr.get("sl_ut") else ""
    l = f"{SENS[tr['d']]}{vue_} • Entrée {px(tr['e'])} • SL {px(tr['sl'])} (mèche) • TP1 {px(tr['tp1'])}" if tr.get("sl_ut") == "5 min" \
        else f"{SENS[tr['d']]}{vue_} • Entrée {px(tr['e'])} • SL {px(tr['sl'])} • TP1 {px(tr['tp1'])}"
    return l + (f" • TP2 {px(tr['tp2'])}" if tr.get("tp2") else "")

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
    niv_plan = [(f"🛑 Stop Loss : {px(tr['sl'])}", tr["sl"]), (f"🟨 Entrée : {px(tr['e'])}", tr["e"]),
                (f"💰 TP1 : {px(tr['tp1'])}", tr["tp1"]), (f"🏁 TP2 : {px(tr['tp2'])}", tr["tp2"])]
    resume = (f"📌 PLAN D'EXÉCUTION — {'🟩 LONG' if d == 1 else '🟥 SHORT'}\n"
              + "".join(l + "\n" for l, _ in sorted(niv_plan, key=lambda z: -z[1]))   # ordre du graphique, du plus haut au plus bas
              + f"⚖️ Ratio gain/risque TP1 : 1:{tr['rr']:.1f}\n"
              + (f"🏷 Type : {tr['strat']} — {DUREE_STRATEGIE[tr['strat']]}\n🧭 {CALE_STRATEGIE[tr['strat']]}\n" if tr.get("strat") in DUREE_STRATEGIE else ""))
    decision = (f"\n━━━━━━━━━━━━\n📍 RÉCAPITULATIF — {m}\n"
                f"{'🟩 LONG ⬆️' if d == 1 else '🟥 SHORT ⬇️'}\n"
                f"Entrée {px(tr['e'])} • SL {px(tr['sl'])}\n"
                f"TP1 {px(tr['tp1'])} • TP2 {px(tr['tp2'])}\n"
                "⛔ Ne pas anticiper la clôture de confirmation. Le SL reste obligatoire.\n")
    if tr.get("retour"):
        tete = f"✅ RETOURNEMENT CONFIRMÉ : {'LONG' if d == 1 else 'SHORT'}\n" + tete
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

def zone_rentable(d, za, zb, sl, tp1):
    """Partie de la zone d'entrée où le gain vers le TP1 vaut au moins GAIN_MIN x le risque jusqu'au SL (plan de l'indicateur).
    Ex. réel GOLD 12/11 : zone 3897 → 3961, SL 3976, TP1 3887 → entrer à 3897 = 79 pts de risque pour 10 de gain : zone ramenée à 3940 → 3961."""
    if d not in (1, -1) or sl is None or tp1 is None:
        return za, zb
    seuil = (tp1 + GAIN_MIN * sl) / (1 + GAIN_MIN)          # point d'entrée où gain = GAIN_MIN x risque
    if d == -1:
        za = max(za, seuil)
    else:
        zb = min(zb, seuil)
    return (za, zb) if za <= zb else (None, None)

def tp2_affichable(d, tp1, tp2):
    """Vrai si le TP2 est AU-DELÀ du TP1. La projection « 3,5 x le risque » du Pine peut tomber entre l'entrée et le TP1 (cas réel GOLD 12/11 :
    TP1 3888,99, TP2 3910,44 en SHORT) : on ne l'affiche pas plutôt que d'afficher un objectif incohérent. Le graphique n'est pas modifié."""
    return tp2 is not None and tp1 is not None and d in (1, -1) and d * (tp2 - tp1) > 0

def trait_indicateur(r, d):
    """Zone + trait « Clôture {UT} sous/au-dessus de ce trait » tels que l'indicateur v24.3 les dessine sur la vue de validation (FVG + mèche).
    None si l'indicateur garde son plan d'origine (on utilise alors zone_pine, comme lui)."""
    try:
        pe = pine_entree(r, d) if d in (1, -1) and r.get("b15") and "planH" in r else None
    except Exception:
        return None
    return dict(za=min(pe["za"], pe["zb"]), zb=max(pe["za"], pe["zb"]), zmil=pe["zmil"]) if pe and pe.get("fvg_ut") else None

SCALP_INV_MIN_VOY = 3       # ↩ 3/5 petites UT (1 à 15 min) contre le plan = le repli se prépare

def scalp_inverse(r, d):
    """↩ SCALP INVERSE (identique à l'indicateur sur la vue 5 min) : quand ≥ 3/5 petites UT tournent contre le plan, petit trade dans l'autre sens
    jusqu'à l'ENTRÉE du plan principal. LONG (plan SHORT) : entrée = haut de la FVG verte la plus proche, SL sous la mèche du dernier creux
    (≥ 1 ATR), TP = entrée du SHORT principal. SHORT (plan LONG) : l'inverse. None si non applicable ou si le gain < 1,2 x le risque."""
    dirs = r.get("dirs") or []
    if d not in (1, -1) or len(dirs) < 5 or sum(1 for k in range(5) if dirs[k] == -d) < SCALP_INV_MIN_VOY:
        return None
    st = (r.get("struct_ut") or {}).get("5")
    pl = (r.get("plan_fige") if r.get("plan_fige") and d == r.get("dirPlan") else (r.get("planH") if d == 1 else r.get("planB"))) or None
    if not st or not pl:
        return None
    principal = plan_fvg(d, st, pl["e"], pl["sl"], pl["tp1"], pl["tp2"], "5 min") or pl
    cible = principal["e"]
    rTop, rBot, gTop, gBot, swH, swL, aS, cl = st[:8]
    if not aS:
        return None
    m_ = max(SL_FVG_MARGE * aS, 0.03)
    di = -d
    if di == 1:
        e = gTop if gTop is not None and gTop <= cl + 0.5 * aS else cl
        s_ = min(min(swL, gBot if gBot is not None else swL) - m_, e - SL_FVG_MIN * aS)
    else:
        e = rBot if rBot is not None and rBot >= cl - 0.5 * aS else cl
        s_ = max(max(swH, rTop if rTop is not None else swH) + m_, e + SL_FVG_MIN * aS)
    risque = abs(e - s_)
    if di * (cible - e) < 1.2 * risque or di * (e - s_) <= 0:
        return None
    return dict(d=di, e=e, sl=s_, tp=cible, rr=abs(cible - e) / max(risque, 1e-9), voy=sum(1 for k in range(5) if dirs[k] == -d))

def texte_scalp(m, si, dp, anglais=False):
    """Carte ↩ SCALP INVERSE : même présentation que la carte d'entrée (sens en couleur en premier, niveaux dans l'ordre du graphique)."""
    d = si["d"]
    sens, sensp = ("LONG" if d == 1 else "SHORT"), ("SHORT" if dp == -1 else "LONG")
    vue = "5 min chart" if anglais else "vue 5 min"
    niv = [(f"🛑 SL : {px(si['sl'])}", si["sl"]), (f"🎯 {'Entry' if anglais else 'Entrée'} : {px(si['e'])} ({vue})", si["e"]),
           (f"💰 TP : {px(si['tp'])} (= {sensp} entry)" if anglais else f"💰 TP : {px(si['tp'])} (= entrée du {sensp})", si["tp"])]
    l = [f"↩ {'🟢' if d == 1 else '🔴'} {m} - SCALP {sens}", ""] + [x for x, _ in sorted(niv, key=lambda z: -z[1])]
    l.append(f"⚖️ R:R : 1:{si['rr']:.1f}".replace(".", ","))
    l += ["", (f"⚠️ {si['voy']}/5 small timeframes turned: against the trend, small size" if anglais else
               f"⚠️ {si['voy']}/5 petites UT retournées : contre la tendance, petite position"),
          (f"🧭 At TP we go back {sensp} (main plan)" if anglais else f"🧭 Au TP on reprend le {sensp} (plan principal)")]
    return l

def lecture_tp1(r, d):
    """Au TP1 : le marché continue vers le TP2 ou peut revenir vers l'entrée ? Lecture des vraies unités (1 → 15 min),
    du RSI 5 min / 15 min / 1 h et des compressions. Même logique pour BTC, Gold et NASDAQ (unités relatives, pas de prix fixes)."""
    dirs = list(r.get("dirs") or [])[:5]
    rsis = list(r.get("rsis") or [])
    sqzs = list(r.get("sqzs") or [])[:5]
    avec = sum(1 for x in dirs if x == d)
    contre = sum(1 for x in dirs if x == -d)
    noms = {2: "5 min", 4: "15 min", 7: "1 h"}
    epuise = [(noms[i], rsis[i]) for i in (2, 4, 7) if i < len(rsis) and rsis[i] is not None and
              ((d == 1 and rsis[i] >= 70) or (d == -1 and rsis[i] <= 30))]
    compr = sum(1 for q in sqzs if q == 1)
    au_dela = "AU-DESSUS" if d == 1 else "EN DESSOUS"
    if contre >= 3 or (epuise and contre >= 2):
        lignes = ["⚠️ RISQUE DE RETOUR VERS L'ENTRÉE", f"↩ {contre}/5 petites unités repartent contre la position"]
        lignes += [f"🧯 RSI {u} {v:.0f} : le marché s'essouffle" for u, v in epuise[:2]]
        lignes += ["✂️ Encaisse une grosse partie maintenant", "🛡 SL à BE : plus aucune perte possible"]
    elif avec >= 3 and not epuise:
        lignes = ["🚀 ÇA PEUT CONTINUER VERS LE TP2", f"✅ {avec}/5 petites unités dans le sens de la position",
                  f"🕯 Bougie 15 min qui CLÔTURE {au_dela} du TP1 = cap sur le TP2"]
        if compr:
            lignes.append(f"⚡ {compr} unité{'s' if compr > 1 else ''} en compression : ça peut accélérer")
    else:
        lignes = ["🟨 LE MARCHÉ HÉSITE AU TP1", f"🕯 Clôture 15 min {au_dela} du TP1 = ça continue vers le TP2",
                  "↩ Mèche qui touche puis revient = on sécurise (SL à BE)"]
        lignes += [f"🧯 RSI {u} {v:.0f} : essoufflé" for u, v in epuise[:1]]
    return lignes


def coach_fvg(r, d, prix, attente=True):
    """Lignes « coach » d'une entrée sur FVG (mêmes niveaux que l'indicateur sur la vue de validation) : zone, alignement 5 min + 15 min,
    FVG qui bloque, SL protégé, manipulation (mèche qui dépasse puis revient), quand entrer. [] si l'indicateur garde son plan d'origine."""
    try:
        pe = pine_entree(r, d) if d in (1, -1) and r.get("b15") and "planH" in r else None
    except Exception:
        pe = None
    if not pe or not pe.get("fvg_ut"):
        return []
    ut, za, zb = pe["sl_ut"], min(pe["za"], pe["zb"]), max(pe["za"], pe["zb"])
    dirs = r.get("dirs") or []
    l = []
    if za <= prix <= zb:
        l.append(f"📍 Prix DANS la zone d'entrée (vue {ut})")
    al = [n for n, k in (("5 min", 2), ("15 min", 4)) if len(dirs) > k and dirs[k] == d]
    l.append("✅ 5 min + 15 min alignés" if len(al) == 2 else f"⏳ Alignement : {' + '.join(al) if al else 'ni 5 min ni 15 min'} pour l'instant")
    l.append(f"🧱 {'Order block + ' if 'Order block' in str(pe.get('src')) else ''}FVG {'rouge' if d == -1 else 'verte'} {ut} ({px(pe['e'])}) : elle bloque la {'hausse' if d == -1 else 'baisse'}")
    l.append(f"🛡️ SL {px(pe['sl'])} protégé derrière {'l’order block, ' if 'Order block' in str(pe.get('src')) else ''}la FVG et la mèche")
    bars = (r.get(UT_FVG_BARS.get(UT_FVG.get(r.get("strat") or "", "5"), "b5")) or [])[-4:]
    if any((x["h"] > pe["zmil"] and x["c"] < pe["zmil"]) if d == -1 else (x["l"] < pe["zmil"] and x["c"] > pe["zmil"]) for x in bars):
        l.append("🎣 Mèche qui dépasse puis revient = manipulation (chasse aux stops), c'est normal")
    if attente:
        l.append(f"⏳ Patiente : j'entre quand une bougie {ut} clôture {'sous' if d == -1 else 'au-dessus de'} {px(pe['zmil'])}")
    l.append("🧘 Ça peut piquer un peu, t'inquiète pas tant que le SL tient")
    return l

def pine_entree(r, d):
    """Ordre Telegram = niveaux du graphique : plan figé de l'indicateur Pine v24 (sens du plan) ou plan instantané de l'autre sens."""
    if d not in (1, -1) or not r.get("b15") or "planH" not in r:
        return None
    if r.get("plan_fige") and d == r.get("dirPlan"):
        pl = r["plan_fige"]
    else:
        pl = r["planH"] if d == 1 else r["planB"]
    z = zone_pine(r["b15"], d, pl["e"], pl["sl"])
    if not z:
        return None
    nom = lambda n: (("résistance " if d == 1 else "support ") + n) if n in ("15m", "1h", "4h", "Daily") else n
    za, zb = zone_rentable(d, z["za"], z["zb"], pl["sl"], pl["tp1"])
    if za is None:
        za = zb = pl["e"]                                 # aucune partie rentable de la zone : seul le point d'entrée du plan
    # TP2 = valeur du graphique (parité TradingView) ; s'il tombe avant le TP1 (projection du Pine), il n'est pas affiché : voir tp2_affichable.
    out = dict(d=d, e=pl["e"], sl=pl["sl"], tp1=pl["tp1"], n1=nom(pl["n1"]), tp2=pl["tp2"], n2=nom(pl["n2"]), rr=pl["rr"],
                src="Fibonacci 50 → 78,6 % (indicateur ALIGN)", za=za, zb=zb, f50=z["f50"], f618=z["f618"], f786=z["f786"],
                zmil=(za + zb) / 2, sl_h=bougie_protegee(r["b15"][-3:], d, pl["sl"]), sl_ut="15 min")
    # v24.3 : mêmes niveaux que l'indicateur sur l'unité de référence (FVG + mèche). Sinon : plan d'origine, comme le Pine.
    ut = UT_FVG.get(r.get("strat") or "", "5")
    vue = PLAN_VUE.get(r.get("strat") or "", "5 min")
    fv = plan_fvg(d, (r.get("struct_ut") or {}).get(ut), pl["e"], pl["sl"], pl["tp1"], pl["tp2"], vue)
    if fv:
        bars_ut = [x for x in (r.get(UT_FVG_BARS[ut]) or [])][-3:]
        out.update(fv, src=fv["src"] + " (indicateur ALIGN)", rr=abs(fv["tp1"] - fv["e"]) / max(abs(fv["e"] - fv["sl"]), 1e-9),
                   zmil=(fv["za"] + fv["zb"]) / 2, sl_ut=vue, fvg_ut=True,
                   sl_h=bougie_protegee(bars_ut, d, fv["sl"]) if bars_ut else out["sl_h"])
    return out

def point_entree(r, d, p):
    """PLAN UNIQUE : l'ordre = FVG / order block de la vue du plan (5 min), comme l'indicateur. Sans ce setup : pas d'ordre (None)."""
    pe = pine_entree(r, d)
    if pe:
        return pe if pe.get("fvg_ut") else None
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
    # Stop structurel M15 commun à toutes les entrées sur repli.
    sl = stop_structure_15m(r, d, e)
    if sl is None:
        return None
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
    # Le stop structurel n'est jamais rapproché artificiellement de la zone.
    risque = max(abs(e - sl), 1e-9)
    return dict(d=d, e=e, sl=sl, tp1=t1[0], n1=nom(t1), tp2=t2[0], n2=nom(t2), rr=abs(t1[0] - e) / risque, src=src,
                za=za, zb=zb, f50=z50, f618=z618, f786=z786, sl_h=bougie_protegee(r["b15"][-3:], d, sl), sl_ut="15 min")

def retenir_prenom(etat, cid, frm):
    """Le coach parle à la personne par son prénom Telegram (comme un humain)."""
    p = ((frm or {}).get("first_name") or "").strip().split(" ")[0][:20]
    if p and cid:
        etat.setdefault("prenoms", {})[str(cid)] = p

def humaniser(etat, cid, texte):
    """« 🔒 METS-TOI À BE — BTC » → « 🔒 Adel, METS-TOI À BE — BTC » + une phrase humaine courte à la fin."""
    p = etat.get("prenoms", {}).get(str(cid))
    if not p or not isinstance(texte, str) or not texte:
        return texte
    tete, _, reste = texte.partition("\n")
    m_ = re.match(r"^([^\w]*)(.*)$", tete)
    tete = f"{m_.group(1)}{p}, {m_.group(2)}" if m_ and m_.group(2) else f"{p}, {tete}"
    haut = texte.upper()
    fin = ("😌 Tu es protégé maintenant, profite" if " BE" in haut or "BREAK" in haut else
           "💪 Bien joué, on garde la tête froide" if "TP" in haut and ("TOUCH" in haut or "ATTEINT" in haut) else
           "🤝 Ça fait partie du jeu, on repart ensemble" if "STOP" in haut or "SL TOUCH" in haut else
           "🤝 Je reste avec toi jusqu'au bout")
    return tete + ("\n" + reste if reste else "") + "\n" + fin

def coach(etat, m, r, cle):
    """Agent individuel : messages courts envoyés aux abonnés effectivement inscrits sur la position."""
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
            _envoi_sur(c, text=humaniser(etat, c, t), reply_markup=markup_position(m))
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
        _envoi_sur(c, reply_markup=markup_position(m), text=humaniser(etat, c, texte))
        return
    # Le marché respire : petit retour vers l'entrée, on ne bouge rien
    r5 = r["r5"][-1]
    excès = (r5 >= 70) if d == 1 else (r5 <= 30)
    tps = pos.setdefault("cool_t", 0)
    if excès and time.time() - tps >= 45 * 60:
        pos["cool_t"] = time.time()
        _envoi_sur(c, reply_markup=markup_position(m), text=humaniser(etat, c, 
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
    if pa and pa["t15"] < debut - 1800:
        cle.pop("pre_manip", None)                 # pré-alerte périmée (ex. mémoire restaurée après un redémarrage) : on ne la ressort jamais
        pa = None
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
    fus = []                                   # niveaux confondus (ex. plus bas d'hier = plus bas de la semaine) : UN seul message
    for v, nom in niv:
        if v is None:
            continue
        pareil = next((f for f in fus if ("haut" in f[1][0]) == ("haut" in nom) and abs(f[0] - v) <= 0.05 * a), None)
        if pareil:
            pareil[1].append(nom)
        else:
            fus.append([v, [nom]])
    niv = [(v, noms[0], noms) for v, noms in fus]
    for v, nom, noms in niv:
        if len(noms) > 1:
            nom_aff = " et ".join([noms[0]] + [n.replace("plus haut ", "").replace("plus bas ", "") for n in noms[1:]])
        else:
            nom_aff = nom
        haut = "haut" in nom
        casse = (x15["c"] > v + 0.05 * a and prev <= v) if haut else (x15["c"] < v - 0.05 * a and prev >= v)
        if casse and not any(f"c{n}{jour}" in vu for n in noms):
            for n in noms:
                vu[f"c{n}{jour}"] = 1
            out.append(f"💥 CASSURE — {ICONE.get(m, '')} {m}\n🕯 La bougie 15 min de {heure(x15['t'])} a CLÔTURÉ {'au-dessus du' if haut else 'sous le'} {nom_aff} ≈ {px(v)}\n"
                       f"{'⬆️ Le mouvement peut continuer vers le haut' if haut else '⬇️ Le mouvement peut continuer vers le bas'}\n👀 Je vérifie l'alignement 15 min / 1 h / 4 h avant d'entrer")
        elif abs(p - v) <= 0.3 * a and not any(f"a{n}{jour}" in vu or f"c{n}{jour}" in vu for n in noms):
            for n in noms:
                vu[f"a{n}{jour}"] = 1
            out.append(f"🧲 NIVEAU CLÉ — {ICONE.get(m, '')} {m}\n📍 Le prix approche le {nom_aff} ≈ {px(v)}\n🕯 Vue 15 min : ça peut rebondir OU casser\n⏳ J'attends la clôture de la bougie 15 min")

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

ANTI_REPETITION_S = 3 * 3600           # même message (mêmes informations) : une seule fois pendant 3 h
# Messages jamais filtrés : exécution du trade (entrée, TP, stop, BE), news/annonces, fermeture, IA, dollar. Ils portent une information
# d'évènement unique : les supprimer serait dangereux.
ANTI_REPETITION_EXEMPTS = ("J'ENTRE MAINTENANT", "TP1 TOUCHÉ", "TP2 TOUCHÉ", "TP3 TOUCHÉ", "TP4 TOUCHÉ", "TP5 TOUCHÉ", "OBJECTIF FINAL", "STOP TOUCHÉ", "SORTIE AU STOP", "METS-TOI À BE",
                           "sorti à BE", "SORTI À BE", "OBJECTIFS REMIS", "ENTRÉE ENCORE POSSIBLE", "TROP TARD POUR ENTRER", "NEWS", "News passée", "FERMETURE",
                           "FERMÉ", "Annonces importantes", "Aucune annonce", "L'IA ALIGN", "leçon de l'IA", "DOLLAR")

_NOMBRE_RE = re.compile(r"(?<![\w.])\d{1,3}(?: \d{3})+(?:\.\d+)?(?!\d)|(?<![\w.])\d+(?:\.\d+)?")

def _forme_message(texte):
    """(modèle, nombres) : le modèle est le texte sans ses chiffres (heures comprises) ; les nombres servent à juger si l'information a changé."""
    t = re.sub(r"\b\d{1,2}[:h]\d{2}\b", "HH:MM", texte)
    nombres = [float(x.replace(" ", "")) for x in _NOMBRE_RE.findall(t)]
    modele = re.sub(r"\s+", " ", _NOMBRE_RE.sub("#", t)).strip()
    return modele, nombres

def _memes_nombres(a, b):
    """Mêmes informations : même nombre de valeurs, chacune à moins de 0,05 % (prix) ou 2 unités (petites valeurs : RSI, scores, compteurs)."""
    if len(a) != len(b):
        return False
    return all(abs(x - y) <= (0.0005 * max(abs(x), abs(y)) if max(abs(x), abs(y)) >= 1000 else 2.0) for x, y in zip(a, b))

def doublon_message(etat, texte, t=None, enregistrer=True):
    """Filet commun d'anti-répétition (une seule boucle d'envoi). True = même message, mêmes informations, déjà envoyé il y a moins de ANTI_REPETITION_S.
    Un message dont les chiffres ont vraiment changé (nouvelle zone, nouveau prix) passe toujours : c'est une information nouvelle."""
    if est_entree(texte) or any(k in texte for k in ANTI_REPETITION_EXEMPTS):
        return False
    t = time.time() if t is None else t
    mem = etat.setdefault("anti_rep", {})
    for k in [k for k, v in mem.items() if t - v["t"] > 2 * ANTI_REPETITION_S]:
        mem.pop(k, None)
    modele, nombres = _forme_message(texte)
    cle = hashlib.sha1(modele.encode()).hexdigest()[:16]
    vu = mem.get(cle)
    if vu and t - vu["t"] <= ANTI_REPETITION_S and _memes_nombres(vu["n"], nombres):
        return True
    if enregistrer:
        mem[cle] = {"t": t, "n": nombres}
    return False

EXTREME_REARMEMENT_S = 3 * 3600      # l'alerte « zone extrême » ne se réarme qu'après 3 h sans situation extrême

def texte_zone_extreme(m, r, d):
    """Message unique « zone extrême Daily/Weekly » : reprend TOUTES les informations des deux anciens messages (alignement 4h + 1h, zones Daily et Weekly,
    refus de suivre la tendance, risque, ce que j'attends) pour ne pas dire deux fois la même chose."""
    sens = "LONG" if d == 1 else "SHORT"
    # Carte courte (une info par ligne) : rien n'est supprimé, les phrases en moins
    return (f"📍 {ICONE.get(m, '')} {m} - EN ATTENTE\n"
            f"⚠️ Prix en zone extrême Daily/Weekly : {zone_txt(r['posD'])} / {zone_txt(r['posW'])}\n"
            f"🧭 4h + 1h alignées {'▲' if d == 1 else '▼'}\n"
            f"⛔ Je ne poursuis pas le {sens} : risque de {'repli' if d == 1 else 'rebond'}\n"
            f"⏳ J'attends : repli ou retournement confirmé en 1h + clôture 5m, ou meilleur prix\n"
            f"🛡️ Action : NE PAS RENTRER")

def alerte_extreme_due(cle, d, t):
    """Alerte « zone extrême Daily/Weekly » : UNE seule fois par situation. La situation est identifiée par le sens bloqué seul
    (le libellé de zone oscille autour des seuils et ne doit pas relancer le message). Elle se réarme si le sens change
    ou si la situation a disparu pendant plus de EXTREME_REARMEMENT_S."""
    vu, sig = cle.get("extreme_vu_t", 0), cle.get("extreme_sig")
    cle["extreme_vu_t"] = t
    if sig == str(d) and t - vu <= EXTREME_REARMEMENT_S:
        return False
    cle["extreme_sig"] = str(d); cle["extreme_warn_t"] = t
    return True

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
    try:
        rv_ = retournement_marche(m, r, cle)          # v71 : retournement par marché (même règle que le graphique)
        if rv_ and not (tr and tr.get("d") == (1 if "LONG" in rv_.split("\n")[0] else -1)):
            out.append(rv_)
    except Exception as ex:
        print("retournement_marche", ex)

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
            # Message conservé dans tous les cas où il partait avant ; seule l'oscillation 1h/4h est limitée (une fois par heure)
            if cle.get("aligne") and r["t"] - cle.get("perdue_t", 0) >= 3600:
                cle["perdue_t"] = r["t"]
                out.append(f"⚪ {m} : confirmation 1h / tendance 4h perdue. Ordre annulé, j'attends.")
            cle["aligne"] = 0; cle["prep"] = False; cle.pop("ordre", None)
            return out
        # Extrême Daily/Weekly : aucune poursuite dans le sens de la tendance.
        # On attend une correction ou un retournement confirmé ; on ne vend pas à découvert sans signal opposé validé.
        if bloque_dw(r, d, p):
            cle["prep"] = False
            cle.pop("ordre", None)
            if alerte_extreme_due(cle, d, r["t"]):
                out.append(texte_zone_extreme(m, r, d))
            cle["aligne"] = d
            return out
        # ── Entrée sur CASSURE confirmée (clôture 5 min au-delà du niveau) ──
        pc = plan_cassure(r, d)
        if pc and pc["t15"] != cle.get("cassure_t") and not r.get("annonce"):
            cle["cassure_t"] = pc["t15"]
            tr = dict(pc, statut="entree", cree=r["t"], encore=0, atr_e=r["atr"])
            tr["profil"] = profil_trade(m, tr, r)
            tr.update(strategie_trade(r, d))
            tr["retour"] = retournement_confirme(cle, d, r)
            non, n_, w_ = memoire_refuse(tr["profil"])
            if non:
                out.append(f"🧠 {ICONE.get(m, '')} {m} : cassure vue, mais je passe mon tour\n📚 Ce type de position a perdu trop souvent ({w_}/{n_} gagnés)")
                return out
            cle["trade"] = tr; cle["prep"] = False; cle["attente_rsi"] = False; cle["parti"] = False; cle.pop("ordre", None)
            out.append((carte_coach(m, r, cle, "signal", tr=tr, validite=validite_cloture(r, "5m"),
                                signal=f"Cassure 5 min {'au-dessus' if d == 1 else 'sous'} {px(pc['niveau'])}") + ferme, boutons(m)))
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
        if o is None:
            if not cle.get("sans_setup"):                  # une seule fois, jusqu'au retour d'un vrai setup (pas de répétition)
                cle["sans_setup"] = True
                out.append(f"⏳ {ICONE.get(m, '')} {m} : pas de FVG / order block exploitable en vue 5 min\n😎 Je ne force rien : j'attends un vrai setup")
            return out
        cle["sans_setup"] = False
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
                out.append(    f"↩️ {ICONE.get(m, '')} {m} : LE REPLI EST LÀ {'⬇️' if d == 1 else '⬆️'}\n{SENS[d]} se prépare\n👀 Vue {o.get('sl_ut', '5 min')}, tiens-toi prêt\n🔔 Prochaine alerte : ÇA ARRIVE")
        if cle.get("aligne") != d:
            cle["aligne"] = d; cle["prep"] = False
            if bloque:
                if alerte_extreme_due(cle, d, r["t"]):          # même message et même anti-répétition que « zone extrême » (plus de double discours)
                    out.append(texte_zone_extreme(m, r, d))
            else:
                cle["ordre"] = o
                out.append((f"🔔 JE PRÉPARE UNE POSITION — {ICONE.get(m, '')} {m}\n{SENS[d]}   {'monte' if d == 1 else 'descend'} sur 15m, 1h et 4h ✅✅✅\n{qualite(o)}"
                           f"⏳ Je n'entre pas encore : j'attends que le prix vienne dans la zone 🟨\n"
                           f"👀 Mets-toi en vue {o.get('sl_ut', '5 min')}\n"
                           f"🕯 Repère {'le dernier creux (mèche du bas)' if d == 1 else 'le dernier sommet (mèche du haut)'}\n"
                           f"🟨 L'entrée sera à peu près {'au-dessus de ce creux' if d == 1 else 'sous ce sommet'}\n"
                           f"🚦 Attends mon feu vert 🟢\n"
                           f"🅰️ Entrée sur le repli dans la zone 🟨\n{ligne_cassure(r, d)}\n\n"
                           f"{fmt_trade(m, o, p)}\n\n"
                           f"📐 Zone = {o['src']}{ferme}", bouton_auto(m)))
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
                out.append((f"{'🟩🟩' if d == 1 else '🟥🟥'} POINT D'ENTRÉE À VENIR — {ICONE.get(m, '')} {m}\n{SENS[d]}\n{qualite(o)}👀 ÇA ARRIVE\n🟩 Le prix entre dans la ZONE du graphique\n🟨 Ligne jaune ENTRÉE : attends la CLÔTURE 15 min {'AU-DESSUS' if d == 1 else 'EN DESSOUS'}\n🙅 Une mèche seule ne suffit pas\n🛑 SL = ligne rouge du graphique\n⚡ Tiens-toi prêt\n🔔 Cloche activée ? Ne rate pas le feu vert\n📍 Zone ≈ {px(o.get('za', o['e']))} – {px(o.get('zb', o['e']))}{statut_txt(0, o)}", bouton_auto(m)))
        # À quelques pips de l'entrée : « PRÉPARE-TOI » + rappel SL / TP (1 fois par point d'entrée)
        seuil = max(5 * PIP.get(m, 0.1), 0.05 * r["atr"])
        if cle.get("prep") and (abs(p - o["e"]) <= seuil or touche) and time.time() - cle.get("pret_t", 0) > 1800:
            cle["pret_t"] = time.time()
            if r["t"] - cle.get("recalc_t", 0) >= 1800:
                out.append((f"⚡⚡ PRÉPARE-TOI — {ICONE.get(m, '')} {m}\n{SENS[d]}\n{qualite(o)}🎯 On est à quelques pips de l'entrée\n👀 Vue {o.get('sl_ut', '5 min')}\n"
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
                # Le déclencheur reste M5, mais le stop protège la structure M15 pour éviter les sorties sur le bruit d'une seule bougie.
                sl_m = stop_meche_5m(r, d, p)
                sl_ut_ = "5 min"
                if sl_m is None:
                    sl_m = stop_structure_15m(r, d, p); sl_ut_ = "15 min"
                if sl_m is None:
                    cle["prep"] = False; cle.pop("ordre", None); cle["attente_rsi"] = False
                    out.append(f"⛔ {ICONE.get(m, '')} {m} : entrée annulée\nLa structure 15 min exige un risque trop grand ou les données sont insuffisantes.\nJe ne resserre pas artificiellement le SL : j'attends un nouveau setup.")
                    return out
                o = dict(o, e=p, sl=sl_m, za=p, zb=p, rr=abs(o["tp1"] - p) / max(abs(p - sl_m), 1e-9), rejet=True,
                         sl_h=bougie_protegee((r["b5"][:-1][-4:] if sl_ut_ == "5 min" else r["b15"][-3:]), d, sl_m), sl_ut=sl_ut_)
                tr = dict(o, statut="entree", cree=r["t"], encore=0, atr_e=a_)
                tr["profil"] = profil_trade(m, tr, r)
                tr.update(strategie_trade(r, d))
                tr["retour"] = retournement_confirme(cle, d, r)
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
                ctx = " + ".join([t for t, ok in checks if ok and not t.startswith(("Pas de news", "Gain / risque"))][:3])
                out.append((carte_coach(m, r, cle, "signal", tr=tr, validite=validite_cloture(r, "15m"),
                                        signal=f"{raison} + {ctx}" if ctx and raison not in ctx else (ctx or raison)) + ferme, boutons(m)))
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
    cs_ = lambda *a_, **k_: carte_suivi(*a_, d=tr["d"], **k_)     # LONG / SHORT en premier sur chaque carte de suivi
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
        out.append(cs_(m, "OBJECTIFS REMIS DANS L'ORDRE", [f"💰 TP1 : {px(n1v)} ({n1n})", f"🏁 TP2 : {px(n2v)} ({n2n})", f"🛑 SL : {px(tr['sl'])} (inchangé)"], "Rester en position", r))
    d, e, sl, t1, t2 = tr["d"], tr["e"], tr["sl"], tr["tp1"], tr["tp2"]
    touche_sl = (lo <= sl) if d == 1 else (hi >= sl)
    touche_t1 = (hi >= t1) if d == 1 else (lo <= t1)
    touche_t2 = (hi >= t2) if d == 1 else (lo <= t2)
    progres = d * (p - e) / max(abs(t1 - e), 1e-9)

    if tr["statut"] == "entree":
        if touche_sl:
            if tr.get("be_dit"):
                out.append(cs_(m, "SORTI À BE", [f"🛑 SL : {px(sl)} touché (BE)", "🛡 Aucune perte"], "Hors position", r, "attente"))
            else:
                inverse = "LONG" if d == -1 else "SHORT"
                out.append(cs_(m, "STOP TOUCHÉ", [f"🛑 Stop : {px(sl)} touché", f"↩ Retournement possible : {inverse} si 15 min + 1 h confirment"], "Hors position", r, "attente"))
                cle["retournement"] = {"d": -d, "t": r["t"]}
            cle["fin"] = [tr, sl, "🔒 Sorti à BE" if tr.get("be_dit") else "🛑 Stop touché"]; cle["stop_t"] = r["t"]
            cle.pop("trade"); cle["aligne"] = 0; return out
        if touche_t1:
            tr["statut"] = "tp1"; tr["sl"] = e
            out.append(cs_(m, "TP1 TOUCHÉ", [f"💰 TP1 : {px(t1)} ✅", f"🔒 SL → BE : {px(e)}", f"🏁 TP2 : {px(t2)}"] + lecture_tp1(r, d),
                                   "Sécuriser une partie, garder le reste", r))
            return out
        # ↩ Voyants de retournement (comme l'indicateur) : 3/5 petites unités contre la position = alerte, 1 fois.
        alerte_r = alerte_retournement(m, r, tr)
        if alerte_r:
            out.append(alerte_r)
            return out
        risque_ = abs(e - sl)
        if not tr.get("be_dit") and risque_ > 0 and d * (p - e) >= 1.2 * risque_ and d * (r["b15"][-1]["c"] - e) >= r["atr"]:
            tr["be_dit"] = True; tr["sl"] = e + d * 0.05 * r["atr"]
            out.append(cs_(m, "METS-TOI À BE", [f"🛑 SL → BE : {px(e)} (entrée)", f"🕯 Clôture 15 min {heure(r['b15'][-1]['t'])} {'au-dessus' if d == 1 else 'sous'} l'entrée",
                                                          f"💰 TP : {px(t1)}", "🙅 Le prix ne doit plus revenir à ton entrée : on encaisse 💰"], "SL à BE (plus de perte possible)", r))
            return out
        if progres < 0.25:
            if tr["encore"] < 1 and r["t"] - tr["cree"] >= 900:
                tr["encore"] += 1
                if True:
                    vue_ = f" (vue {tr['sl_ut']})" if tr.get("sl_ut") else ""
                    niv_ = [(f"🛑 SL : {px(sl)}", sl), (f"🎯 Entrée : {px(e)}{vue_}", e), (f"💰 TP1 : {px(t1)}", t1)]
                    if t2 is not None and d * (t2 - t1) > 0:
                        niv_.append((f"🏁 TP2 : {px(t2)}", t2))
                    lignes_ = [f"🕯 Prix actuel {px(p)} : encore près de l'entrée du bot ({px(e)})", ""] + [x for x, _ in sorted(niv_, key=lambda z: -z[1])]   # ordre du graphique
                    out.append((cs_(m, "ENTRÉE ENCORE POSSIBLE", lignes_, "Entrer (bouton de suivi)", r), boutons(m)))
        elif not tr.get("tard"):
            tr["tard"] = True
            # Le bot reste en position jusqu'au TP ou au SL (son bilan compte toutes ses positions)
            out.append(cs_(m, "TROP TARD POUR ENTRER", [f"📏 Prix trop loin de l'entrée {px(e)}", f"💰 TP1 : {px(t1)}", "🟢 Position déjà ouverte : suivie"], "NE PAS ENTRER", r))
        return out

    if tr["statut"] == "tp1":
        n_tp = int(tr.get("n_tp") or 2)                  # numéro du TP visé (TP2, puis TP3, TP4…) : la course continue tant que la tendance tient
        if touche_t2:
            # Déplacement du TP : tendance 4h toujours dans le bon sens et RSI 15m pas en excès → on vise plus loin (jusqu'au TP5)
            suivants = sorted([z for z in r["grosses"] if d * (z[0] - t2) >= r["atr"]], key=lambda z: d * z[0])
            excès = (r["r15"] >= 70) if d == 1 else (r["r15"] <= 30)
            if r["dirs"][9] == d and not excès and suivants and n_tp < 5:
                prec = tr.get("tp_prec", t1)
                tr["etendu"] = True; tr["sl"] = prec; tr["tp_prec"] = t2; tr["tp2"] = suivants[0][0]; tr["n_tp"] = n_tp + 1
                out.append(cs_(m, f"TP{n_tp} TOUCHÉ", [f"💰 TP{n_tp} : {px(t2)} ✅", f"🏆 {n_tp} TP touchés sur ce trade",
                                                     f"🛑 Nouveau SL : {px(tr['sl'])} (au TP{n_tp - 1})",
                                                     f"🎯 TP{n_tp + 1} : {px(suivants[0][0])}", "🚀 La tendance continue, on laisse courir"],
                               "Rester en position (tendance continue)", r))
                return out
            out.append(cs_(m, "OBJECTIF FINAL ATTEINT", [f"🎯 TP{n_tp} : {px(t2)} ✅", f"🏆 {n_tp} TP touchés sur ce trade"], "Trade terminé", r, "attente"))
            cle["fin"] = [tr, t2, f"🏆 Objectif final ({n_tp} TP)"]
            cle.pop("trade"); cle["aligne"] = 0; return out
        if (lo <= tr["sl"]) if d == 1 else (hi >= tr["sl"]):
            n_ok = n_tp - 1
            out.append(cs_(m, "SORTIE AU STOP SÉCURISÉ", [f"🛑 Sortie : {px(tr['sl'])}", f"🏆 {n_ok} TP encaissé{'s' if n_ok > 1 else ''} avant le retournement",
                                                         "✅ Aucune perte"], "Hors position", r, "attente"))
            cle["fin"] = [tr, t1 if d * (tr["sl"] - t1) < 0 else tr["sl"], f"💰 {n_ok} TP encaissé{'s' if n_ok > 1 else ''}"]
            cle.pop("trade"); cle["aligne"] = 0; return out
    return out

# ───────── Programme ─────────
def _menu_analyse_rapide(cid):
    _envoi_sur(cid, text="📊 Quel marché veux-tu analyser ?",
               reply_markup=json.dumps({"inline_keyboard": [
                   [{"text": "🥇 GOLD", "callback_data": "analysechoice:GOLD"}],
                   [{"text": "🟠 BTC", "callback_data": "analysechoice:BTC"}],
                   [{"text": "💠 NASDAQ", "callback_data": "analysechoice:NASDAQ"}],
                   [{"text": "📡 Mes marchés cochés", "callback_data": "analysechoice:BOTH"}]
               ]}))


def _traiter_lecture_rapide(etat, chats, update):
    """Répond sans attendre l'analyse aux commandes Telegram qui ne modifient pas le trading."""
    msg = update.get("message") or update.get("edited_message") or {}
    if not msg or not msg.get("text"):
        return False
    chat = msg.get("chat") or {}
    cid = str(chat.get("id", ""))
    if not cid or chat.get("type") != "private":
        return False
    localement_autorise = (POSITIONS_GRATUITES or cid in chats or cid in proprio(etat)
                           or cid in etat.get("offerts", []))
    text = msg.get("text", "").strip()
    words = text.split() if text.startswith("/") else []
    cmd = words[0].split("@")[0].lower() if words else ""
    payload = words[1].lower() if len(words) > 1 else ""
    if cmd == "/start":
        if payload:
            return False
        if not localement_autorise:
            return False  # laisse le handler principal vérifier les abonnements Telegram
        _envoi_sur(cid, text="⬇️ Tes boutons sont là 👇\n💡 Clavier caché ? Appuie sur l'icône ⌘ à droite du champ",
                   reply_markup=CLAVIER)
        update["_align_fast_handled"] = True
        return True
    if cmd == "/boutons":
        if not localement_autorise:
            return False
        _envoi_sur(cid, text="⬇️ Tes boutons sont là 👇", reply_markup=CLAVIER)
        update["_align_fast_handled"] = True
        return True
    if cmd in COMMANDES:
        text = COMMANDES[cmd]
    normalized = text.lower().replace("é", "e").replace("è", "e")
    if "mon bot" in normalized or "mon_bot" in normalized:
        if not localement_autorise:
            return False
        menu_bot(etat, cid)
        update["_align_fast_handled"] = True
        return True
    if "mes resultats" in normalized or "my results" in normalized or "resultat" in normalized:
        if not localement_autorise:
            return False
        _envoi_sur(cid, text=texte_resultats(etat, cid), reply_markup=CLAVIER)
        update["_align_fast_handled"] = True
        return True
    if "faire une analyse" in normalized or "run an analysis" in normalized:
        _menu_analyse_rapide(cid)
        update["_align_fast_handled"] = True
        return True
    return False


TOASTS_CALLBACK = {
    "in": ("👊 Suivi de ta position activé : le coach te guide jusqu'au TP", "👊 Position tracking on: the coach guides you to TP"),
    "auto": ("🔔 Suivi activé : je te préviens dès qu'une entrée est confirmée", "🔔 Tracking on: I'll alert you when an entry is confirmed"),
    "followmarket": ("🔔 Suivi activé : je te préviens dès qu'une entrée est confirmée", "🔔 Tracking on: I'll alert you when an entry is confirmed"),
    "markets": ("✅ Marchés enregistrés", "✅ Markets saved"),
    "out": ("🚪 Sortie enregistrée", "🚪 Exit recorded"),
    "analysechoice": ("📊 Analyse en cours…", "📊 Analysis running…"),
}


def toast_callback(data, anglais=False):
    """Petite notification Telegram affichée immédiatement au clic, propre à chaque bouton."""
    cle = str(data or "").split(":", 1)[0]
    fr, en = TOASTS_CALLBACK.get(cle, ("⌛ Action reçue, traitement en cours.", "⌛ Action received, processing."))
    return en if anglais else fr


def _ack_callback_rapide(cb, text):
    try:
        telegram("answerCallbackQuery", callback_query_id=cb["id"], text=text)
        CALLBACKS_ACKNOWLEDGED.add(str(cb["id"]))
    except Exception as ex:
        print("callback ack", ex)


# ───────── LIVE TikTok : bande qui défile + télécommande du graphique ─────────
# Le bot publie sur un canal privé (ntfy, gratuit). Le script Tampermonkey de l'onglet TradingView du live
# l'écoute : texte → bande qui défile ; « CMD:… » → change l'unité de temps / le marché 15 s puis revient.
# Jamais le sens, l'entrée, le SL ni le TP sur la bande (règle du live).
# Canal privé bot → graphique : secret GitHub ALIGN_LIVE_SUJET, sinon dérivé du jeton Telegram (jamais écrit dans le dépôt public)
LIVE_SUJET = (os.environ.get("ALIGN_LIVE_SUJET", "").strip() or
              ("align-live-" + hashlib.sha256(("align-live:" + TOKEN).encode()).hexdigest()[:16] if TOKEN else ""))
LIVE_LIEN = os.environ.get("ALIGN_LIVE_LIEN", "https://www.tiktok.com/@adelkhatra/live").strip()
PRIX_MAIN_STARS = int(os.environ.get("PRIX_MAIN_STARS", "25"))         # ≈ 0,50 € pour l'abonné
LIVE_DUREE_MAIN = 15
LIVE_BOOST_PAUSE = 120                                                 # 1 boost / personne / 2 min
LIVE_CHOIX = {"1": ("tf", "1", "⏱ 1 min"), "5": ("tf", "5", "⏱ 5 min"), "15": ("tf", "15", "⏱ 15 min"),
              "60": ("tf", "60", "⏱ 1 h"), "BTC": ("sym", "CRYPTO:BTCUSD", "🟠 BTC"),
              "GOLD": ("sym", "FOREXCOM:XAUUSD", "🥇 Gold"), "NASDAQ": ("sym", "FX:NAS100", "💠 NASDAQ")}
_LIVE_BOOSTS = {}
_LIVE_DERNIER = {}

def live_actif(etat):
    return bool(etat.get("live_on"))

def live_publier(texte):
    """Envoie une ligne au graphique du live. Ne bloque jamais le bot (échec = ignoré)."""
    if not LIVE_SUJET or not texte:
        return False
    try:
        req = urllib.request.Request("https://ntfy.sh/" + urllib.parse.quote(LIVE_SUJET),
                                     data=str(texte)[:200].encode("utf-8"), headers={"User-Agent": "align-bot"})
        with urllib.request.urlopen(req, timeout=8):
            return True
    except Exception as ex:
        print("live publier", ex)
        return False

def live_bande(etat, texte, cle=None, pause=60):
    """Message sur la bande, seulement quand le live tourne ; une même annonce au plus 1 fois / pause."""
    if not live_actif(etat):
        return False
    if cle:
        if time.time() - _LIVE_DERNIER.get(cle, 0) < pause:
            return False
        _LIVE_DERNIER[cle] = time.time()
    return live_publier(texte)

def live_annonces(etat, m, textes):
    """Ce que le bot envoie sur Telegram → la bande (sans aucun niveau)."""
    ic = ICONE.get(m, "")
    for t in textes or []:
        t = t if isinstance(t, str) else str(t)
        if "J'ENTRE MAINTENANT" in t:
            live_bande(etat, f"🚀 ALIGN ENTRE EN POSITION sur {ic} {m} ! 👉 Le coach est sur Telegram", f"entre{m}", 600)
        elif "OBJECTIF FINAL ATTEINT" in t or "TP2 TOUCHÉ" in t:
            live_bande(etat, f"🏆 TP2 TOUCHÉ sur {ic} {m} ! Bravo à ceux qui ont suivi 🔥", f"tp2{m}", 600)
        elif "TP1 TOUCHÉ" in t:
            if live_bande(etat, f"🎯 TP1 TOUCHÉ sur {ic} {m} ! ✅", f"tp1{m}", 600):
                live_publier(f"BULLE:🎯 {ic} {m} TP1 touché • bougie qui CLÔTURE AU-DELÀ du TP1 = ça continue vers le TP2 🚀 • "
                             "bougie qui REVIENT = le SL passe à BE, on protège 🛡")
        elif "POINT D'ENTRÉE À VENIR" in t:
            # Règle live : aucune info (ni sens, ni niveau, ni marché) → seulement l'invitation au coach Telegram
            live_bande(etat, "BULLE:👉 Connecte-toi au coach sur Telegram pour les infos en temps réel", f"zone{m}", 900)
        elif "RETOURNEMENT EN PRÉPARATION" in t:
            live_bande(etat, f"BULLE:↩ {ic} {m} : regarde la ligne RETOURNEMENT • le marché peut se retourner", f"ret{m}", 900)
        elif "MANIPULATION" in t or "MÈCHE SUSPECTE" in t:
            live_bande(etat, f"BULLE:🎣 {ic} {m} : grosse mèche = chasse aux stops • on attend la clôture", f"meche{m}", 900)

def live_suivi(etat, cid, m):
    """Un abonné entre en position avec le bot → la bande l'annonce (prénom seulement)."""
    try:
        n = sum(1 for v in ((etat.get(m) or {}).get("trade") or {}).get("qui", {}).values() if isinstance(v, dict))
    except Exception:
        n = 0
    p = etat.get("prenoms", {}).get(str(cid)) or "Un abonné"
    live_bande(etat, f"👊 {p} entre en position avec ALIGN sur {ICONE.get(m, '')} {m} • {n} abonné{'s' if n > 1 else ''} dedans 🔥")

def texte_live(etat, anglais=False):
    if not live_actif(etat):
        return ("⚫ PAS DE LIVE EN CE MOMENT\n🔔 Je te préviens dès que le live commence" if not anglais else
                "⚫ NO LIVE RIGHT NOW\n🔔 I'll tell you as soon as the live starts")
    if anglais:
        return ("🔴 LIVE IN PROGRESS\n📺 Adel's chart, live\n━━━━━━━━━━━━━━━\n🚀 Boost the live: your name on screen (free)\n"
                f"🎮 Take control: change the chart for {LIVE_DUREE_MAIN} s\n📸 {LIVE_DUREE_MAIN} s to take your screenshot and spot the candles\n"
                f"⏪ Then the chart goes back to Adel's view automatically\n⭐ {PRIX_MAIN_STARS} Stars\n👇 Choose")
    return ("🔴 LIVE EN COURS\n📺 Le graphique d'Adel, en direct\n━━━━━━━━━━━━━━━\n🚀 Booster le live : ton prénom à l'écran (gratuit)\n"
            f"🎮 Prends la main : tu changes le graphique {LIVE_DUREE_MAIN} s\n📸 {LIVE_DUREE_MAIN} s pour faire ta capture et repérer les bougies\n"
            f"⏪ Ensuite le graphique revient tout seul à la vue d'Adel\n⭐ {PRIX_MAIN_STARS} Stars (≈ 0,50 €)\n👇 Choisis")

def clavier_live(etat, cid, anglais=False):
    lignes = []
    if live_actif(etat):
        lignes.append([{"text": "📺 Watch the live" if anglais else "📺 Regarder le live", "url": LIVE_LIEN}])
        lignes.append([{"text": "🚀 Boost the live" if anglais else "🚀 Booster le live", "callback_data": "liveboost:x"}])
        lignes.append([{"text": LIVE_CHOIX[k][2], "callback_data": f"livemain:{k}"} for k in ("BTC", "GOLD", "NASDAQ")])
        lignes.append([{"text": LIVE_CHOIX[k][2], "callback_data": f"livemain:{k}"} for k in ("1", "5", "15", "60")])
    if str(cid) in {str(x) for x in proprio(etat)}:
        lignes.append([{"text": "⏹ Live terminé" if live_actif(etat) else "🔴 Je lance le live",
                        "callback_data": "liveoff:x" if live_actif(etat) else "liveon:x"}])
    return json.dumps({"inline_keyboard": lignes}) if lignes else None

def menu_live(etat, cid):
    anglais = str(cid) in LANG_EN
    kb = clavier_live(etat, cid, anglais)
    texte = texte_live(etat, anglais)
    if str(cid) in {str(x) for x in proprio(etat)}:      # admin seulement : le code à mettre dans le script de l'écran
        texte += f"\n━━━━━━━━━━━━━━━\n🔐 Code écran (admin) : {LIVE_SUJET or 'absent'}"
    _envoi_sur(cid, text=texte, **({"reply_markup": kb} if kb else {}))

def live_annoncer_debut(etat, chats):
    """Le propriétaire lance le live : tout le monde (VIP + gratuits) reçoit le lien."""
    vus = set()
    for cid in list(chats) + list(etat.get("prospects", [])):
        cid = str(cid)
        if cid in vus:
            continue
        vus.add(cid)
        anglais = cid in LANG_EN
        try:
            _envoi_sur(cid, text=("🔴 ADEL IS LIVE ON TIKTOK\n📺 The ALIGN chart, live\n🎮 You can take control of the chart"
                                  if anglais else "🔴 ADEL EST EN LIVE SUR TIKTOK\n📺 Le graphique ALIGN en direct\n🎮 Tu peux prendre la main sur le graphique"),
                       reply_markup=clavier_live(etat, cid, anglais))
        except Exception as ex:
            print("live annonce", cid, ex)

def live_callback(etat, chats, cb, choix, mk, qui):
    """Boutons du live. Renvoie True si le bouton appartenait au live."""
    if choix not in ("liveon", "liveoff", "liveboost", "livemain"):
        return False
    anglais = qui in LANG_EN
    if choix in ("liveon", "liveoff"):
        if qui not in {str(x) for x in proprio(etat)}:
            return True
        etat["live_on"] = choix == "liveon"
        if etat["live_on"]:
            live_publier("🔴 LE LIVE ALIGN COMMENCE ! 👉 ABONNE-TOI • PARTAGE • TAPOTE L'ÉCRAN")
            live_annoncer_debut(etat, chats)
        else:
            _envoi_sur(qui, text="⏹ Live terminé\n🔕 Plus aucune annonce de live")
        return True
    if not live_actif(etat):
        _envoi_sur(qui, text=texte_live(etat, anglais))
        return True
    if choix == "liveboost":
        if time.time() - _LIVE_BOOSTS.get(qui, 0) < LIVE_BOOST_PAUSE:
            _envoi_sur(qui, text=("⏳ One boost every 2 min" if anglais else "⏳ 1 boost toutes les 2 min"))
            return True
        _LIVE_BOOSTS[qui] = time.time()
        p = etat.get("prenoms", {}).get(qui) or ("A viewer" if anglais else "Un abonné")
        ok = live_publier(f"{p} BOOSTE LE LIVE ! 🚀 ABONNE-TOI • PARTAGE")
        _envoi_sur(qui, text=(("🚀 Your name is on screen! Look at the live 👀" if anglais else "🚀 Ton prénom passe à l'écran ! Regarde le live 👀")
                              if ok else ("⚠️ The live screen is not reachable right now" if anglais else "⚠️ L'écran du live ne répond pas pour l'instant")))
        return True
    if mk not in LIVE_CHOIX:
        return True
    nom = LIVE_CHOIX[mk][2]
    if qui in {str(x) for x in proprio(etat)}:          # l'admin teste gratuitement, sans facture
        live_paiement_recu(etat, qui, {"invoice_payload": f"livemain:{mk}", "total_amount": 0, "telegram_payment_charge_id": "admin"})
        return True
    try:
        telegram("sendInvoice", chat_id=qui, title=("🎮 Take control of the live" if anglais else "🎮 Prends la main sur le live"),
                 description=(f"{nom} on Adel's chart for {LIVE_DUREE_MAIN} seconds, then it goes back automatically." if anglais else
                              f"{nom} sur le graphique d'Adel pendant {LIVE_DUREE_MAIN} secondes, puis retour automatique."),
                 payload=f"livemain:{mk}", currency="XTR", provider_token="",
                 prices=json.dumps([{"label": nom, "amount": PRIX_MAIN_STARS}]))
    except Exception as ex:
        print("live facture", ex)
        _envoi_sur(qui, text="⚠️ Paiement indisponible pour l'instant")
    return True

def live_pre_checkout(etat, pcq):
    """Telegram demande la validation AVANT de débiter : on refuse si le live ne tourne pas (l'abonné ne paie rien)."""
    charge = str(pcq.get("invoice_payload", ""))
    ok = charge.startswith("livemain:") and charge.split(":", 1)[1] in LIVE_CHOIX and live_actif(etat) and bool(LIVE_SUJET)
    try:
        if ok:
            telegram("answerPreCheckoutQuery", pre_checkout_query_id=pcq["id"], ok="true")
        else:
            telegram("answerPreCheckoutQuery", pre_checkout_query_id=pcq["id"], ok="false",
                     error_message="Le live n'est pas en cours : aucun paiement n'a été fait.")
    except Exception as ex:
        print("pre_checkout", ex)
    return ok

def live_paiement_recu(etat, cid, paiement):
    """Paiement validé : l'ordre part vers le graphique (file d'attente côté graphique, 15 s chacun)."""
    charge = str((paiement or {}).get("invoice_payload", ""))
    mk = charge.split(":", 1)[1] if ":" in charge else ""
    if mk not in LIVE_CHOIX:
        return False
    sorte, valeur, nom = LIVE_CHOIX[mk]
    p = etat.get("prenoms", {}).get(str(cid)) or "Un abonné"
    envoye = live_publier(f"CMD:{sorte}:{valeur}:{p}")
    etat.setdefault("live_paiements", []).append({"t": int(time.time()), "cid": str(cid), "choix": mk,
                                                  "stars": (paiement or {}).get("total_amount"),
                                                  "id": (paiement or {}).get("telegram_payment_charge_id"), "envoye": envoye})
    del etat["live_paiements"][:-200]
    anglais = str(cid) in LANG_EN
    if not envoye:
        _envoi_sur(str(cid), text=("⚠️ The live screen did not answer: try again in a moment" if anglais else
                                   "⚠️ L'écran du live n'a pas répondu : réessaie dans un instant"))
        return False
    _envoi_sur(str(cid), text=((f"✅ It's yours! {nom} on the live for {LIVE_DUREE_MAIN} s 👀\n📸 Take your screenshot now: back to Adel's view after {LIVE_DUREE_MAIN} s" if anglais else
                                f"✅ C'est à toi ! {nom} sur le live pendant {LIVE_DUREE_MAIN} s 👀\n📸 Fais ta capture maintenant : retour à la vue d'Adel après {LIVE_DUREE_MAIN} s") +
                               ("\n⏳ If someone is before you, you're next in line" if anglais else "\n⏳ Si quelqu'un est avant toi, tu passes juste après")))
    return True


def boucle_polling_telegram(etat, chats):
    """Poll Telegram indépendamment des analyses longues; les actions d'écriture restent dans le thread principal."""
    offset = int(etat.get("offset", 0) or 0)
    while TOKEN and not TELEGRAM_POLL_STOP.is_set():
        try:
            updates = telegram("getUpdates", offset=offset, timeout=1).get("result", [])
        except Exception as ex:
            if not TELEGRAM_POLL_STOP.is_set():
                print("poller Telegram", ex)
                time.sleep(1)
            continue
        for update in updates:
            offset = max(offset, int(update.get("update_id", offset - 1)) + 1)
            if update.get("pre_checkout_query"):
                live_pre_checkout(etat, update["pre_checkout_query"])
            paiement = (update.get("message") or {}).get("successful_payment")
            if paiement:
                live_paiement_recu(etat, str((update.get("message") or {}).get("chat", {}).get("id", "")), paiement)
                update["_align_fast_handled"] = True
            cb = update.get("callback_query")
            if cb:
                chat = (cb.get("message") or {}).get("chat") or {}
                user_id = str((cb.get("from") or {}).get("id", ""))
                anglais = user_id in etat.get("en", [])
                if chat.get("type") != "private" or str(chat.get("id", "")) != user_id:
                    _ack_callback_rapide(cb, "🔒 Open the bot in a private chat." if anglais else "🔒 Ouvre le bot en conversation privée.")
                    update["_align_fast_handled"] = True
                else:
                    _ack_callback_rapide(cb, toast_callback(cb.get("data", ""), anglais))
            else:
                _traiter_lecture_rapide(etat, chats, update)
            TELEGRAM_UPDATES.put(update)


def recevoir_updates_telegram(etat, chats, demandes):
    """Traite sur le thread principal les mises à jour reçues par le poller indépendant."""
    if not TOKEN:
        return 0
    updates = []
    while True:
        try:
            updates.append(TELEGRAM_UPDATES.get_nowait())
        except queue.Empty:
            break
    if updates:
        demandes.extend(traiter(etat, chats, updates))
    return len(updates)


ARRET_FORCE_SEC = int(os.environ.get("ARRET_FORCE_SEC", "25"))
_ETAT_COURANT = {}


def _arret_garanti():
    """Si une analyse longue bloque l'arrêt, on sauvegarde quand même l'état puis on quitte.
    Évite l'annulation forcée GitHub (état perdu + bot muet plusieurs minutes pendant la relève)."""
    time.sleep(ARRET_FORCE_SEC)
    etat = _ETAT_COURANT.get("etat")
    try:
        if etat is not None and CHRONO_LOCK.acquire(timeout=5):
            try:
                _sauver_etat_sous_verrou(etat, _ETAT_COURANT.get("chats"))
            finally:
                CHRONO_LOCK.release()
            print("ALIGN_STATE_SAVED_ON_FORCED_SHUTDOWN", flush=True)
    except Exception as ex:
        print("ALIGN_FORCED_SAVE_FAILED", ex, flush=True)
    os._exit(0)


def _demander_arret(signum, frame):
    premier = not SHUTDOWN_REQUESTED.is_set()
    SHUTDOWN_REQUESTED.set()
    TELEGRAM_POLL_STOP.set()
    print(f"ALIGN_SHUTDOWN_REQUESTED signal={signum}", flush=True)
    if premier:
        threading.Thread(target=_arret_garanti, name="ALIGN-Arret-Garanti", daemon=True).start()


RELEVE_VERIF_SEC = 30     # toutes les 30 s : un worker plus récent attend-il ? (GitHub n'a pas toujours transmis le SIGINT d'annulation)

def releve_en_attente(runs, mon_id):
    """Vrai si un run plus récent du worker ALIGN est en file / en cours : l'ancien doit s'arrêter LUI-MÊME pour sauver sa mémoire.
    Cause réelle constatée (13/11) : annulation douce jamais reçue → annulation forcée → mémoire non sauvée → doublons au redémarrage."""
    actifs = {"queued", "in_progress", "waiting", "pending", "requested"}
    return any(int(r.get("id") or 0) > mon_id and r.get("status") in actifs for r in runs or [])

def surveiller_releve():
    """Thread : demande l'arrêt propre (sauvegarde puis sortie) dès qu'un nouveau worker est lancé."""
    try:
        mon_id = int(os.environ.get("GITHUB_RUN_ID") or 0)
    except ValueError:
        mon_id = 0
    repo, jeton = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not mon_id or not repo or not jeton:
        return
    url = f"https://api.github.com/repos/{repo}/actions/workflows/align-bot.yml/runs?branch=main&per_page=10"
    while not SHUTDOWN_REQUESTED.is_set():
        time.sleep(RELEVE_VERIF_SEC)
        try:
            req = urllib.request.Request(url, headers={"Authorization": "Bearer " + jeton, "Accept": "application/vnd.github+json",
                                                       "User-Agent": "ALIGN-worker"})
            with urllib.request.urlopen(req, timeout=15) as rep_:
                runs = json.loads(rep_.read().decode("utf-8")).get("workflow_runs", [])
            if releve_en_attente(runs, mon_id):
                print("ALIGN_RELEVE_DETECTEE : arrêt propre + sauvegarde de la mémoire", flush=True)
                _demander_arret(0, None)
                return
        except Exception as ex:
            print("surveiller releve", type(ex).__name__, flush=True)

def un_tour(etat, chats):
    """Un tour complet : messages reçus, analyse BTC + Gold, envois, jauges, sauvegarde."""
    LANG_EN.clear(); LANG_EN.update(etat.get("en", []))
    MEMOIRE[:] = etat.get("memoire", [])
    if TOKEN:
        installer_menu(etat)
    demandes = []
    demandes_servies = set()
    if TOKEN:
        recevoir_updates_telegram(etat, chats, demandes)
        if SHUTDOWN_REQUESTED.is_set():
            return
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
        # Sécurité VIP (1 seule fois) : l'ancien lien d'invitation gratuit de la chaîne est révoqué.
        # Seul le lien d'abonnement payant (Stars) permet d'entrer : partager un lien ne donne jamais l'accès gratuit.
        if etat.get("canal") and not etat.get("lien_primaire_revoque_v1"):
            try:
                telegram("exportChatInviteLink", chat_id=etat["canal"])
                etat["lien_primaire_revoque_v1"] = time.time()
            except Exception as ex:
                print("révocation lien VIP", ex)
        notifier_securite_vip(etat)
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
    global DERNIER_ETAT
    DERNIER_ETAT = etat
    try:
        macro(etat)
    except Exception as ex:
        print("macro", ex)
    recevoir_updates_telegram(etat, chats, demandes)
    if SHUTDOWN_REQUESTED.is_set():
        return
    for nom_marche, pair in MARCHES.items():
        recevoir_updates_telegram(etat, chats, demandes)
        if SHUTDOWN_REQUESTED.is_set():
            return
        try:
            r = analyser(pair, etat.setdefault(nom_marche, {}).setdefault("pine", {}))
            recevoir_updates_telegram(etat, chats, demandes)
            if SHUTDOWN_REQUESTED.is_set():
                return
            r["tv_indicator_mtf"] = fetch_tv_mtf(pair)
            fusionne_lectures_tradingview(r)
        except Exception as ex:
            print(nom_marche, "erreur", ex)
            if TOKEN:
                notifier_erreur_technique(etat, f"analyse {nom_marche}")
            continue
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
        if nom_marche != "BTC" and not cme_ouvert(int(time.time())):
            # Marché FERMÉ (week-end / pause CME) : plus aucune alerte sur ce marché. Une seule annonce si la fermeture dure (> 2 h).
            reo = prochaine_ouverture_cme(time.time())
            if not cle.get("ferme_dit") and reo and reo - time.time() > 2 * 3600:
                cle["ferme_dit"] = True
                j_ = datetime.datetime.fromtimestamp(reo, PARIS)
                envois.append(taguer(f"🔒 {ICONE.get(nom_marche, '')} {nom_marche} : MARCHÉ FERMÉ\n😴 Je ne t'envoie plus rien sur ce marché\n"
                                     f"⏰ Réouverture : {['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'][j_.weekday()]} {j_.strftime('%H:%M')}", nom_marche))
            derniers[nom_marche] = r; DERNIERS[nom_marche] = r
            for index, (cid, mq) in enumerate(demandes):
                if mq in (None, nom_marche) and (index, nom_marche) not in demandes_servies:
                    envoyer_analyse_a(etat, cid, nom_marche, r, cle)
                    demandes_servies.add((index, nom_marche))
            continue
        cle["ferme_dit"] = False
        ferme = ""
        nouveaux = [taguer(x, nom_marche) for x in agent(nom_marche, r, cle, ferme)]
        live_annonces(etat, nom_marche, nouveaux)
        envois += nouveaux
        if TOKEN:
            envois += [taguer(x, nom_marche) for x in commentaires_ia_temps_reel(etat, nom_marche, r, cle, nouveaux)]
        recevoir_updates_telegram(etat, chats, demandes)
        if SHUTDOWN_REQUESTED.is_set():
            return
        if TOKEN and cle.get("trade") and not cle["trade"].get("auto_fait"):
            cle["trade"]["auto_fait"] = True
            trx = cle["trade"]
            t_ = ia(etat, "Le bot vient d'entrer en position selon le plan de l'indicateur. Analyse ce plan (stratégie, SL, TP1, TP2) : dis si tu le valides en bougies ou si tu le déconseilles (« je déconseille » + raison), sans jamais proposer d'autres niveaux, et rappelle de mettre le SL tout de suite. " + IA_TON_JEUNE,
                    dict(donnees_ia(nom_marche, r, cle), position={"sens": "LONG" if trx["d"] == 1 else "SHORT", "entrée": round(trx["e"], 2),
                                                                    "SL": round(trx["sl"], 2), "TP1": round(trx["tp1"], 2), "type": trx.get("src")}), premium=True)
            if t_:
                envois.append(taguer(f"🧠 L'IA ALIGN sur cette entrée — {ICONE.get(nom_marche, '')} {nom_marche}\n{compacter_ia(t_)}", nom_marche))
            entrer_inscrits(etat, nom_marche, cle["trade"], chats)
        if TOKEN:
            coach(etat, nom_marche, r, cle)
            if SHUTDOWN_REQUESTED.is_set():
                return
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
                t_ = ia(etat, "La position est terminée. Tire UNE leçon simple et utile pour la prochaine fois (pourquoi TP ou pourquoi SL). FORMAT : 4 lignes courtes maximum, une info par ligne, chaque ligne commence par un emoji, 12 mots maximum par ligne, aucun paragraphe ni conclusion.",
                        {"marché": nom_marche, "résultat %": round(gain, 2), "motif": motif, "profil": pr, "bilan de ce type": f"{w_}/{n_}"})
                if t_:
                    envois.append(taguer(f"🧠 La leçon de l'IA ALIGN\n{compacter_ia(t_)}", nom_marche))
        derniers[nom_marche] = r; DERNIERS[nom_marche] = r
        synchroniser_veille_auto(etat, nom_marche, r)
        notifier_clotures(etat, nom_marche, r, cle)
        # Veille « je surveille » marché par marché remplacée par le RADAR unique (radar_tick, après la boucle des marchés).
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
        for index, (cid, mq) in enumerate(demandes):
            if mq in (None, nom_marche) and (index, nom_marche) not in demandes_servies:
                envoyer_analyse_a(etat, cid, nom_marche, r, cle)
                demandes_servies.add((index, nom_marche))
        print(texte_etat(nom_marche, r, vip=False), "\n")      # journal du run PUBLIC (dépôt public) : jamais les niveaux VIP

    try:
        if TOKEN:
            alertes_courtes(etat, chats, derniers)
    except Exception as ex:
        print("alertes courtes", type(ex).__name__, ex)
    try:
        if TOKEN:
            radar_tick(etat, chats, derniers)      # remplace « OÙ TE CONCENTRER » + la veille : UN message édité sur place
    except Exception as ex:
        print("radar", type(ex).__name__, ex)
    try:
        publier_live(etat, derniers)
    except Exception as ex:
        print("live public", type(ex).__name__)

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
            menu_canal_vip(etat)
        # Rappel de partage : côté gratuit seulement (jamais dans la chaîne VIP), 1 fois au jour prévu
        if TOKEN and partage_du(etat):
            txt, kb = message_partage(etat)
            for cid in destinataires_gratuits(etat):
                _envoi_sur(cid, text=txt, reply_markup=kb)
    except Exception as ex:
        print("annonces", ex)
    if TOKEN:
        for t in envois:
            texte, clavier = (t if isinstance(t, tuple) else (t, None))
            if doublon_message(etat, texte):
                print("anti-répétition : message identique ignoré —", texte.splitlines()[0][:80])
                continue
            for cid in destinataires_message(etat, chats, texte):
                if cid != str(etat.get("canal") or "") and etat.get("marches_par_chat", {}).get(str(cid)) is not None:
                    texte_cid = filtrer_texte_par_marches(texte, marches_choisis(etat, cid))
                    if not texte_cid:
                        continue                                        # ne concerne aucun de ses marchés
                else:
                    texte_cid = texte
                try:
                    if cid == etat.get("canal"):
                        # Chaîne VIP : pas de clavier possible dans une chaîne → boutons sous le message (ils ouvrent le bot)
                        txt = texte.replace("\n\n📍 Si tu prends cette position, active son suivi avec le bouton ci-dessous.", "")
                        telegram("sendMessage", chat_id=cid, text=txt, reply_markup=boutons_canal(etat, texte))
                    elif clavier:
                        telegram("sendMessage", chat_id=cid, text=texte_cid, reply_markup=clavier)
                    else:
                        telegram("sendMessage", chat_id=cid, text=texte_cid)
                except Exception as ex:
                    print("envoi", cid, ex)
                    if "403" in str(ex) and cid not in proprio(etat):
                        chats.discard(cid)   # l'abonné a bloqué le bot
            # Visiteurs non abonnés : teaser (positions masquées + bouton de paiement)
            alerte_gratuite_preparation(etat, texte)
            envoyer_prospects(etat, texte, bool(re.search(r"(?<!\w)\d{1,3}(?: \d{3})*\.\d+", texte)) and (est_entree(texte) or "JE PRÉPARE" in texte), clavier)
        for nom_marche in MARCHES:
            if nom_marche in derniers:
                maj_jauge(etat, nom_marche, derniers[nom_marche], etat[nom_marche], set() if etat.get("canal") else chats, etat.get("canal"))
                try:
                    maj_chronos(etat, nom_marche, derniers[nom_marche])
                except Exception as ex:
                    print("chronos", ex)
    # Dernière relève : une demande reçue pendant le calcul du second marché ne reste pas en attente.
    recevoir_updates_telegram(etat, chats, demandes)
    if SHUTDOWN_REQUESTED.is_set():
        return
    for index, (cid, mq) in enumerate(demandes):
        marches_a_traiter = tuple(MARCHES) if mq is None else (mq,)
        for marche in marches_a_traiter:
            if marche in DERNIERS and (index, marche) not in demandes_servies:
                envoyer_analyse_a(etat, cid, marche, DERNIERS[marche], etat.get(marche, {}))
                demandes_servies.add((index, marche))
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


def restaurer_cooldowns_telegram(etat, maintenant=None):
    """Un nouveau worker respecte le blocage 429 du précédent au lieu de le prolonger."""
    maintenant = time.time() if maintenant is None else float(maintenant)
    for cle, fin in (etat.get("telegram_retry_until") or {}).items():
        if str(cle) == "__global__":
            continue      # ancien blocage commun : il rendait le bot sourd, on ne le restaure plus
        try:
            if float(fin) > maintenant:
                TELEGRAM_RETRY_UNTIL[str(cle)] = max(float(TELEGRAM_RETRY_UNTIL.get(str(cle), 0)), float(fin))
        except (TypeError, ValueError):
            continue


def _sauver_etat_sous_verrou(etat, chats=None):
    """Écriture atomique : un arrêt du runner ne laisse pas un state.json tronqué."""
    if chats is not None:
        etat["chats"] = sorted(str(x) for x in chats)
    etat["schema_version"] = STATE_SCHEMA_VERSION
    maintenant = time.time()
    etat["telegram_retry_until"] = {k: v for k, v in TELEGRAM_RETRY_UNTIL.items() if float(v) > maintenant}
    journal_vider_sortants(etat)
    dossier = os.path.dirname(os.path.abspath(ETAT_FICHIER))
    temporaire = ETAT_FICHIER + ".tmp"
    with open(temporaire, "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False, separators=(",", ":"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporaire, ETAT_FICHIER)

DEMARRE_T = time.time()          # heure de démarrage du worker (commande /statut)

def sauver_etat(etat, chats=None):
    """Empêche le worker du chronomètre de modifier l'état pendant l'écriture atomique."""
    with CHRONO_LOCK:
        etat["sauve_t"] = int(time.time())          # lu par /statut : la mémoire est-elle bien écrite ?
        return _sauver_etat_sous_verrou(etat, chats)


def main():
    etat = charger_etat()
    LANG_EN.clear(); LANG_EN.update(etat.get("en", []))
    MEMOIRE[:] = etat.get("memoire", [])
    maintenant_paris = datetime.datetime.now(PARIS)
    print(f"ALIGN_TZ=Europe/Paris LOCAL_NOW={maintenant_paris.isoformat()} UTC_NOW={datetime.datetime.now(datetime.timezone.utc).isoformat()}", flush=True)
    chats = set(etat.get("chats", []))
    if os.environ.get("TELEGRAM_CHAT_ID"):
        chats.add(os.environ["TELEGRAM_CHAT_ID"].strip())
    if "proprio" not in etat:           # les téléphones déjà inscrits = le propriétaire (accès gratuit et permanent)
        etat["proprio"] = sorted(chats)
    if POSITIONS_GRATUITES and etat.get("prospects"):
        chats |= set(etat["prospects"]); etat["prospects"] = []

    restaurer_cooldowns_telegram(etat)
    _ETAT_COURANT["etat"] = etat
    _ETAT_COURANT["chats"] = chats

    signal.signal(signal.SIGINT, _demander_arret)
    signal.signal(signal.SIGTERM, _demander_arret)
    # Un seul poller lit getUpdates. Il accuse réception des callbacks et répond aux
    # menus simples pendant que le thread principal calcule les marchés.
    if TOKEN:
        threading.Thread(target=boucle_polling_telegram, args=(etat, chats),
                         name="ALIGN-Telegram-Poller", daemon=True).start()
        threading.Thread(target=boucle_chronos, args=(etat,),
                         name="ALIGN-Telegram-Chrono", daemon=True).start()
        threading.Thread(target=surveiller_releve, name="ALIGN-Releve", daemon=True).start()

    debut = time.time()
    while not SHUTDOWN_REQUESTED.is_set():
        try:
            un_tour(etat, chats)
        except Exception as ex:
            print("tour", ex)
        if SHUTDOWN_REQUESTED.is_set():
            break
        prochain = time.time() + PAUSE_SEC
        while TOKEN and time.time() < min(prochain, debut + DUREE_SEC) and not SHUTDOWN_REQUESTED.is_set():
            demandes = []
            recevoir_updates_telegram(etat, chats, demandes)
            for marche, derniere in list(DERNIERS.items()):
                try:
                    maj_chronos(etat, marche, derniere)
                except Exception as ex:
                    print("tick chrono", marche, ex)
            for cid, mq in demandes:
                envoyer_analyse(cid, etat, mq)
            sauver_etat(etat, chats)
            time.sleep(0.5)
        if SHUTDOWN_REQUESTED.is_set() or time.time() >= debut + DUREE_SEC:
            break
        if not TOKEN:
            time.sleep(max(0, prochain - time.time()))
    TELEGRAM_POLL_STOP.set()
    sauver_etat(etat, chats)
    print("ALIGN_STATE_SAVED_ON_SHUTDOWN", flush=True)

if __name__ == "__main__":
    main()
