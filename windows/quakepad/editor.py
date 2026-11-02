"""Onglet d'édition (document) et barre de recherche / remplacement."""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QFontMetricsF, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLineEdit, QPlainTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from .textio import read_text, write_text



class Document(QPlainTextEdit):
    """Un onglet = un document texte."""

    filesDropped = Signal(list)

    def __init__(self, untitled_name: str = "Sans titre", parent=None):
        super().__init__(parent)
        self.path: str | None = None
        self.encoding = "utf-8"
        self.eol = "\r\n"
        self.untitled_name = untitled_name
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setAcceptDrops(True)

    # --- Identité -------------------------------------------------------
    def title(self) -> str:
        return Path(self.path).name if self.path else self.untitled_name

    def is_modified(self) -> bool:
        return self.document().isModified()

    def is_empty_untitled(self) -> bool:
        return self.path is None and not self.toPlainText()

    # --- Fichiers -------------------------------------------------------
    def load(self, path: str) -> None:
        text, enc, eol = read_text(path)
        self.setPlainText(text)
        self.path, self.encoding, self.eol = str(Path(path).resolve()), enc, eol
        self.document().setModified(False)

    def save(self, path: str | None = None) -> None:
        target = path or self.path
        if not target:
            raise ValueError("Aucun chemin de fichier")
        write_text(target, self.toPlainText(), self.encoding, self.eol)
        self.path = str(Path(target).resolve())
        self.document().setModified(False)

    # --- Apparence ------------------------------------------------------
    def apply_font(self, font) -> None:
        self.setFont(font)
        self.setTabStopDistance(QFontMetricsF(font).horizontalAdvance(" ") * 4)

    def cursor_info(self) -> tuple[int, int]:
        c = self.textCursor()
        return c.blockNumber() + 1, c.positionInBlock() + 1

    def go_to_line(self, line: int) -> None:
        block = self.document().findBlockByNumber(max(0, line - 1))
        cursor = QTextCursor(block)
        self.setTextCursor(cursor)
        self.centerCursor()

    # --- Glisser-déposer de fichiers -----------------------------------
    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            if files:
                self.filesDropped.emit(files)
            e.acceptProposedAction()
        else:
            super().dropEvent(e)


class FindBar(QWidget):
    """Barre Rechercher / Remplacer intégrée (pas de boîte de dialogue qui volerait le focus)."""

    closed = Signal()

    def __init__(self, editor_getter, parent=None):
        super().__init__(parent)
        self.setObjectName("FindBar")
        self._editor = editor_getter

        self.find_edit = QLineEdit(placeholderText="Rechercher")
        self.replace_edit = QLineEdit(placeholderText="Remplacer par")
        self.case_box = QCheckBox("Aa")
        self.case_box.setToolTip("Respecter la casse")
        self.word_box = QCheckBox("Mot")
        self.word_box.setToolTip("Mot entier")
        self.regex_box = QCheckBox(".*")
        self.regex_box.setToolTip("Expression régulière (\\1 utilisable dans le remplacement)")

        def btn(text, tip, slot):
            b = QToolButton(text=text, toolTip=tip)
            b.clicked.connect(slot)
            return b

        row1 = QHBoxLayout()
        row1.setContentsMargins(10, 6, 10, 2)
        row1.addWidget(self.find_edit, 1)
        for w in (self.case_box, self.word_box, self.regex_box):
            row1.addWidget(w)
        row1.addWidget(btn("↑", "Précédent (Maj+F3)", lambda: self.find(backward=True)))
        row1.addWidget(btn("↓", "Suivant (F3)", lambda: self.find()))
        row1.addWidget(btn("✕", "Fermer (Échap)", self.close_bar))

        self.replace_row = QWidget()
        row2 = QHBoxLayout(self.replace_row)
        row2.setContentsMargins(10, 2, 10, 6)
        row2.addWidget(self.replace_edit, 1)
        row2.addWidget(btn("Remplacer", "Remplacer l'occurrence", self.replace_one))
        row2.addWidget(btn("Tout remplacer", "Remplacer toutes les occurrences", self.replace_all))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(row1)
        lay.addWidget(self.replace_row)

        self.find_edit.returnPressed.connect(self.find)
        self.replace_edit.returnPressed.connect(self.replace_one)
        self.find_edit.textChanged.connect(lambda _: self._mark(True))

    # --- Affichage -------------------------------------------------------
    def open_bar(self, replace: bool) -> None:
        ed = self._editor()
        if ed is not None:
            sel = ed.textCursor().selectedText()
            if sel and " " not in sel:
                self.find_edit.setText(sel)
        self.replace_row.setVisible(replace)
        self.show()
        self.find_edit.setFocus()
        self.find_edit.selectAll()

    def close_bar(self) -> None:
        self.hide()
        self.closed.emit()

    def keyPressEvent(self, e):  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self.close_bar()
            return
        super().keyPressEvent(e)

    def _mark(self, found: bool) -> None:
        self.find_edit.setProperty("notFound", not found)
        self.find_edit.style().unpolish(self.find_edit)
        self.find_edit.style().polish(self.find_edit)

    # --- Moteur ------------------------------------------------------------
    def _pattern(self) -> str | None:
        text = self.find_edit.text()
        if not text:
            return None
        pat = text if self.regex_box.isChecked() else re.escape(text)
        if self.word_box.isChecked():
            pat = rf"\b(?:{pat})\b"
        return pat

    def _qregex(self, pat: str) -> QRegularExpression:
        opts = QRegularExpression.PatternOption.NoPatternOption
        if not self.case_box.isChecked():
            opts = QRegularExpression.PatternOption.CaseInsensitiveOption
        return QRegularExpression(pat, opts)

    def _pyregex(self, pat: str):
        try:
            return re.compile(pat, 0 if self.case_box.isChecked() else re.IGNORECASE)
        except re.error:
            return None

    def _replacement(self, matched: str, pat: str) -> str:
        repl = self.replace_edit.text()
        if self.regex_box.isChecked():
            rx = self._pyregex(pat)
            if rx is not None:
                try:
                    return rx.sub(repl, matched, count=1)
                except re.error:
                    pass
        return repl

    def find(self, backward: bool = False) -> bool:
        ed = self._editor()
        pat = self._pattern()
        if ed is None or not pat:
            return False
        rx = self._qregex(pat)
        if not rx.isValid():
            self._mark(False)
            return False
        flags = QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0)
        found = ed.find(rx, flags)
        if not found:  # boucle en début / fin de document
            cursor = ed.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start)
            ed.setTextCursor(cursor)
            found = ed.find(rx, flags)
        self._mark(found)
        return found

    def replace_one(self) -> None:
        ed = self._editor()
        pat = self._pattern()
        if ed is None or not pat:
            return
        cursor = ed.textCursor()
        rx = self._qregex(pat)
        if cursor.hasSelection():
            m = rx.match(cursor.selectedText())
            if m.hasMatch() and m.capturedLength() == len(cursor.selectedText()):
                cursor.insertText(self._replacement(cursor.selectedText(), pat))
        self.find()

    def replace_all(self) -> int:
        ed = self._editor()
        pat = self._pattern()
        if ed is None or not pat:
            return 0
        rx = self._qregex(pat)
        if not rx.isValid():
            self._mark(False)
            return 0
        doc = ed.document()
        count = 0
        edit = QTextCursor(doc)
        edit.beginEditBlock()  # un seul Ctrl+Z annule tout
        cursor = doc.find(rx, 0)
        while not cursor.isNull():
            if not cursor.hasSelection():  # motif vide (ex. ^) : on avance
                if cursor.atEnd():
                    break
                cursor = doc.find(rx, cursor.position() + 1)
                continue
            cursor.insertText(self._replacement(cursor.selectedText(), pat))
            count += 1
            cursor = doc.find(rx, cursor.position())
        edit.endEditBlock()
        self._mark(count > 0)
        return count
