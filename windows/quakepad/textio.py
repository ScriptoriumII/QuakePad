"""Lecture / écriture de fichiers texte avec détection d'encodage et de fins de ligne."""

from __future__ import annotations

import codecs
import os
from pathlib import Path

ENCODINGS = {
    "utf-8": "UTF-8",
    "utf-8-sig": "UTF-8 avec BOM",
    "utf-16": "UTF-16",
    "cp1252": "ANSI (Windows-1252)",
}
EOLS = {"\r\n": "Windows (CRLF)", "\n": "Unix (LF)", "\r": "Mac (CR)"}


def detect_eol(text: str) -> str:
    """Fin de ligne dominante, détectée sur le texte décodé (fonctionne aussi en UTF-16)."""
    if "\r\n" in text:
        return "\r\n"
    if "\n" in text:
        return "\n"
    if "\r" in text:
        return "\r"
    return "\r\n"


def read_text(path: str | Path) -> tuple[str, str, str]:
    """Renvoie (texte normalisé en \\n, encodage, fin de ligne)."""
    raw = Path(path).read_bytes()
    if raw.startswith(codecs.BOM_UTF8):
        enc = "utf-8-sig"
    elif raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        enc = "utf-16"
    else:
        try:
            raw.decode("utf-8")
            enc = "utf-8"
        except UnicodeDecodeError:
            enc = "cp1252"
    text = raw.decode(enc, errors="replace")
    eol = detect_eol(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text, enc, eol


def write_text(path: str | Path, text: str, encoding: str, eol: str) -> None:
    data = text.replace("\n", eol).encode(encoding, errors="replace")
    path = Path(path)
    tmp = path.with_name(path.name + ".qp-tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
