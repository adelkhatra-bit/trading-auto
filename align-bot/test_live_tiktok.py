"""LIVE TikTok : bande qui défile, bulles, boost, télécommande payante (Stars) — jamais de niveaux sur l'écran."""
import json
import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import align_bot as ab


class LiveTikTok(unittest.TestCase):
    def setUp(self):
        ab._LIVE_BOOSTS.clear()
        ab._LIVE_DERNIER.clear()
        self.publie = []
        self.envoye = []
        self.tg = []
        self.p = [mock.patch.object(ab, "LIVE_SUJET", "test-sujet"),
                  mock.patch.object(ab, "live_publier", side_effect=lambda t: self.publie.append(t) or True),
                  mock.patch.object(ab, "_envoi_sur", side_effect=lambda cid, **kw: self.envoye.append((cid, kw))),
                  mock.patch.object(ab, "telegram", side_effect=lambda m, **kw: self.tg.append((m, kw)) or {"ok": True})]
        for x in self.p:
            x.start()
        self.etat = {"proprio": ["1"], "prenoms": {"2": "Karim"}, "prospects": ["3"]}

    def tearDown(self):
        for x in self.p:
            x.stop()

    def test_bouton_live_dans_les_deux_claviers(self):
        for c in (ab.CLAVIER, ab.CLAVIER_VISITEUR):
            textes = [b["text"] for ligne in json.loads(c)["keyboard"] for b in ligne]
            self.assertIn("🔴 Live TikTok", textes)

    def test_rien_sur_la_bande_si_live_eteint(self):
        ab.live_annonces(self.etat, "BTC", ["🟢🟢🟢 J'ENTRE MAINTENANT — BTC"])
        self.assertEqual(self.publie, [])

    def test_proprio_lance_le_live_et_tout_le_monde_est_prevenu(self):
        ab.live_callback(self.etat, {"2"}, {"id": "x"}, "liveon", "x", "1")
        self.assertTrue(self.etat["live_on"])
        dest = {cid for cid, _ in self.envoye}
        self.assertEqual(dest, {"2", "3"})
        self.assertTrue(any("EN LIVE" in kw["text"] for _, kw in self.envoye))

    def test_un_abonne_ne_peut_pas_lancer_le_live(self):
        ab.live_callback(self.etat, {"2"}, {"id": "x"}, "liveon", "x", "2")
        self.assertFalse(self.etat.get("live_on"))

    def test_annonces_sans_aucun_niveau(self):
        self.etat["live_on"] = True
        ab.live_annonces(self.etat, "BTC", ["🟢🟢🟢 J'ENTRE MAINTENANT — BTC\n📌 Entrée 68459,14\n🛑 SL 69105", "🎯 TP1 TOUCHÉ — BTC 67167"])
        self.assertEqual(len(self.publie), 3)          # entrée + TP1 + bulle d'explication du TP1
        self.assertTrue(self.publie[2].startswith("BULLE:"))
        for t in self.publie:
            self.assertIsNone(re.search(r"\d{3,}", t), t)
            self.assertNotIn("SHORT", t)
            self.assertNotIn("LONG", t)
        ab.live_annonces(self.etat, "BTC", ["🟢🟢🟢 J'ENTRE MAINTENANT — BTC"])
        self.assertEqual(len(self.publie), 3)          # pas de doublon

    def test_bulle_zone(self):
        self.etat["live_on"] = True
        ab.live_annonces(self.etat, "GOLD", ["🟥🟥 POINT D'ENTRÉE À VENIR — 🥇 GOLD\n🟨 Le prix entre dans la zone\n📍 Zone ≈ 3990 – 4012"])
        self.assertTrue(self.publie[0].startswith("BULLE:"))
        self.assertIsNone(re.search(r"\d{3,}", self.publie[0]))

    def test_boost_limite_par_personne(self):
        self.etat["live_on"] = True
        ab.live_callback(self.etat, set(), {"id": "x"}, "liveboost", "x", "2")
        ab.live_callback(self.etat, set(), {"id": "y"}, "liveboost", "x", "2")
        self.assertEqual(self.publie, ["Karim BOOSTE LE LIVE ! 🚀 ABONNE-TOI • PARTAGE"])

    def test_facture_en_stars(self):
        self.etat["live_on"] = True
        ab.live_callback(self.etat, set(), {"id": "x"}, "livemain", "5", "2")
        m, kw = self.tg[-1]
        self.assertEqual(m, "sendInvoice")
        self.assertEqual(kw["currency"], "XTR")
        self.assertEqual(kw["provider_token"], "")
        self.assertEqual(json.loads(kw["prices"])[0]["amount"], ab.PRIX_MAIN_STARS)
        self.assertEqual(kw["payload"], "livemain:5")

    def test_admin_prend_la_main_sans_payer(self):
        self.etat["live_on"] = True
        ab.live_callback(self.etat, set(), {"id": "x"}, "livemain", "15", "1")
        self.assertFalse(any(m == "sendInvoice" for m, _ in self.tg))
        self.assertTrue(self.publie[-1].startswith("CMD:tf:15:"))
        self.assertIn("capture", self.envoye[-1][1]["text"])

    def test_ordre_btc_gold_nasdaq_en_premier(self):
        self.etat["live_on"] = True
        kb = json.loads(ab.clavier_live(self.etat, "2"))["inline_keyboard"]
        self.assertEqual([b["text"] for b in kb[2]], ["🟠 BTC", "🥇 Gold", "💠 NASDAQ"])
        self.assertIn("capture", ab.texte_live(self.etat))

    def test_paiement_refuse_si_live_eteint(self):
        self.assertFalse(ab.live_pre_checkout(self.etat, {"id": "q", "invoice_payload": "livemain:5"}))
        self.assertEqual(self.tg[-1][1]["ok"], "false")
        self.etat["live_on"] = True
        self.assertTrue(ab.live_pre_checkout(self.etat, {"id": "q", "invoice_payload": "livemain:5"}))
        self.assertEqual(self.tg[-1][1]["ok"], "true")
        self.assertFalse(ab.live_pre_checkout(self.etat, {"id": "q", "invoice_payload": "autre:5"}))

    def test_ecran_muet_l_abonne_est_prevenu(self):
        self.etat["live_on"] = True
        with mock.patch.object(ab, "live_publier", return_value=False):
            self.assertFalse(ab.live_paiement_recu(self.etat, "2", {"invoice_payload": "livemain:5"}))
        self.assertIn("n'a pas répondu", self.envoye[-1][1]["text"])

    def test_admin_voit_le_code_ecran(self):
        ab.menu_live(self.etat, "1")
        self.assertIn("Code écran (admin) : test-sujet", self.envoye[-1][1]["text"])
        ab.menu_live(self.etat, "2")
        self.assertNotIn("Code écran", self.envoye[-1][1]["text"])

    def test_paiement_recu_envoie_l_ordre_au_graphique(self):
        self.etat["live_on"] = True
        ab.live_paiement_recu(self.etat, "2", {"invoice_payload": "livemain:GOLD", "total_amount": 25, "telegram_payment_charge_id": "c1"})
        self.assertEqual(self.publie, ["CMD:sym:FOREXCOM:XAUUSD:Karim"])
        self.assertEqual(self.etat["live_paiements"][-1]["id"], "c1")
        self.assertIn("C'est à toi", self.envoye[-1][1]["text"])

class CartesRelieesAuGraphique(unittest.TestCase):
    def test_zone_parle_comme_le_graphique_en_anglais_aussi(self):
        fr = ("🟩 Le prix entre dans la ZONE du graphique\n🟨 Ligne jaune ENTRÉE : attends la CLÔTURE 15 min EN DESSOUS\n"
              "🙅 Une mèche seule ne suffit pas\n🛑 SL = ligne rouge du graphique")
        en = ab.traduire(fr)
        self.assertIn("chart ZONE", en)
        self.assertIn("CLOSE BELOW", en)
        self.assertIn("red line", en)
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "align_bot.py"), encoding="utf-8").read()
        self.assertIn("🟨 Ligne jaune ENTRÉE : attends la CLÔTURE 15 min", src)
        self.assertIn("BIENVENUE À", src)



class LectureTP1(unittest.TestCase):
    def r_(self, dirs, rsis=None, sqzs=None):
        return {"dirs": dirs + [0] * (11 - len(dirs)), "rsis": rsis or [50] * 11, "sqzs": sqzs or [0] * 11}

    def test_continue_vers_tp2(self):
        l = ab.lecture_tp1(self.r_([-1, -1, -1, -1, 0]), -1)
        self.assertIn("🚀 ÇA PEUT CONTINUER VERS LE TP2", l)
        self.assertTrue(any("EN DESSOUS" in x for x in l))

    def test_risque_de_retour(self):
        rs = [50] * 11; rs[4] = 25
        l = ab.lecture_tp1(self.r_([1, 1, 1, 0, -1], rs), -1)
        self.assertEqual(l[0], "⚠️ RISQUE DE RETOUR VERS L'ENTRÉE")
        self.assertTrue(any("RSI 15 min 25" in x for x in l))

    def test_hesitation_et_long(self):
        l = ab.lecture_tp1(self.r_([1, 0, -1, 0, 1]), 1)
        self.assertEqual(l[0], "🟨 LE MARCHÉ HÉSITE AU TP1")
        self.assertTrue(any("AU-DESSUS" in x for x in l))
        self.assertIn("IT CAN GO ON TO TP2", ab.traduire("🚀 ÇA PEUT CONTINUER VERS LE TP2"))


class CartesCouleursGraphique(unittest.TestCase):
    def test_cartes_parlent_des_lignes(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "align_bot.py"), encoding="utf-8").read()
        for mot in ("(ligne jaune)", "(ligne rouge)", "(ligne bleue)", "🔒 SL protégé", "🟨 Entrée {px(tr['e'])} • 🛑 SL"):
            self.assertIn(mot, src)
        self.assertIn("(red line)", ab.traduire("🛑 SL : 1 (ligne rouge)"))


if __name__ == "__main__":
    unittest.main()
