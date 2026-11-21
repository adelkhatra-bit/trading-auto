"""Regression tests for the bottom-positioned ALIGN live controls."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
LIVE_JS = ROOT.parent / "docs" / "live" / "align-bande-live.user.js"


class LiveVoiceDisplayLanguage(unittest.TestCase):
    def test_voice_and_animation_controls_are_positioned_at_chart_bottom(self):
        source = LIVE_JS.read_text(encoding="utf-8")
        self.assertIn("id = 'align-live-voice'", source)
        self.assertIn("left:18px;bottom:20px", source)
        self.assertIn("id = 'align-live-animations'", source)
        self.assertIn("left:18px;bottom:72px", source)

    def test_all_live_controls_share_a_collapsible_bottom_dock(self):
        source = LIVE_JS.read_text(encoding="utf-8")
        self.assertIn("align-live-controls-dock", source)
        self.assertIn("align-live-controls-items", source)
        self.assertIn("align-live-controls-toggle", source)
        self.assertIn("left:16px!important;right:auto!important", source)
        self.assertIn("justify-content:flex-start!important", source)
        self.assertNotIn("right:16px!important", source)
        self.assertIn("bottom:16px!important", source)
        self.assertIn("top:auto!important", source)
        self.assertIn("controlsDockItems.appendChild(button)", source)
        self.assertIn("localStorage.setItem('alignControlsDockCollapsed'", source)
        self.assertIn("Afficher les commandes ALIGN", source)
        self.assertIn("controlsDock.remove()", source)

    def test_animation_off_hides_visuals_without_pausing_or_disabling_them(self):
        source = LIVE_JS.read_text(encoding="utf-8")
        start = source.index("const cssAnimationsToggle = document.createElement('style');")
        end = source.index("document.head.appendChild(cssAnimationsToggle);", start)
        toggle_css = source[start:end]
        self.assertIn("visibility:hidden!important", toggle_css)
        self.assertIn("#align-chrono", toggle_css)
        self.assertIn("#align-pnl", toggle_css)
        self.assertIn("#align-etiq", toggle_css)
        self.assertNotIn("animation:none", toggle_css)
        self.assertNotIn("transition:none", toggle_css)
        self.assertNotIn(".pause()", source)
        self.assertIn("localStorage.setItem('alignAnimationsEnabled'", source)

    def test_voice_is_optional_and_reads_french_live_comments(self):
        source = LIVE_JS.read_text(encoding="utf-8")
        self.assertIn("function parlerLive(item, forcer = false)", source)
        self.assertIn("if (!voixActive || !item", source)
        self.assertIn("const voixDuree = parlerLive(m);", source)
        self.assertIn("item.source !== 'ia'", source)
        self.assertIn("Math.max(4000, (W + w) / 0.38, voixDuree)", source)
        self.assertIn("window.speechSynthesis.speak(utterance)", source)

    def test_animation_off_hides_visuals_without_pausing_runtime(self):
        source = LIVE_JS.read_text(encoding="utf-8")
        self.assertIn("visibility:hidden!important", source)
        self.assertIn("align-animations-off #align-bande", source)
        self.assertNotIn("a.pause()", source)
        self.assertNotIn("animCur.pause()", source)
        self.assertIn("timerCur = setTimeout", source)
        self.assertIn("function appliquerAnimations()", source)


if __name__ == "__main__":
    unittest.main()
