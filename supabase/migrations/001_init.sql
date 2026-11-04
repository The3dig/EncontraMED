-- Encontramed — esquema inicial (Supabase / PostgreSQL)
-- Aplicar: Supabase Dashboard > SQL Editor, ou `supabase db push`.

create extension if not exists pgcrypto;

-- Cada busca realizada (histórico e auditoria)
create table if not exists public.searches (
  id               text primary key,
  created_at       timestamptz not null default now(),
  query_text       text not null,
  query            jsonb not null,           -- DrugQuery normalizada
  location_text    text,
  postal_code      text,
  city             text,
  state            text,
  expanded_to_online boolean not null default false,
  summary          jsonb not null default '{}',
  warnings         jsonb not null default '[]'
);
create index if not exists searches_created_idx on public.searches (created_at desc);
create index if not exists searches_city_idx on public.searches (state, city);

-- Ofertas encontradas, com a evidência que sustenta a classificação de estoque
create table if not exists public.offers (
  id             bigint generated always as identity primary key,
  search_id      text not null references public.searches(id) on delete cascade,
  offer_key      text not null,
  channel        text not null check (channel in ('retirada','entrega','consulta')),
  status         text not null check (status in ('ESTOQUE_CONFIRMADO','DISPONIBILIDADE_INFORMADA','CONSULTAR_FARMACIA','INDISPONIVEL')),
  store_name     text not null,
  chain          text,
  city           text,
  state          text,
  product_name   text,
  ean            text,
  match_kind     text,
  price          numeric(10,2),
  shipping_price numeric(10,2),
  shipping_days  numeric(6,2),
  total_price    numeric(10,2),
  product_url    text,
  evidence       jsonb not null default '[]',   -- [{source_id, method, url, checked_at, raw, notes}]
  created_at     timestamptz not null default now()
);
create index if not exists offers_search_idx on public.offers (search_id);
create index if not exists offers_ean_idx on public.offers (ean, created_at desc);
create index if not exists offers_product_idx on public.offers (lower(product_name), created_at desc);

-- Relatório de execução de cada fonte em cada busca
create table if not exists public.source_runs (
  id           bigint generated always as identity primary key,
  search_id    text not null references public.searches(id) on delete cascade,
  source_id    text not null,
  source_name  text not null,
  kind         text not null,
  status       text not null,
  message      text,
  duration_ms  integer,
  urls         jsonb not null default '[]',
  offers       integer not null default 0,
  started_at   timestamptz not null default now()
);
create index if not exists source_runs_source_idx on public.source_runs (source_id, started_at desc);

-- Alertas (fase 3): volta ao estoque / queda de preço / medicamento difícil de achar
create table if not exists public.watches (
  id            uuid primary key default gen_random_uuid(),
  created_at    timestamptz not null default now(),
  medicine      text not null,
  postal_code   text,
  kind          text not null check (kind in ('estoque','preco')),
  target_price  numeric(10,2),
  contact       text not null,
  active        boolean not null default true,
  last_checked_at timestamptz,
  last_status   text
);

-- Referência CMED/ANVISA (marca, substância, apresentação, EAN, preço máximo)
create table if not exists public.medicines_ref (
  ean           text primary key,
  substance     text not null,
  product       text not null,
  presentation  text,
  laboratory    text,
  product_type  text,
  pmc           numeric(10,2),      -- preço máximo ao consumidor (alíquota de referência)
  imported_at   timestamptz not null default now()
);
create index if not exists medicines_ref_product_idx on public.medicines_ref (lower(product));
create index if not exists medicines_ref_substance_idx on public.medicines_ref (lower(substance));

-- Segurança: o backend usa a service_role key. Clientes anônimos não leem nada.
alter table public.searches     enable row level security;
alter table public.offers       enable row level security;
alter table public.source_runs  enable row level security;
alter table public.watches      enable row level security;
alter table public.medicines_ref enable row level security;
create policy "leitura publica da referencia" on public.medicines_ref for select using (true);
