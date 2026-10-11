> **Nota (PT-PT).** Este é o dossier de investigação original, em inglês, que serviu de base ao código do indicador
> «Preço × CVD Normalizado [Order Flow]». Fica aqui como documento de referência e histórico. Onde
> a implementação final difere (duas edições geradas da mesma fonte em vez de um só script, regra dos níveis de
> qualidade, costura da cobertura, aglomerados de eventos, histerese dos alertas, funcionalidades não implementadas,
> como os candidatos de exaustão, a marca de Dickey-Fuller e a transformação côncava do fluxo), prevalece
> [METODOLOGIA.md](METODOLOGIA.md), em especial a secção 10. Os excertos de
> código Pine da secção 7.3 são esboços anteriores à implementação e não correspondem ao código final.
>
> As marcas [V], [V-sec], [M] e [E] mantêm o significado original; números marcados [V-sec] ou [M] não devem ser citados
> como factos. As referências a ficheiros locais foram substituídas por descrições: os scripts e resultados de
> investigação, e as páginas do manual descarregadas durante a investigação, não estão incluídos neste repositório.
> «Cópia local» do manual do Pine designa uma cópia da documentação oficial (espelho
> https://github.com/codenamedevan/pinescriptv6).

# Price × CVD on a Common Scale: Research Dossier

**Purpose.** This dossier drives the implementation of a Pine Script v6 indicator that normalizes an asset's price together with its Cumulative Volume Delta (CVD) and plots both in the same pane. It consolidates six research streams, a critic report and four gap-fill studies, three of them on real aggressor-flagged trade data.
**Date:** 2026-10-10. **Audience:** the implementer of the Pine script and the reviewing quant. **Pine version:** v6, with docs and release notes up to April 2026.

**Source-status legend**

| Tag | Meaning |
|---|---|
| **[V]** | Verified in this run: we saw the primary full text or the abstract. |
| **[V-sec]** | Seen only in an authoritative secondary summary, a mirror, or a third-party quote. |
| **[M]** | From memory, not verified in this run. Do not quote its numbers in user-facing text. |
| **[E]** | Our own empirical or simulation result from this run. Not peer-reviewed. Scripts and outputs: research scripts, not included in this repository. |

The web-search budget for this run was exhausted and most publisher hosts failed DNS, so no further primary sources could be checked while writing this dossier. Every tag reflects what the research agents actually saw.

> **Resumo (PT).** A literatura de microestrutura (Kyle 1985; Evans-Lyons 2002; Cont-Kukanov-Stoikov 2014) liga *variações* de preço a *fluxo assinado*, não níveis a níveis. A forma correcta de pôr preço e CVD na mesma escala é exprimir ambos em **unidades-σ ancoradas** (equivalente ao mapeamento de Kyle com λ ajustado à volatilidade, λσ = σ(Δp)/σ(Δ)), calculadas sobre incrementos e de forma causal. As divergências medem-se com uma estatística **simétrica em unidades-σ** (janela K = 20), calibrada empiricamente (RMS não-centrado, M = 1000) e filtrada pela correlação dos incrementos (ρ ≥ 0,30). Em dados reais não há evidência robusta de que "fluxo sem preço" (absorção) ou "extremo sem fluxo" (exaustão) tenham direcção predefinida. Os rótulos devem ser neutros e resolvidos pelo preço. A qualidade do delta (footprint/1T/1S ≫ intrabar de 1 min ≫ barra do gráfico) condiciona tudo.

---

## 0. Decision register: how the conflicts between research streams were resolved

| # | Issue in conflict | Decision | Main basis |
|---|---|---|---|
| D1 | Display default (rolling z of levels, flow-implied price, or σ-units) | **Anchored σ-units**: both lines start at 0 at the anchor. Price is (ln P − ln O_a)/σ_r,a and flow is (CVD − CVD_a)/σ_d,a, with σ frozen at the anchor from the previous N bars. This is algebraically the Kyle/Evans-Lyons flow-implied price with λ = λσ, read in σ units. Also offered: price units (flow-implied price), rolling-window σ-units, and level z/min-max marked "visual only". | Kyle λσ; increments-based scale; avoids spurious levels statistics; shape-preserving (§5.4) |
| D2 | Divergence statistic | **C1 symmetric σ-unit K-sum**, with σ and ρ lagged one bar and σ-units winsorized at ±4. | Real-data and propagator calibration (§6.3) [E] |
| D3 | Standardization of the statistic | **Non-demeaned rolling RMS of the statistic over the previous M = 1000 bars** (500 acceptable, always ≥ 5N). Never a demeaned rolling z, never an analytic σ√n. | Demeaning erases persistent divergences in 20–50 bars and creates 9–19% wrong-sign alarms. Analytic scaling gives 10–18% null exceedance [E]. |
| D4 | Meaning of "flow > price" | **Direction-neutral labels** based on which leg led and on which side, for example "buy flow not lifting price". Direction comes only from price resolution (state machine). An optional "Directional lean" input defaults to Neutral. | No peer-reviewed forward-return test. Real data shows no robust effect. In simulation the sign depends on the unobservable informedness of the passive side [E]. |
| D5 | Patzelt-Bouchaud: absorption signal vs saturation artefact | No λ-ratio trigger. Winsorizing σ-units at ±4 is the concavity guard. A concave flow transform is optional and off by default. Impact efficiency is shown as context only. | A linear λ over-projects on climactic bars (Weber-Rosenow, square-root law) |
| D6 | Does the visual gap between lines mean anything? | The gap between the anchored σ-unit lines **is** the un-standardized cumulative symmetric residual. It is **context**. Signals come only from calibrated Z. Under ρ < 1 and long-memory flow, the CVD line naturally wanders further than price. | §5.2, §6.3 |
| D7 | Anchoring default | Display lines are **anchored**. Auto rule: chart ≤ 60 min → 1D; < 1D → 1W; 1D → 1M; ≥ 1W → 12M. RTH is an option. **All rolling statistics use continuous, reset-free increments.** Level-z mode uses a continuous CVD. | Avoids reset spikes inside 100-bar windows (5m RTH session = 78 bars) |
| D8 | Fallback when there are no intrabars | **Chart-bar BVC-Normal**, labelled "price-derived". Divergence and absorption are disabled on that tier. Never CLV, never the all-in sign rule. | Real data: CLV worst; chart-tier partial correlation with true delta given ΔP is about 0.1–0.4 [E] |
| D9 | Intrabar classifier default | **TradingView candle rule** (priceCalc, side carried across bars), plus the bid/ask quote rule on "1T". Per-intrabar BVC-Normal is an option. | Real data: candle rule ≥ BVC at 1S in 4 of 5 datasets; matches the built-in CVD [E] |
| D10 | Footprint architecture | **One script.** Footprint is an **opt-in** enum value and the single `request.footprint()` sits inside an `if`. **Never "Auto".** The tooltip warns that the script may stop with an error on plans below Premium. | Pine cannot read the plan or catch errors. The best evidence points to a runtime error, not na [V-sec] |
| D11 | Validity gate | ρ̂(r, Δ)ₜ₋₁ ≥ max(0.30, tanh(1.96/√(N−3))), **and** data tier ≥ medium. | Empirical null false-pass ≤ 0.5%. Fisher 0.196 passes 2.8–3.6% of the null because of heavy tails [E] |
| D12 | Mean-reversion gate | **No half-life label.** Optional rolling Dickey-Fuller t < −2.89 on the cumulative symmetric residual, off by default. | The half-life ≤ N/4 rule passes 88–97% of null windows by construction [E] |
| D13 | Price input | **ln(close)** increments in bps (×1e4). On session-first or gap bars use ln(close/open). Not hlc3. | Alignment with the bar's delta; numerical safety |
| D14 | Concave transform object | Optional, applied to **per-bar σ-unit flow** before summing. It is not the trade-level GOFI of Maitrier et al., which Pine cannot replicate. | §5.5 |
| D15 | Robust scale | No robust-z display mode in v1. Winsorizing the σ-units provides robustness. If MAD is ever used, it must be the exact array median (ta.dev is the *mean* absolute deviation, constant 1.2533). | normalization-stats |

---

## 1. Executive summary

**1. The literature relates price *changes* to *signed flow*, not levels to levels.**
- Kyle (1985) gives Δp = λ·y [V].
- Evans-Lyons (2002) regress daily FX changes on order flow. R² is above 60% and $1bn of flow moves the rate about 0.5% [V abstract; magnitudes V-sec].
- Cont-Kukanov-Stoikov (2014) find a linear relation between short-horizon mid-price changes and order-flow imbalance (OFI), with slope ∝ 1/depth [V abstract].
- Chordia-Roll-Subrahmanyam (2002) report adjusted R² 0.28 for daily S&P returns on contemporaneous NYSE imbalance [V full text].

The natural common scale for price and CVD is therefore the **price impact per unit of flow**, estimated on **increments**, causally and on a rolling basis (λ varies with depth, activity, time of day and news). Evans-Lyons' own Figure 1 overlays exchange-rate levels on cumulative order flow; that is the academic precedent for the requested pane.

**2. Vol-matched λσ = σ(Δp)/σ(Δ) is the right display mapping.**
- In Kyle's model Δp is an exact linear function of flow, so λ = σ(Δp)/σ(y).
- When both legs are noisy, the symmetric (reduced-major-axis, errors-in-variables) slope is the unbiased choice. Price carries public information that CVD cannot see, and CVD carries classification error.
- The OLS slope λ_ols = ρ·λσ shrinks the flow line toward flat whenever ρ is modest.
- Dividing both legs by their own σ gives **σ-units**, which is the same picture without currency units and is comparable across instruments (vol-scaling as in Patzelt-Bouchaud's rescaling and Moskowitz-Ooi-Pedersen ex-ante σ).

**3. Never normalize, correlate or regress the *levels* independently.**
- Price and CVD are integrated series. For two independent random walks, E[r²] of the level correlation is 0.2405 (Ernst-Shepp-Wyner 2017 [V]), so |r| > 0.5 occurs about 40% of the time.
- The difference of two rolling level z-scores exceeds |2| about 33% of the time, with a fake half-life of N/4 [E; Granger-Newbold, Phillips V].
- Levels cointegration is regime-specific (Killeen-Lyons-Moore: FF/DM before EMU [V abstract; cointegration details V-sec]). In theory the levels residual is I(1), because public information and limit-order price discovery are part of price but not of CVD.

**4. CVD sees only part of the flow, and "flow without price" is the normal state.**
- CVD is *trade* imbalance only. CKS report that it explains less than book OFI; the 65% vs 32% R² figures are not confirmed from the primary tables.
- Order signs have long memory (Lillo-Farmer: γ ≈ 0.6) [V].
- Impact is transient and concave (Bouchaud et al. 2004 [V full]; Weber-Rosenow 2005: actual impact is a quarter of book-implied, G = 0.48·Q^0.76 [V full]).
- CVD therefore trends and runs ahead of price even when no information is involved.

**5. Data quality dominates everything.** On real aggressor-flagged data [E], correlation with true per-bar delta at 5 minutes was:

| Delta source | Correlation with true delta (5m) |
|---|---|
| 1-second intrabars, TradingView candle rule | 0.71–0.90 |
| 1-minute intrabars | 0.46–0.90 |
| Chart-bar estimates | 0.24–0.83 |

What matters for divergence is the part of delta *not* explained by price, i.e. the partial correlation given ΔP:
- 1S tier: 0.80–0.88.
- 1-minute tier: 0.29–0.87.
- Chart tier: usually 0.1–0.4. A chart-only CVD is close to a volume-weighted copy of price.

Signed absorption recall was about 0.8 with 1S or 1T data, 0.43–0.64 with 1-minute data and 0.00–0.33 with chart data. `request.footprint()` is classified by TradingView "based on intrabar price action" [V-sec, manual mirror], not from exchange aggressor flags.

**6. The calibrated divergence statistic.**

$$Z_t = \frac{\sum_{i=t-K+1}^{t}\big(\mathrm{clip}(u_{r,i}) - \mathrm{clip}(u_{d,i})\big)\big/\sqrt{2K(1-\hat\rho_{t-1})}}{\mathrm{RMS}_{M}(\cdot)_{t-1}}$$

- K = 20, M = 1000, σ and ρ over N = 100 bars, lagged one bar.
- On 4 months of real BTC aggressor data the null P(|Z| > 2) is 5.6–5.9% and P(|Z| > 3) about 1.1% [E].
- Persistent divergences stay visible for hundreds of bars.

**7. Interpretation must be honest.** There is no peer-reviewed evidence that absorption (flow without price) or exhaustion (an extreme without flow) has a default direction.
- The only effect that holds up is that **confirmed** flow pressure partially reverses (CRS 2002 lagged-imbalance coefficients −4.56 and −5.83 conditional on current imbalance [V full]).
- On one BTC venue, in-sample, 15-minute absorbed and "pinned" windows were followed by a weak **continuation in the aggressor's direction** over 30 minutes: +7.7 bps (CI 1.5–13.7) and +14.6 bps (CI 7.8–22.3) [E]. This disappeared when delta was estimated from 1-minute intrabars.
- The indicator therefore labels events neutrally and lets **price resolve them**.

---

## 2. Annotated bibliography

Only real sources are listed. URLs are given where the research streams recorded them.

### 2.1 Price impact and order-flow theory

- **Kyle, A.S. (1985).** Continuous Auctions and Insider Trading. *Econometrica* 53(6):1315–1335. **[V]** (abstract and lecture-slide form). Prices are linear in net order flow, Δp = λy, and depth is 1/λ. Static model: λ = ½√(Σ0/σu²), falling with noise-trading variance. The continuous-time formula λ = σv/(σu√T) is **[M]**. *Use:* the theoretical basis for the vol-matched mapping. https://www.econometricsociety.org/publications/econometrica/browse/1985/11/01/continuous-auctions-and-insider-trading
- **Glosten, L., Milgrom, P. (1985).** Bid, ask and transaction prices… *JFE* 14:71–100. **[V]** (abstract). Adverse selection alone produces a spread, and the trade sign is informative. https://ideas.repec.org/p/nwu/cmsems/570.html
- **Hasbrouck, J. (1991).** Measuring the Information Content of Stock Trades. *JF* 46(1):179–207. **[V]** (abstract). Information content is the permanent impact of the trade *innovation*. Impact is concave in size and arrives with a lag. *Use:* the optional "flow surprise" idea; the concavity guard. https://ideas.repec.org/a/bla/jfinan/v46y1991i1p179-207.html
- **Cont, R., Kukanov, A., Stoikov, S. (2014).** The Price Impact of Order Book Events. *J. Fin. Econometrics* 12(1):47–88. **[V]** abstract: linear in OFI, slope ∝ 1/depth, robust across time scales and stocks; the trade-volume relation is "noisy and less robust". The figures of average R² ≈ 65% for OFI vs ≈ 32% for trade imbalance are **[V-sec, conflicting status, not confirmed from primary tables]**. *Use:* time-varying λ; CVD is only part of the flow. https://arxiv.org/abs/1011.6402
- **Cont, R., Cucuringu, M., Zhang, C. (2023).** Cross-impact of order flow imbalance in equity markets. *Quant. Finance* 23(10):1373–1393. **[V]** abstract: integrated multi-level OFI beats best-level OFI, and cross-impact adds nothing contemporaneously. The 87/71/33% R² figures are **unverified**. https://arxiv.org/abs/2112.13213
- **Xu, K., Gould, M.D., Howison, S.D. (2019).** Multi-Level Order-Flow Imbalance in a Limit Order Book. **[V]** Fit improves with each added depth level. https://arxiv.org/abs/1907.06230
- **Kolm, P.N., Turiel, J., Westray, N. (2023).** Deep order flow imbalance. *Math. Finance* 33(4). **[V]** abstract: order-flow inputs beat raw book states, and the forecast horizon is about 2 average price changes. https://papers.ssrn.com/abstract=3900141
- **Lillo, F., Farmer, J.D. (2004).** The long memory of the efficient market. *SNDE* 8(3). **[V]** Sign ACF ~ τ^−0.6 (H ≈ 0.7). *Use:* CVD is super-diffusive, so √K scaling fails and empirical calibration is needed. https://arxiv.org/abs/cond-mat/0311053
- **Lillo, F., Mike, S., Farmer, J.D. (2005).** Theory for long memory in supply and demand. *PRE* 71:066122. **[V]** abstract. Splitting of power-law metaorders produces long memory in signs. https://arxiv.org/abs/cond-mat/0412708
- **Bouchaud, J.-P., Gefen, Y., Potters, M., Wyart, M. (2004).** Fluctuations and response in financial markets. *Quant. Finance* 4(2):176–190. **[V full text, local]** Propagator model. Prices are diffusive iff 2β + γ = 1 (β_c = (1−γ)/2; for FT, γ ≈ 1/5 and β_c ≈ 2/5). Persistent market orders are balanced by mean-reverting limit orders. https://arxiv.org/abs/cond-mat/0307332
- **Bouchaud, J.-P., Kockelkoren, J., Potters, M. (2006).** Random walks, liquidity molasses and critical response. *Quant. Finance* 6(2). **[V]** abstract: transient impact. https://arxiv.org/abs/cond-mat/0406224
- **Eisler, Z., Bouchaud, J.-P., Kockelkoren, J. (2012).** The price impact of order book events: market orders, limit orders and cancellations. *Quant. Finance*. **[V]** (local text). Limit orders and cancellations carry impact, so trades-only models imply transient impact. https://arxiv.org/abs/0904.0900
- **Weber, P., Rosenow, B. (2005).** Order book approach to price impact. *Quant. Finance* 5(4). **[V full text, local]** On 5-minute Island ECN data, G = 0.48·Q^0.76 (R² = 0.997). The impact implied by the visible book is **four times** the actual impact, because limit-order flow is anticorrelated with returns. This is the quantitative account of "absorption as the normal state". https://arxiv.org/abs/cond-mat/0311457
- **Plerou, V., Gopikrishnan, P., Gabaix, X., Stanley, H.E. (2002).** Quantifying stock-price response to demand fluctuations. *PRE* 66:027104. **[V]** abstract: concave conditional impact. https://arxiv.org/abs/cond-mat/0106657
- **Patzelt, F., Bouchaud, J.-P. (2018).** Universal scaling and nonlinearity of aggregate price impact. *PRE* 97:012304. **[V]** abstract: a universal sigmoidal (saturating) aggregate impact, linear for small imbalance. The phrasing that the price is "pinned" at extreme imbalance comes from one stream **[V-sec]**. The exponents ξ ≈ 0.84 and ψ ≈ 0.53 are **unverified**. No forward test. https://arxiv.org/abs/1706.04163
- **Tóth, B. et al. (2011).** Anomalous price impact and the critical nature of liquidity. *PRX* 1:021006. **[V]** abstract: square-root metaorder impact I ≈ Y·σ·√(Q/V). https://arxiv.org/abs/1105.1694
- **Sato, Y., Kanazawa, K. (2025).** Strict universality of the square-root law… *PRL* 135:257401. **[V]** abstract: δ = ½ across the TSE. https://arxiv.org/abs/2411.13965
- **Farmer, J.D., Gerig, A., Lillo, F., Waelbroeck, H. (2013).** How efficiency shapes market impact. *Quant. Finance* 13. **[V]** abstract: permanent impact is about 2/3 of peak. https://arxiv.org/abs/1102.5457
- **Bershova, N., Rakhlin, D. (2013).** The non-linear market impact of large trades. *Quant. Finance* 13(11). **[V]** (stream summary). Impact relaxes to about 2/3 of the last-fill impact.
- **Donier, J., Bonart, J. (2015).** A million metaorder analysis of market impact on the Bitcoin. **[V]** abstract: the square-root law holds on BTC. https://arxiv.org/abs/1412.4503
- **Maitrier, G., Loeper, G., Bouchaud, J.-P. (2025/26).** Square-root impact, order imbalance & volatility. *Quant. Finance* 26(6). **[V]** abstract: for the generalized OFI Σε·v^a, the correlation with returns peaks at an interior a, so plain volume weighting (a = 1) is not optimal. https://arxiv.org/abs/2506.07711
- **Bugaenko, A. (2020).** Empirical Study of Market Impact Conditional on Order-Flow Imbalance. **[V]** Linear at small imbalance. https://arxiv.org/abs/2004.08290
- **Çetin, U., Lin, M., Livieri, G. (2026).** When large trades are not (automatically) news. **[V]** abstract: heavy-tailed noise flow flattens and concavifies impact. https://arxiv.org/abs/2607.01198
- **Kyle, A.S., Obizhaeva, A.A. (2016).** Market Microstructure Invariance: Empirical Hypotheses. *Econometrica* 84(4). **[V]** abstract. The exact impact formula is not confirmed. https://ideas.repec.org/a/wly/emetrp/v84y2016ip1345-1404.html
- **Elomari-Kessab, S., Maitrier, G., Bonart, J., Bouchaud, J.-P. (2024).** Microstructure Modes. **[V]** abstract. https://arxiv.org/abs/2405.10654
- **Amihud, Y. (2002).** Illiquidity and stock returns. *JFM* 5:31–56. **[V]** ILLIQ = mean |r|/$Vol. *Use:* an unsigned λ fallback idea only. https://www.cis.upenn.edu/~mkearns/finread/amihud.pdf

### 2.2 Order flow vs returns: horizons, levels, predictability

- **Evans, M.D.D., Lyons, R.K. (2002).** Order Flow and Exchange Rate Dynamics. *JPE* 110(1):170–180. **[V]** abstract. R² > 60% (DM/$). $1bn of net purchases moves the rate about 0.5%. Figure 1 overlays rate levels on cumulative flow **[V-sec]**. https://www.nber.org/papers/w7317
- **Evans, M.D.D., Lyons, R.K. (2005).** Meese-Rogoff redux. *AER* 95(2). **[V]** abstract: the micro model beats the random walk from 1 day to 1 month.
- **Killeen, W.P., Lyons, R.K., Moore, M.J. (2006).** Fixed versus flexible: Lessons from EMS order flow. *JIMF* 25(4):551–579. **[V]** abstract: persistent flow effects before EMU, decoupling afterwards. Johansen cointegration and 3bp per DM1bn are **[V-sec]** only. https://www.nber.org/papers/w8491
- **Berger, D. et al. (2008).** Order flow and exchange rate dynamics in EBS data. *JIE* 75(1):93–109. **[V]** abstract: a strong relation from 1 minute to 2 weeks, weaker beyond; stronger when liquidity is low. https://www.federalreserve.gov/econres/ifdp/order-flow-and-exchange-rate-dynamics-in-electronic-brokerage-system-data.htm
- **Payne, R. (2003).** Informed trade in spot FX markets. *JIE* 61(2). **[V]** (summary). Trades explain about 40% of permanent price variation.
- **Chinn, M.D., Moore, M.J. (2011).** Order flow and the monetary model of exchange rates. *JMCB* 43(8). **[V]** (summary).
- **Sager, M., Taylor, M.P. (2008).** Commercially available order flow data… *JMCB* 40(4). **[V-sec]** Little forecasting value.
- **Rime, D., Sarno, L., Sojli, E. (2010).** Exchange rate forecasting, order flow and macroeconomic information. *JIE* 80(1). **[V]** abstract.
- **Chordia, T., Roll, R., Subrahmanyam, A. (2002).** Order imbalance, liquidity, and market returns. *JFE* 65:111–130. **[V full text, local]**
  - Contemporaneous imbalance: adjusted R² 0.28.
  - Lagged imbalance, conditional on current imbalance: −4.56 (buy side, t −13.1) and −5.83 (sell side, t −5.1). Inventory reversal.
  - Unconditionally, lagged imbalance does not predict.
  - Sell-side impact is about 3× buy-side.
  - Reversal after large-sell days: serial correlation −0.29.
  - https://ideas.repec.org/a/eee/jfinec/v65y2002i1p111-130.html
- **Chordia, T., Subrahmanyam, A. (2004).** Order imbalance and individual stock returns. *JFE* 72:485–518. **[V-sec]** Lagged imbalance is positive, and turns negative once current imbalance is controlled for. https://academicnewsletter.sufe.edu.cn/info/357679
- **Chordia, T., Roll, R., Subrahmanyam, A. (2005).** Evidence on the speed of convergence to market efficiency. *JFE* 76(2):271–292. **[V]** abstract-level: absorbed in more than 5 but less than 60 minutes. *Use:* the event lifetime of about 60 minutes.
- **Hendershott, T., Menkveld, A.J. (2014).** Price pressures. *JFE* 114(3):405–423. **[V-sec]** (abstract via aggregator). Average 0.49%, half-life 0.92 days. https://ideas.repec.org/p/zbw/cfswop/201014.html
- **Deuskar, P., Johnson, T.C. (2011).** Market liquidity and flow-driven risk. *RFS* 24(3). **[V]** (summary). Flow-driven risk is about half of variance and persistent.
- **Froot, K.A., Ramadorai, T. (2005).** Currency returns, intrinsic value, and institutional-investor flows. *JF* 60(3). **[V]** (summary).
- **Hasbrouck, J., Seppi, D. (2001).** Common factors in prices, order flows, and liquidity. *JFE* 59. **[V]** https://archive.nyu.edu/handle/2451/26848
- **Dufour, A., Engle, R.F. (2000).** Time and the price impact of a trade. *JF* 55(6). **[V-sec]** (via citing paper). Impact rises when trading is faster. https://ideas.repec.org/a/bla/jfinan/v55y2000i6p2467-2498.html
- **Takahashi, M. (2025).** Returns and Order Flow Imbalances: intraday dynamics and macro news. **[V]** abstract: news raises price impact. https://arxiv.org/abs/2508.06788
- **Kaniel, R., Liu, H. (2006).** So what orders do informed traders use? *J. Business* 79(4). **[V]** abstract: informed traders may prefer limit orders. Unconditional; no absorption event study. https://ideas.repec.org/a/ucp/jnlbus/v79y2006i4p1867-1914.html
- **Brogaard, J., Hendershott, T., Riordan, R. (2019).** Price discovery without trading. *JF* 74(4). **[V]** (summary). Limit orders supply most price discovery.
- **Frey, S., Sandås, P. (2009 WP / 2017).** The impact of iceberg orders in limit order books. **[V]** (WP summary): icebergs attract market orders and reduce their impact. The direction of the subsequent price move is **unverified**.
- **Campbell, J.Y., Grossman, S.J., Wang, J. (1993).** *QJE* 108(4). **[V]** (summary). High-volume declines tend to reverse.
- **Llorente, G., Michaely, R., Saar, G., Wang, J. (2002).** *RFS* 15(4). **[V]** (summary). Hedging volume reverses; speculative volume continues.
- **Silantyev, E. (2019).** Order flow analysis of cryptocurrency markets. *Digital Finance* 1. **[V]** abstract: on BitMEX, trade-flow imbalance (CVD increments) explains contemporaneous price changes better than OFI. https://ideas.repec.org/a/spr/digfin/v1y2019i1d10.1007_s42521-019-00007-w.html
- **Makarov, I., Schoar, A. (2020).** Trading and arbitrage in cryptocurrency markets. *JFE* 135(2). **[V]** The common cross-exchange signed-volume component explains about 80% of BTC returns. https://personal.lse.ac.uk/makarov1/index_files/CryptocurrencyMarkets.pdf
- **Bessembinder, Panayides & Venkataraman (2009) [M]; Osler (2003) [M]; Kavajecz & Odders-White (2004) [M]; Menkhoff et al. (2016) [M]; Pastor & Stambaugh (2003) [M].** Cited only for qualitative context (§6.8). Do not quote their numbers.

### 2.3 Trade classification and delta estimation

- **Lee, C.M.C., Ready, M.J. (1991).** *JF* 46(2):733–746. **[V]** abstract: quote rule with tick fallback and a 5-second quote delay. https://ideas.repec.org/a/bla/jfinan/v46y1991i2p733-46.html
- **Ellis, K., Michaely, R., O'Hara, M. (2000).** *JFQA* 35(4). **[V]** Accuracy on Nasdaq: quote rule 76.4%, tick rule 77.66%, Lee-Ready 81.05%. Defines the EMO rule.
- **Finucane, T.J. (2000).** *JFQA* 35(4). **[V]** Lee-Ready is about equal to the tick test.
- **Odders-White, E.R. (2000).** *JFM* 3. **[M]**
- **Chakrabarty, B., Li, B., Nguyen, V., Van Ness, R.A. (2007).** *JBF* 31. **[V]** (rule definition via reference implementation). The CLNV rule.
- **Easley, D., López de Prado, M., O'Hara, M. (2012).** Flow toxicity and liquidity in a high-frequency world. *RFS* 25(5):1457–1493. **[V full text]** (accepted manuscript).
  - Eq. 7: V^B = Σ V_i·Z((P_i − P_{i−1})/σ_ΔP), with **raw** price changes and Z the **Normal** CDF.
  - The σ window is not stated.
  - One-minute time bars, buckets of ADV/50, E-mini S&P 500, 2008–2011.
  - VPIN "is not a directional indicator".
  - https://papers.ssrn.com/abstract=1695596
- **Easley, D., López de Prado, M., O'Hara, M. (2016).** Discerning information from trade data. *JFE* 120(2):269–285. **[V]** abstract: the tick rule and BVC are both reasonable; BVC links better to information proxies. Student-t with df = 0.25 is **[V-sec]**, from a third-party verbatim quote of footnote 7. https://ideas.repec.org/a/eee/jfinec/v120y2016i2p269-285.html
- **Chakrabarty, B., Pascual, R., Shkilko, A. (2015).** *JFM* 25:52–79. **[V]** abstract: the tick rule and Lee-Ready beat BVC. BVC accuracy peaks at about 79.7% on 1-hour bars **[V-sec]**. https://www.sciencedirect.com/science/article/abs/pii/S1386418115000415
- **Andersen, T.G., Bondarenko, O. (2015).** *Review of Finance* 19(1). **[V]** abstract: BVC is worse than the tick rule, and its errors are correlated with volume and volatility. https://ideas.repec.org/a/oup/revfin/v19y2015i1p1-54..html
- **Pöppe, T., Moos, S., Schiereck, D. (2016).** *JBF* 73. **[V]** VPIN is very sensitive to the classifier.
- **Panayides, M.A., Shohfi, T.D., Smith, J.D. (2019).** *JBF* 103. **[V]** BVC calibrated out of sample does better.
- **Massot, M., Nawn, S., Pascual, R. (2018 WP).** **[V]** BVC accuracy is 92.4% on 5-minute bars and 50.9% on 1-second bars. That the t distribution beats the Normal is a **probable** attribution only.
- **Jurkatis, S. (2022).** Inferring trade directions in fast markets. *JFM* 58. **[V]** https://ideas.repec.org/p/boe/boeewp/0896.html
- **Siqueira, L. et al. (2023).** *BBR* 20(1). **[V]** In Brazil the tick rule beats BVC.
- **Abramowitz, M., Stegun, I.A. (1964).** Eqs 7.1.26 and 26.2.17. **[V]** Coefficients confirmed; numerically re-validated. https://www.johndcook.com/python_erf.html
- **Bowling, S.R. et al. (2009).** A logistic approximation to the cumulative normal. *JIEM* 2(1). **[V]** https://jiem.org/index.php/jiem/article/view/60
- **Jurkatis reference code**, jktis/Trade-Classification-Algorithms. **[V]** https://github.com/jktis/Trade-Classification-Algorithms
- **Fedenia, M., Ronen, T., Nam, S.** (SSRN 3848068). **[V]** A secondary account of ELO 2016 (price differences, full-sample σ with look-ahead) and of CPS 2015 accuracy ranges.

### 2.4 Statistics: spurious regression, normalization, calibration

- **Granger, C.W.J., Newbold, P. (1974).** Spurious regressions in econometrics. *J. Econometrics* 2. **[V]** https://gwern.net/doc/economics/1974-granger.pdf
- **Phillips, P.C.B. (1986).** Understanding spurious regressions in econometrics. *J. Econometrics* 33. **[V]** https://econpapers.repec.org/RePEc:cwl:cwldpp:757
- **Ernst, P.A., Shepp, L.A., Wyner, A.J. (2017).** Yule's "nonsense correlation" solved! *Ann. Stat.* 45(4). **[V]** E[θ²] = 0.240522. https://www.ma.imperial.ac.uk/~pernst/AOS1509.pdf
- **Engle, R.F., Granger, C.W.J. (1987).** Co-integration and error correction. *Econometrica* 55(2). **[V]** abstract.
- **MacKinnon, J.G. (2010).** Critical values for cointegration tests. QED WP 1227. **[M]** Our Monte Carlo at T = 100 gives an Engle-Granger 5% value of −3.40 and a Dickey-Fuller 5% value of −2.88 [E].
- **Avellaneda, M., Lee, J.-H. (2010).** Statistical arbitrage in the U.S. equities market. *Quant. Finance* 10(7). **[V full text]** Cumulative residuals with an OU s-score. The in-sample X_60 = 0 artefact. Their filter passes 98.6% of null windows [E]. https://math.nyu.edu/~avellane/AvellanedaLeeStatArb071008.pdf
- **Gatev, E., Goetzmann, W.N., Rouwenhorst, K.G. (2006).** Pairs trading. *RFS* 19. **[V-sec]** Precedent for anchored co-normalization.
- **Rousseeuw, P.J., Croux, C. (1993).** *JASA* 88. **[V]** MAD has 37% Gaussian efficiency.
- **Shiffler, R.E. (1988).** Maximum Z scores and outliers. *Am. Stat.* 42(1). **[V]** With population sd, |z| ≤ √(N−1).
- **Fisher, R.A. (1915).** z-transformation. **[V-sec]** (authoritative summary): atanh(r)·√(N−3) ~ N(0,1).
- **Finch, T. (2009).** Incremental calculation of weighted mean and variance. **[V]** The EWMA variance recursion.
- **Andersen, T.G., Bollerslev, T. (1997).** Intraday periodicity and volatility persistence. *JEF* 4. **[V]**
- **Slutzky, E. (1937).** The summation of random causes as the source of cyclic processes. *Econometrica* 5(2). **[V]** (summary).
- **Kendall, M.G. (1954).** AR(1) bias ≈ −(1+3φ)/N. **[M]**, confirmed by our Monte Carlo [E].
- **Moskowitz, T.J., Ooi, Y.H., Pedersen, L.H. (2012).** Time series momentum. *JFE* 104. **[M]** Ex-ante EWMA σ scaling.
- **Bartlett/Quenouille effective sample size**, summarized in arXiv 2401.02387. **[V]**

### 2.5 Platform, practitioner and Pine sources

- **Pine Script v6 Reference & User Manual** (local copy plus GitHub mirrors). **[V]** Covers `request.footprint`, `request.security_lower_tf`, the limits, `input.*(…, active)`, `timeframe.change(series string)`, `session.isfirstbar_regular`, and `footprint.total_volume()`.
  - https://github.com/codenamedevan/pinescriptv6
  - https://github.com/chris-c-thomas/pine-script-v6-md
  - https://github.com/folknor/pine-tools
  - https://github.com/TradersPost/pinescript-agents
- **TradingView `ta` library v12 (2025.12.06), MPL-2.0.** **[V source]**
  - `requestUpAndDownVolume(series string)` and `requestVolumeDelta(series string, series string = "")`.
  - Quote rule on "1T"; candle rule then tick rule then carried side otherwise.
  - Local copy kept with the research material (not included). Mirror: https://github.com/alvinng214/S1_Silver_Bullet/blob/main/S1_Silver_Bullet/ta.txt
  - v14 is referenced by practitioner code, but its source was not seen.
- **TradingView Help Center: Volume Delta / CVD (43000725057 / 43000725058).** **[V-sec]** (search snippets). Auto lower timeframe: 1S on seconds charts, 1 intraday, 5 daily, 60 otherwise. Anchor "1D". https://www.tradingview.com/support/solutions/43000725058-cumulative-volume-delta/
- **TradingView/LucF CVD Candles v8 and CVD Chart v3 (2026).** **[V source mirror]** Reset modes, coverage info box, and a warning when there are fewer than 5 intrabars per bar.
- **Community scripts** (LuxAlgo Volume Delta Methods, Detrended CVD, CVD Momentum Divergence, Elite CVD, Delta Bubble + Absorption, casoon CVD Bias). **[V source mirror]** Prior-art normalizations (min-max overlay, z of levels) and documented bugs (requiring simultaneous pivots in price and CVD).
- **ata_sabanci VFP-Intro (2026).** **[V source mirror]** The `if`-gated single `request.footprint()` pattern, and the claim that the script "stops with an error" on lower plans. https://github.com/venkatalokeshanne/trading_strategies_indicators/blob/main/TradingView/indicators/Tm1cGCPD-Volume-Footprint-Measuring-by-Math-Geometry.pine
- **LuxAlgo PineTS footprint coverage notes.** **[V]** TradingView rejects a second call site even if it never executes. Footprints over 2000 rows return na. https://github.com/LuxAlgo/PineTS/blob/main/docs/api-coverage/footprint.md
- **Sierra Chart** (Studies8.cpp) and **ATAS** (CumulativeDelta.cs) source. **[V]** True ask-minus-bid delta, reset per trading day or session, rolling options.
- **Tucsky/aggr.** **[V]** Multi-venue crypto CVD = cum(vbuy − vsell). https://github.com/Tucsky/aggr
- **mcart13/tvaudible pricing parse (2026-09-29).** **[V-sec]** Second-based intervals are Premium/Ultimate; tick-based intervals are Ultimate only.

### 2.6 Own empirical work in this run [E]

1. **Synthetic trade-classification Monte Carlo** (research scripts, not included). Shows the ordering only. **Superseded by the real-data study wherever they disagree.**
2. **Normalization Monte Carlo** (research scripts, not included). Null distributions of level z-scores and spreads, half-life artefacts, numerics.
3. **Real-data estimator fidelity** (research scripts, not included).
   - Binance BTCUSDT spot (2025-03-01), BTC and ETH perpetuals (2025-10-10 crash day), BTCFDUSD spot (117 days, 2026-04 to 07).
   - LOBSTER AMZN/MSFT/GOOG (2012-06-21).
   - All with true aggressor flags.
4. **Divergence calibration** (research scripts, not included). BTCFDUSD 5m/15m with true delta, plus a propagator simulation (γ = 0.6, capped-price hidden liquidity).
5. **Forward-return event study** (research scripts, not included). BTCFDUSD, 117 days, day-clustered t and day-block bootstrap.

All are in-sample, mostly on one venue, and not peer-reviewed.

---

## 3. Delta estimation

### 3.1 What Pine can access: the data ladder

| Tier | Source | Pine access | Plan / coverage | Quality code |
|---|---|---|---|---|
| A | `request.footprint(ticks_per_row)` → `footprint.delta()`, `footprint.total_volume()` | One call site per script | Premium/Ultimate only [V]. History depth undocumented. Classified "based on intrabar price action" [V-sec manual mirror], not from exchange aggressor flags. | **High** |
| B | "1T" intrabars with `bid`/`ask` → quote rule (EMO-like, mid fallback), then tick rule | `request.security_lower_tf(…, "1T", …)` | Tick intervals Ultimate-only [V-sec]. Capped at 100K/125K/200K intrabars, i.e. ticks, which is hours on liquid futures. Whether historical quotes are present is **unverified**. | **High** |
| C | "1S" intrabars → TradingView candle rule | same call, "1S" | Premium+ [V-sec]. About 28 h of liquid crypto under the 100K cap; about 205 h on a thin pair [E]. | **High** |
| D | "1" (1-minute) intrabars → candle rule (or per-intrabar BVC-Normal) | same call, "1" | All plans. About 69 days of 24/7 data under 100K. | **Medium** |
| E | Chart bars only → BVC-Normal on the bar | none | Always available | **Low, price-derived** |

The intrabar caps (100K on Basic through Premium, 125K Expert, 200K Ultimate) apply to **both** `request.security` and `request.security_lower_tf` on lower timeframes (Pine v6 User Manual, «Limitations» page) [V]. Older chart bars therefore get no intrabars; the indicator must detect this and fall back visibly.

### 3.2 Real-data fidelity (true aggressor delta) [E]

**Correlation of the estimate with true per-bar delta, 5-minute bars**

| Estimator | BTCFDUSD (117 d) | BTC spot (1 d) | BTC perp (crash d) | ETH perp (crash d) | LOBSTER (1 d) |
|---|---|---|---|---|---|
| 1T tick rule | .85 | .96 | 1.00 | .99 | .79 |
| **1S candle rule (TV)** | **.90** | .83 | .90 | .90 | .71 |
| 1S BVC-Normal | .77 | .52 | .91 | .82 | .70 |
| **1m candle rule (TV)** | **.74** | .65 | .77 | .90 | .54 |
| 1m BVC-Normal | .73 | .46 | .79 | .89 | .62 |
| Chart-bar BVC-Normal | .52 | .47 | .83 | .69 | .61 |
| Chart-bar all-in sign rule | .49 | .53 | .81 | .68 | .54 |
| Chart-bar CLV | .42 | .24 | .49 | .51 | .60 |

On the FDUSD data, day-block bootstrap 95% intervals are about ±0.03–0.06. The single-day sets (284 bars at 5m) carry roughly ±0.05–0.10 sampling error.

**Circularity: the property a divergence statistic depends on**
- True delta correlates 0.37–0.66 with ΔP at 5m. The estimates are inflated: 1S slightly (FDUSD 0.44 vs 0.39), 1m moderately (0.52–0.94), chart tier strongly (0.58–0.94).
- Partial correlation of the estimate with true delta given ΔP, i.e. the fidelity of the divergence residual:
  - 1S candle rule: 0.80–0.88 in crypto.
  - 1m: 0.29–0.87.
  - Chart tier: −0.31 to 0.78, typically 0.1–0.4.
- The earlier synthetic claim that estimates correlate 0.95–0.98 with ΔP holds only on crash days.

**CVD tracking within a UTC-day anchor (FDUSD, 5m), mean path correlation with true CVD**

| Source | Path correlation |
|---|---|
| 1S candle rule | 0.86 |
| 1T | 0.82 |
| 1S BVC | 0.75 |
| 1m candle rule | 0.76 |
| 1m BVC | 0.72 |
| Chart tier | 0.45–0.63 |
| **Price path alone (baseline)** | **0.59** |

Chart-only CVD adds nothing beyond price.

**Signed absorption recall (FDUSD)**
- Absorption bars: top-decile |true delta| with bottom-tercile |ΔP|. There are 436, 172 and 42 such bars at 5m, 15m and 60m. Chance recall is about 0.04.

| Source | Recall at 5m / 15m / 60m |
|---|---|
| 1S candle rule | 0.81 / 0.83 / 0.76 |
| 1T | 0.78 / 0.81 / 0.86 |
| 1S BVC | 0.53 / 0.51 / 0.33 |
| 1m candle rule | 0.56 / 0.60 / 0.64 |
| 1m BVC | 0.43 / 0.55 / 0.45 |
| Chart BVC | 0.03 / 0.03 / 0.00 |
| Chart all-in rule | 0.33 / 0.30 / 0.17 (sign right only about 55% of the time) |
| CLV | 0.12–0.22 |

**Settings that barely matter.**
- Δprice vs Δlog-price changes results by ≤ 0.003.
- The σ window (20, 100, 500 or full sample) changes results by ≤ 0.05; the full-sample σ, which looks ahead, is not better.
- Normal vs t(0.1, 0.25, 1) mostly changes the *scale*: t(0.25) gives about 0.3–0.5× the true dispersion.
- The chart all-in rule overstates magnitude 1.5–9.5×.

**Why the synthetic ranking reversed.** At 1 second, volume inside each intrabar is very one-sided: 95% on the thin pair and 57% on the busy crash day. A sign rule therefore loses little information, while BVC's F(0) = 0.5 discards every flat second.

### 3.3 Methods, ranked, with exact formulas

**(1) Footprint delta (tier A).**
- Δ_t = `footprint.delta(fp)`.
- Normalize by `footprint.total_volume(fp)`, **not** by `volume`. On 1D and higher the two "might differ significantly" because EOD feeds include block and OTC trades [V-sec manual].
- *Use when:* the user is on Premium or Ultimate and explicitly selects Footprint.
- Caveat: TradingView's classification rule is undocumented beyond "intrabar price action".

**(2) "1T" quote rule with tick fallback (tier B).** This is the TradingView `ta` v12 rule, verbatim logic, applied per trade:

$$s_i=\begin{cases}+1 & p_i\ge \text{ask}_i\\ -1 & p_i\le\text{bid}_i\\ \operatorname{sign}(p_i-m_i) & \text{otherwise, } m_i=(\text{bid}_i+\text{ask}_i)/2\\ \text{candle/tick rule} & \text{if bid=ask, }p_i=m_i\text{ or quotes are na}\end{cases}\qquad \Delta=\sum_i s_i v_i$$

Related rules for reference:
- EMO: buy at the ask, sell at the bid, tick rule otherwise.
- Lee-Ready: compare with the mid, tick rule at the mid.
- CLNV: top or bottom 30% of the spread, tick rule in the middle.

*Use when:* a "1T" lower timeframe is selected and the plan allows it.

**(3) TradingView candle rule (default classifier for intrabar tiers C/D).** Per intrabar j, with the side **carried across chart bars** (never reset):

$$s_j=\begin{cases}+1 & C_j>O_j\\-1 & C_j<O_j\\+1 & C_j=O_j,\ C_j>C_{j-1}\\-1 & C_j=O_j,\ C_j<C_{j-1}\\ s_{j-1}&\text{otherwise}\end{cases}\qquad \hat\Delta_{\text{bar}}=\sum_{j\in\text{bar}}s_jV_j$$

This is BVC in the limit σ → 0 (a step CDF). It is the best or tied bar-based estimator at 1S in 4 of 5 real datasets, and it matches the built-in CVD.

**(4) Per-intrabar BVC (option).** Easley-López de Prado-O'Hara (2012), adapted to time intrabars with a causal σ:

$$\hat\Delta_{\text{bar}}=\sum_{j}V_j\big(2F(z_j)-1\big),\quad z_j=\mathrm{clip}\!\left(\frac{\Delta C_j}{\sigma_{j}},\pm10\right),\quad \sigma_j=\mathrm{stdev}_{100}(\Delta C)\ \text{(in the LTF context)}$$

- ΔC_j = C_j − O_j on session-first intrabars (gap guard), else C_j − C_{j−1}.
- F = Φ (Normal; ELO 2012 [V]).
- Student-t(ν) is optional but **not recommended**: it only shrinks the scale (F(1): Normal 0.841, t(0.25) 0.644, t(1) 0.750, t(5) 0.818).
- Our implementation (time intrabars, rolling σ) is an **adaptation**. Do not label it "the ELO specification", which used volume buckets of ADV/50 and an unstated σ window.

**(5) Chart-bar BVC-Normal (tier E fallback).**

$$\hat\Delta_t=V_t\big(2\Phi(z_t)-1\big),\ z_t=\mathrm{clip}(r_t/\sigma_{r,t-1},\pm10),\ r_t=10^4\ln\frac{C_t}{C_{t-1}}\ \Big(10^4\ln\frac{C_t}{O_t}\text{ on gap bars}\Big)$$

- A gap bar is `session.isfirstbar` or |10⁴·ln(O_t/C_{t−1})| > 3σ_{t−1}.
- This is the best chart-only estimator (0.47–0.83). It is **price-derived**: divergence and absorption are disabled on this tier.

**Not used.**
- CLV, Δ = V·(2C−H−L)/(H−L): worst on real data, with negative partial correlations in 2 of 5 datasets.
- The chart-level all-in sign rule (OBV-like): the sign is right only about 55% of the time on absorption bars.
- Body rule (C−O)/(H−L): never validated on aggressor data.

### 3.4 Numeric CDF approximations (Pine has no erf, tanh or atanh)

| Approximation | Formula | Max error (computed in this run) |
|---|---|---|
| A&S 7.1.26 (**use this**) | x = \|z\|/√2; t = 1/(1+0.3275911x); erf ≈ 1 − ((((1.061405429t − 1.453152027)t + 1.421413741)t − 0.284496736)t + 0.254829592)·t·e^{−x²}; Φ = ½(1 + sign(z)·erf) | 6.97e‑8 on Φ |
| A&S 26.2.17 | z ≥ 0: t = 1/(1+0.2316419z); Φ = 1 − φ(z)·t·(0.319381530 + t(−0.356563782 + t(1.781477937 + t(−1.821255978 + 1.330274429t)))); Φ(−z) = 1 − Φ(z) | 7.45e‑8 |
| Bowling et al. 2009 | Φ ≈ 1/(1+exp(−(0.07056z³ + 1.5976z))) | 1.41e‑4 |
| Logistic | Φ ≈ 1/(1+exp(−1.702z)) | 9.49e‑3 (display only) |
| Student-t ν = 1 | F = ½ + atan(t)/π | exact |
| Student-t ν = 2 | F = ½ + t/(2√(2+t²)) | exact |
| Student-t general ν | F_ν(t) = 1 − ½·I_x(ν/2, ½), x = ν/(ν+t²), t > 0; incomplete beta by modified-Lentz continued fraction; ln B via Lanczos (g = 7, 9 coefficients) precomputed in a `var` | ≤ 4e‑10 for ν ∈ [0.1, 100], ≤ 18 iterations for ν ≤ 30 (not needed in v1) |

Other helpers: tanh(y) = (e^{2y}−1)/(e^{2y}+1), with y clamped to ±20. atanh(x) = ½·ln((1+x)/(1−x)), with x clamped to ±0.999.

### 3.5 When to use which source (decision rule)

1. User selected **Footprint** → tier A wherever `fp` is not na. Missing bars stay na by default, with an optional fill from intrabar delta that is marked on the chart.
2. Otherwise **Intrabar**:
   - Precision Auto gives TradingView built-in parity: seconds chart → "1S", intraday → "1", daily → "5", else → "60".
   - Overrides: 1T, 1S, 1, Custom.
   - Classifier: candle rule (default), or BVC-Normal.
3. If a bar has **no intrabars** (beyond the cap, a feed gap, or a lower timeframe that is not below the chart TF) → tier E chart-bar BVC, marked "price-derived". A seam marker is drawn where the tier changes.
4. The quality code (High, Medium, Low) **gates features**:

| Feature | High | Medium | Low |
|---|---|---|---|
| Display lines | yes | yes | yes, with a "price-derived" badge |
| Divergence Z | yes | yes | greyed out, no signals |
| Absorption events | full strength | "low confidence" style | off |

---

## 4. CVD construction

### 4.1 Two CVD objects

- **Increments Δ_t:** per-bar delta. All statistics use only these: σ_d, ρ, the divergence statistic, the events. They are reset-free by construction.
- **Anchored CVD:** CVD_t^{(a)} = Σ_{i=a}^{t} Δ_i, reset at each anchor. Used for the display lines and for the net aggressor ratio NAR = CVD^{(a)}/ΣV^{(a)} ∈ [−1, 1].
- **Continuous CVD:** a `var` sum starting at the first bar with valid delta. Used only by shift-invariant visual modes (level z, min-max) and by exhaustion level comparisons. Never displayed raw, and never compared across tiers.

### 4.2 Anchor options and the auto rule

| Option | Reset event | Notes |
|---|---|---|
| **Auto (default)** | chart ≤ 60 min → `timeframe.change("1D")`; 60 min < chart < 1D → "1W"; 1D ≤ chart < 1W → "1M"; ≥ 1W → "12M" | "1D" is the exchange trading day. For CME that means the **Globex** open, not the RTH open [V-sec]. For crypto it is the UTC day. |
| Regular session (RTH) | `session.isfirstbar_regular` [V] | For futures and stock traders who read RTH CVD |
| 1D / 1W / 1M | `timeframe.change(tf)`, valid only if `timeframe.in_seconds(tf) > timeframe.in_seconds()` | Otherwise the anchor never fires and a warning is shown |
| Rolling window W | none: lines = (ln C_t − ln C_{t−W})/σ and (CVD_t − CVD_{t−W})/σ | Moving-sum (Sierra-style) view |

**Why anchor.**
- `ta.cum` depends on the first loaded bar, which varies with plan and timeframe.
- Classification bias and structural taker imbalance make an unanchored CVD trend.
- Long-memory signs make CVD super-diffusive.
- Errors in the CVD level accumulate like a random walk.
- Session anchoring limits all of these and matches the built-in CVD, Sierra Chart and ATAS.

**Why the statistics do not anchor.** A 100-bar window would straddle a reset (a 5-minute RTH session is 78 bars) and create artificial σ spikes. Increments make that impossible.

### 4.3 Sources of drift and countermeasures

| Drift source | Countermeasure |
|---|---|
| Classification bias (e.g. a carried sign on zero-tick intrabars) | Anchor the display; the statistics use σ-normalized increments |
| Structural taker imbalance (perpetuals, venue maker rebates) | Optional "remove flow drift": Δ − SMA_N(Δ)_{t−1}. Default **OFF**; suggest ON for crypto perpetuals. In tests it helped calibration when price reacts only to flow innovations, and hurt detection when persistent flow does move price [E]. |
| Long-memory, metaorder-split flow that is predictable and does not move price (Chordia-Subrahmanyam 2004; Hasbrouck innovations) | Same toggle. The empirical RMS recalibration absorbs the super-diffusive variance. |
| Estimator change across the coverage boundary | Track the tier per bar, draw seam markers, and start statistics' warm-up from the first bar of the active tier |
| Overnight gaps with zero overnight delta (RTH-only data) | First bar of session: r = ln(C/O). Gap > 3σ: r = ln(C/O). BVC uses C−O on gap bars. |

### 4.4 Guards

- `volume` is 0 or na → Δ = 0, and the bar is counted as "no volume".
- Cumulative volume is 0 at `barstate.islast` → `runtime.error` ("no volume from data vendor").
- `syminfo.volumetype` of "tick" or "n/a" → a warning badge. Absence of this value does not prove real volume; FX and CFD feeds report tick or broker volume.
- `request.security_lower_tf` returns an **na array ID**, not an empty array, when `ignore_invalid_timeframe` triggers. Check `na(arr)` before `.size()`.
- Never call `footprint.*()` on an na ID (runtime error).
- Units: label CVD in base, quote or contracts per `syminfo.volumetype` where populated. Never compare absolute CVD across tiers or classifiers; their scales differ by 0.3–9.5×.

---

## 5. Normalization modes

### 5.1 Principles

1. Use the **same transform family and the same estimation window for both legs**.
2. Every **scale is estimated on increments**, causally (lagged or frozen at the anchor).
3. **Shift invariance** removes the arbitrary CVD origin.
4. **Levels are never regressed or correlated** to produce a signal.
5. Display modes are context. Signals come from §6.

Notation:
- r_t = 10⁴·ln(C_t/C_{t−1}) bps, with ln(C/O) on gap bars.
- Δ_t is the bar delta.
- σ_r = stdev_N(r), σ_d = stdev_N(Δ), ρ = corr_N(r, Δ), with N = 100 and population sd as in Pine's default.
- All three are computed only on bars where Δ is valid (r is set to na where Δ is na).

### 5.2 Mode formulas (all causal)

**M1. Anchored σ-units (DEFAULT).** At the anchor bar a, freeze the scales computed on the N bars before it: σ_r,a = σ_r,t=a−1 and σ_d,a = σ_d,t=a−1. Then

$$\tilde P_t=\frac{10^4\,(\ln C_t-\ln O_a)}{\sigma_{r,a}},\qquad \tilde F_t=\frac{\mathrm{CVD}^{(a)}_t}{\sigma_{d,a}},\qquad t\ge a$$

- Both lines start near 0 at the anchor.
- Units: "how many typical one-bar moves price and flow have travelled since the anchor".
- Within an anchor period each line is an **affine transform of ln P and CVD**, so the price line has exactly the chart's shape.
- The gap is S_t = P̃_t − F̃_t = Σ_{i=a}^{t}(r_i/σ_r,a − Δ_i/σ_d,a), the cumulative symmetric residual since the anchor.
- Optional null cone around P̃ for F̃: ±2·√(2n(1−ρ_a)), with n = t − a + 1. Label it "iid null; long-memory flow widens it". On real BTC the variance ratio VR20(u_d) = 1.30 [E], so the iid cone is about 15% too narrow.

**M2. Flow-implied price (price units, Evans-Lyons layout).** With λ in bps per unit delta frozen at the anchor:

$$\hat P_t=O_a\cdot\exp\!\Big(\frac{\lambda_a\,\mathrm{CVD}^{(a)}_t}{10^4}\Big),\quad \lambda_a=\begin{cases}\sigma_{r,a}/\sigma_{d,a}&\text{vol-matched (default)}\\ \rho_a\,\sigma_{r,a}/\sigma_{d,a}&\text{OLS ("expected price given flow")}\end{cases}$$

- Plot C_t and P̂_t. Optionally draw P̂ on the main chart with `force_overlay = true`.
- With vol-matched λ, M2 is M1 rescaled into price, so the two have identical geometry.
- The OLS variant shrinks the flow line by ρ (typically 0.4–0.6 [E]).

**M3. Rolling-window σ-units.**
- P̃_t = 10⁴(ln C_t − ln C_{t−W})/σ_r,t−1 and F̃_t = (CVD^c_t − CVD^c_{t−W})/σ_d,t−1, with continuous CVD^c.
- An anchor-free oscillator, useful on 4h and higher or for 24/7 users who dislike resets.

**M4. Rolling z of levels (visual only).**
- z^P_t = (ln C_t − SMA_N)/SD_N and z^F_t = (CVD^c_t − SMA_N)/SD_N.
- Facts to show in the tooltip:
  - |z| ≤ √(N−1).
  - A linear trend saturates at √(3(N−1)/(N+1)) ≈ 1.71.
  - For a random walk P(|z| > 2) ≈ 12–15%.
  - z^P − z^F of independent walks exceeds |2| about 33% of the time, with a fake half-life of N/4 [E].
- **No signals derived from it.**

**M5. Min-max (visual only).**
- s = 2(x − min_N)/(max_N − min_N) − 1 for both legs, with a guard when the range is 0.
- Bounded, but it saturates in trends and has breakdown 1/N. It had the lowest detection power in tests (AUC 0.54–0.55).

### 5.3 Pros and cons

| Mode | Pros | Cons | Signals allowed? |
|---|---|---|---|
| **M1 Anchored σ-units** | Theory-consistent (Kyle λσ in σ units); shape-preserving; shift-invariant; same object as the divergence statistic; comparable across instruments; no levels regression | Unbounded; lines restart at each anchor; the flow line wanders more than price (long memory, ρ < 1) | Context only; signals from Z |
| M2 Flow-implied price | Literal "CVD in price units"; can be overlaid on the chart; intuitive for discretionary traders | Same as M1, plus the units depend on the frozen λ | Context only |
| M3 Rolling σ-units | No resets; works on high timeframes | Moving-sum lines change shape as the window rolls | Context only |
| M4 Level z | Familiar (common prior art); bounded-ish | Spurious; trend-saturating; fake mean reversion | **No** |
| M5 Min-max | Bounded and visual | Outlier-dominated; lowest power | **No** |

### 5.4 Recommended default and its theoretical justification

**Default: M1, anchored σ-units, with σ over N = 100 increments frozen at the anchor and the auto anchor rule.**

1. **Kyle (1985).** Δp = λy. In the static model price is an exact linear function of flow, so λ = σ(Δp)/σ(y). Expressing price moves in units of σ_r and flow in units of σ_d is Kyle's mapping with the currency units divided out. Equivalently, M1 is the Evans-Lyons flow-implied-price overlay (M2, vol-matched) read in σ units.
2. **Errors in variables.** Price carries information CVD cannot see: public news, limit-order price discovery (Brogaard et al.; Eisler et al.), and the passive flow that CKS show matters. CVD carries classification error (§3.2). When both legs are noisy, the symmetric (RMA) slope sign(ρ)·σ_r/σ_d is the appropriate mapping. The OLS slope ρ·σ_r/σ_d attenuates the flow leg by ρ and would make every flow-led episode look like "no flow". That is why the default divergence statistic (§6.3) is also symmetric.
3. **CKS and time-varying depth.** The OFI slope ∝ 1/depth varies with intraday seasonality, activity (Dufour-Engle; Berger et al.) and news (Takahashi). λ, i.e. the σ ratio, is therefore re-estimated over a rolling N-bar window and frozen per anchor, so that within a session the lines are not refitted to the divergence they are meant to show (no self-fitting).
4. **No cointegration assumption.** Levels cointegration is regime-specific (Killeen-Lyons-Moore) and, under propagator or transient-impact theory, the levels residual is generally I(1). M1 never regresses levels. It anchors them, which bounds the accumulation of the I(1) public-information gap and of classification error to one period.
5. **Vol-scaling.** σ units make instruments and regimes comparable (Patzelt-Bouchaud's rescaling R_N(Q) ≈ g(N)F(Q/h(N)); ex-ante σ in Moskowitz-Ooi-Pedersen [M]). Lagged or frozen σ prevents the current bar from normalizing itself.

### 5.5 Impact-scale and transform options (advanced)

- **λ estimator** (M2 only): vol-matched λσ (default) or OLS λ = ρλσ. Through-origin OLS Σr·Δ/ΣΔ² is not offered: it is less stable on drifted flow and adds nothing for display.
- **Asymmetric λ (λ⁺/λ⁻):** not in v1. CRS 2002 report sell-side impact about 3× buy-side at the daily index level [V], but per-side rolling estimates are noisy at N = 100.
- **Concave flow transform (option, default Linear):** applied after winsorizing, to per-bar σ-unit flow, ũ_d = sign(u_d)·|u_d|^δ with δ ∈ {0.76 (Weber-Rosenow), 0.5 (square-root law)}. The empirical RMS recalibration restores the statistic's scale.
  - This is **not** Maitrier et al.'s trade-level GOFI Σε_i·v_i^a; Pine cannot see individual trades except via "1T".
  - A per-intrabar weight v_j^a inside the lower-timeframe expression is a possible v2 experiment.
- **Winsorizing σ-units at ±4 (on by default for statistics).** This is the practical concavity guard. Real u_d has kurtosis 100–220 and E[u_d²] ≈ 2.4 [E]. Clipping halves the null P(|Z| > 3) (2.1% → 1.1%) and improves early detection (0.30 → 0.48 in the first 20 bars of injected episodes) [E].

---

## 6. Divergence and regime statistics

### 6.1 Increment correlation, R² and the validity gate

- ρ̂_t = corr_N(r, Δ) over valid bars (`ta.correlation`). Use ρ̂_{t−1} everywhere.
- R² = ρ̂².
- Fisher 95% CI: tanh(atanh(ρ̂) ± 1.96/√(N−3)); at N = 100 the half-width in z-space is 0.199.
- **Never report the level correlation as evidence.** If it is shown at all, label it "descriptive; |r| > 0.5 occurs about 40% of the time for independent random walks".

**Gate.**

$$\text{gate}_t = \big[\hat\rho_{t-1}\ \ge\ \max\big(0.30,\ \tanh(1.96/\sqrt{N-3})\big)\big]\ \wedge\ [\text{quality}\ge\text{Medium}]$$

- At N = 100 the threshold is 0.30; at N = 30 it is 0.36.
- Real BTC 5m/15m with true delta [E]: the gate is open on 83–84% of bars, with an empirical null false-pass of 0.25–0.5%.
- Fisher 0.196 alone is open 92–97% of the time with a 2.8–3.6% null pass. R² ≥ 0.10 is practically equal to 0.30.
- With 1-minute *estimated* delta the median ρ is inflated (0.57 vs 0.49) and the gate is open on about 92% of bars. That is why the gate also requires the data tier.
- A negative ρ̂ closes the gate and is flagged "possible data or classification problem".
- When the gate is closed, the statistic is **greyed out, not hidden**.

Literature benchmarks, for context only: daily FX R² is 0.45–0.64 (Evans-Lyons; Berger et al.); CVD-based intraday R² is naturally lower (CKS, conflicting status). Thresholds should be checked per instrument.

### 6.2 Rolling λ and the "absorption gauge": context, not a trigger

- λ_ols,t = ρ̂_{t−1}·σ_r,t−1/σ_d,t−1, in bps per unit delta. In the table it is shown as bps per 1,000 units.
- **Impact efficiency over the event window K_e:**

$$\eta_t=\frac{\sum_{K_e} r}{\lambda_{\text{ols},t-1}\sum_{K_e}\Delta}$$

  Computed only when the flow leg |F_e| ≥ 1.5:
  - η ≈ 1: flow moved price as usual.
  - η ≈ 0: flow absorbed.
  - η < 0: price went against the flow.
  - η > 1: thin book or amplified impact.
- **Why it is not a trigger.**
  - Impact is concave and saturating (Hasbrouck; Weber-Rosenow G ∝ Q^0.76; the square-root law; Patzelt-Bouchaud), so η falls *mechanically* as |flow| grows. A rule "η ≤ 0.5 means absorption" fires exactly on climactic bars.
  - Short-window ratios are noisy.
- η goes in the Data Window and the table with that caveat. The literature's absorption mechanism, limit-order counterflow that makes realized impact about 4× smaller than book-implied (Weber-Rosenow [V]), is **normal market functioning**.

### 6.3 The divergence statistic Z (exact definition and calibration)

$$u_{r,t}=\mathrm{clip}\!\Big(\frac{r_t}{\sigma_{r,t-1}},\pm c\Big),\quad u_{d,t}=\mathrm{clip}\!\Big(\frac{\Delta_t}{\sigma_{d,t-1}},\pm c\Big),\quad c=4$$

$$D_t=\frac{\sum_{i=t-K+1}^{t}(u_{r,i}-u_{d,i})}{\sqrt{2K\,(1-\min(\hat\rho_{t-1},0.95))}},\qquad Z_t=\frac{D_t}{\sqrt{\frac1M\sum_{j=1}^{M}D_{t-j}^2}}$$

- Defaults: N = 100, K = 20, M = 1000. While fewer than M valid values exist, use the expanding mean of the previous D², and show Z only after a warm-up of 2N valid bars.
- (u_r − u_d)/√2 is the minor principal component of the standardized pair, i.e. the orthogonal residual, with variance 1 − ρ. It weights a flow shock and a price shock **equally** (1:1).
- The OLS residual r − λΔ weights flow ρ:1, which is why it misses flow-led episodes.
- **Sign:** Z > 0 means the price leg is ahead of the flow leg. Z < 0 means flow is ahead of price.

**Calibration evidence: candidates compared on real BTCFDUSD (true delta) and a propagator simulation [E]**

| Candidate | Null P(\|Z\|>2): real 5m / 15m / sim | Persistent-divergence behaviour | Flow-led (absorption) sensitivity |
|---|---|---|---|
| **C1 symmetric K-sum / non-demeaned RMS(M=500)** | 6.3% / 6.7% / 5.4% | Detection 0.41–0.56 out to bar 100, 0.35 at 100–200, ≤ 1.5% wrong-sign | Best: sim signed AUC 0.63–0.69, lift 2–2.7 (precision ≤ 8%) |
| **C1 + clip ±4 + RMS(M=1000) (chosen)** | **5.6–5.9%** (P(\|Z\|>3) ≈ 1.1%) | 0.44 / 0.67 / 0.57 / 0.39 at ages 0–20 / 20–100 / 100–200 / 200–400 bars | as above |
| C1 with analytic √(2K(1−ρ)) only | 12.4% / 10.1% / 10.9% | — | — |
| C2 OLS increment residual, demeaned z(100) | 8.4% / 8.2% / 8.7% | **Erased within 20–50 bars**; 9–19% wrong-sign alarms after episodes | Flow weight ρ:1; sim lift 0.3–0.8 (worse than chance) |
| C3 z^P − z^F of level z-scores | **32.5% / 33.1% / 34.3%** | Fake half-life N/4 | — |
| C4 anchored residual / (σ_e√n) | 13.0% / 7.2% / 17.8% | Depends on bars per session | — |

**Thresholds.**
- |Z| ≥ 2 marks "divergence": an empirical null rate of about 6% of bars, cut to about 0.04% when combined with the gate.
- |Z| ≥ 3 marks "strong", about 1.1% under the null.
- Fire on the **first crossing** of a confirmed bar (declustered).

**Forward returns: an honest null.** On real data no robust forward effect exists for either leg at H = K/2 or H = K. Flow-led signed forward returns are within ±0.2σ√H, with hit rates 0.44–0.58. The few |t| ≈ 2–2.5 cells (n = 14–30) do not survive Bonferroni correction across more than 64 cells [E]. **Z is a descriptive divergence gauge, not a forecast.**

### 6.4 Leg attribution and the four neutral states

P_K = Σ_K u_r/√K and F_K = Σ_K u_d/√K. The pair (sign Z, which leg is larger) partitions divergences exactly:

| Condition (gate on, \|Z\| ≥ thr) | Implied signs | Neutral label | Practitioner reading (both possible) |
|---|---|---|---|
| Z ≤ −thr, \|F\| > \|P\| | F > 0 | **"Buy flow not lifting price"** | Buy absorption: passive sellers (reversal if they are informed) *or* fuel for a breakout (catch-up) |
| Z ≤ −thr, \|P\| ≥ \|F\| | P < 0 | **"Price falling without sell flow"** | Unconfirmed decline: passive bid withdrawal or news (can be permanent) |
| Z ≥ +thr, \|F\| > \|P\| | F < 0 | **"Sell flow not pressing price"** | Sell absorption, mirror case |
| Z ≥ +thr, \|P\| ≥ \|F\| | P > 0 | **"Price rising without buy flow"** | Unconfirmed rally: short covering via limit orders, offer withdrawal or news |

The implied signs follow algebraically from Z ∝ P − F, so no fifth state exists apart from ties.

### 6.5 Short-window flow/price events and the resolution state machine

This layer is separate from Z because the only real-data effect was found on windows of about 15 minutes [E].

- Window K_e = max(1, round(900 / tf_seconds)): 3 bars on 5m, 15 bars on 1m, 1 bar on charts of 15m or more.
- F_e = Σ_{K_e}u_d/√K_e and P_e = Σ_{K_e}u_r/√K_e.
- Standardized by their own non-demeaned RMS over M: z_F = F_e/RMS_M(F_e)_{t−1}, z_P likewise. s = sign(z_F).

| Class | Definition | Label |
|---|---|---|
| ABSORBED | \|z_F\| ≥ 2 and s·z_P ≤ 0 | "Buy/Sell flow absorbed" (neutral colour) |
| PINNED (subset) | \|z_F\| ≥ 3 and \|z_P\| ≤ 0.5 | "Pinned: extreme flow, flat price" (breakout watch) |
| CONFIRMED | \|z_F\| ≥ 2 and s·z_P ≥ \|ρ̂\|·\|z_F\| | Not marked by default (partial reversal expected; context) |
| PRICE WITHOUT FLOW | \|z_P\| ≥ 2 and sign(z_P)·z_F ≤ 0 | "Price move without flow" |

**Resolution.**
- At the event bar t₀ record H₀ = highest(high, K_e) and L₀ = lowest(low, K_e).
- Lifetime: L_life = max(1, round(3600 / tf_seconds)) bars, about 60 minutes (CRS 2005: predictability gone within 60 minutes; BTC effects at 30–60 minutes and gone by 3 hours [E]).
- For buy-flow absorbed (s = +1):
  - A confirmed close > H₀ within the lifetime → **"absorption failed → continuation"** (bullish colour).
  - A close < L₀ → **"absorption held → passive side won"** (bearish colour).
  - Neither → "expired".
- Mirror for s = −1.
- Only resolved states receive a directional colour.
- On charts of 1h or more, events are shown as context only, with a tooltip noting that no follow-through is expected.

**Quality gating.**
- Full style on High tier (footprint, 1T, 1S).
- Hollow "low confidence" style on Medium tier (1-minute intrabars). In BTC data the absorption edge vanished with 1-minute estimated delta.
- Off on Low tier.

**Directional-lean input** (Neutral default, or Continuation, or Reversal): it only re-colours *unresolved* events. Never default to "Reversal / passive side informed".

### 6.6 Exhaustion candidates and pivot divergence

**Exhaustion candidate** (default **OFF**; low-confidence style).
- N_x = 4 h of bars, with a minimum of 10.
- High side: newHigh = high > highest(high, N_x)[1] **and** CVD^c < highest(CVD^c, N_x)[1].
- First in cluster: ta.barssince(newHigh)[1] > N_x/4.
- Confirmation: a close back below the prior N_x-bar high within L_life bars.
- Mirror for lows.
- Tooltip: "new extremes already mean-revert slightly; CVD non-confirmation added no significant edge in testing". Evidence: −6 to −8 bps base reversion at 2–3 h regardless of CVD; divergent −5.5 to −7.5 bps vs confirmed −1 to −2 bps, difference n.s. [E].

**Pivot divergence** (default **OFF**).
- ph = ta.pivothigh(high, L, R) with L = 5, R = 2.
- Read the CVD (σ-unit line or CVD^c) **at the price-pivot bar**, `cvd[R]`. Do **not** require a simultaneous CVD pivot; that is a common community bug.
- Bearish: ph > prevPh and cvdAtPivot < prevCvdAtPivot.
- Pivots must be 5–60 bars apart and in the **same anchor segment** if anchored lines are used.
- Require a magnitude difference of at least 0.5σ-units.
- The signal is known only R bars later: draw it at the pivot, alert at confirmation, and say so in the tooltip.

### 6.7 Mean reversion: why no half-life label

- An overlapping K-sum has lag-1 ACF of (K−1)/K. At K = 20 that is 0.95, with half-life 13.5 bars.
- Rolling 100-bar AR(1) fits are biased further downward (Kendall).
- "Half-life ≤ N/4 means reverting" therefore passes 88–97% of **null** windows (97–98% on real data) [E]. Avellaneda-Lee's τ < window/2 filter passes 98.6% of null windows.
- **Optional tag (OFF by default):** rolling 100-bar Dickey-Fuller on X_t = Σ(u_r − u_d), the un-normalized cumulative symmetric residual:
  - ΔX_t = a + gX_{t−1} + e.
  - "Reverting" if t_g < −2.89. Our Monte Carlo 5% critical value is −2.88.
  - Empirical null firing is 4.3–7.6%; real data fires 12–13%.
- Never fit a half-life on a z-normalized spread: its null half-life is about N/4.

### 6.8 Interpretation: exhaustion vs absorption, with evidence strength

| Claim | Evidence | Strength |
|---|---|---|
| Price increments co-move linearly with signed flow at small sizes | Kyle [V]; Evans-Lyons [V]; CKS [V]; CRS 2002 adj. R² 0.28 [V full]; Silantyev (crypto) [V]; own BTC ρ 0.39–0.45 [E] | **Strong** |
| Impact is concave and saturating at large flow | Hasbrouck [V]; Weber-Rosenow 0.48Q^0.76 [V full]; Plerou [V]; Patzelt-Bouchaud [V]; square-root law [V] | **Strong** |
| "Flow without price" is often normal (limit-order counterflow, transient impact, long-memory signs) | Bouchaud et al. 2004 [V full]; Weber-Rosenow 4× [V full]; Lillo-Farmer [V]; Eisler et al. [V] | **Strong (mechanism)** |
| Imbalance forecasts volatility, not direction | ELO 2012 VPIN, "not a directional indicator" [V full] | Moderate |
| Flow-confirmed price pressure partially reverses | CRS 2002 conditional lagged imbalance −4.56 / −5.83 [V full]; Hendershott-Menkveld [V-sec]; metaorders about 1/3 revert [V]; own BTC −4 to −5 bps [E] | **Moderate** |
| Direction after absorption | No peer-reviewed test found. Kaniel-Liu and Brogaard et al. are unconditional. BTC 15-min absorbed +7.7 bps and pinned +14.6 bps (continuation, 30 min), in-sample, one satellite venue, vanishing with 1m-estimated delta [E]. Simulation: sign set by the informedness of the passive side [E]. Osler [M]: resting-order composition decides reversal vs cascade. | **Weak / unvalidated**; at most a slight short-horizon continuation |
| Exhaustion beats the base rate of reversal at new extremes | No peer-reviewed test; own BTC: not significant [E] | **Not established** |
| The K = 20 divergence Z forecasts returns | Own real data: null after multiple-testing control [E]; CRS 2002: no unconditional next-day predictability [V] | **Null** |
| Level correlation or z-spread "confirms" or "diverges" | Spurious-regression theory [V]; Ernst-Shepp-Wyner [V]; own Monte Carlo [E] | **Invalid** |

**What the indicator should say.**
- "Flow ≠ price" is a *state*.
- Absorption has two opposite resolutions: the passive side is informed or persistent, giving a reversal; or the passive side is exhausted (like a peg breaking, Killeen-Lyons-Moore), giving a catch-up in the flow direction. **Price decides.**
- Exhaustion is a low-confidence candidate that needs price re-entry.
- Effects, if any, are a few bps over about 30–60 minutes. Nothing in the evidence supports a stand-alone tradable edge.

---

## 7. Pine v6 implementation notes

### 7.1 Signatures and limits checked against the local docs or official manual mirrors

| Item | Fact | Status |
|---|---|---|
| `request.footprint(ticks_per_row, va_percent, imbalance_percent) → footprint` | ticks_per_row is **simple int** (input.int is fine); va 70; imbalance 300. Returns na if no data. "Only accounts with Premium or Ultimate plans can use scripts that call this function." "A single script cannot include more than one `request.footprint()` call." | [V] local copy of the v6 Reference Manual, `request.footprint()` entry |
| `footprint.total_volume/buy_volume/sell_volume/delta(id)` | Official example uses function-call form with an `not na(id)` guard; `id` cannot be na | [V] manual mirror (page downloaded during the research, not included) |
| Footprint classification | "categorizes volume values from lower timeframes as 'buy' (upward) or 'sell' (downward) based on intrabar price action" | [V-sec] manual mirror |
| Footprint inside other requests | Any `request.security`/`security_lower_tf` whose expression depends on footprint counts as a footprint request; a runtime error results if outputs depend on more than one | [V-sec] manual mirror |
| Lower plans executing `request.footprint` | Undocumented. The best practitioner evidence says the script stops with an error. A gated `if` is claimed to avoid the check. | [V-sec], **verify live** |
| `request.security_lower_tf(symbol, timeframe, expression, ignore_invalid_symbol, currency, ignore_invalid_timeframe, calc_bars_count)` | Returns an array per chart bar (a tuple expression gives a tuple of arrays). Errors if the LTF is above the chart TF unless `ignore_invalid_timeframe = true`, in which case it returns an **na array**. May repaint. | [V] local |
| Intrabar caps | 100K (Basic to Premium), 125K (Expert), 200K (Ultimate); applies to `request.security` and `request.security_lower_tf` | [V] local copy of the User Manual, «Limitations» page |
| `request.*` unique calls | 40 (64 on Ultimate); calls inside imported libraries count | [V] local |
| Plot counts | Max 64. plot, plotshape, plotchar, bgcolor, alertcondition and fill (series colour) count. A series colour adds one count. hline, label, line, box and table do not count. | [V] local |
| `input.*(…, active)` | "the active parameter of all input*() functions accepts an 'input bool' value" | [V] manual mirror, «Inputs» page (downloaded during the research, not included) |
| `timeframe.change(timeframe)` | Argument is series string; true on the first bar of a new period | [V-sec] mirror; behaviour [V] local |
| `session.isfirstbar_regular`, `session.isfirstbar` | Exist | [V] local |
| `ta.stdev(source, length, biased = true)` | Biased (population) default; na ignored. The reference's "same on pine" code (with a SUM helper returning 15) is **not** a precision specification. | [V] local |
| `ta.correlation`, `math.sum`, `ta.sma` | na values ignored; use the last `length` non-na values | [V] local |
| `array.sum`, `array.median`, `label.get_text/set_text/set_color`, `str.endswith`, `timeframe.in_seconds`, `timeframe.isminutes` | Exist | [V] local index |
| `plot(…, force_overlay, linestyle)` | `force_overlay = true` draws on the main pane; title is const string | [V] local copy of the User Manual, «Plots» page |
| No `math.erf`, `math.tanh` or `math.atanh` | Implement by hand (§3.4) | [V] local index |
| Dynamic requests | On by default in v6; `request.*()` is allowed inside `if` blocks and loops | [V-sec] manual mirror |
| `bid` / `ask` | Non-na only on "1T" | [V] local |
| TradingView `ta` v12 | `requestUpAndDownVolume(series string)` → [pos, neg, delta]; `requestVolumeDelta(series string, series string = "")` | [V] source. The import path `TradingView/ta/12` is **verify live**; v14 exists [V-sec]. |

### 7.2 v6 gotchas that matter here

1. **`and`/`or` are lazy.** Compute every `ta.*`, `timeframe.change()` and `math.sum` result into a **global** variable on every bar, then combine. The same applies to ternaries holding `ta.*` calls.
2. **bool cannot be na.** `na()`, `nz()` and `fixnan()` reject bool. Compare with `na(x)`, never `x == na`.
3. **Exactly one `request.footprint()` call site.** Do not put it in a function called twice, and do not also request footprint inside `request.security`.
4. **Align na between legs.** Set `r := na` wherever Δ is na, so that `ta.stdev`, `ta.correlation` and `math.sum` (which skip na) use the same bars.
5. **Lagged scales.** Use `sr[1]`, `sd[1]`, `rho[1]` stored in global variables so the current, unconfirmed bar never normalizes itself.
6. **State in `var`, never `varip`.** `var` is rolled back on each realtime tick, so recalculation does not double count. Signals and alerts use `barstate.isconfirmed` and `alert.freq_once_per_bar_close`.
7. **Numerics.**
   - Returns in bps (×1e4), to stay clear of tiny-value precision in `ta.stdev`.
   - Never form `ta.sma(x*y) − ta.sma(x)*ta.sma(y)` on raw CVD levels. At an offset of 1e12 with sd 2e3 that is off by 5.8× [E].
   - Guard every denominator (> 0 and not na).
8. **`for i = 0 to n − 1` with n = 0 runs i = 0, −1.** Use `for … in` or `array.sum()`.
9. **The anchor timeframe must exceed the chart timeframe.** Otherwise `timeframe.change()` is true every bar; validate with `timeframe.in_seconds()`.
10. **`hline` price and colour are input-level.** Plot titles are const strings. To hide plots dynamically use `color = na` (verified), or an input-driven `display` (the qualifier is unverified; check in the editor).

### 7.3 Code sketches

These are sketches to be compiled in the Pine Editor. Names match §8. Inputs that are not shown (`anchIn`, `lamOls`, `driftIn`, `rhoGateIn`, `eventsOn`, `showTblIn`, colours `bullCol`/`bearCol`/`neutCol`, `srcTxt`) follow §8.1. The required declaration order is (a) → (b) → (c) → (d) → (f) → (e) → (g) → (h).

**(a) Enums and the core inputs**

```pine
//@version=6
indicator("Price × CVD — Normalized Order Flow", shorttitle = "P×CVD", overlay = false,
     explicit_plot_zorder = true, max_labels_count = 500)

enum DeltaSrc
    ltf = "Intrabar (lower timeframe)"
    fp  = "Footprint (Premium/Ultimate only)"
    bar = "Chart bars only (price-derived)"

enum Classifier
    candle = "Candle rule (TradingView parity)"
    bvc    = "BVC-Normal per intrabar"

enum Precision
    auto   = "Auto (built-in CVD parity)"
    t1     = "1T (ticks, Ultimate)"
    s1     = "1S (Premium+)"
    m1     = "1 minute"
    custom = "Custom"

enum AnchorMode
    auto = "Auto"
    rth  = "Regular session (RTH)"
    d1   = "1D"
    w1   = "1W"
    mo1  = "1M"
    roll = "Rolling window"

DeltaSrc   srcIn   = input.enum(DeltaSrc.ltf, "Delta source", group = "Data",
     tooltip = "Footprint needs a Premium or Ultimate plan; on other plans the script may stop with an error when selected.")
Classifier clsIn   = input.enum(Classifier.candle, "Intrabar classifier", group = "Data", active = srcIn == DeltaSrc.ltf)
Precision  precIn  = input.enum(Precision.auto, "Intrabar precision", group = "Data", active = srcIn != DeltaSrc.bar)
string     ltfCust = input.timeframe("1", "Custom intrabar TF", group = "Data",
     active = srcIn != DeltaSrc.bar and precIn == Precision.custom)
int        ticksIn = input.int(100, "Ticks per footprint row", minval = 1, group = "Data", active = srcIn == DeltaSrc.fp)
int        nIn     = input.int(100, "σ/ρ window N", minval = 30, maxval = 300, group = "Statistics")
int        kIn     = input.int(20, "Divergence horizon K", minval = 5, maxval = 50, group = "Statistics")
int        mIn     = input.int(1000, "Calibration window M", minval = 300, maxval = 2000, group = "Statistics")
float      clipIn  = input.float(4.0, "Winsorize σ-units at ±", minval = 2.0, maxval = 10.0, group = "Statistics")
```

**(b) Lower-timeframe delta engine: one unique request returning a tuple of three arrays**

```pine
normCdf(float z) =>                                   // A&S 7.1.26, |err| ≈ 7e-8
    float x = math.abs(z) / math.sqrt(2.0)
    float t = 1.0 / (1.0 + 0.3275911 * x)
    float e = 1.0 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * math.exp(-x * x)
    0.5 * (1.0 + math.sign(z) * e)

// Evaluated on every intrabar inside the lower-timeframe context (state and σ are continuous there).
ltfSigned(int sigLen) =>
    var int dir = 1                                                     // carried side, never reset (TradingView/ta parity)
    bool  hasQ = not na(bid) and not na(ask) and ask > bid              // quotes exist only on "1T"
    float mid  = hasQ ? 0.5 * (bid + ask) : na
    int   qDir = hasQ ? (close >= ask ? 1 : close <= bid ? -1 : close > mid ? 1 : close < mid ? -1 : 0) : 0
    int   pDir = close > open ? 1 : close < open ? -1 : close > close[1] ? 1 : close < close[1] ? -1 : 0
    dir := qDir != 0 ? qDir : pDir != 0 ? pDir : dir
    float v  = nz(volume)
    float dp = session.isfirstbar ? close - open : nz(close - close[1])   // gap guard for BVC
    float sg = ta.stdev(dp, sigLen)
    float z  = sg > 0 ? math.max(-10.0, math.min(10.0, dp / sg)) : 0.0
    [dir * v, v * (2.0 * normCdf(z) - 1.0), v]

string ltf = switch precIn
    Precision.t1     => "1T"
    Precision.s1     => "1S"
    Precision.m1     => "1"
    Precision.custom => ltfCust
    =>                  timeframe.isseconds ? "1S" : timeframe.isintraday ? "1" : timeframe.isdaily ? "5" : "60"

[aCand, aBvc, aVol] = request.security_lower_tf(syminfo.tickerid, ltf, ltfSigned(100), ignore_invalid_timeframe = true)
int   nIntra   = na(aVol) ? 0 : aVol.size()                       // na array ID when the LTF is invalid
float ltfDelta = nIntra > 0 ? (clsIn == Classifier.candle ? aCand.sum() : aBvc.sum()) : na
float ltfVol   = nIntra > 0 ? aVol.sum() : na
bool  ltfFine  = str.endswith(ltf, "T") or str.endswith(ltf, "S")  // tick/second intrabars → High tier
```

Verify live that `bid` and `ask` are populated inside a "1T" `security_lower_tf` context. Practitioner scripts (TradingIQ Footprint IQ Pro) and TradingView's own `ta` library read them in "1T" requests.

**(c) Footprint: plan-safe single call site (practitioner pattern; verify live)**

```pine
footprint fp = na
if srcIn == DeltaSrc.fp
    fp := request.footprint(ticksIn)                                  // the ONLY call site in the whole script
float fpDelta = na(fp) ? na : footprint.delta(fp)
float fpVol   = na(fp) ? na : footprint.total_volume(fp)
```

**(d) Chart-bar fallback, delta selection and quality tier**

```pine
float rRaw   = 1e4 * math.log(close / close[1])                       // bps
float sRaw   = ta.stdev(rRaw, 100)
float sRawP  = sRaw[1]
bool  gapBar = na(close[1]) or session.isfirstbar or math.abs(1e4 * math.log(open / close[1])) > 3.0 * nz(sRawP, 1e10)
float rBar   = gapBar ? 1e4 * math.log(close / open) : rRaw
float sBar   = ta.stdev(rBar, 100)
float sBarP  = sBar[1]
float zBar   = sBarP > 0 ? math.max(-10.0, math.min(10.0, rBar / sBarP)) : 0.0
float barDelta = nz(volume) * (2.0 * normCdf(zBar) - 1.0)             // chart-bar BVC-Normal (price-derived)

bool useFp  = srcIn == DeltaSrc.fp and not na(fpDelta)
bool useLtf = not useFp and srcIn != DeltaSrc.bar and nIntra > 0
float delta   = useFp ? fpDelta : useLtf ? ltfDelta : barDelta
float barVol  = useFp ? fpVol   : useLtf ? ltfVol   : volume
int   quality = useFp or (useLtf and ltfFine) ? 3 : useLtf ? 2 : 1   // 3 High, 2 Medium, 1 Low (price-derived)
```

The optional per-bar fill when footprint is missing is a variant of `useLtf`. In footprint mode without fill, missing bars should be **na** rather than falling to `barDelta`.

**(e) Anchoring and the display lines (M1 and M2)**

```pine
int    tfSec  = timeframe.in_seconds()
string autoTf = tfSec <= 3600 ? "1D" : tfSec < 86400 ? "1W" : tfSec < 604800 ? "1M" : "12M"
string anchTf = switch anchIn
    AnchorMode.d1   => "1D"
    AnchorMode.w1   => "1W"
    AnchorMode.mo1  => "1M"
    AnchorMode.auto => autoTf
    =>                 "12M"
bool tfChg     = timeframe.change(anchTf)                              // global, every bar
bool rth1st    = session.isfirstbar_regular
bool tfOk      = timeframe.in_seconds(anchTf) > tfSec
bool newAnchor = anchIn == AnchorMode.rth ? rth1st : anchIn == AnchorMode.roll ? false : tfOk and tfChg

// statistics on increments (aligned): see (f) for sr/sd/rho
var float lnA  = na
var float cvdA = 0.0
var float volA = 0.0
var float srA  = na
var float sdA  = na
var float rhoA = na
if newAnchor or na(lnA)
    lnA  := math.log(open)
    cvdA := 0.0
    volA := 0.0
    srA  := srP
    sdA  := sdP
    rhoA := rhoP
cvdA += nz(delta)
volA += nz(barVol)

float pSig = srA > 0 ? 1e4 * (math.log(close) - lnA) / srA : na       // M1 price leg (σ-units)
float fSig = sdA > 0 ? cvdA / sdA : na                                // M1 flow leg (σ-units)
float lamA = sdA > 0 ? (lamOls ? rhoA : 1.0) * srA / sdA : na         // bps per unit delta
float pHat = math.exp(lnA + nz(lamA) * cvdA / 1e4)                    // M2 flow-implied price
float nar  = volA > 0 ? cvdA / volA : na                              // net aggressor ratio since anchor
```

**(f) Statistics: increments, gate, Z, legs**

```pine
clip(float x, float c) => math.max(-c, math.min(c, x))
tanh(float y) =>
    float e = math.exp(2.0 * math.max(-20.0, math.min(20.0, y)))
    (e - 1.0) / (e + 1.0)
atanh(float x) =>
    float c = math.max(-0.999, math.min(0.999, x))
    0.5 * math.log((1.0 + c) / (1.0 - c))

// Non-demeaned RMS of x over the previous m non-na values; expanding mean during warm-up.
rmsLag(float x, int m, int warm) =>
    float x2 = x * x
    float s  = ta.sma(x2, m)
    var float cum = 0.0
    var int   cnt = 0
    float out = cnt > m ? math.sqrt(s[1]) : cnt >= warm ? math.sqrt(cum / cnt) : na
    if not na(x2)
        cum += x2
        cnt += 1
    out

float d    = driftIn ? delta - ta.sma(delta, nIn)[1] : delta          // optional drift removal (default off)
float r    = na(d) ? na : rBar                                        // align legs
float sr   = ta.stdev(r, nIn)
float sd   = ta.stdev(d, nIn)
float rho  = ta.correlation(r, d, nIn)
float srP  = sr[1]
float sdP  = sd[1]
float rhoP = rho[1]

float ur   = srP > 0 ? clip(r / srP, clipIn) : na
float ud   = sdP > 0 ? clip(d / sdP, clipIn) : na
float sumU = math.sum(ur - ud, kIn)
float Draw = sumU / math.sqrt(2.0 * kIn * (1.0 - math.min(nz(rhoP), 0.95)))
float rmsD = rmsLag(Draw, mIn, 2 * nIn)
float Z    = rmsD > 0 ? Draw / rmsD : na

float rhoMin = math.max(rhoGateIn, tanh(1.96 / math.sqrt(nIn - 3)))   // = 0.30 at N = 100
bool  gateOn = not na(rhoP) and rhoP >= rhoMin and quality >= 2
float pLeg   = math.sum(ur, kIn) / math.sqrt(kIn)
float fLeg   = math.sum(ud, kIn) / math.sqrt(kIn)
bool  flowLed = math.abs(fLeg) > math.abs(pLeg)
float lamOlsP = sdP > 0 ? nz(rhoP) * srP / sdP : na                   // bps per unit delta (table: ×1000)
```

In the actual script, `srP`, `sdP` and `rhoP` must be declared **before** block (e), because Pine requires declaration before use. Order the code as (d) → (f) → (e).

**(g) Short-window events and the resolution state machine (sketch)**

```pine
int   ke     = math.max(1, math.round(900 / tfSec))
int   life   = math.max(1, math.round(3600 / tfSec))
float fE     = math.sum(ud, ke) / math.sqrt(ke)
float pE     = math.sum(ur, ke) / math.sqrt(ke)
float rF     = rmsLag(fE, mIn, 2 * nIn)
float rP     = rmsLag(pE, mIn, 2 * nIn)
float zF     = rF > 0 ? fE / rF : na
float zP     = rP > 0 ? pE / rP : na
float sF     = math.sign(nz(zF))
float hiKe   = ta.highest(high, ke)
float loKe   = ta.lowest(low, ke)
bool  absorbed = gateOn and math.abs(nz(zF)) >= 2.0 and sF * nz(zP) <= 0
bool  pinned   = gateOn and math.abs(nz(zF)) >= 3.0 and math.abs(nz(zP, 9.0)) <= 0.5
bool  newAbs   = barstate.isconfirmed and eventsOn and quality >= 2 and absorbed and not absorbed[1]

var int   evSide = 0
var float evHi   = na
var float evLo   = na
var int   evBar  = na
var label evLbl  = na
if evSide != 0 and barstate.isconfirmed and bar_index > evBar
    bool cont = evSide > 0 ? close > evHi : close < evLo
    bool held = evSide > 0 ? close < evLo : close > evHi
    if cont or held or bar_index - evBar >= life
        string res = cont ? "→ continuation (absorption failed)" : held ? "→ held (passive side won)" : "→ expired"
        label.set_text(evLbl, label.get_text(evLbl) + "\n" + res)
        label.set_color(evLbl, cont ? (evSide > 0 ? bullCol : bearCol) : held ? (evSide > 0 ? bearCol : bullCol) : neutCol)
        evSide := 0
if newAbs
    evSide := int(sF)
    evHi   := hiKe
    evLo   := loKe
    evBar  := bar_index
    evLbl  := label.new(bar_index, evSide > 0 ? high : low,
         (evSide > 0 ? "Buy" : "Sell") + " flow absorbed" + (pinned ? " (pinned)" : "") + (quality == 2 ? " · low conf." : ""),
         yloc = evSide > 0 ? yloc.abovebar : yloc.belowbar, color = neutCol, textcolor = chart.fg_color,
         style = evSide > 0 ? label.style_label_down : label.style_label_up, size = size.tiny,
         tooltip = str.format("zF={0,number,#.##} zP={1,number,#.##} ρ={2,number,#.##} Z={3,number,#.##}", zF, zP, rhoP, Z),
         force_overlay = true)
```

This handles one pending event at a time. A new event while one is pending either replaces it, after marking the old one "superseded", or is queued. Use a small array of a user-defined type if overlapping events are needed.

**(h) Table (created once, filled on the last bar) and alerts**

```pine
var table tb = table.new(position.top_right, 2, 11, bgcolor = color.new(chart.bg_color, 10),
     frame_color = color.new(chart.fg_color, 70), frame_width = 1,
     border_color = color.new(chart.fg_color, 85), border_width = 1)
float zf = atanh(nz(rhoP))
float ciLo = tanh(zf - 1.96 / math.sqrt(nIn - 3))
float ciHi = tanh(zf + 1.96 / math.sqrt(nIn - 3))
if showTblIn and barstate.islast
    tb.cell(0, 0, "Source", text_color = chart.fg_color, text_size = size.small)
    tb.cell(1, 0, srcTxt + " · " + (quality == 3 ? "High" : quality == 2 ? "Medium" : "Low (price-derived)"),
         text_color = chart.fg_color, text_size = size.small)
    tb.cell(0, 1, "ρ(Δp,Δ) [95% CI]", text_color = chart.fg_color, text_size = size.small)
    tb.cell(1, 1, str.format("{0,number,0.00} [{1,number,0.00}, {2,number,0.00}]", rhoP, ciLo, ciHi),
         text_color = gateOn ? chart.fg_color : color.gray, text_size = size.small,
         tooltip = "Correlation of bar returns and bar delta (increments, not levels). Gate: ρ ≥ max(0.30, tanh(1.96/√(N−3))).")
    // … rows: intrabars/bar & coverage, R², λ (bps per 1k), Z & state, NAR since anchor, volume type, warm-up status

alertcondition(newAbs and sF > 0, "Buy flow absorbed", "{{ticker}} {{interval}}: buy flow absorbed (unconfirmed)")
alertcondition(newAbs and sF < 0, "Sell flow absorbed", "{{ticker}} {{interval}}: sell flow absorbed (unconfirmed)")
// … divergence first-crossings, resolutions, price-without-flow, gate opened
if barstate.isconfirmed and (newAbs or newDiv or resolvedNow)
    alert(str.format("{0} {1}: {2} | Z={3,number,#.##} zF={4,number,#.##} zP={5,number,#.##} ρ={6,number,#.##} [{7}]",
         syminfo.ticker, timeframe.period, stateTxt, Z, zF, zP, rhoP, srcTxt), alert.freq_once_per_bar_close)
```

### 7.4 Must verify in the Pine Editor before release

1. What happens on Basic, Essential, Plus or Expert when the Footprint option is **not** selected (the script must load), and when it is selected (error or na).
2. That `footprint fp = na` followed by `fp := request.footprint(...)` inside `if` compiles.
3. Whether `bid` and `ask` are non-na inside `request.security_lower_tf(…, "1T", …)` on historical bars, and how many ticks are served.
4. How "1S" and "1T" requests behave on plans that lack those chart intervals (error, na, or allowed).
5. The `display` qualifier for input-driven visibility on plot, plotshape and label (fallback: `color = na`).
6. The import path and version of `TradingView/ta` if it is used for parity checks.
7. `timeframe.change(anchTf)` with a simple string derived from an input, and the auto map on 2h/4h/D charts.
8. Total plot count, with alertconditions included, kept at or below 64.

---

## 8. Recommended indicator specification (v1)

### 8.1 Inputs

| Group | Input | Type / options | Default | Tooltip (abridged) |
|---|---|---|---|---|
| Data | Delta source | enum: Intrabar / Footprint (Premium/Ultimate) / Chart bars only | **Intrabar** | "Footprint is opt-in; on lower plans the script may stop with an error. Chart-bars mode is price-derived: divergence and absorption are disabled." |
| Data | Intrabar precision | enum: Auto / 1T / 1S / 1 minute / Custom | **Auto** (1S on seconds charts, 1 intraday, 5 daily, 60 otherwise) | "Lower is more precise but covers fewer bars (100K intrabars on most plans). 1S is Premium+, 1T is Ultimate (third-party pricing parse)." |
| Data | Custom intrabar TF | timeframe (active if Custom) | "1" | — |
| Data | Intrabar classifier | enum: Candle rule / BVC-Normal | **Candle rule** | "Matches TradingView's CVD. BVC is optional; on real data it did not beat the candle rule." |
| Data | Ticks per footprint row | int ≥ 1 (active if Footprint) | 100 | "Does not change delta; increase it if footprint returns na on wide bars (>2000 rows)." |
| Data | Fill missing footprint bars with intrabar delta | bool (active if Footprint) | false | "Avoids mixing classifiers unless enabled; filled bars are marked." |
| Data | Remove flow drift | bool | false | "Subtracts SMA_N(delta)[1]. Consider ON for crypto perpetuals with a structural taker imbalance." |
| Display | Mode | enum: Anchored σ-units / Flow-implied price / Rolling σ-units / Level z (visual only) / Min-max (visual only) | **Anchored σ-units** | "Both legs in units of their own one-bar σ (Kyle vol-matched mapping). The gap is context; signals come from Z." |
| Display | Anchor | enum: Auto / RTH / 1D / 1W / 1M / Rolling | **Auto** | "Auto: ≤1h chart → 1D (CME: Globex day; crypto: UTC day), <1D → 1W, 1D → 1M, ≥1W → 12M." |
| Display | Rolling window W | int (active for rolling and visual modes) | 100 | — |
| Display | Impact scale (flow-implied price) | enum: Vol-matched λσ / OLS λ = ρλσ | **Vol-matched** | "OLS shrinks the flow line by ρ (expected price given flow)." |
| Display | Draw flow-implied price on main chart | bool | false | Uses `force_overlay`. |
| Display | Pane view | enum: Lines / Divergence Z histogram / Both | **Lines** | "In Lines view the fill colour encodes calibrated Z." |
| Display | Show iid null cone | bool | false | "Long-memory flow makes the true cone about 15–30% wider." |
| Statistics | σ/ρ window N | int 30–300 | **100** | "≈ one RTH session on 5m; Fisher threshold 0.196 at N = 100." |
| Statistics | Divergence horizon K | int 5–50 | **20** | — |
| Statistics | Calibration window M | int 300–2000 (≥ 5N) | **1000** | "Non-demeaned RMS keeps persistent divergences visible." |
| Statistics | Winsorize σ-units at ± | float | **4.0** | — |
| Statistics | Divergence / strong thresholds | float, float | **2.0 / 3.0** | "Null ≈ 6% / ≈ 1% of bars on real data before the gate." |
| Statistics | Min ρ gate | float | **0.30** | "Effective gate = max(input, tanh(1.96/√(N−3)))." |
| Statistics | Flow transform | enum: Linear / Power 0.76 / Power 0.5 | **Linear** | Concavity option. |
| Statistics | Mean-reversion tag (Dickey-Fuller) | bool | false | "t < −2.89 on the cumulative symmetric residual (100 bars)." |
| Events | Show flow/price events | bool | **true** | — |
| Events | Event window (minutes) / lifetime (minutes) | int / int | **15 / 60** | "Events of 1h or more are context only." |
| Events | Strong-flow \|zF\| / pinned \|zF\| / pinned max \|zP\| | float ×3 | **2.0 / 3.0 / 0.5** | — |
| Events | Show events on 1-minute data (low confidence) | bool | **true** | "On 1-minute intrabars the absorption edge did not survive in testing." |
| Events | Directional lean | enum: Neutral / Continuation / Reversal | **Neutral** | "Only re-colours unresolved events; no peer-reviewed default exists." |
| Events | Exhaustion candidates / lookback (hours) | bool / float | **false / 4** | "Low confidence; requires price re-entry." |
| Events | Pivot divergence / left / right / min / max bars | bool / int ×4 | **false / 5 / 2 / 5 / 60** | "CVD is read at the price-pivot bar; confirmed R bars later." |
| Style | Colours: price, CVD, bull, bear, neutral; line widths | color/int | price = chart.fg_color, CVD = #26A69A, bull = #26A69A, bear = #EF5350, neutral = #9E9E9E | — |
| Table | Show table / position / size | bool / enum | true / top_right / small | — |

### 8.2 Computed series, all causal

- **Data:** delta, barVol, quality (1–3), nIntra, coverage counters (`var` totals of bars, bars with intrabars, and intrabars).
- **Increments:** r (bps, gap-guarded), d (optionally drift-removed), with r set to na where d is na.
- **Scales:** sr, sd, rho (N), and their lagged values srP, sdP, rhoP. λ_ols = ρσ_r/σ_d and λσ = σ_r/σ_d. R² = ρ². Fisher CI.
- **Anchor:** newAnchor; lnA, cvdA, volA, srA, sdA, rhoA (frozen); NAR.
- **Display legs (per mode):**
  - M1: pSig, fSig.
  - M2: close and pHat.
  - M3: rolling σ-unit legs.
  - M4/M5: visual legs on continuous CVD.
- **Statistic:** ur, ud (clipped), Draw, rmsD, Z, gateOn, pLeg, fLeg, flowLed, the four-state label.
- **Events:** ke, life, fE, pE, zF, zP, the absorbed / pinned / confirmed / price-without-flow classes, the state machine, and η.
- **Optional:** exhaustion candidates (CVD^c), pivot pairs, Dickey-Fuller t on X = Σ(u_r − u_d).

### 8.3 Plots, fills, labels, and the plot-count budget

| Element | Implementation | Plot counts |
|---|---|---|
| Price leg | `plot`, constant colour (chart.fg_color), linewidth 2 | 1 |
| CVD leg | `plot`, constant colour | 1 |
| Fill between legs | `fill(pP, pF, color = …)`. The colour comes from `color.from_gradient(Z, −3, 3, bear, bull)`, neutral when the gate is closed or \|Z\| < 1. Transparency 70–85. | 1 (series colour) |
| Z histogram | `plot(style = plot.style_columns)`, series colour (grey when the gate is closed); hidden in Lines view via `color = na` | 2 |
| Optional null cone (upper/lower) | `plot`, dotted | 2 |
| Zero and ±2/±3 levels | `hline` | 0 |
| Background: anchor resets, tier seams, warm-up | one `bgcolor` with a series colour | 1 |
| Events, resolutions, exhaustion, pivots | `label.new(…, force_overlay = true)` with tooltips; FIFO at max_labels_count = 500 | 0 |
| Data Window values: delta, CVD_a, σ_r, σ_d, ρ, λ_ols, Z, P-leg, F-leg, zF, zP, η, quality, nIntra | `plot(…, display = display.data_window)` | 14 |
| alertconditions: Z ≥ +2 first cross, Z ≤ −2 first cross, buy absorbed, sell absorbed, pinned, resolved continuation, resolved held, price-without-flow up/down, gate opened | `alertcondition` | 10 |
| **Total** | | **≈ 33 of 64** |

### 8.4 Table (top-right, small)

| Row | Content |
|---|---|
| 1 | Source and quality badge, e.g. "Intrabar 1 · Medium" or "Chart-bars · Low (price-derived)" |
| 2 | Intrabars per bar (average) and coverage % of loaded bars. Red warning if the average is below 5 (LucF convention). |
| 3 | ρ(Δp, Δ) [95% CI], N. Grey when the gate is closed. |
| 4 | R² and λ_ols in bps per 1,000 units |
| 5 | Divergence Z (K) and the four-state label, or "warming up (n/M)" |
| 6 | Last event and its resolution state |
| 7 | NAR since anchor (CVD/ΣV), anchor name |
| 8 | Volume type (`syminfo.volumetype`) with a warning for tick or n/a |
| 9 | Evidence note: "Divergence ≠ forecast; resolve with price" |

### 8.5 Alerts

- `alertcondition()` for each class in §8.3, with const messages and `{{ticker}}` / `{{interval}}` placeholders.
- One `alert()` with a dynamic message (symbol, timeframe, state, Z, zF, zP, ρ, source and quality) at `alert.freq_once_per_bar_close`. It fires only on confirmed bars.
- Every alert condition includes `gateOn` and the quality requirement. The message states "unconfirmed" until the state machine resolves.

### 8.6 Performance considerations

- **Request budget:** one unique `request.security_lower_tf` (a tuple of 3 arrays) and at most one `request.footprint` (gated). That is 2 of 40.
- **Memory:**
  - 1S intrabars on a 5m chart give 300 elements × 3 arrays per bar, and coverage of about 333 chart bars under the 100K cap.
  - 1-minute intrabars on 5m give 5 per bar and about 20K chart bars.
  - Leave `calc_bars_count` at its default; expose it only if users hit memory errors.
  - An alternative for very fine intrabar timeframes is the TradingView `ta` library pattern: `request.security` on the lower timeframe with an accumulator, which returns one float per bar. It needs an extra counter for coverage.
- **History buffers:** `ta.sma(x², M = 1000)` and `math.sum(…, K)` are within the 5000-bar series buffer, so no `max_bars_back` is needed.
- **Loops:** none per bar, apart from optional array reductions (`array.sum` is native).
- **Table:** created once with `var`, filled only on `barstate.islast`.
- **Labels:** at most 500, FIFO; old labels drop silently.

### 8.7 Repainting policy

- Lower-timeframe arrays and footprint data fill in as the realtime bar forms. Lines on the realtime bar are provisional.
- Z, events, resolutions and alerts are evaluated only on `barstate.isconfirmed`.
- Pivot divergences are drawn at the pivot but alerted R bars later.
- Visible-range normalization is not offered. No `lookahead_on`. No whole-history min, max or percentile.
- `request.security_lower_tf` history and realtime data may differ (documented). Footprint realtime vs history may differ (third-party claim).

---

## 9. Known limitations and disclaimers

1. **CVD is trade imbalance only.** Passive liquidity, cancellations, icebergs and hidden orders are invisible to it. Much of any "divergence" is limit-order flow, which the literature treats as normal (Weber-Rosenow; Bouchaud et al.; Eisler et al.) and which may itself be informed (Kaniel-Liu; Brogaard et al.).
2. **Delta is estimated, except partly with footprint.**
   - Even footprint is classified by TradingView "based on intrabar price action", not by exchange aggressor flags.
   - 1-minute and chart-bar estimates are partly a function of price (circularity). Divergence fidelity falls from about 0.8–0.9 (1S) to 0.3–0.87 (1m) to about 0.1–0.4 (chart) [E].
   - Chart-only CVD tracks true CVD no better than price itself does.
3. **No validated directional edge.**
   - No peer-reviewed study validates forward returns after CVD divergence, absorption or exhaustion in futures or crypto.
   - Our real-data tests found a null for the K = 20 divergence statistic, and only weak, in-sample, single-venue continuation after 15-minute absorption that disappeared with estimated delta.
   - Labels are descriptive. Users should validate per instrument and timeframe.
4. **Single-venue CVD.** In crypto, single-venue or single-instrument CVD includes venue-specific flow; the common component explains about 80% of BTC returns (Makarov-Schoar). Spot vs perpetual and base vs quote vs contract units differ. Multi-venue aggregation is out of scope for v1 (possible in v2 via additional lower-timeframe requests with unit conversion).
5. **Calibration rests on one crypto spot pair over 4 months plus simulations.**
   - CME futures (Globex vs RTH anchors), equities and liquid perpetuals are not yet validated.
   - Thresholds (gate 0.30, |Z| 2/3, K = 20, M = 1000, clip 4) are theory-backed and empirically sensible but not cross-validated out of sample.
6. **Coverage limits.**
   - 100K/125K/200K intrabars bound the history of 1S/1T delta.
   - History silently mixes tiers unless seams are shown; the indicator shows them.
   - Footprint history depth is undocumented.
7. **Plan-dependent behaviour is not fully documented.** Footprint on lower plans, and 1S/1T requests per plan, must be tested live (§7.4).
8. **Impact nonlinearity.** Linear σ-scaling over-projects on climactic flow. Winsorizing at ±4 mitigates this but does not model the saturation.
9. **Regime breaks.** Auctions, limit-up/down, news and pegs decouple flow and price (Takahashi; Killeen-Lyons-Moore). The gate catches some of these by ρ collapsing, but not instantly.
10. **Citation status.**
    - Numbers tagged [V-sec] or [M] must not appear in user-facing text without checking the primary source. This includes the CKS 65%/32% R², the CCZ R² values, Patzelt-Bouchaud's exponents, the ELO 2016 df = 0.25, Hendershott-Menkveld's magnitudes, the MacKinnon critical values and the Kendall bias formula.
    - The web-search budget was exhausted during this run, so these could not be rechecked.
11. **This is an analytical tool, not investment advice.** All statistics are causal approximations on bar data. Realtime values are provisional until the bar closes.
