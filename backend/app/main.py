"""API Encontramed (FastAPI) + entrega do PWA."""
from __future__ import annotations

import logging

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .db import supabase
from .drug.normalizer import parse_query
from .engine.search import SORTS, run_search, sort_offers
from .models import DrugQuery, SearchResponse
from .sources.registry import load_sources

logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)

app = FastAPI(title="Encontramed API", version="0.1.0",
              description="Buscador de medicamentos com classificação rastreável de estoque.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])


class SearchRequest(BaseModel):
    medicine: str = Field(..., min_length=2, max_length=200, examples=["Cloridrato de Clorpromazina 25 mg (Amplictil)"])
    location: str | None = Field(None, max_length=120, examples=["11666-630"])
    sort: str = "relevancia"


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "supabase": supabase.enabled(), "sources": len(load_sources())}


@app.get("/api/sources")
async def sources() -> list[dict]:
    return [{"id": s.id, "name": s.name, "kind": s.kind, "enabled": s.enabled,
             "type": type(s).__name__, "host": s.config.get("host")} for s in load_sources()]


@app.get("/api/parse", response_model=DrugQuery)
async def parse(q: str = Query(..., min_length=2)) -> DrugQuery:
    return parse_query(q)


@app.post("/api/search", response_model=SearchResponse)
async def search(req: SearchRequest, bg: BackgroundTasks) -> SearchResponse:
    if req.sort not in SORTS:
        raise HTTPException(400, f"sort deve ser um de {SORTS}")
    resp = await run_search(req.medicine, req.location)
    if req.sort != "relevancia":
        resp = resp.model_copy(update={
            "local_offers": sort_offers(resp.local_offers, req.sort),
            "online_offers": sort_offers(resp.online_offers, req.sort),
            "related_offers": sort_offers(resp.related_offers, req.sort),
        })
    bg.add_task(supabase.save_search, resp)
    return resp


class WatchRequest(BaseModel):
    medicine: str
    postal_code: str | None = None
    kind: str = Field("estoque", pattern="^(estoque|preco)$")
    target_price: float | None = None
    contact: str = Field(..., description="e-mail ou identificador push")


@app.post("/api/watches", status_code=201)
async def create_watch(req: WatchRequest) -> dict:
    """Alertas (fase 3): grava o pedido; o job de monitoramento ainda será implementado."""
    try:
        return await supabase.add_watch(req.model_dump())
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e


# ---------- PWA ----------
if settings.frontend_dir.exists():
    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(settings.frontend_dir / "index.html")

    @app.get("/sw.js", include_in_schema=False)
    async def sw() -> FileResponse:
        return FileResponse(settings.frontend_dir / "sw.js", media_type="application/javascript",
                            headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})

    app.mount("/", StaticFiles(directory=settings.frontend_dir), name="static")
