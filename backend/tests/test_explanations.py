"""KI-Erklärtexte: Fakten, Vorlage, Prüfung, Zwischenspeicher, Budget und Endpunkte (Claude per MockTransport)."""
import httpx
import pytest
from sqlalchemy import select

from app.adapters import registry
from app.config import get_settings
from app.db import SessionLocal
from app.explain_facts import forecast_facts_text, forecast_template, pattern_facts_text, pattern_template, validate
from app.explain_service import MODEL, ClaudeExplainSource
from app.models import AiExplanation, LlmUsage, PatternDetection
from tests.conftest import login
from tests.test_forecast_api import run as run_forecast
from tests.test_forecast_api import seed as seed_forecast
from tests.test_pattern_api import run_scan, seed


@pytest.fixture()
def claude(monkeypatch):
    """Registriert die Erklär-Quelle mit Schlüssel; handler(request) -> Text. Gibt (calls, set_handler) zurück."""
    state = {"calls": [], "text": None}

    def install(text_fn=None, budget="10", tin=1500, tout=300, stop_reason="end_turn"):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("CLAUDE_MONTHLY_BUDGET_USD", budget)
        get_settings.cache_clear()

        def handler(req: httpx.Request) -> httpx.Response:
            state["calls"].append(req.read().decode())
            facts = state["calls"][-1]
            text = text_fn(facts) if text_fn else ""
            return httpx.Response(200, json={"content": [{"type": "text", "text": text}], "stop_reason": stop_reason,
                                             "usage": {"input_tokens": tin, "output_tokens": tout}})

        registry.clear()
        registry.register(ClaudeExplainSource(transport=httpx.MockTransport(handler), sleep=lambda _s: None))

    yield state, install
    registry.clear()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()


def setup_pattern(client):
    iid, _ = seed()
    run_scan(iid)
    login(client)
    body = client.get(f"/api/instruments/{iid}/patterns").json()
    det = next(d for d in body["detections"] if d["pattern_type"] == "doppelboden")
    return iid, det


def test_template_passes_own_validation_and_is_neutral(client):
    _, det = setup_pattern(client)
    facts = pattern_facts_text(det)
    tpl = pattern_template(det)
    assert validate(tpl, facts) is None
    assert "Doppelboden" in tpl and "keine Anlageberatung" in tpl
    assert det["backtest"]["status"] == "nicht_berechnet" and "nicht berechnet" in facts


def test_symmetric_triangle_levels_are_breakouts_not_invalidation(client):
    _, det = setup_pattern(client)
    det = {**det, "pattern_type": "dreieck_symmetrisch", "name": "Symmetrisches Dreieck",
           "direction_if_confirmed": "offen"}
    facts, tpl = pattern_facts_text(det), pattern_template(det)
    assert "Ausbruchsniveau oben" in facts and "Ausbruchsniveau unten" in facts
    assert "\nUngültigkeitsniveau:" not in facts and "Ungültigkeitsniveau" not in tpl
    assert "Ausbruch nach unten" in tpl
    assert validate(tpl, facts) is None


def test_validate_rejects_invented_numbers_dates_and_advice():
    facts = "Tief 1: 142,10 am 03.09.2026, Konfidenz 74 %, Stichprobe 41 Fälle"
    ok = ("Das erste Tief lag bei 142,10 am 03.09.2026, die Konfidenz beträgt 74 % bei 41 historischen Fällen. "
          "Ob das Muster bestätigt wird, ist offen und mit Unsicherheit verbunden; es gibt zwei mögliche Szenarien.")
    assert validate(ok, facts) is None
    assert "Zahl 143,50" in validate(ok.replace("142,10", "143,50"), facts)
    assert "Datum" in validate(ok.replace("03.09.2026", "04.09.2026"), facts)
    assert validate(ok.replace("offen", "ein klares Kaufsignal"), facts) == "enthält unzulässige Sprache"
    assert validate(ok + " Wir empfehlen, jetzt zu handeln.", facts) == "enthält unzulässige Sprache"
    assert validate(ok + " Mehr: https://example.org", facts) == "enthält einen Link"
    assert validate("Zu kurz.", facts) == "Länge außerhalb des zulässigen Bereichs"
    # Zahlwörter als Ziffern (bis 10) sind frei, große fremde Zahlen nicht
    assert validate(ok.replace("zwei", "999"), facts).startswith("Zahl 999")


def test_without_key_returns_labeled_template_and_stores_nothing(client, claude):
    _, det = setup_pattern(client)
    r = client.get(f"/api/patterns/{det['id']}/explanation")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "vorlage" and "ohne KI" in body["label"]
    assert body["fallback_reason"] == "Kein API-Schlüssel gesetzt" and body["model_name"] is None
    assert body["text"] == pattern_template(client.get(f"/api/patterns/{det['id']}").json())
    with SessionLocal() as db:
        assert db.scalars(select(AiExplanation)).all() == []


def test_ai_text_generated_once_cached_labeled_and_cost_counted(client, claude):
    state, install = claude
    _, det = setup_pattern(client)
    install(lambda body: pattern_template(det) + " Die Aussage ist unsicher und beschreibt nur die Berechnung.")
    first = client.get(f"/api/patterns/{det['id']}/explanation").json()
    assert first["source"] == "ki" and first["label"] == "KI-generiert (Claude Sonnet 5.5)"
    assert first["model_version"] == MODEL and first["fallback_reason"] is None
    assert first["cost_usd"] == pytest.approx((1500 * 2 + 300 * 10) / 1e6)
    assert first["budget"]["spent_usd"] == pytest.approx(first["cost_usd"], abs=1e-4)
    second = client.get(f"/api/patterns/{det['id']}/explanation").json()
    assert second["text"] == first["text"] and second["generated_at"] == first["generated_at"]
    assert len(state["calls"]) == 1  # nur einmal je Datenstand
    assert MODEL in state["calls"][0] and "Fakten der automatischen Analyse" in state["calls"][0]
    with SessionLocal() as db:
        assert len(db.scalars(select(AiExplanation)).all()) == 1
        assert db.get(LlmUsage, first["budget"]["month"]).cost_usd > 0


def test_new_data_state_gets_new_text(client, claude):
    state, install = claude
    _, det = setup_pattern(client)
    install(lambda body: pattern_template(det) + " Die Aussage ist unsicher und beschreibt nur die Berechnung.")
    client.get(f"/api/patterns/{det['id']}/explanation")
    with SessionLocal() as db:
        d = db.get(PatternDetection, det["id"])
        d.status_reason = d.status_reason + " Zusatz"
        db.commit()
    client.get(f"/api/patterns/{det['id']}/explanation")
    assert len(state["calls"]) == 2


def test_forbidden_or_invented_ai_text_falls_back_to_template_and_is_cached(client, claude):
    state, install = claude
    _, det = setup_pattern(client)
    install(lambda body: pattern_template(det) + " Das ist ein klares Kaufsignal mit Kursziel 200.")
    body = client.get(f"/api/patterns/{det['id']}/explanation").json()
    assert body["source"] == "vorlage" and "abgelehnt" in body["fallback_reason"]
    assert "Kaufsignal" not in body["text"] and body["cost_usd"] > 0
    client.get(f"/api/patterns/{det['id']}/explanation")
    assert len(state["calls"]) == 1  # verworfener Text wird nicht erneut bezahlt

    with SessionLocal() as db:
        d = db.get(PatternDetection, det["id"])
        d.status_reason += " Zweiter Stand"
        db.commit()
    install(lambda body: pattern_template(det) + " Der Kurs steigt danach auf 999,99.")
    body = client.get(f"/api/patterns/{det['id']}/explanation").json()
    assert body["source"] == "vorlage" and "999,99" in body["fallback_reason"]


def test_truncated_ai_text_falls_back_to_template(client, claude):
    state, install = claude
    _, det = setup_pattern(client)
    # Ein bei max_tokens abgeschnittener Text kann die Prüfung bestehen, bricht aber mitten im Satz ab.
    install(lambda body: pattern_template(det)[:400], stop_reason="max_tokens")
    body = client.get(f"/api/patterns/{det['id']}/explanation").json()
    assert body["source"] == "vorlage" and "max_tokens" in body["fallback_reason"]
    assert body["text"].endswith("keine Anlageberatung.") and body["cost_usd"] > 0


def test_budget_exhausted_uses_template_without_calling_api(client, claude):
    state, install = claude
    _, det = setup_pattern(client)
    install(lambda body: "x", budget="0.001")
    body = client.get(f"/api/patterns/{det['id']}/explanation").json()
    assert body["source"] == "vorlage" and body["fallback_reason"] == "Monatslimit erreicht"
    assert state["calls"] == []
    assert registry.get_adapter("claude_explain").budget_exhausted is True
    assert registry.get_adapter("claude_explain").health().status == "degraded"


def test_api_error_falls_back_and_is_retried_next_time(client, claude, monkeypatch):
    state, install = claude
    _, det = setup_pattern(client)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    get_settings.cache_clear()
    registry.clear()
    registry.register(ClaudeExplainSource(transport=httpx.MockTransport(lambda r: httpx.Response(500)),
                                          sleep=lambda _s: None))
    body = client.get(f"/api/patterns/{det['id']}/explanation").json()
    assert body["source"] == "vorlage" and body["fallback_reason"] == "KI-Dienst derzeit nicht erreichbar"
    with SessionLocal() as db:
        assert db.scalars(select(AiExplanation)).all() == []


def test_pattern_explanation_404_and_login(client):
    assert client.get("/api/patterns/1/explanation").status_code == 401
    login(client)
    assert client.get("/api/patterns/999/explanation").status_code == 404
    assert client.get("/api/instruments/999/forecast/explanation").status_code == 404


def test_forecast_explanation(client, claude):
    state, install = claude
    iid, _ = seed_forecast()
    login(client)
    assert client.get(f"/api/instruments/{iid}/forecast/explanation").status_code == 404  # noch nicht berechnet
    run_forecast(iid)
    f = client.get(f"/api/instruments/{iid}/forecast").json()
    facts = forecast_facts_text({**f, "steps": f["steps"]}, "SAP")
    tpl = forecast_template(f, "SAP")
    assert validate(tpl, facts) is None
    assert "Wahrscheinlichkeitsbereiche" in facts and "Einzelprognose" in tpl
    body = client.get(f"/api/instruments/{iid}/forecast/explanation").json()
    assert body["source"] == "vorlage" and body["text"] == tpl
    install(lambda b: tpl + " Die Werte sind unsicher.")
    body = client.get(f"/api/instruments/{iid}/forecast/explanation").json()
    assert body["source"] == "ki" and body["label"].startswith("KI-generiert")
    client.get(f"/api/instruments/{iid}/forecast/explanation")
    assert len(state["calls"]) == 1


def test_demo_data_never_uses_ai(client, claude):
    state, install = claude
    _, det = setup_pattern(client)
    install(lambda body: pattern_template(det) + " Die Aussage ist unsicher und beschreibt nur die Berechnung.")
    with SessionLocal() as db:
        db.get(PatternDetection, det["id"]).is_demo = True
        db.commit()
    body = client.get(f"/api/patterns/{det['id']}/explanation").json()
    assert body["source"] == "vorlage" and "Demo-Modus" in body["fallback_reason"] and state["calls"] == []
