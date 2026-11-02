"""Fenêtre principale : bloc-notes à onglets qui glisse depuis un bord de l'écran (mode Quake)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QFont,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QTextListFormat,
)
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSystemTrayIcon,
    QTabBar,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import winapi
from .ai import AICorrector
from .correction import CorrectionMixin
from .dialogs import SettingsDialog
from .editor import Document
from .files import FilesMixin
from .findbar import FindBar
from .formatting import FormattingMixin
from .icons import icon
from .quake import QuakeMixin
from .session import SessionMixin
from .settings import APP_NAME, APP_VERSION, Settings, app_dir
from .spell import SpellChecker
from .tabs import TabsMixin
from .textio import ENCODINGS, EOLS
from .theme import palette, qpalette, stylesheet
from .updates_ui import UpdatesMixin
from .widgets import DialogWatcher, EdgeHandle, UsageIndicator

FONT_SIZES = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48, 72]


class QuakeWindow(
    QuakeMixin, TabsMixin, FilesMixin, FormattingMixin, CorrectionMixin, SessionMixin, UpdatesMixin, QWidget
):
    def __init__(self, settings: Settings, app_icon: QIcon):
        super().__init__(
            None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        )
        self.setObjectName("QuakeRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon)
        self.settings = settings
        self.app_icon = app_icon

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
        self.tabs = QTabWidget(documentMode=True, tabsClosable=False, movable=True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_current_changed)
        bar = self.tabs.tabBar()
        bar.setObjectName("MainTabs")
        bar.setExpanding(False)
        bar.setElideMode(Qt.TextElideMode.ElideMiddle)
        bar.tabMoved.connect(self._keep_plus_last)
        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar.customContextMenuRequested.connect(self._tab_context_menu)
        bar.tabBarDoubleClicked.connect(
            lambda i: self.rename_tab(i) if isinstance(self.tabs.widget(i), Document) else None
        )
        self._rename_edit = None
        self._plus = QWidget()
        self._guard_plus = True  # pas de création automatique pendant l'initialisation
        self.tabs.addTab(self._plus, "")
        # Bouton « Nouvel onglet » bien visible, accolé au dernier onglet
        self.new_tab_btn = QToolButton(text=" Nouvel onglet", toolTip="Nouvel onglet (Ctrl+N)")
        self.new_tab_btn.setObjectName("NewTabBtn")
        self.new_tab_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.new_tab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_tab_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.new_tab_btn.clicked.connect(lambda: self.new_tab())
        bar.setTabButton(0, QTabBar.ButtonPosition.LeftSide, self.new_tab_btn)
        bar.setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
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
            b.setObjectName("ChromeBtn")
            b.setAutoRaise(True)
            b.setIconSize(QSize(18, 18))
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
        sl.setContentsMargins(10, 4, 10, 4)
        sl.setSpacing(2)
        self.lbl_path = QLabel()
        self.lbl_info = QLabel()
        self.lbl_info.setObjectName("InfoLabel")
        self.lbl_pos = QLabel()
        self.lbl_len = QLabel()
        self.lbl_zoom = QLabel()
        self.lbl_eol = QLabel()
        self.lbl_enc = QLabel()
        self.lbl_hotkey = QLabel()
        self.usage = UsageIndicator()
        self.usage.clicked.connect(lambda: self.open_settings(tab=3))
        self.update_btn = QToolButton()
        self.update_btn.setObjectName("UpdateBtn")
        self.update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_btn.clicked.connect(lambda: self.prompt_update())
        self.update_btn.hide()
        sl.addWidget(self.lbl_path, 1)
        for w in (
            self.lbl_info,
            self.lbl_pos,
            self.lbl_len,
            self.lbl_zoom,
            self.lbl_eol,
            self.lbl_enc,
            self.update_btn,
            self.usage,
            self.lbl_hotkey,
        ):
            sl.addWidget(w)
        self._info_timer = QTimer(self, singleShot=True, interval=8000)
        self._info_timer.timeout.connect(lambda: self.lbl_info.setText(""))
        self._usage_timer = QTimer(self, interval=30_000)  # passage à minuit, quotas serveur…
        self._usage_timer.timeout.connect(self.update_usage)
        self._usage_timer.start()

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
        self._format_bar_pending = False
        self.tabs.installEventFilter(self)
        self.tabs.tabBar().installEventFilter(self)

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
        self.lbl_path.setMinimumWidth(0)
        self.lbl_path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.lbl_info.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        grid.setColumnStretch(1, 1)

        self._build_tray()

        self._session_timer = QTimer(self, singleShot=True, interval=1200)
        self._session_timer.timeout.connect(self.save_session)

        self.hotkey = winapi.GlobalHotkey(self)
        self.hotkey.activated.connect(self.toggle)
        QGuiApplication.instance().applicationStateChanged.connect(self._on_app_state)
        self._dialog_watcher = DialogWatcher(self)
        QApplication.instance().installEventFilter(self._dialog_watcher)
        self._native_dialog_depth = 0
        try:
            QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _s: self._on_system_theme())
        except AttributeError:
            pass

        self.apply_settings()
        self.update_usage()
        self.restore_session()
        self.init_updates()
        if not self.docs():
            self.new_tab()
        self._guard_plus = False

    # ================================================================
    # Actions, raccourcis personnalisables et menus
    # ================================================================
    def _act(
        self,
        aid: str,
        text: str,
        slot,
        default: str = "",
        checkable=False,
        checked=False,
        icon_name: str | None = None,
        configurable: bool = True,
    ) -> QAction:
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
        return [
            (aid, label.replace("…", ""), default, custom.get(aid, default))
            for aid, (_a, label, default) in self._actions.items()
        ]

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
        e.addAction(
            A("edit.pasteplain", "Coller sans mise en forme", lambda: self._doc_call("paste_plain"), "Ctrl+Shift+V")
        )
        e.addAction(A("edit.date", "Insérer date/heure", self.insert_datetime, "F5"))
        e.addAction(A("edit.dupline", "Dupliquer la ligne", self.duplicate_line, "Ctrl+D"))
        e.addSeparator()
        e.addAction(A("spell.ai", "Corriger automatiquement avec l'IA", self.ai_correct, "Ctrl+F7", icon_name="ai"))
        e.addAction(
            A("spell.check", "Vérifier mot par mot (LanguageTool)", self.check_spelling, "F7", icon_name="spell")
        )
        e.addAction(A("spell.next", "Faute suivante", self.next_issue, "F8", icon_name="next_error"))

        fm = m.addMenu("Format")
        self.act_bold = A("fmt.bold", "Gras", lambda: self._doc_call("toggle_bold"), "Ctrl+B", icon_name="bold")
        self.act_italic = A(
            "fmt.italic", "Italique", lambda: self._doc_call("toggle_italic"), "Ctrl+I", icon_name="italic"
        )
        self.act_underline = A(
            "fmt.underline", "Souligné", lambda: self._doc_call("toggle_underline"), "Ctrl+U", icon_name="underline"
        )
        self.act_strike = A(
            "fmt.strike", "Barré", lambda: self._doc_call("toggle_strike"), "Ctrl+Shift+X", icon_name="strike"
        )
        for a in (self.act_bold, self.act_italic, self.act_underline, self.act_strike):
            a.setCheckable(True)
            fm.addAction(a)
        fm.addSeparator()
        self.act_size_up = A(
            "fmt.sizeup", "Agrandir le texte", lambda: self._doc_call("step_size", 1), "Ctrl+]", icon_name="size_up"
        )
        self.act_size_down = A(
            "fmt.sizedown", "Réduire le texte", lambda: self._doc_call("step_size", -1), "Ctrl+[", icon_name="size_down"
        )
        self.act_color = A("fmt.color", "Couleur du texte…", self.pick_color, "", icon_name="color")
        fm.addActions([self.act_size_up, self.act_size_down, self.act_color])
        fm.addSeparator()
        self.act_bullets = A(
            "fmt.bullets",
            "Liste à puces",
            lambda: self._doc_call("toggle_list", QTextListFormat.Style.ListDisc),
            "Ctrl+Shift+L",
            icon_name="list_bullet",
        )
        self.act_numbers = A(
            "fmt.numbers",
            "Liste numérotée",
            lambda: self._doc_call("toggle_list", QTextListFormat.Style.ListDecimal),
            "Ctrl+Shift+O",
            icon_name="list_number",
        )
        fm.addActions([self.act_bullets, self.act_numbers])
        fm.addSeparator()
        self.act_table = A("insert.table", "Insérer un tableau…", self.insert_table, "Ctrl+Alt+T", icon_name="table")
        self.act_image = A("insert.image", "Insérer une image…", self.insert_image, "Ctrl+Shift+I", icon_name="image")
        self.act_clear = A(
            "fmt.clear",
            "Effacer la mise en forme",
            lambda: self._doc_call("clear_formatting"),
            "Ctrl+Space",
            icon_name="clear",
        )
        fm.addActions([self.act_table, self.act_image, self.act_clear])

        v = m.addMenu("Affichage")
        self.act_toolbar = A(
            "view.toolbar",
            "Barre de mise en forme",
            self._set_toolbar,
            "Ctrl+Shift+T",
            checkable=True,
            checked=self.settings["show_toolbar"],
        )
        self.act_wrap = A(
            "view.wrap",
            "Retour automatique à la ligne",
            self._set_wrap,
            "Alt+Z",
            checkable=True,
            checked=self.settings["word_wrap"],
        )
        self.act_status = A(
            "view.status",
            "Barre d'état",
            self._set_statusbar,
            "",
            checkable=True,
            checked=self.settings["show_statusbar"],
        )
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
        m.addAction(A("app.update", "Rechercher les mises à jour…", lambda: self.check_updates(manual=True), ""))
        m.addAction(A("app.datadir", "Ouvrir le dossier des données (journal, session)", self.open_data_dir, ""))
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
        tb.setIconSize(QSize(20, 20))
        tb.addAction(self.act_size_down)
        self.size_btn = QToolButton(text="11", toolTip="Taille du texte")
        self.size_btn.setObjectName("SizeBtn")
        self.size_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.size_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        size_menu = QMenu(self.size_btn)
        for sz in FONT_SIZES:
            size_menu.addAction(f"{sz} pt", lambda v=sz: self._doc_call("set_point_size", float(v)))
        size_menu.addSeparator()
        size_menu.addAction("Autre taille…", self._custom_size)
        self.size_btn.setMenu(size_menu)
        tb.addWidget(self.size_btn)
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
        for label, op in (
            ("Ligne au-dessus", "row_above"),
            ("Ligne en dessous", "row_below"),
            ("Colonne à gauche", "col_left"),
            ("Colonne à droite", "col_right"),
            ("Supprimer la ligne", "del_row"),
            ("Supprimer la colonne", "del_col"),
        ):
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
        self._tray_menu = menu  # référence conservée : sans parent, Qt détruirait le menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.toggle() if r == QSystemTrayIcon.ActivationReason.Trigger else None)
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
            self.tray.showMessage(
                APP_NAME, msg + "\nChangez-le dans Paramètres.", QSystemTrayIcon.MessageIcon.Warning, 6000
            )
        if self.isVisible() and not self._hiding:
            self.setGeometry(self._target_geometry())
        self._update_status()

    def apply_theme(self) -> None:
        app = QApplication.instance()
        app.setPalette(qpalette(self.settings["theme"]))
        app.setStyleSheet(stylesheet(self.settings["theme"]))
        pal = palette(self.settings["theme"])
        accent = pal["accent"]
        self.new_tab_btn.setIcon(icon("plus", accent, 16, stroke=2.2))
        for i in range(self.tabs.count()):
            btn = self.tabs.tabBar().tabButton(i, QTabBar.ButtonPosition.RightSide)
            if isinstance(btn, QToolButton) and btn.objectName() == "TabClose":
                btn.setIcon(icon("close", pal["muted"], 14, stroke=2))
        for obj, name in self._icon_actions:
            if name == "color":
                obj.setIcon(icon(name, pal["icon"], underline_color=accent))
            elif name == "ai":
                obj.setIcon(icon(name, accent))  # l'action IA ressort en couleur d'accent
            else:
                obj.setIcon(icon(name, pal["icon"]))
        for h in getattr(self, "handles", {}).values():
            h.update()

    def _on_system_theme(self) -> None:
        if self.settings["theme"] == "system":
            self.apply_theme()

    def set_theme(self, key: str) -> None:
        self.settings["theme"] = key
        self.settings.save()
        self.apply_theme()

    def _position_format_bar(self) -> None:
        """Superpose la barre de mise en forme juste sous la barre d'onglets."""
        bar = self.tabs.tabBar()
        h = self.format_bar.sizeHint().height() if self.settings["show_toolbar"] else 0
        self.format_bar.setVisible(h > 0)
        self.format_bar.setGeometry(0, bar.geometry().bottom() + 1, self.tabs.width(), h)
        self.format_bar.raise_()
        self.new_tab_btn.setFixedSize(self.new_tab_btn.sizeHint())
        plus_w = self.new_tab_btn.sizeHint().width() + 8
        sheet = (
            f"QTabWidget::pane {{ margin-top: {h}px; border: none; }}"
            f"#MainTabs::tab:last {{ min-width: {plus_w}px; max-width: {plus_w}px; }}"
        )
        if self.tabs.styleSheet() != sheet:  # évite une boucle repolissage -> redimensionnement
            self.tabs.setStyleSheet(sheet)

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        if hasattr(self, "format_bar"):
            self._position_format_bar()

    def eventFilter(self, obj, ev):  # noqa: N802
        """Suit la taille réelle de la zone des onglets : sous Windows, elle est fixée par la mise en
        page après la fenêtre (au show), et l'animation Quake ne fait ensuite que déplacer la fenêtre."""
        if ev.type() in (QEvent.Type.Resize, QEvent.Type.Show) and obj in (self.tabs, self.tabs.tabBar()):
            if not self._format_bar_pending:
                self._format_bar_pending = True
                QTimer.singleShot(0, self._reposition_format_bar_now)
        return super().eventFilter(obj, ev)

    def _reposition_format_bar_now(self) -> None:
        self._format_bar_pending = False
        self._position_format_bar()

    def _font(self) -> QFont:
        font = QFont(self.settings["font_family"])
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(max(5, int(self.settings["font_size"]) + int(self.settings["zoom"])))
        return font

    def _style_doc(self, doc: Document) -> None:
        doc.apply_font(self._font())
        doc.setLineWrapMode(
            QTextEdit.LineWrapMode.WidgetWidth if self.settings["word_wrap"] else QTextEdit.LineWrapMode.NoWrap
        )

    def open_settings(self, tab: int = 0) -> None:
        self.hotkey.unregister()  # sinon la capture déclencherait le raccourci
        dlg = SettingsDialog(self.settings, self.shortcut_table(), self)
        dlg.tabs.setCurrentIndex(tab)
        if dlg.exec():
            vals = dlg.values()
            if vals["start_with_windows"] != self.settings["start_with_windows"]:
                winapi.set_start_with_windows(vals["start_with_windows"])
            self.settings.update(vals)
            self.settings["shortcuts"] = vals["shortcuts"]
            self.settings.save()
            self.act_toolbar.setChecked(self.settings["show_toolbar"])
        self.apply_settings()
        self.update_usage()

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

    # --- Dialogues au premier plan ------------------------------------------

    # ================================================================
    # Onglets
    # ================================================================

    # --- Menu contextuel et renommage des onglets ---------------------------

    # ================================================================
    # Mise en forme
    # ================================================================

    # ================================================================
    # Correction orthographique et grammaticale
    # ================================================================

    # --- Correction automatique par IA ------------------------------------

    # ================================================================
    # Fichiers
    # ================================================================

    # ================================================================
    # Édition
    # ================================================================

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

    # ================================================================
    # Divers
    # ================================================================
    def open_data_dir(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(app_dir())))

    def about(self) -> None:
        QMessageBox.about(
            self,
            f"À propos de {APP_NAME}",
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
