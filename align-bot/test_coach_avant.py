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

if __name__ == "__main__":
    unittest.main()
