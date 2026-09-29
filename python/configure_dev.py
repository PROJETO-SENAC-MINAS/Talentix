"""Cria configuração LOCAL sem imprimir segredos. Não sobrescreve um .env existente."""
from pathlib import Path
import argparse
import secrets


def configurar(rotacionar: bool = False) -> Path:
    raiz = Path(__file__).resolve().parent
    destino = raiz / ".env"
    if destino.exists() and not rotacionar:
        raise SystemExit("Já existe um .env. Use --rotate-keys para substituir as chaves expostas.")

    conteudo = destino.read_text(encoding="utf-8") if destino.exists() else (raiz / ".env.example").read_text(encoding="utf-8")
    valores = {nome: secrets.token_hex(32) for nome in ("SECRET_KEY", "IA_WORKER_TOKEN", "PAYMENT_WEBHOOK_TOKEN")}
    if not destino.exists():
        valores["SESSION_COOKIE_SECURE"] = "false"  # desenvolvimento em HTTP/localhost
    linhas = []
    for linha in conteudo.splitlines():
        nome = linha.partition("=")[0].strip()
        if nome in valores:
            linhas.append(f"{nome}={valores.pop(nome)}")
        else:
            linhas.append(linha)
    linhas.extend(f"{nome}={valor}" for nome, valor in valores.items())
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    destino.chmod(0o600)
    return destino


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rotate-keys", action="store_true", help="Rotaciona as três chaves locais e mantém as demais configurações.")
    args = parser.parse_args()
    configurar(args.rotate_keys)
    print("Configuração local gravada. Ajuste o banco e use uma senha SMTP nova antes de habilitar e-mails.")
