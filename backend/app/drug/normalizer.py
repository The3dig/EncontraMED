"""Interpretação da consulta do usuário e dos nomes de produtos das fontes."""
from __future__ import annotations

import re

from ..models import DrugQuery, MatchResult, ParsedProduct
from .catalog import brand_to_active, find_actives, find_brands, reference
from .controlled import lookup_controlled
from .text import detect_form, norm, parse_concentration, parse_dose, parse_pack_quantity, remove_salts


def parse_query(text: str) -> DrugQuery:
    """Ex.: 'Cloridrato de Clorpromazina 25 mg (Amplictil)'."""
    brands = find_brands(text)
    actives = find_actives(text)
    manufacturer = None
    for b in brands:
        a, m = brand_to_active(b)
        if a and a not in actives:
            actives.append(a)
        manufacturer = manufacturer or m
    _, salt = remove_salts(text)
    dose_value, dose_unit = parse_dose(text)
    concentration = parse_concentration(text)
    form = detect_form(text)

    # Nenhum termo reconhecido: usa o texto limpo (sem dose) como termo livre.
    if not actives and not brands:
        cleaned, _ = remove_salts(text)
        cleaned = re.sub(r"\d+(?:[.,]\d+)?\s*(mcg|mg|g|ui|ml)\b", " ", cleaned)
        cleaned = re.sub(r"[()]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            actives = [cleaned]

    dose_txt = f" {dose_value:g}mg" if dose_value and dose_unit == "mg" else (
        f" {dose_value:g}{dose_unit}" if dose_value else "")
    terms: list[str] = []
    for b in brands:
        terms.append(f"{b}{dose_txt}".strip())
    for a in actives:
        terms.append(f"{a}{dose_txt}".strip())
    # termo amplo sem dose (algumas lojas indexam "25 mg" de forma diferente)
    for b in brands:
        terms.append(b)
    for a in actives:
        terms.append(a)
    seen: set[str] = set()
    terms = [t for t in terms if not (t in seen or seen.add(t))]

    return DrugQuery(
        raw_text=text,
        active_ingredients=actives,
        salt=salt,
        brands=brands,
        dose_value=dose_value,
        dose_unit=dose_unit,
        concentration=concentration,
        form=form,
        manufacturer=manufacturer,
        controlled=lookup_controlled(actives),
        search_terms=terms,
    )


def parse_product(name: str, brand: str | None = None, manufacturer: str | None = None,
                  ean: str | None = None, extra_text: str = "") -> ParsedProduct:
    full = f"{name} {extra_text}"
    actives = find_actives(full)
    brands = find_brands(full)
    for b in brands:
        a, _ = brand_to_active(b)
        if a and a not in actives:
            actives.append(a)
    if ean and ean in reference()["eans"]:
        ref = reference()["eans"][ean]
        if ref.get("active") and ref["active"] not in actives:
            actives.append(ref["active"])
    dv, du = parse_dose(name)
    return ParsedProduct(
        name=name,
        active_ingredients=actives,
        brand=(brands[0] if brands else (norm(brand) or None)),
        manufacturer=manufacturer,
        dose_value=dv,
        dose_unit=du,
        concentration=parse_concentration(name),
        pack_quantity=parse_pack_quantity(name),
        form=detect_form(name),
        ean=ean,
    )


def _same_dose(q: DrugQuery, p: ParsedProduct) -> bool | None:
    if q.dose_value is None:
        return None
    if p.dose_value is None:
        return None
    qu, pu = q.dose_unit or "mg", p.dose_unit or "mg"
    to_mg = {"mg": 1.0, "g": 1000.0, "mcg": 0.001}
    if qu in to_mg and pu in to_mg:
        return abs(q.dose_value * to_mg[qu] - p.dose_value * to_mg[pu]) < 1e-6
    return qu == pu and abs(q.dose_value - p.dose_value) < 1e-6


def match(q: DrugQuery, p: ParsedProduct) -> MatchResult:
    """Decide se o produto da fonte é o medicamento procurado.

    - Exige o mesmo princípio ativo (ou a marca).
    - Exige a mesma dosagem por unidade quando a consulta informa dosagem.
      A quantidade de comprimidos da embalagem NUNCA é usada como dosagem
      e NUNCA exclui um resultado.
    - Formas farmacêuticas incompatíveis (ex.: gotas 40 mg/ml quando se
      procura comprimido de 25 mg) são excluídas.
    """
    reasons: list[str] = []
    pname = norm(p.name)
    q_actives = {norm(a) for a in q.active_ingredients}
    p_actives = {norm(a) for a in p.active_ingredients}
    same_active = bool(q_actives & p_actives) or any(a in pname for a in q_actives)
    same_brand = bool(q.brands) and any(b in pname for b in q.brands)

    if not (same_active or same_brand):
        return MatchResult(matched=False, kind="nao_corresponde", confidence=0.0,
                           reasons=["princípio ativo/marca diferente"])

    # Forma líquida/concentração quando a consulta é dose sólida
    if q.dose_value is not None and q.concentration is None and p.concentration and p.dose_value is None:
        return MatchResult(matched=False, kind="nao_corresponde", confidence=0.0,
                           reasons=[f"apresentação em concentração ({p.concentration}), não {q.dose_value:g}{q.dose_unit}"])
    if q.form and p.form and q.form != p.form:
        return MatchResult(matched=False, kind="nao_corresponde", confidence=0.0,
                           reasons=[f"forma farmacêutica diferente ({p.form} ≠ {q.form})"])
    if q.concentration and p.concentration and norm(q.concentration) != norm(p.concentration):
        return MatchResult(matched=False, kind="nao_corresponde", confidence=0.0,
                           reasons=[f"concentração diferente ({p.concentration})"])

    dose = _same_dose(q, p)
    if dose is False:
        return MatchResult(matched=False, kind="nao_corresponde", confidence=0.0,
                           reasons=[f"dosagem diferente ({p.dose_value:g}{p.dose_unit} ≠ {q.dose_value:g}{q.dose_unit})"])

    confidence = 0.6
    if dose is True:
        confidence += 0.3
        reasons.append(f"dosagem {q.dose_value:g}{q.dose_unit} confere")
    elif q.dose_value is not None:
        confidence -= 0.2
        reasons.append("dosagem não identificada no nome do produto — confirmar na farmácia")
    if p.pack_quantity:
        reasons.append(f"embalagem com {p.pack_quantity} unidades (não limita a busca)")

    if same_brand or not q.brands:
        kind = "exato"
        confidence += 0.1
        reasons.insert(0, "mesma marca" if same_brand else "mesmo princípio ativo")
    else:
        kind = "mesmo_principio_ativo"
        reasons.insert(0, "mesmo princípio ativo, outra marca (genérico/similar) — "
                          "a troca só deve ser feita com orientação do prescritor ou farmacêutico")
    return MatchResult(matched=True, kind=kind, confidence=round(min(confidence, 1.0), 2), reasons=reasons)
