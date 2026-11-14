import os, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import align_bot as ab

class CoachAvantEntree(unittest.TestCase):
    def test_temps_restant_fvg_et_validation_annoncee(self):
        with mock.patch.object(ab, "timeframe_attendu", return_value="15 min"), \
             mock.patch.object(ab, "prochaine_cloture_bougie", side_effect=lambda r, tf, now: now + 125):
            t = ab.avant_entree("BTC", {}, {}, {"src": "Order block + FVG rouge 15 min"}, -1)
        self.assertIn("clôture dans", t)
        self.assertIn("FVG", t)
        self.assertIn("rebondit", t)
        self.assertIn("✅ VALIDÉ 🔴 SHORT", t)

    def test_sans_fvg_pas_de_phrase_rebond(self):
        with mock.patch.object(ab, "timeframe_attendu", side_effect=Exception("x")):
            t = ab.avant_entree("GOLD", {}, {}, {"src": "plan"}, 1)
        self.assertNotIn("FVG", t)
        self.assertIn("✅ VALIDÉ 🟢 LONG", t)

class ApprocheTP(unittest.TestCase):
    def test_direction_tp2_si_ca_pousse(self):
        t = ab.approche_tp("BTC", {"dirs": [-1, -1, -1, 0, -1, 0, 0, -1, 0, -1, -1]}, -1, 65000, "TP2")
        self.assertIn("DIRECTION TP2", t); self.assertIn("café", t)

    def test_perturbation_expliquee(self):
        t = ab.approche_tp("GOLD", {"dirs": [1, 1, 1, 0, 0, 0, 0, -1, 0, -1, -1]}, -1, 3800, "TP1")
        self.assertIn("PETITE PERTURBATION", t); self.assertIn("3/5", t); self.assertIn("BE", t)

class CoachEnDirect(unittest.TestCase):
    def test_carte_a_chaque_cloture_puis_pas_de_doublon(self):
        envoyes = []
        etat = {"coach_live": {"BTC": {"9": {"expire": 9e12, "dernier_t": 0}}}}
        b15 = [dict(t=900 * i, o=100, h=101, l=98, c=99) for i in range(5)]
        r = {"b15": b15, "m1": [dict(c=99)], "confirme": -1, "dirs": [0] * 11}
        with mock.patch.object(ab, "_envoi_sur", side_effect=lambda cid, **k: envoyes.append(k["text"]) or {"ok": True}), \
             mock.patch.object(ab, "raison_attente", return_value="J'attends la zone"):
            ab.notifier_coach_live(etat, "BTC", r, {})
            ab.notifier_coach_live(etat, "BTC", r, {})
        self.assertEqual(len(envoyes), 1)
        self.assertIn("COACH COMMENTATEUR", envoyes[0]); self.assertIn("Bougie en baisse", envoyes[0]); self.assertIn("BILAN 15 MIN", envoyes[0])

    def test_fin_apres_2h_propose_de_continuer(self):
        envoyes = []
        etat = {"coach_live": {"GOLD": {"9": {"expire": 0, "dernier_t": 0}}}}
        r = {"b15": [dict(t=0, o=1, h=1, l=1, c=1), dict(t=900, o=1, h=1, l=1, c=1)]}
        with mock.patch.object(ab, "_envoi_sur", side_effect=lambda cid, **k: envoyes.append(k["text"]) or {"ok": True}):
            ab.notifier_coach_live(etat, "GOLD", r, {})
        self.assertIn("TERMINÉ", envoyes[0]); self.assertEqual(etat["coach_live"]["GOLD"], {})

class FlashCommentateur(unittest.TestCase):
    def test_mouvement_brusque(self):
        r = {"atr": 100, "m1": [dict(o=1000, c=990), dict(o=990, c=960), dict(o=960, c=930)], "b15": []}
        t = ab.flash_commentateur("BTC", r, {"trade": {"d": -1}})
        self.assertIn("ÇA BOUGE", t); self.assertIn("vendeurs", t); self.assertIn("Dans le sens du bot", t)

    def test_grosse_meche(self):
        r = {"atr": 100, "m1": [dict(o=1000, c=1000)] * 3, "b15": [dict(o=990, h=1080, l=985, c=1000)]}
        t = ab.flash_commentateur("GOLD", r, {})
        self.assertIn("GROSSE MÈCHE", t)

    def test_rien_de_special(self):
        r = {"atr": 100, "m1": [dict(o=1000, c=1001)] * 3, "b15": [dict(o=1000, h=1010, l=995, c=1001)]}
        self.assertIsNone(ab.flash_commentateur("BTC", r, {}))

class CanalMarche(unittest.TestCase):
    def test_connexion_canal_btc_sans_toucher_au_vip(self):
        etat = {"canal": "VIP"}
        with mock.patch.object(ab, "_envoi_sur"), mock.patch.object(ab, "proprio", return_value=[]):
            ab.connecter_canal(etat, {"chat": {"id": -100, "title": "ALIGN BTC", "username": "alignbtc"}, "new_chat_member": {"status": "administrator"}})
        self.assertEqual(etat["canaux_marche"]["BTC"], "-100"); self.assertEqual(etat["canal"], "VIP")

    def test_canal_sans_niveaux(self):
        envoyes = []
        etat = {"canaux_marche": {"BTC": "-100"}}
        b15 = [dict(t=900 * i, o=100, h=101, l=98, c=99) for i in range(5)]
        r = {"b15": b15, "m1": [dict(c=99)], "confirme": -1, "dirs": [0] * 11}
        cle = {"trade": {"d": -1, "e": 120, "sl": 130, "tp1": 90}}
        with mock.patch.object(ab, "_envoi_sur", side_effect=lambda cid, **k: envoyes.append((cid, k["text"])) or {"ok": True}):
            ab.notifier_canal_marche(etat, "BTC", r, cle)
        self.assertEqual(envoyes[0][0], "-100")
        self.assertIn("pas une entrée", envoyes[0][1]); self.assertNotIn("130", envoyes[0][1])

class Accueil(unittest.TestCase):
    def test_questionnaire_puis_liens(self):
        envoyes = []
        etat = {"liens_marche": {"BTC": "https://t.me/+abc"}}
        with mock.patch.object(ab, "_envoi_sur", side_effect=lambda cid, **k: envoyes.append(k) or {"ok": True}):
            ab.accueil_questionnaire(etat, "7")
            ab.accueil_marches(etat, "7")
            ab.accueil_liens(etat, "7", "BTC")
        self.assertIn("niveau", envoyes[0]["text"]); self.assertIn("marché", envoyes[1]["text"])
        self.assertIn("https://t.me/+abc", envoyes[2]["reply_markup"])
        self.assertEqual(ab.marches_choisis(etat, "7"), {"BTC"})

if __name__ == "__main__":
    unittest.main()
