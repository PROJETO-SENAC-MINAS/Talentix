"""Subprocesso descartável para PDFs/DOCX não confiáveis; nunca serve HTTP."""
import json
import sys
from pathlib import Path
try:
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (35, 35))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
except ImportError:
    pass  # Windows usa o timeout e kill do processo pai.
from app.core.resume_parser import extrair_texto_curriculo

if __name__ == "__main__":
    print(json.dumps(extrair_texto_curriculo(Path(sys.argv[1])), ensure_ascii=False))
