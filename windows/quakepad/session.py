"""Session : onglets restaurés au démarrage (y compris non enregistrés)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import winapi
from .log import log

SESSION_VERSION = 3


def write_session(path: Path, data: dict) -> None:
    """Écrit la session ; chiffrée avec DPAPI sous Windows (le contenu des notes n'est jamais en clair)."""
    payload = json.dumps(data, ensure_ascii=False)
    blob = winapi.protect(payload) if winapi.IS_WINDOWS else ""
    if blob.startswith(winapi.DPAPI_PREFIX):
        doc = {"version": SESSION_VERSION, "format": "dpapi", "data": blob}
    else:
        if winapi.IS_WINDOWS:
            log.warning("Chiffrement DPAPI indisponible : session enregistrée en clair")
        doc = {"version": SESSION_VERSION, "format": "plain", "session": data}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def read_session(path: Path) -> dict | None:
    """Lit la session (formats 2 en clair et 3 chiffré). Renvoie None si absente ou illisible."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        log.exception("Session illisible : %s", path)
        return None
    if doc.get("format") == "dpapi":
        raw = winapi.unprotect(doc.get("data", ""))
        if not raw:
            # Autre compte Windows ou profil restauré ailleurs : on conserve le fichier sans l'écraser.
            backup = path.with_name(f"session.illisible-{time.strftime('%Y%m%d-%H%M%S')}.json")
            path.replace(backup)
            log.error("Session chiffrée impossible à déchiffrer (autre compte Windows ?), copie : %s", backup)
            return None
        return json.loads(raw)
    if doc.get("format") == "plain":
        return doc.get("session")
    if "tabs" in doc:  # ancien format 2, en clair : chiffré dès maintenant
        log.info("Migration de la session en clair vers le format chiffré")
        try:
            write_session(path, doc)
        except OSError:
            log.exception("Migration de la session impossible")
        return doc
    return None


class SessionMixin:
    """Méthodes de QuakeWindow liées à : session : onglets restaurés au démarrage (y compris non enregistrés)."""

    def _schedule_session(self) -> None:
        self._session_timer.start()

    def save_session(self) -> None:
        tabs = []
        for d in self.docs():
            if d.is_empty_untitled():
                continue
            entry = {
                "path": d.path,
                "untitled": d.untitled_name,
                "title": d.custom_title,
                "encoding": d.encoding,
                "eol": d.eol,
                "modified": d.is_modified(),
                "rich": d.rich,
                "cursor": d.textCursor().position(),
            }
            if d.is_modified() or not d.path:
                entry["html" if d.rich else "content"] = d.toHtml() if d.rich else d.toPlainText()
            tabs.append(entry)
        cur = self.current()
        data = {"current": self.docs().index(cur) if cur in self.docs() else 0, "tabs": tabs}
        try:
            write_session(self._session_path, data)
        except OSError:
            log.exception("Enregistrement de la session impossible")

    def restore_session(self) -> None:
        data = read_session(self._session_path)
        if not data:
            return
        for t in data.get("tabs", []):
            doc = self.new_tab(focus=False)
            doc.untitled_name = t.get("untitled") or doc.untitled_name
            doc.custom_title = t.get("title") or ""
            path = t.get("path")
            try:
                if "html" in t:
                    doc.setHtml(t["html"])
                    doc.rich = True
                elif "content" in t and t["content"] is not None:
                    doc.setPlainText(t["content"])
                elif path and Path(path).is_file():
                    doc.load(path)
                else:
                    self.tabs.removeTab(self.tabs.indexOf(doc))
                    doc.deleteLater()
                    continue
                if "html" in t or t.get("content") is not None:
                    doc.path = path
                    doc.encoding = t.get("encoding", "utf-8")
                    doc.eol = t.get("eol", "\r\n")
                    doc.document().setModified(bool(t.get("modified")))
            except OSError:
                log.warning("Onglet de session non restauré : %s", path)
                continue
            c = doc.textCursor()
            c.setPosition(min(int(t.get("cursor", 0)), doc.document().characterCount() - 1))
            doc.setTextCursor(c)
            self._refresh_tab(doc)
        docs = self.docs()
        cur = int(data.get("current", 0))
        if 0 <= cur < len(docs):
            self.tabs.setCurrentWidget(docs[cur])
