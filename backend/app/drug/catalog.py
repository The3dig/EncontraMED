"""Dicionário de referência marca -> princípio ativo.

Fonte primária recomendada: tabela CMED/ANVISA (preços máximos), que contém
substância, produto (marca), apresentação, laboratório e EAN de TODOS os
medicamentos com preço regulado no Brasil. Importe-a com:

    python scripts/import_cmed.py caminho/para/xls_conformidade.csv

O arquivo gerado (data/cmed_ref.json) é carregado automaticamente.
Sem ele, usamos o pequeno dicionário embutido abaixo (seed).
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from .text import norm, remove_salts

# Seed mínimo (marca -> (princípio ativo, fabricante)). Ampliado via CMED.
SEED_BRANDS: dict[str, tuple[str, str | None]] = {
    "amplictil": ("clorpromazina", "Sanofi"),
    "longactil": ("clorpromazina", "Cristália"),
    "haldol": ("haloperidol", "Janssen"),
    "neozine": ("levomepromazina", "Sanofi"),
    "rivotril": ("clonazepam", "Roche"),
    "frontal": ("alprazolam", "Pfizer"),
    "lexotan": ("bromazepam", "Roche"),
    "valium": ("diazepam", "Roche"),
    "tegretol": ("carbamazepina", "Novartis"),
    "depakote": ("divalproato", "Abbott"),
    "depakene": ("acido valproico", "Abbott"),
    "risperdal": ("risperidona", "Janssen"),
    "seroquel": ("quetiapina", "AstraZeneca"),
    "zyprexa": ("olanzapina", "Lilly"),
    "leponex": ("clozapina", "Novartis"),
    "prozac": ("fluoxetina", "Lilly"),
    "zoloft": ("sertralina", "Pfizer"),
    "lexapro": ("escitalopram", "Lundbeck"),
    "ritalina": ("metilfenidato", "Novartis"),
    "venvanse": ("lisdexanfetamina", "Takeda"),
    "puran t4": ("levotiroxina", "Sanofi"),
    "synthroid": ("levotiroxina", "Abbott"),
    "glifage": ("metformina", "Merck"),
    "losartana": ("losartana", None),
    "tylenol": ("paracetamol", "Kenvue"),
    "dorflex": ("dipirona + orfenadrina + cafeina", "Sanofi"),
    "novalgina": ("dipirona", "Sanofi"),
    "aradois": ("losartana", "Biolab"),
    "selozok": ("metoprolol", "AstraZeneca"),
    "ozempic": ("semaglutida", "Novo Nordisk"),
}

# Princípios ativos conhecidos (para reconhecer texto sem marca).
SEED_ACTIVES = sorted({a for a, _ in SEED_BRANDS.values()} | {
    "clorpromazina", "haloperidol", "dipirona", "paracetamol", "ibuprofeno", "amoxicilina",
    "losartana", "metformina", "omeprazol", "sinvastatina", "atenolol", "captopril",
    "enalapril", "hidroclorotiazida", "anlodipino", "levotiroxina", "prednisona",
})

DATA_DIR = Path(os.environ.get("ENCONTRAMED_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))


@lru_cache(maxsize=1)
def reference() -> dict:
    """Carrega CMED importada (se existir) + seed."""
    brands: dict[str, dict] = {
        b: {"active": a, "manufacturer": m, "source": "seed"} for b, (a, m) in SEED_BRANDS.items()
    }
    actives = set(SEED_ACTIVES)
    eans: dict[str, dict] = {}
    path = DATA_DIR / "cmed_ref.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        for b, info in data.get("brands", {}).items():
            brands.setdefault(b, {**info, "source": "cmed"})
        actives |= set(data.get("actives", []))
        eans = data.get("eans", {})
    return {"brands": brands, "actives": sorted(actives, key=len, reverse=True), "eans": eans}


def brand_to_active(brand: str) -> tuple[str | None, str | None]:
    info = reference()["brands"].get(norm(brand))
    if not info:
        return None, None
    return info["active"], info.get("manufacturer")


def find_brands(text: str) -> list[str]:
    t = f" {norm(text)} "
    return [b for b in reference()["brands"] if f" {b} " in t]


def find_actives(text: str) -> list[str]:
    t, _ = remove_salts(text)
    t = f" {t} "
    found = []
    for a in reference()["actives"]:
        if f" {a} " in t and not any(a in f for f in found):
            found.append(a)
    return found
