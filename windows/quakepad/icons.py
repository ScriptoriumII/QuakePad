"""Icônes vectorielles (SVG en ligne), recolorées selon le thème."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# Tracés 24×24, trait de 2 px (style « ligne »).
_PATHS = {
    "bold": '<path d="M7 5h6a3.5 3.5 0 0 1 0 7H7z"/><path d="M7 12h7a3.5 3.5 0 0 1 0 7H7z"/>',
    "italic": '<path d="M14 5h-4M14 19h-4M14.5 5l-5 14"/><path d="M10 5h6M8 19h6"/>',
    "underline": '<path d="M7 4v7a5 5 0 0 0 10 0V4"/><path d="M5 20h14"/>',
    "strike": '<path d="M5 12h14"/><path d="M16.5 7.5C16 5.8 14.3 5 12 5c-2.8 0-4.5 1.3-4.5 3.2 0 1.6 1.1 2.4 3 2.9"/>'
              '<path d="M8 16.5c.6 1.7 2.2 2.5 4.3 2.5 2.8 0 4.7-1.3 4.7-3.4 0-.8-.3-1.5-.8-2"/>',
    "size_up": '<path d="M3 19l5-13 5 13M5 15h6"/><path d="M18 6v8M14 10h8"/>',
    "size_down": '<path d="M3 19l5-13 5 13M5 15h6"/><path d="M14 10h8"/>',
    "list_bullet": '<path d="M10 6h10M10 12h10M10 18h10"/><circle cx="5" cy="6" r="1.2"/>'
                   '<circle cx="5" cy="12" r="1.2"/><circle cx="5" cy="18" r="1.2"/>',
    "list_number": '<path d="M10 6h10M10 12h10M10 18h10"/><path d="M4 4.5l1.5-1V9M3.5 13.5c.3-1 2.5-1.2 2.5.3 0 1-2.5 2-2.5 3.2H6"/>',
    "table": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18M9 4v16M15 4v16"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9.5" r="1.8"/>'
             '<path d="M21 16l-5-5-9 9"/>',
    "color": '<path d="M6 16l6-12 6 12M8 12h8"/><path d="M4 20h16" stroke-width="3"/>',
    "clear": '<path d="M6 5h12M12 5l-3 14"/><path d="M15 15l5 5M20 15l-5 5"/>',
    "spell": '<path d="M3 15l4-10 4 10M4.5 11.5h5"/><path d="M12 15l3 3 6-7"/>',
    "pdf": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>'
           '<path d="M8 14h1.5a1.5 1.5 0 0 0 0-3H8v6M13 11v6h1a3 3 0 0 0 0-6z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "pin": '<path d="M9 4h6l-1 6 3 3H7l3-3z"/><path d="M12 13v7"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "hide": '<path d="M6 15l6-6 6 6"/>',
    "next_error": '<path d="M5 12h12M13 7l5 5-5 5"/><path d="M3 20h8" stroke-dasharray="1.5 2"/>',
}


def icon(name: str, color: str, size: int = 18) -> QIcon:
    body = _PATHS[name]
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    ).replace('<circle', f'<circle fill="{color}"')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    ic = QIcon()
    for scale in (1, 2):
        pm = QPixmap(size * scale, size * scale)
        pm.fill(Qt.GlobalColor.transparent)
        pm.setDevicePixelRatio(scale)
        p = QPainter(pm)
        renderer.render(p, QRectF(0, 0, size, size))
        p.end()
        ic.addPixmap(pm)
    return ic
