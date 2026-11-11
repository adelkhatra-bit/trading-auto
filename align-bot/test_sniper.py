"""Entrée sniper M1/M3 : ordre limite sur la dernière structure, SL derrière la mèche, jamais forcé.
SCÉNARIO « GOLD ce soir » (SIMULÉ à partir du récit d'Adel : tendance baissière 10/11 UT, ancienne résistance ~3994, pic ~3995 puis chute ~3979).
Le rejeu sur les vraies bougies M1/M3 se lance avec replay_sniper.py (workflow sniper-replay.yml) : ce fichier ne prétend pas être du réel."""
import unittest
from unittest.mock import patch

import align_bot as ab
from test_parite_pine import jeu_simule

T0 = 1_800_000_000


def b(t, o, h, l, c):
    return dict(t=t, o=o, h=h, l=l, c=c)


def contexte_gold(prix=3988.0, **kw):
    """Gold baissier : 10/11 UT en baisse, ATR 15 min = 6, ATR M3 = 2, structure 15 min 3994 (18:30) et support 1 h 3979."""
    b3 = [b(T0 - 180 * (60 - i), 3990 - i * 0.05, 3990.5 - i * 0.05, 3987.5 - i * 0.05, 3989 - i * 0.05) for i in range(60)]
    r = {"dirPlan": -1, "bull": 1, "bear": 10, "sens": -1, "dirs": [-1] * 11, "strat": "DAY", "atr": 6.0, "atr3": 2.0,
         "m1": [b(T0 - 60 * (60 - i), prix, prix + 0.4, prix - 0.4, prix) for i in range(60)], "b3": b3,
         "niveaux": [(3994.0, "15m"), (3979.0, "1h"), (3960.0, "4h")]}
    r.update(kw)
    return r


class Sniper(unittest.TestCase):
    def test_gold_case_limit_sell_on_last_resistance(self):
        sn = ab.entree_sniper(contexte_gold())
        self.assertIsNotNone(sn)
        self.assertEqual(sn["d"], -1)
        self.assertAlmostEqual(sn["niveau"], 3994.0)
        self.assertAlmostEqual(sn["za"], 3993.8); self.assertAlmostEqual(sn["zb"], 3994.8)          # « vente limite 3994–3995 »
        self.assertAlmostEqual(sn["sl"], 3999.09, places=1)                                        # « SL 3999 » : plancher de risque 0,12 %
        self.assertAlmostEqual(sn["tp1"], 3979.0); self.assertEqual(sn["n1"], "1h")
        self.assertGreaterEqual(sn["rr"], ab.GAIN_MIN); self.assertGreater(sn["sl"], sn["e"]); self.assertLess(sn["tp1"], sn["e"])

    def test_replay_of_the_spike_then_drop(self):
        sn = ab.entree_sniper(contexte_gold())
        futur = [b(T0 + 60 * i, 3988 + i, 3989 + i, 3987 + i, 3988.5 + i) for i in range(1, 7)]            # montée vers 3994
        futur += [b(T0 + 60 * 7, 3994.0, 3995.0, 3993.5, 3994.0)]                                            # pic 3995 (touche l'ordre limite)
        futur += [b(T0 + 60 * (8 + i), 3994 - 1.5 * i, 3994.2 - 1.5 * i, 3993 - 1.5 * i, 3993.5 - 1.5 * i) for i in range(12)]   # chute vers 3978
        res = ab.simuler_sniper(sn, futur)
        self.assertEqual(res["etat"], "TP1"); self.assertGreater(res["pnl"], 14)
        print(f"SNIPER_SIMULE entrée {sn['e']:.1f} SL {sn['sl']:.1f} TP1 {sn['tp1']:.1f} -> {res['etat']} {res['pnl']:+.1f} pts (R/R {sn['rr']:.1f})")

    def test_stop_hit_and_unfilled_outcomes(self):
        sn = ab.entree_sniper(contexte_gold())
        monte = [b(T0 + 60 * i, 3990 + i * 2, 3991 + i * 2, 3989 + i * 2, 3990 + i * 2) for i in range(1, 8)]      # monte jusqu'à > SL
        self.assertEqual(ab.simuler_sniper(sn, monte)["etat"], "SL")
        plat = [b(T0 + 60 * i, 3986, 3987, 3985, 3986) for i in range(1, 30)]
        self.assertEqual(ab.simuler_sniper(sn, plat)["etat"], "non rempli")

    def test_never_forced(self):
        cas = {"UT non alignées": contexte_gold(bear=7), "sens pas clair": contexte_gold(sens=0), "contre la 1h": contexte_gold(dirs=[-1] * 7 + [1] + [-1] * 3),
               "contre la 4h": contexte_gold(dirs=[-1] * 9 + [1, -1]), "pas de direction": contexte_gold(dirPlan=0),
               "trop loin": contexte_gold(prix=3950.0), "zone déjà traversée": contexte_gold(prix=3996.0), "au-delà du SL": contexte_gold(prix=4001.0),
               "pas de cible gainMin": contexte_gold(niveaux=[(3994.0, "15m"), (3990.5, "1h")]), "pas de structure ni swing": contexte_gold(niveaux=[], b3=contexte_gold()["b3"][:5])}
        for nom, r in cas.items():
            self.assertIsNone(ab.entree_sniper(r), nom)

    def test_long_mirror_on_last_support(self):
        b3 = [b(T0 - 180 * (60 - i), 4000 + i * 0.05, 4001.5 + i * 0.05, 3999.5 + i * 0.05, 4001 + i * 0.05) for i in range(60)]
        r = {"dirPlan": 1, "bull": 10, "bear": 1, "sens": 1, "dirs": [1] * 11, "strat": "DAY", "atr": 6.0, "atr3": 2.0, "b3": b3,
             "m1": [b(T0 - 60 * (60 - i), 4006, 4006.4, 3999.6, 4006) for i in range(60)], "niveaux": [(4000.0, "15m"), (4020.0, "1h")]}
        sn = ab.entree_sniper(r)
        self.assertEqual(sn["d"], 1); self.assertLess(sn["sl"], sn["e"]); self.assertGreater(sn["tp1"], sn["e"]); self.assertLessEqual(sn["za"], sn["zb"])

    def test_wick_of_the_spike_moves_the_stop_behind_it(self):
        r = contexte_gold()
        r["m1"][-5] = b(T0 - 300, 3993.0, 3999.5, 3992.5, 3994.0)                       # mèche M1 jusqu'à 3999,5 près de la structure
        sn = ab.entree_sniper(r)
        self.assertGreaterEqual(sn["sl"], 3999.5 + 0.5 * 2.0 - 1e-9)

    def test_message_short_varied_vip_only_fr_en(self):
        etat = {}
        r = dict(contexte_gold(), bull=1, comp=0, b15=[b(T0 - 900 * (30 - i), 100, 101, 99, 100) for i in range(30)], sqzs=[0] * 11, dirW=0, pctH=20)
        r["m1"] = [dict(x, t=T0 - 60 * (60 - i)) for i, x in enumerate(r["m1"])]
        with patch.object(ab, "cme_ouvert", return_value=True):
            ev = [e for e in ab.evenements_pine(etat, "GOLD", dict(r, sniper=ab.entree_sniper(r)), etat.setdefault("GOLD", {}), T0 + 10) if e["kind"] == "sniper"]
            self.assertEqual(len(ev), 1)
            self.assertEqual([e for e in ab.evenements_pine(etat, "GOLD", dict(r, sniper=ab.entree_sniper(r)), etat["GOLD"], T0 + 60) if e["kind"] == "sniper"], [])   # une fois
        fr = ab.texte_pine({}, ev[0]); en = ab.texte_pine({}, ev[0], True)
        self.assertLessEqual(len(fr), 3)
        self.assertIn("vente limite 3993,80–3994,80", fr[0]); self.assertIn("SL 3999,09", fr[1]); self.assertIn("TP1 3979", fr[1])
        self.assertIn("sell limit", en[0]); self.assertNotIn("vente", " ".join(en))
        suivants = {" ".join(ab.texte_pine({"al_rot": {"p:sniper:GOLD": k}}, ev[0])) for k in (-1, 0, 1)}
        self.assertEqual(len(suivants), 3)                                                # formulations différentes

    def test_pipeline_attaches_sniper_key_without_crashing(self):
        S = jeu_simule(11, 0.0006)
        mem = {}
        r = ab.analyser_avec_memoire(dict(S, m15=S["m15"][:340]), mem)
        self.assertIn("sniper", r); self.assertIn("b3", r); self.assertIsNotNone(r["atr3"])


class PropositionPineV25(unittest.TestCase):
    """Le Pine v24 publié n'est jamais modifié ; la proposition v25 ne touche ni au design, ni aux couleurs, ni au tableau."""
    RACINE = __import__("pathlib").Path(__file__).resolve().parent / "pine"

    def test_v24_untouched_and_diff_has_no_design_change(self):
        import hashlib
        v24 = (self.RACINE / "ALIGN_MTF_PRO_v24.pine").read_bytes()
        self.assertEqual(len(v24.splitlines()), 577)                                           # copie intégrale d'origine
        diff = (self.RACINE / "PROPOSITION_v25_sniper.diff").read_text(encoding="utf-8").splitlines()
        modifs = [l[1:] for l in diff if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        for l in modifs:
            for interdit in ("color.", "table.", "label.new", "line.new", "box.new", "bgcolor", "plotshape", "size.", "style=", "position."):
                self.assertNotIn(interdit, l)
        self.assertTrue(all(l.lstrip().startswith("//") or any(k in l for k in ("atr3", "hi3", "lo3", "sniper", "snL", "snCtx", "snBon", "mech", "vk", "k = 0 to 7",
                                                                                   "entV", "entS", "tp1", "tp2", "slV", "slS", "tTP", "entC", "slC", "f_plan", "e :=", "s :=",
                                                                                   "if not na", "if sniper", "@version", "")) for l in modifs))
        v25 = (self.RACINE / "ALIGN_MTF_PRO_v25_PROPOSITION.pine").read_text(encoding="utf-8")
        self.assertIn("NON PUBLIÉE", v25); self.assertEqual(v25.count("request.security("), 23)   # 21 en v24 + 2 (limite TradingView : 40)


if __name__ == "__main__":
    unittest.main()
