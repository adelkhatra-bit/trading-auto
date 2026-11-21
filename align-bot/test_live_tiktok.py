import unittest.mock
"""LIVE TikTok : bande qui défile, bulles, boost, télécommande payante (Stars) — jamais de niveaux sur l'écran."""
import datetime
import json
import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import align_bot as ab

# Capture the production constant before setUp deliberately patches it for isolated tests.
_LIVE_SUJET_PRODUCTION = ab.LIVE_SUJET


class LiveTikTok(unittest.TestCase):
    def setUp(self):
        ab._LIVE_BOOSTS.clear()
        ab._LIVE_DERNIER.clear()
        self.publie = []
        self.envoye = []
        self.tg = []
        self.p = [mock.patch.object(ab, "LIVE_SUJET", "test-sujet"),
                  mock.patch.object(ab, "live_publier", side_effect=lambda t: self.publie.append(t) or True),
                  mock.patch.object(ab, "_envoi_sur", side_effect=lambda cid, **kw: self.envoye.append((cid, kw))),
                  mock.patch.object(ab, "telegram", side_effect=lambda m, **kw: self.tg.append((m, kw)) or {"ok": True})]
        for x in self.p:
            x.start()
        self.etat = {"proprio": ["1"], "prenoms": {"2": "Karim"}, "prospects": ["3"]}

    def tearDown(self):
        for x in self.p:
            x.stop()

    def test_bot_and_tradingview_userscript_share_one_live_channel(self):
        bande = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "live", "align-bande-live.user.js"), encoding="utf-8").read()
        match = re.search(r"""const SUJET = [\'"]([^\'"]+)[\'"];""", bande)
        self.assertIsNotNone(match, "sujet canonique absent du userscript")
        self.assertEqual(_LIVE_SUJET_PRODUCTION, match.group(1))

    def test_bouton_live_dans_les_deux_claviers(self):
        for c in (ab.CLAVIER, ab.CLAVIER_VISITEUR):
            textes = [b["text"] for ligne in json.loads(c)["keyboard"] for b in ligne]
            self.assertIn("🔴 Live", textes)

    def test_installer_menu_actualise_la_commande_live(self):
        etat = {"menu": 10}
        ab.installer_menu(etat)
        self.assertEqual(etat.get("menu"), 12)
        commandes = [kw for methode, kw in self.tg if methode == "setMyCommands"]
        self.assertEqual(len(commandes), 2)
        fr = json.loads(commandes[0]["commands"])
        en = json.loads(commandes[1]["commands"])
        self.assertTrue(any(c["command"] == "live" for c in fr))
        self.assertTrue(any(c["command"] == "live" for c in en))

    def test_installer_menu_force_migration_depuis_ancienne_version_11(self):
        etat = {"menu": 11}
        with mock.patch.object(ab, "telegram", return_value={"ok": True}) as tg:
            ab.installer_menu(etat)
        self.assertEqual(etat.get("menu"), 12)
        self.assertEqual(len([c for c in tg.call_args_list if c.args[0] == "setMyCommands"]), 2)

    def test_installer_menu_ne_marque_pas_installe_si_telegram_refuse_en(self):
        etat = {"menu": 10}
        appels = []
        def telegram_faux(methode, **kw):
            appels.append((methode, kw))
            if methode == "setMyCommands" and kw.get("language_code") == "en":
                return {"ok": False, "description": "refused"}
            return {"ok": True}
        with mock.patch.object(ab, "telegram", side_effect=telegram_faux):
            ab.installer_menu(etat)
        self.assertEqual(etat.get("menu"), 10)
        self.assertEqual(len([m for m, _ in appels if m == "setMyCommands"]), 2)



    def test_live_24h_toujours_actif_par_defaut(self):
        self.assertTrue(ab.live_actif({}))

    def test_entree_toujours_sur_la_bande_meme_live_eteint(self):
        # Règle d'Adel (14/11) : l'entrée en position passe toujours sur la bande (elle n'existe que sur l'écran du live)
        with mock.patch.object(ab, "LIVE_24H", False):
            ab.live_annonces(self.etat, "BTC", ["🟢🟢🟢 J'ENTRE MAINTENANT — BTC"])
        self.assertEqual(len(self.publie), 1)
        self.assertIn("lien en bio", self.publie[0]); self.assertNotIn("Telegram", self.publie[0])

    def test_tp_touche_toujours_sur_la_bande(self):
        ab.live_annonces(self.etat, "BTC", ["🎯 BTC : TP1 TOUCHÉ"])
        self.assertTrue(any("TP1 TOUCHÉ" in x for x in self.publie))
        self.assertTrue(any("lien en bio" in x for x in self.publie))
        self.assertFalse(any("Telegram" in x for x in self.publie))

    def test_proprio_lance_le_live_et_tout_le_monde_est_prevenu(self):
        ab.live_callback(self.etat, {"2"}, {"id": "x"}, "liveon", "x", "1")
        self.assertTrue(self.etat["live_on"])
        dest = {cid for cid, _ in self.envoye}
        self.assertEqual(dest, {"2", "3"})
        self.assertTrue(any("EN LIVE" in kw["text"] for _, kw in self.envoye))

    def test_un_abonne_ne_peut_pas_lancer_le_live(self):
        ab.live_callback(self.etat, {"2"}, {"id": "x"}, "liveon", "x", "2")
        self.assertFalse(self.etat.get("live_on"))

    def test_annonces_sans_aucun_niveau(self):
        self.etat["live_on"] = True
        ab.live_annonces(self.etat, "BTC", ["🟢🟢🟢 J'ENTRE MAINTENANT — BTC\n📌 Entrée 68459,14\n🛑 SL 69105", "🎯 TP1 TOUCHÉ — BTC 67167"])
        self.assertEqual(len(self.publie), 2)          # entrée + TP1 (chacun finit par « lien en bio »)
        self.assertTrue(all("lien en bio" in t for t in self.publie))
        for t in self.publie:
            self.assertIsNone(re.search(r"\d{3,}", t), t)
            self.assertNotIn("SHORT", t)
            self.assertNotIn("LONG", t)
        ab.live_annonces(self.etat, "BTC", ["🟢🟢🟢 J'ENTRE MAINTENANT — BTC"])
        self.assertEqual(len(self.publie), 2)          # pas de doublon

    def test_bulle_zone(self):
        self.etat["live_on"] = True
        ab.live_annonces(self.etat, "GOLD", ["🟥🟥 POINT D'ENTRÉE À VENIR — 🥇 GOLD\n🟨 Le prix entre dans la zone\n📍 Zone ≈ 3990 – 4012"])
        self.assertTrue(self.publie[0].startswith("BULLE:"))
        self.assertIsNone(re.search(r"\d{3,}", self.publie[0]))
        self.assertTrue(self.publie[0].startswith("BULLE:🎯 Le prix arrive dans une zone clé 👀 • ⏱ verdict dans "))
        self.assertTrue(self.publie[0].endswith("Ouvre le lien en bio pour voir le plan complet."))
        for mot in ("GOLD", "SHORT", "LONG", "ZONE", "position"):
            self.assertNotIn(mot, self.publie[0])

    def test_reinjection_arrete_tous_les_animateurs_periodiques(self):
        bande = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "live", "align-bande-live.user.js"), encoding="utf-8").read()
        stop = bande[bande.index("stop() { vivant = false;"):]
        for timer in ("coachT", "iaT", "astuceT", "regardT", "chronoT", "coeurT", "posT", "masqueT", "etiqT", "heartbeatT"):
            self.assertIn(f"clearInterval({timer})", stop, f"timer non arrêté lors de la réinjection : {timer}")

    def test_jamais_le_mot_telegram_a_l_ecran(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "align_bot.py"), encoding="utf-8").read()
        for ligne in src.splitlines():
            if ("live_bande(" in ligne or "live_publier(" in ligne) and '"' in ligne:
                self.assertNotIn("Telegram", ligne, ligne)
        bande = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "live", "align-bande-live.user.js"), encoding="utf-8").read()
        self.assertNotIn("sur Telegram", bande)

    def test_masquage_ne_depend_pas_de_conteneurs_dialogue_caches(self):
        bande = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "live", "align-bande-live.user.js"), encoding="utf-8").read()
        self.assertIn("const overlayVisible = el =>", bande)
        self.assertIn("const overlayOuvert = Array.from(document.querySelectorAll", bande)
        self.assertIn(".some(overlayVisible)", bande)
        self.assertNotIn("classList.toggle('align-cache', !!document.querySelector", bande)

    def test_position_confirmee_declenche_spectacle_visuel(self):
        bande = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "live", "align-bande-live.user.js"), encoding="utf-8").read()
        self.assertIn("if (/POSITION ALIGN CONFIRMÉE|ENTRE EN POSITION/i.test(txt)) { feuArtifice(", bande)
        self.assertIn("POSITION ALIGN CONFIRMÉE/i.test(txt))", bande)

    def test_boost_refuse_si_ecran_live_deconnecte(self):
        self.etat["live_on"] = True
        self.etat["live_screen_seen_t"] = __import__("time").time() - 120
        with mock.patch.object(ab, "ecran_signal_frais", return_value=False):
            ab.live_callback(self.etat, set(), {"id": "x"}, "liveboost", "x", "2")
        self.assertEqual(self.publie, [])
        self.assertIn("n'est pas connecté", self.envoye[-1][1]["text"])

    def test_boost_accepte_si_ping_frais_lu_au_clic(self):
        """v12.2.10 : signal sauvegardé périmé, mais ping frais sur ntfy au moment du clic → boost accepté."""
        self.etat["live_on"] = True
        self.etat["live_screen_seen_t"] = __import__("time").time() - 600
        frais = int(__import__("time").time() * 1000)
        ligne = __import__("json").dumps({"event": "message", "message": f"PING|LIVE_SCREEN|{frais}"})
        rep = mock.MagicMock()
        rep.read.return_value = ligne.encode("utf-8")
        rep.__enter__.return_value = rep
        with mock.patch.object(ab.urllib.request, "urlopen", return_value=rep):
            ab.live_callback(self.etat, set(), {"id": "x"}, "liveboost", "x", "2")
        self.assertNotIn("n'est pas connecté", " ".join(t for _, t in [(0, m.get("text", "")) for _, m in self.envoye]))
        self.assertTrue(self.etat["live_screen_seen_t"] >= frais / 1000 - 1)

    def test_ecran_signal_frais_ignore_ping_ancien(self):
        self.etat["live_screen_seen_t"] = 0
        ancien = int((__import__("time").time() - 600) * 1000)
        ligne = __import__("json").dumps({"event": "message", "message": f"PING|LIVE_SCREEN|{ancien}"})
        rep = mock.MagicMock()
        rep.read.return_value = ligne.encode("utf-8")
        rep.__enter__.return_value = rep
        with mock.patch.object(ab.urllib.request, "urlopen", return_value=rep):
            self.assertFalse(ab.ecran_signal_frais(self.etat))
        self.assertEqual(self.etat["live_screen_seen_t"], 0)

    def test_boost_limite_par_personne_et_prenom_apres_heartbeat(self):
        self.etat["live_on"] = True
        self.etat["live_screen_seen_t"] = __import__("time").time()
        with mock.patch.object(ab, "ecran_signal_frais", return_value=True):
            ab.live_callback(self.etat, set(), {"id": "x"}, "liveboost", "x", "2")
            ab.live_callback(self.etat, set(), {"id": "y"}, "liveboost", "x", "2")
        self.assertEqual(self.publie, ["🙏 MERCI KARIM ! Karim BOOSTE LE LIVE 🚀 ABONNE-TOI • PARTAGE"])
        self.assertIn("Ton prénom doit apparaître", self.envoye[0][1]["text"])
        self.assertIn("2 min", self.envoye[1][1]["text"])

    def test_heartbeat_ecran_frais_est_enregistre_sans_annonce_publique(self):
        self.etat["live_screen_seen_t"] = 0
        maintenant = __import__("time").time()
        with mock.patch.object(ab, "time") as horloge:
            horloge.time.return_value = maintenant
            with mock.patch.object(ab, "ecran_lire", return_value=[f"PING|LIVE_SCREEN|{int(maintenant * 1000)}"]):
                ab.ecran_vers_telegram(self.etat)
        self.assertAlmostEqual(self.etat["live_screen_seen_t"], maintenant, delta=0.01)
        self.assertEqual(self.publie, [])

    def test_heartbeat_ancien_ne_reconnecte_pas_un_ecran_deconnecte(self):
        self.etat["live_screen_seen_t"] = 0
        ancien = int((__import__("time").time() - 600) * 1000)
        with mock.patch.object(ab, "ecran_lire", return_value=[f"PING|LIVE_SCREEN|{ancien}"]):
            ab.ecran_vers_telegram(self.etat)
        self.assertEqual(self.etat["live_screen_seen_t"], 0)
        self.assertEqual(self.publie, [])

    def test_facture_en_stars(self):
        self.etat["live_on"] = True
        ab.live_callback(self.etat, set(), {"id": "x"}, "livemain", "5", "2")
        m, kw = self.tg[-1]
        self.assertEqual(m, "sendInvoice")
        self.assertEqual(kw["currency"], "XTR")
        self.assertEqual(kw["provider_token"], "")
        self.assertEqual(json.loads(kw["prices"])[0]["amount"], ab.PRIX_MAIN_STARS)
        self.assertEqual(kw["payload"], "livemain:5")

    def test_admin_prend_la_main_sans_payer(self):
        self.etat["live_on"] = True
        with mock.patch.object(ab, "ecran_signal_frais", return_value=False):
            ab.live_callback(self.etat, set(), {"id": "x"}, "livemain", "15", "1")
        self.assertFalse(any(m == "sendInvoice" for m, _ in self.tg))
        self.assertTrue(self.publie[-1].startswith("CMD:tf:15:"))
        self.assertIn("capture", self.envoye[-1][1]["text"])

    def test_ordre_btc_gold_nasdaq_en_premier(self):
        self.etat["live_on"] = True
        kb = json.loads(ab.clavier_live(self.etat, "2"))["inline_keyboard"]
        # 1re ligne = parcours d'Adel (choix du marché → coach → prochaine position) ; « prendre la main » reste en 4e ligne.
        self.assertEqual([b["callback_data"] for b in kb[0]], ["livemkt:BTC", "livemkt:GOLD"])
        self.assertEqual([b["text"] for b in kb[3]], ["🟠 BTC", "🥇 Gold"])
        self.assertIn("capture", ab.texte_live(self.etat))

    def test_paiement_refuse_si_live_eteint(self):
        p24 = mock.patch.object(ab, "LIVE_24H", False)
        p24.start()
        self.addCleanup(p24.stop)
        self.assertFalse(ab.live_pre_checkout(self.etat, {"id": "q", "invoice_payload": "livemain:5"}))
        self.assertEqual(self.tg[-1][1]["ok"], "false")
        self.etat["live_on"] = True
        self.assertTrue(ab.live_pre_checkout(self.etat, {"id": "q", "invoice_payload": "livemain:5"}))
        self.assertEqual(self.tg[-1][1]["ok"], "true")
        self.assertFalse(ab.live_pre_checkout(self.etat, {"id": "q", "invoice_payload": "autre:5"}))

    def test_ecran_muet_l_abonne_est_prevenu(self):
        self.etat["live_on"] = True
        with mock.patch.object(ab, "live_publier", return_value=False):
            self.assertFalse(ab.live_paiement_recu(self.etat, "2", {"invoice_payload": "livemain:5"}))
        self.assertIn("n'a pas répondu", self.envoye[-1][1]["text"])

    def test_admin_voit_le_code_ecran_et_le_statut_deconnexion(self):
        with mock.patch.object(ab, "ecran_signal_frais", return_value=False):
            ab.menu_live(self.etat, "1")
            self.assertIn("Code écran (admin) : test-sujet", self.envoye[-1][1]["text"])
            self.assertIn("Écran TradingView non connecté", self.envoye[-1][1]["text"])
            ab.menu_live(self.etat, "2")
            self.assertNotIn("Code écran", self.envoye[-1][1]["text"])
            self.assertNotIn("Écran TradingView", self.envoye[-1][1]["text"])

    def test_admin_voit_ecran_tradingview_connecte_apres_heartbeat(self):
        self.etat["live_screen_seen_t"] = __import__("time").time()
        with mock.patch.object(ab, "ecran_signal_frais", return_value=True):
            ab.menu_live(self.etat, "1")
        self.assertIn("Écran TradingView connecté", self.envoye[-1][1]["text"])

    def test_menu_live_admin_affiche_bridge_non_configure_sans_secrets(self):
        with mock.patch.object(ab, "ecran_signal_frais", return_value=False), \
             mock.patch.object(ab, "ALIGN_TV_API_URL", ""), \
             mock.patch.object(ab, "ALIGN_TV_READ_TOKEN", ""):
            ab.menu_live(self.etat, "1")
        self.assertIn("Bridge ROBOT V12 non connecté", self.envoye[-1][1]["text"])
        self.assertIn("analyses et signaux suspendus", self.envoye[-1][1]["text"])
        self.assertIn("données TradingView", self.envoye[-1][1]["text"])
        self.assertNotIn("Yahoo", self.envoye[-1][1]["text"])

    def test_menu_live_admin_ne_confond_pas_configuration_et_connexion_bridge(self):
        with mock.patch.object(ab, "ecran_signal_frais", return_value=False), \
             mock.patch.object(ab, "ALIGN_TV_API_URL", "https://bridge.example"), \
             mock.patch.object(ab, "ALIGN_TV_READ_TOKEN", "test-token"):
            ab.menu_live(self.etat, "1")
        self.assertIn("paramètres présents", self.envoye[-1][1]["text"])
        self.assertNotIn("Bridge ROBOT V12 connecté", self.envoye[-1][1]["text"])


    def test_paiement_recu_envoie_l_ordre_au_graphique(self):
        self.etat["live_on"] = True
        ab.live_paiement_recu(self.etat, "2", {"invoice_payload": "livemain:GOLD", "total_amount": 25, "telegram_payment_charge_id": "c1"})
        self.assertEqual(self.publie, ["CMD:sym:FOREXCOM:XAUUSD:Karim"])
        self.assertEqual(self.etat["live_paiements"][-1]["id"], "c1")
        self.assertIn("C'est à toi", self.envoye[-2][1]["text"])
        self.assertIn("PRENDS LA MAIN", self.envoye[-1][1]["text"])      # le menu du live redescend en bas

    def test_live_menu_exposes_research_market_selection_and_coach_controls(self):
        self.etat["live_on"] = True
        kb = json.loads(ab.clavier_live(self.etat, "2"))["inline_keyboard"]
        actions = {b.get("callback_data"): b["text"] for row in kb for b in row if b.get("callback_data")}
        self.assertIn("analysechoice:BOTH", actions)
        self.assertIn("searchpos:BOTH", actions)
        self.assertIn("marketsmenu:x", actions)
        for market in ("BTC", "GOLD"):
            self.assertIn(f"coachlive:{market}", actions)

    def test_live_script_has_click_to_enable_voice_and_cleans_it_up(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "live", "align-bande-live.user.js")
        source = open(path, encoding="utf-8").read()
        self.assertIn("speechSynthesis.speak(utterance)", source)
        self.assertIn("PING|LIVE_SCREEN|", source)
        self.assertIn("setInterval(pingEcran, 25000)", source)
        self.assertIn("clearInterval(heartbeatT)", source)
        self.assertIn("🔇 COACH VOCAL OFF", source)
        self.assertIn("🔊 COACH VOCAL ON", source)
        self.assertIn("voixBtn.remove()", source)
        self.assertIn("parlerLive(m)", source)
        # End-to-end linkage: bot IA payload -> ntfy receiver -> AI bubble -> voice narration.
        self.assertIn("if (txt.startsWith('IA:')) { recuIA(txt.slice(3)); return; }", source)
        self.assertIn("montrer('🧠 ' + phrase, false, 2, 'membre', false, 'ia')", source)
        self.assertIn("const voixDuree = parlerLive(m)", source)
        self.assertIn("montrer(txt, bulle, 2, '', false, bulle ? 'marche' : 'live')", source)  # BULLE de marché envoyée au vocal
        self.assertIn("const traductionEN = enAnglais(texte), anglaisTraduit = traductionEN !== texte", source)
        self.assertIn("item.source === 'marche' && !item.anglaisTraduit", source)  # évite la voix anglaise sur une bulle restée en français
        self.assertIn("item.source !== 'ia' && item.source !== 'marche'", source)
        self.assertIn("voiceschanged", source)  # voix navigateur parfois disponibles après document-idle
        self.assertIn("removeEventListener('voiceschanged', voixSurVoixChangees)", source)  # listener nettoyé à la réinjection
        self.assertIn("voixEnAttente = item", source)  # commentaire FR retenté quand la liste de voix arrive
        self.assertIn("hortense|audrey|julie|charlotte", source)  # noms courants de voix FR, sans repli robot
        self.assertIn("localStorage.removeItem('alignVoixActive')", source)  # ON persisted ne contourne pas la gesture audio
        self.assertNotIn("Le coach ALIGN est en direct", source)  # v12.2.8 : plus de phrase d'accueil



class CartesRelieesAuGraphique(unittest.TestCase):
    def test_zone_parle_comme_le_graphique_en_anglais_aussi(self):
        fr = ("🟩 Le prix entre dans la ZONE du graphique\n🟨 Ligne jaune ENTRÉE : attends la CLÔTURE 15 min EN DESSOUS\n"
              "🙅 Une mèche seule ne suffit pas\n🛑 SL = ligne rouge du graphique")
        en = ab.traduire(fr)
        self.assertIn("chart ZONE", en)
        self.assertIn("CLOSE BELOW", en)
        self.assertIn("red line", en)
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "align_bot.py"), encoding="utf-8").read()
        self.assertIn("CLÔTURE SOUS l'étiquette « ENTRÉE »", src)
        self.assertIn("REJOINT LA TEAM ALIGN", src)



class LectureTP1(unittest.TestCase):
    def r_(self, dirs, rsis=None, sqzs=None):
        return {"dirs": dirs + [0] * (11 - len(dirs)), "rsis": rsis or [50] * 11, "sqzs": sqzs or [0] * 11}

    def test_continue_vers_tp2(self):
        l = ab.lecture_tp1(self.r_([-1, -1, -1, -1, 0]), -1)
        self.assertIn("🚀 ÇA PEUT CONTINUER VERS LE TP2", l)
        self.assertTrue(any("EN DESSOUS" in x for x in l))

    def test_risque_de_retour(self):
        rs = [50] * 11; rs[4] = 25
        l = ab.lecture_tp1(self.r_([1, 1, 1, 0, -1], rs), -1)
        self.assertEqual(l[0], "⚠️ RISQUE DE RETOUR VERS L'ENTRÉE")
        self.assertTrue(any("RSI 15 min 25" in x for x in l))

    def test_hesitation_et_long(self):
        l = ab.lecture_tp1(self.r_([1, 0, -1, 0, 1]), 1)
        self.assertEqual(l[0], "🟨 LE MARCHÉ HÉSITE AU TP1")
        self.assertTrue(any("AU-DESSUS" in x for x in l))
        self.assertIn("IT CAN GO ON TO TP2", ab.traduire("🚀 ÇA PEUT CONTINUER VERS LE TP2"))


class CartesCouleursGraphique(unittest.TestCase):
    def test_cartes_parlent_des_lignes(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "align_bot.py"), encoding="utf-8").read()
        for mot in ("(étiquette ENTRÉE)", "(ligne rouge)", "(ligne bleue)", "🔒 SL protégé", "🟨 Entrée {px(tr['e'])} • 🛑 SL"):
            self.assertIn(mot, src)
        self.assertIn("(red line)", ab.traduire("🛑 SL : 1 (ligne rouge)"))



class TestFinDeTradeBande(unittest.TestCase):
    def test_tp_final_et_sl_sur_la_bande(self):
        pub = []
        with mock.patch.object(ab, "live_publier", side_effect=lambda t: pub.append(t) or True):
            ab._LIVE_DERNIER.clear()
            ab.live_fin_de_trade({}, "BTC", {"e": 100.0}, 102.0, 2.0)
            ab.live_fin_de_trade({}, "BTC", {"e": 100.0}, 102.0, 2.0)      # même annonce : une seule fois
            ab.live_fin_de_trade({}, "GOLD", {"e": 100.0}, 99.0, -1.0)
        self.assertEqual(len(pub), 2)
        self.assertIn("TP TOUCHÉ", pub[0]); self.assertIn("lien en bio", pub[0]); self.assertNotIn("Telegram", pub[0])
        self.assertIn("stop touché", pub[1])

    def test_compte_a_rebours(self):
        self.assertEqual(ab.min_avant_cloture15(900 * 10 + 1), 15)
        self.assertEqual(ab.min_avant_cloture15(900 * 10 + 840), 1)



class TestPrepareToiLive(unittest.TestCase):
    def test_fenetre_prepare_toi_sans_niveau(self):
        pub = []
        props = [{"m": "BTC", "d": -1, "rang": 0, "za": 65717.0, "zb": 65965.0}]
        with mock.patch.object(ab, "classer_marches", return_value=props), mock.patch.object(ab, "_radar_pret", return_value=True), \
             mock.patch.object(ab, "live_publier", side_effect=lambda t: pub.append(t) or True):
            ab._LIVE_DERNIER.clear()
            ab.live_prepare_toi({}, {}, 1000.0)
            ab.live_prepare_toi({}, {}, 1060.0)
        self.assertEqual(len(pub), 3)                # prépare-toi + chrono « une position arrive » (v8.5) + jeu « tapote l'écran », une seule fois
        self.assertIn("couler", pub[0]); self.assertIn("verdict dans", pub[0]); self.assertIn("lien en bio", pub[0])
        self.assertEqual(pub[1], "CMD:chrono:800:BTC")   # chrono jusqu'à la clôture 15 min, jamais de prix
        self.assertIn("tapote", pub[2])
        for t in pub:
            self.assertNotIn("65", t); self.assertNotIn("Telegram", t)



class TestSpectacleV85(unittest.TestCase):
    def test_phrases_ia_filtrees(self):
        brut = ("ça monte ou ça descend ? dis-le en commentaire 👇 | up or down? tell us in the comments 👇\n"
                "BTC à 65000 ce soir | BTC at 65000 tonight\n"
                "rejoins le Telegram | join the Telegram\n"
                "prépare ton entrée | get your entry ready\n"
                "phrase sans anglais")
        p = ab.phrases_bande_propres(brut)
        self.assertEqual(p, [["ça monte ou ça descend ? dis-le en commentaire 👇", "up or down? tell us in the comments 👇"]])

    def test_agenda_discours_et_ouverture(self):
        pub = []
        t0 = int(ab.datetime.datetime(2026, 11, 16, 15, 15, tzinfo=ab.PARIS).timestamp())   # lundi 15 h 15
        evts = [{"titre": "Fed Chair Powell Speaks", "t": t0 + 15 * 60}]
        with mock.patch.object(ab, "calendrier", return_value=evts), \
             mock.patch.object(ab, "live_publier", side_effect=lambda t: pub.append(t) or True):
            ab._LIVE_DERNIER.clear()
            ab.live_agenda({}, t0)
            ab.live_agenda({}, t0 + 30)                # pas de doublon
        self.assertEqual(len(pub), 2)
        self.assertTrue(any("DISCOURS" in x and "Powell" in x for x in pub))
        self.assertTrue(any("NEW YORK" in x for x in pub))
        for x in pub:
            self.assertNotIn("Telegram", x)


class TestIABandeNumerotee(unittest.TestCase):
    def test_lignes_numerotees_acceptees(self):
        brut = "1. ça monte ou ça descend ? dis-le en commentaire 👇 | up or down? tell us in the comments 👇\n- **tapote l'écran si t'es là 👆** | **tap the screen if you are here 👆**"
        p = ab.phrases_bande_propres(brut)
        self.assertEqual(len(p), 2)
        self.assertTrue(p[0][0].startswith("ça monte"))
        self.assertNotIn("**", p[1][0])


class TestBandeRassure(unittest.TestCase):
    def test_contre_le_bot_rassure_sans_niveau(self):
        t = ab.texte_bande_flash("🎙 ÇA BOUGE !\n🟠 BTC : 65000\n⚠️ Contre le bot", -1, "BTC")
        for x in ("pas de panique", "clôture dans", "reprendre la descente", "lien en bio"):
            self.assertIn(x, t)
        self.assertNotIn("65000", t); self.assertNotIn("Telegram", t)



class LiveOutbox(unittest.TestCase):
    def test_live_publier_persists_and_deduplicates_until_sent(self):
        previous = ab._ETAT_COURANT.get("etat")
        state = {}
        ab._ETAT_COURANT["etat"] = state
        try:
            with mock.patch.object(ab, "LIVE_SUJET", "test-sujet"):
                self.assertTrue(ab.live_publier("NEWS:message de test"))
                self.assertTrue(ab.live_publier("NEWS:message de test"))
            self.assertEqual(len(state.get("live_outbox", [])), 1)
            with mock.patch.object(ab, "LIVE_SUJET", "test-sujet"), \
                 mock.patch.object(ab.urllib.request, "urlopen", return_value=mock.MagicMock()):
                self.assertEqual(ab.traiter_file_live(state, maintenant=100), 1)
            self.assertEqual(state["live_outbox"], [])
        finally:
            if previous is None:
                ab._ETAT_COURANT.pop("etat", None)
            else:
                ab._ETAT_COURANT["etat"] = previous

    def test_live_publier_failure_is_retried_not_dropped(self):
        previous = ab._ETAT_COURANT.get("etat")
        state = {"live_outbox": [{"key": "x", "text": "message", "tries": 0, "next_t": 0}]}
        ab._ETAT_COURANT["etat"] = state
        try:
            with mock.patch.object(ab, "LIVE_SUJET", "test-sujet"), \
                 mock.patch.object(ab.urllib.request, "urlopen", side_effect=OSError("network down")):
                self.assertEqual(ab.traiter_file_live(state, maintenant=100), 0)
            self.assertEqual(len(state["live_outbox"]), 1)
            self.assertEqual(state["live_outbox"][0]["tries"], 1)
            self.assertGreater(state["live_outbox"][0]["next_t"], 100)
        finally:
            if previous is None:
                ab._ETAT_COURANT.pop("etat", None)
            else:
                ab._ETAT_COURANT["etat"] = previous


    def test_coach_live_activation_reenables_bot_and_has_no_expiry(self):
        market = "BTC"
        cid = "user-42"
        state = {"bot_off": [cid], "coach_live": {}}
        bars = [{"t": 100}, {"t": 200}]
        with mock.patch.object(ab, "DERNIERS", {market: {"b15": bars}}), \
             mock.patch.object(ab.time, "time", return_value=500):
            ab.activer_coach_live(state, cid, market, True)
        self.assertNotIn(cid, state["bot_off"])
        self.assertEqual(state["coach_live"][market][cid], {"dernier_t": 100, "started_t": 500})

    def test_legacy_coach_subscriptions_get_a_stable_start_time_once(self):
        state = {"coach_live": {
            "BTC": {"user-42": {"dernier_t": 100}},
            "GOLD": {"user-43": {"dernier_t": 200, "started_t": 300}}
        }}
        ab.initialiser_debut_coach_live(state, maintenant=500)
        self.assertEqual(state["coach_live"]["BTC"]["user-42"]["started_t"], 500)
        self.assertEqual(state["coach_live"]["GOLD"]["user-43"]["started_t"], 300)
        ab.initialiser_debut_coach_live(state, maintenant=600)
        self.assertEqual(state["coach_live"]["BTC"]["user-42"]["started_t"], 500)

    def test_coach_live_ignores_legacy_expiry_and_keeps_monitoring(self):
        market = "BTC"
        cid = "user-42"
        candle = {"t": 300, "o": 100, "h": 102, "l": 99, "c": 101}
        state = {"coach_live": {market: {cid: {"expire": 1, "dernier_t": 0}}}}
        sent = []
        with mock.patch.object(ab, "bot_on", return_value=True), \
             mock.patch.object(ab, "dans_chaine", return_value=False), \
             mock.patch.object(ab, "_envoi_sur", side_effect=lambda *a, **kw: sent.append((a, kw)) or {"ok": True}), \
             mock.patch.object(ab, "texte_coach_live", return_value="COACH BTC"), \
             mock.patch.object(ab, "markup_analyse", return_value=None), \
             mock.patch.object(ab, "positions_bot", return_value=[]), \
             mock.patch.object(ab.time, "time", return_value=500):
            ab.notifier_coach_live(state, market, {"b15": [candle, {"t": 600}]}, {})
        self.assertIn(cid, state["coach_live"][market])
        self.assertTrue(any("COACH BTC" in str(item) for item in sent))
        self.assertFalse(any("COACH EN DIRECT TERMINÉ" in str(item) for item in sent))



    def test_search_position_starts_persistent_coach_for_selected_markets(self):
        state = {"marches_par_chat": {"user-42": ["BTC", "GOLD"]}, "bot_off": ["user-42"]}
        with mock.patch.object(ab, "DERNIERS", {
            "BTC": {"b15": [{"t": 100}, {"t": 200}]},
            "GOLD": {"b15": [{"t": 300}, {"t": 400}]}
        }), mock.patch.object(ab.time, "time", return_value=500):
            selected = ab.demarrer_recherche_positions(state, "user-42")
        self.assertEqual(selected, ("BTC", "GOLD"))
        self.assertEqual(state["coach_live"]["BTC"]["user-42"], {"dernier_t": 100, "started_t": 500})
        self.assertEqual(state["coach_live"]["GOLD"]["user-42"], {"dernier_t": 300, "started_t": 500})
        self.assertNotIn("user-42", state["bot_off"])



    def test_coach_live_sends_new_position_without_waiting_for_m15_close(self):
        market = "BTC"
        cid = "user-42"
        trade = {"d": 1, "e": 100.0, "sl": 98.0, "tp1": 104.0, "tp2": 108.0, "ouvert_t": 100}
        state = {"coach_live": {market: {cid: {"dernier_t": 0, "started_t": 50}}}}
        sent = []
        with mock.patch.object(ab, "bot_on", return_value=True), \
             mock.patch.object(ab, "dans_chaine", return_value=False), \
             mock.patch.object(ab, "_envoi_sur", side_effect=lambda *a, **kw: sent.append((a, kw)) or {"ok": True}), \
             mock.patch.object(ab, "markup_analyse", return_value=None):
            ab.notifier_coach_live(state, market, {"m1": [{"c": 101.0}]}, {"trade": trade})
        self.assertEqual(state["coach_live"][market][cid]["position_key"], "1|100.0|98.0|104.0|108.0")
        self.assertTrue(any("POSITION ALIGN DÉTECTÉE" in str(item) and "TP1" in str(item) for item in sent))





    def test_coach_live_does_not_send_a_trade_opened_before_the_search(self):
        market, cid = "BTC", "user-42"
        trade = {"d": -1, "e": 100.0, "sl": 102.0, "tp1": 96.0, "tp2": 92.0, "ouvert_t": 100}
        state = {
            "coach_live": {market: {cid: {"dernier_t": 0, "started_t": 200}}},
            "recherche_positions_active": [cid]
        }
        sent = []
        with mock.patch.object(ab, "bot_on", return_value=True), \
             mock.patch.object(ab, "dans_chaine", return_value=False), \
             mock.patch.object(ab, "_envoi_sur", side_effect=lambda *a, **kw: sent.append((a, kw)) or {"ok": True}), \
             mock.patch.object(ab, "markup_analyse", return_value=None):
            ab.notifier_coach_live(state, market, {"m1": [{"c": 99.0}]}, {"trade": trade})
        self.assertFalse(any("POSITION ALIGN DÉTECTÉE" in str(item) for item in sent))
        self.assertEqual(state["coach_live"][market][cid]["position_key"], "-1|100.0|102.0|96.0|92.0")
        self.assertEqual(state["recherche_positions_active"], [cid])

    def test_repeated_start_does_not_duplicate_welcome_but_returns_menu(self):
        state = {"bienvenue_pull_v1": ["42"]}
        sent = []
        update = {"update_id": 1, "message": {
            "chat": {"id": 42, "type": "private"},
            "from": {"id": 42, "first_name": "Adel"},
            "text": "/start"
        }}
        with mock.patch.object(ab, "_envoi_sur", side_effect=lambda *a, **kw: sent.append((a, kw)) or {"ok": True}):
            ab.traiter(state, set(), [update])
        self.assertEqual(len(sent), 1)
        self.assertIn("/boutons", sent[0][1]["text"])
        self.assertNotIn("Bonjour", sent[0][1]["text"])
        self.assertEqual(state["bienvenue_pull_v1"], ["42"])

    def test_telegram_pull_mode_blocks_background_notifications(self):
        with mock.patch.object(ab, "TELEGRAM_PULL_MODE", True):
            self.assertFalse(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "other", "text": "ALERT"}))
            self.assertFalse(ab._telegram_sortant_autorise("sendPhoto", {"chat_id": "channel", "photo": "x"}))

    def test_pull_mode_lets_only_a_validated_entry_reach_a_configured_channel(self):
        etat = {"canal": "-1001", "canaux_marche": {"GOLD": "-1002"}}
        with mock.patch.object(ab, "TELEGRAM_PULL_MODE", True), mock.patch.object(ab, "DERNIER_ETAT", etat):
            ab.TELEGRAM_PULL_CONTEXT.chat_id = ""
            ab.TELEGRAM_PULL_CONTEXT.private = False
            entree = "🎯 POSITION ALIGN DÉTECTÉE — GOLD"
            self.assertTrue(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "-1002", "text": entree}))
            self.assertTrue(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "-1001", "text": entree}))
            # Chaîne : tout le reste reste bloqué (point de marché, commentaire, mise à jour).
            self.assertFalse(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "-1002", "text": "📡 POINT DE MARCHÉ"}))
            self.assertFalse(ab._telegram_sortant_autorise("editMessageText", {"chat_id": "-1002", "text": entree}))
            # Chat inconnu : bloqué même pour une entrée.
            self.assertFalse(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "-1999", "text": entree}))

    def test_telegram_pull_mode_allows_only_current_private_interaction(self):
        with mock.patch.object(ab, "TELEGRAM_PULL_MODE", True):
            ab.TELEGRAM_PULL_CONTEXT.chat_id = "42"
            ab.TELEGRAM_PULL_CONTEXT.private = True
            try:
                self.assertTrue(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "42", "text": "Analyse demandée"}))
                self.assertFalse(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "43", "text": "Unsolicited"}))
            finally:
                ab.TELEGRAM_PULL_CONTEXT.chat_id = None
                ab.TELEGRAM_PULL_CONTEXT.private = False

    def test_recevoir_updates_propage_le_contexte_prive_des_callbacks(self):
        update = {"callback_query": {
            "id": "cb-1",
            "from": {"id": 42},
            "message": {"chat": {"id": 42, "type": "private"}},
            "data": "botmenu"
        }}
        observed = []
        def fake_traiter(etat, chats, updates):
            observed.append(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "42", "text": "Réponse au bouton"}))
            observed.append(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "43", "text": "Message non sollicité"}))
            return []
        queue = ab.queue.Queue()
        queue.put(update)
        with mock.patch.object(ab, "TOKEN", "test-token"), \
             mock.patch.object(ab, "TELEGRAM_PULL_MODE", True), \
             mock.patch.object(ab, "TELEGRAM_UPDATES", queue), \
             mock.patch.object(ab, "traiter", side_effect=fake_traiter):
            ab.recevoir_updates_telegram({}, set(), [])
        self.assertEqual(observed, [True, False])
        self.assertIsNone(ab.TELEGRAM_PULL_CONTEXT.chat_id)
        self.assertFalse(ab.TELEGRAM_PULL_CONTEXT.private)

    def test_recevoir_updates_propage_le_contexte_prive_des_messages(self):
        update = {"message": {
            "chat": {"id": 42, "type": "private"},
            "from": {"id": 42},
            "text": "/live"
        }}
        observed = []
        def fake_traiter(etat, chats, updates):
            observed.append(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "42", "text": "Réponse à /live"}))
            observed.append(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "43", "text": "Message non sollicité"}))
            return []
        queue = ab.queue.Queue()
        queue.put(update)
        with mock.patch.object(ab, "TOKEN", "test-token"), \
             mock.patch.object(ab, "TELEGRAM_PULL_MODE", True), \
             mock.patch.object(ab, "TELEGRAM_UPDATES", queue), \
             mock.patch.object(ab, "traiter", side_effect=fake_traiter):
            ab.recevoir_updates_telegram({}, set(), [])
        self.assertEqual(observed, [True, False])
        self.assertIsNone(ab.TELEGRAM_PULL_CONTEXT.chat_id)
        self.assertFalse(ab.TELEGRAM_PULL_CONTEXT.private)

    def test_telegram_pull_block_is_not_reported_as_successful_delivery(self):
        with mock.patch.object(ab, "TELEGRAM_PULL_MODE", True), \
             mock.patch.object(ab, "_telegram_sortant_autorise", return_value=False), \
             mock.patch.object(ab, "http_json") as request:
            result = ab.telegram("sendMessage", chat_id="other", text="ALERT")
        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked_by_pull_mode"])
        request.assert_not_called()

    def test_blocked_position_notification_is_not_marked_as_sent(self):
        market, cid = "BTC", "user-42"
        trade = {"d": 1, "e": 100.0, "sl": 98.0, "tp1": 104.0, "tp2": 108.0, "ouvert_t": 100}
        state = {
            "coach_live": {market: {cid: {"dernier_t": 0, "started_t": 50}}},
            "recherche_positions_active": [cid]
        }
        with mock.patch.object(ab, "bot_on", return_value=True), \
             mock.patch.object(ab, "dans_chaine", return_value=False), \
             mock.patch.object(ab, "_envoi_sur", return_value={"ok": False, "blocked_by_pull_mode": True}), \
             mock.patch.object(ab, "markup_analyse", return_value=None):
            ab.notifier_coach_live(state, market, {"m1": [{"c": 101.0}]}, {"trade": trade})
        self.assertNotIn("position_key", state["coach_live"][market][cid])
        self.assertEqual(state["recherche_positions_active"], [cid])

    def test_telegram_pull_mode_allows_entry_only_for_active_search(self):
        previous = ab.DERNIER_ETAT
        ab.DERNIER_ETAT = {"recherche_positions_active": ["42"]}
        try:
            with mock.patch.object(ab, "TELEGRAM_PULL_MODE", True):
                self.assertTrue(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "42", "text": "🟢 J'ENTRE MAINTENANT — GOLD"}))
                self.assertTrue(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "42", "text": "🎯 POSITION ALIGN DÉTECTÉE — GOLD"}))
                self.assertFalse(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "42", "text": "Commentaire M15 : marché calme"}))
        finally:
            ab.DERNIER_ETAT = previous

    def test_confirmation_paiement_est_autorisee_seulement_dans_le_chat_prive(self):
        observed = []

        def faux_paiement(etat, cid, paiement):
            observed.append(ab._telegram_sortant_autorise(
                "sendMessage", {"chat_id": cid, "text": "Paiement confirmé"}))
            return True

        update = {"message": {
            "chat": {"id": 42, "type": "private"},
            "successful_payment": {"invoice_payload": "livemain:BTC"}
        }}
        with mock.patch.object(ab, "TELEGRAM_PULL_MODE", True), \
             mock.patch.object(ab, "live_paiement_recu", side_effect=faux_paiement):
            self.assertTrue(ab._traiter_paiement_rapide({}, update))
            self.assertFalse(ab._telegram_sortant_autorise(
                "sendMessage", {"chat_id": "42", "text": "Message spontané"}))

        self.assertEqual(observed, [True])

    def test_demande_analyse_autorise_une_reponse_apres_le_traitement_du_bouton(self):
        observations = []

        def faux_http(url, data):
            observations.append(ab._telegram_sortant_autorise(
                "sendMessage", {"chat_id": "42", "text": "Analyse demandée"}))
            return {"ok": True, "result": {"message_id": 123}}

        with mock.patch.object(ab, "TELEGRAM_PULL_MODE", True), \
             mock.patch.object(ab, "http_json", side_effect=faux_http):
            resultat = ab._envoi_sur_demande("42", text="Analyse demandée")
            self.assertFalse(ab._telegram_sortant_autorise(
                "sendMessage", {"chat_id": "42", "text": "Message spontané"}))
            self.assertFalse(ab._telegram_sortant_autorise(
                "sendMessage", {"chat_id": "43", "text": "Analyse demandée"}))

        self.assertTrue(resultat["ok"])
        self.assertEqual(observations, [True])



    def test_entry_price_mask_is_not_hidden_on_transient_canvas_read_miss(self):
        bande = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "live", "align-bande-live.user.js"), encoding="utf-8").read()
        self.assertIn("const cel = celluleSens(); if (!cel) return;", bande)
        self.assertNotIn("if (!cel) { masque.style.display = 'none'; return; }", bande)

    def test_live_overlay_reads_consumption_percent_from_fvg_and_order_block_boxes(self):
        bande = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "live", "align-bande-live.user.js"), encoding="utf-8").read()
        self.assertIn("function texteZone(t, m)", bande)
        self.assertIn("consommée|consommé", bande)
        self.assertIn("'% de zone consommée'", bande)
        self.assertIn("' • ' + consommation", bande)

    def test_market_narration_keeps_forming_candle_anticipation_and_closed_candle_validation(self):
        bande = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "live", "align-bande-live.user.js"), encoding="utf-8").read()
        # Bougie en cours : anticipation provisoire conservée (jamais une autorisation d'entrée).
        self.assertIn("const cur = B[B.length - 1], prev = B.slice(-21, -1);", bande)
        self.assertIn("chasseSousSupport", bande)
        self.assertIn("chasseAuDessus", bande)
        self.assertIn("La bougie est encore en formation", bande)
        # Bougie clôturée : validation du balayage, sans signal d'entrée à elle seule.
        self.assertIn("const terminee = B[B.length - 2]", bande)
        self.assertIn("Possible chasse de liquidité vendeuse", bande)
        self.assertIn("Possible chasse de liquidité acheteuse", bande)
        self.assertIn("ce n’est pas encore un signal LONG", bande)
        self.assertIn("ce n’est pas encore un signal SHORT", bande)
        # Priorité : validation clôturée > anticipation en cours > tendance, chaîne else-if intacte.
        self.assertLess(bande.index("if (balayageBas) lecture"), bande.index("else if (chasseSousSupport) lecture"))
        self.assertLess(bande.index("else if (chasseSousSupport) lecture"), bande.index("else if (dFond > 0 && dRecent < 0) lecture"))

    def test_market_narration_is_factual_and_runs_independently_of_generic_coach(self):
        bande = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "live", "align-bande-live.user.js"), encoding="utf-8").read()
        self.assertIn("function commentaireMarcheEnDirect(B, moyR, moyV, m)", bande)
        self.assertIn("The recent trend still points higher", bande)
        self.assertIn("The market is ranging", bande)
        self.assertIn("Volume is clearly above its recent average", bande)
        self.assertIn("Date.now() - derniereTend > 55000", bande)
        self.assertIn("derniereCoach", bande)
        self.assertIn("Date.now() - derniereTend < 40000", bande)
        self.assertIn("coachN++; derniereCoach = Date.now();", bande)
        self.assertIn("🔇 COACH VOCAL OFF", bande)
        self.assertNotIn("Le coach ALIGN est en direct", bande)  # v12.2.8 : plus de phrase d'accueil

    def test_ai_live_market_commentary_refreshes_every_ten_minutes(self):
        state = {}
        sent = []
        with mock.patch.object(ab, "LIVE_IA_INTERVALLE", 600), \
             mock.patch.object(ab, "live_actif", return_value=True), \
             mock.patch.object(ab, "contexte_technique_live", return_value={"marches": {"BTC": {"biais_plan": "haussier"}}}), \
             mock.patch.object(ab, "ia", return_value="BTC | Les acheteurs gardent la main mais le rythme ralentit. | Buyers remain in control but momentum is slowing.") as ia_mock, \
             mock.patch.object(ab, "live_publier", side_effect=lambda message: sent.append(message) or True):
            self.assertTrue(ab.live_phrases_ia(state, 1000, {}))
            ia_mock.assert_called_with(mock.ANY, mock.ANY, mock.ANY, cle_cache="live_commentary", duree=ab.LIVE_IA_INTERVALLE, premium=True, prefer_paid=True)
            self.assertFalse(ab.live_phrases_ia(state, 1599, {}))
            self.assertTrue(ab.live_phrases_ia(state, 1600, {}))
        self.assertEqual(len(sent), 2)
        self.assertTrue(all(message.startswith("IA:") for message in sent))


class LiveAgendaMarketTimezoneTests(unittest.TestCase):
    def test_live_agenda_uses_local_market_timezones_during_dst_weeks(self):
        cases = (
            # Tokyo is 09:00 JST; in July this is 02:00 Paris, not 01:00.
            (datetime.datetime(2026, 7, 16, 23, 45, tzinfo=datetime.timezone.utc).timestamp(), "TOKYO"),
            # US DST starts before Paris DST in March: NY 09:30 EDT = 13:30 UTC.
            (datetime.datetime(2026, 3, 9, 13, 15, tzinfo=datetime.timezone.utc).timestamp(), "NEW YORK"),
            # US DST ends after Paris DST in October: NY 09:30 EDT = 13:30 UTC.
            (datetime.datetime(2026, 10, 26, 13, 15, tzinfo=datetime.timezone.utc).timestamp(), "NEW YORK"),
        )
        for now, market in cases:
            published = []
            with mock.patch.object(ab, "live_actif", return_value=True), \
                 mock.patch.object(ab, "calendrier", return_value=[]), \
                 mock.patch.object(ab, "live_bande", side_effect=lambda etat, texte, *args, **kwargs: published.append(texte) or True):
                ab.live_agenda({}, now)
            # Session labels include their market emoji (for example, "🇯🇵 TOKYO").
            self.assertTrue(
                any("OUVERTURE" in str(message) and market in str(message) and "DANS 15 MIN" in str(message) for message in published),
                f"opening announcement missing for {market} at {datetime.datetime.fromtimestamp(now, datetime.timezone.utc)}",
            )


if __name__ == "__main__":
    unittest.main()


class BandePulsion(unittest.TestCase):
    def test_pulsion_sans_info(self):
        for f in ("🎙 ÇA BOUGE !\n🟠 BTC : 65 560\n🔴 Les vendeurs accélèrent", "🎙 GROSSE MÈCHE !\n🥇 GOLD : 4 012"):
            t = ab.texte_bande_flash(f)
            self.assertTrue(t.startswith("BULLE:"))
            self.assertIn("lien en bio", t.lower())
            self.assertIsNone(re.search(r"\d{2,}|BTC|GOLD|NASDAQ|LONG|SHORT|Telegram", t))

    def test_menu_chaine(self):
        texte, kb = ab.menu_chaine({}, "BTC")
        self.assertIn("ALIGN", texte)
        urls = [b["url"] for l in json.loads(kb)["inline_keyboard"] for b in l]
        self.assertIn(ab.BOT_LIEN, urls)
        self.assertIn(ab.LIVE_LIEN, urls)
        self.assertIn(ab.LIENS_CHAINES["GOLD"], urls)
        self.assertNotIn(ab.LIENS_CHAINES["BTC"], urls)


class BandeNews(unittest.TestCase):
    def test_etapes(self):
        vus = {}
        for reste, attendu in ((15 * 60, "n15"), (10 * 60, "n10"), (5 * 60, "n5"), (-5 * 60, "nreac"), (-20 * 60, "nfin"), (40 * 60, None)):
            e, t = ab.textes_live_news("CPI (inflation)", reste)
            self.assertEqual(e, attendu)
            if t:
                self.assertIn("lien en bio", t)
                self.assertNotIn("Telegram", t)
        self.assertIn("SL et ton TP", ab.textes_live_news("CPI", 600)[1])

    def test_une_fois_par_etape(self):
        envoye = []
        etat = {}
        with mock.patch.object(ab, "calendrier", return_value=[{"t": 10_000, "titre": "NFP"}]), \
             mock.patch.object(ab, "live_publier", side_effect=lambda t: envoye.append(t) or True):
            ab.live_news(etat, 10_000 - 14 * 60)
            ab.live_news(etat, 10_000 - 13 * 60)
            ab.live_news(etat, 10_000 - 9 * 60)
        self.assertEqual(len(envoye), 2)


class MarcheFermeJamaisEnPosition(unittest.TestCase):
    def test_gold_ferme_avec_trade_perime(self):
        import datetime
        from zoneinfo import ZoneInfo
        samedi = datetime.datetime(2026, 11, 14, 12, 0, tzinfo=ZoneInfo("America/Chicago")).timestamp()
        r = {"m1": [{"c": 4000.0}]}
        for m in ("GOLD", "NASDAQ"):
            p = ab.proximite_marche(m, r, {"trade": {"d": 1}}, samedi)
            self.assertEqual(p["classe"], "ferme")
        self.assertEqual(ab.proximite_marche("BTC", r, {"trade": {"d": 1}}, samedi)["classe"], "position")


class CarteEntreeClaire(unittest.TestCase):
    def test_pas_de_jaune_et_meme_bougie_que_le_chrono(self):
        o = {"e": 100.0, "za": 99.0, "zb": 101.0, "tp1": 95.0, "src": "FVG"}
        with unittest.mock.patch.object(ab, "timeframe_attendu", return_value="5m"):
            t = ab.avant_entree("BTC", {}, {}, o, -1)
        self.assertNotIn("jaune", t.lower()); self.assertNotIn("15 min", t)
        self.assertIn("bougie 5 min CLÔTURE SOUS l'étiquette « ENTRÉE »", t)
        self.assertIn("on n'entre PAS encore", t); self.assertIn("VALIDÉ 🔴 SHORT", t)
        self.assertIn("CLOSE BELOW", ab.traduire(t))


class ZoneMangee(unittest.TestCase):
    """Même lecture que l'indicateur v87 : la partie vide de la zone = mangée par les bougies."""
    def b(self, h, l):
        return {"h": h, "l": l, "o": l, "c": h}

    def test_pourcentages(self):
        self.assertEqual(ab.zone_mangee([self.b(95, 90)], 100, 110), 0)            # pas encore touchée
        self.assertEqual(ab.zone_mangee([self.b(105, 90)], 100, 110), 50)          # la moitié du bas mangée (SHORT)
        self.assertEqual(ab.zone_mangee([self.b(120, 90)], 110, 100), 100)         # traversée (ordre des bornes indifférent)
        self.assertIsNone(ab.zone_mangee([], 100, 110))

    def test_carte_entree_affiche_le_pourcentage(self):
        o = {"e": 100.0, "za": 100.0, "zb": 110.0}
        r = {"b5": [self.b(104, 95)] * 3 + [self.b(1, 1)]}                         # la dernière bougie (en formation) est ignorée
        with unittest.mock.patch.object(ab, "timeframe_attendu", return_value="5m"):
            t = ab.avant_entree("BTC", r, {}, o, -1)
        self.assertIn("🍽 Zone mangée à 40 %", t)
        self.assertIn("Zone eaten 40 %", ab.traduire(t))


class ScalpVautLeCoup(unittest.TestCase):
    def test_regle(self):
        si = {"d": 1, "e": 100.0, "sl": 95.0, "tp": 115.0, "rr": 3.0, "voy": 3, "atr": 4.0}
        self.assertTrue(ab.scalp_vaut_le_coup(si))
        self.assertFalse(ab.scalp_vaut_le_coup(dict(si, rr=1.5)))                 # gain < 2 × risque
        self.assertFalse(ab.scalp_vaut_le_coup(dict(si, atr=10.0)))               # trop court (< 2 ATR)
        self.assertIn("le bot le prend", "\n".join(ab.texte_scalp("BTC", si, -1)))
        self.assertIn("ne le prend pas", "\n".join(ab.texte_scalp("BTC", dict(si, rr=1.5), -1)))


class LeconsIA(unittest.TestCase):
    def test_lecons_relues_et_pause_apres_2_sl(self):
        etat = {}
        pr = {"d": 1, "type": "repli"}
        self.assertFalse(ab.noter_lecon(etat, "BTC", pr, -1.0, "Entrée trop tôt, attendre la clôture"))
        self.assertTrue(ab.noter_lecon(etat, "BTC", pr, -0.5, "Zone déjà mangée à 100 %"))
        self.assertTrue(ab.en_pause(etat, "BTC")); self.assertFalse(ab.en_pause(etat, "GOLD"))
        self.assertTrue(any("trop tôt" in x for x in ab.lecons_pour("BTC")))
        ab.noter_lecon(etat, "BTC", pr, 2.0, "TP propre")
        self.assertEqual(etat["serie_sl"]["BTC"], 0)
        with unittest.mock.patch.object(ab, "_envoi_sur") as env:
            ab.auto_entree(etat, "BTC", {"d": 1, "e": 1, "sl": 0.5, "tp1": 3})   # en pause : aucun ordre
        env.assert_not_called()
        ab.LECONS[:] = []


class TestLiveBoostCallbackDispatch(unittest.TestCase):
    def test_private_boost_callback_saves_telegram_first_name_and_queues_it(self):
        ab._LIVE_BOOSTS.clear()
        state = {"live_on": True, "live_screen_seen_t": __import__("time").time(), "prenoms": {}}
        published = []
        sent = []
        update = {"update_id": 99001, "callback_query": {
            "id": "cb-liveboost",
            "from": {"id": 44, "first_name": "Nora"},
            "message": {"chat": {"id": 44, "type": "private"}},
            "data": "liveboost:x"
        }}
        with mock.patch.object(ab, "LIVE_SUJET", "test-sujet"), \
             mock.patch.object(ab, "ecran_signal_frais", return_value=True), \
             mock.patch.object(ab, "live_publier", side_effect=lambda t: published.append(t) or True), \
             mock.patch.object(ab, "_envoi_sur", side_effect=lambda cid, **kw: sent.append((cid, kw)) or {"ok": True}), \
             mock.patch.object(ab, "telegram", return_value={"ok": True}):
            ab.traiter(state, set(), [update])
        self.assertEqual(state["prenoms"]["44"], "Nora")
        self.assertEqual(published, ["🙏 MERCI NORA ! Nora BOOSTE LE LIVE 🚀 ABONNE-TOI • PARTAGE"])
        self.assertTrue(any("Ton prénom doit apparaître" in kw.get("text", "") for _, kw in sent))




class LiquiditySweepReversalDetection(unittest.TestCase):
    def _bars(self, side):
        bars = []
        for i in range(24):
            bars.append({"t": i * 900, "o": 104.0, "h": 110.0, "l": 100.0, "c": 105.0, "v": 100.0})
        if side == "bull":
            bars.append({"t": 24 * 900, "o": 100.4, "h": 102.0, "l": 99.5, "c": 101.2, "v": 180.0})
        else:
            bars.append({"t": 24 * 900, "o": 109.6, "h": 110.5, "l": 108.0, "c": 108.8, "v": 180.0})
        return bars

    def test_bullish_false_break_reclaims_support(self):
        result = ab.detecter_chasse_liquidite(self._bars("bull"), 2.0)
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], 1)
        self.assertEqual(result["type"], "reprise_haussiere_apres_chasse")
        self.assertEqual(result["volume_ratio"], 1.8)

    def test_bearish_false_break_rejects_resistance(self):
        result = ab.detecter_chasse_liquidite(self._bars("bear"), 2.0)
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], -1)
        self.assertEqual(result["type"], "rejet_baissier_apres_chasse")

    def test_no_reversal_when_close_stays_below_support(self):
        bars = self._bars("bull")
        bars[-1]["c"] = 99.8
        self.assertIsNone(ab.detecter_chasse_liquidite(bars, 2.0))

    def test_missing_or_insufficient_bars_never_invents_a_reversal(self):
        self.assertIsNone(ab.detecter_chasse_liquidite([], 2.0))
        self.assertIsNone(ab.detecter_chasse_liquidite(self._bars("bull")[:10], 2.0))

    def test_m5_early_sweep_uses_shorter_lookback(self):
        result = ab.detecter_chasse_liquidite(self._bars("bull")[-13:], 2.0, lookback=12)
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], 1)




class LiveMarketNarrationFallback(unittest.TestCase):
    """Regression tests for factual commentary when external AI providers fail."""
    def test_fallback_comments_all_markets_from_actual_context(self):
        data = {"marches": {
            "BTC": {"biais_plan": "haussier", "confirmation_4h_1h": "alignées à la hausse",
                    "rsi_15m": 54.0, "volume_15m_vs_moyenne": 1.8,
                    "fibonacci": {"H1": {"lecture": "zone clé de retracement profond"}}},
            "GOLD": {"biais_plan": "baissier", "confirmation_4h_1h": "non alignées",
                     "rsi_15m": 28.0, "volume_15m_vs_moyenne": 0.5},
            "NASDAQ": {"biais_plan": "neutre", "confirmation_4h_1h": "alignées à la baisse",
                       "rsi_15m": 72.0}
        }}
        raw = ab.commentaires_live_de_secours(data)
        parsed = ab.phrases_bande_par_marche(raw)
        self.assertEqual(set(parsed), {"BTC", "GOLD"})
        self.assertTrue(all(len(parsed[m]) == 2 for m in parsed))
        self.assertTrue(all(8 <= len(fr) <= 140 and 8 <= len(en) <= 140 for pairs in parsed.values() for fr, en in pairs))
        self.assertIn("volume Kraken accélère", parsed["BTC"][1][0])
        self.assertIn("confirment la hausse", parsed["BTC"][0][0])
        self.assertIn("zone profonde", parsed["BTC"][1][0])
        self.assertIn("volume proxy reste discret", parsed["GOLD"][1][0])
        self.assertNotIn("NASDAQ", parsed)

    def test_fallback_never_invents_market_without_data(self):
        self.assertEqual(ab.commentaires_live_de_secours({"marches": {}}), "")


class LiveMarketPartialAiCoverage(unittest.TestCase):
    def test_partial_ai_reply_is_completed_for_every_available_market(self):
        data = {"marches": {
            "BTC": {"biais_plan": "haussier", "confirmation_4h_1h": "alignées à la hausse",
                    "rsi_15m": 54.0},
            "GOLD": {"biais_plan": "baissier", "confirmation_4h_1h": "non alignées",
                     "rsi_15m": 28.0, "volume_15m_vs_moyenne": 0.5},
            "NASDAQ": {"biais_plan": "neutre", "confirmation_4h_1h": "alignées à la baisse",
                       "rsi_15m": 72.0}
        }}
        published = []
        state = {}
        with (
            mock.patch.object(ab, "LIVE_IA_INTERVALLE", 180),
            mock.patch.object(ab, "live_actif", return_value=True),
            mock.patch.object(ab, "contexte_technique_live", return_value=data),
            mock.patch.object(ab, "ia", return_value="BTC | Les acheteurs gardent la main mais la reprise doit confirmer. | Buyers remain in control but the recovery must confirm."),
            mock.patch.object(ab, "live_publier", side_effect=lambda message: published.append(message) or True)
        ):
            self.assertTrue(ab.live_phrases_ia(state, 1000, {}))
        self.assertEqual(len(published), 1)
        payload = json.loads(published[0][3:])
        self.assertEqual(set(payload), {"BTC", "GOLD"})
        self.assertTrue(all(len(payload[m]) == 2 for m in payload))
        self.assertIn("biais reste baissier", payload["GOLD"][0][0].lower())


class LiveNarrationPrioritizesLiquiditySweep(unittest.TestCase):
    def test_closed_reversal_watch_overrides_generic_ai_line(self):
        data = {"marches": {
            "GOLD": {
                "biais_plan": "neutre",
                "confirmation_4h_1h": "non alignées",
                "surveillance_retournement": {"direction": 1, "type": "reprise_haussiere_apres_chasse"}
            }
        }}
        ai = (
            "GOLD | Le marché consolide dans sa zone technique et attend une clôture plus claire. | "
            "The market is consolidating in its technical area and awaits a clearer close.\n"
            "GOLD | Le rythme ralentit avant la prochaine impulsion et la structure reste à surveiller. | "
            "Momentum is slowing before the next impulse and structure remains in focus."
        )
        published = []
        with (
            mock.patch.object(ab, "LIVE_IA_INTERVALLE", 180),
            mock.patch.object(ab, "live_actif", return_value=True),
            mock.patch.object(ab, "contexte_technique_live", return_value=data),
            mock.patch.object(ab, "ia", return_value=ai),
            mock.patch.object(ab, "live_publier", side_effect=lambda message: published.append(message) or True)
        ):
            self.assertTrue(ab.live_phrases_ia({}, 1000, {}))
        payload = json.loads(published[0][3:])
        self.assertIn("balayage du support", payload["GOLD"][1][0])
        self.assertIn("not yet confirmed", payload["GOLD"][1][1])
        self.assertLessEqual(len(payload["GOLD"][1][0]), 140)
        self.assertLessEqual(len(payload["GOLD"][1][1]), 140)




class LiveClosedCandleContext(unittest.TestCase):
    def test_context_uses_last_available_closed_m15_candle_for_sweep(self):
        bars = []
        for i in range(24):
            bars.append({"t": i * 900, "o": 104.0, "h": 110.0, "l": 100.0, "c": 105.0, "v": 100.0})
        bars.append({"t": 24 * 900, "o": 100.4, "h": 102.0, "l": 99.5, "c": 101.2, "v": 180.0})
        latest = {
            "b15_long": bars, "m1": [{"c": 101.2}], "atr": 2.0,
            "dirs": [1] * 11, "dirPlan": 1, "niveaux": [], "rC": 54.0
        }
        context = ab.contexte_technique_live({"BTC": latest})
        self.assertEqual(context["marches"]["BTC"]["surveillance_retournement"]["direction"], 1)
        self.assertEqual(context["marches"]["BTC"]["surveillance_retournement"]["type"], "reprise_haussiere_apres_chasse")


class LiveNarrationPrioritizesM5M15Conflict(unittest.TestCase):
    def test_conflicting_closed_timeframe_sweeps_override_generic_ai(self):
        data = {"marches": {
            "GOLD": {
                "biais_plan": "neutre",
                "confirmation_4h_1h": "non alignées",
                "surveillance_retournement": {"direction": 0, "conflit": True, "timeframe": "M5/M15"}
            }
        }}
        ai = (
            "GOLD | Le marché consolide dans sa zone technique et attend une clôture plus claire. | "
            "The market is consolidating in its technical area and awaits a clearer close.\n"
            "GOLD | Le rythme ralentit avant la prochaine impulsion et la structure reste à surveiller. | "
            "Momentum is slowing before the next impulse and structure remains in focus."
        )
        published = []
        with (
            mock.patch.object(ab, "LIVE_IA_INTERVALLE", 180),
            mock.patch.object(ab, "live_actif", return_value=True),
            mock.patch.object(ab, "contexte_technique_live", return_value=data),
            mock.patch.object(ab, "ia", return_value=ai),
            mock.patch.object(ab, "live_publier", side_effect=lambda message: published.append(message) or True)
        ):
            self.assertTrue(ab.live_phrases_ia({}, 1000, {}))
        payload = json.loads(published[0][3:])
        self.assertNotIn("NASDAQ", payload)


class VoixNaturelleSeulementV1228(unittest.TestCase):
    """v12.2.8 (demande d'Adel) : une seule voix naturelle, OFF = silence, pas de phrase d'accueil, pas de voix robot."""

    def _lire(self, rel):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", *rel)
        return open(path, encoding="utf-8").read()

    def test_bande_version_12_2_13_voice_recovery_and_sync(self):
        bande = self._lire(["docs", "live", "align-bande-live.user.js"])
        self.assertIn("// @version      12.2.13", bande)
        self.assertIn("const VERSION = '12.2.13';", bande)
        self.assertIn('let voixUtterance = null', bande)
        self.assertIn('voixUtterance = utterance;', bande)
        self.assertIn("voiceschanged", bande)
        self.assertIn("voixEnAttente = item", bande)
        self.assertIn("bulle ? 'marche' : 'live'", bande)

    def test_voice_button_replays_last_visible_ai_comment_without_greeting(self):
        bande = self._lire(["docs", "live", "align-bande-live.user.js"])
        self.assertIn("let dernierCommentaireIA = null", bande)
        self.assertIn("if (m.source === 'ia') dernierCommentaireIA = m", bande)
        self.assertIn("market: source === 'ia' ? codeMarche() : ''", bande)
        self.assertIn("if (dernier && (!dernier.market || dernier.market === codeMarche())) parlerLive(dernier, true)", bande)
        self.assertIn("function parlerLive(item, forcer = false)", bande)
        self.assertIn("if (anglais && !suiteAnglaise && !forcer) return 0", bande)
        self.assertIn("if (phrase.length < 12 || (!forcer && phrase === (anglais ? voixTexteEN : voixTexte))) return 0", bande)
        self.assertNotIn("Le coach ALIGN est en direct", bande)
        self.assertNotIn("I am now commenting on market action", bande)

    def test_bande_sens_suit_le_plan_reel(self):
        """Le sens LONG/SHORT de la bannière vient du plan réel du tableau, pas de l'horloge seule."""
        bande = self._lire(["docs", "live", "align-bande-live.user.js"])
        self.assertIn("const sensReel = ((cel.t || '').match(/\\b(SHORT|LONG)\\b/) || [])[1];", bande)
        self.assertIn("const vert = sensReel ? sensReel === 'LONG' : vertClignote;", bande)

    def test_bande_sans_sens_connu_pas_de_faux_long_short(self):
        """Sans sens lisible dans le plan, la bannière n'affiche ni LONG ni SHORT et reste neutre."""
        bande = self._lire(["docs", "live", "align-bande-live.user.js"])
        self.assertIn("!sensReel ? '#4a4a4a'", bande)
        self.assertIn(": (en ? 'ENTRY' : 'ENTRÉE') + ' <span class=\"cle\">❓</span> • TP", bande)

    def test_bande_sans_phrase_d_accueil(self):
        bande = self._lire(["docs", "live", "align-bande-live.user.js"])
        self.assertNotIn("Je commente maintenant ce que fait le marché", bande)
        self.assertNotIn("I am now commenting on market action", bande)

    def test_bande_sans_voix_robot_ni_repli(self):
        bande = self._lire(["docs", "live", "align-bande-live.user.js"])
        # plus aucun repli sur "dansLangue[0]" (= voix robot) ; sans voix naturelle, on ne parle pas
        self.assertNotIn("utterance.voice = dansLangue[0]", bande)
        self.assertNotIn("dansLangue[0]", bande)
        self.assertIn("if (!v) {", bande)
        self.assertIn("if (!anglais && voixActive) voixEnAttente = item;", bande)
        self.assertIn("return 0;   // aucune voix naturelle disponible : silence plutôt qu'une voix robot", bande)
        self.assertIn("utterance.voice = v;", bande)

    def test_bande_off_coupe_toute_la_parole(self):
        bande = self._lire(["docs", "live", "align-bande-live.user.js"])
        self.assertIn("try { window.speechSynthesis.cancel(); } catch (e) {}", bande)

    def test_extension_popup_ne_parle_plus(self):
        popup = self._lire(["tradingview-analyzer", "popup.js"])
        self.assertIn("cette extension ne parle plus", popup)
        self.assertNotIn("new SpeechSynthesisUtterance(_txt)\n    ;", popup)

    def test_pine_plus_de_point_entree_trace(self):
        pine = self._lire(["align-bot", "pine", "ALIGN_MTF_PRO_v25.pine"])
        self.assertNotIn('label.new(x1, ent, "ENTRÉE "', pine)
        self.assertNotIn("lE := line.new(x1, ent", pine)
        self.assertIn("plus de point d'entrée tracé", pine)
