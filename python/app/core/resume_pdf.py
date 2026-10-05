"""PDF Talentix gerado só a partir dos dados oficiais, sem buscar recursos externos."""
from io import BytesIO
from html import escape
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer


def gerar_pdf(dados, contato):
    output = BytesIO()
    styles = getSampleStyleSheet()
    story = []
    def text(value, style="BodyText"):
        if value:
            # Paragraph aceita markup; toda informação do candidato é escapada.
            story.append(Paragraph(escape(str(value)).replace("\n", "<br/>"), styles[style]))
            story.append(Spacer(1, 7))
    p = dados["perfil"]
    text(contato["Nome"], "Title")
    text(p.get("TituloProfissional"), "Heading2")
    text(" · ".join(str(v) for v in (contato.get("Email"), contato.get("Telefone"), p.get("Cidade"), p.get("Estado")) if v))
    text(p.get("Resumo"))
    for key in ("GithubUrl", "LinkedinUrl", "PortfolioUrl"):
        text(p.get(key))
    estudos = [f for f in dados['formacoes'] if f.get('Nivel') != 'Certificado']
    estudos += [{**i, 'Curso':i['Titulo'], 'DataConclusao':i.get('DataFim')} for i in dados['itens'] if i['Tipo'] == 'curso']
    for title, items, fields in (("Experiências", dados['experiencias'], ("Cargo", "Empresa", "DataInicio", "DataFim", "Descricao")),
        ("Formação acadêmica e cursos", estudos, ("Curso", "Instituicao", "Nivel", "DataConclusao", "Descricao", "Url")),
        ("Certificados", [f for f in dados['formacoes'] if f.get('Nivel') == 'Certificado'], ("Curso", "Instituicao", "DataConclusao")),
        ("Projetos", [i for i in dados['itens'] if i['Tipo'] == 'projeto'], ("Titulo", "Instituicao", "Descricao", "Url")),
        ("Habilidades técnicas", dados['habilidades'], ("Nome",)), ("Idiomas", dados['idiomas'], ("Nome", "Nivel"))):
        if items:
            text(title, "Heading2")
            for item in items:
                text(" · ".join(str(item[f]) for f in fields if item.get(f)))
    if p.get("HabilidadesComportamentais"):
        text("Habilidades comportamentais", "Heading2")
        text(", ".join(p["HabilidadesComportamentais"]))
    text("Talentix — currículo gerado pelo candidato", "BodyText")
    SimpleDocTemplate(output, pagesize=A4, title="Currículo Talentix", author="Talentix").build(story)
    return output.getvalue()
