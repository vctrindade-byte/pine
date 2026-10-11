# Validação

O que foi verificado, como, com que resultados e o que continua por verificar. Os números deste documento vêm de uma
execução completa sobre as edições actuais (`price_cvd_normalizer.pine` e `price_cvd_normalizer_footprint.pine`,
geradas de `src/price_cvd_normalizer.src.pine`), salvo indicação em contrário.

> **Limite principal.** Não havia acesso ao compilador da TradingView. A correcção da compilação foi defendida a partir
> da documentação do Pine v6, de um parser independente e de um runtime alternativo (PineTS). Antes de publicar, siga a
> [lista de verificação no Pine Editor](#5-lista-de-verificação-no-pine-editor).
>
> **O que esta validação não mostra.** Prova que o código calcula o que a metodologia descreve e mede a frequência dos
> sinais em dados reais. Não mede o seu valor preditivo: os eventos e os cruzamentos de Z do código final não foram
> testados contra retornos seguintes, MFE/MAE, controlos, custos nem fora da amostra. A auditoria externa e o plano
> para essas etapas estão em [AUDITORIA.md](AUDITORIA.md).

## Resumo

| Verificação | Ferramenta | Resultado |
|---|---|---|
| As edições geradas coincidem com a fonte | `python3 tools/build.py --check` | OK (código de saída 0) |
| Sintaxe das duas edições | pynescript 0.3.0 | 2/2 sem erros |
| Built-ins usados existem na referência v6 | pesquisa nas cópias locais do manual | Standard 96/96 na 1.ª cópia; Footprint 97/99 na 1.ª cópia e 99/99 com o 2.º espelho (os 2 `footprint.*`) |
| Limites da plataforma | contagem no código | 44 de 64 plots (pior caso 48); 1 ou 2 pedidos únicos de 40; 407/412 variáveis globais declaradas de 1000 (sem as temporárias do compilador) |
| Harness PineTS com dados sintéticos (T0–T12) | `npm test` | 774 verificações, 774 PASS (com `PINE_PYTHON`; sem pynescript, o T2 dá 1 WARN em vez das 2 verificações de parse) |
| Concordância com a referência Python em dados reais | scripts de validação fora do repositório (exportação, execução no PineTS e referência Python) | corr(Z Pine, Z Python) = 1,000000, \|ΔZ\| máx 6,7 × 10⁻¹⁰, gate igual em 100% das barras |
| Calibração em dados reais (BTCFDUSD, delta verdadeiro) | idem | P(\|Z\| ≥ 2) = 6,19% / 6,07%; P(\|Z\| ≥ 3) = 1,61% / 1,04% (duas janelas de 5 min), contra 4,55% / 0,27% numa normal: o Z é um score empírico; a frequência da dica do Z coincide com a recontagem |
| Cone, preço implícito, amplitude das linhas, calibração provisória, costura (secção 3.6) | edição Standard no PineTS, dados reais | saídas do cone 17% (5 min) e 10% (15 min) contra 4,6% iid; \|P̂/C − 1\| p99 9% em 117 dias (33% na janela de 31 dias); com calibração provisória (n < 200), \|Z\| ≥ 2 1,3 vezes mais frequente; reinício na costura em 88% (15 min) e 20% (5 min) dos casos; no fim do dia, \|F̃\| com mediana 17, p90 63 e máximo 324 (5 min) |

---

## 1. Geração, sintaxe e limites da plataforma

**Build.** `python3 tools/build.py --check` reconstrói as duas edições a partir da fonte única e compara-as com os
ficheiros do repositório: sem diferenças.

**Parse.** As duas edições foram analisadas pelo parser `pynescript` 0.3.0 (gramática ANTLR do Pine), sem cache: ambas
sem erros (284 s para as duas num só processo, em paralelo com as execuções PineTS do `npm test`; o primeiro parse
inclui o aquecimento da cache do ANTLR).

**Verificações estáticas (T3).** A edição Standard não contém `footprint` em código nem em texto visível ao utilizador
(strings de dicas, rótulos, tabela e alertas; só em comentários); a Footprint tem exactamente um
`request.footprint()`; as duas têm um único `request.security_lower_tf` na linha exigida pelo harness, `//@version=6`
na linha 1 e o aviso de ficheiro gerado na linha 2; não sobram etiquetas `// @fp` ou `// @std`.

**Built-ins.** Todos os identificadores com espaço de nomes usados em código (`ta.*`, `math.*`, `str.*`, `request.*`,
`timeframe.*`, `chart.*`, `display.*`, …) foram procurados em duas cópias locais da referência do Pine v6: a 1.ª é o
espelho https://github.com/codenamedevan/pinescriptv6 e o 2.º espelho é
https://github.com/chris-c-thomas/pine-script-v6-md. Na 1.ª cópia: 96/96 na Standard e 97/99 na Footprint; com o 2.º
espelho, 99/99 na Footprint. Os dois que só estão no 2.º espelho, `footprint.delta()` e `footprint.total_volume()`,
estão documentados aí (página do tipo `footprint` e exemplo do manual com `request.footprint()` →
`footprint.total_volume()`/`footprint.delta()`, guardado por um ID não *na*). Uma revisão adversarial anterior, linha
a linha contra a documentação (qualificadores, argumentos nomeados, ordem de declaração, quebras de linha), não
encontrou bloqueadores de compilação; as construções introduzidas depois dessa revisão (`chart.is_standard`,
`syminfo.prefix`, `display` dependente de inputs em `plot`/`hline`/`fill` (a `precision` é sempre literal: dois pares
de plots), `timeframe.isticks`, o ciclo `for … in` sobre o array de volumes dos intrabars) foram verificadas contra as
páginas correspondentes da referência. O volume dos intrabars soma-se nesse ciclo, com o *na* tratado explicitamente,
porque a página do `array.sum()` só documenta o caso do array vazio.

**Limites** (manual do Pine, «Limitations»):

| Limite | Valor no indicador | Máximo |
|---|---|---|
| Plots | 24 `plot` + 3 cores série + 2 `fill` + 1 `bgcolor` + 14 `alertcondition` = **44** (48 se as cores dependentes de inputs contassem como série) | 64 |
| Pedidos `request.*` únicos | Standard 1; Footprint 2 | 40 |
| Elementos do tuplo do pedido intrabar | 3 | 127 |
| Maior desfasamento ou comprimento de histórico | 2000 (`math.sum` com M) | 5000 |
| Recuo dos desenhos | até 1050 barras; `max_bars_back(time, 1100)` | — |
| Rótulos e linhas | `max_labels_count = 500`, `max_lines_count = 500` | 500 |
| Variáveis no âmbito global | 407 declaradas na Standard e 412 na Footprint, mais as temporárias que o compilador cria (não contáveis fora da TradingView) | 1000 por âmbito |

---

## 2. Harness PineTS com dados sintéticos

O harness (`tests/`, ver [tests/README.md](../tests/README.md)) corre o código Pine das duas edições no PineTS 0.11.0
sobre barras sintéticas com **delta verdadeiro conhecido**. O pedido intrabar é substituído, em memória, por um stub
que devolve 5 intrabars por barra cuja soma é o delta verdadeiro; o T10 testa também o pedido intrabar nativo, sem
stub. Os resultados são comparados com as fórmulas de [METODOLOGIA.md](METODOLOGIA.md), o oráculo dos testes, através
de uma reimplementação independente em JavaScript (`tests/lib/refz.mjs`).

Execução completa: `npm test` com `PINE_PYTHON` a apontar para um ambiente com `pynescript` 0.3.0, 22 blocos de testes
(T0–T3 uma vez; T4–T12 em cada edição), **774 verificações, 774 PASS**, código de saída 0, 413 s com o parse em
cache (405 s numa execução anterior com o parse sem cache, que corre em paralelo; o tempo depende da máquina: ver
«Tempo típico» em [tests/README.md](../tests/README.md)). Sem `pynescript`, o
T2 dá 1 WARN (parse não executado) em vez das 2 verificações de parse.

| Teste | O que verifica | Resultado |
|---|---|---|
| T0 | O próprio harness: PineTS, canal do delta (erro ≤ 1/998 de V), volume dos intrabars do stub (igual ao do gráfico, ou 100 com o volume do gráfico em falta), `timeframe.in_seconds()`, `timeframe.change`, `session.isfirstbar`, built-ins presentes no PineTS (106) | 26/26 |
| T1 | `tools/build.py --check` | 3/3 |
| T2 | Parse com pynescript | 2/2 com `PINE_PYTHON` (WARN sem ele) |
| T3 | Verificações estáticas (secção 1), incluindo nenhum texto visível com «footprint» na Standard | 18/18 |
| T4 | Matriz: 5 modos × {intrabar, só barras} × {âncora Auto, diária, semanal}, com as três vistas e os interruptores a rodar; na Footprint, também a fonte footprint | Standard 60/60; Footprint 12/12. Linhas finitas em 99,6–100% das barras depois do aquecimento; Z finito em 100% com intrabars e ausente (0%) com «Só barras do gráfico» |
| T5 | Calibração nula: 4500 barras sem episódios, precisão 1S (qualidade alta); contadores da frequência empírica na dica do Z | P(\|Z\| ≥ 2) = **5,37%** (230/4281); P(\|Z\| ≥ 3) = **0,26%** (11/4281). Critérios: [2%, 12%] e < 3%. Contadores da dica = recontagem a partir dos plots (barras com ≥ 2N valores de calibração) |
| T6 | Detecção de 10 absorções e 10 episódios de preço sem fluxo; auditoria **exacta** de rótulos, lados, «preço travado», resoluções e setas, de cada `alertcondition` e de cada `alert()`, rederivados dos plots; precisão Auto (qualidade média, rótulos ocos); pivots ligados; série nula com \|zP\| máximo do «travado» = 3 (exclusão da classe CONFIRMADO) | 49/49 por edição. Z com o sinal esperado dentro do episódio em 10/10 absorções e 10/10 episódios de preço sem fluxo; absorção rotulada ou alertada em 10/10; P(\|Z\| ≥ 2) fora dos episódios 1,7% e 0,9%; pivots 41/41 topos e 44/44 fundos iguais à referência; todos os conjuntos de barras de rótulos e alertas iguais aos esperados |
| T7 | Invariantes: σ congelado em cada segmento, linhas interrompidas na âncora, fórmulas fechadas dos 5 modos, cone, remoção da deriva, costura da cobertura | 28/28 por edição; erro relativo ≤ 10⁻⁶ (≤ 10⁻⁴ no z-score de níveis, pela precisão do `ta.stdev` do PineTS); costura: reinício exactamente na barra 300 |
| T8 | Concordância com a referência JS da estatística: série nula, absorções, blocos sem intrabars a meio, saltos de abertura e gaps de início de dia | 62/62 por edição: corr = 1,00000, \|Z Pine − Z ref\| máx < 10⁻⁹, Z definido exactamente nas mesmas barras; zF, zP, η, P_K, F_K, λ OLS, σr, σΔ e ρ iguais à referência (≤ 10⁻⁶); depois de um bloco sem intrabars, o Z volta 119 barras depois (hqNeed = 120) |
| T9 | Motor de delta e qualidade: stub = delta verdadeiro; recurso BVC; volume zero; classificador BVC; 1S → 3; Auto em 5 min → 2; 1S com BVC → 2; «30S» → 2; LTF = gráfico → 1 sem Z; «Nenhum» → 0; volume de ticks e FX → 1, sem Z, sem eventos, aviso na tabela; unidade adaptativa do λ | 28/28 por edição |
| T10 | Pedido intrabar **nativo** (sem stub): o PineTS avalia a função `ltfSigned` do indicador sobre sub-barras de 1 minuto (15% doji, 3% volume zero, viragens de dia); intrabars esparsos; volume em falta nos intrabars (todos, todos com o volume do gráfico presente, 2 de 5) e intrabars todos com volume zero | 13/13 por edição: delta = referência JS da regra da vela (lado transportado entre barras) e do BVC por intrabar (erro ≤ 10⁻⁷); intrabars esparsos → «⚠ poucos intrabars»; um intrabar sem volume → volume em falta (delta *na*, qualidade anterior, linha interrompida, «Sem volume nesta barra (dados em falta)»); intrabars de volume zero → sem negócios; o mutante com `nz(volume)` falha 3 de 4 verificações |
| T11 | Outros timeframes: 1 min (Auto e 1S), 1 h, D (âncora Auto e diária inválida), W, gráfico de 1S, sessão personalizada (0830-1515 e 1700-1600), 15 min com absorções opostas em barras seguidas | 68/68 por edição: qualidade por precisão como esperado; âncoras exactamente nas barras esperadas (1700-1600 só às 17:00); mensagens da tabela («Sem sinais no gráfico de 1 min: escolha 1S ou 1T», «âncora inválida → Auto»); nota «Apenas contexto» só em ≥ 1 h |
| T12 | Integridade do volume (volume em falta ≠ volume zero; barras sem observação de fluxo): série nula em 1S com volume em falta isolado e em sequência (alguns com saltos de ±5–6σ), barras sem negócios com e sem intrabars, volume do gráfico em falta com intrabars com volume, divergências por pivots com barras sem negócios no meio; «Só barras do gráfico»; «Barras sem intrabars» = Nenhum; absorções com sequências de 4 barras sem negócios; estado na tabela; na Footprint, footprint com volume próprio | 65/65 na Standard e 82/82 na Footprint: delta, qualidade, Z, zF, zP, σ, ρ, P_K, F_K e η iguais à referência JS com as barras sem observação fora das estatísticas (≤ 10⁻⁶); sem Z, gate ou eventos nessas barras; o Z continua na barra seguinte; linhas contínuas sem negócios e interrompidas com volume em falta; auditoria exacta de eventos (período refractário em observações) e pivots; com «Nenhum», a barra de volume zero sem intrabars é «sem negócios» e não parte a sequência. Mutantes: a regra antiga `nz(volume)` falha 18/32 (Standard) e 31/48 (Footprint); a regra que exige uma fonte falha 2/2 |

**Testes de mutação.** Para saber se o harness apanha erros reais, foram injectados erros plausíveis em cópias do
código (por exemplo σ sem desfasamento, RMS que inclui a barra actual, sinal de Z trocado, σ não congelado, resoluções
trocadas, sem winsorização, alertas sem histerese, «travado» sem a exclusão da classe CONFIRMADO, sem o reinício na
costura, qualidade alta com o BVC). Nas rondas anteriores, 11/11 (revisão 3) e 5/5 (revisão 4: calibração mínima dos
eventos e dos alertas de Z, aglomerados por lado, sufixo de confiança, volume de ticks) foram apanhadas. Continuam por
apanhar, pelo menos, as mutações que só alteram texto da tabela (por exemplo, o NAR, mostrado em % com uma casa
decimal) e a da regra das cotações em «1T» (o PineTS não fornece cotações). A lista completa está em
[tests/README.md](../tests/README.md).

---

## 3. Validação com dados reais

### 3.1 Método

- **Dados:** BTCFDUSD à vista (Binance), barras de 5 minutos e de 15 minutos, com o **delta verdadeiro** de cada barra
  calculado a partir das marcas de agressor de cada negócio (dados de investigação, não incluídos; os dados de mercado
  nunca são versionados).
- **Execução:** um script fora do repositório exporta uma janela de barras, codifica o delta verdadeiro no canal do
  harness (erro máximo de quantização 10⁻³ do volume) e corre a edição no PineTS com precisão 1S (qualidade alta), modo
  unidades-σ ancoradas e valores por omissão.
- **Referência:** uma implementação Python independente (fora do repositório) da guarda de gaps, das escalas, de D,
  do RMS desfasado e do gate, escrita a partir de [METODOLOGIA.md](METODOLOGIA.md). A comparação começa na barra 320
  (3N + K).

### 3.2 Pine contra a referência Python

| Janela | Edição | Barras comparadas | corr(Z Pine, Z Python) | \|ΔZ\| máx | Só num lado | Gate aberto (concordância) | ρ mediano |
|---|---|---|---|---|---|---|---|
| 0–8999 (2026-04-01 → 2026-05-02, 31 dias) | Standard | 8678 | 1,000000 | 6,72 × 10⁻¹⁰ | 0 | 89,71% (100%) | 0,574 |
| 0–8999 | Footprint | 8678 | 1,000000 | 6,72 × 10⁻¹⁰ | 0 | 89,71% (100%) | 0,574 |
| 20000–31999 (2026-06-09 → 2026-07-21, 42 dias) | Standard | 11671 | 1,000000 | 5,82 × 10⁻¹⁰ | 0 | 80,20% (100%) | 0,440 |

Erro relativo máximo de σr, σΔ e ρ entre Pine e Python: 1,5 × 10⁻¹¹, 9,2 × 10⁻¹¹ e 6,4 × 10⁻⁸ (janela 1). Delta lido
pelo Pine contra o stub: 5 × 10⁻¹¹. A regra de gaps alterou o retorno em 32 e 43 barras.

**Barras sem observação de fluxo** ([METODOLOGIA.md](METODOLOGIA.md), secção 2.6, regra 5): em todo o histórico de 5
minutos há 20 barras de volume zero em 33 696, todas sem movimento de preço (abertura = máximo = mínimo = fecho = fecho
anterior), e nenhuma com volume em falta; o histórico de 15 minutos não tem nenhuma. Há 2 dessas barras na janela 1 e
9 na janela 2. A referência Python aplica a
mesma regra (fora de σ, ρ, D e do RMS; a sequência de qualidade não é partida) e o Pine não tem Z nem gate aberto em
nenhuma delas. Com a regra anterior (volume zero = observação com Δ = 0), reproduzida na referência Python, o Z muda
até 0,83 (janela 1) e 1,44 (janela 2) nas barras vizinhas, e P(|Z| ≥ 2) da janela 2 seria 6,05%.

### 3.3 Calibração

| Janela | P(\|Z\| ≥ 2) Pine / Python | P(\|Z\| ≥ 3) Pine / Python | P(\|Z\| ≥ 2 \| gate aberto) |
|---|---|---|---|
| 0–8999 | 6,19% / 6,19% | 1,61% / 1,61% | 6,27% |
| 20000–31999 | 6,07% / 6,07% | 1,04% / 1,04% | 6,45% |

A quantização do canal não altera o resultado: corr(Z Python com delta quantizado, Z Python com delta original) =
1,00000.

A dica do Z (frequência empírica nas barras fechadas com Z e pelo menos 2N = 200 valores de calibração) mostrou, na
janela 1, 8679 barras, |Z| ≥ 2 em 6,2%, |Z| ≥ 3 em 1,61% e, com o gate aberto (89,7% dessas barras), |Z| ≥ 2 em
6,3%; na janela 2, 11 672 barras, 6,1%, 1,05% e 6,5% (gate aberto em 80,3%). A recontagem a partir dos plots dá os
mesmos valores (6,19%, 1,613%, 89,73% e 6,27%; 6,07%, 1,045%, 80,26% e 6,46%).

**O Z não é normal** ([METODOLOGIA.md](METODOLOGIA.md), secções 6.1 e 6.8; [AUDITORIA.md](AUDITORIA.md), ponto (b)).
Nas mesmas barras (a partir da 320), medido sobre o plot «Z (valor)» [E]:

| Janela | RMS do Z | Curtose (normal: 3) | Autocorrelação a 1 / 5 / 10 / 20 barras | P(\|Z\| ≥ 4) (normal: 0,006%) | Barras com \|Z\| ≥ 2 / blocos contíguos |
|---|---|---|---|---|---|
| 0–8999 | 1,05 | 7,3 | 0,94 / 0,77 / 0,56 / 0,10 | 0,48% | 537 / 127 |
| 20000–31999 | 1,00 | 4,4 | 0,93 / 0,70 / 0,43 / −0,09 | 0,09% | 708 / 194 |

A calibração pelo RMS cumpre o que promete (RMS ≈ 1), mas as caudas são mais pesadas do que as de uma normal e as
barras extremas vêm em blocos (3,6–4,2 barras seguidas, em média): a frequência de barras com |Z| ≥ limiar não é uma
frequência de episódios. Na janela 1, essas 537 barras deram 60 alertas de Z (secção 3.5).

### 3.4 Outras configurações em dados reais

Corridas da edição Standard sobre os mesmos dados, a partir da barra 320, com os valores por omissão salvo indicação:

| Configuração | P(\|Z\| ≥ 2) | P(\|Z\| ≥ 3) | Gate aberto | Z médio | Rótulos por dia |
|---|---|---|---|---|---|
| 5 min, 1S, janela 0–8999 | 6,19% | 1,61% | 89,7% | −0,24 | 1,9 |
| idem, com «Remover deriva do fluxo» | 5,02% | 0,89% | 89,7% | −0,01 | 2,0 |
| 5 min, 1S, janela 20000–31999 | 6,07% | 1,04% | 80,2% | +0,01 | 2,6 |
| idem, com «Remover deriva do fluxo» | 5,42% | 0,70% | 79,6% | +0,06 | 2,8 |
| 15 min, 1S, 11 232 barras (117 dias) | 5,35% | 1,48% | 84,4% | −0,11 | 1,5 |
| 5 min, **Auto** (delta estimado pela regra da vela em intrabars de 1 min, qualidade média), janela 0–8999 | 5,95% | 1,59% | 94,7% | −0,12 | 1,6 (todos ocos) |

Re-medido com a regra das barras sem observação de fluxo: mudaram só as duas linhas da janela 20000–31999 (P(|Z| ≥ 2)
6,05% → 6,07%; com a deriva removida, 5,43% → 5,42% e gate 79,7% → 79,6%) e a da precisão Auto (5,94% → 5,95%: uma
barra a menos com Z no denominador, as mesmas 516 barras com |Z| ≥ 2). Os dados de 15 minutos não têm barras sem
volume. As contagens de rótulos e alertas da janela 0–8999 (secção 3.5) e as da Footprint ficaram iguais.

- **Footprint.** Com a fonte Footprint alimentada pelo delta verdadeiro (compra − venda por barra), o delta lido é
  exacto (erro ≤ 7 × 10⁻¹⁵) e o Z coincide com o da fonte intrabar (corr 0,999999; a diferença máxima, 8 × 10⁻³, vem só
  da quantização do canal); P(|Z| ≥ 2) = 6,19%, P(|Z| ≥ 3) = 1,60%; os mesmos 58 rótulos e 322 alertas. Isto prova o
  caminho dos dados do footprint até ao cálculo, não a exactidão do footprint da TradingView, que classifica o lado a
  partir da acção do preço intrabar e não foi comparado com o delta verdadeiro.
- **Delta estimado (Auto).** O Z calculado com o delta estimado de 1 minuto correlaciona 0,68 com o Z do delta
  verdadeiro. Das 537 barras com |Z| ≥ 2 pelo delta verdadeiro, 246 também passam o limiar com o delta estimado (todas
  com o mesmo sinal); o delta estimado assinala 516. O gate abre mais vezes (94,7% contra 89,7%) porque a estimativa
  inflaciona ρ, como o dossier previa. É a razão da qualidade «média» e dos rótulos ocos.
- **Deriva.** Sem a remoção da deriva, o NAR de todo o histórico foi de +6,3% e o Z ficou deslocado (média −0,24;
  alertas «Z ≤ −limiar» 43 contra 17 «Z ≥ +limiar»); a tabela mostrou «⚠ desequilíbrio persistente». Com a remoção,
  Z médio −0,01 e 31 contra 28.
- **Caudas do zF.** P(|zF| ≥ 3) foi 2,09% e 2,38% nas janelas de 5 minutos e 3,54% em 15 minutos: «preço travado» marca
  fluxo forte com o preço quase parado, não um extremo raro.
- **Estados neutros.** Nas três corridas sem remoção da deriva (5 min 0–8999, 5 min 20000–31999 e 15 min), o sinal da
  perna dominante (plots «Perna do preço (P_K)» e «Perna do fluxo (F_K)») coincidiu com o implicado pelo sinal de Z
  em todas as 1829 barras com |Z| ≥ 2 (537 + 708 + 584), como a identidade de
  [METODOLOGIA.md](METODOLOGIA.md#66-pernas-e-os-quatro-estados-neutros) exige.

### 3.5 Eventos e alertas em dados reais (5 min, 1S, janela 0–8999, 31 dias)

| Elemento | Contagem |
|---|---|
| Rótulos | 58 (1,9 por dia): 28 compras absorvidas (10 com «preço travado»), 17 vendas absorvidas (2 travadas), 10 «Preço ↓ sem fluxo vendedor», 3 «Preço ↑ sem fluxo comprador» |
| Resolução das 45 absorções | 21 continuações, 17 «absorção segurou», 5 expiradas, 2 substituídas |
| Alertas de Z | 17 «Z ≥ +limiar», 43 «Z ≤ −limiar» |
| Alertas de eventos | absorvido: 28 compras / 17 vendas; travado: 12 / 2; continuação: 12 / 9; segurou: 12 / 5; preço sem fluxo: 3 subida / 10 queda |
| `alert()` dinâmico | 152 (4,9 por dia) |

Estas contagens descrevem a frequência dos sinais, não o seu valor: as resoluções não foram testadas contra retornos
seguintes nesta validação (ver [METODOLOGIA.md, secção 9](METODOLOGIA.md#9-interpretação-honesta)).

### 3.6 Outras medições em dados reais

Números citados nas dicas, no README e na metodologia, medidos com a edição Standard final no PineTS sobre os mesmos
dados (delta verdadeiro, precisão 1S, qualidade alta, âncora Auto = diária, valores por omissão), salvo indicação em
contrário.

**Cone nulo iid e preço implícito.** Com σ_iid = √(2n(1 − max(ρ_a, 0))), o plot «Cone nulo +2σ» (cone ligado) menos a
linha do preço vale 2σ_iid; há saída quando |F̃ − P̃| > 2σ_iid. Sob a hipótese iid, as saídas seriam ~4,6% e o RMS de
(F̃ − P̃)/σ_iid seria 1. O preço implícito vem do modo «Preço implícito pelo fluxo» com λσ (plot «CVD em preço»),
comparado com o fecho. Barras a partir da 320.

| Dados | Barras | Saídas do cone | RMS de (F̃ − P̃)/σ_iid | \|P̂/C − 1\|: p50 / p95 / p99 / máx |
|---|---|---|---|---|
| 5 min, 0–8999 (31 dias) | 8650 | 15,7% | 2,82 | 0,7% / 5,9% / 33,1% / 43,5% |
| 5 min, 20000–31999 (42 dias) | 11 639 | 12,1% | 1,81 | 0,7% / 4,9% / 9,1% / 12,1% |
| 5 min, todo o histórico (117 dias) | 33 261 | 16,7% | 2,30 | 0,7% / 6,0% / 9,1% / 43,5% |
| 15 min, todo o histórico (117 dias) | 10 799 | 9,9% | 1,46 | 0,6% / 3,7% / 6,9% / 14,3% |

O dossier previa, a partir do rácio de variâncias VR20 = 1,30, um cone verdadeiro 15–30% mais largo (RMS de 1,15 a
1,3). O desvio medido é maior (RMS de 1,5 a 2,8): o fluxo tem memória longa e a volatilidade intradiária varia em
relação às escalas congeladas na âncora; a contribuição de cada factor não foi separada. A dica do cone e a
metodologia ([METODOLOGIA.md](METODOLOGIA.md), secções 5.8 e 10) citam a medição directa. Os afastamentos grandes do
preço implícito concentram-se em poucos dias de fluxo persistente: o percentil 99 de 33% da primeira janela cai para
9% no histórico completo.

**Amplitude das linhas ancoradas.** Valor absoluto das linhas em unidades-σ ancoradas (plots «Preço (normalizado)» e
«CVD (normalizado)», cone desligado) na última barra de cada âncora diária, isto é, na barra anterior ao reinício (as
linhas interrompem-se na barra da âncora). Só âncoras completas: ficam de fora a primeira (aquecimento) e a última
(incompleta); todos os reinícios coincidiram com a mudança de dia UTC.

| Dados | Âncoras | \|P̃\|: mediana / p90 / máx | \|F̃\|: mediana / p90 / máx | \|F̃ − P̃\|: mediana / p90 / máx |
|---|---|---|---|---|
| 5 min, 0–8999 (31 dias) | 30 | 11,4 / 34,6 / 49,9 | 15,4 / 50,8 / 323,8 | 15,2 / 55,1 / 283,9 |
| 5 min, 20000–31999 (42 dias) | 41 | 11,5 / 22,4 / 48,1 | 18,3 / 49,5 / 97,7 | 11,0 / 35,1 / 83,7 |
| 5 min, todo o histórico (117 dias) | 115 | 11,7 / 31,3 / 57,1 | 17,2 / 62,6 / 323,8 | 12,3 / 54,4 / 283,9 |
| 15 min, todo o histórico (117 dias) | 114 | 6,8 / 17,1 / 34,1 | 7,5 / 23,1 / 80,0 | 6,5 / 21,6 / 58,1 |

Em todas as barras (a partir da 320), o máximo de |F̃| foi 327,7 em 5 minutos e 80,6 em 15 minutos. Um |F̃| grande
no fim do dia é, por construção, delta acumulado num só sentido; os valores extremos concentram-se em poucos dias (o
p90 fica muito abaixo do máximo), tal como os afastamentos grandes do preço implícito. O README e a dica da vista do
painel citam a linha «5 min, todo o histórico».

**Calibração provisória.** Para simular a cobertura curta de 1S, cada corrida tem 400 barras sem intrabars (BVC na
barra, qualidade baixa) seguidas de 1300 barras com 1S, a partir de pontos de reinício espalhados pelo histórico (123
em 5 minutos, de 250 em 250 barras; 83 em 15 minutos, de 100 em 100). O RMS que calibra o Z recomeça em cada corrida.
Cada Z provisório é comparado com o Z da corrida contínua de todo o histórico (calibração completa) **nas mesmas
barras**; n é o número de valores de D anteriores no RMS (o Z aparece com n = N = 100). As corridas sobrepõem-se, por
isso as barras não são independentes.

| Dados | n | Barras | P(\|Z\| ≥ 2): provisório / completo (rácio) | P(\|Z\| ≥ 3): provisório / completo (rácio) |
|---|---|---|---|---|
| 5 min | 100–199 | 12 300 | 8,93% / 6,67% (1,34) | 1,92% / 1,21% (1,58) |
| 5 min | 200–399 | 24 600 | 6,74% / 6,06% (1,11) | 1,22% / 1,12% (1,09) |
| 5 min | 400–1000 | 73 923 | 6,88% / 6,59% (1,04) | 1,18% / 1,17% (1,01) |
| 15 min | 100–199 | 8300 | 7,14% / 5,39% (1,33) | 1,43% / 1,23% (1,17) |
| 15 min | 200–399 | 16 600 | 6,48% / 5,67% (1,14) | 1,44% / 1,24% (1,16) |
| 15 min | 400–1000 | 49 883 | 6,03% / 5,75% (1,05) | 1,35% / 1,23% (1,10) |

Com 1S num gráfico de 5 minutos (cerca de 330 barras cobertas), o Z só existe nas ~110 barras mais recentes, com n de
100 a ~210: corresponde à linha «5 min, 100–199». Daí a regra de 2N valores para os alertas de Z e a intensidade
limitada do preenchimento com menos de 20·K valores ([METODOLOGIA.md](METODOLOGIA.md), secção 6.3).

**Janela mista na costura da cobertura.** Com 1S e o limite de 100K intrabars só as barras mais recentes têm intrabars
(cerca de 330 em 5 minutos e 110 em 15 minutos). Para pontos finais espalhados pelo histórico, as barras anteriores à
cobertura foram servidas sem intrabars (BVC na barra, qualidade baixa) e verificou-se se a janela σ/ρ da âncora diária
activa na última barra (as N barras anteriores à âncora) incluía barras sem intrabars:

| Dados | Pontos finais | Âncora activa com escalas de uma janela mista | Linhas reiniciadas pelo indicador («reiniciada no início da cobertura») |
|---|---|---|---|
| 15 min, cobertura de 110 barras | 75 | 88,0% | 88,0% (75/75 casos coincidem) |
| 5 min, cobertura de 330 barras | 82 | 19,5% | 19,5% (82/82 casos coincidem) |

Sem a regra da costura ([METODOLOGIA.md](METODOLOGIA.md), secção 4.4), essas âncoras escalariam o delta fino com um σ
estimado, em parte ou no todo, sobre o delta derivado do preço.

---

## 4. O que não pôde ser validado

1. **Compilador da TradingView.** Não havia acesso. O PineTS é mais permissivo do que o compilador (ordem de
   declaração, qualificadores `simple`/`series`, limite de 64 plots, tipos em ternários de tuplos): um script que corre
   no PineTS pode ainda não compilar. As construções mais arriscadas estão na lista da secção 5.
2. **Footprint em planos sem Premium.** A documentação só diz que é preciso Premium ou Ultimate para usar scripts que
   chamam `request.footprint()`. Não se sabe se a edição Footprint carrega em planos inferiores com a fonte Intrabar
   (a chamada fica dentro de um `if` que não é executado) nem o que acontece quando se escolhe a fonte Footprint
   (erro ou *na*). A edição Standard existe para evitar o problema.
3. **Cotações bid/ask em «1T».** O PineTS não fornece cotações: a regra das cotações não foi exercitada (a mutação que
   a inverte sobrevive). Também não se sabe se a TradingView fornece bid/ask nos intrabars «1T» históricos.
4. **1S e 1T por plano.** O que acontece num plano sem intervalos de segundos ou de ticks (erro, *na* ou permitido) não
   está documentado. Sem intrabars, a tabela mostra «Sem sinais: nenhuma barra com intrabars de …».
5. **Limite de 100 000 elementos por array em «1T».** Uma barra com mais de 100 000 negócios excede o limite de um
   array; o comportamento real (erro de execução) não foi testado. A dica da precisão avisa.
6. **Gráficos de ticks e não padrão.** O código pára com `runtime.error` em gráficos de ticks (`timeframe.isticks`) e
   não padrão (`chart.is_standard`); não foi possível confirmar na TradingView.
7. **Tempo real.** O PineTS corre só histórico (`barstate.isconfirmed` verdadeiro em todas as barras). Não foram
   testados o recálculo dentro da barra, a reposição das variáveis `var` em cada tick, nem as diferenças entre
   histórico e tempo real dos pedidos intrabar e do footprint.
8. **Desenho e legibilidade.** A tabela e os rótulos foram verificados como texto; o tamanho, o contraste nos temas
   claro e escuro e a sobreposição com as velas só se vêem na TradingView.
9. **Volume em falta na TradingView.** Não está documentado quando a TradingView dá `volume` *na* (e não 0) no gráfico
   ou nos intrabars (por exemplo, em índices sem volume), nem se um intrabar de 1S ou 1T pode existir sem negócios. As
   regras das barras sem observação de fluxo (volume em falta ou zero) foram testadas só no PineTS (T10, T12); nos dados
   reais só havia barras de volume zero, todas sem movimento de preço.
10. **Mercados.** Os dados reais são de um único par cripto à vista. Futuros do CME (dia Globex, RTH), acções (leilões
    de abertura e fecho), perpétuos e FX não foram validados com dados reais; 1 h, D e W só com dados sintéticos (T11).
11. **NAR.** Só aparece na tabela e não tem verificação numérica (a mutação correspondente sobrevive).
12. **Fidelidade das fontes da TradingView.** O footprint e os intrabars 1S/1T da TradingView não foram comparados com
    o delta da bolsa: a qualidade classifica a configuração dos dados, não a exactidão do delta
    ([AUDITORIA.md](AUDITORIA.md), ponto (c)).
13. **Valor preditivo.** Os cruzamentos de Z, os eventos, as resoluções e os pivots do código final não foram testados
    contra retornos seguintes em unidades de volatilidade, MFE/MAE, controlos, custos nem fora da amostra; o estudo
    anterior do dossier, com definições de investigação, deu um nulo para o Z e uma ligeira continuação depois da
    absorção, na própria amostra ([AUDITORIA.md](AUDITORIA.md), ponto (i)). Também não foi medido o efeito do gate ρ
    (que hoje não se desliga por completo) nem o de outros limiares (ponto (d)).

---

## 5. Lista de verificação no Pine Editor

Antes de publicar, numa conta TradingView (idealmente uma Premium ou Ultimate e outra de plano inferior):

1. **Compilação.** Colar cada edição no Pine Editor e guardar: sem erros. Registar avisos.
2. **Standard em plano inferior.** Adicionar ao gráfico numa conta Basic, Essential, Plus ou Expert: tem de carregar.
3. **Footprint em plano inferior.** Na mesma conta, adicionar a edição Footprint: (a) com a fonte Intrabar, carrega?
   (b) com a fonte Footprint, que acontece (erro, *na*)? Ajustar a dica da fonte se necessário.
4. **Footprint em Premium/Ultimate.** `footprint fpObj = na` seguido de `fpObj := request.footprint(ticksIn)` dentro de
   `if` compila; a tabela mostra «footprint · 100 ticks/linha · alta»; o delta na Data Window é plausível.
5. **1T.** Numa conta Ultimate, com precisão 1T: verificar se `bid`/`ask` chegam não *na* nos intrabars históricos (por
   exemplo com um plot temporário); quantos ticks são servidos; o que acontece numa barra muito activa (mais de 100 000
   negócios).
6. **1S/1T sem plano.** Numa conta sem esses intervalos, escolher 1S e 1T: erro, *na* ou permitido? Confirmar que a
   tabela explica a situação.
7. **`display` dependente de inputs.** `plot(…, display = cond ? display.all : display.none)`, `hline(…, display = …)`
   e `fill(…, display = …)` compilam e escondem os elementos certos em cada vista e modo.
8. **Âncoras.** `timeframe.change()` com a string derivada de inputs; mapa Auto em 2 h, 4 h, D e W; RTH e sessão
   personalizada 1700-1600 num futuro do CME (uma âncora por dia, às 17:00).
9. **Paridade com o CVD da TradingView.** Com precisão Auto, regra da vela, âncora diária e deriva desligada, comparar
   «CVD ancorado» (Data Window) com o indicador Cumulative Volume Delta da TradingView (âncora 1D, timeframe inferior
   automático) no mesmo símbolo: devem coincidir dentro da cobertura de intrabars.
10. **Limite de plots.** A compilação confirma 44 ≤ 64.
11. **Alertas.** Criar um alerta com uma `alertcondition` e outro com «Any alert() function call», frequência *Once
    Per Bar Close*: verificar que os marcadores `{{plot("Z (valor)")}}` e `{{plot("Qualidade (0–3)")}}` são
    substituídos por valores e que a mensagem dinâmica começa por «BOLSA:SÍMBOLO timeframe ·».
12. **Erros explícitos.** Num gráfico de ticks e num Heikin Ashi, o script pára com a mensagem em português.
13. **Símbolos sem volume e com volume de ticks.** Num índice sem volume: «Sem dados de volume para este símbolo.»
    Num par FX: qualidade baixa, «⚠ volume de ticks», sem Z nem eventos. Num CFD (por exemplo OANDA:SPX500USD):
    registar o «Tipo de volume» da tabela; se não vier declarado como ticks, o indicador não o detecta (o
    `syminfo.type` não tem valor para CFD) e a qualidade segue a fonte, com Z e eventos; confirmar que as dicas o
    explicam.
14. **Tempo real.** Acompanhar algumas barras ao vivo: Z, estados e eventos só mudam ao fecho da barra; os alertas
    disparam uma vez por barra fechada.
15. **Aspecto.** Temas claro e escuro: contraste das linhas, dos rótulos ocos e dos avisos da tabela; a tabela compacta
    não tapa as barras recentes em excesso.
16. **Variáveis por âmbito.** O Pine admite 1000 variáveis por âmbito, incluindo as temporárias que o compilador cria.
    O âmbito global declara 407 (Standard) e 412 (Footprint); as temporárias só se vêem na compilação. As duas edições
    têm de guardar sem o erro «Script has too many local variables»; se aparecer, agrupar cálculos em funções (cada
    função tem o seu próprio limite).
17. **Barras sem observação de fluxo.** Num símbolo pouco líquido, ou fora de horas, encontrar barras sem negócios: a
    tabela mostra «Sem negócios nesta barra» e «qualidade anterior», a linha do CVD continua plana e o Z volta na barra
    seguinte. Num símbolo ou intervalo em que a TradingView dê volume *na* (por exemplo um índice), confirmar «Sem
    volume nesta barra (dados em falta)» e as linhas interrompidas. Registar se os intrabars de 1S/1T chegam com volume
    0 ou *na*.
18. **Frequência empírica do Z.** A dica da célula do Z mostra a frequência de |Z| ≥ limiar e ≥ limiar forte e a parte
    com o gate aberto; com histórico suficiente (≥ 2N valores de calibração), os valores devem ser da ordem dos da
    secção 3.3 num mercado líquido.

---

## 6. Como reproduzir

```bash
python3 tools/build.py --check
PINE_PYTHON=/caminho/para/python-com-pynescript npm test     # T0–T12, as duas edições
node tests/run_tests.mjs --only T5,T8 -v                     # só alguns testes, com pormenor
```

A validação com dados reais precisa dos dados de investigação (barras BTCFDUSD com o delta verdadeiro), que não são
distribuídos; os scripts de exportação, execução e referência Python também ficaram fora do repositório.
