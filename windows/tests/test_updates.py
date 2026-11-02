"""Mise à jour automatique : versions, Release GitHub, téléchargement vérifié par SHA-256."""

from __future__ import annotations

import hashlib

import pytest

from quakepad import updater

SETUP = b"MZ faux installateur QuakePad"


def test_version_comparison():
    assert updater.parse_version("v1.10.2") == (1, 10, 2)
    assert updater.is_newer("1.7.0", "1.6.0")
    assert updater.is_newer("v1.10.0", "1.9.9")  # comparaison numérique, pas alphabétique
    assert not updater.is_newer("1.7", "1.7.0")
    assert not updater.is_newer("1.6.9", "1.7.0")


def _release_server(mock_server, setup_bytes=SETUP, sums=None):
    holder = {}

    def handler(path, headers, body):
        base = holder["url"]
        if path == "/repos/x/releases/latest":
            return (
                200,
                {"Content-Type": "application/json"},
                {
                    "tag_name": "v9.9.0",
                    "body": "- Nouveautés",
                    "html_url": base + "/release",
                    "assets": [
                        {
                            "name": "QuakePad-Setup-9.9.0.exe",
                            "browser_download_url": base + "/setup",
                            "size": len(setup_bytes),
                        },
                        {"name": "SHA256SUMS.txt", "browser_download_url": base + "/sums", "size": 100},
                    ],
                },
            )
        if path == "/setup":
            return 200, {"Content-Type": "application/octet-stream"}, setup_bytes
        if path == "/sums":
            digest = sums or hashlib.sha256(SETUP).hexdigest()
            return 200, {"Content-Type": "text/plain"}, f"{digest}  QuakePad-Setup-9.9.0.exe\n".encode()
        return 404, {}, b""

    srv = mock_server(handler)
    holder["url"] = srv.url
    return srv


def test_latest_release_and_verified_download(mock_server):
    srv = _release_server(mock_server)
    rel = updater.latest_release(srv.url + "/repos/x/releases/latest")
    assert rel.version == "9.9.0" and rel.setup_name == "QuakePad-Setup-9.9.0.exe" and rel.notes
    path = updater.download_verified(rel, allow_local=True)
    assert path.read_bytes() == SETUP


def test_tampered_installer_is_rejected(mock_server):
    srv = _release_server(mock_server, setup_bytes=b"MZ installateur MODIFIE")
    rel = updater.latest_release(srv.url + "/repos/x/releases/latest")
    with pytest.raises(updater.UpdateError, match="empreinte"):
        updater.download_verified(rel, allow_local=True)


def test_missing_checksum_is_rejected(mock_server):
    srv = _release_server(mock_server, sums="pas-une-empreinte")
    rel = updater.latest_release(srv.url + "/repos/x/releases/latest")
    with pytest.raises(updater.UpdateError, match="SHA256SUMS"):
        updater.download_verified(rel, allow_local=True)


def test_only_github_hosts_allowed():
    for url in ("https://evil.example/setup.exe", "http://github.com/x", "file:///C:/setup.exe"):
        with pytest.raises(updater.UpdateError):
            updater._check_download_url(url, allow_local=False)
    updater._check_download_url("https://github.com/ScriptoriumII/QuakePad/releases/download/v1/x.exe", False)


def test_redirect_outside_github_refused(mock_server):
    srv = mock_server(lambda p, h, b: (302, {"Location": "https://evil.example/x.exe"}, b""))
    with pytest.raises(updater.UpdateError, match="refusée"):
        updater._download(
            srv.url + "/setup", srv and __import__("pathlib").Path(updater.tempfile.mkdtemp()) / "x", allow_local=True
        )


def test_private_repo_gives_clear_message(mock_server):
    srv = mock_server(lambda p, h, b: (404, {}, b'{"message": "Not Found"}'))
    with pytest.raises(updater.UpdateError, match="dépôt privé"):
        updater.latest_release(srv.url + "/repos/x/releases/latest")


def test_window_shows_update_button(window, monkeypatch):
    rel = updater.Release(
        "99.0.0", "v99.0.0", "notes", "https://github.com/x", "QuakePad-Setup-99.0.0.exe", "u", 1, "s"
    )
    shown = []
    monkeypatch.setattr(window.tray, "showMessage", lambda *a: shown.append(a))
    window._upd_busy = True
    window._update_checked(rel, False)
    assert not window.update_btn.isHidden() and "99.0.0" in window.update_btn.text() and shown
    old = updater.Release("0.0.1", "v0.0.1", "", "", "QuakePad-Setup-0.0.1.exe", "u", 1, "s")
    window._update_checked(old, False)
    assert window.update_btn.isHidden()
