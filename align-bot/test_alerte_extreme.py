"""Alerte « zone extrême Daily/Weekly » : une seule fois par situation (pas de doublon toutes les 2 h ni à chaque oscillation de libellé)."""
import unittest
from unittest.mock import patch

import align_bot as ab


def bougie(t, c=100.0):
    return dict(t=t, o=c, h=c + 0.1, l=c - 0.1, c=c, v=1)


def lecture(t, posW=0.10):
    return {"t": t, "m1": [bougie(t - 60), bougie(t)], "confirme": -1, "r5": [{"c": 1}, {"c": 1}], "posD": 0.05, "posW": posW,
            "fermeture": False}


class AlerteExtreme(unittest.TestCase):
    def tour(self, cle, t, posW=0.10):
        with patch.object(ab, "manipulation"), patch.object(ab, "meche_suspecte"), patch.object(ab, "niveaux_cles"), \
             patch.object(ab, "bloque_dw", return_value=True):
            return [x for x in ab.agent("GOLD", lecture(t, posW), cle, "") if "zone extrême" in x]

    def test_une_seule_alerte_pendant_toute_la_situation(self):
        cle, n = {}, 0
        for k in range(0, 12 * 3600, 60):                        # 12 h, un tour par minute, même situation
            n += len(self.tour(cle, 1_800_000_000 + k))
        self.assertEqual(n, 1)

    def test_libelle_weekly_qui_oscille_ne_relance_pas(self):
        cle, n = {}, 0
        for k in range(0, 3600, 60):
            n += len(self.tour(cle, 1_800_000_000 + k, posW=0.10 if k % 120 else 0.20))      # « tout en BAS » <-> « en bas »
        self.assertEqual(n, 1)

    def test_rearmement_apres_disparition_de_la_situation(self):
        cle = {}
        self.assertEqual(len(self.tour(cle, 1_800_000_000)), 1)
        self.assertEqual(len(self.tour(cle, 1_800_000_000 + 600)), 0)
        self.assertEqual(len(self.tour(cle, 1_800_000_000 + ab.EXTREME_REARMEMENT_S + 3600)), 1)

    def test_changement_de_sens_relance(self):
        cle = {}
        self.assertTrue(ab.alerte_extreme_due(cle, -1, 1_800_000_000))
        self.assertFalse(ab.alerte_extreme_due(cle, -1, 1_800_000_060))
        self.assertTrue(ab.alerte_extreme_due(cle, 1, 1_800_000_120))

    def test_persiste_dans_l_etat_sauvegarde(self):
        import json
        cle = {}
        self.tour(cle, 1_800_000_000)
        cle2 = json.loads(json.dumps(cle))                       # simule state.json -> redémarrage
        self.assertEqual(len(self.tour(cle2, 1_800_000_060)), 0)


if __name__ == "__main__":
    unittest.main()
