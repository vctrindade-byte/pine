## Summary and interpretation

Written after the pre-registered run, from the tables below, and revised after an external review. The plan, the
inputs and the primary family were not changed after the outcomes were seen. Section 10 lists the departures from the
plan. The review corrected the matched-control implementation and relabelled the cost p-values; section 11 holds the
post-hoc sensitivities it asked for. `CHANGELOG.md` lists every change and how each number moved. Words such as
"hint" describe numbers that do not survive multiple testing. They are not findings.

**Primary endpoint (ES 5m, signed σ return at 30 min, 16 classes): null.** No class survives Benjamini–Hochberg at
5% (all q = 1.000). None reaches even raw p < 0.05; the smallest p is 0.100 (continuation-up resolution, −0.130 σ).
The 16 class means lie between −0.130 σ and +0.041 σ; in basis points they range from −1.56 to +0.97 bps (the two
ranges come from different classes). Among the non-zero outcomes, 46.2–55.6% are in the signal's direction (no
information = 50%). The pre-registered hit rate, which counts the 3.3–6.6% of exact zeros (tick grid) as misses, is
44.5–52.0%, so a random-direction trade would score about 47–48% on it. The day-block bootstrap CIs are about
±0.04–0.05 σ for the frequent classes (flow-led Z states, pivots), ±0.10 σ for absorption, and ±0.13–0.17 σ for the rare
classes (pinned, price without flow, resolutions). Entry is the first print after the alert bar closes, a zero-latency
upper bound; with a 1- or 2-minute delay the endpoint stays null (0 of 16 under BH, smallest p 0.102 and 0.188;
section 11.3).

**Power, relative to costs.** A 30-min round trip costs 0.13–0.22 σ (0.325 pt, section 6). With 80% power the study
would have detected true means of 0.05–0.07 σ for the flow-led Z states and pivots and about 0.14 σ for absorption.
Those are smaller than the cost, so a tradeable effect in these classes is effectively ruled out. For the price-led Z
states the MDE is 0.13–0.14 σ, about the size of the cost. For pinned, price without flow and resolutions it is
0.19–0.25 σ, also about the cost: an effect just large enough to pay the round trip could have been missed there. The
MDE is a post-hoc column.

**Secondary analyses: consistent with chance.**
- ES 5m, all horizons: 5 of 64 class × horizon cells have raw p < 0.05, against about 3.2 expected by chance. The
  smallest q in the table is 0.28.
- ES 15m: 4 of 48 cells (about 2.4 expected), smallest q 0.30. At 30 min on 15m, buy absorbed shows +0.111 σ
  (p 0.011) and pinned buy +0.143 σ (p 0.019), both q 0.150, not significant.
- The 15m numbers are not a direction signal. Sell absorbed at 30 min is −0.069 σ in its own direction, so the price
  rose after both absorption sides. Against the matched controls (corrected design), buy absorbed is +0.077 σ
  (p 0.12) and pinned buy +0.139 σ (p 0.049, q 0.32). Section 11.2 locates both: they are significant only for events
  whose window contains the 14:59 CT settlement minute, and they vanish against exact-slot controls (see the post-hoc
  note below).

**Does the CVD add information beyond price? No detectable directional information.**
- *Twins, absorbed vs confirmed.* An absorption (flow shock, price not following) was followed by the same 30-min
  return as a same-size flow shock that did move the price: difference +0.015 σ, p 0.68, bootstrap CI
  [−0.051, +0.084] on 5m; −0.016 σ, p 0.64 on 15m. The flow-versus-price condition that defines the label changes
  nothing measurable in the signed return that follows.
- *Twins, price without flow vs price shocks with flow.* On 5m: +0.136 σ at 5 min and +0.128 σ at 15 min (p 0.017–0.018,
  q 0.109, not significant). At 30 min the difference is +0.028 σ (p 0.61). This is a short-lived hint that price
  moves without flow carry on slightly more than price moves with flow. It is not confirmed, and it is below the cost
  at those horizons (0.33–0.53 σ at 5 min, 0.19–0.31 σ at 15 min).
- *Matched random controls* (same session type, 30-min bucket, year, σr tercile within the year, sign of pE and
  tercile of |pE|; all events of the same class removed from the cells; SE including the sampling error of the control
  means). At 30 min no class differs from its matched controls after BH: 0 of 18 on each timeframe. On 5m none
  reaches raw p < 0.05 (smallest 0.086). On 15m two do (pinned buy +0.139 σ, p 0.049; continuation-up +0.142 σ,
  p 0.042; q 0.32 for both).
- *Matched on the K-bar price leg* (post hoc). The pre-registered cells match the 15-minute move pE, not the K-bar leg
  P_K that defines the Z classes. Matched instead on 12 bins of P_K, the Z classes stay null on 5m: +0.010, +0.017,
  −0.039 and −0.009 σ (p ≥ 0.10); no class survives BH on either timeframe (section 11.1).
- *The strongest number in these tables* comes from the twin sets on 5m at 5 min. Flow-confirmed shocks are −0.042 σ
  and price shocks with flow −0.041 σ against their matched controls (n ≈ 27,000 and 42,000, p ≤ 0.0004). After the
  matched-design correction they pass BH within the matched table (q 0.013–0.014; before: −0.037 and −0.033 σ,
  q 0.056). That table is a secondary family, so this is a flag, not a finding. It is a tiny 5-minute reversal after
  large flow-confirmed moves, about a tenth of the 5-minute cost (0.33–0.53 σ). It belongs to large shocks in general
  (both twin sets), not to an indicator signal. On 15m the twin sets drift slightly the other way (+0.02 to +0.03 σ at
  30 min, p 0.06–0.07).
- *Unsigned moves (volatility).* Descriptive; the event-versus-twin comparison was added after the review and is
  post hoc.
  - On 5m at 30 min, 13 of the 16 classes show an unsigned excess over their matched controls of +0.06 to +0.18 σ,
    10 of them with p < 0.05. Flow-led Z≤−2, pinned buy and pivot top are near zero. The twin sets show an excess too:
    +0.08 σ for confirmed flow shocks and +0.09 σ for price shocks with flow, both p < 0.001.
  - On 15m, absorbed and pinned events show no excess: +0.001, +0.022, −0.042 and +0.053 σ, p ≥ 0.32.
  - Whether the CVD condition itself changes the excess is mixed. Absorbed minus confirmed, matched excess: +0.061 σ
    on 5m (p 0.012), −0.163 σ on 15m (p < 0.001). Price without flow minus price with flow: +0.041 σ on 5m (p 0.27),
    +0.072 σ on 15m (p 0.22).
  - The unmatched gaps are larger, because time of day and volatility account for much of them. Price without flow
    minus price with flow: +0.22 σ on 5m, +0.19 σ on 15m (p ≤ 0.001). Absorbed minus confirmed: +0.07 σ on 5m,
    −0.28 σ on 15m.
  - So large flow or price shocks are followed by somewhat larger moves (METODOLOGIA 9.1: imbalance relates to
    volatility, not direction). The data do not show that the CVD conditions consistently add to that, and on 15m the
    absorption label marks smaller moves than a confirmed shock.

**Gate.**
- On ES with the 1-minute candle-rule delta, ρ̂ is high: median 0.71 on 5m and 0.66 on 15m. P(ρ̂ < 0.30) is 1.9% and
  0.9%, and the gate is open on 98.1% and 99.1% of hqOk bars. The 1-minute estimate inflates ρ, as METODOLOGIA 6.5
  notes.
- The gate is therefore almost never binding. Turning it off adds at most 27 events to a class on 5m, and ρmin 0.40
  removes at most 58. Every variant is null (0 of 16 under BH in each).
- The added and removed subsets are too small to say anything: n of 1 to 58, nothing interpretable. One cell has
  p 0.013, but n = 2.
- Point (d) of the audit (does the gate hide relevant regimes?) cannot be settled on this ES configuration, because
  the gate almost never closes.

**Costs (0.325 pt per round trip, $16.25: a lower bound).**
- The pre-registered cost fits a 1-lot in normal RTH liquidity. It is optimistic at the open, the 15:00 CT
  settlement, the release bars and the 17:00 CT reopen, where many signals cluster; in the thin 2008–2012 overnight
  book; and in the 2008 and 2020 stress periods. Section 6 adds a 2-tick stress cost (0.575 pt). No news-calendar or
  FOMC filter was applied.
- On 5m at 30 min, all 16 "trade s" rules are net negative (−0.04 to −0.89 pt). Three opposite rules are net positive:
  fading the two continuation resolutions and held-down, +0.09 to +0.24 pt. None is significant (two-sided p ≥ 0.42),
  and all three turn negative at the stress cost.
- Across all 224 rule cells (class × horizon × direction, both timeframes), no net expectancy is significantly above
  zero. On a one-sided test of net > 0 the smallest p is 0.028, and every BH q-value is 1.000. The cost tables'
  p-value columns are two-sided tests of net = 0 (renamed p_net_eq0 / p_opp_net_eq0); a small value there usually
  means significantly negative.
- The best single cell is pinned sell at 60 min on 15m: +1.05 pt net, one-sided p 0.028, n 385. It survives no
  correction, and it is not the same population as the 30-minute cell (n 543, −0.07 pt net). Most of these events sit
  on the 14:45 and 15:00 CT bars. Their 60-minute windows run past the session end unevenly by era: 81% survive in
  2008–12, 24% in 2013–20 and 84% in 2021–26 (section 11.5).
- In σ units the same cell nets only +0.03 σ (p 0.66). Point means weigh the later, higher-priced years more; the σ
  columns are the scale-free view.

**Stability.**
- Per-year signs are close to a coin toss: 6–11 positive years out of 19 on 5m (sign-test p ≥ 0.17), 7–14 on 15m
  (p ≥ 0.06).
- Both halves (2008–2016, 2017–2026) are null.
- A few RTH/ETH and σr-tercile cells reach raw p < 0.01; none survives BH (q ≥ 0.25 on 5m, ≥ 0.15 on 15m).
  - On 5m: flow-led Z≤−2 in ETH −0.082 σ (also −0.082 σ against matched controls, p 0.006); held-down in ETH −0.25 σ.
  - On 15m: buy absorbed in 2008–2016 +0.199 σ and in RTH +0.132 σ.

**Z calibration on ES.**
- P(|Z| ≥ 2) is 6.47% on 5m and 5.75% on 15m; P(|Z| ≥ 3) is 1.43% and 0.98% (normal: 4.55% and 0.27%). This is
  stable across the halves and every year (6.1–6.8% per year on 5m) and close to METODOLOGIA 6.8 (5.4–6.2% on BTC).
  Mean Z ≈ 0.
- Z is not calibrated by time of day. P(|Z| ≥ 2) is 8.9% in RTH vs 5.5% in ETH on 5m, and 9.4% vs 4.3% on 15m
  (RMS Z 1.16 vs 0.96 on 5m), because the RMS is pooled over the 23-hour Globex session.

**Post-hoc observation: absorbed and pinned events at the cash close (section 11.2; not pre-registered).**
- Absorbed and pinned events cluster at the cash close and the open. On 15m, 58% of absorptions and 67% of pinned
  events fall on the 14:45 and 15:00 CT bars; the 14:45 bar alone holds 564 of 1,267 buy and 519 of 1,286 sell
  absorptions. On 5m the most frequent absorption bars are 15:00, 08:30 and 15:05 CT.
- **Mechanism (hypothesis).** The 14:59 CT minute is the CME settlement window and the NYSE closing auction. Its share
  of the clean-session volume grew from 1.3% in 2008 to 2.9–4.2% from 2017 on. Under the TradingView Auto candle rule
  the whole volume of that one 1-minute candle goes to one side, so a window that contains it gets a large |Δ| whose
  side is set by a single candle.
  - The window contains the 14:59 minute for 40.4–49.2% of absorbed and pinned events on 15m and 16.6–20.4% on 5m.
  - In those events the side equals the sign of the 14:59 candle-rule delta in 99.6–100% of cases.
  - So these labels are at least partly an artefact of the delta estimator, not only of intraday volume seasonality.
  - The fidelity study agrees. On the 2026 TopstepX ES sample the 14:59 minute holds 6.6% of the volume, and the
    1-minute correlation between the 1-minute and 1-second candle-rule deltas is 0.36 with that minute and 0.64
    without it. The 5m flow-event recall of the 1-minute candle rule against the true aggressor delta is 0.13.
- **What it does to the outcomes.** The significant part of the 15m secondary hints sits in these settlement-window
  events, and the post-close drift accounts for it.
  - Buy absorbed with the 14:59 minute in its window: +0.133 σ (p 0.003). Pinned buy: +0.189 σ (p 0.003).
  - Against exact-slot controls (same bar of the day) those become +0.012 σ (p 0.86) and −0.035 σ (p 0.79).
  - Without the settlement window: +0.094 σ (p 0.19) and +0.096 σ (p 0.35). The point estimates are similar, on half
    the events, and not significant.
  - The price rose after both sides: sell absorbed in the settlement window is −0.073 σ in its own direction on 15m
    and −0.117 σ (p 0.005) on 5m.
  - The unconditional 30-min drift from the 15m 14:45 bar is +0.051 σ (p 0.002), against +0.027 σ (p 0.28) from 14:30.
    On 5m it is +0.037 to +0.046 σ from 14:50 and 14:55 (p ≤ 0.004), against −0.005 σ from 14:30. The 30-minute
    matching bucket mixes these slots, which is why the exact-slot control is the sharper test here.
  - On 5m, without the settlement window, absorbed and pinned events are null: |mean| ≤ 0.045 σ, p ≥ 0.44.
- Close-clustered windows often span the pre-2021 15:15–15:30 CT halt (`halt_share`, up to 28% on 15m), and their
  60-minute windows run past the session end unevenly by era (section 11.5).

**Other post-hoc caveats.**
- *Resolutions after the daily break.* A pending absorption's life is counted in bars, so it survives the daily break
  and weekends, and the 17:00 CT reopen gap can trigger its "continuation" or "held" alert. That covers 78 of 2,636
  resolution alerts on 5m (3.0%; 60 on the session's first bar) and 146 of 1,758 on 15m (8.3%; 126 on the first bar).
  Excluding them changes nothing material: on 5m continuation-up is −0.133 σ (p 0.10); on 15m it is +0.139 σ (p 0.06).
  Section 11.4.
- *Data scope.* The study uses clean front-month, dominant-contract sessions; roll, roll-window and non-dominant
  sessions are left out. A TradingView user on ES1! keeps those sessions, and the indicator's σΔ, ρ and RMS of D then
  differ for a few sessions around each roll. The null covers non-roll weeks only.

**For users of the indicator (guidance; the indicator source was not changed by this study).**
- Treat absorbed and pinned alerts whose 15-minute window contains the 14:59 CT minute as unvalidated: with the
  TradingView Auto delta their side is set by one candle. An indicator option to flag or suppress them would be a
  natural follow-up.
- Pending absorptions could expire at the session end, or gap-driven resolutions could be labelled.
- The timings above assume CME real-time data on TradingView; with 10-minute-delayed data the 5- and 15-minute
  horizons are gone before the alert arrives.
- Chart the dominant contract (or a volume-rolled continuous contract) and treat roll-week alerts as unvalidated.

**Bottom line.**
- On 18.7 years of ES front-month data with the TradingView-Auto delta (tier 2, 1-minute candle rule), none of the
  indicator's 16 signal classes predicts the signed return 30 minutes later. The primary endpoint is 0 of 16 after FDR,
  and none reaches even raw 5%; this holds with a 1–2 minute entry delay.
- Nothing in the secondary analyses survives multiple testing except a tiny 5-minute reversal after large,
  flow-confirmed shocks. That is not an indicator signal and is about a tenth of the cost. No naive rule earns money
  after costs. The CVD conditions add no detectable directional information beyond matched price moves.
- Large flow and price shocks are followed by somewhat larger moves. Whether the CVD conditions add to that is
  inconsistent between 5m and 15m.
- The 15m hints are significant only for absorbed and pinned events at the 14:59 CT settlement minute, where the
  1-minute candle rule assigns the whole closing-auction volume to one side. Against exact-slot controls they vanish:
  they are post-close drift.
- This agrees with METODOLOGIA 9.1 (the Z is a descriptive meter; events at most a slight short-term effect) and with
  the earlier BTC result, where the continuation after absorption disappeared with 1-minute estimated delta.
- The study does not test signals built on true aggressor delta (tier 3). ES 1-minute data cannot provide it, and the
  2013 tick sample (15 sessions) is far too short for this design.
