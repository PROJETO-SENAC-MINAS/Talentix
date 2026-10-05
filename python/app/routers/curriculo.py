"""
CRUD de Currículos, importação inteligente, Experiências e Formações.
"""
from app.core.routes import AtomicRouter as APIRouter

import asyncio
import json
import re
import sys
import os
from datetime import date
from pathlib import Path
from io import BytesIO
from copy import deepcopy
from typing import Literal

from fastapi import Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel, Field, model_validator, ConfigDict, ValidationError

from app.db.database import fetch_one, fetch_all, execute
from app.core.security import novo_uuid
from app.core.deps import usuario_atual
from app.core.access import checar_leitura_candidato, checar_dono_candidato
from app.core.upload import salvar_arquivo
from app.core.config import settings
from app.core.resume_parser import extrair_texto_curriculo, analisar_curriculo
from app.routers.perfis import CandidatoUpdate
from app.routers.profissional import ItemProfissional

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


async def _curriculo_do_dono(id_curriculo: str, sessao: dict, bloquear: bool = False) -> dict:
    curriculo = await fetch_one(
        "SELECT * FROM Curriculos WHERE ID_Curriculos=%s AND Ativo=1", (id_curriculo,)
    )
    if not curriculo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Currículo não encontrado.")
    await _checar_dono_candidato(curriculo["ID_Candidatos"], sessao)
    if bloquear:
        # Ordem consistente candidato → currículo: upload, principal, importação
        # e remoção não podem competir produzindo duplicatas ou editar versão removida.
        parent = await fetch_one("SELECT ID_Candidatos FROM Candidatos WHERE ID_Candidatos=%s AND Ativo=1 FOR UPDATE", (curriculo["ID_Candidatos"],))
        curriculo = await fetch_one("SELECT * FROM Curriculos WHERE ID_Curriculos=%s AND Ativo=1 FOR UPDATE", (id_curriculo,))
        if not parent or not curriculo:
            raise HTTPException(404, "Currículo não encontrado.")
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


def _dados_revisao(importacao: dict) -> dict | None:
    """A prévia e a confirmação usam a mesma separação, sem mudar o original."""
    dados = deepcopy(_json_importacao(importacao.get("DadosExtraidos")))
    if not dados:
        return dados
    if dados.get("versao") == 1 and importacao.get("TextoExtraido"):
        # Recupera a separação de documentos já analisados pelo parser antigo.
        novos = analisar_curriculo(importacao["TextoExtraido"])
        for secao in ("formacoes", "certificados", "projetos"):
            dados[secao] = novos[secao]
    else:
        formacoes = dados.get("formacoes") or []
        dados["certificados"] = (dados.get("certificados") or []) + [f for f in formacoes if f.get("nivel") == "Certificado"]
        dados["formacoes"] = [f for f in formacoes if f.get("nivel") != "Certificado"]
        dados.setdefault("projetos", [])
    dados["versao"] = 2
    return dados


async def _processar_importacao(curriculo: dict) -> dict:
    extensao = Path(curriculo["ArquivoUrl"]).suffix.lower()
    id_curriculo = curriculo["ID_Curriculos"]

    # Executado somente pelo worker após claim durável; nunca pela requisição HTTP.
    lease = curriculo["ProcessamentoIniciadoEm"]

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

        process = await asyncio.create_subprocess_exec(sys.executable, "-m", "app.core.resume_extract", str(caminho.resolve()),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            env={**{key: os.environ[key] for key in ("PATH", "PYTHONPATH", "SYSTEMROOT", "WINDIR", "LD_LIBRARY_PATH") if key in os.environ}, "PYTHONIOENCODING": "utf-8"})
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=45)
            if process.returncode != 0:
                raise ValueError("Documento ilegível.")
            texto = json.loads(stdout)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        dados = await asyncio.to_thread(
            analisar_curriculo,
            texto,
            [item["Nome"] for item in habilidades],
            [item["Nome"] for item in idiomas],
        )
        dados_json = json.dumps(dados, ensure_ascii=False)
        await execute(
            """UPDATE Curriculo_Importacoes
               SET ID_Status_Processamento_IA=%s, DadosExtraidos=%s, TextoCaracteres=%s, TextoExtraido=%s,
                   ErroProcessamento=NULL, ProcessadoEm=NOW()
               WHERE ID_Curriculos=%s AND ID_Status_Processamento_IA=2 AND ProcessamentoIniciadoEm=%s""",
            (_STATUS_CONCLUIDO, dados_json, len(texto), texto, id_curriculo, lease),
        )
    except Exception as exc:
        mensagem = "Não foi possível ler este documento. Envie um PDF com texto selecionável, sem senha, ou DOCX válido."
        await execute(
            """UPDATE Curriculo_Importacoes
               SET ID_Status_Processamento_IA=%s, ErroProcessamento=%s, ProcessadoEm=NOW()
               WHERE ID_Curriculos=%s AND ID_Status_Processamento_IA=2 AND ProcessamentoIniciadoEm=%s""",
            (_STATUS_FALHOU, mensagem, id_curriculo, lease),
        )
        return {"ID_Status_Processamento_IA": 4, "ErroProcessamento": mensagem}

    resultado = await fetch_one(
        "SELECT * FROM Curriculo_Importacoes WHERE ID_Curriculos=%s", (id_curriculo,)
    )
    resultado["DadosExtraidos"] = _json_importacao(resultado["DadosExtraidos"])
    return resultado


async def _enfileirar(curriculo):
    if Path(curriculo["ArquivoUrl"]).suffix.lower() not in {".pdf", ".docx"}:
        raise HTTPException(422, "A análise aceita somente PDF com texto ou DOCX. O original permanece salvo.")
    existente = await fetch_one("SELECT * FROM Curriculo_Importacoes WHERE ID_Curriculos=%s", (curriculo["ID_Curriculos"],))
    if existente and existente["ID_Status_Processamento_IA"] in (1, 2, 3):
        existente["DadosExtraidos"] = _dados_revisao(existente)
        return existente
    if existente:
        await execute("UPDATE Curriculo_Importacoes SET ID_Status_Processamento_IA=1,ErroProcessamento=NULL WHERE ID_Curriculos=%s", (curriculo["ID_Curriculos"],))
    else:
        await execute("INSERT INTO Curriculo_Importacoes(ID_Curriculo_Importacoes,ID_Curriculos) VALUES (%s,%s)", (novo_uuid(), curriculo["ID_Curriculos"]))
    return {"ID_Status_Processamento_IA": 1, "mensagem": "Aguardando análise. Nenhum dado foi aplicado ao perfil."}


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
    await fetch_one("SELECT ID_Candidatos FROM Candidatos WHERE ID_Candidatos=%s FOR UPDATE", (id_candidato,))
    if not await fetch_one("SELECT ID_Curriculos FROM Curriculos WHERE ID_Candidatos=%s AND Ativo=1 AND Principal=1 LIMIT 1", (id_candidato,)):
        principal = True
    info = await salvar_arquivo(arquivo, "curriculos")

    # Evita duplicar o mesmo documento para o mesmo candidato.
    existente = await fetch_one(
        """SELECT * FROM Curriculos
           WHERE ID_Candidatos=%s AND ArquivoHash=%s AND Ativo=1 LIMIT 1""",
        (id_candidato, info["hash"]),
    )
    if existente:
        curriculo = existente
        if principal:
            await execute("UPDATE Curriculos SET Principal=0 WHERE ID_Candidatos=%s", (id_candidato,))
            await execute("UPDATE Curriculos SET Principal=1 WHERE ID_Curriculos=%s", (curriculo["ID_Curriculos"],))
            curriculo["Principal"] = True
    else:
        if principal:
            await execute("UPDATE Curriculos SET Principal=0 WHERE ID_Candidatos=%s", (id_candidato,))

        id_curriculo = novo_uuid()
        versao = await fetch_one("SELECT COALESCE(MAX(Versao),0)+1 AS proxima FROM Curriculos WHERE ID_Candidatos=%s", (id_candidato,))
        await execute(
            """INSERT INTO Curriculos
               (ID_Curriculos, ID_Candidatos, Titulo, ArquivoUrl, ArquivoTamanhoBytes,
                ArquivoTipoMime, ArquivoHash, Principal, Versao)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                id_curriculo, id_candidato, titulo, info["url"], info["tamanho_bytes"],
                info["tipo_mime"], info["hash"], principal, versao["proxima"],
            ),
        )
        curriculo = await fetch_one(
            "SELECT * FROM Curriculos WHERE ID_Curriculos=%s", (id_curriculo,)
        )

    resposta = dict(curriculo)
    if analisar and Path(curriculo["ArquivoUrl"]).suffix.lower() in {".pdf", ".docx"}:
        resposta["importacao"] = await _enfileirar(curriculo)
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
           ORDER BY c.Principal DESC, c.Versao DESC""",
        (id_candidato,),
    )


@router.delete("/curriculos/{id_curriculo}", tags=["Currículos"])
async def excluir_curriculo(id_curriculo: str, sessao: dict = Depends(usuario_atual)):
    cv = await _curriculo_do_dono(id_curriculo, sessao, bloquear=True)
    await execute(
        "UPDATE Curriculos SET Ativo=0, Principal=0, DeletadoEm=NOW() WHERE ID_Curriculos=%s", (id_curriculo,)
    )
    if cv["Principal"]:
        restante = await fetch_one("SELECT ID_Curriculos FROM Curriculos WHERE ID_Candidatos=%s AND Ativo=1 ORDER BY Versao DESC, ID_Curriculos LIMIT 1", (cv["ID_Candidatos"],))
        if restante:
            await execute("UPDATE Curriculos SET Principal=1 WHERE ID_Curriculos=%s", (restante["ID_Curriculos"],))
    return {"mensagem": "Versão arquivada. Candidaturas já enviadas mantêm o documento original."}


@router.get("/candidatos/{id_candidato}/curriculos/historico", tags=["Currículos"])
async def historico_curriculos(id_candidato: str, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_candidato(id_candidato, sessao)
    return await fetch_all(
        """SELECT c.*, (SELECT COUNT(*) FROM Candidaturas ca
             WHERE ca.ID_Candidatos=c.ID_Candidatos AND ca.CurriculoUrl=c.ArquivoUrl AND ca.Ativo=1) AS CandidaturasEnviadas
           FROM Curriculos c WHERE c.ID_Candidatos=%s ORDER BY c.Versao DESC, c.ID_Curriculos""",
        (id_candidato,),
    )


@router.post("/curriculos/{id_curriculo}/analisar", tags=["Currículos"])
async def analisar_curriculo_enviado(id_curriculo: str, sessao: dict = Depends(usuario_atual)):
    curriculo = await _curriculo_do_dono(id_curriculo, sessao, bloquear=True)
    return await _enfileirar(curriculo)


@router.get("/curriculos/{id_curriculo}/importacao", tags=["Currículos"])
async def obter_importacao_curriculo(id_curriculo: str, sessao: dict = Depends(usuario_atual)):
    await _curriculo_do_dono(id_curriculo, sessao)
    importacao = await fetch_one(
        "SELECT * FROM Curriculo_Importacoes WHERE ID_Curriculos=%s", (id_curriculo,)
    )
    if not importacao:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este currículo ainda não foi analisado.")
    importacao["DadosExtraidos"] = _dados_revisao(importacao)
    return importacao


class CurriculoImportacaoAplicar(BaseModel):
    importar_perfil: bool = True
    importar_experiencias: bool = True
    importar_formacoes: bool = True
    importar_certificados: bool = False
    importar_projetos: bool = False
    importar_habilidades: bool = True
    importar_idiomas: bool = True
    sobrescrever_perfil: bool = False
    versao_revisao: Literal[1, 2] = 1
    # Índices escolhidos na prévia, e nomes de campos do perfil. Ausente mantém
    # compatibilidade com clientes anteriores que aprovam explicitamente categorias.
    selecionados: dict[str, list[int | str]] | None = None

    @model_validator(mode="after")
    def selecao(self):
        if self.selecionados is not None:
            if set(self.selecionados) - {"perfil", "experiencias", "formacoes", "certificados", "projetos", "habilidades", "idiomas"} or any(len(v)>50 for v in self.selecionados.values()):
                raise ValueError("Seleção de dados inválida.")
        return self


@router.post("/curriculos/{id_curriculo}/importacao/aplicar", tags=["Currículos"])
async def aplicar_importacao_curriculo(
    id_curriculo: str,
    opcoes: CurriculoImportacaoAplicar,
    sessao: dict = Depends(usuario_atual),
):
    curriculo = await _curriculo_do_dono(id_curriculo, sessao, bloquear=True)
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

    dados = _dados_revisao(importacao) if opcoes.versao_revisao == 2 else deepcopy(_json_importacao(importacao["DadosExtraidos"]))
    if opcoes.versao_revisao == 1 and dados.get("versao") == 2:
        # Clientes anteriores têm um único grupo de formação/certificados.
        dados["formacoes"] = dados.get("formacoes", []) + dados.get("certificados", [])
        dados["certificados"] = []
    if opcoes.selecionados is not None:
        for secao in ("experiencias", "formacoes", "certificados", "projetos", "habilidades", "idiomas"):
            indices = opcoes.selecionados.get(secao, [])
            dados[secao] = [v for i, v in enumerate(dados.get(secao, [])) if i in indices]
        dados["perfil"] = {k: v for k, v in dados.get("perfil", {}).items() if k in opcoes.selecionados.get("perfil", [])}
    contadores = {"perfil": 0, "experiencias": 0, "formacoes": 0, "habilidades": 0, "idiomas": 0}
    if opcoes.versao_revisao == 2 or opcoes.importar_certificados or opcoes.importar_projetos:
        contadores.update(certificados=0, projetos=0)

    if opcoes.importar_perfil:
        try:
            perfil = CandidatoUpdate(**(dados.get("perfil") or {})).model_dump(exclude_unset=True)
        except ValidationError as exc:
            raise HTTPException(422, "Um campo identificado é inválido. Desmarque-o e corrija no perfil.") from exc
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
            try:
                exp = ExperienciaCreate(**exp).model_dump(mode="json")
            except ValidationError as exc:
                raise HTTPException(422, "Revise a experiência identificada ou desmarque-a antes de confirmar.") from exc
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

    for secao, importar in (("formacoes", opcoes.importar_formacoes), ("certificados", opcoes.importar_certificados)):
        if not importar:
            continue
        rotulo = "certificado" if secao == "certificados" else "formação acadêmica"
        for formacao in dados.get(secao) or []:
            if not formacao.get("instituicao") or not formacao.get("curso"):
                raise HTTPException(422, f"Revise instituição e curso do item de {rotulo}, ou desmarque-o antes de confirmar.")
            formacao_normalizada = {**formacao, "status_formacao": formacao.get("status")}
            if secao == "certificados":
                formacao_normalizada["nivel"] = "Certificado"
            inicio = formacao_normalizada.get("data_inicio")
            conclusao = formacao_normalizada.get("data_conclusao")
            # Mantém compatibilidade com análises concluídas antes da correção
            # do parser, que podiam armazenar os anos na ordem em que apareciam.
            if inicio and conclusao and str(conclusao) < str(inicio):
                formacao_normalizada["data_inicio"] = conclusao
                formacao_normalizada["data_conclusao"] = inicio
            try:
                formacao_validada = FormacaoCreate(**formacao_normalizada).model_dump(mode="json")
            except ValidationError as exc:
                titulo = str(formacao.get("curso", ""))[:100]
                campo = str(exc.errors()[0]["loc"][0]) if exc.errors()[0]["loc"] else "datas"
                campo = {"instituicao":"a instituição", "curso":"o nome do curso", "nivel":"o nível", "data_inicio":"a data de início", "data_conclusao":"a data de conclusão", "status_formacao":"a situação"}.get(campo, "as datas")
                raise HTTPException(422, f'Revise {campo} em “{titulo}” ({rotulo}) ou desmarque esse item antes de confirmar.') from exc
            duplicada = await fetch_one(
                """SELECT ID_Formacoes FROM Formacoes
                   WHERE ID_Candidatos=%s AND Instituicao=%s AND Curso=%s
                     AND COALESCE(Nivel, '')=%s LIMIT 1""",
                (id_candidato, formacao_validada["instituicao"], formacao_validada["curso"], formacao_validada.get("nivel") or ""),
            )
            if duplicada:
                continue
            await execute(
                """INSERT INTO Formacoes
                   (ID_Formacoes, ID_Candidatos, Instituicao, Curso, Nivel, DataInicio, DataConclusao, Status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    novo_uuid(), id_candidato, formacao_validada["instituicao"], formacao_validada["curso"],
                    formacao_validada.get("nivel"), formacao_validada.get("data_inicio"),
                    formacao_validada.get("data_conclusao"), formacao_validada.get("status_formacao"),
                ),
            )
            contadores[secao] += 1

    if opcoes.importar_projetos:
        for projeto in dados.get("projetos") or []:
            try:
                item = ItemProfissional(**{**projeto, "tipo": "projeto"}).model_dump(mode="json")
            except ValidationError as exc:
                titulo = str(projeto.get("titulo", "Projeto"))[:100]
                raise HTTPException(422, f'Revise o projeto “{titulo}” ou desmarque esse item antes de confirmar.') from exc
            duplicado = await fetch_one(
                """SELECT ID_Item FROM Candidato_Itens
                   WHERE ID_Candidatos=%s AND Tipo='projeto' AND Titulo=%s
                     AND COALESCE(Url, '')=%s LIMIT 1""",
                (id_candidato, item["titulo"], item.get("url") or ""),
            )
            if duplicado:
                continue
            await execute(
                """INSERT INTO Candidato_Itens
                   (ID_Item, ID_Candidatos, Tipo, Titulo, Instituicao, Descricao, Url, DataInicio, DataFim)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (novo_uuid(), id_candidato, "projeto", item["titulo"], item.get("instituicao"),
                 item.get("descricao"), item.get("url"), item.get("data_inicio"), item.get("data_fim")),
            )
            contadores["projetos"] += 1

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
        "UPDATE Curriculo_Importacoes SET AplicadoEm=NOW(),DadosConfirmados=%s WHERE ID_Curriculos=%s",
        (json.dumps({"selecionados": dados, "opcoes": opcoes.model_dump()}, ensure_ascii=False), id_curriculo),
    )
    return {
        "mensagem": "Dados do currículo importados para o perfil.",
        "importados": contadores,
    }


# ==================== EXPERIÊNCIAS ====================

class ExperienciaCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    empresa: str = Field(min_length=1, max_length=150)
    cargo: str = Field(min_length=1, max_length=150)
    descricao: str | None = Field(None, max_length=5000)
    data_inicio: date
    data_fim: date | None = None
    atual: bool = False

    @model_validator(mode="after")
    def datas(self):
        if self.data_fim and (self.data_fim < self.data_inicio or self.atual):
            raise ValueError("Revise as datas: término anterior ao início ou experiência atual com término.")
        return self


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
    model_config = ConfigDict(str_strip_whitespace=True)
    instituicao: str = Field(min_length=1, max_length=200)
    curso: str = Field(min_length=1, max_length=200)
    nivel: str | None = Field(default=None, max_length=50)
    data_inicio: date | None = None
    data_conclusao: date | None = None
    status_formacao: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def datas(self):
        if self.data_inicio and self.data_conclusao and self.data_conclusao < self.data_inicio:
            raise ValueError("A conclusão não pode anteceder o início.")
        return self


class CurriculoEdicao(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    titulo: str = Field(min_length=1, max_length=150)
    principal: bool = False


@router.put("/curriculos/{id_curriculo}", tags=["Currículos"])
async def editar_curriculo(id_curriculo: str, dados: CurriculoEdicao, sessao=Depends(usuario_atual)):
    cv = await _curriculo_do_dono(id_curriculo, sessao, bloquear=True)
    if dados.principal:
        await execute("UPDATE Curriculos SET Principal=0 WHERE ID_Candidatos=%s", (cv["ID_Candidatos"],))
    await execute("UPDATE Curriculos SET Titulo=%s,Principal=%s WHERE ID_Curriculos=%s", (dados.titulo, dados.principal, id_curriculo))
    return await fetch_one("SELECT * FROM Curriculos WHERE ID_Curriculos=%s", (id_curriculo,))


@router.post("/candidatos/{id_candidato}/curriculo-talentix", status_code=201, tags=["Currículos"])
async def gerar_curriculo(id_candidato: str, sessao=Depends(usuario_atual)):
    from app.routers.profissional import perfil_completo
    from app.core.resume_pdf import gerar_pdf
    from starlette.datastructures import UploadFile as StarletteUploadFile
    await _checar_dono_candidato(id_candidato, sessao)
    dados = await perfil_completo(id_candidato)
    contato = await fetch_one("SELECT Nome,Email,Telefone FROM Usuarios WHERE ID_Usuarios=%s", (dados["perfil"]["ID_Usuarios"],))
    pdf = await asyncio.to_thread(gerar_pdf, dados, contato)
    result = await enviar_curriculo(id_candidato, titulo="Currículo Talentix", principal=False, analisar=False,
        arquivo=StarletteUploadFile(BytesIO(pdf), filename="talentix.pdf"), sessao=sessao)
    await execute("UPDATE Curriculos SET Origem='talentix' WHERE ID_Curriculos=%s", (result["ID_Curriculos"],))
    result["Origem"] = "talentix"
    return result


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
