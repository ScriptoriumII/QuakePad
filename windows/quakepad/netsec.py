"""Sécurité réseau : validation des adresses et ouverture HTTP(S) sans redirection.

Règles :
- seuls http:// et https:// sont acceptés (jamais file://, ftp://, data:…) ;
- une requête qui transporte un secret (clé API) exige https://, sauf vers la machine locale
  (localhost / 127.0.0.1 / ::1, ex. Ollama) ;
- sans secret, http:// est toléré vers le réseau local (LanguageTool ou Ollama auto-hébergés) :
  adresses privées RFC 1918, link-local, noms sans point, .local / .lan / .internal / .home.arpa ;
- les redirections HTTP sont refusées (elles pourraient renvoyer une clé vers un autre hôte).
"""

from __future__ import annotations

import ipaddress
import urllib.request
from urllib.parse import urlsplit

LOCAL_SUFFIXES = (".local", ".lan", ".internal", ".home.arpa", ".localdomain")


class UnsafeURLError(ValueError):
    pass


def _host_kind(host: str) -> str:
    """'loopback', 'private' ou 'public'."""
    host = host.strip("[]").lower()
    if host in ("localhost",) or host.endswith(".localhost"):
        return "loopback"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or host.endswith(LOCAL_SUFFIXES):
            return "private"
        return "public"
    if ip.is_loopback:
        return "loopback"
    if ip.is_private or ip.is_link_local:
        return "private"
    return "public"


def validate_url(url: str, *, sends_secret: bool) -> str:
    """Vérifie une adresse de service ; lève UnsafeURLError avec un message clair sinon."""
    parts = urlsplit((url or "").strip())
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeURLError(f"Adresse refusée : « {url} ». Seules les adresses http:// ou https:// sont acceptées.")
    if parts.username or parts.password:
        raise UnsafeURLError("Adresse refusée : ne mettez pas d'identifiants dans l'adresse (user:motdepasse@…).")
    if scheme == "https":
        return url
    kind = _host_kind(parts.hostname)
    if kind == "loopback":
        return url
    if sends_secret:
        raise UnsafeURLError(
            f"Adresse refusée : « {url} » n'est pas chiffrée (http). La clé API circulerait en clair sur le réseau : "
            "utilisez https://."
        )
    if kind == "private":
        return url
    raise UnsafeURLError(f"Adresse refusée : « {url} ». Utilisez https:// pour un serveur sur Internet.")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401, ARG002
        raise UnsafeURLError(f"Redirection refusée vers « {newurl} » : vérifiez l'adresse du service.")


# Proxy système respecté (ProxyHandler par défaut), redirections interdites.
_OPENER = urllib.request.build_opener(_NoRedirect)


def open_url(req: urllib.request.Request, timeout: float, *, sends_secret: bool):
    validate_url(req.full_url, sends_secret=sends_secret)
    return _OPENER.open(req, timeout=timeout)
