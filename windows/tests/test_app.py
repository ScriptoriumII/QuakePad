"""Fenêtre et documents : onglets, session chiffrée, images, PDF, positions, raccourcis, dialogues, Quitter."""

from __future__ import annotations

import json

import pytest
from PySide6.QtCore import QMimeData, Qt, QTimer
from PySide6.QtGui import QColor, QImage

from quakepad import winapi
from quakepad.session import read_session, write_session

# --------------------------------------------------------------------------- session


def test_session_roundtrip_is_encrypted_on_windows(tmp_path):
    path = tmp_path / "session.json"
    data = {"current": 0, "tabs": [{"content": "mot de passe du NAS : hunter2", "path": None}]}
    write_session(path, data)
    raw = path.read_text(encoding="utf-8")
    assert read_session(path) == data
    if winapi.IS_WINDOWS:
        assert "hunter2" not in raw and json.loads(raw)["format"] == "dpapi"


def test_old_plaintext_session_is_migrated(tmp_path):
    path = tmp_path / "session.json"
    old = {"version": 2, "current": 0, "tabs": [{"content": "ancienne note", "path": None}]}
    path.write_text(json.dumps(old), encoding="utf-8")
    assert read_session(path)["tabs"][0]["content"] == "ancienne note"
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 3


def test_unreadable_encrypted_session_is_kept_aside(tmp_path):
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"version": 3, "format": "dpapi", "data": "dpapi:AAAA"}), encoding="utf-8")
    assert read_session(path) is None
    assert not path.exists() and list(tmp_path.glob("session.illisible-*.json"))


def test_window_restores_tabs_titles_and_images(window, settings, qapp):
    from PySide6.QtGui import QIcon

    from quakepad.window import QuakeWindow

    d = window.current()
    d.setPlainText("note non enregistrée")
    img = QImage(10, 10, QImage.Format.Format_RGB32)
    img.fill(QColor("blue"))
    d.insert_image(img)
    window._set_tab_title(d, "Incidents réseau")
    window.save_session()
    w2 = QuakeWindow(settings, QIcon())
    try:
        docs = w2.docs()
        assert docs[0].title() == "Incidents réseau" and docs[0].toHtml().count("data:image/") == 1
    finally:
        w2._quitting = True
        w2.hotkey.unregister()
        w2.tray.hide()
        qapp.removeEventFilter(w2._dialog_watcher)
        w2.deleteLater()


# --------------------------------------------------------------------------- onglets


def test_new_tab_button_stays_last(window):
    n = len(window.docs())
    window.new_tab_btn.click()
    assert len(window.docs()) == n + 1
    bar = window.tabs.tabBar()
    bar.moveTab(window.tabs.count() - 1, 0)
    assert window.tabs.indexOf(window._plus) == window.tabs.count() - 1


def test_rename_tab_enter_and_escape(window, qapp):
    from PySide6.QtTest import QTest

    window.show()
    window.rename_tab(0)
    QTest.keyClicks(window._rename_edit, "X")
    window._rename_edit.setText("Mon onglet")
    QTest.keyClick(window._rename_edit, Qt.Key.Key_Return)
    assert window.tabs.tabText(0).endswith("Mon onglet")
    window.rename_tab(0)
    window._rename_edit.setText("ignoré")
    QTest.keyClick(window._rename_edit, Qt.Key.Key_Escape)
    assert window.tabs.tabText(0).endswith("Mon onglet") and window.isVisible()


def test_closing_last_tab_creates_a_new_one(window):
    window.close_tab(0)
    assert len(window.docs()) == 1


# --------------------------------------------------------------------------- édition


def test_plain_txt_file_stays_plain(window, tmp_path):
    f = tmp_path / "notes.txt"
    f.write_bytes("ligne1\r\ncafé\r\n".encode("cp1252"))
    window.open_files([str(f)])
    d = window.current()
    md = QMimeData()
    md.setHtml("<b>gras</b>")
    md.setText("gras")
    c = d.textCursor()
    c.movePosition(c.MoveOperation.End)
    d.setTextCursor(c)
    d.insertFromMimeData(md)
    assert not d.rich
    d.save()
    assert f.read_bytes().endswith(b"gras") and b"<b>" not in f.read_bytes()


def test_export_pdf(window, tmp_path):
    window.current().setPlainText("Compte rendu d'intervention")
    out = tmp_path / "cr.pdf"
    assert window.export_pdf(str(out))
    assert out.read_bytes().startswith(b"%PDF")


@pytest.mark.parametrize("edge", ["top", "bottom", "left", "right"])
def test_edges_and_remembered_size(window, edge):
    window.set_edge(edge)
    window.begin_resize()
    window.drag_resize("depth", 40)
    window.end_resize()
    from quakepad.settings import Settings

    saved = Settings.load()
    assert saved["edge"] == edge
    assert saved["sizes"][edge]["depth"] != {"top": 45, "bottom": 45, "left": 35, "right": 35}[edge]


def test_custom_shortcut(window):
    window.settings["shortcuts"] = {"fmt.bold": "Ctrl+Alt+G"}
    window.apply_shortcuts()
    assert window.act_bold.shortcut().toString() == "Ctrl+Alt+G"


def test_dialogs_are_raised_above_topmost_window(window, qapp):
    from PySide6.QtWidgets import QMessageBox

    QTimer.singleShot(150, lambda: [w.close() for w in qapp.topLevelWidgets() if isinstance(w, QMessageBox)])
    QMessageBox.information(window, "t", "x")
    for _ in range(5):
        qapp.processEvents()
    assert window.topmost_calls[0] is False and window.topmost_calls[-1] is True


def test_quit_really_exits(window, qapp):
    QTimer.singleShot(100, window.quit_app)
    assert qapp.exec() == 0


def test_format_bar_follows_tab_area_size(window, qapp):
    """Régression 1.7.0 : sous Windows, la zone des onglets reçoit sa taille après la fenêtre ;
    la barre de mise en forme doit suivre la zone des onglets, pas seulement la fenêtre."""
    window.show()
    qapp.processEvents()
    window.format_bar.resize(640, 30)  # état observé sous Windows à l'ouverture
    window.tabs.resize(1234, 300)  # mise en page tardive de la zone des onglets
    qapp.processEvents()
    assert window.format_bar.width() == window.tabs.width() > 640
    bar_bottom = window.tabs.tabBar().geometry().bottom()
    assert window.format_bar.y() == bar_bottom + 1
