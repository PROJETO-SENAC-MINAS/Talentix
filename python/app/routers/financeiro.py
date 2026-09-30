"""
CRUD de Assinaturas (planos das empresas) e Pagamentos.
"""
from app.core.routes import AtomicRouter as APIRouter

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from datetime import date

from app.db.database import fetch_one, fetch_all, execute
from app.core.security import novo_uuid
from app.core.deps import usuario_atual, exigir_tipo
from app.core.access import checar_empresa
from app.core.validation import PositiveMoney
from app.core.service_auth import exigir_gateway_pagamento
from app.core.notificar import notificar_usuario
from app.core.email_service import email_pagamento_processado

router = APIRouter(tags=["Financeiro"])

_ASSINATURA_ATIVA = 1
_ASSINATURA_CANCELADA = 3
_PAGAMENTO_PENDENTE = 1
_PAGAMENTO_APROVADO = 2
_PAGAMENTO_ESTORNADO = 4


async def _checar_dono_empresa(id_empresa: str, sessao: dict) -> None:
    await checar_empresa(id_empresa, sessao, permitir_recrutador=False)


# ==================== ASSINATURAS ====================

class AssinaturaCreate(BaseModel):
    id_empresa: str
    plano: str = Field(min_length=1, max_length=50)
    valor: PositiveMoney
    inicio: date
    fim: date | None = None

    @model_validator(mode="after")
    def intervalo(self):
        if self.fim and self.fim < self.inicio:
            raise ValueError("Fim da assinatura deve ser posterior ao início.")
        return self


@router.post("/assinaturas", status_code=201)
async def criar_assinatura(dados: AssinaturaCreate, sessao: dict = Depends(exigir_tipo("administrador"))):
    await _checar_dono_empresa(dados.id_empresa, sessao)
    await fetch_one("SELECT ID_Empresas FROM Empresas WHERE ID_Empresas=%s FOR UPDATE", (dados.id_empresa,))
    if await fetch_one("SELECT ID_Assinaturas FROM Assinaturas WHERE ID_Empresas=%s AND ID_Status_Assinatura=1", (dados.id_empresa,)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A empresa já possui assinatura ativa.")
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
async def renovar_assinatura(id_assinatura: str, nova_data_fim: date, sessao: dict = Depends(exigir_tipo("administrador"))):
    assinatura = await fetch_one("SELECT * FROM Assinaturas WHERE ID_Assinaturas=%s", (id_assinatura,))
    if not assinatura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assinatura não encontrada.")
    await _checar_dono_empresa(assinatura["ID_Empresas"], sessao)
    if nova_data_fim < assinatura["Inicio"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Fim anterior ao início da assinatura.")
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
    valor: PositiveMoney
    metodo: str | None = Field(default=None, max_length=50)
    transacao_id: str | None = Field(default=None, min_length=1, max_length=150)


@router.post("/pagamentos", status_code=201)
async def registrar_pagamento(dados: PagamentoCreate, sessao: dict = Depends(usuario_atual)):
    assinatura = await fetch_one("SELECT * FROM Assinaturas WHERE ID_Assinaturas=%s", (dados.id_assinatura,))
    if not assinatura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assinatura não encontrada.")
    await _checar_dono_empresa(assinatura["ID_Empresas"], sessao)

    if dados.valor != assinatura["Valor"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Valor deve corresponder ao valor da assinatura.")
    if dados.transacao_id and await fetch_one("SELECT ID_Pagamentos FROM Pagamentos WHERE TransacaoId=%s", (dados.transacao_id,)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Transação já registrada.")

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


@router.patch("/pagamentos/{id_pagamento}/processar", dependencies=[Depends(exigir_gateway_pagamento)])
async def processar_pagamento(id_pagamento: str, aprovado: bool):
    """Endpoint chamado pelo gateway de pagamento (webhook) para confirmar o resultado."""
    pagamento = await fetch_one("SELECT * FROM Pagamentos WHERE ID_Pagamentos=%s FOR UPDATE", (id_pagamento,))
    if not pagamento:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pagamento não encontrado.")
    novo_status = _PAGAMENTO_APROVADO if aprovado else 3  # 3 = RECUSADO
    if pagamento["ID_Status_Pagamento"] == novo_status:
        return pagamento
    if pagamento["ID_Status_Pagamento"] != _PAGAMENTO_PENDENTE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Pagamento já finalizado com outro resultado.")
    await execute(
        "UPDATE Pagamentos SET ID_Status_Pagamento=%s, PagoEm=CASE WHEN %s THEN NOW() ELSE NULL END WHERE ID_Pagamentos=%s",
        (novo_status, aprovado, id_pagamento),
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
    pagamento = await fetch_one("SELECT * FROM Pagamentos WHERE ID_Pagamentos=%s FOR UPDATE", (id_pagamento,))
    if not pagamento:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pagamento não encontrado.")
    if pagamento["ID_Status_Pagamento"] == _PAGAMENTO_ESTORNADO:
        return {"mensagem": "Estorno já registrado."}
    if pagamento["ID_Status_Pagamento"] != _PAGAMENTO_APROVADO:
        raise HTTPException(status.HTTP_409_CONFLICT, "Só é possível registrar estorno de pagamento aprovado.")
    await execute(
        "UPDATE Pagamentos SET ID_Status_Pagamento=%s WHERE ID_Pagamentos=%s",
        (_PAGAMENTO_ESTORNADO, id_pagamento),
    )
    return {"mensagem": "Estorno registrado. A devolução financeira depende do gateway contratado."}
