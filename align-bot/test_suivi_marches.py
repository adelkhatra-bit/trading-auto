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


if __name__ == "__main__":
    unittest.main()
