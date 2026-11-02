"""Correction orthographique et grammaticale via l'API LanguageTool.

Par défaut : serveur public https://api.languagetool.org (le texte y est envoyé).
Un serveur LanguageTool auto-hébergé peut être configuré dans les Paramètres.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request

from PySide6.QtCore import QObject, Signal

from .editor import SpellIssue

CHUNK = 15000  # caractères par requête (limite du serveur public : 20 Ko)


def _chunks(text: str):
    """Découpe aux fins de ligne en conservant les décalages d'origine."""
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK)
        if end < len(text):
            nl = text.rfind("\n", start, end)
            if nl > start:
                end = nl + 1
        yield start, text[start:end]
        start = end


def check_text(text: str, server: str, language: str) -> list[SpellIssue]:
    issues: list[SpellIssue] = []
    for offset, chunk in _chunks(text):
        if not chunk.strip():
            continue
        # level=picky active les règles supplémentaires (style, typographie, grammaire avancée)
        params = {"text": chunk, "language": language or "auto", "level": "picky"}
        if params["language"] == "auto":
            params["preferredVariants"] = "fr-FR,en-US"
        data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(server, data=data, headers={
            "Accept": "application/json", "User-Agent": "QuakePad",
            "Content-Type": "application/x-www-form-urlencoded",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        # Les positions de LanguageTool et de Qt sont toutes deux en UTF-16 :
        # on ajoute seulement le décalage du morceau, converti en UTF-16.
        chunk_utf16_offset = len(text[:offset].encode("utf-16-le")) // 2
        for m in payload.get("matches", []):
            issue_type = (m.get("rule") or {}).get("issueType", "")
            issues.append(SpellIssue(
                start=chunk_utf16_offset + int(m["offset"]),
                length=int(m["length"]),
                message=m.get("message") or m.get("shortMessage") or "Erreur",
                replacements=[r["value"] for r in m.get("replacements", [])[:8]],
                kind="spelling" if issue_type == "misspelling" else "grammar",
            ))
    return issues


def document_text(document) -> str:
    """Texte du document avec exactement une unité par position Qt (images, tableaux…)."""
    raw = document.toRawText()
    for ch, rep in (("\u2029", "\n"), ("\u2028", "\n"), ("\ufdd0", "\n"), ("\ufdd1", "\n"), ("\ufffc", " ")):
        raw = raw.replace(ch, rep)
    return raw


class SpellChecker(QObject):
    """Lance la vérification dans un thread et renvoie le résultat par signal."""

    finished = Signal(object, list)  # document, issues
    failed = Signal(object, str)

    def check(self, doc, text: str, server: str, language: str) -> None:
        def run():
            try:
                self.finished.emit(doc, check_text(text, server, language))
            except urllib.error.HTTPError as exc:
                msg = "Trop de requêtes, réessayez dans une minute." if exc.code == 429 else f"HTTP {exc.code}"
                self.failed.emit(doc, msg)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                self.failed.emit(doc, str(getattr(exc, "reason", exc)))

        threading.Thread(target=run, daemon=True).start()
