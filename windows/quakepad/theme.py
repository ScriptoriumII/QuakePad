"""Thèmes sombre / clair (feuilles de style Qt)."""

PALETTES = {
    "dark": {
        "bg": "#111318", "surface": "#171a21", "raised": "#1f232c", "border": "#2a2f3a",
        "fg": "#d6dbe4", "muted": "#7d8590", "accent": "#f0a742", "accent_fg": "#14110a",
        "selection": "#2c3d5c", "danger": "#e5534b",
    },
    "light": {
        "bg": "#fbfaf7", "surface": "#f1efe9", "raised": "#e7e4dc", "border": "#d8d3c8",
        "fg": "#23262d", "muted": "#6b6f78", "accent": "#b86e00", "accent_fg": "#ffffff",
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


def stylesheet(name: str, assets: str = "") -> str:
    p = palette(name)
    theme = resolve(name)
    close = f"{assets}/close-{theme}.svg".replace("\\", "/")
    close_hover = f"{assets}/close-{theme}-hover.svg".replace("\\", "/")
    return f"""
#QuakeRoot {{ background: {p['bg']}; }}
QWidget {{ color: {p['fg']}; font-size: 10pt; }}
QTextEdit {{
    background: {p['bg']}; color: {p['fg']}; border: none;
    selection-background-color: {p['selection']}; selection-color: {p['fg']};
    padding: 6px 10px;
}}
QTabWidget::pane {{ border: none; }}
QTabBar {{ background: {p['surface']}; qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent; color: {p['muted']}; padding: 7px 14px; margin: 0;
    border: none; border-bottom: 2px solid transparent; min-width: 60px;
}}
QTabBar::tab:selected {{ color: {p['fg']}; background: {p['bg']}; border-bottom: 2px solid {p['accent']}; }}
QTabBar::tab:hover:!selected {{ color: {p['fg']}; background: {p['raised']}; }}
QTabBar::close-button {{ subcontrol-position: right; image: url({close}); border-radius: 3px; margin: 2px; }}
QTabBar::close-button:hover {{ image: url({close_hover}); background: {p['raised']}; }}
#TopBar, #StatusBar, #FindBar, #FormatBar {{ background: {p['surface']}; }}
#FormatBar {{ border-top: 1px solid {p['border']}; border-bottom: 1px solid {p['border']}; spacing: 2px; padding: 2px 6px; }}
#FormatBar QToolButton {{ padding: 4px; }}
#FormatBar QToolButton:checked {{ background: {p['raised']}; }}
#FormatBar QComboBox {{ padding: 2px 4px; min-width: 52px; }}
#FormatBar::separator {{ width: 1px; background: {p['border']}; margin: 4px 4px; }}
#MainTabs::tab:last {{ min-width: 28px; padding: 7px 10px; color: {p['accent']}; }}
#StatusBar QLabel {{ color: {p['muted']}; font-size: 9pt; padding: 0 6px; }}
#AccentEdge {{ background: {p['accent']}; }}
#DragHandle {{ background: {p['surface']}; }}
#DragHandle:hover {{ background: {p['raised']}; }}
QToolButton {{
    background: transparent; border: none; border-radius: 4px; padding: 4px 8px; color: {p['muted']};
}}
QToolButton:hover {{ background: {p['raised']}; color: {p['fg']}; }}
QToolButton:checked {{ color: {p['accent']}; }}
QToolButton::menu-indicator {{ image: none; }}
QLineEdit, QSpinBox, QComboBox, QFontComboBox {{
    background: {p['bg']}; border: 1px solid {p['border']}; border-radius: 4px; padding: 4px 6px;
    selection-background-color: {p['selection']};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {p['accent']}; }}
QLineEdit[notFound="true"] {{ border-color: {p['danger']}; }}
QPushButton {{
    background: {p['raised']}; border: 1px solid {p['border']}; border-radius: 4px; padding: 5px 12px;
}}
QPushButton:hover {{ border-color: {p['accent']}; }}
QPushButton:default {{ background: {p['accent']}; color: {p['accent_fg']}; border-color: {p['accent']}; }}
QMenu {{ background: {p['surface']}; border: 1px solid {p['border']}; padding: 4px; }}
QMenu::item {{ padding: 5px 24px 5px 12px; border-radius: 3px; }}
QMenu::item:selected {{ background: {p['raised']}; }}
QMenu::separator {{ height: 1px; background: {p['border']}; margin: 4px 6px; }}
QDialog {{ background: {p['surface']}; }}
QCheckBox::indicator {{ width: 14px; height: 14px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {p['raised']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p['border']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {p['raised']}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QSlider::groove:horizontal {{ height: 4px; background: {p['border']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {p['accent']}; width: 14px; margin: -6px 0; border-radius: 7px; }}
"""
