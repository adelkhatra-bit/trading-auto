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
        self.assertIn("🟨 Entrée : 100.00", message)
        self.assertIn("🛑 Stop Loss : 98.00", message)
        self.assertIn("💰 TP1 : 104.00", message)
        self.assertIn("🏁 TP2 : 108.00", message)
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
        self.assertIn("🛑 Stop Loss : 102.00", message)
        self.assertIn("🏁 TP2 : 92.00", message)

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
self.assertIn("🕒 1m ⬆️", message)
                self.assertIn("📈 RSI : 1m 55", message)
self.assertIn("🧭 CONFIRMATION DE TENDANCE", message)
                self.assertIn("Alignement 1h + 4h", message)
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

if __name__ == "__main__":
    unittest.main()
