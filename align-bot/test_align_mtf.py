import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import align_bot


def candle(t, o=100.0, h=101.0, l=99.0, c=100.0):
    return {"t": t, "o": o, "h": h, "l": l, "c": c}


class AlignMtfRulesTest(unittest.TestCase):
    def test_4h_and_1h_confirm_without_15m(self):
        r = {"dirs": [0, 0, 0, 0, -1, 0, 0, 1, 0, 1, 0]}
        self.assertEqual(align_bot.alignement(r), (1, 2))

    def test_15m_opposition_does_not_block_4h_1h(self):
        r = {"dirs": [0, 0, 0, 0, -1, 0, 0, -1, 0, -1, 0]}
        self.assertEqual(align_bot.alignement(r), (-1, 2))

    def test_breakout_uses_closed_5m_bars(self):
        bars = [candle(i) for i in range(21)]
        bars.append(candle(21, o=100.5, h=103.0, l=100.2, c=102.0))
        r = {
            "b5": bars, "atr5": 1.0, "atr": 1.0, "r5": [50.0],
            "m1": [candle(22, o=101.0, h=102.0, l=100.8, c=102.0)],
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


    def test_countdown_keeps_seconds_visible_over_one_hour(self):
        self.assertEqual(align_bot.mmss(59), "0 min 59 s")
        self.assertEqual(align_bot.mmss(3599), "59 min 59 s")
        self.assertEqual(align_bot.mmss(3600), "1 h 00 min 00 s")
        self.assertEqual(align_bot.mmss(3617), "1 h 00 min 17 s")

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
        self.assertIn("PROCHAINE CLÔTURE 1h : 1 h 00 min 00 s", message)
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

    def test_multi_timeframe_watcher_reports_each_new_close_only_once(self):
        from unittest.mock import patch
        state = {"veille_cloture": {"GOLD": {"123": {
            "multi": True, "derniers_t": {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400},
            "expire": 999999
        }}}}
        r = {
            "b5": [candle(300), candle(600)],
            "b15": [candle(900), candle(1800)],
            "b1h": [candle(3600), candle(7200)],
            "b4h": [candle(14400), candle(28800)]
        }
        with patch.object(align_bot.time, "time", return_value=100), \
             patch.object(align_bot, "texte_cloture", side_effect=lambda m, tf, b, r, c: f"close-{tf}"), \
             patch.object(align_bot, "markup_analyse", return_value=None), \
             patch.object(align_bot, "_envoi_sur") as send:
            align_bot.notifier_clotures(state, "GOLD", r, {})
            align_bot.notifier_clotures(state, "GOLD", r, {})
        self.assertEqual(send.call_count, 4)
        self.assertEqual({x.kwargs["text"] for x in send.call_args_list},
                         {"close-5m", "close-15m", "close-1h", "close-4h"})

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
        self.assertIn("💰 TP1\n4075,50\nancienne mèche haute — bougie 15 minutes", message)
        self.assertIn("🛑 Stop Loss\n4020\nsous la mèche basse — bougie 15 minutes", message)
        self.assertIn("📌 Entrée\n4050", message)

    def test_telegram_price_values_remove_all_thousands_grouping_spaces(self):
        message = align_bot.mise_en_forme("PLAN\n💰 TP1 : 12 345 678,90 (niveau majeur)")
        self.assertIn("💰 TP1\n12345678,90\nniveau majeur", message)


    def test_telegram_price_formatting_is_idempotent_after_card_layout(self):
        first = align_bot.mise_en_forme(
            "PLAN\n💰 TP1 ≈ 4 075,50 (ancienne mèche haute — bougie 15 minutes)"
        )
        second = align_bot.mise_en_forme(first)
        self.assertIn("💰 TP1\n4075,50\nancienne mèche haute — bougie 15 minutes", second)
        self.assertNotIn("4 075", second)
        self.assertEqual(first, second)

    def test_telegram_standalone_price_line_is_compacted(self):
        message = align_bot.mise_en_forme(
            "💰 TP1\n4 075,50\nancienne mèche haute — bougie 15 minutes\n"
            "📌 Entrée\n4 000,00"
        )
        self.assertIn("💰 TP1\n4075,50", message)
        self.assertIn("📌 Entrée\n4000", message)
        self.assertNotIn("4 075", message)
        self.assertNotIn("4 000", message)

    def test_price_helper_uses_french_decimal_without_thousands_separator(self):
        self.assertEqual(align_bot.px(4075.5), "4075,50")
        self.assertEqual(align_bot.px(4000), "4000")
        self.assertEqual(align_bot.mise_en_forme("TP1 : 4 000,00"), "TP1\n4000")

    def test_previous_analysis_button_is_market_specific(self):
        import json
        keyboard = json.loads(align_bot.bouton_rappel("GOLD"))["inline_keyboard"]
        callbacks = [button["callback_data"] for row in keyboard for button in row]
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
        self.assertIn("CLÔTURE CONFIRMÉE", send.call_args.kwargs["text"])
        self.assertNotIn("123", state["veille_cloture"]["BTC"])

    def test_chronometer_refreshes_every_five_seconds_without_spamming(self):
        from unittest.mock import patch
        state = {"chrono": {"GOLD": {"123": {"mid": 9, "t0": 1, "maj": 100.0}}}, "GOLD": {}}
        with patch.object(align_bot.time, "time", side_effect=[100.1, 104.9, 105.1]), \
             patch.object(align_bot, "chrono_txt", return_value="tick-105") as render, \
             patch.object(align_bot, "telegram") as send:
            align_bot.maj_chronos(state, "GOLD", {})
            align_bot.maj_chronos(state, "GOLD", {})
            align_bot.maj_chronos(state, "GOLD", {})
        self.assertEqual(send.call_count, 1)
        self.assertEqual(render.call_count, 1)
        self.assertEqual(send.call_args.kwargs["text"], "tick-105")
    def test_analysis_keyboard_exposes_details_levels_and_explicit_position_action(self):
        import json
        keyboard = json.loads(align_bot.markup_analyse({}, "GOLD", {}))["inline_keyboard"]
        labels = [button["text"] for row in keyboard for button in row]
        callbacks = [button["callback_data"] for row in keyboard for button in row]
        self.assertIn("ℹ️ Comprendre l'analyse", labels)
        self.assertIn("📊 Voir les niveaux", labels)
        self.assertIn("🎯 Suivre la prochaine position", labels)
        self.assertIn("details:GOLD", callbacks)
        self.assertIn("levels:GOLD", callbacks)
        self.assertIn("auto:GOLD", callbacks)

    def test_active_trade_keyboard_has_manual_entry_and_exit_controls(self):
        import json
        keyboard = json.loads(align_bot.markup_analyse({"GOLD": {"trade": {"e": 1}}}, "GOLD", {}))["inline_keyboard"]
        callbacks = [button["callback_data"] for row in keyboard for button in row]
        self.assertIn("in:GOLD", callbacks)
        self.assertIn("out:GOLD", callbacks)
        self.assertNotIn("auto:GOLD", callbacks)

    def test_telegram_formatter_splits_compound_information(self):
        message = align_bot.mise_en_forme(
            "ALIGN • GOLD\n"
            "Tendance : haussière • Confirmation : 2/2\n"
            "FVG 15m : haussière | Basse 4 050,00 | Haute 4 060,00"
        )
        self.assertIn("Tendance\nhaussière", message)
        self.assertIn("Confirmation\n2/2", message)
        self.assertIn("Basse\n4050", message)
        self.assertIn("Haute\n4060", message)

    def test_telegram_analysis_layout_is_clear_for_btc_and_gold(self):
        from unittest.mock import patch
        r = {
            "dirs": [1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1],
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
                self.assertIn("UNITÉ 1m\n⬆️", message)
                self.assertIn("RSI 1m\n55", message)
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
        self.assertIn("💰 TP1\n4075,50", payload["text"][0])

    def test_unknown_telegram_callback_never_becomes_manual_exit(self):
        from unittest.mock import patch
        update = {
            "update_id": 9001,
            "callback_query": {
                "id": "cb-unknown",
                "data": "unknown:GOLD",
                "message": {"chat": {"id": 123}},
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
                "message": {"chat": {"id": 123}},
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
                    "message": {"chat": {"id": 123}},
                    "from": {"id": 123}
                }
            }
            with patch.object(align_bot, "autorise", return_value=True), \
                 patch.object(align_bot, "telegram"), \
                 patch.object(align_bot, "repondre") as reply:
                align_bot.traiter({}, set(), [update])
            reply.assert_called_once()
            self.assertEqual(reply.call_args.args[1:], ("123", expected, "GOLD"))

    def test_valid_auto_callback_registers_only_the_requested_market(self):
        from unittest.mock import patch
        update = {
            "update_id": 9012,
            "callback_query": {
                "id": "cb-auto",
                "data": "auto:BTC",
                "message": {"chat": {"id": 123}},
                "from": {"id": 123}
            }
        }
        with patch.object(align_bot, "autorise", return_value=True), \
             patch.object(align_bot, "telegram"), \
             patch.object(align_bot, "inscrire_auto") as register:
            align_bot.traiter({}, set(), [update])
        register.assert_called_once()
        self.assertEqual(register.call_args.args[1:], ("123", "BTC"))

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


    def test_all_analysis_inline_buttons_route_without_silent_failure(self):
        from unittest.mock import patch
        r = {"m1": [candle(1, c=100.0)], "dirs": [0] * 11, "confirme": 0}
        for action in ("details", "levels", "resume", "previous"):
            update = {"update_id": 9100, "callback_query": {
                "id": "cb-" + action, "data": action + ":GOLD",
                "message": {"chat": {"id": 123}}, "from": {"id": 123}
            }}
            with (
                patch.object(align_bot, "autorise", return_value=True),
                patch.dict(align_bot.DERNIERS, {"GOLD": r}),
                patch.object(align_bot, "texte_apercu", return_value="analysis-card"),
                patch.object(align_bot, "texte_etat", return_value="analysis-details"),
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
                "message": {"chat": {"id": 123}}, "from": {"id": 123}
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
                "message": {"chat": {"id": 123}}, "from": {"id": 123}
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
            "message": {"chat": {"id": 123}}, "from": {"id": 123}
        }}
        revoke = {"update_id": 9161, "callback_query": {
            "id": "cb-revoke", "data": "retirer:456",
            "message": {"chat": {"id": 123}}, "from": {"id": 123}
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
            "message": {"chat": {"id": 123}}, "from": {"id": 123}
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

    def test_chronometer_recreates_deleted_telegram_message(self):
        from unittest.mock import patch
        chrono = {"mid": 10, "t0": 1, "maj": 1}
        def telegram_side_effect(method, **kwargs):
            if method == "editMessageText":
                raise RuntimeError("Bad Request: message to edit not found")
            if method == "sendMessage":
                return {"ok": True, "result": {"message_id": 99}}
            raise AssertionError(method)
        with patch.object(align_bot, "telegram", side_effect=telegram_side_effect), \\
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
        with patch.object(align_bot.time, "time", return_value=align_bot.CHRONO_MAX + 2), \\
             patch.object(align_bot, "_editer_chrono_ou_recreer") as edit:
            align_bot.maj_chronos(state, "GOLD", {})
        text = edit.call_args.args[2]
        self.assertIn("\n", text)
        self.assertNotIn("\\n", text)

if __name__ == "__main__":
    unittest.main()
