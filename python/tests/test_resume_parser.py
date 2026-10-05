from app.core.resume_parser import analisar_curriculo
from pathlib import Path


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


def test_parser_normaliza_periodo_de_formacao_escrito_com_conclusao_primeiro():
    dados = analisar_curriculo("""
Maria Silva
Desenvolvedora Web

Formação acadêmica
Tecnologia em Sistemas | Faculdade Exemplo | Conclusão 2027, início 2025
""")

    assert dados["formacoes"] == [{
        "instituicao": "Faculdade Exemplo",
        "curso": "Tecnologia em Sistemas",
        "nivel": None,
        "data_inicio": "2025-01-01",
        "data_conclusao": "2027-01-01",
        "status": None,
    }]


def test_separa_certificados_projetos_e_formacao_sem_misturar_periodos():
    dados = analisar_curriculo("""Maria Silva
Desenvolvedora Web
Formação acadêmica
Técnico em Sistemas | SENAC Minas | 2025 - 2027
Ensino Médio | Escola Exemplo | 2022 - 2024
Certificados
Python Avançado | IFMG | 2026
Java Básico | IFRS | 2024
Projetos pessoais
Talentix — Plataforma de empregos
Aplicação desenvolvida durante o curso no SENAC.
https://github.com/exemplo/talentix
Biblioteca — Gestão de empréstimos
Habilidades
Python | SQL
""")
    assert [(f['curso'], f['data_inicio'], f['data_conclusao']) for f in dados['formacoes']] == [
        ('Técnico em Sistemas', '2025-01-01', '2027-01-01'),
        ('Ensino Médio', '2022-01-01', '2024-01-01'),
    ]
    assert [f['curso'] for f in dados['certificados']] == ['Python Avançado', 'Java Básico']
    assert all(f['nivel'] == 'Certificado' for f in dados['certificados'])
    assert [p['titulo'] for p in dados['projetos']] == ['Talentix', 'Biblioteca']
    assert dados['projetos'][0]['url'] == 'https://github.com/exemplo/talentix'
    assert 'SENAC' in dados['projetos'][0]['descricao']


def test_certificado_com_instituicao_em_outra_linha():
    dados = analisar_curriculo('Maria Silva\nCertificados\nPython Avançado\nIFMG\n2026\nProjetos\nTalentix — Portal de empregos')
    assert len(dados['certificados']) == 1
    assert dados['certificados'][0]['curso'] == 'Python Avançado'
    assert dados['certificados'][0]['instituicao'] == 'IFMG'
    assert dados['formacoes'] == []
    assert dados['projetos'][0]['titulo'] == 'Talentix'


def test_cabecalhos_compostos_das_imagens_nao_contaminam_formacao():
    texto = (Path(__file__).parent / 'fixtures/resume_review_sections.txt').read_text()
    dados = analisar_curriculo(texto)
    assert len(dados['formacoes']) == 2
    assert [f['nivel'] for f in dados['formacoes']] == ['Técnico', 'Ensino Médio']
    assert dados['formacoes'][0]['data_inicio'] == '2025-01-01'
    assert dados['formacoes'][0]['data_conclusao'] == '2027-01-01'
    assert len(dados['certificados']) == 2
    assert dados['certificados'][0]['curso'] == 'Microsoft Office 2016 Avançado'
    assert dados['certificados'][0]['data_inicio'] is None
    assert dados['certificados'][1]['instituicao'] == 'Cisco'
    assert [p['titulo'] for p in dados['projetos']] == ['Talentix', 'LUMORA', 'AcademiaFit', 'ChurrasPlan']
    assert all(f['nivel'] != 'Certificado' for f in dados['formacoes'])
