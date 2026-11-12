"""RADAR ALIGN : un seul message par personne, édité sur place ; cassures fusionnées ; news réservées au VIP."""
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import align_bot as ab


def props_test():
    return [
        dict(m="GOLD", prix=3995.0, atr_n=0.8, classe="proche", rang=1, d=-1, za=3990.05, zb=4012.54, dist=4.95,
             action="clôture 1h sous 4001,30", au_dessus=False),
        dict(m="BTC", prix=60000.0, atr_n=3.2, classe="en_approche", rang=2, d=-1, za=61000, zb=61500, dist=1000,
             action="x", au_dessus=True),
        dict(m="NASDAQ", prix=28227.0, atr_n=99.0, classe="sans_plan", rang=5),
    ]


DERNIERS = {"GOLD": {"strat": "SWING", "bear": 11, "plan_fige": {"d": -1, "e": 4000.0, "sl": 4019.86, "tp1": 3895.54}},
            "BTC": {"bear": 7}, "NASDAQ": {}}


class TexteRadarTest(unittest.TestCase):
    def test_vip_focus_et_niveaux(self):
        t = ab.texte_radar(props_test(), DERNIERS, vip=True, now=time.time())
        self.assertTrue(t.startswith("🎯 FOCUS : 🥇 GOLD — prépare-toi"))
        for morceau in ("SHORT", "SWING", "Zone d'entrée", "SL", "TP1", "J'attends", "11/11", "2️⃣ 🟠 BTC", "3️⃣ 💠 NASDAQ"):
            self.assertIn(morceau, t)
        self.assertNotIn("SHORT ⬇️ · pas de plan", t)          # pas de sens affiché pour un marché sans plan

    def test_gratuit_sans_niveaux(self):
        t = ab.texte_radar(props_test(), DERNIERS, vip=False, now=time.time())
        self.assertIn("🔒 Entrée, SL, TP : VIP", t)
        self.assertIn("SHORT", t)                               # le sens reste visible côté gratuit
        for interdit in ("4019", "3895", "Zone d'entrée :", "J'attends"):
            self.assertNotIn(interdit, t)

    def test_rien_de_proche(self):
        p = [dict(m="NASDAQ", prix=1.0, atr_n=99.0, classe="sans_plan", rang=5)]
        t = ab.texte_radar(p, {}, vip=True, now=time.time())
        self.assertTrue(t.startswith("📡 RADAR ALIGN — aucune entrée proche"))


class AlignementRequisTest(unittest.TestCase):
    def test_proche_mais_pas_aligne_n_est_pas_prepare_toi(self):
        d = {"NASDAQ": {"bull": 6}, "GOLD": {"bear": 9}}
        p = [dict(m="NASDAQ", prix=1.0, atr_n=0.9, classe="proche", rang=1, d=1, za=1, zb=2, dist=0.5, action="x", au_dessus=True),
             dict(m="GOLD", prix=1.0, atr_n=2.8, classe="en_approche", rang=2, d=-1, za=1, zb=2, dist=3, action="y", au_dessus=False)]
        t = ab.texte_radar(p, d, vip=True, now=time.time())
        self.assertNotIn("prépare-toi", t)
        self.assertIn("NASDAQ — proche, alignement pas encore atteint", t)
        d["NASDAQ"]["bull"] = 8
        self.assertIn("NASDAQ — prépare-toi", ab.texte_radar(p, d, vip=True, now=time.time()))

    def test_marche_pret_passe_devant(self):
        d = {"NASDAQ": {"bull": 6}, "GOLD": {"bear": 10}}
        p = [dict(m="NASDAQ", prix=1.0, atr_n=0.2, classe="dans_zone", rang=0, d=1, za=1, zb=2, dist=0, action="x", au_dessus=True),
             dict(m="GOLD", prix=1.0, atr_n=1.2, classe="proche", rang=1, d=-1, za=1, zb=2, dist=1, action="y", au_dessus=False)]
        self.assertTrue(ab.texte_radar(p, d, vip=True, now=time.time()).startswith("🎯 FOCUS : 🥇 GOLD — prépare-toi"))


class RadarTickTest(unittest.TestCase):
    def setUp(self):
        self.appels = []
        self.mid = 100

        def tg(methode, **kw):
            self.appels.append((methode, kw))
            self.mid += 1
            return {"ok": True, "result": {"message_id": self.mid}}
        self.p = [mock.patch.object(ab, "telegram", tg),
                  mock.patch.object(ab, "_envoi_sur", lambda cid, **kw: tg("sendMessage", chat_id=cid, **kw)),
                  mock.patch.object(ab, "autorise", lambda *a: True),
                  mock.patch.object(ab, "marches_choisis", lambda e, c: {"GOLD", "BTC", "NASDAQ"}),
                  mock.patch.object(ab, "classer_marches", lambda d, e, c, n=None: self.props)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()

    def test_un_seul_message_puis_edition(self):
        etat = {}
        self.props = props_test()
        self.props[0] = dict(self.props[0], rang=2, classe="en_approche", atr_n=2.5)
        t0 = 1_000_000.0
        ab.radar_tick(etat, {"42"}, DERNIERS, now=t0)
        self.assertEqual([a[0] for a in self.appels], ["sendMessage"])
        self.assertEqual(self.appels[0][1].get("disable_notification"), "true")   # radar normal : sans son
        # même fond, 3 min plus tard : aucune action (pas de doublon, pas d'édition inutile)
        ab.radar_tick(etat, {"42"}, DERNIERS, now=t0 + 180)
        self.assertEqual(len(self.appels), 1)
        # le prix entre dans la zone d'un marché déjà en tête → nouveau message AVEC son, ancien supprimé
        self.props[0] = dict(self.props[0], rang=0, classe="dans_zone", atr_n=0.0, dist=0.0)
        ab.radar_tick(etat, {"42"}, DERNIERS, now=t0 + 400)
        methodes = [a[0] for a in self.appels]
        self.assertEqual(methodes[-2:], ["sendMessage", "deleteMessage"])
        self.assertNotIn("disable_notification", self.appels[-2][1])
        self.assertIn("prépare-toi", self.appels[-2][1]["text"])
        # oscillation : retour « en approche » puis de nouveau « dans la zone » 2 min après → pas de 2e alerte sonore
        self.props[0] = dict(self.props[0], rang=2, classe="en_approche", atr_n=2.0)
        ab.radar_tick(etat, {"42"}, DERNIERS, now=t0 + 530)
        self.props[0] = dict(self.props[0], rang=0, classe="dans_zone", atr_n=0.0)
        n = len(self.appels)
        ab.radar_tick(etat, {"42"}, DERNIERS, now=t0 + 660)
        self.assertFalse(any(a[0] == "sendMessage" for a in self.appels[n:]))
        self.assertTrue(all(a[0] == "editMessageText" for a in self.appels[n:]))

    def test_jamais_la_chaine(self):
        self.props = props_test()
        ab.radar_tick({"canal": "-100"}, {"-100"}, DERNIERS, now=1.0)
        self.assertEqual(self.appels, [])


class CassureFusionneeTest(unittest.TestCase):
    def test_hier_et_semaine_au_meme_niveau(self):
        b15 = [{"t": 0, "o": 3990, "h": 3992, "l": 3985, "c": 3990}, {"t": 900, "o": 3984, "h": 3985, "l": 3970, "c": 3975}]
        r = {"m1": [{"c": 3975}], "atr": 5.0, "b15": b15,
             "niv_cles": [(3981.18, "plus bas d'hier"), (3981.18, "plus bas de la semaine dernière"), (4050.0, "plus haut d'hier")]}
        out = []
        ab.niveaux_cles(out, "GOLD", r, {})
        cassures = [x for x in out if x.startswith("💥 CASSURE")]
        self.assertEqual(len(cassures), 1)
        self.assertIn("plus bas d'hier et de la semaine dernière", cassures[0])
        out2 = []
        ab.niveaux_cles(out2, "GOLD", r, {"nivc": {}})
        self.assertEqual(len([x for x in out2 if x.startswith("💥")]), 1)


class NewsVipTest(unittest.TestCase):
    def test_news_absentes_du_gratuit(self):
        with mock.patch.object(ab, "news_du_jour", lambda e, *a, **k: ["📰 NEWS USA DU JOUR", "x"]), \
             mock.patch.object(ab, "DERNIER_ETAT", {"cal": {}}), \
             mock.patch.object(ab, "verdict", lambda r, c: ("⛔ NON", "raison")), \
             mock.patch.object(ab, "alignement", lambda r: (0, 0)), \
             mock.patch.object(ab, "voyants_unites", lambda r: []), \
             mock.patch.object(ab, "objectifs_marche", lambda r, d: []), \
             mock.patch.object(ab, "zone_retournement_visee", lambda r, c: []), \
             mock.patch.object(ab, "direction_attente", lambda r: "AUCUNE"):
            r = {"m1": [{"c": 1.0}]}
            self.assertIn("NEWS USA DU JOUR", ab.texte_apercu("GOLD", r, {}, vip=True))
            self.assertNotIn("NEWS USA DU JOUR", ab.texte_apercu("GOLD", r, {}, vip=False))


class DureeHumaineTest(unittest.TestCase):
    def test_pas_confondu_avec_une_heure(self):
        self.assertEqual(ab.duree_humaine(570), "9 min 30 s")
        self.assertEqual(ab.duree_humaine(3900), "1 h 05")


if __name__ == "__main__":
    unittest.main()
