"""Le bot dit toujours clairement quels marchés il surveille pour la personne (GOLD + NASDAQ, etc.)."""
import os, sys, json
os.environ.setdefault("TELEGRAM_TOKEN", "test")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import align_bot as ab

import pytest
ENVOIS = []
def faux_telegram(methode, **kw):
    ENVOIS.append((methode, kw)); return {"ok": True, "result": {"message_id": 1}}

@pytest.fixture(autouse=True)
def _isole(monkeypatch):
    monkeypatch.setattr(ab, "telegram", faux_telegram)
    monkeypatch.setattr(ab, "autorise", lambda *a: True)

def etat_vide():
    return {"marches_par_chat": {}, "auto": {}, "bot_off": [], "bienvenue": {}}

def test_gold_nasdaq_suivis_btc_non():
    e = etat_vide(); ab.selectionner_marches_suivi(e, "42", ["GOLD", "NASDAQ"])
    t = ab.texte_suivi(e, "42")
    assert "JE SURVEILLE POUR TOI" in t
    assert "🥇 GOLD : ⏳" in t and "💠 NASDAQ : ⏳" in t and "🟠 BTC : ⬜ non suivi" in t

def test_trois_marches():
    e = etat_vide(); ab.selectionner_marches_suivi(e, "42", "ALL")
    t = ab.texte_suivi(e, "42")
    assert t.count("⏳") == 3

def test_valider_affiche_le_bloc():
    e = etat_vide(); ab.selectionner_marches_suivi(e, "42", ["GOLD", "NASDAQ"]); ENVOIS.clear()
    assert ab.valider_et_suivre_marches(e, "42", 42)
    txt = [kw.get("text", "") for m, kw in ENVOIS if m == "sendMessage"][-1]
    assert "Suivi activé : GOLD + NASDAQ" in txt and "JE SURVEILLE POUR TOI" in txt

def test_case_cochee_edite_le_meme_message():
    e = etat_vide(); ab.selectionner_marches_suivi(e, "42", ["GOLD"]); ENVOIS.clear()
    ab.basculer_marche(e, "42", "NASDAQ"); ab.menu_marches(e, "42", 99)
    assert ENVOIS[-1][0] == "editMessageText" and ENVOIS[-1][1]["message_id"] == 99
    clavier = json.loads(ENVOIS[-1][1]["reply_markup"])["inline_keyboard"]
    textes = [l[0]["text"] for l in clavier]
    assert "✅ 💠 NASDAQ" in textes and "⬜ Tout recevoir" in textes
    assert "Cochés en ce moment : 🥇 GOLD + 💠 NASDAQ" in ENVOIS[-1][1]["text"]

def test_tout_recevoir_coche_seulement_si_tout():
    e = etat_vide(); ab.selectionner_marches_suivi(e, "42", "ALL"); ENVOIS.clear()
    ab.menu_marches(e, "42")
    textes = [l[0]["text"] for l in json.loads(ENVOIS[-1][1]["reply_markup"])["inline_keyboard"]]
    assert "✅ Tout recevoir" in textes
