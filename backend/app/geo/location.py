"""Resolução de localização: CEP (ViaCEP / BrasilAPI) e geocodificação (Nominatim/OSM)."""
from __future__ import annotations

import math
import re
import urllib.parse

import httpx

from ..config import settings
from ..models import Location

CEP_RE = re.compile(r"^\s*(\d{5})-?(\d{3})\s*$")


def normalize_cep(text: str | None) -> str | None:
    if not text:
        return None
    m = CEP_RE.match(text)
    return f"{m.group(1)}{m.group(2)}" if m else None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def directions_url(lat: float | None, lon: float | None, address: str | None = None) -> str | None:
    """Link 'Como chegar' (abre Apple Maps no iPhone; Google Maps nos demais)."""
    if lat is not None and lon is not None:
        return f"https://maps.apple.com/?daddr={lat},{lon}&dirflg=d"
    if address:
        return "https://maps.apple.com/?daddr=" + urllib.parse.quote(address)
    return None


async def _viacep(client: httpx.AsyncClient, cep: str) -> dict | None:
    r = await client.get(f"https://viacep.com.br/ws/{cep}/json/")
    r.raise_for_status()
    data = r.json()
    return None if data.get("erro") else data


async def _brasilapi(client: httpx.AsyncClient, cep: str) -> dict | None:
    r = await client.get(f"https://brasilapi.com.br/api/cep/v2/{cep}")
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


async def _nominatim(client: httpx.AsyncClient, **params) -> tuple[float, float] | None:
    q = {"format": "json", "limit": 1, "countrycodes": "br", **params}
    r = await client.get(f"{settings.nominatim_url}/search", params=q)
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"])


async def resolve_location(client: httpx.AsyncClient, text: str, notes: list[str]) -> Location:
    """Aceita CEP ('11666-630') ou 'Cidade - UF' / 'Cidade'."""
    loc = Location(raw_text=text)
    cep = normalize_cep(text)
    if cep:
        loc.postal_code = cep
        data = None
        try:
            data = await _viacep(client, cep)
            if data:
                loc.street, loc.district = data.get("logradouro") or None, data.get("bairro") or None
                loc.city, loc.state, loc.ibge = data.get("localidade"), data.get("uf"), data.get("ibge")
                loc.sources.append("ViaCEP")
        except Exception as e:  # noqa: BLE001
            notes.append(f"ViaCEP indisponível: {e.__class__.__name__}")
        try:
            b = await _brasilapi(client, cep)
            if b:
                loc.city = loc.city or b.get("city")
                loc.state = loc.state or b.get("state")
                loc.street = loc.street or b.get("street")
                loc.district = loc.district or b.get("neighborhood")
                coords = (b.get("location") or {}).get("coordinates") or {}
                if coords.get("latitude") and coords.get("longitude"):
                    loc.lat, loc.lon = float(coords["latitude"]), float(coords["longitude"])
                    loc.geocode_precision = "cep"
                loc.sources.append("BrasilAPI")
        except Exception as e:  # noqa: BLE001
            notes.append(f"BrasilAPI indisponível: {e.__class__.__name__}")
        if not loc.city:
            notes.append(f"CEP {cep} não encontrado nas bases de CEP consultadas.")
    else:
        parts = re.split(r"\s*[-/,]\s*", text.strip())
        loc.city = parts[0] if parts else text.strip()
        if len(parts) > 1 and len(parts[-1]) == 2:
            loc.state = parts[-1].upper()

    if loc.lat is None and loc.city:
        try:
            coords = None
            if loc.street:
                coords = await _nominatim(client, street=loc.street, city=loc.city, state=loc.state or "")
                if coords:
                    loc.geocode_precision = "logradouro"
            if not coords:
                coords = await _nominatim(client, city=loc.city, state=loc.state or "")
                if coords:
                    loc.geocode_precision = "cidade"
            if coords:
                loc.lat, loc.lon = coords
                loc.sources.append("Nominatim/OpenStreetMap")
        except Exception as e:  # noqa: BLE001
            notes.append(f"Geocodificação (Nominatim) indisponível: {e.__class__.__name__}")
    if loc.lat is None:
        notes.append("Não foi possível obter coordenadas; distâncias não serão calculadas.")
    return loc
