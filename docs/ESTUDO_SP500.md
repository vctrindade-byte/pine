# Estudo S&P 500: os sinais do indicador no ES, no MES e no SPY

Estudo de eventos pré-registado que responde, para o S&P 500, ao plano de validação da auditoria externa
([AUDITORIA.md](AUDITORIA.md), ponto (i)). A pergunta: os sinais do indicador «Preço × CVD Normalizado [Order Flow]»,
com os valores por omissão e o delta que a TradingView usa por omissão num gráfico de 5 ou 15 minutos, dizem alguma
coisa sobre o que o preço faz a seguir, depois de custos e para além do que o próprio preço já diz?

- **Código e reprodução:** [research/sp500/](../research/sp500/README.md). As tabelas completas, em inglês, estão em
  `research/sp500/results/` (`es/results.md` para o estudo principal).
- **Dados:** não estão no repositório. As licenças são só para investigação e não permitem redistribuição (secção 2).
- **Fórmulas do indicador:** [METODOLOGIA.md](METODOLOGIA.md). O estudo não alterou o indicador.
- Todos os números deste documento são resultados empíricos próprios, não revistos por pares (a marca [E] dos outros
  documentos). Os números entre parênteses rectos são intervalos de confiança de 95%; σ é a unidade de volatilidade
  definida na secção 3.

## Em resumo

1. **Resultado principal nulo.** Em 18,7 anos de ES (gráfico de 5 minutos, 2008–2026, 30 554 sinais com janela
   válida), nenhuma das 16 classes de sinais prevê o retorno com sinal 30 minutos depois: 0 de 16 depois da correcção
   de Benjamini-Hochberg, e nenhuma chega sequer a p < 0,05 sem correcção (menor p = 0,100). As médias ficam entre
   −0,130σ e +0,041σ, ou seja, entre −1,6 e +1,0 pontos-base.
2. **O CVD não acrescenta direcção ao preço.** Uma absorção (fluxo forte, preço parado) foi seguida do mesmo retorno
   que um choque de fluxo do mesmo tamanho que moveu o preço: diferença +0,015σ, p = 0,68. Contra barras aleatórias
   emparelhadas por hora, volatilidade e movimento recente do preço, 0 de 18 diferenças sobrevivem à correcção, em 5 e
   em 15 minutos.
3. **Nenhuma regra simples ganha dinheiro depois de custos.** Nas 224 combinações de classe, horizonte e direcção,
   nenhum resultado líquido é significativamente positivo (todos os q = 1,000), mesmo com um custo optimista de
   0,325 pontos por ida e volta.
4. **O que os sinais marcam é sobretudo volatilidade.** Depois de 13 das 16 classes, o preço move-se mais, em valor
   absoluto, do que em barras comparáveis (+0,06σ a +0,18σ aos 30 minutos). Isso não indica o sentido.
5. **Cuidado com absorções e «preço travado» ao fecho.** Em 15 minutos, 58% das absorções e 67% dos «travados» caem
   nas barras das 14:45 e das 15:00 CT. Quando a janela inclui o minuto de liquidação das 14:59 CT, o lado do evento
   coincide em 99,6–100% dos casos com o sinal dessa única vela de 1 minuto. As únicas pistas de 15 minutos vêm daí e
   desaparecem contra controlos da mesma barra do dia.
6. **O delta «Auto» não é o fluxo verdadeiro.** Na amostra com o lado agressor de cada negócio (15 sessões de 2013),
   os eventos de fluxo calculados com o delta de 1 minuto recuperaram 2 de 15 eventos do delta verdadeiro (gráfico de
   5 minutos). Este estudo testa os sinais que um utilizador do «Auto» vê. Não testa sinais construídos com o fluxo
   verdadeiro.
7. **Robustez.** No MES (2021–2026) e no SPY (2000–2026, só horário regular e também com horário alargado), o
   resultado principal é igualmente nulo: 0 de 16 em cada conjunto.

## Índice

1. [Objectivo](#1-objectivo)
2. [Dados](#2-dados)
3. [Plano pré-registado](#3-plano-pré-registado)
4. [Validação do motor contra o Pine](#4-validação-do-motor-contra-o-pine)
5. [Fidelidade do delta no ES](#5-fidelidade-do-delta-no-es)
6. [Calibração do Z no ES](#6-calibração-do-z-no-es)
7. [Resultado primário](#7-resultado-primário)
8. [Gémeos e controlos: o CVD acrescenta alguma coisa ao preço?](#8-gémeos-e-controlos-o-cvd-acrescenta-alguma-coisa-ao-preço)
9. [Estudo do gate](#9-estudo-do-gate)
10. [MFE e MAE](#10-mfe-e-mae)
11. [Custos](#11-custos)
12. [Estabilidade](#12-estabilidade)
13. [Observação post hoc: o minuto de liquidação das 14:59 CT](#13-observação-post-hoc-o-minuto-de-liquidação-das-1459-ct)
14. [Robustez: MES e SPY](#14-robustez-mes-e-spy)
15. [Desvios ao plano](#15-desvios-ao-plano)
16. [Limitações](#16-limitações)
17. [Conclusão para quem negoceia de forma discricionária](#17-conclusão-para-quem-negoceia-de-forma-discricionária)
18. [Reprodução](#18-reprodução)

---

## 1. Objectivo

A auditoria classificou o valor dos sinais como uma **questão que exige backtest** e propôs um plano em sete etapas:
integridade dos dados, estabilidade estatística, valor preditivo em unidades de volatilidade a 5, 15, 30 e 60 minutos,
MFE/MAE, controlos, custos e validação fora da amostra ([AUDITORIA.md](AUDITORIA.md), ponto (i)). Até aqui só havia
evidência num par cripto à vista, na própria amostra e com as definições de investigação do dossier, não com o código
final.

Este estudo aplica esse plano ao S&P 500, um mercado muito líquido para o qual há quase 19 anos de barras de 1 minuto
e uma amostra com o lado agressor de cada negócio:

- **o quê:** as 14 condições de alerta do indicador (16 classes, secção 3), com os valores por omissão;
- **com que delta:** o que a TradingView usa por omissão («Auto») num gráfico de 5 ou 15 minutos, isto é, a regra da
  vela em intrabars de 1 minuto (qualidade média);
- **onde:** futuros ES (estudo principal), MES e o ETF SPY (robustez);
- **como:** um plano fixado antes de calcular qualquer resultado, todas as células relatadas, correcção de testes
  múltiplos, controlos que separam o contributo do CVD do contributo do preço, e custos em pontos de ES.

Não é objectivo optimizar parâmetros nem procurar uma estratégia. Também ficam respondidos, em parte, o ponto (d) (o
gate pode esconder regimes relevantes?) e o ponto (f) (as absorções são hipóteses). A secção 16 e o ponto (i) da
auditoria listam o que continua por responder.

## 2. Dados

### 2.1 Fontes e níveis

Os níveis A, B e C dizem quanto se sabe sobre o lado agressor. Não se confundem com a qualidade do indicador (baixa,
média, alta), que classifica a configuração dos dados na TradingView.

| Nível | Conjunto | Período | Conteúdo | Uso | Licença |
|---|---|---|---|---|---|
| A | Amostra de ticks do ES (Tick Data LLC) | 1–20 de Setembro de 2013, 15 sessões (ESU13 → ESZ13) | Todos os negócios do CME e cotações L1; lado agressor inferido pela regra das cotações | Fidelidade do delta (secção 5); validação do motor (secção 4) | Amostra de avaliação, sem redistribuição |
| B | TopstepX ES e MES | Barras de 1 segundo: 9 de Março a 15 de Abril de 2026 (sobretudo 14:30–21:00 UTC); barras de 1 minuto: 20 de Janeiro a 15 de Abril de 2026 | OHLCV de 1 segundo, sem lado agressor | Comparação entre 1S e 1 minuto em 2026 (secção 5) | Nenhuma declarada; só investigação |
| C | ES, contrato dominante | 2 de Janeiro de 2008 a 29 de Setembro de 2026 | OHLCV de 1 minuto, preços não ajustados, contrato e diferença de rolagem por barra | Estudo principal | FirstRate Data (sessões até 2015) e Databento/CME (desde 2016): só investigação |
| C | MES, contrato dominante | Maio de 2021 a Setembro de 2026 | Idem | Robustez (secção 14) | Databento/CME: só investigação |
| C | SPY | 3 de Janeiro de 2000 a 9 de Abril de 2026 (Agosto de 2016 excluído) | OHLCV de 1 minuto, horário regular e alargado | Robustez (secção 14) | Fornecedor não identificado, sem licença declarada; só investigação |

Fontes usadas apenas em verificações cruzadas: um excerto Databento MBP-10 do ES com a marca de agressor da bolsa
(5 de Novembro de 2025, 73 minutos), para validar o classificador do nível A, e três fontes independentes de SPY a
1 minuto (2008–2014, 2022–2023 e 2024–2025), para verificar fechos e volumes.

**Lado agressor no nível A.** Regra de Lee-Ready com a cotação em vigor estritamente antes do milissegundo do negócio
e regra do tick como recurso. No excerto MBP-10, 97,2% do volume foi classificado pela cotação, com 96,8% de acerto;
com o recurso, 95,6% do volume ficou com o lado correcto, e a correlação do delta por minuto com o delta da bolsa foi
0,98.

### 2.2 Licenças: o que está e o que não está no repositório

- Os dados de mercado e os ficheiros derivados barra a barra (barras de 5 e 15 minutos, saídas do indicador por barra)
  **não estão no repositório e não são redistribuídos**. As licenças, quando existem, são para investigação ou
  avaliação.
- O repositório contém o código, as tabelas agregadas (contagens, médias, erros-padrão, p-valores, correlações por
  sessão) e este relatório. Nenhuma tabela contém preços nem séries por barra.
- O `.gitignore` exclui os ficheiros de dados. O código recusa escrever ficheiros por barra dentro de uma árvore git
  (`research/sp500/code/studyenv.py`). Os caminhos são dados só por variáveis de ambiente, sem valores por omissão.
- Como obter os dados e reconstruir os ficheiros limpos: [research/sp500/README.md](../research/sp500/README.md).

### 2.3 Limpeza e sessões

- **ES.** 4 841 sessões, das quais 4 688 limpas. Ficam de fora 153: sessões de rolagem (75), de contrato não dominante
  (30), da janela de rolagem anterior a Junho de 2010, em que a dominância não se pode verificar (35), sessões
  marcadas como degradadas pela Databento, as duas sessões parciais nos extremos do ficheiro e sessões em que o
  contrato escolhido teve menos de 70% do volume. Nos 6 554 710 minutos: nenhum carimbo duplicado, preço não positivo,
  barra OHLC incoerente, volume zero ou preço fora da grelha de 0,25.
- **Emenda das fontes.** Até 2015, FirstRate (contínuo não ajustado); de 2016 em diante, barras Databento por contrato,
  escolhendo em cada sessão o contrato com mais volume. Onde as duas fontes cobrem o mesmo contrato (2016–2026), o
  fecho coincide em pelo menos 99,5% dos minutos em 9 dos 11 anos (96,1% em 2018, 98,9% em 2026), com rácio de volume
  1,00.
- **Rolagens.** Os preços não são ajustados. As janelas dos resultados nunca atravessam uma mudança de sessão nem de
  contrato. As sessões excluídas saem do fluxo de barras que alimenta o indicador.
- **MES.** 1 393 sessões, 1 357 limpas (mesmas regras).
- **SPY.** Linhas duplicadas removidas; Agosto de 2016, em falta na fonte, foi excluído. Contra as três fontes de
  verificação, o fecho regular coincide a 1 cêntimo em 87%, 99,9% e 99,3% dos minutos, mas o volume difere conforme
  a fonte (rácios 0,95, 1,08 e 1,37). No SPY o próprio volume, e portanto o CVD, depende de quem o reporta.

### 2.4 O delta estudado

- **«Auto» da TradingView num gráfico de 5 ou 15 minutos:** intrabars de 1 minuto com a regra da vela (+v se o fecho
  sobe face à abertura, −v se desce; se fica igual, compara com o fecho anterior; se ainda for igual, mantém o lado
  anterior), somados por barra do gráfico. O lado transita de barra para barra e de sessão para sessão ao longo de
  todo o fluxo de 1 minuto, como no contexto de `request.security_lower_tf`. Qualidade **média** no indicador.
- **Delta verdadeiro:** só na amostra do nível A, para medir o que o «Auto» perde (secção 5).
- O estudo reproduz o que a TradingView calcularia a partir das mesmas barras OHLCV. Não usa barras servidas pela
  própria TradingView (secção 16).

## 3. Plano pré-registado

O plano foi fixado e escrito no código (`study_es.py`) antes de calcular qualquer resultado. As escolhas que o plano
deixava em aberto foram também fixadas antes dos resultados e estão listadas em `results/es/results.md`, secção 9.

**Indicador.** Valores por omissão: N = 100, K = 20, M = 1000, c = 4, limiares de Z 2 e 3, ρmin 0,30, janela de
eventos de 15 minutos (k_e = 3 barras em 5 minutos, 1 em 15 minutos), vida da absorção de 60 minutos, z_F ≥ 2,
«travado» com |z_F| ≥ 3 e |z_P| ≤ 0,5. A divergência por pivots, desligada por omissão no indicador, foi ligada e
estudada com os seus valores por omissão (L = 5, R = 2, distância 5–60 barras, magnitude 0,5).

**Sinais.** As 14 condições de alerta do indicador. Os dois alertas de Z foram separados pela perna dominante (os
estados neutros da metodologia, secção 6.6), o que dá 16 classes. Cada sinal tem uma direcção s, e um retorno positivo
quer dizer que o preço continuou nessa direcção:

| Classe | Alerta do indicador | s | Retorno positivo significa |
|---|---|---|---|
| Z ≥ +2, liderado pelo preço | «Z ≥ +limiar», com \|P_K\| ≥ \|F_K\| e P_K > 0 | +1 | O preço continuou a subir |
| Z ≥ +2, liderado pelo fluxo | «Z ≥ +limiar», com \|F_K\| > \|P_K\| e F_K < 0 | −1 | O preço seguiu as vendas e caiu |
| Z ≤ −2, liderado pelo fluxo | «Z ≤ −limiar», com \|F_K\| > \|P_K\| e F_K > 0 | +1 | O preço seguiu as compras e subiu |
| Z ≤ −2, liderado pelo preço | «Z ≤ −limiar», com \|P_K\| ≥ \|F_K\| e P_K < 0 | −1 | O preço continuou a cair |
| Fluxo comprador absorvido | «Fluxo comprador absorvido» | +1 | O preço acabou por seguir as compras |
| Fluxo vendedor absorvido | «Fluxo vendedor absorvido» | −1 | O preço acabou por seguir as vendas |
| Preço travado sob compras | «Preço travado sob compras extremas» | +1 | Idem, compras |
| Preço travado sob vendas | «Preço travado sob vendas extremas» | −1 | Idem, vendas |
| Preço sem fluxo (subida) | «Preço sem fluxo (subida)» | +1 | O preço continuou a subir |
| Preço sem fluxo (queda) | «Preço sem fluxo (queda)» | −1 | O preço continuou a cair |
| Compras absorvidas → continuação | «Compras absorvidas → continuação (alta)» | +1 | O preço continuou a subir |
| Vendas absorvidas → continuação | «Vendas absorvidas → continuação (baixa)» | −1 | O preço continuou a cair |
| Vendas absorvidas → segurou | «Vendas absorvidas → segurou (alta)» | +1 | O preço continuou a subir |
| Compras absorvidas → segurou | «Compras absorvidas → segurou (baixa)» | −1 | O preço continuou a cair |
| Pivot: topo | «Divergência por pivots (topo)» | −1 | O preço reverteu e caiu |
| Pivot: fundo | «Divergência por pivots (fundo)» | +1 | O preço reverteu e subiu |

**Momento.** O sinal conta no fecho da barra em que é conhecido: os pivots na barra de confirmação, R barras depois
do pivot ([AUDITORIA.md](AUDITORIA.md), ponto (g)); as resoluções na barra da resolução. A entrada é a abertura da
barra seguinte (o primeiro negócio depois do fecho da barra do alerta, um limite superior sem latência) e a saída é o
fecho n barras depois da barra do sinal.

**Horizontes.** 5, 15, 30 e 60 minutos (1, 3, 6 e 12 barras em 5 minutos; 1, 2 e 4 em 15 minutos).

**Resultado.** Retorno com sinal em unidades de volatilidade:

    y = s · 10⁴ · ln(C[t+n] / O[t+1]) / (σr · √n)

com σr o desvio-padrão do retorno de uma barra, em bps, das N barras anteriores (o σ desfasado que o próprio
indicador usa na barra do sinal). Uma entrada em direcção aleatória tem esperança 0σ. Também: bps, pontos de ES, taxa
de acerto, mediana, MFE e MAE (excursões favorável e adversa máximas) e o movimento absoluto |y| (efeito de
volatilidade).

**Resultado primário.** y aos 30 minutos para cada uma das 16 classes, no ES de 5 minutos, amostra completa, com
correcção de Benjamini-Hochberg (BH) a 5% sobre estes 16 testes. Tudo o resto é secundário ou descritivo.

**Inferência.** Erros-padrão agrupados por dia de negociação (CR1, t com G − 1 graus de liberdade) e intervalos
*bootstrap* de 95% por blocos de dias (10 000 réplicas no resultado primário, 2 000 nos restantes).

**Controlos.**

1. *Gémeos condicionais.* Absorções contra choques de fluxo **confirmados** pelo preço (|z_F| ≥ 2 e o preço a
   acompanhar); preço sem fluxo contra choques de preço **com** fluxo (|z_P| ≥ 2 e fluxo no mesmo sentido). Os gémeos
   são construídos como os eventos do indicador: gate aberto, aglomerados por lado com período refractário de k_e
   observações, sem eventos com calibração fraca. Isolam a condição do CVD: o mesmo tamanho de choque, com e sem a
   discordância entre preço e fluxo.
2. *Controlos aleatórios emparelhados.* Para cada evento, a média das barras da mesma célula: ano, horário regular
   (08:30–15:15 CT) ou electrónico, bloco de 30 minutos do dia, tercil de σr dentro do ano, sinal e tercil do movimento
   recente do preço p_E (15 minutos).
3. *Linha de base incondicional:* todas as barras com os mesmos filtros.

**Restantes análises secundárias.** Estudo do gate (por omissão, sem gate, ρmin 0,20 e 0,40); custos de 0,325 pontos
por ida e volta (1 tick de derrapagem e cerca de 4 dólares de comissão) para a regra «entrar no sentido s» e para a
oposta; estabilidade (2008–2016 contra 2017–2026, sinal ano a ano, horário regular contra electrónico, tercis de σr);
calibração do Z. A robustez no MES e no SPY usa as mesmas definições (`study_robust.py`); os custos do MES e do SPY não
faziam parte do pré-registo.

## 4. Validação do motor contra o Pine

O estudo corre sobre uma tradução exacta do indicador para Python (`engine.py`): 1,28 milhões de barras em segundos,
quando o PineTS leva cerca de 8 minutos por ano de barras de 5 minutos. Antes de usar o motor, verificou-se que
reproduz o indicador real barra a barra:

- `validate_pine.py` envia o delta de cada barra pelo canal de dados dos testes do repositório
  (`tests/lib/channel.mjs`), que o entrega ao script Pine real da edição Standard a correr no PineTS 0.11.0, com plots
  só de observação acrescentados no fim. O canal quantiza Δ/V em 999 níveis (erro até 0,1% do volume da barra); o
  motor recebe exactamente o mesmo delta quantizado, por isso qualquer diferença seria do motor;
- compara barra a barra 28 sinalizadores (qualidade, gate, classes, aglomerados, resoluções, cruzamentos e alertas de
  Z, pivots), 30 séries contínuas (r, Δ, σr, σΔ, ρ, u_r, u_d, D, RMS, Z, z_F, z_P, pernas, …) e os conjuntos de barras
  de cada `alertcondition`.

| Fatia | Delta | Barras | Sessões | Barras com Z | máx. \|ΔZ\| | Sinalizadores diferentes |
|---|---|---|---|---|---|---|
| ES 5 min, 2008, todas as sessões (com rolagens) | 1 minuto | 70 911 | 259 | 70 692 | 4,7 × 10⁻¹⁰ | 0 |
| ES 5 min, 2019 | 1 minuto | 68 094 | 251 | 67 875 | 2,7 × 10⁻¹⁰ | 0 |
| ES 15 min, 2020 | 1 minuto | 22 912 | 253 | 22 693 | 2,6 × 10⁻¹⁰ | 0 |
| SPY 5 min, 2022 | 1 minuto | 47 885 | 251 | 47 666 | 2,4 × 10⁻¹⁰ | 0 |
| Ticks 2013, 1 min | verdadeiro | 19 992 | 15 | 19 773 | 3,2 × 10⁻¹⁰ | 0 |
| Ticks 2013, 1 min, outros parâmetros¹ | verdadeiro | 19 992 | 15 | 19 833 | 3,1 × 10⁻¹⁰ | 0 |
| Ticks 2013, 5 min | verdadeiro / 1S / 1 minuto | 4 074 (×3) | 15 | 3 855 | ≤ 2,0 × 10⁻¹⁰ | 0 |
| Ticks 2013, 5 min, dados degradados² | verdadeiro | 4 074 | 15 | 3 481 | 1,8 × 10⁻¹⁰ | 0 |
| Ticks 2013, 15 min | verdadeiro / 1 minuto | 1 358 (×2) | 15 | 1 139 | 2,1 × 10⁻¹⁰ | 0 |

¹ ρmin 0, N = 50, K = 10, M = 500, remoção da deriva ligada, janela de eventos de 5 minutos, vida de 30 minutos,
z_F ≥ 1,8, «travado» 2,5/0,8, limiar de Z 1,8, pivots L = 4, R = 3. ² 12 barras com volume 0, 6 com volume em falta e
35 sem intrabars, inseridas ao acaso.

Nas 12 fatias (268 798 barras), **todos os sinalizadores e todos os conjuntos de alertas são iguais** e as séries
contínuas coincidem até à precisão numérica (|ΔZ| ≤ 4,7 × 10⁻¹⁰).

- **Arredondamento.** O PineTS arredonda certos valores a 10 casas decimais. O motor reproduz esse arredondamento, que
  só decide empates exactos (somas que são matematicamente zero numa grelha de ticks). Nos históricos completos
  (ES, MES e SPY, 5 e 15 minutos, 3,6 milhões de barras), desligá-lo não muda nenhum sinalizador (máx. |ΔZ| 2,9 × 10⁻⁹).
- **Coerência interna.** No próprio estudo, uma nova execução do motor reproduz exactamente as 30 colunas de sinais
  dos ficheiros de características, e nenhum evento foi descartado por calibração fraca.
- **Limite.** O PineTS não é o compilador da TradingView, e as barras de entrada são as dos fornecedores, não as que a
  TradingView serve (secção 16).

## 5. Fidelidade do delta no ES

### 5.1 Amostra de ticks de 2013: «Auto» contra 1S contra o fluxo verdadeiro

Na amostra do nível A (15 sessões), o indicador correu com quatro deltas: o verdadeiro (referência), a regra da vela
em barras de 1 segundo (o que dão intrabars «1S»), a regra da vela em barras de 1 minuto (o «Auto» de um gráfico de
5 ou 15 minutos) e a regra do tick em cada negócio (o que daria «1T» sem cotações). Comparação com o delta verdadeiro,
gráfico de 5 minutos salvo indicação:

| Medida | 1 minuto («Auto») | 1S | Regra do tick |
|---|---|---|---|
| Correlação do delta por barra | 0,67 [0,61; 0,71] | 0,78 [0,73; 0,81] | 0,84 [0,81; 0,86] |
| Correlação parcial, dado o retorno da barra | 0,39 [0,30; 0,48] | 0,59 [0,50; 0,66] | 0,70 [0,67; 0,74] |
| Idem, só horário regular | 0,26 | 0,50 | 0,63 |
| Idem, gráfico de 15 minutos | 0,33 [0,20; 0,45] | 0,57 [0,44; 0,67] | 0,67 [0,63; 0,73] |
| Concordância de sinal do delta por barra | 74% | 80% | 82% |
| Correlação do caminho do CVD na sessão (mediana; âncora Globex) | 0,56 (mín. −0,46) | 0,93 | 0,92 |
| Idem, âncora no horário regular | 0,76 | 0,91 | 0,92 |
| Correlação do Z | 0,26 | 0,52 | 0,52 |
| Estados \|Z\| ≥ 2 do delta verdadeiro recuperados | 13% | 32% | 26% |
| Eventos de fluxo (absorvido, travado) recuperados, ±k_e barras | 2 de 15 | 4 de 15 | 5 de 15 |
| Todos os eventos recuperados, ±k_e barras | 27% | 39% | 39% |
| ρ̂ mediano (delta verdadeiro: 0,69) | 0,69 | 0,65 | 0,67 |
| P(\|Z\| ≥ 2) (delta verdadeiro: 6,98%) | 7,32% | 7,24% | 6,63% |

- A **perna do preço é a mesma**; muda a perna do fluxo. O que o delta de 1 minuto traz **para além do preço** (a
  correlação parcial) é pouco: 0,39 em 5 minutos e 0,17–0,26 no horário regular, contra 0,58–0,70 da regra do tick.
  É precisamente essa parte que define as absorções e o «preço sem fluxo».
- O **Z** e os **eventos** do «Auto» são, em grande parte, outros episódios: correlação do Z 0,26 e 2 de 15 eventos
  de fluxo recuperados. Os intervalos são largos (15 sessões, 15 eventos), mas a direcção é clara.
- O **1S** fica a meio caminho: muito melhor no caminho do CVD (0,93), ainda longe no Z (0,52).
- **ρ e o gate.** No gráfico de 5 minutos, o ρ̂ mediano do «Auto» (0,69) é igual ao do delta verdadeiro. No ES o gate
  fica aberto sobretudo porque a relação entre preço e fluxo é forte, e não por o delta de 1 minuto inflacionar ρ. A
  inflação existe no gráfico de 1 minuto (0,66 contra 0,57), onde o «Auto» é a própria vela.
- As frequências de |Z| ≥ 2 são parecidas entre deltas (6,6–7,3%): a calibração do Z não depende muito da fonte do
  delta, mas os episódios que marca dependem.

### 5.2 TopstepX 2026: o fosso entre 1 minuto e 1S continua

Sem delta verdadeiro, o 1S serve de referência. Usam-se só os minutos com todos os segundos presentes.

| Medida, «Auto» contra 1S | ES 2013 (ticks) | ES 2026 | MES 2026 |
|---|---|---|---|
| Correlação do delta por barra de 1 minuto | 0,65 | 0,36 (0,64 sem o minuto das 14:59 CT) | 0,73 |
| Idem, barras de 5 minutos | 0,66 | 0,34 | 0,73 |
| Volume do minuto das 14:59 CT | — | 6,6% | 1,8% |
| Correlação do Z, 5 minutos | 0,33 | 0,47 | 0,38 |
| Eventos de fluxo do 1S recuperados (±k_e), 5 minutos | 3 de 27 | 6 de 25 | 2 de 6 |

O desacordo entre o «Auto» e o 1S não diminuiu entre 2013 e 2026. No ES de 2026, uma só vela de 1 minuto, a do minuto
de liquidação, concentra 6,6% do volume da amostra e chega para baixar a correlação de 0,64 para 0,36: com a regra da
vela, todo esse volume vai para um só lado. A secção 13 mostra o que isto faz aos eventos.

**Consequência para o estudo.** Os resultados das secções 7 a 14 dizem respeito aos sinais do «Auto» (qualidade
média), que é o que a maioria dos utilizadores vê num gráfico de ES de 5 ou 15 minutos. Não se estendem a sinais
calculados com intrabars de 1S, com 1T ou com o fluxo verdadeiro: a amostra de ticks é curta demais para um estudo de
eventos (15 sessões, 15 eventos de fluxo em 5 minutos).

## 6. Calibração do Z no ES

Barras com Z e calibração completa (pelo menos 2N valores anteriores de D), como na dica do Z do indicador.

| Gráfico | Subamostra | Barras | P(\|Z\| ≥ 2) | P(\|Z\| ≥ 3) | RMS do Z | Gate aberto | ρ̂ mediano | P(ρ̂ < 0,30) |
|---|---|---|---|---|---|---|---|---|
| 5 min | completa | 1 279 902 | 6,47% | 1,43% | 1,02 | 98,1% | 0,71 | 1,9% |
| 5 min | 2008–2016 | 609 480 | 6,56% | 1,49% | 1,02 | 98,6% | 0,70 | 1,4% |
| 5 min | 2017–2026 | 670 422 | 6,39% | 1,38% | 1,02 | 97,6% | 0,73 | 2,4% |
| 5 min | horário regular | 372 112 | 8,86% | 2,29% | 1,16 | 99,8% | 0,74 | 0,2% |
| 5 min | horário electrónico | 907 790 | 5,49% | 1,08% | 0,96 | 97,4% | 0,70 | 2,6% |
| 15 min | completa | 426 809 | 5,75% | 0,98% | 1,01 | 99,1% | 0,66 | 0,9% |
| 15 min | horário regular | 123 993 | 9,39% | 1,85% | 1,21 | 99,5% | 0,68 | 0,5% |
| 15 min | horário electrónico | 302 816 | 4,26% | 0,63% | 0,92 | 98,9% | 0,65 | 1,1% |

Uma normal daria 4,55% e 0,27%.

- **Estável no tempo.** P(|Z| ≥ 2) ficou entre 6,1% e 6,8% em todos os anos de 2008 a 2026 em 5 minutos, e entre 5,4%
  e 6,5% em 15 minutos. O Z médio é praticamente 0. O nível é próximo do medido em BTCFDUSD (5,4–6,2%,
  [METODOLOGIA.md](METODOLOGIA.md), secção 6.8): o excesso face à normal é de cerca de 1,3–1,4 vezes a 2 e de 3,6 a
  5,3 vezes a 3.
- **Não está calibrado por hora do dia.** O RMS de D é calculado sobre as 23 horas da sessão Globex, por isso um
  |Z| ≥ 2 é cerca de 1,6 vezes mais frequente no horário regular do que no electrónico em 5 minutos (8,9% contra
  5,5%) e 2,2 vezes em 15 minutos (9,4% contra 4,3%). No horário regular, um |Z| ≥ 2 é uma leitura menos rara do que
  parece.
- **Blocos.** As barras com |Z| ≥ 2 formam 19 403 blocos contíguos em 5 minutos, que deram 11 525 alertas de Z
  (primeiro cruzamento com histerese): uma frequência de barras não é uma frequência de episódios independentes.
- **ρ e gate.** No ES com o «Auto», ρ̂ é alto e o gate quase nunca fecha (secção 9).

## 7. Resultado primário

Retorno com sinal aos 30 minutos, ES de 5 minutos, amostra completa. 16 testes, BH a 5%. Erro-padrão agrupado por dia;
IC por *bootstrap* de blocos de dias (10 000 réplicas). «Acerto ≠ 0» é a parte dos retornos não nulos que foram no
sentido do sinal (sem informação: 50%). MDE80 é o efeito verdadeiro que este teste detectaria com 80% de potência
(coluna acrescentada depois dos resultados).

| Classe | s | n | Dias | Média (σ) | IC 95% | p | q (BH) | Acerto ≠ 0 | bps | MDE80 (σ) |
|---|---|---|---|---|---|---|---|---|---|---|
| Z ≥ +2, liderado pelo preço | +1 | 1 114 | 988 | +0,001 | [−0,10; +0,10] | 0,980 | 1,00 | 50,1% | +0,29 | 0,14 |
| Z ≥ +2, liderado pelo fluxo | −1 | 4 516 | 3 031 | +0,007 | [−0,04; +0,05] | 0,755 | 1,00 | 48,2% | −0,02 | 0,07 |
| Z ≤ −2, liderado pelo fluxo | +1 | 4 447 | 3 033 | −0,036 | [−0,08; +0,01] | 0,135 | 1,00 | 50,4% | −0,30 | 0,07 |
| Z ≤ −2, liderado pelo preço | −1 | 1 318 | 1 138 | −0,017 | [−0,10; +0,07] | 0,704 | 1,00 | 46,2% | −1,09 | 0,12 |
| Fluxo comprador absorvido | +1 | 1 483 | 1 256 | +0,004 | [−0,09; +0,10] | 0,927 | 1,00 | 52,2% | +0,16 | 0,13 |
| Fluxo vendedor absorvido | −1 | 1 496 | 1 303 | +0,019 | [−0,08; +0,12] | 0,696 | 1,00 | 47,8% | +0,02 | 0,14 |
| Preço travado sob compras | +1 | 456 | 433 | +0,041 | [−0,11; +0,20] | 0,603 | 1,00 | 55,6% | +0,97 | 0,22 |
| Preço travado sob vendas | −1 | 489 | 469 | +0,006 | [−0,17; +0,18] | 0,949 | 1,00 | 48,2% | −0,29 | 0,25 |
| Preço sem fluxo (subida) | +1 | 626 | 590 | +0,018 | [−0,14; +0,17] | 0,817 | 1,00 | 52,9% | +0,44 | 0,22 |
| Preço sem fluxo (queda) | −1 | 674 | 618 | +0,030 | [−0,12; +0,18] | 0,699 | 1,00 | 50,3% | +0,31 | 0,21 |
| Compras absorvidas → continuação | +1 | 567 | 537 | −0,130 | [−0,28; +0,02] | 0,100 | 1,00 | 48,7% | −1,38 | 0,22 |
| Vendas absorvidas → continuação | −1 | 550 | 525 | −0,067 | [−0,23; +0,10] | 0,420 | 1,00 | 46,6% | −1,56 | 0,23 |
| Vendas absorvidas → segurou | +1 | 734 | 685 | +0,000 | [−0,13; +0,13] | 1,000 | 1,00 | 52,6% | −0,40 | 0,19 |
| Compras absorvidas → segurou | −1 | 687 | 638 | −0,096 | [−0,24; +0,05] | 0,196 | 1,00 | 47,7% | −0,77 | 0,21 |
| Pivot: topo | −1 | 5 954 | 3 404 | −0,010 | [−0,05; +0,03] | 0,593 | 1,00 | 48,8% | −0,24 | 0,05 |
| Pivot: fundo | +1 | 5 443 | 3 261 | +0,006 | [−0,03; +0,04] | 0,769 | 1,00 | 53,3% | −0,15 | 0,06 |

**0 de 16 classes sobrevivem à correcção; nenhuma tem p < 0,05 sem correcção.**

- **Taxa de acerto.** Entre os retornos não nulos, 46,2–55,6% foram no sentido do sinal. A taxa pré-registada, que
  conta como falhas os 3,3–6,6% de retornos exactamente nulos (grelha de ticks), foi 44,5–52,0%; nessa medida, uma
  entrada em direcção aleatória teria cerca de 47–48%.
- **Potência face aos custos.** Uma ida e volta de 30 minutos custa 0,13–0,22σ (secção 11). O estudo detectaria
  efeitos de 0,05–0,07σ nos estados de Z liderados pelo fluxo e nos pivots e de cerca de 0,13–0,14σ nas absorções:
  abaixo do custo, por isso um efeito negociável nestas classes fica, na prática, excluído. Nos estados de Z
  liderados pelo preço (0,12–0,14σ) e nas classes raras, «travado», preço sem fluxo e resoluções (0,19–0,25σ), o
  efeito mínimo detectável é da ordem do custo: um efeito apenas suficiente para pagar a ida e volta poderia ter
  escapado.
- **Latência.** Com a entrada 1 ou 2 minutos depois do fecho da barra do alerta (análise acrescentada depois da
  revisão), continua 0 de 16 (menor p 0,102 e 0,188).
- **Outros horizontes (secundário).** Em 5 minutos, 5 das 64 células classe × horizonte têm p < 0,05, quando o acaso
  daria cerca de 3,2; menor q 0,28. Em 15 minutos, 4 de 48 (cerca de 2,4 esperadas), menor q 0,30.
- **Gráfico de 15 minutos aos 30 minutos (secundário).** 0 de 16 depois da correcção. Os dois valores mais baixos são
  o fluxo comprador absorvido, +0,111σ (p 0,011), e o preço travado sob compras, +0,143σ (p 0,019), ambos com q 0,15.
  Não são um sinal de direcção: o fluxo vendedor absorvido foi −0,069σ no seu próprio sentido, ou seja, o preço subiu
  depois dos dois lados. A secção 13 localiza estas pistas no minuto de liquidação.

## 8. Gémeos e controlos: o CVD acrescenta alguma coisa ao preço?

### 8.1 Gémeos condicionais (30 minutos)

| Gráfico | Evento | Gémeo | n evento | n gémeo | Evento (σ) | Gémeo (σ) | Diferença (σ) | p | IC 95% |
|---|---|---|---|---|---|---|---|---|---|
| 5 min | Absorvido | Choque de fluxo confirmado | 2 979 | 27 443 | +0,012 | −0,003 | +0,015 | 0,68 | [−0,05; +0,08] |
| 5 min | Preço sem fluxo | Choque de preço com fluxo | 1 300 | 41 711 | +0,024 | −0,004 | +0,028 | 0,61 | [−0,08; +0,14] |
| 15 min | Absorvido | Choque de fluxo confirmado | 2 499 | 11 407 | +0,020 | +0,036 | −0,016 | 0,63 | [−0,08; +0,05] |
| 15 min | Preço sem fluxo | Choque de preço com fluxo | 471 | 22 335 | +0,089 | +0,020 | +0,068 | 0,42 | [−0,09; +0,24] |

A condição que dá nome ao evento, o preço não acompanhar o fluxo (ou o fluxo não acompanhar o preço), **não muda
nada mensurável** no retorno com sinal que se segue. Separado por lado, só o fluxo vendedor absorvido em 15 minutos
tem p < 0,05 (−0,097σ face ao gémeo, p 0,036, q 0,46). Nos horizontes curtos do gráfico de 5 minutos, o preço sem
fluxo continuou ligeiramente mais do que o choque de preço com fluxo: +0,136σ aos 5 minutos e +0,128σ aos 15 minutos
(p 0,017–0,018, q 0,11). É uma pista de curta duração, não confirmada, e abaixo do custo nesses horizontes
(0,33–0,53σ aos 5 minutos, 0,19–0,31σ aos 15).

### 8.2 Controlos aleatórios emparelhados (30 minutos)

Diferença entre o evento e a média das barras da sua célula (secção 3), com sinal. O erro-padrão inclui o erro de
amostragem das médias dos controlos. A coluna |σ| é o excesso de movimento absoluto do evento face aos controlos.

| Classe | 5 min: Δ (σ) | p | q | Excesso \|σ\| | p | 15 min: Δ (σ) | p | q | Excesso \|σ\| | p |
|---|---|---|---|---|---|---|---|---|---|---|
| Z ≥ +2, liderado pelo preço | −0,006 | 0,911 | 0,98 | +0,07 | 0,057 | +0,075 | 0,115 | 0,32 | +0,04 | 0,263 |
| Z ≥ +2, liderado pelo fluxo | +0,008 | 0,728 | 0,98 | +0,07 | < 0,001 | +0,073 | 0,167 | 0,34 | +0,09 | 0,011 |
| Z ≤ −2, liderado pelo fluxo | −0,040 | 0,086 | 0,85 | −0,01 | 0,439 | −0,006 | 0,903 | 0,96 | +0,09 | 0,019 |
| Z ≤ −2, liderado pelo preço | −0,011 | 0,807 | 0,98 | +0,16 | < 0,001 | −0,069 | 0,175 | 0,34 | +0,22 | < 0,001 |
| Fluxo comprador absorvido | +0,003 | 0,956 | 0,98 | +0,13 | < 0,001 | +0,077 | 0,123 | 0,32 | +0,00 | 0,968 |
| Fluxo vendedor absorvido | +0,019 | 0,705 | 0,98 | +0,14 | < 0,001 | −0,025 | 0,602 | 0,72 | +0,02 | 0,485 |
| Preço travado sob compras | +0,025 | 0,760 | 0,98 | +0,03 | 0,570 | +0,139 | 0,049 | 0,32 | −0,04 | 0,378 |
| Preço travado sob vendas | +0,008 | 0,934 | 0,98 | +0,18 | 0,002 | +0,048 | 0,533 | 0,69 | +0,05 | 0,318 |
| Preço sem fluxo (subida) | +0,010 | 0,891 | 0,98 | +0,14 | 0,009 | +0,000 | 0,998 | 1,00 | +0,21 | 0,014 |
| Preço sem fluxo (queda) | +0,026 | 0,733 | 0,98 | +0,13 | 0,009 | +0,159 | 0,190 | 0,34 | +0,26 | 0,001 |
| Compras absorvidas → continuação | −0,131 | 0,095 | 0,85 | +0,10 | 0,043 | +0,142 | 0,042 | 0,32 | +0,01 | 0,849 |
| Vendas absorvidas → continuação | −0,071 | 0,382 | 0,98 | +0,11 | 0,051 | +0,039 | 0,657 | 0,74 | +0,05 | 0,433 |
| Vendas absorvidas → segurou | −0,001 | 0,984 | 0,98 | +0,07 | 0,090 | −0,073 | 0,313 | 0,51 | +0,00 | 0,937 |
| Compras absorvidas → segurou | −0,106 | 0,144 | 0,87 | +0,09 | 0,040 | −0,072 | 0,376 | 0,52 | +0,06 | 0,244 |
| Pivot: topo | −0,002 | 0,894 | 0,98 | +0,01 | 0,448 | +0,059 | 0,096 | 0,32 | +0,05 | 0,038 |
| Pivot: fundo | −0,004 | 0,859 | 0,98 | +0,06 | < 0,001 | +0,038 | 0,338 | 0,51 | +0,11 | < 0,001 |
| Gémeo: choques de fluxo confirmados | −0,007 | 0,427 | 0,98 | +0,08 | < 0,001 | +0,034 | 0,057 | 0,32 | +0,17 | < 0,001 |
| Gémeo: choques de preço com fluxo | −0,006 | 0,459 | 0,98 | +0,09 | < 0,001 | +0,022 | 0,071 | 0,32 | +0,16 | < 0,001 |

**Direcção: 0 de 18 diferenças sobrevivem à correcção em cada gráfico.** Em 5 minutos nenhuma tem p < 0,05 (menor
0,086). Em 15 minutos, duas têm (travado sob compras e compras absorvidas → continuação, q 0,32 para ambas).

Dois emparelhamentos alternativos, acrescentados depois da revisão, dão o mesmo resultado:

- **Pela perna de preço de K barras** (P_K, a que define as classes de Z; as células pré-registadas usam o movimento de
  15 minutos p_E). As classes de Z em 5 minutos ficam em +0,010, +0,017, −0,039 e −0,009σ (p ≥ 0,10). 0 de 18 nos dois
  gráficos.
- **Pela barra exacta do dia**, em vez do bloco de 30 minutos. 0 de 18 nos dois gráficos (menor q 0,84 em 5 minutos e
  0,28 em 15).

### 8.3 O número mais forte destas tabelas: uma pequena reversão depois de choques grandes

Aos **5 minutos** no gráfico de 5 minutos, os choques de fluxo confirmados e os choques de preço com fluxo ficaram
−0,042σ e −0,041σ abaixo dos seus controlos emparelhados (n ≈ 27 500 e 41 800, p ≤ 0,0004). São os únicos valores que
passam a correcção de BH dentro da tabela de controlos (q 0,013–0,014), uma família secundária: é uma **marca, não uma
conclusão**. É uma reversão minúscula depois de movimentos grandes em geral, cerca de um décimo do custo a 5 minutos
(0,33–0,53σ), e pertence aos dois conjuntos de choques, não a um sinal do indicador. É coerente com a reversão parcial
da pressão de preço confirmada pelo fluxo referida na literatura ([METODOLOGIA.md](METODOLOGIA.md), secção 9.1). Em
15 minutos os mesmos conjuntos derivam ligeiramente no sentido contrário (+0,02 a +0,03σ aos 30 minutos, p 0,06–0,07).

### 8.4 Volatilidade: os eventos marcam movimentos maiores, sem sentido

- **5 minutos, 30 minutos.** 13 das 16 classes têm um excesso de movimento absoluto de +0,06σ a +0,18σ sobre os
  controlos, 10 com p < 0,05. Os Z ≤ −2 liderados pelo fluxo, os travados sob compras e os topos de pivot ficam perto
  de zero. Os dois conjuntos de gémeos também têm excesso (+0,08σ e +0,09σ, p < 0,001).
- **15 minutos.** As absorções e os travados não têm excesso (+0,001, +0,022, −0,042 e +0,053σ; p ≥ 0,32).
- **A condição do CVD não acrescenta de forma consistente.** Diferença dos excessos emparelhados, absorvido menos
  choque de fluxo confirmado: +0,061σ em 5 minutos (p 0,012) e −0,163σ em 15 minutos (p < 0,001), sinais opostos.
  Preço sem fluxo menos choque de preço com fluxo: +0,041σ (p 0,27) e +0,072σ (p 0,22). Esta comparação foi
  acrescentada depois da revisão.

Choques grandes de fluxo ou de preço são seguidos de movimentos um pouco maiores, o que concorda com a literatura (o
desequilíbrio relaciona-se com a volatilidade, não com a direcção; [METODOLOGIA.md](METODOLOGIA.md), secção 9.1). Os
dados não mostram que as condições do CVD acrescentem a isso de forma consistente, e em 15 minutos o rótulo
«absorvido» marca movimentos menores do que um choque confirmado.

## 9. Estudo do gate

As variantes foram obtidas com o mesmo motor nas mesmas barras, mudando só o gate. O Z, z_F, z_P e a sua calibração
não dependem do gate; mudam as classes, os aglomerados, as resoluções e os alertas de Z.

| Variante | Gate aberto, 5 min | Gate aberto, 15 min | Sinais, 5 min | BH 30 min, 5 min | BH 30 min, 15 min |
|---|---|---|---|---|---|
| Por omissão (ρmin 0,30) | 98,1% | 99,1% | 31 030 | 0 de 16 | 0 de 16 |
| Sem gate (só qualidade) | 100% | 100% | 31 189 | 0 de 16 | 0 de 16 |
| ρmin 0,20 | 99,3% | 99,7% | 31 137 | 0 de 16 | 0 de 16 |
| ρmin 0,40 | 95,6% | 96,8% | 30 714 | 0 de 16 | 0 de 16 |

- Desligar o gate acrescenta no máximo 27 eventos a uma classe em 5 minutos; ρmin 0,40 retira no máximo 59. Os
  subconjuntos acrescentados ou retirados têm de 1 a 59 eventos: nada interpretável (uma célula tem p 0,013, com
  n = 2).
- **Ponto (d) da auditoria:** não se decide no ES com o «Auto», porque o gate quase nunca fecha (P(ρ̂ < 0,30) de 1,9%
  e 0,9%). No SPY com horário alargado o gate fecha mais vezes (aberto em 86% das barras, ρ̂ mediano 0,55; secção 14),
  mas o estudo de robustez não variou o gate.

## 10. MFE e MAE

Excursões favorável (MFE) e adversa (MAE) máximas desde a entrada até aos 30 minutos, médias, em σ e em pontos de ES.
São descritivas: não há teste sobre a diferença.

| Classe | MFE 5 min (σ) | MAE 5 min (σ) | MFE − MAE 5 min | MFE 5 min (pt) | MAE 5 min (pt) | MFE − MAE 15 min (σ) |
|---|---|---|---|---|---|---|
| Z ≥ +2, liderado pelo preço | 1,07 | 1,10 | −0,03 | 3,80 | 3,99 | +0,06 |
| Z ≥ +2, liderado pelo fluxo | 1,24 | 1,18 | +0,06 | 3,73 | 3,63 | +0,14 |
| Z ≤ −2, liderado pelo fluxo | 1,09 | 1,16 | −0,07 | 3,25 | 3,31 | −0,07 |
| Z ≤ −2, liderado pelo preço | 1,28 | 1,16 | +0,12 | 4,74 | 4,38 | +0,07 |
| Fluxo comprador absorvido | 1,30 | 1,39 | −0,09 | 3,53 | 3,52 | +0,02 |
| Fluxo vendedor absorvido | 1,38 | 1,29 | +0,10 | 3,57 | 3,37 | +0,00 |
| Preço travado sob compras | 1,25 | 1,30 | −0,05 | 3,21 | 3,42 | +0,04 |
| Preço travado sob vendas | 1,45 | 1,35 | +0,11 | 3,77 | 3,76 | +0,07 |
| Preço sem fluxo (subida) | 1,45 | 1,45 | −0,00 | 3,70 | 3,71 | −0,04 |
| Preço sem fluxo (queda) | 1,61 | 1,39 | +0,23 | 4,04 | 3,61 | +0,32 |
| Compras absorvidas → continuação | 1,23 | 1,42 | −0,19 | 3,24 | 3,78 | +0,15 |
| Vendas absorvidas → continuação | 1,46 | 1,41 | +0,05 | 3,69 | 4,02 | +0,27 |
| Vendas absorvidas → segurou | 1,27 | 1,34 | −0,07 | 3,14 | 3,38 | −0,02 |
| Compras absorvidas → segurou | 1,47 | 1,45 | +0,03 | 3,64 | 3,64 | +0,10 |
| Pivot: topo | 1,03 | 1,01 | +0,03 | 3,43 | 3,33 | +0,11 |
| Pivot: fundo | 1,03 | 1,08 | −0,05 | 3,37 | 3,59 | +0,01 |
| *Linha de base (todas as barras, compra)* | *0,80* | *0,82* | *−0,02* | *2,69* | *2,76* | *−0,03* |

- Depois de um sinal, as duas excursões são **maiores do que numa barra qualquer**: cerca de 1,2 a 2 vezes a linha de
  base, ou 3,1–4,7 pontos favoráveis e 3,3–4,4 adversos em 30 minutos, em média. É o mesmo efeito de volatilidade da
  secção 8.4.
- São **quase simétricas**: MFE − MAE entre −0,19σ e +0,23σ em 5 minutos, coerente com médias com sinal perto de zero.
  Não há uma assimetria que um *stop* e um alvo fixos pudessem explorar.

## 11. Custos

Custo pré-registado: **0,325 pontos por ida e volta (16,25 dólares por contrato)**, 1 tick de derrapagem e cerca de
4 dólares de comissão. É um **limite inferior**: vale para 1 contrato com liquidez normal no horário regular, e é
optimista onde estes sinais se concentram (abertura das 08:30 CT, liquidação das 15:00 CT, barras de dados económicos
das 07:30 e 09:00 CT, reabertura das 17:00 CT), no livro fino da noite em 2008–2012 e nos períodos de tensão de 2008 e
2020. Acrescentou-se, depois da revisão, um custo de esforço de 0,575 pontos (2 ticks). Não houve filtro de notícias nem
de reuniões da Fed. Em unidades de volatilidade, o custo de uma ida e volta de 30 minutos é 0,13–0,22σ.

Regra ingénua: «entrar no sentido s e sair ao fim do horizonte», todos os sinais, mesmo sobrepostos; regra oposta:
entrar contra s, com o mesmo custo. Gráfico de 5 minutos, 30 minutos:

| Classe | Bruto (pt) | Líquido (pt) | Líquido, 2 ticks | Oposta, líquido | Oposta, 2 ticks | Líquido (σ) |
|---|---|---|---|---|---|---|
| Z ≥ +2, liderado pelo preço | −0,04 | −0,37 | −0,62 | −0,28 | −0,53 | −0,142 |
| Z ≥ +2, liderado pelo fluxo | −0,04 | −0,37 | −0,62 | −0,28 | −0,53 | −0,167 |
| Z ≤ −2, liderado pelo fluxo | +0,03 | −0,29 | −0,54 | −0,36 | −0,61 | −0,216 |
| Z ≤ −2, liderado pelo preço | −0,18 | −0,50 | −0,75 | −0,15 | −0,40 | −0,151 |
| Fluxo comprador absorvido | +0,23 | −0,10 | −0,35 | −0,55 | −0,80 | −0,201 |
| Fluxo vendedor absorvido | −0,09 | −0,41 | −0,66 | −0,24 | −0,49 | −0,179 |
| Preço travado sob compras | +0,29 | −0,04 | −0,29 | −0,61 | −0,86 | −0,163 |
| Preço travado sob vendas | −0,17 | −0,49 | −0,74 | −0,16 | −0,41 | −0,185 |
| Preço sem fluxo (subida) | +0,17 | −0,15 | −0,40 | −0,50 | −0,75 | −0,187 |
| Preço sem fluxo (queda) | −0,05 | −0,38 | −0,63 | −0,27 | −0,52 | −0,178 |
| Compras absorvidas → continuação | −0,49 | −0,81 | −1,06 | +0,16 | −0,09 | −0,332 |
| Vendas absorvidas → continuação | −0,57 | −0,89 | −1,14 | +0,24 | −0,01 | −0,265 |
| Vendas absorvidas → segurou | +0,01 | −0,32 | −0,57 | −0,33 | −0,58 | −0,200 |
| Compras absorvidas → segurou | −0,41 | −0,74 | −0,99 | +0,09 | −0,16 | −0,313 |
| Pivot: topo | −0,06 | −0,38 | −0,63 | −0,27 | −0,52 | −0,168 |
| Pivot: fundo | −0,03 | −0,36 | −0,61 | −0,29 | −0,54 | −0,155 |

- **5 minutos, 30 minutos.** As 16 regras «no sentido s» perdem dinheiro (−0,04 a −0,89 pontos por operação). Três
  regras opostas ficam positivas, ir contra as duas continuações e contra «compras absorvidas → segurou» (+0,09 a
  +0,24 pontos), mas nenhuma é significativa (p bilateral ≥ 0,42) e as três passam a negativas com 2 ticks.
- **15 minutos, 30 minutos.** Quatro regras «no sentido s» e duas opostas ficam ligeiramente positivas (até +0,28
  pontos), nenhuma significativa (melhor p unilateral 0,20); em σ, todas ficam em +0,002σ ou abaixo.
- **Todas as 224 células** (16 classes × horizontes × duas direcções, dois gráficos): no teste unilateral de
  «líquido > 0», o menor p é 0,028 e todos os q de BH são 1,000. Nenhuma regra ingénua tem expectativa líquida
  positiva demonstrável.
- **A melhor célula isolada** é ir no sentido do «preço travado sob vendas» durante 60 minutos no gráfico de
  15 minutos: +1,05 pontos líquidos, p unilateral 0,028, n = 385. Não sobrevive a nenhuma correcção; em σ vale só
  +0,03σ (p 0,66), porque os pontos pesam mais os anos recentes, de preço mais alto; e não é a mesma população da célula
  de 30 minutos (n = 543, −0,07 pontos). Estes eventos ficam quase todos nas barras das 14:45 e 15:00 CT, cujas janelas
  de 60 minutos ultrapassam o fim da sessão de forma desigual consoante a época: são válidas em 81% dos casos em
  2008–2012, 24% em 2013–2020 e 84% em 2021–2026.

## 12. Estabilidade

ES de 5 minutos, 30 minutos: média em σ (p) por subamostra e número de anos com média positiva.

| Classe | 2008–2016 | 2017–2026 | Horário regular | Horário electrónico | σr baixo | σr alto | Anos + | p (sinal) |
|---|---|---|---|---|---|---|---|---|
| Z ≥ +2, liderado pelo preço | +0,02 (0,85) | −0,01 (0,92) | −0,02 (0,80) | +0,02 (0,82) | +0,03 (0,68) | −0,07 (0,48) | 7/19 | 0,36 |
| Z ≥ +2, liderado pelo fluxo | −0,01 (0,71) | +0,03 (0,45) | +0,04 (0,35) | −0,01 (0,74) | +0,01 (0,83) | −0,01 (0,85) | 10/19 | 1,00 |
| Z ≤ −2, liderado pelo fluxo | −0,06 (0,043) | −0,01 (0,83) | +0,05 (0,24) | −0,08 (0,006) | −0,08 (0,041) | −0,01 (0,78) | 7/19 | 0,36 |
| Z ≤ −2, liderado pelo preço | −0,04 (0,61) | −0,01 (0,92) | −0,02 (0,77) | −0,01 (0,81) | +0,06 (0,51) | −0,02 (0,74) | 9/19 | 1,00 |
| Fluxo comprador absorvido | −0,08 (0,21) | +0,09 (0,22) | +0,05 (0,48) | −0,05 (0,46) | +0,02 (0,79) | +0,07 (0,43) | 10/19 | 1,00 |
| Fluxo vendedor absorvido | +0,01 (0,88) | +0,03 (0,69) | −0,03 (0,63) | +0,08 (0,26) | +0,05 (0,49) | −0,05 (0,57) | 9/19 | 1,00 |
| Preço travado sob compras | +0,02 (0,85) | +0,07 (0,60) | +0,13 (0,23) | −0,07 (0,54) | −0,07 (0,54) | +0,18 (0,25) | 9/19 | 1,00 |
| Preço travado sob vendas | +0,01 (0,91) | −0,00 (0,99) | −0,08 (0,50) | +0,14 (0,30) | +0,04 (0,77) | −0,03 (0,87) | 9/19 | 1,00 |
| Preço sem fluxo (subida) | +0,00 (0,98) | +0,03 (0,76) | +0,03 (0,80) | +0,01 (0,95) | +0,04 (0,75) | +0,24 (0,15) | 7/19 | 0,36 |
| Preço sem fluxo (queda) | +0,12 (0,22) | −0,07 (0,54) | +0,04 (0,74) | +0,02 (0,85) | +0,04 (0,69) | −0,03 (0,88) | 9/19 | 1,00 |
| Compras absorvidas → continuação | −0,10 (0,40) | −0,16 (0,14) | −0,13 (0,21) | −0,13 (0,29) | −0,10 (0,41) | −0,06 (0,67) | 6/19 | 0,17 |
| Vendas absorvidas → continuação | −0,20 (0,069) | +0,07 (0,60) | −0,11 (0,39) | −0,03 (0,80) | −0,04 (0,77) | −0,16 (0,25) | 7/19 | 0,36 |
| Vendas absorvidas → segurou | −0,04 (0,62) | +0,05 (0,61) | −0,08 (0,44) | +0,08 (0,37) | +0,00 (0,98) | −0,28 (0,038) | 9/19 | 1,00 |
| Compras absorvidas → segurou | −0,07 (0,51) | −0,13 (0,24) | +0,08 (0,50) | −0,25 (0,005) | −0,16 (0,16) | −0,08 (0,54) | 8/19 | 0,65 |
| Pivot: topo | −0,05 (0,057) | +0,02 (0,44) | −0,01 (0,85) | −0,01 (0,58) | +0,05 (0,12) | −0,01 (0,73) | 8/19 | 0,65 |
| Pivot: fundo | −0,01 (0,79) | +0,02 (0,55) | +0,01 (0,82) | +0,00 (0,86) | +0,03 (0,48) | −0,03 (0,29) | 11/19 | 0,65 |

- **Metades.** As duas metades (2008–2016 e 2017–2026) são nulas.
- **Ano a ano** o sinal da média é próximo de uma moeda ao ar: 6 a 11 anos positivos em 19 no gráfico de 5 minutos
  (teste do sinal, p ≥ 0,17) e 7 a 14 em 15 minutos (p ≥ 0,06).
- **Horário e volatilidade.** Algumas células têm p < 0,01, mas nenhuma sobrevive à correcção dentro da tabela (q ≥ 0,25
  em 5 minutos, ≥ 0,15 em 15). Em 5 minutos: Z ≤ −2 liderado pelo fluxo no horário electrónico, −0,082σ (também
  −0,082σ contra os controlos, p 0,006), e «compras absorvidas → segurou» no electrónico, −0,25σ. Em 15 minutos: fluxo
  comprador absorvido em 2008–2016 (+0,20σ) e no horário regular (+0,13σ), travado sob compras no horário regular
  (+0,17σ) e «compras absorvidas → segurou» no tercil alto de σr (−0,33σ). As pistas de 15 minutos no horário regular
  explicam-se, em grande parte, pela secção 13.

## 13. Observação post hoc: o minuto de liquidação das 14:59 CT

Esta secção não fazia parte do plano: foi acrescentada depois de ver os resultados e depois da revisão externa. É uma
**hipótese** com evidência, não um resultado confirmatório.

**Onde caem os eventos.** As absorções e os «travados» concentram-se no fecho e na abertura do mercado à vista. Em
15 minutos, 58% das absorções e 67% dos «travados» caem nas barras das 14:45 e das 15:00 CT; só a barra das 14:45
tem 564 das 1 267 compras absorvidas e 519 das 1 286 vendas absorvidas. Em 5 minutos, as barras mais frequentes são
as das 15:00, 08:30 e 15:05 CT.

**Mecanismo provável.** O minuto das 14:59 CT é a janela de liquidação diária dos futuros de índices do CME e coincide
com o leilão de fecho da NYSE. A sua parte do volume da sessão cresceu de 1,3% em 2008 para 2,9–4,2% a partir de 2017.
Com a regra da vela do «Auto», **todo** o volume dessa vela de 1 minuto vai para um só lado, decidido pelo fecho face à
abertura. Uma janela de eventos que contenha esse minuto recebe um |Δ| grande, com o lado decidido por uma única vela,
e pouco movimento de preço: um rótulo de absorção ou de «travado» que é, pelo menos em parte, um artefacto do
estimador do delta.

- A janela contém o minuto das 14:59 em 40–49% das absorções e «travados» de 15 minutos e em 17–20% dos de 5 minutos.
- Nesses eventos, o lado coincide com o sinal da vela das 14:59 em **99,6–100%** dos casos.
- A fidelidade (secção 5.2) aponta no mesmo sentido: no ES de 2026, esse minuto tem 6,6% do volume e baixa a
  correlação entre o «Auto» e o 1S de 0,64 para 0,36.

**O que isto faz aos resultados (15 minutos, 30 minutos):**

| Classe | Subconjunto | n | Média (σ) | p | Contra controlos da mesma barra do dia (σ) | p |
|---|---|---|---|---|---|---|
| Fluxo comprador absorvido | todos | 1 240 | +0,111 | 0,011 | +0,076 | 0,22 |
| Fluxo comprador absorvido | janela com as 14:59 | 555 | +0,133 | 0,003 | +0,012 | 0,86 |
| Fluxo comprador absorvido | janela sem as 14:59 | 685 | +0,094 | 0,19 | +0,121 | 0,19 |
| Preço travado sob compras | todos | 526 | +0,143 | 0,019 | +0,087 | 0,37 |
| Preço travado sob compras | janela com as 14:59 | 263 | +0,189 | 0,003 | −0,035 | 0,79 |
| Preço travado sob compras | janela sem as 14:59 | 263 | +0,096 | 0,35 | +0,151 | 0,25 |
| Fluxo vendedor absorvido | janela com as 14:59 | 511 | −0,073 | 0,13 | +0,011 | 0,88 |

- A parte significativa das pistas de 15 minutos está nos eventos da janela de liquidação e **desaparece contra
  controlos da mesma barra do dia**: o que se mede é a deriva do preço depois do fecho, não informação do fluxo. Sem a
  janela de liquidação, as estimativas são parecidas, mas com metade dos eventos e sem significância; não se pode
  dizer de onde vem todo o efeito, só que a parte significativa é explicada pela deriva depois do fecho.
- O preço subiu depois dos dois lados: as vendas absorvidas na janela de liquidação ficaram −0,073σ no seu próprio
  sentido em 15 minutos e −0,117σ (p 0,005) em 5 minutos.
- A deriva incondicional confirma-o: aos 30 minutos, +0,051σ (p 0,002) a partir da barra de 15 minutos das 14:45 e
  +0,027σ (p 0,016) a partir da das 15:00, contra +0,027σ (p 0,28) a partir da das 14:30. O bloco de 30 minutos do
  emparelhamento mistura estas barras; por isso o controlo da barra exacta é o teste mais fino aqui.
- Em 5 minutos, fora da janela de liquidação, as absorções e os «travados» são nulos (|média| ≤ 0,045σ, p ≥ 0,44).

**Outras observações post hoc.**

- *Resoluções depois da pausa diária.* A vida de uma absorção pendente conta-se em barras, por isso atravessa a pausa
  diária e os fins de semana, e o salto da reabertura das 17:00 CT pode disparar o alerta de «continuação» ou de
  «segurou». Isso abrange 78 de 2 636 alertas de resolução em 5 minutos (3,0%) e 146 de 1 758 em 15 minutos (8,3%).
  Excluí-los não muda nada de relevante.
- *Fecho da sessão por época.* As janelas que começam perto do fecho atravessam, até 2021, a pausa das 15:15–15:30 CT
  (até 28% delas em 15 minutos), e as de 60 minutos ultrapassam o fim da sessão de forma desigual por época (secção 11).

## 14. Robustez: MES e SPY

As mesmas definições pré-registadas, com o mesmo código (`study_robust.py`), noutros instrumentos do S&P 500. O
resultado primário é corrigido com BH dentro de cada conjunto.

| Conjunto | Período | Sessões | Sinais com janela | BH (16) | Menor p (classe) | Menor q | P(\|Z\| ≥ 2) | Gate aberto | ρ̂ mediano |
|---|---|---|---|---|---|---|---|---|---|
| ES 5 min (referência) | 2008–2026 | 4 688 | 30 555 | 0 | 0,100 (compras absorvidas → continuação) | 0,98 | 6,47% | 98,1% | 0,71 |
| ES 5 min, sessões do MES | 2021–2026 | 1 359 | 9 074 | 0 | 0,078 (fluxo comprador absorvido) | 0,62 | 6,36% | 97,4% | 0,74 |
| MES 5 min | 2021–2026 | 1 357 | 8 285 | 0 | 0,156 (fluxo comprador absorvido) | 0,93 | 6,29% | 99,8% | 0,79 |
| SPY 5 min, só horário regular | 2000–2026 | 6 583 | 15 217 | 0 | 0,003 (vendas absorvidas → continuação) | 0,055 | 5,69% | 97,1% | 0,69 |
| SPY 5 min, regular e alargado | 2000–2026 | 6 583 | 34 640 | 0 | 0,022 (vendas absorvidas → continuação) | 0,35 | 5,98% | 86,2% | 0,55 |

O código de robustez fecha as janelas pelo relógio e não pelo número de barras, por isso a contagem do ES difere numa
unidade da secção 7.

- **0 de 16 em todos os conjuntos.** Os gémeos também ficam nulos aos 30 minutos (absorvido contra choque confirmado:
  +0,11σ no MES, p 0,25; −0,05σ e −0,02σ no SPY, p ≥ 0,26). Os custos aproximados do MES (0,45 pontos) e do SPY
  (0,015 dólares por acção) não fazem parte do pré-registo; com eles, os resultados líquidos positivos são isolados e
  de classes sem efeito bruto significativo.
- **Os mesmos minutos, outros eventos.** Nas barras comuns, o Z do ES e o do MES correlacionam 0,73 (z_F 0,90), e as
  absorções coincidem pouco: índice de Jaccard de 0,19–0,21 na mesma barra e de 0,24–0,27 com ±3 barras. Entre o ES e
  o SPY no horário regular, o Z correlaciona 0,30 e o Jaccard das absorções é 0,04–0,05 na mesma barra e 0,07 com
  ±3 barras. O mesmo índice, no mesmo minuto, dá rótulos muito
  diferentes conforme o mercado e o volume que cada um reporta.
- **Uma pista a testar, não um resultado.** As resoluções «continuação» foram seguidas, em média, de uma reversão no ES
  (−0,130σ e −0,067σ) e no SPY (−0,222σ, p 0,003, q 0,055 no horário regular; −0,133σ, p 0,022, com horário
  alargado), mas não no MES (+0,24σ e +0,11σ, n.s.). Nenhum conjunto passa a correcção, e o ES e o SPY são o mesmo
  activo subjacente, não réplicas independentes. Esta hipótese só pode ser confirmada em dados novos (secção 17).

## 15. Desvios ao plano

Todos registados também em `research/sp500/results/es/results.md` (secção 10) e em `CHANGELOG.md`.

1. **Procedimento do estudo do gate.** As variantes foram obtidas reexecutando o motor validado com outro gate, e não
   com código separado que rederivasse as classes a partir das séries guardadas. Por construção dá o mesmo resultado; a
   execução por omissão reproduz exactamente as colunas de sinais guardadas.
2. **Controlos emparelhados.** Em vez de sortear um número finito de barras de controlo por evento, usou-se a média de
   todas as barras da célula (a esperança de um sorteio), o que elimina o ruído de Monte Carlo. Eventos com menos de 5
   barras de controlo na célula ficam fora dessa comparação (0,1–9% dos eventos, contagens nas tabelas).
3. **Correcções depois da revisão externa** (feitas depois de ver os resultados; o plano, os parâmetros e a família
   primária não mudaram, e os números primários ficaram iguais):
   - nos controlos emparelhados, todos os eventos da mesma classe passaram a ser retirados das células (antes, só o
     próprio evento); o tercil de σr passou a ser calculado dentro de cada ano; o erro-padrão passou a incluir o erro
     de amostragem das médias dos controlos. O efeito foi pequeno e continua 0 de 18; a única mudança de interpretação
     é que a reversão a 5 minutos dos choques grandes (secção 8.3) passou a ter q 0,013–0,014 (antes 0,056);
   - nas tabelas de custos, as colunas de p tinham nomes de teste unilateral mas eram testes bilaterais de «líquido
     = 0»: foram renomeadas e acrescentou-se o teste unilateral com BH sobre as 224 células.
4. **Acrescentado depois dos resultados, descritivo ou de sensibilidade** (nada disto entra na família primária): a
   distribuição horária dos eventos; a coluna MDE80; a taxa de acerto entre retornos não nulos; a comparação do
   movimento absoluto entre eventos e gémeos (secção 8.4); os emparelhamentos por P_K e pela barra exacta; a análise do
   minuto de liquidação; a latência de 1 e 2 minutos; as resoluções de absorções nascidas na sessão anterior; a
   sobrevivência das janelas por época; o custo de esforço de 2 ticks.
5. **Fora do pré-registo:** os custos do MES e do SPY; o estudo de fidelidade (descritivo por natureza).

## 16. Limitações

1. **Só o delta «Auto» (qualidade média).** Os sinais com intrabars de 1S, 1T ou com o fluxo verdadeiro não foram
   testados: a amostra de ticks tem 15 sessões e a de 1 segundo cobre parte de 28 sessões. A secção 5 mostra que esses
   sinais seriam, em boa parte, outros episódios.
2. **Não são dados servidos pela TradingView.** O estudo reproduz o cálculo do indicador sobre barras de fornecedores. O
   volume em falta contra zero, a cobertura de intrabars por plano, as diferenças entre histórico e tempo real e o
   footprint da TradingView continuam por verificar.
3. **Semanas de rolagem excluídas.** Um utilizador em ES1! mantém essas sessões; nelas σΔ, ρ e o RMS de D diferem
   durante algumas sessões. O resultado nulo cobre as semanas sem rolagem.
4. **Só os valores por omissão.** Não houve análise de sensibilidade a N, K, M, c, limiares ou janela de eventos. Um
   resultado nulo com os valores por omissão não prova que nenhuma combinação funcione, e procurar essa combinação
   nestes dados seria sobreajustamento.
5. **Custos e execução.** O custo é um limite inferior; a entrada principal não tem latência; não há posição na fila,
   preenchimentos parciais nem impacto de tamanho; não há filtro de notícias.
6. **Um só activo subjacente.** O MES e o SPY não são réplicas independentes do ES. Não foram estudados outros mercados
   (NQ, acções individuais, perpétuos cripto, FX).
7. **Testes múltiplos fora da família primária.** Cada tabela secundária é corrigida dentro de si mesma. Com tantas
   tabelas, alguns valores baixos de p são esperados por acaso; nada fora da família primária é confirmatório.
8. **Análises post hoc.** As secções marcadas como post hoc e as correcções da revisão foram feitas depois de ver os
   resultados. Estão registadas, com os valores antigos e novos, no `CHANGELOG.md`.
9. **Pormenores de implementação.** No estudo de robustez, o erro-padrão dos controlos emparelhados trata as médias dos
   controlos como conhecidas (cerca de 5% de subestimação nas classes mais raras). A cópia do código em
   `research/sp500/code` reproduziu exactamente, com os mesmos dados, todas as tabelas do estudo principal, da robustez
   e da fidelidade, e uma fatia da validação contra o Pine.
10. **Fontes.** As cópias dos dados vieram de terceiros. As verificações cruzadas são boas, mas há anos com mais
    discrepância entre fontes (2018), e o volume do SPY depende do fornecedor.
11. **Um só estudo, não revisto por pares.**

## 17. Conclusão para quem negoceia de forma discricionária

**A resposta curta.** No S&P 500, com o delta que a TradingView usa por omissão, os sinais do indicador não dizem para
que lado o preço vai nos 5 a 60 minutos seguintes. Isto vale para os alertas de Z, para as absorções, para os
«travados», para o preço sem fluxo, para as resoluções e para os pivots, em 5 e em 15 minutos, em 18,7 anos de ES, no
MES e no SPY. Seguir os alertas, ou ir contra eles, perde em média o custo da operação.

**Onde os sinais podem ajudar.**

- **Como medidor de contexto, não de direcção.** O Z e os eventos marcam momentos em que o fluxo e o preço se afastam
  do habitual. Depois deles, o preço tende a mover-se um pouco mais do que numa barra comparável (+0,06σ a +0,18σ aos
  30 minutos, em 13 das 16 classes no gráfico de 5 minutos), nos dois sentidos. Isso pode servir para ajustar o tamanho
  da posição ou a largura do *stop*, não para escolher o lado.
- **Para ler o mercado por si mesmo.** A relação entre o preço e o fluxo no ES é forte e estável (ρ̂ mediano 0,71,
  gate aberto em 98% das barras), e o Z tem uma frequência estável de ano para ano. O indicador descreve bem essa
  relação; o que não faz é prevê-la.
- **Como filtro de uma ideia que já tem razões próprias**, desde que essa combinação seja testada à parte. Este estudo
  não testou combinações com outras regras.

**Onde os sinais enganam.**

- **Ler um rótulo como uma ordem.** «Absorvido», «continuação» e «segurou» descrevem o que aconteceu no par preço-fluxo,
  não o que vai acontecer. Depois das resoluções de «continuação», o preço até reverteu ligeiramente em média no ES e no
  SPY (sem significância).
- **Absorções e «travados» ao fecho.** No gráfico de 15 minutos, mais de metade destes eventos cai nas barras das 14:45
  e 15:00 CT. Quando a janela inclui o minuto das 14:59 CT, o lado do evento é, na prática, o sinal de uma única vela
  de 1 minuto com o volume do leilão de fecho. Trate estes alertas como não validados.
- **Achar que o «Auto» mostra o fluxo agressor.** Com intrabars de 1 minuto, o que o delta traz para além do preço é
  pouco, e a maioria dos eventos de fluxo não coincide com os que o fluxo verdadeiro daria. O mesmo minuto do índice dá
  absorções diferentes no ES, no MES e no SPY.
- **Ler um |Z| ≥ 2 como raro.** Acontece em cerca de 6,5% das barras de 5 minutos e em quase 9% das do horário
  regular.
- **Resoluções logo a seguir à reabertura**, causadas pelo salto da sessão e não por fluxo, e **alertas em semana de
  rolagem**, que ficaram fora do estudo.
- **Dados atrasados.** Sem dados do CME em tempo real na TradingView (atraso de 10 minutos), os horizontes de 5 e
  15 minutos já passaram quando o alerta chega.

**O que vale a pena testar a seguir.**

1. **Sinais com o fluxo verdadeiro ou com 1S, numa amostra longa.** É a pergunta que este estudo não pode responder:
   o mesmo plano, pré-registado, com delta de negócios classificados (por exemplo, um ano ou mais de negócios do CME) ou
   com intrabars de 1S servidos pela TradingView.
2. **A reversão depois das resoluções de «continuação»**, como hipótese confirmatória em dados posteriores a Setembro
   de 2026 (ES e SPY) e noutro mercado, com o teste fixado antes de olhar para os dados.
3. **Um resultado de volatilidade pré-registado.** Se o valor está no tamanho do movimento e não no sentido, a
   pergunta certa é se o Z ou os eventos prevêem |retorno| ou amplitude melhor do que a hora do dia e a volatilidade
   recente.
4. **O gate onde ele fecha** (SPY com horário alargado, outros mercados, delta verdadeiro), para responder ao ponto (d)
   da auditoria.
5. **Alterações ao indicador que este estudo sugere**, a decidir à parte: assinalar ou suprimir absorções e «travados»
   cuja janela contém o minuto de liquidação; expirar as absorções pendentes no fim da sessão ou marcar as resoluções
   causadas pelo salto da reabertura; calibrar o Z separadamente no horário regular e no electrónico.

## 18. Reprodução

O código, a reconstrução dos dados a partir das fontes e os comandos que geram cada tabela estão em
[research/sp500/README.md](../research/sp500/README.md). Os resultados agregados de referência estão em
`research/sp500/results/`: `es/` (estudo principal: `results.md`, `interpretation.md`, `CHANGELOG.md` e os CSV),
`fidelity/`, `robust/` e os ficheiros `validation_*.json` da validação contra o Pine. Com 4 CPUs, o estudo principal
corre em cerca de 3 minutos depois de construídos os ficheiros de características; a validação de um ano de barras de
5 minutos no PineTS leva cerca de 8 minutos.
