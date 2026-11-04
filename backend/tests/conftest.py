"""Fixtures SINTÉTICAS para testes de parsing/classificação.

Os dados abaixo seguem o formato documentado das APIs (VTEX, Overpass,
ViaCEP), mas os valores são fictícios. Eles servem apenas para testar o
código — nunca são exibidos ao usuário como resultados reais.
"""
from __future__ import annotations

import json

import httpx
import pytest

FAKE_HOST = "loja-teste.example"

CATALOG = [
    {
        "productId": "100", "productName": "Amplictil 25mg 20 Comprimidos Revestidos", "brand": "Sanofi",
        "linkText": "amplictil-25mg-20-comprimidos", "link": f"https://{FAKE_HOST}/amplictil-25mg-20-comprimidos/p",
        "items": [{"itemId": "1001", "name": "Amplictil 25mg 20 Comprimidos Revestidos", "ean": "7890000000011",
                   "sellers": [{"sellerId": "1", "sellerDefault": True,
                                "commertialOffer": {"Price": 15.9, "ListPrice": 18.5, "AvailableQuantity": 30,
                                                    "IsAvailable": True}}]}],
    },
    {
        "productId": "101", "productName": "Amplictil 100mg 20 Comprimidos", "brand": "Sanofi",
        "linkText": "amplictil-100mg",
        "items": [{"itemId": "1002", "name": "Amplictil 100mg 20 Comprimidos",
                   "sellers": [{"sellerId": "1", "commertialOffer": {"Price": 30.0, "AvailableQuantity": 5}}]}],
    },
    {
        "productId": "102", "productName": "Amplictil Gotas 40mg/ml 20ml", "brand": "Sanofi",
        "linkText": "amplictil-gotas",
        "items": [{"itemId": "1003", "name": "Amplictil Gotas 40mg/ml 20ml",
                   "sellers": [{"sellerId": "1", "commertialOffer": {"Price": 25.0, "AvailableQuantity": 3}}]}],
    },
    {
        "productId": "103", "productName": "Cloridrato de Clorpromazina 25mg 200 Comprimidos Genérico",
        "brand": "Cristália", "linkText": "clorpromazina-25mg-200",
        "items": [{"itemId": "1004", "name": "Cloridrato de Clorpromazina 25mg 200 Comprimidos",
                   "sellers": [{"sellerId": "1", "commertialOffer": {"Price": 60.0, "AvailableQuantity": 0,
                                                                     "IsAvailable": False}}]}],
    },
]

PICKUP_LAT, PICKUP_LON = -23.6200, -45.4120


def simulation(body: dict) -> dict:
    items, logistics = [], []
    for i, it in enumerate(body["items"]):
        sku = it["id"]
        avail = {"1001": "available", "1004": "withoutStock"}.get(sku, "available")
        items.append({"id": sku, "requestIndex": i, "availability": avail, "price": 1590, "sellingPrice": 1490,
                      "seller": "1"})
        slas = []
        if avail == "available":
            slas = [
                {"id": "Normal", "name": "Normal", "deliveryChannel": "delivery", "price": 1200, "shippingEstimate": "5bd"},
                {"id": "Expressa", "name": "Expressa", "deliveryChannel": "delivery", "price": 2500, "shippingEstimate": "1bd"},
                {"id": "Retira", "name": "Retire na loja", "deliveryChannel": "pickup-in-point", "price": 0,
                 "shippingEstimate": "2h", "pickupPointId": "1_loja123",
                 "pickupStoreInfo": {"friendlyName": "Loja Teste Centro", "address": {
                     "street": "Rua Exemplo", "number": "100", "neighborhood": "Centro", "city": "Caraguatatuba",
                     "state": "SP", "postalCode": "11660000", "geoCoordinates": [PICKUP_LON, PICKUP_LAT]}}},
            ]
        logistics.append({"itemIndex": i, "slas": slas})
    return {"items": items, "logisticsInfo": logistics, "postalCode": body.get("postalCode")}


OVERPASS = {"elements": [
    {"type": "node", "id": 1, "lat": PICKUP_LAT + 0.0003, "lon": PICKUP_LON,
     "tags": {"amenity": "pharmacy", "name": "Loja Teste Centro", "phone": "+55 12 0000-0000",
              "opening_hours": "Mo-Sa 08:00-22:00", "addr:street": "Rua Exemplo", "addr:housenumber": "100"}},
    {"type": "node", "id": 2, "lat": -23.6400, "lon": -45.4300,
     "tags": {"amenity": "pharmacy", "name": "Farmácia Bairro Teste", "phone": "+55 12 1111-1111"}},
]}

VIACEP = {"cep": "11666-630", "logradouro": "Rua Teste", "bairro": "Bairro", "localidade": "Caraguatatuba",
          "uf": "SP", "ibge": "3510500"}


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "viacep.com.br" in url:
        return httpx.Response(200, json=VIACEP)
    if "brasilapi.com.br" in url:
        return httpx.Response(200, json={"city": "Caraguatatuba", "state": "SP", "location": {
            "coordinates": {"latitude": "-23.6210", "longitude": "-45.4130"}}})
    if "nominatim" in url:
        return httpx.Response(200, json=[{"lat": "-23.62", "lon": "-45.41"}])
    if "overpass" in url:
        return httpx.Response(200, json=OVERPASS)
    if FAKE_HOST in url and "catalog_system" in url:
        return httpx.Response(200, json=CATALOG)
    if FAKE_HOST in url and "simulation" in url:
        return httpx.Response(200, json=simulation(json.loads(request.content)))
    if "bloqueada.example" in url:
        return httpx.Response(403, text="forbidden")
    return httpx.Response(404)


@pytest.fixture
def client():
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def sources():
    from app.sources.local_directories import OsmPharmacies
    from app.sources.manual import ManualLinkSource
    from app.sources.vtex import VtexSource
    return [
        OsmPharmacies(id="osm", name="OSM", url="https://overpass.example/api/interpreter"),
        VtexSource(id="teste", name="Loja Teste", host=FAKE_HOST),
        VtexSource(id="bloq", name="Loja Bloqueada", host="bloqueada.example"),
        ManualLinkSource(id="man", name="Manual", search_url="https://m.example/?q={q}", reason="sem API"),
    ]
