# Preço × CVD Normalizado [Order Flow]

Indicador em Pine Script v6 para a TradingView que põe o **preço** e o **CVD** (*cumulative volume delta*, delta de
volume acumulado) na mesma escala, no mesmo painel, e mede de forma calibrada quando um se afasta do outro. Todos os
cálculos são causais: nenhum valor usa barras futuras.

> **Aviso.** É uma ferramenta de análise estatística. Não é recomendação de investimento. As divergências e os eventos
> que o indicador assinala são descritivos: em dados reais não se encontrou um efeito direccional robusto
> (ver [Limitações](#limitações) e [docs/METODOLOGIA.md](docs/METODOLOGIA.md)).

## Índice

- [O que é](#o-que-é)
- [Porque normalizar em unidades-σ](#porque-normalizar-em-unidades-σ)
- [Edições e planos da TradingView](#edições-e-planos-da-tradingview)
- [Instalação](#instalação)
- [Leitura do painel](#leitura-do-painel)
- [Estados e eventos](#estados-e-eventos)
- [Qualidade dos dados](#qualidade-dos-dados)
- [Parâmetros](#parâmetros)
- [Alertas](#alertas)
- [Limitações](#limitações)
- [Aviso legal](#aviso-legal)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Testes](#testes)
- [Referências principais](#referências-principais)

## O que é

O painel mostra duas linhas, ambas em zero no início de cada período de âncora (por exemplo, o início do dia):

- **Preço (normalizado)**: o caminho do preço desde a âncora, em múltiplos da variação típica de uma barra (σ do retorno).
- **CVD (normalizado)**: o delta acumulado desde a âncora, em múltiplos do delta típico de uma barra (σ do delta).

Sobre as linhas, o indicador calcula:

- uma estatística de divergência **Z**, calibrada empiricamente, que colore o preenchimento entre as linhas e pode
  ser vista como histograma;
- **eventos** de janela curta (cerca de 15 minutos): fluxo absorvido, preço travado e preço sem fluxo. São marcados no
  gráfico principal com rótulos neutros e só ganham cor direccional depois de o preço os resolver;
- uma **tabela** de estado: fonte e qualidade do delta, Z e estado, último evento.

O delta de cada barra é estimado a partir de barras de um timeframe inferior (intrabars) ou, na edição Footprint, do
footprint de volume da TradingView. A qualidade desse delta condiciona tudo, por isso o indicador classifica cada
barra (alta, média, baixa) e só produz sinais com qualidade média ou alta.

## Porque normalizar em unidades-σ

Preço e CVD têm unidades diferentes (USD contra BTC, pontos contra contratos) e o CVD não tem origem natural. A solução
habitual é reescalar os **níveis** (mín–máx, z-score dos níveis). Isso é estatisticamente enganador: duas séries
integradas independentes (passeios aleatórios) mostram correlações grandes por puro acaso. Para dois passeios
aleatórios independentes, o quadrado esperado da correlação dos níveis é 0,24 (Ernst, Shepp e Wyner, 2017), e nas
nossas simulações a diferença entre os z-scores móveis de dois passeios independentes passou |2| em cerca de um terço
das barras.

A microestrutura liga **variações** de preço a **fluxo assinado**, não níveis a níveis. No modelo de Kyle (1985) a
variação do preço é linear no fluxo líquido, Δp = λ·y. Evans e Lyons (2002) regridem as variações diárias de câmbio
sobre o fluxo de ordens e obtêm R² acima de 60%; a figura 1 do artigo sobrepõe a taxa de câmbio ao fluxo acumulado,
que é o precedente académico deste painel. Se o preço responde linearmente ao fluxo, o factor de escala natural é λ.
Quando as duas pernas têm ruído (o preço reflecte informação pública que o CVD não vê; o CVD tem erro de
classificação), a versão simétrica λσ = σ(Δp)/σ(Δ) não encolhe a linha do fluxo pelo factor ρ, como faria uma
regressão OLS. Dividir cada perna pelo seu próprio σ, estimado sobre incrementos de N = 100 barras, desfasado uma barra
e congelado na âncora, dá exactamente esse mapeamento sem unidades: «quantas barras típicas o preço e o fluxo
percorreram desde a âncora». Dentro de cada período, a linha do preço tem a forma do gráfico (exacta em escala
logarítmica).

A derivação completa está em [docs/METODOLOGIA.md](docs/METODOLOGIA.md).

## Edições e planos da TradingView

As duas edições são geradas a partir de uma única fonte (`src/price_cvd_normalizer.src.pine`).

| | Standard | Footprint |
|---|---|---|
| Ficheiro | `price_cvd_normalizer.pine` | `price_cvd_normalizer_footprint.pine` |
| Título (abreviado) | Preço × CVD Normalizado [Order Flow] (P×CVD) | Preço × CVD Normalizado [Order Flow · Footprint] (P×CVD FP) |
| Planos | Todos | Todos para intrabars; Premium ou Ultimate para a fonte Footprint |
| Fontes de delta | Intrabar; só barras do gráfico | Intrabar; **Footprint**; só barras do gráfico |
| `request.footprint()` | Não existe no código | Um único local de chamada, só executado com a fonte Footprint |

**Porque há duas edições.** A documentação da TradingView diz que só contas Premium ou Ultimate podem usar scripts
que **chamam** `request.footprint()`. Não está documentado se uma chamada que nunca é executada é tolerada nos
outros planos. A edição Standard não tem nenhuma referência de código ao footprint e deve carregar em qualquer plano.
Na edição Footprint, a fonte Footprint nunca é escolhida automaticamente; se a seleccionar num plano inferior, o script
pode parar com um erro.

**Precisão intrabar e plano.** O limite de intrabars por script está documentado no manual do Pine: 100 000 nos
planos Basic, Essential, Plus e Premium, 125 000 no Expert e 200 000 no Ultimate. Os planos exigidos para os
intervalos de segundos e de ticks vêm da página de preços da TradingView, vista apenas através de uma fonte
secundária: confirme no seu plano.

| Precisão | Plano (indicativo) | Qualidade | Cobertura aproximada com 100 000 intrabars |
|---|---|---|---|
| 1T (ticks) | Ultimate | alta | Horas num mercado líquido; uma barra com mais de 100 000 negócios excede o limite de elementos de um array |
| 1S (segundos) | Premium ou superior | alta | ~28 h de mercado líquido (~330 barras de 5 min, ~110 de 15 min) |
| 1 minuto | todos | média | 100 000 minutos ≈ 69 dias de mercado 24/7 |
| Só barras do gráfico | todos | baixa (sem sinais) | todo o histórico |

O Footprint (qualidade alta) exige Premium ou Ultimate. A profundidade histórica do footprint não está documentada.

## Instalação

1. Abra o ficheiro da edição pretendida (`price_cvd_normalizer.pine` ou `price_cvd_normalizer_footprint.pine`) e copie
   todo o conteúdo.
2. Na TradingView, abra o **Pine Editor**, crie um indicador novo, substitua o código pelo conteúdo copiado, guarde e
   escolha **Adicionar ao gráfico**.
3. Use um gráfico de velas, barras ou linha num timeframe de tempo. Os gráficos Heikin Ashi, Renko, Range, Kagi, Line
   Break e Ponto e Figura (preços sintéticos) e os gráficos de ticks param com um erro explícito.
4. Confirme na tabela a fonte efectiva e a qualidade. Num gráfico de 1 minuto, a precisão Auto usa intrabars de 1
   minuto, iguais ao gráfico, e a qualidade fica baixa: escolha 1S ou 1T para ter sinais.

Não edite os ficheiros `.pine` da raiz: são gerados. Altere `src/price_cvd_normalizer.src.pine` e corra
`python3 tools/build.py`.

## Leitura do painel

### Linhas

- **Preço (normalizado)**, na cor do texto do tema: 10⁴·(ln C − ln O_a)/σr,a, em que O_a é a abertura da barra da
  âncora e σr,a o desvio-padrão do retorno (bps) nas N barras anteriores à âncora.
- **CVD (normalizado)**, em violeta: o delta acumulado desde a âncora sobre o σ do delta congelado na âncora. Fica
  esbatida nas barras de qualidade baixa, em que o delta é derivado do próprio preço.
- As linhas interrompem-se na barra da âncora e recomeçam perto de zero. A **distância** entre elas é, no essencial,
  o resíduo acumulado desde a âncora: é contexto, não sinal. A linha do fluxo afasta-se naturalmente mais (memória
  longa dos sinais das ordens, ρ < 1) e, com fluxo persistente num só sentido, pode chegar a ±15–30.

Os outros modos (preço implícito pelo fluxo, janela móvel, z-score de níveis, mín–máx) estão na tabela de
[parâmetros](#parâmetros); os dois últimos são só visuais e não geram sinais.

### Preenchimento, histograma Z e fundo

- A cor do preenchimento é o **Z calibrado das últimas K = 20 barras**, não a distância entre as linhas (podem
  discordar). **Laranja** (Z > 0): preço à frente do fluxo, isto é, nas últimas K barras o preço subiu mais (ou caiu
  menos) do que o fluxo implica; não é um sinal de alta. **Azul** (Z < 0): fluxo à frente do preço. **Cinzento**: gate
  fechado, Z indisponível ou |Z| < 1. A intensidade cresce até ao limiar forte e fica limitada enquanto a calibração for
  fraca. Na vista «Linhas», o Z aparece na linha de estado e na Data Window.
- As vistas «Histograma Z» e «Linhas + Z» mostram o Z em colunas, com os limiares (±2 tracejado, ±3 pontilhado). Em
  «Linhas + Z» as linhas dominam a escala; para ver ambos legíveis, adicione o indicador duas vezes.
- O **cone nulo** opcional (±2·√(2n(1 − max(ρ_a, 0))) à volta da linha do preço) é só uma referência iid: em dados
  reais de 5 minutos a linha do fluxo saiu dele em ~17% das barras, não ~4,6%.
- O **fundo** marca as barras de âncora (cinzento) e as mudanças de qualidade do delta (castanho), por exemplo no
  início da cobertura dos intrabars.

### Tabela e Data Window

A tabela **compacta** (por omissão) tem três linhas: (1) fonte e qualidade, por exemplo «intrabar 1 s · regra da vela
· alta», mais avisos com ⚠; (2) Z, com «cal. n/M» enquanto a calibração for provisória, e o estado; (3) último evento,
idade e resolução. As dicas das células mostram a âncora, o NAR (rácio de agressão líquida = CVD/volume), a
cobertura, o tipo de volume, ρ com IC 95%, R², λ e η; a versão **completa** mostra-os em 9 linhas. Avisos possíveis:
«âncora inválida → Auto», «poucos intrabars», «volume de ticks» e «desequilíbrio persistente» (|NAR| ≥ 3% em todo o
histórico de qualidade ≥ média: considere «Remover deriva do fluxo»).

A Data Window (janela de dados) mostra delta, CVD ancorado, σr, σΔ, ρ, λ OLS, Z, as pernas P_K e F_K, zF, zP, η,
qualidade (0–3), intrabars, gate e a confiança do evento resolvido.

## Estados e eventos

### Os quatro estados neutros de Z

Com o gate aberto e |Z| ≥ limiar (2 por omissão), o sinal de Z e a perna dominante (|F_K| contra |P_K|, as somas das
unidades-σ do fluxo e do preço nas K barras) dão um de quatro estados, sem direcção prevista:

| Condição | Estado (tabela) | Leituras possíveis (ambas plausíveis) |
|---|---|---|
| Z ≤ −2 e \|F\| > \|P\| | Compras sem subida do preço | Vendedores passivos absorvem as compras: reversão se forem informados, ou combustível para uma quebra em que o preço apanha o fluxo |
| Z ≤ −2 e \|P\| ≥ \|F\| | Preço a cair sem vendas | Descida não confirmada pelo fluxo: retirada de ofertas de compra ou notícia (pode ser permanente) |
| Z ≥ +2 e \|F\| > \|P\| | Vendas sem queda do preço | Absorção das vendas (caso espelho) |
| Z ≥ +2 e \|P\| ≥ \|F\| | Preço a subir sem compras | Subida não confirmada: recompra de vendas a descoberto com ordens limite, retirada de ofertas de venda ou notícia |

Fora destes casos a tabela mostra «Sem divergência significativa», «Gate fechado: …», «Em aquecimento (x/y)» ou «Sem
sinais: …» com a razão. Z é um medidor descritivo, não uma previsão.

### Eventos de janela curta

Os eventos usam zF e zP, as pernas do fluxo e do preço numa janela de ~15 minutos (3 barras em 5 min; 1 barra em
15 min ou mais), cada uma padronizada pelo seu próprio RMS:

- **Compras absorvidas / Vendas absorvidas**: |zF| ≥ 2 e o preço não andou no sentido do fluxo.
- **· preço travado**: |zF| ≥ 3 com |zP| ≤ 0,5 (fluxo forte, preço quase parado). Não é raro: em dados reais |zF| ≥ 3
  ocorreu em 2–3,5% das barras.
- **Preço ↑ sem fluxo comprador / Preço ↓ sem fluxo vendedor**: |zP| ≥ 2 sem fluxo no mesmo sentido.

Só a primeira barra fechada de cada aglomerado (por classe e lado) gera rótulo. Rótulos cheios com qualidade alta;
ocos com «(baixa conf.)» com qualidade média (por exemplo, intrabars de 1 minuto); ocos com «(cal. prov.)» enquanto a
calibração do zF/zP for fraca (sem alertas); nenhum com qualidade baixa. Em gráficos de 1 hora ou mais, os eventos
são apenas contexto.

### Resolução da absorção

O indicador regista o máximo e o mínimo da janela do evento. Depois, em barras fechadas e dentro da vida máxima
(60 minutos: 12 barras em 5 min; 1 barra em 1 h ou mais):

- fecho para lá do extremo **no sentido do fluxo** → «→ continuação ↑/↓» (a absorção falhou);
- fecho para lá do extremo **oposto** → «→ absorção segurou ↑/↓» (o lado passivo venceu);
- nenhum dos dois → «→ expirou»; nova absorção com uma pendente → a anterior fica «→ substituído».

Só os eventos resolvidos ganham cor direccional. O «Viés direccional» (Neutro por omissão) só recolore eventos de
qualidade alta por resolver: não há evidência revista por pares de uma direcção típica após absorção.

### Divergência por pivots (opcional)

Pivot de máximo do preço mais alto do que o anterior, com o CVD (lido na barra do pivot do preço) mais baixo em pelo
menos 0,5 σΔ, pivots a 5–60 barras e ambos em qualidade ≥ média → «Topo sem confirmação do fluxo» (espelho: «Fundo
sem confirmação do fluxo»). Só é conhecido R = 2 barras depois: o rótulo fica no pivot e o alerta sai na confirmação.
Evidência fraca.

## Qualidade dos dados

| Nível | Origem do delta | Linhas | Z | Eventos |
|---|---|---|---|---|
| **Alta (3)** | Footprint; intrabars 1T ou 1S abaixo do timeframe do gráfico, com a regra da vela | sim | sim | estilo normal |
| **Média (2)** | Outros intrabars abaixo do gráfico (1 minuto, 5S–45S, …) ou o classificador BVC | sim | sim | ocos, «baixa conf.» |
| **Baixa (1)** | Intrabars não inferiores ao gráfico; BVC na barra (sem intrabars); volume de ticks (FX à vista, CFD) | sim, CVD esbatido | não | não |
| **Sem dados (0)** | «Barras sem intrabars» = Nenhum, numa barra sem intrabars | interrompidas | não | não |

**Porquê.** Em dados reais com o lado agressor de cada negócio (BTC, barras de 5 minutos), o que interessa para a
divergência é a parte do delta que o preço não explica. A sua correlação parcial com o delta verdadeiro foi 0,80–0,88
com intrabars de 1 segundo, 0,29–0,87 com intrabars de 1 minuto e tipicamente 0,1–0,4 com estimativas a partir das
barras do gráfico. Um delta derivado das barras do gráfico é, no essencial, uma cópia do preço ponderada pelo volume.

**Precisão Auto** (paridade com o CVD da TradingView):

| Gráfico | Auto usa | Qualidade | Para ter mais |
|---|---|---|---|
| Segundos (5S, 10S, …) | 1S | alta | — |
| 1 segundo | 1S (= gráfico) | baixa, sem sinais | 1T |
| 1 minuto | 1 minuto (= gráfico) | baixa, sem sinais | 1S ou 1T |
| Intradiário de 2 minutos ou mais (até 4 h, …) | 1 minuto | média | 1S ou 1T (cobertura curta) |
| Diário | 5 minutos | média | — |
| Semanal ou superior | 60 minutos | média | — |

**Limites de intrabars.** Para lá do limite do plano (100K, 125K ou 200K intrabars, contados a partir da barra mais
recente), as barras antigas não têm intrabars e usam a regra «Barras sem intrabars» (por omissão, BVC na barra:
qualidade baixa). A transição fica marcada no fundo e as linhas reiniciam uma vez na primeira barra cuja janela σ/ρ
está toda em dados finos.

**Aquecimento.** O Z exige N + max(K, janela do evento) barras seguidas de qualidade ≥ média e depois N valores de
D: cerca de 220 barras com os valores por omissão em 5 minutos (mais N com a remoção da deriva). Com 1S num gráfico de
5 minutos (~330 barras cobertas com 100K intrabars), o Z só existe nas ~110 barras mais recentes, a calibração fica
provisória e quase não há alertas históricos; em tempo real os alertas passam a disparar quando houver valores de
calibração suficientes.

## Parâmetros

### Dados de delta

| Entrada | Por omissão | Efeito |
|---|---|---|
| Fonte do delta | Intrabar (timeframe inferior) | Intrabar, Footprint (só na edição Footprint; Premium/Ultimate) ou «Só barras do gráfico» (BVC na barra, qualidade baixa, sem sinais) |
| Ticks por linha do footprint | 100 | Só Footprint. Não altera o delta total; aumente-o se o footprint vier vazio em barras amplas (mais de 2000 linhas) |
| Preencher barras sem footprint com delta intrabar | desligado | Só Footprint. Ligado: barras sem footprint usam o delta intrabar (mistura de classificadores) |
| Precisão intrabar | Auto | Timeframe dos intrabars: Auto, 1T, 1S, 1 minuto ou Personalizado (ver a tabela da precisão Auto) |
| Timeframe personalizado | 1 | Usado com «Personalizado»; tem de ser inferior ao gráfico |
| Classificador intrabar | Regra da vela | Regra da vela da TradingView (com a regra das cotações bid/ask em 1T) ou BVC-Normal por intrabar (qualidade no máximo média) |
| Barras sem intrabars | BVC na barra | BVC-Normal na barra (qualidade baixa, sem sinais) ou Nenhum (a barra fica sem dados) |
| Remover deriva do fluxo | desligado | Usa Δ − média móvel de N barras do Δ (desfasada). Sugerido em perpétuos de cripto e quando a tabela avisa «desequilíbrio persistente» |

### Normalização e visualização

| Entrada | Por omissão | Efeito |
|---|---|---|
| Modo de normalização | Unidades-σ ancoradas | **Unidades-σ ancoradas**; **Preço implícito pelo fluxo (λ)**: o CVD convertido em preço, P̂ = O_a·exp(λ_a·CVD_a/10⁴); **Unidades-σ em janela móvel** (W barras, sem reinícios); **Z-score de níveis** e **Mín–máx** (só visuais) |
| Âncora | Auto | Auto: gráfico ≤ 1 h → diária (CME: dia Globex; cripto: dia UTC); < 1D → semanal; 1D → mensal; ≥ 1W → anual. Também RTH e sessão personalizada (só intradiário) e diária, semanal ou mensal (só se maior do que o gráfico); uma âncora inválida passa à Auto e a tabela avisa. As estatísticas nunca reiniciam, só as linhas |
| Sessão personalizada (âncora) | 0830-1515 | Início da sessão que ancora as linhas, na hora da bolsa; aceita sessões que atravessam a meia-noite |
| Janela W | 100 | Janela dos modos em janela móvel, z-score de níveis e mín–máx (10–1000) |
| Escala de impacto λ | λσ = σr/σΔ | Só no modo preço implícito. λ OLS = ρ·σr/σΔ encolhe a linha do fluxo pelo factor ρ |
| Mostrar preço implícito no gráfico principal | desligado | Desenha o preço implícito pelo fluxo sobre as velas (referência visual, não preço justo) |
| Vista do painel | Linhas | Linhas, Histograma Z, ou Linhas + Z |
| Cone nulo iid (±2σ) | desligado | Só em unidades-σ ancoradas |
| Marcar âncoras e mudanças de qualidade | ligado | Fundo ténue nas âncoras e nas transições de qualidade |

### Estatística

| Entrada | Por omissão | Efeito |
|---|---|---|
| Janela σ/ρ (N) | 100 | Janela de σr, σΔ e ρ sobre incrementos, desfasados uma barra (30–300) |
| Horizonte da divergência (K) | 20 | Barras somadas na estatística D (5–50) |
| Janela de calibração (M) | 1000 | RMS não centrado que calibra o Z (300–2000; recomendado ≥ 5N) |
| Winsorizar unidades-σ em ± | 4,0 | Limita as unidades-σ de cada barra antes de somar (guarda contra caudas pesadas e impacto côncavo) |
| Limiar \|Z\| | 2,0 | Marca divergência: cerca de 6% das barras em dados reais |
| Limiar forte \|Z\| | 3,0 | Intensidade máxima do preenchimento: cerca de 1–1,5% das barras em dados reais |
| ρ mínimo (gate) | 0,30 | Gate efectivo = max(este valor, tanh(1,96/√(N−3))); abaixo dele o Z fica cinzento e não há sinais |

### Eventos

| Entrada | Por omissão | Efeito |
|---|---|---|
| Eventos de absorção | ligado | Compras/vendas absorvidas e preço travado |
| Eventos de preço sem fluxo | ligado | Preço ↑ sem fluxo comprador / Preço ↓ sem fluxo vendedor |
| Janela do evento (min) | 15 | Convertida em barras: mínimo 1, máximo M/20 |
| Vida máxima do evento (min) | 60 | Tempo para a resolução da absorção (mínimo 1 barra) |
| Limiar dos eventos (\|zF\|, \|zP\|) | 2,0 | Limiar da absorção (zF) e do preço sem fluxo (zP) |
| Travado: \|zF\| mínimo | 3,0 | Fluxo extremo para «preço travado» |
| Travado: \|zP\| máximo | 0,5 | Preço quase parado para «preço travado» |
| Mostrar eventos com qualidade média (baixa confiança) | ligado | Eventos com intrabars de minutos, em estilo oco |
| Viés direccional | Neutro | Neutro, Continuação ou Reversão; só recolore eventos de qualidade alta por resolver |
| Divergência por pivots (clássica) | desligado | Activa os rótulos «Topo/Fundo sem confirmação do fluxo» |
| Pivot: barras à esquerda / à direita | 5 / 2 | Definição do pivot; a da direita é o atraso de confirmação |
| Pivot: distância mínima / máxima | 5 / 60 | Distância, em barras, entre os dois pivots comparados |
| Pivot: diferença mínima de CVD (σΔ) | 0,5 | Em unidades do σΔ de uma barra |

### Estilo e tabela

| Entrada | Por omissão | Efeito |
|---|---|---|
| Preço / CVD | cinzento (= cor do texto do tema) / violeta #AB47BC | Cores das linhas |
| Z > 0 / Z < 0 | laranja #EF6C00 / azul #2962FF | Preenchimento e colunas Z |
| Subida / Descida / Neutro | #26A69A / #EF5350 / #787B86 | Resoluções e eventos |
| Espessura: preço / CVD | 2 / 2 | Espessura das linhas |
| Mostrar tabela | ligado | |
| Posição | Canto superior direito | Seis posições |
| Tamanho | Pequeno | Muito pequeno, Pequeno ou Normal |
| Versão | Compacta | Compacta (3 linhas) ou Completa (9 linhas) |

## Alertas

Crie um alerta sobre o indicador e escolha a condição. Todas as condições são avaliadas só em barras fechadas;
escolha a frequência *Once Per Bar Close* (uma vez por fecho de barra).

| Condição | Quando dispara |
|---|---|
| Z ≥ +limiar (preço à frente do fluxo) | 1.º cruzamento com o gate aberto |
| Z ≤ −limiar (fluxo à frente do preço) | 1.º cruzamento com o gate aberto |
| Fluxo comprador absorvido / Fluxo vendedor absorvido | 1.ª barra de um evento de absorção |
| Preço travado sob compras extremas / sob vendas extremas | 1.ª barra de um evento «travado» |
| Compras absorvidas → continuação (alta) / → segurou (baixa) | Resolução de uma absorção de compras |
| Vendas absorvidas → continuação (baixa) / → segurou (alta) | Resolução de uma absorção de vendas |
| Preço sem fluxo (subida) / (queda) | 1.ª barra de um evento de preço sem fluxo |
| Divergência por pivots (topo) / (fundo) | Confirmação do pivot (R barras depois) |
| *Any alert() function call* (qualquer chamada da função `alert()`) | Mensagem dinâmica para qualquer um dos casos acima, com símbolo, timeframe, fecho, estado, Z, zF, zP, ρ, fonte e qualidade |

Regras:

- Os alertas de Z voltam a armar só depois de o Z regressar a menos de limiar − 1 do mesmo lado, e exigem pelo menos 2N
  valores de calibração.
- Os eventos com calibração fraca («cal. prov.») não alertam, nem as suas resoluções. Uma expiração sozinha não alerta.
- As mensagens incluem a qualidade (3 alta, 2 média = baixa confiança). Nos alertas de resolução, a confiança é a do
  evento resolvido.

## Limitações

1. **O CVD só vê negócios agressores.** Liquidez passiva, cancelamentos, icebergs e ordens escondidas são invisíveis;
   muito do que parece «divergência» é fluxo de ordens limite, funcionamento normal do mercado.
2. **O delta é estimado.** Mesmo o footprint é classificado pela TradingView a partir da acção do preço intrabar, não
   das marcas de agressor da bolsa. Com intrabars de 1 minuto ou só com as barras do gráfico, a estimativa depende em
   parte do próprio preço.
3. **Não há vantagem direccional validada.** Nenhum estudo revisto por pares valida os retornos após divergência,
   absorção ou exaustão do CVD. Nos nossos testes com dados reais, o Z não previu retornos; houve só uma ligeira
   continuação após absorção de 15 minutos, numa só bolsa e na própria amostra, que desapareceu com delta estimado de
   1 minuto.
4. **Calibração numa amostra estreita:** um par cripto à vista (BTCFDUSD, 4 meses) e simulações. Futuros do CME,
   acções, perpétuos e FX não estão validados. Em cripto, o CVD de uma bolsa inclui fluxo próprio dessa bolsa.
5. **Cobertura, planos e tempo real.** Os limites de intrabars encurtam o histórico de 1S/1T; o comportamento do
   footprint e de 1S/1T em cada plano não está totalmente documentado. Na barra em curso os valores são provisórios, e
   os dados intrabar e de footprint podem diferir entre histórico e tempo real.
6. **Compilação.** Não havia acesso ao compilador da TradingView; o código foi verificado contra a documentação, com um
   parser e com um runtime alternativo. Ver a lista de verificação em [docs/VALIDACAO.md](docs/VALIDACAO.md).

## Aviso legal

Este indicador é fornecido tal como está, sem garantias de qualquer tipo, para fins de análise e estudo. Não é
recomendação de investimento, aconselhamento financeiro nem incitamento à compra ou venda de qualquer activo. Os
resultados passados, simulados ou estatísticos não garantem resultados futuros. Negociar instrumentos financeiros
envolve risco de perda. Cada utilizador é responsável pelas suas decisões e deve validar o indicador no seu
instrumento e timeframe antes de o usar.

## Estrutura do repositório

```
price_cvd_normalizer.pine             edição Standard (gerada; todos os planos)
price_cvd_normalizer_footprint.pine   edição Footprint (gerada; Premium/Ultimate para a fonte Footprint)
src/price_cvd_normalizer.src.pine     fonte única, a única editada à mão (linhas com // @std ou // @fp)
tools/build.py                        gera as duas edições; --check falha se estiverem desactualizadas
tests/                                harness de testes (PineTS) e o seu README
docs/METODOLOGIA.md                   derivação completa, estatística, eventos, interpretação, bibliografia
docs/VALIDACAO.md                     o que foi validado, como, com que resultados, e o que falta verificar
docs/research-dossier.md              dossier de investigação original (inglês)
package.json, requirements-dev.txt    dependências dos testes (pinets 0.11.0; pynescript 0.3.0)
```

## Testes

Requisitos: Node.js ≥ 20 e, para o teste de parse, Python 3 com `pynescript`.

```bash
npm install                                    # instala o pinets 0.11.0
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt   # opcional: teste T2 (parse)
python3 tools/build.py --check                 # as edições geradas coincidem com a fonte
npm test                                       # T0–T11 nas duas edições (alguns minutos)
npm run test:quick                             # matriz reduzida
```

Os testes correm o código Pine no PineTS (um runtime de Pine Script para Node) sobre barras sintéticas com delta
verdadeiro conhecido e comparam o resultado com uma referência independente. O PineTS não é o compilador da
TradingView. Pormenores em [tests/README.md](tests/README.md); resultados em [docs/VALIDACAO.md](docs/VALIDACAO.md).
A validação com dados reais é feita fora do repositório: os dados de mercado nunca são versionados.

## Referências principais

- Kyle, A.S. (1985). Continuous Auctions and Insider Trading. *Econometrica* 53(6). [Econometric Society](https://www.econometricsociety.org/publications/econometrica/browse/1985/11/01/continuous-auctions-and-insider-trading)
- Evans, M.D.D., Lyons, R.K. (2002). Order Flow and Exchange Rate Dynamics. *JPE* 110(1). [NBER w7317](https://www.nber.org/papers/w7317)
- Cont, R., Kukanov, A., Stoikov, S. (2014). The Price Impact of Order Book Events. *J. Fin. Econometrics* 12(1). [arXiv:1011.6402](https://arxiv.org/abs/1011.6402)
- Chordia, T., Roll, R., Subrahmanyam, A. (2002). Order imbalance, liquidity, and market returns. *JFE* 65. [RePEc](https://ideas.repec.org/a/eee/jfinec/v65y2002i1p111-130.html)
- Easley, D., López de Prado, M., O'Hara, M. (2012). Flow toxicity and liquidity in a high-frequency world. *RFS* 25(5). [SSRN](https://papers.ssrn.com/abstract=1695596)
- Lillo, F., Farmer, J.D. (2004). The long memory of the efficient market. *SNDE* 8(3). [arXiv:cond-mat/0311053](https://arxiv.org/abs/cond-mat/0311053)
- Bouchaud, J.-P., Gefen, Y., Potters, M., Wyart, M. (2004). Fluctuations and response in financial markets. *Quant. Finance* 4(2). [arXiv:cond-mat/0307332](https://arxiv.org/abs/cond-mat/0307332)
- Weber, P., Rosenow, B. (2005). Order book approach to price impact. *Quant. Finance* 5(4). [arXiv:cond-mat/0311457](https://arxiv.org/abs/cond-mat/0311457)
- Granger, C.W.J., Newbold, P. (1974). Spurious regressions in econometrics. *J. Econometrics* 2. [PDF](https://gwern.net/doc/economics/1974-granger.pdf)
- Ernst, P.A., Shepp, L.A., Wyner, A.J. (2017). Yule's "nonsense correlation" solved! *Ann. Stat.* 45(4). [PDF](https://www.ma.imperial.ac.uk/~pernst/AOS1509.pdf)
- Abramowitz, M., Stegun, I.A. (1964). *Handbook of Mathematical Functions*, eq. 7.1.26.
- TradingView, *Pine Script v6 User Manual and Reference* (limites de intrabars, `request.footprint`, `request.security_lower_tf`).

A bibliografia anotada, com o estado de verificação de cada fonte, está em
[docs/METODOLOGIA.md](docs/METODOLOGIA.md#bibliografia-anotada).
