"""Régression : Fibonacci réservé à l'intelligence du commentateur live, sans nouvel indicateur graphique ni message Telegram."""
from pathlib import Path
import re
import unittest
from unittest import mock

import align_bot as ab

ROOT = Path(__file__).resolve().parent
PINE = ROOT / "pine" / "ALIGN_MTF_PRO_v24.pine"
BOT = ROOT / "align_bot.py"
LIVE_JS = ROOT.parent / "docs" / "live" / "align-bande-live.user.js"


def mouvement_hausse(n=48):
    return [
        dict(t=i, o=100 + i * 100 / (n - 1), h=100 + i * 100 / (n - 1),
             l=100 + i * 100 / (n - 1), c=100 + i * 100 / (n - 1), v=10)
        for i in range(n)
    ]


class FibonacciCommentateurLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pine = PINE.read_text(encoding="utf-8")
        cls.bot = BOT.read_text(encoding="utf-8")
        cls.js = LIVE_JS.read_text(encoding="utf-8")

    def test_no_new_fibonacci_indicator_is_added_to_the_chart(self):
        self.assertIn("voirFibo = input.bool(true, \"Zone d'entrée + Fibonacci\"", self.pine)
        self.assertNotIn("voirFiboProgression", self.pine)
        self.assertNotIn("FIBO —", self.pine)
        self.assertFalse((ROOT / "pine" / "ALIGN_MTF_PRO_v24_5_FIBO_PROPOSITION.pine").exists())
        self.assertNotIn("request.security(", self.bot)

    def test_existing_pine_entry_zone_is_preserved(self):
        self.assertIn("def zone_pine(", self.bot)
        self.assertIn("f50, f618, f786", self.bot)
        self.assertIn("def pine_entree(", self.bot)
        self.assertIn('src="Fibonacci 50 → 78,6 % (indicateur ALIGN)"', self.bot)

    def test_fibonacci_is_internal_live_context_not_a_telegram_alert(self):
        self.assertIn("def progression_fibonacci_live(r, market=None):", self.bot)
        self.assertIn("def contexte_technique_live(derniers):", self.bot)
        self.assertIn("def live_phrases_ia(etat, maintenant, derniers=None):", self.bot)
        self.assertNotIn("def fibo_zones(", self.bot)
        self.assertNotIn("ZONE FIBONACCI —", self.bot)

    def test_existing_bars_are_reused_without_new_market_requests(self):
        self.assertIn("b15_long=m15[-90:]", self.bot)
        self.assertIn("b1h_long=h1[-60:]", self.bot)
        self.assertIn("b4h_long=h4[-40:]", self.bot)
        self.assertEqual(self.bot.count("live_phrases_ia(etat, int(time.time()), derniers)"), 1)

    def test_fibonacci_retracement_is_calculated_from_closed_m15_bars(self):
        bars = mouvement_hausse(48)
        bars.append(dict(t=49, o=132, h=133, l=131, c=132, v=10))
        r = {"m1": [dict(c=132)], "b15_long": bars}
        result = ab.progression_fibonacci_live(r, "GOLD")
        self.assertAlmostEqual(result["M15"]["retracement_pct"], 68.0, places=1)
        self.assertTrue(result["M15"]["zone_cle_61_8_78_6"])
        self.assertEqual(result["M15"]["fenetre_bougies_cloturees"], 48)

    def test_live_ai_receives_market_context_and_publishes_market_scoped_phrases(self):
        r = {
            "m1": [dict(c=132)],
            "b15_long": mouvement_hausse(48) + [dict(t=49, o=132, h=133, l=131, c=132, v=10)],
            "dirs": [1] * 11, "dirPlan": 1, "strat": "SWING", "rC": 54,
        }
        brut = ("GOLD | Le retracement Fibonacci teste une zone profonde, la tendance reste à confirmer | "
                "The Fibonacci pullback tests a deep zone, trend confirmation is still needed")
        with mock.patch.object(ab, "live_actif", return_value=True), \
             mock.patch.object(ab, "ia", return_value=brut) as ia_mock, \
             mock.patch.object(ab, "live_publier", return_value=True) as publish_mock:
            state = {}
            self.assertTrue(ab.live_phrases_ia(state, 10000, {"GOLD": r}))
        donnees = ia_mock.call_args.args[2]
        self.assertIn("fibonacci", donnees["marches"]["GOLD"])
        self.assertIn("GOLD", publish_mock.call_args.args[0])
        self.assertNotIn("ZONE FIBONACCI", publish_mock.call_args.args[0])

    def test_gold_nasdaq_use_latest_equal_extreme_but_btc_keeps_legacy_direction(self):
        bars = [dict(t=i, o=150, h=180, l=120, c=150, v=10) for i in range(49)]
        bars[5]["l"] = 100
        bars[10]["h"] = 200
        bars[45]["h"] = 200
        bars[46]["l"] = 100
        r = {"m1": [dict(c=168)], "b15_long": bars}
        gold = ab.progression_fibonacci_live(r, "GOLD")["M15"]
        btc = ab.progression_fibonacci_live(r, "BTC")["M15"]
        self.assertEqual(gold["mouvement"], "baisse")
        self.assertAlmostEqual(gold["retracement_pct"], 68.0, places=1)
        self.assertEqual(btc["mouvement"], "hausse")
        self.assertAlmostEqual(btc["retracement_pct"], 32.0, places=1)

    def test_gold_nasdaq_wait_for_full_lookback_and_skip_ambiguous_single_bar_swing(self):
        partial = mouvement_hausse(20) + [dict(t=20, o=132, h=133, l=131, c=132, v=10)]
        r = {"m1": [dict(c=132)], "b15_long": partial}
        self.assertNotIn("M15", ab.progression_fibonacci_live(r, "GOLD"))
        self.assertIn("M15", ab.progression_fibonacci_live(r, "BTC"))

        ambiguous = [dict(t=i, o=150, h=180, l=120, c=150, v=10) for i in range(49)]
        ambiguous[20]["h"] = 220
        ambiguous[20]["l"] = 80
        r["b15_long"] = ambiguous
        self.assertNotIn("M15", ab.progression_fibonacci_live(r, "NASDAQ"))

    def test_btc_does_not_receive_new_fibonacci_context(self):
        r = {"m1": [dict(c=132)], "b15_long": mouvement_hausse(48) + [dict(t=49, o=132, h=133, l=131, c=132, v=10)],
             "dirs": [1] * 11, "dirPlan": 1, "strat": "SWING", "rC": 54}
        context = ab.contexte_technique_live({"BTC": r})
        self.assertNotIn("fibonacci", context["marches"]["BTC"])

    def test_market_specific_live_phrases_are_filtered_and_clean(self):
        brut = (
            "BTC | Le retracement Fibonacci approche une zone de réaction | The Fibonacci pullback approaches a reaction zone\n"
            "GOLD | Les acheteurs défendent leur support après un repli | Buyers defend support after a pullback\n"
            "NASDAQ | Le marché attend une confirmation des unités longues | The market awaits higher timeframe confirmation"
        )
        result = ab.phrases_bande_par_marche(brut)
        self.assertEqual(set(result), {"BTC", "GOLD"})
        self.assertEqual(len(result["BTC"]), 1)
        self.assertNotIn("BTC", ab.phrases_bande_par_marche(
            "BTC | Le retracement est à 68 % | The retracement is 68 %"
        ))

    def test_live_script_selects_commentary_for_the_current_market_without_visual_changes(self):
        self.assertIn("iaPools[codeMarche()]", self.js)
        self.assertIn("const pool = Object.keys(iaPools).length ? (iaPools[m] || []) : iaPool", self.js)
        self.assertIn("afficherIA(pool[iaN++ % pool.length])", self.js)
        self.assertIn("voixBtn.addEventListener", self.js)
        self.assertIn("if (!voixActive", self.js)
        self.assertIn("speechSynthesis.speak(utterance)", self.js)
        self.assertNotIn("voirFiboProgression", self.js)
        self.assertIn("@updateURL    https://raw.githubusercontent.com/adelkhatra-bit/trading-align-/main/docs/live/align-bande-live.user.js", self.js)
        self.assertIn("@downloadURL  https://raw.githubusercontent.com/adelkhatra-bit/trading-align-/main/docs/live/align-bande-live.user.js", self.js)
        header_version = re.search(r"^// @version\s+(\d+\.\d+\.\d+)$", self.js, re.MULTILINE)
        runtime_version = re.search(r"""const VERSION = [\'"](\d+\.\d+\.\d+)[\'"]""", self.js)
        self.assertIsNotNone(header_version, "Userscript metadata version must exist")
        self.assertIsNotNone(runtime_version, "Runtime version must exist")
        self.assertEqual(header_version.group(1), runtime_version.group(1))
        self.assertIn("live-data/live.json", self.js)
        self.assertIn("10 * 60 * 1000", self.js)
        self.assertIn("synchroniserEtatBot()", self.js)
        vue_start = self.js.index("function vueTxt()")
        vue_txt = self.js[vue_start:self.js.index("let vueVue", vue_start)]
        self.assertIn("try {", vue_txt)
        self.assertIn("catch (e) {", vue_txt)
        self.assertIn("typeof c.resolution !== 'function'", vue_txt)
        self.assertIn("item.etat === 'entree'", self.js)
        # v12.2.7 (règle d'Adel) : chaque info dite en français PUIS en anglais, jamais d'anglais orphelin.
        self.assertIn("const anglais = !!item.en;", self.js)
        self.assertIn("if (anglais && !suiteAnglaise && !forcer) return 0;", self.js)
        self.assertIn("source: source || 'live'", self.js)
        self.assertIn("montrer('🧠 ' + phrase, false, 2, 'membre', false, 'ia');", self.js)
        self.assertIn("item.source !== 'ia'", self.js)
        self.assertIn("if (!anglais && maintenant - voixDerniere < 12000 && !forcer) return 0;", self.js)
        self.assertIn("const voixDuree = parlerLive(m);", self.js)
        self.assertIn("Math.max(4000, (W + w) / 0.38, voixDuree)", self.js)
        self.assertIn("left:16px!important;right:auto!important", self.js)
        self.assertIn("justify-content:flex-start!important", self.js)
        self.assertIn("if (anglais && !suiteAnglaise && !forcer) return 0;", self.js)
        self.assertIn("POSITION ALIGN CONFIRMÉE", self.js[self.js.index("function botSuivi"):self.js.index("function synchroniserEtatBot")])
        self.assertIn("telegram", self.js[self.js.index("function sansPrix"):self.js.index("function montrer")])
        self.assertIn("Tu veux savoir si le feu vert est confirmé ?", self.bot)
        self.assertIn("ne cours pas après un mouvement déjà parti", self.bot)
        self.assertIn("POSITION ALIGN ACTIVE SUR", self.js)
        self.assertIn("clearInterval(botEtatSyncT)", self.js)
        self.assertIn("attends la confirmation, ne cours pas après le prix", self.js)
        self.assertIn("wait for confirmation, never chase price", self.js)
        for ancien in ("dépêche-toi", "retardataires", "hurry", "latecomers", "DÉPÊCHE-TOI", "HURRY:", "LIEN EN BIO, VITE !", "C'EST MAINTENANT !", "IT'S NOW!", "too late to get in", "too late to jump on"):
            self.assertNotIn(ancien.lower(), self.js.lower())


if __name__ == "__main__":
    unittest.main()
