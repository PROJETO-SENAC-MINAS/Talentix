"""Publicação explícita, páginas HTML com SEO e avaliações moderadas."""

import json
import re
from datetime import datetime, timezone
from html import escape
from typing import Literal
from urllib.parse import quote
from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from app.core.routes import AtomicRouter
from app.core.deps import usuario_atual, exigir_tipo
from app.core.config import settings
from app.core.audit import registrar_auditoria
from app.core.security import novo_uuid
from app.db.database import fetch_one, fetch_all, execute
from app.routers.organizations import contexto_empresa

router = AtomicRouter(tags=["Páginas públicas"])


def unpack(v, default):
    return json.loads(v) if isinstance(v, str) else (v if v is not None else default)


def base():
    return settings.PUBLIC_SITE_URL.rstrip("/")


def frontend():
    return settings.cors_origins[0]


def utc(v):
    return datetime.fromisoformat(v) if isinstance(v, str) else v


def asset(v):
    return v if v and re.fullmatch(r"/uploads/logos/[a-f0-9]{64}\.png", v) else None


class PublicacaoEmpresa(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    slug: str = Field(
        min_length=3, max_length=180, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    publicada: bool = False
    cultura: str = Field(default="", max_length=10000)
    beneficios: list[str] = Field(default_factory=list, max_length=30)
    tecnologias: list[str] = Field(default_factory=list, max_length=50)
    localizacao: str = Field(default="", max_length=200)
    versao: int = Field(default=1, ge=1)


@router.get("/publicacao/empresa")
async def configuracao(id_empresa: str | None = None, s=Depends(usuario_atual)):
    e = await contexto_empresa(s, id_empresa, "publicacao")
    row = await fetch_one(
        "SELECT * FROM Publico_Empresas WHERE ID_Empresas=%s", (e["ID_Empresas"],)
    )
    if not row:
        return None
    for k in ("Beneficios", "Tecnologias"):
        row[k] = unpack(row[k], [])
    return row


@router.put("/publicacao/empresa")
async def publicar_empresa(
    d: PublicacaoEmpresa,
    request: Request,
    id_empresa: str | None = None,
    s=Depends(usuario_atual),
):
    e = await contexto_empresa(s, id_empresa, "publicacao")
    if any(
        not str(v).strip() or len(str(v)) > 150 for v in d.beneficios + d.tecnologias
    ):
        raise HTTPException(422, "Cada item deve conter de 1 a 150 caracteres.")
    await fetch_one(
        "SELECT ID_Empresas FROM Empresas WHERE ID_Empresas=%s FOR UPDATE",
        (e["ID_Empresas"],),
    )
    old = await fetch_one(
        "SELECT * FROM Publico_Empresas WHERE ID_Empresas=%s FOR UPDATE",
        (e["ID_Empresas"],),
    )
    if old and old["Versao"] != d.versao:
        raise HTTPException(409, "Página alterada; recarregue.")
    values = (
        d.slug,
        d.publicada,
        d.cultura,
        json.dumps(d.beneficios, ensure_ascii=False),
        json.dumps(d.tecnologias, ensure_ascii=False),
        d.localizacao,
        e["ID_Empresas"],
    )
    if old:
        await execute(
            "UPDATE Publico_Empresas SET Slug=%s,Publicada=%s,Cultura=%s,Beneficios=%s,Tecnologias=%s,Localizacao=%s,Versao=Versao+1 WHERE ID_Empresas=%s",
            values,
        )
    else:
        await execute(
            "INSERT INTO Publico_Empresas(Slug,Publicada,Cultura,Beneficios,Tecnologias,Localizacao,ID_Empresas) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            values,
        )
    await registrar_auditoria(
        request,
        "publicacao.empresa",
        "Publico_Empresas",
        s["id_usuario"],
        e["ID_Empresas"],
        novo={"publicada": d.publicada, "slug": d.slug},
    )
    return {
        "url": base() + "/p/empresa/" + d.slug,
        "versao": old["Versao"] + 1 if old else 1,
    }


class PublicacaoVaga(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(
        min_length=3, max_length=240, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    expira_em: datetime
    pais: Literal["BR", "PT", "US", "CA", "GB", "AR", "CL", "UY", "PY", "DE"] = "BR"


@router.put("/publicacao/vagas/{id}")
async def publicar_vaga(
    id: str, d: PublicacaoVaga, request: Request, s=Depends(usuario_atual)
):
    v = await fetch_one("SELECT * FROM Vagas WHERE ID_Vagas=%s AND Ativo=1", (id,))
    if not v:
        raise HTTPException(404, "Vaga indisponível.")
    await contexto_empresa(s, v["ID_Empresas"], "publicacao")
    p = await fetch_one(
        "SELECT Publicada FROM Publico_Empresas WHERE ID_Empresas=%s",
        (v["ID_Empresas"],),
    )
    if v["ID_Status_Vaga"] != 2 or not p or not p["Publicada"]:
        raise HTTPException(
            409, "Publique a empresa e a vaga antes de liberar o endereço público."
        )
    end = (
        d.expira_em.replace(tzinfo=timezone.utc)
        if d.expira_em.tzinfo is None
        else d.expira_em.astimezone(timezone.utc)
    )
    if end <= datetime.now(timezone.utc):
        raise HTTPException(422, "Expiração deve estar no futuro.")
    if not v.get("Localizacao") and (v.get("Modalidade") or "").lower() != "remoto":
        raise HTTPException(422, "Informe uma localização para a vaga.")
    old = await fetch_one("SELECT ID_Vagas FROM Publico_Vagas WHERE ID_Vagas=%s", (id,))
    if old:
        await execute(
            "UPDATE Publico_Vagas SET Slug=%s,ExpiraEm=%s,Pais=%s WHERE ID_Vagas=%s",
            (d.slug, end.replace(tzinfo=None), d.pais, id),
        )
    else:
        await execute(
            "INSERT INTO Publico_Vagas(ID_Vagas,Slug,ExpiraEm,Pais) VALUES (%s,%s,%s,%s)",
            (id, d.slug, end.replace(tzinfo=None), d.pais),
        )
    await registrar_auditoria(
        request, "publicacao.vaga", "Publico_Vagas", s["id_usuario"], id
    )
    return {"url": base() + "/p/vaga/" + d.slug}


def document(title, description, path, body, structured=None, status=200):
    canonical = base() + path
    data = ""
    if structured:
        payload = (
            json.dumps(structured, ensure_ascii=False, default=str)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
        )
        data = '<script type="application/ld+json">' + payload + "</script>"
    html = f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} — Talentix</title><meta name="description" content="{escape(description[:180], quote=True)}">
<link rel="canonical" href="{escape(canonical, quote=True)}"><meta property="og:title" content="{escape(title, quote=True)}">
<meta property="og:description" content="{escape(description[:180], quote=True)}"><meta property="og:url" content="{escape(canonical, quote=True)}"><meta property="og:type" content="website">
<link rel="stylesheet" href="/publico-estatico/publico.css">{data}</head><body><a class="skip-link" href="#conteudo">Ir ao conteúdo</a>
<header><a href="{escape(frontend(), quote=True)}/html/index.html">Talentix</a><nav aria-label="Navegação"><a href="{escape(frontend(), quote=True)}/html/login.html">Entrar</a></nav></header>
<main id="conteudo" tabindex="-1"><h1>{escape(title)}</h1>{body}</main><footer><a href="{escape(frontend(), quote=True)}/html/privacidade.html">Privacidade</a></footer></body></html>'''
    return HTMLResponse(
        html,
        status_code=status,
        headers={
            "Content-Security-Policy": "default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
            "Cache-Control": "public, max-age=0, must-revalidate",
        },
    )


@router.get("/p/empresa/{slug}", response_class=HTMLResponse)
async def pagina_empresa(slug: str):
    e = await fetch_one(
        """SELECT e.ID_Empresas,e.NomeFantasia,e.RazaoSocial,e.Descricao,e.Setor,e.Porte,e.LogoUrl,p.*
        FROM Publico_Empresas p JOIN Empresas e ON e.ID_Empresas=p.ID_Empresas WHERE p.Slug=%s AND p.Publicada=1 AND e.Ativo=1""",
        (slug,),
    )
    if not e:
        raise HTTPException(404, "Página indisponível.")
    jobs = await fetch_all(
        """SELECT v.Titulo,p.Slug FROM Vagas v JOIN Publico_Vagas p ON p.ID_Vagas=v.ID_Vagas
        WHERE v.ID_Empresas=%s AND v.Ativo=1 AND v.ID_Status_Vaga=2 AND p.ExpiraEm>NOW() ORDER BY v.PublicadaEm DESC LIMIT 100""",
        (e["ID_Empresas"],),
    )
    reviews = await fetch_all(
        "SELECT Nota,Comentario FROM Publico_Avaliacoes WHERE ID_Empresas=%s AND Estado='aprovada' ORDER BY CriadoEm DESC LIMIT 50",
        (e["ID_Empresas"],),
    )
    logo = asset(e["LogoUrl"])
    body = (
        f'<img alt="Logo da empresa" width="120" height="120" src="{escape(logo)}">'
        if logo
        else ""
    )
    body += (
        "<p>"
        + escape(e["Descricao"] or "")
        + "</p><p>"
        + escape(
            " · ".join(str(e.get(k) or "") for k in ("Setor", "Porte", "Localizacao"))
        )
        + "</p>"
    )
    body += (
        "<section><h2>Cultura</h2><p>" + escape(e["Cultura"] or "") + "</p></section>"
    )
    for key, label in [("Beneficios", "Benefícios"), ("Tecnologias", "Tecnologias")]:
        body += (
            "<section><h2>"
            + label
            + "</h2><ul>"
            + "".join("<li>" + escape(str(x)) + "</li>" for x in unpack(e[key], []))
            + "</ul></section>"
        )
    body += (
        "<section><h2>Vagas abertas</h2><ul>"
        + (
            "".join(
                f'<li><a href="/p/vaga/{escape(v["Slug"])}">{escape(v["Titulo"])}</a></li>'
                for v in jobs
            )
            or "<li>Nenhuma vaga aberta.</li>"
        )
        + "</ul></section>"
    )
    body += (
        "<section><h2>Avaliações moderadas</h2>"
        + (
            "".join(
                "<article><h3>Avaliação "
                + str(r["Nota"])
                + "/5</h3><p>"
                + escape(r["Comentario"])
                + "</p></article>"
                for r in reviews
            )
            or "<p>Sem avaliações publicadas.</p>"
        )
        + "</section>"
    )
    return document(
        e["NomeFantasia"] or e["RazaoSocial"],
        e["Descricao"] or "",
        "/p/empresa/" + slug,
        body,
    )


@router.get("/p/vaga/{slug}", response_class=HTMLResponse)
async def pagina_vaga(slug: str):
    v = await fetch_one(
        """SELECT v.*,p.ExpiraEm,p.Pais AS PaisPublico,e.NomeFantasia,e.RazaoSocial,pe.Slug AS EmpresaSlug
        FROM Publico_Vagas p JOIN Vagas v ON v.ID_Vagas=p.ID_Vagas
        JOIN Empresas e ON e.ID_Empresas=v.ID_Empresas AND e.Ativo=1
        JOIN Publico_Empresas pe ON pe.ID_Empresas=e.ID_Empresas AND pe.Publicada=1 WHERE p.Slug=%s""",
        (slug,),
    )
    if not v:
        raise HTTPException(404, "Vaga indisponível.")
    if (
        not v["Ativo"]
        or v["ID_Status_Vaga"] != 2
        or utc(v["ExpiraEm"]) <= datetime.now(timezone.utc).replace(tzinfo=None)
    ):
        r = document(
            "Vaga encerrada",
            "Esta oportunidade foi encerrada.",
            "/p/vaga/" + slug,
            "<p>Esta vaga não recebe mais candidaturas.</p>",
            status=410,
        )
        r.headers["X-Robots-Tag"] = "noindex"
        return r
    name = v["NomeFantasia"] or v["RazaoSocial"]
    url = base() + "/p/vaga/" + slug
    schema = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": v["Titulo"],
        "description": v["Descricao"],
        "datePosted": utc(v["PublicadaEm"] or v["CriadoEm"]).isoformat() + "Z",
        "validThrough": utc(v["ExpiraEm"]).isoformat() + "Z",
        "hiringOrganization": {
            "@type": "Organization",
            "name": name,
            "sameAs": base() + "/p/empresa/" + v["EmpresaSlug"],
        },
        "identifier": {
            "@type": "PropertyValue",
            "name": "Talentix",
            "value": v["ID_Vagas"],
        },
        "url": url,
    }
    if (v.get("Modalidade") or "").lower() == "remoto":
        schema["jobLocationType"] = "TELECOMMUTE"
        schema["applicantLocationRequirements"] = {
            "@type": "Country",
            "name": v["PaisPublico"],
        }
    elif v.get("Localizacao"):
        schema["jobLocation"] = {
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": v["Localizacao"],
                "addressCountry": v["PaisPublico"],
            },
        }
    body = (
        '<p><a href="/p/empresa/'
        + escape(v["EmpresaSlug"])
        + '">'
        + escape(name)
        + "</a></p><p>"
        + escape(v.get("Localizacao") or "Remoto")
        + " · País de atuação: "
        + escape(v["PaisPublico"])
        + "</p>"
    )
    body += (
        '<section><h2>Descrição da oportunidade</h2><p class="texto">'
        + escape(v["Descricao"])
        + "</p></section>"
    )
    if not v["SalarioConfidencial"] and v["SalarioMin"] is not None:
        body += (
            "<p>Salário: R$ "
            + escape(str(v["SalarioMin"]))
            + ((" a R$ " + escape(str(v["SalarioMax"]))) if v["SalarioMax"] else "")
            + "</p>"
        )
    apply = frontend() + "/html/login.html?vaga=" + quote(v['ID_Vagas']) + '&cargo=' + quote(v["Titulo"])
    body += (
        '<p><a class="botao" href="'
        + escape(apply, quote=True)
        + '">Entrar para se candidatar</a></p>'
    )
    body += (
        '<p><a href="https://www.linkedin.com/sharing/share-offsite/?url='
        + quote(url, safe="")
        + '" rel="noopener noreferrer">Compartilhar no LinkedIn</a> · <a href="https://wa.me/?text='
        + quote(url, safe="")
        + '" rel="noopener noreferrer">Compartilhar no WhatsApp</a></p>'
    )
    return document(v["Titulo"], v["Descricao"], "/p/vaga/" + slug, body, schema)


@router.get("/sitemap.xml", response_class=Response)
async def sitemap():
    companies = await fetch_all(
        """SELECT p.Slug FROM Publico_Empresas p JOIN Empresas e ON e.ID_Empresas=p.ID_Empresas AND e.Ativo=1 WHERE p.Publicada=1 LIMIT 5000"""
    )
    jobs = await fetch_all("""SELECT p.Slug FROM Publico_Vagas p JOIN Vagas v ON v.ID_Vagas=p.ID_Vagas AND v.Ativo=1 AND v.ID_Status_Vaga=2
        JOIN Empresas e ON e.ID_Empresas=v.ID_Empresas AND e.Ativo=1 JOIN Publico_Empresas pe ON pe.ID_Empresas=e.ID_Empresas AND pe.Publicada=1 WHERE p.ExpiraEm>NOW() LIMIT 5000""")
    urls = [base() + "/p/empresa/" + r["Slug"] for r in companies] + [
        base() + "/p/vaga/" + r["Slug"] for r in jobs
    ]
    return Response(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join("<url><loc>" + escape(u) + "</loc></url>" for u in urls)
        + "</urlset>",
        media_type="application/xml",
    )


@router.get("/robots.txt", response_class=Response)
async def robots():
    return Response(
        "User-agent: *\nAllow: /p/\nDisallow: /auth/\nDisallow: /agenda\nDisallow: /comunicacao/\nSitemap: "
        + base()
        + "/sitemap.xml\n",
        media_type="text/plain",
    )


class Avaliacao(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nota: int = Field(ge=1, le=5)
    comentario: str = Field(min_length=10, max_length=2000)


@router.post("/publicacao/empresas/{id}/avaliacoes", status_code=201)
async def avaliar(id: str, d: Avaliacao, request: Request, s=Depends(usuario_atual)):
    linked = await fetch_one(
        """SELECT c.ID_Candidaturas FROM Candidaturas c JOIN Vagas v ON v.ID_Vagas=c.ID_Vagas
        JOIN Candidatos ca ON ca.ID_Candidatos=c.ID_Candidatos WHERE ca.ID_Usuarios=%s AND v.ID_Empresas=%s LIMIT 1""",
        (s["id_usuario"], id),
    )
    if not linked:
        raise HTTPException(
            403, "Avaliações exigem participação em um processo desta empresa."
        )
    key = novo_uuid()
    await execute(
        "INSERT INTO Publico_Avaliacoes(ID_Avaliacao,ID_Empresas,ID_Usuarios,Nota,Comentario) VALUES (%s,%s,%s,%s,%s)",
        (key, id, s["id_usuario"], d.nota, d.comentario),
    )
    await registrar_auditoria(
        request, "publicacao.avaliacao", "Publico_Avaliacoes", s["id_usuario"], key
    )
    return {"mensagem": "Avaliação recebida para moderação."}


@router.get("/publicacao/moderacao")
async def moderacao(s=Depends(exigir_tipo("administrador"))):
    return await fetch_all(
        "SELECT ID_Avaliacao,ID_Empresas,Nota,Comentario,CriadoEm FROM Publico_Avaliacoes WHERE Estado='pendente' ORDER BY CriadoEm LIMIT 100"
    )


class Moderacao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    estado: Literal["aprovada", "rejeitada"]


@router.patch("/publicacao/moderacao/{id}")
async def moderar(
    id: str, d: Moderacao, request: Request, s=Depends(exigir_tipo("administrador"))
):
    if not await fetch_one(
        "SELECT ID_Avaliacao FROM Publico_Avaliacoes WHERE ID_Avaliacao=%s", (id,)
    ):
        raise HTTPException(404, "Avaliação indisponível.")
    await execute(
        "UPDATE Publico_Avaliacoes SET Estado=%s WHERE ID_Avaliacao=%s", (d.estado, id)
    )
    await registrar_auditoria(
        request,
        "publicacao.moderar",
        "Publico_Avaliacoes",
        s["id_usuario"],
        id,
        novo=d.model_dump(),
    )
    return {"mensagem": "Moderação registrada."}
