"""
Utilitário de upload de arquivos: salva em disco dentro de uploads/<categoria>/
e retorna a URL relativa + metadados (tamanho em bytes, tipo MIME, hash SHA-256),
conforme o padrão adotado no banco (campo Url + TamanhoBytes + TipoMime + Hash).
"""
import hashlib
import os
from pathlib import Path
from fastapi import UploadFile, HTTPException, status
from app.core.config import settings

EXTENSOES_PERMITIDAS = {
    "fotos": {".jpg", ".jpeg", ".png", ".webp"},
    "logos": {".jpg", ".jpeg", ".png", ".webp", ".svg"},
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

    conteudo = await arquivo.read()
    tamanho_bytes = len(conteudo)

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if tamanho_bytes > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Arquivo excede o limite de {settings.MAX_UPLOAD_SIZE_MB}MB.",
        )

    sha256_hash = hashlib.sha256(conteudo).hexdigest()
    nome_arquivo = f"{sha256_hash}{extensao}"

    diretorio = Path(settings.UPLOAD_DIR) / categoria
    diretorio.mkdir(parents=True, exist_ok=True)
    caminho_completo = diretorio / nome_arquivo

    with open(caminho_completo, "wb") as f:
        f.write(conteudo)

    url_relativa = f"/{settings.UPLOAD_DIR}/{categoria}/{nome_arquivo}"

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
    caminho = Path(url_relativa.lstrip("/"))
    if caminho.exists() and caminho.is_file():
        os.remove(caminho)