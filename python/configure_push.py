"""Gera chaves Web Push no .env local; não mostra nem substitui chaves existentes."""

import base64
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization


def main():
    path = Path(__file__).resolve().parent / ".env"
    if not path.exists():
        raise SystemExit("Execute configure_dev.py antes de configurar push.")
    text = path.read_text()
    values = dict(
        line.split("=", 1)
        for line in text.splitlines()
        if "=" in line and not line.startswith("#")
    )
    if values.get("VAPID_PRIVATE_KEY") or values.get("VAPID_PUBLIC_KEY"):
        raise SystemExit("Chaves existentes preservadas. Nenhuma alteração realizada.")
    key = ec.generate_private_key(ec.SECP256R1())
    encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b"=").decode()
    additions = {
        "VAPID_PRIVATE_KEY": encode(
            key.private_numbers().private_value.to_bytes(32, "big")
        ),
        "VAPID_PUBLIC_KEY": encode(
            key.public_key().public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint,
            )
        ),
        "VAPID_SUBJECT": values.get("VAPID_SUBJECT")
        or "mailto:" + values.get("SMTP_FROM_EMAIL", "no-reply@talentix.com"),
    }
    lines = [
        line for line in text.splitlines() if line.split("=", 1)[0] not in additions
    ]
    path.write_text(
        "\n".join(lines)
        + "\n"
        + "".join(k + "=" + v + "\n" for k, v in additions.items())
    )
    print(
        "Chaves Web Push salvas localmente. Reinicie a API e o worker. Revise VAPID_SUBJECT com o contato responsável."
    )


if __name__ == "__main__":
    main()
