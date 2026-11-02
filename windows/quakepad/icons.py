"""Icônes vectorielles dessinées en code (aucun fichier : insensible aux chemins accentués).

Deux familles : tracés SVG « ligne » (24×24) et lettres typographiques (B, I, U, S, A).
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    "list_bullet": '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1.3"/>'
                   '<circle cx="4.5" cy="12" r="1.3"/><circle cx="4.5" cy="18" r="1.3"/>',
    "list_number": '<path d="M10 6h10M10 12h10M10 18h10"/>'
                   '<path d="M4 4.5l1.6-.9V9" stroke-width="1.6"/><path d="M3.6 14c.4-.9 2.6-1 2.6.4 0 1.1-2.6 1.9-2.6 3.3h2.8" stroke-width="1.6"/>',
    "table": '<rect x="3" y="4.5" width="18" height="15" rx="2.5"/><path d="M3 9.5h18M3 14.5h18M9 4.5v15M15 4.5v15"/>',
    "image": '<rect x="3" y="4.5" width="18" height="15" rx="2.5"/><circle cx="8.5" cy="9.5" r="1.7"/>'
             '<path d="M21 15.5l-4.5-4.5L7 19.5"/>',
    "clear": '<path d="M5 6h11M10.5 6l-3 13"/><path d="M14 14l6 6M20 14l-6 6"/>',
    "spell": '<path d="M3 16l4-11 4 11M4.6 12.2h4.8"/><path d="M12.5 15.5l3 3 6-7"/>',
    "ai": '<path d="M11 3.5l1.7 4.6 4.6 1.7-4.6 1.7L11 16.1l-1.7-4.6-4.6-1.7 4.6-1.7z"/>'
          '<path d="M18.5 14.5l.9 2.3 2.3.9-2.3.9-.9 2.3-.9-2.3-2.3-.9 2.3-.9z"/>',
    "next_error": '<path d="M4 12h13M13 7l5 5-5 5"/><path d="M4 19.5h7" stroke-dasharray="1.6 2.2"/>',
    "pdf": '<path d="M14 3H6.5A2.5 2.5 0 0 0 4 5.5v13A2.5 2.5 0 0 0 6.5 21h11a2.5 2.5 0 0 0 2.5-2.5V9z"/>'
           '<path d="M14 3v6h6"/><path d="M8 17v-4h1.5a1.3 1.3 0 0 1 0 2.6H8M13 13v4h.9a2 2 0 0 0 0-4z" stroke-width="1.4"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "close": '<path d="M7 7l10 10M17 7L7 17"/>',
    "pin": '<path d="M9 3.5h6l-.8 6.3 3.3 3.2h-11l3.3-3.2z"/><path d="M12 13v7.5"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "hide": '<path d="M6 15l6-6 6 6"/>',
    "color": '<path d="M6.5 15.5L12 4l5.5 11.5M8.4 11.5h7.2"/>',
}

# Icônes « lettres » : (texte, gras, italique, souligné, barré, échelle)
_LETTERS = {
    "bold": ("B", True, False, False, False, 1.0),
    "italic": ("I", False, True, False, False, 1.0),
    "underline": ("U", False, False, True, False, 0.9),
    "strike": ("S", False, False, False, True, 0.95),
    "size_up": ("A+", True, False, False, False, 0.78),
    "size_down": ("A−", True, False, False, False, 0.78),
}

UI_FONT = "Segoe UI"


def _letter_pixmap(spec, color: str, size: int, scale: int) -> QPixmap:
    text, bold, italic, underline, strike, k = spec
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(scale)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    f = QFont(UI_FONT)
    f.setPixelSize(round(size * 0.82 * k))
    f.setWeight(QFont.Weight.Bold if bold else QFont.Weight.DemiBold)
    f.setItalic(italic)
    f.setStrikeOut(strike)
    p.setFont(f)
    p.setPen(QColor(color))
    rect = QRectF(0, -size * 0.06 if underline else 0, size, size)
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
    if underline:
        pen = QPen(QColor(color), max(1.4, size / 13))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        y = size * 0.86
        p.drawLine(int(size * 0.28), int(y), int(size * 0.72), int(y))
    p.end()
    return pm


def _svg_pixmap(body: str, color: str, size: int, scale: int, stroke: float) -> QPixmap:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    ).replace("<circle", f'<circle fill="{color}" stroke="none"')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(scale)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, size, size))
    p.end()
    return pm


def icon(name: str, color: str, size: int = 20, stroke: float = 1.8, underline_color: str | None = None) -> QIcon:
    ic = QIcon()
    for scale in (1, 2, 3):  # net sur les écrans 100 %, 200 % et 300 %
        if name in _LETTERS:
            pm = _letter_pixmap(_LETTERS[name], color, size, scale)
        else:
            pm = _svg_pixmap(_PATHS[name], color, size, scale, stroke)
            if name == "color" and underline_color:  # barre de couleur sous le « A »
                p = QPainter(pm)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(underline_color))
                p.drawRoundedRect(QRectF(size * 0.2, size * 0.78, size * 0.6, size * 0.13), 1.5, 1.5)
                p.end()
        ic.addPixmap(pm)
    return ic
