"""Correction automatique par IA (Claude via l'API Anthropic, ou API compatible OpenAI : Ollama, LM Studio…).

Le texte est envoyé paragraphe par paragraphe ; la réponse corrigée est réappliquée caractère par
caractère (diff), ce qui préserve la mise en forme, les images et les tableaux.
"""
from __future__ import annotations

import difflib
import json
import re
import threading
import urllib.error
import urllib.request

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QTextCursor

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-5-5"
DEFAULT_OPENAI_BASE = "http://localhost:11434/v1"  # Ollama
DEFAULT_OPENAI_MODEL = "mistral-nemo"
OBJ = "￼"  # caractère d'une image dans le document Qt
BATCH_CHARS = 12000
BATCH_PARAS = 80

SYSTEM_PROMPT = """Tu es un correcteur professionnel, expert de la langue française (et des autres langues
si le paragraphe n'est pas en français). Tu reçois un tableau JSON de paragraphes à corriger.

CORRIGE toutes les fautes, y compris celles qu'un correcteur automatique classique rate :
- orthographe et fautes de frappe (lettres manquantes, inversées ou en trop) ;
- grammaire, conjugaison, accords (genre, nombre, participes passés), homophones
  (a/à, et/est, ou/où, ces/ses, se/ce, on/ont, -er/-é/-ez…) ;
- ordre des mots manifestement erroné, mots doublés, petit mot manquant
  (ex. pronom ou négation « ne ») quand la phrase est incorrecte sans lui ;
- ponctuation, majuscules et typographie (en français : espace avant « ; : ! ? », apostrophes).

NE CHANGE PAS ce qui est déjà correct : pas de reformulation de style, pas de synonymes,
pas de phrases réorganisées si elles sont déjà correctes, ni le sens, ni le ton, ni le niveau de langue.
Ne traduis rien. Conserve à l'identique : noms propres, termes techniques, commandes, code, chemins,
URL, adresses IP, noms de serveurs, nombres, émojis et le caractère \ufffc.
N'ajoute ni ne supprime de paragraphe ; un paragraphe sans faute est renvoyé tel quel.

Exemples :
["je suis ma suis trompper sur lorthografe."] -> ["Je me suis trompé sur l'orthographe."]
["Il ma dit qu'il viendrais demain si il a le temps"] -> ["Il m'a dit qu'il viendrait demain s'il a le temps."]
["Redémarrer le service sshd sur srv-web01 apres la maj."] -> ["Redémarrer le service sshd sur srv-web01 après la maj."]

Réponds UNIQUEMENT avec un tableau JSON de chaînes, de même longueur et dans le même ordre."""


class AIError(Exception):
    pass


def _post_json(url: str, payload: dict, headers: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"content-type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        if exc.code in (401, 403):
            raise AIError("Clé API refusée (401/403). Vérifiez-la dans Paramètres → Correction.") from exc
        if exc.code == 429:
            raise AIError("Limite de requêtes atteinte (429). Réessayez dans un instant.") from exc
        if exc.code == 404:
            raise AIError(f"Modèle ou adresse introuvable (404). {detail}") from exc
        raise AIError(f"Erreur HTTP {exc.code} : {detail}") from exc
    except urllib.error.URLError as exc:
        raise AIError(f"Serveur injoignable : {exc.reason}") from exc


def _call(cfg: dict, user_text: str) -> str:
    provider = cfg.get("ai_provider", "anthropic")
    if provider == "anthropic":
        key = cfg.get("anthropic_key", "")
        if not key:
            raise AIError("Aucune clé API Anthropic configurée (Paramètres → Correction).")
        data = _post_json(ANTHROPIC_URL, {
            "model": cfg.get("anthropic_model") or DEFAULT_ANTHROPIC_MODEL,
            "max_tokens": 16000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_text}],
        }, {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION})
        if data.get("stop_reason") == "max_tokens":
            raise AIError("Réponse tronquée : sélectionnez une partie plus courte du texte.")
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    # API compatible OpenAI (Ollama, LM Studio, Mistral, OpenAI…)
    base = (cfg.get("openai_base") or DEFAULT_OPENAI_BASE).rstrip("/")
    headers = {}
    if cfg.get("openai_key"):
        headers["authorization"] = f"Bearer {cfg['openai_key']}"
    data = _post_json(f"{base}/chat/completions", {
        "model": cfg.get("openai_model") or DEFAULT_OPENAI_MODEL,
        "temperature": 0,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": user_text}],
    }, headers, timeout=300)
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError("Réponse inattendue du serveur IA.") from exc


def _parse_array(text: str, expected: int) -> list[str]:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()  # modèles « raisonnants » locaux
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        raise AIError("L'IA n'a pas renvoyé de tableau JSON.")
    try:
        arr = json.loads(text[start:end + 1])
    except ValueError as exc:
        raise AIError("Réponse JSON de l'IA illisible.") from exc
    if not isinstance(arr, list) or len(arr) != expected or not all(isinstance(x, str) for x in arr):
        raise AIError("L'IA a renvoyé un nombre de paragraphes différent ; correction annulée.")
    return arr


def correct_paragraphs(paragraphs: list[str], cfg: dict) -> list[str]:
    out: list[str] = []
    batch: list[str] = []
    size = 0

    def flush():
        nonlocal batch, size
        if batch:
            reply = _call(cfg, json.dumps(batch, ensure_ascii=False))
            out.extend(_parse_array(reply, len(batch)))
            batch, size = [], 0

    for p in paragraphs:
        if batch and (size + len(p) > BATCH_CHARS or len(batch) >= BATCH_PARAS):
            flush()
        batch.append(p)
        size += len(p)
    flush()
    return out


def test_connection(cfg: dict) -> str:
    result = correct_paragraphs(["Je suis aller a la plage hier, il faisait tres beaux."], cfg)
    return result[0]


# ---------------------------------------------------------------------------
# Application des corrections dans le document Qt
# ---------------------------------------------------------------------------
def collect_blocks(doc_widget, selection_only: bool) -> list[tuple[int, str]]:
    """(numéro de bloc, texte) des paragraphes à corriger (dans la sélection si demandé)."""
    document = doc_widget.document()
    cursor = doc_widget.textCursor()
    if selection_only and cursor.hasSelection():
        first = document.findBlock(cursor.selectionStart()).blockNumber()
        last = document.findBlock(cursor.selectionEnd()).blockNumber()
    else:
        first, last = 0, document.blockCount() - 1
    blocks = []
    block = document.findBlockByNumber(first)
    while block.isValid() and block.blockNumber() <= last:
        text = block.text()
        if text.replace(OBJ, "").strip():
            blocks.append((block.blockNumber(), text))
        block = block.next()
    return blocks


def _acceptable(old: str, new: str) -> bool:
    """Garde-fou : refuse un paragraphe réécrit au lieu d'être corrigé."""
    if old == new:
        return False
    if old.count(OBJ) != new.count(OBJ):
        return False
    ratio = difflib.SequenceMatcher(None, old, new, autojunk=False).ratio()
    return ratio >= 0.6 or len(old) < 25


def apply_corrections(doc_widget, blocks: list[tuple[int, str]], corrected: list[str]) -> tuple[int, int, list]:
    """Applique les différences ; renvoie (paragraphes modifiés, modifications, plages corrigées)."""
    document = doc_widget.document()
    changed_paras = edits = 0
    touched = []  # (bloc, [(début, fin) dans le nouveau texte])
    master = QTextCursor(document)
    master.beginEditBlock()  # un seul Ctrl+Z pour toute la correction
    for (number, old), new in sorted(zip(blocks, corrected), key=lambda x: -x[0][0]):
        block = document.findBlockByNumber(number)
        if not block.isValid() or block.text() != old or not _acceptable(old, new):
            continue
        ops = difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes()
        ranges = []
        for tag, i1, i2, j1, j2 in reversed(ops):
            if tag == "equal" or OBJ in old[i1:i2]:
                continue
            c = QTextCursor(document)
            c.setPosition(block.position() + i1)
            if i2 > i1:
                c.setPosition(block.position() + i2, QTextCursor.MoveMode.KeepAnchor)
            c.insertText(new[j1:j2])  # garde la mise en forme du caractère voisin
            edits += 1
            if j2 > j1:
                ranges.append((j1, j2))
        if ranges:
            changed_paras += 1
            touched.append((block, ranges))
    master.endEditBlock()
    spans = [(b.position() + a, b.position() + z) for b, rs in touched if b.isValid() for a, z in rs]
    return changed_paras, edits, spans


class AICorrector(QObject):
    finished = Signal(object, object, list)  # document, blocs, textes corrigés
    failed = Signal(object, str)

    def correct(self, doc, blocks: list[tuple[int, str]], cfg: dict) -> None:
        def run():
            try:
                self.finished.emit(doc, blocks, correct_paragraphs([t for _, t in blocks], cfg))
            except AIError as exc:
                self.failed.emit(doc, str(exc))
            except Exception as exc:  # noqa: BLE001 — remonté à l'utilisateur
                self.failed.emit(doc, f"{type(exc).__name__} : {exc}")

        threading.Thread(target=run, daemon=True).start()
