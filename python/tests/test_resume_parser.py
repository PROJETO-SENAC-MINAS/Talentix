from app.core.resume_parser import analisar_curriculo


def test_parser_curriculo_identifica_dados_principais():
    texto = """
Arthur Barbosa
Desenvolvedor Web Full Stack
Contagem - MG
https://www.linkedin.com/in/arthurhenrique-eng/
https://github.com/ArthurHenrique-eng

Resumo
Desenvolvedor com foco em aplicações web e APIs.

Experiência profissional
Würth Industry
Jovem Aprendiz
2026 - Atual

Formação acadêmica
Técnico em Desenvolvimento de Sistemas | SENAC Minas | 2025 - 2027

Habilidades
Python | FastAPI | MySQL | JavaScript

Idiomas
Português - Nativo
Inglês - Intermediário
"""

    dados = analisar_curriculo(
        texto,
        habilidades_catalogo=["Python", "FastAPI", "MySQL", "JavaScript", "C#"],
        idiomas_catalogo=["Português", "Inglês", "Espanhol"],
    )

    assert dados["perfil"]["titulo_profissional"] == "Desenvolvedor Web Full Stack"
    assert dados["perfil"]["cidade"] == "Contagem"
    assert dados["perfil"]["estado"] == "MG"
    assert dados["perfil"]["linkedin_url"].startswith("https://")
    assert dados["perfil"]["github_url"].startswith("https://")

    habilidades = {item["nome"] for item in dados["habilidades"]}
    assert {"Python", "FastAPI", "MySQL", "JavaScript"} <= habilidades

    idiomas = {item["idioma"]: item["nivel"] for item in dados["idiomas"]}
    assert idiomas["Português"] == "Nativo"
    assert idiomas["Inglês"] == "Intermediário"

    assert dados["experiencias"][0]["empresa"] == "Würth Industry"
    assert dados["experiencias"][0]["cargo"] == "Jovem Aprendiz"
    assert dados["experiencias"][0]["atual"] is True

    assert any(item["instituicao"] == "SENAC Minas" for item in dados["formacoes"])


def test_parser_nao_inventa_campos_sem_evidencia():
    dados = analisar_curriculo("Maria Silva\nContato: maria@example.com\nObjetivo\nPrimeira oportunidade na área.")
    assert dados["perfil"]["cidade"] is None
    assert dados["perfil"]["estado"] is None
    assert dados["experiencias"] == []
    assert dados["habilidades"] == []
