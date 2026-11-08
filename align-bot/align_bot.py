#!/usr/bin/env python3
"""ALIGN MTF BOT — même logique que l'indicateur TradingView ALIGN MTF PRO.
Prix gratuits Kraken (BTC = XBTUSD, Gold = PAXGUSD), signaux envoyés sur Telegram.
Tourne toutes les 5 minutes (GitHub Actions). Aucune dépendance externe."""
import json, os, time, urllib.request, urllib.error, urllib.parse, datetime
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
CLAVIER = json.dumps({"keyboard": [[{"text": "📊 Analyse"}], [{"text": "✅ Je suis rentré"}, {"text": "❌ Non"}]],
                      "resize_keyboard": True, "is_persistent": True})
PRIX_STARS = int(os.environ.get("PRIX_STARS", "500"))   # abonnement mensuel de la chaîne VIP (≈ 10 €)
ECOUTE_SEC = int(os.environ.get("ECOUTE_SEC", "200"))   # le bot reste à l'écoute entre deux analyses

def envoyer_analyse(cid):
    for nom_marche, pair in MARCHES.items():
        try:
            telegram("sendMessage", chat_id=cid, text=texte_etat(nom_marche, analyser(pair)), reply_markup=CLAVIER)
        except Exception as ex:
            print("analyse", ex)

def repondre(etat, cid, oui, mk=None):
    """Oui / Non sur le trade en attente de réponse (ou sur le marché du bouton cliqué)."""
    cands = [m for m in MARCHES if etat.get(m, {}).get("trade") and (mk is None or m == mk)]
    cands = [m for m in cands if cid not in etat[m]["trade"].get("qui", {})] or cands
    if not cands:
        telegram("sendMessage", chat_id=cid, text="Aucun trade en cours pour le moment. Je te préviens dès qu'il y a une entrée.", reply_markup=CLAVIER)
        return
    m = cands[0]; etat[m]["trade"].setdefault("qui", {})[cid] = oui
    telegram("sendMessage", chat_id=cid, reply_markup=CLAVIER,
             text=(f"👊 OK, on est dedans ensemble sur {m}. Je te coache jusqu'au TP." if oui else f"👌 OK, pas de position sur {m}. J'attends le prochain setup."))

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
            if not autorise(etat, str(cb["message"]["chat"]["id"]), cb["from"]["id"]):
                continue
            choix, _, mk = cb.get("data", "").partition(":")
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
            refuser(etat, cid); chats.discard(cid)
            continue
        if cid not in chats:
            chats.add(cid)
            telegram("sendMessage", chat_id=cid, text="✅ ALIGN MTF BOT activé. Signaux BTC et Gold ici.\nUtilise les boutons en bas.", reply_markup=CLAVIER)
        txt = msg.get("text", "").lower().replace("é", "e")
        if "analyse" in txt or "etat" in txt:
            demandes.append(cid)
        elif "rentre" in txt or txt.strip() == "oui":
            repondre(etat, cid, True)
        elif "non" in txt:
            repondre(etat, cid, False)
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
    return cid in proprio(etat) or membre(etat, user_id)

def refuser(etat, cid):
    lien = etat.get("lien")
    _envoi_sur(cid, text=("🔒 Les signaux ALIGN sont réservés aux abonnés VIP.\n"
             + (f"Abonnement mensuel : {lien}\nUne fois abonné, reviens ici et appuie sur /start." if lien else "Ouverture des abonnements très bientôt.")))

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
    """Texte de la jauge (un seul message mis à jour toutes les 5 min), ou None."""
    tr = cle.get("trade"); p = r["m1"][-1]["c"]; d = r["confirme"]
    if tr and (canal or tr.get("qui", {}).get(cid)):
        e, t1, t2 = tr["e"], tr["tp1"], tr["tp2"]; cible = t2 if tr["statut"] == "tp1" else t1
        pct = 100 * tr["d"] * (p - e) / max(abs(cible - e), 1e-9)
        vit = abs(r["m1"][-1]["c"] - r["m1"][-31]["c"]) / 30 if len(r["m1"]) > 31 else 0   # vitesse moyenne / minute
        reste = abs(cible - p) / vit if vit > 0 else None
        return (f"📍 {m} en position {'LONG' if tr['d'] == 1 else 'SHORT'}\n{'TP2' if tr['statut'] == 'tp1' else 'TP1'} : {barre_pct(pct)}\n"
                f"Prix {px(p)} → objectif {px(cible)}" + (f" • ≈ {reste:.0f} min" if reste and reste < 600 else ""))
    if not tr and d and cle.get("ordre"):
        o = cle["ordre"]; dep = abs(o["sl"] - o["e"]) * 3
        pct = 100 * (1 - min(abs(p - o["e"]) / max(dep, 1e-9), 1))
        vit = abs(r["m1"][-1]["c"] - r["m1"][-31]["c"]) / 30 if len(r["m1"]) > 31 else 0
        reste = abs(p - o["e"]) / vit if vit > 0 else None
        return (f"⏱ {m} {'▲ ACHAT' if d == 1 else '▼ VENTE'} visé à {px(o['e'])}\n{barre_pct(pct)}\nPrix {px(p)} • RSI 5m {r['r5'][-1]:.0f}"
                + (f" • arrivée ≈ {reste:.0f} min" if reste and reste < 300 else ""))
    return None

def maj_jauge(m, r, cle, chats, canal=None):
    for cid in list(chats) + ([canal] if canal else []):
        txt = jauge(m, r, cle, cid, cid == canal)
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

def annonce_proche(etat, maintenant):
    return any(abs(e["t"] - maintenant) <= 15 * 60 for e in etat.get("cal", {}).get("ev", []))

# ───────── Agent : suit le trade du début à la fin ─────────
def fmt_trade(m, tr, p=None):
    """Carte visuelle pour débutant : couleurs + échelle des prix dessinée de haut en bas."""
    d = tr["d"]
    tete = ("🟩🟩🟩  ACHAT " if d == 1 else "🟥🟥🟥  VENTE ") + m + ("  🟩🟩🟩" if d == 1 else "  🟥🟥🟥")
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
    return (f"{tete}\n"
            f"⏱ Mets ton graphique en 15 minutes\n\n"
            f"{echelle}\n\n"
            f"🟨 Entre entre {px(za)} et {px(zb)}\n"
            f"🛑 Stop {px(tr['sl'])} ({bougie})\n"
            f"💰 TP1 {px(tr['tp1'])} → sécurise, stop à l'entrée\n"
            f"🏁 TP2 {px(tr['tp2'])}\n\n"
            f"Risque {barres(risque)}\nGain   {barres(gain)}  (x{tr['rr']:.1f})")

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
        res1h = [v for v, n in r["grosses"] if n in ("1h", "4h") and e < v < e + 3 * a]
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
        sup1h = [v for v, n in r["grosses"] if n in ("1h", "4h") and e - 3 * a < v < e]
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
        bloque = (d == -1 and (r["posD"] <= 0.15 or (r["posW"] <= 0.15 and r["posD"] <= 0.35))) or \
                 (d == 1 and (r["posD"] >= 0.85 or (r["posW"] >= 0.85 and r["posD"] >= 0.65)))
        o = point_entree(r, d, p)
        if cle.get("aligne") != d:
            cle["aligne"] = d; cle["prep"] = False
            if bloque:
                out.append(f"🧭 {m} aligné {'▲' if d == 1 else '▼'} sur 15m/1h/4h, MAIS prix {zone_txt(r['posD'])} Daily / {zone_txt(r['posW'])} Weekly.\n"
                           f"⛔ Pas de {'long' if d == 1 else 'short'} ici : risque de rebond. J'attends un meilleur prix.")
            else:
                cle["ordre"] = o
                out.append(f"🔔 PRÉPARE-TOI — {m} {'monte' if d == 1 else 'descend'} sur 15m, 1h et 4h ✅✅✅\n"
                           f"⏳ N'entre PAS encore : j'attends que le prix vienne dans la zone 🟨\n\n"
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
            out.append(f"🟡🟡 BIENTÔT — {m} approche de la zone 🟨\n👉 Prix {px(p)}  →  zone {px(o.get('za', o['e']))} – {px(o.get('zb', o['e']))}\n📲 Prépare ton ordre {'ACHAT 🟩' if d == 1 else 'VENTE 🟥'}, stop {px(o['sl'])}\n⏳ N'entre pas avant mon signal 🟢")
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
                out.append((f"🟢🟢🟢 ENTRE MAINTENANT — {m} 🟢🟢🟢\n✅ Prix dans la zone 🟨\n✅ RSI {'trop bas (rebond)' if d == 1 else 'trop haut (baisse)'} sur {', '.join(['5m'] + [u + 'm' for u in petites])}\n✅ Confirmé en 1h\n\n{fmt_trade(m, tr, p)}{ferme}\n\nTu es rentré ?", boutons(m)))
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
            if not any(tr.get("qui", {}).values()):
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
    if "proprio" not in etat:           # les téléphones déjà inscrits = le propriétaire (accès gratuit et permanent)
        etat["proprio"] = sorted(chats)

    # Messages reçus et boutons
    debut = time.time()
    demandes = []
    if TOKEN:
        demandes = traiter(etat, chats, telegram("getUpdates", offset=etat.get("offset", 0), timeout=0).get("result", []))
        if etat.get("clavier") != 1:
            for cid in chats:
                telegram("sendMessage", chat_id=cid, text="🆕 Boutons activés : 📊 Analyse • ✅ Je suis rentré • ❌ Non", reply_markup=CLAVIER)
            etat["clavier"] = 1
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
            for cid in [c for c in chats if c not in proprio(etat)]:
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
        ferme = "" if nom_marche == "BTC" or cme_ouvert(r["t"]) else "\n⚠️ Futures CME fermés en ce moment (Topstep) : signal à titre indicatif."
        envois += agent(nom_marche, r, cle, ferme)
        derniers[nom_marche] = r
        cle["vu"] = r["t"]
        for cid in demandes:
            telegram("sendMessage", chat_id=cid, text=texte_etat(nom_marche, r), reply_markup=CLAVIER)
        print(texte_etat(nom_marche, r), "\n")

    try:
        envois += annonces_et_sessions(etat, int(time.time()), derniers)
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
        for cid in traiter(etat, chats, maj):
            envoyer_analyse(cid)
    etat["chats"] = sorted(chats)
    json.dump(etat, open(ETAT_FICHIER, "w"))

if __name__ == "__main__":
    main()
