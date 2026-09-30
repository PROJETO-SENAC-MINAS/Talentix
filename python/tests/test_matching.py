"""Propriedades esperadas do índice, sem depender de números específicos."""
from app.core.matching import calculate_match


def test_skill_and_level_improve_match():
    required = [{"Nome":"Python", "Obrigatoria":True, "NivelMinimo":3, "Peso":2}]
    empty = calculate_match("Python", "Python", [], required)
    beginner = calculate_match("Python", "Python", [{"Nome":"Python","Nivel":1}], required)
    complete = calculate_match("Python", "Python", [{"Nome":"PYTHON","Nivel":3}], required)
    assert complete["score_compatibilidade"] > beginner["score_compatibilidade"]
    assert beginner["score_compatibilidade"] == empty["score_compatibilidade"]
    assert complete["missing_skills"] == []
    assert empty["missing_skills"] == ["Python"]


def test_empty_text_has_no_invented_compatibility():
    result = calculate_match("", "", [], [])
    assert result["score_compatibilidade"] == 0
    assert "somente na similaridade" in result["justificativa"]


def test_dissimilar_profile_scores_less_than_matching_text():
    related = calculate_match("python testes software", "python testes software", [], [])
    unrelated = calculate_match("culinaria confeitaria", "python testes software", [], [])
    assert 0 <= unrelated["score_compatibilidade"] < related["score_compatibilidade"] <= 100


def test_accents_and_case_do_not_hide_matching_skills():
    result = calculate_match("", "", [{"Nome":"COMUNICAÇÃO", "Nivel":2}], [{"Nome":"Comunicação", "NivelMinimo":1}])
    assert result["missing_skills"] == []
