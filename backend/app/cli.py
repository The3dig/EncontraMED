"""Linha de comando: busca real e verificação de fontes.

    python -m app.cli buscar "Cloridrato de Clorpromazina 25 mg (Amplictil)" --local 11666-630
    python -m app.cli buscar "Amplictil 25mg" --local 11666-630 --json resultado.json
    python -m app.cli verify-sources
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .drug.normalizer import parse_query
from .engine.search import run_search
from .http import classify_error, make_client
from .models import Offer, SourceRun
from .sources.base import SearchContext
from .sources.registry import load_sources
from .sources.vtex import VtexSource


def _brl(v: float | None) -> str:
    return "—" if v is None else f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _print_offer(o: Offer) -> None:
    s = o.store
    p = o.product.name if o.product else "—"
    print(f"  [{o.status.label.upper()}] {s.name}  {('· ' + str(s.distance_km) + ' km') if s.distance_km is not None else ''}")
    print(f"     Produto: {p}")
    if o.price is not None:
        print(f"     Preço: {_brl(o.price)}  Frete: {_brl(o.shipping_price)}  Total: {_brl(o.total_price)}"
              f"  {o.shipping_label or ''}")
    if s.address:
        print(f"     Endereço: {s.address}, {s.city or ''}")
    if s.phone:
        print(f"     Telefone: {s.phone}")
    if s.opening_hours:
        print(f"     Horário: {s.opening_hours}")
    for w in o.warnings:
        print(f"     ! {w}")
    for e in o.evidence[:2]:
        print(f"     fonte: {e.source_name} · {e.method} · {e.checked_at:%d/%m/%Y %H:%M:%S} UTC · {e.url}")


def _print_runs(runs: list[SourceRun]) -> None:
    print("\nRelatório de fontes:")
    for r in runs:
        print(f"  - {r.source_name:<38} {r.status:<15} {r.offers:>3} ofertas  {r.duration_ms or 0:>5} ms  {r.message or ''}")


async def cmd_buscar(args: argparse.Namespace) -> int:
    resp = await run_search(args.medicamento, args.local, use_cache=False)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            f.write(resp.model_dump_json(indent=2))
        print(f"JSON completo salvo em {args.json}")
    q = resp.query
    print(f"\nEncontramed — busca {resp.search_id} em {resp.created_at:%d/%m/%Y %H:%M:%S} UTC")
    print(f"Medicamento: {q.raw_text}")
    print(f"  princípio ativo: {', '.join(q.active_ingredients) or '—'} · marca: {', '.join(q.brands) or '—'}"
          f" · dosagem: {f'{q.dose_value:g} {q.dose_unit}' if q.dose_value else '—'}")
    if resp.location:
        loc = resp.location
        print(f"Local: {loc.city or '?'}-{loc.state or '?'} CEP {loc.postal_code or '—'} "
              f"({loc.lat}, {loc.lon}) precisão={loc.geocode_precision} fontes={loc.sources}")
    for w in resp.warnings:
        print(f"! {w}")
    print(f"\n=== ETAPA 1 — RETIRADA EM {((resp.location.city if resp.location else None) or 'CIDADE NÃO IDENTIFICADA').upper()} ===")
    for o in resp.local_offers:
        _print_offer(o)
    if not resp.local_offers:
        print("  Nenhuma loja integrada com estoque classificado na cidade.")
    print(f"\n  Farmácias da cidade SEM dados de estoque (ligar para consultar): {len(resp.local_pharmacies_without_data)}")
    for o in resp.local_pharmacies_without_data[: args.max]:
        s = o.store
        print(f"   · {s.name} — {s.address or 's/ endereço'} — {s.phone or 's/ telefone'}"
              f"{' — ' + str(s.distance_km) + ' km' if s.distance_km is not None else ''}")
    print("\n=== ETAPA 2 — COMPRA PELA INTERNET ===")
    if resp.expansion_reason:
        print(f"  ({resp.expansion_reason})")
    for o in resp.online_offers[: args.max]:
        _print_offer(o)
    if resp.related_offers:
        print("\n=== MESMO PRINCÍPIO ATIVO E DOSAGEM (genéricos/similares — troca só com orientação profissional) ===")
        for o in resp.related_offers[: args.max]:
            _print_offer(o)
    if resp.manual_checks:
        print("\n=== FONTES SEM INTEGRAÇÃO (consulta manual) ===")
        for m in resp.manual_checks:
            print(f"  · {m.name}: {m.url}\n      {m.reason}")
    _print_runs(resp.source_runs)
    return 0


async def cmd_verify(args: argparse.Namespace) -> int:
    """Testa cada loja VTEX: catálogo responde? simulação responde?"""
    q = parse_query(args.termo)
    async with make_client() as client:
        ctx = SearchContext(query=q, location=None, client=client)
        for s in load_sources():
            if not isinstance(s, VtexSource):
                continue
            run = SourceRun(source_id=s.id, source_name=s.name, kind=s.kind, status="ok")
            try:
                prods = await s._catalog(ctx, args.termo, run)
                cat = f"catálogo OK ({len(prods)} produtos)"
                sim = "—"
                skus = [{"sku": str(p["items"][0]["itemId"]), "seller": "1"} for p in prods[:1] if p.get("items")]
                if skus:
                    try:
                        data = await s._simulate(ctx, skus, args.cep, run)
                        sim = f"simulação OK (availability={(data.get('items') or [{}])[0].get('availability')})"
                    except Exception as e:  # noqa: BLE001
                        sim = f"simulação FALHOU: {classify_error(e)[1]}"
            except Exception as e:  # noqa: BLE001
                cat, sim = f"catálogo FALHOU: {classify_error(e)[1]}", "—"
            print(f"{s.name:<25} {s.host:<35} {cat} | {sim}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="encontramed")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("buscar", help="Executa uma busca real")
    b.add_argument("medicamento")
    b.add_argument("--local", help="CEP ou 'Cidade - UF'")
    b.add_argument("--json", help="Salvar resposta completa em JSON")
    b.add_argument("--max", type=int, default=30)
    v = sub.add_parser("verify-sources", help="Verifica se as lojas configuradas respondem")
    v.add_argument("--termo", default="dipirona")
    v.add_argument("--cep", default="11666630")
    args = ap.parse_args(argv)
    fn = {"buscar": cmd_buscar, "verify-sources": cmd_verify}[args.cmd]
    return asyncio.run(fn(args))


if __name__ == "__main__":
    sys.exit(main())
