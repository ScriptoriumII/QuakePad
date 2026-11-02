"""Correction par IA : analyse des réponses, application sans perte de mise en forme, fournisseurs, quotas."""

from __future__ import annotations

import json

import pytest
from conftest import corrector

from quakepad import ai, usage


@pytest.fixture
def gemini_cfg(monkeypatch, mock_server):
    """Fournisseur Gemini redirigé vers un faux serveur local."""

    def make(handler):
        srv = mock_server(handler)
        monkeypatch.setitem(ai.PROVIDERS["gemini"], "base", srv.url + "/v1")
        cfg = {"ai_provider": "gemini", "ai_keys": {"gemini": "AIzaFAKE"}, "ai_models": {}}
        return srv, cfg

    return make


def test_parse_array_tolerates_fences_and_think_tags():
    text = '<think>hmm</think>```json\n["a", "b"]\n```'
    assert ai._parse_array(text, 2) == ["a", "b"]
    with pytest.raises(ai.AIError):
        ai._parse_array('["a"]', 2)
    with pytest.raises(ai.AIError):
        ai._parse_array("pas de json", 1)


def test_guard_rejects_rewrites_and_image_loss():
    assert ai._acceptable("Je suis aller a la plage hier.", "Je suis allé à la plage hier.")
    assert not ai._acceptable("Phrase identique.", "Phrase identique.")
    long = "Le serveur web redémarre chaque nuit à trois heures."
    assert not ai._acceptable(long, "Totalement autre chose sans rapport avec le texte initial !")
    assert not ai._acceptable("photo ￼ ici", "photo ici")


def test_apply_corrections_keeps_formatting_images_tables_and_single_undo(qapp):
    from PySide6.QtGui import QColor, QFont, QImage, QTextCharFormat, QTextCursor

    from quakepad.editor import Document

    d = Document()
    d.setPlainText("Je suis me sui tromper sur lorthografe.\nIl ma dit tres vite.")
    c = QTextCursor(d.document())
    c.setPosition(d.toPlainText().index("tres"))
    c.movePosition(QTextCursor.MoveOperation.EndOfWord, QTextCursor.MoveMode.KeepAnchor)
    f = QTextCharFormat()
    f.setFontWeight(QFont.Weight.Bold)
    c.mergeCharFormat(f)
    end = QTextCursor(d.document())
    end.movePosition(QTextCursor.MoveOperation.End)
    d.setTextCursor(end)
    d.insertPlainText("\nphoto ")
    img = QImage(8, 8, QImage.Format.Format_RGB32)
    img.fill(QColor("red"))
    d.insert_image(img)
    d.insertPlainText(" tres jolie\n")
    d.insert_table(1, 2)
    d.insertPlainText("les serveur")
    original = d.toPlainText()

    blocks = ai.collect_blocks(d, selection_only=False)
    fixed = [
        t.replace("Je suis me sui tromper sur lorthografe.", "Je me suis trompé sur l'orthographe.")
        .replace("ma dit tres", "m'a dit très")
        .replace("tres jolie", "très jolie")
        .replace("les serveur", "les serveurs")
        for _, t in blocks
    ]
    paras, edits, spans = ai.apply_corrections(d, blocks, fixed)
    text = d.toPlainText()
    assert "Je me suis trompé sur l'orthographe." in text and "les serveurs" in text
    assert paras == 4 and edits >= 4 and spans
    pos = text.index("très vite")
    c = QTextCursor(d.document())
    c.setPosition(pos + 2)
    assert c.charFormat().fontWeight() == QFont.Weight.Bold  # gras conservé
    assert d.toHtml().count("data:image/") == 1 and "<table" in d.toHtml()
    d.undo()
    assert d.toPlainText() == original  # un seul Ctrl+Z annule tout


def test_gemini_request_shape_and_usage_tracking(gemini_cfg):
    srv, cfg = gemini_cfg(corrector({"aller": "allé"}))
    out = ai.correct_paragraphs(["Je suis aller a la plage."], cfg)
    assert out == ["Je suis allé a la plage."]
    req = srv.requests[0]
    assert req["path"] == "/v1/chat/completions"
    assert req["headers"]["Authorization"] == "Bearer AIzaFAKE"
    assert req["body"]["model"] == "gemini-3.8-flash" and req["body"]["reasoning_effort"] == "low"
    st = usage.status("gemini", daily_quota=10)
    assert st["requests"] == 1 and st["tokens"] == 120 and st["pct_used"] == pytest.approx(10)


def test_fallback_to_other_model_when_overloaded(gemini_cfg, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    ok = corrector({"aller": "allé"})

    def handler(path, headers, body):
        if body["model"] == "gemini-3.8-flash":
            return 503, {"Content-Type": "application/json"}, [{"error": {"code": 503, "message": "high demand"}}]
        return ok(path, headers, body)

    srv, cfg = gemini_cfg(handler)
    assert "via gemini-3.5-flash-lite" in ai.test_connection(cfg)
    models = [r["body"]["model"] for r in srv.requests]
    assert models.count("gemini-3.8-flash") == 3 and models[-1] == "gemini-3.5-flash-lite"


def test_quota_exhausted_after_429(gemini_cfg, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    _, cfg = gemini_cfg(lambda p, h, b: (429, {}, {"error": {"message": "quota"}}))
    with pytest.raises(ai.AIError, match="429"):
        ai.correct_paragraphs(["texte"], cfg)
    assert usage.status("gemini")["exhausted"] and usage.status("gemini")["pct_used"] == 100


def test_html_page_instead_of_api_gives_clear_error(mock_server):
    srv = mock_server(lambda p, h, b: (200, {"Content-Type": "text/html"}, b"<!doctype html><html></html>"))
    cfg = {"ai_provider": "openai", "openai_base": srv.url, "openai_key": "", "openai_model": "x"}
    with pytest.raises(ai.AIError, match="page web"):
        ai.correct_paragraphs(["texte"], cfg)


def test_server_rate_limit_headers_are_used(mock_server):
    base = corrector({})

    def handler(path, headers, body):
        status, h, payload = base(path, headers, body)
        h.update({"x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "750"})
        return status, h, payload

    srv = mock_server(handler)
    cfg = {"ai_provider": "openai", "openai_base": srv.url + "/v1", "openai_key": "", "openai_model": "m"}
    ai.correct_paragraphs(["texte"], cfg)
    st = usage.status("openai")
    assert st["source"] == "serveur" and st["pct_used"] == pytest.approx(25)


def test_anthropic_request_shape(monkeypatch, mock_server):
    def handler(path, headers, body):
        out = json.dumps([p.replace("aller", "allé") for p in json.loads(body["messages"][0]["content"])])
        return (
            200,
            {"Content-Type": "application/json"},
            {
                "content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": out}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )

    srv = mock_server(handler)
    monkeypatch.setattr(ai, "ANTHROPIC_URL", srv.url + "/v1/messages")
    cfg = {"ai_provider": "anthropic", "anthropic_key": "sk-ant-FAKE", "anthropic_model": "claude-haiku-5-5"}
    assert ai.correct_paragraphs(["Je suis aller"], cfg) == ["Je suis allé"]
    req = srv.requests[0]
    headers = {k.lower(): v for k, v in req["headers"].items()}
    assert headers["x-api-key"] == "sk-ant-FAKE" and headers["anthropic-version"]
    assert "temperature" not in req["body"] and req["body"]["system"]


def test_key_never_sent_over_plain_http_to_network():
    cfg = {
        "ai_provider": "openai",
        "openai_base": "http://203.0.113.5/v1",
        "openai_key": "sk-secret",
        "openai_model": "m",
    }
    with pytest.raises(ai.AIError, match="n'est pas chiffrée"):
        ai.correct_paragraphs(["texte"], cfg)
