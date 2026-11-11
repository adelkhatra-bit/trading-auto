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


    def test_next_candle_close_is_strictly_in_the_future(self):
        self.assertEqual(align_bot.prochaine_cloture(601, 300), 900)
        self.assertEqual(align_bot.prochaine_cloture(899, 300), 900)
        self.assertEqual(align_bot.prochaine_cloture(900, 300), 1200)
        self.assertGreater(align_bot.prochaine_cloture(1000, 300), 1000)
        with self.assertRaises(ValueError):
            align_bot.prochaine_cloture(1000, 0)

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
        self.assertIn("🟨 Entrée : 100,00", message)
        self.assertIn("🛑 Stop Loss : 98,00", message)
        self.assertIn("💰 TP1 : 104,00", message)
        self.assertIn("🏁 TP2 : 108,00", message)
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
        self.assertIn("🛑 Stop Loss : 102,00", message)
        self.assertIn("🏁 TP2 : 92,00", message)

    def test_telegram_price_levels_render_value_before_explanation(self):
        message = align_bot.mise_en_forme(
            "PLAN\n💰 TP1 ≈ 4 075,50 (ancienne mèche haute — bougie 15 minutes)\n"
            "🛑 Stop Loss : 4 020,00 (sous la mèche basse — bougie 15 minutes)\n"
            "📌 Entrée : 4 050,00"
        )
        self.assertIn("💰 TP1\n4075,50\nancienne mèche haute — bougie 15 minutes", message)
        self.assertIn("🛑 Stop Loss\n4020,00\nsous la mèche basse — bougie 15 minutes", message)
        self.assertIn("📌 Entrée\n4050,00", message)

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
        self.assertIn("📌 Entrée\n4000,00", message)
        self.assertNotIn("4 075", message)
        self.assertNotIn("4 000", message)

    def test_price_helper_uses_french_decimal_without_thousands_separator(self):
        self.assertEqual(align_bot.px(4075.5), "4075,50")
        self.assertEqual(align_bot.px(4000), "4000,00")

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

    def test_chronometer_edits_again_on_the_next_second(self):
        from unittest.mock import patch
        state = {"chrono": {"GOLD": {"123": {"mid": 9, "t0": 1}}}, "GOLD": {}}
        with patch.object(align_bot.time, "time", side_effect=[100.1, 101.1]), \
             patch.object(align_bot, "chrono_txt", side_effect=["tick-100", "tick-101"]), \
             patch.object(align_bot, "telegram") as send:
            align_bot.maj_chronos(state, "GOLD", {})
            align_bot.maj_chronos(state, "GOLD", {})
        self.assertEqual(send.call_count, 2)
        self.assertEqual(send.call_args_list[0].kwargs["text"], "tick-100")
        self.assertEqual(send.call_args_list[1].kwargs["text"], "tick-101")

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
        self.assertIn("Basse\n4050,00", message)
        self.assertIn("Haute\n4060,00", message)

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
                self.assertIn("67500.00", message)
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

if __name__ == "__main__":
    unittest.main()
