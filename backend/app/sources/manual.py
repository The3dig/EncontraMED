"""Fontes sem integração autorizada/disponível.

Não fazemos raspagem de sites que não oferecem API pública ou que proíbem
coleta automatizada. Em vez de inventar resultados, o sistema apresenta a
limitação e um link direto de consulta (busca já preenchida) e/ou telefone.
"""
from __future__ import annotations

import urllib.parse

from ..models import ManualCheck, SourceRun
from .base import SearchContext, Source, SourceResult


class ManualLinkSource(Source):
    kind = "consulta_manual"

    async def search(self, ctx: SearchContext, run: SourceRun) -> SourceResult:
        term = ctx.query.search_terms[0] if ctx.query.search_terms else ctx.query.raw_text
        url = self.config["search_url"].replace("{q}", urllib.parse.quote(term))
        run.status = "sem_integracao"
        run.message = self.config.get("reason")
        return SourceResult(run=run, manual_checks=[ManualCheck(
            source_id=self.id, name=self.name, url=url,
            reason=self.config.get("reason") or "Sem integração automática disponível.")])
