"""Validação central contra SSRF para chamadas HTTP iniciadas pelo servidor."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from fastapi import HTTPException, status


_HOSTS_BLOQUEADOS = {
    "localhost",
    "metadata",
    "metadata.google.internal",
}


def validar_url_saida(url: str, hosts_permitidos: set[str] | None = None) -> str:
    """
    Valida destinos antes de qualquer request server-side.

    Regras:
    - apenas HTTPS;
    - sem usuário/senha embutidos na URL;
    - allowlist opcional;
    - bloqueia loopback, redes privadas, link-local, multicast,
      endereços reservados e endpoints de metadata.
    """
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "URL inválida.") from exc

    if parsed.scheme != "https":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Somente URLs HTTPS são permitidas.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Destino HTTP inválido.")

    host = parsed.hostname.rstrip(".").lower()
    if hosts_permitidos is not None:
        permitidos = {item.rstrip(".").lower() for item in hosts_permitidos}
        if host not in permitidos:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Destino não está na allowlist.")

    if host in _HOSTS_BLOQUEADOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Destino interno não permitido.")

    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Não foi possível resolver o destino.") from exc

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Destino de rede interno não permitido.")

    return url
