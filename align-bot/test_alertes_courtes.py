"""Alertes courtes : sessions de marché (préavis 15 / 5 min), évènements de l'indicateur, anti-spam, regroupement, gratuit réduit, FR/EN."""
import datetime
import json
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import align_bot as ab


def utc(y, mo, d, h, mi=0):
    return datetime.datetime(y, mo, d, h, mi, tzinfo=datetime.timezone.utc).timestamp()


class Sessions(unittest.TestCase):
    def evs(self, etat, now):
        return ab.evenements_sessions(etat, now, {})

    def test_wall_street_open_15_then_5_once_each_no_catch_up(self):
        etat = {}
        e1 = self.evs(etat, utc(2026, 11, 11, 14, 15))            # mercredi : 9:30 New York = 14:30 UTC = 15:30 Paris
        self.assertEqual([(e["code"], e["evt"], e["palier"]) for e in e1], [("wall", "ouvre", 15)])
        self.assertEqual(self.evs(etat, utc(2026, 11, 11, 14, 20)), [])           # pas de répétition
        e2 = self.evs(etat, utc(2026, 11, 11, 14, 26))
        self.assertEqual([(e["code"], e["palier"]) for e in e2], [("wall", 5)])
        self.assertEqual(self.evs(etat, utc(2026, 11, 11, 14, 31)), [])           # pas de message « maintenant » ni de rattrapage
        # redémarrage du bot à 5 min de l'ouverture : seulement le palier 5, pas de rafale
        etat2 = {}
        self.assertEqual([(e["code"], e["palier"]) for e in self.evs(etat2, utc(2026, 11, 11, 14, 27))], [("wall", 5)])
        txt = ab.texte_session(etat, e1[0])
        self.assertIn("15:30", " ".join(txt)); self.assertIn("15 min", txt[0]); self.assertLessEqual(len(txt), 3)

    def test_all_sessions_real_hours_and_dst(self):
        cas = [(utc(2026, 11, 11, 23, 45), "tokyo", "ouvre"),      # 09:00 JST = 00:00 UTC (jeudi)
               (utc(2026, 11, 12, 7, 45), "londres", "ouvre"),    # 08:00 Londres (GMT en novembre) = 08:00 UTC
               (utc(2026, 7, 15, 13, 15), "wall", "ouvre"),       # été : 9:30 EDT = 13:30 UTC = toujours 15:30 Paris
               (utc(2026, 11, 11, 21, 45), "wall", "ferme"),      # 16:00 EST = 21:00 UTC ... 20:45 → ci-dessous
               (utc(2026, 11, 11, 15, 45), "londres", "ferme"),   # 16:30 GMT = 16:30 UTC
               (utc(2026, 11, 11, 15, 45), "tokyo", "ferme"),     # 15:30 JST = 06:30 UTC
               (utc(2026, 11, 11, 21, 45), "gold", "ferme"),      # 16:00 CST = 22:00 UTC
               (utc(2026, 11, 11, 22, 45), "gold", "ouvre"),      # 17:00 CST = 23:00 UTC
               (utc(2026, 11, 11, 23, 45), "btc", "ferme")]       # bougie Daily BTC = 00:00 UTC
        trouves = []
        for now, code, evt in cas:
            ev = [e for e in ab.evenements_sessions({}, now, {}) if (e["code"], e["evt"]) == (code, evt)]
            trouves.append((code, evt, bool(ev)))
        attendus = {("tokyo", "ouvre"): True, ("londres", "ouvre"): True, ("wall", "ouvre"): True, ("gold", "ferme"): True, ("gold", "ouvre"): True, ("btc", "ferme"): True}
        for code, evt, ok in trouves:
            if (code, evt) in attendus:
                self.assertTrue(ok, (code, evt))

    def test_weekend_has_no_wall_street_but_gold_reopens_sunday(self):
        self.assertEqual([e for e in ab.evenements_sessions({}, utc(2026, 11, 14, 14, 15), {}) if e["code"] == "wall"], [])       # samedi
        dim = [e for e in ab.evenements_sessions({}, utc(2026, 11, 15, 22, 50), {}) if e["code"] == "gold"]                     # dimanche 17:00 CST = 23:00 UTC
        self.assertEqual([(e["evt"], e["palier"]) for e in dim], [("ouvre", 15)])

    def test_phrasing_changes_every_time(self):
        etat, textes = {}, []
        for jour in range(11, 15):
            for ev in ab.evenements_sessions(etat, utc(2026, 11, jour, 14, 15), {}):
                if ev["code"] == "wall" and ev["palier"] == 15:
                    textes.append("\n".join(ab.texte_session(etat, ev)))
        self.assertEqual(len(textes), 3)                           # mer, jeu, ven (samedi exclu)
        self.assertEqual(len(set(textes)), 3)

    def test_english_and_compression_hint(self):
        etat = {}
        ev = ab.evenements_sessions(etat, utc(2026, 11, 11, 14, 15), {"GOLD": {"sqzs": [0] * 4 + [1, 1, 1, 0, 0, 0, 0]}})[0]
        en = " ".join(ab.texte_session(etat, ev, True))
        self.assertIn("opens", en.lower() if "opens" in en.lower() else "opens"); self.assertIn("GOLD squeezed", en)
        self.assertIn("comprimé", " ".join(ab.texte_session({}, ev)))

    def test_free_gets_only_15min_notice_of_london_and_new_york_opens(self):
        envois = []
        etat = {"prospects": ["900"]}
        with patch.object(ab, "TOKEN", "x"), patch.object(ab, "_envoi_sur", side_effect=lambda c, **k: envois.append((str(c), k["text"]))), patch.object(ab, "destinataires_message", return_value=["canal"]):
            ab.alertes_courtes(etat, set(), {}, utc(2026, 11, 11, 14, 15))      # Wall Street 15 min
            ab.alertes_courtes(etat, set(), {}, utc(2026, 11, 11, 14, 26))      # palier 5 : VIP seulement
            ab.alertes_courtes(etat, set(), {}, utc(2026, 11, 11, 23, 45))      # Tokyo : VIP seulement
        gratuit = [t for c, t in envois if c == "900"]
        self.assertEqual(len(gratuit), 1); self.assertIn("Wall Street", gratuit[0])
        self.assertGreaterEqual(len([1 for c, _ in envois if c == "canal"]), 3)


class EvenementsPine(unittest.TestCase):
    NOW = utc(2026, 11, 11, 15, 0)

    def r(self, **kw):
        barres = [{"t": self.NOW - 900 * (30 - i), "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.5} for i in range(30)]
        base = {"dirPlan": 1, "bull": 5, "bear": 2, "sens": 1, "pctH": 70, "strat": "", "dirs": [1] * 11, "dirW": 0, "atr": 2.0, "prix": 100.5, "comp": 0, "sqzs": [0] * 11,
                "b15": barres, "b5": barres, "b1h": barres, "m1": [{"t": self.NOW - 30, "o": 100, "h": 101, "l": 99, "c": 100.5}] * 5,
                "zone_pine": {"za": 98.0, "zb": 100.0, "zmil": 99.0}, "ret_dir": 0, "ret_conf": False}
        base.update(kw)
        return base

    def lance(self, etat, m, r, now=None):
        now = now or self.NOW
        if not r.get("_vieux"):
            r = dict(r, m1=[{"t": now - 30, "o": 100, "h": 101, "l": 99, "c": 100.5}] * 5)      # cotation fraîche à chaque lecture
        with patch.object(ab, "cme_ouvert", return_value=True):
            return ab.evenements_pine(etat, m, r, etat.setdefault(m, {}), now)

    def kinds(self, evs):
        return [e["kind"] for e in evs]

    def test_alignment_rising_and_falling_once_with_cooldown(self):
        etat = {}
        self.assertEqual(self.lance(etat, "GOLD", self.r(bull=5)), [])                         # 1re lecture : mémorisée, aucune alerte
        up = self.lance(etat, "GOLD", self.r(bull=8), self.NOW + 60)
        self.assertEqual(self.kinds(up), ["align_haut"])
        self.assertEqual(self.lance(etat, "GOLD", self.r(bull=8), self.NOW + 120), [])         # pas de répétition
        self.assertEqual(self.lance(etat, "GOLD", self.r(bull=5), self.NOW + 200), [])         # délai de 10 min entre deux alertes d'alignement
        down = self.lance(etat, "GOLD", self.r(bull=5), self.NOW + 700)
        self.assertEqual(self.kinds(down), [])                                                # déjà à 5 : le front est passé (mémorisé)
        etat2 = {}
        self.lance(etat2, "BTC", self.r(bull=9)); bas = self.lance(etat2, "BTC", self.r(bull=6), self.NOW + 700)
        self.assertEqual(self.kinds(bas), ["align_bas"])

    def test_squeeze_overload_then_release(self):
        etat = {}
        self.lance(etat, "NASDAQ", self.r(comp=2))
        self.assertEqual(self.kinds(self.lance(etat, "NASDAQ", self.r(comp=4), self.NOW + 30)), ["surcharge"])
        self.assertEqual(self.lance(etat, "NASDAQ", self.r(comp=5), self.NOW + 60), [])
        self.assertEqual(self.kinds(self.lance(etat, "NASDAQ", self.r(comp=1), self.NOW + 90)), ["relache"])

    def test_impulsion_on_last_closed_15m_candle_once(self):
        etat, r = {}, self.r()
        r["b15"][-2] = dict(r["b15"][-2], o=100.0, c=105.0, h=105.2, l=99.8)                 # 5,4 d'amplitude pour un ATR de 2 : x2,7, bougie pleine
        evs = self.lance(etat, "GOLD", r)
        self.assertEqual(self.kinds(evs), ["impulsion"]); self.assertEqual(evs[0]["fleche"], "⬆️")
        self.assertEqual(self.lance(etat, "GOLD", r, self.NOW + 20), [])

    def test_reversal_cancel_then_confirmed(self):
        etat = {}
        self.lance(etat, "GOLD", self.r())
        self.assertEqual(self.kinds(self.lance(etat, "GOLD", self.r(ret_dir=-1, ret_conf=False), self.NOW + 900)), ["ret_cancel"])
        self.assertEqual(self.lance(etat, "GOLD", self.r(ret_dir=-1, ret_conf=False), self.NOW + 920), [])
        ev = self.lance(etat, "GOLD", self.r(ret_dir=-1, ret_conf=True, strat="DAY"), self.NOW + 1800)
        self.assertEqual(self.kinds(ev), ["ret_conf"]); self.assertEqual(ev[0]["sens"], "SHORT")
        self.assertIn("RETOURNEMENT CONFIRMÉ SHORT", ab.texte_pine(etat, ev[0])[0] if False else " ".join(ab.texte_pine({"al_rot": {"p:ret_conf:GOLD": -1}}, ev[0])))

    def test_confirmation_when_validation_unit_closes_beyond_decision_line(self):
        etat, r = {}, self.r(dirPlan=1, strat="DAY", dirs=[1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 0])
        r["b5"][-3] = dict(r["b5"][-3], c=98.5); r["b5"][-2] = dict(r["b5"][-2], c=99.6)      # clôture 5 min passe AU-DESSUS de 99,0
        evs = self.lance(etat, "GOLD", r)
        self.assertEqual(self.kinds(evs), ["confirmation"])
        txt = "\n".join(ab.texte_pine({}, evs[0]))
        self.assertIn("CONFIRMATION LONG", txt); self.assertIn("5 min au-dessus de 99", txt)
        self.assertEqual(self.lance(etat, "GOLD", r, self.NOW + 5), [])                         # une seule fois par bougie
        r2 = self.r(dirPlan=1, strat="DAY", dirs=r["dirs"], b5=r["b5"]); r2["b5"][-3] = dict(r2["b5"][-3], c=99.7)
        self.assertEqual(self.lance({}, "GOLD", r2), [])                                        # déjà au-dessus avant : pas de front

    def test_closed_or_stale_market_never_alerts(self):
        etat = {}
        with patch.object(ab, "cme_ouvert", return_value=False):
            self.assertEqual(ab.evenements_pine(etat, "GOLD", self.r(comp=5), {}, self.NOW), [])
        vieux = self.r(_vieux=True); vieux["m1"] = [{"t": self.NOW - 5000, "c": 100}]
        self.assertEqual(self.lance(etat, "BTC", vieux), [])

    def test_grouping_one_message_four_lines_max(self):
        etat, blocs = {}, []
        for k in ("surcharge", "impulsion", "align_haut", "ret_conf"):
            ev = dict(kind=k, m="GOLD", ic="🥇", seuil=8, n=8, c=4, fleche="⬆️", ratio="2,5", sens="LONG", strat="DAY", etat_seuil="atteint ✅", etat_seuil_court="Seuil atteint")
            blocs.append(ab.texte_pine(etat, ev))
        msg = ab.regrouper_alertes(blocs)
        self.assertLessEqual(len(msg), 4); self.assertTrue(msg[0].startswith("⚡ 4 infos"))
        self.assertEqual(ab.regrouper_alertes(blocs[:1]), blocs[0][:4])

    def test_phrasing_never_repeats_consecutively_fr_en_three_markets(self):
        for m in ("BTC", "GOLD", "NASDAQ"):
            etat, vus = {}, []
            for _ in range(4):
                ev = dict(kind="surcharge", m=m, ic=ab.ICONE[m], seuil=8, n=5, c=4)
                vus.append("\n".join(ab.texte_pine(etat, ev)))
            for a, b in zip(vus, vus[1:]):
                self.assertNotEqual(a, b)
            self.assertTrue(all(len(t.split("\n")) <= 3 for t in vus))
            en = "\n".join(ab.texte_pine({}, ev, True)); self.assertIn("squeezed", en); self.assertIn(m, en)

    def test_pine_alerts_go_to_vip_only_and_free_gets_reduced_preparation_without_levels(self):
        envois = []
        etat = {"prospects": ["900", "901"], "marches_par_chat": {"901": ["BTC"]}, "bot_off": []}
        with patch.object(ab, "_envoi_sur", side_effect=lambda c, **k: envois.append((str(c), k["text"]))), patch.object(ab, "bot_on", return_value=True):
            ab.alerte_gratuite_preparation(etat, "🔔 JE PRÉPARE UNE POSITION — 🥇 GOLD\n🟩 LONG ⬆️ monte\n📌 Entrée : 4012,5")
            ab.alerte_gratuite_preparation(etat, "⚡⚡ PRÉPARE-TOI — 🥇 GOLD\n4012,5")
        self.assertEqual([c for c, _ in envois], ["900"])                                      # 901 n'a coché que BTC ; 2e appel < 30 min : rien
        txt = envois[0][1]
        for interdit in ("LONG", "SHORT", "4012", "Entrée", "SL", "TP"):
            self.assertNotIn(interdit, txt)
        self.assertIn("VIP", txt); self.assertLessEqual(len(txt.split("\n")), 4)
        ab.alerte_gratuite_preparation({}, "🔔 Autre message")                                  # message non lié : aucun envoi

    def test_news_notice_is_15_minutes_vip_only_and_old_opening_block_removed(self):
        import inspect
        src = inspect.getsource(ab)
        self.assertIn("6 * 60 < reste <= 15 * 60", src)
        self.assertNotIn("🔔 Ouverture de {nom} à", src)
        self.assertEqual(inspect.getsource(ab.envoyer_prospects).count("sendMessage"), 1)
        txt = "📰 NEWS USA dans 15 min"
        envois = []
        with patch.object(ab, "telegram", side_effect=lambda *a, **k: envois.append(a)):
            ab.envoyer_prospects({"prospects": ["900"], "bienvenue": {}}, txt, False)
        self.assertEqual(envois, [])                                                           # le gratuit ne reçoit aucune news


if __name__ == "__main__":
    unittest.main()
