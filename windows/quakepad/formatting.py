"""Mise en forme et édition : barre d'outils, tailles, couleurs, tableaux, images."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtGui import (
    QFont,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QInputDialog,
    QMessageBox,
)

from .dialogs import TableDialog
from .editor import Document
from .files import IMAGE_FILTER
from .settings import APP_NAME


class FormattingMixin:
    """Méthodes de QuakeWindow liées à : mise en forme et édition : barre d'outils, tailles, couleurs, tableaux, images."""

    def _sync_format_bar(self, doc: Document) -> None:
        if doc is not self.current():
            return
        f = doc.currentCharFormat()
        self.act_bold.setChecked(f.fontWeight() > QFont.Weight.Normal)
        self.act_italic.setChecked(f.fontItalic())
        self.act_underline.setChecked(f.fontUnderline())
        self.act_strike.setChecked(f.fontStrikeOut())
        size = doc.current_point_size()
        self.size_btn.setText(f"{size:g} ▾")

    def _custom_size(self) -> None:
        doc = self.current()
        if not doc:
            return
        size, ok = QInputDialog.getDouble(self, "Taille du texte", "Taille (pt) :", doc.current_point_size(), 4, 144, 1)
        if ok:
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
            files, _ = QFileDialog.getOpenFileNames(
                self, "Insérer une image", str(Path.home() / "Pictures"), IMAGE_FILTER
            )
        for f in files:
            if not doc.insert_image_file(f):
                QMessageBox.warning(self, APP_NAME, f"Image illisible :\n{f}")
        doc.setFocus()

    def go_to_line(self) -> None:
        doc = self.current()
        if not doc:
            return
        total = doc.document().blockCount()
        line, ok = QInputDialog.getInt(self, "Atteindre", f"Ligne (1 – {total}) :", doc.cursor_info()[0], 1, total)
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
