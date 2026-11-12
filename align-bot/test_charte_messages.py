"""Charte des messages (demande du propriétaire) : 3 modèles stricts, zéro blabla, une information par ligne, erreurs en une ligne."""
import unittest
from unittest.mock import patch

import align_bot as ab

T = 1_800_000_000


class ZeroBlabla(unittest.TestCase):
    def test_phrases_citees_retirees_titre_conserve(self):
        txt = ("⏳ GOLD - TEST\n🚦 ⏳ Je n'entre pas encore\n↩️ Pas d'entrée, heureusement\n🕒 Analyse de référence : 12:00\n"
               "🔔 Cloche activée ? Ne rate pas le feu vert\n👍 Like si tu participes\n📉 Raison : marché neutre")
        sortie = ab.mise_en_forme(txt)
        for interdit in ("n'entre pas encore", "heureusement", "Analyse de référence", "Cloche", "Like si"):
            self.assertNotIn(interdit.lower(), sortie.lower())
        self.assertIn("GOLD - TEST", sortie)
        self.assertIn("Raison", sortie)

    def test_avertissements_de_risque_conserves(self):
        sortie = ab.mise_en_forme("⏳ GOLD - TEST\n⛔ Le SL reste obligatoire\nℹ️ Analyse indicative : décision et ordre sous ta responsabilité")
        self.assertIn("SL reste obligatoire", sortie)
        self.assertIn("Analyse indicative", sortie)

    def test_le_titre_n_est_jamais_supprime(self):
        self.assertTrue(ab.mise_en_forme("😎 RIEN N'A BOUGÉ\n📉 Raison : x").startswith("😎 RIEN N'A BOUGÉ"))


class Modele1Signal(unittest.TestCase):
    def test_format_exact_short_et_long(self):
        txt = ab.msg_signal("GOLD", -1, 3995.2, 3999.99, 3985.0, 3895.54, "Rejet H1 + corrélation DXY", "jusqu'à la clôture 15 min (14:15)")
        self.assertEqual(txt.split("\n"), ["🔴 GOLD - SHORT", "", "🎯 Entrée : 3995,20", "🛑 Stop : 3999,99", "💰 TP1 : 3985", "💰 TP2 : 3895,54", "",
                                           "📊 Contexte : Rejet H1 + corrélation DXY", "⏱ Validité : jusqu'à la clôture 15 min (14:15)"])
        self.assertTrue(ab.msg_signal("BTC", 1, 100.0, 99.0, 102.0, 105.0, "x", "y").startswith("🟢 BTC - LONG"))

    def test_tp2_absent_ou_incoherent_n_est_pas_affiche(self):
        self.assertNotIn("TP2", ab.msg_signal("GOLD", -1, 3995.2, 3999.99, 3985.0, None, "x", "y"))
        self.assertNotIn("TP2", ab.msg_signal("GOLD", -1, 3995.2, 3999.99, 3985.0, 4100.0, "x", "y"))      # TP2 du mauvais côté

    def test_une_information_par_ligne_et_aucun_paragraphe(self):
        txt = ab.mise_en_forme(ab.msg_signal("GOLD", -1, 3995.2, 3999.99, 3985.0, 3895.54, "Rejet 5 min + 4h/1h alignées", "clôture 15 min"))
        for l in txt.splitlines():
            self.assertLessEqual(len(l), 80, l)

    def test_detecte_comme_signal_d_entree_et_jamais_filtre_par_l_anti_doublon(self):
        sig = ab.msg_signal("GOLD", -1, 3995.2, 3999.99, 3985.0, 3895.54, "x", "y")
        self.assertTrue(ab.est_entree(sig)); self.assertTrue(ab.est_entree("🟢🟢🟢 J'ENTRE MAINTENANT — GOLD"))
        self.assertFalse(ab.est_entree("⏳ GOLD - EN ATTENTE\n\n📉 Raison : x"))
        e = {}
        self.assertFalse(ab.doublon_message(e, sig, T)); self.assertFalse(ab.doublon_message(e, sig, T + 5))

    def test_traduction_anglaise(self):
        t = ab.traduire(ab.msg_signal("GOLD", -1, 3995.2, 3999.99, 3985.0, 3895.54, "x", "jusqu'à la clôture 15 min (14:15)"))
        for k in ("🎯 Entry:", "🛑 SL:", "📊 Context:", "⏱ Validity: until the 15 min close (14:15)"):
            self.assertIn(k, t)


class Modele2Attente(unittest.TestCase):
    def test_format_exact(self):
        self.assertEqual(ab.msg_attente("GOLD", "Marché neutre, zone de bruit", "Clôture > 3990"),
                         "⏳ GOLD - EN ATTENTE\n\n📉 Raison : Marché neutre, zone de bruit\n🚀 Déclencheur : Clôture > 3990")

    def test_raison_et_declencheur_issus_des_vraies_donnees(self):
        r = {"dirs": [0] * 11, "confirme": 0, "m1": [{"t": T - 10, "o": 1, "h": 1, "l": 1, "c": 3985.0}], "dirPlan": -1, "strat": "SWING",
             "zone_pine": {"za": 3994.0, "zb": 4012.0, "zmil": 4005.22}}
        self.assertEqual(ab.declencheur_attente(r, {}, 3985.0, 0, 0), "Clôture 1h sous 4005,22")
        self.assertEqual(ab.declencheur_attente(r, {"ordre": {"d": 1, "e": 3996.0}}, 3985.0, 0, 0), "Clôture 5 min au-dessus de 3996")
        self.assertEqual(ab.ligne_raison_attente("⏳ La 4 h est neutre : pas de direction\n🔔 Je te préviens"), "La 4 h est neutre : pas de direction")


class ErreursTechniques(unittest.TestCase):
    def test_une_seule_ligne(self):
        self.assertEqual(ab.erreur_technique("TradingView"), "⚠️ [Erreur technique : TradingView]")

    def test_proprietaire_seulement_et_pas_plus_d_une_fois_par_30_min(self):
        envois, etat = [], {"proprio": ["adel"]}
        with patch.object(ab, "_envoi_sur", side_effect=lambda c, **k: envois.append((c, k["text"]))):
            self.assertTrue(ab.notifier_erreur_technique(etat, "analyse GOLD", T))
            self.assertFalse(ab.notifier_erreur_technique(etat, "analyse GOLD", T + 600))
            self.assertTrue(ab.notifier_erreur_technique(etat, "analyse GOLD", T + 1900))
        self.assertEqual(envois, [("adel", "⚠️ [Erreur technique : analyse GOLD]")] * 2)


class Modele3Ouverture(unittest.TestCase):
    def r(self, prix=3985.0):
        return {"m1": [{"t": T - 20, "o": prix, "h": prix, "l": prix, "c": prix}], "dirs": [0, 0, 0, 0, 0, 0, 0, -1, 0, 1, 0],
                "niveaux": [(3995.0, "1h"), (4010.0, "4h"), (3970.0, "Daily"), (3960.0, "15m"), (3999.0, "15m")]}

    def etat(self):
        return {"cal": {"ev": [{"t": T + 3 * 3600, "titre": "CPI USA", "prev": "3", "avant": "3"}]}}

    def test_donnees_reelles(self):
        with patch.object(ab, "heure", return_value="14:30"):
            d = ab.donnees_ouverture(self.etat(), "GOLD", self.r(), T)
        self.assertEqual((d["h4"], d["h1"]), ("Haussier", "Baissier"))
        self.assertEqual((d["res"], d["sup"]), (3995.0, 3970.0))            # niveaux 1h / 4h / Daily seulement, les plus proches
        self.assertEqual(d["news"], "CPI USA à 14:30")

    def test_format_vip_exact(self):
        dn = dict(m="GOLD", h4="Haussier", h1="Baissier", res=3995.0, sup=3970.0, news="CPI USA à 14:30")
        txt = ab.texte_ouverture("Londres", "09:00", 15, dn, True)
        self.assertEqual(txt.split("\n"), ["🔔 OUVERTURE MARCHÉ : LONDRES", "", "🥇 GOLD", "⏰ Ouverture : 09:00 (dans 15 min)", "📈 Tendance H4 : Haussier",
                                           "📈 Tendance H1 : Baissier", "🔑 Niveaux clés :", "· Résistance : 3995", "· Support : 3970", "⚠️ News : CPI USA à 14:30"])

    def test_gratuit_sans_niveaux(self):
        dn = dict(m="GOLD", h4="Haussier", h1="Baissier", res=3995.0, sup=3970.0, news="aucune annonce majeure")
        txt = ab.texte_ouverture("Londres", "09:00", 15, dn, False)
        self.assertNotIn("3995", txt); self.assertNotIn("3970", txt); self.assertIn("Niveaux clés : VIP", txt)

    def test_un_message_complet_par_marche_concerne_et_routage_par_compte(self):
        ev = dict(code="londres", evt="ouvre", palier=15, t=T + 900, nom=("Londres", "London"), mk=("GOLD et BTC", "GOLD and BTC"), marches=["BTC"])
        derniers = {"GOLD": self.r(), "BTC": self.r(73000.0), "NASDAQ": self.r(28000.0)}
        msgs = ab.messages_ouverture(self.etat(), ev, derniers, T, True)
        self.assertEqual([m for m, _ in msgs], ["GOLD", "BTC"])                              # NASDAQ non concerné par Londres
        self.assertIn("⚡ Compression : explosion possible", dict(msgs)["BTC"])
        envois, etat = [], {"marches_par_chat": {"adel": ["GOLD", "NASDAQ"], "btc": ["BTC"], "tous": ["BTC", "GOLD", "NASDAQ"]}}
        with patch.object(ab, "_envoi_sur", side_effect=lambda c, **k: envois.append((c, k["text"]))):
            ab.diffuser_messages(etat, {"adel", "btc", "tous"}, msgs)
        recu = {}
        for c, t in envois:
            recu.setdefault(c, []).append(t.split("\n")[2])
        self.assertEqual(recu, {"adel": ["🥇 GOLD"], "btc": ["🟠 BTC"], "tous": ["🥇 GOLD", "🟠 BTC"]})      # chaque compte : seulement ses marchés

    def test_integration_alertes_courtes_n_envoie_plus_l_ancienne_alerte_groupee(self):
        ev = dict(kind="session", code="londres", evt="ouvre", palier=15, t=T + 900, nom=("Londres", "London"), mk=("GOLD et BTC", "GOLD and BTC"), marches=[])
        envois = []
        with patch.object(ab, "TOKEN", "x"), patch.object(ab, "evenements_sessions", return_value=[ev]), patch.object(ab, "evenements_pine", return_value=[]), \
             patch.object(ab, "_envoi_sur", side_effect=lambda c, **k: envois.append((c, k["text"]))), patch.object(ab, "destinataires_gratuits", return_value=[]):
            ab.alertes_courtes({}, {"vip"}, {"GOLD": self.r(), "BTC": self.r(73000.0)}, T)
        self.assertEqual(len(envois), 2)
        self.assertTrue(all(t.startswith("🔔 OUVERTURE MARCHÉ : LONDRES") for _, t in envois))

    def test_sans_donnees_repli_sur_l_ancienne_alerte(self):
        ev = dict(kind="session", code="londres", evt="ouvre", palier=15, t=T + 900, nom=("Londres", "London"), mk=("GOLD et BTC", "GOLD and BTC"), marches=[])
        envois = []
        with patch.object(ab, "TOKEN", "x"), patch.object(ab, "evenements_sessions", return_value=[ev]), patch.object(ab, "evenements_pine", return_value=[]), \
             patch.object(ab, "_envoi_sur", side_effect=lambda c, **k: envois.append((c, k["text"]))), patch.object(ab, "destinataires_gratuits", return_value=[]):
            ab.alertes_courtes({}, {"vip"}, {}, T)
        self.assertEqual(len(envois), 1)                                                     # l'alerte de session n'est jamais perdue

    def test_traduction_anglaise(self):
        dn = dict(m="GOLD", h4="Haussier", h1="Baissier", res=3995.0, sup=3970.0, news="aucune annonce majeure")
        t = ab.traduire(ab.texte_ouverture("Londres", "09:00", 15, dn, True))
        for k in ("🔔 MARKET OPEN:", "⏰ Opening:", "📈 H4 trend: Bullish", "📈 H1 trend: Bearish", "🔑 Key levels", "· Resistance:", "· Support:"):
            self.assertIn(k, t)


class RenduTelegram(unittest.TestCase):
    def test_niveaux_importants_en_gras_et_sauts_de_ligne_entre_blocs(self):
        html = ab.rendu_html(ab.mise_en_forme(ab.msg_signal("GOLD", -1, 3995.2, 3999.99, 3985.0, 3895.54, "Rejet 5 min", "clôture 15 min")))
        l = html.split("\n")
        self.assertEqual(l[0], "<b>🔴 GOLD - SHORT</b>")
        for lab, val in (("🎯 Entrée", "3995,20"), ("🛑 Stop", "3999,99"), ("💰 TP1", "3985"), ("💰 TP2", "3895,54")):
            self.assertIn(f"<b>{lab} :</b> <b>{val}</b>", l)
        self.assertEqual(l.count(""), 1)                                    # un seul saut de ligne : entre les niveaux et le contexte
        self.assertNotEqual(l[-1], ""); self.assertNotEqual(l[2], "")

    def test_pas_de_saut_de_ligne_double_ni_en_tete(self):
        html = ab.rendu_html("Titre\n\n\n\nLigne : 1\n\n\nAutre : 2\n\n")
        self.assertNotIn("\n\n\n", html); self.assertFalse(html.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
