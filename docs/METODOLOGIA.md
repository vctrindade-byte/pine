# Metodologia

Este documento descreve, com as fórmulas exactas, o que o indicador «Preço × CVD Normalizado [Order Flow]» calcula e
porquê. Segue o código de `src/price_cvd_normalizer.src.pine`. Onde a implementação se afasta do dossier de
investigação original ([research-dossier.md](research-dossier.md)), prevalece este documento; as diferenças estão
resumidas na [secção 10](#10-diferenças-em-relação-ao-dossier).

**Oráculo dos testes.** As fórmulas e regras deste documento são a referência contra a qual o código é verificado.
Há duas reimplementações independentes: uma em JavaScript (`tests/lib/refz.mjs`), usada pelo harness de testes (ver
[tests/README.md](../tests/README.md)), e outra em Python (guarda de gaps, escalas, D, RMS desfasado e gate), usada na
validação com dados reais e mantida fora do repositório (ver [VALIDACAO.md](VALIDACAO.md), secção 3).

**Estado das fontes.** As marcas usadas ao longo do texto vêm do dossier:

| Marca | Significado |
|---|---|
| **[V]** | Verificado: lemos o texto integral ou o resumo da fonte primária. |
| **[V-sec]** | Visto apenas num resumo secundário, num espelho ou numa citação de terceiros. |
| **[M]** | De memória, não verificado. Os seus números não são citados. |
| **[E]** | Resultado empírico ou de simulação próprio. Não revisto por pares. |

Números de fontes [V-sec] ou [M] não são apresentados como factos. Os resultados [E] vêm de scripts de investigação
não incluídos neste repositório, sobretudo dados de um par cripto à vista (BTCFDUSD, 117 dias) com o lado agressor de
cada negócio, e de simulações.

## Índice

1. [Notação](#1-notação)
2. [Estimação do delta](#2-estimação-do-delta)
3. [Incrementos e escalas](#3-incrementos-e-escalas)
4. [Construção do CVD e âncoras](#4-construção-do-cvd-e-âncoras)
5. [Modos de normalização](#5-modos-de-normalização)
6. [Estatística de divergência Z](#6-estatística-de-divergência-z)
7. [Eventos de janela curta e máquina de estados](#7-eventos-de-janela-curta-e-máquina-de-estados)
8. [Divergência por pivots](#8-divergência-por-pivots)
9. [Interpretação honesta](#9-interpretação-honesta)
10. [Diferenças em relação ao dossier](#10-diferenças-em-relação-ao-dossier)

[Bibliografia anotada](#bibliografia-anotada)

---

## 1. Notação

- *t* indexa as barras do gráfico; *C*, *O*, *H*, *L*, *V* são fecho, abertura, máximo, mínimo e volume.
- *j* indexa os intrabars (barras do timeframe inferior) dentro de uma barra do gráfico.
- Valores por omissão: N = 100 (janela de σ e ρ), K = 20 (horizonte da divergência), M = 1000 (janela de calibração),
  c = 4 (winsorização), limiares |Z| de 2 e 3, ρ mínimo 0,30.
- σ é sempre o desvio-padrão **populacional** (o `ta.stdev` do Pine por omissão). As funções `ta.stdev`,
  `ta.correlation`, `ta.sma` e `math.sum` ignoram valores *na* e usam os últimos valores válidos [V, manual do Pine].
- O índice *t*−1 indica um valor **desfasado uma barra**: a barra actual nunca entra na sua própria escala.
- Retornos em pontos base (bps, ×10⁴), para evitar problemas de precisão com valores muito pequenos.
- clip(x, ±c) = max(−c, min(c, x)).

---

## 2. Estimação do delta

O delta de uma barra é o volume comprador agressor menos o volume vendedor agressor. A TradingView não expõe as marcas
de agressor da bolsa: o delta tem de ser estimado. A qualidade dessa estimativa domina tudo o resto.

### 2.1 Escada de fontes

| Nível | Fonte | Acesso em Pine | Plano e cobertura |
|---|---|---|---|
| **Alta (3)** | Footprint: delta = `footprint.delta()`; volume da barra para o NAR = `footprint.total_volume()` | `request.footprint()`, um único local de chamada | Premium/Ultimate [V]. Profundidade histórica não documentada. Classificado pela TradingView «com base na acção do preço intrabar» [V-sec], não pelas marcas de agressor |
| **Alta (3)** | Intrabars «1T» com a regra das cotações e a regra da vela | `request.security_lower_tf(…, "1T", …)` | Ultimate [V-sec]. Limite de 100K/125K/200K intrabars, isto é, negócios: horas em futuros líquidos. Presença histórica de bid/ask **não verificada** |
| **Alta (3)** | Intrabars «1S» com a regra da vela | idem, «1S» | Premium ou superior [V-sec]. Cerca de 28 h de cripto líquida com 100K [E] |
| **Média (2)** | Intrabars de minutos (ou de segundos > 1, ou ticks > 1) com a regra da vela; qualquer intrabar com o classificador BVC | idem | Todos os planos. 100K minutos ≈ 69 dias 24/7 |
| **Baixa (1)** | BVC-Normal na barra do gráfico; intrabars não inferiores ao gráfico; símbolos com volume de ticks | nenhum | Sempre disponível. **Derivado do preço**: sem Z nem eventos |
| **Sem dados (0)** | Barra sem intrabars com a opção «Barras sem intrabars» = Nenhum | — | — |

Os limites de intrabars (100K nos planos Basic a Premium, 125K no Expert, 200K no Ultimate) aplicam-se a
`request.security` e a `request.security_lower_tf` em timeframes inferiores [V, manual do Pine, «Limitations»]. As
barras mais antigas do que esse limite ficam sem intrabars e caem na regra de recurso (secção 2.5).

### 2.2 Regra da vela (paridade com a TradingView)

É a regra do CVD da própria TradingView (biblioteca `ta` v12 [V, código-fonte]). Para cada intrabar *j*, com o lado
**transportado entre barras do gráfico** (nunca reinicia; começa em +1):

$$
s_j=\begin{cases}
+1 & C_j>O_j\\
-1 & C_j<O_j\\
+1 & C_j=O_j,\ C_j>C_{j-1}\\
-1 & C_j=O_j,\ C_j<C_{j-1}\\
s_{j-1} & \text{caso contrário}
\end{cases}
\qquad
\hat\Delta_t=\sum_{j\in t}s_j\,V_j
$$

É o BVC no limite σ → 0 (uma função de distribuição em degrau). Em dados reais foi o melhor estimador baseado em
barras, ou empatado, com intrabars de 1 segundo em 4 de 5 conjuntos de dados, e coincide com o CVD da TradingView [E].

### 2.3 Regra das cotações em «1T»

Quando há cotações válidas no contexto intrabar (bid e ask não *na* e ask > bid; só acontece em «1T» [V, manual do
Pine]), a regra das cotações tem prioridade, como na biblioteca `ta` v12:

$$
q_j=\begin{cases}
+1 & p_j\ge \text{ask}_j\\
-1 & p_j\le \text{bid}_j\\
\operatorname{sign}(p_j-m_j) & \text{caso contrário},\ m_j=(\text{bid}_j+\text{ask}_j)/2
\end{cases}
$$

Se q_j = 0 (negócio exactamente no ponto médio) aplica-se a regra da vela, e depois o lado transportado. É uma regra
do tipo EMO (Ellis-Michaely-O'Hara [V]) com recurso ao ponto médio, como na regra de Lee e Ready [V]. Não se sabe se a
TradingView fornece bid/ask nos intrabars «1T» históricos; sem cotações, a regra reduz-se à regra da vela, que em «1T»
é a regra do tick.

### 2.4 BVC-Normal por intrabar (opção)

*Bulk volume classification* de Easley, López de Prado e O'Hara (2012, eq. 7 [V]), adaptada a intrabars de tempo com
um σ móvel causal:

$$
\hat\Delta_t=\sum_{j\in t}V_j\big(2\Phi(z_j)-1\big),\qquad
z_j=\operatorname{clip}\!\Big(\frac{\Delta C_j}{\sigma_j},\pm10\Big)
$$

- ΔC_j = C_j − O_j no primeiro intrabar da sessão (guarda de gap), C_j − C_{j−1} nos restantes.
- σ_j = desvio-padrão dos últimos 100 ΔC no contexto intrabar (incluindo o actual); z_j = 0 se σ_j não for positivo.
- Φ é a distribuição Normal. A versão Student-t não é oferecida: só encolhe a escala.
- É uma **adaptação**: a especificação original usa *buckets* de volume (ADV/50) e não indica a janela de σ. Não deve
  ser chamada «a especificação ELO».

Com o BVC, a qualidade fica no máximo média: em dados reais, o BVC com intrabars de 1 segundo ficou ao nível da regra
da vela com intrabars de 1 minuto (correlação com o delta verdadeiro 0,77 contra 0,74 em BTCFDUSD, 5 min) [E].

**Φ sem função erf.** O Pine não tem `erf`, `tanh` nem `atanh` [V, índice da referência]. Φ é calculada pela
aproximação 7.1.26 de Abramowitz e Stegun [V]:

$$
x=\frac{\lvert z\rvert}{\sqrt2},\quad \tau=\frac{1}{1+0{,}3275911\,x},\quad
\operatorname{erf}(x)\approx 1-\big(a_1\tau+a_2\tau^2+a_3\tau^3+a_4\tau^4+a_5\tau^5\big)e^{-x^2},
\quad \Phi(z)=\tfrac12\big(1+\operatorname{sign}(z)\operatorname{erf}(x)\big)
$$

com a₁ = 0,254829592, a₂ = −0,284496736, a₃ = 1,421413741, a₄ = −1,453152027 e a₅ = 1,061405429. O erro máximo
medido em Φ é 6,97 × 10⁻⁸ [E]. As funções auxiliares são tanh(y) = (e^{2y} − 1)/(e^{2y} + 1), com y limitado a ±20,
e atanh(x) = ½·ln((1 + x)/(1 − x)), com x limitado a ±0,999 (erro máximo medido ≤ 4,4 × 10⁻¹⁶ [E]).

### 2.5 BVC-Normal na barra do gráfico (recurso)

Para barras sem intrabars (para lá do limite do plano, falhas do fornecedor, timeframe inferior inválido) ou com a
fonte «Só barras do gráfico»:

$$
\hat\Delta_t=V_t\big(2\Phi(z_t)-1\big),\qquad z_t=\operatorname{clip}\!\Big(\frac{r_t}{\sigma_{r,t-1}},\pm10\Big)
$$

em que r_t é o retorno da barra com a guarda de gaps da secção 3.1 e σ_{r,t−1} o desvio-padrão de r nas 100 barras
anteriores (z_t = 0 se σ não for válido). Foi o melhor estimador só com barras do gráfico em dados reais
(correlação 0,47–0,83 com o delta verdadeiro), mas é **derivado do preço**: a qualidade é baixa e não há Z nem eventos
nessas barras. Não se usam o CLV, V·(2C − H − L)/(H − L), que foi o pior estimador em dados reais (correlações parciais
negativas em 2 de 5 conjuntos), nem a regra do sinal da barra inteira (sinal certo em só ~55% das barras de absorção)
[E].

### 2.6 Selecção da fonte e qualidade por barra

O nível de qualidade **configurado** depende do timeframe dos intrabars (ltf), do do gráfico e do classificador
(seg(·) = duração de um timeframe em segundos, `timeframe.in_seconds()`):

$$
\text{cfg}=\min\Big(h,\ \begin{cases}
1 & \text{ltf não é de ticks e } \text{seg}(\text{ltf})\ge\text{seg}(\text{gráfico})\\
3 & \text{ltf} \in \{\text{1T},\ \text{1S}\}\ \text{e regra da vela}\\
2 & \text{caso contrário}
\end{cases}\Big),\qquad
h=\begin{cases}1 & \text{volume de ticks}\\ 3 & \text{caso contrário}\end{cases}
$$

«Volume de ticks» significa `syminfo.volumetype == "tick"` ou `syminfo.type == "forex"`: o volume conta negócios ou
actualizações de cotação, sem lado agressor, e o delta é derivado do preço (decisão D8 do dossier). O `syminfo.type`
não tem valor para CFD e o `syminfo.volumetype` só vem declarado em alguns símbolos: um CFD (ou outro símbolo) com
volume de ticks não declarado não é detectado e recebe a qualidade da fonte; as dicas pedem para confirmar o «Tipo de
volume» na tabela. Em cada barra:

1. Fonte «Só barras do gráfico» → BVC na barra, qualidade 1.
2. Footprint seleccionado e com dados nesta barra → delta do footprint, qualidade *h*.
3. Intrabars disponíveis (fonte intrabar, ou footprint com o preenchimento ligado) → delta intrabar, qualidade cfg.
4. Caso contrário, «Barras sem intrabars» = BVC → BVC na barra, qualidade 1; = Nenhum → delta *na*, qualidade 0.
5. Barra com volume zero → delta 0 e a qualidade da barra anterior (não parte as séries).

Um contador hqRun guarda o número de barras **seguidas** com qualidade ≥ 2. As estatísticas exigem que as suas
janelas caibam inteiras nesse regime (secção 6.4).

A precisão Auto replica a regra da TradingView para o seu CVD [V-sec, Centro de Ajuda]: «1S» em gráficos de
segundos, «1» (1 minuto) em intradiário, «5» no diário e «60» no semanal ou superior. Num gráfico de 1 minuto ou de
1 segundo, os intrabars Auto são iguais ao gráfico e a qualidade é baixa.

### 2.7 Evidência empírica sobre os estimadores [E]

Correlação da estimativa com o delta verdadeiro por barra, barras de 5 minutos:

| Estimador | BTCFDUSD (117 d) | BTC à vista (1 d) | BTC perpétuo (dia de queda) | ETH perpétuo (dia de queda) | LOBSTER (1 d) |
|---|---|---|---|---|---|
| 1T, regra do tick | 0,85 | 0,96 | 1,00 | 0,99 | 0,79 |
| **1S, regra da vela** | **0,90** | 0,83 | 0,90 | 0,90 | 0,71 |
| 1S, BVC-Normal | 0,77 | 0,52 | 0,91 | 0,82 | 0,70 |
| **1 min, regra da vela** | **0,74** | 0,65 | 0,77 | 0,90 | 0,54 |
| 1 min, BVC-Normal | 0,73 | 0,46 | 0,79 | 0,89 | 0,62 |
| Barra do gráfico, BVC-Normal | 0,52 | 0,47 | 0,83 | 0,69 | 0,61 |
| Barra do gráfico, CLV | 0,42 | 0,24 | 0,49 | 0,51 | 0,60 |

Nos dados FDUSD os intervalos de confiança a 95% por *bootstrap* em blocos de dias são de cerca de ±0,03–0,06; os
conjuntos de um só dia têm erro de amostragem de ±0,05–0,10.

**O que importa para a divergência** é a parte do delta que o preço não explica. A correlação **parcial** da estimativa
com o delta verdadeiro, dado ΔP, foi 0,80–0,88 com 1S (cripto), 0,29–0,87 com 1 minuto e tipicamente 0,1–0,4 com as
barras do gráfico. As estimativas também inflacionam a correlação com ΔP: 1S ligeiramente (0,44 contra 0,39 no FDUSD),
1 minuto moderadamente, as barras do gráfico fortemente. Ao longo de um dia UTC, o CVD de barras do gráfico seguiu o CVD
verdadeiro (correlação de caminho 0,45–0,63) **não melhor do que o próprio preço** (0,59).

**Porque a regra da vela bate o BVC a 1 segundo.** Dentro de cada segundo o volume é muito unilateral (95% no par
pouco líquido, 57% no dia de queda): uma regra de sinal perde pouca informação, enquanto o BVC, com F(0) = ½, descarta
todos os segundos sem variação de preço.

---

## 3. Incrementos e escalas

### 3.1 Retorno da barra com guarda de gaps

$$
r_t=\begin{cases}
10^4\ln(C_t/O_t) & \text{1.ª barra, 1.ª barra da sessão, ou }\big\lvert10^4\ln(O_t/C_{t-1})\big\rvert>3\,\sigma^{\text{bruto}}_{t-1}\\
10^4\ln(C_t/C_{t-1}) & \text{caso contrário}
\end{cases}
$$

com σ^bruto_{t−1} o desvio-padrão de 10⁴·ln(C/C₋₁) nas 100 barras anteriores. Nas barras de gap (abertura da sessão,
saltos de abertura), o retorno mede só o movimento dentro da barra, que é o período em que o delta da barra foi
gerado: um gap nocturno sem negócios não é atribuído ao fluxo. Usa-se ln(fecho), não hlc3, para alinhar o retorno com o
delta da barra (decisão D13).

### 3.2 Incremento do fluxo e alinhamento

$$
d_t=\begin{cases}\hat\Delta_t-\overline{\hat\Delta}_{N,t-1} & \text{com «Remover deriva do fluxo»}\\ \hat\Delta_t & \text{caso contrário}\end{cases}
$$

em que a média móvel de N barras é desfasada uma barra. As pernas são **alinhadas**: r_t passa a *na* sempre que d_t
é *na*, e vice-versa, para que σ, ρ e as somas usem exactamente as mesmas barras.

### 3.3 Escalas

$$
\sigma_{r,t}=\operatorname{sd}_N(r),\qquad \sigma_{\Delta,t}=\operatorname{sd}_N(d),\qquad \hat\rho_t=\operatorname{corr}_N(r,d)
$$

e usa-se sempre σ_{r,t−1}, σ_{Δ,t−1} e ρ̂_{t−1}. As escalas são estimadas sobre **incrementos**, nunca sobre níveis,
porque os incrementos são aproximadamente estacionários e os níveis não (secção 5.9).

---

## 4. Construção do CVD e âncoras

### 4.1 Três objectos

- **Incrementos** d_t: a única coisa que as estatísticas usam (σ_Δ, ρ, Z, eventos). Não têm reinícios.
- **CVD ancorado**: CVD_t^(a) = Σ_{i=a}^{t} d_i, reiniciado em cada âncora *a*. Serve as linhas.
- **CVD contínuo**: CVD_t^c = Σ d_i desde a primeira barra com delta válido. Serve apenas os modos invariantes a
  translações (janela móvel, z-score de níveis, mín–máx) e a divergência por pivots. Nunca é mostrado em bruto.

O **rácio de agressão líquida** desde a âncora é NAR = Σ Δ̂ / Σ V ∈ [−1, 1], com o delta bruto (sem a remoção da
deriva) e o volume das barras com delta. Um segundo NAR, sobre todo o histórico de qualidade ≥ média, alimenta o aviso
«desequilíbrio persistente»: |NAR| ≥ 3% com pelo menos max(M, 5 dias de barras) barras de qualidade ≥ média e a remoção
da deriva desligada. O NAR desde a âncora não serve para isso: de dia para dia varia cerca de 2 vezes mais do que o
desequilíbrio persistente [E].

### 4.2 Regras de âncora

| Opção | Reinício | Notas |
|---|---|---|
| **Auto** (por omissão) | gráfico ≤ 60 min → «1D»; 60 min < gráfico < 1D → «1W»; 1D ≤ gráfico < 1W → «1M»; ≥ 1W → «12M», via `timeframe.change()` | «1D» é o dia de negociação da bolsa: no CME é o dia **Globex**, não a sessão regular [V-sec]; em cripto é o dia UTC |
| Sessão regular (RTH) | `session.isfirstbar_regular` [V] | Só intradiário. No CME pode coincidir com o dia Globex e em cripto/FX com a diária: nesses casos, use a sessão personalizada |
| Sessão personalizada | 1.ª barra dentro da sessão (por omissão 0830-1515, hora da bolsa); ou a barra que contém a hora de início; ou a 1.ª barra do dia, só em sessões que não atravessam a meia-noite | Aceita sessões como 1700-1600 sem reiniciar à meia-noite |
| Diária, semanal, mensal | `timeframe.change(tf)` | Só válida se `timeframe.in_seconds(tf)` for maior do que o gráfico; senão usa-se a Auto e a tabela avisa |

Uma âncora nova também nasce na primeira barra em que as pernas podem ser inicializadas (primeiro delta válido).

### 4.3 Escalas congeladas na âncora

Na barra da âncora *a*:

$$
\ln O_a,\quad \mathrm{CVD}^{(a)}\leftarrow0,\quad \sigma_{r,a}=\sigma_{r,a-1},\quad \sigma_{\Delta,a}=\sigma_{\Delta,a-1},\quad \rho_a=\hat\rho_{a-1}
$$

isto é, as escalas das N barras **anteriores** à âncora. Ficam fixas durante todo o período. Se ainda não existirem
(aquecimento), o indicador tenta de novo em cada barra até haver escalas. Congelar evita que as linhas se reajustem,
dentro da sessão, à própria divergência que pretendem mostrar (sem auto-ajuste); reestimar a cada âncora acompanha a
variação do impacto com a profundidade, a hora do dia e as notícias (Cont-Kukanov-Stoikov [V]; Dufour-Engle [V-sec];
Takahashi [V]).

### 4.4 Costura da cobertura

As barras mais antigas do que o limite de intrabars usam o BVC na barra: outra escala de delta e um ρ inflacionado (o
delta é derivado do preço). Se as escalas congeladas na âncora actual vierem de uma janela que inclui barras de
qualidade baixa, as linhas **reiniciam uma vez** na primeira barra cuja janela σ/ρ (as N barras anteriores) está toda
em qualidade ≥ média. A tabela indica-o («reiniciada no início da cobertura»). O reinício acontece no máximo uma vez
por entrada em dados finos e só se a escala congelada tiver sido estimada numa janela mista. Em dados reais, com a
cobertura de 1S de 100K intrabars (110 barras de 15 minutos, 330 de 5 minutos), a âncora diária activa na última barra
tinha as escalas estimadas numa janela com barras sem intrabars em 88% dos casos em 15 minutos e em 20% em 5 minutos;
o indicador reiniciou as linhas exactamente nesses casos ([VALIDACAO.md](VALIDACAO.md), secção 3.6) [E].

### 4.5 Porque as estatísticas não ancoram

Uma janela de 100 barras atravessaria um reinício (uma sessão RTH em barras de 5 minutos tem 78 barras) e criaria
picos artificiais de σ. Sobre incrementos isso é impossível. Só as **linhas** reiniciam; σ, ρ, Z e os eventos usam
séries contínuas.

### 4.6 Fontes de deriva do CVD

| Fonte de deriva | Contramedida |
|---|---|
| Viés de classificação (por exemplo, o lado transportado em intrabars sem variação) | Linhas ancoradas; estatísticas sobre incrementos normalizados |
| Desequilíbrio estrutural de agressores (perpétuos, descontos de *maker*) | «Remover deriva do fluxo»: d = Δ − média_N(Δ)_{t−1}. Desligado por omissão; sugerido em perpétuos de cripto e quando a tabela avisa. Em testes ajudou a calibração quando o preço só reage às inovações do fluxo e piorou a detecção quando o fluxo persistente move o preço [E] |
| Fluxo de memória longa e previsível que não move o preço (metaordens divididas; Hasbrouck: inovações [V]) | O mesmo interruptor; a recalibração empírica (RMS) absorve a variância superdifusiva |
| Mudança de estimador na fronteira da cobertura | Qualidade por barra, marca no fundo, reinício das janelas estatísticas e costura da secção 4.4 |
| Gaps nocturnos sem delta (dados só da sessão) | Guarda de gaps da secção 3.1 |

Nos dados reais da validação, sem a remoção da deriva o Z médio foi −0,24 na primeira janela e os alertas «Z ≤ −limiar»
foram 43 contra 17 «Z ≥ +limiar»; com a remoção, Z médio −0,01 e 31 contra 28 (ver [VALIDACAO.md](VALIDACAO.md)) [E].

---

## 5. Modos de normalização

### 5.1 Princípios

1. A mesma família de transformação e a mesma janela de estimação para as duas pernas.
2. Todas as escalas são estimadas sobre incrementos, de forma causal (desfasadas ou congeladas na âncora).
3. Invariância a translações: a origem arbitrária do CVD desaparece.
4. Os níveis nunca são regredidos nem correlacionados para produzir um sinal.
5. Os modos de visualização são contexto. Os sinais vêm sempre do Z e dos eventos (secções 6 e 7).

### 5.2 Mapeamento de Kyle e λσ

No modelo de Kyle (1985) [V] a variação do preço é linear no fluxo líquido, Δp = λ·y, e a profundidade é 1/λ. No
modelo estático o preço é uma função linear exacta do fluxo, portanto

$$
\operatorname{Var}(\Delta p)=\lambda^2\operatorname{Var}(y)\quad\Longrightarrow\quad\lambda=\frac{\sigma(\Delta p)}{\sigma(y)}.
$$

Na prática as duas pernas têm ruído: o preço incorpora informação pública e a descoberta de preço feita por ordens
limite, que o CVD não vê (Brogaard et al. [V]; Eisler et al. [V]); o CVD tem erro de classificação (secção 2.7). Com
erro nas duas variáveis, o declive simétrico (*reduced major axis*) sign(ρ)·σ_r/σ_Δ é o mapeamento adequado. O declive
OLS, ρ·σ_r/σ_Δ, atenua a perna do fluxo pelo factor ρ (tipicamente 0,4–0,6 [E]) e faria qualquer episódio liderado
pelo fluxo parecer «sem fluxo».

Dividir cada perna pelo seu σ dá o mesmo mapeamento sem unidades: o preço implícito pelo fluxo com λσ, expresso em
unidades de σ_r, é λσ·CVD/σ_r = CVD/σ_Δ. Unidades-σ tornam também comparáveis instrumentos e regimes (como o
reescalamento de Patzelt e Bouchaud [V] e o σ *ex ante* de Moskowitz, Ooi e Pedersen [M]).

### 5.3 M1 — Unidades-σ ancoradas (por omissão)

$$
\tilde P_t=\frac{10^4\,(\ln C_t-\ln O_a)}{\sigma_{r,a}},\qquad
\tilde F_t=\frac{\mathrm{CVD}^{(a)}_t}{\sigma_{\Delta,a}},\qquad t\ge a
$$

- As duas linhas começam perto de 0. Na barra da âncora ficam *na* (a linha interrompe-se), para não desenhar uma
  ligação vertical enganadora.
- Unidades: «quantos movimentos típicos de uma barra o preço e o fluxo percorreram desde a âncora».
- Dentro de um período cada linha é uma transformação afim de ln P e do CVD: a linha do preço tem exactamente a forma
  do gráfico em escala logarítmica.
- A distância S_t = P̃_t − F̃_t ≈ Σ_{i=a}^{t}(r_i/σ_{r,a} − d_i/σ_{Δ,a}) é o resíduo simétrico acumulado desde a
  âncora, sem winsorização. É contexto. Com ρ < 1 e fluxo de memória longa, a linha do CVD afasta-se naturalmente mais
  do que a do preço.

### 5.4 M2 — Preço implícito pelo fluxo

$$
\hat P_t=O_a\cdot\exp\!\Big(\frac{\lambda_a\,\mathrm{CVD}^{(a)}_t}{10^4}\Big),\qquad
\lambda_a=\begin{cases}\sigma_{r,a}/\sigma_{\Delta,a} & \text{igualado à volatilidade (por omissão)}\\ \rho_a\,\sigma_{r,a}/\sigma_{\Delta,a} & \text{OLS («preço esperado dado o fluxo»)}\end{cases}
$$

O painel mostra C_t e P̂_t; opcionalmente P̂ é desenhado no gráfico principal. Com λσ, M2 é M1 reescalado para preço:
a geometria é idêntica. É o formato da figura 1 de Evans e Lyons (2002) [V-sec]. Em dias de fluxo persistente num só
sentido, P̂ pode afastar-se dezenas de por cento do preço (λ congelado na âncora). Nos dados reais da validação (λσ,
delta verdadeiro), |P̂/C − 1| em 5 minutos teve percentil 99 de 33% e máximo de 44% na janela de 31 dias que contém
esses dias, mas percentil 99 de 9% (máximo 12%) numa janela de 42 dias e de 9% (máximo 44%) em todo o histórico de 117
dias; em 15 minutos, 7% (máximo 14%) ([VALIDACAO.md](VALIDACAO.md), secção 3.6) [E].

### 5.5 M3 — Unidades-σ em janela móvel

$$
\tilde P_t=\frac{10^4(\ln C_t-\ln C_{t-W})}{\sigma_{r,t-1}},\qquad
\tilde F_t=\frac{\mathrm{CVD}^c_t-\mathrm{CVD}^c_{t-W}}{\sigma_{\Delta,t-1}}
$$

Oscilador sem âncora, útil em 4 h ou mais, ou em mercados 24/7. As linhas mudam de forma à medida que a janela
avança (somas móveis).

### 5.6 M4 — Z-score de níveis (só visual)

$$
z^P_t=\frac{\ln C_t-\overline{\ln C}_W}{\operatorname{sd}_W(\ln C)},\qquad
z^F_t=\frac{\mathrm{CVD}^c_t-\overline{\mathrm{CVD}^c}_W}{\operatorname{sd}_W(\mathrm{CVD}^c)}
$$

Propriedades que justificam o rótulo «só visual»:

- com o desvio-padrão populacional, |z| ≤ √(W − 1) (Shiffler, 1988 [V]);
- uma tendência linear satura em √(3(W − 1)/(W + 1)) ≈ 1,71;
- num passeio aleatório, P(|z| > 2) ≈ 12–15% [E];
- z^P − z^F de dois passeios independentes passa |2| em cerca de 33% das barras, com uma falsa meia-vida de W/4 [E].

Não geram sinais.

### 5.7 M5 — Mín–máx (só visual)

$$
s_t=100\cdot\Big(2\,\frac{x_t-\min_W x}{\max_W x-\min_W x}-1\Big)\in[-100,100]
$$

com x = fecho para o preço e x = CVD^c para o fluxo, e uma guarda quando o intervalo é zero. Limitado, mas satura em
tendência, é dominado por valores extremos (ponto de ruptura 1/W) e teve a menor capacidade de detecção nos testes
(AUC 0,54–0,55) [E].

### 5.8 Cone nulo iid

Sob a hipótese nula iid, com as pernas padronizadas e correlação ρ, cada termo d_i/σ_Δ − r_i/σ_r tem variância
2(1 − ρ), e a soma de n termos tem variância 2n(1 − ρ). O cone é

$$
\tilde P_t\pm2\sqrt{2n(1-\max(\rho_a,0))},\qquad n=t-a+1.
$$

É só uma referência. O fluxo tem memória longa (o rácio de variâncias VR20 de u_d foi 1,30 em BTC real [E]) e a
volatilidade intradiária varia. Em dados reais com âncora diária (117 dias), a linha do fluxo saiu do cone em 17% das
barras em 5 minutos e em 10% em 15 minutos, em vez de ~4,6%, e o desvio RMS foi 2,3 e 1,5 vezes o do cone (1,8–2,8 nas
duas janelas de 5 minutos da validação) [E]. O dossier previa um cone verdadeiro só 15–30% mais largo, a partir do
VR20; a medição directa substitui essa estimativa (secção 10; [VALIDACAO.md](VALIDACAO.md), secção 3.6).

### 5.9 Porque não regredir nem correlacionar níveis

Preço e CVD são séries integradas. A regressão de um passeio aleatório sobre outro, independente, dá relações
«significativas» espúrias (Granger e Newbold, 1974 [V]; Phillips, 1986 [V]). Para dois passeios aleatórios
independentes, o valor esperado do quadrado da correlação dos níveis é E[θ²] = 0,240522 (Ernst, Shepp e Wyner, 2017
[V]): uma correlação |r| > 0,5 ocorre em cerca de 40% das amostras. A cointegração dos níveis é específica de cada
regime (Killeen, Lyons e Moore: efeitos persistentes do fluxo antes da UEM e desacoplamento depois [V]). Em teoria, o
resíduo dos níveis é I(1), porque a informação pública e a descoberta de preço por ordens limite fazem parte do preço
mas não do CVD (Engle e Granger, 1987 [V], para o enquadramento). O M1 nunca regride níveis: ancora-os, o que limita a
acumulação do desvio I(1) e do erro de classificação a um período.

---

## 6. Estatística de divergência Z

### 6.1 Definição

$$
u_{r,t}=\operatorname{clip}\!\Big(\frac{r_t}{\sigma_{r,t-1}},\pm c\Big),\qquad
u_{d,t}=\operatorname{clip}\!\Big(\frac{d_t}{\sigma_{\Delta,t-1}},\pm c\Big),\qquad c=4
$$

Em cada barra, u_r e u_d são ambos definidos ou ambos *na*.

$$
D_t=\frac{\sum_{i=t-K+1}^{t}\big(u_{r,i}-u_{d,i}\big)}{\sqrt{2K\,\big(1-\min(\hat\rho_{t-1},\,0{,}95)\big)}},
\qquad
Z_t=\frac{D_t}{\mathrm{RMS}_{t-1}(D)}
$$

**Sinal.** Z > 0: a perna do preço está à frente da perna do fluxo (o preço subiu mais, ou caiu menos, do que o fluxo
implica). Z < 0: o fluxo está à frente do preço. Não é um sinal de alta nem de baixa.

### 6.2 Porque é simétrica

Para duas variáveis padronizadas com correlação ρ, Var(u_r − u_d) = 2(1 − ρ). (u_r − u_d)/√2 é a componente principal
menor do par padronizado, o resíduo ortogonal: pesa um choque de fluxo e um choque de preço de igual modo (1:1). Sob a
nula iid, a soma de K termos tem variância 2K(1 − ρ), daí o denominador de D. O resíduo OLS r − λΔ pesa o fluxo na
proporção ρ:1 e por isso falha os episódios liderados pelo fluxo; numa simulação de propagador, um Z construído assim
teve um *lift* de 0,3–0,8, pior do que o acaso [E]. O limite ρ ≤ 0,95 evita que o denominador colapse.

A winsorização das unidades-σ em ±4 é a guarda prática contra a concavidade do impacto: o impacto real cresce menos do
que linearmente com o fluxo (Weber e Rosenow: G = 0,48·Q^0,76 [V]; lei da raiz quadrada, Tóth et al. [V]), e u_d tem
caudas muito pesadas (curtose 100–220, E[u_d²] ≈ 2,4 [E]). A winsorização reduziu para metade a taxa nula de
P(|Z| > 3) (2,1% → 1,1%) e melhorou a detecção precoce (0,30 → 0,48 nas primeiras 20 barras de episódios injectados)
[E].

### 6.3 Calibração: RMS não centrado e desfasado

O denominador analítico √(2K(1 − ρ)) não chega: os sinais das ordens têm memória longa (função de autocorrelação
~τ^−0,6, Lillo e Farmer [V]), o CVD é superdifusivo e o escalamento em √K falha. Só com o denominador analítico a
taxa nula P(|Z| > 2) foi de 10–18% [E]. Por isso D é recalibrado empiricamente pelo seu **RMS não centrado** nos
valores **anteriores**:

$$
\mathrm{RMS}_{t-1}(D)=\begin{cases}
\sqrt{\tfrac1M\sum_{k=1}^{M}D_{(k)}^2} & n_{t}>M\\[4pt]
\sqrt{\tfrac1{n_t}\sum_{k=1}^{n_t}D_{(k)}^2} & N\le n_t\le M\\[4pt]
\text{na} & n_t<N
\end{cases}
$$

em que D_(1), D_(2), … são os valores válidos de D **antes** da barra *t*, do mais recente para o mais antigo, e n_t o
seu número. O valor actual nunca entra no próprio denominador.

**Porque não centrado.** Um z-score móvel centrado (subtrair a média móvel de D) apaga as divergências persistentes em
20–50 barras e cria 9–19% de alarmes de sinal errado depois dos episódios [E]. O RMS não centrado mantém visíveis as
divergências persistentes: com M = 1000, a taxa de detecção de um episódio injectado foi 0,44 / 0,67 / 0,57 / 0,39 nas
idades 0–20 / 20–100 / 100–200 / 200–400 barras [E].

**Calibração provisória.** Enquanto n_t ≤ M a calibração é uma média expansiva de poucos valores efectivos (a soma K é
sobreposta, com autocorrelação de ordem 1 de (K − 1)/K = 0,95): a tabela mostra «cal. n/M». Com menos de 20·K valores
(cerca de 20 somas K independentes) o preenchimento e as colunas ficam limitados à intensidade abaixo do limiar. Os
**alertas** de Z só disparam com pelo menos 2N valores de calibração (o aquecimento de 2N do dossier): em dados reais,
com 100 a 199 valores de calibração (o caso de 1S num gráfico de 5 minutos), P(|Z| ≥ 2) foi cerca de 1,3 vezes e P(|Z|
≥ 3) 1,2–1,6 vezes o das mesmas barras com a calibração completa; o excesso desce para ~1,1 vezes com 200 a 399
valores e para ~1,05 (|Z| ≥ 2) e ≤ 1,1 (|Z| ≥ 3) com 400 ou mais ([VALIDACAO.md](VALIDACAO.md), secção 3.6) [E].

### 6.4 Condição sobre os dados

D só é calculado quando todas as janelas que o alimentam estão em dados de qualidade ≥ média:

$$
\text{hqOk}_t=\big[\text{qualidade}_t\ge2\big]\wedge\big[\text{hqRun}_t\ge N+\max(K,k_e)+N\cdot\mathbb 1_{\text{deriva}}\big]
$$

O termo mais antigo da soma K usa o σ das barras [t − K + 1 − N, t − K]; com a remoção da deriva, a média de N barras
recua mais N barras. O mesmo vale para as somas curtas dos eventos (janela k_e). Com os valores por omissão em 5
minutos (k_e = 3), são precisas 120 barras seguidas de qualidade ≥ média e depois N = 100 valores de D: o Z aparece
ao fim de cerca de 220 barras.

### 6.5 Gate de validade ρ

$$
\text{gate}_t=\text{hqOk}_t\ \wedge\ \hat\rho_{t-1}\ \ge\ \max\big(\rho_{\min},\ \tanh(1{,}96/\sqrt{N-3})\big)
$$

- Com N = 100, tanh(1,96/√97) = 0,196 e o limite efectivo é 0,30; com N = 30 é 0,360.
- O segundo termo é o limite de significância a 95% pela transformação de Fisher, atanh(ρ̂)·√(N − 3) ≈ N(0, 1)
  [V-sec]. O intervalo de confiança mostrado na tabela é tanh(atanh(ρ̂) ± 1,96/√(N − 3)).
- Em BTC real de 5 e 15 minutos com o delta verdadeiro, o gate esteve aberto em 83–84% das barras, com uma taxa de
  passagem nula empírica de 0,25–0,5% [E]; na validação do código final, nas janelas usadas, esteve aberto em 80–90%
  das barras [E]. Só o limite de Fisher (0,196) ficaria aberto em 92–97% das barras, com 2,8–3,6% de passagem nula,
  por causa das caudas pesadas [E]. R² ≥ 0,10 é praticamente o mesmo que ρ ≥ 0,30.
- Com delta **estimado** de intrabars de 1 minuto, o ρ mediano fica inflacionado (0,57 contra 0,49) e o gate abre em
  ~92% das barras [E]: por isso o gate exige também qualidade ≥ média.
- Um ρ̂ negativo fecha o gate e é assinalado como possível problema de dados ou de classificação.
- Com o gate fechado o Z fica cinzento, não escondido.

Referências de contexto: em câmbio, com dados diários, o fluxo explica uma fracção grande das variações (R² acima de
60% em Evans e Lyons [V]); o R² intradiário com o CVD, que só vê negócios agressores, é naturalmente mais baixo. Os
limiares devem ser verificados por instrumento.

### 6.6 Pernas e os quatro estados neutros

$$
P_K=\frac{\sum_K u_r}{\sqrt K},\qquad F_K=\frac{\sum_K u_d}{\sqrt K},\qquad
\sum_K(u_r-u_d)=\sqrt K\,(P_K-F_K)
$$

Como o denominador de D e o RMS são positivos, sign(Z) = sign(P_K − F_K). O par (sinal de Z, perna maior em valor
absoluto) determina o sinal da perna dominante:

- Z < 0 e |F_K| > |P_K| ⟹ F_K > 0. (Se F_K ≤ 0, então P_K < F_K ≤ 0 e |P_K| > |F_K|, contradição.)
- Z < 0 e |P_K| ≥ |F_K| ⟹ P_K < 0. (Se P_K ≥ 0, então F_K > P_K ≥ 0 e |F_K| > |P_K|, contradição.)
- Z > 0: casos espelho, F_K < 0 ou P_K > 0.

| Condição (gate aberto, \|Z\| ≥ limiar) | Sinais implicados | Estado | Leituras possíveis (ambas plausíveis) |
|---|---|---|---|
| Z ≤ −limiar, \|F\| > \|P\| | F > 0 | Fluxo comprador sem subida proporcional do preço | Absorção das compras por vendedores passivos: reversão se estes forem informados, ou combustível para uma quebra (o preço apanha o fluxo) |
| Z ≤ −limiar, \|P\| ≥ \|F\| | P < 0 | Preço a cair sem fluxo vendedor proporcional | Descida não confirmada: retirada de ofertas de compra ou notícia (pode ser permanente) |
| Z ≥ +limiar, \|F\| > \|P\| | F < 0 | Fluxo vendedor sem queda proporcional do preço | Absorção das vendas (espelho) |
| Z ≥ +limiar, \|P\| ≥ \|F\| | P > 0 | Preço a subir sem fluxo comprador proporcional | Subida não confirmada: recompra de vendas a descoberto com ordens limite, retirada de ofertas de venda ou notícia |

Não há quinto estado além dos empates (que caem no ramo do preço). Em dados reais, a coerência entre o sinal de Z e o
sinal implicado da perna dominante foi de 100% nas 1828 barras com |Z| ≥ 2 das três corridas sem remoção da deriva da
secção 3.4 de [VALIDACAO.md](VALIDACAO.md) [E].

### 6.7 Alertas de Z

- Disparam no **primeiro cruzamento** de ±limiar numa barra fechada, com o gate aberto.
- **Histerese**: depois de disparar, o lado só volta a armar quando o Z regressa a menos de limiar − 1 (por omissão 1)
  desse lado. A soma K sobreposta oscila em torno do limiar e o gate pisca perto de ρ mínimo; sem histerese, o mesmo
  episódio repetia o alerta poucas barras depois.
- Exigem pelo menos 2N valores de calibração. Um cruzamento antes disso desarma na mesma: o alerta não sai atrasado, a
  meio do episódio.

### 6.8 Evidência de calibração [E]

Candidatos comparados em BTCFDUSD real (delta verdadeiro) e numa simulação de propagador:

| Candidato | P(\|Z\| > 2) nulo: 5 min / 15 min / simulação | Divergências persistentes | Sensibilidade a episódios liderados pelo fluxo |
|---|---|---|---|
| Soma K simétrica, RMS não centrado (M = 500) | 6,3% / 6,7% / 5,4% | Detecção 0,41–0,56 até à barra 100; ≤ 1,5% de sinal errado | Melhor: AUC com sinal 0,63–0,69 na simulação, *lift* 2–2,7 (precisão ≤ 8%) |
| **Idem + winsorização ±4 + RMS(M = 1000) (escolhido)** | **5,6–5,9%** (P(\|Z\| > 3) ≈ 1,1%) | 0,44 / 0,67 / 0,57 / 0,39 nas idades 0–20 / 20–100 / 100–200 / 200–400 | idem |
| Só o denominador analítico √(2K(1 − ρ)) | 12,4% / 10,1% / 10,9% | — | — |
| Resíduo OLS dos incrementos, z centrado (100) | 8,4% / 8,2% / 8,7% | Apagadas em 20–50 barras; 9–19% de alarmes de sinal errado | Peso ρ:1; *lift* 0,3–0,8 |
| z^P − z^F de níveis | 32,5% / 33,1% / 34,3% | Falsa meia-vida W/4 | — |
| Resíduo ancorado / (σ_e√n) | 13,0% / 7,2% / 17,8% | Depende do número de barras por sessão | — |

Na validação do código final em dados reais (secção 3 de [VALIDACAO.md](VALIDACAO.md)), com o delta verdadeiro e
calibração completa, P(|Z| ≥ 2) foi 6,19% e 6,05% em duas janelas de 5 minutos e 5,35% em 15 minutos; P(|Z| ≥ 3) foi
1,61%, 1,04% e 1,48% [E]. O dossier refere que, combinado com o gate, um |Z| ≥ 2 nulo cai para cerca de 0,04% das
barras: essa nula é uma série em que o preço e o fluxo não estão relacionados (ρ ≈ 0), e aí o gate fica fechado em
quase todas as barras (passagem nula de 0,25–0,5%, secção 6.5). Esse número mede a protecção do gate quando não há
relação preço-fluxo, não a frequência de |Z| ≥ 2 em dados reais: com o gate aberto, a taxa base continua a ser cerca
de 6% (P(|Z| ≥ 2 | gate aberto) = 6,27% e 6,45% nas duas janelas de 5 minutos, [VALIDACAO.md](VALIDACAO.md), secção
3.3) [E].

### 6.9 λ e eficiência de impacto η (contexto, não gatilho)

$$
\lambda^{\text{OLS}}_{t-1}=\hat\rho_{t-1}\frac{\sigma_{r,t-1}}{\sigma_{\Delta,t-1}},\qquad
\lambda^{\sigma}_{t-1}=\frac{\sigma_{r,t-1}}{\sigma_{\Delta,t-1}}\qquad\text{(bps por unidade de delta)}
$$

A tabela mostra-os por 1, 10³, 10⁶, … unidades de volume, escolhendo a escala que deixa λσ ≥ 0,1. Na janela do
evento k_e:

$$
\eta_t=\frac{\sum_{k_e} r}{\lambda^{\text{OLS}}_{t-1}\sum_{k_e} d}\qquad\text{só quando }\lvert F_e\rvert\ge1{,}5
$$

η ≈ 1: o fluxo moveu o preço como habitualmente; η ≈ 0: fluxo absorvido; η < 0: o preço foi contra o fluxo; η > 1:
livro fino ou impacto amplificado. **Não é gatilho**: o impacto é côncavo e satura (Hasbrouck [V]; Weber-Rosenow [V];
lei da raiz quadrada [V]; Patzelt-Bouchaud [V]), por isso η cai mecanicamente quando |fluxo| cresce, e uma regra «η ≤
0,5 = absorção» dispararia exactamente nas barras climácticas. O mecanismo de absorção da literatura, contrafluxo de
ordens limite que torna o impacto realizado cerca de 4 vezes menor do que o implícito no livro visível (Weber e
Rosenow [V]), é funcionamento normal do mercado.

---

## 7. Eventos de janela curta e máquina de estados

Esta camada é separada do Z porque o único efeito encontrado em dados reais foi em janelas de cerca de 15 minutos [E].

### 7.1 Janelas e pernas curtas

$$
k_e=\min\Big(\max\big(1,\operatorname{round}(60\,w/\text{seg})\big),\ \max(1,\lfloor M/20\rfloor)\Big),\qquad
L=\max\big(1,\operatorname{round}(60\,\ell/\text{seg})\big)
$$

com *w* = 15 min (janela do evento), ℓ = 60 min (vida máxima) e «seg» os segundos por barra do gráfico. Em 5 minutos:
k_e = 3 e L = 12; em 1 minuto: 15 e 60; em 15 minutos ou mais: k_e = 1; em 1 hora ou mais: L = 1. O máximo M/20
garante que zF e zP são calibrados em pelo menos 20 janelas.

$$
F_e=\frac{\sum_{k_e}u_d}{\sqrt{k_e}},\quad P_e=\frac{\sum_{k_e}u_r}{\sqrt{k_e}}\quad(\text{só com hqOk}),\qquad
z_F=\frac{F_e}{\mathrm{RMS}_{t-1}(F_e)},\quad z_P=\frac{P_e}{\mathrm{RMS}_{t-1}(P_e)}
$$

com o mesmo RMS não centrado e desfasado da secção 6.3 (cada um com o seu próprio histórico).

### 7.2 Classes

Com s = sign(z_F) e o gate aberto:

| Classe | Definição | Rótulo |
|---|---|---|
| ABSORVIDO | (\|z_F\| ≥ 2 e s·z_P ≤ 0) ou TRAVADO | «Compras absorvidas» / «Vendas absorvidas» |
| TRAVADO (subconjunto) | \|z_F\| ≥ 3, \|z_P\| ≤ 0,5 e s·z_P < \|ρ̂\|·\|z_F\| | «· preço travado» |
| CONFIRMADO | \|z_F\| ≥ 2 e s·z_P ≥ \|ρ̂\|·\|z_F\| | Não é marcado (espera-se reversão parcial; contexto) |
| PREÇO SEM FLUXO | não ABSORVIDO, \|z_P\| ≥ 2 e sign(z_P)·z_F ≤ 0 | «Preço ↑ sem fluxo comprador» / «Preço ↓ sem fluxo vendedor» |

Entre ABSORVIDO e CONFIRMADO fica uma zona intermédia (0 < s·z_P < |ρ̂|·|z_F|: o preço acompanhou o fluxo, mas menos
do que ρ implica) que não é marcada, excepto pelos casos TRAVADO: estes incluem casos com o preço ligeiramente no
sentido do fluxo, mas nunca a classe CONFIRMADO. Com os valores por omissão a exclusão não muda nada
(|ρ̂|·|z_F| ≥ 0,3·3 > 0,5), mas impede que um |z_P| máximo alto deixe entrar barras confirmadas. «Travado» não é raro:
o z_F tem caudas pesadas e |z_F| ≥ 3 ocorreu em 2–3,5% das barras em dados reais [E].

### 7.3 Aglomerados

Um evento novo de uma classe começa quando o lado muda (por exemplo, compras absorvidas e, na barra seguinte, vendas
absorvidas, comum com k_e = 1) ou quando passaram **mais de k_e barras** desde a última barra da mesma classe e do
mesmo lado (período refractário). Um mergulho de 1–2 barras de |z_F| abaixo do limiar não cria um evento novo. Só a
primeira barra de cada aglomerado gera rótulo e alerta, e só em barras fechadas. Se um aglomerado TRAVADO começar
dentro de um aglomerado de absorção já assinalado, do mesmo lado, o rótulo pendente recebe «· preço travado» e o
alerta de «travado» dispara, sem um evento novo.

### 7.4 Qualidade e confiança

| Situação | Rótulo | Alertas |
|---|---|---|
| Qualidade alta e calibração do zF/zP com pelo menos max(20·k_e, 2N) valores | cheio | sim |
| Qualidade média (com «Mostrar eventos com qualidade média» ligado) e calibração suficiente | oco, «(baixa conf.)» | sim; a mensagem indica qualidade 2 |
| Calibração do zF/zP com menos de max(20·k_e, 2N) valores | oco, «(cal. prov.)»; com qualidade média, «(baixa conf.)» | não (nem o evento nem a sua resolução) |
| Qualidade baixa ou sem dados | nenhum | não |

O estilo de baixa confiança para a qualidade média vem dos dados: em BTC, o ligeiro efeito de continuação observado
com o delta verdadeiro desapareceu com delta estimado de intrabars de 1 minuto [E].

### 7.5 Máquina de resolução da absorção

Há no máximo **um** evento de absorção pendente.

1. Na barra do evento t₀ regista-se o lado (+1 compras, −1 vendas), H₀ = máximo de H nas últimas k_e barras e
   L₀ = mínimo de L nas últimas k_e barras (incluindo t₀).
2. Em cada barra fechada t > t₀, para compras absorvidas (lado +1):
   - C_t > H₀ → **«→ continuação ↑»**: a absorção falhou, o fluxo ganhou; cor de subida.
   - C_t < L₀ → **«→ absorção segurou ↓»**: o lado passivo venceu; cor de descida.
   - nenhum dos dois e t − t₀ ≥ L → **«→ expirou»**: cor neutra.
   - Para vendas absorvidas, o espelho: C_t < L₀ → continuação ↓; C_t > H₀ → segurou ↑.
3. Uma absorção nova com um evento pendente marca o anterior «→ substituído» (neutro) e passa a ser a pendente.

A seta indica o sentido em que o preço resolveu, para que a leitura não dependa só da cor. Os eventos de preço sem
fluxo não têm máquina de resolução. A vida de ~60 minutos segue Chordia, Roll e Subrahmanyam (2005): a
previsibilidade a partir do desequilíbrio desaparece em mais de 5 e menos de 60 minutos [V]; em BTC os efeitos
apareceram a 30–60 minutos e tinham desaparecido às 3 horas [E].

**Viés direccional** (Neutro por omissão, Continuação, Reversão): só recolore eventos de qualidade alta ainda **não
resolvidos**. Nunca deve ser «Reversão» por omissão: não há evidência de que o lado passivo esteja tipicamente
informado.

Em gráficos de 1 hora ou mais os eventos são apenas contexto (a vida é de 1 barra e a dica do rótulo indica que a
evidência de seguimento só existe a ~15–60 minutos).

### 7.6 Frequência em dados reais [E]

Na validação (BTCFDUSD, 5 minutos, delta verdadeiro, intrabars de 1S, 31 dias) houve 58 rótulos (1,9 por dia): 28
compras absorvidas (10 com «preço travado»), 17 vendas absorvidas (2 travadas) e 13 de preço sem fluxo. As 45
absorções resolveram-se em 21 continuações, 17 «segurou», 5 expirações e 2 substituições. Pormenores e outras
configurações em [VALIDACAO.md](VALIDACAO.md).

---

## 8. Divergência por pivots

Opcional, desligada por omissão.

- ph_t = `ta.pivothigh(high, Le, Ri)` e pl_t = `ta.pivotlow(low, Le, Ri)`, com Le = 5 e Ri = 2: o pivot está na barra
  t − Ri e só é conhecido em *t*.
- O CVD lê-se **na barra do pivot do preço**: CVD^c_{t−Ri}. Não se exige um pivot simultâneo no CVD (um erro comum em
  scripts da comunidade).
- **Topo sem confirmação do fluxo**: ph > pivot de máximo anterior e CVD^c no pivot ≤ CVD^c no pivot anterior −
  0,5·σ_{Δ,t−1}.
- **Fundo sem confirmação do fluxo**: pl < pivot de mínimo anterior e CVD^c no pivot ≥ CVD^c no pivot anterior +
  0,5·σ_{Δ,t−1}.
- Os dois pivots têm de estar a 5–60 barras de distância e dentro do mesmo regime contínuo de qualidade ≥ média.
- O rótulo fica na barra do pivot, em estilo neutro e oco; o alerta sai na confirmação (Ri barras depois). No painel,
  uma linha pontilhada liga os valores da linha do CVD nos dois pivots, se estiverem no mesmo período de âncora.
- A magnitude é medida em unidades do σΔ de **uma** barra: não escala com a distância entre os pivots.

**Evidência.** Num teste interno a extremos de 4 horas (não a estes pivots), os novos extremos já reverteram
ligeiramente por si só (−6 a −8 bps a 2–3 h, qualquer que fosse o CVD); com não-confirmação do CVD −5,5 a −7,5 bps
contra −1 a −2 bps com confirmação, diferença não significativa [E]. É contexto, não previsão.

---

## 9. Interpretação honesta

### 9.1 Força da evidência

| Afirmação | Evidência | Força |
|---|---|---|
| Os incrementos do preço co-movem linearmente com o fluxo assinado, em tamanhos pequenos | Kyle [V]; Evans-Lyons [V]; Cont-Kukanov-Stoikov [V]; Chordia-Roll-Subrahmanyam 2002, R² ajustado 0,28 [V]; Silantyev (cripto) [V]; ρ próprio em BTC 0,39–0,45 [E] | **Forte** |
| O impacto é côncavo e satura com fluxo grande | Hasbrouck [V]; Weber-Rosenow 0,48·Q^0,76 [V]; Plerou et al. [V]; Patzelt-Bouchaud [V]; lei da raiz quadrada [V] | **Forte** |
| «Fluxo sem preço» é muitas vezes normal (contrafluxo de ordens limite, impacto transitório, memória longa dos sinais) | Bouchaud et al. 2004 [V]; Weber-Rosenow, factor 4 [V]; Lillo-Farmer [V]; Eisler et al. [V] | **Forte** (mecanismo) |
| O desequilíbrio prevê volatilidade, não direcção | Easley-López de Prado-O'Hara 2012: o VPIN «não é um indicador direccional» [V] | Moderada |
| A pressão de preço confirmada pelo fluxo reverte parcialmente | Chordia-Roll-Subrahmanyam 2002: coeficientes do desequilíbrio desfasado, condicionais ao actual, −4,56 e −5,83 [V]; Hendershott-Menkveld [V-sec]; cerca de 1/3 do impacto de metaordens reverte (Farmer et al. [V]); BTC próprio −4 a −5 bps [E] | **Moderada** |
| Direcção depois de absorção | Nenhum teste revisto por pares. Kaniel-Liu e Brogaard et al. são incondicionais [V]. BTC, janelas de 15 min: absorvidas +7,7 bps (IC 1,5–13,7) e travadas +14,6 bps (IC 7,8–22,3), continuação a 30 min, na amostra, numa bolsa satélite; desaparece com delta estimado de 1 minuto [E]. Simulação: o sinal depende de quão informado está o lado passivo [E]. Osler [M]: a composição das ordens em repouso decide entre reversão e cascata | **Fraca / não validada**; no máximo uma ligeira continuação de curto prazo |
| A exaustão bate a taxa base de reversão em novos extremos | Nenhum teste revisto por pares; BTC próprio: não significativo [E] | **Não estabelecida** |
| O Z (K = 20) prevê retornos | Dados reais próprios: nulo depois do controlo de testes múltiplos [E]; Chordia-Roll-Subrahmanyam 2002: sem previsibilidade incondicional no dia seguinte [V] | **Nula** |
| A correlação de níveis ou o spread de z-scores «confirma» ou «diverge» | Regressão espúria [V]; Ernst-Shepp-Wyner [V]; Monte Carlo próprio [E] | **Inválida** |

**Retornos seguintes: um nulo honesto [E].** Em dados reais não houve efeito robusto de nenhuma das pernas a H = K/2
nem a H = K. Os retornos seguintes com sinal, nos episódios liderados pelo fluxo, ficaram dentro de ±0,2σ√H, com taxas
de acerto de 0,44–0,58. As poucas células com |t| ≈ 2–2,5 (n = 14–30) não sobrevivem à correcção de Bonferroni sobre
mais de 64 células. **O Z é um medidor descritivo de divergência, não uma previsão.**

### 9.2 O que o indicador diz, e o que não diz

- «Fluxo ≠ preço» é um **estado**, não um sinal.
- A absorção tem duas resoluções opostas. O lado passivo está informado ou é persistente → reversão. O lado passivo
  esgota-se (como uma paridade que quebra; Killeen-Lyons-Moore) → o preço apanha o fluxo. **O preço decide.**
- Os efeitos, se existirem, são de poucos bps em ~30–60 minutos. Nada na evidência suporta uma vantagem negociável por
  si só.
- O CVD só vê negócios agressores. Grande parte do que parece divergência é fluxo de ordens limite, que pode ele
  próprio ser informado (Kaniel-Liu; Brogaard et al.).
- Em cripto, o CVD de uma só bolsa inclui fluxo específico dessa bolsa; a componente comum do volume assinado entre
  bolsas explica cerca de 80% dos retornos do BTC (Makarov e Schoar [V]).
- A calibração assenta num par cripto à vista em 4 meses mais simulações. Futuros do CME (âncoras Globex e RTH),
  acções e perpétuos líquidos não estão validados. Os limiares (gate 0,30, |Z| 2/3, K = 20, M = 1000, c = 4) têm base
  teórica e são empiricamente razoáveis, mas não foram validados fora da amostra.

---

## 10. Diferenças em relação ao dossier

O dossier ([research-dossier.md](research-dossier.md)) é o documento de investigação original. A implementação final
difere nos pontos seguintes, todos deliberados:

| Tema | Dossier | Implementação |
|---|---|---|
| Qualidade alta | Intrabars de ticks ou de segundos | Só «1T» ou «1S» com a regra da vela; outros segundos/ticks e o BVC: média. Símbolos com volume de ticks declarado ou FX à vista: no máximo baixa (os CFD com volume de ticks não declarado não são detectados; secção 2.6) |
| Costura da cobertura | Marcar a transição e recomeçar o aquecimento | Também reinicia as linhas uma vez quando a escala congelada veio de uma janela mista (secção 4.4) |
| Aquecimento do Z | 2N valores antes de mostrar o Z | Z mostrado com N valores (calibração provisória assinalada); alertas de Z com 2N; eventos sem alertas com menos de max(20·k_e, 2N) |
| Condição de dados do Z | Janelas σ/ρ em dados de qualidade ≥ média | Todas as janelas de todos os termos: N + max(K, k_e) barras seguidas (+N com a deriva) |
| Aglomerados de eventos | 1.ª barra de `cond and not cond[1]` | Por classe **e** lado, com período refractário de k_e barras |
| Alertas de Z | 1.º cruzamento | 1.º cruzamento com histerese (rearme em limiar − 1) |
| Alerta «travado» | Um alerta | Um por lado; também quando o «travado» surge dentro de uma absorção pendente |
| Janela do evento | max(1, round(900/seg)) | Limitada a M/20 barras |
| Tipo de volume | Aviso para «tick» e «n/a» | «n/a» é o normal fora de cripto e não leva aviso; o volume de ticks leva aviso e corta a qualidade |
| Âncoras | Auto, RTH, 1D/1W/1M | Mais a sessão personalizada |
| Arquitectura do footprint | Um só script (D10) | Duas edições geradas da mesma fonte: a Standard, sem código nem texto visível do footprint, e a Footprint, com um único `request.footprint()` dentro de `if` (README, «Edições e planos da TradingView») |
| Classe «travado» | \|z_F\| ≥ 3 e \|z_P\| ≤ 0,5 | Também exclui a classe CONFIRMADO (secção 7.2) |
| λ na tabela | bps por 1000 unidades | Unidade adaptativa: 1, 10³, 10⁶, … unidades, a que deixa λσ ≥ 0,1 (secção 6.9); o Data Window mantém «λ OLS (bps/1000)» |
| Cone nulo iid | Cone verdadeiro cerca de 15–30% mais largo, por causa da memória longa do fluxo (estimativa pelo VR20 = 1,30) | Mesmo cone; a dica e a documentação citam a medição directa em dados reais: desvio RMS 1,5 (15 min) a 2,3 vezes (5 min) o do cone, 10% e 17% de saídas em vez de 4,6% (secção 5.8) |
| Divergência por pivots | Pivots no mesmo segmento de âncora | CVD contínuo e os dois pivots no mesmo regime de qualidade ≥ média; só a linha pontilhada do painel exige a mesma âncora (secção 8) |
| Não implementado | Candidatos de exaustão; marca de reversão à média (Dickey-Fuller); transformação côncava do fluxo; λ assimétrico; alerta «gate aberto» | — |

---

## Bibliografia anotada

Apenas fontes do dossier. Entre parênteses rectos, o estado de verificação. Os números de fontes [V-sec] ou [M] não
são citados como factos.

### Impacto no preço e teoria do fluxo de ordens

- **Kyle, A.S. (1985).** Continuous Auctions and Insider Trading. *Econometrica* 53(6):1315–1335. **[V]** (resumo e
  forma em diapositivos). Preços lineares no fluxo líquido, Δp = λy; profundidade 1/λ; no modelo estático
  λ = ½√(Σ₀/σ_u²), decrescente com a variância do ruído. *Uso:* base teórica do mapeamento igualado à volatilidade.
  https://www.econometricsociety.org/publications/econometrica/browse/1985/11/01/continuous-auctions-and-insider-trading
- **Glosten, L., Milgrom, P. (1985).** *JFE* 14:71–100. **[V]** (resumo). A selecção adversa por si só cria um spread;
  o sinal do negócio é informativo. https://ideas.repec.org/p/nwu/cmsems/570.html
- **Hasbrouck, J. (1991).** Measuring the Information Content of Stock Trades. *JF* 46(1):179–207. **[V]** (resumo). O
  conteúdo informativo é o impacto permanente da **inovação** do negócio; impacto côncavo e com atraso. *Uso:* guarda
  de concavidade; remoção da deriva. https://ideas.repec.org/a/bla/jfinan/v46y1991i1p179-207.html
- **Cont, R., Kukanov, A., Stoikov, S. (2014).** The Price Impact of Order Book Events. *J. Fin. Econometrics*
  12(1):47–88. **[V]** (resumo). Relação linear entre variações de curto prazo do ponto médio e o desequilíbrio do
  fluxo do livro (OFI), com declive ∝ 1/profundidade; a relação com o volume negociado é «mais ruidosa e menos
  robusta». *Uso:* λ variável no tempo; o CVD é só parte do fluxo. https://arxiv.org/abs/1011.6402
- **Cont, R., Cucuringu, M., Zhang, C. (2023).** Cross-impact of order flow imbalance in equity markets. *Quant.
  Finance* 23(10). **[V]** (resumo). OFI integrado em vários níveis bate o do melhor nível. https://arxiv.org/abs/2112.13213
- **Xu, K., Gould, M.D., Howison, S.D. (2019).** Multi-Level Order-Flow Imbalance in a Limit Order Book. **[V]** O
  ajuste melhora com cada nível de profundidade. https://arxiv.org/abs/1907.06230
- **Lillo, F., Farmer, J.D. (2004).** The long memory of the efficient market. *SNDE* 8(3). **[V]** Autocorrelação dos
  sinais ~τ^−0,6. *Uso:* o CVD é superdifusivo; o escalamento em √K falha; é precisa calibração empírica.
  https://arxiv.org/abs/cond-mat/0311053
- **Lillo, F., Mike, S., Farmer, J.D. (2005).** Theory for long memory in supply and demand. *PRE* 71. **[V]** (resumo).
  A divisão de metaordens com lei de potência gera memória longa nos sinais. https://arxiv.org/abs/cond-mat/0412708
- **Bouchaud, J.-P., Gefen, Y., Potters, M., Wyart, M. (2004).** Fluctuations and response in financial markets.
  *Quant. Finance* 4(2). **[V]** (texto integral). Modelo de propagador: preços difusivos sse 2β + γ = 1; ordens de
  mercado persistentes são compensadas por ordens limite que revertem à média. https://arxiv.org/abs/cond-mat/0307332
- **Bouchaud, J.-P., Kockelkoren, J., Potters, M. (2006).** Random walks, liquidity molasses and critical response.
  *Quant. Finance* 6(2). **[V]** (resumo). Impacto transitório. https://arxiv.org/abs/cond-mat/0406224
- **Eisler, Z., Bouchaud, J.-P., Kockelkoren, J. (2012).** The price impact of order book events. *Quant. Finance*.
  **[V]** Ordens limite e cancelamentos também têm impacto; modelos só com negócios implicam impacto transitório.
  https://arxiv.org/abs/0904.0900
- **Weber, P., Rosenow, B. (2005).** Order book approach to price impact. *Quant. Finance* 5(4). **[V]** (texto
  integral). Em dados de 5 minutos da Island ECN, G = 0,48·Q^0,76 (R² = 0,997); o impacto implícito no livro visível é
  **quatro vezes** o real, porque o fluxo de ordens limite é anticorrelacionado com os retornos. *Uso:* explicação
  quantitativa da «absorção como estado normal». https://arxiv.org/abs/cond-mat/0311457
- **Plerou, V., Gopikrishnan, P., Gabaix, X., Stanley, H.E. (2002).** *PRE* 66. **[V]** (resumo). Impacto condicional
  côncavo. https://arxiv.org/abs/cond-mat/0106657
- **Patzelt, F., Bouchaud, J.-P. (2018).** Universal scaling and nonlinearity of aggregate price impact. *PRE* 97.
  **[V]** (resumo). Impacto agregado sigmoidal universal, linear para desequilíbrios pequenos. Sem teste de retornos
  seguintes. https://arxiv.org/abs/1706.04163
- **Tóth, B. et al. (2011).** Anomalous price impact and the critical nature of liquidity. *PRX* 1. **[V]** (resumo).
  Impacto de metaordens em raiz quadrada, I ≈ Y·σ·√(Q/V). https://arxiv.org/abs/1105.1694
- **Sato, Y., Kanazawa, K. (2025).** Strict universality of the square-root law. *PRL* 135. **[V]** (resumo). δ = ½ em
  toda a bolsa de Tóquio. https://arxiv.org/abs/2411.13965
- **Farmer, J.D., Gerig, A., Lillo, F., Waelbroeck, H. (2013).** How efficiency shapes market impact. *Quant. Finance*
  13. **[V]** (resumo). O impacto permanente é cerca de 2/3 do máximo. https://arxiv.org/abs/1102.5457
- **Donier, J., Bonart, J. (2015).** A million metaorder analysis of market impact on the Bitcoin. **[V]** (resumo). A
  lei da raiz quadrada vale no BTC. https://arxiv.org/abs/1412.4503
- **Maitrier, G., Loeper, G., Bouchaud, J.-P. (2025/26).** Square-root impact, order imbalance & volatility. *Quant.
  Finance* 26(6). **[V]** (resumo). Para o OFI generalizado Σε·v^a, a correlação com os retornos é máxima num *a*
  interior: ponderar pelo volume (a = 1) não é óptimo. https://arxiv.org/abs/2506.07711
- **Amihud, Y. (2002).** Illiquidity and stock returns. *JFM* 5. **[V]** ILLIQ = média de |r|/volume em moeda. Só como
  ideia de λ sem sinal. https://www.cis.upenn.edu/~mkearns/finread/amihud.pdf

### Fluxo de ordens e retornos: horizontes, níveis, previsibilidade

- **Evans, M.D.D., Lyons, R.K. (2002).** Order Flow and Exchange Rate Dynamics. *JPE* 110(1):170–180. **[V]** (resumo).
  Variações diárias do câmbio regredidas sobre o fluxo de ordens, R² acima de 60% (DM/$). A figura 1, que sobrepõe os
  níveis da taxa ao fluxo acumulado, é **[V-sec]**. *Uso:* precedente do painel e do modo preço implícito.
  https://www.nber.org/papers/w7317
- **Evans, M.D.D., Lyons, R.K. (2005).** Meese-Rogoff redux. *AER* 95(2). **[V]** (resumo). O micro-modelo bate o
  passeio aleatório de 1 dia a 1 mês.
- **Killeen, W.P., Lyons, R.K., Moore, M.J. (2006).** Fixed versus flexible: Lessons from EMS order flow. *JIMF* 25(4).
  **[V]** (resumo). Efeitos persistentes do fluxo antes da UEM, desacoplamento depois; os pormenores de cointegração
  são **[V-sec]**. https://www.nber.org/papers/w8491
- **Berger, D. et al. (2008).** Order flow and exchange rate dynamics in EBS data. *JIE* 75(1). **[V]** (resumo).
  Relação forte de 1 minuto a 2 semanas, mais fraca para lá disso; mais forte com pouca liquidez.
- **Chordia, T., Roll, R., Subrahmanyam, A. (2002).** Order imbalance, liquidity, and market returns. *JFE* 65.
  **[V]** (texto integral). Desequilíbrio contemporâneo: R² ajustado 0,28. Desequilíbrio desfasado, condicional ao
  actual: −4,56 (compras, t −13,1) e −5,83 (vendas, t −5,1), reversão de inventário; incondicionalmente, não prevê.
  Impacto das vendas cerca de 3 vezes o das compras. https://ideas.repec.org/a/eee/jfinec/v65y2002i1p111-130.html
- **Chordia, T., Subrahmanyam, A. (2004).** Order imbalance and individual stock returns. *JFE* 72. **[V-sec]**
  Qualitativamente: o desequilíbrio desfasado tem efeito positivo, que passa a negativo quando se controla o actual.
- **Chordia, T., Roll, R., Subrahmanyam, A. (2005).** Evidence on the speed of convergence to market efficiency. *JFE*
  76(2). **[V]** (resumo). Absorvido em mais de 5 e menos de 60 minutos. *Uso:* vida de ~60 minutos dos eventos.
- **Hendershott, T., Menkveld, A.J. (2014).** Price pressures. *JFE* 114(3). **[V-sec]** Pressões de preço que
  revertem; magnitudes não citadas. https://ideas.repec.org/p/zbw/cfswop/201014.html
- **Dufour, A., Engle, R.F. (2000).** Time and the price impact of a trade. *JF* 55(6). **[V-sec]** O impacto cresce
  quando a negociação é mais rápida.
- **Takahashi, M. (2025).** Returns and Order Flow Imbalances: intraday dynamics and macro news. **[V]** (resumo). As
  notícias aumentam o impacto. https://arxiv.org/abs/2508.06788
- **Kaniel, R., Liu, H. (2006).** So what orders do informed traders use? *J. Business* 79(4). **[V]** (resumo). Os
  informados podem preferir ordens limite. Incondicional; sem estudo de eventos de absorção.
- **Brogaard, J., Hendershott, T., Riordan, R. (2019).** Price discovery without trading. *JF* 74(4). **[V]** (resumo).
  As ordens limite fazem a maior parte da descoberta de preço.
- **Silantyev, E. (2019).** Order flow analysis of cryptocurrency markets. *Digital Finance* 1. **[V]** (resumo). Na
  BitMEX, o desequilíbrio dos negócios (incrementos do CVD) explica as variações contemporâneas do preço melhor do que
  o OFI.
- **Makarov, I., Schoar, A. (2020).** Trading and arbitrage in cryptocurrency markets. *JFE* 135(2). **[V]** A
  componente comum do volume assinado entre bolsas explica cerca de 80% dos retornos do BTC.
- **Osler (2003), Bessembinder-Panayides-Venkataraman (2009), Kavajecz-Odders-White (2004), Menkhoff et al. (2016),
  Pastor-Stambaugh (2003). [M]** Só como contexto qualitativo; números não citados.

### Classificação de negócios e estimação do delta

- **Lee, C.M.C., Ready, M.J. (1991).** *JF* 46(2). **[V]** (resumo). Regra das cotações com recurso à regra do tick.
- **Ellis, K., Michaely, R., O'Hara, M. (2000).** *JFQA* 35(4). **[V]** No Nasdaq: regra das cotações 76,4%, regra do
  tick 77,66%, Lee-Ready 81,05% de acerto. Define a regra EMO.
- **Easley, D., López de Prado, M., O'Hara, M. (2012).** Flow toxicity and liquidity in a high-frequency world. *RFS*
  25(5). **[V]** (manuscrito aceite). Eq. 7: V^B = Σ V_i·Z((P_i − P_{i−1})/σ_ΔP), com Z a distribuição Normal; janela
  de σ não indicada; o VPIN «não é um indicador direccional». https://papers.ssrn.com/abstract=1695596
- **Easley, D., López de Prado, M., O'Hara, M. (2016).** Discerning information from trade data. *JFE* 120(2).
  **[V]** (resumo). A regra do tick e o BVC são ambos razoáveis; o BVC liga-se melhor a proxies de informação.
- **Chakrabarty, B., Pascual, R., Shkilko, A. (2015).** *JFM* 25. **[V]** (resumo). A regra do tick e Lee-Ready batem o
  BVC.
- **Andersen, T.G., Bondarenko, O. (2015).** *Review of Finance* 19(1). **[V]** (resumo). O BVC é pior do que a regra
  do tick e os seus erros correlacionam-se com o volume e a volatilidade.
- **Massot, M., Nawn, S., Pascual, R. (2018, WP).** **[V]** Acerto do BVC de 92,4% em barras de 5 minutos e 50,9% em
  barras de 1 segundo.
- **Abramowitz, M., Stegun, I.A. (1964).** *Handbook of Mathematical Functions*, eqs. 7.1.26 e 26.2.17. **[V]**
  Coeficientes confirmados e revalidados numericamente. https://www.johndcook.com/python_erf.html
- **Biblioteca `ta` da TradingView, v12 (2025.12.06), MPL-2.0.** **[V]** (código-fonte). Regra das cotações em «1T»;
  regra da vela, depois do tick, depois lado transportado.
- **Centro de Ajuda da TradingView: Volume Delta / CVD.** **[V-sec]** Timeframe inferior Auto: 1S em gráficos de
  segundos, 1 em intradiário, 5 no diário, 60 nos restantes; âncora «1D».
  https://www.tradingview.com/support/solutions/43000725058-cumulative-volume-delta/

### Estatística: regressão espúria, normalização, calibração

- **Granger, C.W.J., Newbold, P. (1974).** Spurious regressions in econometrics. *J. Econometrics* 2. **[V]**
  https://gwern.net/doc/economics/1974-granger.pdf
- **Phillips, P.C.B. (1986).** Understanding spurious regressions in econometrics. *J. Econometrics* 33. **[V]**
- **Ernst, P.A., Shepp, L.A., Wyner, A.J. (2017).** Yule's "nonsense correlation" solved! *Ann. Stat.* 45(4). **[V]**
  E[θ²] = 0,240522 para dois passeios aleatórios independentes. https://www.ma.imperial.ac.uk/~pernst/AOS1509.pdf
- **Engle, R.F., Granger, C.W.J. (1987).** Co-integration and error correction. *Econometrica* 55(2). **[V]** (resumo).
- **Avellaneda, M., Lee, J.-H. (2010).** Statistical arbitrage in the U.S. equities market. *Quant. Finance* 10(7).
  **[V]** (texto integral). Resíduos acumulados com *s-score* OU; o seu filtro τ < janela/2 passa 98,6% das janelas
  nulas [E].
- **Shiffler, R.E. (1988).** Maximum Z scores and outliers. *Am. Stat.* 42(1). **[V]** Com o desvio-padrão populacional,
  |z| ≤ √(N − 1).
- **Fisher, R.A. (1915).** Transformação z. **[V-sec]** atanh(r)·√(N − 3) ≈ N(0, 1).
- **Rousseeuw, P.J., Croux, C. (1993).** *JASA* 88. **[V]** O MAD tem eficiência gaussiana de 37%.
- **Moskowitz, T.J., Ooi, Y.H., Pedersen, L.H. (2012).** Time series momentum. *JFE* 104. **[M]** Escalamento por σ
  *ex ante*; só como referência qualitativa.

### Plataforma e prática

- **Pine Script v6 — manual e referência da TradingView** (cópia local e espelhos no GitHub). **[V]** `request.footprint`
  («só contas Premium ou Ultimate podem usar scripts que chamam esta função»; um único local de chamada),
  `request.security_lower_tf` (devolve um ID de array *na* com `ignore_invalid_timeframe`), limites de intrabars,
  `input.*(…, active)`, `timeframe.change`, `session.isfirstbar_regular`, limite de 64 plots.
  https://github.com/codenamedevan/pinescriptv6 (1.ª cópia) e https://github.com/chris-c-thomas/pine-script-v6-md
  (2.º espelho, com as páginas de `footprint.delta()` e `footprint.total_volume()`)
- **TradingView/LucF, CVD Candles v8 e CVD Chart v3 (2026).** **[V]** (espelho do código). Modos de reinício, caixa de
  cobertura e aviso com menos de 5 intrabars por barra.
- **ata_sabanci, VFP-Intro (2026).** **[V]** (espelho do código). Padrão de um único `request.footprint()` dentro de um
  `if`, e a afirmação de que o script «pára com erro» nos planos inferiores.
- **LuxAlgo, notas de cobertura do footprint no PineTS.** **[V]** A TradingView rejeita um segundo local de chamada,
  mesmo que nunca seja executado; footprints com mais de 2000 linhas devolvem *na*.
  https://github.com/LuxAlgo/PineTS/blob/main/docs/api-coverage/footprint.md
- **Sierra Chart (Studies8.cpp) e ATAS (CumulativeDelta.cs).** **[V]** (código). Delta verdadeiro *ask* menos *bid*,
  reinício por dia ou sessão.
- **mcart13/tvaudible, leitura da página de preços (2026-09-29).** **[V-sec]** Intervalos de segundos só em
  Premium/Ultimate; intervalos de ticks só em Ultimate.

### Trabalho empírico próprio [E]

Todos na própria amostra, maioritariamente numa só bolsa e não revistos por pares; scripts de investigação não
incluídos neste repositório.

1. Monte Carlo sintético de classificação de negócios (só a ordenação; substituído pelo estudo com dados reais onde
   discordam).
2. Monte Carlo de normalização: distribuições nulas de z-scores de níveis e spreads, artefactos de meia-vida, numérica.
3. Fidelidade dos estimadores com dados reais: Binance BTCUSDT à vista (1 dia), perpétuos BTC e ETH (dia de queda),
   BTCFDUSD à vista (117 dias) e LOBSTER AMZN/MSFT/GOOG (1 dia), todos com marcas de agressor.
4. Calibração da divergência: BTCFDUSD 5 e 15 minutos com delta verdadeiro, mais uma simulação de propagador (γ = 0,6,
   liquidez escondida com preço limitado).
5. Estudo de retornos seguintes a eventos: BTCFDUSD, 117 dias, t com agrupamento por dia e *bootstrap* em blocos de
   dias.
