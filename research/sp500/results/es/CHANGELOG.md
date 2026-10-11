# Changelog: ES event study (`study_es.py`, `results/es/`)

## 2026-10-11: external review (findings M1, m1–m5, R1–R7)

**Process.** Each finding was first reproduced independently from the feature files and the clean 1-minute file,
before any code was changed. All 12 were confirmed: M1 is major, the others minor. Small numeric differences from
the reviewers' figures are noted in the table. The pre-registered plan, the parameters, the primary family and the
primary-endpoint numbers are unchanged. Every change is logged in section 10 of `results.md`, and every addition is
labelled post hoc in section 11.

### Findings, verdicts and changes

| id | verdict | change |
|---|---|---|
| M1 | Confirmed. The reproduction matches the reviewer exactly with the old design: 5m absorbed − confirmed matched \|σ\| excess +0.058 σ (p 0.015); 15m −0.120 σ (p 5e-7). | Added the test to `twins_table` (post hoc, secondary): an unmatched \|σ\| difference and a difference of the matched \|σ\| excess, with a joint day-clustered SE. Replaced the "volatility, not direction … CVD conditions add little" sentence with a descriptive statement. |
| m1 (a) | Confirmed. On 15m, same-class events were 8.1% / 7.5% / 8.1% of the controls of abs_buy / abs_sell / pin_buy (1–2% on 5m). | All events of the same class (or twin set) are now removed from the control cells. |
| m1 (b) | Confirmed. Control-mean noise SD on 15m: 0.014 / 0.014 / 0.023 σ. | The SE and the bootstrap now include the control means' sampling error, through the per-day influence of every control bar, clustered by day jointly with the events. The old SE is kept as `se_ctrl_fixed`. |
| m1 (c) | Confirmed by inspection: full-sample σr cut points. | σr terciles are now taken within each year for matching. The stability split keeps the full-sample terciles (absolute volatility regimes). |
| m1 (d) | Confirmed. The reviewer's P_K-matched numbers reproduce exactly. | Added a P_K-matched control (year × RTH × 30-min bucket × 12 P_K bins) and an exact-bar-slot control, both post hoc (section 11.1). Text now says "sign and tercile of \|pE\|". |
| m2 | Confirmed. The best cell is 15m pin_sell at 60 min: +1.046 pt, two-sided p 0.056, n 385 vs 543 at 30 min. Close-bar 60-min windows survive 81% / 24% / 84% by era. | One-sided p of net > 0, with BH over the 224 full-sample rule cells (`q_net_1s`, `q_opp_net_1s`). Added `valid_share` and a window-survival-by-era table (section 11.5). The best-cell caveats are in the text, including its σ-unit net. |
| m3 | Confirmed. Zero shares are 3.3–6.6%; hit among non-zero outcomes is 46.2–55.6%. The bps extremes come from different classes. | Added `hit_nz` and `loss` columns and reported `hit_nz` in the tables. The bps range is now worded as "class means range from −1.56 to +0.97 bps". |
| m4 | Confirmed. | The explanation is now labelled a hypothesis, with the 14:59 settlement-minute mechanism, the fidelity cross-reference and a sensitivity that drops the open/close bars (section 11.2). |
| m5 | Confirmed by inspection. | Paths now fail closed through the new `studyenv.py`. OUT_DIR and DATA_DIR are required, with no defaults relative to the code. FEAT_DIR (per-bar features) and the PineTS work folder are refused inside any git work tree. A missing feature file stops `study_es.py` unless `--rebuild-features` is given. Applied to `bars.py`, `features.py`, `study_es.py`, `study_robust.py`, `study_fidelity.py`, `validate_pine.py`, `rounding_effect.py` and `validation_summary.py`. |
| R1 | Confirmed. Settlement-window shares are 16.6–20.4% (5m) and 40.4–49.2% (15m); side = sign(14:59 candle) in 99.6–100%. The reviewer's volume shares were slightly off: 2008 is 1.30%, not 1.4%, and 2017–2026 is 2.9–4.2%, not 3.0–4.3% (2020: 2.86%). | Added the settlement table, the exact-slot matched control, the slot-drift table and the 14:59 volume share by year (section 11.2). The text states the mechanism, and the user guidance recommends flagging these alerts. |
| R2 | Confirmed exactly: 0/16 under BH with a 1- and 2-minute delay; min p 0.102 / 0.188. | Section 1 now states the zero-latency entry. Added a latency table (section 11.3) and the real-time-data note. |
| R3 | Confirmed by inspection. | The cost is described as a lower bound. Added a 2-tick stress column (0.575 pt) and a note that no news/FOMC filter was applied. |
| R4 | Confirmed exactly: 78 of 2,636 (5m, 60 on the first bar) and 146 of 1,758 (15m, 126 on the first bar). | Added a sensitivity that excludes resolutions of absorptions born in an earlier session (section 11.4), plus a caveat and user guidance. |
| R5 | Confirmed. The columns held two-sided tests of net = 0. | Renamed them to `p_net_eq0` / `p_opp_net_eq0`; one-sided columns added as under m2. |
| R6 | Same as m3. | Same as m3. |
| R7 | Confirmed: manifest es_1m.sessions has 4,841 total and 4,688 clean (75 roll, 30 non-dominant, 35 roll-window). | Added a data-scope caveat (section 1) and user guidance. |

Also fixed: literal `|` characters in table headers (such as `|σ| ev`) split the Markdown table cells; `md_table` now
escapes them. The heading of section 10 is now in English.

### How the results moved

**Unchanged, verified identical before and after:**
- the class tables (all means and p-values, both timeframes), so the primary endpoint is unchanged;
- the signed twin differences;
- the baseline, gate study, Z calibration and per-year signs;
- the cost point estimates (gross and net).

**Matched controls at 30 min** (old design → corrected design). The corrections move event − control away from zero
where same-class events had filled the cells (15m absorbed and pinned). On 15m the SE widens by 6–9% for the absorbed
and pinned classes and by up to 13% for the large twin sets. On 5m it changes by −8% to +1%: the within-year σr
terciles make the cells more homogeneous. Still 0 of 18 under BH on each timeframe.

| tf | set | control σ | event − control σ | SE | p |
|---|---|---|---|---|---|
| 5m | z_dn_flow | +0.002 → +0.004 | −0.037 → −0.040 | 0.024 → 0.023 | 0.120 → 0.086 |
| 5m | res_cont_up | −0.007 → +0.002 | −0.121 → −0.131 | 0.079 → 0.078 | 0.124 → 0.095 |
| 15m | abs_buy | +0.051 → +0.031 | +0.066 → +0.077 | 0.047 → 0.050 | 0.158 → 0.123 |
| 15m | pin_buy | +0.047 → +0.006 | +0.092 → +0.139 | 0.065 → 0.071 | 0.158 → 0.049 |
| 15m | res_cont_up | −0.006 → −0.016 | +0.138 → +0.142 | 0.069 → 0.070 | 0.046 → 0.042 |
| 15m | pwf_dn | −0.010 → −0.001 | +0.183 → +0.159 | 0.120 → 0.121 | 0.129 → 0.190 |

- Raw p < 0.05 at 30 min: 5m 0 → 0 (smallest p 0.086); 15m 1 → 2 (pin_buy, res_cont_up). Smallest q at 30 min:
  5m 0.85, 15m 0.32.
- Twin sets on 5m at 5 min: confirmed −0.037 → −0.042 σ, price with flow −0.033 → −0.041 σ (p ≤ 0.0004). Their q
  within the matched table (secondary, flag only) moved from 0.056 to 0.013–0.014: this 5-minute reversal after large
  flow-confirmed shocks now passes BH in that secondary family. It is about a tenth of the 5-minute cost and is not an
  indicator signal. The interpretation reports it as a flag.
- Unsigned \|σ\| excess at 30 min, classes with p < 0.05: 5m 9 → 10 of 16, 15m 7 → 7. The old text's "+0.06 to
  +0.18 σ for 12 classes, p < 0.05 for 8, plus pivot bottom" is now 13 classes from +0.06 to +0.18 σ, 10 with
  p < 0.05. 15m absorbed buy: +0.028 → +0.001 σ.
- Stability table, matched column: largest change 0.04 σ (5m) and 0.08 σ (15m). 5m flow-led Z≤−2 in ETH is now
  p 0.006 (it was raw p < 0.01 in the raw-mean column already). 15m held-down in the high-σr tercile went from p 0.002
  to p > 0.01. Nothing survives BH, before or after.

**M1 test, corrected design** (absorbed − confirmed and pwf − price-with-flow, matched \|σ\| excess difference,
30 min). These numbers replace the sentence the review flagged.

| tf | absorbed − confirmed | pwf − price with flow |
|---|---|---|
| 5m | +0.061 σ (SE 0.024, p 0.012) | +0.041 σ (p 0.27) |
| 15m | −0.163 σ (SE 0.027, p < 1e-6) | +0.072 σ (p 0.22) |

**Costs.** No rule cell has net > 0 at a one-sided BH-corrected level: the smallest one-sided p over the 224 cells is
0.028 (15m pin_sell, 60 min) and every q is 1.000. That cell's σ-unit net is +0.034 σ (p 0.66). At the 2-tick stress
cost, the three positive opposite rules on 5m at 30 min turn negative.

**Post hoc (new):**
- P_K-matched Z classes on 5m: +0.010 / +0.017 / −0.039 / −0.009 σ (p ≥ 0.10); 0/18 under BH on both timeframes.
- Settlement window, 15m: abs_buy +0.133 σ (p 0.003) and pin_buy +0.189 σ (p 0.003) against exact-slot controls
  become +0.012 σ (p 0.86) and −0.035 σ (p 0.79).
- Latency: 0/16 under BH at 1 and 2 minutes.
- Prior-session resolutions excluded: nothing material changes.

### Not changed, and why

- `study_robust.py`: its matched controls already removed same-class events and used within-year σr terciles. Its SE
  still treats the control means as fixed: about 5% on the SE of the rarest classes, not material to its conclusions.
  Only its path handling changed. A smoke run of `mes_5m` into a throwaway folder reproduced the stored
  `mes_5m_classes.csv` exactly, so the robust results were not rerun.
- `study_fidelity.py`: only path handling changed; not rerun.
- The indicator source: not modified, as instructed. Indicator-side suggestions are in the interpretation, under user
  guidance (flag settlement-window absorbed/pinned alerts; expire pending absorptions at the session end).

### Versioning decision for the copy into `research/sp500/` (m5)

- Version the code, `results.md`, `interpretation.md`, `CHANGELOG.md` and the CSVs of `results/es/`,
  `results/robust/` and `results/fidelity/`. They are aggregate statistics: counts, means, p-values and per-session
  correlations, with no prices and no per-bar series.
- The repository's `.gitignore` ignores `*.csv`, so the copy needs a scoped exception:
  `!research/sp500/results/**/*.csv`.
- Never copy the `features/` and `validation/` folders, which hold licensed per-bar data. `studyenv.py` refuses to
  write them inside a git work tree.
- Run from the repository with `OUT_DIR` pointing to a scratch folder for features, and `RES_DIR` (or `OUT_DIR`)
  pointing to where the aggregate results should go.
