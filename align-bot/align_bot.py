#!/usr/bin/env python3
"""ALIGN MTF BOT — même logique que l'indicateur TradingView ALIGN MTF PRO.
Prix gratuits Kraken (BTC = XBTUSD, Gold = PAXGUSD), signaux envoyés sur Telegram.
Tourne toutes les 15 minutes (GitHub Actions). Aucune dépendance externe."""
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
    # Confirmation GROSSES UT : 1h, 2h, 4h, Daily (au moins 3 sur 4 dans le même sens, aucune contre)
    gros = dirs[7:]
    confirme = 1 if gros.count(1) >= 3 and -1 not in gros else -1 if gros.count(-1) >= 3 and 1 not in gros else 0
    return dict(m1=m1, confirme=confirme, atr=a, t=b[-1]["t"], prix=cl, dirs=dirs, sqzs=sqzs, rsis=rsis, bull=bull, bear=bear, comp=comp, rsiOB=rsiOB, rsiOS=rsiOS,
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
    if d:
        lignes += ["", texte_plan(nom_marche, r, r["plan"], d)]
    return "\n".join(lignes)

def telegram(methode, **params):
    url = f"https://api.telegram.org/bot{TOKEN}/{methode}"
    return http_json(url, urllib.parse.urlencode(params).encode())

# ───────── Agent : suit le trade du début à la fin ─────────
def fmt_trade(m, tr):
    sens = "▲ LONG (achat)" if tr["d"] == 1 else "▼ SHORT (vente)"
    return (f"{sens} {m}\nEntrée : {px(tr['e'])}\nTP1 : {px(tr['tp1'])} ({tr['n1']})\nTP2 : {px(tr['tp2'])} ({tr['n2']})\n"
            f"Stop : {px(tr['sl'])}\nGain/risque ≈ {tr['rr']:.1f}")

def agent(m, r, cle, ferme):
    """Renvoie la liste des messages à envoyer pour ce marché."""
    out = []
    tr = cle.get("trade")
    depuis = cle.get("t1m", 0)
    bougies = [x for x in r["m1"] if x["t"] > depuis] or r["m1"][-1:]
    cle["t1m"] = r["m1"][-1]["t"]
    p = r["m1"][-1]["c"]
    hi = max(x["h"] for x in bougies); lo = min(x["l"] for x in bougies)

    # Pas de trade en cours : on cherche un setup CONFIRMÉ par les grosses UT
    if not tr:
        d = r["confirme"]
        if d and r["dirPlan"] == d:
            pl = r["planH"] if d == 1 else r["planB"]
            avance = d * (p - pl["e"])  # > 0 = le prix a déjà dépassé l'entrée dans le bon sens
            if pl["rr"] >= 1.5 and avance < 0.25 * abs(pl["tp1"] - pl["e"]):
                tr = dict(d=d, e=pl["e"], sl=pl["sl"], tp1=pl["tp1"], tp2=pl["tp2"], n1=pl["n1"], n2=pl["n2"], rr=pl["rr"],
                          statut="attente", cree=r["t"], proche=False, encore=0)
                cle["trade"] = tr
                out.append(f"🧭 SETUP CONFIRMÉ — {m}\nLes grosses UT (1h, 2h, 4h, Daily) sont alignées {'à la HAUSSE' if d == 1 else 'à la BAISSE'}.\n"
                           f"Je surveille le point d'entrée, ne rentre pas encore.\n\n{fmt_trade(m, tr)}\n\n{barre(r)}{ferme}")
        return out

    d, e, sl, t1, t2 = tr["d"], tr["e"], tr["sl"], tr["tp1"], tr["tp2"]
    risque = abs(e - sl)
    touche_e = (lo <= e) if d == 1 else (hi >= e)
    touche_sl = (lo <= sl) if d == 1 else (hi >= sl)
    touche_t1 = (hi >= t1) if d == 1 else (lo <= t1)
    touche_t2 = (hi >= t2) if d == 1 else (lo <= t2)
    progres = d * (p - e) / max(abs(t1 - e), 1e-9)   # 0 = sur l'entrée, 1 = sur le TP1

    if tr["statut"] == "attente":
        if r["confirme"] == -d:
            out.append(f"🚫 SETUP ANNULÉ — {m}\nLes grosses UT ont changé de sens. On ne prend pas ce trade.")
            cle.pop("trade"); return out
        if r["t"] - tr["cree"] > 6 * 3600:
            out.append(f"⌛ SETUP EXPIRÉ — {m}\nLe prix n'est pas venu sur l'entrée en 6 h. On attend le prochain.")
            cle.pop("trade"); return out
        if touche_e and not touche_sl:
            tr["statut"] = "entree"
            out.append(f"✅ TU PEUX RENTRER — {m}\nLe prix est sur le point d'entrée {px(e)} (prix actuel {px(p)}).\n\n{fmt_trade(m, tr)}{ferme}")
        elif progres > 0.35:
            out.append(f"⛔ TROP TARD — {m}\nLe prix est parti vers le TP sans repasser par l'entrée. Ne cours pas après, on attend le prochain setup.")
            cle.pop("trade"); return out
        elif not tr["proche"] and abs(p - e) <= max(0.5 * risque, r["atr"] * 0.6):
            tr["proche"] = True
            out.append(f"⏳ PRÉPARE-TOI — {m}\nLe prix ({px(p)}) arrive sur le point d'entrée {px(e)}.\nPrépare ton ordre : {'achat' if d == 1 else 'vente'}, stop {px(sl)}, TP1 {px(t1)}.")
        return out

    if tr["statut"] == "entree":
        if touche_sl:
            out.append(f"❌ STOP TOUCHÉ — {m}\nLe stop {px(sl)} a été touché. Trade terminé, on attend le prochain setup confirmé.")
            cle.pop("trade"); return out
        if touche_t1:
            tr["statut"] = "tp1"
            out.append(f"🎯 TP1 ATTEINT — {m} ({px(t1)})\nSécurise une partie et remonte ton stop au point d'entrée {px(e)} (0 risque).\n"
                       f"Prochain objectif : TP2 {px(t2)} ({tr['n2']}). Patience, on laisse courir.")
            return out
        if progres < 0.25:
            if tr["encore"] < 2 and r["t"] - cle.get("dernier_encore", 0) >= 3600:
                tr["encore"] += 1; cle["dernier_encore"] = r["t"]
                out.append(f"👍 TU PEUX ENCORE RENTRER — {m}\nPrix {px(p)}, encore proche de l'entrée {px(e)}. Stop {px(sl)}, TP1 {px(t1)}.")
        elif not tr.get("tard"):
            tr["tard"] = True
            out.append(f"⛔ TROP TARD POUR RENTRER — {m}\nLe prix ({px(p)}) est déjà loin de l'entrée. Si tu es dedans, garde le plan.\n"
                       f"Patience : prochain objectif TP1 {px(t1)}, puis TP2 {px(t2)}.")
        return out

    if tr["statut"] == "tp1":
        if touche_t2:
            out.append(f"🏆 TP2 ATTEINT — {m} ({px(t2)})\nObjectif maximum atteint. Trade terminé, bravo. J'attends le prochain setup confirmé.")
            cle.pop("trade"); return out
        if (lo <= e) if d == 1 else (hi >= e):
            out.append(f"↩️ RETOUR AU POINT D'ENTRÉE — {m}\nTon stop remonté à l'entrée sort à 0. Le TP1 est déjà sécurisé.")
            cle.pop("trade"); return out
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
            msg = u.get("message") or {}
            cid = str(msg.get("chat", {}).get("id", ""))
            if cid:
                if cid not in chats:
                    chats.add(cid)
                    telegram("sendMessage", chat_id=cid, text="✅ ALIGN MTF BOT activé. Tu recevras les signaux BTC et Gold ici.\nÉcris « etat » pour voir l'analyse du moment.")
                if "etat" in (msg.get("text", "").lower().replace("é", "e")):
                    demandes.append(cid)

    envois = []
    for nom_marche, pair in MARCHES.items():
        try:
            r = analyser(pair)
        except Exception as ex:
            print(nom_marche, "erreur", ex); continue
        cle = etat.setdefault(nom_marche, {})
        ferme = "" if nom_marche == "BTC" or cme_ouvert(r["t"]) else "\n⚠️ Futures CME fermés en ce moment (Topstep) : signal à titre indicatif."
        envois += agent(nom_marche, r, cle, ferme)
        cle["vu"] = r["t"]
        for cid in demandes:
            telegram("sendMessage", chat_id=cid, text=texte_etat(nom_marche, r))
        print(texte_etat(nom_marche, r), "\n")

    if TOKEN:
        for t in envois:
            for cid in chats:
                telegram("sendMessage", chat_id=cid, text=t)
    print(f"{len(envois)} signal(s) envoyé(s) à {len(chats)} téléphone(s)")
    etat["chats"] = sorted(chats)
    json.dump(etat, open(ETAT_FICHIER, "w"))

if __name__ == "__main__":
    main()
