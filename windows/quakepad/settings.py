"""Paramètres persistants de QuakePad (stockés dans %APPDATA%\\QuakePad)."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

APP_NAME = "QuakePad"
APP_VERSION = "1.0.0"

# Scan code 0x29 = touche située sous Échap (« ² » en AZERTY, « ` » en QWERTY),
# la même que celle utilisée par le mode Quake de Windows Terminal.
SCANCODE_UNDER_ESC = 0x29

DEFAULTS: dict = {
    "hotkey": {
        "ctrl": False,
        "alt": True,
        "shift": False,
        "win": False,
        "vk": 0,  # 0 => résolu à partir du scan code au lancement
        "scancode": SCANCODE_UNDER_ESC,
        "label": "Alt+²",
    },
    "height_pct": 45,
    "width_pct": 100,
    "opacity": 97,
    "anim_ms": 170,
    "hide_on_focus_loss": True,
    "font_family": "Cascadia Mono",
    "font_size": 11,
    "zoom": 0,
    "word_wrap": True,
    "show_statusbar": True,
    "theme": "dark",
    "start_with_windows": False,
    "first_run": True,
}


def app_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


class Settings(dict):
    """Dictionnaire de paramètres fusionné avec les valeurs par défaut."""

    path: Path

    @classmethod
    def load(cls) -> "Settings":
        s = cls(copy.deepcopy(DEFAULTS))
        s.path = app_dir() / "settings.json"
        try:
            data = json.loads(s.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key, value in data.items():
                    if key == "hotkey" and isinstance(value, dict):
                        s["hotkey"].update(value)
                    elif key in DEFAULTS:
                        s[key] = value
        except (OSError, ValueError):
            pass
        return s

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)
