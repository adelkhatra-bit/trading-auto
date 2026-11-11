import os
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

    def test_strategy_profile_selects_swing_when_h4_h1_m15_align(self):
        dirs = [0] * 11
        dirs[9], dirs[7], dirs[4], dirs[2] = 1, 1, 1, 1
        profile = align_bot.profil_strategie({"dirs": dirs})
        self.assertEqual(profile["mode"], "SWING")
        self.assertTrue(profile["m5_aligne"])
        self.assertFalse(profile["contre_tendance"])

    def test_strategy_profile_selects_intraday_during_m15_pullback(self):
        dirs = [0] * 11
        dirs[9], dirs[7], dirs[4], dirs[2] = 1, 1, -1, 1
        profile = align_bot.profil_strategie({"dirs": dirs})
        self.assertEqual(profile["mode"], "INTRADAY")
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

    def test_tradingview_links_select_market_and_requested_timeframe(self):
        btc = align_bot.url_tradingview("BTC", 5)
        gold = align_bot.url_tradingview("GOLD", 240)
        self.assertIn("KRAKEN%3AXBTUSD", btc)
        self.assertIn("interval=5", btc)
        self.assertIn("FOREXCOM%3AXAUUSD", gold)
        self.assertIn("interval=240", gold)

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
                patch.object(align_bot, "_envoi_sur") as send,
            ):
                align_bot.envoyer_analyse_a(state, "123", market, r, {})
            arm.assert_called_once()
            ai.assert_called_once_with(state, market, r, {}, anglais=False)
            self.assertEqual(send.call_count, 2, market)
            self.assertIn("AI opinion", send.call_args.kwargs["text"])

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
        self.assertEqual([b["callback_data"] for b in fr_buttons], [b["callback_data"] for b in en_buttons])
        self.assertEqual(
            [align_bot.TRAD.get(b["text"], b["text"]) for b in fr_buttons],
            [b["text"] for b in en_buttons],
        )
        self.assertIn("❓ Why this decision?", [b["text"] for b in en_buttons])
        self.assertIn("📊 Full analysis", [b["text"] for b in en_buttons])
        self.assertIn("🎯 Levels / prices", [b["text"] for b in en_buttons])
        self.assertIn("⏱ All timeframes", [b["text"] for b in en_buttons])
        self.assertIn("🗂 Message history", [b["text"] for b in en_buttons])
        self.assertIn("🔔 Follow the next position", [b["text"] for b in en_buttons])

    def test_all_static_telegram_inline_button_labels_have_english_translations(self):
        labels = [
            "🎯 Suivre la prochaine position", "❓ Pourquoi cette décision ?",
            "📊 Analyse complète", "🎯 Niveaux / prix", "⏱ Toutes les unités",
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
        self.assertTrue(send.call_args.kwargs["text"].startswith("🔴 SIGNAL NON CONFIRMÉ"))
        self.assertIn("🚫 N'ENTRE PAS : ATTENDS LE PROCHAIN SIGNAL", send.call_args.kwargs["text"])
        self.assertIn("N'ENTRE PAS", send.call_args.kwargs["text"])
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
        self.assertTrue(msg.startswith("🔴 SIGNAL NON CONFIRMÉ"))
        self.assertLess(msg.index("🔴 SIGNAL NON CONFIRMÉ"), msg.index("🕯 BOUGIE 5m CLÔTURÉE"))
        self.assertIn("BOUGIE 5m CLÔTURÉE", msg)
        self.assertNotIn("CLÔTURE 5m —", msg)
        self.assertIn("N'ENTRE PAS", msg)
        self.assertIn("POURQUOI", msg)
        self.assertIn("CE QUE TU DOIS FAIRE", msg)

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
        self.assertIn("POSITION À VENIR", msg)
        self.assertIn("ordre en attente", msg)
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
        self.assertIn("⏳ PROCHAINE CLÔTURE 1h\n⏱ Temps restant : 60:00\n🕒 Heure prévue : 04:00:00 (heure de Paris)", message)
        formatted = align_bot.mise_en_forme(message)
        self.assertIn("⏱ Temps restant\n60:00", formatted)
        self.assertIn("🕒 Heure prévue\n04:00:00 (heure de Paris)", formatted)

    def test_independent_chronometer_tick_updates_every_market_with_cached_data(self):
        from unittest.mock import patch
        with patch.dict(align_bot.DERNIERS, {"BTC": {"m1": []}, "GOLD": {"m1": []}}, clear=True):
            with patch.object(align_bot, "maj_chronos") as update:
                align_bot.tick_chronos({"BTC": {}, "GOLD": {}})
        self.assertEqual([call.args[1] for call in update.call_args_list], ["BTC", "GOLD"])

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
        self.assertIn("❓ Pourquoi cette décision ?", labels)
        self.assertIn("📊 Analyse complète", labels)
        self.assertIn("🎯 Niveaux / prix", labels)
        self.assertIn("🔔 Suivre la prochaine position", labels)
        self.assertIn("why:GOLD", callbacks)
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
        self.assertIn("Tendance Daily : 🟠➖", message)
        self.assertIn("Confirmation 1 h : 🔴⬇️", message)
        self.assertIn("Préparation 15 min : 🔴⬇️", message)
        self.assertIn("Timing 5 min : 🟢⬆️", message)
        self.assertIn("PROFIL RETENU : SCALPING CONTRE-TENDANCE", message)

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

    def test_valid_auto_callback_registers_only_the_requested_market(self):
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
        callbacks = [button["callback_data"] for row in buttons for button in row]
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
        callbacks = [button["callback_data"] for row in buttons for button in row]
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
        callbacks = [button["callback_data"] for row in buttons for button in row]
        self.assertIn("position:GOLD", callbacks)
        self.assertIn("timeframes:GOLD", callbacks)
        self.assertIn("history:GOLD", callbacks)

    def test_all_timeframe_breakdown_lists_every_calculated_unit_and_strategy_role(self):
        r = {
            "dirs": [1, -1, 1, 0, -1, 1, 0, 1, -1, 1, 1],
            "rsis": [61, 45, 65, 50, 38, 54, 49, 63, 42, 68, 71],
        }
        message = align_bot.texte_timeframes("GOLD", r)
        for label in ("1 min", "2 min", "5 min", "10 min", "15 min", "30 min",
                      "45 min", "1 heure", "2 heures", "4 heures", "Daily"):
            self.assertIn(label, message)
        self.assertIn("4 h : tendance principale", message)
        self.assertIn("1 h : confirmation obligatoire", message)
        self.assertIn("5 min : déclencheur après clôture", message)
        self.assertIn("RSI 68", message)

    def test_all_timeframe_button_is_present_and_callback_is_handled(self):
        import json
        from unittest.mock import patch
        keyboard = json.loads(align_bot.markup_analyse({}, "BTC", {}))["inline_keyboard"]
        callbacks = [button["callback_data"] for row in keyboard for button in row]
        self.assertIn("timeframes:BTC", callbacks)
        update = {"update_id": 9210, "callback_query": {
            "id": "cb-timeframes", "data": "timeframes:BTC",
            "message": {"chat": {"id": 123, "type": "private"}}, "from": {"id": 123}
        }}
        r = {
            "dirs": [1] * 11, "rsis": [55] * 11,
            "m1": [candle(1, c=100.0)], "confirme": 1
        }
        with (
            patch.object(align_bot, "autorise", return_value=True),
            patch.dict(align_bot.DERNIERS, {"BTC": r}),
            patch.object(align_bot, "_envoi_sur") as send,
            patch.object(align_bot, "telegram"),
        ):
            align_bot.traiter({}, set(), [update])
        self.assertIn("TOUTES LES UNITÉS", send.call_args.kwargs["text"])
        self.assertIn("45 min", send.call_args.kwargs["text"])

    def test_compact_analysis_buttons_expose_why_full_analysis_and_levels(self):
        import json
        keyboard = json.loads(align_bot.markup_analyse({}, "BTC", {}))["inline_keyboard"]
        callbacks = [button["callback_data"] for row in keyboard for button in row]
        labels = [button["text"] for row in keyboard for button in row]
        self.assertIn("why:BTC", callbacks)
        self.assertIn("details:BTC", callbacks)
        self.assertIn("levels:BTC", callbacks)
        self.assertIn("Pourquoi cette décision ?", " ".join(labels))
        self.assertIn("Analyse complète", " ".join(labels))
        self.assertIn("Niveaux / prix", " ".join(labels))

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

    def test_candle_close_notification_has_priority_title_and_preserves_every_detail(self):
        from unittest.mock import patch
        dirs = [0] * 11
        dirs[9] = -1
        dirs[7] = -1
        r = {"dirs": dirs, "confirme": -1, "m1": [candle(7200, c=73498.30)]}
        b = candle(7200, o=73444.10, h=73510.0, l=73430.0, c=73498.30)
        with (
            patch.object(align_bot, "verdict", return_value=("🔴🔴 N'ENTRE PAS", "raison technique")),
            patch.object(align_bot, "raison_attente", return_value="La zone Daily/Weekly est extrême : j'attends un meilleur prix."),
            patch.object(align_bot, "prochaine", return_value="Prochaine entrée SHORT"),
            patch.object(align_bot, "heure", return_value="03:00"),
        ):
            raw = align_bot.texte_cloture("BTC", "1h", b, r, {})
        message = align_bot.mise_en_forme(raw)
        lines = message.splitlines()
        self.assertEqual(lines[0], "🔴 SIGNAL NON CONFIRMÉ")
        self.assertIn("🚫 N'ENTRE PAS", message)
        self.assertIn("ATTENDS LE PROCHAIN SIGNAL", message)
        self.assertIn("🕯 BOUGIE 1h CLÔTURÉE", message)
        self.assertIn("🟠 BTC", message)
        for required in ("03:00", "RÉSULTAT DE LA BOUGIE", "haussière", "Ouverture", "73444,10", "Clôture", "73498,30",
                         "TENDANCE MULTI-UNITÉS", "4 h\nSHORT", "Confirmation 1 h\nSHORT", "2/2", "DÉCISION ALIGN",
                         "N'ENTRE PAS", "POURQUOI", "La zone Daily/Weekly est extrême", "j'attends un meilleur prix", "PROCHAINE ÉTAPE",
                         "Prochaine entrée SHORT", "Une clôture seule ne déclenche pas une entrée", "Aucun ordre n'est envoyé à ton broker"):
            self.assertIn(required, message)


    def test_candle_close_alert_is_translated_for_english_users(self):
        from unittest.mock import patch
        dirs = [0] * 11
        r = {"dirs": dirs, "confirme": 0, "m1": [candle(7200, c=100.0)]}
        b = candle(7200, o=99.0, h=101.0, l=98.0, c=100.0)
        with (
            patch.object(align_bot, "verdict", return_value=("🔴🔴 N'ENTRE PAS", "Conditions insuffisantes")),
            patch.object(align_bot, "raison_attente", return_value="Attendre la confirmation."),
            patch.object(align_bot, "prochaine", return_value="Prochaine entrée LONG"),
            patch.object(align_bot, "heure", return_value="03:00"),
        ):
            raw = align_bot.texte_cloture("BTC", "5m", b, r, {})
        translated = align_bot.traduire(raw)
        self.assertEqual(translated.splitlines()[0], "🔴 SIGNAL NOT CONFIRMED")
        self.assertEqual(translated.splitlines()[1], "🚫 DON'T ENTER: WAIT FOR THE NEXT SIGNAL")
        for expected in ("CANDLE RESULT", "Open:", "Close:", "MULTI-TIMEFRAME TREND",
                         "ALIGN DECISION", "WHY", "NEXT STEP", "IMPORTANT",
                         "A candle close alone does not trigger an entry.",
                         "No order is sent to your broker."):
            self.assertIn(expected, translated)

    def test_candle_close_titles_support_all_watched_timeframes(self):
        from unittest.mock import patch
        dirs = [0] * 11
        r = {"dirs": dirs, "confirme": 0, "m1": [candle(7200, c=100.0)]}
        b = candle(7200, o=99.0, h=101.0, l=98.0, c=100.0)
        with (
            patch.object(align_bot, "verdict", return_value=("🔴🔴 N'ENTRE PAS", "Conditions insuffisantes")),
            patch.object(align_bot, "raison_attente", return_value="Attendre."),
            patch.object(align_bot, "prochaine", return_value="Prochaine entrée"),
            patch.object(align_bot, "heure", return_value="03:00"),
        ):
            for tf in ("5m", "15m", "1h", "4h", "D", "W"):
                message = align_bot.texte_cloture("BTC", tf, b, r, {})
                self.assertEqual(message.splitlines()[0], "🔴 SIGNAL NON CONFIRMÉ")
                self.assertEqual(message.splitlines()[1], "🚫 N'ENTRE PAS : ATTENDS LE PROCHAIN SIGNAL")
                self.assertIn(f"🕯 BOUGIE {tf} CLÔTURÉE", message)

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
        self.assertEqual(message.splitlines()[0], "🟢 SIGNAL CONFIRMÉ")
        self.assertEqual(message.splitlines()[1], "🟢 SIGNAL D'ENTRÉE VALIDÉ : VÉRIFIE LES NIVEAUX")
        self.assertNotIn("SIGNAL NON CONFIRMÉ", message)

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

