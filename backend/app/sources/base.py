"""Contrato das fontes de dados.

Para adicionar uma fonte nova:
  1. Se a loja usa uma plataforma já suportada (ex.: VTEX), basta incluí-la
     em `sources.yaml` — nenhum código novo.
  2. Para uma plataforma/API nova, crie uma subclasse de `Source`, implemente
     `search()` e registre o tipo em `registry.SOURCE_TYPES`.

Regras que toda fonte deve seguir:
  - nunca inventar resultados: se a fonte falhar, devolve SourceRun com erro;
  - toda oferta deve ter Evidence (URL, horário, método, campos brutos);
  - a classificação de estoque segue `engine.classify`, nunca "disponível"
    por padrão.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from ..http import classify_error
from ..models import DrugQuery, Location, ManualCheck, Offer, SourceRun


@dataclass
class SearchContext:
    query: DrugQuery
    location: Location | None
    client: httpx.AsyncClient


@dataclass
class SourceResult:
    run: SourceRun
    offers: list[Offer] = field(default_factory=list)
    manual_checks: list[ManualCheck] = field(default_factory=list)


class Source(ABC):
    id: str
    name: str
    kind: str  # "loja_online", "diretorio_local", "consulta_manual"

    def __init__(self, id: str, name: str, **config):
        self.id = id
        self.name = name
        self.config = config

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True))

    @abstractmethod
    async def search(self, ctx: SearchContext, run: SourceRun) -> SourceResult: ...

    async def run(self, ctx: SearchContext) -> SourceResult:
        run = SourceRun(source_id=self.id, source_name=self.name, kind=self.kind, status="ok")
        t0 = time.perf_counter()
        try:
            result = await self.search(ctx, run)
        except Exception as exc:  # noqa: BLE001 — falha de uma fonte não derruba a busca
            status, msg = classify_error(exc)
            run.status, run.message = status, msg
            result = SourceResult(run=run)
        run.duration_ms = int((time.perf_counter() - t0) * 1000)
        run.offers = len(result.offers)
        if run.status == "ok" and not result.offers and not result.manual_checks:
            run.status = "sem_resultado"
        return result
