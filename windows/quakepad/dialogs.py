"""Boîtes de dialogue : paramètres (raccourci global, fenêtre, raccourcis, correction) et tableau."""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFontComboBox, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QKeySequenceEdit, QLabel, QLineEdit, QMessageBox, QPushButton, QSlider,
    QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from .settings import DEFAULTS, EDGES, SCANCODE_UNDER_ESC
from .theme import THEMES

_MODIFIER_KEYS = {
    Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
    Qt.Key.Key_AltGr, Qt.Key.Key_Super_L, Qt.Key.Key_Super_R,
}


class HotkeyEdit(QLineEdit):
    """Champ qui enregistre une combinaison de touches (codes natifs Windows)."""

    changed = Signal(dict)

    def __init__(self, spec: dict, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Appuyez sur la combinaison…")
        self.spec = dict(spec)
        self.setText(self.spec.get("label", ""))

    def keyPressEvent(self, e):  # noqa: N802
        key = e.key()
        if key in _MODIFIER_KEYS:
            return
        mods = e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        win = bool(mods & Qt.KeyboardModifier.MetaModifier)
        if not (ctrl or alt or win) and not (Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24):
            self.setText("Ajoutez Ctrl, Alt ou Win (ou utilisez une touche F1–F24)")
            return
        name = QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText) or "?"
        parts = [p for p, on in (("Ctrl", ctrl), ("Alt", alt), ("Maj", shift), ("Win", win)) if on]
        label = "+".join(parts + [name.upper() if len(name) == 1 else name])
        self.spec = {
            "ctrl": ctrl, "alt": alt, "shift": shift, "win": win,
            "vk": int(e.nativeVirtualKey()), "scancode": int(e.nativeScanCode()), "label": label,
        }
        self.setText(label)
        self.changed.emit(self.spec)


class ShortcutTable(QTableWidget):
    """Liste des actions avec leur raccourci, modifiable."""

    def __init__(self, actions: list[tuple[str, str, str, str]], parent=None):
        # actions : (identifiant, libellé, raccourci par défaut, raccourci actuel)
        super().__init__(len(actions), 3, parent)
        self.setHorizontalHeaderLabels(["Action", "Raccourci", ""])
        self.verticalHeader().hide()
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.setColumnWidth(1, 170)
        self._edits: dict[str, QKeySequenceEdit] = {}
        self._defaults: dict[str, str] = {}
        for row, (aid, label, default, current) in enumerate(actions):
            item = QTableWidgetItem(label)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.setItem(row, 0, item)
            edit = QKeySequenceEdit(QKeySequence(current))
            edit.setMaximumSequenceLength(1)
            edit.setClearButtonEnabled(True)
            self.setCellWidget(row, 1, edit)
            reset = QPushButton("↺")
            reset.setToolTip(f"Par défaut : {default or 'aucun'}")
            reset.setFixedWidth(34)
            reset.setStyleSheet("padding: 2px;")
            reset.clicked.connect(lambda _=False, e=edit, d=default: e.setKeySequence(QKeySequence(d)))
            self.setCellWidget(row, 2, reset)
            self._edits[aid] = edit
            self._defaults[aid] = default

    def overrides(self) -> dict[str, str]:
        out = {}
        for aid, edit in self._edits.items():
            seq = edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
            if seq != self._defaults[aid]:
                out[aid] = seq  # "" = raccourci supprimé volontairement
        return out

    def conflicts(self) -> list[str]:
        seen: dict[str, str] = {}
        dup = []
        for row in range(self.rowCount()):
            seq = self.cellWidget(row, 1).keySequence().toString(QKeySequence.SequenceFormat.NativeText)
            if not seq:
                continue
            label = self.item(row, 0).text()
            if seq in seen:
                dup.append(f"{seq} : « {seen[seq]} » et « {label} »")
            else:
                seen[seq] = label
        return dup


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, actions: list[tuple[str, str, str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paramètres de QuakePad")
        self.setMinimumSize(600, 560)
        s = settings
        self._sizes = copy.deepcopy(s["sizes"])

        tabs = QTabWidget()

        # --- Général ---------------------------------------------------------
        self.hotkey = HotkeyEdit(s["hotkey"])
        reset = QPushButton("Défaut")
        reset.clicked.connect(self._reset_hotkey)
        hk_row = QHBoxLayout()
        hk_row.addWidget(self.hotkey, 1)
        hk_row.addWidget(reset)
        self.theme = QComboBox()
        for key, label in THEMES.items():
            self.theme.addItem(label, key)
        self.theme.setCurrentIndex(max(0, self.theme.findData(s["theme"])))
        self.font = QFontComboBox()
        self.font.setCurrentFont(QFont(s["font_family"]))
        self.font_size = QSpinBox(minimum=6, maximum=48, value=int(s["font_size"]), suffix=" pt")
        f_row = QHBoxLayout()
        f_row.addWidget(self.font, 1)
        f_row.addWidget(self.font_size)
        self.toolbar = QCheckBox("Afficher la barre de mise en forme")
        self.toolbar.setChecked(bool(s["show_toolbar"]))
        self.startup = QCheckBox("Lancer QuakePad au démarrage de Windows")
        self.startup.setChecked(bool(s["start_with_windows"]))
        general = QWidget()
        g = QFormLayout(general)
        g.addRow("Raccourci afficher/masquer", hk_row)
        g.addRow("", QLabel("<small>Cliquez dans le champ puis appuyez sur la combinaison (global, système).</small>"))
        g.addRow("Thème", self.theme)
        g.addRow("Police par défaut", f_row)
        g.addRow("", self.toolbar)
        g.addRow("", self.startup)
        tabs.addTab(general, "Général")

        # --- Fenêtre ---------------------------------------------------------
        self.edge = QComboBox()
        for key, label in EDGES.items():
            self.edge.addItem(label, key)
        self.edge.setCurrentIndex(max(0, self.edge.findData(s["edge"])))
        self.depth = QSpinBox(minimum=10, maximum=100, suffix=" %")
        self.span = QSpinBox(minimum=20, maximum=100, suffix=" %")
        self.depth_lbl, self.span_lbl = QLabel(), QLabel()
        self._edge_cur = s["edge"]
        self._load_size(self._edge_cur)
        self.edge.currentIndexChanged.connect(self._edge_changed)
        self.opacity = QSlider(Qt.Orientation.Horizontal, minimum=40, maximum=100, value=int(s["opacity"]))
        self.opacity_lbl = QLabel(f"{s['opacity']} %")
        self.opacity.valueChanged.connect(lambda v: self.opacity_lbl.setText(f"{v} %"))
        op_row = QHBoxLayout()
        op_row.addWidget(self.opacity, 1)
        op_row.addWidget(self.opacity_lbl)
        self.anim = QSpinBox(minimum=0, maximum=1000, singleStep=10, suffix=" ms", value=int(s["anim_ms"]))
        self.autohide = QCheckBox("Réduire quand je clique sur une autre fenêtre")
        self.autohide.setChecked(bool(s["hide_on_focus_loss"]))
        window = QWidget()
        w = QFormLayout(window)
        w.addRow("Position", self.edge)
        w.addRow(self.depth_lbl, self.depth)
        w.addRow(self.span_lbl, self.span)
        w.addRow("", QLabel("<small>Astuce : tirez directement les bords de la fenêtre ; "
                            "la taille est mémorisée pour chaque position.</small>"))
        w.addRow("Opacité", op_row)
        w.addRow("Animation", self.anim)
        w.addRow("", self.autohide)
        tabs.addTab(window, "Fenêtre")

        # --- Raccourcis -------------------------------------------------------
        self.shortcuts = ShortcutTable(actions)
        sc = QWidget()
        sl = QVBoxLayout(sc)
        hint = QLabel("Cliquez sur un raccourci puis appuyez sur la nouvelle combinaison. "
                      "✕ pour le supprimer, ↺ pour revenir au défaut.")
        hint.setWordWrap(True)
        sl.addWidget(hint)
        sl.addWidget(self.shortcuts)
        tabs.addTab(sc, "Raccourcis")

        # --- Correction ------------------------------------------------------
        spell = QWidget()
        sv = QVBoxLayout(spell)

        ai_box = QGroupBox("Correction automatique par IA (icône ✦ ou Ctrl+F7)")
        af = QFormLayout(ai_box)
        self.ai_provider = QComboBox()
        self.ai_provider.addItem("Claude — API Anthropic", "anthropic")
        self.ai_provider.addItem("IA compatible OpenAI — Ollama, LM Studio, Mistral…", "openai")
        self.ai_provider.setCurrentIndex(max(0, self.ai_provider.findData(s["ai_provider"])))
        af.addRow("Fournisseur", self.ai_provider)

        self.anthropic_key = QLineEdit(s["anthropic_key"])
        self.anthropic_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.anthropic_key.setPlaceholderText("sk-ant-…  (console.anthropic.com → API Keys)")
        self.anthropic_model = QComboBox(editable=True)
        self.anthropic_model.addItems(["claude-haiku-5-5", "claude-sonnet-5-5"])
        self.anthropic_model.setEditText(s["anthropic_model"])
        self.anthropic_rows = [("Clé API", self.anthropic_key), ("Modèle", self.anthropic_model)]

        self.openai_base = QLineEdit(s["openai_base"])
        self.openai_base.setPlaceholderText("http://localhost:11434/v1")
        self.openai_key = QLineEdit(s["openai_key"])
        self.openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_key.setPlaceholderText("Facultative pour Ollama / LM Studio")
        self.openai_model = QLineEdit(s["openai_model"])
        self.openai_rows = [("Adresse de l'API", self.openai_base), ("Clé API", self.openai_key),
                            ("Modèle", self.openai_model)]
        for label, w in self.anthropic_rows + self.openai_rows:
            af.addRow(label, w)
        self._ai_form = af

        test_row = QHBoxLayout()
        self.test_btn = QPushButton("Tester la connexion")
        self.test_btn.clicked.connect(self._test_ai)
        self.test_result = QLabel()
        self.test_result.setWordWrap(True)
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_result, 1)
        af.addRow(test_row)
        self.ai_note = QLabel()
        self.ai_note.setWordWrap(True)
        af.addRow(self.ai_note)
        self.ai_provider.currentIndexChanged.connect(self._ai_provider_changed)
        self._ai_provider_changed()
        sv.addWidget(ai_box)

        lt_box = QGroupBox("Vérification mot par mot — LanguageTool (icône A✓ ou F7)")
        lf = QFormLayout(lt_box)
        self.spell_server = QLineEdit(s["spell_server"])
        self.spell_lang = QComboBox()
        for code, label in (("fr", "Français"), ("auto", "Détection automatique"), ("en-US", "Anglais (US)"),
                            ("en-GB", "Anglais (GB)"), ("de-DE", "Allemand"), ("es", "Espagnol"), ("it", "Italien")):
            self.spell_lang.addItem(label, code)
        self.spell_lang.setCurrentIndex(max(0, self.spell_lang.findData(s["spell_language"])))
        lf.addRow("Langue", self.spell_lang)
        lf.addRow("Serveur", self.spell_server)
        note = QLabel(
            "<small>Envoie le texte au serveur indiqué. Serveur public gratuit mais limité ; pour rester en "
            "interne : Docker <code>erikvl87/languagetool</code> puis <code>http://serveur:8010/v2/check</code>.</small>")
        note.setWordWrap(True)
        lf.addRow(note)
        sv.addWidget(lt_box)
        sv.addStretch(1)
        tabs.addTab(spell, "Correction")
        self.tabs = tabs

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(buttons)

    # --- Position / taille ---------------------------------------------------
    def _load_size(self, edge: str) -> None:
        vertical = edge in ("top", "bottom")
        self.depth_lbl.setText("Hauteur" if vertical else "Largeur")
        self.span_lbl.setText("Largeur" if vertical else "Hauteur")
        self.depth.setValue(round(self._sizes[edge]["depth"]))
        self.span.setValue(round(self._sizes[edge]["span"]))

    def _edge_changed(self) -> None:
        self._sizes[self._edge_cur] = {"depth": self.depth.value(), "span": self.span.value()}
        self._edge_cur = self.edge.currentData()
        self._load_size(self._edge_cur)

    def _reset_hotkey(self) -> None:
        self.hotkey.spec = dict(DEFAULTS["hotkey"], scancode=SCANCODE_UNDER_ESC)
        self.hotkey.setText(self.hotkey.spec["label"])

    def _accept(self) -> None:
        dup = self.shortcuts.conflicts()
        if dup:
            QMessageBox.warning(self, "Raccourcis en double",
                                "Ces raccourcis sont utilisés deux fois :\n\n" + "\n".join(dup))
            return
        self.accept()

    def values(self) -> dict:
        self._sizes[self._edge_cur] = {"depth": self.depth.value(), "span": self.span.value()}
        return {
            "hotkey": self.hotkey.spec,
            "theme": self.theme.currentData(),
            "font_family": self.font.currentFont().family(),
            "font_size": self.font_size.value(),
            "show_toolbar": self.toolbar.isChecked(),
            "start_with_windows": self.startup.isChecked(),
            "edge": self.edge.currentData(),
            "sizes": self._sizes,
            "opacity": self.opacity.value(),
            "anim_ms": self.anim.value(),
            "hide_on_focus_loss": self.autohide.isChecked(),
            "shortcuts": self.shortcuts.overrides(),
            "spell_server": self.spell_server.text().strip() or DEFAULTS["spell_server"],
            "spell_language": self.spell_lang.currentData(),
            **self._ai_values(),
        }

    # --- IA ------------------------------------------------------------------
    def _ai_values(self) -> dict:
        return {
            "ai_provider": self.ai_provider.currentData(),
            "anthropic_key": self.anthropic_key.text().strip(),
            "anthropic_model": self.anthropic_model.currentText().strip() or DEFAULTS["anthropic_model"],
            "openai_base": self.openai_base.text().strip() or DEFAULTS["openai_base"],
            "openai_key": self.openai_key.text().strip(),
            "openai_model": self.openai_model.text().strip() or DEFAULTS["openai_model"],
        }

    def _ai_provider_changed(self) -> None:
        anthropic = self.ai_provider.currentData() == "anthropic"
        for rows, visible in ((self.anthropic_rows, anthropic), (self.openai_rows, not anthropic)):
            for _label, w in rows:
                self._ai_form.setRowVisible(w, visible)
        self.ai_note.setText(
            "<small>Le texte est envoyé à Anthropic. <code>claude-haiku-5-5</code> : rapide et économique. "
            "<code>claude-sonnet-5-5</code> : plus précis sur les phrases très fautives (environ 20× plus cher, "
            "reste de l'ordre du centime par note). Clé chiffrée avec votre compte Windows (DPAPI).</small>"
            if anthropic else
            "<small>Pour une IA 100 % locale : installez Ollama puis <code>ollama pull mistral-nemo</code>. "
            "Rien ne quitte le PC. La qualité dépend du modèle choisi.</small>")
        self.test_result.setText("")

    def _test_ai(self) -> None:
        from PySide6.QtWidgets import QApplication

        from .ai import AIError, test_connection

        self.test_result.setText("Test en cours…")
        self.test_btn.setEnabled(False)
        QApplication.processEvents()
        try:
            out = test_connection(self._ai_values())
            self.test_result.setText(f"✓ OK : « {out} »")
        except AIError as exc:
            self.test_result.setText(f"✗ {exc}")
        except Exception as exc:  # noqa: BLE001
            self.test_result.setText(f"✗ {type(exc).__name__} : {exc}")
        finally:
            self.test_btn.setEnabled(True)


class TableDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Insérer un tableau")
        self.rows = QSpinBox(minimum=1, maximum=100, value=3)
        self.cols = QSpinBox(minimum=1, maximum=20, value=3)
        form = QFormLayout(self)
        form.addRow("Lignes", self.rows)
        form.addRow("Colonnes", self.cols)
        b = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        b.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        b.accepted.connect(self.accept)
        b.rejected.connect(self.reject)
        form.addRow(b)
