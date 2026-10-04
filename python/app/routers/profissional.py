"""Perfil profissional: leitura contextual, completude e coleções editáveis."""
import json
from datetime import date
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, model_validator, ConfigDict
from app.core.routes import AtomicRouter
from app.core.access import checar_dono_candidato, checar_leitura_candidato
from app.core.deps import usuario_atual
from app.core.security import novo_uuid
from app.core.validation import safe_url
from app.db.database import execute, fetch_all, fetch_one

router = AtomicRouter(tags=["Perfil profissional"])


async def garantir_schema():
    await fetch_one("SELECT Modalidades,TiposContrato,HabilidadesComportamentais,Preferencias FROM Candidatos LIMIT 0")
    await fetch_one("SELECT Versao,Origem FROM Curriculos LIMIT 0")
    await fetch_one("SELECT TextoExtraido,DadosConfirmados FROM Curriculo_Importacoes LIMIT 0")
    for table in ("Candidato_Itens", "Buscas_Salvas", "Historico_Buscas", "Alertas_Busca"):
        await fetch_one(f"SELECT * FROM {table} LIMIT 0")


def decode_list(value):
    return json.loads(value) if isinstance(value, (str, bytes)) else (value or [])


class ItemProfissional(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    tipo: Literal["projeto", "curso"]
    titulo: str = Field(min_length=1, max_length=200)
    instituicao: str | None = Field(None, max_length=200)
    descricao: str | None = Field(None, max_length=5000)
    url: str | None = Field(None, max_length=300)
    data_inicio: date | None = None
    data_fim: date | None = None

    @model_validator(mode="after")
    def validar(self):
        self.url = safe_url(self.url)
        if self.data_inicio and self.data_fim and self.data_fim < self.data_inicio:
            raise ValueError("A data final não pode anteceder o início.")
        return self


async def perfil_completo(candidate_id):
    perfil = await fetch_one("""SELECT c.*, u.Nome, u.FotoUrl FROM Candidatos c
        JOIN Usuarios u ON u.ID_Usuarios=c.ID_Usuarios AND u.Ativo=1
        WHERE c.ID_Candidatos=%s AND c.Ativo=1""", (candidate_id,))
    if not perfil:
        raise HTTPException(404, "Perfil não encontrado.")
    for key in ("Modalidades", "TiposContrato", "HabilidadesComportamentais"):
        perfil[key] = decode_list(perfil.get(key))
    colecoes = {
        "experiencias": await fetch_all("SELECT * FROM Experiencias WHERE ID_Candidatos=%s ORDER BY DataInicio DESC", (candidate_id,)),
        "formacoes": await fetch_all("SELECT * FROM Formacoes WHERE ID_Candidatos=%s ORDER BY DataInicio DESC", (candidate_id,)),
        "habilidades": await fetch_all("""SELECT ch.*, h.Nome FROM Candidato_Habilidades ch
            JOIN Habilidades h ON h.ID_Habilidades=ch.ID_Habilidades AND h.Ativo=1 WHERE ch.ID_Candidatos=%s""", (candidate_id,)),
        "idiomas": await fetch_all("""SELECT ci.*, i.Nome FROM Candidato_Idiomas ci
            JOIN Idiomas i ON i.ID_Idiomas=ci.ID_Idiomas WHERE ci.ID_Candidatos=%s""", (candidate_id,)),
        "itens": await fetch_all("SELECT * FROM Candidato_Itens WHERE ID_Candidatos=%s ORDER BY CriadoEm DESC, ID_Item", (candidate_id,)),
    }
    # Pesos somam 100; disponibilidade falsa e salário zero são respostas válidas.
    criterios = [
        ("Foto de perfil", 5, perfil.get("FotoUrl")), ("Headline profissional", 10, perfil.get("TituloProfissional")),
        ("Apresentação pessoal", 10, perfil.get("Resumo")), ("Cidade e estado", 5, perfil.get("Cidade") and perfil.get("Estado")),
        ("Disponibilidade", 2, perfil.get("Disponivel") is not None), ("Modalidade desejada", 5, perfil["Modalidades"]),
        ("Pretensão salarial", 5, perfil.get("PretensaoSalarial") is not None), ("Tipos de contrato", 5, perfil["TiposContrato"]),
        ("Experiência profissional", 10, colecoes["experiencias"]),
        ("Formação acadêmica", 10, [f for f in colecoes["formacoes"] if f.get("Nivel") != "Certificado"]),
        ("Certificado", 3, [f for f in colecoes["formacoes"] if f.get("Nivel") == "Certificado"]),
        ("Curso", 3, [i for i in colecoes["itens"] if i["Tipo"] == "curso"]),
        ("Projeto", 5, [i for i in colecoes["itens"] if i["Tipo"] == "projeto"]),
        ("Habilidade técnica", 5, colecoes["habilidades"]), ("Habilidade comportamental", 3, perfil["HabilidadesComportamentais"]),
        ("Idioma", 3, colecoes["idiomas"]), ("GitHub", 5, perfil.get("GithubUrl")),
        ("LinkedIn", 2, perfil.get("LinkedinUrl")), ("Portfólio", 2, perfil.get("PortfolioUrl")),
        ("Preferências profissionais", 2, perfil.get("Preferencias")),
    ]
    def preenchido(value):
        return bool(value.strip()) if isinstance(value, str) else bool(value)
    return {"perfil": perfil, **colecoes, "completude": sum(p for _, p, ok in criterios if preenchido(ok)),
            "faltantes": [{"campo": nome, "peso": peso} for nome, peso, ok in criterios if not preenchido(ok)]}


@router.get("/candidatos/{id_candidato}/profissional")
async def obter_profissional(id_candidato: str, sessao=Depends(usuario_atual)):
    await checar_leitura_candidato(id_candidato, sessao)
    return await perfil_completo(id_candidato)


@router.post("/candidatos/{id_candidato}/itens", status_code=201)
async def adicionar_item(id_candidato: str, dados: ItemProfissional, sessao=Depends(usuario_atual)):
    await checar_dono_candidato(id_candidato, sessao)
    item = novo_uuid()
    await execute("""INSERT INTO Candidato_Itens
        (ID_Item, ID_Candidatos, Tipo, Titulo, Instituicao, Descricao, Url, DataInicio, DataFim)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (item, id_candidato, dados.tipo, dados.titulo, dados.instituicao, dados.descricao, dados.url, dados.data_inicio, dados.data_fim))
    return await fetch_one("SELECT * FROM Candidato_Itens WHERE ID_Item=%s", (item,))


@router.put("/itens-profissionais/{id_item}")
async def editar_item(id_item: str, dados: ItemProfissional, sessao=Depends(usuario_atual)):
    item = await fetch_one("SELECT * FROM Candidato_Itens WHERE ID_Item=%s", (id_item,))
    if not item:
        raise HTTPException(404, "Item não encontrado.")
    await checar_dono_candidato(item["ID_Candidatos"], sessao)
    await execute("""UPDATE Candidato_Itens SET Tipo=%s,Titulo=%s,Instituicao=%s,Descricao=%s,Url=%s,DataInicio=%s,DataFim=%s WHERE ID_Item=%s""",
        (dados.tipo, dados.titulo, dados.instituicao, dados.descricao, dados.url, dados.data_inicio, dados.data_fim, id_item))
    return await fetch_one("SELECT * FROM Candidato_Itens WHERE ID_Item=%s", (id_item,))


@router.delete("/itens-profissionais/{id_item}")
async def remover_item(id_item: str, sessao=Depends(usuario_atual)):
    item = await fetch_one("SELECT * FROM Candidato_Itens WHERE ID_Item=%s", (id_item,))
    if not item:
        raise HTTPException(404, "Item não encontrado.")
    await checar_dono_candidato(item["ID_Candidatos"], sessao)
    await execute("DELETE FROM Candidato_Itens WHERE ID_Item=%s", (id_item,))
    return {"mensagem": "Item removido."}
