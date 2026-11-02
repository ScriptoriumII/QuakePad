"""Fichiers : ouvrir, enregistrer, exporter en PDF, imprimer, encodage et fins de ligne."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import (
    QPageLayout,
    QPageSize,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QMessageBox,
)

from .editor import IMAGE_EXTS, Document, format_for_path
from .settings import APP_NAME

OPEN_FILTER = (
    "Textes et notes (*.txt *.md *.html *.htm *.log *.ini *.cfg *.conf *.json *.yaml *.yml "
    "*.ps1 *.py *.sh *.csv *.xml);;Tous les fichiers (*)"
)

SAVE_FILTERS = {
    "txt": "Texte brut (*.txt)",
    "html": "Document enrichi avec images (*.html)",
    "md": "Markdown (*.md)",
}

IMAGE_FILTER = "Images (" + " ".join(f"*{e}" for e in sorted(IMAGE_EXTS)) + ")"


class FilesMixin:
    """Méthodes de QuakeWindow liées à : fichiers : ouvrir, enregistrer, exporter en PDF, imprimer, encodage et fins de ligne."""

    def open_dialog(self) -> None:
        cur = self.current()
        start = str(Path(cur.path).parent) if cur and cur.path else str(Path.home() / "Documents")
        with self.native_dialog():
            files, _ = QFileDialog.getOpenFileNames(self, "Ouvrir", start, OPEN_FILTER)
        self.open_files(files)

    def open_files(self, files: list[str]) -> None:
        for f in files:
            p = str(Path(f).resolve())
            if Path(p).suffix.lower() in IMAGE_EXTS:
                doc = self.current() or self.new_tab()
                doc.insert_image_file(p)
                continue
            existing = next((d for d in self.docs() if d.path and Path(d.path) == Path(p)), None)
            if existing:
                self.tabs.setCurrentWidget(existing)
                continue
            if not Path(p).is_file():
                continue
            cur = self.current()
            doc = cur if cur and cur.is_empty_untitled() and not cur.is_modified() else self.new_tab()
            try:
                doc.load(p)
            except OSError as exc:
                QMessageBox.warning(self, APP_NAME, f"Impossible d'ouvrir {p} :\n{exc}")
                continue
            self.tabs.setCurrentWidget(doc)
            self._refresh_tab(doc)
        self._schedule_session()

    def _ask_save_path(self, doc: Document) -> str | None:
        fmt = doc.fmt
        base = Path(doc.path).stem if doc.path else doc.title()
        folder = Path(doc.path).parent if doc.path else Path.home() / "Documents"
        suggested = str(folder / f"{base}.{'html' if fmt == 'html' else fmt}")
        filters = ";;".join(list(SAVE_FILTERS.values()) + ["Tous les fichiers (*)"])
        with self.native_dialog():
            path, chosen = QFileDialog.getSaveFileName(
                self, "Enregistrer sous", suggested, filters, SAVE_FILTERS.get(fmt, "")
            )
        if not path:
            return None
        if not Path(path).suffix:
            ext = next((k for k, v in SAVE_FILTERS.items() if v == chosen), "txt")
            path += f".{ext}"
        return path

    def _save(self, doc: Document, save_as: bool = False) -> bool:
        path = doc.path
        if save_as or not path:
            path = self._ask_save_path(doc)
            if not path:
                return False
        if doc.rich and format_for_path(path) == "txt":
            box = QMessageBox(
                QMessageBox.Icon.Question,
                APP_NAME,
                "Ce document contient de la mise en forme, des tableaux ou des images, "
                "qui seront perdus en texte brut (.txt).",
                parent=self,
            )
            as_html = box.addButton("Enregistrer en .html", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Texte brut quand même", QMessageBox.ButtonRole.DestructiveRole)
            cancel = box.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is cancel:
                return False
            if box.clickedButton() is as_html:
                path = str(Path(path).with_suffix(".html"))
        try:
            doc.save(path)
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"Échec de l'enregistrement :\n{exc}")
            return False
        self._refresh_tab(doc)
        self._info(f"Enregistré : {Path(path).name}")
        self._schedule_session()
        return True

    def save_current(self) -> None:
        if self.current():
            self._save(self.current())

    def save_current_as(self) -> None:
        if self.current():
            self._save(self.current(), save_as=True)

    def save_all(self) -> None:
        for d in self.docs():
            if d.is_modified() and d.path:
                self._save(d)

    def export_pdf(self, path: str | None = None) -> bool:
        doc = self.current()
        if not doc:
            return False
        if path is None:
            base = Path(doc.path).stem if doc.path else doc.title()
            folder = Path(doc.path).parent if doc.path else Path.home() / "Documents"
            with self.native_dialog():
                path, _ = QFileDialog.getSaveFileName(
                    self, "Exporter en PDF", str(folder / f"{base}.pdf"), "PDF (*.pdf)"
                )
            if not path:
                return False
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
        from PySide6.QtPrintSupport import QPrinter

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        printer.setPageLayout(
            QPageLayout(
                QPageSize(QPageSize.PageSizeId.A4),
                QPageLayout.Orientation.Portrait,
                QMarginsF(15, 15, 15, 15),
                QPageLayout.Unit.Millimeter,
            )
        )
        printer.setDocName(doc.title())
        clone = doc.document().clone()
        clone.setDefaultFont(doc.document().defaultFont())
        clone.print_(printer)
        self._info(f"PDF exporté : {Path(path).name}")
        return True

    def _set_encoding(self, enc: str) -> None:
        if self.current():
            self.current().encoding = enc
            self.current().document().setModified(True)
            self._update_status()

    def _set_eol(self, eol: str) -> None:
        if self.current():
            self.current().eol = eol
            self.current().document().setModified(True)
            self._update_status()

    def print_current(self) -> None:
        doc = self.current()
        if not doc:
            return
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        printer = QPrinter()
        dlg = QPrintDialog(printer, self)
        with self.native_dialog():
            accepted = dlg.exec()
        if accepted:
            doc.document().print_(printer)
