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
    for title, key, fields in (("Experiências", "experiencias", ("Cargo", "Empresa", "DataInicio", "DataFim", "Descricao")),
        ("Formação e certificados", "formacoes", ("Curso", "Instituicao", "Nivel", "DataConclusao")),
        ("Cursos e projetos", "itens", ("Titulo", "Instituicao", "Descricao", "Url")),
        ("Habilidades técnicas", "habilidades", ("Nome",)), ("Idiomas", "idiomas", ("Nome", "Nivel"))):
        if dados[key]:
            text(title, "Heading2")
            for item in dados[key]:
                text(" · ".join(str(item[f]) for f in fields if item.get(f)))
    if p.get("HabilidadesComportamentais"):
        text("Habilidades comportamentais", "Heading2")
        text(", ".join(p["HabilidadesComportamentais"]))
    text("Talentix — currículo gerado pelo candidato", "BodyText")
    SimpleDocTemplate(output, pagesize=A4, title="Currículo Talentix", author="Talentix").build(story)
    return output.getvalue()
