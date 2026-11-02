"""Fenêtre principale : bloc-notes à onglets qui descend du haut de l'écran (mode Quake)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer
from PySide6.QtGui import QAction, QCursor, QFont, QGuiApplication, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QMenu, QMessageBox,
    QPlainTextEdit, QSystemTrayIcon, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from . import winapi
from .dialogs import SettingsDialog
from .editor import Document, FindBar
from .settings import APP_NAME, APP_VERSION, Settings, app_dir
from .textio import ENCODINGS, EOLS
from .theme import stylesheet

FILE_FILTER = "Fichiers texte (*.txt *.md *.log *.ini *.cfg *.conf *.json *.yaml *.yml *.ps1 *.py *.sh *.csv);;Tous les fichiers (*)"


class DragHandle(QWidget):
    """Bord inférieur : glisser pour redimensionner la hauteur, comme Windows Terminal."""

    def __init__(self, window: "QuakeWindow"):
        super().__init__(window)
        self.setObjectName("DragHandle")
        self.setFixedHeight(6)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self._win = window
        self._start = None

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._start = (e.globalPosition().y(), self._win.height())

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._start:
            y0, h0 = self._start
            self._win.resize(self._win.width(), max(120, int(h0 + e.globalPosition().y() - y0)))

    def mouseReleaseEvent(self, e):  # noqa: N802
        if self._start:
            self._start = None
            self._win.remember_height()


class QuakeWindow(QWidget):
    def __init__(self, settings: Settings, icon: QIcon):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setObjectName("QuakeRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icon)
        self.settings = settings
        self.icon = icon
        from .app import resource
        self.assets_dir = str(Path(resource('quakepad.png')).parent)
        self.pinned = False
        self._anim: QPropertyAnimation | None = None
        self._hiding = False
        self._untitled_counter = 0
        self._session_path = app_dir() / "session.json"

        # --- Barre du haut : onglets + boutons ---------------------------
        self.tabs = QTabWidget(documentMode=True, tabsClosable=True, movable=True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_current_changed)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setElideMode(Qt.TextElideMode.ElideMiddle)
        self.tabs.tabBar().tabBarDoubleClicked.connect(lambda i: self.new_tab() if i < 0 else None)

        corner = QWidget()
        corner.setObjectName("TopBar")
        cl = QHBoxLayout(corner)
        cl.setContentsMargins(4, 0, 6, 0)
        cl.setSpacing(2)
        add_btn = QToolButton(text="+", toolTip="Nouvel onglet (Ctrl+N)")
        add_btn.clicked.connect(lambda: self.new_tab())
        self.pin_btn = QToolButton(text="📌", toolTip="Épingler : ne pas masquer en perdant le focus", checkable=True)
        self.pin_btn.toggled.connect(self._set_pinned)
        self.menu_btn = QToolButton(text="☰", toolTip="Menu")
        self.menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        hide_btn = QToolButton(text="⌃", toolTip="Masquer (Échap)")
        hide_btn.clicked.connect(self.hide_animated)
        for b in (add_btn, self.pin_btn, self.menu_btn, hide_btn):
            cl.addWidget(b)
        self.tabs.setCornerWidget(corner, Qt.Corner.TopRightCorner)

        self.find_bar = FindBar(self.current, self)
        self.find_bar.hide()
        self.find_bar.closed.connect(lambda: self.current() and self.current().setFocus())

        # --- Barre d'état --------------------------------------------------
        self.status = QWidget()
        self.status.setObjectName("StatusBar")
        sl = QHBoxLayout(self.status)
        sl.setContentsMargins(8, 3, 8, 3)
        self.lbl_path = QLabel()
        self.lbl_pos = QLabel()
        self.lbl_len = QLabel()
        self.lbl_zoom = QLabel()
        self.lbl_eol = QLabel()
        self.lbl_enc = QLabel()
        self.lbl_hotkey = QLabel()
        sl.addWidget(self.lbl_path, 1)
        for w in (self.lbl_pos, self.lbl_len, self.lbl_zoom, self.lbl_eol, self.lbl_enc, self.lbl_hotkey):
            sl.addWidget(w)

        edge = QWidget()
        edge.setObjectName("AccentEdge")
        edge.setFixedHeight(2)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.tabs, 1)
        root.addWidget(self.find_bar)
        root.addWidget(self.status)
        root.addWidget(edge)
        root.addWidget(DragHandle(self))

        self._build_actions()
        self._build_tray()

        self._session_timer = QTimer(self, singleShot=True, interval=1200)
        self._session_timer.timeout.connect(self.save_session)

        self.hotkey = winapi.GlobalHotkey(self)
        self.hotkey.activated.connect(self.toggle)
        QGuiApplication.instance().applicationStateChanged.connect(self._on_app_state)

        self.apply_settings()
        self.restore_session()
        if self.tabs.count() == 0:
            self.new_tab()

    # ================================================================
    # Actions et menus
    # ================================================================
    def _act(self, text, slot, shortcut=None, checkable=False, checked=False) -> QAction:
        a = QAction(text, self)
        if shortcut:
            seqs = shortcut if isinstance(shortcut, list) else [shortcut]
            a.setShortcuts([QKeySequence(x) for x in seqs])
            a.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        if checkable:
            a.setCheckable(True)
            a.setChecked(checked)
            a.toggled.connect(slot)
        else:
            a.triggered.connect(lambda _=False: slot())
        self.addAction(a)
        return a

    def _build_actions(self) -> None:
        m = QMenu(self)

        f = m.addMenu("Fichier")
        f.addAction(self._act("Nouvel onglet", self.new_tab, "Ctrl+N"))
        f.addAction(self._act("Ouvrir…", self.open_dialog, "Ctrl+O"))
        f.addAction(self._act("Enregistrer", self.save_current, "Ctrl+S"))
        f.addAction(self._act("Enregistrer sous…", self.save_current_as, "Ctrl+Shift+S"))
        f.addAction(self._act("Enregistrer tout", self.save_all, "Ctrl+Alt+S"))
        f.addSeparator()
        self.enc_menu = f.addMenu("Encodage")
        for key, label in ENCODINGS.items():
            a = self.enc_menu.addAction(label)
            a.setData(key)
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, k=key: self._set_encoding(k))
        self.eol_menu = f.addMenu("Fins de ligne")
        for key, label in EOLS.items():
            a = self.eol_menu.addAction(label)
            a.setData(key)
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, k=key: self._set_eol(k))
        f.addSeparator()
        f.addAction(self._act("Imprimer…", self.print_current, "Ctrl+P"))
        f.addSeparator()
        f.addAction(self._act("Fermer l'onglet", lambda: self.close_tab(self.tabs.currentIndex()), "Ctrl+W"))

        e = m.addMenu("Édition")
        e.addAction(self._act("Rechercher…", lambda: self.find_bar.open_bar(False), "Ctrl+F"))
        e.addAction(self._act("Remplacer…", lambda: self.find_bar.open_bar(True), "Ctrl+H"))
        e.addAction(self._act("Suivant", lambda: self.find_bar.find(), "F3"))
        e.addAction(self._act("Précédent", lambda: self.find_bar.find(backward=True), "Shift+F3"))
        e.addAction(self._act("Atteindre la ligne…", self.go_to_line, "Ctrl+G"))
        e.addSeparator()
        e.addAction(self._act("Insérer date/heure", self.insert_datetime, "F5"))
        e.addAction(self._act("Dupliquer la ligne", self.duplicate_line, "Ctrl+D"))

        v = m.addMenu("Affichage")
        self.act_wrap = self._act("Retour automatique à la ligne", self._set_wrap, "Alt+Z",
                                  checkable=True, checked=self.settings["word_wrap"])
        self.act_status = self._act("Barre d'état", self._set_statusbar, None,
                                    checkable=True, checked=self.settings["show_statusbar"])
        v.addAction(self.act_wrap)
        v.addAction(self.act_status)
        v.addSeparator()
        v.addAction(self._act("Zoom avant", lambda: self.zoom(+1), ["Ctrl++", "Ctrl+="]))
        v.addAction(self._act("Zoom arrière", lambda: self.zoom(-1), "Ctrl+-"))
        v.addAction(self._act("Zoom par défaut", lambda: self.zoom(0, reset=True), "Ctrl+0"))

        m.addSeparator()
        m.addAction(self._act("Paramètres…", self.open_settings, "Ctrl+,"))
        m.addAction(self._act(f"À propos de {APP_NAME}", self.about))
        m.addSeparator()
        m.addAction(self._act("Quitter", self.quit_app, "Ctrl+Q"))
        m.aboutToShow.connect(self._sync_doc_menus)
        self.menu_btn.setMenu(m)

        # Raccourcis sans entrée de menu
        self._act("Onglet suivant", lambda: self._cycle(+1), "Ctrl+Tab")
        self._act("Onglet précédent", lambda: self._cycle(-1), "Ctrl+Shift+Tab")
        self._act("Masquer", self._escape, "Esc")
        for i in range(1, 10):
            self._act(f"Onglet {i}", lambda i=i: self._goto_tab(i), f"Alt+{i}")

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.icon, self)
        menu = QMenu()
        menu.addAction("Afficher / masquer", self.toggle)
        menu.addAction("Nouvel onglet", lambda: (self.show_animated(), self.new_tab()))
        menu.addAction("Paramètres…", lambda: (self.show_animated(), self.open_settings()))
        menu.addSeparator()
        menu.addAction("Quitter", self.quit_app)
        self._tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self.toggle() if r == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        self.tray.show()

    # ================================================================
    # Paramètres
    # ================================================================
    def apply_settings(self) -> None:
        s = self.settings
        self.setStyleSheet(stylesheet(s["theme"], self.assets_dir))
        self.setWindowOpacity(max(0.4, min(1.0, s["opacity"] / 100)))
        for doc in self.docs():
            self._style_doc(doc)
        self.status.setVisible(s["show_statusbar"])
        ok, msg = self.hotkey.register(s["hotkey"])
        self.lbl_hotkey.setText(f"⌨ {s['hotkey'].get('label', '')}" if ok else "⌨ raccourci inactif")
        self.tray.setToolTip(f"{APP_NAME} — {s['hotkey'].get('label', '')}")
        if not ok and winapi.IS_WINDOWS:
            self.tray.showMessage(APP_NAME, msg + "\nChangez-le dans Paramètres.",
                                  QSystemTrayIcon.MessageIcon.Warning, 6000)
        if self.isVisible():
            self.setGeometry(self._target_geometry())
        self._update_status()

    def _font(self) -> QFont:
        font = QFont(self.settings["font_family"])
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(max(5, int(self.settings["font_size"]) + int(self.settings["zoom"])))
        return font

    def _style_doc(self, doc: Document) -> None:
        doc.apply_font(self._font())
        doc.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if self.settings["word_wrap"]
                            else QPlainTextEdit.LineWrapMode.NoWrap)

    def open_settings(self) -> None:
        self.hotkey.unregister()  # sinon la capture déclencherait le raccourci
        dlg = SettingsDialog(self.settings, self)
        dlg.setStyleSheet(stylesheet(self.settings["theme"], self.assets_dir))
        if dlg.exec():
            vals = dlg.values()
            if vals["start_with_windows"] != self.settings["start_with_windows"]:
                winapi.set_start_with_windows(vals["start_with_windows"])
            self.settings.update(vals)
            self.settings.save()
        self.apply_settings()

    def remember_height(self) -> None:
        ag = self._screen().availableGeometry()
        self.settings["height_pct"] = max(15, min(100, round(self.height() * 100 / ag.height())))
        self.settings.save()

    def _set_wrap(self, on: bool) -> None:
        self.settings["word_wrap"] = on
        self.settings.save()
        for d in self.docs():
            self._style_doc(d)

    def _set_statusbar(self, on: bool) -> None:
        self.settings["show_statusbar"] = on
        self.settings.save()
        self.status.setVisible(on)

    def zoom(self, step: int, reset: bool = False) -> None:
        self.settings["zoom"] = 0 if reset else max(-8, min(40, self.settings["zoom"] + step))
        self.settings.save()
        for d in self.docs():
            self._style_doc(d)
        self._update_status()

    def _set_pinned(self, on: bool) -> None:
        self.pinned = on

    # ================================================================
    # Animation Quake
    # ================================================================
    def _screen(self):
        return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

    def _target_geometry(self) -> QRect:
        ag = self._screen().availableGeometry()
        w = round(ag.width() * self.settings["width_pct"] / 100)
        h = round(ag.height() * self.settings["height_pct"] / 100)
        return QRect(ag.x() + (ag.width() - w) // 2, ag.y(), w, h)

    def _animate(self, start: QRect, end: QRect, on_done=None) -> None:
        if self._anim is not None:
            self._anim.stop()
            self._anim.deleteLater()
        ms = int(self.settings["anim_ms"])
        if ms <= 0:
            self.setGeometry(end)
            if on_done:
                on_done()
            return
        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(ms)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        if on_done:
            self._anim.finished.connect(on_done)
        self._anim.start()

    def toggle(self) -> None:
        if self.isVisible() and not self._hiding:
            if self.isActiveWindow():
                self.hide_animated()
            else:
                self._activate()
        else:
            self.show_animated()

    def show_animated(self) -> None:
        self._hiding = False
        end = self._target_geometry()
        start = QRect(end.x(), end.y() - end.height(), end.width(), end.height())
        if not self.isVisible():
            self.setGeometry(start)
            self.show()
        self._activate()
        self._animate(self.geometry(), end)

    def hide_animated(self) -> None:
        if not self.isVisible() or self._hiding:
            return
        self._hiding = True
        self.save_session()
        g = self.geometry()
        end = QRect(g.x(), g.y() - g.height(), g.width(), g.height())

        def done():
            if self._hiding:
                self.hide()
                self._hiding = False

        self._animate(g, end, done)

    def _activate(self) -> None:
        self.raise_()
        self.activateWindow()
        winapi.force_foreground(int(self.winId()))
        doc = self.current()
        if doc:
            doc.setFocus()

    def _on_app_state(self, state) -> None:
        if (state != Qt.ApplicationState.ApplicationActive and self.isVisible()
                and self.settings["hide_on_focus_loss"] and not self.pinned
                and QApplication.activeModalWidget() is None):
            self.hide_animated()

    def _escape(self) -> None:
        if self.find_bar.isVisible():
            self.find_bar.close_bar()
        else:
            self.hide_animated()

    # ================================================================
    # Onglets
    # ================================================================
    def docs(self) -> list[Document]:
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def current(self) -> Document | None:
        w = self.tabs.currentWidget()
        return w if isinstance(w, Document) else None

    def _next_untitled(self) -> str:
        used = {d.untitled_name for d in self.docs() if d.path is None}
        n = 1
        while f"Sans titre {n}" in used:
            n += 1
        return f"Sans titre {n}"

    def new_tab(self, text: str = "", path: str | None = None, focus: bool = True) -> Document:
        doc = Document(self._next_untitled())
        self._style_doc(doc)
        if text:
            doc.setPlainText(text)
        doc.path = path
        doc.document().setModified(False)
        doc.modificationChanged.connect(lambda _m, d=doc: self._refresh_tab(d))
        doc.textChanged.connect(self._on_text_changed)
        doc.cursorPositionChanged.connect(self._update_status)
        doc.filesDropped.connect(self.open_files)
        idx = self.tabs.addTab(doc, doc.title())
        if focus:
            self.tabs.setCurrentIndex(idx)
            doc.setFocus()
        self._refresh_tab(doc)
        return doc

    def _refresh_tab(self, doc: Document) -> None:
        i = self.tabs.indexOf(doc)
        if i < 0:
            return
        self.tabs.setTabText(i, ("● " if doc.is_modified() else "") + doc.title())
        self.tabs.setTabToolTip(i, doc.path or doc.title())
        if doc is self.current():
            self._update_status()

    def close_tab(self, index: int) -> None:
        doc = self.tabs.widget(index)
        if not isinstance(doc, Document):
            return
        if doc.is_modified() and doc.toPlainText():
            self.tabs.setCurrentIndex(index)
            r = QMessageBox.question(
                self, APP_NAME, f"Enregistrer les modifications de « {doc.title()} » ?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if r == QMessageBox.StandardButton.Cancel:
                return
            if r == QMessageBox.StandardButton.Save and not self._save(doc):
                return
        self.tabs.removeTab(index)
        doc.deleteLater()
        if self.tabs.count() == 0:
            self.new_tab()
        self._schedule_session()

    def _cycle(self, step: int) -> None:
        n = self.tabs.count()
        if n:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + step) % n)

    def _goto_tab(self, i: int) -> None:
        n = self.tabs.count()
        if n:
            self.tabs.setCurrentIndex(n - 1 if i == 9 else min(i - 1, n - 1))

    def _on_current_changed(self, _i: int) -> None:
        self._update_status()
        doc = self.current()
        if doc and self.isVisible():
            doc.setFocus()

    def _on_text_changed(self) -> None:
        self._update_status()
        self._schedule_session()

    # ================================================================
    # Fichiers
    # ================================================================
    def open_dialog(self) -> None:
        start = str(Path(self.current().path).parent) if self.current() and self.current().path else ""
        files, _ = QFileDialog.getOpenFileNames(self, "Ouvrir", start, FILE_FILTER)
        self.open_files(files)

    def open_files(self, files: list[str]) -> None:
        for f in files:
            p = str(Path(f).resolve())
            existing = next((d for d in self.docs() if d.path and Path(d.path) == Path(p)), None)
            if existing:
                self.tabs.setCurrentWidget(existing)
                continue
            if not Path(p).is_file():
                continue
            cur = self.current()
            doc = cur if cur and cur.is_empty_untitled() and not cur.is_modified() else self.new_tab()
            try:
                doc.load(p)
            except OSError as exc:
                QMessageBox.warning(self, APP_NAME, f"Impossible d'ouvrir {p} :\n{exc}")
                continue
            self.tabs.setCurrentWidget(doc)
            self._refresh_tab(doc)
        self._schedule_session()

    def _save(self, doc: Document, save_as: bool = False) -> bool:
        path = doc.path
        if save_as or not path:
            suggested = path or str(Path.home() / "Documents" / f"{doc.title()}.txt")
            path, _ = QFileDialog.getSaveFileName(self, "Enregistrer sous", suggested, FILE_FILTER)
            if not path:
                return False
        try:
            doc.save(path)
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"Échec de l'enregistrement :\n{exc}")
            return False
        self._refresh_tab(doc)
        self._schedule_session()
        return True

    def save_current(self) -> None:
        if self.current():
            self._save(self.current())

    def save_current_as(self) -> None:
        if self.current():
            self._save(self.current(), save_as=True)

    def save_all(self) -> None:
        for d in self.docs():
            if d.is_modified() and d.path:
                self._save(d)

    def _set_encoding(self, enc: str) -> None:
        if self.current():
            self.current().encoding = enc
            self.current().document().setModified(True)
            self._update_status()

    def _set_eol(self, eol: str) -> None:
        if self.current():
            self.current().eol = eol
            self.current().document().setModified(True)
            self._update_status()

    def _sync_doc_menus(self) -> None:
        doc = self.current()
        for menu, attr in ((self.enc_menu, "encoding"), (self.eol_menu, "eol")):
            for a in menu.actions():
                a.setChecked(bool(doc) and a.data() == getattr(doc, attr))

    def print_current(self) -> None:
        doc = self.current()
        if not doc:
            return
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        printer = QPrinter()
        dlg = QPrintDialog(printer, self)
        if dlg.exec():
            doc.document().print_(printer)

    # ================================================================
    # Édition
    # ================================================================
    def go_to_line(self) -> None:
        doc = self.current()
        if not doc:
            return
        total = doc.blockCount()
        line, ok = QInputDialog.getInt(self, "Atteindre", f"Ligne (1 – {total}) :",
                                       doc.cursor_info()[0], 1, total)
        if ok:
            doc.go_to_line(line)

    def insert_datetime(self) -> None:
        if self.current():
            self.current().insertPlainText(datetime.now().strftime("%H:%M %d/%m/%Y"))

    def duplicate_line(self) -> None:
        doc = self.current()
        if not doc:
            return
        c = doc.textCursor()
        text = c.block().text()
        c.movePosition(c.MoveOperation.EndOfBlock)
        c.insertText("\n" + text)
        doc.setTextCursor(c)

    # ================================================================
    # Barre d'état
    # ================================================================
    def _update_status(self) -> None:
        doc = self.current()
        if not doc:
            return
        ln, col = doc.cursor_info()
        self.lbl_path.setText(doc.path or doc.title())
        self.lbl_pos.setText(f"Ln {ln}, Col {col}")
        self.lbl_len.setText(f"{len(doc.toPlainText())} caractères")
        base = int(self.settings["font_size"])
        self.lbl_zoom.setText(f"{round((base + self.settings['zoom']) * 100 / base)} %")
        self.lbl_eol.setText(EOLS.get(doc.eol, "?"))
        self.lbl_enc.setText(ENCODINGS.get(doc.encoding, doc.encoding))

    # ================================================================
    # Session (restaure les onglets, même non enregistrés, comme le Bloc-notes de Windows 11)
    # ================================================================
    def _schedule_session(self) -> None:
        self._session_timer.start()

    def save_session(self) -> None:
        tabs = []
        for d in self.docs():
            if d.is_empty_untitled():
                continue
            c = d.textCursor()
            tabs.append({
                "path": d.path,
                "untitled": d.untitled_name,
                "encoding": d.encoding,
                "eol": d.eol,
                "modified": d.is_modified(),
                "content": d.toPlainText() if (d.is_modified() or not d.path) else None,
                "cursor": c.position(),
            })
        data = {"version": 1, "current": self.tabs.currentIndex(), "tabs": tabs}
        try:
            tmp = self._session_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._session_path)
        except OSError:
            pass

    def restore_session(self) -> None:
        try:
            data = json.loads(self._session_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for t in data.get("tabs", []):
            doc = self.new_tab(focus=False)
            doc.untitled_name = t.get("untitled") or doc.untitled_name
            path = t.get("path")
            try:
                if t.get("content") is None and path and Path(path).is_file():
                    doc.load(path)
                elif t.get("content") is not None:
                    doc.setPlainText(t["content"])
                    doc.path = path
                    doc.encoding = t.get("encoding", "utf-8")
                    doc.eol = t.get("eol", "\r\n")
                    doc.document().setModified(bool(t.get("modified")))
                else:
                    self.tabs.removeTab(self.tabs.indexOf(doc))
                    doc.deleteLater()
                    continue
            except OSError:
                continue
            c = doc.textCursor()
            c.setPosition(min(int(t.get("cursor", 0)), len(doc.toPlainText())))
            doc.setTextCursor(c)
            self._refresh_tab(doc)
        cur = int(data.get("current", 0))
        if 0 <= cur < self.tabs.count():
            self.tabs.setCurrentIndex(cur)

    # ================================================================
    # Divers
    # ================================================================
    def about(self) -> None:
        QMessageBox.about(
            self, f"À propos de {APP_NAME}",
            f"<b>{APP_NAME} {APP_VERSION}</b><br>Bloc-notes déroulant façon Quake.<br>"
            f"Raccourci : <b>{self.settings['hotkey'].get('label', '')}</b><br><br>"
            "ScriptoriumII — github.com/ScriptoriumII",
        )

    def quit_app(self) -> None:
        self.save_session()
        self.hotkey.unregister()
        self.tray.hide()
        QApplication.instance().quit()

    def closeEvent(self, e):  # noqa: N802  (Alt+F4 masque au lieu de quitter)
        e.ignore()
        self.hide_animated()
