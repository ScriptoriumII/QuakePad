"""Journal d'erreurs : %APPDATA%\\QuakePad\\quakepad.log (rotation 3 × 1 Mo).

- Les exceptions non gérées (y compris dans les slots Qt et les threads) sont journalisées :
  avec pythonw (pas de console), elles seraient sinon invisibles.
- Les secrets (clés API, jetons « Bearer ») sont masqués avant écriture.
"""

from __future__ import annotations

import logging
import re
import sys
import threading
from logging.handlers import RotatingFileHandler

from .settings import APP_VERSION, app_dir

log = logging.getLogger("quakepad")

_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),  # Anthropic
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),  # Google
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)(x-api-key['\"]?\s*[:=]\s*['\"]?)[A-Za-z0-9._\-]{8,}"),
    re.compile(r"gsk_[A-Za-z0-9]{8,}"),  # Groq
]


def redact(text: str) -> str:
    for pat in _SECRET_PATTERNS:
        text = pat.sub(lambda m: (m.group(1) if m.groups() else "") + "«secret masqué»", text)
    return text


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if record.args:
            record.args = tuple(redact(str(a)) for a in record.args)
        return True


_notifier = None  # fonction(message) appelée sur une erreur non gérée (notification à l'utilisateur)


def path():
    return app_dir() / "quakepad.log"


def setup(level: int = logging.INFO) -> None:
    if log.handlers:
        return
    handler = RotatingFileHandler(path(), maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s : %(message)s"))
    handler.addFilter(_RedactFilter())
    log.addHandler(handler)
    log.setLevel(level)
    log.info("QuakePad %s démarré (Python %s, %s)", APP_VERSION, sys.version.split()[0], sys.platform)

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("Exception non gérée", exc_info=(exc_type, exc, tb))
        if _notifier:
            try:
                _notifier(f"Erreur interne : {exc_type.__name__}. Détails dans le journal.")
            except Exception:  # noqa: BLE001
                log.debug("Notification d'erreur impossible", exc_info=True)

    sys.excepthook = hook
    threading.excepthook = lambda a: hook(a.exc_type, a.exc_value, a.exc_traceback)


def set_notifier(func) -> None:
    global _notifier
    _notifier = func
