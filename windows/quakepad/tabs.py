"""Onglets : création, fermeture, renommage, menu contextuel, bouton « Nouvel onglet »."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtWidgets import (
    QApplication,
    QLineEdit,
    QMenu,
    QMessageBox,
    QTabBar,
    QToolButton,
)

from . import winapi
from .editor import Document
from .icons import icon
from .settings import APP_NAME
from .theme import palette


class TabsMixin:
    """Méthodes de QuakeWindow liées à : onglets : création, fermeture, renommage, menu contextuel, bouton « Nouvel onglet »."""

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
        close = QToolButton(toolTip="Fermer l'onglet (Ctrl+W)")
        close.setObjectName("TabClose")
        close.setIcon(icon("close", palette(self.settings["theme"])["muted"], 14, stroke=2))
        close.setIconSize(QSize(14, 14))
        close.setAutoRaise(True)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.clicked.connect(lambda _=False, d=doc: self.close_tab(self.tabs.indexOf(d)))
        self.tabs.tabBar().setTabButton(idx, QTabBar.ButtonPosition.RightSide, close)
        if focus:
            self.tabs.setCurrentIndex(idx)
            doc.setFocus()
        self._guard_plus = prev
        self._refresh_tab(doc)
        return doc

    def _tab_context_menu(self, pos) -> None:
        bar = self.tabs.tabBar()
        index = bar.tabAt(pos)
        doc = self.tabs.widget(index)
        if not isinstance(doc, Document):
            return
        menu = QMenu(self)
        menu.addAction("Renommer l'onglet…", lambda: self.rename_tab(index))
        if doc.custom_title:
            menu.addAction("Rétablir le nom d'origine", lambda: self._set_tab_title(doc, ""))
        menu.addSeparator()
        menu.addAction("Nouvel onglet", self.new_tab)
        menu.addAction("Dupliquer l'onglet", lambda: self.duplicate_tab(doc))
        menu.addSeparator()
        if doc.path:
            menu.addAction("Copier le chemin du fichier", lambda: QApplication.clipboard().setText(doc.path))
            menu.addAction("Ouvrir le dossier", lambda: self._reveal(doc.path))
            menu.addSeparator()
        menu.addAction("Fermer l'onglet", lambda: self.close_tab(self.tabs.indexOf(doc)))
        others = [d for d in self.docs() if d is not doc]
        a = menu.addAction("Fermer les autres onglets", lambda: self._close_many(others))
        a.setEnabled(bool(others))
        right = self.docs()[self.docs().index(doc) + 1 :]
        a = menu.addAction("Fermer les onglets à droite", lambda: self._close_many(right))
        a.setEnabled(bool(right))
        menu.exec(bar.mapToGlobal(pos))
        menu.deleteLater()

    def rename_tab(self, index: int) -> None:
        """Renommage directement dans l'onglet (Entrée = valider, Échap = annuler, vide = nom d'origine)."""
        doc = self.tabs.widget(index)
        if not isinstance(doc, Document):
            return
        self.tabs.setCurrentIndex(index)
        bar = self.tabs.tabBar()
        rect = bar.tabRect(index).adjusted(8, 6, -30, -4)
        edit = QLineEdit(doc.title(), bar)
        edit.setObjectName("TabRename")
        edit.setGeometry(rect)
        edit.selectAll()
        edit.show()
        edit.setFocus()
        self._rename_edit = edit
        done = {"v": False}

        def finish(commit: bool) -> None:
            if done["v"]:
                return
            done["v"] = True
            if commit:
                text = edit.text().strip()
                default = Path(doc.path).name if doc.path else doc.untitled_name
                self._set_tab_title(doc, "" if text in ("", default) else text)
            edit.deleteLater()
            self._rename_edit = None
            doc.setFocus()

        class _Keys(QObject):
            def eventFilter(self_, obj, ev):  # noqa: N802
                if ev.type() == QEvent.Type.ShortcutOverride and ev.key() == Qt.Key.Key_Escape:
                    ev.accept()  # Échap annule le renommage au lieu de masquer la fenêtre
                    return True
                if ev.type() == QEvent.Type.KeyPress and ev.key() == Qt.Key.Key_Escape:
                    finish(False)
                    return True
                if ev.type() == QEvent.Type.FocusOut:
                    finish(True)
                return False

        keys = _Keys(edit)
        edit.installEventFilter(keys)
        edit.returnPressed.connect(lambda: finish(True))

    def _set_tab_title(self, doc: Document, title: str) -> None:
        doc.custom_title = title
        self._refresh_tab(doc)
        self._schedule_session()

    def duplicate_tab(self, doc: Document) -> None:
        copy = self.new_tab()
        if doc.rich:
            copy.setHtml(doc.toHtml())
            copy.rich = True
        else:
            copy.setPlainText(doc.toPlainText())
        copy.custom_title = f"{doc.title()} (copie)"
        copy.document().setModified(True)
        self._refresh_tab(copy)

    def _close_many(self, docs: list) -> None:
        for d in list(docs):
            i = self.tabs.indexOf(d)
            if i >= 0:
                self.close_tab(i)

    @staticmethod
    def _reveal(path: str) -> None:
        import subprocess

        if winapi.IS_WINDOWS:
            subprocess.Popen(["explorer", "/select,", str(Path(path))])
        else:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

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
        tip = doc.path or doc.untitled_name
        self.tabs.setTabToolTip(i, f"{tip}\nClic droit : renommer, dupliquer, fermer…")
        if doc is self.current():
            self._update_status()

    def close_tab(self, index: int) -> None:
        doc = self.tabs.widget(index)
        if not isinstance(doc, Document):
            return
        if doc.is_modified() and not doc.document().isEmpty():
            self.tabs.setCurrentIndex(index)
            r = QMessageBox.question(
                self,
                APP_NAME,
                f"Enregistrer les modifications de « {doc.title()} » ?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
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
