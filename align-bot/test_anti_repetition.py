"""Anti-répétition des messages Telegram : un même message (mêmes informations) n'est envoyé qu'une fois ; une information nouvelle passe toujours."""
import unittest
from unittest.mock import patch

import align_bot as ab

T0 = 1_800_000_000
ZONE = "🟥🟥 POINT D'ENTRÉE À VENIR — 🥇 GOLD\n🔽 SHORT\n👀 ÇA ARRIVE\n📍 Zone ≈ 3 995.20 – 3 997.20 (prochaine décision 14:35)"


class DoublonMessage(unittest.TestCase):
    def test_message_identique_envoye_une_fois(self):
        e = {}
        self.assertFalse(ab.doublon_message(e, ZONE, T0))
        self.assertTrue(ab.doublon_message(e, ZONE, T0 + 60))

    def test_heure_differente_seule_est_un_doublon(self):
        e = {}
        ab.doublon_message(e, ZONE, T0)
        self.assertTrue(ab.doublon_message(e, ZONE.replace("14:35", "15:05"), T0 + 1800))

    def test_derive_de_prix_minuscule_est_un_doublon(self):
        e = {}
        ab.doublon_message(e, "⛔ GOLD : zone 3995.20 – 3997.20", T0)
        self.assertTrue(ab.doublon_message(e, "⛔ GOLD : zone 3995.90 – 3997.60", T0 + 600))

    def test_zone_qui_bouge_vraiment_est_une_information_nouvelle(self):
        e = {}
        ab.doublon_message(e, "⛔ GOLD : zone 3995.20 – 3997.20", T0)
        self.assertFalse(ab.doublon_message(e, "⛔ GOLD : zone 3984.00 – 3986.00", T0 + 600))

    def test_reenvoi_possible_apres_3_heures(self):
        e = {}
        ab.doublon_message(e, ZONE, T0)
        self.assertFalse(ab.doublon_message(e, ZONE, T0 + ab.ANTI_REPETITION_S + 1))

    def test_marches_differents_ne_se_filtrent_pas(self):
        e = {}
        self.assertFalse(ab.doublon_message(e, "⛔ GOLD : le prix est reparti sans signal", T0))
        self.assertFalse(ab.doublon_message(e, "⛔ BTC : le prix est reparti sans signal", T0 + 10))

    def test_messages_d_execution_jamais_filtres(self):
        e = {}
        for txt in ("🟢🟢🟢 J'ENTRE MAINTENANT — GOLD\nEntrée 3995.2", "🎯 TP1 TOUCHÉ — GOLD\nTP1 3985", "❌ STOP TOUCHÉ — GOLD\nStop 4000",
                    "🔒 METS-TOI À BE — GOLD", "⚠️ NEWS USA DANS 40 MIN — 14:30", "🧠 L'IA ALIGN EN DIRECT — GOLD"):
            self.assertFalse(ab.doublon_message(e, txt, T0))
            self.assertFalse(ab.doublon_message(e, txt, T0 + 5), txt)

    def test_liste_de_valeurs_ne_fusionne_pas(self):
        modele1, n1 = ab._forme_message("RSI 5m 32 • 10m 41 • 1h 55")
        self.assertEqual(n1, [5.0, 32.0, 10.0, 41.0, 1.0, 55.0])
        self.assertEqual(ab._forme_message("prix 3 995.20")[1], [3995.2])

    def test_cycle_d_entree_ne_rejoue_pas_la_meme_annonce(self):
        e, envoyes = {}, 0
        for k in range(0, 2 * 3600, 600):                    # 2 h de cycles, même zone
            envoyes += 0 if ab.doublon_message(e, ZONE, T0 + k) else 1
        self.assertEqual(envoyes, 1)

    def test_etat_serialisable_pour_state_json(self):
        import json
        e = {}
        ab.doublon_message(e, ZONE, T0)
        e2 = json.loads(json.dumps(e))
        self.assertTrue(ab.doublon_message(e2, ZONE, T0 + 60))


class CommentaireIaOrphelin(unittest.TestCase):
    def test_pas_de_commentaire_ia_si_le_message_principal_est_un_doublon(self):
        e = {}
        ab.doublon_message(e, "🔔 JE PRÉPARE UNE POSITION — GOLD\nZone 3995.20", T0)             # déjà envoyé
        with patch.object(ab, "ia", return_value="avis") as ia_:
            sortie = ab.commentaires_ia_temps_reel(e, "GOLD", {}, {}, ["🔔 JE PRÉPARE UNE POSITION — GOLD\nZone 3995.20"])
        self.assertEqual(sortie, [])
        ia_.assert_not_called()

    def test_consultation_n_enregistre_pas(self):
        e = {}
        self.assertFalse(ab.doublon_message(e, "⛔ GOLD : test 100", T0, enregistrer=False))
        self.assertFalse(ab.doublon_message(e, "⛔ GOLD : test 100", T0 + 1))


class UneSeuleVoixZoneExtreme(unittest.TestCase):
    def test_meme_texte_pour_les_deux_chemins(self):
        r = {"posD": 0.05, "posW": 0.1}
        self.assertEqual(ab.texte_zone_extreme("GOLD", r, -1), ab.texte_zone_extreme("GOLD", r, -1))
        self.assertIn("tout en BAS", ab.texte_zone_extreme("GOLD", r, -1))

    def test_chemin_entree_et_chemin_global_partagent_la_meme_anti_repetition(self):
        cle = {}
        self.assertTrue(ab.alerte_extreme_due(cle, -1, T0))            # chemin « zone extrême » global
        self.assertFalse(ab.alerte_extreme_due(cle, -1, T0 + 300))     # chemin « entrée bloquée » : déjà dit, silence


class OrdreAnnulePerdu(unittest.TestCase):
    def tour(self, cle, t, confirme):
        r = {"t": t, "m1": [dict(t=t - 60, o=1, h=1, l=1, c=1), dict(t=t, o=1, h=1, l=1, c=1)], "confirme": confirme,
             "r5": [{"c": 1}, {"c": 1}], "posD": 0.5, "posW": 0.5, "fermeture": False}
        with patch.object(ab, "manipulation"), patch.object(ab, "meche_suspecte"), patch.object(ab, "niveaux_cles"):
            return [x for x in ab.agent("GOLD", r, cle, "") if "perdue" in (x if isinstance(x, str) else x[0])]

    def test_pas_de_message_si_aucun_ordre_annonce(self):
        self.assertEqual(self.tour({"aligne": -1}, T0, 0), [])

    def test_un_seul_message_malgre_l_oscillation(self):
        cle, n = {"aligne": -1, "ordre": {"e": 1}}, 0
        for k in range(6):
            n += len(self.tour(cle, T0 + k * 600, 0))
            cle.update(aligne=-1, ordre={"e": 1})                        # la confirmation revient puis repart
        self.assertEqual(n, 1)


if __name__ == "__main__":
    unittest.main()
