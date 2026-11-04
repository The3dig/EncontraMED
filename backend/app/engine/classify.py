"""Regra fundamental: classificação de estoque.

Um anúncio ou página de produto NUNCA é, por si só, estoque disponível.

ESTOQUE_CONFIRMADO
    A fonte confirmou, em consulta transacional em tempo real, que o item
    pode ser vendido agora para aquele CEP/loja (ex.: simulação de checkout
    VTEX retornou `available` com opção de entrega/retirada). Sempre com
    horário da consulta.
DISPONIBILIDADE_INFORMADA
    A loja informa disponibilidade (ex.: quantidade > 0 no catálogo), mas não
    foi possível confirmar em tempo real para o CEP/loja.
CONSULTAR_FARMACIA
    Produto anunciado ou farmácia conhecida, sem informação confiável de
    estoque (inclui farmácias locais do OpenStreetMap/Google, que só têm
    endereço/telefone).
INDISPONIVEL
    A fonte informa explicitamente que não há estoque.
"""
from __future__ import annotations

from ..models import StockStatus


def classify_simulation(availability: str | None, has_fulfillment_option: bool) -> tuple[StockStatus, list[str]]:
    a = (availability or "").strip()
    if a == "available" and has_fulfillment_option:
        return StockStatus.CONFIRMADO, [
            "Sistema de pedidos da loja confirmou disponibilidade para o CEP/loja no horário da consulta."]
    if a == "available":
        return StockStatus.INFORMADO, [
            "Loja informa item disponível, mas sem opção de entrega/retirada para o CEP informado."]
    if a in {"withoutStock", "unavailable", "outOfStock"}:
        return StockStatus.INDISPONIVEL, [f"Sistema de pedidos da loja informou: {a}."]
    if a in {"cannotBeDelivered", "cannotBeShipped"}:
        return StockStatus.INFORMADO, [
            f"Loja informou '{a}': pode haver estoque, mas não para entrega neste CEP."]
    return StockStatus.CONSULTAR, [f"Resposta de disponibilidade não conclusiva ({a or 'vazia'})."]


def classify_catalog(available_qty: int | float | None, is_available: bool | None) -> tuple[StockStatus, list[str]]:
    if available_qty is not None:
        if available_qty > 0:
            return StockStatus.INFORMADO, [
                "Catálogo da loja indica quantidade disponível; não confirmado em tempo real para o CEP."]
        return StockStatus.INDISPONIVEL, ["Catálogo da loja indica quantidade zero."]
    if is_available is False:
        return StockStatus.INDISPONIVEL, ["Catálogo da loja indica produto indisponível."]
    if is_available is True:
        return StockStatus.INFORMADO, ["Catálogo da loja marca o produto como disponível (sem quantidade)."]
    return StockStatus.CONSULTAR, ["Produto anunciado sem informação de estoque."]
