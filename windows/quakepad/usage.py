"""Suivi de la consommation des IA (requêtes et jetons du jour, par fournisseur).

- Gemini n'expose pas le quota restant par API : QuakePad compte ses propres requêtes ; le pourcentage
  est calculé à partir du quota quotidien saisi dans les Paramètres (visible dans Google AI Studio).
  Le quota quotidien de Gemini se réinitialise à minuit, heure du Pacifique.
- Groq (et les API de style OpenAI qui le font) renvoient x-ratelimit-limit-requests /
  x-ratelimit-remaining-requests : la valeur du serveur est alors prioritaire.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone

from .settings import app_dir

_LOCK = threading.Lock()


def _path():
    return app_dir() / "usage.json"


def _pacific_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/Los_Angeles"))
    except Exception:  # noqa: BLE001 — base de fuseaux absente (Windows sans tzdata)
        now = datetime.now(timezone.utc)
        # Approximation : heure d'été américaine du 2e dimanche de mars au 1er dimanche de novembre
        dst = 3 < now.month < 11 or (now.month == 3 and now.day >= 8) or (now.month == 11 and now.day < 7)
        return now + timedelta(hours=-7 if dst else -8)


def day_key(provider: str) -> str:
    """Journée de facturation du fournisseur (Pacifique pour Gemini, heure locale sinon)."""
    now = _pacific_now() if provider == "gemini" else datetime.now()
    return now.strftime("%Y-%m-%d")


def reset_in(provider: str) -> str:
    now = _pacific_now() if provider == "gemini" else datetime.now()
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    secs = int((nxt - now).total_seconds())
    return f"{secs // 3600} h {secs % 3600 // 60:02d}"


def _load() -> dict:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    tmp = _path().with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, _path())


def _entry(data: dict, provider: str) -> dict:
    e = data.get(provider) or {}
    if e.get("day") != day_key(provider):  # nouvelle journée : remise à zéro
        e = {"day": day_key(provider), "requests": 0, "tokens": 0}
    data[provider] = e
    return e


def record(provider: str, model: str, tokens: int, headers: dict | None) -> None:
    """Appelé après chaque requête IA réussie (depuis n'importe quel thread)."""
    with _LOCK:
        data = _load()
        e = _entry(data, provider)
        e["requests"] = e.get("requests", 0) + 1
        e["tokens"] = e.get("tokens", 0) + max(0, int(tokens or 0))
        e["model"] = model
        e.pop("exhausted", None)
        h = {k.lower(): v for k, v in (headers or {}).items()}
        try:
            if "x-ratelimit-limit-requests" in h and "x-ratelimit-remaining-requests" in h:
                e["server"] = {
                    "limit": int(float(h["x-ratelimit-limit-requests"])),
                    "remaining": int(float(h["x-ratelimit-remaining-requests"])),
                    "reset": h.get("x-ratelimit-reset-requests", ""),
                }
        except ValueError:
            pass
        _save(data)


def mark_exhausted(provider: str) -> None:
    """Erreur 429 (quota épuisé) : l'indicateur passe à 100 % jusqu'à la remise à zéro."""
    with _LOCK:
        data = _load()
        _entry(data, provider)["exhausted"] = True
        _save(data)


def status(provider: str, daily_quota: int = 0) -> dict:
    """État du jour : requests, tokens, pct_used (None si inconnu), source, reset."""
    with _LOCK:
        data = _load()
        e = dict(data.get(provider) or {})
    if e.get("day") != day_key(provider):
        e = {"requests": 0, "tokens": 0}
    out = {
        "requests": e.get("requests", 0),
        "tokens": e.get("tokens", 0),
        "pct_used": None,
        "source": "",
        "reset": reset_in(provider),
        "limit": 0,
        "exhausted": bool(e.get("exhausted")),
    }
    srv = e.get("server")
    if srv and srv.get("limit"):
        out.update(
            limit=srv["limit"], source="serveur", pct_used=100 * (srv["limit"] - srv["remaining"]) / srv["limit"]
        )
    elif daily_quota:
        out.update(limit=daily_quota, source="QuakePad", pct_used=100 * out["requests"] / daily_quota)
    if out["exhausted"]:
        out["pct_used"] = 100.0
    if out["pct_used"] is not None:
        out["pct_used"] = max(0.0, min(100.0, out["pct_used"]))
    return out


def tokens_label(n: int) -> str:
    return f"{n / 1000:.1f} k".replace(".", ",") if n >= 1000 else str(n)
