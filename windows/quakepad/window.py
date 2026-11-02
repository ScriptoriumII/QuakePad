"""Fenêtre principale : bloc-notes à onglets qui glisse depuis un bord de l'écran (mode Quake)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QEasingCurve, QMarginsF, QPropertyAnimation, QRect, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction, QColor, QCursor, QFont, QGuiApplication, QIcon, QKeySequence, QPageLayout,
    QPageSize, QPainter, QTextListFormat,
)
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QComboBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QInputDialog,
    QLabel, QLayout, QMenu, QMessageBox, QSizePolicy, QSystemTrayIcon, QTabBar, QTabWidget, QTextEdit,
    QToolBar, QToolButton, QVBoxLayout, QWidget,
)

from . import winapi
from .dialogs import SettingsDialog, TableDialog
from .editor import IMAGE_EXTS, Document, format_for_path
from .findbar import FindBar
from .icons import icon
from .settings import APP_NAME, APP_VERSION, Settings, app_dir
from .ai import AICorrector, apply_corrections, collect_blocks
from .spell import SpellChecker, document_text
from .textio import ENCODINGS, EOLS
from .theme import palette, qpalette, stylesheet

OPEN_FILTER = ("Textes et notes (*.txt *.md *.html *.htm *.log *.ini *.cfg *.conf *.json *.yaml *.yml "
               "*.ps1 *.py *.sh *.csv *.xml);;Tous les fichiers (*)")
SAVE_FILTERS = {
    "txt": "Texte brut (*.txt)",
    "html": "Document enrichi avec images (*.html)",
    "md": "Markdown (*.md)",
}
IMAGE_FILTER = "Images (" + " ".join(f"*{e}" for e in sorted(IMAGE_EXTS)) + ")"
OPPOSITE = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}
FONT_SIZES = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48, 72]


class EdgeHandle(QWidget):
    """Bord redimensionnable. role = "depth" (bord intérieur) ou "span" (bords latéraux)."""

    def __init__(self, window: "QuakeWindow", side: str):
        super().__init__(window)
        self.side = side
        self.role = "span"
        self._win = window
        self._start = None
        horizontal = side in ("top", "bottom")
        if horizontal:
            self.setFixedHeight(6)
        else:
            self.setFixedWidth(6)
        self.setCursor(Qt.CursorShape.SizeVerCursor if horizontal else Qt.CursorShape.SizeHorCursor)
        self.setMouseTracking(True)

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        pal = palette(self._win.settings["theme"])
        p.fillRect(self.rect(), QColor(pal["raised"] if self.underMouse() else pal["surface"]))
        if self.role == "depth":  # liseré d'accent côté contenu, comme Windows Terminal
            r = self.rect()
            accent = QColor(pal["accent"])
            if self.side == "bottom":
                p.fillRect(0, 0, r.width(), 2, accent)
            elif self.side == "top":
                p.fillRect(0, r.height() - 2, r.width(), 2, accent)
            elif self.side == "right":
                p.fillRect(0, 0, 2, r.height(), accent)
            else:
                p.fillRect(r.width() - 2, 0, 2, r.height(), accent)

    def enterEvent(self, e):  # noqa: N802
        self.update()

    def leaveEvent(self, e):  # noqa: N802
        self.update()

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._start = e.globalPosition()
            self._win.begin_resize()

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._start is None:
            return
        d = e.globalPosition() - self._start
        delta = d.y() if self.side in ("top", "bottom") else d.x()
        sign = 1 if self.side in ("bottom", "right") else -1
        self._win.drag_resize(self.role, sign * delta)

    def mouseReleaseEvent(self, e):  # noqa: N802
        if self._start is not None:
            self._start = None
            self._win.end_resize()


class _DialogWatcher(QObject):
    """Place chaque boîte de dialogue au-dessus de QuakePad (fenêtre « toujours au premier plan »)."""

    def __init__(self, window: "QuakeWindow"):
        super().__init__(window)
        self._win = window

    def eventFilter(self, obj, ev):  # noqa: N802
        if isinstance(obj, QDialog) and obj.isWindow():
            t = ev.type()
            if t == QEvent.Type.Show:
                self._win.dialog_opened(obj)
            elif t in (QEvent.Type.Hide, QEvent.Type.Close):
                QTimer.singleShot(0, self._win.dialog_closed)
        return False


class QuakeWindow(QWidget):
    def __init__(self, settings: Settings, app_icon: QIcon):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setObjectName("QuakeRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon)
        self.settings = settings
        self.app_icon = app_icon
        from .app import resource
        self.assets_dir = str(Path(resource("quakepad.png")).parent)
        self.pinned = False
        self._anim: QPropertyAnimation | None = None
        self._hiding = False
        self._guard_plus = False
        self._resize_start: dict | None = None
        self._screen_obj = None
        self._session_path = app_dir() / "session.json"
        self._actions: dict[str, tuple[QAction, str, str]] = {}  # id -> (action, libellé, défaut)
        self._icon_actions: list[tuple[object, str]] = []

        # --- Onglets + onglet « + » --------------------------------------------
        self.tabs = QTabWidget(documentMode=True, tabsClosable=True, movable=True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_current_changed)
        bar = self.tabs.tabBar()
        bar.setObjectName("MainTabs")
        bar.setExpanding(False)
        bar.setElideMode(Qt.TextElideMode.ElideMiddle)
        bar.tabMoved.connect(self._keep_plus_last)
        self._plus = QWidget()
        self._guard_plus = True  # pas de création automatique pendant l'initialisation
        self.tabs.addTab(self._plus, "+")
        bar.setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
        bar.setTabButton(0, QTabBar.ButtonPosition.LeftSide, None)
        bar.setTabToolTip(0, "Nouvel onglet (Ctrl+N)")

        corner = QWidget()
        corner.setObjectName("TopBar")
        cl = QHBoxLayout(corner)
        cl.setContentsMargins(4, 0, 6, 0)
        cl.setSpacing(2)
        self.pin_btn = QToolButton(toolTip="Épingler : ne pas réduire quand je clique ailleurs", checkable=True)
        self.pin_btn.toggled.connect(self._set_pinned)
        self.menu_btn = QToolButton(toolTip="Menu")
        self.menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.hide_btn = QToolButton(toolTip="Masquer (Échap)")
        self.hide_btn.clicked.connect(self.hide_animated)
        for b, name in ((self.pin_btn, "pin"), (self.menu_btn, "menu"), (self.hide_btn, "hide")):
            cl.addWidget(b)
            self._icon_actions.append((b, name))
        self.tabs.setCornerWidget(corner, Qt.Corner.TopRightCorner)

        self.find_bar = FindBar(self.current, self)
        self.find_bar.hide()
        self.find_bar.closed.connect(lambda: self.current() and self.current().setFocus())

        self.ai = AICorrector(self)
        self.ai.finished.connect(self._ai_done)
        self.ai.failed.connect(self._ai_failed)
        self._ai_busy = False

        self.spell = SpellChecker(self)
        self.spell.finished.connect(self._spell_done)
        self.spell.failed.connect(self._spell_failed)

        # --- Barre d'état ------------------------------------------------------
        self.status = QWidget()
        self.status.setObjectName("StatusBar")
        sl = QHBoxLayout(self.status)
        sl.setContentsMargins(8, 3, 8, 3)
        self.lbl_path = QLabel()
        self.lbl_info = QLabel()
        self.lbl_pos = QLabel()
        self.lbl_len = QLabel()
        self.lbl_zoom = QLabel()
        self.lbl_eol = QLabel()
        self.lbl_enc = QLabel()
        self.lbl_hotkey = QLabel()
        sl.addWidget(self.lbl_path, 1)
        for w in (self.lbl_info, self.lbl_pos, self.lbl_len, self.lbl_zoom, self.lbl_eol, self.lbl_enc,
                  self.lbl_hotkey):
            sl.addWidget(w)
        self._info_timer = QTimer(self, singleShot=True, interval=8000)
        self._info_timer.timeout.connect(lambda: self.lbl_info.setText(""))

        self._build_actions()
        self._build_format_bar()

        content = QWidget()
        cv = QVBoxLayout(content)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        cv.addWidget(self.tabs, 1)
        cv.addWidget(self.find_bar)
        cv.addWidget(self.status)
        # La barre de mise en forme est superposée sous les onglets, au-dessus du texte.
        self.format_bar.setParent(self.tabs)

        self.handles = {side: EdgeHandle(self, side) for side in ("top", "bottom", "left", "right")}
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        grid.addWidget(self.handles["top"], 0, 1)
        grid.addWidget(self.handles["left"], 1, 0)
        grid.addWidget(content, 1, 1)
        grid.addWidget(self.handles["right"], 1, 2)
        grid.addWidget(self.handles["bottom"], 2, 1)
        grid.setRowStretch(1, 1)
        # La taille est pilotée par les pourcentages, pas par le contenu (positions gauche/droite étroites).
        grid.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setMinimumSize(200, 120)
        for lbl in (self.lbl_path, self.lbl_info):
            lbl.setMinimumWidth(0)
            lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        grid.setColumnStretch(1, 1)

        self._build_tray()

        self._session_timer = QTimer(self, singleShot=True, interval=1200)
        self._session_timer.timeout.connect(self.save_session)

        self.hotkey = winapi.GlobalHotkey(self)
        self.hotkey.activated.connect(self.toggle)
        QGuiApplication.instance().applicationStateChanged.connect(self._on_app_state)
        self._dialog_watcher = _DialogWatcher(self)
        QApplication.instance().installEventFilter(self._dialog_watcher)
        self._native_dialog_depth = 0
        try:
            QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _s: self._on_system_theme())
        except AttributeError:
            pass

        self.apply_settings()
        self.restore_session()
        if not self.docs():
            self.new_tab()
        self._guard_plus = False

    # ================================================================
    # Actions, raccourcis personnalisables et menus
    # ================================================================
    def _act(self, aid: str, text: str, slot, default: str = "", checkable=False, checked=False,
             icon_name: str | None = None, configurable: bool = True) -> QAction:
        a = QAction(text, self)
        a.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        if checkable:
            a.setCheckable(True)
            a.setChecked(checked)
            a.toggled.connect(slot)
        else:
            a.triggered.connect(lambda _=False: slot())
        if icon_name:
            self._icon_actions.append((a, icon_name))
        self.addAction(a)
        if configurable:
            self._actions[aid] = (a, text, default)
        else:
            a.setShortcut(QKeySequence(default))
        return a

    def apply_shortcuts(self) -> None:
        custom = self.settings.get("shortcuts", {})
        for aid, (a, _label, default) in self._actions.items():
            seq = custom.get(aid, default)
            a.setShortcut(QKeySequence(seq) if seq else QKeySequence())
            base = a.toolTip().split(" (")[0] if a.toolTip() else a.text()
            native = a.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
            a.setToolTip(f"{base} ({native})" if native else base)

    def shortcut_table(self) -> list[tuple[str, str, str, str]]:
        custom = self.settings.get("shortcuts", {})
        return [(aid, label.replace("…", ""), default, custom.get(aid, default))
                for aid, (_a, label, default) in self._actions.items()]

    def _build_actions(self) -> None:
        m = QMenu(self)
        A = self._act

        f = m.addMenu("Fichier")
        f.addAction(A("file.new", "Nouvel onglet", self.new_tab, "Ctrl+N"))
        f.addAction(A("file.open", "Ouvrir…", self.open_dialog, "Ctrl+O"))
        f.addAction(A("file.save", "Enregistrer", self.save_current, "Ctrl+S"))
        f.addAction(A("file.saveas", "Enregistrer sous…", self.save_current_as, "Ctrl+Shift+S"))
        f.addAction(A("file.saveall", "Enregistrer tout", self.save_all, "Ctrl+Alt+S"))
        f.addSeparator()
        f.addAction(A("file.pdf", "Exporter en PDF…", self.export_pdf, "Ctrl+Shift+E", icon_name="pdf"))
        f.addAction(A("file.print", "Imprimer…", self.print_current, "Ctrl+P"))
        f.addSeparator()
        self.enc_menu = f.addMenu("Encodage (texte brut)")
        for key, label in ENCODINGS.items():
            a = self.enc_menu.addAction(label)
            a.setData(key)
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, k=key: self._set_encoding(k))
        self.eol_menu = f.addMenu("Fins de ligne (texte brut)")
        for key, label in EOLS.items():
            a = self.eol_menu.addAction(label)
            a.setData(key)
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, k=key: self._set_eol(k))
        f.addSeparator()
        f.addAction(A("file.close", "Fermer l'onglet", lambda: self.close_tab(self.tabs.currentIndex()), "Ctrl+W"))

        e = m.addMenu("Édition")
        e.addAction(A("edit.find", "Rechercher…", lambda: self.find_bar.open_bar(False), "Ctrl+F"))
        e.addAction(A("edit.replace", "Remplacer…", lambda: self.find_bar.open_bar(True), "Ctrl+H"))
        e.addAction(A("edit.findnext", "Occurrence suivante", lambda: self.find_bar.find(), "F3"))
        e.addAction(A("edit.findprev", "Occurrence précédente", lambda: self.find_bar.find(backward=True), "Shift+F3"))
        e.addAction(A("edit.goto", "Atteindre la ligne…", self.go_to_line, "Ctrl+G"))
        e.addSeparator()
        e.addAction(A("edit.pasteplain", "Coller sans mise en forme", lambda: self._doc_call("paste_plain"),
                      "Ctrl+Shift+V"))
        e.addAction(A("edit.date", "Insérer date/heure", self.insert_datetime, "F5"))
        e.addAction(A("edit.dupline", "Dupliquer la ligne", self.duplicate_line, "Ctrl+D"))
        e.addSeparator()
        e.addAction(A("spell.ai", "Corriger automatiquement avec l'IA", self.ai_correct, "Ctrl+F7",
                      icon_name="ai"))
        e.addAction(A("spell.check", "Vérifier mot par mot (LanguageTool)", self.check_spelling, "F7",
                      icon_name="spell"))
        e.addAction(A("spell.next", "Faute suivante", self.next_issue, "F8", icon_name="next_error"))

        fm = m.addMenu("Format")
        self.act_bold = A("fmt.bold", "Gras", lambda: self._doc_call("toggle_bold"), "Ctrl+B", icon_name="bold")
        self.act_italic = A("fmt.italic", "Italique", lambda: self._doc_call("toggle_italic"), "Ctrl+I",
                            icon_name="italic")
        self.act_underline = A("fmt.underline", "Souligné", lambda: self._doc_call("toggle_underline"), "Ctrl+U",
                               icon_name="underline")
        self.act_strike = A("fmt.strike", "Barré", lambda: self._doc_call("toggle_strike"), "Ctrl+Shift+X",
                            icon_name="strike")
        for a in (self.act_bold, self.act_italic, self.act_underline, self.act_strike):
            a.setCheckable(True)
            fm.addAction(a)
        fm.addSeparator()
        self.act_size_up = A("fmt.sizeup", "Agrandir le texte", lambda: self._doc_call("step_size", 1), "Ctrl+]",
                             icon_name="size_up")
        self.act_size_down = A("fmt.sizedown", "Réduire le texte", lambda: self._doc_call("step_size", -1),
                               "Ctrl+[", icon_name="size_down")
        self.act_color = A("fmt.color", "Couleur du texte…", self.pick_color, "", icon_name="color")
        fm.addActions([self.act_size_up, self.act_size_down, self.act_color])
        fm.addSeparator()
        self.act_bullets = A("fmt.bullets", "Liste à puces",
                             lambda: self._doc_call("toggle_list", QTextListFormat.Style.ListDisc), "Ctrl+Shift+L",
                             icon_name="list_bullet")
        self.act_numbers = A("fmt.numbers", "Liste numérotée",
                             lambda: self._doc_call("toggle_list", QTextListFormat.Style.ListDecimal),
                             "Ctrl+Shift+O", icon_name="list_number")
        fm.addActions([self.act_bullets, self.act_numbers])
        fm.addSeparator()
        self.act_table = A("insert.table", "Insérer un tableau…", self.insert_table, "Ctrl+Alt+T", icon_name="table")
        self.act_image = A("insert.image", "Insérer une image…", self.insert_image, "Ctrl+Shift+I",
                           icon_name="image")
        self.act_clear = A("fmt.clear", "Effacer la mise en forme", lambda: self._doc_call("clear_formatting"),
                           "Ctrl+Space", icon_name="clear")
        fm.addActions([self.act_table, self.act_image, self.act_clear])

        v = m.addMenu("Affichage")
        self.act_toolbar = A("view.toolbar", "Barre de mise en forme", self._set_toolbar, "Ctrl+Shift+T",
                             checkable=True, checked=self.settings["show_toolbar"])
        self.act_wrap = A("view.wrap", "Retour automatique à la ligne", self._set_wrap, "Alt+Z",
                          checkable=True, checked=self.settings["word_wrap"])
        self.act_status = A("view.status", "Barre d'état", self._set_statusbar, "",
                            checkable=True, checked=self.settings["show_statusbar"])
        v.addActions([self.act_toolbar, self.act_wrap, self.act_status])
        self.edge_menu = v.addMenu("Position de la fenêtre")
        from .settings import EDGES
        for key, label in EDGES.items():
            a = self.edge_menu.addAction(label)
            a.setData(key)
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, k=key: self.set_edge(k))
        self.theme_menu = v.addMenu("Thème")
        from .theme import THEMES
        for key, label in THEMES.items():
            a = self.theme_menu.addAction(label)
            a.setData(key)
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, k=key: self.set_theme(k))
        v.addSeparator()
        v.addAction(A("view.zoomin", "Zoom avant", lambda: self.zoom(+1), "Ctrl+="))
        v.addAction(A("view.zoomout", "Zoom arrière", lambda: self.zoom(-1), "Ctrl+-"))
        v.addAction(A("view.zoomreset", "Zoom par défaut", lambda: self.zoom(0, reset=True), "Ctrl+0"))

        m.addSeparator()
        m.addAction(A("app.settings", "Paramètres…", self.open_settings, "Ctrl+,"))
        m.addAction(A("app.about", "À propos de QuakePad", self.about, ""))
        m.addSeparator()
        m.addAction(A("app.quit", "Quitter", self.quit_app, "Ctrl+Q"))
        m.aboutToShow.connect(self._sync_menus)
        self.menu_btn.setMenu(m)

        # Raccourcis sans entrée de menu (également personnalisables)
        A("tab.next", "Onglet suivant", lambda: self._cycle(+1), "Ctrl+Tab")
        A("tab.prev", "Onglet précédent", lambda: self._cycle(-1), "Ctrl+Shift+Tab")
        A("app.hide", "Masquer la fenêtre", self._escape, "Esc")
        for i in range(1, 10):
            A(f"tab.{i}", f"Aller à l'onglet {i}", lambda i=i: self._goto_tab(i), f"Alt+{i}", configurable=False)

    def _build_format_bar(self) -> None:
        tb = QToolBar("Mise en forme")
        tb.setObjectName("FormatBar")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setIconSize(QSize(18, 18))
        tb.addAction(self.act_size_down)
        self.size_box = QComboBox(editable=True)
        self.size_box.setToolTip("Taille du texte")
        self.size_box.addItems([str(s) for s in FONT_SIZES])
        self.size_box.setFixedWidth(64)
        self.size_box.activated.connect(lambda _i: self._apply_size_box())
        self.size_box.lineEdit().returnPressed.connect(self._apply_size_box)
        tb.addWidget(self.size_box)
        tb.addAction(self.act_size_up)
        tb.addSeparator()
        tb.addActions([self.act_bold, self.act_italic, self.act_underline, self.act_strike, self.act_color])
        tb.addSeparator()
        tb.addActions([self.act_bullets, self.act_numbers])
        tb.addSeparator()
        self.table_btn = QToolButton()
        self.table_btn.setDefaultAction(self.act_table)
        self.table_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        tmenu = QMenu(self.table_btn)
        tmenu.addAction("Insérer un tableau…", self.insert_table)
        tmenu.addSeparator()
        for label, op in (("Ligne au-dessus", "row_above"), ("Ligne en dessous", "row_below"),
                          ("Colonne à gauche", "col_left"), ("Colonne à droite", "col_right"),
                          ("Supprimer la ligne", "del_row"), ("Supprimer la colonne", "del_col")):
            tmenu.addAction(label, lambda o=op: self._table_op(o))
        self.table_btn.setMenu(tmenu)
        tb.addWidget(self.table_btn)
        tb.addAction(self.act_image)
        tb.addAction(self.act_clear)
        tb.addSeparator()
        tb.addAction(self._actions["spell.ai"][0])
        tb.addAction(self._actions["spell.check"][0])
        tb.addAction(self._actions["spell.next"][0])
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(self._actions["file.pdf"][0])
        self.format_bar = tb

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.app_icon, self)
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
    # Paramètres, thème, disposition
    # ================================================================
    def apply_settings(self) -> None:
        s = self.settings
        self.apply_theme()
        self.apply_shortcuts()
        self.apply_edge_layout()
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
        if self.isVisible() and not self._hiding:
            self.setGeometry(self._target_geometry())
        self._update_status()

    def apply_theme(self) -> None:
        app = QApplication.instance()
        app.setPalette(qpalette(self.settings["theme"]))
        app.setStyleSheet(stylesheet(self.settings["theme"], self.assets_dir))
        pal = palette(self.settings["theme"])
        for obj, name in self._icon_actions:
            obj.setIcon(icon(name, pal["muted"]))
        for h in getattr(self, "handles", {}).values():
            h.update()

    def _on_system_theme(self) -> None:
        if self.settings["theme"] == "system":
            self.apply_theme()

    def set_theme(self, key: str) -> None:
        self.settings["theme"] = key
        self.settings.save()
        self.apply_theme()

    def apply_edge_layout(self) -> None:
        edge = self.settings["edge"]
        inner = OPPOSITE[edge]
        lateral = ("left", "right") if edge in ("top", "bottom") else ("top", "bottom")
        for side, h in self.handles.items():
            if side == inner:
                h.role, visible = "depth", True
            elif side in lateral:
                h.role, visible = "span", True
            else:
                visible = False
            h.setVisible(visible)
            h.update()
        self._position_format_bar()

    def _position_format_bar(self) -> None:
        """Superpose la barre de mise en forme juste sous la barre d'onglets."""
        bar = self.tabs.tabBar()
        h = self.format_bar.sizeHint().height() if self.settings["show_toolbar"] else 0
        self.format_bar.setVisible(h > 0)
        self.format_bar.setGeometry(0, bar.geometry().bottom() + 1, self.tabs.width(), h)
        self.format_bar.raise_()
        self.tabs.setStyleSheet(f"QTabWidget::pane {{ margin-top: {h}px; border: none; }}")

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        if hasattr(self, "format_bar"):
            self._position_format_bar()

    def set_edge(self, edge: str) -> None:
        self.settings["edge"] = edge
        self.settings.save()
        self.apply_edge_layout()
        if self.isVisible():
            self.setGeometry(self._target_geometry())

    def _font(self) -> QFont:
        font = QFont(self.settings["font_family"])
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(max(5, int(self.settings["font_size"]) + int(self.settings["zoom"])))
        return font

    def _style_doc(self, doc: Document) -> None:
        doc.apply_font(self._font())
        doc.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth if self.settings["word_wrap"]
                            else QTextEdit.LineWrapMode.NoWrap)

    def open_settings(self, tab: int = 0) -> None:
        self.hotkey.unregister()  # sinon la capture déclencherait le raccourci
        dlg = SettingsDialog(self.settings, self.shortcut_table(), self)
        dlg.tabs.setCurrentIndex(tab)
        dlg.setStyleSheet(stylesheet(self.settings["theme"], self.assets_dir))
        if dlg.exec():
            vals = dlg.values()
            if vals["start_with_windows"] != self.settings["start_with_windows"]:
                winapi.set_start_with_windows(vals["start_with_windows"])
            self.settings.update(vals)
            self.settings["shortcuts"] = vals["shortcuts"]
            self.settings.save()
            self.act_toolbar.setChecked(self.settings["show_toolbar"])
        self.apply_settings()

    def _set_toolbar(self, on: bool) -> None:
        self.settings["show_toolbar"] = on
        self.settings.save()
        self._position_format_bar()

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

    def _sync_menus(self) -> None:
        doc = self.current()
        for menu, attr in ((self.enc_menu, "encoding"), (self.eol_menu, "eol")):
            for a in menu.actions():
                a.setChecked(bool(doc) and a.data() == getattr(doc, attr))
        for a in self.edge_menu.actions():
            a.setChecked(a.data() == self.settings["edge"])
        for a in self.theme_menu.actions():
            a.setChecked(a.data() == self.settings["theme"])

    # ================================================================
    # Position, taille et animation
    # ================================================================
    def _screen(self):
        if self._screen_obj is not None and self._screen_obj in QGuiApplication.screens():
            return self._screen_obj
        return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

    def _target_geometry(self) -> QRect:
        ag = self._screen().availableGeometry()
        edge = self.settings["edge"]
        size = self.settings.size()
        if edge in ("top", "bottom"):
            w = round(ag.width() * size["span"] / 100)
            h = round(ag.height() * size["depth"] / 100)
            x = ag.x() + (ag.width() - w) // 2
            y = ag.y() if edge == "top" else ag.y() + ag.height() - h
        else:
            w = round(ag.width() * size["depth"] / 100)
            h = round(ag.height() * size["span"] / 100)
            y = ag.y() + (ag.height() - h) // 2
            x = ag.x() if edge == "left" else ag.x() + ag.width() - w
        return QRect(x, y, w, h)

    def _hidden_geometry(self, g: QRect) -> QRect:
        edge = self.settings["edge"]
        dx = {"left": -g.width(), "right": g.width()}.get(edge, 0)
        dy = {"top": -g.height(), "bottom": g.height()}.get(edge, 0)
        return g.translated(dx, dy)

    def begin_resize(self) -> None:
        ag = self._screen().availableGeometry()
        vertical = self.settings["edge"] in ("top", "bottom")
        self._resize_start = {
            "depth_px": self.height() if vertical else self.width(),
            "span_px": self.width() if vertical else self.height(),
            "depth_axis": ag.height() if vertical else ag.width(),
            "span_axis": ag.width() if vertical else ag.height(),
        }

    def drag_resize(self, role: str, delta: float) -> None:
        st = self._resize_start
        if not st:
            return
        size = self.settings.size()
        if role == "depth":
            px = max(120, st["depth_px"] + delta)
            size["depth"] = max(10.0, min(100.0, px * 100 / st["depth_axis"]))
        else:  # étendue : redimensionnement symétrique (fenêtre centrée)
            px = max(240, st["span_px"] + 2 * delta)
            size["span"] = max(20.0, min(100.0, px * 100 / st["span_axis"]))
        self.setGeometry(self._target_geometry())

    def end_resize(self) -> None:
        self._resize_start = None
        size = self.settings.size()
        size["depth"] = round(size["depth"], 1)
        size["span"] = round(size["span"], 1)
        self.settings.save()  # mémorisé pour la prochaine session

    def _animate(self, start: QRect, end: QRect, on_done=None) -> None:
        if self._anim is not None:
            self._anim.stop()
            self._anim.deleteLater()
            self._anim = None
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
        if not self.isVisible():
            self._screen_obj = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        end = self._target_geometry()
        if not self.isVisible():
            self.setGeometry(self._hidden_geometry(end))
            self.show()
        self._activate()
        self._animate(self.geometry(), end)

    def hide_animated(self) -> None:
        if not self.isVisible() or self._hiding:
            return
        self._hiding = True
        self.save_session()
        g = self.geometry()

        def done():
            if self._hiding:
                self.hide()
                self._hiding = False

        self._animate(g, self._hidden_geometry(g), done)

    # --- Dialogues au premier plan ------------------------------------------
    def dialog_opened(self, dlg: QDialog) -> None:
        winapi.set_topmost(int(self.winId()), False)
        dlg.finished.connect(lambda _r: QTimer.singleShot(0, self.dialog_closed))

        def lift():
            winapi.set_topmost(int(dlg.winId()), True, activate=True)
            dlg.raise_()
            dlg.activateWindow()

        QTimer.singleShot(0, lift)

    def dialog_closed(self) -> None:
        """Rétablit « toujours au premier plan » quand plus aucun dialogue n'est ouvert."""
        if self._native_dialog_depth:
            return
        if any(isinstance(w, QDialog) and w.isVisible() for w in QApplication.topLevelWidgets()):
            return
        winapi.set_topmost(int(self.winId()), True)

    def native_dialog(self):
        """Contexte pour les dialogues natifs de Windows (Ouvrir, Enregistrer, Imprimer)."""
        window = self

        class _Ctx:
            def __enter__(self_):
                window._native_dialog_depth += 1
                winapi.set_topmost(int(window.winId()), False)

            def __exit__(self_, *exc):
                window._native_dialog_depth -= 1
                if window._native_dialog_depth == 0:
                    winapi.set_topmost(int(window.winId()), True)
                    window._activate()
                return False

        return _Ctx()

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
                and self._resize_start is None and QApplication.activeModalWidget() is None):
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
        return [w for w in (self.tabs.widget(i) for i in range(self.tabs.count())) if isinstance(w, Document)]

    def current(self) -> Document | None:
        w = self.tabs.currentWidget()
        return w if isinstance(w, Document) else None

    def _doc_call(self, method: str, *args) -> None:
        doc = self.current()
        if doc:
            getattr(doc, method)(*args)
            doc.setFocus()

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
        doc.document().modificationChanged.connect(lambda _m, d=doc: self._refresh_tab(d))
        doc.textChanged.connect(self._on_text_changed)
        doc.cursorPositionChanged.connect(self._update_status)
        doc.currentCharFormatChanged.connect(lambda _f, d=doc: self._sync_format_bar(d))
        doc.filesDropped.connect(self.open_files)
        prev, self._guard_plus = self._guard_plus, True
        idx = self.tabs.insertTab(self.tabs.indexOf(self._plus), doc, doc.title())
        if focus:
            self.tabs.setCurrentIndex(idx)
            doc.setFocus()
        self._guard_plus = prev
        self._refresh_tab(doc)
        return doc

    def _keep_plus_last(self, _from: int, _to: int) -> None:
        last = self.tabs.count() - 1
        i = self.tabs.indexOf(self._plus)
        if i != last and not self._guard_plus:
            self._guard_plus = True
            self.tabs.tabBar().moveTab(i, last)
            self._guard_plus = False

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
        if doc.is_modified() and not doc.document().isEmpty():
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
        prev, self._guard_plus = self._guard_plus, True
        self.tabs.removeTab(index)
        if self.tabs.currentWidget() is self._plus and self.docs():
            self.tabs.setCurrentIndex(max(0, min(index, len(self.docs())) - 1))
        self._guard_plus = prev
        doc.deleteLater()
        if not self.docs():
            self.new_tab()
        self._schedule_session()

    def _cycle(self, step: int) -> None:
        docs = self.docs()
        if docs:
            cur = self.current()
            i = docs.index(cur) if cur in docs else 0
            self.tabs.setCurrentWidget(docs[(i + step) % len(docs)])

    def _goto_tab(self, i: int) -> None:
        docs = self.docs()
        if docs:
            self.tabs.setCurrentWidget(docs[-1] if i == 9 else docs[min(i - 1, len(docs) - 1)])

    def _on_current_changed(self, _i: int) -> None:
        if self.tabs.currentWidget() is self._plus:
            if not self._guard_plus:
                self.new_tab()
            return
        self._update_status()
        doc = self.current()
        if doc:
            self._sync_format_bar(doc)
            if self.isVisible():
                doc.setFocus()

    def _on_text_changed(self) -> None:
        self._update_status()
        self._schedule_session()

    # ================================================================
    # Mise en forme
    # ================================================================
    def _sync_format_bar(self, doc: Document) -> None:
        if doc is not self.current():
            return
        f = doc.currentCharFormat()
        self.act_bold.setChecked(f.fontWeight() > QFont.Weight.Normal)
        self.act_italic.setChecked(f.fontItalic())
        self.act_underline.setChecked(f.fontUnderline())
        self.act_strike.setChecked(f.fontStrikeOut())
        size = doc.current_point_size()
        self.size_box.setEditText(f"{size:g}")

    def _apply_size_box(self) -> None:
        try:
            size = float(self.size_box.currentText().replace(",", "."))
        except ValueError:
            return
        self._doc_call("set_point_size", size)

    def pick_color(self) -> None:
        doc = self.current()
        if not doc:
            return
        color = QColorDialog.getColor(doc.textColor(), self, "Couleur du texte")
        if color.isValid():
            doc.set_color(color)

    def insert_table(self) -> None:
        doc = self.current()
        if not doc:
            return
        dlg = TableDialog(self)
        if dlg.exec():
            doc.insert_table(dlg.rows.value(), dlg.cols.value())
            doc.setFocus()

    def _table_op(self, op: str) -> None:
        doc = self.current()
        if doc and not doc.table_op(op):
            self._info("Placez le curseur dans un tableau.")

    def insert_image(self) -> None:
        doc = self.current()
        if not doc:
            return
        with self.native_dialog():
            files, _ = QFileDialog.getOpenFileNames(self, "Insérer une image", str(Path.home() / "Pictures"),
                                                    IMAGE_FILTER)
        for f in files:
            if not doc.insert_image_file(f):
                QMessageBox.warning(self, APP_NAME, f"Image illisible :\n{f}")
        doc.setFocus()

    # ================================================================
    # Correction orthographique et grammaticale
    # ================================================================
    def check_spelling(self) -> None:
        doc = self.current()
        if not doc:
            return
        text = document_text(doc.document())
        if not text.strip():
            self._info("Rien à corriger.")
            return
        doc._spell_snapshot = text
        self._info("Vérification orthographe et grammaire…", keep=True)
        self.spell.check(doc, text, self.settings["spell_server"], self.settings["spell_language"])

    def _spell_done(self, doc: Document, issues: list) -> None:
        if doc not in self.docs():
            return
        if document_text(doc.document()) != getattr(doc, "_spell_snapshot", None):
            self._info("Le texte a changé pendant la vérification : relancez (F7).")
            return
        doc.set_issues(issues)
        n = len(issues)
        if n == 0:
            self._info("✓ Aucune faute trouvée.")
        else:
            sp = sum(1 for i in issues if i.kind == "spelling")
            self._info(f"{n} correction(s) proposée(s) : {sp} orthographe, {n - sp} grammaire/style — "
                       "clic droit sur le mot souligné, F8 = suivante.")
            if doc is self.current():
                doc.next_issue()

    def _spell_failed(self, doc: Document, msg: str) -> None:
        self._info("Correction indisponible.")
        QMessageBox.warning(self, APP_NAME, f"La correction n'a pas pu être effectuée :\n{msg}\n\n"
                            f"Serveur : {self.settings['spell_server']}")

    # --- Correction automatique par IA ------------------------------------
    def ai_correct(self) -> None:
        doc = self.current()
        if not doc or self._ai_busy:
            return
        cfg = self.settings
        if cfg["ai_provider"] == "anthropic" and not cfg["anthropic_key"]:
            QMessageBox.information(self, APP_NAME, "Configurez d'abord l'IA : clé API Anthropic, "
                                    "ou une IA locale (Ollama) dans l'onglet Correction.")
            self.open_settings(tab=3)
            return
        selection = doc.textCursor().hasSelection()
        blocks = collect_blocks(doc, selection_only=selection)
        if not blocks:
            self._info("Rien à corriger.")
            return
        self._ai_busy = True
        doc._ai_snapshot = [t for _, t in blocks]
        doc.setReadOnly(True)  # évite tout décalage pendant la requête
        for aid in ("spell.ai",):
            self._actions[aid][0].setEnabled(False)
        what = "la sélection" if selection else "la note"
        model = cfg["anthropic_model"] if cfg["ai_provider"] == "anthropic" else cfg["openai_model"]
        self._info(f"✦ Correction de {what} par IA ({model})…", keep=True)
        self.ai.correct(doc, blocks, dict(cfg))

    def _ai_finish(self, doc: Document) -> None:
        self._ai_busy = False
        self._actions["spell.ai"][0].setEnabled(True)
        if doc in self.docs():
            doc.setReadOnly(False)

    def _ai_done(self, doc: Document, blocks: list, corrected: list) -> None:
        self._ai_finish(doc)
        if doc not in self.docs():
            return
        doc._applying_ai = True
        try:
            paras, edits, spans = apply_corrections(doc, blocks, corrected)
        finally:
            doc._applying_ai = False
        doc.issues = []  # les soulignements LanguageTool ne correspondent plus
        if edits:
            doc.flash_ranges(spans)
            self._info(f"✦ {edits} correction(s) dans {paras} paragraphe(s) — surlignées en vert, "
                       "Ctrl+Z pour tout annuler.")
        else:
            doc._paint_issues()
            self._info("✦ Aucune faute trouvée par l'IA.")

    def _ai_failed(self, doc: Document, msg: str) -> None:
        self._ai_finish(doc)
        self._info("Correction IA impossible.")
        QMessageBox.warning(self, APP_NAME, f"La correction par IA a échoué :\n{msg}")

    def next_issue(self) -> None:
        doc = self.current()
        if doc and not doc.next_issue():
            self._info("Aucune faute en attente (F7 pour vérifier).")

    # ================================================================
    # Fichiers
    # ================================================================
    def open_dialog(self) -> None:
        cur = self.current()
        start = str(Path(cur.path).parent) if cur and cur.path else str(Path.home() / "Documents")
        with self.native_dialog():
            files, _ = QFileDialog.getOpenFileNames(self, "Ouvrir", start, OPEN_FILTER)
        self.open_files(files)

    def open_files(self, files: list[str]) -> None:
        for f in files:
            p = str(Path(f).resolve())
            if Path(p).suffix.lower() in IMAGE_EXTS:
                doc = self.current() or self.new_tab()
                doc.insert_image_file(p)
                continue
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

    def _ask_save_path(self, doc: Document) -> str | None:
        fmt = doc.fmt
        base = Path(doc.path).stem if doc.path else doc.title()
        folder = Path(doc.path).parent if doc.path else Path.home() / "Documents"
        suggested = str(folder / f"{base}.{'html' if fmt == 'html' else fmt}")
        filters = ";;".join(list(SAVE_FILTERS.values()) + ["Tous les fichiers (*)"])
        with self.native_dialog():
            path, chosen = QFileDialog.getSaveFileName(self, "Enregistrer sous", suggested, filters,
                                                       SAVE_FILTERS.get(fmt, ""))
        if not path:
            return None
        if not Path(path).suffix:
            ext = next((k for k, v in SAVE_FILTERS.items() if v == chosen), "txt")
            path += f".{ext}"
        return path

    def _save(self, doc: Document, save_as: bool = False) -> bool:
        path = doc.path
        if save_as or not path:
            path = self._ask_save_path(doc)
            if not path:
                return False
        if doc.rich and format_for_path(path) == "txt":
            box = QMessageBox(QMessageBox.Icon.Question, APP_NAME,
                              "Ce document contient de la mise en forme, des tableaux ou des images, "
                              "qui seront perdus en texte brut (.txt).", parent=self)
            as_html = box.addButton("Enregistrer en .html", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Texte brut quand même", QMessageBox.ButtonRole.DestructiveRole)
            cancel = box.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is cancel:
                return False
            if box.clickedButton() is as_html:
                path = str(Path(path).with_suffix(".html"))
        try:
            doc.save(path)
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"Échec de l'enregistrement :\n{exc}")
            return False
        self._refresh_tab(doc)
        self._info(f"Enregistré : {Path(path).name}")
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

    def export_pdf(self, path: str | None = None) -> bool:
        doc = self.current()
        if not doc:
            return False
        if path is None:
            base = Path(doc.path).stem if doc.path else doc.title()
            folder = Path(doc.path).parent if doc.path else Path.home() / "Documents"
            with self.native_dialog():
                path, _ = QFileDialog.getSaveFileName(self, "Exporter en PDF", str(folder / f"{base}.pdf"),
                                                      "PDF (*.pdf)")
            if not path:
                return False
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
        from PySide6.QtPrintSupport import QPrinter

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        printer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                          QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter))
        printer.setDocName(doc.title())
        clone = doc.document().clone()
        clone.setDefaultFont(doc.document().defaultFont())
        clone.print_(printer)
        self._info(f"PDF exporté : {Path(path).name}")
        return True

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

    def print_current(self) -> None:
        doc = self.current()
        if not doc:
            return
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        printer = QPrinter()
        dlg = QPrintDialog(printer, self)
        with self.native_dialog():
            accepted = dlg.exec()
        if accepted:
            doc.document().print_(printer)

    # ================================================================
    # Édition
    # ================================================================
    def go_to_line(self) -> None:
        doc = self.current()
        if not doc:
            return
        total = doc.document().blockCount()
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
    def _info(self, text: str, keep: bool = False) -> None:
        self.lbl_info.setText(text)
        if keep:
            self._info_timer.stop()
        else:
            self._info_timer.start()

    def _update_status(self) -> None:
        doc = self.current()
        if not doc:
            return
        ln, col = doc.cursor_info()
        self.lbl_path.setText(doc.path or doc.title())
        self.lbl_pos.setText(f"Ln {ln}, Col {col}")
        self.lbl_len.setText(f"{doc.document().characterCount() - 1} caractères")
        base = int(self.settings["font_size"])
        self.lbl_zoom.setText(f"{round((base + self.settings['zoom']) * 100 / base)} %")
        fmt = doc.fmt
        if fmt == "txt":
            self.lbl_eol.setText(EOLS.get(doc.eol, "?"))
            self.lbl_enc.setText(ENCODINGS.get(doc.encoding, doc.encoding))
        else:
            self.lbl_eol.setText({"html": "Texte enrichi", "md": "Markdown"}[fmt])
            self.lbl_enc.setText("UTF-8")

    # ================================================================
    # Session (onglets restaurés, y compris non enregistrés, images et mise en forme)
    # ================================================================
    def _schedule_session(self) -> None:
        self._session_timer.start()

    def save_session(self) -> None:
        tabs = []
        for d in self.docs():
            if d.is_empty_untitled():
                continue
            entry = {
                "path": d.path, "untitled": d.untitled_name, "encoding": d.encoding, "eol": d.eol,
                "modified": d.is_modified(), "rich": d.rich, "cursor": d.textCursor().position(),
            }
            if d.is_modified() or not d.path:
                entry["html" if d.rich else "content"] = d.toHtml() if d.rich else d.toPlainText()
            tabs.append(entry)
        cur = self.current()
        data = {"version": 2, "current": self.docs().index(cur) if cur in self.docs() else 0, "tabs": tabs}
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
                if "html" in t:
                    doc.setHtml(t["html"])
                    doc.rich = True
                elif "content" in t and t["content"] is not None:
                    doc.setPlainText(t["content"])
                elif path and Path(path).is_file():
                    doc.load(path)
                else:
                    self.tabs.removeTab(self.tabs.indexOf(doc))
                    doc.deleteLater()
                    continue
                if "html" in t or t.get("content") is not None:
                    doc.path = path
                    doc.encoding = t.get("encoding", "utf-8")
                    doc.eol = t.get("eol", "\r\n")
                    doc.document().setModified(bool(t.get("modified")))
            except OSError:
                continue
            c = doc.textCursor()
            c.setPosition(min(int(t.get("cursor", 0)), doc.document().characterCount() - 1))
            doc.setTextCursor(c)
            self._refresh_tab(doc)
        docs = self.docs()
        cur = int(data.get("current", 0))
        if 0 <= cur < len(docs):
            self.tabs.setCurrentWidget(docs[cur])

    # ================================================================
    # Divers
    # ================================================================
    def about(self) -> None:
        QMessageBox.about(
            self, f"À propos de {APP_NAME}",
            f"<b>{APP_NAME} {APP_VERSION}</b><br>Bloc-notes déroulant façon Quake.<br>"
            f"Raccourci : <b>{self.settings['hotkey'].get('label', '')}</b><br><br>"
            "Correction : LanguageTool (languagetool.org)<br>"
            "ScriptoriumII — github.com/ScriptoriumII/QuakePad",
        )

    def quit_app(self) -> None:
        self._quitting = True
        QApplication.instance().removeEventFilter(self._dialog_watcher)
        self.save_session()
        self.hotkey.unregister()
        self.tray.hide()
        # exit() et non quit() : sous Qt 6, quit() demande d'abord aux fenêtres de se fermer,
        # et notre closeEvent (Alt+F4 = masquer) annulerait la sortie.
        QApplication.instance().exit(0)

    def closeEvent(self, e):  # noqa: N802  (Alt+F4 masque au lieu de quitter)
        if getattr(self, "_quitting", False):
            e.accept()
            return
        e.ignore()
        self.hide_animated()
