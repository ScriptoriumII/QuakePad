"""Onglet d'édition : texte enrichi (gras, tailles, tableaux, images) ou texte brut."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QMimeData, Qt, QUrl, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFrameFormat,
    QTextImageFormat,
    QTextLength,
    QTextListFormat,
    QTextTableFormat,
)
from PySide6.QtWidgets import QMenu, QTextEdit

from .textio import read_text, write_text

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".ico"}
RICH_EXTS = {".html", ".htm"}
MD_EXTS = {".md", ".markdown"}
MAX_IMAGE_PX = 1600  # résolution stockée maximale
DISPLAY_IMAGE_PX = 640  # largeur affichée par défaut


@dataclass
class SpellIssue:
    start: int
    length: int
    message: str
    replacements: list[str]
    kind: str  # "spelling" | "grammar"

    @property
    def end(self) -> int:
        return self.start + self.length


def format_for_path(path: str | None) -> str:
    suffix = Path(path).suffix.lower() if path else ""
    if suffix in RICH_EXTS:
        return "html"
    if suffix in MD_EXTS:
        return "md"
    return "txt"


def image_to_data_uri(img: QImage) -> str:
    """Encode une image en data URI (PNG si transparence, sinon JPEG compact)."""
    if img.width() > MAX_IMAGE_PX:
        img = img.scaledToWidth(MAX_IMAGE_PX, Qt.TransformationMode.SmoothTransformation)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    if img.hasAlphaChannel():
        img.save(buf, "PNG")
        mime = "image/png"
    else:
        img.save(buf, "JPEG", 88)
        mime = "image/jpeg"
    return f"data:{mime};base64,{bytes(ba.toBase64()).decode('ascii')}"


class Document(QTextEdit):
    """Un onglet = un document. Les fichiers .txt restent du texte brut à l'enregistrement."""

    filesDropped = Signal(list)
    formatUsed = Signal()

    def __init__(self, untitled_name: str = "Sans titre", parent=None):
        super().__init__(parent)
        self.path: str | None = None
        self.encoding = "utf-8"
        self.eol = "\r\n"
        self.untitled_name = untitled_name
        self.custom_title = ""  # nom choisi par l'utilisateur pour l'onglet (prioritaire)
        self.rich = False  # contient mise en forme / images / tableaux
        self.issues: list[SpellIssue] = []
        self._flash: list[tuple[int, int]] = []
        self.setAcceptRichText(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setAcceptDrops(True)
        self.document().setDocumentMargin(18)
        self.document().contentsChange.connect(self._shift_issues)

    # --- Identité -------------------------------------------------------
    def title(self) -> str:
        if self.custom_title:
            return self.custom_title
        return Path(self.path).name if self.path else self.untitled_name

    @property
    def fmt(self) -> str:
        return format_for_path(self.path) if self.path else ("html" if self.rich else "txt")

    def plain_file(self) -> bool:
        """Fichier texte ouvert depuis le disque (.txt, .ps1…) : collage sans mise en forme."""
        return bool(self.path) and format_for_path(self.path) == "txt"

    def is_modified(self) -> bool:
        return self.document().isModified()

    def is_empty_untitled(self) -> bool:
        return self.path is None and self.document().isEmpty()

    def mark_rich(self) -> None:
        if not self.rich:
            self.rich = True
            self.formatUsed.emit()

    # --- Fichiers -------------------------------------------------------
    def load(self, path: str) -> None:
        fmt = format_for_path(path)
        text, enc, eol = read_text(path)
        if fmt == "html":
            base = QUrl.fromLocalFile(str(Path(path).resolve().parent) + "/")
            self.document().setBaseUrl(base)
            self.setHtml(text)
            self.rich = True
        elif fmt == "md":
            self.document().setBaseUrl(QUrl.fromLocalFile(str(Path(path).resolve().parent) + "/"))
            self.setMarkdown(text)
            self.rich = True
        else:
            self.setPlainText(text)
            self.rich = False
        self.path, self.encoding, self.eol = str(Path(path).resolve()), enc, eol
        self.document().setModified(False)

    def content_for(self, fmt: str) -> str:
        if fmt == "html":
            return self.toHtml()
        if fmt == "md":
            return self.toMarkdown()
        return self.toPlainText().replace("￼", "")  # retire les images

    def save(self, path: str | None = None) -> None:
        target = path or self.path
        if not target:
            raise ValueError("Aucun chemin de fichier")
        fmt = format_for_path(target)
        eol = self.eol if fmt == "txt" else "\n"
        enc = self.encoding if fmt == "txt" else "utf-8"
        write_text(target, self.content_for(fmt), enc, eol)
        self.path = str(Path(target).resolve())
        self.document().setModified(False)

    # --- Apparence ------------------------------------------------------
    def apply_font(self, font: QFont) -> None:
        self.document().setDefaultFont(font)
        self.setFont(font)
        self.setTabStopDistance(QFontMetricsF(font).horizontalAdvance(" ") * 4)

    def cursor_info(self) -> tuple[int, int]:
        c = self.textCursor()
        return c.blockNumber() + 1, c.positionInBlock() + 1

    def go_to_line(self, line: int) -> None:
        block = self.document().findBlockByNumber(max(0, line - 1))
        self.setTextCursor(QTextCursor(block))
        self.ensureCursorVisible()

    # --- Mise en forme ----------------------------------------------------
    def merge_format(self, fmt: QTextCharFormat) -> None:
        c = self.textCursor()
        if not c.hasSelection():
            c.select(QTextCursor.SelectionType.WordUnderCursor)
        c.mergeCharFormat(fmt)
        self.mergeCurrentCharFormat(fmt)
        self.mark_rich()

    def toggle_bold(self) -> None:
        f = QTextCharFormat()
        f.setFontWeight(QFont.Weight.Normal if self.fontWeight() > QFont.Weight.Normal else QFont.Weight.Bold)
        self.merge_format(f)

    def toggle_italic(self) -> None:
        f = QTextCharFormat()
        f.setFontItalic(not self.fontItalic())
        self.merge_format(f)

    def toggle_underline(self) -> None:
        f = QTextCharFormat()
        f.setFontUnderline(not self.fontUnderline())
        self.merge_format(f)

    def toggle_strike(self) -> None:
        f = QTextCharFormat()
        f.setFontStrikeOut(not self.currentCharFormat().fontStrikeOut())
        self.merge_format(f)

    def current_point_size(self) -> float:
        size = self.currentCharFormat().fontPointSize()
        return size if size > 0 else self.document().defaultFont().pointSizeF()

    def set_point_size(self, size: float) -> None:
        f = QTextCharFormat()
        f.setFontPointSize(max(4.0, min(144.0, size)))
        self.merge_format(f)

    def step_size(self, step: int) -> None:
        sizes = [6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48, 60, 72, 96]
        cur = self.current_point_size()
        if step > 0:
            new = next((s for s in sizes if s > cur + 0.1), cur + 12)
        else:
            new = next((s for s in reversed(sizes) if s < cur - 0.1), max(4, cur - 1))
        self.set_point_size(new)

    def set_color(self, color: QColor) -> None:
        f = QTextCharFormat()
        f.setForeground(QBrush(color))
        self.merge_format(f)

    def clear_formatting(self) -> None:
        c = self.textCursor()
        if not c.hasSelection():
            return
        c.setCharFormat(QTextCharFormat())
        c.setBlockFormat(QTextBlockFormat())

    def toggle_list(self, style: QTextListFormat.Style) -> None:
        c = self.textCursor()
        current = c.currentList()
        c.beginEditBlock()
        if current and current.format().style() == style:
            for i in reversed(range(current.count())):
                current.remove(current.item(i))
            bf = c.blockFormat()
            bf.setIndent(0)
            c.setBlockFormat(bf)
        else:
            lf = QTextListFormat()
            lf.setStyle(style)
            c.createList(lf)
        c.endEditBlock()
        self.mark_rich()

    # --- Tableaux ---------------------------------------------------------
    def insert_table(self, rows: int, cols: int) -> None:
        tf = QTextTableFormat()
        tf.setBorder(1)
        tf.setBorderBrush(QBrush(QColor("#8a8f99")))
        tf.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
        tf.setBorderCollapse(True)
        tf.setCellPadding(5)
        tf.setCellSpacing(0)
        tf.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
        self.textCursor().insertTable(rows, cols, tf)
        self.mark_rich()

    def table_op(self, op: str) -> bool:
        c = self.textCursor()
        table = c.currentTable()
        if table is None:
            return False
        cell = table.cellAt(c)
        r, col = cell.row(), cell.column()
        if op == "row_below":
            table.insertRows(r + 1, 1)
        elif op == "row_above":
            table.insertRows(r, 1)
        elif op == "col_right":
            table.insertColumns(col + 1, 1)
        elif op == "col_left":
            table.insertColumns(col, 1)
        elif op == "del_row":
            table.removeRows(r, 1)
        elif op == "del_col":
            table.removeColumns(col, 1)
        return True

    # --- Images -----------------------------------------------------------
    def insert_image(self, img: QImage) -> bool:
        if img.isNull():
            return False
        uri = image_to_data_uri(img)
        stored = QImage.fromData(QByteArray.fromBase64(uri.split(",", 1)[1].encode()))
        self.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(uri), stored)
        fmt = QTextImageFormat()
        fmt.setName(uri)
        w = min(stored.width(), DISPLAY_IMAGE_PX)
        fmt.setWidth(w)
        fmt.setHeight(stored.height() * w / max(1, stored.width()))
        self.textCursor().insertImage(fmt)
        self.mark_rich()
        return True

    def insert_image_file(self, path: str) -> bool:
        return self.insert_image(QImage(path))

    def _image_cursor_at(self, pos) -> QTextCursor | None:
        c = self.cursorForPosition(pos)
        for p in (c.position(), c.position() - 1):
            if p < 0:
                continue
            t = QTextCursor(self.document())
            t.setPosition(p)
            t.setPosition(p + 1, QTextCursor.MoveMode.KeepAnchor)
            if t.charFormat().isImageFormat():
                return t
        return None

    def resize_image(self, cursor: QTextCursor, ratio: float) -> None:
        fmt = cursor.charFormat().toImageFormat()
        img = self.document().resource(QTextDocument.ResourceType.ImageResource, QUrl(fmt.name()))
        if isinstance(img, QImage) and not img.isNull():
            w0, h0 = img.width(), img.height()
        else:
            w0, h0 = fmt.width() or DISPLAY_IMAGE_PX, fmt.height() or DISPLAY_IMAGE_PX
        fmt.setWidth(w0 * ratio)
        fmt.setHeight(h0 * ratio)
        cursor.setCharFormat(fmt)

    # --- Collage / glisser-déposer ---------------------------------------
    def canInsertFromMimeData(self, source: QMimeData) -> bool:  # noqa: N802
        return source.hasImage() or source.hasUrls() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source: QMimeData) -> None:  # noqa: N802
        if source.hasUrls():
            images = [
                u.toLocalFile()
                for u in source.urls()
                if u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() in IMAGE_EXTS
            ]
            others = [
                u.toLocalFile()
                for u in source.urls()
                if u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() not in IMAGE_EXTS
            ]
            for p in images:
                self.insert_image_file(p)
            if others:
                self.filesDropped.emit(others)
            if images or others:
                return
        if source.hasImage():
            img = source.imageData()
            if isinstance(img, QImage) and self.insert_image(img):
                return
        if self.plain_file() or not source.hasHtml():
            if source.hasText():
                self.textCursor().insertText(source.text())
            return
        super().insertFromMimeData(source)
        self.mark_rich()

    def paste_plain(self) -> None:
        from PySide6.QtWidgets import QApplication

        text = QApplication.clipboard().text()
        if text:
            self.textCursor().insertText(text)

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            self.setTextCursor(self.cursorForPosition(e.position().toPoint()))
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            self.insertFromMimeData(e.mimeData())
            e.acceptProposedAction()
        else:
            super().dropEvent(e)

    # --- Correction orthographique ------------------------------------------
    def set_issues(self, issues: list[SpellIssue]) -> None:
        self.issues = issues
        self._paint_issues()

    def flash_ranges(self, spans: list[tuple[int, int]], ms: int = 8000) -> None:
        """Surligne en vert les passages corrigés (jusqu'à la prochaine frappe ou {ms} ms)."""
        from PySide6.QtCore import QTimer

        self._flash = spans
        self._paint_issues()
        QTimer.singleShot(ms, self._clear_flash)

    def _clear_flash(self) -> None:
        if self._flash:
            self._flash = []
            self._paint_issues()

    def _paint_issues(self) -> None:
        sels = []
        n = self.document().characterCount() - 1
        for a, z in self._flash:
            sel = QTextEdit.ExtraSelection()
            c = QTextCursor(self.document())
            c.setPosition(min(a, n))
            c.setPosition(min(z, n), QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = c
            f = QTextCharFormat()
            f.setBackground(QColor(46, 160, 67, 70))
            sel.format = f
            sels.append(sel)
        for it in self.issues:
            sel = QTextEdit.ExtraSelection()
            c = QTextCursor(self.document())
            c.setPosition(min(it.start, self.document().characterCount() - 1))
            c.setPosition(min(it.end, self.document().characterCount() - 1), QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = c
            f = QTextCharFormat()
            f.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
            f.setUnderlineColor(QColor("#e5534b" if it.kind == "spelling" else "#3b8eea"))
            sel.format = f
            sels.append(sel)
        self.setExtraSelections(sels)

    def _shift_issues(self, pos: int, removed: int, added: int) -> None:
        if self._flash and not getattr(self, "_applying_ai", False):
            self._flash = []
            self._paint_issues()
        if not self.issues:
            return
        delta = added - removed
        kept = []
        for it in self.issues:
            if it.end <= pos:
                kept.append(it)
            elif it.start >= pos + removed:
                it.start += delta
                kept.append(it)
        if len(kept) != len(self.issues) or delta:
            self.issues = kept
            self._paint_issues()

    def issue_at(self, position: int) -> SpellIssue | None:
        return next((i for i in self.issues if i.start <= position <= i.end), None)

    def apply_issue(self, issue: SpellIssue, replacement: str) -> None:
        c = QTextCursor(self.document())
        c.setPosition(issue.start)
        c.setPosition(issue.end, QTextCursor.MoveMode.KeepAnchor)
        self.issues.remove(issue)
        c.insertText(replacement)
        self._paint_issues()

    def ignore_issue(self, issue: SpellIssue) -> None:
        if issue in self.issues:
            self.issues.remove(issue)
            self._paint_issues()

    def next_issue(self) -> bool:
        if not self.issues:
            return False
        pos = self.textCursor().selectionEnd()
        it = next(
            (i for i in sorted(self.issues, key=lambda x: x.start) if i.start >= pos),
            min(self.issues, key=lambda x: x.start),
        )
        c = QTextCursor(self.document())
        c.setPosition(it.start)
        c.setPosition(it.end, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(c)
        return True

    # --- Menu contextuel --------------------------------------------------
    def contextMenuEvent(self, e):  # noqa: N802
        menu = self.createStandardContextMenu(e.pos())
        first = menu.actions()[0] if menu.actions() else None
        pos = self.cursorForPosition(e.pos()).position()

        issue = self.issue_at(pos)
        if issue:
            head = menu.addSection(issue.message[:90])
            menu.insertAction(first, head)
            for rep in issue.replacements[:6]:
                a = menu.addAction(f"→ {rep}")
                a.triggered.connect(lambda _=False, r=rep, i=issue: self.apply_issue(i, r))
                menu.insertAction(first, a)
            if not issue.replacements:
                a = menu.addAction("(aucune suggestion)")
                a.setEnabled(False)
                menu.insertAction(first, a)
            ign = menu.addAction("Ignorer")
            ign.triggered.connect(lambda _=False, i=issue: self.ignore_issue(i))
            menu.insertAction(first, ign)
            menu.insertSeparator(first)

        img_cursor = self._image_cursor_at(e.pos())
        if img_cursor:
            sub = QMenu("Taille de l'image", menu)
            for label, ratio in (("25 %", 0.25), ("50 %", 0.5), ("75 %", 0.75), ("100 % (originale)", 1.0)):
                a = sub.addAction(label)
                a.triggered.connect(lambda _=False, r=ratio, c=img_cursor: self.resize_image(c, r))
            menu.insertMenu(first, sub)
            menu.insertSeparator(first)

        if self.textCursor().currentTable() is not None:
            sub = QMenu("Tableau", menu)
            for label, op in (
                ("Insérer une ligne au-dessus", "row_above"),
                ("Insérer une ligne en dessous", "row_below"),
                ("Insérer une colonne à gauche", "col_left"),
                ("Insérer une colonne à droite", "col_right"),
                ("Supprimer la ligne", "del_row"),
                ("Supprimer la colonne", "del_col"),
            ):
                a = sub.addAction(label)
                a.triggered.connect(lambda _=False, o=op: self.table_op(o))
            menu.addSeparator()
            menu.addMenu(sub)
        menu.exec(e.globalPos())
        menu.deleteLater()
