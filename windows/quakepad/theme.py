"""Thèmes Système / Clair / Sombre : palette et feuille de style Qt (design « navigateur moderne »)."""

PALETTES = {
    "dark": {
        "bg": "#16181d",       # zone de texte, onglet actif, barre d'outils
        "surface": "#1d2027",  # bandeau des onglets, barre d'état
        "raised": "#2a2e37",   # survol
        "border": "#2f343e",
        "fg": "#e4e8ee", "muted": "#8d95a3", "icon": "#c9cfd9",
        "accent": "#f2a93b", "accent_fg": "#1a1306",
        "selection": "#2d4370", "danger": "#ef6b62",
    },
    "light": {
        "bg": "#ffffff",
        "surface": "#f3f1ed",
        "raised": "#e8e5df",
        "border": "#dedad2",
        "fg": "#1e2228", "muted": "#68707d", "icon": "#3a404a",
        "accent": "#c47400", "accent_fg": "#ffffff",
        "selection": "#cfe0ff", "danger": "#c4372f",
    },
}

THEMES = {"system": "Système", "dark": "Sombre", "light": "Clair"}


def resolve(name: str) -> str:
    """« system » suit le mode clair/sombre de Windows."""
    if name in ("dark", "light"):
        return name
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication

    scheme = QGuiApplication.styleHints().colorScheme()
    return "light" if scheme == Qt.ColorScheme.Light else "dark"


def palette(name: str) -> dict:
    return PALETTES.get(resolve(name), PALETTES["dark"])


def rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


def qpalette(name: str):
    """Palette Qt cohérente avec le thème (menus, dialogues, champs non couverts par la feuille de style)."""
    from PySide6.QtGui import QColor, QPalette

    p = palette(name)
    pal = QPalette()
    R = QPalette.ColorRole
    for role, key in ((R.Window, "surface"), (R.WindowText, "fg"), (R.Base, "bg"), (R.AlternateBase, "surface"),
                      (R.Text, "fg"), (R.Button, "raised"), (R.ButtonText, "fg"), (R.ToolTipBase, "surface"),
                      (R.ToolTipText, "fg"), (R.Highlight, "selection"), (R.HighlightedText, "fg"),
                      (R.PlaceholderText, "muted"), (R.Link, "accent"), (R.Light, "raised"), (R.Mid, "border"),
                      (R.Dark, "border"), (R.Midlight, "raised"), (R.Shadow, "bg")):
        pal.setColor(role, QColor(p[key]))
    for role in (R.WindowText, R.Text, R.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(p["muted"]))
    return pal


def stylesheet(name: str, assets: str = "") -> str:  # noqa: ARG001 (assets conservé pour compatibilité)
    p = palette(name)
    accent_soft = rgba(p["accent"], 0.16)
    accent_line = rgba(p["accent"], 0.55)
    return f"""
QWidget {{ color: {p['fg']}; }}
#QuakeRoot {{ background: {p['surface']}; }}

/* ---------- Zone de texte ---------- */
QTextEdit {{
    background: {p['bg']}; color: {p['fg']}; border: none;
    selection-background-color: {p['selection']}; selection-color: {p['fg']};
}}

/* ---------- Onglets (style navigateur) ---------- */
QTabWidget::pane {{ border: none; background: {p['bg']}; }}
QTabBar {{ background: {p['surface']}; qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent; color: {p['muted']};
    padding: 8px 6px 8px 14px; margin: 6px 0 0 4px;
    border: none; border-top-left-radius: 9px; border-top-right-radius: 9px;
    min-width: 96px; max-width: 220px; font-size: 10pt;
}}
QTabBar::tab:hover:!selected {{ background: {p['raised']}; color: {p['fg']}; }}
QTabBar::tab:selected {{ background: {p['bg']}; color: {p['fg']}; font-weight: 600; }}
#MainTabs::tab:last {{ background: transparent; padding: 4px 4px; margin: 6px 0 0 6px; min-width: 0; }}
#TabClose {{ border: none; background: transparent; border-radius: 6px; padding: 3px; margin-left: 6px; }}
#TabClose:hover {{ background: {p['raised']}; }}
#NewTabBtn {{
    color: {p['accent']}; font-weight: 600; font-size: 10pt;
    padding: 4px 12px 4px 8px; border-radius: 8px;
    border: 1px solid {accent_line}; background: {accent_soft};
}}
#NewTabBtn:hover {{ background: {p['accent']}; color: {p['accent_fg']}; border-color: {p['accent']}; }}

/* ---------- Boutons plats ---------- */
QToolButton {{
    background: transparent; border: none; border-radius: 7px; padding: 5px; color: {p['icon']};
}}
QToolButton:hover {{ background: {p['raised']}; }}
QToolButton:pressed {{ background: {p['border']}; }}
QToolButton:checked {{ background: {accent_soft}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton::menu-button {{ border: none; width: 14px; border-radius: 6px; }}
QToolButton::menu-button:hover {{ background: {p['raised']}; }}
#TopBar {{ background: {p['surface']}; }}
#ChromeBtn {{ padding: 6px; }}
#ChromeBtn:checked {{ background: {accent_soft}; }}

/* ---------- Barre de mise en forme ---------- */
#FormatBar {{
    background: {p['bg']}; border: none; border-bottom: 1px solid {p['border']};
    padding: 5px 10px; spacing: 3px;
}}
#FormatBar QToolButton {{ padding: 6px; min-width: 22px; min-height: 22px; }}
#FormatBar::separator {{ width: 1px; background: {p['border']}; margin: 7px 7px; }}
#SizeBtn {{
    font-weight: 600; font-size: 10pt; padding: 5px 10px; min-width: 38px;
    border: 1px solid {p['border']}; border-radius: 7px;
}}
#SizeBtn:hover {{ border-color: {p['accent']}; background: transparent; }}

/* ---------- Barre d'état ---------- */
#StatusBar {{ background: {p['surface']}; border-top: 1px solid {p['border']}; }}
#StatusBar QLabel {{ color: {p['muted']}; font-size: 9pt; padding: 0 8px; }}
#StatusBar QLabel#InfoLabel {{ color: {p['accent']}; }}

/* ---------- Rechercher / remplacer ---------- */
#FindBar {{ background: {p['surface']}; border-top: 1px solid {p['border']}; }}

/* ---------- Champs, boutons, menus ---------- */
QLineEdit, QSpinBox, QComboBox, QFontComboBox, QKeySequenceEdit {{
    background: {p['bg']}; border: 1px solid {p['border']}; border-radius: 7px; padding: 5px 8px;
    selection-background-color: {p['selection']};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {p['accent']}; }}
QLineEdit[notFound="true"] {{ border-color: {p['danger']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QPushButton {{
    background: {p['raised']}; border: 1px solid {p['border']}; border-radius: 7px; padding: 6px 14px;
}}
QPushButton:hover {{ border-color: {p['accent']}; }}
QPushButton:default {{ background: {p['accent']}; color: {p['accent_fg']}; border-color: {p['accent']}; font-weight: 600; }}
QMenu {{ background: {p['surface']}; color: {p['fg']}; border: 1px solid {p['border']}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ background: transparent; color: {p['fg']}; padding: 7px 30px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p['raised']}; color: {p['fg']}; }}
QMenu::item:disabled {{ color: {p['muted']}; }}
QMenu::icon {{ padding-left: 8px; }}
QMenu::separator {{ height: 1px; background: {p['border']}; margin: 5px 8px; }}
QToolTip {{ background: {p['surface']}; color: {p['fg']}; border: 1px solid {p['border']}; border-radius: 6px; padding: 5px 8px; }}
QDialog {{ background: {p['surface']}; }}
QGroupBox {{ border: 1px solid {p['border']}; border-radius: 9px; margin-top: 14px; padding: 12px 8px 8px 8px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QTabWidget#SettingsTabs::pane {{ border: 1px solid {p['border']}; border-radius: 9px; top: -1px; background: {p['bg']}; }}
QHeaderView::section {{ background: {p['surface']}; color: {p['fg']}; border: none; padding: 5px; }}
QTableWidget {{ background: {p['bg']}; gridline-color: {p['border']}; border: none; }}
QCheckBox {{ spacing: 8px; }}
QSlider::groove:horizontal {{ height: 4px; background: {p['border']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {p['accent']}; width: 16px; margin: -6px 0; border-radius: 8px; }}

/* ---------- Barres de défilement fines ---------- */
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p['raised']}; border-radius: 4px; min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: {p['muted']}; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p['raised']}; border-radius: 4px; min-width: 36px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
"""
