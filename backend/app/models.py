"""Modelos de dados do Encontramed.

Toda oferta carrega a sua *evidência*: de onde veio, quando foi consultada,
por qual método e quais campos da fonte sustentam a classificação de estoque.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StockStatus(str, Enum):
    """As quatro classificações de estoque (regra fundamental do projeto)."""

    CONFIRMADO = "ESTOQUE_CONFIRMADO"
    INFORMADO = "DISPONIBILIDADE_INFORMADA"
    CONSULTAR = "CONSULTAR_FARMACIA"
    INDISPONIVEL = "INDISPONIVEL"

    @property
    def label(self) -> str:
        return {
            "ESTOQUE_CONFIRMADO": "Estoque confirmado",
            "DISPONIBILIDADE_INFORMADA": "Disponibilidade informada",
            "CONSULTAR_FARMACIA": "Consultar farmácia",
            "INDISPONIVEL": "Indisponível",
        }[self.value]

    @property
    def rank(self) -> int:
        """Menor = melhor. Usado na ordenação padrão."""
        return {
            "ESTOQUE_CONFIRMADO": 0,
            "DISPONIBILIDADE_INFORMADA": 1,
            "CONSULTAR_FARMACIA": 2,
            "INDISPONIVEL": 3,
        }[self.value]


class Channel(str, Enum):
    RETIRADA = "retirada"  # retirada presencial na cidade
    ENTREGA = "entrega"  # compra online com entrega no CEP
    CONSULTA = "consulta"  # apenas link/telefone para consulta manual


class Evidence(BaseModel):
    """Rastreabilidade: o que a fonte disse, quando e como."""

    source_id: str
    source_name: str
    method: str  # ex.: "vtex_checkout_simulation", "vtex_catalog", "osm_overpass"
    url: str
    checked_at: datetime = Field(default_factory=utcnow)
    raw: dict[str, Any] = Field(default_factory=dict)  # campos brutos relevantes
    notes: list[str] = Field(default_factory=list)


class DrugQuery(BaseModel):
    """Consulta normalizada a partir do texto digitado."""

    raw_text: str
    active_ingredients: list[str] = Field(default_factory=list)  # sem sal (ex.: "clorpromazina")
    salt: str | None = None  # ex.: "cloridrato"
    brands: list[str] = Field(default_factory=list)  # ex.: ["amplictil"]
    dose_value: float | None = None  # dosagem por unidade (ex.: 25)
    dose_unit: str | None = None  # "mg", "mcg", "g", "ui"
    concentration: str | None = None  # ex.: "40mg/ml" (formas líquidas)
    form: str | None = None  # "comprimido", "solucao", "injetavel" ...
    manufacturer: str | None = None
    controlled: "ControlledInfo | None" = None
    search_terms: list[str] = Field(default_factory=list)  # termos enviados às fontes


class ControlledInfo(BaseModel):
    list_code: str  # ex.: "C1"
    substance: str
    prescription: str  # tipo de receita exigida
    online_sale_allowed: bool
    legal_notes: list[str] = Field(default_factory=list)


class ParsedProduct(BaseModel):
    """Produto de uma fonte, interpretado."""

    name: str
    active_ingredients: list[str] = Field(default_factory=list)
    brand: str | None = None
    manufacturer: str | None = None
    dose_value: float | None = None
    dose_unit: str | None = None
    concentration: str | None = None
    pack_quantity: int | None = None  # nº de comprimidos/unidades na embalagem
    form: str | None = None
    ean: str | None = None


class MatchResult(BaseModel):
    matched: bool
    kind: str  # "exato" (marca+dose), "mesmo_principio_ativo", "nao_corresponde"
    confidence: float
    reasons: list[str] = Field(default_factory=list)


class Store(BaseModel):
    name: str
    chain: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    lat: float | None = None
    lon: float | None = None
    phone: str | None = None
    opening_hours: str | None = None
    website: str | None = None
    distance_km: float | None = None
    directions_url: str | None = None


class Offer(BaseModel):
    id: str
    channel: Channel
    store: Store
    product: ParsedProduct | None = None
    match: MatchResult | None = None
    status: StockStatus
    status_label: str = ""
    price: float | None = None  # preço do produto (R$)
    list_price: float | None = None
    shipping_price: float | None = None
    shipping_days: float | None = None  # prazo estimado em dias úteis
    shipping_label: str | None = None
    total_price: float | None = None
    product_url: str | None = None
    purchase_allowed_online: bool = True
    warnings: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:  # noqa: D401
        self.status_label = self.status.label
        if self.total_price is None and self.price is not None:
            if self.channel == Channel.ENTREGA and self.shipping_price is not None:
                self.total_price = round(self.price + self.shipping_price, 2)
            elif self.channel == Channel.RETIRADA:
                self.total_price = self.price


class SourceRun(BaseModel):
    """Relatório de execução de cada fonte (sucesso, erro, bloqueio)."""

    source_id: str
    source_name: str
    kind: str
    status: str  # "ok", "sem_resultado", "erro", "bloqueado", "nao_configurado", "sem_integracao"
    message: str | None = None
    duration_ms: int | None = None
    urls: list[str] = Field(default_factory=list)
    offers: int = 0
    started_at: datetime = Field(default_factory=utcnow)


class Location(BaseModel):
    raw_text: str
    postal_code: str | None = None
    street: str | None = None
    district: str | None = None
    city: str | None = None
    state: str | None = None
    ibge: str | None = None
    lat: float | None = None
    lon: float | None = None
    geocode_precision: str | None = None  # "cep", "logradouro", "cidade"
    sources: list[str] = Field(default_factory=list)


class ManualCheck(BaseModel):
    """Fonte sem integração: alternativa de consulta apresentada ao usuário."""

    source_id: str
    name: str
    url: str
    reason: str


class SearchResponse(BaseModel):
    search_id: str
    created_at: datetime = Field(default_factory=utcnow)
    query: DrugQuery
    location: Location | None
    local_offers: list[Offer] = Field(default_factory=list)
    online_offers: list[Offer] = Field(default_factory=list)
    related_offers: list[Offer] = Field(default_factory=list)  # mesmo princípio ativo/dose (genéricos/similares)
    local_pharmacies_without_data: list[Offer] = Field(default_factory=list)
    manual_checks: list[ManualCheck] = Field(default_factory=list)
    expanded_to_online: bool = False
    expansion_reason: str | None = None
    source_runs: list[SourceRun] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


DrugQuery.model_rebuild()
