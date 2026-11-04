# Encontramed

Buscador de medicamentos: mostra **onde existe** o medicamento, para retirar numa
farmácia da sua cidade ou comprar online com entrega no seu CEP. Cada resultado traz
uma classificação de estoque rastreável (fonte, método e horário da consulta).

> **Prioridade:** encontrar medicamentos, não apenas anúncios de medicamentos.

- Análise de viabilidade, fontes, limitações, legislação e custos: [`docs/VIABILIDADE.md`](docs/VIABILIDADE.md)
- Fontes configuradas: [`backend/sources.yaml`](backend/sources.yaml)
- Esquema do banco: [`supabase/migrations/001_init.sql`](supabase/migrations/001_init.sql)

## Classificação de estoque

| | Significado |
|---|---|
| **Estoque confirmado** | O sistema de pedidos da loja confirmou disponibilidade para o seu CEP ou loja, no horário indicado |
| **Disponibilidade informada** | A loja informa que tem, sem confirmação em tempo real |
| **Consultar farmácia** | Anunciado ou farmácia localizada, sem dado confiável de estoque |
| **Indisponível** | A fonte informa que não há estoque |

## Rodar localmente

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000     # abre o PWA em http://localhost:8000
python -m pytest -q                            # testes
```

Busca real pela linha de comando (precisa de acesso à internet):

```bash
python -m app.cli verify-sources
python -m app.cli buscar "Cloridrato de Clorpromazina 25 mg (Amplictil)" --local 11666-630 --json amplictil.json
```

Variáveis opcionais em [`.env.example`](.env.example): Supabase (persistência) e Google Places (dados mais completos das farmácias).

## Instalar no iPhone

1. Publique a API com HTTPS (o `Dockerfile` funciona em Render, Railway, Fly.io etc.).
2. Abra o endereço no Safari, toque em **Compartilhar** e depois em **Adicionar à Tela de Início**.

## Adicionar uma fonte

- **Loja em plataforma já suportada (VTEX):** acrescente um bloco em `backend/sources.yaml`
  e rode `python -m app.cli verify-sources`.
- **Plataforma ou API nova:** crie uma subclasse de `Source` em `backend/app/sources/` e
  registre o tipo em `registry.SOURCE_TYPES`. Regras: nunca inventar resultado e sempre anexar `Evidence`.

## Estrutura

```
backend/app/
  drug/        normalização (marca, princípio ativo, dose vs. embalagem, controlados)
  geo/         CEP, geocodificação, distância, "como chegar"
  sources/     conectores (vtex, OSM, Google Places, links manuais) + registro
  engine/      orquestração em 2 etapas, classificação de estoque, ordenação
  db/          persistência no Supabase (PostgREST)
  main.py      API FastAPI + entrega do PWA
  cli.py       busca real e verificação de fontes
frontend/      PWA (HTML/CSS/JS, manifest, service worker)
scripts/       importador da tabela CMED/ANVISA
```
