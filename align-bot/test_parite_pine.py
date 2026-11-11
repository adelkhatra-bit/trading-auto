"""Test de parité : logique Python du bot  <->  indicateur Pine « ALIGN MTF PRO (Inside) » v24
(fichier de référence en lecture seule : pine/ALIGN_MTF_PRO_v24.pine).

PRINCIPE
- `PineRef` est une transcription indépendante du Pine, dans l'ordre du script (tableau `niveaux` à 16 entrées,
  boucles `for k`, variables d'état `var` mises à jour barre par barre à la clôture 15 min).
- Le bot (`analyser_avec_memoire`) est rejoué sur les mêmes bougies : un appel PENDANT la bougie, un appel APRÈS sa clôture.
- Tout est comparé : 11 unités (sens / compression / RSI), biais, sens stable, stratégie, score, plan figé, zone verte, trait de décision,
  RETOURNEMENT, voyants ↩.

SOURCES DE BOUGIES
- Toujours : bougies SIMULÉES (marche aléatoire à graine fixe) -> « simulé ».
- Si ALIGN_PARITE_RESEAU=1 (CI GitHub, réseau ouvert) : vraies bougies Kraken -> « réel ». Sans réseau le test est SAUTÉ (pas de faux vert).
"""
import os
import random
import unittest

import align_bot as ab

MIN_ALIGN, MIN_SQZ, MARGE_ATR, GAIN_MIN = 8, 4, 0.5, 1.5            # réglages du Pine
POIDS = [1.0, 1.0, 1.0, 1.0, 2.0, 2.0, 2.0, 3.0, 3.0, 4.0, 5.0]
NOMS_NIV = ["15m"] * 4 + ["1h"] * 4 + ["4h"] * 4 + ["Daily"] * 4


# ───────────────────────── port Pine (ta.*) ─────────────────────────
def t_ema(x, n):
    out, e = [], None
    for i, v in enumerate(x):
        if v is None:
            out.append(None); continue
        if e is None:
            valid = [y for y in x[:i + 1] if y is not None]
            if len(valid) == n:
                e = sum(valid) / n
        else:
            e = (2 / (n + 1)) * v + (1 - 2 / (n + 1)) * e
        out.append(e)
    return out


def t_rma(x, n):
    out, r = [], None
    for i, v in enumerate(x):
        if v is None:
            out.append(None); continue
        if r is None:
            valid = [y for y in x[:i + 1] if y is not None]
            if len(valid) == n:
                r = sum(valid) / n
        else:
            r = (r * (n - 1) + v) / n
        out.append(r)
    return out


def t_sma(x, n, i):
    return None if i < n - 1 else sum(x[i - n + 1:i + 1]) / n


def t_stdev(x, n, i):
    if i < n - 1:
        return None
    w = x[i - n + 1:i + 1]; m = sum(w) / n
    return (sum((v - m) ** 2 for v in w) / n) ** 0.5


def t_atr(bars, n):
    tr = []
    for i, b in enumerate(bars):
        if i == 0:
            tr.append(b["h"] - b["l"])           # Pine : TR de la 1re barre = high - low
        else:
            pc = bars[i - 1]["c"]
            tr.append(max(b["h"] - b["l"], abs(b["h"] - pc), abs(b["l"] - pc)))
    return t_rma(tr, n)


def t_rsi(c, n=14):
    ch = [None] + [c[i] - c[i - 1] for i in range(1, len(c))]            # Pine : change() = na sur la 1re barre
    up = [None if v is None else max(v, 0.0) for v in ch]
    dn = [None if v is None else max(-v, 0.0) for v in ch]
    ru, rd = t_rma(up, n), t_rma(dn, n)
    return [None if u is None or d is None else (100.0 if d == 0 else 100 - 100 / (1 + u / d)) for u, d in zip(ru, rd)]


def f_etat(bars):
    """f_etat() du Pine -> (d, sqz, rsi) sur la dernière barre."""
    c = [b["c"] for b in bars]
    i = len(c) - 1
    ef, es = t_ema(c, 20)[i], t_ema(c, 50)[i]
    d = 1 if c[i] > ef and ef > es else -1 if c[i] < ef and ef < es else 0
    basis, dev = t_sma(c, 20, i), 2.0 * t_stdev(c, 20, i)
    kc, rng = t_ema(c, 20)[i], 1.5 * t_atr(bars, 20)[i]
    sqz = (basis + dev) < (kc + rng) and (basis - dev) > (kc - rng)
    return d, 1 if sqz else 0, t_rsi(c)[i]


def f_niv(bars):
    """f_niv() : valuewhen des pivots (5,5) -> [rA, sA, rB, sB]."""
    ph, pl = [], []
    for j in range(5, len(bars)):                                   # pivot confirmé à la barre j, centre = j-5
        ctr = j - 5
        fen = bars[ctr - 5:ctr + 6] if ctr - 5 >= 0 else None
        if fen is None:
            continue
        if bars[ctr]["h"] == max(x["h"] for x in fen):
            ph.append(bars[ctr]["h"])
        if bars[ctr]["l"] == min(x["l"] for x in fen):
            pl.append(bars[ctr]["l"])
    g = lambda arr, k: arr[-1 - k] if len(arr) > k else None
    return [g(ph, 0), g(pl, 0), g(ph, 1), g(pl, 1)]


def linreg0(y):
    n = len(y); xm = (n - 1) / 2; ym = sum(y) / n
    b = sum((i - xm) * (v - ym) for i, v in enumerate(y)) / sum((i - xm) ** 2 for i in range(n))
    return ym + b * (n - 1 - xm)


class PineRef:
    """Transcription du script Pine pour une vue 15 min. L'état `var` vit dans l'objet."""

    def __init__(self, S):
        self.S = S
        self.dirStable = 0; self.ent = self.tp1 = self.tp2 = self.sl = None
        self.dirFig = 0; self.stratFig = ""; self.retDir = 0; self.retAge = 0
        self.prev_sqz = 0; self.init = False
        self.n1 = self.n2 = ""

    def ut_series(self, m15):
        S = self.S
        return [S["m1"], ab.regrouper(S["m1"], 3, 60), S["m5"], ab.regrouper(S["m5"], 2, 300), m15, S["m30"],
                ab.regrouper(m15, 3, 900), S["h1"], ab.regrouper(S["h1"], 2, 3600), S["h4"], S["d1"]]

    def barre(self, m15):
        """Valeurs « live » à la clôture de la dernière barre de m15 (aucune mise à jour d'état)."""
        S = self.S
        v = {}
        et = [f_etat(b) for b in self.ut_series(m15)]
        dirs = [e[0] for e in et]; sqzs = [e[1] for e in et]; rsis = [e[2] if e[2] is not None else 50 for e in et]
        bull = bear = comp = rsiOB = rsiOS = 0
        sw = ts = rs = court = longT = 0.0
        for i in range(11):
            dv, w = dirs[i], POIDS[i]
            bull += dv == 1; bear += dv == -1; comp += sqzs[i]
            sw += w; ts += w * dv; rs += w * (rsis[i] - 50) / 50
            court += dv if i <= 4 else 0; longT += dv if i >= 8 else 0
            rsiOB += rsis[i] >= 70; rsiOS += rsis[i] <= 30
        c = [b["c"] for b in m15]
        rC_arr = t_rsi(c); rC = rC_arr[-1]
        rsiSig = t_ema([x if x is not None else None for x in rC_arr], 9)
        cu = lambda a, b_, i, lvl=None: None
        def crossover(x, y, i):    # x,y : listes ou niveaux
            gx = x[i] if isinstance(x, list) else x; gx1 = x[i - 1] if isinstance(x, list) else x
            gy = y[i] if isinstance(y, list) else y; gy1 = y[i - 1] if isinstance(y, list) else y
            return gx > gy and gx1 <= gy1
        i = len(c) - 1
        rsiAchat = (crossover(rC_arr, rsiSig, i) and rC < 50) or crossover(rC_arr, 30, i) or crossover(rC_arr, 50, i)
        rsiVente = (crossover(rsiSig, rC_arr, i) and rC > 50) or crossover(70, rC_arr, i) or crossover(50, rC_arr, i)
        def mom_at(j):
            hh = max(x["h"] for x in m15[j - 19:j + 1]); ll = min(x["l"] for x in m15[j - 19:j + 1])
            sm = sum(c[j - 19:j + 1]) / 20
            ys = []
            for k in range(j - 19, j + 1):
                h2 = max(x["h"] for x in m15[k - 19:k + 1]); l2 = min(x["l"] for x in m15[k - 19:k + 1])
                ys.append(c[k] - (((h2 + l2) / 2) + sum(c[k - 19:k + 1]) / 20) / 2)
            return linreg0(ys)
        mom, mom1 = mom_at(i), mom_at(i - 1)
        momS = (1.0 if mom > mom1 else 0.4) if mom > 0 else (-1.0 if mom < mom1 else -0.4)
        sC = et[4][1]
        sC1 = f_etat(m15[:-1])[1]
        liberation = sC1 == 1 and sC == 0
        trendS = ts / sw
        rsiS = max(-1.0, min(1.0, rs / sw * 2))
        score = 0.45 * trendS + 0.30 * rsiS + 0.25 * momS
        sens = 1 if score > 0.15 else -1 if score < -0.15 else 0
        retHaut = court >= 3 and longT <= -1 and momS > 0
        retBas = court <= -3 and longT >= 1 and momS < 0
        # niveaux : tableau de 16 valeurs, ordre du Pine
        niveaux = f_niv(m15) + f_niv(S["h1"]) + f_niv(S["h4"]) + f_niv(S["d1"])
        atrC = t_atr(m15, 14)[-1]
        atr15 = t_atr(m15, 14)[-2]                      # ta.atr(14)[1]
        close, high, low, opn = m15[-1]["c"], m15[-1]["h"], m15[-1]["l"], m15[-1]["o"]
        # f_dessus / f_dessous (1er niveau seulement : c'est le seul utilisé ensuite)
        hau1 = None
        for k in range(12):
            val = niveaux[k]
            if val is not None and val > close + atrC * 0.3 and (hau1 is None or val < hau1[0]):
                hau1 = (val, NOMS_NIV[k])
        bas1 = None
        for k in range(12):
            val = niveaux[k]
            if val is not None and val < close - atrC * 0.3 and (bas1 is None or val > bas1[0]):
                bas1 = (val, NOMS_NIV[k])
        surR = hau1 is not None and high >= hau1[0] - atrC * MARGE_ATR and close < hau1[0]
        surS = bas1 is not None and low <= bas1[0] + atrC * MARGE_ATR and close > bas1[0]
        zBas0 = surR and (rC > 58 or rsiOB >= 3) and momS < 1.0 and close < opn
        zHaut0 = surS and (rC < 42 or rsiOS >= 3) and momS > -1.0 and close > opn
        zoneBas = zBas0 and not (zHaut0 and rC < 50)
        zoneHaut = zHaut0 and not zoneBas
        dirBrut = 1 if zoneHaut else -1 if zoneBas else 1 if longT >= 2 else -1 if longT <= -2 else 1 if retHaut else -1 if retBas else sens
        dW = f_etat(S["w1"])[0] if len(S["w1"]) >= 50 else 0
        v.update(dirs=dirs, sqzs=sqzs, rsis=rsis, bull=bull, bear=bear, comp=comp, sens=sens, dirBrut=dirBrut, niveaux=niveaux,
                 atrC=atrC, atr15=atr15, close=close, hau1=hau1, bas1=bas1, dW=dW, rsiAchat=rsiAchat, rsiVente=rsiVente,
                 liberation=liberation, mom=mom, rsiOB=rsiOB, rsiOS=rsiOS, longT=longT, zoneHaut=zoneHaut, zoneBas=zoneBas,
                 low10=min(x["l"] for x in m15[-10:]), high10=max(x["h"] for x in m15[-10:]),
                 d15=dirs[4], d60=dirs[7], vol=[x.get("v") for x in m15])
        return v

    # --- f_stopB / f_stopH / f_cible / f_plan, boucles k comme dans le Pine
    @staticmethod
    def f_plan(v, d, sMin, sMax, cMin, cMax):
        niv, atrC, close = v["niveaux"], v["atrC"], v["close"]
        r = None
        for k in range(sMin, sMax + 1):
            val = niv[k]
            if d == 1:
                if val is not None and val < close - atrC * 0.3 and (r is None or val > r):
                    r = val
            else:
                if val is not None and val > close + atrC * 0.3 and (r is None or val < r):
                    r = val
        if r is None:
            r = (v["bas1"][0] if v["bas1"] else close - 1.5 * atrC) if d == 1 else (v["hau1"][0] if v["hau1"] else close + 1.5 * atrC)
        sb = r
        swing = v["low10"] - atrC * 0.35 if d == 1 else v["high10"] + atrC * 0.35
        s = min(sb - atrC * 0.3, swing) if d == 1 else max(sb + atrC * 0.3, swing)
        eLim = sb + atrC * 0.3 if d == 1 else sb - atrC * 0.3
        e = min(close, max(eLim, s + atrC * 0.5)) if d == 1 else max(close, min(eLim, s - atrC * 0.5))
        aP = max(atrC, v["atr15"] if v["atr15"] is not None else atrC)
        e = min(e, s + aP * 1.5) if d == 1 else max(e, s - aP * 1.5)
        s = min(s, e - max(1.4 * aP, close * 0.0012)) if d == 1 else max(s, e + max(1.4 * aP, close * 0.0012))
        risque = abs(e - s)

        def f_cible(ref, dist_min):
            v1, n1 = None, ""
            for k in range(cMin, cMax + 1):
                val = niv[k]
                if val is not None and d * (val - ref) >= dist_min and (v1 is None or d * (val - v1) < 0):
                    v1, n1 = val, NOMS_NIV[k]
            return v1, n1
        c1, nc1 = f_cible(e, risque * GAIN_MIN)
        t1 = e + d * risque * GAIN_MIN if c1 is None else c1
        c2, nc2 = f_cible(e, abs(t1 - e) + atrC)
        t2 = e + d * risque * (GAIN_MIN + 2) if c2 is None else c2
        return dict(e=e, tp1=t1, tp2=t2, sl=s, n1=nc1 if c1 is not None else f"projection {GAIN_MIN} x le risque",
                    n2=nc2 if c2 is not None else f"projection {GAIN_MIN + 2} x le risque")

    def strat_de(self, v, dP):
        d = v["dirs"]; dW = v["dW"]
        uW, uD, u4, u1h, u15, u5, u1 = dW == dP, d[10] == dP, d[9] == dP, d[7] == dP, d[4] == dP, d[2] == dP, d[0] == dP
        oW, o4, o1h = dW == -dP, d[9] == -dP, d[7] == -dP
        nz = dP != 0
        swOk = nz and uD and not oW and u1h and not o4
        swAtt = nz and uD and not oW and not u4 and not u1h
        dyOk = nz and not o4 and u1h and u5
        dyAtt = nz and not o4 and u1h and not u15 and not u5
        scOk = nz and not o1h and u15 and u5 and u1
        scAtt = nz and not o1h and u15 and u5 and not u1
        strat = "SWING" if swOk else "DAY" if dyOk else "SCALPING" if scOk else "SWING" if swAtt else "DAY" if dyAtt else "SCALPING" if scAtt else ""
        etat = "CONFIRMÉ" if (swOk or dyOk or scOk) else "EN ATTENTE" if strat else "AUCUNE"
        flags = dict(uW=uW, uD=uD, u4=u4, u1h=u1h, u15=u15, u5=u5, u1=u1, oW=oW, o4=o4, o1h=o1h)
        return strat, etat, flags

    def plan_live(self, v, dP):
        strat, etat, fl = self.strat_de(v, dP)
        prof = {"SWING": 3, "DAY": 2, "SCALPING": 1}.get(strat, 0)
        sMin = {3: 4, 2: 4, 1: 0, 0: 4}[prof]; sMax = {3: 11, 2: 7, 1: 3, 0: 11}[prof]
        cMin = {3: 8, 2: 4, 1: 0, 0: 4}[prof]; cMax = {3: 15, 2: 11, 1: 7, 0: 15}[prof]
        return strat, etat, fl, self.f_plan(v, dP if dP != 0 else 1, sMin, sMax, cMin, cMax)

    def cloture(self, m15):
        """Traitement d'une barre CONFIRMÉE (barstate.isconfirmed), dans l'ordre du script."""
        v = self.barre(m15)
        if not self.init:
            self.dirStable = v["dirBrut"]
        else:
            brut, d15, d60 = v["dirBrut"], v["d15"], v["d60"]
            if self.dirStable == 0:
                self.dirStable = brut
            elif brut != 0 and brut != self.dirStable and (d15 == brut or d60 == brut):
                self.dirStable = brut
            elif brut == 0 and d15 != self.dirStable and d60 != self.dirStable:
                self.dirStable = 0
        dirPlan = self.dirStable
        strat, etat, fl, pl = self.plan_live(v, dirPlan)
        slFranchi = self.sl is not None and ((self.dirFig == -1 and v["close"] > self.sl) or (self.dirFig == 1 and v["close"] < self.sl))
        if self.init:
            if slFranchi:
                self.retDir, self.retAge = -self.dirFig, 0
            elif self.retDir:
                self.retAge += 1
                if self.retAge > 40:
                    self.retDir = 0
        nouvelle15 = True                                           # vue 15 min : chaque barre ouvre une nouvelle fenêtre 15 min
        if self.ent is None or nouvelle15 or dirPlan != self.dirFig or strat != self.stratFig or slFranchi:
            self.ent, self.tp1, self.tp2, self.sl = pl["e"], pl["tp1"], pl["tp2"], pl["sl"]
            self.n1, self.n2 = pl["n1"], pl["n2"]
            self.dirFig, self.stratFig = dirPlan, strat
        self.init = True
        self.v_close = v
        return v

    def zone(self, m15, dirPlan):
        z = m15[-25:-1]
        fH, fL = max(x["h"] for x in z), min(x["l"] for x in z)
        fR = fH - fL
        f = (lambda k: fL + k * fR) if dirPlan == -1 else (lambda k: fH - k * fR)
        f50, f618, f786 = f(0.5), f(0.618), f(0.786)
        ent, sl = self.ent, self.sl
        zMin = min(ent, f50) if dirPlan == -1 else max(min(ent, f786), sl + 0.25 * (ent - sl))
        zMax = min(max(ent, f786), sl - 0.25 * (sl - ent)) if dirPlan == -1 else max(ent, f50)
        zb, zh = min(zMin, zMax), max(zMin, zMax)
        return dict(za=zb, zb=zh, f50=f50, f618=f618, f786=f786, zmil=(zb + zh) / 2)

    def score(self, v, dirPlan, strat, etat, fl, m15):
        if not strat:
            return 0
        alignN = {"SWING": [fl["uW"], fl["uD"], fl["u4"], fl["u1h"]], "DAY": [fl["u4"], fl["u1h"], fl["u15"], fl["u5"]],
                  "SCALPING": [fl["u1h"], fl["u15"], fl["u5"], fl["u1"]]}[strat]
        ptsAlign = round(25.0 * sum(alignN) / 4.0)
        ctxU = fl["uD"] if strat == "SWING" else fl["u4"] if strat == "DAY" else fl["u1h"]
        ctxO = fl["oW"] if strat == "SWING" else fl["o4"] if strat == "DAY" else fl["o1h"]
        ptsStruct = 20 if ctxU else 0 if ctxO else 10
        distE = abs(v["close"] - self.ent)
        ptsZone = 20 if distE <= 0.5 * v["atrC"] else 10 if distE <= 1.5 * v["atrC"] else 0
        vol = v["vol"][-20:]
        volOk = len(vol) == 20 and all(x is not None for x in vol) and vol[-1] > 0 and sum(vol) > 0
        volR = vol[-1] / (sum(vol) / 20) if volOk else 0.0
        ptsVol = 0 if not volOk else 15 if volR >= 1.0 else 7 if volR >= 0.7 else 0
        rsiT = v["rsis"][7] if strat == "SWING" else v["rsis"][2] if strat == "DAY" else v["rsis"][0]
        rsiSain = rsiT < 70 if dirPlan == 1 else rsiT > 30
        ptsInd = (10 if v["sens"] == dirPlan else 5) if rsiSain else 0
        rrS = abs(self.tp1 - self.ent) / max(abs(self.ent - self.sl), 1e-12)
        ptsRR = 10 if rrS >= 2.0 else 7 if rrS >= 1.5 else 0
        return ptsAlign + ptsStruct + ptsZone + ptsVol + ptsInd + ptsRR


# ───────────────────────── génération de bougies simulées ─────────────────────────
def marche_aleatoire(n, pas, depart, vol, graine, derive=0.0, volume=True):
    rnd = random.Random(graine); t0 = 1_700_000_000 // pas * pas - n * pas; c = depart; out = []
    for i in range(n):
        o = c; c = max(1.0, o * (1 + derive + rnd.gauss(0, vol)))
        h = max(o, c) * (1 + abs(rnd.gauss(0, vol / 2))); l = min(o, c) * (1 - abs(rnd.gauss(0, vol / 2)))
        b = dict(t=t0 + i * pas, o=o, h=h, l=l, c=c)
        if volume:
            b["v"] = 50 + rnd.random() * 100
        out.append(b)
    return out


def jeu_simule(graine, derive=0.0):
    p = 3000.0
    return dict(m1=marche_aleatoire(300, 60, p, 0.0008, graine + 1, derive), m5=marche_aleatoire(300, 300, p, 0.0018, graine + 2, derive),
                m15=marche_aleatoire(400, 900, p, 0.003, graine + 3, derive), m30=marche_aleatoire(300, 1800, p, 0.004, graine + 4, derive),
                h1=marche_aleatoire(300, 3600, p, 0.006, graine + 5, derive), h4=marche_aleatoire(300, 14400, p, 0.012, graine + 6, derive),
                d1=marche_aleatoire(300, 86400, p, 0.025, graine + 7, derive), w1=marche_aleatoire(80, 604800, p, 0.05, graine + 8, derive))


# ───────────────────────── comparaison ─────────────────────────
class ParitePine(unittest.TestCase):
    TOL = 1e-6

    def rejouer(self, S, i0, n, etiquette, avant=None):
        """Rejoue n clôtures 15 min à partir de l'index i0. Retourne les statistiques de couverture."""
        ref = PineRef(S)
        mem = {}
        m15 = S["m15"]
        stats = dict(barres=0, longs=0, shorts=0, strats=set(), retournements=0, flips=0, confirmes=0)
        prev_stable = None
        for i in range(i0, i0 + n):
            if avant:
                avant(i, ref, mem, m15)
            # 1) appel PENDANT la bougie i (dernier instant de la bougie i = clôture) -> valeurs « live »
            S_live = dict(S, m15=m15[:i + 1])
            r = ab.analyser_avec_memoire(S_live, mem)
            # 2) référence Pine à la clôture de la bougie i
            v = ref.cloture(m15[:i + 1])
            # 3) appel APRÈS la clôture (la bougie i+1 vient de s'ouvrir) : le bot avance son état
            S_next = dict(S, m15=m15[:i + 2])
            r2 = ab.analyser_avec_memoire(S_next, mem)
            ctx = f"[{etiquette} barre {i}]"
            # --- 11 unités (live, avant clôture)
            if mem.get("bar_t") is not None and i > i0:
                pass
            self.assertEqual(r["dirs"], v["dirs"], ctx + " sens des 11 UT")
            self.assertEqual(r["sqzs"], v["sqzs"], ctx + " compressions des 11 UT")
            for a, b in zip(r["rsis"], v["rsis"]):
                self.assertAlmostEqual(a, b, delta=1e-6, msg=ctx + " RSI des 11 UT")
            self.assertEqual((r["bull"], r["bear"], r["comp"]), (v["bull"], v["bear"], v["comp"]), ctx + " bull/bear/comp")
            self.assertEqual(r["sens"], v["sens"], ctx + " sens probable")
            self.assertEqual(r["dirBrut"], v["dirBrut"], ctx + " dirBrut")
            self.assertAlmostEqual(r["atr"], v["atrC"], delta=1e-6, msg=ctx + " ATR 15 min")
            # --- état après clôture : sens stable, stratégie, plan FIGÉ
            dirPlan = ref.dirStable
            self.assertEqual(mem["stable"], dirPlan, ctx + " sens stable (anti-parasites)")
            self.assertEqual(mem["strat_fig"], ref.stratFig, ctx + " stratégie figée")
            for k in ("ent", "tp1", "tp2", "sl"):
                self.assertAlmostEqual(mem[k], getattr(ref, k), delta=1e-4 * max(1.0, abs(getattr(ref, k)) / 1000), msg=ctx + f" niveau figé {k}")
            self.assertEqual(mem["n1"], ref.n1, ctx + " nom TP1"); self.assertEqual(mem["n2"], ref.n2, ctx + " nom TP2")
            self.assertEqual(mem.get("ret_dir", 0), ref.retDir, ctx + " RETOURNEMENT")
            # --- zone verte + Fibonacci + trait de décision (sur la bougie i+1 en formation, entrée/SL figés)
            if dirPlan != 0 or True:
                zr = ref.zone(m15[:i + 2], dirPlan)
                zb = r2["zone_pine"]
                for k in ("za", "zb", "f50", "f618", "f786", "zmil"):
                    self.assertAlmostEqual(zb[k], zr[k], delta=1e-4 * max(1.0, abs(zr[k]) / 1000), msg=ctx + f" zone {k}")
            # --- stratégie + score /100 (live bougie i+1 vs référence recalculée sur m15[:i+2])
            vlive = ref.barre(m15[:i + 2])
            strat2, etat2, fl2 = ref.strat_de(vlive, dirPlan)
            sc_ref = ref.score(vlive, dirPlan, strat2, etat2, fl2, m15[:i + 2])
            st_bot, et_bot, _ = ab.strategie_alignement(r2["dirs"], r2["dirPlan"], r2["dirW"])
            self.assertEqual((st_bot, et_bot), (strat2, etat2), ctx + " stratégie / état")
            if st_bot:
                sc_bot, _, _ = ab.score_validation(st_bot, et_bot, r2["dirs"], r2["dirPlan"], r2["dirW"], r2["prix"], r2["plan"], r2["atr"],
                                                   r2["rsis"], r2["sens"], [x.get("v") for x in r2["b15"]])
                self.assertEqual(sc_bot, sc_ref, ctx + " score /100")
            # --- voyants ↩ x/5 et RETOURNEMENT confirmé
            nvoy = sum(1 for k in range(5) if dirPlan != 0 and r2["dirs"][k] == -dirPlan)
            self.assertEqual(r2["nVoy"], nvoy, ctx + " voyants ↩ x/5")
            self.assertEqual(r2["ret_conf"], bool(ref.retDir) and dirPlan == ref.retDir, ctx + " RETOURNEMENT confirmé")
            # --- niveaux de l'ordre Telegram == niveaux du graphique
            o = ab.point_entree(r2, dirPlan if dirPlan else 1, r2["prix"])
            if dirPlan:
                self.assertAlmostEqual(o["e"], ref.ent, delta=1e-4 * max(1.0, abs(ref.ent) / 1000)); self.assertAlmostEqual(o["sl"], ref.sl, delta=1e-4 * max(1.0, abs(ref.sl) / 1000))
                self.assertAlmostEqual(o["tp1"], ref.tp1, delta=1e-4 * max(1.0, abs(ref.tp1) / 1000)); self.assertAlmostEqual(o["tp2"], ref.tp2, delta=1e-4 * max(1.0, abs(ref.tp2) / 1000))
            stats["barres"] += 1
            stats["longs"] += dirPlan == 1; stats["shorts"] += dirPlan == -1
            stats["strats"].add(ref.stratFig)
            stats["retournements"] += 1 if ref.retDir else 0
            stats["confirmes"] += 1 if r2["ret_conf"] else 0
            if prev_stable is not None and prev_stable != dirPlan:
                stats["flips"] += 1
            prev_stable = dirPlan
        return stats

    def test_parite_pine_bougies_simulees(self):
        """TEST SIMULÉ (marche aléatoire à graine fixe, 3 régimes) : 3 x 60 clôtures comparées au port du Pine."""
        total = dict(barres=0, longs=0, shorts=0, strats=set(), retournements=0, flips=0)
        for graine, derive in ((11, 0.0006), (23, -0.0006), (37, 0.0)):
            st = self.rejouer(jeu_simule(graine, derive), 330, 60, f"simulé g{graine}")
            for k in ("barres", "longs", "shorts", "retournements", "flips"):
                total[k] += st[k]
            total["strats"] |= st["strats"]
        print(f"PARITE_SIMULEE barres={total['barres']} LONG={total['longs']} SHORT={total['shorts']} stratégies={sorted(total['strats'])} "
              f"changements_de_sens={total['flips']} barres_en_retournement={total['retournements']}")
        self.assertEqual(total["barres"], 180)
        self.assertTrue(total["longs"] and total["shorts"], "le jeu de test doit couvrir LONG et SHORT")

    def test_retournement_sl_franchi_puis_confirme_ou_expire(self):
        """SL franchi à la clôture -> position annulée + RETOURNEMENT ; confirmé si le nouveau sens est validé ; expire après 40 barres."""
        S = jeu_simule(23, -0.0006)
        etat = {"force": False}

        def avant(i, ref, mem, m15):
            # à la barre 340 on place le SL du plan figé de l'autre côté du prix : il sera franchi à la clôture
            if i == 340 and ref.dirFig in (1, -1) and ref.sl is not None:
                c = m15[i]["c"]
                ref.sl = mem["sl"] = (c + 1.0) if ref.dirFig == 1 else (c - 1.0)
                etat["force"] = True
        st = self.rejouer(S, 330, 60, "retournement forcé", avant)
        self.assertTrue(etat["force"], "le scénario doit avoir forcé un SL franchi")
        print(f"PARITE_RETOURNEMENT barres_en_retournement={st['retournements']} barres_confirmées={st['confirmes']}")
        self.assertGreater(st["retournements"], 0)

    def test_etiquettes_retournement_fr_en(self):
        r = {"ret_dir": 1, "ret_conf": False, "strat": "DAY"}
        self.assertIn("⛔ SL cassé à la clôture : SHORT annulé ↩ RETOURNEMENT en cours", ab.ligne_retournement(r)[0])
        r.update(ret_conf=True)
        self.assertEqual(ab.ligne_retournement(r), ["✅ RETOURNEMENT CONFIRMÉ : LONG • DAY"])
        self.assertEqual(ab.ligne_retournement({"ret_dir": 0}), [])
        self.assertIn("REVERSAL CONFIRMED: LONG", ab.traduire(ab.ligne_retournement(r)[0]))
        self.assertIn("SL broken at the close", ab.traduire(ab.ligne_retournement({"ret_dir": -1, "ret_conf": False})[0]))
        self.assertIn("2/5", "\n".join(ab.voyants_unites({"dirs": [1] * 11, "nVoy": 2})))

    def test_niveaux_figes_entre_deux_clotures(self):
        """Entre deux clôtures 15 min, les niveaux affichés ne bougent pas (même si le prix et les bougies 1/5 min bougent)."""
        S = jeu_simule(11, 0.0006); m15 = S["m15"]; mem = {}
        ab.analyser_avec_memoire(dict(S, m15=m15[:340]), mem)
        ab.analyser_avec_memoire(dict(S, m15=m15[:341]), mem)
        niveaux = [tuple(mem[k] for k in ("ent", "tp1", "tp2", "sl"))]
        S_bis = dict(S, m15=m15[:341], m1=marche_aleatoire(300, 60, 3500.0, 0.003, 99))   # le marché 1 min change complètement
        r = ab.analyser_avec_memoire(S_bis, mem)
        self.assertEqual(niveaux[0], tuple(mem[k] for k in ("ent", "tp1", "tp2", "sl")))
        self.assertEqual((r["plan"]["e"], r["plan"]["tp1"], r["plan"]["tp2"], r["plan"]["sl"]), niveaux[0])

    def test_sens_stable_ne_clignote_pas(self):
        self.assertEqual(ab.dir_stable_pas(1, -1, 0, 0), 1)      # nouveau sens non confirmé par 15 min / 1h : on garde
        self.assertEqual(ab.dir_stable_pas(1, -1, -1, 0), -1)    # confirmé par le 15 min
        self.assertEqual(ab.dir_stable_pas(1, -1, 0, -1), -1)    # confirmé par la 1h
        self.assertEqual(ab.dir_stable_pas(1, 0, 1, 0), 1)       # biais neutre mais 15 min encore dans le sens : on garde
        self.assertEqual(ab.dir_stable_pas(1, 0, 0, 0), 0)       # plus aucune UT dans le sens : neutre
        self.assertEqual(ab.dir_stable_pas(0, -1, 0, 0), -1)

    def test_constantes_du_pine(self):
        self.assertEqual((ab.MIN_ALIGN, ab.MIN_SQZ, ab.MARGE_ATR, ab.GAIN_MIN), (8, 4, 0.5, 1.5))
        self.assertEqual(ab.UT, ["1", "3", "5", "10", "15", "30", "45", "1h", "2h", "4h", "D"])
        self.assertEqual(ab.POIDS, [1, 1, 1, 1, 2, 2, 2, 3, 3, 4, 5])
        self.assertEqual((ab.SL_RISQUE_MIN_ATR, ab.SL_RISQUE_MIN_PCT), (1.4, 0.0012))

    @unittest.skipUnless(os.environ.get("ALIGN_PARITE_RESEAU") == "1", "SAUTÉ : ALIGN_PARITE_RESEAU=1 absent (pas de réseau) — aucun statut vert sur du réel")
    def test_parite_pine_bougies_reelles(self):
        """TEST RÉEL (CI GitHub) : vraies bougies Kraken téléchargées par le bot lui-même, 40 clôtures rejouées par marché."""
        fait = 0
        for pair in ("XBTUSD",):
            try:
                S = dict(m1=ab.bougies(pair, 1), m5=ab.bougies(pair, 5), m15=ab.bougies(pair, 15), m30=ab.bougies(pair, 30),
                         h1=ab.bougies(pair, 60), h4=ab.bougies(pair, 240), d1=ab.bougies(pair, 1440), w1=ab.bougies(pair, 10080))
            except Exception as ex:
                self.skipTest(f"SAUTÉ : bougies réelles indisponibles ({type(ex).__name__})")
            n = len(S["m15"])
            st = self.rejouer(S, n - 45, 40, f"réel {pair}")
            print(f"PARITE_REELLE {pair} barres={st['barres']} LONG={st['longs']} SHORT={st['shorts']} stratégies={sorted(st['strats'])} changements_de_sens={st['flips']}")
            fait += st["barres"]
        self.assertGreaterEqual(fait, 40)


if __name__ == "__main__":
    unittest.main()
