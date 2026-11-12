"""Le bot dit toujours clairement quels marchés il surveille pour la personne (GOLD + NASDAQ, etc.)."""
import json
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("TELEGRAM_TOKEN", "test")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import align_bot as ab


class SuiviMarchesTest(unittest.TestCase):
    def setUp(self):
        self.envois = []
        def faux_telegram(methode, **kw):
            self.envois.append((methode, kw))
            return {"ok": True, "result": {"message_id": 1}}
        p1 = mock.patch.object(ab, "telegram", faux_telegram)
        p2 = mock.patch.object(ab, "autorise", lambda *a: True)
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)
        self.e = {"marches_par_chat": {}, "auto": {}, "bot_off": [], "bienvenue": {}}

    def test_gold_nasdaq_suivis_btc_non(self):
        ab.selectionner_marches_suivi(self.e, "42", ["GOLD", "NASDAQ"])
        t = ab.texte_suivi(self.e, "42")
        self.assertIn("JE SURVEILLE POUR TOI", t)
        self.assertIn("🥇 GOLD : ⏳", t)
        self.assertIn("💠 NASDAQ : ⏳", t)
        self.assertIn("🟠 BTC : ⬜ non suivi", t)

    def test_ou_en_est_avec_vraies_donnees(self):
        ab.selectionner_marches_suivi(self.e, "42", ["GOLD"])
        with mock.patch.object(ab, "DERNIERS", {"GOLD": {"prix": 3975.2, "dirPlan": -1, "bear": 11, "strat": "SWING", "atr": 5}}), \
             mock.patch.object(ab, "strategie_alignement", lambda *a: (None, "OK")):
            t = ab.texte_suivi(self.e, "42")
        self.assertIn("↳ 11/11 UT alignées • SWING • prochaine clôture 1h dans ", t)

    def test_trois_marches(self):
        ab.selectionner_marches_suivi(self.e, "42", "ALL")
        self.assertEqual(ab.texte_suivi(self.e, "42").count("⏳"), 3)

    def test_valider_affiche_le_bloc(self):
        ab.selectionner_marches_suivi(self.e, "42", ["GOLD", "NASDAQ"])
        self.assertTrue(ab.valider_et_suivre_marches(self.e, "42", 42))
        txt = [kw.get("text", "") for m, kw in self.envois if m == "sendMessage"][-1]
        self.assertIn("Suivi activé : GOLD + NASDAQ", txt)
        self.assertIn("JE SURVEILLE POUR TOI", txt)

    def test_case_cochee_edite_le_meme_message(self):
        ab.selectionner_marches_suivi(self.e, "42", ["GOLD"])
        ab.basculer_marche(self.e, "42", "NASDAQ")
        ab.menu_marches(self.e, "42", 99)
        methode, kw = self.envois[-1]
        self.assertEqual(methode, "editMessageText")
        self.assertEqual(kw["message_id"], 99)
        textes = [l[0]["text"] for l in json.loads(kw["reply_markup"])["inline_keyboard"]]
        self.assertIn("✅ 💠 NASDAQ", textes)
        self.assertIn("⬜ Tout recevoir", textes)
        self.assertIn("Cochés en ce moment : 🥇 GOLD + 💠 NASDAQ", kw["text"])

    def test_tout_recevoir_coche_seulement_si_tout(self):
        ab.selectionner_marches_suivi(self.e, "42", "ALL")
        ab.menu_marches(self.e, "42")
        textes = [l[0]["text"] for l in json.loads(self.envois[-1][1]["reply_markup"])["inline_keyboard"]]
        self.assertIn("✅ Tout recevoir", textes)


class IaEnPositionTest(unittest.TestCase):
    def test_ia_branchee_au_sl_be_et_retournement(self):
        appels = []
        with mock.patch.object(ab, "ia", lambda etat, consigne, data, **kw: appels.append(consigne) or "🧠 test"), \
             mock.patch.object(ab, "donnees_ia", lambda *a, **k: {}):
            for i, entete in enumerate(("❌ STOP TOUCHÉ — 🥇 GOLD", "🔒 🥇 GOLD : sorti à BE", "↩ RETOURNEMENT EN PRÉPARATION — 🥇 GOLD")):
                out = ab.commentaires_ia_temps_reel({"ia_moments": {}}, f"M{i}", {}, {}, [entete + "\nligne"])
                self.assertTrue(out and "L'IA ALIGN EN DIRECT" in out[0], entete)
        self.assertEqual(len(appels), 3)


class VisionEtFormatTest(unittest.TestCase):
    def test_zone_garde_ses_deux_bornes(self):
        t = ab.mise_en_forme("📍 Zone d'entrée : 3981,48 – 4012,15 (prix dans la zone)")
        self.assertIn("3981,48 → 4012,15 (prix dans la zone)", t)

    def test_niveaux_sans_plan_donne_la_vision(self):
        r = {"dirs": [-1, -1, 1, -1, -1, -1, 0, -1, 1, -1, -1]}
        h = {"d": -1, "pct": 81, "n": 7, "strat": "SWING", "zp": {"za": 3981.48, "zb": 4012.15}, "prix": 3989.5}
        with mock.patch.object(ab, "hb_etat_surveille", lambda r: h), \
             mock.patch.object(ab, "raison_attente", lambda r, c: "J'attends une clôture 1h sous 3996,81"):
            t = ab.texte_vision("GOLD", r, {})
        self.assertIn("Sens probable : SHORT", t)
        self.assertIn("UT alignées : 7/11", t)
        self.assertIn("1m🟥 3m🟥 5m🟩 15m🟥 1h🟥 4h🟥 D🟥", t)
        self.assertIn("(prix dans la zone)", t)
        self.assertNotIn("Aucun plan", t)


class AntiBruitClotureTest(unittest.TestCase):
    def test_meme_decision_meme_signature(self):
        a = "🥇 GOLD · 3994,98\n━━━\n🔴 PAS D'ENTRÉE — SIGNAL NON CONFIRMÉ\n🕯 5m clôturée 02:10 · BAISSE\nH4 SHORT · H1 SHORT · ALIGN 2/2\n🎯 SWING SHORT\n⏳ Prochaine validation : clôture 5m dans 04:47"
        b = "🥇 GOLD · 3998,06\n━━━\n🔴 PAS D'ENTRÉE — SIGNAL NON CONFIRMÉ\n🕯 5m clôturée 02:15 · HAUSSE\nH4 SHORT · H1 SHORT · ALIGN 2/2\n🎯 SWING SHORT\n⏳ Prochaine validation : clôture 5m dans 04:19"
        c = b.replace("🔴 PAS D'ENTRÉE — SIGNAL NON CONFIRMÉ", "🟢 J'ENTRE MAINTENANT")
        self.assertEqual(ab.signature_cloture(a), ab.signature_cloture(b))
        self.assertNotEqual(ab.signature_cloture(a), ab.signature_cloture(c))


class FiltreDailyTendanceTest(unittest.TestCase):
    base = {"posD": 0.05, "posW": 0.4}

    def test_jour_de_baisse_aligne_ne_bloque_plus_le_short(self):
        r = dict(self.base, dirs=[-1] * 11)
        self.assertFalse(ab.bloque_dw(r, -1))

    def test_bas_du_daily_avec_retournement_bloque_toujours(self):
        r = dict(self.base, dirs=[1, 1, -1, -1, -1, -1, -1, -1, -1, -1, -1])     # 1 min et 3 min repartent à la hausse
        self.assertTrue(ab.bloque_dw(r, -1))

    def test_daily_pas_aligne_bloque_toujours(self):
        r = dict(self.base, dirs=[-1] * 10 + [1])
        self.assertTrue(ab.bloque_dw(r, -1))


if __name__ == "__main__":
    unittest.main()
