"""Diretórios de farmácias físicas na cidade.

Estes diretórios dão NOME, ENDEREÇO, TELEFONE, HORÁRIO e COORDENADAS, mas
NÃO têm informação de estoque. Por isso toda farmácia encontrada aqui entra
como CONSULTAR_FARMACIA, a menos que outra fonte (ex.: ponto de retirada
VTEX da mesma loja) confirme estoque — a fusão é feita em engine/search.py.
"""
from __future__ import annotations

import hashlib

from ..geo.location import directions_url, haversine_km
from ..models import Channel, Evidence, Offer, SourceRun, Store, StockStatus, utcnow
from ..config import settings
from .base import SearchContext, Source, SourceResult


def _addr_from_osm(tags: dict) -> str | None:
    parts = [tags.get("addr:street"), tags.get("addr:housenumber"), tags.get("addr:suburb")]
    s = ", ".join(p for p in parts if p)
    return s or tags.get("addr:full")


class OsmPharmacies(Source):
    """Farmácias mapeadas no OpenStreetMap (Overpass API, gratuita, ODbL)."""

    kind = "diretorio_local"

    def _query(self, city: str, state: str | None, lat: float | None, lon: float | None) -> str:
        state_filter = f'area["ISO3166-2"="BR-{state}"]->.s;' if state else ""
        within = "(area.s)" if state else ""
        radius = int(self.config.get("fallback_radius_m", 12000))
        around = (f'nwr["amenity"="pharmacy"](around:{radius},{lat},{lon});' if lat is not None else "")
        city_esc = city.replace('"', '\\"')
        return (
            f'[out:json][timeout:25];{state_filter}'
            f'rel["boundary"="administrative"]["admin_level"="8"]["name"="{city_esc}"]{within};'
            f'map_to_area->.c;'
            f'(nwr["amenity"="pharmacy"](area.c);nwr["healthcare"="pharmacy"](area.c);{around});'
            f'out center tags;'
        )

    async def search(self, ctx: SearchContext, run: SourceRun) -> SourceResult:
        result = SourceResult(run=run)
        loc = ctx.location
        if not loc or not loc.city:
            run.status, run.message = "nao_configurado", "Cidade não identificada."
            return result
        q = self._query(loc.city, loc.state, loc.lat, loc.lon)
        url = self.config.get("url") or settings.overpass_url
        run.urls.append(url)
        r = await ctx.client.post(url, data={"data": q})
        r.raise_for_status()
        checked_at = utcnow()
        for el in r.json().get("elements", []):
            tags = el.get("tags") or {}
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            name = tags.get("name") or tags.get("brand") or "Farmácia (sem nome no mapa)"
            city = tags.get("addr:city") or loc.city
            dist = haversine_km(loc.lat, loc.lon, lat, lon) if (loc.lat is not None and lat is not None) else None
            address = _addr_from_osm(tags)
            store = Store(
                name=name, chain=tags.get("brand"), address=address, city=city, state=loc.state,
                postal_code=tags.get("addr:postcode"), lat=lat, lon=lon,
                phone=tags.get("phone") or tags.get("contact:phone"),
                opening_hours=tags.get("opening_hours"), website=tags.get("website") or tags.get("contact:website"),
                distance_km=round(dist, 2) if dist is not None else None,
                directions_url=directions_url(lat, lon, f"{name}, {address or ''}, {city}"),
            )
            osm_url = f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}"
            result.offers.append(Offer(
                id=hashlib.sha1(osm_url.encode()).hexdigest()[:16], channel=Channel.RETIRADA, store=store,
                status=StockStatus.CONSULTAR,
                warnings=["Farmácia localizada no mapa, sem dados de estoque. Ligue antes de ir."],
                evidence=[Evidence(source_id=self.id, source_name=self.name, method="osm_overpass", url=osm_url,
                                   checked_at=checked_at, raw={k: v for k, v in tags.items() if not k.startswith("source")},
                                   notes=["Diretório de estabelecimentos: não informa estoque."])],
            ))
        return result


class GooglePlacesPharmacies(Source):
    """Google Places API (New) — Text Search. Requer GOOGLE_PLACES_API_KEY (pago, com cota gratuita)."""

    kind = "diretorio_local"
    URL = "https://places.googleapis.com/v1/places:searchText"
    FIELDS = ("places.id,places.displayName,places.formattedAddress,places.location,"
              "places.nationalPhoneNumber,places.regularOpeningHours.weekdayDescriptions,"
              "places.currentOpeningHours.openNow,places.websiteUri,places.googleMapsUri,places.businessStatus")

    @property
    def enabled(self) -> bool:
        return bool(super().enabled and settings.google_places_api_key)

    async def search(self, ctx: SearchContext, run: SourceRun) -> SourceResult:
        result = SourceResult(run=run)
        loc = ctx.location
        if not settings.google_places_api_key:
            run.status, run.message = "nao_configurado", "Defina GOOGLE_PLACES_API_KEY para ativar."
            return result
        if not loc or not loc.city:
            run.status, run.message = "nao_configurado", "Cidade não identificada."
            return result
        body: dict = {"textQuery": f"farmácia em {loc.city} {loc.state or ''}".strip(),
                      "includedType": "pharmacy", "languageCode": "pt-BR", "regionCode": "BR", "pageSize": 20}
        if loc.lat is not None:
            body["locationBias"] = {"circle": {"center": {"latitude": loc.lat, "longitude": loc.lon},
                                               "radius": 15000.0}}
        run.urls.append(self.URL)
        r = await ctx.client.post(self.URL, json=body, headers={
            "X-Goog-Api-Key": settings.google_places_api_key, "X-Goog-FieldMask": self.FIELDS})
        r.raise_for_status()
        checked_at = utcnow()
        for p in r.json().get("places", []):
            if p.get("businessStatus") and p["businessStatus"] != "OPERATIONAL":
                continue
            lat = (p.get("location") or {}).get("latitude")
            lon = (p.get("location") or {}).get("longitude")
            dist = haversine_km(loc.lat, loc.lon, lat, lon) if (loc.lat is not None and lat is not None) else None
            hours = (p.get("regularOpeningHours") or {}).get("weekdayDescriptions")
            store = Store(
                name=(p.get("displayName") or {}).get("text") or "Farmácia", address=p.get("formattedAddress"),
                city=loc.city, state=loc.state, lat=lat, lon=lon, phone=p.get("nationalPhoneNumber"),
                opening_hours="; ".join(hours) if hours else None, website=p.get("websiteUri"),
                distance_km=round(dist, 2) if dist is not None else None,
                directions_url=directions_url(lat, lon, p.get("formattedAddress")),
            )
            result.offers.append(Offer(
                id=hashlib.sha1(("gp" + p.get("id", "")).encode()).hexdigest()[:16], channel=Channel.RETIRADA,
                store=store, status=StockStatus.CONSULTAR,
                warnings=["Farmácia localizada, sem dados de estoque. Ligue antes de ir."],
                evidence=[Evidence(source_id=self.id, source_name=self.name, method="google_places_text_search",
                                   url=p.get("googleMapsUri") or self.URL, checked_at=checked_at,
                                   raw={"place_id": p.get("id"),
                                        "openNow": (p.get("currentOpeningHours") or {}).get("openNow")},
                                   notes=["Diretório de estabelecimentos: não informa estoque."])],
            ))
        return result
