"""Régressions : file Telegram après 429, calendrier inconnu, retours à la ligne des messages."""
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import align_bot as ab


class TelegramPullAuthorization(unittest.TestCase):
    def setUp(self):
        self.old_mode = ab.TELEGRAM_PULL_MODE
        self.old_chat = getattr(ab.TELEGRAM_PULL_CONTEXT, "chat_id", None)
        self.old_private = getattr(ab.TELEGRAM_PULL_CONTEXT, "private", False)
        self.old_news_chat = getattr(ab.TELEGRAM_PULL_CONTEXT, "news_chat_id", None)
        self.old_state = ab.DERNIER_ETAT
        ab.TELEGRAM_PULL_MODE = True
        ab.DERNIER_ETAT = None

    def tearDown(self):
        ab.TELEGRAM_PULL_MODE = self.old_mode
        ab.TELEGRAM_PULL_CONTEXT.chat_id = self.old_chat
        ab.TELEGRAM_PULL_CONTEXT.private = self.old_private
        ab.TELEGRAM_PULL_CONTEXT.news_chat_id = self.old_news_chat
        ab.DERNIER_ETAT = self.old_state

    def test_private_reply_allowed_only_for_requesting_chat(self):
        ab.TELEGRAM_PULL_CONTEXT.chat_id = "42"
        ab.TELEGRAM_PULL_CONTEXT.private = True
        self.assertTrue(ab._telegram_sortant_autorise(
            "sendMessage", {"chat_id": "42", "text": "Réponse à ta demande"}
        ))
        self.assertFalse(ab._telegram_sortant_autorise(
            "sendMessage", {"chat_id": "43", "text": "Réponse à ta demande"}
        ))

    def test_scoped_urgent_news_allowed_only_to_marked_market_channel(self):
        ab.TELEGRAM_PULL_CONTEXT.chat_id = None
        ab.TELEGRAM_PULL_CONTEXT.private = False
        ab.TELEGRAM_PULL_CONTEXT.news_chat_id = "-100123"
        ab.DERNIER_ETAT = {"canaux_marche": {"BTC": "-100123", "GOLD": "-100456"}}
        news = "🚨 NEWS DE DERNIÈ MINUTE\n📰 Headline\nDYOR"
        self.assertTrue(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "-100123", "text": news}))
        self.assertFalse(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "-100456", "text": news}))
        self.assertFalse(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "-100123", "text": "Statut du marché"}))
        self.assertFalse(ab._telegram_sortant_autorise("editMessageText", {"chat_id": "-100123", "text": news}))
        ab.TELEGRAM_PULL_CONTEXT.news_chat_id = None
        self.assertFalse(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "-100123", "text": news}))

    def test_unsolicited_status_message_remains_blocked(self):
        ab.TELEGRAM_PULL_CONTEXT.chat_id = None
        ab.TELEGRAM_PULL_CONTEXT.private = False
        self.assertFalse(ab._telegram_sortant_autorise(
            "sendMessage", {"chat_id": "42", "text": "Statut du marché"}
        ))


    def test_validated_entry_only_reaches_requested_user_and_configured_market_channel(self):
        ab.TELEGRAM_PULL_CONTEXT.chat_id = None
        ab.TELEGRAM_PULL_CONTEXT.private = False
        state = {
            "recherche_positions_active": ["42"],
            "canaux_marche": {"BTC": "-100123"},
        }
        entry = "J'ENTRE MAINTENANT — BTC"
        with mock.patch.object(ab, "DERNIER_ETAT", state):
            self.assertTrue(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "42", "text": entry}))
            self.assertTrue(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "-100123", "text": entry}))
            self.assertFalse(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "43", "text": entry}))
            self.assertFalse(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "-100999", "text": entry}))
            self.assertFalse(ab._telegram_sortant_autorise("sendMessage", {"chat_id": "-100123", "text": "Point de marché BTC"}))


class FileTelegram(unittest.TestCase):
    def item(self, prive):
        return {"key": "k", "chat_id": "42", "method": "sendMessage", "prive": prive,
                "params": {"chat_id": "42", "text": "Réponse à ton bouton"}, "tries": 0, "next_t": 0}

    def test_message_bloque_par_le_mode_pull_n_est_pas_compte_comme_envoye(self):
        etat = {"telegram_outbox": [self.item(False)]}
        with mock.patch.object(ab, "telegram", return_value={"ok": False, "blocked_by_pull_mode": True}):
            self.assertEqual(ab.traiter_file_telegram(etat, maintenant=10), 0)
        self.assertEqual(etat["telegram_outbox"], [])

    def test_reponse_privee_rejouee_dans_son_contexte_prive(self):
        vu = {}
        def faux(methode, **p):
            vu["ctx"] = (ab.TELEGRAM_PULL_CONTEXT.chat_id, ab.TELEGRAM_PULL_CONTEXT.private)
            return {"ok": True, "result": {"message_id": 1}}
        ab.TELEGRAM_PULL_CONTEXT.chat_id, ab.TELEGRAM_PULL_CONTEXT.private = "", False
        etat = {"telegram_outbox": [self.item(True)]}
        with mock.patch.object(ab, "telegram", side_effect=faux):
            self.assertEqual(ab.traiter_file_telegram(etat, maintenant=10), 1)
        self.assertEqual(vu["ctx"], ("42", True))
        self.assertEqual((ab.TELEGRAM_PULL_CONTEXT.chat_id, ab.TELEGRAM_PULL_CONTEXT.private), ("", False))

    def test_reponse_non_ok_reste_en_file(self):
        etat = {"telegram_outbox": [self.item(False)]}
        with mock.patch.object(ab, "telegram", return_value={"ok": False, "description": "Too Many Requests"}):
            self.assertEqual(ab.traiter_file_telegram(etat, maintenant=10), 0)
        self.assertEqual(len(etat["telegram_outbox"]), 1)
        self.assertEqual(etat["telegram_outbox"][0]["tries"], 1)


class CalendrierInconnu(unittest.TestCase):
    def test_calendrier_jamais_lu_bloque_comme_une_annonce(self):
        self.assertTrue(ab.annonce_proche({}, int(time.time())))

    def test_calendrier_trop_ancien_bloque(self):
        now = int(time.time())
        self.assertTrue(ab.annonce_proche({"cal": {"t": now - 7 * 3600, "ev": []}}, now))

    def test_calendrier_frais_sans_annonce_ne_bloque_pas(self):
        now = int(time.time())
        self.assertFalse(ab.annonce_proche({"cal": {"t": now - 600, "ev": []}}, now))

    def test_calendrier_frais_avec_annonce_proche_bloque(self):
        now = int(time.time())
        self.assertTrue(ab.annonce_proche({"cal": {"t": now - 600, "ev": [{"t": now + 300}]}}, now))

    def test_texte_news_dit_indisponible_si_trop_ancien(self):
        now = int(time.time())
        self.assertEqual(ab.news_txt({"cal": {"t": now - 7 * 3600, "ev": []}}), "📰 News : calendrier indisponible")


class PlanArrondi(unittest.TestCase):
    """Cas réel du 18/11 : bord de zone 63803,65 (arrondi JSON) contre 63803,6475 attendu."""
    def plan(self, signal, entry, sl, low, high):
        robot = {"signal": signal, "entry": entry, "sl": sl, "tp1": entry + (3 if signal == "LONG" else -3) * abs(entry - sl),
                 "planTimeframe": "M15", "entryTimeframe": "M5", "strategy": "DAY",
                 "entryZoneLow": low, "entryZoneHigh": high, "entryDecision": (low + high) / 2,
                 "entryBarTime": 900_000, "entryBarOpen": low, "entryBarHigh": high, "entryBarLow": low,
                 "entryBarClose": (low + high) / 2, "confirmed": True}
        r = {"tv_indicator_mtf": {"available": True, "activeTimeframe": "M5",
                                  "snapshots": {"M5": {"fresh": True, "confirmed": True, "robotV12": robot}}}}
        return ab.plan_indicateur(r)

    def test_bord_de_zone_arrondi_accepte_comme_par_le_bridge(self):
        # LONG : SL 63700, entrée 64114,59 → bord exact 63803,6475, envoyé arrondi 63803,64 (sous la limite)
        p = self.plan("LONG", 64114.59, 63700.0, 63803.64, 64200.0)
        self.assertTrue(p["available"], p.get("reason"))

    def test_bord_vraiment_trop_pres_du_stop_reste_refuse(self):
        p = self.plan("LONG", 64114.59, 63700.0, 63780.0, 64200.0)
        self.assertFalse(p["available"])
        self.assertIn("géométrie", p["reason"])


class RetoursALaLigne(unittest.TestCase):
    def test_aucun_antislash_n_litteral_dans_le_code_des_messages(self):
        import io, tokenize
        src = open(ab.__file__, encoding="utf-8").read()
        mauvais = []
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.STRING or tok.type == getattr(tokenize, "FSTRING_MIDDLE", -1):
                if "\\\\n" in tok.string and not tok.string.lstrip("bfuBFU").startswith(("r'", 'r"', "R'", 'R"')):
                    mauvais.append(tok.start[0])
        self.assertEqual(mauvais, [], f"« \\\\n » affiché tel quel aux lignes {mauvais}")


if __name__ == "__main__":
    unittest.main()
