"""Conector genérico para lojas na plataforma VTEX.

Muitas redes de farmácias brasileiras usam VTEX. A plataforma expõe, para a
própria vitrine da loja, dois endpoints públicos (sem autenticação):

  1. Catálogo:  GET /api/catalog_system/pub/products/search?ft=<termo>
     -> produtos, SKUs, preço, `AvailableQuantity`/`IsAvailable`.
  2. Simulação de checkout: POST /api/checkout/pub/orderForms/simulation
     -> para um CEP: disponibilidade do SKU no sistema de pedidos,
        preço final, opções de frete (preço/prazo) e pontos de retirada.

Classificação (ver engine/classify.py):
  - Simulação para o CEP retornou `available` + opção de entrega/retirada
    -> ESTOQUE CONFIRMADO (confirmado pelo sistema de pedidos da loja, no
       horário da consulta, para aquele CEP/loja).
  - Simulação retornou `withoutStock` -> INDISPONÍVEL.
  - Sem simulação (sem CEP ou falha) e catálogo com quantidade > 0
    -> DISPONIBILIDADE INFORMADA.
  - Catálogo sem quantidade -> INDISPONÍVEL; sem dado -> CONSULTAR.

Documentação: https://developers.vtex.com/docs/api-reference/
Uso desses endpoints deve respeitar os termos de cada loja; o caminho
recomendado para produção é um acordo formal (ver docs/VIABILIDADE.md).
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from typing import Any

from ..drug.normalizer import match, parse_product
from ..drug.text import norm
from ..engine.classify import classify_catalog, classify_simulation
from ..geo.location import directions_url, haversine_km
from ..models import Channel, Evidence, Offer, SourceRun, Store, StockStatus, utcnow
from .base import SearchContext, Source, SourceResult

MAX_SKUS_PER_STORE = 12


def parse_shipping_estimate(est: str | None) -> float | None:
    """'3bd' -> 3 dias úteis; '2d' -> 2; '4h' -> 0.17; '30m' -> 0.02."""
    if not est:
        return None
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(bd|d|h|m)\s*$", est)
    if not m:
        return None
    n, u = float(m.group(1)), m.group(2)
    return {"bd": n, "d": n, "h": round(n / 24, 2), "m": round(n / 1440, 2)}[u]


def _fmt_estimate(est: str | None) -> str | None:
    if not est:
        return None
    m = re.match(r"^\s*(\d+)\s*(bd|d|h|m)\s*$", est)
    if not m:
        return est
    n, u = int(m.group(1)), m.group(2)
    return {"bd": f"{n} dia(s) útil(eis)", "d": f"{n} dia(s)", "h": f"{n} hora(s)", "m": f"{n} min"}[u]


def _cents(v: Any) -> float | None:
    return round(v / 100, 2) if isinstance(v, (int, float)) else None


class VtexSource(Source):
    kind = "loja_online"

    @property
    def host(self) -> str:
        return self.config["host"]

    @property
    def sc(self) -> str:
        return str(self.config.get("sales_channel", 1))

    @property
    def base(self) -> str:
        return f"https://{self.host}"

    # ---------- catálogo ----------
    async def _catalog(self, ctx: SearchContext, term: str, run: SourceRun) -> list[dict]:
        url = f"{self.base}/api/catalog_system/pub/products/search"
        params = {"ft": term, "_from": 0, "_to": 29, "sc": self.sc}
        run.urls.append(f"{url}?ft={term}")
        r = await ctx.client.get(url, params=params)
        if r.status_code == 206 or r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else []
        r.raise_for_status()
        return []

    def _extract_skus(self, ctx: SearchContext, products: list[dict]) -> list[dict]:
        out: dict[str, dict] = {}
        for p in products:
            for item in p.get("items") or []:
                sku = str(item.get("itemId"))
                if sku in out:
                    continue
                name = item.get("nameComplete") or item.get("name") or p.get("productName") or ""
                pn = p.get("productName") or ""
                if pn and norm(pn) not in norm(name):
                    # nome do SKU contido no nome do produto -> usa o mais completo; senão concatena
                    name = pn if norm(name) in norm(pn) else f"{pn} {item.get('name') or ''}".strip()
                parsed = parse_product(name, brand=p.get("brand"), manufacturer=p.get("brand"),
                                       ean=item.get("ean") or None,
                                       extra_text=" ".join(p.get("Princípio Ativo", []) or []))
                m = match(ctx.query, parsed)
                if not m.matched:
                    continue
                sellers = item.get("sellers") or []
                seller = next((s for s in sellers if s.get("sellerDefault")), sellers[0] if sellers else {})
                offer = seller.get("commertialOffer") or {}
                link = p.get("link") or (f"{self.base}/{p.get('linkText')}/p" if p.get("linkText") else None)
                out[sku] = {
                    "sku": sku, "seller": str(seller.get("sellerId") or "1"), "parsed": parsed, "match": m,
                    "url": link, "price": offer.get("Price"), "list_price": offer.get("ListPrice"),
                    "available_qty": offer.get("AvailableQuantity"), "is_available": offer.get("IsAvailable"),
                    "product_id": p.get("productId"),
                }
        # Prioriza correspondência exata e maior confiança
        ranked = sorted(out.values(), key=lambda s: (s["match"].kind != "exato", -s["match"].confidence))
        return ranked[:MAX_SKUS_PER_STORE]

    # ---------- simulação ----------
    async def _simulate(self, ctx: SearchContext, skus: list[dict], cep: str, run: SourceRun) -> dict:
        url = f"{self.base}/api/checkout/pub/orderForms/simulation"
        body = {"items": [{"id": s["sku"], "quantity": 1, "seller": s["seller"]} for s in skus],
                "postalCode": cep, "country": "BRA"}
        run.urls.append(f"{url}?sc={self.sc} (CEP {cep})")
        r = await ctx.client.post(url, params={"sc": self.sc}, json=body,
                                  headers={"Content-Type": "application/json"})
        r.raise_for_status()
        return r.json()

    def _offer_id(self, *parts: str) -> str:
        return hashlib.sha1("|".join([self.id, *parts]).encode()).hexdigest()[:16]

    async def search(self, ctx: SearchContext, run: SourceRun) -> SourceResult:
        result = SourceResult(run=run)
        terms = ctx.query.search_terms[:4]
        responses = await asyncio.gather(*(self._catalog(ctx, t, run) for t in terms), return_exceptions=True)
        products: list[dict] = []
        errors = [e for e in responses if isinstance(e, Exception)]
        for resp in responses:
            if isinstance(resp, list):
                products.extend(resp)
        if errors and len(errors) == len(responses):
            raise errors[0]
        skus = self._extract_skus(ctx, products)
        if not skus:
            return result

        checked_at = utcnow()
        loc = ctx.location
        cep = loc.postal_code if loc else None
        sim: dict | None = None
        sim_error: str | None = None
        if cep:
            try:
                sim = await self._simulate(ctx, skus, cep, run)
            except Exception as e:  # noqa: BLE001
                sim_error = f"Simulação de checkout falhou ({e.__class__.__name__}); usando dados do catálogo."
                run.message = sim_error
        controlled = ctx.query.controlled
        online_allowed = controlled is None or controlled.online_sale_allowed
        store_online = Store(name=self.name, chain=self.config.get("chain") or self.name,
                             website=self.base)

        sim_items = {}
        sim_logistics = {}
        pickup_points = {}
        if sim:
            for it in sim.get("items") or []:
                idx = it.get("requestIndex")
                if idx is not None:
                    sim_items[idx] = it
            for li in sim.get("logisticsInfo") or []:
                sim_logistics[li.get("itemIndex")] = li
            for pp in sim.get("pickupPoints") or []:
                pickup_points[pp.get("id")] = pp

        for idx, s in enumerate(skus):
            parsed, m = s["parsed"], s["match"]
            catalog_ev = Evidence(
                source_id=self.id, source_name=self.name, method="vtex_catalog", url=s["url"] or self.base,
                checked_at=checked_at,
                raw={"sku": s["sku"], "AvailableQuantity": s["available_qty"], "IsAvailable": s["is_available"],
                     "Price": s["price"], "ListPrice": s["list_price"]},
            )
            base_warn: list[str] = []
            if controlled and not controlled.online_sale_allowed:
                base_warn.append("Medicamento controlado: compra somente presencial com receita. "
                                 "Preço/disponibilidade online exibidos apenas como informação.")

            it = sim_items.get(idx)
            if sim and it is not None:
                li = sim_logistics.get(idx) or {}
                slas = li.get("slas") or []
                delivery = [x for x in slas if x.get("deliveryChannel", "delivery") == "delivery"]
                pickups = [x for x in slas if x.get("deliveryChannel") == "pickup-in-point"]
                price = _cents(it.get("sellingPrice") if it.get("sellingPrice") is not None else it.get("price"))
                sim_ev = Evidence(
                    source_id=self.id, source_name=self.name, method="vtex_checkout_simulation",
                    url=f"{self.base}/api/checkout/pub/orderForms/simulation", checked_at=checked_at,
                    raw={"sku": s["sku"], "postalCode": cep, "availability": it.get("availability"),
                         "sellingPrice": it.get("sellingPrice"),
                         "slas": [{"name": x.get("name"), "channel": x.get("deliveryChannel"),
                                   "price": x.get("price"), "shippingEstimate": x.get("shippingEstimate")}
                                  for x in slas]},
                )
                # Entrega no CEP
                status, notes = classify_simulation(it.get("availability"), bool(delivery))
                sim_ev.notes = notes
                best = min(delivery, key=lambda x: (x.get("price") or 0)) if delivery else None
                fastest = min(delivery, key=lambda x: parse_shipping_estimate(x.get("shippingEstimate")) or 99) if delivery else None
                warnings = list(base_warn)
                if not delivery and status != StockStatus.INDISPONIVEL:
                    warnings.append(f"A loja não oferece entrega para o CEP {cep}.")
                # Só há retirada (sem entrega): a oferta aparece como retirada, não duplica.
                if delivery or not pickups:
                    result.offers.append(Offer(
                        id=self._offer_id(s["sku"], "entrega"), channel=Channel.ENTREGA, store=store_online,
                        product=parsed, match=m, status=status,
                        price=price if price is not None else s["price"], list_price=s["list_price"],
                        shipping_price=_cents(best.get("price")) if best else None,
                        shipping_days=parse_shipping_estimate(fastest.get("shippingEstimate")) if fastest else None,
                        shipping_label=(f"{best.get('name')} — {_fmt_estimate(best.get('shippingEstimate'))}"
                                        if best else None),
                        product_url=s["url"], purchase_allowed_online=online_allowed and bool(delivery),
                        warnings=warnings, evidence=[sim_ev, catalog_ev],
                    ))
                # Retirada em loja física (ponto de retirada)
                for sla in pickups:
                    info = sla.get("pickupStoreInfo") or {}
                    addr = info.get("address") or {}
                    coords = addr.get("geoCoordinates") or []
                    lon, lat = (coords[0], coords[1]) if len(coords) == 2 else (None, None)
                    dist = (haversine_km(loc.lat, loc.lon, lat, lon)
                            if loc and loc.lat is not None and lat is not None else None)
                    address = ", ".join(x for x in [addr.get("street"), addr.get("number"),
                                                    addr.get("neighborhood")] if x)
                    pstatus, pnotes = classify_simulation(it.get("availability"), True)
                    store = Store(
                        name=info.get("friendlyName") or f"{self.name} (retirada)", chain=self.name,
                        address=address or None, city=addr.get("city"), state=addr.get("state"),
                        postal_code=addr.get("postalCode"), lat=lat, lon=lon,
                        distance_km=round(dist, 2) if dist is not None else None,
                        directions_url=directions_url(lat, lon, address), website=self.base,
                    )
                    pev = sim_ev.model_copy(update={"method": "vtex_checkout_simulation_pickup",
                                                    "notes": pnotes + [f"Ponto de retirada: {store.name}"]})
                    result.offers.append(Offer(
                        id=self._offer_id(s["sku"], "retirada", str(sla.get("pickupPointId") or store.name)),
                        channel=Channel.RETIRADA, store=store, product=parsed, match=m, status=pstatus,
                        price=price if price is not None else s["price"], list_price=s["list_price"],
                        shipping_price=_cents(sla.get("price")), shipping_days=parse_shipping_estimate(
                            sla.get("shippingEstimate")),
                        shipping_label=f"Retirada — pronto em {_fmt_estimate(sla.get('shippingEstimate'))}",
                        product_url=s["url"], purchase_allowed_online=online_allowed,
                        warnings=list(base_warn), evidence=[pev, catalog_ev],
                    ))
            else:
                status, notes = classify_catalog(s["available_qty"], s["is_available"])
                catalog_ev.notes = notes + ([sim_error] if sim_error else []) + (
                    [] if cep else ["Sem CEP: frete e confirmação em tempo real não consultados."])
                result.offers.append(Offer(
                    id=self._offer_id(s["sku"], "catalogo"), channel=Channel.ENTREGA, store=store_online,
                    product=parsed, match=m, status=status, price=s["price"], list_price=s["list_price"],
                    product_url=s["url"], purchase_allowed_online=False, warnings=base_warn,
                    evidence=[catalog_ev],
                ))
        return result
