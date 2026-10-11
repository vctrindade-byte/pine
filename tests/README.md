# Testes do indicador "Preço × CVD Normalizado [Order Flow]"

Harness automático que verifica as duas edições geradas (`price_cvd_normalizer.pine` e
`price_cvd_normalizer_footprint.pine`) sem as alterar: corre o código Pine no
[PineTS](https://www.npmjs.com/package/pinets) (runtime Pine Script para Node, versão fixada **0.11.0**)
sobre barras sintéticas com **delta verdadeiro conhecido** e compara o resultado com o oráculo dos testes: as
fórmulas e regras de [docs/METODOLOGIA.md](../docs/METODOLOGIA.md). Essas fórmulas foram reimplementadas de forma
independente em JavaScript (`tests/lib/refz.mjs`, usado no T7, T8 e T10) e, para a validação com dados reais, em
Python, fora do repositório (método e resultados em [docs/VALIDACAO.md](../docs/VALIDACAO.md), secção 3).

> O PineTS **não** é o compilador da TradingView. Os testes provam o comportamento numérico e a lógica;
> não provam que o script compila na TradingView (qualificadores, ordem de declaração, limites de plots).
> Isso continua a exigir a verificação no Pine Editor.

## Requisitos

- Node.js ≥ 20 e npm.
- Opcional (teste T2): Python 3 com `pynescript==0.3.0`.

## Instalação

```bash
npm install                                   # instala o pinets 0.11.0 (devDependency)
python3 -m venv .venv                         # opcional, para o T2
.venv/bin/pip install -r requirements-dev.txt
```

Sem acesso à rede, aponte para uma instalação existente do PineTS de uma destas formas:

```bash
ln -s /caminho/para/node_modules node_modules          # o import ESM só procura em node_modules
NODE_PATH=/caminho/para/node_modules npm test          # o harness recorre a require(), que respeita NODE_PATH
PINETS_DIR=/caminho/para/node_modules npm test         # ou indica a pasta directamente
```

## Correr

```bash
npm test                                      # edições Standard + Footprint (T0–T11)
npm run test:quick                            # matriz reduzida (≈ 1/3 do tempo)
npm run test:standin                          # auto-teste do harness com tests/fixtures/standin.pine
node tests/run_tests.mjs --only T5,T6 -v      # só alguns testes, mostrando também o que passou
node tests/run_tests.mjs --json tests/out/relatorio.json
```

Opções: `--target std|fp|both|standin`, `--only T0,T4,…`, `--quick`, `--bars N` (matriz T4, por omissão 3000),
`--json FICHEIRO`, `--shim ID`, `--no-cache`, `--verbose`, `--file-std CAMINHO` / `--file-fp CAMINHO` (testar uma
build candidata noutra pasta em vez das edições do repositório).
Variáveis de ambiente: `PINE_PYTHON` (Python com pynescript para o T2; senão tenta `.venv/bin/python`, `python3`,
`python`), `NODE_PATH`/`PINETS_DIR` (ver acima), `HARNESS_JOBS` (execuções PineTS em paralelo; por omissão
nº de CPUs − 1, máx. 4), `HARNESS_INPROCESS=1` (sem workers, para depuração), `PINE_STD_FILE`/`PINE_FP_FILE`
(equivalentes a `--file-std`/`--file-fp`), `NO_COLOR`.

O código de saída é ≠ 0 se algum teste tiver **FAIL**. **WARN** e **SKIP** não fazem falhar a suite.

Tempo típico (4 CPUs): ≈ 3 min quando as edições mudaram (o T2 leva ~2 min: o ANTLR do pynescript faz o parse de
cada edição em ~1 min; os ficheiros inalterados ficam em `tests/out/parse-cache.json`) e ≈ 2 min nas execuções
seguintes. Os testes T5–T11 correm nas duas edições. Cada execução PineTS (≈ 5 s para 3000 barras do indicador real) corre num *worker thread* novo:
o PineTS 0.11.0 fica progressivamente mais lento quando reutiliza o mesmo isolate (medido: 4,7 s → 8,6 s em 5
execuções iguais), e os workers permitem correr 3 execuções em paralelo. Todas as execuções planeadas são lançadas
no arranque e os testes avaliam-nas por ordem, por isso o tempo mostrado por teste é só o de avaliação.

## Testes

| ID | O que verifica | Critério de sucesso |
|----|----------------|---------------------|
| T0 | Auto-verificação do harness: PineTS carrega; o stub devolve 5 intrabars por barra cuja soma é o delta do canal; `timeframe.in_seconds()` = 300; `timeframe.change("1D"/"1W")` e `session.isfirstbar` nas viragens UTC apesar dos ms do canal; `syminfo.mintick`; títulos e inputs descobertos; built-ins usados existem no PineTS | tudo exacto; built-ins em falta → WARN |
| T1 | `python3 tools/build.py --check` | sai com 0 |
| T2 | Parse de ambas as edições com pynescript | sem erro (SKIP+WARN se não houver pynescript) |
| T3 | Estático: a Standard não tem `footprint` em código (fora de comentários/strings) nem em texto visível (strings fora de comentários: dicas, rótulos, tabela, alertas); a Footprint tem exactamente 1 `request.footprint()`; linha 1 `//@version=6`, banner na linha 2; linha única do pedido intrabar (ver «Stub do `request.security_lower_tf`»); sem etiquetas `// @fp`/`// @std` remanescentes | todos |
| T4 | Matriz: cada modo de visualização × {LTF (stub), "Só barras do gráfico"} × {âncora Auto, Diária, Semanal}, ~3000 barras com 5% iniciais sem intrabars, barras de volume 0 e dois episódios; as vistas e os toggles (cone, pivots, deriva, overlay) rodam entre execuções. Na edição Footprint: fonte footprint servida pelo provider | sem excepções; linhas finitas em ≥ 95% das barras após o aquecimento; Z finito ≥ 95% (fonte LTF); footprint: delta = compra − venda, tier 3, barras sem footprint seguem o fallback/preenchimento |
| T5 | Calibração nula: 4500 barras sem episódios, precisão 1S (tier 3) | P(\|Z\| ≥ 2) ∈ [2%, 12%] e P(\|Z\| ≥ 3) < 3% |
| T6 | Detecção: 10 absorções (fluxo forte e persistente, λ≈0, 20–40 barras, lados alternados) e 10 episódios de preço sem fluxo (deriva, Δ≈0); mais uma execução com precisão Auto (qualidade média), outra com **pivots ligados e \|zP\| máximo do «travado» = 2.0** e a série nula com **\|zP\| máximo do «travado» = 3.0** (há aí barras da classe CONFIRMADO com \|zF\| ≥ 3). **Auditoria exacta dos eventos**: a partir dos plots do próprio indicador (zF, zP, ρ, gate, qualidade, Z, delta, σΔ) e do OHLC re-deriva as classes (absorvido ∪ travado sem a classe CONFIRMADO s·zP ≥ \|ρ\|·\|zF\|, preço sem fluxo), a 1.ª barra de cada aglomerado (por classe **e lado**, com período refractário de ke barras: novo aglomerado quando o lado muda ou depois de > ke barras sem a classe do mesmo lado), a máquina de resolução (H0/L0 em ke barras, vida), os alertas de Z com histerese (1.º cruzamento; rearme depois de Z < limiar − 1) **só com ≥ 2N valores de calibração** (o cruzamento anterior desarma na mesma), os alertas de eventos e das suas resoluções só com calibração do zF/zP ≥ max(20·ke, 2N) (contagens derivadas dos Z/zF finitos anteriores) e, com pivots, uma referência independente dos pivots (regra de empates do PineTS, CVD contínuo em R, magnitude em σΔ, distância 5–60, hqSpan) | Z com o sinal esperado e \|Z\| ≥ 2 dentro do episódio em ≥ 70%; etiqueta ou alertcondition "absorvido" em ≥ 50% das absorções; auditoria: conjuntos de barras das etiquetas e de cada alertcondition (incl. «Preço travado sob compras/vendas extremas» e pivots topo/fundo) e alert() **iguais** aos esperados, lado, «preço travado», resolução e seta ↑/↓ da resolução de cada etiqueta iguais; etiquetas dos pivots na barra do pivot; texto do estado nas mensagens alert() dos cruzamentos de Z = sinal de Z + perna dominante (\|F_K\| vs \|P_K\|); qualidade média → rótulos ocos (65% de transparência); em todas as auditorias, cada rótulo com «(baixa conf.)» (qualidade média) ou «(cal. prov.)» (calibração fraca) e oco exactamente nesses casos |
| T7 | Invariantes em "Unidades-σ ancoradas": linhas interrompidas (na) na barra de reinício e, na seguinte, F = (Δ_a + Δ_a+1)/σΔ_a, P = 1e4·ln(C/O_a)/σr_a; σ congelado em todo o segmento; "CVD ancorado" reinicia nas âncoras. "Preço implícito" com λσ: linha de preço = close e (ln fLine − lnA) / perna de fluxo sig = σr_a/1e4. Formas fechadas de "janela móvel", "Z-score de níveis" e "Mín–máx"; cone = ±2·√(2n(1 − max(ρ_a, 0))); com a deriva removida, incremento do CVD ancorado = Δ − SMA_N(Δ)[1]. **Costura da cobertura** (200 barras iniciais sem intrabars): as linhas reiniciam nas âncoras do calendário e uma vez na 1.ª barra cuja janela σ/ρ (N barras) está toda em dados finos, com σΔ congelado aí | erro relativo ≤ 1e-6 (1e-5 na razão; 1e-4 no z-score de níveis, pela precisão do `ta.stdev` do PineTS) |
| T8 | Concordância com a referência JS das fórmulas de METODOLOGIA §3, §6 e §7 (`tests/lib/refz.mjs`) na série nula, na de absorções, na série nula com **blocos sem intrabars a meio do histórico** (1500+5 e 3000+30 barras → fallback BVC, tier 1) e em duas séries com **saltos de abertura** (guarda de gaps, METODOLOGIA §3.1: ~1% das barras com \|ln(O/C₋₁)\| de 60–120 bps ≈ 8–15σ e gaps N(0, 3 bps) em cada início de dia; a 2.ª com 0,3% de barras isoladas sem intrabars) | corr(Z Pine, Z ref) ≥ 0.98; Z definido **exactamente** nas mesmas barras (hqOk = N + max(K, ke) barras seguidas de qualidade ≥ média); \|Z Pine − Z ref\| ≤ 1e-6 desde a barra 3N + K; zF e zP = referência (≤ 1e-6); pernas P_K/F_K, λ OLS (×1000) e η do Data Window = referência (≤ 1e-6; só edições reais); nas séries com saltos, delta por barra = referência (stub; BVC na barra com r = ln(C/O) nos gaps); σr/σΔ/ρ do Data Window = referência (WARN) |
| T9 | Motor de delta e tier: stub = delta verdadeiro; "Intrabars" = 5 (0 sem intrabars); classificador BVC = soma do array BVC; barras sem intrabars → BVC na barra (tier 1); volume 0 → delta 0 e tier anterior; precisão Auto → tier 2, 1S → tier 3, 1S com BVC → tier 2, personalizado "30S" → tier 2, personalizado = TF do gráfico → tier 1 sem Z; "Só barras" = BVC; fallback "Nenhum" → delta na, tier 0; volume de ticks (`syminfo.volumetype` "tick" ou `syminfo.type` "forex", série nula em 1S) → tier 1 (sem lado agressor), sem Z, sem eventos nem alertas, tabela com «⚠ volume de ticks» e «Sem sinais: volume de ticks»; unidade adaptativa do λ: com volume × 1e6 o λσ aparece «por 1 milhão de unidades» com valor em [0.1, 1000) e igual ao original / 1e6 | exacto (1e-9 / 1e-6; 1e-7 no BVC; λ ± 2%) |
| T10 | `request.security_lower_tf` **nativo, sem stub**: o provider serve sub-barras de 1 min (15% doji, 3% volume 0, viragens de dia) e o PineTS avalia o `ltfSigned` do próprio indicador no contexto intrabar; mais uma execução com intrabars esparsos (2 das 5 sub-barras) | 5 intrabars/barra, tier 2, delta = referência JS da regra da vela (lado transportado entre barras) e do BVC por intrabar (erro ≤ 1e-7); esparsos: 2 intrabars/barra e «⚠ poucos intrabars» (2.0 de 5 possíveis) na tabela |
| T11 | Timeframes fora dos 5 min (`target.run(…, { timeframe })`): 1m com Auto (intrabars = gráfico) e com 1S, 1h, D (âncora Auto e âncora diária inválida), W, gráfico de 1S com Auto, e âncora «Sessão personalizada» em 5m (0830-1515 e 1700-1600, que atravessa a meia-noite). A auditoria de eventos do T6 corre também em 1m/1S (ke = 15), 1h (ke = vida = 1) e 15m/1S com absorções de uma barra e lados opostos em barras seguidas (ke = 1: tem de haver ≥ 1 inversão de lado com evento nas duas barras) | qualidade por precisão (1m/1S-Auto → 1 sem Z; 1h/D/W-Auto → 2; 1S → 3); a linha do fluxo interrompe-se exactamente nas âncoras do calendário (diária, mensal, anual, sessão; 1700-1600 só às 17:00, nunca também à meia-noite); tabela com o estado/âncora esperados («Sem sinais no gráfico de 1 min: escolha 1S ou 1T», «… de 1 s: escolha 1T», «âncora inválida»); nota «Apenas contexto» só em ≥ 1h; alert() começa por «HARNESS:SYNBTC 1 min ·» / «… 1 h ·» (prefixo da bolsa; horas em h) |

## Como funciona

### Stub do `request.security_lower_tf`
O PineTS executaria o pedido LTF a partir do provider, mas o harness precisa de controlar o delta de cada barra.
A linha única do pedido intrabar, que o harness exige numa só linha física,

```pine
[aCand, aBvc, aVol] = request.security_lower_tf(syminfo.tickerid, ltf, ltfSigned(100), ignore_invalid_timeframe = true)
```

é substituída **em memória** (o ficheiro nunca é alterado) por `[aCand, aBvc, aVol] = __ltfStub()`, e a função
`__ltfStub()` é inserida antes dessa linha (`tests/lib/preprocess.mjs`, `tests/lib/channel.mjs`). O stub devolve 5 intrabars
por barra com pesos desiguais (somam 1), e o array do BVC vale ½ do delta, para que a soma por barra, a média de
intrabars da tabela e o input do classificador sejam exercitados. O harness falha
com uma mensagem clara se a linha não existir, estiver repetida, indentada ou partida em várias linhas físicas.

O caminho real do `request.security_lower_tf` (a função `ltfSigned` do indicador) é testado à parte no T10, sem
stub: o provider responde a `getMarketData(…, "1")` com sub-barras de 1 minuto e o PineTS executa `ltfSigned` no
contexto intrabar. A regra das cotações (bid/ask, só em "1T") não é exercitada: o provider não fornece cotações.

### Canal do delta verdadeiro
O delta de cada barra viaja nos **milissegundos do `openTime`**: `code = time % 1000 ∈ [0, 998]` e
`Δ = nz(volume)·(code/499 − 1)`; `code = 999` significa "barra sem intrabars" (o stub devolve arrays vazios, o que
exercita o fallback, como acontece para lá do limite de intrabars). Resolução: 1/499 em Δ/V; o gerador quantiza o
delta da mesma forma, por isso o delta "verdadeiro" dos testes é exactamente o que o script lê. Como os limites de
dia/semana/mês são múltiplos de segundos, um desvio < 1 s não altera `timeframe.change`, `session.isfirstbar` nem a
âncora — o T0 verifica-o.

### Provider, timeframe e syminfo
`tests/lib/pinets.mjs` cria um provider em memória: `new PineTS(provider, "HARNESS:SYNBTC", "5", n)` dá
`timeframe.in_seconds() = 300` e `timeframe.isintraday = true`; `getSymbolInfo()` define `syminfo.mintick = 0.01`,
`syminfo.volumetype = "base"`, `timezone = "UTC"`, `session = "24x7"`. `getFootprintData()` alimenta
`request.footprint()` na edição Footprint (um nível por barra com compra = V(1+q)/2 e venda = V(1−q)/2).

### Inputs
Os overrides passam pela API do PineTS (`new Indicator(código, { varId: valor })`). Para enums, o PineTS espera o
**título** da opção e **ignora em silêncio** valores desconhecidos; por isso `tests/lib/inputs.mjs` resolve
`membro` → título a partir das declarações `enum` do próprio script, valida tudo e falha alto
(ex.: `{ modeIn: 'imp', precIn: 's1', anchIn: 'w1' }`).

### Títulos dos plots
`tests/lib/discover.mjs` lê os `plot(...)` do ficheiro gerado e associa papéis (linha de preço, linha CVD, Z, delta,
σr, σΔ, ρ, tier, gate, …) por regex; havendo vários candidatos, usa o que tem mais valores finitos (ex.: "Z (valor)"
do Data Window em vez de "Z da divergência"). Títulos repetidos aparecem no
PineTS como `Título#n` e são tratados. Etiquetas com `force_overlay = true` são lidas de `__labels_overlay__`.

### Shims
Política: nunca editar o indicador; se o PineTS não implementar um built-in usado, acrescenta-se um shim textual em
`tests/lib/preprocess.mjs` (lista `SHIMS`) e documenta-se aqui. A sonda do T0 lista os built-ins usados que faltam.

| ID | Estado | O que faz |
|----|--------|-----------|
| `runtime.error→harness` | desligado (opt-in com `--shim runtime.error→harness`) | troca `runtime.error(msg)` por um registo + plot `__harness_runtime_error`, para diagnosticar sem abortar. Não é necessário: os dados sintéticos têm volume. |

Com o PineTS 0.11.0, todos os built-ins do indicador que foram sondados existem (incluindo `request.footprint`,
`footprint.*`, `timeframe.change/in_seconds`, `session.isfirstbar_regular`, `color.from_gradient`, `str.format`,
`label.*`, `table.*`, `alertcondition`, `input.enum`).

### Diferenças conhecidas entre o PineTS e a TradingView
- `barstate.isconfirmed` é verdadeiro em todas as barras históricas (como na TradingView); os alertas são lidos com
  `setAlertMode('all')`.
- `session.isfirstbar` = primeira barra de cada dia na timezone do símbolo (UTC aqui), como num símbolo cripto 24x7.
- A grelha semanal do PineTS recomeça a 1 de Janeiro; os dados sintéticos começam numa segunda-feira e não cruzam
  o ano.
- O PineTS é mais permissivo do que o compilador (ordem de declaração, qualificadores `simple`/`series`, limite de
  64 plots, tipos em ternários de tuplos): um script que passa aqui pode ainda não compilar na TradingView.

## O harness apanha erros reais? (testes de mutação)

Treze erros plausíveis foram injectados em cópias de `tests/fixtures/standin.pine` e o harness
(`--only T4,…,T10 --quick`) falhou em todos:

| Mutação | Apanhada por |
|---------|--------------|
| σ sem desfasamento (`sr` em vez de `sr[1]`) | T8 (\|ΔZ\| com janela cheia) |
| RMS inclui a barra actual | T8 |
| sinal de Z trocado | T6, T8 |
| σ não congelado no modo sig | T7 |
| Z calculado também com tier ≤ 1 | T9 (+ WARN no T4) |
| fallback CLV em vez de BVC-Normal | T9 |
| sem winsorização ±c | T8 |
| "CVD ancorado" não reinicia | T7 |
| delta intrabar ignorado | T4–T9 |
| eventos de absorção nunca disparam | T6 |
| λ OLS usado em "vol-matched" | T7 |
| precisão "1 minuto" tratada como tier 3 | T9 |
| regra da vela sem lado transportado (`dir := pDir`) | T10 |

### Mutações no indicador real (revisão 1)

Vinte mutações aplicadas a cópias de `price_cvd_normalizer.pine` (Standard), corridas com
`--target std --file-std MUTANTE --only T4,…,T11 --quick`: 19 apanhadas.

| Mutação | Apanhada por |
|---------|--------------|
| σ sem desfasamento | T7, T8 |
| sinal de Z trocado | T6, T8 |
| hqOk ignora o tier | T8, T9, T11 |
| σ não congelado no modo sig | T7 |
| resoluções «continuação»/«segurou» trocadas | T6, T11 |
| teste de sinal do preço sem fluxo trocado | T6, T11 |
| etiqueta em todas as barras do aglomerado (sem `not absPrev`) | T6, T11 |
| deriva com SMA não desfasada | T7 |
| modo janela móvel com σ congelado | T7 |
| cone a ±1σ | T7 |
| alerta Z em todas as barras (sem 1.º cruzamento) | T6, T11 |
| absorção sem gate | T6 |
| RMS inclui a barra actual | T8 |
| z-score de níveis centrado em SMA[1] | T7 |
| alerta «travado» só na 1.ª barra da absorção | T6 |
| hqOk com a regra antiga (N barras) | T8 |
| ordem antiga do tier (1S num gráfico de 1S = alta) | T11 |
| alertas de resolução sem o lado (evSide já reiniciado) | T6 |
| linha do fluxo sem interrupção na âncora | T7, T11 |
| **sobrevive:** NAR calculado com o delta sem deriva | — (só na tabela, com 2 casas, e só com a deriva removida: ±0.01 em dados nulos) |

### Mutações no indicador real (revisão 2, verificação de execução)

Oito mutações dirigidas a saídas que nenhum teste verificava (`--only T4,…,T11 --quick`). Antes das verificações novas só
1 era apanhada; com as verificações novas do T6/T8 passam a ser 4. As restantes ficam documentadas como lacunas.

| Mutação | Apanhada por |
|---------|--------------|
| BVC na barra com z limitado a ±1 | T9 |
| textos dos estados de Z ≤ −limiar trocados | T6 (texto do estado nas mensagens alert(), novo) |
| P_K = Σu_r/K em vez de /√K | T8 (P_K/F_K, novo) |
| λ OLS sem o factor ρ | T8 (λ OLS, novo) |
| gap de abertura com 30σ em vez de 3σ (METODOLOGIA §3.1) | T8 desde a revisão 3 (séries com saltos de abertura) |
| gap sem `session.isfirstbar` | T8 desde a revisão 3 |
| η sem λ OLS | T8 desde a revisão 3 (η contra a referência JS) |
| **sobrevive:** regra das cotações (bid/ask) invertida | — o provider do PineTS não fornece cotações (só se aplica a «1T»): não testável aqui |

### Mutações no indicador real (revisão 3)

Onze mutações dirigidas às alterações da revisão 3 do indicador e às lacunas da revisão 2, aplicadas a cópias da
edição Standard (`--target std --file-std MUTANTE --only T4,…,T11 --quick`): todas apanhadas.

| Mutação | Apanhada por |
|---------|--------------|
| gap de abertura com 30σ em vez de 3σ (METODOLOGIA §3.1) | T8 (séries com saltos de abertura) |
| gap sem `session.isfirstbar` | T8 |
| η sem λ OLS | T8 (η contra a referência JS) |
| sessão personalizada com a regra antiga (`dayChg` também em sessões que atravessam a meia-noite) | T11 (1700-1600) |
| «travado» sem excluir a classe CONFIRMADO (s·zP ≥ \|ρ\|·\|zF\|) | T6 (série nula com \|zP\| travado ≤ 3; com o máximo por omissão 0.5 a exclusão é inócua) |
| alertas de Z sem histerese (1.º cruzamento simples) | T6, T11 |
| sem reinício das linhas na costura da cobertura | T7 (costura) |
| qualidade alta também com o classificador BVC | T9 |
| qualidade alta com qualquer LTF em segundos (ex.: 30S) | T9 |
| setas ↑/↓ das resoluções trocadas | T6, T11 |
| divergência por pivots sem a magnitude mínima em σΔ | T6 (referência dos pivots) |

### Mutações no indicador real (revisão 4)

Cinco mutações dirigidas às regras de calibração, de aglomeração e de qualidade acrescentadas depois da revisão 3,
aplicadas a cópias da edição Standard (`--target std --file-std MUTANTE --only T6,T9,T11 --quick`): todas apanhadas.

| Mutação | Apanhada por |
|---------|--------------|
| eventos sem o mínimo de 2N valores de calibração do zF/zP (só 20·ke) | T6 |
| aglomerados com a regra antiga `cond and not cond[1]` (sem lado nem período refractário) | T6, T11 |
| rótulos sem o sufixo de confiança («(baixa conf.)» / «(cal. prov.)») | T6, T11 |
| volume de ticks com qualidade média em vez de baixa | T9 |
| alertas de Z sem o mínimo de 2N valores de calibração | T6, T11 |

Continua por verificar numericamente: o NAR (só na tabela, com 2 casas) e a regra das cotações em «1T» (sem cotações
no provider do PineTS).

## Ficheiros

- `tests/run_tests.mjs` — orquestrador e relatório.
- `tests/lib/channel.mjs` — canal do delta e código Pine do stub.
- `tests/lib/synth.mjs` — gerador sintético determinístico (AR(1) no fluxo, r = λΔ + ε com corr ≈ 0,5, episódios).
- `tests/lib/datasets.mjs` — conjuntos de dados de cada teste.
- `tests/lib/preprocess.mjs` — stub LTF, shims, utilitários de texto Pine.
- `tests/lib/inputs.mjs`, `tests/lib/discover.mjs` — inputs e títulos.
- `tests/lib/pinets.mjs`, `tests/lib/pine_worker.mjs` — carregamento do PineTS, provider, execução em workers.
- `tests/lib/harness.mjs` — alvo (ficheiro, código preparado, inputs, papéis) e cache de execuções.
- `tests/lib/report.mjs`, `tests/lib/util.mjs` — relatório e utilitários numéricos.
- `tests/lib/refz.mjs` — referência JS de METODOLOGIA §3.1 (guarda de gaps), §3.3 e §6 (escalas, D, Z, gate) e de zF/zP (§7.1).
- `tests/lib/builtins.mjs` — sonda de built-ins.
- `tests/lib/tests_static.mjs`, `tests/lib/tests_runtime.mjs` — T1–T3 e T0/T4–T11.
- `tests/fixtures/standin.pine` — script Pine v6 de substituição (não é o indicador) que imita as construções-chave
  do indicador; serve para validar o harness (`npm run test:standin`).

A validação com dados reais (BTCFDUSD 5m com delta verdadeiro do agressor) é feita fora do repositório; os dados
de mercado nunca são versionados.
