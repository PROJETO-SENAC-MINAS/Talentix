"""
Utilitário de upload seguro de arquivos.
"""
import hashlib
import os
import re
import zipfile
import asyncio
import warnings
import tempfile
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile, HTTPException, status

from app.core.config import settings
from PIL import Image, ImageOps, UnidentifiedImageError


def _sanitizar_imagem(conteudo, extensao):
    """Decodifica pixels, limita dimensões e elimina EXIF/metadados/polyglots."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(conteudo)) as original:
                expected = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}[extensao]
                if original.format != expected or original.width * original.height > 16_000_000:
                    raise ValueError("Imagem inválida ou muito grande.")
                original.load()
                image = ImageOps.exif_transpose(original).convert("RGB")
                image.thumbnail((1200, 1200))
                image.info.clear()
                output = BytesIO()
                image.save(output, format="PNG", exif=b"", icc_profile=None)
                return output.getvalue()
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(400, "Imagem inválida. Use JPG, PNG ou WebP com até 16 megapixels.") from exc

EXTENSOES_PERMITIDAS = {
    "fotos": {".jpg", ".jpeg", ".png", ".webp"},
    # SVG não é aceito: pode conter scripts quando servido no mesmo domínio.
    "logos": {".jpg", ".jpeg", ".png", ".webp"},
    "curriculos": {".pdf", ".doc", ".docx"},
}

_MIME_REAL = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _validar_assinatura(conteudo: bytes, extensao: str, categoria: str) -> None:
    """Confere assinatura real para impedir arquivo executável disfarçado."""
    valido = True
    if extensao == ".pdf":
        valido = conteudo.startswith(b"%PDF-")
    elif extensao == ".doc":
        valido = conteudo.startswith(bytes.fromhex("D0CF11E0A1B11AE1"))
    elif extensao == ".docx":
        valido = conteudo.startswith(b"PK")
        if valido:
            try:
                with zipfile.ZipFile(BytesIO(conteudo)) as pacote:
                    nomes = set(pacote.namelist())
                    total_descompactado = sum(item.file_size for item in pacote.infolist())
                    valido = (
                        "[Content_Types].xml" in nomes
                        and "word/document.xml" in nomes
                        and len(nomes) <= 2000
                        and total_descompactado <= 25 * 1024 * 1024
                    )
            except (zipfile.BadZipFile, RuntimeError):
                valido = False
    elif extensao in {".jpg", ".jpeg"}:
        valido = conteudo.startswith(b"\xff\xd8\xff")
    elif extensao == ".png":
        valido = conteudo.startswith(b"\x89PNG\r\n\x1a\n")
    elif extensao == ".webp":
        valido = len(conteudo) >= 12 and conteudo[:4] == b"RIFF" and conteudo[8:12] == b"WEBP"

    if not valido:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"O conteúdo do arquivo não corresponde à extensão {extensao}.",
        )


async def salvar_arquivo(arquivo: UploadFile, categoria: str) -> dict:
    """
    Salva em uploads/<categoria>/ com nome baseado em SHA-256.
    O nome original nunca vira caminho no servidor.
    """
    if categoria not in EXTENSOES_PERMITIDAS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Categoria de upload inválida.")

    extensao = Path(arquivo.filename or "").suffix.lower()
    if extensao not in EXTENSOES_PERMITIDAS[categoria]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Extensão '{extensao}' não permitida para {categoria}. "
            f"Permitidas: {', '.join(sorted(EXTENSOES_PERMITIDAS[categoria]))}",
        )

    max_bytes = min(settings.MAX_UPLOAD_SIZE_MB, 5) * 1024 * 1024 if categoria in {"fotos", "logos"} else settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    conteudo = await arquivo.read(max_bytes + 1)
    tamanho_bytes = len(conteudo)

    if not conteudo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "O arquivo enviado está vazio.")
    if tamanho_bytes > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Arquivo excede o limite de {settings.MAX_UPLOAD_SIZE_MB}MB.",
        )

    _validar_assinatura(conteudo, extensao, categoria)
    if categoria in {"fotos", "logos"}:
        conteudo = await asyncio.to_thread(_sanitizar_imagem, conteudo, extensao)
        extensao = ".png"
        tamanho_bytes = len(conteudo)

    sha256_hash = hashlib.sha256(conteudo).hexdigest()
    nome_arquivo = f"{sha256_hash}{extensao}"

    diretorio = Path(settings.UPLOAD_DIR) / categoria
    try:
        diretorio.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        if not diretorio.is_dir():
            raise
    caminho_completo = diretorio / nome_arquivo

    # Escrita idempotente: o mesmo hash representa exatamente os mesmos bytes.
    if not caminho_completo.exists():
        temporario = None
        try:
            with tempfile.NamedTemporaryFile(dir=diretorio, delete=False) as f:
                temporario = f.name
                f.write(conteudo)
                f.flush()
                os.fsync(f.fileno())
            os.link(temporario, caminho_completo)
        except FileExistsError:
            pass
        finally:
            if temporario:
                os.unlink(temporario)

    url_relativa = f"/uploads/{categoria}/{nome_arquivo}"
    return {
        "url": url_relativa,
        "tamanho_bytes": tamanho_bytes,
        "tipo_mime": _MIME_REAL.get(extensao, "application/octet-stream"),
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
    caminho = Path(settings.UPLOAD_DIR) / partes[2] / partes[3]
    if caminho.exists() and caminho.is_file():
        os.remove(caminho)
