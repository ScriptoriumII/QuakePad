"""Boîte de dialogue des paramètres et capture du raccourci global."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFontComboBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSlider, QSpinBox, QVBoxLayout,
)

from .settings import DEFAULTS, SCANCODE_UNDER_ESC

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
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) and not mods:
            self.setText("")
            return
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


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paramètres de QuakePad")
        self.setMinimumWidth(460)
        s = settings

        self.hotkey = HotkeyEdit(s["hotkey"])
        reset = QPushButton("Défaut")
        reset.clicked.connect(self._reset_hotkey)
        hk_row = QHBoxLayout()
        hk_row.addWidget(self.hotkey, 1)
        hk_row.addWidget(reset)

        self.height = QSpinBox(minimum=15, maximum=100, suffix=" %", value=int(s["height_pct"]))
        self.width = QSpinBox(minimum=30, maximum=100, suffix=" %", value=int(s["width_pct"]))
        self.opacity = QSlider(Qt.Orientation.Horizontal, minimum=40, maximum=100, value=int(s["opacity"]))
        self.opacity_lbl = QLabel(f"{s['opacity']} %")
        self.opacity.valueChanged.connect(lambda v: self.opacity_lbl.setText(f"{v} %"))
        op_row = QHBoxLayout()
        op_row.addWidget(self.opacity, 1)
        op_row.addWidget(self.opacity_lbl)
        self.anim = QSpinBox(minimum=0, maximum=1000, singleStep=10, suffix=" ms", value=int(s["anim_ms"]))
        self.autohide = QCheckBox("Masquer quand la fenêtre perd le focus")
        self.autohide.setChecked(bool(s["hide_on_focus_loss"]))

        self.font = QFontComboBox()
        self.font.setFontFilters(QFontComboBox.FontFilter.MonospacedFonts)
        self.font.setCurrentFont(QFont(s["font_family"]))
        self.font_size = QSpinBox(minimum=6, maximum=48, value=int(s["font_size"]), suffix=" pt")
        f_row = QHBoxLayout()
        f_row.addWidget(self.font, 1)
        f_row.addWidget(self.font_size)

        self.theme = QComboBox()
        self.theme.addItem("Sombre", "dark")
        self.theme.addItem("Clair", "light")
        self.theme.setCurrentIndex(max(0, self.theme.findData(s["theme"])))
        self.startup = QCheckBox("Lancer QuakePad au démarrage de Windows")
        self.startup.setChecked(bool(s["start_with_windows"]))

        form = QFormLayout()
        form.addRow("Raccourci global", hk_row)
        form.addRow("", QLabel("<small>Cliquez dans le champ puis appuyez sur la combinaison.</small>"))
        form.addRow("Hauteur", self.height)
        form.addRow("Largeur", self.width)
        form.addRow("Opacité", op_row)
        form.addRow("Animation", self.anim)
        form.addRow("", self.autohide)
        form.addRow("Police", f_row)
        form.addRow("Thème", self.theme)
        form.addRow("", self.startup)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def _reset_hotkey(self) -> None:
        self.hotkey.spec = dict(DEFAULTS["hotkey"], scancode=SCANCODE_UNDER_ESC)
        self.hotkey.setText(self.hotkey.spec["label"])

    def values(self) -> dict:
        return {
            "hotkey": self.hotkey.spec,
            "height_pct": self.height.value(),
            "width_pct": self.width.value(),
            "opacity": self.opacity.value(),
            "anim_ms": self.anim.value(),
            "hide_on_focus_loss": self.autohide.isChecked(),
            "font_family": self.font.currentFont().family(),
            "font_size": self.font_size.value(),
            "theme": self.theme.currentData(),
            "start_with_windows": self.startup.isChecked(),
        }
