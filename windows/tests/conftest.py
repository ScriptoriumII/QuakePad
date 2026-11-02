"""Configuration commune : Qt hors écran, dossier de données isolé, faux serveurs HTTP."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

# Avant tout import de Qt / quakepad : affichage hors écran et données dans un dossier temporaire.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="quakepad-tests-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    yield app


@pytest.fixture(autouse=True)
def appdata(tmp_path, monkeypatch):
    """Chaque test a son propre %APPDATA% (paramètres, session, consommation, journal)."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path / "QuakePad"


@pytest.fixture
def settings(appdata):
    from quakepad.settings import Settings

    return Settings.load()


@pytest.fixture
def window(qapp, settings, monkeypatch):
    from PySide6.QtGui import QIcon

    from quakepad import winapi
    from quakepad.window import QuakeWindow

    calls = []
    monkeypatch.setattr(winapi, "set_topmost", lambda hwnd, on, activate=False: calls.append(on))
    w = QuakeWindow(settings, QIcon())
    w.resize(900, 360)
    w.topmost_calls = calls
    yield w
    w._quitting = True
    w.hotkey.unregister()
    w.tray.hide()
    qapp.removeEventFilter(w._dialog_watcher)
    w.close()
    w.deleteLater()
    qapp.processEvents()


class MockServer:
    """Serveur HTTP local ; `handler(path, headers, body) -> (status, headers, payload)`."""

    def __init__(self, handler):
        self.requests: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                try:
                    body = json.loads(raw)
                except ValueError:
                    body = raw.decode()
                outer.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                status, headers, payload = handler(self.path, dict(self.headers), body)
                data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):  # noqa: N802
                outer.requests.append({"path": self.path, "headers": dict(self.headers), "body": None})
                status, headers, payload = handler(self.path, dict(self.headers), None)
                data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def mock_server():
    servers = []

    def make(handler):
        s = MockServer(handler)
        servers.append(s)
        return s

    yield make
    for s in servers:
        s.close()


def corrector(fixes: dict[str, str]):
    """Réponse type OpenAI qui applique des remplacements simples aux paragraphes reçus."""

    def handler(path, headers, body):
        paragraphs = json.loads(body["messages"][-1]["content"])
        out = []
        for p in paragraphs:
            for a, b in fixes.items():
                p = p.replace(a, b)
            out.append(p)
        return (
            200,
            {"Content-Type": "application/json"},
            {
                "choices": [{"message": {"content": json.dumps(out, ensure_ascii=False)}}],
                "usage": {"total_tokens": 120},
            },
        )

    return handler
