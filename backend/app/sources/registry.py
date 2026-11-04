"""Registro de fontes carregado de `sources.yaml` (adicionar fontes sem reconstruir o sistema)."""
from __future__ import annotations

from pathlib import Path

import yaml

from ..config import settings
from .base import Source
from .local_directories import GooglePlacesPharmacies, OsmPharmacies
from .manual import ManualLinkSource
from .vtex import VtexSource

SOURCE_TYPES: dict[str, type[Source]] = {
    "vtex": VtexSource,
    "osm_overpass": OsmPharmacies,
    "google_places": GooglePlacesPharmacies,
    "manual_link": ManualLinkSource,
}


def load_sources(path: Path | None = None) -> list[Source]:
    data = yaml.safe_load(Path(path or settings.sources_file).read_text(encoding="utf-8")) or {}
    sources: list[Source] = []
    for entry in data.get("sources", []):
        entry = dict(entry)
        t = entry.pop("type")
        cls = SOURCE_TYPES.get(t)
        if not cls:
            raise ValueError(f"Tipo de fonte desconhecido: {t} (fonte {entry.get('id')})")
        sources.append(cls(**entry))
    ids = [s.id for s in sources]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"IDs de fonte duplicados: {dup}")
    return sources
