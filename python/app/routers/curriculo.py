"""
CRUD de Currículos, importação inteligente, Experiências e Formações.
"""
from app.core.routes import AtomicRouter as APIRouter

import asyncio
import json
import re
from datetime import date
from pathlib import Path

from fastapi import Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel, Field

from app.db.database import fetch_one, fetch_all, execute
from app.core.security import novo_uuid
from app.core.deps import usuario_atual
from app.core.access import checar_leitura_candidato, checar_dono_candidato
from app.core.upload import salvar_arquivo
from app.core.config import settings
from app.core.resume_parser import extrair_texto_curriculo, analisar_curriculo

router = APIRouter(tags=["Currículo"])

_STATUS_NA_FILA = 1
_STATUS_PROCESSANDO = 2
_STATUS_CONCLUIDO = 3
_STATUS_FALHOU = 4


async def garantir_schema_curriculo_importacoes() -> None:
    """Verifica o schema sem exigir DDL da conta operacional. Execute migrate.py antes da API."""
    await fetch_one("SELECT * FROM Curriculo_Importacoes LIMIT 0")


async def _checar_dono_candidato(id_candidato: str, sessao: dict) -> None:
    await checar_dono_candidato(id_candidato, sessao)


async def _curriculo_do_dono(id_curriculo: str, sessao: dict) -> dict:
    curriculo = await fetch_one(
        "SELECT * FROM Curriculos WHERE ID_Curriculos=%s AND Ativo=1", (id_curriculo,)
    )
    if not curriculo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Currículo não encontrado.")
    await _checar_dono_candidato(curriculo["ID_Candidatos"], sessao)
    return curriculo


def _caminho_curriculo(curriculo: dict) -> Path:
    nome = Path(curriculo["ArquivoUrl"]).name
    if not re.fullmatch(r"[a-f0-9]{64}\.(pdf|doc|docx)", nome):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Referência de arquivo inválida.")
    caminho = Path(settings.UPLOAD_DIR) / "curriculos" / nome
    if not caminho.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arquivo físico do currículo não encontrado.")
    return caminho


def _json_importacao(valor) -> dict | None:
    if valor is None:
        return None
    if isinstance(valor, dict):
        return valor
    if isinstance(valor, (bytes, bytearray)):
        valor = valor.decode("utf-8")
    if isinstance(valor, str):
        return json.loads(valor)
    return dict(valor)


async def _processar_importacao(curriculo: dict) -> dict:
    extensao = Path(curriculo["ArquivoUrl"]).suffix.lower()
    id_curriculo = curriculo["ID_Curriculos"]

    existente = await fetch_one(
        """SELECT * FROM Curriculo_Importacoes
           WHERE ID_Curriculos=%s AND ID_Status_Processamento_IA=3""",
        (id_curriculo,),
    )
    if existente and existente.get("DadosExtraidos"):
        existente["DadosExtraidos"] = _json_importacao(existente["DadosExtraidos"])
        return existente

    id_importacao = existente["ID_Curriculo_Importacoes"] if existente else novo_uuid()
    await execute(
        """INSERT INTO Curriculo_Importacoes
           (ID_Curriculo_Importacoes, ID_Curriculos, ID_Status_Processamento_IA, ProcessamentoIniciadoEm)
           VALUES (%s,%s,%s,NOW())
           ON DUPLICATE KEY UPDATE
             ID_Status_Processamento_IA=VALUES(ID_Status_Processamento_IA),
             ProcessamentoIniciadoEm=NOW(), ProcessadoEm=NULL,
             ErroProcessamento=NULL, DadosExtraidos=NULL""",
        (id_importacao, id_curriculo, _STATUS_PROCESSANDO),
    )

    if extensao == ".doc":
        mensagem = "O currículo .doc foi salvo, mas a importação automática aceita PDF ou DOCX."
        await execute(
            """UPDATE Curriculo_Importacoes
               SET ID_Status_Processamento_IA=%s, ErroProcessamento=%s, ProcessadoEm=NOW()
               WHERE ID_Curriculos=%s""",
            (_STATUS_FALHOU, mensagem, id_curriculo),
        )
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, mensagem)

    try:
        caminho = _caminho_curriculo(curriculo)
        habilidades = await fetch_all("SELECT Nome FROM Habilidades WHERE Ativo=1 ORDER BY Nome")
        idiomas = await fetch_all("SELECT Nome FROM Idiomas ORDER BY Nome")

        texto = await asyncio.to_thread(extrair_texto_curriculo, caminho)
        dados = await asyncio.to_thread(
            analisar_curriculo,
            texto,
            [item["Nome"] for item in habilidades],
            [item["Nome"] for item in idiomas],
        )
        dados_json = json.dumps(dados, ensure_ascii=False)
        await execute(
            """UPDATE Curriculo_Importacoes
               SET ID_Status_Processamento_IA=%s, DadosExtraidos=%s, TextoCaracteres=%s,
                   ErroProcessamento=NULL, ProcessadoEm=NOW()
               WHERE ID_Curriculos=%s""",
            (_STATUS_CONCLUIDO, dados_json, len(texto), id_curriculo),
        )
    except HTTPException:
        raise
    except Exception as exc:
        mensagem = str(exc)[:500] or "Falha ao interpretar o currículo."
        await execute(
            """UPDATE Curriculo_Importacoes
               SET ID_Status_Processamento_IA=%s, ErroProcessamento=%s, ProcessadoEm=NOW()
               WHERE ID_Curriculos=%s""",
            (_STATUS_FALHOU, mensagem, id_curriculo),
        )
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, mensagem) from exc

    resultado = await fetch_one(
        "SELECT * FROM Curriculo_Importacoes WHERE ID_Curriculos=%s", (id_curriculo,)
    )
    resultado["DadosExtraidos"] = _json_importacao(resultado["DadosExtraidos"])
    return resultado


# ==================== CURRÍCULOS (arquivo) ====================

@router.post("/candidatos/{id_candidato}/curriculos", status_code=201, tags=["Currículos"])
async def enviar_curriculo(
    id_candidato: str,
    titulo: str = Form(..., min_length=1, max_length=150),
    principal: bool = Form(False),
    analisar: bool = Form(True),
    arquivo: UploadFile = File(...),
    sessao: dict = Depends(usuario_atual),
):
    await _checar_dono_candidato(id_candidato, sessao)
    info = await salvar_arquivo(arquivo, "curriculos")

    # Evita duplicar o mesmo documento para o mesmo candidato.
    existente = await fetch_one(
        """SELECT * FROM Curriculos
           WHERE ID_Candidatos=%s AND ArquivoHash=%s AND Ativo=1 LIMIT 1""",
        (id_candidato, info["hash"]),
    )
    if existente:
        curriculo = existente
    else:
        if principal:
            await execute("UPDATE Curriculos SET Principal=0 WHERE ID_Candidatos=%s", (id_candidato,))

        id_curriculo = novo_uuid()
        await execute(
            """INSERT INTO Curriculos
               (ID_Curriculos, ID_Candidatos, Titulo, ArquivoUrl, ArquivoTamanhoBytes,
                ArquivoTipoMime, ArquivoHash, Principal)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                id_curriculo, id_candidato, titulo, info["url"], info["tamanho_bytes"],
                info["tipo_mime"], info["hash"], principal,
            ),
        )
        curriculo = await fetch_one(
            "SELECT * FROM Curriculos WHERE ID_Curriculos=%s", (id_curriculo,)
        )

    resposta = dict(curriculo)
    if analisar and Path(curriculo["ArquivoUrl"]).suffix.lower() in {".pdf", ".docx"}:
        try:
            resposta["importacao"] = await _processar_importacao(curriculo)
        except HTTPException as exc:
            resposta["importacao"] = {
                "ID_Status_Processamento_IA": _STATUS_FALHOU,
                "ErroProcessamento": exc.detail,
            }
    return resposta


@router.get("/candidatos/{id_candidato}/curriculos", tags=["Currículos"])
async def listar_curriculos(id_candidato: str, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_candidato(id_candidato, sessao)
    return await fetch_all(
        """SELECT c.*, ci.ID_Status_Processamento_IA AS ImportacaoStatus,
                  ci.ErroProcessamento AS ImportacaoErro, ci.AplicadoEm AS ImportacaoAplicadaEm
           FROM Curriculos c
           LEFT JOIN Curriculo_Importacoes ci ON ci.ID_Curriculos=c.ID_Curriculos
           WHERE c.ID_Candidatos=%s AND c.Ativo=1
           ORDER BY c.Principal DESC, c.AtualizadoEm DESC""",
        (id_candidato,),
    )


@router.delete("/curriculos/{id_curriculo}", tags=["Currículos"])
async def excluir_curriculo(id_curriculo: str, sessao: dict = Depends(usuario_atual)):
    curriculo = await fetch_one("SELECT * FROM Curriculos WHERE ID_Curriculos=%s", (id_curriculo,))
    if not curriculo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Currículo não encontrado.")
    await _checar_dono_candidato(curriculo["ID_Candidatos"], sessao)
    await execute(
        "UPDATE Curriculos SET Ativo=0, DeletadoEm=NOW() WHERE ID_Curriculos=%s", (id_curriculo,)
    )
    return {"mensagem": "Currículo removido (soft delete)."}


@router.post("/curriculos/{id_curriculo}/analisar", tags=["Currículos"])
async def analisar_curriculo_enviado(id_curriculo: str, sessao: dict = Depends(usuario_atual)):
    curriculo = await _curriculo_do_dono(id_curriculo, sessao)
    return await _processar_importacao(curriculo)


@router.get("/curriculos/{id_curriculo}/importacao", tags=["Currículos"])
async def obter_importacao_curriculo(id_curriculo: str, sessao: dict = Depends(usuario_atual)):
    await _curriculo_do_dono(id_curriculo, sessao)
    importacao = await fetch_one(
        "SELECT * FROM Curriculo_Importacoes WHERE ID_Curriculos=%s", (id_curriculo,)
    )
    if not importacao:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este currículo ainda não foi analisado.")
    importacao["DadosExtraidos"] = _json_importacao(importacao.get("DadosExtraidos"))
    return importacao


class CurriculoImportacaoAplicar(BaseModel):
    importar_perfil: bool = True
    importar_experiencias: bool = True
    importar_formacoes: bool = True
    importar_habilidades: bool = True
    importar_idiomas: bool = True
    sobrescrever_perfil: bool = False


@router.post("/curriculos/{id_curriculo}/importacao/aplicar", tags=["Currículos"])
async def aplicar_importacao_curriculo(
    id_curriculo: str,
    opcoes: CurriculoImportacaoAplicar,
    sessao: dict = Depends(usuario_atual),
):
    curriculo = await _curriculo_do_dono(id_curriculo, sessao)
    id_candidato = curriculo["ID_Candidatos"]
    importacao = await fetch_one(
        """SELECT * FROM Curriculo_Importacoes
           WHERE ID_Curriculos=%s AND ID_Status_Processamento_IA=%s""",
        (id_curriculo, _STATUS_CONCLUIDO),
    )
    if not importacao or not importacao.get("DadosExtraidos"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Analise o currículo com sucesso antes de importar os dados.",
        )

    dados = _json_importacao(importacao["DadosExtraidos"]) or {}
    contadores = {"perfil": 0, "experiencias": 0, "formacoes": 0, "habilidades": 0, "idiomas": 0}

    if opcoes.importar_perfil:
        perfil = dados.get("perfil") or {}
        atual = await fetch_one("SELECT * FROM Candidatos WHERE ID_Candidatos=%s", (id_candidato,))
        mapa = {
            "titulo_profissional": "TituloProfissional",
            "resumo": "Resumo",
            "cidade": "Cidade",
            "estado": "Estado",
            "linkedin_url": "LinkedinUrl",
            "github_url": "GithubUrl",
            "portfolio_url": "PortfolioUrl",
            "experiencia_anos": "ExperienciaAnos",
        }
        alteracoes = []
        valores = []
        for chave, coluna in mapa.items():
            valor = perfil.get(chave)
            if valor in (None, ""):
                continue
            if opcoes.sobrescrever_perfil or atual.get(coluna) in (None, ""):
                alteracoes.append(f"{coluna}=%s")
                valores.append(valor)
        if alteracoes:
            valores.append(id_candidato)
            await execute(
                f"UPDATE Candidatos SET {', '.join(alteracoes)} WHERE ID_Candidatos=%s",
                tuple(valores),
            )
            contadores["perfil"] = len(alteracoes)

    if opcoes.importar_experiencias:
        for exp in dados.get("experiencias") or []:
            if not exp.get("empresa") or not exp.get("cargo") or not exp.get("data_inicio"):
                continue
            duplicada = await fetch_one(
                """SELECT ID_Experiencias FROM Experiencias
                   WHERE ID_Candidatos=%s AND Empresa=%s AND Cargo=%s AND DataInicio=%s LIMIT 1""",
                (id_candidato, exp["empresa"], exp["cargo"], exp["data_inicio"]),
            )
            if duplicada:
                continue
            await execute(
                """INSERT INTO Experiencias
                   (ID_Experiencias, ID_Candidatos, Empresa, Cargo, Descricao, DataInicio, DataFim, Atual)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    novo_uuid(), id_candidato, exp["empresa"][:150], exp["cargo"][:150],
                    (exp.get("descricao") or None), exp["data_inicio"], exp.get("data_fim"),
                    bool(exp.get("atual")),
                ),
            )
            contadores["experiencias"] += 1

    if opcoes.importar_formacoes:
        for formacao in dados.get("formacoes") or []:
            if not formacao.get("instituicao") or not formacao.get("curso"):
                continue
            duplicada = await fetch_one(
                """SELECT ID_Formacoes FROM Formacoes
                   WHERE ID_Candidatos=%s AND Instituicao=%s AND Curso=%s LIMIT 1""",
                (id_candidato, formacao["instituicao"], formacao["curso"]),
            )
            if duplicada:
                continue
            await execute(
                """INSERT INTO Formacoes
                   (ID_Formacoes, ID_Candidatos, Instituicao, Curso, Nivel, DataInicio, DataConclusao, Status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    novo_uuid(), id_candidato, formacao["instituicao"][:200], formacao["curso"][:200],
                    (formacao.get("nivel") or None), formacao.get("data_inicio"),
                    formacao.get("data_conclusao"), formacao.get("status"),
                ),
            )
            contadores["formacoes"] += 1

    if opcoes.importar_habilidades:
        for item in dados.get("habilidades") or []:
            nome = (item.get("nome") or "").strip()
            if not nome:
                continue
            habilidade = await fetch_one(
                "SELECT * FROM Habilidades WHERE LOWER(Nome)=LOWER(%s) AND Ativo=1 LIMIT 1", (nome,)
            )
            if not habilidade:
                id_habilidade = novo_uuid()
                await execute(
                    "INSERT INTO Habilidades (ID_Habilidades, Nome, Categoria) VALUES (%s,%s,%s)",
                    (id_habilidade, nome[:100], "Importado do currículo"),
                )
            else:
                id_habilidade = habilidade["ID_Habilidades"]

            existente = await fetch_one(
                """SELECT ID_Candidato_Habilidades FROM Candidato_Habilidades
                   WHERE ID_Candidatos=%s AND ID_Habilidades=%s""",
                (id_candidato, id_habilidade),
            )
            if existente:
                continue
            await execute(
                """INSERT INTO Candidato_Habilidades
                   (ID_Candidato_Habilidades, ID_Candidatos, ID_Habilidades, Nivel)
                   VALUES (%s,%s,%s,%s)""",
                (novo_uuid(), id_candidato, id_habilidade, item.get("nivel")),
            )
            contadores["habilidades"] += 1

    if opcoes.importar_idiomas:
        for item in dados.get("idiomas") or []:
            nome = (item.get("idioma") or "").strip()
            if not nome:
                continue
            idioma = await fetch_one(
                "SELECT * FROM Idiomas WHERE LOWER(Nome)=LOWER(%s) LIMIT 1", (nome,)
            )
            if not idioma:
                id_idioma = novo_uuid()
                await execute(
                    "INSERT INTO Idiomas (ID_Idiomas, Nome) VALUES (%s,%s)",
                    (id_idioma, nome[:100]),
                )
            else:
                id_idioma = idioma["ID_Idiomas"]

            existente = await fetch_one(
                """SELECT ID_Candidato_Idiomas FROM Candidato_Idiomas
                   WHERE ID_Candidatos=%s AND ID_Idiomas=%s""",
                (id_candidato, id_idioma),
            )
            if existente:
                continue
            await execute(
                """INSERT INTO Candidato_Idiomas
                   (ID_Candidato_Idiomas, ID_Candidatos, ID_Idiomas, Nivel)
                   VALUES (%s,%s,%s,%s)""",
                (novo_uuid(), id_candidato, id_idioma, (item.get("nivel") or None)),
            )
            contadores["idiomas"] += 1

    await execute(
        "UPDATE Curriculo_Importacoes SET AplicadoEm=NOW() WHERE ID_Curriculos=%s",
        (id_curriculo,),
    )
    return {
        "mensagem": "Dados do currículo importados para o perfil.",
        "importados": contadores,
    }


# ==================== EXPERIÊNCIAS ====================

class ExperienciaCreate(BaseModel):
    empresa: str = Field(min_length=1, max_length=150)
    cargo: str = Field(min_length=1, max_length=150)
    descricao: str | None = None
    data_inicio: date
    data_fim: date | None = None
    atual: bool = False


@router.post("/candidatos/{id_candidato}/experiencias", status_code=201, tags=["Experiências"])
async def criar_experiencia(id_candidato: str, dados: ExperienciaCreate, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_candidato(id_candidato, sessao)
    id_exp = novo_uuid()
    await execute(
        """INSERT INTO Experiencias (ID_Experiencias, ID_Candidatos, Empresa, Cargo, Descricao, DataInicio, DataFim, Atual)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (id_exp, id_candidato, dados.empresa, dados.cargo, dados.descricao,
         dados.data_inicio, dados.data_fim, dados.atual),
    )
    return await fetch_one("SELECT * FROM Experiencias WHERE ID_Experiencias=%s", (id_exp,))


@router.get("/candidatos/{id_candidato}/experiencias", tags=["Experiências"])
async def listar_experiencias(id_candidato: str, sessao: dict = Depends(usuario_atual)):
    await checar_leitura_candidato(id_candidato, sessao)
    return await fetch_all(
        "SELECT * FROM Experiencias WHERE ID_Candidatos=%s ORDER BY DataInicio DESC", (id_candidato,)
    )


@router.put("/experiencias/{id_experiencia}", tags=["Experiências"])
async def atualizar_experiencia(id_experiencia: str, dados: ExperienciaCreate, sessao: dict = Depends(usuario_atual)):
    experiencia = await fetch_one("SELECT * FROM Experiencias WHERE ID_Experiencias=%s", (id_experiencia,))
    if not experiencia:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Experiência não encontrada.")
    await _checar_dono_candidato(experiencia["ID_Candidatos"], sessao)
    await execute(
        """UPDATE Experiencias SET Empresa=%s, Cargo=%s, Descricao=%s, DataInicio=%s, DataFim=%s, Atual=%s
           WHERE ID_Experiencias=%s""",
        (dados.empresa, dados.cargo, dados.descricao, dados.data_inicio, dados.data_fim,
         dados.atual, id_experiencia),
    )
    return await fetch_one("SELECT * FROM Experiencias WHERE ID_Experiencias=%s", (id_experiencia,))


@router.delete("/experiencias/{id_experiencia}", tags=["Experiências"])
async def excluir_experiencia(id_experiencia: str, sessao: dict = Depends(usuario_atual)):
    experiencia = await fetch_one("SELECT * FROM Experiencias WHERE ID_Experiencias=%s", (id_experiencia,))
    if not experiencia:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Experiência não encontrada.")
    await _checar_dono_candidato(experiencia["ID_Candidatos"], sessao)
    await execute("DELETE FROM Experiencias WHERE ID_Experiencias=%s", (id_experiencia,))
    return {"mensagem": "Experiência excluída."}


# ==================== FORMAÇÕES ====================

class FormacaoCreate(BaseModel):
    instituicao: str = Field(min_length=1, max_length=200)
    curso: str = Field(min_length=1, max_length=200)
    nivel: str | None = Field(default=None, max_length=50)
    data_inicio: date | None = None
    data_conclusao: date | None = None
    status_formacao: str | None = Field(default=None, max_length=50)


@router.post("/candidatos/{id_candidato}/formacoes", status_code=201, tags=["Formações"])
async def criar_formacao(id_candidato: str, dados: FormacaoCreate, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_candidato(id_candidato, sessao)
    id_form = novo_uuid()
    await execute(
        """INSERT INTO Formacoes (ID_Formacoes, ID_Candidatos, Instituicao, Curso, Nivel, DataInicio, DataConclusao, Status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (id_form, id_candidato, dados.instituicao, dados.curso, dados.nivel,
         dados.data_inicio, dados.data_conclusao, dados.status_formacao),
    )
    return await fetch_one("SELECT * FROM Formacoes WHERE ID_Formacoes=%s", (id_form,))


@router.get("/candidatos/{id_candidato}/formacoes", tags=["Formações"])
async def listar_formacoes(id_candidato: str, sessao: dict = Depends(usuario_atual)):
    await checar_leitura_candidato(id_candidato, sessao)
    return await fetch_all(
        "SELECT * FROM Formacoes WHERE ID_Candidatos=%s ORDER BY DataInicio DESC", (id_candidato,)
    )


@router.put("/formacoes/{id_formacao}", tags=["Formações"])
async def atualizar_formacao(id_formacao: str, dados: FormacaoCreate, sessao: dict = Depends(usuario_atual)):
    formacao = await fetch_one("SELECT * FROM Formacoes WHERE ID_Formacoes=%s", (id_formacao,))
    if not formacao:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Formação não encontrada.")
    await _checar_dono_candidato(formacao["ID_Candidatos"], sessao)
    await execute(
        """UPDATE Formacoes SET Instituicao=%s, Curso=%s, Nivel=%s, DataInicio=%s, DataConclusao=%s, Status=%s
           WHERE ID_Formacoes=%s""",
        (dados.instituicao, dados.curso, dados.nivel, dados.data_inicio,
         dados.data_conclusao, dados.status_formacao, id_formacao),
    )
    return await fetch_one("SELECT * FROM Formacoes WHERE ID_Formacoes=%s", (id_formacao,))


@router.delete("/formacoes/{id_formacao}", tags=["Formações"])
async def excluir_formacao(id_formacao: str, sessao: dict = Depends(usuario_atual)):
    formacao = await fetch_one("SELECT * FROM Formacoes WHERE ID_Formacoes=%s", (id_formacao,))
    if not formacao:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Formação não encontrada.")
    await _checar_dono_candidato(formacao["ID_Candidatos"], sessao)
    await execute("DELETE FROM Formacoes WHERE ID_Formacoes=%s", (id_formacao,))
    return {"mensagem": "Formação excluída."}
