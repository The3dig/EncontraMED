from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def _bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "sim", "on"}


@dataclass
class Settings:
    user_agent: str = os.environ.get(
        "ENCONTRAMED_USER_AGENT", "Encontramed/0.1 (buscador de medicamentos; +https://github.com/the3dig/encontramed)")
    http_timeout: float = float(os.environ.get("ENCONTRAMED_HTTP_TIMEOUT", "15"))
    max_concurrency: int = int(os.environ.get("ENCONTRAMED_MAX_CONCURRENCY", "8"))
    cache_ttl_seconds: int = int(os.environ.get("ENCONTRAMED_CACHE_TTL", "600"))
    sources_file: Path = Path(os.environ.get("ENCONTRAMED_SOURCES_FILE", BASE_DIR / "sources.yaml"))
    # geolocalização
    nominatim_url: str = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org")
    overpass_url: str = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
    google_places_api_key: str | None = os.environ.get("GOOGLE_PLACES_API_KEY") or None
    # Supabase (opcional): persiste buscas, ofertas e evidências
    supabase_url: str | None = os.environ.get("SUPABASE_URL") or None
    supabase_key: str | None = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or None
    # frontend
    frontend_dir: Path = Path(os.environ.get("ENCONTRAMED_FRONTEND_DIR", BASE_DIR.parent / "frontend"))
    cors_origins: list[str] = field(default_factory=lambda: [
        o.strip() for o in os.environ.get("ENCONTRAMED_CORS_ORIGINS", "*").split(",") if o.strip()])
    debug: bool = _bool(os.environ.get("ENCONTRAMED_DEBUG"))


settings = Settings()
