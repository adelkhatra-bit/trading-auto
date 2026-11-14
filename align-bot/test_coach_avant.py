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

if __name__ == "__main__":
    unittest.main()
