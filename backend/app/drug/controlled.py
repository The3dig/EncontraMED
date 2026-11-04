"""Medicamentos sujeitos a controle especial (Portaria SVS/MS nº 344/1998).

ATENÇÃO: esta é uma lista PARCIAL e curada das substâncias mais comuns.
Os anexos da Portaria 344 são atualizados periodicamente por RDCs da ANVISA.
Antes de produção, esta tabela deve ser sincronizada com a versão vigente
(ver docs/VIABILIDADE.md, seção "Legislação").

Regra aplicada pelo Encontramed: para substâncias das listas da Portaria 344,
a venda/entrega remota (internet, telefone, aplicativo) é tratada como NÃO
permitida (RDC nº 44/2009 e normas correlatas). O sistema continua mostrando
preço e disponibilidade informados pelas lojas, mas orienta a compra
presencial com a receita adequada e nunca apresenta "comprar com entrega".
"""
from __future__ import annotations

from ..models import ControlledInfo
from .text import norm

_PRESCRIPTION = {
    "A1": "Notificação de Receita A (amarela)",
    "A2": "Notificação de Receita A (amarela)",
    "A3": "Notificação de Receita A (amarela)",
    "B1": "Notificação de Receita B (azul)",
    "B2": "Notificação de Receita B2 (azul)",
    "C1": "Receita de Controle Especial em 2 vias (retida na farmácia)",
    "C2": "Notificação de Receita Especial para retinoides",
    "C4": "Receita de Controle Especial",
    "C5": "Receita de Controle Especial em 2 vias",
    "ANTIMICROBIANO": "Receita em 2 vias (RDC 471/2021), validade de 10 dias",
}

# substância (sem sal, sem acento) -> lista
CONTROLLED: dict[str, str] = {
    # C1 — antipsicóticos
    "clorpromazina": "C1", "haloperidol": "C1", "levomepromazina": "C1", "periciazina": "C1",
    "tioridazina": "C1", "flufenazina": "C1", "risperidona": "C1", "quetiapina": "C1",
    "olanzapina": "C1", "aripiprazol": "C1", "clozapina": "C1", "ziprasidona": "C1",
    "paliperidona": "C1", "lurasidona": "C1", "sulpirida": "C1", "amissulprida": "C1",
    "pimozida": "C1", "penfluridol": "C1", "zuclopentixol": "C1", "trifluoperazina": "C1",
    # C1 — antidepressivos
    "amitriptilina": "C1", "nortriptilina": "C1", "imipramina": "C1", "clomipramina": "C1",
    "fluoxetina": "C1", "sertralina": "C1", "paroxetina": "C1", "citalopram": "C1",
    "escitalopram": "C1", "fluvoxamina": "C1", "venlafaxina": "C1", "desvenlafaxina": "C1",
    "duloxetina": "C1", "bupropiona": "C1", "mirtazapina": "C1", "trazodona": "C1",
    "vortioxetina": "C1", "agomelatina": "C1", "tianeptina": "C1",
    # C1 — anticonvulsivantes e outros
    "carbamazepina": "C1", "oxcarbazepina": "C1", "acido valproico": "C1", "valproato": "C1",
    "divalproato": "C1", "lamotrigina": "C1", "topiramato": "C1", "gabapentina": "C1",
    "pregabalina": "C1", "fenitoina": "C1", "levetiracetam": "C1", "lacosamida": "C1",
    "vigabatrina": "C1", "biperideno": "C1", "tramadol": "A2",
    # B1 — benzodiazepínicos e hipnóticos
    "alprazolam": "B1", "clonazepam": "B1", "diazepam": "B1", "lorazepam": "B1",
    "bromazepam": "B1", "midazolam": "B1", "flunitrazepam": "B1", "nitrazepam": "B1",
    "cloxazolam": "B1", "zolpidem": "B1", "zopiclona": "B1", "fenobarbital": "B1",
    # B2 — anorexígenos
    "sibutramina": "B2", "anfepramona": "B2", "femproporex": "B2", "mazindol": "B2",
    # A3 — psicoestimulantes
    "metilfenidato": "A3", "lisdexanfetamina": "A3",
    # A1/A2 — opioides
    "morfina": "A1", "oxicodona": "A1", "metadona": "A1", "fentanil": "A1",
    "codeina": "A2",
    # C2 — retinoides
    "isotretinoina": "C2", "acitretina": "C2",
    # C5 — anabolizantes
    "testosterona": "C5", "oxandrolona": "C5", "nandrolona": "C5",
}

# Antimicrobianos não são da Portaria 344, mas têm retenção de receita.
ANTIMICROBIALS = {
    "amoxicilina", "azitromicina", "cefalexina", "ciprofloxacino", "levofloxacino",
    "claritromicina", "doxiciclina", "sulfametoxazol", "nitrofurantoina", "metronidazol",
    "clindamicina", "cefuroxima", "ceftriaxona",
}


def lookup_controlled(active_ingredients: list[str]) -> ControlledInfo | None:
    for ai in active_ingredients:
        key = norm(ai)
        if key in CONTROLLED:
            lst = CONTROLLED[key]
            return ControlledInfo(
                list_code=lst,
                substance=key,
                prescription=_PRESCRIPTION[lst],
                online_sale_allowed=False,
                legal_notes=[
                    f"Substância da lista {lst} da Portaria SVS/MS 344/1998 (controle especial).",
                    f"Exige {_PRESCRIPTION[lst]}.",
                    "Venda por meio remoto (internet/telefone/app) com entrega não é permitida "
                    "para medicamentos sujeitos a controle especial (RDC ANVISA 44/2009). "
                    "Compre presencialmente, apresentando a receita.",
                    "Preços e disponibilidade online são exibidos apenas como informação.",
                ],
            )
        if key in ANTIMICROBIALS:
            return ControlledInfo(
                list_code="ANTIMICROBIANO",
                substance=key,
                prescription=_PRESCRIPTION["ANTIMICROBIANO"],
                online_sale_allowed=True,
                legal_notes=[
                    "Antimicrobiano: a farmácia retém a 2ª via da receita (RDC 471/2021).",
                    "Compras online exigem envio/apresentação da receita conforme a loja.",
                ],
            )
    return None
