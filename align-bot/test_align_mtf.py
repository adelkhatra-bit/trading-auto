import json
import os
import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import align_bot
align_bot.TELEGRAM_HTML = False   # rendu texte testé ici ; le rendu HTML a son propre test


def candle(t, o=100.0, h=101.0, l=99.0, c=100.0):
    return {"t": t, "o": o, "h": h, "l": l, "c": c}


class AlignMtfRulesTest(unittest.TestCase):
    def test_4h_and_1h_confirm_without_15m(self):
        r = {"dirs": [0, 0, 0, 0, -1, 0, 0, 1, 0, 1, 0]}
        self.assertEqual(align_bot.alignement(r), (1, 2))

    def test_15m_opposition_does_not_block_4h_1h(self):
        r = {"dirs": [0, 0, 0, 0, -1, 0, 0, -1, 0, -1, 0]}
        self.assertEqual(align_bot.alignement(r), (-1, 2))

    def test_strategy_profile_selects_swing_when_h4_h1_m15_align(self):
        dirs = [0] * 11
        dirs[9], dirs[7], dirs[4], dirs[2] = 1, 1, 1, 1
        # Règle validée par Adel : sans D1 aligné ce n'est pas un swing mais du DAY TRADING
        self.assertEqual(align_bot.profil_strategie({"dirs": list(dirs)})["mode"], "DAY TRADING")
        dirs[10] = 1
        profile = align_bot.profil_strategie({"dirs": dirs})
        self.assertEqual(profile["mode"], "SWING")
        self.assertTrue(profile["m5_aligne"])
        self.assertFalse(profile["contre_tendance"])

    def test_strategy_profile_selects_intraday_during_m15_pullback(self):
        dirs = [0] * 11
        dirs[9], dirs[7], dirs[4], dirs[2] = 1, 1, -1, 1
        profile = align_bot.profil_strategie({"dirs": dirs})
        self.assertEqual(profile["mode"], "DAY TRADING")
        self.assertIn("retracement", profile["contexte"])
        self.assertTrue(profile["m5_aligne"])

    def test_strategy_profile_detects_countertrend_scalp_without_calling_it_swing(self):
        dirs = [0] * 11
        dirs[9], dirs[7], dirs[4], dirs[2] = -1, -1, 1, 1
        profile = align_bot.profil_strategie({"dirs": dirs})
        self.assertEqual(profile["mode"], "SCALPING CONTRE-TENDANCE")
        self.assertTrue(profile["contre_tendance"])
        self.assertIn("ne pas transformer", profile["horizon"])

    def test_strategy_profile_waits_when_no_timeframe_confluence_exists(self):
        profile = align_bot.profil_strategie({"dirs": [0] * 11})
        self.assertEqual(profile["mode"], "ATTENTE")
        self.assertEqual(profile["direction"], 0)

    def test_fetch_tv_mtf_preserves_the_server_selected_timeframe(self):
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return b'{"ok":true,"symbol":"XAUUSD","activeTimeframe":"M15","activeTimeframeFresh":true,"activeTimeframeAgeMs":1200,"snapshots":{"M5":{"fresh":true},"M15":{"fresh":true}},"receivedTimeframes":["M5","M15"]}'

        old_url, old_token = align_bot.ALIGN_TV_API_URL, align_bot.ALIGN_TV_READ_TOKEN
        align_bot.ALIGN_TV_API_URL, align_bot.ALIGN_TV_READ_TOKEN = "https://align.example", "test-token"
        try:
            with unittest.mock.patch("align_bot.urllib.request.urlopen", return_value=FakeResponse()):
                result = align_bot.fetch_tv_mtf("XAUUSD")
        finally:
            align_bot.ALIGN_TV_API_URL, align_bot.ALIGN_TV_READ_TOKEN = old_url, old_token
        self.assertTrue(result["available"])
        self.assertEqual(result["activeTimeframe"], "M15")
        self.assertEqual(result["activeTimeframeAgeMs"], 1200)
        self.assertEqual(result["receivedTimeframes"], ["M5", "M15"])

    def test_fetch_tv_mtf_rejects_stale_active_timeframe(self):
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return b'{"ok":true,"symbol":"XAUUSD","activeTimeframe":"H4","activeTimeframeFresh":false,"snapshots":{"H4":{"fresh":true}}}'

        old_url, old_token = align_bot.ALIGN_TV_API_URL, align_bot.ALIGN_TV_READ_TOKEN
        align_bot.ALIGN_TV_API_URL, align_bot.ALIGN_TV_READ_TOKEN = "https://align.example", "test-token"
        try:
            with unittest.mock.patch("align_bot.urllib.request.urlopen", return_value=FakeResponse()):
                result = align_bot.fetch_tv_mtf("XAUUSD")
        finally:
            align_bot.ALIGN_TV_API_URL, align_bot.ALIGN_TV_READ_TOKEN = old_url, old_token
        self.assertTrue(result["available"])
        self.assertIsNone(result["activeTimeframe"])

    def test_indicator_plan_follows_the_active_tradingview_timeframe(self):
        r = {"tv_indicator_mtf": {"available": True, "activeTimeframe": "M15", "snapshots": {
            "M5": {"fresh": True, "robotV12": {"signal": "SHORT", "entry": 100, "sl": 102, "tp": 96}},
            "M15": {"fresh": True, "confirmed": True, "robotV12": {"signal": "LONG", "entry": 101, "sl": 99, "tp": 105}},
            "H4": {"fresh": True, "robotV12": {"signal": "LONG", "entry": 98, "sl": 95, "tp": 104}}
        }}}
        plan = align_bot.plan_indicateur(r)
        self.assertTrue(plan["available"])
        self.assertEqual(plan["timeframe"], "M15")
        self.assertEqual((plan["entry"], plan["sl"], plan["tp"]), (101, 99, 105))
        self.assertTrue(plan["confirmed"])

    def test_indicator_plan_changes_when_active_timeframe_changes(self):
        r = {"tv_indicator_mtf": {"available": True, "activeTimeframe": "H4", "snapshots": {
            "M15": {"fresh": True, "robotV12": {"signal": "LONG", "entry": 101, "sl": 99, "tp": 105}},
            "H4": {"fresh": True, "robotV12": {"signal": "SHORT", "entry": 110, "sl": 112, "tp": 106}}
        }}}
        plan = align_bot.plan_indicateur(r)
        self.assertTrue(plan["available"])
        self.assertEqual(plan["timeframe"], "H4")
        self.assertEqual((plan["entry"], plan["sl"], plan["tp"]), (110, 112, 106))

    def test_indicator_plan_rejects_stale_or_missing_active_snapshot(self):
        stale = {"tv_indicator_mtf": {"available": True, "activeTimeframe": "M15", "snapshots": {
            "M15": {"fresh": False, "robotV12": {"signal": "LONG", "entry": 100, "sl": 98, "tp": 104}}
        }}}
        missing = {"tv_indicator_mtf": {"available": True, "activeTimeframe": "H1", "snapshots": {
            "M15": {"fresh": True, "robotV12": {"signal": "LONG", "entry": 100, "sl": 98, "tp": 104}}
        }}}
        self.assertFalse(align_bot.plan_indicateur(stale)["available"])
        self.assertFalse(align_bot.plan_indicateur(missing)["available"])

    def test_indicator_plan_rejects_incoherent_levels(self):
        r = {"tv_indicator_mtf": {"available": True, "activeTimeframe": "M5", "snapshots": {
            "M5": {"fresh": True, "robotV12": {"signal": "LONG", "entry": 100, "sl": 102, "tp": 104}}
        }}}
        self.assertFalse(align_bot.plan_indicateur(r)["available"])

    def test_tradingview_mtf_readings_merge_into_existing_align_context(self):
        r = {"dirs": [0] * 11, "rsis": [50.0] * 11, "tv_indicator_mtf": {
            "activeTimeframe": "M15", "snapshots": {"M15": {"fresh": True, "robotV12": {
                "lecture_1m": "LONG", "lecture_5m": "SHORT", "lecture_15m": "LONG",
                "lecture_60m": "LONG", "rsi_5m": 31.5, "rsi_15m": 62
            }}}
        }}
        align_bot.fusionne_lectures_tradingview(r)
        self.assertEqual([r["dirs"][i] for i in (0, 2, 4, 7)], [1, -1, 1, 1])
        self.assertEqual(r["rsis"][2], 31.5)
        self.assertEqual(r["rsis"][4], 62)

    def test_tradingview_links_select_market_and_requested_timeframe(self):
        btc = align_bot.url_tradingview("BTC", 5)
        gold = align_bot.url_tradingview("GOLD", 240)
        self.assertIn("KRAKEN%3AXBTUSD", btc)
        self.assertIn("interval=5", btc)
        self.assertIn("FOREXCOM%3AXAUUSD", gold)
        self.assertIn("interval=240", gold)

    def test_failed_telegram_analysis_delivery_is_not_marked_as_sent(self):
        state = {}
        market = "GOLD"
        analysis = {"m1": [candle(1, c=4050.0)], "dirs": [0] * 11, "rsis": [50.0] * 11,
                    "prix": 4050.0, "atr": 2.0, "confirme": 0}
        with unittest.mock.patch.object(align_bot, "signature_analyse", return_value="sig-test"), \
             unittest.mock.patch.object(align_bot, "armer_cloture"), \
             unittest.mock.patch.object(align_bot, "_envoi_sur", return_value=None):
            align_bot.envoyer_analyse_a(state, "chat-429", market, analysis, {})
        self.assertNotIn("chat-429", state.get("vu_analyse", {}).get(market, {}))

    def test_entry_stop_uses_m15_structure_not_the_trigger_m5_wick(self):
        r = {"b15": [candle(0, l=98.0, h=102.0), candle(900, l=97.5, h=102.5),
                      candle(1800, l=97.0, h=103.0)], "atr": 3.0}
        sl = align_bot.stop_structure_15m(r, 1, 100.0)
        self.assertAlmostEqual(sl, 96.25)
        self.assertLess(sl, min(x["l"] for x in r["b15"]))

    def test_entry_is_rejected_when_m15_structure_requires_too_wide_a_stop(self):
        r = {"b15": [candle(0, l=90.0), candle(900, l=89.0), candle(1800, l=88.0)], "atr": 2.0}
        self.assertIsNone(align_bot.stop_structure_15m(r, 1, 100.0))

    def test_short_entry_stop_is_above_m15_structure(self):
        r = {"b15": [candle(0, h=102.0), candle(900, h=102.5), candle(1800, h=103.0)], "atr": 3.0}
        sl = align_bot.stop_structure_15m(r, -1, 100.0)
        self.assertGreater(sl, max(x["h"] for x in r["b15"]))

    def test_gold_analysis_choice_callback_returns_only_gold_request(self):
        from unittest.mock import patch
        update = {"update_id": 99101, "callback_query": {
            "id": "gold-analysis", "data": "analysechoice:GOLD",
            "message": {"chat": {"id": 123, "type": "private"}}, "from": {"id": 123}
        }}
        with patch.object(align_bot, "telegram"), patch.object(align_bot, "autorise", return_value=True):
            self.assertEqual(align_bot.traiter({}, set(), [update]), [("123", "GOLD")])

    def test_both_analysis_choice_callback_returns_both_markets(self):
        from unittest.mock import patch
        update = {"update_id": 99102, "callback_query": {
            "id": "both-analysis", "data": "analysechoice:BOTH",
            "message": {"chat": {"id": 123, "type": "private"}}, "from": {"id": 123}
        }}
        with patch.object(align_bot, "telegram"), patch.object(align_bot, "autorise", return_value=True):
            self.assertEqual(align_bot.traiter({}, set(), [update]), [("123", "BTC"), ("123", "GOLD")])

    def test_breakout_uses_closed_5m_bars(self):
        bars = [candle(i) for i in range(21)]
        bars.append(candle(21, o=100.5, h=103.0, l=100.2, c=102.0))
        r = {
            "b5": bars, "atr5": 1.0, "atr": 1.0, "r5": [50.0],
            "m1": [candle(22, o=101.0, h=102.0, l=100.8, c=102.0)],
            "b15": [candle(0, l=101.5), candle(900, l=101.4), candle(1800, l=101.3)],
            "grosses": []
        }
        plan = align_bot.plan_cassure(r, 1)
        self.assertIsNotNone(plan)
        self.assertEqual(plan["src"], "cassure 5 min")
        self.assertEqual(plan["t15"], 21)

    def test_rejection_trigger_ignores_15m_candle(self):
        r = {
            "b5": [candle(10, o=100.0, h=100.5, l=99.8, c=100.1)],
            "b15": [candle(0, o=100.0, h=101.0, l=98.0, c=100.8)]
        }
        self.assertIsNone(align_bot.rejet(r, 1, 100.0, 1.0))

    def test_long_is_blocked_at_daily_weekly_extreme(self):
        r = {
            "posD": 0.95, "posW": 0.90,
            "basD": 90.0, "hautD": 110.0,
            "basW": 80.0, "hautW": 120.0
        }
        self.assertTrue(align_bot.bloque_dw(r, 1, 109.0))
        self.assertFalse(align_bot.bloque_dw(r, -1, 109.0))

    def test_15m_rsi_does_not_mark_entry_as_overextended(self):
        r = {
            "m1": [candle(1, c=100.0)], "atr5": 1.0, "ema5": 100.0,
            "r5": [50.0], "r15": 95.0, "ema15": 100.0, "atr": 1.0
        }
        self.assertFalse(align_bot.etire(r, 1))


    def test_market_selection_defaults_to_gold_and_allows_btc_or_both(self):
        self.assertEqual(align_bot.marche_demande("Analyse"), "GOLD")
        self.assertEqual(align_bot.marche_demande("Je veux prendre la prochaine position"), "GOLD")
        self.assertEqual(align_bot.marche_demande("Analyse Gold"), "GOLD")
        self.assertEqual(align_bot.marche_demande("Analyse BTC"), "BTC")
        self.assertIsNone(align_bot.marche_demande("Analyse BTC et Gold"))
        self.assertIsNone(align_bot.marche_demande("Analyse Bitcoin + XAUUSD"))

    def test_next_candle_close_is_strictly_in_the_future(self):
        self.assertEqual(align_bot.prochaine_cloture(601, 300), 900)
        self.assertEqual(align_bot.prochaine_cloture(899, 300), 900)
        self.assertEqual(align_bot.prochaine_cloture(900, 300), 1200)
        self.assertGreater(align_bot.prochaine_cloture(1000, 300), 1000)
        with self.assertRaises(ValueError):
            align_bot.prochaine_cloture(1000, 0)


    def test_countdown_uses_four_numeric_digits_mm_ss_for_telegram(self):
        self.assertEqual(align_bot.mmss(0), "00:00")
        self.assertEqual(align_bot.mmss(59), "00:59")
        self.assertEqual(align_bot.mmss(3599), "59:59")
        self.assertEqual(align_bot.mmss(3600), "60:00")
        self.assertEqual(align_bot.mmss(3617), "60:17")
        self.assertRegex(align_bot.mmss(3599), r"^\d{2}:\d{2}$")

    def test_next_close_uses_latest_closed_candle_timestamp(self):
        r = {"b5": [candle(300), candle(600)]}
        self.assertEqual(align_bot.prochaine_cloture_bougie(r, "5m", 899), 900)
        self.assertEqual(align_bot.prochaine_cloture_bougie(r, "5m", 900), 1200)
        self.assertEqual(align_bot.prochaine_cloture_bougie(r, "5m", 901), 1200)

    def test_chronometer_counts_down_the_timeframe_that_is_actually_blocking(self):
        from unittest.mock import patch
        dirs = [0] * 11
        dirs[9] = 1  # 4h haussière
        r = {
            "m1": [candle(7200, c=4031.42)],
            "dirs": dirs, "confirme": 0, "atr": 1.0,
            "b1h": [candle(3600)], "b4h": [candle(0)]
        }
        with patch.object(align_bot.time, "time", return_value=7200):
            message = align_bot.chrono_txt("GOLD", r, {}, 0)
        self.assertIn("DIRECTION : 4 h LONG — confirmation 1 h manquante", message)
        self.assertIn("⏳ PROCHAINE CLÔTURE 1h", message)
        self.assertIn("⏱ Temps restant : 60:00", message)
        self.assertNotIn("PROCHAINE CLÔTURE 5m", message)
        self.assertIn("J'attends une clôture 1 h", message)

    def test_h1_blocker_has_priority_over_a_stale_entry_order(self):
        from unittest.mock import patch
        dirs = [0] * 11
        dirs[9] = 1  # 4h haussière
        r = {
            "m1": [candle(7200, c=4031.42)],
            "dirs": dirs, "confirme": 0, "atr": 1.0,
            "b5": [candle(6900)], "b1h": [candle(3600)], "b4h": [candle(0)]
        }
        stale_order = {"d": 1, "e": 4030.0, "za": 4029.0, "zb": 4031.0, "sl": 4025.0}
        with patch.object(align_bot.time, "time", return_value=7200):
            message = align_bot.chrono_txt("GOLD", r, {"ordre": stale_order}, 0)
        self.assertIn("confirmation 1 h manquante", message)
        self.assertIn("PROCHAINE CLÔTURE 1h", message)
        self.assertNotIn("PROCHAINE CLÔTURE 5m", message)

    def test_neutral_4h_has_priority_over_a_stale_entry_order(self):
        dirs = [0] * 11
        dirs[7] = 1
        r = {"dirs": dirs, "confirme": 0}
        self.assertEqual(align_bot.timeframe_attendu(r, {"ordre": {"e": 100.0}}), "4h")

    def test_confirmed_bias_with_entry_order_waits_for_5m_trigger(self):
        dirs = [0] * 11
        dirs[7] = dirs[9] = 1
        r = {"dirs": dirs, "confirme": 1}
        self.assertEqual(align_bot.timeframe_attendu(r, {"ordre": {"e": 100.0}}), "5m")

    def test_neutral_market_is_explained_without_inventing_long_or_short(self):
        r = {"dirs": [0] * 11, "confirme": 0, "m1": [candle(1, c=100.0)]}
        reason = align_bot.raison_attente(r, {})
        self.assertIn("marché est neutre", reason)
        self.assertNotIn("LONG est confirmé", reason)
        self.assertNotIn("SHORT est confirmé", reason)


    def test_long_entry_zone_waits_for_pullback_from_above(self):
        from unittest.mock import patch
        dirs = [0] * 11
        dirs[7] = dirs[9] = 1
        r = {"dirs": dirs, "confirme": 1, "m1": [candle(1, c=102.0)]}
        order = {"d": 1, "e": 100.0, "za": 99.0, "zb": 101.0}
        with patch.object(align_bot, "etire", return_value=False), \
             patch.object(align_bot, "bloque_dw", return_value=False):
            reason = align_bot.raison_attente(r, {"ordre": order})
        self.assertIn("j'attends qu'il redescende", reason)
        self.assertNotIn("remonte dans cette zone", reason)

    def test_short_entry_zone_waits_for_rebound_from_below(self):
        from unittest.mock import patch
        dirs = [0] * 11
        dirs[7] = dirs[9] = -1
        r = {"dirs": dirs, "confirme": -1, "m1": [candle(1, c=98.0)]}
        order = {"d": -1, "e": 100.0, "za": 99.0, "zb": 101.0}
        with patch.object(align_bot, "etire", return_value=False), \
             patch.object(align_bot, "bloque_dw", return_value=False):
            reason = align_bot.raison_attente(r, {"ordre": order})
        self.assertIn("j'attends qu'il remonte", reason)
        self.assertNotIn("redescende dans cette zone", reason)

    def test_existing_auto_reservations_are_migrated_to_multi_timeframe_watch(self):
        from unittest.mock import patch
        state = {
            "auto": {"GOLD": ["123"]},
            "veille_cloture": {"GOLD": {"123": {"tf": "5m", "dernier_t": 300, "restants": 2}}}
        }
        r = {
            "b5": [candle(600)], "b15": [candle(900)],
            "b1h": [candle(3600)], "b4h": [candle(14400)]
        }
        with patch.object(align_bot.time, "time", return_value=100):
            align_bot.synchroniser_veille_auto(state, "GOLD", r)
        watcher = state["veille_cloture"]["GOLD"]["123"]
        self.assertTrue(watcher["multi"])
        self.assertEqual(watcher["derniers_t"], {"5m": 600, "15m": 900, "1h": 3600, "4h": 14400})
        self.assertEqual(watcher["expire"], 100 + align_bot.CHRONO_MAX + 300)
        self.assertTrue(watcher["h4_close_grace_v1"])

    def test_existing_multi_watcher_gets_h4_grace_once_without_repeated_extension(self):
        from unittest.mock import patch
        state = {"auto": {"GOLD": ["123"]}, "veille_cloture": {"GOLD": {"123": {
            "multi": True, "derniers_t": {"4h": 14400}, "expire": 10000
        }}}}
        r = {"b5": [], "b15": [], "b1h": [], "b4h": [candle(14400)]}
        with patch.object(align_bot.time, "time", return_value=100):
            align_bot.synchroniser_veille_auto(state, "GOLD", r)
        watcher = state["veille_cloture"]["GOLD"]["123"]
        self.assertEqual(watcher["expire"], 10300)
        self.assertTrue(watcher["h4_close_grace_v1"])
        with patch.object(align_bot.time, "time", return_value=200):
            align_bot.synchroniser_veille_auto(state, "GOLD", r)
        self.assertEqual(watcher["expire"], 10300)

    def test_multi_timeframe_watcher_only_notifies_the_blocking_timeframe(self):
        from unittest.mock import patch
        state = {"veille_cloture": {"GOLD": {"123": {
            "multi": True, "derniers_t": {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400},
            "expire": 999999
        }}}}
        r = {
            "b5": [candle(300), candle(600)],
            "b15": [candle(900), candle(1800)],
            "b1h": [candle(3600), candle(7200)],
            "b4h": [candle(14400), candle(28800)],
            "m1": [candle(28800)], "dirs": [0] * 11, "confirme": 0
        }
        with patch.object(align_bot.time, "time", return_value=100), \
             patch.object(align_bot, "texte_cloture", return_value="close-4h"), \
             patch.object(align_bot, "markup_analyse", return_value=None), \
             patch.object(align_bot, "_envoi_sur", return_value={"ok": True}) as send:
            align_bot.notifier_clotures(state, "GOLD", r, {})
            align_bot.notifier_clotures(state, "GOLD", r, {})
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.kwargs["text"], "close-4h")
        self.assertEqual(state["veille_cloture"]["GOLD"]["123"]["derniers_t"]["4h"], 28800)
        self.assertEqual(state["veille_cloture"]["GOLD"]["123"]["derniers_t"]["5m"], 300)
        self.assertEqual(state["veille_cloture"]["GOLD"]["123"]["derniers_t"]["15m"], 900)
        self.assertEqual(state["veille_cloture"]["GOLD"]["123"]["derniers_t"]["1h"], 3600)

    def test_multi_timeframe_watcher_retries_when_telegram_send_fails(self):
        from unittest.mock import patch
        state = {"veille_cloture": {"GOLD": {"123": {
            "multi": True, "derniers_t": {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400},
            "expire": 999999
        }}}}
        r = {"b4h": [candle(14400), candle(28800)], "m1": [candle(28800)],
             "dirs": [0] * 11, "confirme": 0}
        with patch.object(align_bot.time, "time", return_value=100), \
             patch.object(align_bot, "texte_cloture", return_value="close-4h"), \
             patch.object(align_bot, "markup_analyse", return_value=None), \
             patch.object(align_bot, "_envoi_sur", side_effect=[None, {"ok": True}]) as send:
            align_bot.notifier_clotures(state, "GOLD", r, {})
            self.assertEqual(state["veille_cloture"]["GOLD"]["123"]["derniers_t"]["4h"], 14400)
            align_bot.notifier_clotures(state, "GOLD", r, {})
        self.assertEqual(send.call_count, 2)
        self.assertEqual(state["veille_cloture"]["GOLD"]["123"]["derniers_t"]["4h"], 28800)

    def test_signup_message_does_not_invent_a_yellow_entry_zone(self):
        from unittest.mock import patch
        state = {"GOLD": {"aligne": 0}}
        r = {"dirs": [0] * 11, "confirme": 0, "m1": [candle(1, c=100.0)]}
        with patch.dict(align_bot.DERNIERS, {"GOLD": r}), \
             patch.object(align_bot, "_envoi_sur") as send, \
             patch.object(align_bot, "armer_clotures_multi"), \
             patch.object(align_bot, "lancer_chrono"):
            align_bot.inscrire_auto(state, "123", "GOLD")
        message = send.call_args.kwargs["text"]
        self.assertIn("NEUTRE", message)
        self.assertIn("Aucune zone d'entrée validée", message)
        self.assertIn("Aucun ordre n'est envoyé", message)
        self.assertNotIn("zone 🟨", message)

    def test_regrouping_accepts_only_a_fully_closed_bucket(self):
        bars = [candle(0), candle(60, o=100.0, h=103.0, l=98.0, c=102.0)]
        self.assertEqual(align_bot.regrouper(bars, 2, 60, now_ts=119), [])
        grouped = align_bot.regrouper(bars, 2, 60, now_ts=120)
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["t"], 0)
        self.assertEqual(grouped[0]["h"], 103.0)
        self.assertEqual(grouped[0]["l"], 98.0)
        self.assertEqual(grouped[0]["c"], 102.0)

    def test_regrouping_rejects_a_missing_source_candle(self):
        bars = [candle(0), candle(120)]
        self.assertEqual(align_bot.regrouper(bars, 2, 60, now_ts=180), [])

    def test_regrouping_rejects_duplicate_source_timestamps(self):
        bars = [candle(0), candle(0), candle(60)]
        self.assertEqual(align_bot.regrouper(bars, 2, 60, now_ts=120), [])

    def test_regrouping_rejects_misaligned_source_timestamps(self):
        bars = [candle(1), candle(61)]
        self.assertEqual(align_bot.regrouper(bars, 2, 60, now_ts=180), [])


    def test_trade_card_repeats_clear_long_levels_at_start_and_end(self):
        from unittest.mock import patch
        trade = {
            "d": 1, "e": 100.0, "sl": 98.0, "tp1": 104.0, "tp2": 108.0,
            "n1": "résistance 4h", "n2": "Daily", "rr": 2.0,
            "za": 99.5, "zb": 100.5, "src": "cassure 5 min"
        }
        with patch.object(align_bot, "meche_sl", return_value="sous la mèche"), \
             patch.object(align_bot, "vue", return_value="4h"), \
             patch.object(align_bot, "duree_txt", return_value=""):
            message = align_bot.fmt_trade("BTC", trade, 101.0)
        self.assertIn("🟩🟩🟩  LONG", message)
        self.assertIn("📌 PLAN D'EXÉCUTION — 🟩 LONG", message)
        self.assertIn("🟨 Entrée : 100", message)
        self.assertIn("🛑 Stop Loss : 98", message)
        self.assertIn("💰 TP1 : 104", message)
        self.assertIn("🏁 TP2 : 108", message)
        self.assertIn("📍 RÉCAPITULATIF — BTC", message)

    def test_trade_card_marks_short_in_red(self):
        from unittest.mock import patch
        trade = {
            "d": -1, "e": 100.0, "sl": 102.0, "tp1": 96.0, "tp2": 92.0,
            "n1": "support 4h", "n2": "Daily", "rr": 2.0,
            "za": 99.5, "zb": 100.5, "src": "cassure 5 min"
        }
        with patch.object(align_bot, "meche_sl", return_value="au-dessus de la mèche"), \
             patch.object(align_bot, "vue", return_value="4h"), \
             patch.object(align_bot, "duree_txt", return_value=""):
            message = align_bot.fmt_trade("GOLD", trade, 99.0)
        self.assertIn("🟥🟥🟥  SHORT", message)
        self.assertIn("📌 PLAN D'EXÉCUTION — 🟥 SHORT", message)
        self.assertIn("🛑 Stop Loss : 102", message)
        self.assertIn("🏁 TP2 : 92", message)

    def test_telegram_price_levels_render_value_before_explanation(self):
        message = align_bot.mise_en_forme(
            "PLAN\n💰 TP1 ≈ 4 075,50 (ancienne mèche haute — bougie 15 minutes)\n"
            "🛑 Stop Loss : 4 020,00 (sous la mèche basse — bougie 15 minutes)\n"
            "📌 Entrée : 4 050,00"
        )
        self.assertIn("💰 TP1 : 4075,50 (ancienne mèche haute — bougie 15 minutes)", message)
        self.assertIn("🛑 Stop Loss : 4020 (sous la mèche basse — bougie 15 minutes)", message)
        self.assertIn("📌 Entrée : 4050", message)

    def test_telegram_price_values_remove_all_thousands_grouping_spaces(self):
        message = align_bot.mise_en_forme("PLAN\n💰 TP1 : 12 345 678,90 (niveau majeur)")
        self.assertIn("💰 TP1 : 12345678,90 (niveau majeur)", message)


    def test_telegram_price_formatting_is_idempotent_after_card_layout(self):
        first = align_bot.mise_en_forme(
            "PLAN\n💰 TP1 ≈ 4 075,50 (ancienne mèche haute — bougie 15 minutes)"
        )
        second = align_bot.mise_en_forme(first)
        self.assertIn("💰 TP1 : 4075,50 (ancienne mèche haute — bougie 15 minutes)", second)
        self.assertNotIn("4 075", second)
        self.assertEqual(first, second)

    def test_telegram_standalone_price_line_is_compacted(self):
        message = align_bot.mise_en_forme(
            "💰 TP1\n4 075,50\nancienne mèche haute — bougie 15 minutes\n"
            "📌 Entrée\n4 000,00"
        )
        self.assertIn("4075,50", message)
        self.assertIn("4000", message)
        self.assertNotIn("4 075", message)
        self.assertNotIn("4 000", message)

    def test_price_helper_uses_french_decimal_without_thousands_separator(self):
        self.assertEqual(align_bot.px(4075.5), "4075,50")
        self.assertEqual(align_bot.px(4000), "4000")
        self.assertEqual(align_bot.mise_en_forme("TP1 : 4 000,00"), "TP1 : 4000")

    def test_repeated_analysis_keeps_ai_commentary_for_btc_and_gold(self):
        from unittest.mock import patch
        for market in ("BTC", "GOLD"):
            state = {"vu_analyse": {market: {"123": {"sig": "same", "t": align_bot.time.time() - 30}}}}
            r = {"m1": [candle(300, c=100.0)], "atr": 1.0, "dirs": [0] * 11}
            with (
                patch.object(align_bot, "signature_analyse", return_value="same"),
                patch.object(align_bot, "armer_cloture") as arm,
                patch.object(align_bot, "chrono_txt", return_value="⏳ Prochaine clôture"),
                patch.object(align_bot, "statut_txt", return_value="⏳ ATTENTE"),
                patch.object(align_bot, "avis_ia", return_value="🧠 AI opinion") as ai,
                patch.object(align_bot, "verdict", return_value=("🟡 PATIENCE", "attendre la clôture 1 h")),
                patch.object(align_bot, "profil_strategie", return_value={"mode": "SWING", "direction": -1}),
                patch.object(align_bot, "_envoi_sur") as send,
            ):
                align_bot.envoyer_analyse_a(state, "123", market, r, {})
            arm.assert_called_once()
            # Avis court avec voyants ; l'avis IA complet n'est envoyé que sur « En savoir plus ».
            ai.assert_not_called()
            # Un seul message : « RIEN N'A BOUGÉ » avec les voyants, pas de 2e carte en doublon.
            self.assertEqual(send.call_count, 1, market)
            texte = send.call_args.kwargs["text"]
            self.assertIn("RIEN N'A BOUGÉ", texte)
            self.assertIn("15m ➖", texte)

    def test_ai_commentary_uses_english_for_english_subscribers(self):
        from unittest.mock import patch
        state = {}
        r = {"macro_data": {"disponible": False}}
        with (
            patch.object(align_bot, "macro_confluence", return_value={"disponible": False}),
            patch.object(align_bot, "donnees_ia", return_value={"market": "GOLD"}),
            patch.object(align_bot, "ia", return_value="Gold is neutral; wait for a confirmed 4h close.") as call,
        ):
            message = align_bot.avis_ia(state, "GOLD", r, {}, anglais=True)
        self.assertIn("ALIGN AI opinion", message)
        self.assertIn("Gold is neutral", message)
        self.assertIn("English", call.call_args.args[1])

    def test_ai_response_cache_is_separated_by_subscriber_language(self):
        from unittest.mock import patch
        for english, expected in ((False, "_fr_"), (True, "_en_")):
            with (
                patch.object(align_bot, "macro_confluence", return_value={"disponible": False}),
                patch.object(align_bot, "donnees_ia", return_value={"market": "GOLD"}),
                patch.object(align_bot, "ia", return_value="A clear market view.") as call,
            ):
                align_bot.avis_ia({}, "GOLD", {}, {}, anglais=english)
            self.assertIn(expected, call.call_args.kwargs["cle_cache"])

    def test_english_analysis_inline_button_labels_are_translated_without_changing_callbacks(self):
        import json
        state = {"GOLD": {}}
        french = json.loads(align_bot.markup_analyse(state, "GOLD", {}))
        english = json.loads(align_bot.traduire_clavier(align_bot.markup_analyse(state, "GOLD", {})))
        fr_buttons = [b for row in french["inline_keyboard"] for b in row]
        en_buttons = [b for row in english["inline_keyboard"] for b in row]
        self.assertEqual([b.get("callback_data") for b in fr_buttons], [b.get("callback_data") for b in en_buttons])
        self.assertEqual([align_bot.TRAD.get(b["text"], b["text"]) for b in fr_buttons], [b["text"] for b in en_buttons])
        self.assertEqual([b["text"] for b in en_buttons], [
            "❓ Why this decision?", "🧠 Learn more", "🎯 Levels / prices",
            "⏱ All timeframes", "🗂 Message history", "🔔 Follow the next position"
        ])

    def test_all_static_telegram_inline_button_labels_have_english_translations(self):
        labels = [
            "🎯 Suivre la prochaine position", "❓ Pourquoi cette décision ?",
            "📊 Analyse complète", "🧠 En savoir plus", "🎯 Niveaux / prix", "⏱ Toutes les unités",
            "🗂 Historique des messages", "🟢 Je suis rentré",
            "🔔 Suivre la prochaine position", "📍 Ma position • SL / TP",
            "🗂 Historique", "🔔 Suivre le prochain setup",
            "✅ Publier", "❌ Refuser", "✅ Accepter", "👀 Voir son profil",
            "⬅️ Plus récents", "Plus anciens ➡️", "↩️ Retour à l'analyse",
            "🎯 Voir les niveaux", "ℹ️ Comprendre l'analyse",
        ]
        missing = [label for label in labels if label not in align_bot.TRAD]
        self.assertEqual(missing, [])

    def test_english_position_and_close_keyboard_labels_are_translated(self):
        import json
        for french_markup, expected in (
            (align_bot.markup_position("GOLD"), "📍 My position • SL / TP"),
            (align_bot.markup_cloture("GOLD"), "🔔 Follow the next setup"),
            (align_bot.bouton_rappel("GOLD"), "📌 Review analysis: GOLD"),
        ):
            english = json.loads(align_bot.traduire_clavier(french_markup))
            labels = [b["text"] for row in english["inline_keyboard"] for b in row]
            self.assertIn(expected, labels)

    def test_english_rules_translate_current_risk_line_and_main_keyboard_placeholder(self):
        rules = align_bot.traduire(align_bot.REGLES)
        self.assertIn("Suggested risk: 0.5 to 1%", rules)
        self.assertNotIn("0,5 à 1 %", rules)
        import json
        keyboard = json.loads(align_bot.traduire_clavier(align_bot.CLAVIER))
        self.assertEqual(keyboard["input_field_placeholder"], "Choose an ALIGN action")

    def test_english_and_french_main_keyboards_keep_identical_button_actions(self):
        import json
        french = json.loads(align_bot.CLAVIER)
        english = json.loads(align_bot.traduire_clavier(align_bot.CLAVIER))
        self.assertEqual([[align_bot.TRAD.get(b.get("text"), b.get("text")) for b in row] for row in french["keyboard"]],
                         [[b.get("text") for b in row] for row in english["keyboard"]])
        self.assertEqual(len(french["keyboard"]), len(english["keyboard"]))

    def test_english_and_french_analysis_buttons_keep_identical_callbacks(self):
        import json
        french = json.loads(align_bot.markup_analyse({}, "GOLD", {}))
        english = json.loads(align_bot.traduire_clavier(align_bot.markup_analyse({}, "GOLD", {})))
        self.assertEqual([[b.get("callback_data") or b.get("url") for b in row] for row in french["inline_keyboard"]],
                         [[b.get("callback_data") or b.get("url") for b in row] for row in english["inline_keyboard"]])
        self.assertTrue(all(b["text"] for row in english["inline_keyboard"] for b in row))

    def test_previous_analysis_button_is_market_specific(self):
        import json
        keyboard = json.loads(align_bot.bouton_rappel("GOLD"))["inline_keyboard"]
        callbacks = [button.get("callback_data") for row in keyboard for button in row if button.get("callback_data")]
        labels = [button["text"] for row in keyboard for button in row]
        self.assertIn("previous:GOLD", callbacks)
        self.assertIn("📌 Revoir l'analyse GOLD", labels)

    def test_requested_analysis_arms_the_next_relevant_closed_candle(self):
        state = {}
        r = {"confirme": 0, "dirs": [0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
             "b1h": [candle(3600)]}
        align_bot.armer_cloture(state, "123", "GOLD", r, {})
        self.assertEqual(state["veille_cloture"]["GOLD"]["123"]["tf"], "1h")
        self.assertEqual(state["veille_cloture"]["GOLD"]["123"]["dernier_t"], 3600)

    def test_closed_candle_notifier_sends_once_per_new_candle(self):
        from unittest.mock import patch
        state = {"veille_cloture": {"BTC": {"123": {"tf": "5m", "dernier_t": 300, "restants": 1}}}}
        r = {"b5": [candle(300), candle(600, o=100, h=103, l=99, c=102)],
             "confirme": 0, "dirs": [0] * 11, "rsis": [50] * 11}
        with patch.object(align_bot, "verdict", return_value=("ATTENDRE", "pas de confirmation")), \
             patch.object(align_bot, "alignement", return_value=(0, 0)), \
             patch.object(align_bot, "prochaine", return_value="Attendre"), \
             patch.object(align_bot, "_envoi_sur") as send:
            align_bot.notifier_clotures(state, "BTC", r, {})
            align_bot.notifier_clotures(state, "BTC", r, {})
        self.assertEqual(send.call_count, 1)
        self.assertTrue(send.call_args.kwargs["text"].startswith("🟠 BTC"))
        self.assertIn("🔴 PAS D'ENTRÉE — SIGNAL NON CONFIRMÉ", send.call_args.kwargs["text"])
        self.assertIn("PAS D'ENTRÉE", send.call_args.kwargs["text"])
        self.assertNotIn("123", state["veille_cloture"]["BTC"])

    def test_candle_alert_puts_clear_no_entry_verdict_before_market_details(self):
        from unittest.mock import patch
        r = {
            "m1": [candle(600, c=4031.11)],
            "dirs": [0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
            "rsis": [50] * 11,
            "confirme": 0,
            "b5": [candle(300, o=4029.73, h=4032, l=4028, c=4031.11)],
        }
        with patch.object(align_bot, "verdict", return_value=("🔴🔴 N'ENTRE PAS", "Le 1h ne confirme pas la tendance 4h")):
            with patch.object(align_bot, "raison_attente", return_value="La 1 h doit confirmer la 4 h"):
                with patch.object(align_bot, "prochaine", return_value="Pas encore de sens"):
                    msg = align_bot.texte_cloture("GOLD", "5m", candle(300, o=4029.73, h=4032, l=4028, c=4031.11), r, {})
        self.assertTrue(msg.startswith("🥇 GOLD"))
        self.assertLess(msg.index("🥇 GOLD"), msg.index("PAS D'ENTRÉE"))
        self.assertIn("5m clôturée", msg)
        self.assertIn("H4 LONG", msg)
        self.assertIn("H1 NEUTRE", msg)
        self.assertNotIn("POURQUOI", msg)
        self.assertNotIn("CE QUE TU DOIS FAIRE", msg)

    def test_upcoming_position_is_distinguished_from_open_trade(self):
        from unittest.mock import patch
        r = {"dirs": [1] * 11, "confirme": 1, "m1": [candle(7200, c=67500.0)]}
        ordre = {"d": 1, "e": 67510.0, "za": 67490.0, "zb": 67520.0, "sl": 67400.0}
        with (
            patch.object(align_bot, "verdict", return_value=("🔴🔴 N'ENTRE PAS", "Attendre le retour en zone")),
            patch.object(align_bot, "raison_attente", return_value="Le prix doit revenir en zone"),
            patch.object(align_bot, "prochaine", return_value="Prochaine entrée LONG sur repli"),
            patch.object(align_bot, "heure", return_value="03:00"),
            patch.object(align_bot, "alignement", return_value=(2, 2)),
            patch.object(align_bot, "meche_sl", return_value="sous la mèche"),
        ):
            msg = align_bot.texte_cloture("BTC", "5m", candle(7200), r, {"ordre": ordre})
        self.assertIn("🟡 Zone 67490–67520", msg)
        self.assertIn("Zone 67490–67520", msg)
        self.assertNotIn("POSITION EN COURS", msg)

    def test_candle_close_countdown_supports_every_watched_timeframe(self):
        for tf, interval in align_bot.TF_SECONDES.items():
            field = align_bot.TF_CHAMPS[tf]
            r = {field: [candle(1000)]}
            self.assertEqual(
                align_bot.prochaine_cloture_bougie(r, tf, 1000 + interval - 1),
                1000 + interval,
                tf,
            )
            self.assertEqual(
                align_bot.prochaine_cloture_bougie(r, tf, 1000 + interval),
                1000 + 2 * interval,
                tf,
            )

    def test_candle_close_countdown_uses_next_real_candle_boundary(self):
        from unittest.mock import patch
        r = {"b5": [candle(600)]}
        with patch.object(align_bot.time, "time", return_value=899.0):
            self.assertEqual(align_bot.prochaine_cloture_bougie(r, "5m"), 900)
        with patch.object(align_bot.time, "time", return_value=900.0):
            self.assertEqual(align_bot.prochaine_cloture_bougie(r, "5m"), 1200)

    def test_dxy_requires_a_real_one_hour_reference_window(self):
        now = 10_000
        self.assertIsNone(align_bot.variation_une_heure([(now - 240, 101.0), (now, 101.2)]))
        change = align_bot.variation_une_heure([(now - 3600, 100.0), (now, 100.5)])
        self.assertIsNotNone(change)
        self.assertAlmostEqual(change[0], 0.5)
        self.assertEqual(change[1], 60)

    def test_macro_confluence_detects_dollar_impulse_and_asset_divergence_without_forcing_entry(self):
        now = align_bot.time.time()
        etat = {"macro": {
            "dxy": [(now - 3600, 100.0), (now, 100.30)],
            "eurusd": [(now - 3600, 1.1000), (now, 1.0960)]
        }}
        bars = [{"c": 100.0} for _ in range(5)]
        bars[-1]["c"] = 101.0
        result = align_bot.macro_confluence(etat, "GOLD", {"b15": bars}, maintenant=now)
        self.assertIn("FORTE HAUSSE", result["dollar_direction"])
        self.assertIn("COHÉRENT", result["controle_dxy_eurusd"])
        self.assertIn("DIVERGENCE HAUSSIÈRE", result["divergence_actif_dollar"])
        self.assertIn("ne jamais inverser LONG/SHORT", result["regle"])

    def test_dxy_rejects_quotes_older_than_fifteen_minutes(self):
        now = align_bot.time.time()
        state = {"macro": {"dxy": [(now - 7200, 100.0), (now - 3600, 100.5)]}}
        self.assertIsNone(align_bot.dxy_info(state, maintenant=now))

    def test_eurusd_is_not_compared_when_its_quote_is_not_synchronized(self):
        now = align_bot.time.time()
        state = {"macro": {
            "dxy": [(now - 3600, 100.0), (now, 100.4)],
            "eurusd": [(now - 7200, 1.1000), (now - 3600, 1.0950)]
        }}
        bars = [{"c": 100.0} for _ in range(5)]
        result = align_bot.macro_confluence(state, "BTC", {"b15": bars}, maintenant=now)
        self.assertEqual(result["controle_dxy_eurusd"], "INDISPONIBLE")
        self.assertIsNone(result["eurusd_variation_1h_pct"])

    def test_eurusd_quote_older_than_fifteen_minutes_is_not_used(self):
        now = align_bot.time.time()
        state = {"macro": {
            "dxy": [(now - 3600, 100.0), (now, 100.4)],
            "eurusd": [(now - 5400, 1.1000), (now - 1200, 1.0950)]
        }}
        bars = [{"c": 100.0} for _ in range(5)]
        result = align_bot.macro_confluence(state, "BTC", {"b15": bars}, maintenant=now)
        self.assertEqual(result["controle_dxy_eurusd"], "INDISPONIBLE")
        self.assertIsNone(result["eurusd_variation_1h_pct"])

    def test_us10y_is_included_as_official_daily_data_for_ai_context(self):
        today = align_bot.datetime.datetime.now(align_bot.PARIS).date()
        yesterday = today - align_bot.datetime.timedelta(days=1)
        state = {"macro": {"us10": (4.25, 4.20, yesterday.strftime("%m/%d/%Y"))}}
        info = align_bot.us10_info(state)
        self.assertTrue(info["disponible"])
        self.assertEqual(info["rendement_pct"], 4.25)
        self.assertAlmostEqual(info["variation_points_base"], 5.0)
        self.assertIn("QUOTIDIENNE", info["frequence"])

    def test_us10y_rejects_stale_official_data_instead_of_calling_it_live(self):
        old = (align_bot.datetime.datetime.now(align_bot.PARIS).date() - align_bot.datetime.timedelta(days=8)).strftime("%m/%d/%Y")
        info = align_bot.us10_info({"macro": {"us10": (4.25, 4.20, old)}})
        self.assertFalse(info["disponible"])
        self.assertEqual(info["statut"], "US10Y TROP ANCIEN")

    def test_macro_confluence_fails_closed_when_eurusd_or_dxy_history_is_too_short(self):
        now = 10_000
        etat = {"macro": {"dxy": [(now - 240, 100.0), (now, 100.4)], "eurusd": []}}
        result = align_bot.macro_confluence(etat, "BTC", {"b15": [{"c": 100.0}] * 5})
        self.assertFalse(result["disponible"])
        self.assertEqual(result["statut"], "DONNÉES DXY INSUFFISANTES")

    def test_chronometer_keeps_remaining_duration_and_paris_close_time_on_separate_lines(self):
        from unittest.mock import patch
        dirs = [0] * 11
        dirs[9] = 1
        r = {
            "m1": [candle(7200, c=4031.42)],
            "dirs": dirs, "confirme": 0, "atr": 1.0,
            "b1h": [candle(3600)], "b4h": [candle(0)]
        }
        with patch.object(align_bot.time, "time", return_value=7200):
            message = align_bot.chrono_txt("GOLD", r, {}, 0)
        self.assertIn("⏳ PROCHAINE CLÔTURE 1h\n⏱ Temps restant : 60:00\n🕒 Heure prévue : 04:00 (heure de Paris)", message)
        formatted = align_bot.mise_en_forme(message)
        self.assertIn("⏱ Temps restant : 60:00", formatted)
        self.assertIn("🕒 Heure prévue : 04:00 (heure de Paris)", formatted)

    def test_independent_chronometer_tick_updates_every_market_with_cached_data(self):
        from unittest.mock import patch
        with patch.dict(align_bot.DERNIERS, {"BTC": {"m1": []}, "GOLD": {"m1": []}}, clear=True):
            with patch.object(align_bot, "maj_chronos") as update:
                align_bot.tick_chronos({"BTC": {}, "GOLD": {}})
        self.assertEqual([call.args[1] for call in update.call_args_list], ["BTC", "GOLD"])

    def test_chronometer_refreshes_every_thirty_seconds_without_spamming(self):
        from unittest.mock import patch
        state = {"chrono": {"GOLD": {"123": {"mid": 9, "t0": 1, "maj": 100.0}}}, "GOLD": {}}
        with patch.object(align_bot.time, "time", side_effect=[100.1, 129.9, 130.1]), \
             patch.object(align_bot, "chrono_txt", return_value="tick-105") as render, \
             patch.object(align_bot, "telegram") as send:
            align_bot.maj_chronos(state, "GOLD", {})
            align_bot.maj_chronos(state, "GOLD", {})
            align_bot.maj_chronos(state, "GOLD", {})
        self.assertEqual(send.call_count, 1)
        self.assertEqual(render.call_count, 1)
        self.assertEqual(send.call_args.kwargs["text"], "tick-105")
    def test_analysis_keyboard_exposes_only_the_next_position_follow_action(self):
        import json
        keyboard = json.loads(align_bot.markup_analyse({}, "GOLD", {}))["inline_keyboard"]
        labels = [button["text"] for row in keyboard for button in row]
        callbacks = [button.get("callback_data") for row in keyboard for button in row if button.get("callback_data")]
        self.assertTrue({"❓ Pourquoi cette décision ?", "🧠 En savoir plus", "🎯 Niveaux / prix",
                         "⏱ Toutes les unités", "🗂 Historique des messages",
                         "🔔 Suivre la prochaine position"}.issubset(set(labels)))
        self.assertTrue({"why:GOLD", "details:GOLD", "levels:GOLD", "timeframes:GOLD",
                         "history:GOLD", "auto:GOLD"}.issubset(set(callbacks)))

    def test_active_trade_keyboard_has_manual_entry_and_exit_controls(self):
        import json
        keyboard = json.loads(align_bot.markup_analyse({"GOLD": {"trade": {"e": 1}}}, "GOLD", {}))["inline_keyboard"]
        callbacks = [button.get("callback_data") for row in keyboard for button in row if button.get("callback_data")]
        self.assertTrue({"position:GOLD", "out:GOLD", "why:GOLD", "details:GOLD",
                         "levels:GOLD", "timeframes:GOLD", "history:GOLD"}.issubset(set(callbacks)))
        self.assertNotIn("in:GOLD", callbacks)
        self.assertNotIn("auto:GOLD", callbacks)

    def test_telegram_formatter_splits_compound_information(self):
        message = align_bot.mise_en_forme(
            "ALIGN • GOLD\n"
            "Tendance : haussière • Confirmation : 2/2\n"
            "FVG 15m : haussière | Basse 4 050,00 | Haute 4 060,00"
        )
        self.assertIn("Tendance : haussière", message)
        self.assertIn("Confirmation : 2/2", message)
        self.assertIn("Basse 4050", message)
        self.assertIn("Haute 4060", message)

    def test_telegram_analysis_layout_is_clear_for_btc_and_gold(self):
        from unittest.mock import patch
        r = {
            "dirs": [1, 1, 1, 1, 1, 1, 1, 1, 0, 1, -1],
            "rsis": [55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65],
            "m1": [candle(1, c=67500.0)],
            "confirme": 1, "posD": 0.55, "posW": 0.60,
            "news": "📰 Calendrier : aucun événement majeur imminent",
            "niv_cles": [(68000.0, "plus haut d'hier"), (66000.0, "plus bas d'hier")],
            "asie": (67800.0, 67000.0), "macro": [], "fvg": [],
            "atr": 100.0, "distrib": False, "accum": False,
            "b5": [candle(i) for i in range(22)]
        }
        with patch.object(align_bot, "zone_txt", side_effect=lambda x: "milieu"), \
             patch.object(align_bot, "strategie_mtf", return_value=["🏔 Tendance 4 h", "🔁 Confirmation 1 h"]), \
             patch.object(align_bot, "verdict", return_value=("🟢 SETUP VALIDÉ", "Attendre la clôture 5 min.")), \
             patch.object(align_bot, "ligne_cassure", return_value="🎯 Déclencheur : clôture 5 min"), \
             patch.object(align_bot, "prochaine", return_value="⏳ Prochaine entrée : attendre le signal"):
            for market in ("BTC", "GOLD"):
                message = align_bot.texte_etat(market, r, {})
                self.assertIn(f"ALIGN • {market}", message)
                self.assertIn("📊 INDICATEURS PAR UNITÉ DE TEMPS", message)
                self.assertIn("1m 🟢⬆️", message)
                self.assertIn("5m 🟢⬆️", message)
                self.assertIn("15m 🟢⬆️", message)
                self.assertIn("1h 🟢⬆️", message)
                self.assertIn("4h 🟢⬆️", message)
                self.assertIn("Daily 🔴⬇️", message)
                self.assertIn("1m 55", message)
                self.assertIn("5m 57", message)
                self.assertIn("Daily 65", message)
                self.assertNotIn("UNITÉ 1m\n", message)
                self.assertNotIn("RSI 1m\n", message)
                self.assertIn("🧭 CONFIRMATION DE TENDANCE", message)
                self.assertIn("ALIGNEMENT 1H + 4H\n2/2", message)
                self.assertIn("🧭 PLAN MULTI-TIMEFRAME", message)
                self.assertIn("🏔 Tendance 4 h", message)
                self.assertIn("🚦 DÉCISION ALIGN", message)
                self.assertIn("🎯 DIRECTION À SURVEILLER : 🟩 LONG", message)
                self.assertIn("⏳ Prochaine entrée : attendre le signal", message)
                self.assertIn("67500", message)
                self.assertIn("\n💹 Prix actuel", message)
                self.assertNotIn("\\n", message)
                self.assertIn("Plus haut d'hier", message) if "niv_cles" in r else None
                self.assertLess(len(message), 4096)
        self.assertEqual(align_bot.traduire("📊 INDICATEURS PAR UNITÉ DE TEMPS"), "📊 TIMEFRAME INDICATORS")
        self.assertEqual(align_bot.traduire("📈 RSI PAR UNITÉ DE TEMPS"), "📈 RSI BY TIMEFRAME")

    def test_multi_timeframe_strategy_uses_consistent_direction_colors(self):
        r = {"dirs": [1, 1, 1, 1, -1, 0, 0, -1, 0, 1, 0], "confirme": 0}
        message = "\\n".join(align_bot.strategie_mtf(r))
        self.assertIn("Tendance principale 4 h : 🟢⬆️", message)
        self.assertIn("Contexte Daily : 🟠➖", message)
        self.assertIn("Confirmation 1 h : 🔴⬇️", message)
        self.assertIn("Préparation 15 min : 🔴⬇️", message)
        self.assertIn("Timing 5 min : 🟢⬆️", message)
        self.assertIn("PROFIL RETENU : ATTENTE", message)

    def test_telegram_public_market_card_keeps_vip_restriction_clear(self):
        r = {"m1": [candle(1, c=67500.0)], "news": "📰 Calendrier économique"}
        message = align_bot.texte_etat("BTC", r, {}, vip=False)
        self.assertIn("ALIGN • BTC", message)
        self.assertIn("POINT DE MARCHÉ", message)
        self.assertIn("Direction et niveaux de trading réservés aux VIP", message)

    def test_news_announcement_warns_40_minutes_before_once(self):
        from unittest.mock import patch
        now = align_bot.datetime.datetime(2026, 11, 11, 12, 0, tzinfo=align_bot.PARIS).timestamp()
        event = {"t": int(now + 40 * 60), "titre": "Discours Fed", "prev": "?", "avant": "?"}
        state = {}
        with patch.object(align_bot, "calendrier", return_value=[event]), \
             patch.object(align_bot, "minutes_avant_fermeture_gold", return_value=100), \
             patch.object(align_bot, "horaires_gold", return_value=(now + 100 * 60, now + 200 * 60, now + 300 * 60)):
            first = align_bot.annonces_et_sessions(state, now, {})
            second = align_bot.annonces_et_sessions(state, now, {})
        alerts = [x for x in first + second if "NEWS USA DANS 40 MIN" in x]
        self.assertEqual(len(alerts), 1)
        self.assertIn("Discours Fed", alerts[0])
        self.assertIn("Vérifie ton SL", alerts[0])

    def test_post_news_reaction_includes_ai_commentary(self):
        from unittest.mock import patch
        now = align_bot.datetime.datetime(2026, 11, 11, 12, 10, tzinfo=align_bot.PARIS).timestamp()
        event_time = int(now - 7 * 60)
        event = {"t": event_time, "titre": "Discours Fed", "prev": "?", "avant": "?"}
        bars = [candle(event_time + 60, o=100.0, h=102.0, l=99.0, c=101.5)]
        with patch.object(align_bot, "calendrier", return_value=[event]), \
             patch.object(align_bot, "minutes_avant_fermeture_gold", return_value=100), \
             patch.object(align_bot, "horaires_gold", return_value=(now + 100 * 60, now + 200 * 60, now + 300 * 60)), \
             patch.object(align_bot, "ia", return_value="Le mouvement observé est haussier mais doit être confirmé en clôture.") as ai:
            messages = align_bot.annonces_et_sessions({}, now, {"GOLD": {"m1": bars}})
        reaction = next(x for x in messages if "RÉACTION À LA NEWS" in x)
        self.assertIn("L'analyse de l'IA ALIGN après l'annonce", reaction)
        self.assertIn("doit être confirmé en clôture", reaction)
        ai.assert_called_once()

    def test_gold_market_closure_warns_40_minutes_before(self):
        from unittest.mock import patch
        now = align_bot.datetime.datetime(2026, 11, 11, 12, 0, tzinfo=align_bot.PARIS).timestamp()
        with patch.object(align_bot, "calendrier", return_value=[]), \
             patch.object(align_bot, "minutes_avant_fermeture_gold", return_value=39.5), \
             patch.object(align_bot, "horaires_gold", return_value=(now + 39.5 * 60, now + 90 * 60, now + 150 * 60)):
            messages = align_bot.annonces_et_sessions({}, now, {})
        closure = [x for x in messages if "FERMETURE DU GOLD DANS 40 MIN" in x]
        self.assertEqual(len(closure), 1)


    def test_telegram_wrapper_formats_every_outgoing_message(self):
        import urllib.parse
        from unittest.mock import patch
        with patch.object(align_bot, "TOKEN", "test-token"), patch.object(align_bot, "http_json", return_value={"ok": True}) as request:
            align_bot.telegram("sendMessage", chat_id="123", text="PLAN\n💰 TP1 : 4 075,50")
        url = request.call_args.args[0]
        payload = urllib.parse.parse_qs(request.call_args.args[1].decode())
        self.assertIn("test-token", url)
        self.assertIn("💰 TP1 : 4075,50", payload["text"][0])

    def test_unknown_telegram_callback_never_becomes_manual_exit(self):
        from unittest.mock import patch
        update = {
            "update_id": 9001,
            "callback_query": {
                "id": "cb-unknown",
                "data": "unknown:GOLD",
                "message": {"chat": {"id": 123, "type": "private"}},
                "from": {"id": 123}
            }
        }
        with patch.object(align_bot, "telegram") as api, \
             patch.object(align_bot, "repondre") as reply:
            align_bot.traiter({}, set(), [update])
        reply.assert_not_called()
        api.assert_called_once()
        self.assertEqual(api.call_args.args[0], "answerCallbackQuery")
        self.assertEqual(api.call_args.kwargs["text"], "Action inconnue ou expirée")

    def test_unknown_market_auto_callback_is_rejected(self):
        from unittest.mock import patch
        update = {
            "update_id": 9002,
            "callback_query": {
                "id": "cb-auto-invalid",
                "data": "auto:UNKNOWN",
                "message": {"chat": {"id": 123, "type": "private"}},
                "from": {"id": 123}
            }
        }
        with patch.object(align_bot, "telegram"), \
             patch.object(align_bot, "inscrire_auto") as register:
            align_bot.traiter({}, set(), [update])
        register.assert_not_called()

    def test_explicit_in_and_out_callbacks_route_to_the_requested_market(self):
        from unittest.mock import patch
        for action, expected in (("in", True), ("out", False)):
            update = {
                "update_id": 9010 if expected else 9011,
                "callback_query": {
                    "id": "cb-" + action,
                    "data": action + ":GOLD",
                    "message": {"chat": {"id": 123, "type": "private"}},
                    "from": {"id": 123}
                }
            }
            with patch.object(align_bot, "autorise", return_value=True), \
                 patch.object(align_bot, "telegram"), \
                 patch.object(align_bot, "repondre") as reply:
                align_bot.traiter({}, set(), [update])
            reply.assert_called_once()
            self.assertEqual(reply.call_args.args[1:], ("123", expected, "GOLD"))

    def test_valid_auto_callback_registers_requested_market_in_one_tap(self):
        from unittest.mock import patch
        update = {
            "update_id": 9012,
            "callback_query": {
                "id": "cb-auto",
                "data": "auto:BTC",
                "message": {"chat": {"id": 123, "type": "private"}},
                "from": {"id": 123}
            }
        }
        with patch.object(align_bot, "autorise", return_value=True), \
             patch.object(align_bot, "telegram"), \
             patch.object(align_bot, "selectionner_marches_suivi") as select, \
             patch.object(align_bot, "menu_suivi") as menu, \
             patch.object(align_bot, "inscrire_auto") as register, \
             patch.object(align_bot, "_envoi_sur"):
            align_bot.traiter({}, set(), [update])
        select.assert_called_once_with(unittest.mock.ANY, "123", "BTC")
        register.assert_called_once_with(unittest.mock.ANY, "123", "BTC", notifier=False)
        menu.assert_not_called()

    def test_main_keyboards_show_gold_btc_and_markets_buttons(self):
        import json
        for keyboard, attendus in ((align_bot.CLAVIER, ("🥇 Analyse Gold", "🟠 Analyse BTC", "📡 Mes marchés", "📊 Faire une analyse")),
                                   (align_bot.CLAVIER_VISITEUR, ("🥇 Analyse Gold", "🟠 Analyse BTC", "📊 Faire une analyse", "💎 Devenir VIP"))):
            parsed = json.loads(keyboard)
            labels = [b["text"] for row in parsed["keyboard"] for b in row]
            for attendu in attendus:
                self.assertIn(attendu, labels)
            self.assertEqual(len(labels), len(set(labels)))   # aucun doublon


    def test_user_facing_ai_commentary_uses_internal_analysis_when_providers_fail(self):
        from unittest.mock import patch
        r = {
            "m1": [candle(1, c=100.0)],
            "dirs": [0] * 11,
            "rsis": [50] * 11,
            "posD": 0.5,
            "posW": 0.5,
            "confirme": 0,
            "b5": []
        }
        with patch.object(align_bot, "ia", return_value=""), \
             patch.object(align_bot, "strategie_mtf", return_value=["Tendance 4h", "Confirmation 1h"]), \
             patch.object(align_bot, "verdict", return_value=("ATTENDRE", "Pas de confirmation")):
            message = align_bot.avis_ia({}, "GOLD", r, {})
        self.assertIn("L'avis ALIGN (analyse interne)", message)
        self.assertIn("Tendance 4h", message)
        self.assertIn("ATTENDRE", message)
        self.assertNotIn("L'avis de l'IA ALIGN", message)

    def test_internal_ai_fallback_is_explicit_when_all_external_providers_fail(self):
        from unittest.mock import patch
        state = {}
        with patch.object(align_bot, "_appel_ia", side_effect=RuntimeError("provider offline")):
            answer = align_bot.ia(state, "Explique le contexte", {"market": "BTC"})
        self.assertEqual(answer, "")
        self.assertEqual(state["ia_dernier_fournisseur"], "INTERNAL_FALLBACK")
        self.assertEqual(state["ia_dernier_statut"], "ALL_EXTERNAL_PROVIDERS_FAILED")
        self.assertTrue(state.get("ia_err"))

    def test_openai_is_configured_as_primary_external_ai_provider(self):
        provider = align_bot.IA_FOURNISSEURS[0]
        self.assertEqual(provider[0], "OpenAI")
        self.assertEqual(provider[1], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(provider[2], "chat-latest")
        self.assertTrue(provider[4])

    def test_ai_data_includes_next_review_time_not_predicted_entry_time(self):
        from unittest.mock import patch
        r = {
            "m1": [candle(1, c=100.0)], "dirs": [0] * 11, "rsis": [50] * 11,
            "posD": 0.5, "posW": 0.5, "confirme": 0, "b5": [],
            "macro_data": {}, "tv_indicator_mtf": {}
        }
        with patch.object(align_bot, "verdict", return_value=("ATTENTE", "Pas de confirmation")), \
             patch.object(align_bot, "plan_indicateur", return_value={"available": False}), \
             patch.object(align_bot, "profil_strategie", return_value={"mode": "ATTENTE"}), \
             patch.object(align_bot, "timeframe_attendu", return_value="4h"), \
             patch.object(align_bot, "prochaine_cloture_bougie", return_value=18000):
            data = align_bot.donnees_ia("GOLD", r, {})
        self.assertEqual(data["prochaine_reevaluation"]["unite_bloquante"], "4h")
        self.assertIn("pas une prévision d'entrée", data["prochaine_reevaluation"]["signification"])

    def test_ai_context_calculates_distance_and_mechanical_approach_time_from_live_plan(self):
        from unittest.mock import patch
        r = {
            "m1": [candle(1, c=100.0)], "dirs": [0] * 11, "rsis": [50] * 11,
            "posD": 0.5, "posW": 0.5, "confirme": 0, "b5": [
                {"o": 100, "h": 101, "l": 99, "c": 100, "v": 100.0,
                 "volume_source": "Kraken BTC"} for _ in range(12)
            ], "b15": [], "b1h": [], "b4h": [], "atr": 2.0,
            "macro_data": {}, "tv_indicator_mtf": {}
        }
        plan = {"available": True, "entry": 104.0, "sl": 98.0, "tp": 112.0, "direction": 1}
        with patch.object(align_bot, "verdict", return_value=("ATTENTE", "Attendre le déclencheur")), \
             patch.object(align_bot, "plan_indicateur", return_value=plan), \
             patch.object(align_bot, "profil_strategie", return_value={"mode": "INTRADAY"}), \
             patch.object(align_bot, "timeframe_attendu", return_value="5m"), \
             patch.object(align_bot, "prochaine_cloture_bougie", return_value=18000):
            data = align_bot.donnees_ia("GOLD", r, {})
        self.assertEqual(data["distance_plan_entree"]["entree_visee"], 104.0)
        self.assertEqual(data["distance_plan_entree"]["distance_prix"], 4.0)
        self.assertEqual(data["estimation_approche_entree"]["minutes_indicatives"], 10)
        self.assertTrue(data["volume"]["M5"]["disponible"])
        self.assertEqual(data["volume"]["M5"]["provenance"], "Kraken BTC")
        self.assertFalse(data["volume"]["M15"]["disponible"])

    def test_details_button_returns_ai_briefing_and_keeps_raw_technical_details(self):
        import json
        from unittest.mock import patch
        update = {"update_id": 99500, "callback_query": {
            "id": "details-gold", "data": "details:GOLD",
            "message": {"chat": {"id": 101, "type": "private"}}, "from": {"id": 101}
        }}
        r = {"m1": [candle(1, c=100.0)], "dirs": [0] * 11, "confirme": 0, "b5": []}
        with patch.object(align_bot, "autorise", return_value=True), \
             patch.object(align_bot, "analyse_marche", return_value=r), \
             patch.object(align_bot, "avis_ia", return_value="BRIEFING IA GOLD") as ai, \
             patch.object(align_bot, "_envoi_sur") as send, \
             patch.object(align_bot, "telegram"):
            align_bot.traiter({}, set(), [update])
        self.assertEqual(ai.call_args.args[1], "GOLD")
        self.assertEqual(send.call_args.kwargs["text"], "BRIEFING IA GOLD")
        keyboard = json.loads(send.call_args.kwargs["reply_markup"])["inline_keyboard"]
        self.assertIn("rawdetails:GOLD", [b["callback_data"] for row in keyboard for b in row])

    def test_raw_technical_details_callback_is_routed_and_responds(self):
        from unittest.mock import patch
        update = {"update_id": 99501, "callback_query": {
            "id": "rawdetails-gold", "data": "rawdetails:GOLD",
            "message": {"chat": {"id": 101, "type": "private"}}, "from": {"id": 101}
        }}
        r = {"m1": [candle(1, c=100.0)], "dirs": [0] * 11, "confirme": 0, "b5": []}
        with patch.object(align_bot, "autorise", return_value=True), \
             patch.object(align_bot, "analyse_marche", return_value=r), \
             patch.object(align_bot, "texte_etat", return_value="DONNEES TECHNIQUES GOLD"), \
             patch.object(align_bot, "_envoi_sur") as send, \
             patch.object(align_bot, "telegram"):
            align_bot.traiter({}, set(), [update])
        self.assertEqual(send.call_args.kwargs["text"], "DONNEES TECHNIQUES GOLD")


    def test_external_ai_provider_name_stays_out_of_telegram_commentary(self):
        from unittest.mock import patch
        state = {"ia_dernier_fournisseur": "Gemini", "ia_dernier_modele": "gemini-flash-latest",
                 "ia_dernier_statut": "CONNECTED"}
        r = {"macro_data": {"disponible": False}}
        with patch.object(align_bot, "macro_confluence", return_value={"disponible": False}), \
             patch.object(align_bot, "donnees_ia", return_value={"market": "GOLD"}), \
             patch.object(align_bot, "ia", return_value="Gold is neutral; wait for a confirmed close."):
            message = align_bot.avis_ia(state, "GOLD", r, {})
        self.assertNotIn("Gemini", message)  # rien de technique dans Telegram
        self.assertNotIn("gemini-flash-latest", message)
        self.assertIn("Gold is neutral", message)

    def test_ai_daily_limit_is_explicitly_marked_as_internal_fallback(self):
        from unittest.mock import patch
        jour = align_bot.datetime.datetime.now(align_bot.PARIS).strftime("%Y-%m-%d")
        state = {"ia_jour": {jour: align_bot.IA_MAX_JOUR}}
        with patch.object(align_bot, "_appel_ia") as call:
            answer = align_bot.ia(state, "Explain", {"market": "GOLD"})
        self.assertEqual(answer, "")
        self.assertEqual(state["ia_dernier_fournisseur"], "INTERNAL_FALLBACK")
        self.assertEqual(state["ia_dernier_statut"], "DAILY_LIMIT_INTERNAL_FALLBACK")
        call.assert_not_called()



    def test_all_analysis_inline_buttons_route_without_silent_failure(self):
        from unittest.mock import patch
        r = {"m1": [candle(1, c=100.0)], "dirs": [0] * 11, "confirme": 0}
        for action in ("why", "details", "levels", "resume", "previous"):
            update = {"update_id": 9100, "callback_query": {
                "id": "cb-" + action, "data": action + ":GOLD",
                "message": {"chat": {"id": 123, "type": "private"}}, "from": {"id": 123}
            }}
            with (
                patch.object(align_bot, "autorise", return_value=True),
                patch.dict(align_bot.DERNIERS, {"GOLD": r}),
                patch.object(align_bot, "texte_apercu", return_value="analysis-card"),
                patch.object(align_bot, "texte_etat", return_value="analysis-details"),
                patch.object(align_bot, "texte_pourquoi", return_value="analysis-why"),
                patch.object(align_bot, "avis_ia", return_value="analysis-ai"),
                patch.object(align_bot, "_envoi_sur") as send,
                patch.object(align_bot, "telegram", return_value={"ok": True}),
            ):
                align_bot.traiter({}, set(), [update])
                self.assertTrue(send.called, action + " did not send a response")

    def test_bot_on_off_buttons_route_to_personal_bot_setting(self):
        from unittest.mock import patch
        for action, enabled in (("boton", True), ("botoff", False)):
            update = {"update_id": 9110, "callback_query": {
                "id": "cb-" + action, "data": action + ":x",
                "message": {"chat": {"id": 123, "type": "private"}}, "from": {"id": 123}
            }}
            with (
                patch.object(align_bot, "regler_bot") as toggle,
                patch.object(align_bot, "telegram"),
            ):
                align_bot.traiter({}, set(), [update])
            toggle.assert_called_once()
            args, _ = toggle.call_args
            self.assertEqual(args[1:], ("123", enabled))
            self.assertEqual(args[0]["offset"], 9111)

    def test_owner_admin_buttons_are_routed_to_their_handlers(self):
        from unittest.mock import patch
        cases = [
            ("jok:gold", "decider_entree"),
            ("jno:gold", "decider_entree"),
            ("pub:photo1", "valider_gain"),
            ("refus:photo1", "valider_gain"),
            ("tvoffre:456", None),
            ("tvok:456", None),
        ]
        for data, handler in cases:
            update = {"update_id": 9120, "callback_query": {
                "id": "cb-admin", "data": data,
                "message": {"chat": {"id": 123, "type": "private"}}, "from": {"id": 123}
            }}
            state = {"proprio": ["123"], "indic": {"456": {"tv": "trader456"}}}
            with (
                patch.object(align_bot, "telegram"),
                patch.object(align_bot, "_envoi_sur"),
                patch.object(align_bot, "decider_entree") as decision,
                patch.object(align_bot, "valider_gain") as gain,
            ):
                align_bot.traiter(state, set(), [update])
                if handler == "decider_entree":
                    decision.assert_called_once()
                elif handler == "valider_gain":
                    gain.assert_called_once()
                elif data.startswith("tvoffre"):
                    self.assertIn("456", state.get("indic_offert", []))
                else:
                    self.assertTrue(state["indic"]["456"]["ok"])

    def test_bottom_keyboard_actions_are_connected_to_handlers(self):
        from unittest.mock import patch
        cases = [
            ("🟠 Analyse BTC", "analysis"),
            ("🥇 Analyse Gold", "analysis"),
            ("🤖 Mon bot", "bot"),
            ("📈 Mes résultats", "results"),
            ("📸 Partager mon gain", "gain"),
            ("🧩 Indicateur TradingView", "indicator"),
            ("🌐 English", "language"),
            ("✅ Je suis rentré", "entry"),
            ("🚪 Je suis sorti", "exit"),
        ]
        for text, action in cases:
            state = {"proprio": ["123"]}
            message = {"update_id": 9140, "message": {
                "text": text, "chat": {"id": 123, "type": "private"},
                "from": {"id": 123, "first_name": "Test"}
            }}
            with (
                patch.object(align_bot, "autorise", return_value=True),
                patch.object(align_bot, "menu_bot") as bot,
                patch.object(align_bot, "texte_resultats", return_value="results-card"),
                patch.object(align_bot, "menu_indicateur") as indicator,
                patch.object(align_bot, "changer_langue") as language,
                patch.object(align_bot, "repondre") as reply,
                patch.object(align_bot, "_envoi_sur") as send,
            ):
                demandes = align_bot.traiter(state, set(), [message])
                if action == "analysis":
                    expected = "BTC" if "BTC" in text else "GOLD"
                    self.assertEqual(demandes, [("123", expected)])
                elif action == "bot":
                    bot.assert_called_once()
                elif action == "results":
                    self.assertTrue(send.called)
                    self.assertIn("results-card", send.call_args.kwargs["text"])
                elif action == "gain":
                    self.assertIn("123", state.get("attente_photo", {}))
                elif action == "indicator":
                    indicator.assert_called_once()
                elif action == "language":
                    language.assert_called_once()
                    self.assertTrue(language.call_args.args[2])
                elif action == "entry":
                    reply.assert_called_once_with(state, "123", True)
                elif action == "exit":
                    reply.assert_called_once_with(state, "123", False)

    def test_visitor_vip_button_returns_purchase_information(self):
        from unittest.mock import patch
        message = {"update_id": 9150, "message": {
            "text": "💎 Devenir VIP", "chat": {"id": 456, "type": "private"},
            "from": {"id": 456, "first_name": "Visitor"}
        }}
        with (
            patch.object(align_bot, "autorise", return_value=False),
            patch.object(align_bot, "refuser") as refuse,
        ):
            align_bot.traiter({}, set(), [message])
        refuse.assert_called_once()

    def test_owner_access_grant_and_revoke_buttons_are_idempotent(self):
        from unittest.mock import patch
        grant = {"update_id": 9160, "callback_query": {
            "id": "cb-grant", "data": "offrir:456",
            "message": {"chat": {"id": 123, "type": "private"}}, "from": {"id": 123}
        }}
        revoke = {"update_id": 9161, "callback_query": {
            "id": "cb-revoke", "data": "retirer:456",
            "message": {"chat": {"id": 123, "type": "private"}}, "from": {"id": 123}
        }}
        state = {"proprio": ["123"], "offerts": ["456"], "noms": {"456": "Member"}}
        chats = {"456"}
        with patch.object(align_bot, "telegram"), patch.object(align_bot, "_envoi_sur") as send:
            align_bot.traiter(state, chats, [grant])
            self.assertIn("possède déjà", send.call_args.kwargs["text"])
            align_bot.traiter(state, chats, [revoke])
        self.assertNotIn("456", state["offerts"])
        self.assertNotIn("456", chats)

    def test_resume_button_reports_missing_analysis_instead_of_silence(self):
        from unittest.mock import patch
        update = {"update_id": 9130, "callback_query": {
            "id": "cb-resume", "data": "resume:BTC",
            "message": {"chat": {"id": 123, "type": "private"}}, "from": {"id": 123}
        }}
        with (
            patch.object(align_bot, "autorise", return_value=True),
            patch.dict(align_bot.DERNIERS, {}, clear=True),
            patch.object(align_bot, "analyse_marche", side_effect=RuntimeError("offline")),
            patch.object(align_bot, "_envoi_sur") as send,
            patch.object(align_bot, "telegram"),
        ):
            align_bot.traiter({}, set(), [update])
        self.assertIn("n'est pas disponible", send.call_args.kwargs["text"])


    def test_confirmed_bias_without_execution_state_waits_for_15m(self):
        dirs = [0] * 11
        dirs[7] = dirs[9] = 1
        r = {"dirs": dirs, "confirme": 1}
        self.assertEqual(align_bot.timeframe_attendu(r, {}), "15m")

    def test_http_json_preserves_telegram_error_description(self):
        import io
        import urllib.error
        from unittest.mock import patch
        body = io.BytesIO(b'{"ok":false,"description":"Bad Request: message is not modified"}')
        error = urllib.error.HTTPError("https://api.telegram.org/test", 400, "Bad Request", {}, body)
        with patch.object(align_bot.urllib.request, "urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "message is not modified"):
                align_bot.http_json("https://api.telegram.org/test")

    def test_chronometer_recreates_deleted_message_from_telegram_http_body(self):
        import io
        import json
        import urllib.error
        from unittest.mock import patch
        chrono = {"mid": 10, "t0": 1, "maj": 1}
        deleted = urllib.error.HTTPError(
            "https://api.telegram.org/test", 400, "Bad Request", {},
            io.BytesIO(b'{"ok":false,"description":"Bad Request: message to edit not found"}')
        )
        replacement = io.BytesIO(json.dumps({"ok": True, "result": {"message_id": 99}}).encode())
        with patch.object(align_bot, "TOKEN", "test-token"), \
             patch.object(align_bot.urllib.request, "urlopen", side_effect=[deleted, replacement]), \
             patch.object(align_bot.time, "time", return_value=100):
            ok = align_bot._editer_chrono_ou_recreer("123", chrono, "timer restored")
        self.assertTrue(ok)
        self.assertEqual(chrono["mid"], 99)
        self.assertEqual(chrono["maj"], 100)

    def test_chronometer_recreates_deleted_telegram_message(self):
        from unittest.mock import patch
        chrono = {"mid": 10, "t0": 1, "maj": 1}
        def telegram_side_effect(method, **kwargs):
            if method == "editMessageText":
                raise RuntimeError("Bad Request: message to edit not found")
            if method == "sendMessage":
                return {"ok": True, "result": {"message_id": 99}}
            raise AssertionError(method)
        with patch.object(align_bot, "telegram", side_effect=telegram_side_effect), \
             patch.object(align_bot.time, "time", return_value=100):
            ok = align_bot._editer_chrono_ou_recreer("123", chrono, "timer restored")
        self.assertTrue(ok)
        self.assertEqual(chrono["mid"], 99)
        self.assertEqual(chrono["maj"], 100)

    def test_chronometer_stops_for_blocked_telegram_chat(self):
        from unittest.mock import patch
        chrono = {"mid": 10, "t0": 1, "maj": 1}
        with patch.object(align_bot, "telegram", side_effect=RuntimeError("Forbidden: bot was blocked by the user")):
            ok = align_bot._editer_chrono_ou_recreer("123", chrono, "timer")
        self.assertFalse(ok)

    def test_timeout_chronometer_message_uses_real_line_breaks(self):
        from unittest.mock import patch
        state = {"chrono": {"GOLD": {"123": {"mid": 10, "t0": 1, "maj": 1}}}, "GOLD": {}}
        with patch.object(align_bot.time, "time", return_value=align_bot.CHRONO_MAX + 2), \
             patch.object(align_bot, "_editer_chrono_ou_recreer") as edit:
            align_bot.maj_chronos(state, "GOLD", {})
        text = edit.call_args.args[2]
        self.assertIn("\n", text)
        self.assertNotIn("\\n", text)

    def test_compact_analysis_puts_entry_permission_first_and_separates_bias(self):
        from unittest.mock import patch
        r = {"dirs": [0] * 11, "confirme": -1, "m1": [candle(1, c=73665.2)]}
        r["dirs"][7] = -1
        r["dirs"][9] = -1
        with patch.object(align_bot, "verdict", return_value=(
            "🔴🔴 N'ENTRE PAS",
            "Le prix est dans une zone Daily/Weekly extrême. Attendre un meilleur prix."
        )):
            message = align_bot.texte_apercu("BTC", r, {})
        self.assertLess(message.index("⛔ NE PAS ENTRER"), message.index("Biais à surveiller"))
        self.assertIn("Biais à surveiller : SHORT", message)
        self.assertIn("Le biais n'est pas une autorisation d'entrée", message)
        self.assertIn("Attendre un nouveau message explicite", message)
        self.assertNotIn("Prochaine entrée SHORT", message)

    def test_telegram_history_renders_incoming_and_outgoing_messages_for_one_chat(self):
        now = align_bot.time.time()
        state = {"journal_telegram": [
            {"direction": "entrant", "chat_id": "123", "timestamp": now, "text": "Analyse Gold"},
            {"direction": "sortant", "chat_id": "123", "timestamp": now, "text": "Attendre la clôture"},
            {"direction": "sortant", "chat_id": "456", "timestamp": now, "text": "Message privé autre chat"}
        ]}
        message = align_bot.texte_historique(state, "123")
        self.assertIn("📥 TOI", message)
        self.assertIn("📤 ALIGN", message)
        self.assertIn("Analyse Gold", message)
        self.assertIn("Attendre la clôture", message)
        self.assertNotIn("Message privé autre chat", message)
        self.assertGreaterEqual(message.count("\n"), 3)
        self.assertNotIn("\\n", message)

    def test_history_page_stays_under_telegram_message_limit(self):
        now = align_bot.time.time()
        state = {"journal_telegram": [
            {"direction": "sortant", "chat_id": "123", "timestamp": now, "text": "X" * 4096}
            for _ in range(8)
        ]}
        message = align_bot.texte_historique(state, "123")
        self.assertLess(len(message), 4096)
        self.assertEqual(message.count("📤 ALIGN"), 8)

    def test_telegram_history_coalesces_edits_of_the_same_live_timer(self):
        state = {}
        first = {"direction": "sortant", "chat_id": "123", "message_id": 88,
                 "type": "sendMessage", "text": "Chrono 00:10", "timestamp": 1}
        edit = {"direction": "sortant", "chat_id": "123", "message_id": 88,
                "type": "editMessageText", "text": "Chrono 00:05", "timestamp": 2}
        align_bot.journal_ajouter(state, first)
        align_bot.journal_ajouter(state, edit)
        self.assertEqual(len(state["journal_telegram"]), 1)
        self.assertEqual(state["journal_telegram"][0]["text"], "Chrono 00:05")
        self.assertEqual(state["journal_telegram"][0]["timestamp"], 2)

    def test_telegram_wrapper_records_successful_outgoing_messages(self):
        from unittest.mock import patch
        align_bot.JOURNAL_SORTANT.clear()
        with patch.object(align_bot, "TOKEN", "test-token"), patch.object(align_bot, "http_json", return_value={"ok": True, "result": {"message_id": 88}}):
            align_bot.telegram("sendMessage", chat_id="123", text="Message ALIGN")
        self.assertEqual(len(align_bot.JOURNAL_SORTANT), 1)
        self.assertEqual(align_bot.JOURNAL_SORTANT[0]["direction"], "sortant")
        self.assertEqual(align_bot.JOURNAL_SORTANT[0]["chat_id"], "123")
        self.assertEqual(align_bot.JOURNAL_SORTANT[0]["message_id"], 88)
        self.assertEqual(align_bot.JOURNAL_SORTANT[0]["text"], "Message ALIGN")
        align_bot.JOURNAL_SORTANT.clear()

    def test_history_callback_is_recorded_and_shows_only_the_requesting_chat(self):
        from unittest.mock import patch
        update = {"update_id": 9220, "callback_query": {
            "id": "cb-history", "data": "history:BTC",
            "message": {"chat": {"id": 123, "type": "private"}}, "from": {"id": 123}
        }}
        state = {"journal_telegram": [
            {"direction": "sortant", "chat_id": "123", "timestamp": align_bot.time.time(), "text": "Signal GOLD"},
            {"direction": "sortant", "chat_id": "999", "timestamp": align_bot.time.time(), "text": "Private other"}
        ]}
        with patch.object(align_bot, "telegram"), patch.object(align_bot, "_envoi_sur") as send:
            align_bot.traiter(state, set(), [update])
        self.assertEqual(state["journal_telegram"][-1]["direction"], "entrant")
        self.assertIn("HISTORIQUE ALIGN", send.call_args.kwargs["text"])
        self.assertIn("Signal GOLD", send.call_args.kwargs["text"])
        self.assertNotIn("Private other", send.call_args.kwargs["text"])

    def test_position_summary_uses_personal_stop_and_both_targets(self):
        r = {"m1": [candle(1, c=105.0)]}
        state = {"trade": {
            "d": 1, "e": 100.0, "sl": 95.0, "tp1": 110.0, "tp2": 120.0,
            "qui": {"123": {"e": 101.0, "sl": 96.0, "sl_conseil": 102.0, "tp1": 110.0}}
        }}
        message = align_bot.texte_position("BTC", r, state, "123")
        self.assertIn("Ton entrée : 101", message)
        self.assertIn("Ton SL actuel : 102", message)
        self.assertIn("TP1 : 110", message)
        self.assertIn("TP2 : 120", message)
        self.assertIn("STOP À BE", message)
        self.assertIn("ne passe aucun ordre", message)

    def test_telegram_journal_records_incoming_media_without_text(self):
        from unittest.mock import patch
        update = {"update_id": 9250, "message": {
            "chat": {"id": 123}, "from": {"id": 456},
            "photo": [{"file_id": "photo-id"}]
        }}
        state = {}
        with patch.object(align_bot, "telegram"):
            align_bot.traiter(state, set(), [update])
        event = state["journal_telegram"][-1]
        self.assertEqual(event["direction"], "entrant")
        self.assertEqual(event["chat_id"], "123")
        self.assertEqual(event["user_id"], "456")
        self.assertEqual(event["type"], "photo")
        self.assertEqual(event["text"], "[photo]")

    def test_history_callback_supports_older_and_newer_pages(self):
        import json
        from unittest.mock import patch
        now = align_bot.time.time()
        state = {"journal_telegram": [
            {"direction": "entrant", "chat_id": "123", "timestamp": now, "text": f"Message {i}"}
            for i in range(40)
        ]}
        update = {"update_id": 9240, "callback_query": {
            "id": "cb-history-page", "data": "history:BTC:8",
            "message": {"chat": {"id": 123, "type": "private"}}, "from": {"id": 123}
        }}
        with patch.object(align_bot, "telegram"), patch.object(align_bot, "_envoi_sur") as send:
            align_bot.traiter(state, set(), [update])
        self.assertIn("Messages 26 à 33 sur 41", send.call_args.kwargs["text"])
        buttons = json.loads(send.call_args.kwargs["reply_markup"])["inline_keyboard"]
        callbacks = [button.get("callback_data") for row in buttons for button in row if button.get("callback_data")]
        self.assertIn("history:BTC:0", callbacks)
        self.assertIn("history:BTC:16", callbacks)

    def test_personal_close_notification_attaches_results_and_history_buttons(self):
        from unittest.mock import patch
        state = {}
        pos = {"d": 1, "e": 100.0, "sl": 95.0, "tp1": 110.0, "fini": False}
        with patch.object(align_bot, "_envoi_sur") as send:
            align_bot.noter(state, "123", "BTC", pos, 110.0, "🎯 TP1 touché")
        self.assertIn("results:x", send.call_args.kwargs["reply_markup"])
        self.assertIn("history:BTC", send.call_args.kwargs["reply_markup"])

    def test_closed_trade_keyboard_links_to_results_history_and_next_setup(self):
        import json
        buttons = json.loads(align_bot.markup_cloture("BTC"))["inline_keyboard"]
        callbacks = [button.get("callback_data") for row in buttons for button in row if button.get("callback_data")]
        self.assertIn("results:x", callbacks)
        self.assertIn("history:BTC", callbacks)
        self.assertIn("auto:BTC", callbacks)

    def test_results_callback_returns_personal_results(self):
        from unittest.mock import patch
        update = {"update_id": 9230, "callback_query": {
            "id": "cb-results", "data": "results:x",
            "message": {"chat": {"id": 123, "type": "private"}}, "from": {"id": 123}
        }}
        with patch.object(align_bot, "telegram"), patch.object(align_bot, "_envoi_sur") as send:
            align_bot.traiter({}, set(), [update])
        self.assertIn("Mes résultats", send.call_args.kwargs["text"])

    def test_position_button_is_attached_to_following_alerts(self):
        import json
        buttons = json.loads(align_bot.markup_position("GOLD"))["inline_keyboard"]
        callbacks = [button.get("callback_data") for row in buttons for button in row if button.get("callback_data")]
        self.assertIn("position:GOLD", callbacks)
        self.assertIn("timeframes:GOLD", callbacks)
        self.assertIn("history:GOLD", callbacks)

    def test_all_timeframe_breakdown_lists_every_calculated_unit_and_strategy_role(self):
        r = {
            "dirs": [1, -1, 1, 0, -1, 1, 0, 1, -1, 1, 1],
            "rsis": [61, 45, 65, 50, 38, 54, 49, 63, 42, 68, 71],
        }
        message = align_bot.texte_timeframes("GOLD", r)
        for label in ("1 min", "3 min", "5 min", "10 min", "15 min", "30 min",
                      "45 min", "1 heure", "2 heures", "4 heures", "Daily"):
            self.assertIn(label, message)
        self.assertIn("4 h : tendance principale", message)
        self.assertIn("1 h : confirme ou contredit", message)
        self.assertIn("5 min : timing", message)
        self.assertIn("RSI 68", message)

    def test_all_timeframe_callback_remains_available_without_cluttering_default_analysis(self):
        import json
        from unittest.mock import patch
        keyboard = json.loads(align_bot.markup_analyse({}, "BTC", {}))["inline_keyboard"]
        callbacks = [button.get("callback_data") for row in keyboard for button in row if button.get("callback_data")]
        self.assertTrue({"why:BTC", "details:BTC", "levels:BTC", "timeframes:BTC",
                         "history:BTC", "auto:BTC"}.issubset(set(callbacks)))
        update = {"update_id": 9210, "callback_query": {
            "id": "cb-timeframes", "data": "timeframes:BTC",
            "message": {"chat": {"id": 123, "type": "private"}}, "from": {"id": 123}
        }}
        r = {"dirs": [1] * 11, "rsis": [55] * 11, "m1": [candle(1, c=100.0)], "confirme": 1}
        with (
            patch.object(align_bot, "autorise", return_value=True),
            patch.dict(align_bot.DERNIERS, {"BTC": r}),
            patch.object(align_bot, "_envoi_sur") as send,
            patch.object(align_bot, "telegram"),
        ):
            align_bot.traiter({}, set(), [update])
        self.assertIn("TOUTES LES UNITÉS", send.call_args.kwargs["text"])
        self.assertIn("45 min", send.call_args.kwargs["text"])

    def test_default_analysis_keyboard_is_compact_and_keeps_follow_action(self):
        import json
        keyboard = json.loads(align_bot.markup_analyse({}, "BTC", {}))["inline_keyboard"]
        callbacks = [button.get("callback_data") for row in keyboard for button in row if button.get("callback_data")]
        labels = [button["text"] for row in keyboard for button in row]
        self.assertTrue({"why:BTC", "details:BTC", "levels:BTC", "timeframes:BTC",
                         "history:BTC", "auto:BTC"}.issubset(set(callbacks)))
        self.assertIn("❓ Pourquoi cette décision ?", labels)
        self.assertIn("🧠 En savoir plus", labels)

    def test_why_callback_returns_short_explanation_and_more_detail_buttons(self):
        from unittest.mock import patch
        update = {"update_id": 9200, "callback_query": {
            "id": "cb-why", "data": "why:BTC",
            "message": {"chat": {"id": 123, "type": "private"}}, "from": {"id": 123}
        }}
        r = {"dirs": [0] * 11, "confirme": -1, "m1": [candle(1, c=73665.2)]}
        r["dirs"][7] = r["dirs"][9] = -1
        with (
            patch.object(align_bot, "autorise", return_value=True),
            patch.dict(align_bot.DERNIERS, {"BTC": r}),
            patch.object(align_bot, "verdict", return_value=("🔴🔴 N'ENTRE PAS", "Zone Daily/Weekly extrême.")),
            patch.object(align_bot, "_envoi_sur") as send,
            patch.object(align_bot, "telegram"),
        ):
            align_bot.traiter({}, set(), [update])
        self.assertIn("NE PAS ENTRER", send.call_args.kwargs["text"])
        self.assertIn("Direction à surveiller : SHORT", send.call_args.kwargs["text"])
        self.assertIn("Zone Daily/Weekly extrême", send.call_args.kwargs["text"])
        self.assertIn("details:BTC", send.call_args.kwargs["reply_markup"])

    def test_callback_from_group_is_rejected_before_any_action(self):
        from unittest.mock import patch
        update = {"update_id": 9901, "callback_query": {
            "id": "cb-group", "data": "in:BTC",
            "message": {"chat": {"id": -100123, "type": "supergroup"}},
            "from": {"id": 123}
        }}
        with patch.object(align_bot, "telegram") as api, patch.object(align_bot, "repondre") as reply:
            align_bot.traiter({}, set(), [update])
        reply.assert_not_called()
        api.assert_called_once()
        self.assertIn("conversation privée", api.call_args.kwargs["text"])

    def test_free_text_from_subscriber_is_ignored(self):
        from unittest.mock import patch
        update = {"update_id": 9902, "message": {
            "chat": {"id": 123, "type": "private"}, "from": {"id": 123},
            "text": "Bonjour, donne-moi une position"
        }}
        with patch.object(align_bot, "autorise", return_value=True), patch.object(align_bot, "_envoi_sur") as send:
            align_bot.traiter({}, {"123"}, [update])
        send.assert_not_called()

    def test_candle_close_notification_is_compact_and_puts_market_first(self):
        from unittest.mock import patch
        dirs = [0] * 11
        dirs[9] = 0
        dirs[7] = -1
        r = {"dirs": dirs, "confirme": 0, "m1": [candle(7200, c=4046.76)]}
        b = candle(7200, o=4050.53, h=4052.0, l=4044.0, c=4046.76)
        with patch.object(align_bot, "verdict", return_value=("🔴🔴 N'ENTRE PAS", "raison technique")), \
             patch.object(align_bot, "alignement", return_value=(0, 0)), \
             patch.object(align_bot, "heure", return_value="06:00"), \
             patch.object(align_bot, "profil_strategie", return_value={"mode":"ATTENTE","direction":0}):
            message = align_bot.texte_cloture("GOLD", "1h", b, r, {})
        lines = message.splitlines()
        self.assertTrue(lines[0].startswith("🥇 GOLD"))
        self.assertIn("4046,76", lines[0])
        self.assertEqual(lines[1], "🔴 PAS D'ENTRÉE — SIGNAL NON CONFIRMÉ")
        self.assertIn("1h clôturée 06:00", lines[2])
        self.assertIn("O 4050,53 → C 4046,76", lines[2])
        self.assertIn("H4 NEUTRE", lines[3])
        self.assertIn("H1 SHORT", lines[3])
        self.assertIn("ALIGN 0/2", lines[3])
        self.assertLess(len(message), 360)
        self.assertNotIn("POURQUOI", message)
        self.assertNotIn("RÉSULTAT DE LA BOUGIE", message)

    def test_compact_candle_alert_is_translated_for_english_users(self):
        from unittest.mock import patch
        r = {"dirs": [0] * 11, "confirme": 0, "m1": [candle(7200, c=100.0)]}
        b = candle(7200, o=99.0, h=101.0, l=98.0, c=100.0)
        with patch.object(align_bot, "verdict", return_value=("🔴🔴 N'ENTRE PAS", "Conditions insuffisantes")), \
             patch.object(align_bot, "alignement", return_value=(0, 0)), \
             patch.object(align_bot, "heure", return_value="03:00"), \
             patch.object(align_bot, "profil_strategie", return_value={"mode":"ATTENTE","direction":0}):
            translated = align_bot.traduire(align_bot.texte_cloture("BTC", "5m", b, r, {}))
        self.assertTrue(translated.startswith("🟠 BTC"))
        self.assertIn("🔴 NO ENTRY — SIGNAL NOT CONFIRMED", translated)
        self.assertIn("closed", translated)
        self.assertIn("UP", translated)
        self.assertIn("NEUTRAL", translated)
        self.assertIn("Next confirmation: candle close", translated)

    def test_candle_close_titles_support_all_watched_timeframes(self):
        from unittest.mock import patch
        r = {"dirs": [0] * 11, "confirme": 0, "m1": [candle(7200, c=100.0)]}
        b = candle(7200, o=99.0, h=101.0, l=98.0, c=100.0)
        with patch.object(align_bot, "verdict", return_value=("🔴🔴 N'ENTRE PAS", "Conditions insuffisantes")), \
             patch.object(align_bot, "alignement", return_value=(0, 0)), \
             patch.object(align_bot, "heure", return_value="03:00"), \
             patch.object(align_bot, "profil_strategie", return_value={"mode":"ATTENTE","direction":0}):
            for tf in ("5m", "15m", "1h", "4h", "D", "W"):
                message = align_bot.texte_cloture("BTC", tf, b, r, {})
                self.assertTrue(message.startswith("🟠 BTC"))
                self.assertIn(f"{tf} clôturée", message)
                self.assertIn("🔴 PAS D'ENTRÉE", message)

    def test_candle_close_title_confirms_only_when_entry_is_authorized(self):
        from unittest.mock import patch
        r = {"dirs": [0] * 11, "confirme": 1, "m1": [candle(7200, c=73498.30)]}
        b = candle(7200, o=73444.10, h=73510.0, l=73430.0, c=73498.30)
        with (
            patch.object(align_bot, "verdict", return_value=("🟢 TU PEUX ENTRER\\n⬆️ ACHAT", "Conditions réunies")),
            patch.object(align_bot, "raison_attente", return_value="Conditions réunies."),
            patch.object(align_bot, "prochaine", return_value="Entrée autorisée"),
            patch.object(align_bot, "heure", return_value="03:00"),
        ):
            message = align_bot.texte_cloture("BTC", "5m", b, r, {})
        self.assertTrue(message.startswith("🟠 BTC"))
        self.assertEqual(message.splitlines()[1], "🟢 SIGNAL VALIDÉ — VÉRIFIE LES NIVEAUX")
        self.assertNotIn("SIGNAL NON CONFIRMÉ", message)


class TelegramRateLimitTest(unittest.TestCase):
    def setUp(self):
        align_bot.TELEGRAM_RETRY_UNTIL.clear()

    def tearDown(self):
        align_bot.TELEGRAM_RETRY_UNTIL.clear()

    def test_429_retry_after_sets_a_chat_specific_cooldown(self):
        delay = align_bot._telegram_enregistre_429(
            "gold-chat", "HTTP Error 429: Too Many Requests: retry after 29359", maintenant=1000
        )
        self.assertEqual(delay, 29359)
        self.assertEqual(align_bot._telegram_cooldown_restant("gold-chat", maintenant=1001), 29358)
        self.assertEqual(align_bot._telegram_cooldown_restant("btc-chat", maintenant=1001), 0)

    def test_expired_cooldown_is_removed(self):
        align_bot.TELEGRAM_RETRY_UNTIL["gold-chat"] = 1100
        self.assertEqual(align_bot._telegram_cooldown_restant("gold-chat", maintenant=1101), 0)
        self.assertNotIn("gold-chat", align_bot.TELEGRAM_RETRY_UNTIL)

    def test_telegram_does_not_repeat_network_calls_during_retry_after(self):
        with unittest.mock.patch.object(
            align_bot, "http_json",
            side_effect=RuntimeError("HTTP Error 429: Too Many Requests: retry after 120")
        ) as request:
            with self.assertRaisesRegex(RuntimeError, "HTTP Error 429"):
                align_bot.telegram("sendMessage", chat_id="gold-chat", text="test")
            with self.assertRaisesRegex(RuntimeError, "cooldown actif"):
                align_bot.telegram("sendMessage", chat_id="gold-chat", text="test")
            self.assertEqual(request.call_count, 1)

    def test_telegram_cooldown_does_not_block_another_chat(self):
        align_bot.TELEGRAM_RETRY_UNTIL["gold-chat"] = __import__("time").time() + 2000
        with self.assertRaisesRegex(RuntimeError, "cooldown actif"):
            align_bot.telegram("sendMessage", chat_id="gold-chat", text="test")
        with unittest.mock.patch.object(
            align_bot, "http_json", return_value={"ok": True, "result": {"message_id": 7}}
        ) as request:
            result = align_bot.telegram("sendMessage", chat_id="btc-chat", text="test")
        self.assertTrue(result["ok"])
        request.assert_called_once()


if __name__ == "__main__":
    unittest.main()


class TestPersistenceAndLiveRefresh(unittest.TestCase):
    def test_state_migration_preserves_open_trade_subscribers_and_telegram_offset(self):
        import json
        import tempfile
        from unittest.mock import patch
        old = {
            "schema_version": 1,
            "BTC": {"trade": {"e": 70000, "qui": {"123": {"e": 70010, "sl": 69900}}}},
            "chats": ["123"], "offset": 987, "offerts": ["456"],
            "journal_telegram": [{"chat_id": "123", "text": "ancienne instruction"}]
        }
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(old, f)
            with patch.object(align_bot, "ETAT_FICHIER", path):
                state = align_bot.charger_etat()
                self.assertEqual(state["schema_version"], align_bot.STATE_SCHEMA_VERSION)
                self.assertEqual(state["BTC"]["trade"]["qui"]["123"]["sl"], 69900)
                self.assertEqual(state["offset"], 987)
                self.assertEqual(state["offerts"], ["456"])
                self.assertEqual(state["journal_telegram"][0]["text"], "ancienne instruction")
                align_bot.sauver_etat(state, {"123"})
                restored = align_bot.charger_etat()
            self.assertEqual(restored["BTC"]["trade"]["qui"]["123"]["e"], 70010)
            self.assertEqual(restored["offset"], 987)
            self.assertFalse(os.path.exists(path + ".tmp"))

    def test_corrupt_state_fails_closed_instead_of_resetting_subscribers(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{broken")
            with patch.object(align_bot, "ETAT_FICHIER", path):
                with self.assertRaisesRegex(RuntimeError, "aucune donnée écrasée"):
                    align_bot.charger_etat()
            with open(path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "{broken")

    def test_telegram_journal_keeps_a_fair_per_chat_history(self):
        state = {}
        for i in range(align_bot.JOURNAL_PAR_CHAT + 7):
            align_bot.journal_ajouter(state, {
                "direction": "entrant", "chat_id": "123", "timestamp": i, "text": f"m{i}"
            })
        align_bot.journal_ajouter(state, {
            "direction": "entrant", "chat_id": "456", "timestamp": 999, "text": "autre abonné"
        })
        mine = [x for x in state["journal_telegram"] if x["chat_id"] == "123"]
        self.assertEqual(len(mine), align_bot.JOURNAL_PAR_CHAT)
        self.assertEqual(mine[0]["text"], "m7")
        self.assertIn("autre abonné", [x["text"] for x in state["journal_telegram"]])

    def test_live_price_sources_refresh_within_five_seconds(self):
        self.assertEqual(align_bot.TTL_KRAKEN[1], 5)
        self.assertEqual(align_bot.TTL_KRAKEN[5], 10)


class TestFrenchAndChicagoTimezones(unittest.TestCase):
    def test_cme_closed_hour_tracks_chicago_winter_offset(self):
        from datetime import datetime, timezone
        # 16:30 à Chicago en hiver = 22:30 UTC.
        ts = datetime(2026, 1, 12, 22, 30, tzinfo=timezone.utc).timestamp()
        self.assertFalse(align_bot.cme_ouvert(ts))

    def test_cme_closed_hour_tracks_chicago_summer_offset(self):
        from datetime import datetime, timezone
        # 16:30 à Chicago en été = 21:30 UTC (UTC-5, pas UTC-6).
        ts = datetime(2026, 7, 13, 21, 30, tzinfo=timezone.utc).timestamp()
        self.assertFalse(align_bot.cme_ouvert(ts))

    def test_cme_open_hour_tracks_chicago_summer_offset(self):
        from datetime import datetime, timezone
        # 15:30 à Chicago en été : encore ouvert avant la fenêtre de fermeture.
        ts = datetime(2026, 7, 13, 20, 30, tzinfo=timezone.utc).timestamp()
        self.assertTrue(align_bot.cme_ouvert(ts))

    def test_all_user_facing_clock_helpers_use_paris_zone(self):
        from datetime import datetime, timezone
        ts = datetime(2026, 1, 12, 12, 34, tzinfo=timezone.utc).timestamp()
        self.assertEqual(align_bot.heure(ts), "13:34")
        self.assertEqual(align_bot.PARIS.key, "Europe/Paris")



class AlignTelegramMarketPreferencesTest(unittest.TestCase):
    def test_existing_subscribers_default_to_both_markets(self):
        state = {}
        self.assertEqual(align_bot.marche_selection(state, "101"), "BOTH")
        self.assertTrue(align_bot.marche_autorise(state, "101", "BTC"))
        self.assertTrue(align_bot.marche_autorise(state, "101", "GOLD"))

    def test_market_preference_is_isolated_per_subscriber(self):
        state = {"marches_par_chat": {"101": "BTC", "202": "GOLD"}}
        self.assertTrue(align_bot.marche_autorise(state, "101", "BTC"))
        self.assertFalse(align_bot.marche_autorise(state, "101", "GOLD"))
        self.assertFalse(align_bot.marche_autorise(state, "202", "BTC"))
        self.assertTrue(align_bot.marche_autorise(state, "202", "GOLD"))

    def test_market_message_routing_keeps_btc_and_gold_separate(self):
        state = {"marches_par_chat": {"101": "BTC", "202": "GOLD", "303": "BOTH"}, "canal": "-1000"}
        chats = {"101", "202", "303"}
        btc = align_bot.destinataires_message(state, chats, "🟠 BTC — SIGNAL EN ATTENTE\\nPrix 70000")
        gold = align_bot.destinataires_message(state, chats, "🥇 GOLD — SIGNAL CONFIRMÉ\\nPrix 4000")
        # Le flux VIP complet part uniquement dans la chaîne VIP (plus de doublon en privé)
        self.assertEqual(btc, ["-1000"])
        self.assertEqual(gold, ["-1000"])
        state.pop("canal")
        self.assertEqual(set(align_bot.destinataires_message(state, chats, "🟠 BTC — SIGNAL EN ATTENTE\\nPrix 70000")), {"101", "303"})

    def test_html_design_bold_title_separators_and_monospace_units(self):
        html = align_bot.rendu_html("😎 GOLD <test> & co\n⚡ Petites unités : 1m ⬇️ 15m ⬆️\nPOURQUOI J'ATTENDS\nℹ️ note")
        self.assertTrue(html.startswith("<b>😎 GOLD &lt;test&gt; &amp; co</b>\n" + align_bot.SEPARATEUR))
        self.assertIn("<code>1m</code> ⬇️ <code>15m</code> ⬆️", html)
        self.assertIn(align_bot.SEPARATEUR + "\n<b>POURQUOI J'ATTENDS</b>", html)
        self.assertIn("<i>ℹ️ note</i>", html)

    def test_free_flow_one_proposed_position_then_masked(self):
        from unittest.mock import patch
        state = {"prospects": ["7"], "proprio": ["1"], "proprio_gratuit": True, "lien": "https://t.me/+x", "GOLD": {"trade": {"cree": 5, "qui": {}}}}
        entree = "🥇 GOLD — J'ENTRE MAINTENANT\nEntrée 3990.50"
        with patch.object(align_bot, "telegram") as tg:
            align_bot.envoyer_prospects(state, "📰 NEWS USA DANS 1 H", False)
            self.assertEqual(tg.call_count, 0)          # plus de news côté gratuit
            align_bot.envoyer_prospects(state, entree, True)
            textes = {c.kwargs["chat_id"]: c.kwargs["text"] for c in tg.call_args_list}
            self.assertIn("POSITION GRATUITE DU JOUR", textes["7"])
            self.assertIn("POSITION GRATUITE DU JOUR", textes["1"])   # le propriétaire voit le gratuit
            tg.reset_mock()
            state["GOLD"]["trade"]["cree"] = 6
            align_bot.envoyer_prospects(state, entree, True)
            self.assertIn("🔒", tg.call_args_list[0].kwargs["text"])
            self.assertNotIn("3990", tg.call_args_list[0].kwargs["text"])
            tg.reset_mock()
            align_bot.envoyer_prospects(state, entree, True)
            self.assertEqual(tg.call_count, 0)          # pas deux fois le même avis

    def test_free_bot_off_gets_only_masked_and_respects_market(self):
        from unittest.mock import patch
        state = {"prospects": ["7", "8"], "bot_off": ["7"], "marches_par_chat": {"8": "BTC"}, "GOLD": {"trade": {"cree": 5}}}
        with patch.object(align_bot, "telegram") as tg, patch.object(align_bot, "PROPRIO_VUE_GRATUITE", False):
            align_bot.envoyer_prospects(state, "🥇 GOLD — J'ENTRE MAINTENANT\nEntrée 3990.50", True)
        self.assertEqual([c.kwargs["chat_id"] for c in tg.call_args_list], ["7"])
        self.assertIn("OFF", tg.call_args_list[0].kwargs["text"])

    def test_share_reminder_once_per_planned_day(self):
        import datetime
        state = {}
        jour = datetime.datetime(2026, 11, 12, align_bot.PARTAGE_HEURE, 5, tzinfo=align_bot.PARIS)
        while jour.date().toordinal() % align_bot.PARTAGE_JOURS:
            jour += datetime.timedelta(days=1)
        self.assertTrue(align_bot.partage_du(state, jour))
        self.assertFalse(align_bot.partage_du(state, jour + datetime.timedelta(minutes=5)))

    def test_mixed_market_macro_alert_requires_both_selection(self):
        state = {"marches_par_chat": {"101": "BTC", "202": "GOLD", "303": "BOTH"}}
        recipients = align_bot.destinataires_message(
            state, {"101", "202", "303"},
            "💵 DOLLAR EN FORTE HAUSSE\\n🥇 GOLD : prudence\\n🟠 BTC : prudence"
        )
        self.assertEqual(set(recipients), {"303"})

    def test_market_selection_menu_exposes_three_real_callbacks(self):
        from unittest.mock import patch
        with patch.object(align_bot, "_envoi_sur") as send:
            align_bot.menu_marches({}, "101")
        kwargs = send.call_args.kwargs
        keyboard = __import__("json").loads(kwargs["reply_markup"])
        callbacks = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
        self.assertEqual(callbacks, ["markets:BTC", "markets:GOLD", "markets:BOTH"])

    def test_market_selection_callback_persists_without_changing_other_users(self):
        from unittest.mock import patch
        state = {"marches_par_chat": {"202": "GOLD"}, "auto": {"BTC": ["101"]},
                 "veille_cloture": {"BTC": {"101": {"multi": True}}}}
        update = {"update_id": 1, "callback_query": {
            "id": "callback-1", "from": {"id": 101},
            "message": {"chat": {"id": 101, "type": "private"}},
            "data": "markets:GOLD"
        }}
        with patch.object(align_bot, "telegram", return_value={"ok": True}), \
             patch.object(align_bot, "_envoi_sur") as send:
            align_bot.traiter(state, {"101", "202"}, [update])
        self.assertEqual(align_bot.marche_selection(state, "101"), "GOLD")
        self.assertEqual(align_bot.marche_selection(state, "202"), "GOLD")
        self.assertNotIn("101", state["auto"]["BTC"])
        self.assertNotIn("101", state["veille_cloture"]["BTC"])
        self.assertIn("reply_markup", send.call_args.kwargs)


    def test_market_selection_menu_is_localized_for_english_users(self):
        from unittest.mock import patch
        old = set(align_bot.LANG_EN)
        try:
            align_bot.LANG_EN.add("101")
            with patch.object(align_bot, "_envoi_sur") as send:
                align_bot.menu_marches({}, "101")
            kwargs = send.call_args.kwargs
            self.assertIn("CHOOSE THE MARKETS", kwargs["text"])
            keyboard = __import__("json").loads(kwargs["reply_markup"])
            labels = [button["text"] for row in keyboard["inline_keyboard"] for button in row]
            self.assertIn("BTC only", labels[0])
            self.assertIn("GOLD only", labels[1])
            self.assertEqual(len(labels), 3)
        finally:
            align_bot.LANG_EN.clear()
            align_bot.LANG_EN.update(old)


if __name__ == "__main__":
    unittest.main()


class TestTelegramCompactKeyboards(unittest.TestCase):
    def test_analysis_and_position_keyboards_do_not_add_unrequested_tradingview_links(self):
        import json
        for markup in (align_bot.markup_analyse({}, "BTC", {}), align_bot.markup_position("GOLD")):
            keyboard = json.loads(markup)["inline_keyboard"]
            labels = [button.get("text", "") for row in keyboard for button in row]
            urls = [button.get("url", "") for row in keyboard for button in row]
            self.assertFalse(any("TradingView" in label for label in labels))
            self.assertFalse(any("tradingview.com" in url for url in urls))
        analysis = json.loads(align_bot.markup_analyse({}, "BTC", {}))["inline_keyboard"]
        callbacks = [button.get("callback_data") for row in analysis for button in row]
        self.assertTrue({"why:BTC", "details:BTC", "levels:BTC", "timeframes:BTC",
                         "history:BTC", "auto:BTC"}.issubset(set(callbacks)))


class TestTradingViewReportRegression(unittest.TestCase):
    def test_fresh_indicator_plan_renders_without_unbound_report_variable(self):
        from unittest.mock import patch
        r = {
            "dirs": [1] * 11, "rsis": [55.0] * 11,
            "m1": [candle(1, c=100.0)], "confirme": 1,
            "posD": 0.5, "posW": 0.5, "niv_cles": [], "asie": None,
            "macro": [], "fvg": [], "atr": 1.0, "distrib": False,
            "accum": False, "b5": [candle(i) for i in range(22)],
        }
        plan = {"available": True, "timeframe": "H4", "entry": 100.0,
                "sl": 98.0, "tp": 104.0, "confirmed": True}
        with patch.object(align_bot, "plan_indicateur", return_value=plan), \
             patch.object(align_bot, "zone_txt", return_value="milieu"), \
             patch.object(align_bot, "strategie_mtf", return_value=["Profil SWING", "Horizon : plusieurs séances"]), \
             patch.object(align_bot, "verdict", return_value=("ATTENTE", "Attendre la clôture.")), \
             patch.object(align_bot, "ligne_cassure", return_value="Déclencheur"), \
             patch.object(align_bot, "prochaine", return_value="Attendre"):
            message = align_bot.texte_etat("GOLD", r, {})
        self.assertIn("Unité sélectionnée : H4", message)
        self.assertIn("Entrée indicateur", message)
        self.assertIn("Profil SWING", message)


    def test_analysis_command_maps_to_market_selection_prompt(self):
        self.assertEqual(align_bot.COMMANDES["/faire_analyse"], "📊 Faire une analyse")
        from unittest.mock import patch
        with patch.object(align_bot, "telegram") as api:
            align_bot.installer_menu({})
        import json
        commands = json.loads(api.call_args_list[0].kwargs["commands"])
        self.assertIn("faire_analyse", [x["command"] for x in commands])

    def test_installer_menu_refreshes_existing_version_four_users(self):
        from unittest.mock import patch
        state = {"menu": 4}
        with patch.object(align_bot, "telegram") as api:
            align_bot.installer_menu(state)
        self.assertEqual(state["menu"], 7)
        self.assertTrue(any(call.args[0] == "setMyCommands" for call in api.call_args_list))

class TestOneTapMarketAnalysis(unittest.TestCase):
    def test_analysis_button_asks_market_and_gold_choice_returns_only_gold_request(self):
        from unittest.mock import patch
        update = {"update_id": 99601, "callback_query": {
            "id": "choose-gold", "data": "analysechoice:GOLD",
            "message": {"chat": {"id": 101, "type": "private"}}, "from": {"id": 101}
        }}
        with patch.object(align_bot, "telegram"), patch.object(align_bot, "autorise", return_value=True):
            demandes = align_bot.traiter({}, set(), [update])
        self.assertEqual(demandes, [("101", "GOLD")])

    def test_both_market_choice_returns_exactly_btc_and_gold(self):
        from unittest.mock import patch
        update = {"update_id": 99602, "callback_query": {
            "id": "choose-both", "data": "analysechoice:BOTH",
            "message": {"chat": {"id": 101, "type": "private"}}, "from": {"id": 101}
        }}
        with patch.object(align_bot, "telegram"), patch.object(align_bot, "autorise", return_value=True):
            demandes = align_bot.traiter({}, set(), [update])
        self.assertEqual(set(demandes), {("101", "BTC"), ("101", "GOLD")})

class TestFollowPositionMarketChoice(unittest.TestCase):
    def test_follow_button_opens_explicit_btc_gold_or_both_menu(self):
        import json
        from unittest.mock import patch
        for cid, expected in (("101", "CHOISIS LES MARCHÉS"), ("202", "CHOOSE THE MARKETS")):
            with patch.object(align_bot, "_envoi_sur") as send:
                if cid == "202":
                    old = set(align_bot.LANG_EN)
                    align_bot.LANG_EN.add(cid)
                    try:
                        align_bot.menu_suivi({}, cid)
                    finally:
                        align_bot.LANG_EN.clear()
                        align_bot.LANG_EN.update(old)
                else:
                    align_bot.menu_suivi({}, cid)
            args = send.call_args.kwargs
            self.assertIn(expected, args["text"])
            keyboard = json.loads(args["reply_markup"])["inline_keyboard"]
            callbacks = [button["callback_data"] for row in keyboard for button in row]
            self.assertEqual(callbacks, ["followmarket:BTC", "followmarket:GOLD", "followmarket:BOTH"])

    def test_followmarket_btc_registers_only_btc(self):
        from unittest.mock import patch
        update = {"update_id": 99001, "callback_query": {
            "id": "follow-btc", "data": "followmarket:BTC",
            "message": {"chat": {"id": 101, "type": "private"}}, "from": {"id": 101}
        }}
        with patch.object(align_bot, "autorise", return_value=True), \
             patch.object(align_bot, "inscrire_auto") as subscribe, \
             patch.object(align_bot, "_envoi_sur"), patch.object(align_bot, "telegram"):
            align_bot.traiter({}, set(), [update])
        subscribe.assert_called_once_with(unittest.mock.ANY, "101", "BTC", notifier=False)

    def test_followmarket_btc_registers_only_btc(self):
        from unittest.mock import patch
        state = {
            "auto": {"BTC": [], "GOLD": ["101"]},
            "veille_cloture": {"GOLD": {"101": {"multi": True}}},
            "marches_par_chat": {"101": "BOTH"}
        }
        update = {"update_id": 99001, "callback_query": {
            "id": "follow-btc", "data": "followmarket:BTC",
            "message": {"chat": {"id": 101, "type": "private"}}, "from": {"id": 101}
        }}
        with patch.object(align_bot, "autorise", return_value=True), \
             patch.object(align_bot, "inscrire_auto") as subscribe, \
             patch.object(align_bot, "_envoi_sur"), patch.object(align_bot, "telegram"):
            align_bot.traiter(state, set(), [update])
        subscribe.assert_called_once_with(unittest.mock.ANY, "101", "BTC", notifier=False)
        self.assertEqual(state["marches_par_chat"]["101"], "BTC")
        self.assertNotIn("101", state["auto"]["GOLD"])
        self.assertNotIn("101", state["veille_cloture"]["GOLD"])

    def test_followmarket_gold_sets_exclusive_preference_and_clears_stale_btc_watch(self):
        from unittest.mock import patch
        state = {
            "auto": {"BTC": ["101", "202"], "GOLD": []},
            "veille_cloture": {"BTC": {"101": {"multi": True}, "202": {"multi": True}}},
            "marches_par_chat": {"101": "BOTH"}
        }
        update = {"update_id": 99003, "callback_query": {
            "id": "follow-gold", "data": "followmarket:GOLD",
            "message": {"chat": {"id": 101, "type": "private"}}, "from": {"id": 101}
        }}
        with patch.object(align_bot, "autorise", return_value=True), \
             patch.object(align_bot, "inscrire_auto") as subscribe, \
             patch.object(align_bot, "_envoi_sur"), patch.object(align_bot, "telegram"):
            align_bot.traiter(state, set(), [update])
        subscribe.assert_called_once_with(unittest.mock.ANY, "101", "GOLD", notifier=False)
        self.assertEqual(state["marches_par_chat"]["101"], "GOLD")
        self.assertEqual(state["auto"]["BTC"], ["202"])
        self.assertNotIn("101", state["veille_cloture"]["BTC"])
        self.assertIn("202", state["veille_cloture"]["BTC"])
        self.assertEqual(
            align_bot.destinataires_message(state, {"101", "202"}, "🔴 BTC — SIGNAL NON CONFIRMÉ"),
            ["202"]
        )
        self.assertEqual(
            set(align_bot.destinataires_message(state, {"101", "202"}, "🥇 GOLD — SIGNAL NON CONFIRMÉ")),
            {"101", "202"}
        )

    def test_followmarket_both_registers_btc_and_gold(self):
        from unittest.mock import patch
        state = {}
        update = {"update_id": 99002, "callback_query": {
            "id": "follow-both", "data": "followmarket:BOTH",
            "message": {"chat": {"id": 102, "type": "private"}}, "from": {"id": 102}
        }}
        with patch.object(align_bot, "autorise", return_value=True), \
             patch.object(align_bot, "inscrire_auto") as subscribe, \
             patch.object(align_bot, "_envoi_sur"), patch.object(align_bot, "telegram"):
            align_bot.traiter(state, set(), [update])
        self.assertEqual([call.args[2] for call in subscribe.call_args_list], ["BTC", "GOLD"])
        self.assertEqual(state["marches_par_chat"]["102"], "BOTH")


class TestTelegramSimpleAnalysisLayout(unittest.TestCase):
    def test_analysis_message_has_only_the_relevant_follow_or_position_actions(self):
        import json
        markup = json.loads(align_bot.markup_analyse({}, "GOLD", {}))
        callbacks = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
        self.assertTrue({"why:GOLD", "details:GOLD", "levels:GOLD", "timeframes:GOLD",
                         "history:GOLD", "auto:GOLD"}.issubset(set(callbacks)))

    def test_active_position_keeps_only_position_and_exit_actions(self):
        import json
        markup = json.loads(align_bot.markup_analyse({"GOLD": {"trade": {"e": 1}}}, "GOLD", {}))
        callbacks = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
        self.assertTrue({"position:GOLD", "out:GOLD", "why:GOLD", "details:GOLD",
                         "levels:GOLD", "timeframes:GOLD", "history:GOLD"}.issubset(set(callbacks)))

    def test_telegram_command_menu_has_one_analysis_entry_not_separate_btc_gold_entries(self):
        from unittest.mock import patch
        import json
        with patch.object(align_bot, "telegram") as tg:
            align_bot.installer_menu({})
        calls = [c for c in tg.call_args_list if c.args and c.args[0] == "setMyCommands"]
        self.assertEqual(len(calls), 2)
        for call in calls:
            commands = json.loads(call.kwargs["commands"])
            names = [c["command"] for c in commands]
            self.assertIn("faire_analyse", names)
            self.assertNotIn("analyse_btc", names)
            self.assertNotIn("analyse_gold", names)


class TestTelegramPositionStateClarity(unittest.TestCase):
    def test_trade_alert_does_not_offer_ambiguous_no_or_im_in_buttons(self):
        import json
        buttons = json.loads(align_bot.boutons("BTC"))["inline_keyboard"]
        labels = [b["text"] for row in buttons for b in row]
        callbacks = [b["callback_data"] for row in buttons for b in row]
        self.assertEqual(labels, ["📍 Suivre cette position"])
        self.assertEqual(callbacks, ["in:BTC"])

    def test_active_trade_keyboard_is_personalized_for_untracked_user(self):
        import json
        state = {"GOLD": {"trade": {"e": 100, "qui": {"101": {"e": 100, "sl": 98, "tp1": 104}}}}}
        untracked = json.loads(align_bot.markup_analyse(state, "GOLD", {}, "202"))["inline_keyboard"]
        tracked = json.loads(align_bot.markup_analyse(state, "GOLD", {}, "101"))["inline_keyboard"]
        self.assertTrue({"in:GOLD", "why:GOLD", "details:GOLD", "levels:GOLD",
                         "timeframes:GOLD", "history:GOLD"}.issubset(
                             {b["callback_data"] for row in untracked for b in row}))
        self.assertTrue({"position:GOLD", "out:GOLD", "why:GOLD", "details:GOLD",
                         "levels:GOLD", "timeframes:GOLD", "history:GOLD"}.issubset(
                             {b["callback_data"] for row in tracked for b in row}))

    def test_position_details_never_call_unregistered_user_a_position_holder(self):
        state = {"GOLD": {"trade": {"e": 100, "sl": 98, "tp1": 104, "tp2": 108, "d": 1, "qui": {}}}}
        message = align_bot.texte_position("GOLD", {"m1": [candle(1, c=101)]}, state["GOLD"], "202")
        self.assertIn("Tu n'es pas encore enregistré", message)
        self.assertNotIn("TA POSITION", message)

    def test_results_empty_state_has_no_manual_entry_instruction(self):
        message = align_bot._texte_resultats({}, "101")
        self.assertIn("première clôture réellement enregistrée", message)
        self.assertNotIn("Je suis rentré", message)

    def test_position_keyboard_exposes_manual_exit_to_registered_user(self):
        import json
        markup = json.loads(align_bot.markup_position("BTC"))["inline_keyboard"]
        callbacks = [b["callback_data"] for row in markup for b in row]
        self.assertIn("out:BTC", callbacks)


    def test_manual_follow_returns_personal_position_and_exit_controls(self):
        from unittest.mock import patch
        state = {"GOLD": {"trade": {
            "d": 1, "e": 100.0, "sl": 98.0, "tp1": 104.0, "tp2": 108.0,
            "qui": {}
        }}}
        with patch.object(align_bot, "prix_actuel", return_value=101.0), \
             patch.object(align_bot, "controle_entree", return_value="Contrôles OK"), \
             patch.object(align_bot, "_envoi_sur") as send:
            align_bot.repondre(state, "101", True, "GOLD")
        args = send.call_args.kwargs
        self.assertEqual(args["reply_markup"], align_bot.markup_position("GOLD"))
        self.assertIn("SUIVI PERSONNEL ACTIVÉ", args["text"])
        self.assertIn("101", state["GOLD"]["trade"]["qui"])


    def test_volume_summary_detects_relative_spike_and_preserves_source(self):
        bars = [{"v": 100.0} for _ in range(20)] + [{"v": 180.0}]
        result = align_bot.resume_volume(bars, "Kraken spot BTC")
        self.assertTrue(result["disponible"])
        self.assertEqual(result["provenance"], "Kraken spot BTC")
        self.assertEqual(result["etat"], "pic")
        self.assertEqual(result["ratio_vs_moyenne"], 1.8)

    def test_volume_summary_never_invents_missing_volume(self):
        result = align_bot.resume_volume([candle(1)], "PAXG proxy")
        self.assertFalse(result["disponible"])
        self.assertEqual(result["provenance"], "PAXG proxy")
        self.assertIn("indisponible", result["interpretation"])

    def test_regrouping_sums_source_volume_without_changing_price_aggregation(self):
        bars = [
            dict(candle(0), v=12.5, trades=4),
            dict(candle(60, o=100.0, h=103.0, l=98.0, c=102.0), v=7.5, trades=3),
        ]
        grouped = align_bot.regrouper(bars, 2, 60, now_ts=120)
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["v"], 20.0)
        self.assertEqual(grouped[0]["trades"], 7)
        self.assertEqual(grouped[0]["c"], 102.0)

    def test_kraken_ohlc_parser_keeps_exchange_volume_and_trade_count(self):
        from unittest.mock import patch
        payload = {"error": [], "result": {"XXBTZUSD": [
            [0, "100", "102", "99", "101", "100.5", "12.75", 9],
            [60, "101", "103", "100", "102", "101.5", "18.25", 12],
        ], "last": 120}}
        with patch.object(align_bot, "http_json", return_value=payload):
            rows = align_bot._kraken("XBTUSD", 1)
        self.assertEqual(rows[-1]["v"], 12.75)
        self.assertEqual(rows[-1]["trades"], 9)


    def test_gold_paxg_recalibration_preserves_proxy_volume_and_provenance(self):
        from unittest.mock import patch
        import time
        source = [dict(candle(0), v=42.5, trades=8, volume_source="Kraken PAXG")]
        cache = {
            ("paxg", 5): (time.time(), source),
            "paxg_dernier": 1999.0,
        }
        with patch.dict(align_bot._CACHE, cache, clear=True), \
             patch.object(align_bot, "or_spot", return_value=2000.0):
            rows = align_bot.paxg_or(5)
        self.assertEqual(rows[0]["v"], 42.5)
        self.assertEqual(rows[0]["trades"], 8)
        self.assertEqual(rows[0]["volume_source"], "Kraken PAXG")


    def test_volume_summary_excludes_unclosed_current_candle(self):
        bars = [
            {"t": 0, "v": 100.0, "volume_source": "Kraken BTC"},
            {"t": 300, "v": 900.0, "volume_source": "Kraken BTC"},
        ]
        result = align_bot.resume_volume(bars, "Kraken BTC", timeframe_sec=300, now_ts=500)
        self.assertTrue(result["disponible"])
        self.assertEqual(result["derniere_bougie"], 100.0)
        self.assertEqual(result["nb_bougies"], 1)

    def test_volume_summary_reports_unavailable_if_only_candle_is_still_open(self):
        bars = [{"t": 300, "v": 900.0, "volume_source": "Kraken BTC"}]
        result = align_bot.resume_volume(bars, "Kraken BTC", timeframe_sec=300, now_ts=500)
        self.assertFalse(result["disponible"])
        self.assertIn("indisponible", result["interpretation"])


class TelegramAnalysisActionsRegressionTest(unittest.TestCase):
    def test_analysis_keyboard_exposes_every_existing_detail_action(self):
        import json
        for market in ("BTC", "GOLD"):
            markup = json.loads(align_bot.markup_analyse({}, market, {}))
            callbacks = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
            self.assertEqual(set(callbacks), {
                f"why:{market}", f"details:{market}", f"levels:{market}",
                f"timeframes:{market}", f"history:{market}", f"auto:{market}"
            })

    def test_registered_trade_keeps_position_and_exit_actions_with_details(self):
        import json
        state = {"GOLD": {"trade": {"qui": {"123": {"e": 100, "fini": False}}}}}
        markup = json.loads(align_bot.markup_analyse(state, "GOLD", {}, "123"))
        callbacks = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
        self.assertTrue({"position:GOLD", "out:GOLD", "why:GOLD", "details:GOLD",
                         "levels:GOLD", "timeframes:GOLD", "history:GOLD"}.issubset(set(callbacks)))
        self.assertNotIn("auto:GOLD", callbacks)

    def test_unregistered_user_sees_follow_current_trade_and_detail_actions(self):
        import json
        state = {"BTC": {"trade": {"qui": {}}}}
        markup = json.loads(align_bot.markup_analyse(state, "BTC", {}, "456"))
        callbacks = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
        self.assertIn("in:BTC", callbacks)
        self.assertIn("why:BTC", callbacks)
        self.assertIn("timeframes:BTC", callbacks)


class TelegramResponsivePollingRegressionTest(unittest.TestCase):
    def test_pending_telegram_updates_are_drained_from_the_independent_poller_queue(self):
        from unittest.mock import patch
        state = {"offset": 77}
        chats = {"123"}
        update = {"update_id": 77, "message": {"chat": {"id": 123, "type": "private"}}}
        demandes = []
        while not align_bot.TELEGRAM_UPDATES.empty():
            align_bot.TELEGRAM_UPDATES.get_nowait()
        align_bot.TELEGRAM_UPDATES.put(update)
        with patch.object(align_bot, "TOKEN", "test-token"), \
             patch.object(align_bot, "telegram") as api, \
             patch.object(align_bot, "traiter", return_value=[("123", "GOLD")]) as handle:
            count = align_bot.recevoir_updates_telegram(state, chats, demandes)
        self.assertEqual(count, 1)
        self.assertEqual(demandes, [("123", "GOLD")])
        api.assert_not_called()
        handle.assert_called_once_with(state, chats, [update])
        self.assertTrue(align_bot.TELEGRAM_UPDATES.empty())

    def test_telegram_polling_helper_is_safe_when_token_is_not_configured(self):
        from unittest.mock import patch
        with patch.object(align_bot, "TOKEN", ""), patch.object(align_bot, "telegram") as api:
            self.assertEqual(align_bot.recevoir_updates_telegram({}, set(), []), 0)
        api.assert_not_called()

    def test_mon_bot_slash_command_reaches_the_existing_menu_handler(self):
        from unittest.mock import patch
        update = {"update_id": 99801, "message": {
            "text": "/mon_bot", "chat": {"id": 123, "type": "private"},
            "from": {"id": 123}
        }}
        with patch.object(align_bot, "autorise", return_value=True), \
             patch.object(align_bot, "menu_bot") as menu:
            align_bot.traiter({"proprio": ["123"]}, {"123"}, [update])
        menu.assert_called_once()


class TelegramIndependentPollerFastPathTest(unittest.TestCase):
    def setUp(self):
        align_bot.CALLBACKS_ACKNOWLEDGED.clear()
        align_bot.TELEGRAM_POLL_STOP.clear()
        align_bot.SHUTDOWN_REQUESTED.clear()

    def test_mon_bot_command_is_answered_by_fast_path_without_waiting_for_analysis(self):
        from unittest.mock import patch
        update = {"update_id": 99811, "message": {
            "text": "/mon_bot", "chat": {"id": 123, "type": "private"},
            "from": {"id": 123}
        }}
        with patch.object(align_bot, "POSITIONS_GRATUITES", True), \
             patch.object(align_bot, "menu_bot") as menu:
            self.assertTrue(align_bot._traiter_lecture_rapide({}, {"123"}, update))
        menu.assert_called_once_with({}, "123")
        self.assertTrue(update.get("_align_fast_handled"))

    def test_reply_keyboard_mon_bot_button_uses_same_fast_path(self):
        from unittest.mock import patch
        update = {"update_id": 99812, "message": {
            "text": "🤖 Mon bot", "chat": {"id": 123, "type": "private"},
            "from": {"id": 123}
        }}
        with patch.object(align_bot, "POSITIONS_GRATUITES", True), \
             patch.object(align_bot, "menu_bot") as menu:
            self.assertTrue(align_bot._traiter_lecture_rapide({}, {"123"}, update))
        menu.assert_called_once_with({}, "123")

    def test_results_button_is_answered_by_fast_path(self):
        from unittest.mock import patch
        update = {"update_id": 99813, "message": {
            "text": "📈 Mes résultats", "chat": {"id": 123, "type": "private"},
            "from": {"id": 123}
        }}
        with patch.object(align_bot, "POSITIONS_GRATUITES", True), \
             patch.object(align_bot, "texte_resultats", return_value="results"), \
             patch.object(align_bot, "_envoi_sur") as send:
            self.assertTrue(align_bot._traiter_lecture_rapide({}, {"123"}, update))
        send.assert_called_once()

    def test_analysis_button_opens_market_choice_without_waiting_for_analysis(self):
        from unittest.mock import patch
        update = {"update_id": 99814, "message": {
            "text": "📊 Faire une analyse", "chat": {"id": 123, "type": "private"},
            "from": {"id": 123}
        }}
        with patch.object(align_bot, "_menu_analyse_rapide") as menu:
            self.assertTrue(align_bot._traiter_lecture_rapide({}, set(), update))
        menu.assert_called_once_with("123")

    def test_fast_path_never_treats_group_messages_as_private_bot_commands(self):
        update = {"update_id": 99815, "message": {
            "text": "/mon_bot", "chat": {"id": -100, "type": "supergroup"},
            "from": {"id": 123}
        }}
        self.assertFalse(align_bot._traiter_lecture_rapide({}, set(), update))

    def test_fast_path_does_not_bypass_deep_link_state_changes(self):
        update = {"update_id": 99816, "message": {
            "text": "/start auto_gold", "chat": {"id": 123, "type": "private"},
            "from": {"id": 123}
        }}
        self.assertFalse(align_bot._traiter_lecture_rapide({}, {"123"}, update))

    def test_callback_acknowledgement_is_not_sent_twice_by_the_main_handler(self):
        from unittest.mock import patch
        cb = {"id": "fast-callback"}
        with patch.object(align_bot, "telegram", return_value={"ok": True}) as api:
            align_bot._ack_callback_rapide(cb, "⌛ Action reçue")
        self.assertIn("fast-callback", align_bot.CALLBACKS_ACKNOWLEDGED)
        with patch.object(align_bot, "http_json") as http:
            result = align_bot.telegram("answerCallbackQuery", callback_query_id="fast-callback")
        self.assertEqual(result, {"ok": True, "result": True})
        http.assert_not_called()


    def test_independent_poller_acknowledges_callback_before_queueing_action(self):
        from unittest.mock import patch
        callback = {"id": "poller-fast", "from": {"id": 123},
                    "message": {"chat": {"id": 123, "type": "private"}},
                    "data": "why:BTC"}
        update = {"update_id": 99817, "callback_query": callback}
        while not align_bot.TELEGRAM_UPDATES.empty():
            align_bot.TELEGRAM_UPDATES.get_nowait()
        align_bot.TELEGRAM_POLL_STOP.clear()
        def fake_telegram(method, **kwargs):
            if method == "getUpdates":
                align_bot.TELEGRAM_POLL_STOP.set()
                return {"result": [update]}
            if method == "answerCallbackQuery":
                return {"ok": True}
            return {"ok": True}
        with patch.object(align_bot, "TOKEN", "test-token"), \
             patch.object(align_bot, "telegram", side_effect=fake_telegram) as api:
            align_bot.boucle_polling_telegram({}, {"123"})
        self.assertIn("poller-fast", align_bot.CALLBACKS_ACKNOWLEDGED)
        self.assertFalse(align_bot.TELEGRAM_UPDATES.empty())
        self.assertTrue(any(call.args[0] == "answerCallbackQuery" for call in api.call_args_list))
        align_bot.TELEGRAM_UPDATES.get_nowait()
        align_bot.CALLBACKS_ACKNOWLEDGED.clear()
        align_bot.TELEGRAM_POLL_STOP.clear()

    def test_shutdown_signal_requests_state_save_and_stops_poller(self):
        import signal
        align_bot._demander_arret(signal.SIGTERM, None)
        self.assertTrue(align_bot.SHUTDOWN_REQUESTED.is_set())
        self.assertTrue(align_bot.TELEGRAM_POLL_STOP.is_set())


class TestTelegramMarketButtonsJourney(unittest.TestCase):
    """Parcours utilisateur réel : choix BTC / GOLD / les deux, sans fuite entre marchés."""

    def _cb(self, uid, data, n):
        return {"update_id": 777000 + n, "callback_query": {
            "id": f"cb{n}", "data": data,
            "message": {"chat": {"id": uid, "type": "private"}}, "from": {"id": uid}}}

    def _run(self, state, data, n):
        from unittest.mock import patch
        sent = []
        with patch.object(align_bot, "autorise", return_value=True), \
             patch.object(align_bot, "_envoi_sur", side_effect=lambda cid, **k: sent.append(k)), \
             patch.object(align_bot, "telegram"):
            align_bot.traiter(state, set(), [self._cb(501, data, n)])
        return sent

    def test_gold_only_never_receives_btc_and_both_receives_both(self):
        state = {}
        self._run(state, "followmarket:GOLD", 1)
        self.assertEqual(state["marches_par_chat"]["501"], "GOLD")
        self.assertEqual(align_bot.destinataires_message(state, {"501"}, "🟠 BTC • LONG"), [])
        self.assertIn("501", align_bot.destinataires_message(state, {"501"}, "🥇 GOLD • SHORT"))
        self._run(state, "followmarket:BTC", 2)
        self.assertEqual(align_bot.destinataires_message(state, {"501"}, "🥇 GOLD • SHORT"), [])
        self.assertIn("501", align_bot.destinataires_message(state, {"501"}, "🟠 BTC • LONG"))
        self._run(state, "followmarket:BOTH", 3)
        for t in ("🟠 BTC • LONG", "🥇 GOLD • SHORT"):
            self.assertIn("501", align_bot.destinataires_message(state, {"501"}, t))

    def test_follow_next_btc_keeps_gold_when_both_selected(self):
        state = {}
        self._run(state, "followmarket:BOTH", 4)
        self._run(state, "auto:BTC", 5)
        self.assertEqual(state["marches_par_chat"]["501"], "BOTH")
        self.assertIn("501", align_bot.destinataires_message(state, {"501"}, "🥇 GOLD • SHORT"))

    def test_follow_confirmation_has_real_line_breaks(self):
        sent = self._run({}, "auto:GOLD", 6)
        texts = [k.get("text", "") for k in sent]
        self.assertTrue(texts)
        self.assertFalse(any("\\n" in t for t in texts))

    def test_markets_menu_callbacks_all_handled(self):
        for i, mk in enumerate(("BTC", "GOLD", "BOTH")):
            state = {}
            sent = self._run(state, f"markets:{mk}", 10 + i)
            self.assertEqual(state["marches_par_chat"]["501"], mk)
            kb = json.loads(sent[-1]["reply_markup"])["inline_keyboard"]
            coches = [b["text"] for r in kb for b in r if b["text"].startswith("✅")]
            self.assertEqual(len(coches), 1)

    def test_both_label_translated_in_english(self):
        self.assertEqual(align_bot.traduire("🥇 + 🟠 Les deux"), "🥇 + 🟠 Both")


class TestTelegramFloodProtection(unittest.TestCase):
    """Telegram bloque un chat des heures si le bot édite trop souvent : on protège la cause racine."""

    def test_cooldown_survives_worker_restart(self):
        import time as _t
        align_bot.TELEGRAM_RETRY_UNTIL.clear()
        fin = _t.time() + 3600
        align_bot.restaurer_cooldowns_telegram({"telegram_retry_until": {"42": fin, "7": _t.time() - 5}})
        self.assertIn("42", align_bot.TELEGRAM_RETRY_UNTIL)
        self.assertNotIn("7", align_bot.TELEGRAM_RETRY_UNTIL)
        from unittest.mock import patch
        with patch.object(align_bot, "http_json") as net:
            with self.assertRaises(RuntimeError):
                align_bot.telegram("sendMessage", chat_id="42", text="x")
            net.assert_not_called()
        align_bot.TELEGRAM_RETRY_UNTIL.clear()

    def test_gauge_is_edited_at_most_once_per_minute(self):
        from unittest.mock import patch
        cle = {"jauge": {"1": 5}, "jauge_txt": {"1": "old"}, "jauge_t": {"1": 1000.0}}
        with patch.object(align_bot, "jauge", side_effect=["p1", "p2", "p3"]), \
             patch.object(align_bot, "marche_autorise", return_value=True), \
             patch.object(align_bot.time, "time", side_effect=[1010.0, 1059.0, 1061.0, 1061.0]), \
             patch.object(align_bot, "telegram") as tg:
            for _ in range(3):
                align_bot.maj_jauge({}, "GOLD", {}, cle, {"1"})
        edits = [c for c in tg.call_args_list if c.args[0] == "editMessageText"]
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].kwargs["text"], "p3")


class TestCandleCloseClarity(unittest.TestCase):
    def test_chrono_shows_m5_m15_closes_in_mmss_and_explains(self):
        from unittest.mock import patch
        now = 1_700_000_100.0   # 100 s après une clôture 5 min alignée
        r = {"dirs": [0] * 11, "m1": [{"c": 100.0}], "prix": 100.0}
        with patch.object(align_bot.time, "time", return_value=now):
            txt = align_bot.chrono_txt("GOLD", r, {}, now - 10)
        import re
        self.assertRegex(txt, r"🕯 Clôture 5 min : \d\d:\d\d\n🕯 Clôture 15 min : \d\d:\d\d")
        self.assertIn("👉 À la clôture 4 h", txt)
        self.assertRegex(txt, r"Heure prévue : \d\d:\d\d \(heure")
        en = align_bot.traduire(txt)
        self.assertIn("5m close", en)
        self.assertEqual(align_bot.duree_cloture(2 * 3600 + 42 * 60 + 5), "2 h 42")
        self.assertEqual(align_bot.duree_cloture(3600), "60:00")
        self.assertIn("At the 4h close", en)


class TestMainKeyboardButtonsRouting(unittest.TestCase):
    """Chaque bouton du clavier principal déclenche une vraie action (FR et EN)."""

    def _send(self, text, en=False):
        from unittest.mock import patch
        upd = {"update_id": 880001, "message": {"message_id": 1, "text": text, "date": 0,
               "chat": {"id": 601, "type": "private"}, "from": {"id": 601, "first_name": "T"}}}
        state = {"bienvenue": {"601": 1}, "en": ["601"] if en else []}
        align_bot.LANG_EN.clear(); align_bot.LANG_EN.update(state["en"])
        with patch.object(align_bot, "autorise", return_value=True), \
             patch.object(align_bot, "_envoi_sur") as envoi, \
             patch.object(align_bot, "menu_marches") as marches, \
             patch.object(align_bot, "telegram"):
            demandes = align_bot.traiter(state, {"601"}, [upd])
        align_bot.LANG_EN.clear()
        return demandes, envoi, marches

    def test_gold_and_btc_buttons_request_only_their_market(self):
        self.assertEqual(self._send("🥇 Analyse Gold")[0], [("601", "GOLD")])
        self.assertEqual(self._send("🟠 Analyse BTC")[0], [("601", "BTC")])

    def test_english_gold_and_btc_buttons_route_identically(self):
        self.assertEqual(self._send(align_bot.TRAD["🥇 Analyse Gold"], en=True)[0], [("601", "GOLD")])
        self.assertEqual(self._send(align_bot.TRAD["🟠 Analyse BTC"], en=True)[0], [("601", "BTC")])

    def test_markets_button_opens_market_selector(self):
        self.assertTrue(self._send("📡 Mes marchés")[2].called)
        self.assertTrue(self._send(align_bot.TRAD["📡 Mes marchés"], en=True)[2].called)


class TestFollowToastAndLatencyGuard(unittest.TestCase):
    def test_each_follow_button_gets_specific_toast(self):
        self.assertIn("Suivi de ta position activé", align_bot.toast_callback("in:GOLD"))
        self.assertIn("entrée est confirmée", align_bot.toast_callback("auto:BTC"))
        self.assertIn("Position tracking on", align_bot.toast_callback("in:GOLD", anglais=True))
        self.assertIn("traitement", align_bot.toast_callback("inconnu:x"))

    def test_poller_sends_specific_toast_on_click(self):
        from unittest.mock import patch
        upd = {"update_id": 990001, "callback_query": {"id": "t1", "data": "in:GOLD",
               "message": {"chat": {"id": 5, "type": "private"}}, "from": {"id": 5}}}
        calls = []
        def fake(methode, **k):
            calls.append((methode, k))
            if methode == "getUpdates":
                align_bot.TELEGRAM_POLL_STOP.set()
                return {"result": [upd]}
            return {"ok": True}
        align_bot.TELEGRAM_POLL_STOP.clear()
        with patch.object(align_bot, "telegram", side_effect=fake), patch.object(align_bot, "TOKEN", "x"):
            align_bot.boucle_polling_telegram({}, set())
        align_bot.TELEGRAM_POLL_STOP.clear()
        while not align_bot.TELEGRAM_UPDATES.empty():
            align_bot.TELEGRAM_UPDATES.get_nowait()
        toasts = [k["text"] for m, k in calls if m == "answerCallbackQuery"]
        self.assertTrue(toasts and "Suivi de ta position activé" in toasts[0])

    def test_latency_guard(self):
        tr = {"d": -1, "e": 4065.0, "sl": 4068.0, "tp1": 4027.0}   # SHORT, risque 3
        self.assertEqual(align_bot.alerte_latence_entree(tr, 4064.5), "")
        self.assertTrue(align_bot.alerte_latence_entree(tr, 4066.5).startswith("⚠️"))
        self.assertTrue(align_bot.alerte_latence_entree(tr, 4067.6).startswith("⛔"))
        self.assertTrue(align_bot.alerte_latence_entree(tr, 4028.0).startswith("⚠️"))

    def test_join_refused_when_price_at_stop(self):
        from unittest.mock import patch
        etat = {"GOLD": {"trade": {"d": -1, "e": 4065.0, "sl": 4068.0, "tp1": 4027.0, "qui": {}}}}
        with patch.object(align_bot, "prix_actuel", return_value=4067.8), \
             patch.object(align_bot, "_envoi_sur") as envoi, \
             patch.object(align_bot, "markup_position", return_value="{}"):
            align_bot.repondre(etat, "9", True, "GOLD")
        self.assertNotIn("9", etat["GOLD"]["trade"]["qui"])
        self.assertIn("collé au stop", envoi.call_args.kwargs["text"])


class TestActiveTimeframeReading(unittest.TestCase):
    def test_m5_chart_reads_5_15_60_alignment(self):
        r = {"dirs": [-1] * 9 + [0, -1], "tv_indicator_mtf": {"activeTimeframe": "M5"}}
        txt = align_bot.lecture_unite_active(r)
        self.assertIn("M5", txt); self.assertIn("SHORT", txt); self.assertIn("5 min + 15 min + 1 h", txt)

    def test_h1_chart_needs_4h_for_swing(self):
        r = {"dirs": [-1] * 9 + [0, -1], "tv_indicator_mtf": {"activeTimeframe": "H1"}}
        self.assertIn("pas d'alignement", align_bot.lecture_unite_active(r))

    def test_no_bridge_no_invented_line(self):
        self.assertIsNone(align_bot.lecture_unite_active({"dirs": [1] * 11}))


class TestGuaranteedShutdown(unittest.TestCase):
    def test_forced_shutdown_saves_state_then_exits(self):
        from unittest.mock import patch
        align_bot._ETAT_COURANT.update({"etat": {"x": 1}, "chats": {"1"}})
        with patch.object(align_bot.time, "sleep"), \
             patch.object(align_bot, "_sauver_etat_sous_verrou") as save, \
             patch.object(align_bot.os, "_exit") as quit_:
            align_bot._arret_garanti()
        save.assert_called_once()
        quit_.assert_called_once_with(0)
        align_bot._ETAT_COURANT.clear()

    def test_signal_starts_single_watchdog(self):
        from unittest.mock import patch
        align_bot.SHUTDOWN_REQUESTED.clear(); align_bot.TELEGRAM_POLL_STOP.clear()
        with patch.object(align_bot.threading, "Thread") as th:
            align_bot._demander_arret(2, None)
            align_bot._demander_arret(15, None)
        self.assertEqual(th.call_count, 1)
        align_bot.SHUTDOWN_REQUESTED.clear(); align_bot.TELEGRAM_POLL_STOP.clear()


class TestStrategiesScalpingDaySwing(unittest.TestCase):
    """Règles identiques à l'indicateur v12 (index UT : 0=1m 2=5m 4=15m 7=1h 9=4h 10=D)."""
    def test_swing_confirmed_and_waiting(self):
        f = align_bot.strategie_alignement
        self.assertEqual(f([-1] * 9 + [0, -1], -1)[:2], ("SWING", "CONFIRMÉ"))
        s = f([0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1], 1)   # D1 ↑, H4 ↑ pas retracé, H1 neutre → pas de swing
        self.assertNotEqual(s[:2], ("SWING", "CONFIRMÉ"))
        w = f([0, 0, 0, 0, 0, 0, 0, 0, 0, -1, 1], 1)
        self.assertEqual(w[:2], ("SWING", "EN ATTENTE"))
        self.assertIn("Retracement H4 détecté, H1 non confirmé", w[2])

    def test_weekly_against_blocks_swing(self):
        self.assertNotEqual(align_bot.strategie_alignement([1] * 11, 1, dW=-1)[0], "SWING")

    def test_day_and_scalping(self):
        f = align_bot.strategie_alignement
        self.assertEqual(f([0, 0, 1, 0, -1, 0, 0, 1, 0, 0, -1], 1)[:2], ("DAY", "CONFIRMÉ"))
        self.assertEqual(f([0, 0, -1, 0, -1, 0, 0, 1, 0, 0, -1], 1)[:2], ("DAY", "EN ATTENTE"))
        self.assertEqual(f([1, 0, 1, 0, 1, 0, 0, 0, 0, 0, -1], 1)[:2], ("SCALPING", "CONFIRMÉ"))
        self.assertEqual(f([0, 0, 1, 0, 1, 0, 0, 0, 0, 0, -1], 1)[:2], ("SCALPING", "EN ATTENTE"))
        self.assertEqual(f([1] * 11, 0)[0], "")

    def test_levels_by_strategy(self):
        f = align_bot.niveaux_strategie
        self.assertEqual(f("SWING"), (("1h", "4h"), ("4h", "Daily")))
        self.assertEqual(f("DAY"), (("1h",), ("1h", "4h")))
        self.assertEqual(f("SCALPING"), (("15m",), ("15m", "1h")))
        self.assertEqual(f(""), (("1h", "4h"), ("1h", "4h", "Daily")))

    def test_score_thresholds_and_no_compensation(self):
        plan = {"e": 100.0, "sl": 101.0, "tp1": 97.0}
        tot, p, dec = align_bot.score_validation("SWING", "CONFIRMÉ", [-1] * 11, -1, -1, 100.2, plan, 1.0,
                                                 [50] * 11, -1, [10] * 20 + [15])
        self.assertEqual(tot, 100); self.assertIn("ENTRÉE POSSIBLE", dec)
        tot2, p2, dec2 = align_bot.score_validation("SWING", "EN ATTENTE", [-1] * 11, -1, -1, 100.2, plan, 1.0,
                                                    [50] * 11, -1, [10] * 20 + [15])
        self.assertIn("confirmation manquante", dec2)          # un score élevé ne remplace pas la confirmation
        tot3, p3, _ = align_bot.score_validation("DAY", "CONFIRMÉ", [-1] * 11, -1, 0, 100.2, plan, 1.0,
                                                 [50] * 11, -1, [])
        self.assertTrue(p3.get("volume_indisponible")); self.assertEqual(p3["volume"], 0)
        _, _, dec4 = align_bot.score_validation("SCALPING", "CONFIRMÉ", [0] * 11, -1, 0, 105.0, plan, 1.0,
                                                [20] * 11, 1, [])
        self.assertIn("AUCUNE ENTRÉE", dec4)


class TestStopNotTooTight(unittest.TestCase):
    def test_minimum_risk_covers_btc_wick_of_11_november(self):
        # SHORT BTC 11/11 : entrée 73911, ATR 15 min ≈ 105, mèche max 74044 puis baisse à 73535
        a, e = 105.0, 73911.2
        mini = max(align_bot.SL_RISQUE_MIN_ATR * a, e * align_bot.SL_RISQUE_MIN_PCT)
        self.assertGreater(e + mini, 74044)          # le nouveau SL survit à la mèche
        self.assertGreater(e - 1.5 * mini, 73535)  # TP1 à 1,5 R reste atteignable (plus bas 73535)


class TestEveryMainButtonAnswers(unittest.TestCase):
    """Chaque bouton du clavier répond (membre et visiteur), sans fuite des niveaux VIP."""
    def _run(self, text=None, cb=None, auth=True, state=None):
        from unittest.mock import patch
        st = state if state is not None else {"bienvenue": {"601": 1}, "lien": "https://t.me/+VIP"}
        if cb:
            upd = {"update_id": 5, "callback_query": {"id": "c", "data": cb, "message": {"chat": {"id": 601, "type": "private"}}, "from": {"id": 601}}}
        else:
            upd = {"update_id": 5, "message": {"message_id": 1, "text": text, "date": 0, "chat": {"id": 601, "type": "private"}, "from": {"id": 601, "first_name": "T"}}}
        out = []
        with patch.object(align_bot, "autorise", return_value=auth), \
             patch.object(align_bot, "_envoi_sur", side_effect=lambda c, **k: out.append(k)), \
             patch.object(align_bot, "telegram"), \
             patch.object(align_bot, "analyse_visiteur", side_effect=lambda *x: out.append({"text": "VISITEUR"})):
            d = align_bot.traiter(st, {"601"} if auth else set(), [upd])
        return out, d

    def test_member_vip_button_answers(self):
        for t in ("💎 Devenir VIP", "/vip"):
            out, _ = self._run(t)
            self.assertTrue(out and "DÉJÀ VIP" in out[0]["text"])

    def test_member_buttons_all_answer(self):
        for t in ("🤖 Mon bot", "📈 Mes résultats", "📸 Partager mon gain", "🧩 Indicateur TradingView", "📊 Faire une analyse"):
            out, d = self._run(t)
            self.assertTrue(out or d, t)

    def test_visitor_never_gets_vip_levels_from_analysis_choice(self):
        out, d = self._run(cb="analysechoice:GOLD", auth=False, state={"lien": "x", "prospects": ["601"]})
        self.assertEqual(d, [])
        self.assertEqual(out[-1]["text"], "VISITEUR")

    def test_visitor_keyboard_has_no_dead_button(self):
        for row in json.loads(align_bot.CLAVIER_VISITEUR)["keyboard"]:
            for b in row:
                out, d = self._run(b["text"], auth=False, state={"lien": "x", "prospects": ["601"]})
                self.assertTrue(out or d, b["text"])
                self.assertFalse(any("Utilise les boutons en bas" in (o.get("text") or "") for o in out), b["text"])


class TestTradeCardShowsStrategy(unittest.TestCase):
    def test_entry_card_states_type_duration_and_levels(self):
        tr = {"d": -1, "e": 100.0, "sl": 101.0, "tp1": 97.0, "tp2": 95.0, "rr": 3.0, "n1": "support 4h", "n2": "support Daily"}
        tr.update(align_bot.strategie_trade({"dirs": [-1] * 11, "dirW": -1}, -1))
        txt = align_bot.fmt_trade("GOLD", tr, 100.1)
        self.assertIn("🏷 Type : SWING — position de plusieurs jours", txt)
        self.assertIn("validation clôture 1h", txt)
        en = align_bot.traduire(txt)
        self.assertIn("multi-day position", en)

    def test_no_strategy_no_invented_line(self):
        tr = {"d": 1, "e": 100.0, "sl": 99.0, "tp1": 103.0, "tp2": 105.0, "rr": 3.0, "n1": "r 1h", "n2": "r 4h"}
        tr.update(align_bot.strategie_trade({"dirs": [0] * 11}, 1))
        self.assertNotIn("🏷 Type", align_bot.fmt_trade("BTC", tr))


class TestNextValidationCountdown(unittest.TestCase):
    def test_countdown_and_time_on_waiting_card(self):
        from unittest.mock import patch
        now = 1_700_000_000.0
        r = {"b1h": [{"t": int(now // 3600 * 3600) - 3600}]}
        with patch.object(align_bot.time, "time", return_value=now):
            fin = align_bot.prochaine_cloture_bougie(r, "1h", now)
        self.assertGreater(fin, now)
        self.assertRegex(align_bot.duree_cloture(fin - now), r"^\d\d:\d\d$")


class TestReversalAfterStop(unittest.TestCase):
    def test_entry_after_opposite_stop_is_labelled_reversal(self):
        cle = {"retournement": {"d": 1, "t": 1000}}
        self.assertTrue(align_bot.retournement_confirme(cle, 1, {"t": 2000}))
        self.assertNotIn("retournement", cle)
        tr = {"d": 1, "e": 100.0, "sl": 99.0, "tp1": 103.0, "tp2": 105.0, "rr": 3.0, "n1": "a", "n2": "b", "retour": True}
        self.assertTrue(align_bot.fmt_trade("GOLD", tr).startswith("✅ RETOURNEMENT CONFIRMÉ : LONG"))

    def test_old_or_same_direction_is_not_reversal(self):
        self.assertFalse(align_bot.retournement_confirme({"retournement": {"d": 1, "t": 0}}, 1, {"t": 5 * 3600}))
        self.assertFalse(align_bot.retournement_confirme({"retournement": {"d": -1, "t": 0}}, 1, {"t": 10}))


class TestMessagesPropres(unittest.TestCase):
    def test_compacter_ia_sans_paves_ni_conclusion(self):
        t = align_bot.compacter_ia("**Mouvement** : baisse. Le H4 est baissier.\nEn conclusion, belle opportunité.")
        self.assertEqual(t.split("\n"), ["Mouvement : baisse.", "Le H4 est baissier."])
        long = align_bot.compacter_ia("x " * 200)
        self.assertLessEqual(len(long), align_bot.IA_LIGNE_MAX_CAR + 1)

    def test_entree_encore_possible_en_carte(self):
        t = align_bot.mise_en_forme("✅ ENTRÉE ENCORE POSSIBLE — 🟠 BTC\n🟥 SHORT ⬇️\n📌 Entrée : 74508.80\n🛑 Stop : 74824.57\n🎯 TP1 : 73672.44")
        lignes = t.split("\n")
        self.assertIn("📌 Entrée : 74508,80", lignes)
        self.assertIn("🛑 Stop : 74824,57", lignes)
        self.assertIn("🎯 TP1 : 73672,44", lignes)

    def test_carte_analyse_donne_cible_essoufflement_et_voyants(self):
        r = {"dirs": [-1] * 7 + [0, -1, -1, -1], "m1": [{"t": 0, "o": 1, "h": 1, "l": 1, "c": 3993.56}], "atr": 6.0, "atr5": 2.5,
             "niveaux": [(3984.2, "1h"), (3971.0, "4h"), (4010, "1h")], "niv_cles": [(3978.4, "plus bas d'hier")]}
        l = align_bot.objectifs_marche(r, -1)
        self.assertIn("3984,20", l[0])
        self.assertIn("Essoufflement", l[1])
        self.assertIn("3978,40", l[1])
        self.assertEqual(align_bot.voyants_unites(r)[0], "⚡ Petites unités : 1m ⬇️  3m ⬇️  5m ⬇️  15m ⬇️")
        self.assertEqual(align_bot.objectifs_marche(r, 0), [])

    def test_alerte_retournement_3_sur_5_une_seule_fois(self):
        tr = {"d": -1, "e": 74410.2}
        r = {"dirs": [1, 1, 1, 0, -1, 0, 0, -1, 0, -1, -1]}
        t = align_bot.alerte_retournement("BTC", r, tr)
        self.assertIn("RETOURNEMENT EN PRÉPARATION", t)
        self.assertIn("3/5", t)
        self.assertIsNone(align_bot.alerte_retournement("BTC", r, tr))
        r["dirs"][:5] = [-1, -1, -1, -1, -1]
        self.assertIsNone(align_bot.alerte_retournement("BTC", r, tr))
        self.assertNotIn("ret_dit", tr)
