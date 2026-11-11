"""Message SÉCURITÉ VIP (bouton payant, une seule fois) et page publique ALIGN LIVE (niveau gratuit, jamais de donnée VIP)."""
import base64
import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

import align_bot as ab

RACINE = Path(__file__).resolve().parent.parent
LIEN = "https://t.me/+PaidSubscriptionLink"


class SecuriteVip(unittest.TestCase):
    def _etat(self, **kw):
        return dict({"proprio": ["1", "2"], "lien": LIEN, "lien_primaire_revoque_v1": 1.0}, **kw)

    def test_message_has_paid_button_and_real_price_once_per_user(self):
        etat, envois = self._etat(), []
        with patch.object(ab, "_envoi_sur", side_effect=lambda c, **k: envois.append((c, k)) or {"ok": True}):
            ab.notifier_securite_vip(etat); ab.notifier_securite_vip(etat); ab.notifier_securite_vip(etat)
        self.assertEqual([c for c, _ in envois], ["1", "2"])                    # une fois par utilisateur, jamais en doublon
        for _, k in envois:
            bouton = json.loads(k["reply_markup"])["inline_keyboard"][0][0]
            self.assertEqual((bouton["text"], bouton["url"]), ("💎 Rejoindre le VIP", LIEN))
            self.assertIn(f"💎 Abonnement VIP : {ab.PRIX_STARS} ⭐ / mois", k["text"])
            self.assertIn("L'ancien lien gratuit de la chaîne VIP est révoqué", k["text"])

    def test_english_version_and_late_new_owner(self):
        etat, envois = self._etat(proprio=["1"]), []
        ab.LANG_EN.add("1")
        try:
            with patch.object(ab, "_envoi_sur", side_effect=lambda c, **k: envois.append((c, k)) or {"ok": True}):
                ab.notifier_securite_vip(etat)
                etat["proprio"].append("3")
                ab.notifier_securite_vip(etat)
        finally:
            ab.LANG_EN.discard("1")
        self.assertEqual([c for c, _ in envois], ["1", "3"])
        self.assertEqual(json.loads(envois[0][1]["reply_markup"])["inline_keyboard"][0][0]["text"], "💎 Join VIP")
        self.assertIn(f"VIP subscription: {ab.PRIX_STARS} ⭐ / month", envois[0][1]["text"])
        self.assertEqual(json.loads(envois[1][1]["reply_markup"])["inline_keyboard"][0][0]["text"], "💎 Rejoindre le VIP")

    def test_no_message_without_paid_link_then_sent_once_when_it_exists(self):
        etat, envois = self._etat(lien=""), []
        with patch.object(ab, "_envoi_sur", side_effect=lambda c, **k: envois.append(c) or {"ok": True}):
            ab.notifier_securite_vip(etat)
            self.assertEqual(envois, [])
            etat["lien"] = LIEN
            ab.notifier_securite_vip(etat); ab.notifier_securite_vip(etat)
        self.assertEqual(envois, ["1", "2"])

    def test_failed_send_is_retried_not_marked_as_seen(self):
        etat = self._etat(proprio=["1"])
        with patch.object(ab, "_envoi_sur", return_value=None):
            ab.notifier_securite_vip(etat)
        self.assertEqual(etat.get("secu_vip_vu"), [])

    def test_vip_link_is_the_paid_subscription_link_and_no_free_link_exists_in_code(self):
        src = (Path(ab.__file__)).read_text(encoding="utf-8")
        self.assertGreaterEqual(len(re.findall(r'telegram\("createChatSubscriptionInviteLink"', src)), 2)
        for m in re.finditer(r'telegram\("createChatSubscriptionInviteLink"[^)]*\)', src):
            self.assertIn("subscription_price=PRIX_STARS", m.group(0))
            self.assertIn("subscription_period=2592000", m.group(0))
        # aucun lien d'invitation simple vers la chaîne VIP : createChatInviteLink ne vise que la chaîne de validation des résultats
        for m in re.finditer(r'"createChatInviteLink"[^)]*\)', src):
            self.assertIn('etat["canal_preuves"]', m.group(0))
            self.assertNotIn('etat["canal"]', m.group(0))
        self.assertEqual(src.count('"exportChatInviteLink"'), 1)                # utilisé seulement pour RÉVOQUER l'ancien lien
        self.assertNotIn("sendMessage\", chat_id=cid, text=etat[\"lien_primaire", src)


class DonneesLive(unittest.TestCase):
    def _r(self, **kw):
        r = {"dirPlan": -1, "bull": 2, "bear": 6, "sens": -1, "pctH": 30, "strat": "DAY", "dirs": [-1] * 11, "dirW": 0, "atr": 2.0, "prix": 3983.52,
             "m1": [{"t": 1_800_000_000 - 20, "c": 3983.52}], "zone_pine": {"za": 3990.0, "zb": 4001.0, "zmil": 3995.0}}
        r.update(kw)
        return r

    def test_public_json_has_free_level_only(self):
        etat = {"GOLD": {"ordre": {"e": 4000, "sl": 4010, "tp1": 3950}}, "BTC": {}, "NASDAQ": {"trade": {"e": 1}}, "bot": "align_mtf_adel_bot"}
        derniers = {"GOLD": self._r(), "BTC": self._r(strat="", dirPlan=0, sens=0, bull=3, bear=4), "NASDAQ": self._r()}
        with patch.object(ab, "cme_ouvert", return_value=True):
            d = ab.construire_live(etat, derniers, 1_800_000_000)
        txt = json.dumps(d)
        self.assertEqual(set(d), {"v", "maj", "bot", "marches"})
        for m in d["marches"]:
            self.assertEqual(set(m), {"m", "etat", "biais", "ut", "seuil", "profil"})
        for interdit in ("3983", "3990", "4000", "4001", "4010", "3950", "sl", "tp", "entree_prix", "token", "ghp_", "prix"):
            self.assertNotIn(interdit, txt.replace('"entree"', ""))
        etats = {m["m"]: m["etat"] for m in d["marches"]}
        self.assertEqual(etats, {"GOLD": "preparation", "BTC": "calme", "NASDAQ": "entree"})
        with patch.object(ab, "cme_ouvert", return_value=False):
            ferme = {m["m"]: m["etat"] for m in ab.construire_live(etat, derniers, 1_800_000_000)["marches"]}
        self.assertEqual((ferme["GOLD"], ferme["NASDAQ"], ferme["BTC"]), ("ferme", "ferme", "calme"))

    def test_publication_throttled_unchanged_skipped_token_never_exposed(self):
        etat, appels = {}, []
        derniers = {"GOLD": self._r()}

        def faux_api(chemin, methode="GET", corps=None):
            appels.append((chemin, methode, corps))
            if methode == "GET" and "contents" in chemin:
                return {"sha": "abc"}
            return {}
        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghs_SECRETTOKEN123"}), patch.object(ab, "_api_github", side_effect=faux_api), \
             patch.object(ab, "cme_ouvert", return_value=True):
            self.assertTrue(ab.publier_live(etat, derniers, 1000))
            self.assertFalse(ab.publier_live(etat, derniers, 1060))               # < 2 min
            self.assertFalse(ab.publier_live(etat, derniers, 1130))               # inchangé et < 5 min : pas de commit
            self.assertTrue(ab.publier_live(etat, derniers, 1400))                # rafraîchissement forcé après 5 min
            self.assertTrue(ab.publier_live(etat, {"GOLD": self._r(bear=7)}, 1530))   # vraie évolution
        puts = [a for a in appels if a[1] == "PUT"]
        self.assertEqual(len(puts), 3)
        for chemin, _, corps in puts:
            self.assertIn("contents/live.json", chemin)
            self.assertEqual(corps["branch"], "live-data")
            self.assertNotIn("ghs_SECRETTOKEN123", json.dumps(corps))
            contenu = base64.b64decode(corps["content"]).decode()
            self.assertNotIn("ghs_", contenu); self.assertNotIn("3983", contenu)

    def test_publication_error_is_silent_for_token_and_backs_off(self):
        etat = {}
        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghs_SECRETTOKEN123"}), patch.object(ab, "_api_github", side_effect=RuntimeError("boom ghs_SECRETTOKEN123")), \
             patch.object(ab, "cme_ouvert", return_value=True), patch("builtins.print") as pr:
            self.assertFalse(ab.publier_live(etat, {"GOLD": self._r()}, 1000))
        self.assertNotIn("ghs_SECRETTOKEN123", " ".join(str(a) for c in pr.call_args_list for a in c.args))
        self.assertGreaterEqual(etat["live_t"], 1000 + 180)

    def test_no_token_means_no_call(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(ab, "_api_github") as api:
            self.assertFalse(ab.publier_live({}, {"GOLD": self._r()}, 1000))
        api.assert_not_called()


class PageLive(unittest.TestCase):
    PAGE = (RACINE / "docs" / "live" / "index.html").read_text(encoding="utf-8")

    def test_page_format_transparency_sources(self):
        self.assertIn("width: 1080px; height: 1920px", self.PAGE)
        self.assertIn("background: transparent", self.PAGE)
        self.assertIn("raw.githubusercontent.com/adelkhatra-bit/trading-auto/live-data/live.json", self.PAGE)
        self.assertIn("Thomas", self.PAGE); self.assertIn("Leïla", self.PAGE)
        self.assertIn("Pas un conseil financier", self.PAGE)
        self.assertIn("@align_mtf_adel_bot", self.PAGE)
        self.assertIn("Position en préparation sur", self.PAGE)

    def test_no_forbidden_words_or_promises(self):
        mots = re.findall(r"(?i)\b(like|likes|follow|followers?|cadeau|gagn\w*|garanti\w*|profit certain|abonne\w*)\b", self.PAGE)
        self.assertEqual(mots, [])

    def test_page_never_references_vip_levels_or_tokens(self):
        for interdit in ("token", "ghp_", "ghs_", "Authorization", "SL ", "TP1", "entrée à"):
            self.assertNotIn(interdit, self.PAGE)

    def test_enough_distinct_phrases_for_variety(self):
        dialogues = re.findall(r'\["([^"]+)", "([^"]+)"\]', self.PAGE)
        self.assertGreaterEqual(len({a for a, _ in dialogues}), 20)
        self.assertEqual(len({a for a, _ in dialogues}), len(dialogues))

    def test_bot_workflow_may_write_only_for_live_branch(self):
        wf = (RACINE / ".github" / "workflows" / "align-bot.yml").read_text(encoding="utf-8")
        self.assertIn("contents: write", wf)
        self.assertEqual(ab.LIVE_BRANCHE, "live-data")


if __name__ == "__main__":
    unittest.main()
