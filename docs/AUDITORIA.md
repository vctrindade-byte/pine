# Auditoria externa

Registo, ponto a ponto, de uma auditoria externa ao indicador (Outubro de 2026) em quatro áreas: Pine v6, lógica do
indicador, validade estatística e utilidade para negociação real. Para cada ponto: a classificação, a nossa avaliação
com as provas, o que mudou e o que continua por testar.

- As referências «l. n» são linhas de `src/price_cvd_normalizer.src.pine` na versão actual. Se se deslocarem, o
  identificador citado ao lado permite encontrá-las.
- Os números medidos vêm de [VALIDACAO.md](VALIDACAO.md), do dossier de investigação
  ([research-dossier.md](research-dossier.md)) e, para o S&P 500, do estudo de eventos em
  [ESTUDO_SP500.md](ESTUDO_SP500.md). A marca [E] indica trabalho próprio, na própria amostra e não revisto
  por pares.
- As fórmulas estão em [METODOLOGIA.md](METODOLOGIA.md); os testes, em [tests/README.md](../tests/README.md).

**Classificação usada.**

| Classe | Significado |
|---|---|
| **Erro confirmado** | Reproduzimos o problema no código. Foi corrigido e há testes que o apanham. |
| **Risco provável** | O código faz o que diz, mas a forma como é lido, ou o que ainda não foi verificado, pode levar a conclusões erradas. É tratado com documentação ou medições; uma parte fica por verificar. |
| **Questão que exige backtest** | Não se decide com testes de código: exige um estudo de retornos seguintes com controlos, custos e dados fora da amostra. |

## Resumo

| Ponto | Área | Classificação | Estado |
|---|---|---|---|
| [(a)](#a-volume-em-falta-tratado-como-volume-zero) Volume em falta (*na*) tratado como volume 0 | Pine v6 e lógica | Erro confirmado | Corrigido: regra das barras sem observação de fluxo, avaliada no volume da fonte; T10 e T12 |
| [(h)](#h-requisitos-da-plataforma-e-compilação) Requisitos da plataforma e compilação | Pine v6 | Risco provável (não verificado) | Por verificar na TradingView |
| [(e)](#e-modos-de-visualização) Modos de visualização | Lógica | Risco provável (de leitura) | Sem alteração de código; documentado |
| [(g)](#g-pivots-desenhados-no-pivot-conhecidos-r-barras-depois) Pivots desenhados no pivot, conhecidos R barras depois | Lógica | Risco provável (de backtest) | Documentado: um backtest entra na confirmação |
| [(b)](#b-o-z-não-é-um-z-score-gaussiano) O Z não é um z-score gaussiano | Estatística | Risco provável (de leitura) | Concordamos: Z descrito como score empírico; frequência empírica por gráfico na dica do Z; medida também no ES (6,1–6,8% por ano) |
| [(c)](#c-a-qualidade-é-uma-classificação-não-uma-garantia) A qualidade é uma classificação, não uma garantia | Estatística | Risco provável (de leitura) | Concordamos: documentado |
| [(d)](#d-o-gate-ρ-pode-filtrar-regimes-relevantes) O gate ρ pode filtrar regimes relevantes | Estatística | Questão que exige backtest | Em aberto: no ES com o delta «Auto» o gate quase nunca fecha e as variantes são todas nulas; hoje o gate não se desliga por completo |
| [(f)](#f-os-eventos-de-absorção-são-hipóteses) Os eventos de absorção são hipóteses | Negociação | Questão que exige backtest | Concordamos: mecanismos alternativos listados; no S&P 500 as absorções não acrescentam direcção ao preço |
| [(i)](#i-plano-de-validação) Plano de validação | Negociação | Questão que exige backtest | Respondido para o S&P 500 com o delta «Auto»: resultado nulo depois de controlos e custos. Por fazer: fluxo verdadeiro ou 1S, dados servidos pela TradingView, outros mercados |

Saldo: um erro de código confirmado e corrigido; o resto pede leitura cuidadosa ou testes. Nada nesta auditoria nem na
validação mostra uma vantagem negociável. O estudo S&P 500 testou-o directamente no ES, no MES e no SPY: nenhuma das 16
classes de sinais prevê o retorno seguinte, e nenhuma regra simples ganha depois de custos
([ESTUDO_SP500.md](ESTUDO_SP500.md)).

---

## 1. Pine v6

### (a) Volume em falta tratado como volume zero

**Classificação: erro confirmado. Corrigido.**

**Ponto.** `nz(volume)` juntava «volume em falta» (*na*: o fornecedor não deu o valor) com «volume = 0» (sem
negócios). Essas barras entravam em σ, ρ, Z e nos eventos como observações (r, Δ = 0), um falso «preço sem fluxo», e
herdavam a qualidade da barra anterior. Além disso, o teste usava o volume do **gráfico** mesmo quando o delta vinha dos
intrabars ou do footprint.

**Avaliação.** Confirmado, e com um âmbito mais largo do que o descrito:

1. O BVC na barra usava `nz(volume)`: com o volume em falta, o delta era 0 em vez de *na*.
2. A regra antiga «volume 0 → delta 0 e qualidade anterior» mantinha a barra como observação. Entrava em σr, σΔ, ρ,
   nas somas K e k_e, no RMS e nos eventos; se o preço se movesse nessa barra, era um «preço sem fluxo» fabricado; e
   contava para a sequência de qualidade (hqRun).
3. O teste usava o volume do gráfico mesmo com a fonte intrabar ou footprint. Um footprint com negócios numa barra
   com volume do gráfico 0 ou *na* ficava com delta 0; uma barra com volume no gráfico mas intrabars sem volume
   contava como observação normal.
4. Dentro do pedido intrabar, `ltfSigned` devolvia `nz(volume)` como volume: um intrabar sem volume valia 0.
5. A tabela não indicava que a qualidade mostrada nessas barras era herdada.

**O que mudou.**

- `ltfSigned` devolve o volume tal como vem (l. 480). O BVC na barra é *na* quando falta o volume (`barDelta`, l. 588).
- `barVol` é o volume da **fonte escolhida** (l. 624–649): o do gráfico com o BVC na barra («Só barras do gráfico» ou
  recurso); a soma dos intrabars, *na* se faltar em algum (ciclo explícito, l. 636–643); `footprint.total_volume()`
  com o footprint.
- `volMiss` (fonte com volume *na*), `noTrade` (volume 0) e `noObs` (um dos dois) (l. 656–662). Numa barra sem fonte
  (qualidade 0, «Barras sem intrabars» = Nenhum) decide o volume do gráfico. Nas barras sem observação, o delta fica
  *na* (volume em falta) ou 0 (sem negócios) e a qualidade é a anterior.
- Fora das estatísticas: `deltaObs`, `d` e `r` ficam *na* (l. 706–710). `ta.stdev`, `ta.correlation`, `ta.sma` e
  `math.sum` saltam os *na*, por isso as janelas contam observações. `hqOk` exige `not noObs` (l. 736): nessas barras
  não há D, Z, gate nem eventos, e o D anterior não é repetido.
- `hqRun` passa a contar observações: as barras sem observação não o incrementam nem o reiniciam (l. 666–671). O
  período refractário dos aglomerados conta observações (`obsIdx`, l. 1024). Os pivots usam `lqBar`, a última barra
  **observada** de qualidade < média (l. 667–671, 1218, 1236), em vez do teste antigo com hqRun.
- Linhas: `dDisp` (l. 712) é 0 nas barras sem negócios (as linhas continuam) e *na* com o volume em falta (as linhas
  interrompem-se). `cvdC`, `cvdA`, `firstInit`, `pLine` e `fLine` usam-no (l. 859, 901, 927, 977–978).
- Tabela e alertas: estados «Sem negócios nesta barra» e «Sem volume nesta barra (dados em falta)»; fonte «sem negócios
  (…)» ou «volume em falta (…)» e «qualidade anterior: …» (l. 787–790, 805–807).
- O NAR do histórico exclui essas barras (l. 694).
- Documentação: README («Barras sem negócios ou sem volume»); metodologia, secções 2.6 (regra 5), 3.2, 5.3, 6.4, 7.3
  e 8; testes T10 e T12 ([tests/README.md](../tests/README.md)).

**Provas.**

- Dados reais (BTCFDUSD, 5 minutos, delta verdadeiro): 20 das 33 696 barras têm volume 0, todas sem variação de preço;
  nenhuma tem volume em falta. Nas duas janelas da validação há 2 e 9 dessas barras. O Pine não tem Z nem gate aberto
  em nenhuma delas e coincide com a referência Python que aplica a mesma regra (corr 1,000000; |ΔZ| máx 6,7 × 10⁻¹⁰).
  Com a regra antiga, o Z das barras vizinhas muda até 0,83 e 1,44 e P(|Z| ≥ 2) da segunda janela passa de 6,07% para
  6,05% ([VALIDACAO.md](VALIDACAO.md), secção 3.2) [E].
- O efeito agregado é pequeno neste par líquido e sem buracos de volume. Num símbolo com muitas barras sem negócios
  (pouco líquido, fora de horas) ou com volume em falta, a regra antiga distorceria σ, ρ e Z de forma visível.
- Testes: T10 (volume em falta nos intrabars, com o pedido intrabar nativo) e T12 (integridade do volume), com
  mutantes automáticos. A regra antiga falha 18 de 32 verificações na Standard e 31 de 48 na Footprint; uma regra que
  exigisse uma fonte (`tier > 0`) falha 2 de 2; `nz(volume)` no `ltfSigned` falha 3 de 4. Outras onze mutações manuais
  dirigidas à regra nova foram todas apanhadas ([tests/README.md](../tests/README.md)).

**Por testar.** Quando a TradingView dá `volume` *na* em vez de 0, no gráfico e nos intrabars (por exemplo em índices);
se um intrabar de 1S ou 1T pode existir sem negócios; o comportamento em tempo real. O caso «gráfico com volume 0,
intrabars com volume» não é representável com o stub do harness (está testado com o footprint)
([VALIDACAO.md](VALIDACAO.md), secções 4 e 5).

### (h) Requisitos da plataforma e compilação

**Classificação: risco provável (não verificado).**

**Ponto.** Os requisitos de plano e a compilação na TradingView ainda não foram verificados.

**Avaliação.** É verdade: não houve acesso ao compilador da TradingView. O que existe:

- parse das duas edições com `pynescript` 0.3.0, sem erros;
- built-ins procurados em duas cópias da referência do Pine v6 (Standard 96/96; Footprint 99/99 com o segundo
  espelho, que documenta os dois `footprint.*`);
- o harness PineTS (T0–T12, 774 verificações, todas PASS), que executa o código mas não é o compilador da
  TradingView;
- limites contados no código: 44 de 64 plots (48 no pior caso), 1 ou 2 pedidos `request.*` de 40, 407 e 412
  variáveis globais declaradas de 1000 (as temporárias do compilador não se podem contar fora da TradingView);
- a construção nova desta ronda, o ciclo `for … in` sobre o array de volumes dos intrabars, foi verificada contra a
  referência.

Requisitos de plano: footprint em Premium ou Ultimate [V, manual]; limites de intrabars de 100K, 125K e 200K [V,
manual]; intervalos de segundos em Premium ou superior e de ticks em Ultimate [V-sec, página de preços vista por fonte
secundária]. Não documentados: a profundidade histórica do footprint, a presença de bid/ask nos intrabars «1T»
históricos, o comportamento da edição Footprint em planos inferiores.

**O que mudou.** Nada no código. O README apresenta os planos como indicativos.

**Por testar.** A lista de verificação no Pine Editor ([VALIDACAO.md](VALIDACAO.md), secção 5): compilação das duas
edições, Standard num plano inferior, Footprint com e sem a fonte Footprint, 1S/1T sem plano, `display` dependente de
inputs, limites de variáveis, alertas, tempo real e as barras sem observação de fluxo.

---

## 2. Lógica do indicador

### (e) Modos de visualização

**Classificação: risco provável (de leitura).**

**Ponto.** Os modos de visualização: o que mostram e se podem ser lidos como sinal.

**Avaliação.** Nenhum sinal depende do modo. O Z, os eventos e os alertas usam os incrementos r e d (metodologia,
secções 6 e 7); os pivots usam o CVD contínuo. O modo só escolhe o que as duas linhas desenham (`pSel`, `fSel`,
l. 962–978). O risco é de leitura:

- **Z-score de níveis e mín–máx** são só visuais e não geram sinais. Com dois passeios aleatórios independentes,
  z^P − z^F passa |2| em cerca de 33% das barras; o mín–máx teve a menor capacidade de detecção (AUC 0,54–0,55)
  (metodologia, secções 5.6, 5.7 e 6.8) [E].
- **Unidades-σ ancoradas** (por omissão): a distância entre as linhas é o resíduo acumulado desde a âncora, não o Z.
  A linha do fluxo afasta-se naturalmente mais: no fim do dia, |F̃| teve mediana 17, p90 63 e máximo 324 em 5 minutos.
  A linha do fluxo saiu do cone nulo iid em 17% (5 min) e 10% (15 min) das barras, contra 4,6% sob a hipótese iid
  ([VALIDACAO.md](VALIDACAO.md), secção 3.6) [E].
- **Preço implícito pelo fluxo**: |P̂/C − 1| com percentil 99 de 9% e máximo de 44% em 117 dias de 5 minutos. É uma
  referência visual, não um preço justo.
- A cor do preenchimento é o Z, não a distância entre as linhas, e as duas podem discordar.
- Com a correcção do ponto (a), as linhas continuam numa barra sem negócios e interrompem-se numa barra com o volume
  em falta. São níveis: se o preço se mover numa barra sem negócios, a linha do preço mostra-o, mas o Z não o conta.

**O que mudou.** Nada no código nesta ronda; o README e a metodologia já tinham estes avisos e números.

**Por testar.** A legibilidade na TradingView (lista da secção 5 de [VALIDACAO.md](VALIDACAO.md)). Manter ou retirar os
modos só visuais é uma decisão de produto, não uma questão estatística.

### (g) Pivots desenhados no pivot, conhecidos R barras depois

**Classificação: risco provável (de backtest).**

**Ponto.** As divergências por pivots são desenhadas na barra do pivot, mas só são conhecidas R barras depois.

**Avaliação.** Correcto, e é assim por construção. `ta.pivothigh` e `ta.pivotlow` só confirmam o pivot Ri barras
depois (l. 1193–1194). O CVD é lido na barra do pivot (`cvdC[pivRIn]`, l. 1195). O rótulo vai para a barra do pivot
(`label.new(pb, …)` com pb = bar_index − Ri, l. 1222 e 1239). As `alertcondition` e o `alert()` saem na barra de
confirmação (l. 1581–1582 e 1589). O indicador não usa barras futuras, mas um rótulo visível na barra do pivot **não
existia** nessa barra. O mesmo acontece:

- nos rótulos de absorção, que recebem a resolução («→ continuação», «→ absorção segurou», «→ expirou», «→ substituído»)
  e a cor direccional na barra em que ela acontece (l. 1090–1124);
- na idade do «último evento» da tabela, contada a partir do pivot (l. 1256).

**Regra para um backtest.**

- Entrar só na barra de confirmação t = pivot + Ri, no fecho dessa barra ou na abertura da seguinte; nunca no pivot.
- Nos eventos de absorção, entrar no fecho da barra do evento e não usar a resolução como informação de entrada.
- Ler os sinais das `alertcondition`, do `alert()` ou dos plots, não dos rótulos de um gráfico histórico.

**O que mudou.** Documentação: README («Divergência por pivots») e metodologia (secção 8).

**Por testar.** Os pivots nunca foram testados contra retornos seguintes. A única evidência é de extremos de 4 horas
(não destes pivots): os novos extremos reverteram por si sós −6 a −8 bps a 2–3 h; com não-confirmação do CVD, −5,5 a
−7,5 bps contra −1 a −2 bps com confirmação, diferença não significativa [E].

---

## 3. Validade estatística

### (b) O Z não é um z-score gaussiano

**Classificação: risco provável (de leitura). Concordamos.**

**Ponto.** O Z não é um z-score de uma normal padrão; |Z| ≥ 2 e |Z| ≥ 3 não têm as probabilidades de 4,6% e 0,27%.

**Avaliação.** Correcto. O Z é um **score empírico de divergência**: D é uma soma móvel de K = 20 diferenças de
unidades-σ winsorizadas, sobreposta de barra para barra, dividida pelo RMS não centrado dos seus M valores anteriores
(l. 738–741). O RMS faz com que
E[Z²] ≈ 1, mas não torna o Z normal:

- **Soma sobreposta e autocorrelação.** Dois Z seguidos partilham 19 de 20 termos. Em dados reais, a autocorrelação
  do Z foi 0,93–0,94 a 1 barra e 0,43–0,56 a 10 barras. As barras com |Z| ≥ 2 vêm em blocos: na primeira janela,
  537 barras formam 127 blocos contíguos e deram 60 alertas de Z (primeiro cruzamento com histerese e gate aberto).
  Uma frequência de barras não é uma frequência de episódios independentes [E].
- **Memória longa do fluxo** (rácio de variâncias VR20 de u_d = 1,30 [E]; Lillo e Farmer [V]) e volatilidade
  intradiária variável.
- **Caudas pesadas.** u_d tem curtose de 100–220 antes da winsorização [E]. Depois dela, a curtose do Z foi 4,4 e 7,3
  nas duas janelas (3 numa normal) [E].
- **Frequências medidas** com o delta verdadeiro e calibração completa: P(|Z| ≥ 2) = 6,19% e 6,07% (5 min) e 5,35%
  (15 min), contra 4,55% numa normal; P(|Z| ≥ 3) = 1,61%, 1,04% e 1,48%, contra 0,27% (4 a 6 vezes mais). Na série
  sintética nula do T5, 5,37% e 0,26%: a simulação tem caudas mais leves do que os dados reais. Com calibração
  provisória (100–199 valores), os extremos são 1,3 a 1,6 vezes mais frequentes ([VALIDACAO.md](VALIDACAO.md), secções
  2, 3.3 e 3.6) [E].

**O que mudou.**

1. Texto: o Z é descrito como score empírico de divergência no README, na metodologia (secções 6.1 e 6.8) e na
   validação. Os limiares 2 e 3 são marcas convencionais, não probabilidades.
2. Contadores só de medição (`zN`, `zN1`, `zN2`, `zNGo`, `zNG`, l. 764–774; dica do Z, l. 1449–1458). Mostram a
   frequência empírica de |Z| ≥ limiar e ≥ limiar forte **neste gráfico**, nas barras fechadas com Z e pelo menos 2N
   valores de calibração, e a parte dessas barras com o gate aberto, com a frequência de |Z| ≥ limiar entre elas. Não
   alteram o Z, o gate, os eventos nem os alertas. Os testes T5 e T12 comparam os contadores com uma recontagem a
   partir dos plots. Em dados reais a dica mostrou 6,2%, 1,61% e, com o gate aberto (89,7% das barras), 6,3% na
   primeira janela; 6,1%, 1,05% e 6,5% (gate aberto em 80,3%) na segunda, iguais à recontagem.

**Por testar.** A frequência da dica é medida na própria amostra, sobre barras sobrepostas: não é um p-valor nem um
nível de confiança. A calibração foi medida num par cripto à vista e, com o delta de 1 minuto, no ES de 2008–2026:
P(|Z| ≥ 2) de 6,47% em 5 minutos (6,1–6,8% em cada ano) e 5,75% em 15 minutos, P(|Z| ≥ 3) de 1,43% e 0,98%. No ES, o Z
não está calibrado por hora do dia: |Z| ≥ 2 em 8,9% das barras do horário regular e 5,5% das do electrónico (5 minutos),
porque o RMS é calculado sobre toda a sessão Globex ([ESTUDO_SP500.md](ESTUDO_SP500.md), secção 6).

### (c) A qualidade é uma classificação, não uma garantia

**Classificação: risco provável (de leitura). Concordamos.**

**Ponto.** A qualidade (alta, média, baixa) não garante que o lado agressor foi observado, nem com o footprint.

**Avaliação.** Correcto. O nível é atribuído pela **configuração** dos dados: a fonte (footprint, intrabars, barra do
gráfico), o timeframe dos intrabars face ao do gráfico, o classificador e o tipo de volume declarado (l. 610–617,
626–649). Não é uma medição, barra a barra, da exactidão do delta. O Pine não dá acesso às marcas de agressor da bolsa:
todas as fontes são estimativas.

- **Footprint.** A TradingView classifica-o «com base na acção do preço intrabar» [V-sec]. Nunca foi comparado aqui com
  o delta verdadeiro: a corrida «Footprint» da validação alimenta o footprint com o delta verdadeiro e só prova que os
  dados chegam ao cálculo.
- **1S com a regra da vela (alta).** Correlação com o delta verdadeiro de 0,90 em BTCFDUSD, 0,83 em BTCUSDT e 0,71 em
  acções (LOBSTER); correlação parcial, dado ΔP, de 0,80–0,88 em cripto (metodologia, secção 2.7) [E].
- **1 minuto (média).** O Z com delta estimado correlacionou 0,68 com o Z do delta verdadeiro; das 537 barras com
  |Z| ≥ 2 pelo delta verdadeiro, só 246 passaram o limiar com o estimado. O gate abriu mais vezes (94,7% contra 89,7%)
  porque a estimativa inflaciona ρ [E].
- **Volume de ticks não declarado** (por exemplo CFD) não é detectado: a qualidade segue a fonte, com Z e eventos.
- **Barras sem observação de fluxo** herdam a qualidade anterior; a tabela passa a dizê-lo («qualidade anterior»).

**O que mudou.** Documentação (README, «Qualidade dos dados»; metodologia, secção 2.6) e a indicação da qualidade
herdada na tabela.

**Por testar.** A fidelidade do footprint e de 1S/1T da TradingView contra o delta da bolsa, mercado a mercado. Em
Pine não é possível uma medida de qualidade por barra.

### (d) O gate ρ pode filtrar regimes relevantes

**Classificação: questão que exige backtest. Em aberto.**

**Ponto.** O gate ρ pode esconder regimes em que a divergência é relevante.

**Avaliação.** É plausível e não foi medido. O gate (l. 754–755) exige que o ρ̂ das N observações anteriores seja pelo
menos max(ρmin, tanh(1,96/√(N − 3))), além da qualidade ≥ média. Um ρ baixo pode vir de dados maus, que é a razão do
gate, mas também de regimes com interesse: preço descoberto noutra bolsa ou por ordens limite, notícias sem negócios,
ou absorção prolongada. Fluxo forte sem preço durante muitas barras baixa o próprio ρ e pode fechar o gate exactamente
no regime que os eventos de absorção procuram. Medido: gate aberto em 89,7% e 80,2% das barras nas duas janelas de
5 minutos, 84,4% em 15 minutos e 94,7% com delta estimado de 1 minuto; passagem nula de 0,25–0,5% [E]. O que acontece
depois das barras com o gate fechado não foi medido.

**Hoje o gate não se desliga por completo.** O input «ρ mínimo (gate)» aceita 0 (l. 350), mas o limite de Fisher
continua: com ρmin = 0, o gate exige ρ̂ ≥ 0,196 com N = 100, 0,113 com N = 300 e 0,360 com N = 30 (com N = 30 o limite
de Fisher já supera os 0,30 por omissão). Os eventos (l. 1015–1017), os alertas de Z (l. 1522–1523) e os quatro
estados exigem o gate aberto.

**O que uma comparação «sem gate» ou com outros limiares precisaria.**

- **Z.** O Z não depende do gate: só precisa de hqOk, e o RMS é calibrado em todas as barras com D (l. 739–741). Os
  plots «Z (valor)», «Gate (1 = aberto)» e «ρ(r, Δ)» chegam para comparar o Z com o gate como está, sem gate, só com
  o limite de Fisher ou com outros limiares, sem alterar o indicador.
- **Eventos.** É preciso rederivar as classes a partir dos plots zF, zP e ρ com outra regra de gate, incluindo os
  aglomerados e o período refractário (a auditoria de eventos do T6 já rederiva as classes assim), ou acrescentar um
  input de investigação que desligue o limite de Fisher.
- **Desenho.** As mesmas barras e a mesma calibração em todas as variantes; variantes fixadas antes de ver os
  resultados (sem gate, só Fisher, ρmin de 0,2, 0,3 e 0,4, tercis de ρ̂); as medidas do ponto (i) (retornos em
  unidades de volatilidade a 5, 15, 30 e 60 minutos, MFE/MAE, controlos, custos), com correcção de testes múltiplos e
  confirmação fora da amostra.

**O que mudou.** Nada no código.

**Actualização: estudo S&P 500 (Outubro de 2026).** O desenho acima foi aplicado ao ES de 2008–2026, com o delta
«Auto» (intrabars de 1 minuto): gate por omissão, sem gate (só qualidade), ρmin 0,20 e 0,40, nas mesmas barras e com a
mesma calibração ([ESTUDO_SP500.md](ESTUDO_SP500.md), secção 9). As quatro variantes dão 0 de 16 classes significativas
aos 30 minutos. A pergunta, porém, **não fica decidida**: no ES o ρ̂ é alto (mediana 0,71 em 5 minutos) e o gate está
aberto em 98–99% das barras; desligá-lo acrescenta no máximo 27 eventos a uma classe. Na amostra de ticks, o ρ̂ com o
delta verdadeiro foi igual ao do delta de 1 minuto em 5 minutos (0,69): no ES o gate fica aberto porque a relação entre
preço e fluxo é forte. Fica por testar onde o gate fecha com frequência (SPY com horário alargado, aberto em 86% das
barras; outros mercados; delta verdadeiro).

---

## 4. Utilidade para negociação real

### (f) Os eventos de absorção são hipóteses

**Classificação: questão que exige backtest. Concordamos.**

**Ponto.** «Absorção» e «preço travado» são hipóteses sobre o mecanismo, não observações.

**Avaliação.** Concordamos. «Compras absorvidas», «preço travado» e «preço sem fluxo» descrevem o par (zF, zP) numa
janela de cerca de 15 minutos (l. 1015–1017); não identificam o mecanismo. O mesmo padrão pode vir de:

1. liquidez passiva real (ordens limite repostas, icebergs): a hipótese que dá o nome ao evento;
2. impacto côncavo: fluxo grande move o preço menos do que linearmente (Weber e Rosenow; lei da raiz quadrada [V]),
   e um |zF| alto com |zP| moderado é funcionamento normal do mercado;
3. memória longa dos sinais das ordens (metaordens divididas): o fluxo previsível move pouco o preço (Lillo e Farmer;
   Hasbrouck [V]);
4. descoberta de preço noutro mercado: em cripto o preço forma-se em várias bolsas e nos derivados; o CVD de uma bolsa
   só vê o fluxo local, que pode ser arbitragem a seguir o preço de outro lado (Makarov e Schoar [V]);
5. erro de classificação do delta: com o preço parado, a regra da vela transporta o lado anterior, e uma sequência de
   intrabars sem variação pode fabricar fluxo «sem preço»; com intrabars de 1 minuto o erro é maior (a absorção com o
   lado certo foi recuperada em cerca de 80% dos casos com 1S/1T e em 43–64% com 1 minuto [E]);
6. variação das cotações sem negócios (notícias, retirada de ofertas), no caso do «preço sem fluxo»;
7. fluxo forçado (liquidações, coberturas) contra a liquidez de *market makers* que gerem inventário;
8. artefactos de dados: cobertura parcial de intrabars, volume de ticks não declarado, *wash trading* ou fluxo
   específico de uma bolsa.

Evidência: no estudo do dossier (BTCFDUSD, janelas de 15 minutos, na própria amostra), as absorções foram seguidas de
uma ligeira continuação a 30 minutos, +7,7 bps (IC 1,5–13,7), e os «travados» de +14,6 bps (IC 7,8–22,3), numa só
bolsa; o efeito desapareceu com delta estimado de 1 minuto. Numa simulação, o sinal do efeito depende de quão
informado está o lado passivo [E]. Os eventos do código final (aglomerados, gate, calibração mínima) não foram
testados contra retornos seguintes. Na validação, 45 absorções em 31 dias resolveram-se em 21 continuações, 17
«segurou», 5 expirações e 2 substituições: são contagens, não valor ([VALIDACAO.md](VALIDACAO.md), secção 3.5).

**O que mudou.** Nada no código: os rótulos já eram neutros e o «Viés direccional» é Neutro por omissão. A metodologia
(secção 7.2) remete para esta lista.

**Actualização: estudo S&P 500 (Outubro de 2026).** No ES de 2008–2026, com o delta «Auto», as absorções foram
seguidas do mesmo retorno que choques de fluxo do mesmo tamanho confirmados pelo preço (diferença +0,015σ aos 30
minutos, p = 0,68), e nenhuma classe difere de barras aleatórias emparelhadas depois da correcção de testes múltiplos
([ESTUDO_SP500.md](ESTUDO_SP500.md), secções 7 e 8). Dois dos mecanismos da lista ficaram documentados no ES:

- **Erro de classificação (5).** Na amostra de ticks de 2013, os eventos de fluxo do delta de 1 minuto recuperaram 2 de
  15 eventos do delta verdadeiro (gráfico de 5 minutos).
- **Artefacto de dados (8).** No gráfico de 15 minutos, 58% das absorções caem nas barras das 14:45 e 15:00 CT. Quando
  a janela inclui o minuto de liquidação das 14:59 CT, o lado do evento coincide em 99,6–100% dos casos com o sinal
  dessa única vela de 1 minuto, que a regra da vela atribui inteira a um lado. As pistas de continuação de 15 minutos
  vêm desses eventos e desaparecem contra controlos da mesma barra do dia (secção 13 do estudo; análise post hoc).

**Por testar.** Os mesmos eventos calculados com o fluxo verdadeiro ou com 1S numa amostra longa; eventos com e sem
intrabars parados; fluxo de outras bolsas e dos derivados; horas de notícias.

### (i) Plano de validação

**Classificação: questão que exige backtest. Respondida para o S&P 500 com o delta «Auto»; em aberto para o fluxo
verdadeiro e para outros mercados.**

**Ponto.** Um plano em etapas: integridade dos dados, estabilidade estatística, valor preditivo em unidades de
volatilidade a 5, 15, 30 e 60 minutos, MFE/MAE, controlos, custos e validação fora da amostra.

**Avaliação.** Concordamos com o plano.

**Resposta para o S&P 500 (Outubro de 2026).** O estudo [ESTUDO_SP500.md](ESTUDO_SP500.md) aplicou o plano ao ES
(2008–2026, gráficos de 5 e 15 minutos), com o MES e o SPY como robustez: plano pré-registado, valores por omissão, o
delta que a TradingView usa por omissão (intrabars de 1 minuto, qualidade média), todas as células relatadas e correcção
de Benjamini-Hochberg. Resultado: **nulo**. Nenhuma das 16 classes de sinais prevê o retorno com sinal aos 30 minutos
(0 de 16; menor p = 0,100); o CVD não acrescenta direcção ao preço nos gémeos nem nos controlos emparelhados; nenhuma
regra ingénua tem resultado líquido positivo demonstrável depois de custos; o resultado repete-se no MES e no SPY. Os
eventos são seguidos de movimentos um pouco maiores, sem sentido definido. O código e os resultados agregados estão em
[research/sp500/](../research/sp500/README.md).

Mapeamento do que já existe e do que falta:

| Etapa | Antes do estudo S&P 500 | Estudo S&P 500 (ES, MES, SPY; delta «Auto») | O que falta |
|---|---|---|---|
| 1. Integridade dos dados | Regra das barras sem observação de fluxo e testes T10/T12 (ponto (a)); delta verdadeiro a partir das marcas de agressor; 20 barras de volume 0 em 33 696, nenhuma em falta; guarda de gaps (32 e 43 barras alteradas nas duas janelas); quantização do canal sem efeito (corr 1,00000); Pine igual à referência Python (\|ΔZ\| ≤ 7 × 10⁻¹⁰) | Ficheiros limpos com verificações (sem carimbos duplicados, preços fora da grelha nem barras OHLC incoerentes; sessões de rolagem e de contrato não dominante excluídas). Motor Python igual ao Pine real no PineTS em 12 fatias e 268 798 barras: todos os sinalizadores e alertas iguais, \|ΔZ\| ≤ 5 × 10⁻¹⁰, também com barras de volume 0, volume em falta e sem intrabars (secções 2 e 4) | Dados servidos pela própria TradingView: volume *na* contra 0, cobertura de intrabars por plano, diferenças entre histórico e tempo real, footprint e 1S/1T contra o delta da bolsa; paridade com o CVD da TradingView (lista da secção 5 de [VALIDACAO.md](VALIDACAO.md), item 9); semanas de rolagem do ES1! |
| 2. Estabilidade estatística | P(\|Z\| ≥ 2) de 6,07–6,19% em duas janelas de 5 minutos e 5,35% em 15 minutos; excesso com calibração provisória (1,3–1,6 vezes); gate aberto em 80–90% das barras; ρ mediano 0,44–0,57 conforme a janela; efeito da remoção da deriva; delta estimado contra verdadeiro ([VALIDACAO.md](VALIDACAO.md), secções 3.3, 3.4 e 3.6) | P(\|Z\| ≥ 2) de 6,1–6,8% em cada ano de 2008–2026 (ES, 5 minutos; 5,75% em 15 minutos), igual nas duas metades; MES e SPY parecidos (5,7–6,4%). Não calibrado por hora do dia: 8,9% no horário regular contra 5,5% no electrónico. Gate aberto em 98–99% das barras, ρ̂ mediano 0,66–0,71 (secção 6) | Sensibilidade a N, K, M e c; calibração separada por horário; mercados fora do S&P 500 (perpétuos, FX, acções individuais) e outras bolsas |
| 3. Valor preditivo em unidades de volatilidade (5/15/30/60 min) | Estudo de retornos seguintes do dossier (BTCFDUSD, 117 dias, t com agrupamento por dia, *bootstrap* em blocos de dias), com as definições de investigação: **Z nulo** a H = K/2 e H = K (retornos com sinal dentro de ±0,2σ√H; taxas de acerto 0,44–0,58; as células com \|t\| ≈ 2–2,5 não sobrevivem a Bonferroni sobre mais de 64 células); **ligeira continuação** depois da absorção com o delta verdadeiro (+7,7 e +14,6 bps a 30 minutos), que desapareceu com delta estimado de 1 minuto [E] | Resultado primário pré-registado (ES 5 minutos, 30 minutos, 16 classes, BH): **nulo**, 0 de 16 e nenhum p < 0,05 (médias de −0,13σ a +0,04σ). Também nulo a 5, 15 e 60 minutos, no gráfico de 15 minutos, com 1–2 minutos de latência, nas duas metades, no MES e no SPY (secções 7, 12 e 14) | Os mesmos sinais calculados com o fluxo verdadeiro ou com 1S, numa amostra longa (a amostra de ticks tem 15 sessões); outros mercados |
| 4. MFE/MAE | Nada | Medidos por classe e horizonte: excursões 1,2 a 2 vezes as de uma barra qualquer e quase simétricas (MFE − MAE entre −0,19σ e +0,23σ aos 30 minutos) (secção 10) | Nada para o S&P 500 com o delta «Auto» |
| 5. Controlos | Só o nulo da calibração (série sintética do T5; ρ ≈ 0 no dossier) e, para os pivots, a taxa base de reversão em novos extremos de 4 h | Gémeos condicionais (absorção contra choque de fluxo confirmado: +0,015σ, p = 0,68), controlos aleatórios emparelhados por ano, horário, bloco de 30 minutos, volatilidade e movimento recente do preço (0 de 18 em cada gráfico; também pela perna P_K e pela barra exacta), linha de base, gate ligado e desligado, delta verdadeiro contra estimado em 15 sessões (secções 5, 8 e 9). O CVD não acrescenta direcção ao preço | Delta permutado entre dias (placebo); horas de notícias; o gate onde ele fecha (ponto (d)) |
| 6. Custos | Nada | ES: 0,325 pontos por ida e volta (limite inferior) e 0,575 de esforço; MES 0,45 pontos e SPY 0,015 dólares por acção (aproximados). Nenhuma das 224 regras ingénuas do ES tem resultado líquido positivo demonstrável (menor p unilateral 0,028; todos os q = 1,000) (secção 11) | Derrapagem medida por hora do dia (abertura, liquidação, reabertura) e por tamanho; filtro de notícias |
| 7. Fora da amostra | Nada: os limiares (gate 0,30, \|Z\| 2/3, K = 20, M = 1000, c = 4) têm base teórica e foram escolhidos e medidos na mesma amostra | Valores por omissão fixados antes, na amostra cripto, e plano pré-registado: os 18,7 anos de ES são um teste fora da amostra dos parâmetros. Todas as células relatadas, com BH; metades, anos, MES e SPY (que têm o mesmo activo subjacente) | Mercados independentes do S&P 500; dados posteriores a Setembro de 2026 para confirmar qualquer hipótese gerada pelo estudo (por exemplo, a reversão depois das resoluções «continuação») |

Regras para qualquer estudo futuro: usar só barras fechadas; entrar no fecho da barra do sinal (pivots na
confirmação, ponto (g)); não usar a resolução nem a cor dos rótulos como informação de entrada; medir em unidades de
volatilidade; agrupar os erros por dia; relatar também os resultados nulos.

**O que mudou.** Nada no código do indicador. Foram acrescentados o estudo S&P 500 ([ESTUDO_SP500.md](ESTUDO_SP500.md))
e o seu código e resultados agregados ([research/sp500/](../research/sp500/README.md)), sem os dados de mercado. As
alterações ao indicador que o estudo sugere ficam por decidir: assinalar ou suprimir as absorções e os «travados» cuja
janela inclui o minuto de liquidação das 14:59 CT, expirar as absorções pendentes no fim da sessão (ou marcar as
resoluções causadas pelo salto da reabertura) e calibrar o Z separadamente por horário. O indicador continua a ser um
medidor descritivo da relação entre o preço e o fluxo, não um sistema de negociação ([METODOLOGIA.md](METODOLOGIA.md),
secção 9): no S&P 500, com o delta «Auto», os seus sinais não têm valor direccional demonstrável.
