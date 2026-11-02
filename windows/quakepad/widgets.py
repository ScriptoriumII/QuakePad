"""Petits composants de la fenêtre : bords redimensionnables, indicateur de consommation IA, dialogues."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QPainter,
)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QWidget,
)

from .theme import palette

if TYPE_CHECKING:  # annotations uniquement (évite l'import circulaire)
    from .window import QuakeWindow


class EdgeHandle(QWidget):
    """Bord redimensionnable. role = "depth" (bord intérieur) ou "span" (bords latéraux)."""

    def __init__(self, window: QuakeWindow, side: str):
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


class DialogWatcher(QObject):
    """Place chaque boîte de dialogue au-dessus de QuakePad (fenêtre « toujours au premier plan »)."""

    def __init__(self, window: QuakeWindow):
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


class UsageIndicator(QWidget):
    """Consommation IA du jour : « ✦ Gemini ▮▮▯ 12 % utilisé · 88 % libre » (clic = Paramètres)."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("UsageIndicator")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(6)
        self.label = QLabel()
        self.bar = QProgressBar()
        self.bar.setObjectName("UsageBar")
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedSize(54, 6)
        self.pct = QLabel()
        self.pct.setMinimumWidth(self.pct.fontMetrics().horizontalAdvance("100 % utilisé · 100 % libre") + 4)
        for w in (self.label, self.bar, self.pct):
            lay.addWidget(w)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
