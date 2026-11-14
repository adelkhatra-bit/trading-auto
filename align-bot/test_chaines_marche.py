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


if __name__ == "__main__":
    unittest.main()
