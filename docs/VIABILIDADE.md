# Encontramed — Análise de viabilidade técnica (v2)

> **Status: aguardando aprovação do responsável pelo projeto.**
> A v2 incorpora o *Adendo — Ampliação das fontes de pesquisa* (redes regionais,
> farmácias independentes, pesquisa em camadas, cadastro inteligente de fontes).
> Data: novembro/2026.
>
> Legenda: **[confirmado]** verificado em fonte pública; **[terceiros]** informação
> de diretórios, blogs ou comparadores, que precisa de confirmação; **[verificar]**
> depende de teste técnico com a rede liberada ou de contato com a empresa.

---

## 0. Resumo para decisão

1. **A falha do primeiro teste tem causa clara.** O sistema consultava apenas 5 redes
   nacionais com loja online e um mapa colaborativo (OpenStreetMap), que cobre mal
   cidades menores. Faltava um **cadastro completo de estabelecimentos**, e redes
   regionais como a Farma Ponte não tinham como aparecer.
2. **Existe uma base pública que lista praticamente todas as farmácias legalmente
   registradas no Brasil:** os dados abertos de CNPJ da Receita Federal, filtrados pela
   atividade econômica de farmácia. Combinada com CNES, OpenStreetMap e Google Maps, ela
   resolve a **descoberta** de redes regionais, independentes e de bairro, inclusive em
   cidades vizinhas.
3. **Descobrir a farmácia não é descobrir o estoque.** Para independentes e regionais
   sem sistema consultável, o estoque só pode ser obtido por três caminhos: (a) a farmácia
   confirmar, por telefone ou WhatsApp; (b) parceria com a rede; (c) integração com o
   sistema de gestão (ERP) da farmácia. O Encontramed deve facilitar e registrar essas
   confirmações, e nunca supor estoque.
4. **Farma Ponte:** rede regional paulista com indícios de unidades em Caraguatatuba e
   de e-commerce próprio **[terceiros]**. A plataforma do site e os termos de uso
   **ainda não foram verificados**, porque o ambiente de desenvolvimento bloqueou o acesso
   ao domínio. Ela entra como **primeira fonte da fila de investigação** (§4).
5. **Ponto jurídico pendente:** fontes secundárias divergem sobre entrega de medicamentos
   controlados, e saiu norma nova de receita eletrônica (RDC 1.000/2025). Isso exige
   **validação jurídica** antes de definir o comportamento final da Camada 4 para
   controlados (§9).

---

## 1. Por que a Farma Ponte ficou de fora

| Causa | Efeito |
|---|---|
| Lista fixa de 5 redes nacionais (VTEX) em `sources.yaml` | Redes regionais e independentes não eram consultadas |
| OpenStreetMap como único diretório local | Muitas farmácias de cidades médias não estão mapeadas, ou estão sem nome |
| Google Maps desligado (sem chave) | Perdia a fonte de diretório com maior cobertura |
| Nenhuma base cadastral oficial (CNPJ/CNES) | Não havia como saber quais farmácias existem na cidade |
| Rede bloqueada no ambiente de desenvolvimento | O teste automatizado nem chegou a rodar; o usuário encontrou a Farma Ponte por conta própria |

Lição de projeto: **a lista de fontes não pode ser fixa**. Ela precisa nascer de um
cadastro de estabelecimentos descobertos automaticamente e passar por investigação
contínua (§3 e §4).

---

## 2. Universo de pesquisa ampliado

| Tipo de estabelecimento | Como descobrir | Como obter estoque | Situação |
|---|---|---|---|
| Grandes redes nacionais | Cadastro CNPJ + lista de redes | E-commerce (simulação por CEP), parceria | Parcial (VTEX integrado) |
| **Redes regionais** (Farma Ponte, Farma Conde etc.) | CNPJ agrupado pela raiz (mesma empresa, várias filiais) + Google Maps | Site próprio, se permitido; parceria; WhatsApp | **A investigar, rede por rede** |
| Farmácias independentes e de bairro | CNPJ (atividade de farmácia) + CNES + OSM + Google | Confirmação humana (telefone/WhatsApp) ou ERP | Descoberta viável; estoque só com confirmação |
| Farmácias com loja virtual | Site no Google Maps e no cadastro; detecção de plataforma | Conector por plataforma (VTEX, outras) | Viável por plataforma |
| Farmácias com WhatsApp | Número no site, no Google ou informado pela farmácia | Pergunta enviada pelo usuário (link) ou pela plataforma oficial com consentimento | Viável (§6) |
| Farmácias com retirada presencial | Cadastro + pontos de retirada do e-commerce | Simulação de retirada ou confirmação | Parcial |
| Farmácias de manipulação | CNPJ (atividade de manipulação) | Não se aplica a produto industrializado | Exibir só se a receita for de manipulação (não sugerir) |
| **Distribuidores/atacadistas** | — | — | **Fora do escopo ao consumidor.** Distribuidoras vendem apenas a estabelecimentos licenciados, não a pessoa física. Úteis só como informação de abastecimento, mediante parceria |
| Rede pública (SUS) | Lista municipal de medicamentos (REMUME), Farmácia Dose Certa (SP), UBS e CAPS | Telefone da unidade / portal da prefeitura | Camada 5 (§5) |

---

## 3. Mapeamento geográfico: descoberta automática de estabelecimentos

### 3.1 Bases de descoberta

| Base | O que fornece | Cobertura | Custo | Limitações |
|---|---|---|---|---|
| **CNPJ — dados abertos da Receita Federal** | Razão social, nome fantasia, endereço, CEP, município, telefone e e-mail declarados, situação cadastral, atividade principal e secundárias, matriz/filial | **Todas as empresas registradas.** Filtrar pelas atividades 4771-7/01 (farmácia sem manipulação), 4771-7/02 (com manipulação) e 4771-7/03 (homeopatia), situação "ativa" | Gratuito (download mensal) | Telefone e endereço podem estar desatualizados; arquivos grandes, exigem processamento; nome fantasia nem sempre igual ao da fachada |
| **CNES (DATASUS)** — tipo de estabelecimento 43, Farmácia | Cadastro sanitário, endereço, responsável técnico | Farmácias comunitárias têm sido orientadas pelo CFF a se cadastrar **[terceiros]** | Gratuito | Cobertura ainda incompleta em farmácias privadas |
| **OpenStreetMap** | Coordenadas, nome, horário, telefone | Boa em capitais, irregular no interior | Gratuito | Lacunas |
| **Google Maps (Places API)** | Nome de fachada, telefone, site, horário, "aberto agora", avaliações | **A mais alta para estabelecimentos ativos** | 5.000 consultas Pro grátis/mês; depois ≈ US$ 32 por 1.000 **[terceiros — conferir na página oficial]** | Os termos do Google **proíbem guardar** a maior parte dos dados (só o ID do local pode ser armazenado), então uso sob demanda com cache curto |
| **ANVISA — Autorização de Funcionamento (AFE)** | Confirma que a farmácia está autorizada a funcionar | Todas as legalizadas | Gratuito | Não encontrei arquivo aberto em lote; só consulta individual **[verificar]** |
| **IBGE — API de localidades** | Municípios, códigos, regiões imediatas e intermediárias | Nacional | Gratuito | — |

### 3.2 Cadastro único de estabelecimentos

Um processo periódico (mensal para CNPJ e CNES, sob demanda para Google):

1. **Importa** os CNPJs de farmácia ativos, por município.
2. **Geocodifica** os endereços (Nominatim em instância própria, ou serviço pago em escala).
3. **Funde as bases** (resolução de entidades): o mesmo estabelecimento aparece no CNPJ, no
   CNES, no OSM e no Google. A ligação usa proximidade de coordenadas, telefone, CEP + número
   e semelhança de nome.
4. **Agrupa em redes** pela raiz do CNPJ (8 primeiros dígitos = mesma empresa) e por
   marca/nome fantasia. Exemplo **[terceiros]**: diretórios citam a razão social "Sos Farma
   Ponte LTDA" em Caraguatatuba. Ainda é preciso confirmar se é a mesma empresa da rede
   Farma Ponte de Sorocaba ou uma empresa distinta com nome parecido. **É isso que o
   agrupamento por CNPJ resolve.**
5. **Classifica** cada estabelecimento: rede nacional, rede regional (por exemplo, ≥ 5
   filiais em até 2 estados), independente ou manipulação.
6. **Cria candidatos a fonte.** Toda rede regional nova e todo site encontrado entram na
   **fila de investigação** (§4) com status "a investigar".

### 3.3 Cidades vizinhas

- Vizinhança calculada pela região geográfica imediata do IBGE **e** por raio rodoviário.
- Exemplo para Caraguatatuba: São Sebastião, Ilhabela e Ubatuba (Litoral Norte), depois o
  Vale do Paraíba (São José dos Campos, Taubaté e outras).
- O resultado mostra a distância e o tempo estimado de deslocamento. O usuário decide se vale
  a viagem.

---

## 4. Investigação de redes regionais — Farma Ponte como primeiro caso

### 4.1 O que já se sabe sobre a Farma Ponte

| Informação | Fonte | Grau |
|---|---|---|
| Rede de farmácias do interior de SP, sede em Sorocaba | Diretórios de lojas e vagas | [terceiros] |
| Mais de 115 lojas; canais de *Disk Delivery* e *E-commerce* | Página da rede no comparador Cliquefarma | [terceiros] |
| Domínio oficial informado: farmaponte.com.br | Perfil da empresa no Craft | [terceiros] |
| Unidades listadas em Caraguatatuba: Av. Maria de Lourdes da Silva Kfouri, 83; Av. José da Costa Pinheiro Júnior, 175; Av. Marechal Floriano Peixoto, 156 | Tiendeo (encartes, julho/2026) | [terceiros — podem estar desatualizadas] |
| "Sos Farma Ponte LTDA" com endereços em Caraguatatuba (Av. Arthur Costa Filho, 1659; Av. Miguel Varlez) | Diretório comercial | [terceiros — confirmar se é a mesma rede] |
| Aparece em comparador (Cliquefarma) | Cliquefarma | [terceiros] — indica que a rede fornece dados de preço a terceiros, possível caminho de parceria |
| Plataforma do site, API, retirada em loja, termos de uso | — | **[verificar]** — o domínio não estava acessível a partir do ambiente de desenvolvimento |

### 4.2 Protocolo de investigação (aplicado a cada rede candidata)

1. **Identidade:** CNPJ raiz, filiais e municípios atendidos (base CNPJ).
2. **Canais:** site, app, WhatsApp, telefone central, delivery.
3. **Plataforma técnica:** detectar se o site é VTEX (endpoints públicos de catálogo e de
   simulação respondem), outra plataforma conhecida ou sistema próprio.
4. **Permissão:** ler os termos de uso e o `robots.txt`. Se proibirem coleta automatizada,
   **não integrar sem autorização escrita.**
5. **Teste de evidência:** a fonte informa estoque por loja? por CEP? só a página do produto?
   Registrar exatamente o que ela devolve.
6. **Decisão:** integrar automaticamente (se permitido e útil), pedir parceria, ou manter como
   "consulta manual + WhatsApp/telefone".
7. **Registro:** tudo no cadastro de fontes (§7), com data e responsável pela verificação.

Primeiras redes da fila (região do caso real): **Farma Ponte**, **Farma Conde** (rede citada
com mais de 300 unidades em SP e MG e presença em Caraguatatuba **[terceiros]**) e as redes
encontradas pela base CNPJ no Litoral Norte e no Vale do Paraíba.

---

## 5. Pesquisa em camadas

| Camada | Escopo | Fontes | Resultado típico |
|---|---|---|---|
| **1** | Farmácias da cidade | Cadastro único + estoque das fontes integradas + confirmações recentes | Lista completa de farmácias da cidade; estoque quando houver; botões Ligar / WhatsApp / Como chegar |
| **2** | Redes regionais e independentes (cidade e região) | Conectores das redes regionais investigadas + confirmação humana | Estoque das redes regionais integradas; independentes para consultar |
| **3** | Cidades vizinhas | Mesmas fontes, raio ampliado (região imediata do IBGE) | Opções de retirada a X km / Y min |
| **4** | Online, todo o Brasil, com entrega no CEP | E-commerces (simulação por CEP) | Preço, frete, prazo, total (para controlados, ver §9) |
| **5** | Outras fontes legais | Rede pública (REMUME municipal, Farmácia Dose Certa/SP, CAPS/UBS), avisos de falta e descontinuação da ANVISA, atendimento do fabricante | Orientação de onde buscar no SUS; alerta se o produto estiver em falta no país |

Regras de execução:

- As camadas rodam **em sequência lógica, mas em paralelo técnico.** O usuário vê a Camada 1
  em poucos segundos, e as demais chegam aos poucos (atualização contínua da tela).
- A busca **só termina quando todas as fontes de todas as camadas foram consultadas ou
  falharam.** Cada falha aparece no relatório de fontes.
- A tela sempre informa o que foi pesquisado, o que não pôde ser verificado e o que depende
  de ligação.
- Sobre a Camada 5: a SES-SP mantém material sobre a dispensação de clorpromazina na Farmácia
  Dose Certa **[confirmado — documento público da SES-SP]**. O Encontramed apenas informa
  esse caminho; não avalia elegibilidade.

---

## 6. Como identificar estoque real

### 6.1 Hierarquia de evidências

| Nível | Método | Classificação resultante | Validade sugerida |
|---|---|---|---|
| A | Integração autorizada com o ERP ou a API da rede, estoque por loja | **Estoque confirmado** | Hora da consulta |
| B | Simulação de checkout/retirada do e-commerce para o CEP ou loja | **Estoque confirmado** (pelo sistema de pedidos) | Hora da consulta |
| C | **Farmácia confirma** por canal identificável (WhatsApp oficial, portal da farmácia, atendente com nome) | **Estoque confirmado pela farmácia** *(decisão D1)* | Curta (sugestão: 4 h) |
| D | Catálogo/site informa quantidade ou "disponível" | Disponibilidade informada | Hora da consulta |
| E | Relato de usuário ("liguei e tinha") | Sinal separado: *relatado por usuário*; **nunca** "confirmado" *(decisão D2)* | Curta, com decaimento |
| F | Página do produto / anúncio sem dado de estoque | Consultar farmácia | — |
| G | Fonte informa ausência | Indisponível | Hora da consulta |

**Regra que se mantém:** página de produto, anúncio ou listagem em comparador **nunca**
geram "Estoque confirmado".

### 6.2 Confirmação humana assistida (viável já, custo zero)

- Botão **"Perguntar no WhatsApp"**: abre o WhatsApp do usuário com a mensagem pronta, por
  exemplo: *"Olá! Vocês têm Cloridrato de Clorpromazina 25 mg (Amplictil) para retirada hoje?"*
  A pergunta é enviada **pelo próprio usuário** (link público `wa.me`), sem automação
  e sem violar termos de uso.
- Botão **"Ligar"**, com roteiro: o que perguntar (dosagem, apresentação, receita exigida).
- Ao voltar ao app, o usuário pode registrar **"tinha / não tinha"**. Isso vira um relato de
  usuário (nível E), útil para os próximos usuários, com data e hora.

### 6.3 Confirmação pela farmácia (requer adesão da farmácia)

- **Portal da farmácia (gratuito para ela):** a farmácia recebe pedidos de consulta ("alguém
  procura X na sua cidade") e responde "tenho / não tenho". Resposta = nível C.
- **WhatsApp Business Platform (API oficial da Meta):** a plataforma pode enviar a pergunta à
  farmácia **somente se a farmácia tiver aceitado receber** essas mensagens (exigência da Meta).
  Custo por mensagem baixo (§10). **Automatizar o WhatsApp pessoal é proibido pelos termos e
  não será feito.**
- **Integração com ERP** (Trier, Linx, Digifarma, Vetor e outros): o caminho de maior qualidade
  para independentes e regionais, mas depende de acordo comercial com cada fornecedor ou farmácia.

---

## 7. Cadastro inteligente de fontes

Novas farmácias e redes entram por **dados**, não por código. O núcleo só conhece *métodos de
consulta* (conectores por plataforma).

### 7.1 Campos de cada fonte

| Campo | Exemplo |
|---|---|
| Nome | Farma Ponte |
| Tipo de estabelecimento | rede regional / rede nacional / independente / e-commerce / pública |
| CNPJ raiz e filiais | (preenchido pela base CNPJ) |
| Região atendida | lista de municípios IBGE, ou raio, ou UF, ou nacional |
| Site | farmaponte.com.br **[verificar]** |
| Telefone / WhatsApp | central e por loja |
| **Método de consulta** | `api_autorizada`, `vtex`, `outra_plataforma`, `catalogo_site`, `portal_farmacia`, `whatsapp_oficial`, `whatsapp_link`, `telefone`, `link_manual` |
| Possibilidade de retirada | sim / não / a verificar |
| Possibilidade de entrega | sim / não / área de entrega |
| **Grau de confiabilidade** | A–G (§6.1): melhor evidência que a fonte consegue fornecer |
| Situação dos termos de uso | permitido / sem restrição encontrada / proibido / parceria assinada / a verificar |
| Situação da investigação | a investigar / em teste / ativa / suspensa / recusada |
| Última verificação e responsável | 2026-11-04, nome |
| Observações | ex.: "C1 só presencial", "site bloqueia automação" |

### 7.2 Onde fica

- Tabelas no Supabase: `estabelecimentos` (cadastro único), `redes`, `fontes` (como consultar),
  `investigacoes` (fila e histórico), `confirmacoes` (níveis C e E com validade).
- Página administrativa simples para cadastrar ou editar fontes e acompanhar a fila de investigação.
- O `sources.yaml` atual vira apenas a carga inicial.

---

## 8. Automação sem violar termos de uso — regras do projeto

1. Preferir **API oficial ou acordo escrito**.
2. Endpoints públicos de vitrine (como os da VTEX) só são usados se os termos e o `robots.txt`
   da loja não proibirem. A verificação é registrada no cadastro.
3. Identificação honesta (User-Agent com contato), limite de requisições, cache.
4. **Proibido:** contornar login, captcha, bloqueio ou limite; usar proxies para fugir de
   bloqueio; automatizar WhatsApp pessoal; robôs de ligação.
5. Fonte bloqueou ou proibiu → o sistema **para**, registra e passa a mostrar o link manual.
6. Dados do Google Maps são usados conforme os termos (sem formar base própria com eles).
7. Comparadores (Consulta Remédios, Cliquefarma, Farmaindex) **não** são raspados. Servem
   como link e, eventualmente, como parceiros.

---

## 9. Legislação — atualização e ponto pendente

- **Venda online de controlados (Portaria 344/98, listas A, B, C1, C2, C5):** as fontes
  consultadas concordam que **continua não permitida** por e-commerce ou aplicativo.
  A Drogaria São Paulo, por exemplo, informa na página do Amplictil que o produto não está
  disponível para venda online conforme a Portaria 344/98 **[confirmado na página da loja,
  via resultado de busca]**.
- **Divergências encontradas que exigem validação jurídica:**
  - A página da Drogarias Pacheco indica que a compra de C1 só é concluída com **receita digital
    válida em PDF** **[terceiros — resultado de busca]**.
  - Fontes secundárias divergem sobre **entrega domiciliar após venda presencial ou por telefone**
    (citam RDC 44/2009 e uma "RDC 812/2023" que não consegui confirmar).
  - A **RDC 1.000/2025** regulamentou o receituário eletrônico de controlados, integrado ao Sistema
    Nacional de Controle de Receituários (SNCR), com prazos de transição em 2026 **[terceiros — CFF e CFM]**.
- **Proposta até a validação jurídica:** manter o comportamento atual (Camada 4 apenas informativa
  para controlados; orientar a compra presencial com receita) e exibir a política declarada pela
  própria loja quando ela existir.
- **Distribuidores:** sem venda a consumidor final.
- **Lista de controlados:** sincronizar com os anexos vigentes da Portaria 344. Uma fonte cita
  atualização da lista C1 pela RDC 999/2025 **[terceiros]**.

---

## 10. Custos (estimativas; conferir nas páginas oficiais)

| Item | Custo |
|---|---|
| CNPJ (Receita), CNES, IBGE, CMED/ANVISA, OSM | Gratuitos |
| Processamento mensal da base CNPJ | GitHub Actions ou máquina pequena: ≈ R$ 0–50/mês |
| Armazenamento (cadastro de ~100 mil farmácias) | Cabe no Supabase gratuito no início; Pro ≈ US$ 25/mês |
| Geocodificação em lote | Nominatim próprio ≈ US$ 20–40/mês, ou serviço pago por volume |
| Google Places (enriquecimento sob demanda) | 5.000 consultas/mês grátis; depois ≈ US$ 32 por 1.000 (cai com volume) **[terceiros]**. Piloto em Caraguatatuba e região: dentro da cota gratuita |
| Botão "Perguntar no WhatsApp" (link) | Gratuito |
| WhatsApp Business Platform (com adesão da farmácia) | ≈ R$ 0,035 por mensagem de serviço/utilidade (tabela de out/2026) **[terceiros]** + taxa do provedor (BSP) |
| Portal da farmácia | Desenvolvimento interno; operação ≈ R$ 0 |
| Integrações com ERP e parcerias | Negociação comercial (maior custo e maior ganho de cobertura) |
| Operação humana (opcional): equipe que liga para farmácias em casos difíceis | Custo de pessoal; pode ser serviço premium |

---

## 11. Estratégia de implementação proposta (para aprovação)

| Fase | Entrega | Critério de aceite |
|---|---|---|
| **F1 — Cadastro único** | Importação CNPJ + CNES + OSM; enriquecimento Google sob demanda; agrupamento por rede; vizinhança IBGE | Em Caraguatatuba, **a Farma Ponte e as demais farmácias da cidade aparecem**, comparadas com uma lista conferida manualmente pelo responsável (meta ≥ 95% das farmácias abertas) |
| **F2 — Pesquisa em camadas** | Camadas 1–5 com atualização contínua na tela e relatório por camada | Busca do Amplictil mostra todas as camadas e o que foi ou não verificado |
| **F3 — Confirmação assistida** | Botões WhatsApp/Ligar com mensagem pronta; registro "tinha / não tinha" | Fluxo completo testado no iPhone |
| **F4 — Investigação de redes** | Protocolo §4.2 aplicado à Farma Ponte, Farma Conde e redes do Litoral Norte/Vale; novos conectores só onde for permitido | Relatório por rede com decisão registrada |
| **F5 — Portal da farmácia e parcerias** | Painel para a farmácia responder consultas; WhatsApp oficial com adesão; contato com ERPs | Primeiras farmácias piloto respondendo |
| **F6 — Alertas** | Volta ao estoque, queda de preço, monitoramento de itens difíceis | Já previsto na v1 |

### Decisões necessárias do responsável

- **D1.** A resposta da própria farmácia (WhatsApp oficial ou portal) pode ser exibida como
  **"Estoque confirmado pela farmácia"**, com hora e validade de 4 h? *(recomendo sim)*
- **D2.** Relatos de usuários entram como sinal separado ("relatado por usuário"), nunca como
  confirmado? *(recomendo sim)*
- **D3.** Orçamento para Google Places e geocodificação depois do piloto.
- **D4.** Quem faz o contato comercial com as redes (Farma Ponte, Farma Conde) e com os
  fornecedores de ERP?
- **D5.** Contratar validação jurídica sobre venda e entrega de controlados e receita eletrônica (§9).
- **D6.** Liberar no ambiente de desenvolvimento o acesso aos domínios necessários (farmácias,
  ViaCEP, OSM, Receita/DATASUS), para executar os testes reais.

---

## Anexo A — Conteúdo técnico da v1 (mantido)

### A.1 Classificação de estoque implementada na v1

| Classificação | Regra |
|---|---|
| Estoque confirmado | Simulação de checkout da loja para o CEP retornou `available` com opção real de entrega ou retirada |
| Disponibilidade informada | Catálogo com quantidade > 0, sem confirmação em tempo real |
| Consultar farmácia | Anúncio sem dado de estoque, ou farmácia sem estoque publicado |
| Indisponível | Fonte informou ausência |

### A.2 Fontes integradas na v1

ViaCEP, BrasilAPI, Nominatim, Overpass/OSM, Google Places (opcional), lojas VTEX
(catálogo e simulação de checkout), links manuais (Drogasil, Droga Raia, Panvel, Ultrafarma,
Consulta Remédios). Os padrões de URL das páginas da Drogaria São Paulo e da Pacheco
(`/produto/p`, filtros `specificationFilter`) são típicos da VTEX, o que reforça a
configuração dessas redes **[verificar com `verify-sources`]**.

### A.3 Arquitetura da v1

PWA → FastAPI → orquestrador (paralelo, cache) → normalização do medicamento + localização
+ registro de fontes (conectores) → classificação com evidência → Supabase. A v2 acrescenta o
cadastro único de estabelecimentos, a fila de investigação, a pesquisa em camadas e as
confirmações (§3–§7).

### A.4 Caso Amplictil 25 mg — Caraguatatuba/SP — CEP 11666-630

O motor reconhece princípio ativo, sal, marca e dosagem; não confunde dosagem com quantidade
de comprimidos; separa genéricos e similares sem sugerir troca; e identifica a lista C1. A
execução real ainda depende da liberação de rede (D6).
