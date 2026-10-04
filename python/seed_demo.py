"""Seed idempotente de dados fictícios para demonstrações locais."""
from __future__ import annotations

import argparse
import os
import uuid

import pymysql

from app.core.config import settings
from app.core.security import hash_senha


USERS = {
    "candidato": ("candidato@demo.talentix.local", "Candidato Demo"),
    "empresa": ("empresa@demo.talentix.local", "Empresa Demo"),
    "admin": ("admin@demo.talentix.local", "Administrador Demo"),
}


def deterministic_uuid(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"talentix-demo:{name}"))


def seed(password: str) -> None:
    if settings.APP_ENV == "production":
        raise SystemExit("O seed de demonstração é bloqueado em produção.")
    if len(password) < 12:
        raise SystemExit("Use uma senha de demonstração com pelo menos 12 caracteres.")

    conn = pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset="utf8mb4",
        autocommit=False,
    )
    try:
        with conn.cursor() as cur:
            ids = {}
            for role, (email, name) in USERS.items():
                user_id = deterministic_uuid(role)
                ids[role] = user_id
                cur.execute("SELECT ID_Usuarios FROM Usuarios WHERE Email=%s", (email,))
                existing = cur.fetchone()
                if existing and existing[0] != user_id:
                    raise RuntimeError(f"E-mail demo já pertence a outra conta: {email}")
                if not existing:
                    cur.execute(
                        """INSERT INTO Usuarios
                           (ID_Usuarios, Nome, Email, SenhaHash, Ativo, EmailConfirmadoEm)
                           VALUES (%s, %s, %s, %s, 1, CURRENT_TIMESTAMP)""",
                        (user_id, name, email, hash_senha(password)),
                    )

            candidate_id = deterministic_uuid("candidate-profile")
            cur.execute("SELECT 1 FROM Candidatos WHERE ID_Usuarios=%s", (ids["candidato"],))
            if not cur.fetchone():
                cur.execute(
                    """INSERT INTO Candidatos
                       (ID_Candidatos, ID_Usuarios, TituloProfissional, Resumo, Cidade, Estado)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (candidate_id, ids["candidato"], "Desenvolvedor(a) Júnior",
                     "Perfil fictício usado somente na apresentação do Talentix.", "Belo Horizonte", "MG"),
                )

            company_id = deterministic_uuid("company-profile")
            cur.execute("SELECT 1 FROM Empresas WHERE ID_Usuarios=%s", (ids["empresa"],))
            if not cur.fetchone():
                cur.execute(
                    """INSERT INTO Empresas
                       (ID_Empresas, ID_Usuarios, RazaoSocial, NomeFantasia, Cnpj, Descricao, Setor, Verificada)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, 1)""",
                    (company_id, ids["empresa"], "Talentix Demo Ltda.", "Talentix Demo",
                     "00.000.000/0001-00", "Empresa fictícia para demonstrações.", "Tecnologia"),
                )

            admin_id = deterministic_uuid("admin-profile")
            cur.execute("SELECT 1 FROM Administradores WHERE ID_Usuarios=%s", (ids["admin"],))
            if not cur.fetchone():
                cur.execute(
                    """INSERT INTO Administradores
                       (ID_Administradores, ID_Usuarios, NivelAcesso, Ativo)
                       VALUES (%s, %s, %s, 1)""",
                    (admin_id, ids["admin"], "superadmin"),
                )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--password", default=os.getenv("DEMO_PASSWORD"), help="Senha comum somente para os usuários fictícios locais.")
    args = parser.parse_args()
    if not args.password:
        parser.error("Informe DEMO_PASSWORD ou --password.")
    seed(args.password)
    print("Seed de demonstração aplicado com sucesso.")
