"""Compatibilidade explicável: habilidades declaradas e similaridade TF-IDF.

Não usa nome, e-mail, idade, gênero, salário ou outros dados pessoais para pontuar.
O arquivo PDF/DOC não é extraído; o texto vem dos campos preenchidos no perfil.
"""
import unicodedata
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

MODEL = "talentix-tfidf-habilidades-v1"
STOP_WORDS = ["de", "do", "da", "dos", "das", "a", "o", "as", "os", "e", "em", "para", "com", "um", "uma"]


def normalize(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value or "").casefold() if not unicodedata.combining(c))


def calculate_match(profile_text, job_text, candidate_skills, required_skills):
    """Retorna pontuação 0..100 e evidências rastreáveis às habilidades informadas."""
    try:
        vectors = TfidfVectorizer(strip_accents="unicode", stop_words=STOP_WORDS,
                                 ngram_range=(1, 2), max_features=5000).fit_transform([profile_text or "", job_text or ""])
        text_score = float(cosine_similarity(vectors[0], vectors[1])[0, 0])
    except ValueError:  # perfil e vaga sem termos úteis
        text_score = 0.0
    levels = {normalize(h["Nome"]): h.get("Nivel") or 0 for h in candidate_skills}
    strong, gaps, matched_weight, total_weight = [], [], 0, 0
    for skill in required_skills:
        weight = max(skill.get("Peso") or 1, 1) * (2 if skill.get("Obrigatoria") else 1)
        total_weight += weight
        name = normalize(skill["Nome"])
        if name in levels and levels[name] >= (skill.get("NivelMinimo") or 0):
            matched_weight += weight
            strong.append(skill["Nome"])
        else:
            gaps.append(skill["Nome"])
    skill_score = matched_weight / total_weight if total_weight else None
    score = round(100 * (0.8 * skill_score + 0.2 * text_score if skill_score is not None else text_score))
    reason = (f"{len(strong)} de {len(required_skills)} habilidades atendidas; 80% habilidades e 20% similaridade textual."
              if required_skills else "A vaga não definiu habilidades; pontuação baseada somente na similaridade textual.")
    return {"score_compatibilidade": max(0, min(100, score)), "pontos_fortes": ", ".join(strong) or "Nenhuma habilidade da vaga atendida nas informações do perfil.",
            "lacunas": ", ".join(gaps) or "Nenhuma lacuna nas habilidades declaradas da vaga.",
            "justificativa": reason + " Este índice auxilia a preparação e não decide contratação.",
            "modelo_ia": MODEL, "missing_skills": gaps}
