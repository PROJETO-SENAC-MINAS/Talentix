"""Orientação local e informativa, com fatores observáveis e versão explícita."""

import asyncio
import json
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from app.core.routes import AtomicRouter
from app.core.deps import usuario_atual
from app.core.access import checar_acesso_analise
from app.core.matching import calculate_match, normalize
from app.core.security import novo_uuid
from app.core.audit import registrar_auditoria
from app.db.database import fetch_one, fetch_all, execute

router = AtomicRouter(prefix="/inteligencia", tags=["IA informativa"])
MODEL = "talentix-local-explicavel-v2"
ALIASES = {
    "js": "javascript",
    "javascript": "javascript",
    "c sharp": "c#",
    "csharp": "c#",
    "postgres": "postgresql",
    "py": "python",
    "nodejs": "node.js",
    "reactjs": "react",
}


def skill_key(v):
    key = normalize(v).strip()
    return ALIASES.get(key, key)


def explicar(profile_text, job_text, skills, required):
    levels = {skill_key(h["Nome"]): h.get("Nivel") or 0 for h in skills}
    details = []
    weight = 0
    matched = 0
    for h in required:
        w = max(float(h.get("Peso") or 1), 1) * (2 if h.get("Obrigatoria") else 1)
        level = h.get("NivelMinimo") or 0
        actual = levels.get(skill_key(h["Nome"]))
        ok = actual is not None and actual >= level
        weight += w
        matched += w if ok else 0
        details.append(
            {
                "habilidade": h["Nome"],
                "obrigatoria": bool(h.get("Obrigatoria")),
                "nivel_minimo": level,
                "nivel_declarado": actual,
                "atendida": ok,
                "peso": w,
            }
        )
    text = calculate_match(profile_text, job_text, [], [])["score_compatibilidade"]
    skill = 100 * matched / weight if weight else None
    score = round(0.8 * skill + 0.2 * text) if skill is not None else text
    return {
        "modelo": MODEL,
        "score": score,
        "fatores": {
            "habilidades": round(skill, 2) if skill is not None else None,
            "similaridade_textual": text,
            "pesos": {
                "habilidades": 80 if weight else 0,
                "texto": 20 if weight else 100,
            },
            "requisitos": details,
        },
        "fortes": [r["habilidade"] for r in details if r["atendida"]],
        "lacunas": [r["habilidade"] for r in details if not r["atendida"]],
        "obrigatorios_pendentes": [
            r["habilidade"] for r in details if r["obrigatoria"] and not r["atendida"]
        ],
        "limites": "Índice de correspondência declarada, não probabilidade de contratação. TF-IDF e aliases locais; sem embeddings treinados ou decisões automáticas.",
        "atributos_excluidos": [
            "nome",
            "email",
            "idade",
            "genero",
            "raca",
            "deficiencia",
            "foto",
            "salario",
            "endereco",
        ],
    }


async def contexto(cid, vid, s):
    await checar_acesso_analise(cid, vid, s)
    p = await fetch_one(
        "SELECT * FROM Candidatos WHERE ID_Candidatos=%s AND Ativo=1", (cid,)
    )
    v = await fetch_one("SELECT * FROM Vagas WHERE ID_Vagas=%s AND Ativo=1", (vid,))
    if not p or not v:
        raise HTTPException(404, "Perfil ou vaga indisponível.")
    skills = await fetch_all(
        "SELECT h.Nome,ch.Nivel FROM Candidato_Habilidades ch JOIN Habilidades h ON h.ID_Habilidades=ch.ID_Habilidades AND h.Ativo=1 WHERE ch.ID_Candidatos=%s",
        (cid,),
    )
    required = await fetch_all(
        "SELECT h.Nome,vh.NivelMinimo,vh.Obrigatoria,vh.Peso FROM Vaga_Habilidades vh JOIN Habilidades h ON h.ID_Habilidades=vh.ID_Habilidades AND h.Ativo=1 WHERE vh.ID_Vagas=%s",
        (vid,),
    )
    xp = await fetch_all(
        "SELECT Cargo,Descricao FROM Experiencias WHERE ID_Candidatos=%s", (cid,)
    )
    edu = await fetch_all(
        "SELECT Curso,Nivel FROM Formacoes WHERE ID_Candidatos=%s", (cid,)
    )
    text = " ".join(
        str(x or "")
        for x in [
            p.get("TituloProfissional"),
            p.get("Resumo"),
            *(h["Nome"] for h in skills),
            *(r.get("Cargo") for r in xp),
            *(r.get("Descricao") for r in xp),
            *(r["Curso"] for r in edu),
        ]
    )
    result = await asyncio.to_thread(
        explicar, text, f"{v['Titulo']} {v['Descricao'] or ''}", skills, required
    )
    result["experiencia"] = {
        "anos_declarados": p.get("ExperienciaAnos"),
        "cargos": [r["Cargo"] for r in xp],
        "pontua": False,
    }
    result["formacao"] = {"cursos": [r["Curso"] for r in edu], "pontua": False}
    result["localizacao"] = {
        "pontua": False,
        "observacao": "Preferências logísticas devem ser revisadas pelo candidato e RH.",
    }
    result["orientacoes"] = [
        f"Confira o nível exigido em {h} e registre evidências no perfil."
        for h in result["lacunas"]
    ]
    if not p.get("Resumo"):
        result["orientacoes"].append("Escreva uma apresentação profissional objetiva.")
    if not xp:
        result["orientacoes"].append(
            "Inclua experiências acadêmicas ou projetos, sem inventar experiência profissional."
        )
    result["resumo_vaga"] = v["Titulo"] + ": " + (v["Descricao"] or "")[:500]
    result["perguntas_entrevista"] = [
        f"Que projeto demonstra seu conhecimento em {h['Nome']}?" for h in required[:8]
    ]
    result["revisao_humana"] = True
    return result


@router.get("/candidatos/{cid}/vagas/{vid}")
async def orientacao(cid: str, vid: str, s=Depends(usuario_atual)):
    return await contexto(cid, vid, s)


class Analise(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_candidato: str = Field(min_length=1, max_length=36)
    id_vaga: str = Field(min_length=1, max_length=36)


@router.post("/analises", status_code=201)
async def registrar(d: Analise, request: Request, s=Depends(usuario_atual)):
    result = await contexto(d.id_candidato, d.id_vaga, s)
    id = novo_uuid()
    await execute(
        "INSERT INTO IA_Explicacoes(ID_Explicacao,ID_Candidatos,ID_Vagas,Modelo,Fatores) VALUES (%s,%s,%s,%s,%s)",
        (
            id,
            d.id_candidato,
            d.id_vaga,
            MODEL,
            json.dumps(result, ensure_ascii=False, default=str),
        ),
    )
    await registrar_auditoria(
        request,
        "ia.orientacao",
        "IA_Explicacoes",
        s["id_usuario"],
        id,
        novo={"modelo": MODEL, "score": result["score"]},
    )
    return {"id": id, **result}


@router.get("/candidatos/{cid}/vagas/{vid}/historico")
async def historico(cid: str, vid: str, s=Depends(usuario_atual)):
    await checar_acesso_analise(cid, vid, s)
    rows = await fetch_all(
        "SELECT * FROM IA_Explicacoes WHERE ID_Candidatos=%s AND ID_Vagas=%s ORDER BY CriadoEm DESC LIMIT 30",
        (cid, vid),
    )
    for row in rows:
        row["Fatores"] = (
            json.loads(row["Fatores"])
            if isinstance(row["Fatores"], str)
            else row["Fatores"]
        )
    return rows
