"""Persistência no Supabase via PostgREST (sem SDK extra).

Opcional: se SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY não estiverem
definidas, a API funciona sem persistência. Esquema em
supabase/migrations/001_init.sql.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings
from ..models import SearchResponse

log = logging.getLogger("encontramed.db")


def enabled() -> bool:
    return bool(settings.supabase_url and settings.supabase_key)


def _headers() -> dict[str, str]:
    return {"apikey": settings.supabase_key or "", "Authorization": f"Bearer {settings.supabase_key}",
            "Content-Type": "application/json", "Prefer": "return=minimal"}


async def _post(client: httpx.AsyncClient, table: str, rows: list[dict] | dict) -> None:
    r = await client.post(f"{settings.supabase_url}/rest/v1/{table}", json=rows, headers=_headers())
    r.raise_for_status()


async def save_search(resp: SearchResponse, client: httpx.AsyncClient | None = None) -> bool:
    if not enabled():
        return False
    own = client is None
    client = client or httpx.AsyncClient(timeout=15)
    try:
        loc = resp.location
        await _post(client, "searches", {
            "id": resp.search_id, "created_at": resp.created_at.isoformat(), "query_text": resp.query.raw_text,
            "query": resp.query.model_dump(mode="json"),
            "location_text": loc.raw_text if loc else None, "postal_code": loc.postal_code if loc else None,
            "city": loc.city if loc else None, "state": loc.state if loc else None,
            "expanded_to_online": resp.expanded_to_online, "summary": resp.summary, "warnings": resp.warnings,
        })
        offers = resp.local_offers + resp.online_offers + resp.related_offers
        if offers:
            await _post(client, "offers", [{
                "search_id": resp.search_id, "offer_key": o.id, "channel": o.channel.value,
                "status": o.status.value, "store_name": o.store.name, "chain": o.store.chain,
                "city": o.store.city, "state": o.store.state,
                "product_name": o.product.name if o.product else None,
                "ean": o.product.ean if o.product else None,
                "match_kind": o.match.kind if o.match else None,
                "price": o.price, "shipping_price": o.shipping_price, "shipping_days": o.shipping_days,
                "total_price": o.total_price, "product_url": o.product_url,
                "evidence": [e.model_dump(mode="json") for e in o.evidence],
            } for o in offers])
        await _post(client, "source_runs", [{
            "search_id": resp.search_id, **r.model_dump(mode="json"),
        } for r in resp.source_runs])
        return True
    except Exception as e:  # noqa: BLE001 — persistência não pode derrubar a busca
        log.warning("Falha ao salvar busca no Supabase: %s", e)
        return False
    finally:
        if own:
            await client.aclose()


async def add_watch(payload: dict) -> dict:
    """Cadastro de alerta (volta ao estoque / queda de preço) — processado por job futuro."""
    if not enabled():
        raise RuntimeError("Supabase não configurado.")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{settings.supabase_url}/rest/v1/watches", json=payload,
                              headers={**_headers(), "Prefer": "return=representation"})
        r.raise_for_status()
        return r.json()[0]
