# Encontramed — Análise de viabilidade técnica

> Documento de decisão. Resume o que é possível consultar, o que não é, onde está o
> limite real do acesso a estoques, que arquitetura foi implementada e quanto custa.
> Data da análise: novembro/2026. Itens marcados **[verificar]** dependem de
> confirmação com a fonte ou de teste com rede liberada (`python -m app.cli verify-sources`).

## 1. Conclusão em uma frase

É viável construir um buscador **real** de medicamentos que **encontra estoque**,
não só anúncios, mas a cobertura de estoque confirmado depende de quais redes
expõem um mecanismo de consulta transacional (hoje: lojas em plataformas como a
VTEX) ou aceitam parceria. Para o restante, o sistema mostra a farmácia, o telefone e
o link de consulta — e diz claramente que **não há dado de estoque**.

## 2. A limitação real: estoque de farmácia não é público

| Camada | Quem tem o dado | Acessível? |
|---|---|---|
| Estoque por loja física | ERP da farmácia (Trier, Linx/Big, Digifarma, Vetor, sistemas próprios das redes) | **Não publicamente.** Só por parceria/integração com o ERP ou com a rede. |
| Estoque do e-commerce | Plataforma de e-commerce da rede | **Parcialmente.** Plataformas como a VTEX expõem à vitrine uma simulação de checkout por CEP (disponibilidade + frete + retirada). |
| Anúncio / página de produto | Sites, comparadores, marketplaces | Sim, mas **anúncio ≠ estoque**. |
| Cadastro de farmácias (endereço, telefone, horário) | OpenStreetMap, Google Maps, CNES/ANVISA | Sim. Sem estoque. |
| Cadastro de medicamentos (marca, substância, apresentação, EAN, preço máximo) | CMED/ANVISA (dados públicos) | Sim, gratuito. |

Consequências de projeto:

1. **Farmácias independentes** quase nunca têm estoque consultável. Elas aparecem
   como *Consultar farmácia*, com telefone e "Como chegar".
2. **Redes com e-commerce VTEX** permitem o melhor dado público possível: o sistema
   de pedidos da loja responde, para o CEP do usuário, se o SKU pode ser vendido
   agora, por quanto, com qual frete e se há retirada numa loja física específica.
3. **Raia/Drogasil (RD Saúde)**, a maior rede do país, usa plataforma própria sem API
   pública. Sem parceria, o sistema mostra só um link de consulta.
4. **Comparadores e marketplaces** mostram preço anunciado; os termos de uso, em geral,
   não autorizam coleta automatizada. Usados só como link de consulta manual.

## 3. Fontes de dados identificadas

### 3.1 Integradas nesta versão

| Fonte | Uso | Mecanismo | Custo | Estoque? |
|---|---|---|---|---|
| **ViaCEP** | CEP → endereço/cidade | API pública REST | Gratuito | — |
| **BrasilAPI** (CEP v2) | CEP → coordenadas (quando houver) | API pública REST | Gratuito | — |
| **Nominatim (OpenStreetMap)** | Geocodificação | API pública, máx. 1 req/s (política de uso) | Gratuito; produção: instância própria ou provedor pago | — |
| **Overpass (OpenStreetMap)** | Farmácias da cidade, telefone, horário | API pública (uso justo) | Gratuito | Não |
| **Google Places API (New)** — opcional | Farmácias com telefone/horário mais completos | API paga com chave | Cota gratuita mensal e depois pago por chamada **[verificar tabela atual]** | Não |
| **Lojas VTEX** — catálogo | Produto, SKU, preço, quantidade informada | `GET /api/catalog_system/pub/products/search` | Gratuito | Informado |
| **Lojas VTEX** — simulação de checkout | Disponibilidade para o CEP, frete, prazo, retirada em loja física | `POST /api/checkout/pub/orderForms/simulation` | Gratuito | **Confirmado** (ver §4) |

Redes configuradas como VTEX em `backend/sources.yaml` **[verificar cada uma]**:
Drogaria São Paulo, Drogarias Pacheco (grupo DPSP), Pague Menos, Drogaria Araujo,
Drogaria Venancio. Adicionar outra rede VTEX leva 4 linhas no YAML.

### 3.2 Sem integração (link de consulta manual)

Drogasil, Droga Raia, Panvel, Ultrafarma, Consulta Remédios. Motivo: plataforma
própria sem API pública documentada, ou termos de uso que não permitem coleta automatizada.
Caminho: parceria comercial ou programa de afiliados com feed de produtos.

### 3.3 Próximas fontes a avaliar

- **CMED/ANVISA** (já tem importador: `scripts/import_cmed.py`): dicionário completo
  marca ↔ substância ↔ apresentação ↔ EAN e preço máximo (PMC) para conferir preços.
- **Programas de afiliados** (Awin, Lomadee, Rakuten etc.) que oferecem feeds de
  produtos de farmácias: preço e link oficiais, mas o estoque costuma vir defasado
  (→ *Disponibilidade informada*).
- **Integradores de ERP de farmácia** (Trier, Linx, Digifarma etc.): é o **único**
  caminho para estoque por loja em farmácias independentes. Exige acordo B2B.
- **CNES/DATASUS e cadastro de AFE da ANVISA**: lista oficial de estabelecimentos
  farmacêuticos, para completar o mapa local.
- Outras plataformas de e-commerce (Magento/Adobe Commerce, Shopify, Wake/Linx Commerce,
  plataformas próprias): novo conector por plataforma, não por loja.

## 4. Regra de estoque implementada

| Classificação | Quando o sistema atribui |
|---|---|
| **ESTOQUE CONFIRMADO** | A simulação de checkout da loja, **para o CEP do usuário**, retornou `available` **e** uma opção real de entrega ou retirada. Fica registrado o horário da consulta. |
| **DISPONIBILIDADE INFORMADA** | O catálogo informa quantidade > 0, mas não foi possível confirmar em tempo real (sem CEP, falha da simulação, ou loja sem entrega para o CEP). |
| **CONSULTAR FARMÁCIA** | Produto anunciado sem dado de estoque, ou farmácia física sem estoque publicado (OSM/Google). |
| **INDISPONÍVEL** | A fonte informou `withoutStock` ou quantidade zero. |

O que a classificação **não** significa: "Estoque confirmado" é a confirmação do sistema de
pedidos da loja no horário indicado, e não uma garantia física de prateleira. Toda oferta
mostra a fonte, o método, a URL e a hora da consulta, e guarda os campos brutos (`evidence.raw`).

## 5. Legislação aplicada

- **Medicamentos controlados (Portaria SVS/MS 344/1998).** A venda remota com entrega
  não é permitida (RDC ANVISA 44/2009 e normas correlatas). O Encontramed mostra preço
  e disponibilidade apenas como informação, nunca oferece "comprar com entrega" e orienta
  a compra presencial com a receita exigida. A tabela de substâncias em
  `app/drug/controlled.py` é **parcial** e precisa ser sincronizada com os anexos
  vigentes da Portaria 344 (a ANVISA os atualiza por RDC) **[verificar antes de produção]**.
- **Antimicrobianos (RDC 471/2021):** exigem receita com retenção. O sistema avisa.
- **Substituição:** o sistema separa "mesmo princípio ativo e dosagem" (genérico/similar)
  e não recomenda trocas. A troca é decisão do prescritor ou do farmacêutico, nos limites da lei.
- **LGPD:** buscas são gravadas sem dados pessoais. Os alertas guardam só o contato
  informado pelo usuário, com finalidade explícita.
- **Termos de uso das fontes:** os endpoints VTEX usados são os mesmos que a vitrine
  pública da loja chama, sem autenticação. Mesmo assim, para escala comercial, o recomendado
  é formalizar acordo com cada rede. O sistema se identifica no User-Agent, usa cache de
  10 min e limita a concorrência.

## 6. Primeiro caso real: Amplictil 25 mg em Caraguatatuba-SP (CEP 11666-630)

O que o motor já sabe fazer neste caso (coberto por testes automatizados):

- Reconhece *Cloridrato de Clorpromazina 25 mg (Amplictil)* → princípio ativo
  `clorpromazina`, sal `cloridrato`, marca `amplictil`, dosagem 25 mg.
- Aceita 20, 50 ou 200 comprimidos (a embalagem não limita) e exclui 100 mg,
  gotas 40 mg/ml e injetável 5 mg/ml.
- Separa Longactil e genéricos de clorpromazina 25 mg em "mesmo princípio ativo",
  sem sugerir substituição.
- Identifica a **lista C1** e a **Receita de Controle Especial em 2 vias**. Com isso,
  a **etapa online fica apenas informativa**: pela regra de venda remota, o caminho
  legal é **retirada presencial**. O dado mais útil neste caso é o ponto de retirada
  com estoque confirmado em Caraguatatuba ou região, quando alguma rede integrada tiver.

**Execução real:** não foi possível rodar a busca no ambiente de desenvolvimento, porque a
política de rede do container bloqueou todos os hosts externos (resposta 403 do proxy).
O próprio sistema registrou cada fonte como `bloqueado` e **não inventou resultados**.
Para executar:

```bash
cd backend
python -m app.cli verify-sources                 # confirma quais redes VTEX respondem
python -m app.cli buscar "Cloridrato de Clorpromazina 25 mg (Amplictil)" --local 11666-630 --json amplictil.json
```

## 7. Arquitetura

```
 PWA (Safari/iPhone)  ──HTTP──►  FastAPI (app/main.py)
                                   │
                                   ▼
                         engine/search.py  (orquestrador, paralelo, cache)
             ┌─────────────┬───────┴────────┬──────────────────┐
             ▼             ▼                ▼                  ▼
     drug/normalizer   geo/location   sources/registry  ◄── sources.yaml
     (marca, ativo,    (ViaCEP,        ├─ vtex.py          (adicionar fontes
      dose ≠ embalagem, BrasilAPI,     ├─ local_directories.py  sem código)
      controlados)      Nominatim)     │   (OSM, Google Places)
                                       └─ manual.py (links de consulta)
                                   │
                                   ▼
                         engine/classify.py  (4 classificações + evidência)
                                   │
                                   ▼
                         db/supabase.py ──► Supabase (searches, offers,
                                             source_runs, watches, medicines_ref)
```

Princípios:
- **Modular:** cada fonte é uma classe com o mesmo contrato (`Source.search`).
  Lojas da mesma plataforma são só configuração.
- **Falha isolada:** fonte com erro ou bloqueio vira uma linha no relatório de fontes e não derruba a busca.
- **Rastreável:** cada oferta carrega `Evidence` (fonte, método, URL, horário, campos brutos), gravada no Supabase.
- **Duas etapas:** retirada na cidade (pontos de retirada das redes + mapa de farmácias,
  fundidos por proximidade de até 150 m) e compra online (frete, prazo, total). A expansão
  é sinalizada quando a cidade não tem estoque confirmado ou informado.

## 8. Custos estimados (valores de referência, conferir nas páginas oficiais)

| Item | Faixa inicial |
|---|---|
| ViaCEP, BrasilAPI, Overpass, Nominatim público, CMED, endpoints VTEX | R$ 0 |
| Supabase | Plano gratuito para o MVP; plano Pro ≈ US$ 25/mês |
| Hospedagem da API (Render, Railway, Fly.io etc.) | ≈ US$ 0–10/mês no MVP |
| Domínio .com.br | ≈ R$ 40/ano |
| HTTPS (obrigatório para PWA no iPhone) | Incluso no provedor de hospedagem |
| Google Places (opcional) | Cota gratuita mensal; acima disso, cobrança por chamada **[verificar]** |
| Nominatim/geocoding em escala | Instância própria (≈ US$ 20–40/mês) ou provedor pago |
| Integração com ERPs/redes (estoque por loja) | Negociação comercial; é o maior custo e o maior ganho de cobertura |

## 9. Plano por etapas

1. **Concluída nesta entrega:** motor modular, normalização, classificação de estoque,
   conectores reais (CEP, mapa, VTEX, Google opcional), API, PWA, esquema Supabase, testes, CLI.
2. **Validação real:** liberar a rede, rodar `verify-sources`, ajustar a lista de redes,
   rodar o caso Amplictil/Caraguatatuba e revisar a evidência bruta de cada oferta.
3. **Cobertura:** importar a CMED, adicionar mais redes VTEX regionais, conectores de
   outras plataformas e feeds de afiliados.
4. **Alertas:** job agendado (Supabase cron / GitHub Actions) que reexecuta as buscas
   da tabela `watches` e notifica volta ao estoque ou queda de preço (Web Push no iOS 16.4+
   com o PWA instalado, ou e-mail).
5. **Parcerias:** RD Saúde, integradores de ERP e farmácias independentes da região-piloto,
   para obter estoque por loja física.
