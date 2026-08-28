"""
CRUD de Assinaturas (planos das empresas) e Pagamentos.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from datetime import date

from app.db.database import fetch_one, fetch_all, execute
from app.core.security import novo_uuid
from app.core.deps import usuario_atual, exigir_tipo
from app.core.notificar import notificar_usuario
from app.core.email_service import email_pagamento_processado

router = APIRouter(tags=["Financeiro"])

_ASSINATURA_ATIVA = 1
_ASSINATURA_CANCELADA = 3
_PAGAMENTO_PENDENTE = 1
_PAGAMENTO_APROVADO = 2
_PAGAMENTO_ESTORNADO = 4


async def _checar_dono_empresa(id_empresa: str, sessao: dict) -> None:
    if sessao["tipo_usuario"] == "administrador":
        return
    empresa = await fetch_one("SELECT * FROM Empresas WHERE ID_Empresas=%s", (id_empresa,))
    if not empresa or empresa["ID_Usuarios"] != sessao["id_usuario"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão sobre esta empresa.")


# ==================== ASSINATURAS ====================

class AssinaturaCreate(BaseModel):
    id_empresa: str
    plano: str
    valor: float
    inicio: date
    fim: date | None = None


@router.post("/assinaturas", status_code=201)
async def criar_assinatura(dados: AssinaturaCreate, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_empresa(dados.id_empresa, sessao)
    id_assinatura = novo_uuid()
    await execute(
        """INSERT INTO Assinaturas (ID_Assinaturas, ID_Empresas, ID_Status_Assinatura, Plano, Valor, Inicio, Fim)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (id_assinatura, dados.id_empresa, _ASSINATURA_ATIVA, dados.plano, dados.valor, dados.inicio, dados.fim),
    )
    return await fetch_one("SELECT * FROM Assinaturas WHERE ID_Assinaturas=%s", (id_assinatura,))


@router.get("/empresas/{id_empresa}/assinatura")
async def obter_assinatura_empresa(id_empresa: str, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_empresa(id_empresa, sessao)
    assinatura = await fetch_one(
        "SELECT * FROM Assinaturas WHERE ID_Empresas=%s ORDER BY CriadaEm DESC LIMIT 1", (id_empresa,)
    )
    if not assinatura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nenhuma assinatura encontrada para esta empresa.")
    return assinatura


@router.patch("/assinaturas/{id_assinatura}/renovar")
async def renovar_assinatura(id_assinatura: str, nova_data_fim: date, sessao: dict = Depends(usuario_atual)):
    assinatura = await fetch_one("SELECT * FROM Assinaturas WHERE ID_Assinaturas=%s", (id_assinatura,))
    if not assinatura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assinatura não encontrada.")
    await _checar_dono_empresa(assinatura["ID_Empresas"], sessao)
    await execute(
        "UPDATE Assinaturas SET Fim=%s, ID_Status_Assinatura=%s WHERE ID_Assinaturas=%s",
        (nova_data_fim, _ASSINATURA_ATIVA, id_assinatura),
    )
    return await fetch_one("SELECT * FROM Assinaturas WHERE ID_Assinaturas=%s", (id_assinatura,))


@router.patch("/assinaturas/{id_assinatura}/cancelar")
async def cancelar_assinatura(id_assinatura: str, sessao: dict = Depends(usuario_atual)):
    assinatura = await fetch_one("SELECT * FROM Assinaturas WHERE ID_Assinaturas=%s", (id_assinatura,))
    if not assinatura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assinatura não encontrada.")
    await _checar_dono_empresa(assinatura["ID_Empresas"], sessao)
    await execute(
        "UPDATE Assinaturas SET ID_Status_Assinatura=%s WHERE ID_Assinaturas=%s",
        (_ASSINATURA_CANCELADA, id_assinatura),
    )
    return {"mensagem": "Assinatura cancelada."}


# ==================== PAGAMENTOS ====================

class PagamentoCreate(BaseModel):
    id_assinatura: str
    valor: float
    metodo: str | None = None
    transacao_id: str | None = None


@router.post("/pagamentos", status_code=201)
async def registrar_pagamento(dados: PagamentoCreate, sessao: dict = Depends(usuario_atual)):
    assinatura = await fetch_one("SELECT * FROM Assinaturas WHERE ID_Assinaturas=%s", (dados.id_assinatura,))
    if not assinatura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assinatura não encontrada.")
    await _checar_dono_empresa(assinatura["ID_Empresas"], sessao)

    id_pagamento = novo_uuid()
    await execute(
        """INSERT INTO Pagamentos (ID_Pagamentos, ID_Assinaturas, ID_Status_Pagamento, Valor, Metodo, TransacaoId)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (id_pagamento, dados.id_assinatura, _PAGAMENTO_PENDENTE, dados.valor, dados.metodo, dados.transacao_id),
    )
    return await fetch_one("SELECT * FROM Pagamentos WHERE ID_Pagamentos=%s", (id_pagamento,))


@router.get("/assinaturas/{id_assinatura}/pagamentos")
async def listar_pagamentos(id_assinatura: str, sessao: dict = Depends(usuario_atual)):
    assinatura = await fetch_one("SELECT * FROM Assinaturas WHERE ID_Assinaturas=%s", (id_assinatura,))
    if not assinatura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assinatura não encontrada.")
    await _checar_dono_empresa(assinatura["ID_Empresas"], sessao)
    return await fetch_all(
        "SELECT * FROM Pagamentos WHERE ID_Assinaturas=%s ORDER BY CriadoEm DESC", (id_assinatura,)
    )


@router.patch("/pagamentos/{id_pagamento}/processar")
async def processar_pagamento(id_pagamento: str, aprovado: bool):
    """Endpoint chamado pelo gateway de pagamento (webhook) para confirmar o resultado."""
    novo_status = _PAGAMENTO_APROVADO if aprovado else 3  # 3 = RECUSADO
    await execute(
        "UPDATE Pagamentos SET ID_Status_Pagamento=%s, PagoEm=NOW() WHERE ID_Pagamentos=%s",
        (novo_status, id_pagamento),
    )

    pagamento = await fetch_one("SELECT * FROM Pagamentos WHERE ID_Pagamentos=%s", (id_pagamento,))
    assinatura = await fetch_one("SELECT * FROM Assinaturas WHERE ID_Assinaturas=%s", (pagamento["ID_Assinaturas"],))
    if assinatura:
        empresa = await fetch_one("SELECT ID_Usuarios FROM Empresas WHERE ID_Empresas=%s", (assinatura["ID_Empresas"],))
        if empresa:
            await notificar_usuario(
                id_usuario=empresa["ID_Usuarios"],
                titulo="Pagamento processado",
                mensagem=f"Seu pagamento de R$ {pagamento['Valor']:.2f} foi {'aprovado' if aprovado else 'recusado'}.",
                tipo="pagamento",
                enviar_email_fn=lambda email: email_pagamento_processado(email, float(pagamento["Valor"]), aprovado),
            )

    return pagamento


@router.patch("/pagamentos/{id_pagamento}/estornar")
async def estornar_pagamento(id_pagamento: str, sessao: dict = Depends(exigir_tipo("administrador"))):
    await execute(
        "UPDATE Pagamentos SET ID_Status_Pagamento=%s WHERE ID_Pagamentos=%s",
        (_PAGAMENTO_ESTORNADO, id_pagamento),
    )
    return {"mensagem": "Pagamento estornado."}