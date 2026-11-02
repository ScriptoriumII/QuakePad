"""Fichiers texte, paramètres et secrets, sécurité réseau, journal."""

from __future__ import annotations

import json
import logging

import pytest

from quakepad import netsec, winapi
from quakepad.textio import read_text, write_text

# --------------------------------------------------------------------------- fichiers texte


@pytest.mark.parametrize(
    "raw, enc, eol",
    [
        ("é café\r\nligne 2".encode("cp1252"), "cp1252", "\r\n"),
        ("é café\nligne 2".encode(), "utf-8", "\n"),
        (b"\xef\xbb\xbf" + "BOM é\r\n".encode(), "utf-8-sig", "\r\n"),
        ("UTF-16 é\r\n".encode("utf-16"), "utf-16", "\r\n"),
    ],
)
def test_text_roundtrip_keeps_encoding_and_eol(tmp_path, raw, enc, eol):
    f = tmp_path / "a.txt"
    f.write_bytes(raw)
    text, got_enc, got_eol = read_text(f)
    assert (got_enc, got_eol) == (enc, eol)
    assert "\r" not in text
    write_text(f, text, got_enc, got_eol)
    assert f.read_bytes() == raw


# --------------------------------------------------------------------------- paramètres


def test_settings_defaults_and_unknown_keys_ignored(appdata):
    from quakepad.settings import Settings

    appdata.mkdir(parents=True)
    (appdata / "settings.json").write_text(json.dumps({"theme": "dark", "inconnu": 1}), encoding="utf-8")
    s = Settings.load()
    assert s["theme"] == "dark" and "inconnu" not in s and s["edge"] == "top"


def test_settings_migrations(appdata):
    from quakepad.settings import Settings

    appdata.mkdir(parents=True)
    old = {
        "height_pct": 60,
        "width_pct": 80,
        "opacity": 97,
        "ai_provider": "openai",
        "openai_base": "https://aistudio.google.com/api-keys",
        "openai_key": "AIzaFAKEFAKEFAKEFAKEFAKE",
        "edge": "nimporte",
    }
    (appdata / "settings.json").write_text(json.dumps(old), encoding="utf-8")
    s = Settings.load()
    assert s["sizes"]["top"] == {"depth": 60, "span": 80}
    assert s["opacity"] == 100
    assert s["ai_provider"] == "gemini" and s["ai_keys"]["gemini"].startswith("AIza")
    assert s["openai_key"] == "" and s["openai_base"].startswith("http://localhost")
    assert s["edge"] == "top"


def test_api_keys_never_written_in_clear_on_windows(settings):
    settings["anthropic_key"] = "sk-ant-test-123456789"
    settings["ai_keys"] = {"gemini": "AIzaTESTKEYTESTKEYTESTKEY"}
    settings.save()
    on_disk = settings.path.read_text(encoding="utf-8")
    from quakepad.settings import Settings

    reloaded = Settings.load()
    assert reloaded["anthropic_key"] == "sk-ant-test-123456789"
    assert reloaded["ai_keys"]["gemini"] == "AIzaTESTKEYTESTKEYTESTKEY"
    if winapi.IS_WINDOWS:
        assert "sk-ant-test" not in on_disk and "AIzaTEST" not in on_disk
        assert winapi.DPAPI_PREFIX in on_disk


@pytest.mark.skipif(not winapi.IS_WINDOWS, reason="DPAPI : Windows uniquement")
def test_dpapi_roundtrip_and_tamper():
    blob = winapi.protect("secret é 🔑")
    assert blob.startswith(winapi.DPAPI_PREFIX) and "secret" not in blob
    assert winapi.unprotect(blob) == "secret é 🔑"
    assert winapi.unprotect(winapi.DPAPI_PREFIX + "AAAA") == ""


# --------------------------------------------------------------------------- sécurité réseau


@pytest.mark.parametrize(
    "url, secret, ok",
    [
        ("https://api.mistral.ai/v1", True, True),
        ("http://localhost:11434/v1", True, True),
        ("http://127.0.0.1:8010/v2/check", False, True),
        ("http://serveur:8010/v2/check", False, True),
        ("http://192.168.1.20:8010/v2/check", False, True),
        ("http://192.168.1.20:11434/v1", True, False),  # clé en clair sur le réseau
        ("http://api.example.com/v1", False, False),  # Internet sans chiffrement
        ("file:///C:/Windows/win.ini", False, False),
        ("ftp://example.com", False, False),
        ("https://user:pw@api.example.com", True, False),
        ("", False, False),
    ],
)
def test_validate_url(url, secret, ok):
    if ok:
        assert netsec.validate_url(url, sends_secret=secret) == url
    else:
        with pytest.raises(netsec.UnsafeURLError):
            netsec.validate_url(url, sends_secret=secret)


def test_redirects_are_refused(mock_server):
    srv = mock_server(lambda p, h, b: (302, {"Location": "http://evil.example/steal"}, b""))
    import urllib.request

    req = urllib.request.Request(srv.url + "/v1/chat/completions", data=b"{}", method="POST")
    with pytest.raises(netsec.UnsafeURLError, match="Redirection refusée"):
        netsec.open_url(req, 5, sends_secret=True)


# --------------------------------------------------------------------------- journal


def test_log_redacts_secrets(appdata):
    from quakepad import log as qlog

    for h in list(qlog.log.handlers):
        qlog.log.removeHandler(h)
    qlog.setup(logging.DEBUG)
    qlog.log.warning("clés sk-ant-api03-ABCDEFGH12345 AIzaSyABCDEFGHIJKLMNOPQRSTUV Bearer gsk_ABCDEFGH123")
    for h in qlog.log.handlers:
        h.flush()
    content = qlog.path().read_text(encoding="utf-8")
    assert "sk-ant-api03" not in content and "AIzaSy" not in content and "gsk_ABC" not in content
    assert content.count("«secret masqué»") >= 3
    for h in list(qlog.log.handlers):
        h.close()
        qlog.log.removeHandler(h)
