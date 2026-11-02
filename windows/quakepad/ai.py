"""Correction automatique par IA : Claude (Anthropic), Google Gemini, Mistral, Ollama ou toute API compatible OpenAI.

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

# Fournisseurs proposés dans Paramètres → Correction.
#   kind "anthropic" = API Messages d'Anthropic ; "openai" = /chat/completions compatible OpenAI.
#   base None = adresse saisie par l'utilisateur (fournisseur « Autre »).
PROVIDERS = {
    "gemini": {
        "label": "Google Gemini — gratuit", "kind": "openai",
        "base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-3.8-flash", "models": ["gemini-3.8-flash", "gemini-3.5-flash-lite"],
        "key_url": "https://aistudio.google.com/api-keys", "key_hint": "AIza…",
        "quota_url": "https://ai.google.dev/gemini-api/docs/rate-limits",
        "extra": {"reasoning_effort": "low"},  # la correction ne demande pas de réflexion poussée
        "note": "Gratuit, sans carte bancaire. En offre gratuite, Google peut utiliser les textes pour "
                "améliorer ses produits (relecture humaine possible) : réservez-le aux notes non sensibles.",
    },
    "mistral": {
        "label": "Mistral — gratuit (français, UE)", "kind": "openai",
        "base": "https://api.mistral.ai/v1",
        "model": "mistral-small-latest", "models": ["mistral-small-latest", "mistral-medium-latest", "mistral-large-latest"],
        "key_url": "https://console.mistral.ai/api-keys", "key_hint": "clé Mistral",
        "quota_url": "https://console.mistral.ai/limits",
        "note": "Mode gratuit sans carte bancaire, excellente qualité en français. En gratuit, les textes "
                "peuvent servir à améliorer les modèles : vérifiez l'option dans votre console Mistral.",
    },
    "anthropic": {
        "label": "Claude — Anthropic (payant à l'usage)", "kind": "anthropic",
        "model": DEFAULT_ANTHROPIC_MODEL, "models": ["claude-haiku-5-5", "claude-sonnet-5-5"],
        "key_url": "https://platform.claude.com/settings/keys", "key_hint": "sk-ant-…",
        "note": "Clé à créer sur Claude Platform (facturation séparée de l'abonnement Claude). "
                "claude-haiku-5-5 : rapide et économique ; claude-sonnet-5-5 : plus précis.",
    },
    "ollama": {
        "label": "Ollama — IA locale gratuite", "kind": "openai",
        "base": "http://localhost:11434/v1",
        "model": "mistral-nemo", "models": ["mistral-nemo", "mistral-small3.2", "gemma3:12b", "qwen3:8b"],
        "key_url": "https://ollama.com/download", "key_hint": "(aucune clé)",
        "note": "100 % local, rien ne quitte le PC. Installez Ollama puis « ollama pull mistral-nemo ».",
    },
    "openai": {
        "label": "Autre service compatible OpenAI…", "kind": "openai", "base": None,
        "model": DEFAULT_OPENAI_MODEL, "models": [],
        "key_url": "", "key_hint": "clé du service",
        "note": "Groq, OpenRouter, LM Studio, OpenAI… : indiquez l'adresse de l'API (se termine souvent par /v1), "
                "pas celle de la page web du service.",
    },
}


def resolve(cfg: dict) -> dict:
    """Paramètres effectifs (type, adresse, clé, modèle) du fournisseur choisi."""
    pid = cfg.get("ai_provider") or "gemini"
    meta = PROVIDERS.get(pid, PROVIDERS["openai"])
    keys = cfg.get("ai_keys") or {}
    models = cfg.get("ai_models") or {}
    if pid == "anthropic":
        key = cfg.get("anthropic_key", "")
        model = cfg.get("anthropic_model") or meta["model"]
    elif pid == "openai":
        key = cfg.get("openai_key", "")
        model = cfg.get("openai_model") or meta["model"]
    else:
        key = keys.get(pid, "")
        model = models.get(pid) or meta["model"]
    base = meta.get("base") or (cfg.get("openai_base") or DEFAULT_OPENAI_BASE)
    return {"id": pid, "kind": meta["kind"], "base": base.rstrip("/"), "key": key, "model": model, "meta": meta}
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
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


TRANSIENT = (429, 500, 502, 503, 504)  # erreurs temporaires côté service


def _error_message(detail: str) -> str:
    """Extrait le message lisible d'une réponse d'erreur JSON (dict ou liste)."""
    try:
        data = json.loads(detail)
    except ValueError:
        return detail.strip()[:200]
    if isinstance(data, list) and data:
        data = data[0]
    err = data.get("error", data) if isinstance(data, dict) else data
    if isinstance(err, dict):
        return str(err.get("message") or err.get("status") or err)[:300]
    return str(err)[:300]


def _post_json(url: str, payload: dict, headers: dict, timeout: int = 120, retries: int = 2) -> dict:
    """POST JSON avec nouvelles tentatives (1,5 s puis 4 s) sur les erreurs temporaires 429/5xx."""
    import time

    for attempt in range(retries + 1):
        try:
            return _post_json_once(url, payload, headers, timeout)
        except AIError as exc:
            if exc.status not in TRANSIENT or attempt == retries:
                raise
            time.sleep((1.5, 4.0, 8.0)[min(attempt, 2)])
    raise AIError("Échec inattendu.")


def _post_json_once(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    import socket
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"content-type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            resp_headers = dict(resp.headers.items())
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data["_headers"] = resp_headers  # en-têtes de quota (ex. Groq x-ratelimit-*)
            return data
        except ValueError:
            hint = ""
            if "aistudio.google.com" in url or "console." in url or raw.lstrip().startswith("<"):
                hint = (" L'adresse semble être celle d'une page web (page des clés, console…) et non celle "
                        "de l'API. Choisissez le fournisseur dédié dans la liste, ou corrigez l'adresse.")
            raise AIError("Le serveur n'a pas renvoyé de réponse d'API (JSON)." + hint) from None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        detail = _error_message(raw)
        code = exc.code
        if code in (401, 403):
            raise AIError("Clé API refusée (401/403). Vérifiez-la dans Paramètres → Correction.", code) from exc
        if code == 429:
            raise AIError("Quota gratuit ou limite de requêtes atteint (429). Patientez une minute, "
                          "ou essayez un autre modèle.", code) from exc
        if code in (500, 502, 503, 504):
            raise AIError(f"Le service IA est momentanément surchargé ou indisponible ({code}) : « {detail} »", code) from exc
        if code == 404:
            raise AIError(f"Modèle ou adresse introuvable (404) : vérifiez le nom du modèle. {detail}", code) from exc
        if code == 400 and "API key" in raw:
            raise AIError("Clé API invalide pour ce fournisseur. Vérifiez-la dans Paramètres → Correction.", code) from exc
        raise AIError(f"Erreur HTTP {code} : {detail}", code) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise AIError(f"Le service IA n'a pas répondu en {timeout} s. Réessayez, ou choisissez un modèle plus "
                          "rapide (ex. « flash-lite »).") from exc
        raise AIError(f"Serveur injoignable : {exc.reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise AIError(f"Le service IA n'a pas répondu en {timeout} s. Réessayez, ou choisissez un modèle plus "
                      "rapide (ex. « flash-lite »).") from exc


def _call(cfg: dict, user_text: str, timeout: int | None = None) -> str:
    """Appelle le modèle choisi ; s'il reste surchargé (503/429…), bascule sur un autre modèle du fournisseur."""
    ep = resolve(cfg)
    candidates = [ep["model"]] + [m for m in ep["meta"].get("models", []) if m != ep["model"]]
    if ep["id"] in ("openai", "ollama"):
        candidates = candidates[:1]  # modèles locaux / personnalisés : pas de bascule implicite
    last: AIError | None = None
    for model in candidates[:3]:
        try:
            text = _call_model(cfg, user_text, timeout, model)
            cfg["_model_used"] = model
            return text
        except AIError as exc:
            if exc.status not in TRANSIENT:
                raise
            last = exc
    if last is not None and last.status == 429:
        try:
            from . import usage

            usage.mark_exhausted(ep["id"])
        except Exception:  # noqa: BLE001
            pass
    tried = ", ".join(candidates[:3])
    raise AIError(f"{last} — modèles essayés : {tried}. Réessayez dans quelques minutes.", last.status if last else None)


def _record(provider: str, model: str, tokens: int, data: dict) -> None:
    try:
        from . import usage

        usage.record(provider, model, tokens, data.get("_headers") if isinstance(data, dict) else None)
    except Exception:  # noqa: BLE001 — le suivi ne doit jamais faire échouer une correction
        pass


def _call_model(cfg: dict, user_text: str, timeout: int | None, model: str) -> str:
    ep = resolve(cfg)
    ep["model"] = model
    if timeout is None:
        timeout = 300 if ep["id"] == "ollama" else 120
    if ep["kind"] == "anthropic":
        if not ep["key"]:
            raise AIError("Aucune clé API Anthropic configurée (Paramètres → Correction).")
        data = _post_json(ANTHROPIC_URL, {
            "model": ep["model"],
            "max_tokens": 16000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_text}],
        }, {"x-api-key": ep["key"], "anthropic-version": ANTHROPIC_VERSION}, timeout=timeout)
        if data.get("stop_reason") == "max_tokens":
            raise AIError("Réponse tronquée : sélectionnez une partie plus courte du texte.")
        u = data.get("usage") or {}
        _record(ep["id"], model, int(u.get("input_tokens", 0)) + int(u.get("output_tokens", 0)), data)
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    # API compatible OpenAI (Gemini, Mistral, Ollama, Groq, OpenRouter, LM Studio…)
    if not ep["key"] and ep["id"] not in ("ollama", "openai"):
        raise AIError(f"Aucune clé API configurée pour {ep['meta']['label'].split(' —')[0]} "
                      "(Paramètres → Correction).")
    headers = {"authorization": f"Bearer {ep['key']}"} if ep["key"] else {}
    payload = {
        "model": ep["model"],
        "temperature": 0,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": user_text}],
        **ep["meta"].get("extra", {}),
    }
    data = _post_json(f"{ep['base']}/chat/completions", payload, headers, timeout=timeout)
    if isinstance(data, list) and data and isinstance(data[0], dict) and "error" in data[0]:
        data = data[0]  # certaines API renvoient l'erreur dans une liste
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        raise AIError(f"Erreur du service IA : {err.get('message', err) if isinstance(err, dict) else err}")
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError("Réponse inattendue du serveur IA.") from exc
    u = data.get("usage") or {}
    _record(ep["id"], model, int(u.get("total_tokens") or (u.get("prompt_tokens", 0) + u.get("completion_tokens", 0))), data)
    return text


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


def correct_paragraphs(paragraphs: list[str], cfg: dict, timeout: int | None = None) -> list[str]:
    out: list[str] = []
    batch: list[str] = []
    size = 0

    def flush():
        nonlocal batch, size
        if batch:
            reply = _call(cfg, json.dumps(batch, ensure_ascii=False), timeout)
            out.extend(_parse_array(reply, len(batch)))
            batch, size = [], 0

    for p in paragraphs:
        if batch and (size + len(p) > BATCH_CHARS or len(batch) >= BATCH_PARAS):
            flush()
        batch.append(p)
        size += len(p)
    flush()
    return out


TEST_TIMEOUT = 45


def test_connection(cfg: dict) -> str:
    result = correct_paragraphs(["Je suis aller a la plage hier, il faisait tres beaux."], cfg, TEST_TIMEOUT)
    used = cfg.get("_model_used")
    chosen = resolve(cfg)["model"]
    suffix = f" [via {used}, {chosen} étant surchargé]" if used and used != chosen else ""
    return result[0] + suffix


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
