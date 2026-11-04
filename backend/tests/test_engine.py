import pytest

from app.engine.classify import classify_catalog, classify_simulation
from app.engine.search import run_search, sort_offers
from app.models import Channel, StockStatus
from app.sources.vtex import parse_shipping_estimate

Q = "Cloridrato de Clorpromazina 25 mg (Amplictil)"


def test_classification_rules():
    assert classify_simulation("available", True)[0] == StockStatus.CONFIRMADO
    assert classify_simulation("available", False)[0] == StockStatus.INFORMADO
    assert classify_simulation("withoutStock", True)[0] == StockStatus.INDISPONIVEL
    assert classify_simulation("cannotBeDelivered", False)[0] == StockStatus.INFORMADO
    assert classify_simulation(None, False)[0] == StockStatus.CONSULTAR
    # anúncio sem dado de estoque nunca vira disponível
    assert classify_catalog(None, None)[0] == StockStatus.CONSULTAR
    assert classify_catalog(10, True)[0] == StockStatus.INFORMADO  # catálogo != confirmado
    assert classify_catalog(0, True)[0] == StockStatus.INDISPONIVEL


def test_shipping_estimate():
    assert parse_shipping_estimate("3bd") == 3
    assert parse_shipping_estimate("2h") == 0.08
    assert parse_shipping_estimate("x") is None


@pytest.mark.asyncio
async def test_full_search(client, sources):
    r = await run_search(Q, "11666-630", sources=sources, client=client, use_cache=False)

    assert r.location.city == "Caraguatatuba" and r.location.geocode_precision == "cep"

    # Etapa 1: ponto de retirada confirmado, fundido com a farmácia do mapa (telefone/horário herdados)
    assert len(r.local_offers) == 1
    lo = r.local_offers[0]
    assert lo.channel == Channel.RETIRADA and lo.status == StockStatus.CONFIRMADO
    assert lo.store.phone == "+55 12 0000-0000" and lo.store.opening_hours
    assert lo.store.distance_km is not None and lo.store.directions_url
    assert any(e.method == "vtex_checkout_simulation_pickup" for e in lo.evidence)
    assert all(e.checked_at for e in lo.evidence)
    # a outra farmácia do mapa fica como "consultar"
    assert [p.store.name for p in r.local_pharmacies_without_data] == ["Farmácia Bairro Teste"]
    assert r.local_pharmacies_without_data[0].status == StockStatus.CONSULTAR
    assert r.expanded_to_online is False

    # Etapa 2: só o SKU de 25mg da marca; 100mg e gotas excluídos
    names = [o.product.name for o in r.online_offers]
    assert names == ["Amplictil 25mg 20 Comprimidos Revestidos"]
    on = r.online_offers[0]
    assert on.status == StockStatus.CONFIRMADO
    assert on.price == 14.90 and on.shipping_price == 12.00 and on.total_price == 26.90
    assert on.shipping_days == 1  # opção mais rápida
    # controlado: sem compra online
    assert on.purchase_allowed_online is False
    assert any("controlado" in w.lower() for w in on.warnings)

    # genérico com estoque zero: separado e indisponível
    assert len(r.related_offers) == 1
    assert r.related_offers[0].status == StockStatus.INDISPONIVEL
    assert r.related_offers[0].match.kind == "mesmo_principio_ativo"
    assert r.related_offers[0].product.name == "Cloridrato de Clorpromazina 25mg 200 Comprimidos Genérico"

    runs = {x.source_id: x for x in r.source_runs}
    assert runs["bloq"].status == "bloqueado"
    assert runs["man"].status == "sem_integracao"
    assert r.manual_checks and r.manual_checks[0].url.startswith("https://m.example/?q=amplictil")


@pytest.mark.asyncio
async def test_without_cep_uses_catalog_only(client, sources):
    r = await run_search("Amplictil 25mg", "Caraguatatuba - SP", sources=sources, client=client, use_cache=False)
    on = r.online_offers[0]
    assert on.status == StockStatus.INFORMADO  # sem CEP não há confirmação em tempo real
    assert on.shipping_price is None
    assert r.expanded_to_online is True
    assert any("CEP" in w for w in r.warnings)


def test_sort_modes():
    from app.models import Offer, Store
    a = Offer(id="a", channel=Channel.ENTREGA, store=Store(name="A"), status=StockStatus.INFORMADO,
              price=10, shipping_price=5, shipping_days=2)
    b = Offer(id="b", channel=Channel.ENTREGA, store=Store(name="B"), status=StockStatus.CONFIRMADO,
              price=20, shipping_price=10, shipping_days=1)
    c = Offer(id="c", channel=Channel.RETIRADA, store=Store(name="C", distance_km=1.2),
              status=StockStatus.CONSULTAR)
    assert [o.id for o in sort_offers([a, b, c])] == ["b", "a", "c"]
    assert [o.id for o in sort_offers([a, b, c], "preco")][0] == "a"
    assert [o.id for o in sort_offers([a, b], "entrega")][0] == "b"
    assert [o.id for o in sort_offers([a, b, c], "proximos")][0] == "c"
