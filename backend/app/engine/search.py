"""Orquestrador da busca.

Etapa 1 — retirada presencial na cidade:
    farmácias físicas (diretórios) + pontos de retirada das lojas online
    localizados na cidade/raio, com estoque classificado.
Etapa 2 — compra pela internet:
    lojas online que entregam no CEP (frete, prazo, total).
    A expansão é sinalizada quando a Etapa 1 não encontra estoque
    confirmado/informado na cidade. Para medicamentos controlados, a etapa 2
    é apenas informativa (venda remota não permitida).

Todas as fontes rodam em paralelo; falha de uma fonte não derruba a busca e
fica registrada em `source_runs`.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Iterable

import httpx

from ..config import settings
from ..drug.normalizer import parse_query
from ..drug.text import norm
from ..geo.location import haversine_km, resolve_location
from ..http import make_client
from ..models import Channel, Offer, SearchResponse, SourceRun, StockStatus
from ..sources.base import SearchContext, Source, SourceResult
from ..sources.registry import load_sources

LOCAL_RADIUS_KM = 25.0
SAME_PLACE_M = 150.0

SORTS = ("relevancia", "proximos", "preco", "entrega", "confirmado")


def sort_offers(offers: Iterable[Offer], mode: str = "relevancia") -> list[Offer]:
    big = 1e9

    def price(o: Offer) -> float:
        return o.total_price if o.total_price is not None else (o.price if o.price is not None else big)

    def dist(o: Offer) -> float:
        return o.store.distance_km if o.store.distance_km is not None else big

    def days(o: Offer) -> float:
        if o.channel == Channel.RETIRADA:
            return o.shipping_days if o.shipping_days is not None else 0.0
        return o.shipping_days if o.shipping_days is not None else big

    keys = {
        # 1) estoque confirmado 2) próximas 3) com entrega 4) menor total 5) distância/prazo
        "relevancia": lambda o: (o.status.rank, o.channel != Channel.RETIRADA, price(o), dist(o), days(o)),
        "proximos": lambda o: (dist(o), o.status.rank, price(o)),
        "preco": lambda o: (o.status == StockStatus.INDISPONIVEL, price(o), o.status.rank),
        "entrega": lambda o: (o.status == StockStatus.INDISPONIVEL, days(o), o.status.rank, price(o)),
        "confirmado": lambda o: (o.status.rank, dist(o), price(o)),
    }
    return sorted(offers, key=keys.get(mode, keys["relevancia"]))


def _near(a: Offer, b: Offer, meters: float) -> bool:
    if None in (a.store.lat, a.store.lon, b.store.lat, b.store.lon):
        return False
    return haversine_km(a.store.lat, a.store.lon, b.store.lat, b.store.lon) * 1000 <= meters


def _dedupe_directory(pharmacies: list[Offer]) -> list[Offer]:
    out: list[Offer] = []
    for p in pharmacies:
        dup = next((o for o in out if _near(o, p, 80) and
                    (norm(o.store.name)[:6] == norm(p.store.name)[:6] or not o.store.name)), None)
        if dup:
            # completa campos faltantes e soma evidências
            for f in ("phone", "opening_hours", "address", "website"):
                if not getattr(dup.store, f) and getattr(p.store, f):
                    setattr(dup.store, f, getattr(p.store, f))
            dup.evidence.extend(p.evidence)
        else:
            out.append(p)
    return out


def _is_local(o: Offer, city: str | None) -> bool:
    if city and o.store.city and norm(o.store.city) == norm(city):
        return True
    return o.store.distance_km is not None and o.store.distance_km <= LOCAL_RADIUS_KM


class _Cache:
    def __init__(self) -> None:
        self._d: dict[tuple, tuple[float, SearchResponse]] = {}

    def get(self, key: tuple) -> SearchResponse | None:
        v = self._d.get(key)
        if v and time.time() - v[0] < settings.cache_ttl_seconds:
            return v[1]
        return None

    def set(self, key: tuple, value: SearchResponse) -> None:
        self._d[key] = (time.time(), value)
        if len(self._d) > 500:
            for k in sorted(self._d, key=lambda k: self._d[k][0])[:100]:
                self._d.pop(k, None)


cache = _Cache()


async def run_search(
    medicine: str,
    location_text: str | None,
    *,
    sources: list[Source] | None = None,
    client: httpx.AsyncClient | None = None,
    use_cache: bool = True,
) -> SearchResponse:
    key = (norm(medicine), norm(location_text or ""))
    if use_cache and (hit := cache.get(key)):
        return hit

    own_client = client is None
    client = client or make_client()
    try:
        resp = await _run(medicine, location_text, sources or load_sources(), client)
    finally:
        if own_client:
            await client.aclose()
    if use_cache:
        cache.set(key, resp)
    return resp


async def _run(medicine: str, location_text: str | None, sources: list[Source],
               client: httpx.AsyncClient) -> SearchResponse:
    warnings: list[str] = []
    query = parse_query(medicine)
    if query.controlled:
        warnings.extend(query.controlled.legal_notes)
    if not query.brands and not any(len(a.split()) == 1 for a in query.active_ingredients):
        warnings.append("Termo não reconhecido no dicionário de referência; busca feita por texto livre.")
    if query.dose_value is None:
        warnings.append("Dosagem não informada: serão mostradas todas as dosagens encontradas.")

    location = await resolve_location(client, location_text, warnings) if location_text else None
    ctx = SearchContext(query=query, location=location, client=client)

    sem = asyncio.Semaphore(settings.max_concurrency)

    async def guarded(s: Source) -> SourceResult:
        async with sem:
            return await s.run(ctx)

    active = [s for s in sources if s.enabled]
    results = await asyncio.gather(*(guarded(s) for s in active))

    resp = SearchResponse(search_id=uuid.uuid4().hex, query=query, location=location, warnings=warnings)
    directory: list[Offer] = []
    store_offers: list[Offer] = []
    for s, res in zip(active, results):
        resp.source_runs.append(res.run)
        resp.manual_checks.extend(res.manual_checks)
        (directory if s.kind == "diretorio_local" else store_offers).extend(res.offers)
    skipped = [s for s in sources if not s.enabled]
    for s in skipped:
        resp.source_runs.append(SourceRun(source_id=s.id, source_name=s.name, kind=s.kind,
                                          status="nao_configurado", message="Fonte desativada ou sem credencial."))

    directory = _dedupe_directory(directory)
    city = location.city if location else None

    local, online, related = [], [], []
    for o in store_offers:
        is_related = o.match is not None and o.match.kind == "mesmo_principio_ativo"
        if o.channel == Channel.RETIRADA:
            if not _is_local(o, city):
                continue  # ponto de retirada fora da região: não útil para retirada
            # funde com a farmácia do diretório (mesmo endereço) para herdar telefone/horário
            twin = next((d for d in directory if _near(d, o, SAME_PLACE_M)), None)
            if twin:
                o.store.phone = o.store.phone or twin.store.phone
                o.store.opening_hours = o.store.opening_hours or twin.store.opening_hours
                o.evidence.extend(twin.evidence)
                if not is_related:
                    directory.remove(twin)
            (related if is_related else local).append(o)
        else:
            (related if is_related else online).append(o)

    resp.local_offers = sort_offers(local)
    resp.online_offers = sort_offers(online)
    resp.related_offers = sort_offers(related)
    resp.local_pharmacies_without_data = sort_offers(directory, "proximos")

    found_local = any(o.status in (StockStatus.CONFIRMADO, StockStatus.INFORMADO) for o in local)
    resp.expanded_to_online = not found_local
    if not found_local:
        resp.expansion_reason = (
            f"Nenhuma farmácia {'em ' + city if city else 'na região'} com estoque confirmado ou informado "
            "pelas fontes integradas. Pesquisa expandida para lojas online que entregam no CEP.")
    if query.controlled and not query.controlled.online_sale_allowed:
        resp.warnings.append("Etapa online exibida somente como referência de preço/disponibilidade: "
                             "este medicamento não pode ser comprado com entrega.")
    if location and not location.postal_code:
        resp.warnings.append("Informe o CEP para calcular frete, prazo e confirmar estoque em tempo real.")

    def count(lst: list[Offer]) -> dict[str, int]:
        return {s.value: sum(1 for o in lst if o.status == s) for s in StockStatus}

    priced = [o for o in online if o.total_price is not None and o.status != StockStatus.INDISPONIVEL]
    resp.summary = {
        "local": count(local),
        "online": count(online),
        "related": count(related),
        "local_pharmacies_without_data": len(directory),
        "manual_checks": len(resp.manual_checks),
        "sources_ok": sum(1 for r in resp.source_runs if r.status in ("ok", "sem_resultado")),
        "sources_failed": sum(1 for r in resp.source_runs if r.status in ("erro", "bloqueado")),
        "best_total_online": min((o.total_price for o in priced), default=None),
    }
    return resp
