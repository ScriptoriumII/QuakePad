"""Position, taille, animation Quake et premier plan de la fenêtre."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer
from PySide6.QtGui import (
    QCursor,
    QGuiApplication,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
)

from . import winapi

OPPOSITE = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}


class QuakeMixin:
    """Méthodes de QuakeWindow liées à : position, taille, animation Quake et premier plan de la fenêtre."""

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

    def set_edge(self, edge: str) -> None:
        self.settings["edge"] = edge
        self.settings.save()
        self.apply_edge_layout()
        if self.isVisible():
            self.setGeometry(self._target_geometry())

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
        if (
            state != Qt.ApplicationState.ApplicationActive
            and self.isVisible()
            and self.settings["hide_on_focus_loss"]
            and not self.pinned
            and self._resize_start is None
            and QApplication.activeModalWidget() is None
        ):
            self.hide_animated()

    def _escape(self) -> None:
        if self.find_bar.isVisible():
            self.find_bar.close_bar()
        else:
            self.hide_animated()
