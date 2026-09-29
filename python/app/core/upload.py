"""
Utilitário de upload de arquivos: salva em disco dentro de uploads/<categoria>/
e retorna a URL relativa + metadados (tamanho em bytes, tipo MIME, hash SHA-256),
conforme o padrão adotado no banco (campo Url + TamanhoBytes + TipoMime + Hash).
"""
import hashlib
import os
import re
from pathlib import Path
from fastapi import UploadFile, HTTPException, status
from app.core.config import settings

EXTENSOES_PERMITIDAS = {
    "fotos": {".jpg", ".jpeg", ".png", ".webp"},
    # SVG pode conter scripts quando servido no mesmo domínio da API.
    "logos": {".jpg", ".jpeg", ".png", ".webp"},
    "curriculos": {".pdf", ".doc", ".docx"},
}


async def salvar_arquivo(arquivo: UploadFile, categoria: str) -> dict:
    """
    Salva o arquivo enviado em uploads/<categoria>/ com nome único (hash),
    e retorna um dicionário com: url, tamanho_bytes, tipo_mime, hash.
    """
    if categoria not in EXTENSOES_PERMITIDAS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Categoria de upload inválida.")

    extensao = Path(arquivo.filename or "").suffix.lower()
    if extensao not in EXTENSOES_PERMITIDAS[categoria]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Extensão '{extensao}' não permitida para {categoria}. "
            f"Permitidas: {', '.join(EXTENSOES_PERMITIDAS[categoria])}",
        )

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    conteudo = await arquivo.read(max_bytes + 1)
    tamanho_bytes = len(conteudo)

    if tamanho_bytes > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Arquivo excede o limite de {settings.MAX_UPLOAD_SIZE_MB}MB.",
        )

    sha256_hash = hashlib.sha256(conteudo).hexdigest()
    nome_arquivo = f"{sha256_hash}{extensao}"

    diretorio = Path(settings.UPLOAD_DIR) / categoria
    try:
        diretorio.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        # No Windows, mkdir com exist_ok=True pode falhar mesmo quando o
        # diretório já existe (reparse points/junctions criados pelo WAMP).
        # Se o caminho já existe e é um diretório de fato, seguimos normalmente.
        if not diretorio.is_dir():
            raise
    caminho_completo = diretorio / nome_arquivo

    with open(caminho_completo, "wb") as f:
        f.write(conteudo)

    url_relativa = f"/uploads/{categoria}/{nome_arquivo}"

    return {
        "url": url_relativa,
        "tamanho_bytes": tamanho_bytes,
        "tipo_mime": arquivo.content_type or "application/octet-stream",
        "hash": sha256_hash,
    }


def remover_arquivo(url_relativa: str) -> None:
    """Remove um arquivo físico dado a URL relativa salva no banco (best-effort)."""
    if not url_relativa:
        return
    partes = Path(url_relativa).parts
    if len(partes) != 4 or partes[:2] != ("/", "uploads") or partes[2] not in EXTENSOES_PERMITIDAS:
        return
    if not re.fullmatch(r"[a-f0-9]{64}\.[a-z]+", partes[3]):
        return
    # Formato /uploads/<categoria>/<arquivo>; Path inclui a raiz como primeira parte.
    caminho = Path(settings.UPLOAD_DIR) / partes[2] / partes[3]
    if caminho.exists() and caminho.is_file():
        os.remove(caminho)
