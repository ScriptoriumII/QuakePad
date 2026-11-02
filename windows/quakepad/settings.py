"""Paramètres persistants de QuakePad (stockés dans %APPDATA%\\QuakePad)."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

APP_NAME = "QuakePad"
APP_VERSION = "1.2.1"
SECRET_KEYS = ("anthropic_key", "openai_key")

# Scan code 0x29 = touche située sous Échap (« ² » en AZERTY, « ` » en QWERTY),
# la même que celle utilisée par le mode Quake de Windows Terminal.
SCANCODE_UNDER_ESC = 0x29

EDGES = {"top": "Haut", "bottom": "Bas", "left": "Gauche", "right": "Droite"}

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
    # Bord d'ancrage et taille mémorisée pour chaque bord (en % de l'écran) :
    # depth = épaisseur (hauteur en haut/bas, largeur à gauche/droite), span = étendue.
    "edge": "top",
    "sizes": {
        "top": {"depth": 45, "span": 100},
        "bottom": {"depth": 45, "span": 100},
        "left": {"depth": 35, "span": 100},
        "right": {"depth": 35, "span": 100},
    },
    "opacity": 97,
    "anim_ms": 170,
    "hide_on_focus_loss": True,
    "font_family": "Cascadia Mono",
    "font_size": 11,
    "zoom": 0,
    "word_wrap": True,
    "show_statusbar": True,
    "show_toolbar": True,
    "theme": "system",  # system | dark | light
    "shortcuts": {},  # identifiant d'action -> séquence personnalisée
    "spell_server": "https://api.languagetool.org/v2/check",
    "spell_language": "fr",
    "ai_provider": "anthropic",  # anthropic | openai
    "anthropic_key": "",  # chiffrée avec DPAPI (compte Windows) dans le fichier
    "anthropic_model": "claude-haiku-5-5",
    "openai_base": "http://localhost:11434/v1",
    "openai_key": "",
    "openai_model": "mistral-nemo",
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
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict):
            # Migration depuis la 1.0 (height_pct / width_pct, thème sans « système »)
            if "sizes" not in data and "height_pct" in data:
                s["sizes"]["top"] = {"depth": data.get("height_pct", 45), "span": data.get("width_pct", 100)}
            for key, value in data.items():
                if key in ("hotkey", "shortcuts") and isinstance(value, dict):
                    s[key].update(value)
                elif key == "sizes" and isinstance(value, dict):
                    for edge, size in value.items():
                        if edge in s["sizes"] and isinstance(size, dict):
                            s["sizes"][edge].update(size)
                elif key in DEFAULTS:
                    s[key] = value
        from .winapi import unprotect
        for k in SECRET_KEYS:
            s[k] = unprotect(s.get(k, ""))
        if s["edge"] not in EDGES:
            s["edge"] = "top"
        return s

    def size(self, edge: str | None = None) -> dict:
        return self["sizes"][edge or self["edge"]]

    def save(self) -> None:
        from .winapi import protect

        data = dict(self)
        for k in SECRET_KEYS:  # clés API jamais écrites en clair sous Windows
            data[k] = protect(data.get(k, ""))
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)
