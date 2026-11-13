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


class CarteCoach(unittest.TestCase):
    """Carte unique compressée : toutes les informations (ordre, DXY, news, niveaux, agent, action, système), une information par ligne."""
    TR = dict(d=-1, e=3995.2, sl=3999.99, tp1=3985.0, tp2=3895.54)

    def r(self, **kw):
        return dict({"m1": [{"t": T - 20, "o": 3985.0, "h": 3985.0, "l": 3985.0, "c": 3985.0}], "dirPlan": -1, "atr": 4.0, "strat": "SWING",
                     "niveaux": [(3995.0, "1h"), (4010.0, "4h"), (3970.0, "Daily"), (3999.0, "15m")], "tv_indicator_mtf": {"available": False},
                     "macro_data": {"disponible": True, "dollar_direction": "HAUSSIER (BULLISH)", "dxy_variation_1h_pct": 0.13}}, **kw)

    def etat(self, **kw):
        return dict({"cal": {"ev": [{"t": T + 900, "titre": "CPI USA", "prev": "3", "avant": "3"}]}}, **kw)

    def test_signal_format_complet(self):
        with patch.object(ab, "heure", return_value="14:30"), patch.object(ab, "time", wraps=ab.time) as tm:
            tm.time.return_value = T
            txt = ab.carte_coach("GOLD", self.r(), {}, "signal", tr=self.TR, validite="clôture 15 min (14:15)", signal="Rejet 5 min + 4h/1h", etat=self.etat())
        self.assertEqual(txt.split("\n"), [
            "📍 GOLD - SHORT", "", "🛑 SL : 3999,99", "🎯 Entrée : 3995,20", "💰 TP1 : 3985", "🏁 TP2 : 3895,54", "⚖️ R:R : 1:2,1", "⏱ Valide : clôture 15 min (14:15)", "",
            "📊 Contexte :", "🔹 Signal : Rejet 5 min + 4h/1h", "🔹 DXY : Haussier ⚠️ +0,13 %/1h", "🔹 News : CPI USA 14:30 (dans 15 min)",
            "🔹 Niveaux : R: 3995 | S: 3970", "", "🤖 Agent Auto-Trade : %%AGENT:signal%%", "🛡️ Action : ENTRER", "", "🔌 Sys: TV❌ News✅ DXY✅ Agent✅"])

    def test_attente_raison_declencheur_zone_et_contexte(self):
        r = self.r(zone_pine={"za": 3994.0, "zb": 4012.0, "zmil": 4005.22})
        with patch.object(ab, "heure", return_value="14:30"):
            txt = ab.carte_coach("GOLD", r, {}, "attente", raison="Hors zone", declencheur="Clôture 1h sous 4005,22", etat=self.etat())
        l = txt.split("\n")
        self.assertEqual(l[:6], ["📍 GOLD - ATTENTE", "", "⏳ Raison : Hors zone", "🚀 Déclencheur : Clôture 1h sous 4005,22", "🔑 Zone : 3994 → 4012", ""])
        for k in ("🔹 DXY :", "🔹 News :", "🔹 Niveaux :", "🤖 Agent Auto-Trade :", "🛡️ Action : NE PAS RENTRER", "🔌 Sys:"):
            self.assertTrue(any(x.startswith(k) for x in l), k)

    def test_aucune_information_du_systeme_perdue(self):
        txt = ab.carte_coach("GOLD", self.r(), {}, "attente", raison="News proche", declencheur="x", etat=self.etat())
        for k in ("DXY", "News", "Niveaux", "Agent Auto-Trade", "Action", "Sys:"):
            self.assertIn(k, txt)

    def test_donnees_manquantes_affichees_honnetement(self):
        txt = ab.carte_coach("GOLD", self.r(niveaux=[], macro_data=None), {}, "attente", raison="x", declencheur="y", etat={})
        self.assertIn("DXY : n/d", txt); self.assertIn("News : Aucune", txt); self.assertIn("R: — | S: —", txt)
        self.assertIn("TV❌ News❌ DXY❌ Agent✅", txt)

    def test_raisons_en_deux_mots(self):
        for brut, court in (("La 4 h est neutre : pas de direction", "4h neutre"), ("Le 1h ne confirme pas la tendance 4h", "1h non confirmé"),
                            ("Le prix doit revenir en zone", "Hors zone"), ("📰 News dans moins de 15 min", "News proche"),
                            ("Prix tout en BAS Daily / Weekly", "Zone extrême D/W"), ("Rien de connu ici bas", "Rien de connu")):
            self.assertEqual(ab.raison_2_mots(brut), court)

    def test_agent_auto_trade_par_compte(self):
        e = {"bot_off": ["off"], "canal": "canal", "GOLD": {}}
        self.assertEqual(ab.agent_pour(e, "off", "GOLD", "attente"), "OFF")
        self.assertEqual(ab.agent_pour(e, "on", "GOLD", "attente"), "Attente")
        self.assertEqual(ab.agent_pour(e, "on", "GOLD", "signal"), "ON")
        self.assertEqual(ab.agent_pour(dict(e, GOLD={"trade": {"d": 1}}), "on", "GOLD", "attente"), "ON")
        self.assertEqual(ab.agent_pour(e, "canal", "GOLD", "signal"), "Actif")

    def test_substitution_par_destinataire_dans_telegram(self):
        envoyes = []
        txt = "📍 GOLD - ATTENTE\n\n🤖 Agent Auto-Trade : %%AGENT:attente%%"
        with patch.object(ab, "DERNIER_ETAT", {"bot_off": ["off"]}), patch.object(ab, "TOKEN", "x"), \
             patch.object(ab, "_telegram_verifie_cooldown", lambda *a, **k: None), patch.object(ab, "api_telegram", create=True), \
             patch("time.sleep"), patch("urllib.request.urlopen", side_effect=lambda req, timeout=None: envoyes.append(req.data) or (_ for _ in ()).throw(RuntimeError("stop"))):
            for cid in ("on", "off"):
                try:
                    ab.telegram("sendMessage", chat_id=cid, text=txt)
                except Exception:
                    pass
        corps = [b.decode() if isinstance(b, bytes) else str(b) for b in envoyes]
        self.assertTrue(any("Attente" in c for c in corps), corps)
        self.assertTrue(any("OFF" in c for c in corps), corps)
        self.assertFalse(any("%%AGENT" in c or "%25%25AGENT" in c for c in corps), corps)

    def test_detecte_comme_signal_et_jamais_filtre(self):
        sig = ab.carte_coach("GOLD", self.r(), {}, "signal", tr=self.TR, etat=self.etat())
        self.assertTrue(ab.est_entree(sig)); self.assertTrue(ab.est_entree("🟢🟢🟢 J'ENTRE MAINTENANT — GOLD"))
        self.assertFalse(ab.est_entree(ab.carte_coach("GOLD", self.r(), {}, "attente", raison="x", etat=self.etat())))
        e = {}
        self.assertFalse(ab.doublon_message(e, sig, T)); self.assertFalse(ab.doublon_message(e, sig, T + 5))

    def test_traduction_anglaise_de_la_carte(self):
        txt = ab.traduire(ab.carte_coach("GOLD", self.r(), {}, "attente", raison="Hors zone", declencheur="Clôture 1h sous 4005,22", etat=self.etat()))
        for k in ("📍 GOLD - WAIT", "⏳ Reason: Hors zone", "🚀 Trigger: 1h close below 4005,22", "📊 Context:", "Action: DO NOT ENTER", "Bullish"):
            self.assertIn(k, txt)

    def test_paires_compressees_restent_sur_une_ligne(self):
        txt = ab.mise_en_forme("📍 GOLD - SHORT\n\n🎯 Entrée : 3995,20 | 🛑 SL : 3999,99\n💰 TP : 3985 / 3895,54 | ⚖️ R:R : 1:2,1\n🔹 Niveaux : R: 3995 | S: 3970")
        l = txt.splitlines()
        for k in ("🎯 Entrée : 3995,20 | 🛑 SL : 3999,99", "💰 TP : 3985 / 3895,54 | ⚖️ R:R : 1:2,1", "🔹 Niveaux : R: 3995 | S: 3970"):
            self.assertIn(k, l)

    def test_une_information_par_ligne(self):
        txt = ab.mise_en_forme(ab.carte_coach("GOLD", self.r(), {}, "signal", tr=self.TR, validite="clôture 15 min (14:15)", signal="Rejet 5 min", etat=self.etat()))
        for l in txt.splitlines():
            self.assertLessEqual(len(l), 70, l)


class Hygiene(unittest.TestCase):
    def test_aucune_fonction_definie_deux_fois(self):
        """Une 2e définition du même nom écrase silencieusement la 1re (arrivé deux fois : raison_attente, news_courte)."""
        import collections, pathlib, re
        src = (pathlib.Path(ab.__file__)).read_text(encoding="utf-8")
        dups = {n: c for n, c in collections.Counter(re.findall(r"^def (\w+)\(", src, re.M)).items() if c > 1}
        self.assertEqual(dups, {})


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
            recu.setdefault(c, []).append([x for x in t.split("\n") if x in ("🥇 GOLD", "🟠 BTC", "💠 NASDAQ")])
        self.assertEqual(recu, {"adel": [["🥇 GOLD"]], "btc": [["🟠 BTC"]], "tous": [["🥇 GOLD", "🟠 BTC"]]})   # ses marchés seulement, UN message par session
        t_tous = dict(envois)["tous"]
        self.assertEqual(t_tous.count("🔔 OUVERTURE MARCHÉ"), 1)
        self.assertEqual(t_tous.count("⏰ Ouverture"), 1)

    def test_integration_alertes_courtes_n_envoie_plus_l_ancienne_alerte_groupee(self):
        ev = dict(kind="session", code="londres", evt="ouvre", palier=15, t=T + 900, nom=("Londres", "London"), mk=("GOLD et BTC", "GOLD and BTC"), marches=[])
        envois = []
        with patch.object(ab, "TOKEN", "x"), patch.object(ab, "evenements_sessions", return_value=[ev]), patch.object(ab, "evenements_pine", return_value=[]), \
             patch.object(ab, "_envoi_sur", side_effect=lambda c, **k: envois.append((c, k["text"]))), patch.object(ab, "destinataires_gratuits", return_value=[]):
            ab.alertes_courtes({}, {"vip"}, {"GOLD": self.r(), "BTC": self.r(73000.0)}, T)
        self.assertEqual(len(envois), 1)                                                     # GOLD + BTC regroupés en un seul message
        self.assertTrue(envois[0][1].startswith("🔔 OUVERTURE MARCHÉ : LONDRES"))
        self.assertIn("🥇 GOLD", envois[0][1]); self.assertIn("🟠 BTC", envois[0][1])

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
        html = ab.rendu_html(ab.mise_en_forme("🔴 GOLD - SHORT\n\n🎯 Entrée : 3995,20\n🛑 Stop : 3999,99\n💰 TP1 : 3985\n\n📊 Contexte : x"))
        l = html.split("\n")
        self.assertEqual(l[0], "<b>🔴 GOLD - SHORT</b>")
        for lab, val in (("🎯 Entrée", "3995,20"), ("🛑 Stop", "3999,99"), ("💰 TP1", "3985")):
            self.assertIn(f"<b>{lab} :</b> <b>{val}</b>", l)
        self.assertEqual(l.count(""), 1)                                    # un seul saut de ligne : entre les niveaux et le contexte
        self.assertNotEqual(l[-1], ""); self.assertNotEqual(l[2], "")

    def test_pas_de_saut_de_ligne_double_ni_en_tete(self):
        html = ab.rendu_html("Titre\n\n\n\nLigne : 1\n\n\nAutre : 2\n\n")
        self.assertNotIn("\n\n\n", html); self.assertFalse(html.endswith("\n"))



class SuiviPositionTests(unittest.TestCase):
    def test_carte_suivi_compacte_et_garde_jetons(self):
        t = ab.carte_suivi("GOLD", "TP1 TOUCHÉ", ["💰 TP1 : 1 ✅", "🔒 SL → BE : 2", "🏁 TP2 : 3"], "Sécuriser", {})
        self.assertTrue(t.startswith("🎉🥳 GOLD - TP1 TOUCHÉ"))   # un TP se fête (demande d Adel)
        for k in ("TP1", "BE", "TP2", "Action", "Agent Auto-Trade", "Sys:"):
            self.assertIn(k, t)
        self.assertNotIn("Ne coupe pas tout", t)


if __name__ == "__main__":
    unittest.main()
