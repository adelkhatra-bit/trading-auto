import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import align_bot as ab

def bar(t, c, h=None, l=None, v=100):
    return dict(t=t, o=c, h=h if h is not None else c + 1, l=l if l is not None else c - 1, c=c, v=v)

def r_(dirs, vol_dernier=100, prix=100.0):
    b5 = [bar(i * 300, 100 - (i % 3)) for i in range(20)]
    b15 = [bar(i * 900, 100) for i in range(50)]
    b15[-2]["v"] = vol_dernier                       # la dernière CLÔTURÉE (la -1 est en formation)
    b1 = [bar(i * 3600, 100, h=110, l=90) for i in range(10)]
    b4 = [bar(i * 14400, 100, h=130, l=70) for i in range(10)]
    return dict(dirs=dirs, b5=b5, b15=b15, b1h=b1, b4h=b4, m1=[bar(0, prix)], t=10000)

#        1m 3m 5m 10m 15m 30m 45m 1h 2h 4h D
LONG_GOLD = [1, 1, 1, 0, 1, 0, -1, -1, -1, -1, -1]
LONG_BTC  = [1, 1, 1, 0, 1, 1, 1, 1, -1, -1, -1]

class RetournementParMarche(unittest.TestCase):
    def test_gold_5m_15m_contre_1h(self):
        cle = {}
        t = ab.retournement_marche("GOLD", r_(LONG_GOLD), cle)
        self.assertIn("RETOURNEMENT LONG", t)
        self.assertIn("(haut 1h)", t); self.assertIn("(haut 4h)", t); self.assertIn("Regarde ton graphique", t)
        self.assertIn("mets-toi à BE", t); self.assertIn("60 derniers jours", t)
        self.assertIsNone(ab.retournement_marche("GOLD", r_(LONG_GOLD), cle))     # pas de doublon

    def test_btc_attend_le_1h(self):
        self.assertIsNone(ab.retournement_marche("BTC", r_(LONG_GOLD), {}))       # 5m + 15m seuls : piège sur BTC
        t = ab.retournement_marche("BTC", r_(LONG_BTC), {})
        self.assertIn("le 1h a suivi", t)

    def test_nasdaq_demande_du_volume(self):
        self.assertIsNone(ab.retournement_marche("NASDAQ", r_(LONG_GOLD, vol_dernier=100), {}))
        t = ab.retournement_marche("NASDAQ", r_(LONG_GOLD, vol_dernier=500), {})
        self.assertIn("gros volume", t)

    def test_short_symetrique(self):
        t = ab.retournement_marche("GOLD", r_([-x for x in LONG_GOLD]), {})
        self.assertIn("RETOURNEMENT SHORT", t); self.assertIn("(bas 1h)", t)

    def test_cible_deja_depassee(self):
        self.assertIsNone(ab.retournement_marche("GOLD", r_(LONG_GOLD, prix=115.0), {}))

if __name__ == "__main__":
    unittest.main()
