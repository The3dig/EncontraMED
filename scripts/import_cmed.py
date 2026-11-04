"""Importa a tabela CMED/ANVISA (preços máximos de medicamentos) para o dicionário de referência.

Onde obter: portal da ANVISA > CMED > "Listas de preços de medicamentos"
(arquivo "Preço Máximo ao Consumidor"/"PMC", publicado mensalmente em XLS/PDF).
Abra o XLS e salve como CSV (separador ';', UTF-8) e rode:

    python scripts/import_cmed.py caminho/para/cmed.csv

Gera backend/data/cmed_ref.json, carregado automaticamente pelo motor:
  - brands:  marca -> princípio ativo/fabricante (reconhecimento de nome comercial)
  - actives: lista de princípios ativos
  - eans:    EAN -> substância/produto/apresentação/PMC (correspondência exata por código de barras)
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.drug.text import norm, remove_salts  # noqa: E402

COLS = {
    "substance": ["SUBSTÂNCIA", "SUBSTANCIA"],
    "product": ["PRODUTO"],
    "presentation": ["APRESENTAÇÃO", "APRESENTACAO"],
    "lab": ["LABORATÓRIO", "LABORATORIO"],
    "ean": ["EAN 1", "EAN1", "EAN"],
    "type": ["TIPO DE PRODUTO (STATUS DO PRODUTO)", "TIPO DE PRODUTO"],
    "pmc": ["PMC 18 %", "PMC 18%", "PMC 0 %", "PMC 0%"],
}


def _find_header(rows: list[list[str]]) -> int:
    for i, r in enumerate(rows[:80]):
        up = [c.strip().upper() for c in r]
        if any(c in up for c in COLS["substance"]) and "PRODUTO" in up:
            return i
    raise SystemExit("Cabeçalho com 'SUBSTÂNCIA' e 'PRODUTO' não encontrado.")


def _idx(header: list[str], names: list[str]) -> int | None:
    up = [h.strip().upper() for h in header]
    for n in names:
        if n in up:
            return up.index(n)
    return None


def main(path: str) -> None:
    raw = Path(path).read_bytes()
    text = raw.decode("utf-8-sig", errors="replace") if b"\xc3" in raw[:20000] else raw.decode("latin-1")
    rows = list(csv.reader(text.splitlines(), delimiter=";"))
    h = _find_header(rows)
    header = rows[h]
    ix = {k: _idx(header, v) for k, v in COLS.items()}
    brands, actives, eans = {}, set(), {}
    for r in rows[h + 1:]:
        get = lambda k: (r[ix[k]].strip() if ix[k] is not None and ix[k] < len(r) else "")  # noqa: E731
        sub, prod = get("substance"), get("product")
        if not sub or not prod:
            continue
        active, _ = remove_salts(sub.split(";")[0])
        active = active.replace(" ;", " +")
        actives.add(active)
        b = norm(prod)
        if b and b != active and len(b) > 2:
            brands.setdefault(b, {"active": active, "manufacturer": get("lab").title() or None})
        ean = get("ean")
        if ean and ean.isdigit():
            pmc = get("pmc").replace(".", "").replace(",", ".")
            eans[ean] = {"active": active, "product": prod, "presentation": get("presentation"),
                         "laboratory": get("lab"), "type": get("type"),
                         "pmc": float(pmc) if pmc.replace(".", "").isdigit() else None}
    out = ROOT / "backend" / "data" / "cmed_ref.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"brands": brands, "actives": sorted(actives), "eans": eans}, ensure_ascii=False),
                   encoding="utf-8")
    print(f"{len(brands)} marcas, {len(actives)} princípios ativos, {len(eans)} EANs -> {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
