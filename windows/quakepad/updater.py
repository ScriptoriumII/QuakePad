"""Mise à jour automatique depuis les Releases GitHub de ScriptoriumII/QuakePad.

Sécurité :
- requêtes en HTTPS uniquement, sans aucun secret ;
- téléchargement autorisé seulement vers les hôtes de GitHub (redirections incluses) ;
- l'installateur n'est lancé que si son empreinte SHA-256 correspond à celle publiée dans
  SHA256SUMS.txt (fichier généré par GitHub Actions lors de la publication).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from . import netsec
from .log import log
from .settings import APP_VERSION

REPO = "ScriptoriumII/QuakePad"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
DOWNLOAD_HOSTS = {
    "github.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "github-releases.githubusercontent.com",
}
CHECK_INTERVAL_S = 24 * 3600
_UA = {"User-Agent": f"QuakePad/{APP_VERSION}", "Accept": "application/vnd.github+json"}


class UpdateError(Exception):
    pass


@dataclass
class Release:
    version: str
    tag: str
    notes: str
    page_url: str
    setup_name: str
    setup_url: str
    setup_size: int
    sums_url: str


def parse_version(text: str) -> tuple[int, ...]:
    """« v1.10.2 » -> (1, 10, 2) ; les suffixes (-beta…) sont ignorés."""
    m = re.match(r"v?(\d+(?:\.\d+)*)", (text or "").strip())
    if not m:
        return (0,)
    return tuple(int(x) for x in m.group(1).split("."))


def is_newer(candidate: str, current: str = APP_VERSION) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def _get_json(url: str, timeout: float = 15) -> dict:
    req = urllib.request.Request(url, headers=_UA)
    try:
        with netsec.open_url(req, timeout, sends_secret=False) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError(
                "Aucune version publiée trouvée (dépôt privé ou aucune Release). "
                f"Les versions sont publiées sur {RELEASES_PAGE}."
            ) from exc
        if exc.code == 403:
            raise UpdateError("GitHub limite temporairement les vérifications (403). Réessayez plus tard.") from exc
        raise UpdateError(f"Erreur GitHub HTTP {exc.code}.") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise UpdateError(f"Vérification impossible : {getattr(exc, 'reason', exc)}") from exc


def latest_release(api_url: str = API_LATEST) -> Release:
    data = _get_json(api_url)
    tag = data.get("tag_name") or ""
    assets = {a.get("name", ""): a for a in data.get("assets", [])}
    setup = next((a for n, a in assets.items() if re.fullmatch(r"QuakePad-Setup-[\w.\-]+\.exe", n)), None)
    sums = assets.get("SHA256SUMS.txt")
    if not setup or not sums:
        raise UpdateError(f"La version {tag} ne contient pas d'installateur vérifiable.")
    return Release(
        version=tag.lstrip("v"),
        tag=tag,
        notes=(data.get("body") or "").strip(),
        page_url=data.get("html_url") or RELEASES_PAGE,
        setup_name=setup["name"],
        setup_url=setup["browser_download_url"],
        setup_size=int(setup.get("size") or 0),
        sums_url=sums["browser_download_url"],
    )


# --- Téléchargement : redirections permises uniquement vers les hôtes GitHub, en HTTPS ---------
class _GitHubOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urlsplit(newurl)
        if parts.scheme != "https" or (parts.hostname or "") not in DOWNLOAD_HOSTS:
            raise UpdateError(f"Redirection de téléchargement refusée vers « {parts.hostname} ».")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_DL_OPENER = urllib.request.build_opener(_GitHubOnlyRedirect)


def _check_download_url(url: str, allow_local: bool) -> None:
    parts = urlsplit(url)
    if allow_local and parts.hostname in ("127.0.0.1", "localhost"):
        return  # tests uniquement
    if parts.scheme != "https" or (parts.hostname or "") not in DOWNLOAD_HOSTS:
        raise UpdateError(f"Adresse de téléchargement non autorisée : {url}")


def _download(url: str, dest: Path, progress=None, allow_local: bool = False, limit: int = 300_000_000) -> str:
    """Télécharge vers dest et renvoie l'empreinte SHA-256 (hex)."""
    _check_download_url(url, allow_local)
    req = urllib.request.Request(url, headers={"User-Agent": _UA["User-Agent"], "Accept": "application/octet-stream"})
    h = hashlib.sha256()
    done = 0
    try:
        with _DL_OPENER.open(req, timeout=60) as resp, open(dest, "wb") as f:
            total = int(resp.headers.get("Content-Length") or 0)
            while chunk := resp.read(256 * 1024):
                done += len(chunk)
                if done > limit:
                    raise UpdateError("Fichier anormalement volumineux : téléchargement interrompu.")
                f.write(chunk)
                h.update(chunk)
                if progress:
                    progress(done, total)
    except (urllib.error.URLError, OSError) as exc:
        raise UpdateError(f"Téléchargement impossible : {getattr(exc, 'reason', exc)}") from exc
    return h.hexdigest()


def download_verified(rel: Release, progress=None, allow_local: bool = False) -> Path:
    """Télécharge l'installateur et vérifie son empreinte ; renvoie son chemin."""
    folder = Path(tempfile.mkdtemp(prefix="quakepad-update-"))
    sums_path = folder / "SHA256SUMS.txt"
    _download(rel.sums_url, sums_path, allow_local=allow_local, limit=100_000)
    expected = None
    for line in sums_path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[1].lstrip("*") == rel.setup_name and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            expected = parts[0].lower()
    if not expected:
        raise UpdateError("Empreinte de l'installateur absente de SHA256SUMS.txt : mise à jour annulée.")
    setup = folder / rel.setup_name
    actual = _download(rel.setup_url, setup, progress=progress, allow_local=allow_local)
    if actual != expected:
        setup.unlink(missing_ok=True)
        log.error("Empreinte invalide pour %s : attendue %s, obtenue %s", rel.setup_name, expected, actual)
        raise UpdateError("L'installateur téléchargé ne correspond pas à l'empreinte publiée : mise à jour annulée.")
    log.info("Mise à jour %s téléchargée et vérifiée (SHA-256 %s)", rel.version, actual)
    return setup


def can_self_update() -> bool:
    """Seule la version installée (exécutable) se met à jour seule ; depuis les sources : git pull."""
    return bool(getattr(sys, "frozen", False)) and sys.platform == "win32"


def launch_installer(setup: Path) -> None:
    """Lance l'installateur en mode silencieux ; il ferme QuakePad puis le relance."""
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(  # noqa: S603 — chemin vérifié (empreinte), arguments fixes
        [str(setup), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
        creationflags=flags,
        close_fds=True,
    )
    log.info("Installateur lancé : %s", setup)
