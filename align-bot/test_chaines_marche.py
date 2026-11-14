import unittest
from unittest import mock
import align_bot as ab


class PreparerChaines(unittest.TestCase):
    def setUp(self):
        self.appels = []
        self.p = [mock.patch.object(ab, "TOKEN", "x"),
                  mock.patch.object(ab, "photo_canal", side_effect=lambda c: self.appels.append(("photo", c)) or True),
                  mock.patch.object(ab, "telegram", side_effect=lambda meth, **k: self.appels.append((meth, k["chat_id"])) or {"ok": True})]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()

    def test_logo_et_description_pour_les_3_chaines_meme_marche_ferme(self):
        etat = {"canaux_marche": {"BTC": -1, "GOLD": -2, "NASDAQ": -3}}
        ab.preparer_chaines(etat)
        for c in (-1, -2, -3):
            self.assertIn(("photo", c), self.appels)
            self.assertIn(("setChatDescription", c), self.appels)
        self.appels.clear()
        ab.preparer_chaines(etat)                       # déjà fait : rien n'est renvoyé
        self.assertEqual(self.appels, [])

    def test_echec_photo_reessaye_plus_tard(self):
        etat = {"canaux_marche": {"GOLD": -2}}
        with mock.patch.object(ab, "photo_canal", return_value=False):
            ab.preparer_chaines(etat)
        self.assertFalse(etat["canal_live"]["GOLD"]["photo_ok"])
        etat["canal_live"]["GOLD"]["photo_essai"] = 0  # une heure plus tard
        ab.preparer_chaines(etat)
        self.assertTrue(etat["canal_live"]["GOLD"]["photo_ok"])


class PasDeDoublon(unittest.TestCase):
    def setUp(self):
        ab._CACHE_CHAINE.clear()
        self.etat = {"canaux_marche": {"BTC": -1, "GOLD": -2}}

    def test_commentaire_saute_si_dans_la_chaine(self):
        with mock.patch.object(ab, "TOKEN", "x"), \
             mock.patch.object(ab, "telegram", return_value={"ok": True, "result": {"status": "member"}}):
            self.assertTrue(ab.doublon_chaine(self.etat, 5, "🎙 ÇA BOUGE !\n🟠 BTC : 66000"))
            self.assertFalse(ab.doublon_chaine(self.etat, 5, "🚦 🟢 J'ENTRE MAINTENANT — BTC"))   # perso : reste dans le bot

    def test_commentaire_garde_si_pas_dans_la_chaine(self):
        with mock.patch.object(ab, "TOKEN", "x"), \
             mock.patch.object(ab, "telegram", return_value={"ok": True, "result": {"status": "left"}}):
            self.assertFalse(ab.doublon_chaine(self.etat, 6, "🎙 ÇA BOUGE !\n🟠 BTC : 66000"))

    def test_ca_bouge_dit_ou_ca_va(self):
        m1 = [{"o": 100, "h": 100, "l": 90, "c": 95}, {"o": 95, "h": 95, "l": 85, "c": 88}, {"o": 88, "h": 88, "l": 80, "c": 82}]
        t = ab.flash_commentateur("BTC", {"m1": m1, "atr": 10}, {"trade": {"d": -1, "e": 101, "sl": 110, "tp1": 85}})
        self.assertIn("ÇA BOUGE", t); self.assertIn("Direction TP2", t)
        t = ab.flash_commentateur("BTC", {"m1": m1, "atr": 10, "confirme": -1}, {})
        self.assertIn("sens de la tendance", t)


if __name__ == "__main__":
    unittest.main()
