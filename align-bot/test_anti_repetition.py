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
        txt = ab.texte_zone_extreme("GOLD", r, -1)
        for morceau in ("tout en BAS", "4h + 1h alignées ▼", "Je ne poursuis pas le SHORT", "rebond", "retournement confirmé en 1h + clôture 5m", "meilleur prix"):
            self.assertIn(morceau, txt)                                              # aucune information des deux anciens messages perdue

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

    def test_message_conserve_meme_sans_ordre_annonce(self):
        self.assertEqual(len(self.tour({"aligne": -1}, T0, 0)), 1)                  # rien n'a été retiré : le message part comme avant

    def test_un_seul_message_malgre_l_oscillation(self):
        cle, n = {"aligne": -1, "ordre": {"e": 1}}, 0
        for k in range(6):
            n += len(self.tour(cle, T0 + k * 600, 0))
            cle.update(aligne=-1, ordre={"e": 1})                        # la confirmation revient puis repart
        self.assertEqual(n, 1)


if __name__ == "__main__":
    unittest.main()


class BattementSansOscillation(unittest.TestCase):
    base = (-1, 8, "DAY", "CONFIRMÉ", -1, 3990.0, 4.0)

    def test_oscillation_est_faible_donc_limitee_a_une_info_par_30_min(self):
        for n in (9, 7 + 2, 10):                                    # 8 -> 9 / 10 : même côté du seuil, moins de 3 UT
            self.assertEqual(ab.hb_evolution(self.base, (-1, n, "DAY", "CONFIRMÉ", -1, 3990.0, 4.0)), 1, n)
        self.assertEqual(ab.hb_evolution(self.base, self.base), 0)
        self.assertEqual(ab.hb_evolution(self.base, (-1, 8, "DAY", "CONFIRMÉ", -1, 3992.0, 4.0)), 1)   # zone d'un demi-ATR

    def test_vraies_evolutions_sont_fortes_donc_toujours_envoyees(self):
        b = self.base
        for nouveau in ((1,) + b[1:], b[:2] + ("SWING",) + b[3:], b[:3] + ("EN ATTENTE",) + b[4:], b[:4] + (1,) + b[5:],
                        (-1, 7) + b[2:], (-1, 11) + b[2:], b[:5] + (3995.0, 4.0), b[:5] + (None, 4.0)):
            self.assertEqual(ab.hb_evolution(b, nouveau), 2, nouveau)

    def test_premier_battement_et_ancien_format_d_etat(self):
        self.assertEqual(ab.hb_evolution(None, self.base), 2)
        self.assertEqual(ab.hb_evolution([-1, 8, "DAY", "CONFIRMÉ", -1, 12], self.base), 2)

    def test_serie_reelle_de_l_audit(self):
        """L'oscillation de l'audit (UT 8/9, zone d'un demi-ATR) : 120 minutes = 4 infos au plus (une par 30 min), pas 24 (une par 5 min)."""
        envoyes, dernier, t_dernier = 0, None, -10_000
        for k in range(0, 120):
            n = 8 + (k % 3 == 0)
            sig = (-1, n, "DAY", "CONFIRMÉ", -1, 3990.0 + (2.0 if k % 2 else 0.0), 4.0)
            niveau = ab.hb_evolution(dernier, sig)
            if niveau == 2 or (niveau == 1 and (k - t_dernier) * 60 >= ab.HB_INTERVALLE_FAIBLE):
                envoyes += 1; dernier = sig; t_dernier = k
        self.assertLessEqual(envoyes, 5)


class RoutageParCompte(unittest.TestCase):
    """Demande d'Adel : si je ne coche que GOLD et NASDAQ, je ne reçois QUE ces marchés (messages, lignes, sessions)."""
    ETAT = {"marches_par_chat": {"adel": ["GOLD", "NASDAQ"], "btc": ["BTC"], "tous": ["BTC", "GOLD", "NASDAQ"]}}

    def test_message_tague_n_est_plus_devine_depuis_le_texte(self):
        avis = ab.taguer("🧠 L'avis de l'IA ALIGN\nLe cours monte, prudence.", "BTC")           # aucun marché dans le texte
        self.assertEqual(sorted(ab.destinataires_message(self.ETAT, {"adel", "btc", "tous"}, avis)), ["btc", "tous"])

    def test_message_sans_tag_ni_marche_reste_global(self):
        self.assertEqual(sorted(ab.destinataires_message(self.ETAT, {"adel", "btc"}, "📅 Aucune annonce majeure US aujourd'hui.")), ["adel", "btc"])

    def test_tuple_avec_clavier_garde_son_tag(self):
        x = ab.taguer(("texte", "clavier"), "GOLD")
        self.assertEqual(x[1], "clavier")
        self.assertEqual(ab.marches_message(x[0]), {"GOLD"})

    def test_reaction_news_filtree_ligne_par_ligne(self):
        txt = "📰 RÉACTION À LA NEWS — CPI\n🟠 BTC : +12 $ en 10 min ⬆️\n🥇 GOLD : -4 $ en 10 min ⬇️\n💠 NASDAQ : +30 $ en 10 min ⬆️\n⏳ J'attends la clôture"
        sortie = ab.filtrer_texte_par_marches(txt, {"GOLD", "NASDAQ"})
        self.assertNotIn("BTC", sortie)
        for garde in ("RÉACTION À LA NEWS", "GOLD", "NASDAQ", "J'attends la clôture"):
            self.assertIn(garde, sortie)                                                    # rien d'autre n'est retiré

    def test_message_d_un_marche_non_coche_n_arrive_pas(self):
        self.assertIsNone(ab.filtrer_texte_par_marches("⚠️ BTC : prudence", {"GOLD", "NASDAQ"}))
        self.assertEqual(ab.filtrer_texte_par_marches("⚠️ GOLD : prudence", {"GOLD", "NASDAQ"}), "⚠️ GOLD : prudence")

    def test_sans_choix_ou_tout_coche_rien_n_est_modifie(self):
        txt = "x\n🟠 BTC : 1\n🥇 GOLD : 2"
        self.assertEqual(ab.filtrer_texte_par_marches(txt, None), txt)
        self.assertEqual(ab.filtrer_texte_par_marches(txt, {"BTC", "GOLD", "NASDAQ"}), txt)

    def test_ligne_squeeze_reduite_aux_marches_coches(self):
        lignes = ["🔔 Ouverture Londres dans 15 min", "⚡ BTC, GOLD comprimé : explosion possible"]
        self.assertEqual(ab.ajuster_squeeze(lignes, {"GOLD", "NASDAQ"})[1], "⚡ GOLD comprimé : explosion possible")
        self.assertEqual(len(ab.ajuster_squeeze(lignes, {"NASDAQ"})), 1)                     # plus aucun marché : ligne supprimée
        self.assertEqual(ab.ajuster_squeeze(lignes, None), lignes)

    def test_alertes_courtes_chaque_compte_ne_recoit_que_ses_marches(self):
        envois = []
        evts = [({"BTC"}, ["🟠 BTC : alignement 9/11"], ["🟠 BTC: aligned 9/11"]),
                ({"GOLD"}, ["🥇 GOLD : alignement 9/11"], ["🥇 GOLD: aligned 9/11"]),
                ({"*"}, ["🔔 Ouverture Londres dans 15 min", "⚡ BTC, GOLD comprimé : explosion possible"], ["x"])]
        etat = dict(self.ETAT)
        with patch.object(ab, "_envoi_sur", side_effect=lambda c, **k: envois.append((c, k["text"]))):
            ab.diffuser_evenements(etat, {"adel", "btc", "tous"}, evts)
        par = {c: t for c, t in envois}
        self.assertIn("GOLD", par["adel"]); self.assertNotIn("🟠", par["adel"]); self.assertNotIn("BTC", par["adel"])
        self.assertIn("BTC", par["btc"]); self.assertNotIn("🥇", par["btc"])
        self.assertIn("🟠", par["tous"]); self.assertIn("🥇", par["tous"])


class ZoneDeRetournementVisee(unittest.TestCase):
    def r(self, prix, **kw):
        return dict({"m1": [dict(t=1, o=prix, h=prix, l=prix, c=prix)], "dirPlan": -1, "zone_pine": {"za": 3994.0, "zb": 4011.0, "zmil": 4002.0}}, **kw)

    def test_zone_du_plan_avec_sens_et_distance(self):
        l = ab.zone_retournement_visee(self.r(3985.0), {})
        self.assertIn("3994", l[0]); self.assertIn("4011", l[0]); self.assertIn("SHORT", l[0])
        self.assertIn("au-dessus", l[1]); self.assertIn("9", l[1])                    # zone à 9 pts au-dessus du prix

    def test_prix_dans_la_zone(self):
        self.assertIn("dans la zone", ab.zone_retournement_visee(self.r(4000.0), {})[1])

    def test_ordre_surveille_garde_ses_chiffres(self):
        l = ab.zone_retournement_visee(self.r(3985.0), {"ordre": {"e": 3996.0, "za": 3995.2, "zb": 3997.2, "d": -1}})
        self.assertIn("3995", l[0]); self.assertIn("3997", l[0])

    def test_jamais_inventee_sans_plan(self):
        l = ab.zone_retournement_visee(self.r(3985.0, dirPlan=0), {})
        self.assertEqual(len(l), 1); self.assertIn("pas encore définie", l[0])


class FormeDesMessages(unittest.TestCase):
    """Relecture des vrais messages : lisibilité (plages de prix, consigne d'abord, marchés de la personne)."""
    def test_plage_de_prix_reste_entiere(self):
        t = ab.mise_en_forme("⏳ 🥇 GOLD : en attente\n📍 Zone d'entrée : 3986.06 – 4024.39 (prix à 14.38)\n📍 Zone d'entrée : 3986.00 → 3990.00 (prix dans la zone)")
        self.assertIn("Zone d'entrée : 3986,06 → 4024,39 (prix à 14.38)", t)
        self.assertIn("3986 → 3990 (prix dans la zone)", t)
        self.assertNotIn("(4024", t)                                              # bug réel : « 3986,06 (4024,39 (prix à 14,38) »

    def test_prix_isole_inchange(self):
        self.assertIn("Entrée : 4075,50", ab.mise_en_forme("t\n📌 Entrée : 4 075.50"))

    def test_battement_consigne_d_abord(self):
        r = {"dirPlan": -1, "sens": -1, "bull": 0, "bear": 11, "pctH": 86, "strat": "SWING", "dirs": [-1] * 11, "atr": 4.0,
             "zone_pine": {"za": 3986.06, "zb": 4024.39, "zmil": 4005.22}, "prix": 3972.0, "m1": [{"c": 3972.0}], "b5": [0] * 30}
        l = ab.texte_battement("GOLD", r, {}, vip=True).split("\n")
        self.assertTrue(l[1].startswith("🕯 J'attends une clôture 1h sous 4005,22"), l)       # la consigne juste sous le titre
        self.assertTrue(l[2].startswith("🧭 Sens probable"))
        for garde in ("📍 Zone d'entrée", "📊 UT alignées : 11/11", "🎯 Profil visé"):
            self.assertTrue(any(x.startswith(garde) for x in l), garde)                # rien n'a disparu

    def test_session_marches_de_la_personne(self):
        self.assertEqual(ab.adapter_marches_session(["⏰ Ouverture Londres", "💥 Volatilité attendue sur GOLD et BTC"], "GOLD et BTC", {"GOLD", "NASDAQ"}),
                         ["⏰ Ouverture Londres", "💥 Volatilité attendue sur GOLD"])
        self.assertIsNone(ab.adapter_marches_session(["x GOLD et BTC"], "GOLD et BTC", {"NASDAQ"}))               # aucun de ses marchés
        self.assertEqual(ab.adapter_marches_session(["NASDAQ, GOLD et BTC"], "NASDAQ, GOLD et BTC", {"NASDAQ", "GOLD"}), ["NASDAQ et GOLD"])
        self.assertEqual(ab.adapter_marches_session(["a GOLD and BTC"], "GOLD and BTC", {"GOLD", "BTC"}, True), ["a GOLD and BTC"])
        self.assertEqual(ab.adapter_marches_session(["x GOLD et BTC"], "GOLD et BTC", None), ["x GOLD et BTC"])         # pas de choix : inchangé

    def test_diffusion_session_adaptee_par_compte(self):
        envois = []
        etat = {"marches_par_chat": {"adel": ["GOLD", "NASDAQ"], "nas": ["NASDAQ"], "tous": ["BTC", "GOLD", "NASDAQ"]}}
        evts = [({"*"}, ["🚨 Londres ouvre dans 5 min", "💥 Attention à la volatilité sur GOLD et BTC"], ["x"], ("GOLD et BTC", "GOLD and BTC"))]
        with patch.object(ab, "_envoi_sur", side_effect=lambda c, **k: envois.append((c, k["text"]))):
            ab.diffuser_evenements(etat, {"adel", "nas", "tous"}, evts)
        par = dict(envois)
        self.assertIn("sur GOLD", par["adel"]); self.assertNotIn("BTC", par["adel"])
        self.assertNotIn("nas", par)                                                  # NASDAQ seul : Londres ne le concerne pas
        self.assertIn("GOLD et BTC", par["tous"])


class SensIaCoherent(unittest.TestCase):
    """Cas signalé par Adel : « gros mouvement baissier à venir » pendant que le marché explosait à la hausse."""
    def test_sens_contraire_a_l_indicateur_bloque(self):
        self.assertTrue(ab.sens_ia_contradictoire("Gros mouvement baissier à venir, reste prudent.", 1))
        self.assertTrue(ab.sens_ia_contradictoire("Le prix va chuter, SHORT possible.", 1))
        self.assertTrue(ab.sens_ia_contradictoire("Gros mouvement haussier à venir.", -1))
        self.assertTrue(ab.sens_ia_contradictoire("Prépare un LONG.", -1))

    def test_meme_sens_ou_description_du_passe_passe(self):
        self.assertFalse(ab.sens_ia_contradictoire("Mouvement haussier en cours, attends le repli.", 1))
        self.assertFalse(ab.sens_ia_contradictoire("BTC en forte baisse, RSI très bas. Patience, surveille le rebond.", -1))
        self.assertFalse(ab.sens_ia_contradictoire("Un long mouvement vient de se terminer, prudence.", 1))          # « long » (adjectif) ≠ LONG
        self.assertFalse(ab.sens_ia_contradictoire("Marché baissier à court terme mais rebond haussier possible.", 1)) # cite aussi le bon sens

    def test_sans_sens_de_l_indicateur_aucun_blocage(self):
        self.assertFalse(ab.sens_ia_contradictoire("Gros mouvement baissier à venir.", 0))
        self.assertFalse(ab.sens_ia_contradictoire("Gros mouvement baissier à venir.", None))

    def test_commentaire_en_direct_contradictoire_n_est_pas_envoye(self):
        r = {"sens": 1}
        with patch.object(ab, "ia", return_value="Gros mouvement baissier à venir."), patch.object(ab, "donnees_ia", return_value={}):
            sortie = ab.commentaires_ia_temps_reel({}, "GOLD", r, {}, ["⚡⚡ PRÉPARE-TOI — 🥇 GOLD\nzone"])
        self.assertEqual(sortie, [])

    def test_commentaire_en_direct_coherent_est_envoye(self):
        r = {"sens": 1}
        with patch.object(ab, "ia", return_value="Mouvement haussier en cours, attends le repli."), patch.object(ab, "donnees_ia", return_value={}):
            sortie = ab.commentaires_ia_temps_reel({}, "GOLD", r, {}, ["⚡⚡ PRÉPARE-TOI — 🥇 GOLD\nzone"])
        self.assertEqual(len(sortie), 1)
        self.assertIn("haussier", sortie[0])

    def test_consigne_interdit_la_prediction_de_sens(self):
        self.assertIn("JAMAIS un sens à venir", ab.REGLE_SENS_IA)


class MessageEntreeLisible(unittest.TestCase):
    """Rendu réel d'un message d'entrée (même formateur que Telegram) : l'essentiel d'abord, aucune ligne coupée."""
    TR = dict(d=-1, e=3995.2, sl=3999.99, tp1=3985.0, tp2=3895.54, n1="15m", n2="plan SWING", rr=2.1, za=3995.2, zb=3997.2,
              strat="SWING", src="Fibonacci + 15m", statut="entree", sl_h=1)

    def rendu(self):
        return ab.mise_en_forme(f"🟢🟢🟢 J'ENTRE MAINTENANT — 🥇 GOLD\\n👉 {ab.resume_ordre(self.TR)}\\n{ab.SENS[-1]}\\n\\n{ab.fmt_trade('GOLD', self.TR, 3994.0)}")

    def test_essentiel_dans_les_premieres_lignes(self):
        haut = "\\n".join(self.rendu().splitlines()[:8])
        for k in ("J'ENTRE MAINTENANT", "SHORT", "Entrée 3995,20", "SL 3999,99", "TP1 3985", "TP2 3895,54"):
            self.assertIn(k, haut)

    def test_lignes_non_coupees_et_parentheses_equilibrees(self):
        t = self.rendu()
        self.assertIn("Ratio gain/risque TP1 : 1:2.1", t)                                     # plus « 1 (2.1) »
        self.assertIn("Vue d'entrée : 5 minutes (15M = préparation, M5 = timing après clôture confirmée)", t)
        self.assertIn("Distance entrée → SL : 0.12 % du prix (pas le % du capital risqué)", t)
        for l in t.splitlines():
            self.assertEqual(l.count("("), l.count(")"), l)

    def test_position_longue_duree_ne_se_lit_pas_comme_un_long(self):
        t = ab.mise_en_forme(ab.fmt_trade("GOLD", dict(self.TR, tp2=3000.0, n2="Daily"), 3994.0))
        self.assertNotIn("Position LONGUE", t)
        self.assertIn("LONGUE DURÉE", t)

    def test_prix_et_niveaux_toujours_formates(self):
        self.assertIn("Entrée : 4075,50 (ordre limite)", ab.mise_en_forme("t\\n🟨 Entrée : 4 075.50 (ordre limite)"))
        self.assertIn("TP1 : 3985 (15m)", ab.mise_en_forme("t\\n💰 TP1 : 3985.00 (15m)"))


class CoachDeConcentration(unittest.TestCase):
    """« Dis-moi sur quel marché me concentrer » : le plus proche d'une entrée, sa zone, le sens, la clôture à attendre."""
    def r(self, prix, za, zb, d=-1, atr=4.0, **kw):
        return dict({"m1": [dict(t=1, o=prix, h=prix, l=prix, c=prix)], "dirPlan": d, "atr": atr, "strat": "SWING",
                     "zone_pine": {"za": za, "zb": zb, "zmil": (za + zb) / 2}, "posD": 0.5, "posW": 0.5, "basD": 0, "hautD": 1, "basW": 0, "hautW": 1}, **kw)

    def derniers(self):
        return {"GOLD": self.r(3985.0, 3994.0, 4012.0),            # à 9 pts ≈ 2,3 ATR : en approche
                "NASDAQ": self.r(28000.0, 28500.0, 28700.0, atr=40.0),   # à 500 pts ≈ 12 ATR : loin
                "BTC": self.r(73000.0, 73010.0, 73400.0, d=1, atr=200.0)}  # à 10 pts : proche

    def classer(self, derniers=None, choisis=None, etats=None):
        with patch.object(ab, "cme_ouvert", return_value=True), patch.object(ab, "bloque_dw", return_value=False):
            return ab.classer_marches(derniers or self.derniers(), etats or {}, choisis or {"GOLD", "NASDAQ", "BTC"}, 1_800_000_000)

    def test_le_plus_proche_en_premier(self):
        p = self.classer()
        self.assertEqual([x["m"] for x in p], ["BTC", "GOLD", "NASDAQ"])
        self.assertEqual([x["classe"] for x in p], ["proche", "en_approche", "loin"])

    def test_seuls_les_marches_coches_sont_compares(self):
        p = self.classer(choisis={"GOLD", "NASDAQ"})
        self.assertEqual([x["m"] for x in p], ["GOLD", "NASDAQ"])
        txt = ab.texte_concentration(p, True)
        self.assertNotIn("BTC", txt)

    def test_prix_dans_la_zone_passe_devant(self):
        d = self.derniers(); d["NASDAQ"] = self.r(28600.0, 28500.0, 28700.0, atr=40.0)
        p = self.classer(d)
        self.assertEqual((p[0]["m"], p[0]["classe"]), ("NASDAQ", "dans_zone"))

    def test_marche_ferme_bloque_ou_en_position_ne_sont_jamais_favoris(self):
        d = self.derniers()
        with patch.object(ab, "cme_ouvert", return_value=False), patch.object(ab, "bloque_dw", return_value=False):
            p = ab.classer_marches(d, {}, {"GOLD", "BTC"}, 1_800_000_000)
        self.assertEqual(p[0]["m"], "BTC")                                           # BTC 24/7, GOLD fermé
        self.assertEqual(p[1]["classe"], "ferme")
        with patch.object(ab, "cme_ouvert", return_value=True), patch.object(ab, "bloque_dw", return_value=True):
            self.assertEqual({x["classe"] for x in ab.classer_marches(d, {}, {"GOLD", "BTC"}, 1_800_000_000)}, {"bloque"})
        p = self.classer(etats={"BTC": {"trade": {"d": 1}}})
        self.assertEqual([x["classe"] for x in p if x["m"] == "BTC"], ["position"])
        self.assertNotEqual(p[0]["m"], "BTC")
        d2 = self.derniers(); d2["GOLD"]["dirPlan"] = 0; d2["GOLD"]["zone_pine"] = None
        self.assertEqual([x["classe"] for x in self.classer(d2) if x["m"] == "GOLD"], ["sans_plan"])

    def test_message_vip_zone_sens_distance_et_unite(self):
        txt = ab.texte_concentration(self.classer(), True)
        l = txt.split("\n")
        self.assertEqual(l[0], "🎯 OÙ TE CONCENTRER")
        self.assertIn("BTC", l[1]); self.assertIn("le plus proche", l[1])
        self.assertIn("LONG", txt); self.assertIn("73010", txt); self.assertIn("73400", txt)                    # zone visée
        self.assertIn("ATR 15 min", txt); self.assertIn("À surveiller : clôture 1h au-dessus de 73205", txt)    # unité à surveiller
        self.assertIn("GOLD : en approche", txt); self.assertIn("NASDAQ : loin de la zone", txt)
        self.assertIn("Je les surveille pour toi", txt)

    def test_message_gratuit_sans_zone_ni_niveaux(self):
        txt = ab.texte_concentration(self.classer(), False)
        self.assertIn("BTC", txt); self.assertIn("VIP", txt)
        for interdit in ("73010", "73400", "73205", "zone de retournement", "À surveiller"):
            self.assertNotIn(interdit, txt)

    def test_aucun_favori_si_tout_est_bloque_ou_ferme(self):
        with patch.object(ab, "cme_ouvert", return_value=False):
            p = ab.classer_marches({"GOLD": self.r(3985.0, 3994.0, 4012.0)}, {}, {"GOLD"}, 1_800_000_000)
        self.assertIsNone(ab.texte_concentration(p, True))

    def test_aucun_marche_proche_le_dit_honnetement(self):
        d = {"NASDAQ": self.r(28000.0, 28500.0, 28700.0, atr=40.0), "GOLD": self.r(3900.0, 3994.0, 4012.0)}
        txt = ab.texte_concentration(self.classer(d, {"GOLD", "NASDAQ"}), True)
        self.assertIn("aucun n'est proche", txt)

    def test_envoi_automatique_seulement_quand_le_favori_change_et_pas_plus_d_une_fois_par_30_min(self):
        etat, envois = {"marches_par_chat": {"adel": ["GOLD", "NASDAQ", "BTC"], "solo": ["GOLD"]}}, []
        with patch.object(ab, "_envoi_sur", side_effect=lambda c, **k: envois.append((c, k["text"]))), patch.object(ab, "autorise", return_value=True), \
             patch.object(ab, "cme_ouvert", return_value=True), patch.object(ab, "bloque_dw", return_value=False):
            T = 1_800_000_000
            ab.coach_concentration(etat, {"adel", "solo"}, self.derniers(), T)
            self.assertEqual([c for c, _ in envois], ["adel"])                                    # « solo » ne suit qu'un marché : rien à comparer
            ab.coach_concentration(etat, {"adel"}, self.derniers(), T + 60)
            ab.coach_concentration(etat, {"adel"}, self.derniers(), T + 3600)                    # même favori, pas plus proche : silence
            self.assertEqual(len(envois), 1)
            d = self.derniers(); d["GOLD"] = self.r(4000.0, 3994.0, 4012.0)                      # GOLD entre dans la zone : nouveau favori
            ab.coach_concentration(etat, {"adel"}, d, T + 120)                                    # trop tôt (< 30 min)
            self.assertEqual(len(envois), 1)
            ab.coach_concentration(etat, {"adel"}, d, T + 3700)
            self.assertEqual(len(envois), 2)
            self.assertIn("GOLD", envois[1][1].split("\n")[1])

    def test_le_gratuit_ne_recoit_pas_l_envoi_automatique(self):
        envois = []
        with patch.object(ab, "_envoi_sur", side_effect=lambda c, **k: envois.append(c)), patch.object(ab, "autorise", return_value=False), \
             patch.object(ab, "cme_ouvert", return_value=True), patch.object(ab, "bloque_dw", return_value=False):
            ab.coach_concentration({"marches_par_chat": {"x": ["GOLD", "BTC"]}}, {"x"}, self.derniers(), 1_800_000_000)
        self.assertEqual(envois, [])

    def test_commande_focus_declaree_dans_le_menu(self):
        self.assertIn("/focus", ab.COMMANDES)


class StatutOperationnel(unittest.TestCase):
    """/statut : chaque ligne vient d'une donnée réelle du worker ; « tout est opérationnel » seulement si rien ne cloche."""
    T = 1_800_000_000

    def derniers(self, age=30):
        r = {"m1": [dict(t=self.T - age, o=1, h=1, l=1, c=1)], "dirPlan": -1, "bull": 1, "bear": 9}
        return {"BTC": r, "GOLD": r, "NASDAQ": r}

    def etat(self, **kw):
        return dict({"ia_dernier_statut": "CONNECTED", "ia_dernier_fournisseur": "Groq", "sauve_t": self.T - 120,
                     "cal": {"ev": [{"t": self.T + 3600, "titre": "CPI USA", "prev": "3 %", "avant": "3,1 %"}]}}, **kw)

    def statut(self, etat=None, derniers=None):
        with patch.object(ab, "cme_ouvert", return_value=True):
            return ab.texte_statut(etat or self.etat(), self.derniers() if derniers is None else derniers, self.T)

    def test_tout_est_operationnel_quand_tout_est_a_jour(self):
        t = self.statut()
        self.assertIn("✅ Tout est opérationnel", t)
        for k in ("Telegram : connecté", "BTC : analyse de l'indicateur à jour (9/11 UT, plan SHORT", "IA : connectée (Groq)", "calendrier chargé",
                  "Ouvertures de marché : prochaine", "Mémoire : sauvegardée il y a 2 min"):
            self.assertIn(k, t)
        self.assertNotIn("⚠️ 1 point", t)

    def test_ia_indisponible_est_signalee_sans_declarer_tout_ok(self):
        t = self.statut(self.etat(ia_dernier_statut="ALL_EXTERNAL_PROVIDERS_FAILED"))
        self.assertIn("point(s) à surveiller", t); self.assertIn("IA externe indisponible", t); self.assertNotIn("Tout est opérationnel", t)

    def test_donnees_en_retard_calendrier_vide_memoire_ancienne(self):
        t = self.statut(self.etat(cal={"ev": []}, sauve_t=self.T - 7200), self.derniers(age=1500))
        for k in ("données en retard de 25 min", "aucune annonce dans le calendrier", "aucune sauvegarde récente"):
            self.assertIn(k, t)
        self.assertNotIn("Tout est opérationnel", t)

    def test_marche_ferme_est_normal_pas_une_alerte(self):
        with patch.object(ab, "cme_ouvert", return_value=False):
            t = ab.texte_statut(self.etat(), self.derniers(age=7200), self.T)
        self.assertIn("GOLD : marché fermé (normal)", t)
        self.assertIn("BTC : données en retard", t)                       # le BTC, lui, est 24/7 : 2 h de retard est un vrai problème

    def test_pas_encore_d_analyse_est_signale(self):
        t = self.statut(derniers={})
        self.assertIn("pas encore d'analyse", t); self.assertNotIn("Tout est opérationnel", t)

    def test_prochaine_session_est_dans_le_futur(self):
        nom, quand = ab.prochaine_session(self.T)
        self.assertGreater(quand, self.T); self.assertLess(quand - self.T, 8 * 86400)

    def test_ia_jamais_sollicitee_n_est_pas_une_alerte(self):
        e = self.etat(); e.pop("ia_dernier_statut"); e.pop("ia_dernier_fournisseur")
        self.assertIn("pas encore sollicitée", self.statut(e))
