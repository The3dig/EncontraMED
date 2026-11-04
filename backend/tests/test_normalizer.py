import pytest

from app.drug.normalizer import match, parse_product, parse_query
from app.drug.text import parse_dose, parse_pack_quantity

Q = "Cloridrato de Clorpromazina 25 mg (Amplictil)"


def test_parse_query_case_real():
    q = parse_query(Q)
    assert q.active_ingredients == ["clorpromazina"]
    assert q.brands == ["amplictil"]
    assert q.salt == "cloridrato"
    assert (q.dose_value, q.dose_unit) == (25.0, "mg")
    assert q.controlled and q.controlled.list_code == "C1"
    assert q.controlled.online_sale_allowed is False
    assert "amplictil 25mg" in q.search_terms and "clorpromazina" in q.search_terms


@pytest.mark.parametrize("name,dose,pack", [
    ("Amplictil 25mg 20 Comprimidos", (25.0, "mg"), 20),
    ("Amplictil 25 mg caixa com 200 comprimidos", (25.0, "mg"), 200),
    ("Clorpromazina 25mg c/ 50", (25.0, "mg"), 50),
    ("20 comprimidos Amplictil 25mg", (25.0, "mg"), 20),
    ("Losartana 50mg 30cpr", (50.0, "mg"), 30),
])
def test_dose_never_confused_with_pack(name, dose, pack):
    assert parse_dose(name) == dose
    assert parse_pack_quantity(name) == pack


@pytest.mark.parametrize("name,expected", [
    ("Amplictil 25mg 20 Comprimidos Revestidos", "exato"),
    ("Amplictil 25mg 200 Comprimidos", "exato"),  # embalagem diferente não limita
    ("Amplictil 100mg 20 Comprimidos", "nao_corresponde"),
    ("Amplictil Gotas 40mg/ml 20ml", "nao_corresponde"),
    ("Clorpromazina 5mg/ml Solução Injetável 5 ampolas", "nao_corresponde"),
    ("Cloridrato de Clorpromazina 25mg 20 Comprimidos Genérico", "mesmo_principio_ativo"),
    ("Haloperidol 5mg 20 Comprimidos", "nao_corresponde"),
])
def test_match(name, expected):
    assert match(parse_query(Q), parse_product(name)).kind == expected


def test_active_only_query_treats_generics_as_exact():
    q = parse_query("clorpromazina 25mg")
    assert match(q, parse_product("Amplictil 25mg 20 comp")).kind == "exato"


def test_missing_dose_lowers_confidence():
    m = match(parse_query(Q), parse_product("Amplictil comprimidos"))
    assert m.matched and m.confidence < 0.9
