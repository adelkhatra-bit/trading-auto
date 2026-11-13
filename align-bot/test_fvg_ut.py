"""v24.3 : le bot donne la même entrée / SL / TP que l'indicateur « ALIGN MTF PRO (Inside) » sur la vue 5 min (FVG + mèche)."""
import unittest

import align_bot as ab


def bougie(o, h, l, c, t=0):
    return dict(o=o, h=h, l=l, c=c, t=t)


def serie_short():
    """Montée calme, sommet (mèche 110), chute qui laisse une FVG rouge 106 → 104, petit rebond sous la FVG."""
    b = [bougie(100 + i * 0.2, 100.6 + i * 0.2, 99.6 + i * 0.2, 100.2 + i * 0.2, i) for i in range(30)]   # ~100 → 106
    b += [bougie(106, 110, 105.8, 107, 30), bougie(107, 107.2, 106, 106.2, 31),      # sommet mèche 110 ; bougie 1 (bas 106)
          bougie(106.2, 106.3, 103, 103.2, 32), bougie(103.2, 104, 101, 101.5, 33)]  # bougie 3 : haut 104 < 106 → FVG rouge 104–106
    b += [bougie(101.5, 103.1, 100.5, 101, 34 + k) for k in range(8)]
    b += [bougie(101, 102.5, 100.8, 102.2, 42), bougie(102.2, 103.8, 101.9, 103.5, 43)]
    return b


class PlanFVG(unittest.TestCase):
    def test_short_entree_bas_fvg_sl_meche(self):
        st = ab.structure_fvg(serie_short())
        rTop, rBot, gTop, gBot, hH, lL, a, cl = st
        self.assertAlmostEqual(rBot, 104)
        self.assertAlmostEqual(rTop, 106)
        self.assertAlmostEqual(hH, 110)
        fv = ab.plan_fvg(-1, st, 120, 125, 90, 80, "5 min")
        self.assertIsNotNone(fv)
        self.assertAlmostEqual(fv["e"], 104)                                     # entrée = bas de la FVG rouge
        self.assertAlmostEqual(fv["sl"], max(110 + max(0.3 * a, 0.03), 104 + 1.0 * a))   # un peu au-dessus de la mèche du dernier plus haut
        self.assertLess(fv["tp1"], fv["e"])
        self.assertGreaterEqual(fv["e"] - fv["tp1"], 1.5 * (fv["sl"] - fv["e"]) - 1e-9)    # TP1 ≥ 1,5 x le risque
        self.assertLessEqual(fv["tp2"], fv["tp1"])                               # TP2 = plus loin (continuation)
        self.assertEqual((fv["za"], fv["zb"]), (104, fv["sl"] - 0.25 * (fv["sl"] - 104)))   # bande verte du graphique
        self.assertIn("FVG rouge 5 min", fv["src"])

    def test_long_miroir(self):
        inv = [bougie(-x["o"], -x["l"], -x["h"], -x["c"], x["t"]) for x in serie_short()]
        st = ab.structure_fvg(inv)
        fv = ab.plan_fvg(1, st, -120, -125, -90, -80, "5 min")
        self.assertAlmostEqual(fv["e"], -104)
        self.assertLess(fv["sl"], -110)
        self.assertIn("FVG verte 5 min", fv["src"])

    def test_sans_fvg_plan_origine(self):
        calme = [bougie(100, 100.5, 99.5, 100, i) for i in range(40)]
        self.assertIsNone(ab.plan_fvg(-1, ab.structure_fvg(calme), 101, 102, 98, 97, "5 min"))

    def test_fvg_comblee_par_cloture_disparait(self):
        b = serie_short() + [bougie(103, 106.5, 102.8, 106.4, 50)]               # clôture au-dessus du haut (106) : FVG comblée
        self.assertIsNone(ab.structure_fvg(b)[1])

    def test_pine_entree_utilise_la_vue_5_min(self):
        b5 = serie_short()
        st = ab.structure_fvg(b5)
        pl = dict(e=120, sl=125, tp1=90, n1="15m", tp2=80, n2="1h", rr=6)
        b15 = [bougie(100 + i, 101 + i, 99 + i, 100.5 + i, i) for i in range(30)]
        r = dict(b15=b15, b5=b5, planH=pl, planB=pl, dirPlan=-1, strat="DAY", struct_ut={"5": st, "3": None, "15": None, "1h": None})
        pe = ab.pine_entree(r, -1)
        if pe is None:
            self.skipTest("zone du plan indisponible sur ces bougies")
        self.assertTrue(pe.get("fvg_ut"))
        self.assertAlmostEqual(pe["e"], 104)
        self.assertEqual(pe["sl_ut"], "5 min")

    def test_coach_fvg_explique_l_attente(self):
        b5 = serie_short()
        st = ab.structure_fvg(b5)
        pl = dict(e=120, sl=125, tp1=90, n1="15m", tp2=80, n2="1h", rr=6)
        b15 = [bougie(100 + i, 101 + i, 99 + i, 100.5 + i, i) for i in range(30)]
        r = dict(b15=b15, b5=b5, planH=pl, planB=pl, dirPlan=-1, strat="DAY", dirs=[-1] * 11,
                 struct_ut={"5": st, "3": None, "15": None, "1h": None})
        if ab.pine_entree(r, -1) is None:
            self.skipTest("zone du plan indisponible sur ces bougies")
        l = ab.coach_fvg(r, -1, 104.5)
        txt = "\n".join(l)
        self.assertIn("✅ 5 min + 15 min alignés", txt)
        self.assertIn("🧱 FVG rouge 5 min (104)", txt)
        self.assertIn("🛡️ SL", txt)
        self.assertIn("⏳ Patiente : j'entre quand une bougie 5 min clôture sous", txt)
        self.assertIn("📍 Prix DANS la zone d'entrée (vue 5 min)", txt)
        self.assertEqual(ab.coach_fvg(dict(r, struct_ut={}), -1, 104.5), [])        # pas de FVG : rien d'inventé

    def test_scalp_inverse_vers_l_entree_du_plan(self):
        st = (None, None, 100.0, 99.0, 110.0, 98.0, 1.0, 100.2)                 # FVG verte 99–100, plus bas 98, ATR 1
        pl = dict(e=108, sl=112, tp1=95, n1="15m", tp2=90, n2="1h", rr=3)
        r = dict(dirs=[1, 1, 1, -1, -1, -1, -1, -1, -1, -1, -1], dirPlan=-1, planB=pl, planH=pl, struct_ut={"5": st})
        si = ab.scalp_inverse(r, -1)
        self.assertEqual(si["d"], 1)                                             # plan SHORT → scalp LONG
        self.assertAlmostEqual(si["e"], 100.0)                                   # haut de la FVG verte
        self.assertAlmostEqual(si["sl"], 97.7)                                   # sous la mèche du dernier creux (98 - 0,3 ATR)
        self.assertAlmostEqual(si["tp"], 108)                                    # TP = entrée du SHORT principal
        self.assertEqual(si["voy"], 3)
        self.assertIsNone(ab.scalp_inverse(dict(r, dirs=[1, 1, -1, -1, -1] + [-1] * 6), -1))   # 2/5 seulement : rien
        self.assertIsNone(ab.scalp_inverse(dict(r, planB=dict(pl, e=101)), -1))                # gain trop petit : rien
        txt = ab.texte_scalp("GOLD", si, -1)
        self.assertEqual(txt[0], "↩ 🟢 GOLD - SCALP LONG")                          # sens en couleur en premier
        self.assertEqual(txt[2:5], ["💰 TP : 108 (= entrée du SHORT)", "🎯 Entrée : 100 (vue 5 min)", "🛑 SL : 97,70"])   # ordre du graphique
        self.assertFalse(ab.est_entree("\n".join(txt)))                            # jamais confondu avec le signal principal


if __name__ == "__main__":
    unittest.main()
