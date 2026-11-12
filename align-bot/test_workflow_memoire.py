"""La mémoire du bot (state.json) ne doit plus se perdre à chaque déploiement : attente de l'ancien worker, sauvegarde à clé unique."""
import pathlib
import unittest

WF = pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows" / "align-bot.yml"


class MemoireDuBot(unittest.TestCase):
    def setUp(self):
        self.t = WF.read_text(encoding="utf-8")

    def test_sauvegarde_a_cles_uniques_jamais_la_cle_fixe(self):
        save = self.t[self.t.index("Clé unique de sauvegarde de la mémoire"):]
        self.assertNotIn("key: align-etat-${{ github.run_id }}\n", save)                 # clé fixe refusée à l'arrêt (cache immuable)
        self.assertIn("steps.cle_sauvegarde.outputs.a", save)
        self.assertIn("steps.cle_sauvegarde.outputs.b", save)                           # deuxième exemplaire
        self.assertEqual(save.count("actions/cache/save@v4"), 2)
        self.assertEqual(save.count("if: always()"), 3)                                 # clé + 2 sauvegardes, même sur annulation

    def test_restauration_par_prefixe_et_attente_de_l_ancien_worker_avant(self):
        self.assertIn("restore-keys: align-etat-", self.t)                              # les nouvelles clés commencent par ce préfixe
        self.assertLess(self.t.index("Attendre la fin de l'ancien worker"), self.t.index("Récupérer la mémoire du robot"))

    def test_attente_bornee_et_non_bloquante(self):
        bloc = self.t[self.t.index("Attendre la fin de l'ancien worker"):self.t.index("Récupérer la mémoire du robot")]
        self.assertIn("continue-on-error: true", bloc)
        self.assertIn("< 240", bloc)                                                    # jamais plus de 4 minutes
        self.assertIn('x["id"] < me', bloc)                                           # n'attend que les workers plus anciens

    def test_permissions_minimales(self):
        entete = self.t[self.t.index("permissions:"):self.t.index("concurrency:")]
        self.assertIn("actions: read", entete)
        self.assertIn("contents: write", entete)                                         # uniquement la branche live-data (test_live_securite)
        self.assertNotIn("actions: write", entete)


if __name__ == "__main__":
    unittest.main()
