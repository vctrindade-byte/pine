#!/usr/bin/env python3
"""Delta fidelity: what the TradingView "Auto" setting (1-minute intrabars, candle rule, quality tier 2) loses on S&P
futures versus 1-second intrabars (1S, tier 3) and versus the true aggressor flow.

Part A — 2013 ES tick sample (Tick Data LLC, ESU13→ESZ13, 2013-09-01..20, 15 CME sessions; 2013-09-13 is the roll
session, kept and flagged; 2013-09-02 is the Labor Day short session). Delta variants per 1-minute bar
(clean/es_ticks_2013-09_1m.parquet):
    true   aggressor delta from the quote rule (Lee–Ready with the quote strictly before the trade; ≈96% of volume
           agrees with the CME aggressor flag on a 2025 Databento check) — the reference;
    cr1s   candle rule on 1-second bars (what 1S intrabars give on TradingView), tier 3;
    cr1m   candle rule on 1-minute bars (what "Auto" gives on a 5m/15m chart), tier 2;
    tick   tick rule on every trade (what 1T intrabars without quotes would give), tier 3 — extra reference.
For each chart timeframe (1m, 5m, 15m) the chart bars are rebuilt (bars.chart_bars) and the indicator port
(engine.run_engine, defaults) is run once per variant; true/cr1s/cr1m are checked against the feature files.
On the 1-minute chart cr1m is the candle of the bar itself: TradingView would give tier 1 (no Z, no events); it is
computed AS IF tier 2 and flagged.

Measured per timeframe:
  * per-bar delta: Pearson correlation with the true delta, sign agreement, partial correlation with the true delta
    given the bar's price increment r (the information beyond price), correlation with r (inflation of ρ); on the raw
    delta and on the indicator's clipped σ-units u_d (given u_r); all hours, RTH (09:30–16:00 ET) and ETH;
  * session CVD paths (Globex session anchor = the indicator's Auto anchor, and RTH anchor): correlation of the
    cumulative estimated delta with the cumulative true delta, with the log-price path as the benchmark;
  * indicator level: Z / zF / F_K correlation and Z sign agreement between variants, |Z| ≥ 2 state agreement, gate
    agreement; per variant gate-open rate, ρ distribution, P(|Z| ≥ 2), P(|Z| ≥ 3);
  * event overlap (labels as drawn: new absorbed / pinned / price-without-flow clusters, Z alerts, pivot divergences;
    and bar-level class membership): precision, recall and Jaccard of each estimated variant against the true-delta
    events, exact bar and within ±ke bars (±15 minutes), one-to-one matching, same class and side.
Uncertainty: session-block bootstrap (15 sessions) 95% intervals for the per-bar correlations.

Part B — TopstepX 2026 1-second bars (ES and MES, 2026-03-09..04-15) as a second 1S check, using only minutes whose
1-second volume equals the 1-minute volume (complete_1s); a chart bar is used when all its minutes are complete.
There is no true delta here: the check compares cr1m with cr1s (the 1S proxy) and puts the numbers next to the same
cr1m-vs-cr1s numbers of 2013, so that one can judge whether the 2013 picture carries over to the 2026 market. For the
indicator-level comparison both variants are run on the same stream in which incomplete bars are no-observation bars
(volume missing: they neither count nor break the quality run), so the two runs see the same observations.

Usage:  python3 -I study_fidelity.py            (env, required: DATA_DIR = clean data, OUT_DIR = study folder)
Outputs: OUT_DIR/results/fidelity/*.csv and fidelity_summary.json. No data rows are written, only statistics.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bars as B            # noqa: E402
import engine as E          # noqa: E402

import studyenv            # noqa: E402
SEED = 20261011
NBOOT = 2000

# variant → (delta column, configured tier)
VARIANTS = {'true': ('d_true', 3), 'cr1s': ('d_cr1s', 3), 'cr1m': ('d_cr1m', 2), 'tick': ('d_tick', 3)}
PAIRS = [('cr1m', 'true'), ('cr1s', 'true'), ('tick', 'true'), ('cr1m', 'cr1s')]
TFS = (1, 5, 15)


# ───────────────────────────── generic statistics ─────────────────────────────

def _suff(x, y, r, g, groups):
    """Per-group sufficient statistics for correlation / partial correlation (x, y given r)."""
    cols = np.column_stack([np.ones_like(x), x, y, r, x * x, y * y, r * r, x * y, x * r, y * r])
    out = np.zeros((len(groups), cols.shape[1]))
    gi = np.searchsorted(groups, g)
    np.add.at(out, gi, cols)
    return out


def _corr_from(s):
    """corr(x, y) and partial corr(x, y | r) from summed sufficient statistics (last axis)."""
    n, sx, sy, sr, sxx, syy, srr, sxy, sxr, syr = np.moveaxis(s, -1, 0)
    cxx = sxx / n - (sx / n) ** 2
    cyy = syy / n - (sy / n) ** 2
    crr = srr / n - (sr / n) ** 2
    cxy = sxy / n - sx * sy / n ** 2
    cxr = sxr / n - sx * sr / n ** 2
    cyr = syr / n - sy * sr / n ** 2
    with np.errstate(invalid='ignore', divide='ignore'):
        corr = cxy / np.sqrt(cxx * cyy)
        pxy = cxy - cxr * cyr / crr
        pxx = cxx - cxr ** 2 / crr
        pyy = cyy - cyr ** 2 / crr
        pcorr = pxy / np.sqrt(pxx * pyy)
        cxr_c = cxr / np.sqrt(cxx * crr)
        cyr_c = cyr / np.sqrt(cyy * crr)
    return corr, pcorr, cxr_c, cyr_c


def corr_block(x, y, r, g, nboot=NBOOT, seed=SEED):
    """Correlation, partial correlation given r, corr(x, r), corr(y, r) and sign agreement with session-block bootstrap
    95% intervals. x = estimate, y = reference (true), r = price increment, g = session label."""
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(r)
    x, y, r, g = x[ok], y[ok], r[ok], g[ok]
    groups = np.unique(g)
    s = _suff(x, y, r, g, groups)
    corr, pcorr, cxr, cyr = _corr_from(s.sum(0))
    sg_ok = np.sign(y) != 0
    agree = (np.sign(x) == np.sign(y)) & sg_ok
    gi = np.searchsorted(groups, g)
    ag = np.bincount(gi, agree, len(groups))
    an = np.bincount(gi, sg_ok, len(groups))
    rng = np.random.default_rng(seed)
    w = rng.multinomial(len(groups), np.full(len(groups), 1.0 / len(groups)), size=nboot).astype(float)
    bs = w @ s
    bc, bp, _, _ = _corr_from(bs)
    ba = (w @ ag) / (w @ an)
    q = lambda a: [float(np.nanpercentile(a, 2.5)), float(np.nanpercentile(a, 97.5))]
    spear = float(pd.Series(x).rank().corr(pd.Series(y).rank()))
    return {'n': int(len(x)), 'n_sessions': int(len(groups)), 'corr': float(corr), 'corr_ci': q(bc), 'spearman': spear,
            'pcorr_given_r': float(pcorr), 'pcorr_ci': q(bp), 'corr_est_r': float(cxr), 'corr_true_r': float(cyr),
            'sign_agree': float(ag.sum() / an.sum()), 'sign_agree_ci': q(ba)}


def match_events(ie, it, tol):
    """One-to-one matching of event bar indices ie (estimate) to it (reference) within |Δ| ≤ tol, nearest first."""
    ie, it = np.asarray(ie), np.asarray(it)
    if len(ie) == 0 or len(it) == 0:
        return 0
    d = np.abs(ie[:, None] - it[None, :])
    cand = np.argwhere(d <= tol)
    if len(cand) == 0:
        return 0
    order = np.argsort(d[cand[:, 0], cand[:, 1]], kind='stable')
    ue, ut, m = set(), set(), 0
    for a, b in cand[order]:
        if a in ue or b in ut:
            continue
        ue.add(a)
        ut.add(b)
        m += 1
    return m


def overlap_row(m, ne, nt):
    return {'n_est': int(ne), 'n_ref': int(nt), 'matched': int(m),
            'precision': (m / ne) if ne else np.nan, 'recall': (m / nt) if nt else np.nan,
            'jaccard': (m / (ne + nt - m)) if (ne + nt - m) else np.nan}


def event_sets(o: pd.DataFrame):
    """Event label sets as drawn by the indicator: (class, side) → bar indices (confirmation / label bar)."""
    ev = {}
    for side in (1, -1):
        sd = 'buy' if side > 0 else 'sell'
        ev[f'abs_{sd}'] = np.flatnonzero((o.new_abs.to_numpy() == 1) & (o.ev_side.to_numpy() == side))
        ev[f'pin_{sd}'] = np.flatnonzero((o.new_pin.to_numpy() == 1) & (o.pin_side.to_numpy() == side))
        ev[f'pwf_{"up" if side > 0 else "down"}'] = np.flatnonzero((o.new_pwf.to_numpy() == 1) & (o.pwf_side.to_numpy() == side))
    ev['z_alert_up'] = np.flatnonzero(o.al_z_up.to_numpy() == 1)
    ev['z_alert_dn'] = np.flatnonzero(o.al_z_dn.to_numpy() == 1)
    ev['piv_top'] = np.flatnonzero(o.piv_top.to_numpy() == 1)
    ev['piv_bot'] = np.flatnonzero(o.piv_bot.to_numpy() == 1)
    return ev


def flag_sets(o: pd.DataFrame, thr=2.0):
    """Bar-level class membership (with side) for Jaccard on bars rather than on cluster starts."""
    zf = o.zF.to_numpy()
    zp = o.zP.to_numpy()
    z = o.Z.to_numpy()
    g = o.gate.to_numpy() == 1
    fl = {}
    with np.errstate(invalid='ignore'):
        sfz, spz = np.sign(zf), np.sign(zp)
        for side in (1, -1):
            sd = 'buy' if side > 0 else 'sell'
            fl[f'absorbed_{sd}'] = (o.absorbed.to_numpy() == 1) & (sfz == side)
            fl[f'pinned_{sd}'] = (o.pinned.to_numpy() == 1) & (sfz == side)
            fl[f'pwf_{"up" if side > 0 else "down"}'] = (o.pwf.to_numpy() == 1) & (spz == side)
        fl['z_ge_thr'] = g & (z >= thr)
        fl['z_le_-thr'] = g & (z <= -thr)
        fl['abs_zF_ge2_buy'] = g & (zf >= 2)
        fl['abs_zF_ge2_sell'] = g & (zf <= -2)
    return fl


def indicator_stats(o: pd.DataFrame, rth: np.ndarray):
    """Per-variant indicator summary: gate, ρ, P(|Z| ≥ 2/3) (bars with Z and zCalOk, as the Z tooltip), events."""
    z = o.Z.to_numpy()
    zc = np.isfinite(z) & (o.z_cal_ok.to_numpy() == 1)
    hq = o.hq_ok.to_numpy() == 1
    g = o.gate.to_numpy() == 1
    rho = o.rho_p.to_numpy()[hq]
    zf = o.zF.to_numpy()
    zfo = np.isfinite(zf)
    res = {
        'bars': int(len(o)), 'hq_ok_bars': int(hq.sum()), 'z_bars_calok': int(zc.sum()),
        'gate_open_pct_of_hq': float(100 * g[hq].mean()) if hq.any() else np.nan,
        'gate_open_pct_of_hq_rth': float(100 * g[hq & rth].mean()) if (hq & rth).any() else np.nan,
        'gate_open_pct_of_hq_eth': float(100 * g[hq & ~rth].mean()) if (hq & ~rth).any() else np.nan,
        'rho_median': float(np.nanmedian(rho)) if len(rho) else np.nan,
        'rho_q10': float(np.nanpercentile(rho, 10)) if len(rho) else np.nan,
        'rho_q90': float(np.nanpercentile(rho, 90)) if len(rho) else np.nan,
        'P_absZ_ge2_pct': float(100 * (np.abs(z[zc]) >= 2).mean()) if zc.any() else np.nan,
        'P_absZ_ge3_pct': float(100 * (np.abs(z[zc]) >= 3).mean()) if zc.any() else np.nan,
        'P_absZ_ge2_given_gate_pct': float(100 * (np.abs(z[zc & g]) >= 2).mean()) if (zc & g).any() else np.nan,
        'P_abs_zF_ge2_pct': float(100 * (np.abs(zf[zfo]) >= 2).mean()) if zfo.any() else np.nan,
        'P_abs_zF_ge3_pct': float(100 * (np.abs(zf[zfo]) >= 3).mean()) if zfo.any() else np.nan,
    }
    for k in ('new_abs', 'new_pin', 'new_pwf', 'al_z_up', 'al_z_dn', 'piv_top', 'piv_bot', 'res_cont', 'res_held', 'res_exp'):
        res[f'n_{k}'] = int(o[k].sum())
    return res


def agreement(oa: pd.DataFrame, ob: pd.DataFrame, thr=2.0):
    """Indicator-level agreement of variant a (estimate) with b (reference)."""
    za, zb = oa.Z.to_numpy(), ob.Z.to_numpy()
    both = np.isfinite(za) & np.isfinite(zb)
    cal = both & (oa.z_cal_ok.to_numpy() == 1) & (ob.z_cal_ok.to_numpy() == 1)
    res = {'z_bars_both': int(both.sum())}
    res['Z_corr'] = float(np.corrcoef(za[both], zb[both])[0, 1]) if both.sum() > 2 else np.nan
    res['Z_sign_agree'] = float((np.sign(za[both]) == np.sign(zb[both])).mean()) if both.any() else np.nan
    ga, gb = oa.gate.to_numpy() == 1, ob.gate.to_numpy() == 1
    sa = np.where(ga & (za >= thr), 1, np.where(ga & (za <= -thr), -1, 0))[cal]
    sb = np.where(gb & (zb >= thr), 1, np.where(gb & (zb <= -thr), -1, 0))[cal]
    ref_on = sb != 0
    est_on = sa != 0
    res['state_bars_calok'] = int(cal.sum())
    res['ref_state_bars'] = int(ref_on.sum())
    res['est_state_bars'] = int(est_on.sum())
    res['state_recall'] = float((sa[ref_on] == sb[ref_on]).mean()) if ref_on.any() else np.nan
    res['state_precision'] = float((sa[est_on] == sb[est_on]).mean()) if est_on.any() else np.nan
    res['state_opposite_sign_bars'] = int(((sa * sb) < 0).sum())
    for col in ('zF', 'f_leg', 'ud', 'D'):
        a, b = oa[col].to_numpy(), ob[col].to_numpy()
        ok = np.isfinite(a) & np.isfinite(b)
        res[f'{col}_corr'] = float(np.corrcoef(a[ok], b[ok])[0, 1]) if ok.sum() > 2 else np.nan
    zfa, zfb = oa.zF.to_numpy(), ob.zF.to_numpy()
    ok = np.isfinite(zfa) & np.isfinite(zfb) & (np.abs(zfb) >= 2)
    res['zF_sign_agree_when_ref_abs_ge2'] = float((np.sign(zfa[ok]) == np.sign(zfb[ok])).mean()) if ok.any() else np.nan
    res['zF_abs_ge2_recall'] = float((np.abs(zfa[ok]) >= 2).mean()) if ok.any() else np.nan
    hq = (oa.hq_ok.to_numpy() == 1) & (ob.hq_ok.to_numpy() == 1)
    res['gate_agree'] = float((ga[hq] == gb[hq]).mean()) if hq.any() else np.nan
    return res


def overlaps(oa, ob, ke, pair, tf, extra=None):
    rows = []
    ea, eb = event_sets(oa), event_sets(ob)
    for tol_name, tol in (('exact', 0), ('pm_ke', ke)):
        tot = np.zeros(3)
        for k in ea:
            m = match_events(ea[k], eb[k], tol)
            rows.append({'tf_min': tf, 'pair': pair, 'level': 'event', 'class': k, 'tolerance': tol_name, 'tol_bars': tol,
                         **overlap_row(m, len(ea[k]), len(eb[k])), **(extra or {})})
            tot += [m, len(ea[k]), len(eb[k])]
        for grp, keys in (('all_events', list(ea)), ('flow_events', [k for k in ea if k.startswith(('abs', 'pin', 'pwf'))])):
            m = sum(match_events(ea[k], eb[k], tol) for k in keys)
            rows.append({'tf_min': tf, 'pair': pair, 'level': 'event', 'class': grp, 'tolerance': tol_name, 'tol_bars': tol,
                         **overlap_row(m, sum(len(ea[k]) for k in keys), sum(len(eb[k]) for k in keys)), **(extra or {})})
    fa, fb = flag_sets(oa), flag_sets(ob)
    for k in fa:
        a, b = fa[k], fb[k]
        m = int((a & b).sum())
        rows.append({'tf_min': tf, 'pair': pair, 'level': 'bar', 'class': k, 'tolerance': 'exact', 'tol_bars': 0,
                     **overlap_row(m, int(a.sum()), int(b.sum())), **(extra or {})})
    return rows


def cvd_paths(b: pd.DataFrame, est: str, ref: str, mask=None, min_bars=20):
    """Per session: corr(cumsum est, cumsum ref) and the benchmark corr(log price path, cumsum ref); Globex anchor and
    RTH anchor. mask: bars to use (others dropped before the cumulative sums)."""
    rows = []
    d = b if mask is None else b[mask]
    for anchor in ('globex', 'rth'):
        dd = d if anchor == 'globex' else d[d.rth.to_numpy()]
        for sd, g in dd.groupby('session_date', sort=True):
            if len(g) < min_bars:
                continue
            ce, cr = g[est].cumsum().to_numpy(float), g[ref].cumsum().to_numpy(float)
            lp = np.log(g.c.to_numpy(float)) - math.log(float(g.o.iloc[0]))
            if ce.std() == 0 or cr.std() == 0:
                continue
            rows.append({'anchor': anchor, 'session_date': str(pd.Timestamp(sd).date()), 'bars': int(len(g)),
                         'path_corr': float(np.corrcoef(ce, cr)[0, 1]), 'price_path_corr': float(np.corrcoef(lp, cr)[0, 1])})
    return rows


def run_variant(b: pd.DataFrame, dcol: str, tier: int, tf: int, vol_mask=None) -> pd.DataFrame:
    vol = b.v.to_numpy(float)
    dl = b[dcol].to_numpy(float)
    src_vol = vol.copy()
    if vol_mask is not None:            # bars outside the mask: no observation (source volume missing)
        src_vol = np.where(vol_mask, vol, np.nan)
        dl = np.where(vol_mask, dl, np.nan)
    p = E.Params(tf_sec=tf * 60)
    return E.run_engine(pd.DataFrame({
        'open': b.o.to_numpy(float), 'high': b.h.to_numpy(float), 'low': b.l.to_numpy(float), 'close': b.c.to_numpy(float),
        'volume': vol, 'delta': dl, 'session_first': b.session_first.to_numpy(), 'tier': tier, 'src_vol': src_vol,
        'has_src': np.ones(len(b), bool)}), p)


# ───────────────────────────── part A: 2013 tick sample ─────────────────────────────

def tick_sample_bars(tf: int) -> pd.DataFrame:
    m1 = B.tick_sample_1m()
    m1['d_tick'] = m1['delta_tick'].astype(np.int64)
    return B.chart_bars(m1, tf, delta_cols=('d_true', 'd_cr1s', 'd_cr1m', 'd_tick'))


def check_against_features(o: pd.DataFrame, tf: int, var: str):
    fn = studyenv.feat_dir() / f'es_tick_{tf}m_{var}.parquet'
    if not fn.exists():
        return None
    f = pd.read_parquet(fn, columns=['Z', 'new_abs', 'new_pwf', 'al_z_up'])
    za, zb = o.Z.to_numpy(), f.Z.to_numpy()
    same_na = bool(np.array_equal(np.isfinite(za), np.isfinite(zb)))
    ok = np.isfinite(za) & np.isfinite(zb)
    mx = float(np.max(np.abs(za[ok] - zb[ok]))) if ok.any() else 0.0
    flags = all(np.array_equal(o[k].to_numpy(), f[k].to_numpy()) for k in ('new_abs', 'new_pwf', 'al_z_up'))
    if not (same_na and mx < 1e-9 and flags):
        raise AssertionError(f'feature file mismatch for {fn.name}: same_na={same_na} max|dZ|={mx} flags={flags}')
    return mx


def part_a():
    per_bar, paths, ind, agr, ovl, checks = [], [], [], [], [], {}
    for tf in TFS:
        b = tick_sample_bars(tf)
        rth = b.rth.to_numpy()
        outs = {}
        for var, (dcol, tier) in VARIANTS.items():
            o = run_variant(b, dcol, tier, tf)
            outs[var] = o
            if var != 'tick':
                checks[f'{tf}m_{var}_max_abs_dZ_vs_feature_file'] = check_against_features(o, tf, var)
        ke = outs['true'].attrs['ke']
        g = b.session_date.to_numpy()
        r = outs['true'].r_bar.to_numpy()
        ur = outs['true'].ur.to_numpy()
        for var in ('cr1m', 'cr1s', 'tick'):
            for sub, msk in (('all', np.ones(len(b), bool)), ('rth', rth), ('eth', ~rth)):
                x = b[VARIANTS[var][0]].to_numpy(float)
                y = b.d_true.to_numpy(float)
                row = corr_block(np.where(msk, x, np.nan), y, r, g)
                per_bar.append({'tf_min': tf, 'variant': var, 'subset': sub, 'scale': 'raw_delta', **row})
                # σ-units as the indicator uses them (each variant normalised by its own lagged σΔ), given u_r
                xu, yu = outs[var].ud.to_numpy(), outs['true'].ud.to_numpy()
                row = corr_block(np.where(msk, xu, np.nan), yu, ur, g)
                per_bar.append({'tf_min': tf, 'variant': var, 'subset': sub, 'scale': 'sigma_units_ud', **row})
            for pr in cvd_paths(b, VARIANTS[var][0], 'd_true', min_bars=max(5, 60 // tf)):
                paths.append({'tf_min': tf, 'variant': var, **pr})
        for var, o in outs.items():
            ind.append({'tf_min': tf, 'variant': var, 'tier_used': VARIANTS[var][1],
                        'pine_tier': 1 if (var == 'cr1m' and tf == 1) else VARIANTS[var][1], 'ke': ke,
                        **indicator_stats(o, rth)})
        for a, bb in PAIRS:
            agr.append({'tf_min': tf, 'pair': f'{a}_vs_{bb}', **agreement(outs[a], outs[bb])})
            ovl += overlaps(outs[a], outs[bb], ke, f'{a}_vs_{bb}', tf)
    return (pd.DataFrame(per_bar), pd.DataFrame(paths), pd.DataFrame(ind), pd.DataFrame(agr), pd.DataFrame(ovl), checks)


# ───────────────────────────── part B: TopstepX 2026 1S check ─────────────────────────────

def topstepx_1m(root: str) -> tuple[pd.DataFrame, dict]:
    """TopstepX 1-minute bars restricted to the 1-second span, with d_cr1s recomputed from the 1-second file and
    checked against the 1-minute file on complete minutes."""
    m = pd.read_parquet(studyenv.data_dir() / f'{root}_topstepx_2026_1m.parquet').sort_values('t_utc', kind='stable')
    s = pd.read_parquet(studyenv.data_dir() / f'{root}_topstepx_2026_1s.parquet', columns=['t_utc', 'o', 'c', 'v']).sort_values('t_utc', kind='stable')
    sd = B.candle_dir(s.o, s.c).astype(np.int64) * s.v.to_numpy()
    rec = pd.Series(sd, index=s.t_utc.dt.floor('1min').to_numpy()).groupby(level=0).sum()
    m = m[m.t_utc >= s.t_utc.min().floor('1min')].reset_index(drop=True)
    r = rec.reindex(m.t_utc.to_numpy()).to_numpy()
    comp = m.complete_1s.to_numpy()
    bad = int((r[comp] != m.d_cr1s.to_numpy()[comp]).sum())
    if bad:
        raise AssertionError(f'{root}: recomputed d_cr1s differs on {bad} complete minutes')
    m['d_cr1s0'] = np.where(comp, m.d_cr1s.fillna(0).to_numpy(), 0).astype(np.int64)
    m['complete_i'] = comp.astype(np.int64)
    info = {'minutes': int(len(m)), 'complete_minutes': int(comp.sum()), 'complete_rth_minutes': int((comp & m.rth.to_numpy()).sum()),
            'sessions': int(m.session_date.nunique()), 'first': str(m.t_utc.iloc[0]), 'last': str(m.t_utc.iloc[-1]),
            'd_cr1s_recomputed_equal_on_complete_minutes': True}
    # the CME settlement minute (14:59 CT) carries a large share of ES volume and dominates the raw Pearson correlation
    ct = m.t_utc.dt.tz_convert('America/Chicago')
    settle = ((ct.dt.hour * 60 + ct.dt.minute) == 14 * 60 + 59).to_numpy() & comp
    x, y = m.d_cr1m.to_numpy(float)[comp], m.d_cr1s.to_numpy(float)[comp]
    keep = ~settle[comp]
    info['settlement_minutes_1459CT'] = int(settle.sum())
    info['settlement_minute_volume_share'] = float(m.v.to_numpy()[settle].sum() / m.v.to_numpy()[comp].sum())
    info['1m_raw_corr_cr1m_cr1s_all'] = float(np.corrcoef(x, y)[0, 1])
    info['1m_raw_corr_cr1m_cr1s_excl_settlement_minute'] = float(np.corrcoef(x[keep], y[keep])[0, 1])
    return m, info


def part_b():
    per_bar, paths, ind, agr, ovl, info = [], [], [], [], [], {}
    for root in ('es', 'mes'):
        m1, inf = topstepx_1m(root)
        info[root] = inf
        for tf in TFS:
            b = B.chart_bars(m1, tf, delta_cols=('d_cr1m', 'd_cr1s0', 'complete_i'))
            comp = (b.complete_i.to_numpy() == b.n_1m.to_numpy())
            b['d_cr1s'] = np.where(comp, b.d_cr1s0.to_numpy(), np.nan)
            rth = b.rth.to_numpy()
            g = b.session_date.to_numpy()
            # price increment within the session (gap rule as the indicator) for the partial correlations
            outs = {'cr1m': run_variant(b, 'd_cr1m', 2, tf, vol_mask=comp), 'cr1s': run_variant(b, 'd_cr1s', 3, tf, vol_mask=comp)}
            r = outs['cr1s'].r_bar.to_numpy()
            ur = outs['cr1s'].ur.to_numpy()
            info[root][f'{tf}m_complete_bars'] = int(comp.sum())
            info[root][f'{tf}m_complete_rth_bars'] = int((comp & rth).sum())
            for sub, msk in (('all', comp), ('rth', comp & rth), ('eth', comp & ~rth)):
                x = np.where(msk, b.d_cr1m.to_numpy(float), np.nan)
                row = corr_block(x, b.d_cr1s.to_numpy(float), r, g)
                per_bar.append({'source': f'topstepx_{root}_2026', 'tf_min': tf, 'variant': 'cr1m', 'reference': 'cr1s',
                                'subset': sub, 'scale': 'raw_delta', **row})
                xu = np.where(msk, outs['cr1m'].ud.to_numpy(), np.nan)
                row = corr_block(xu, outs['cr1s'].ud.to_numpy(), ur, g)
                per_bar.append({'source': f'topstepx_{root}_2026', 'tf_min': tf, 'variant': 'cr1m', 'reference': 'cr1s',
                                'subset': sub, 'scale': 'sigma_units_ud', **row})
            for pr in cvd_paths(b, 'd_cr1m', 'd_cr1s', mask=comp, min_bars=max(5, 60 // tf)):
                paths.append({'source': f'topstepx_{root}_2026', 'tf_min': tf, 'variant': 'cr1m', 'reference': 'cr1s', **pr})
            if tf == 1:
                continue                # 1-minute chart: Auto is tier 1 on TradingView; per-bar numbers only
            ke = outs['cr1s'].attrs['ke']
            for var, o in outs.items():
                ind.append({'source': f'topstepx_{root}_2026', 'tf_min': tf, 'variant': var, 'ke': ke, **indicator_stats(o, rth)})
            agr.append({'source': f'topstepx_{root}_2026', 'tf_min': tf, 'pair': 'cr1m_vs_cr1s', **agreement(outs['cr1m'], outs['cr1s'])})
            ovl += overlaps(outs['cr1m'], outs['cr1s'], ke, 'cr1m_vs_cr1s', tf, extra={'source': f'topstepx_{root}_2026'})
    return (pd.DataFrame(per_bar), pd.DataFrame(paths), pd.DataFrame(ind), pd.DataFrame(agr), pd.DataFrame(ovl), info)


# ───────────────────────────── main ─────────────────────────────

def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 5)
    if isinstance(o, np.integer):
        return int(o)
    return o


def summarise(a, b):
    per_bar, paths, ind, agr, ovl, checks = a
    pb_b, paths_b, ind_b, agr_b, ovl_b, info_b = b
    s = {'feature_file_checks_max_abs_dZ': checks}
    pick = lambda df, **kw: df.loc[np.logical_and.reduce([df[k] == v for k, v in kw.items()])]
    s['per_bar_raw_delta_vs_true_all_hours'] = {
        f'{tf}m': {v: {k: pick(per_bar, tf_min=tf, variant=v, subset='all', scale='raw_delta')[k].iloc[0]
                       for k in ('corr', 'corr_ci', 'spearman', 'pcorr_given_r', 'pcorr_ci', 'sign_agree', 'corr_est_r', 'corr_true_r')}
                   for v in ('cr1m', 'cr1s', 'tick')} for tf in TFS}
    s['per_bar_sigma_units_vs_true_all_hours'] = {
        f'{tf}m': {v: {k: pick(per_bar, tf_min=tf, variant=v, subset='all', scale='sigma_units_ud')[k].iloc[0]
                       for k in ('corr', 'pcorr_given_r', 'sign_agree')} for v in ('cr1m', 'cr1s', 'tick')} for tf in TFS}
    s['per_bar_raw_delta_vs_true_rth'] = {
        f'{tf}m': {v: {k: pick(per_bar, tf_min=tf, variant=v, subset='rth', scale='raw_delta')[k].iloc[0]
                       for k in ('corr', 'pcorr_given_r', 'sign_agree')} for v in ('cr1m', 'cr1s', 'tick')} for tf in TFS}
    pm = paths.groupby(['tf_min', 'variant', 'anchor']).agg(path_corr_median=('path_corr', 'median'), path_corr_min=('path_corr', 'min'),
                                                            price_path_corr_median=('price_path_corr', 'median'), sessions=('path_corr', 'size'))
    s['cvd_path_corr_with_true'] = {f'{tf}m_{v}_{an}': r.to_dict() for (tf, v, an), r in pm.iterrows()}
    s['indicator_per_variant'] = {f'{r.tf_min}m_{r.variant}': {k: r[k] for k in ('gate_open_pct_of_hq', 'rho_median', 'P_absZ_ge2_pct',
                                                                               'P_absZ_ge3_pct', 'P_abs_zF_ge2_pct', 'n_new_abs', 'n_new_pin',
                                                                               'n_new_pwf', 'n_al_z_up', 'n_al_z_dn', 'z_bars_calok')}
                                  for _, r in ind.iterrows()}
    s['indicator_agreement'] = {f'{r.tf_min}m_{r.pair}': {k: r[k] for k in ('Z_corr', 'Z_sign_agree', 'state_recall', 'state_precision',
                                                                            'state_opposite_sign_bars', 'zF_corr', 'zF_sign_agree_when_ref_abs_ge2',
                                                                            'zF_abs_ge2_recall', 'gate_agree')}
                                for _, r in agr.iterrows()}
    ev = ovl[(ovl.level == 'event') & ovl['class'].isin(['all_events', 'flow_events'])]
    s['event_overlap_pooled'] = {f'{r.tf_min}m_{r.pair}_{r["class"]}_{r.tolerance}': {k: r[k] for k in ('n_est', 'n_ref', 'matched', 'precision', 'recall', 'jaccard')}
                                 for _, r in ev.iterrows()}
    bl = ovl[(ovl.level == 'bar') & ovl['class'].isin(['z_ge_thr', 'z_le_-thr', 'absorbed_buy', 'absorbed_sell', 'pwf_up', 'pwf_down'])]
    s['bar_flag_jaccard'] = {f'{r.tf_min}m_{r.pair}_{r["class"]}': {k: r[k] for k in ('n_est', 'n_ref', 'jaccard')} for _, r in bl.iterrows()}
    # TopstepX (cr1m vs cr1s; the per-bar side-by-side with 2013 is added in main)
    s['topstepx_info'] = info_b
    s['topstepx_indicator_agreement'] = {f'{r.source}_{r.tf_min}m': {k: r[k] for k in ('z_bars_both', 'Z_corr', 'Z_sign_agree', 'state_recall',
                                                                                         'state_precision', 'zF_corr', 'gate_agree')}
                                         for _, r in agr_b.iterrows()}
    s['topstepx_indicator_per_variant'] = {f'{r.source}_{r.tf_min}m_{r.variant}': {k: r[k] for k in ('z_bars_calok', 'gate_open_pct_of_hq', 'rho_median',
                                                                                                      'P_absZ_ge2_pct', 'P_absZ_ge3_pct', 'n_new_abs', 'n_new_pwf')}
                                           for _, r in ind_b.iterrows()}
    evb = ovl_b[(ovl_b.level == 'event') & ovl_b['class'].isin(['all_events', 'flow_events'])]
    s['topstepx_event_overlap_pooled'] = {f'{r.source}_{r.tf_min}m_{r["class"]}_{r.tolerance}': {k: r[k] for k in ('n_est', 'n_ref', 'matched', 'precision', 'recall', 'jaccard')}
                                          for _, r in evb.iterrows()}
    pmb = paths_b.groupby(['source', 'tf_min', 'anchor']).agg(path_corr_median=('path_corr', 'median'), sessions=('path_corr', 'size'))
    s['topstepx_cvd_path_corr_cr1m_vs_cr1s'] = {f'{src}_{tf}m_{an}': r.to_dict() for (src, tf, an), r in pmb.iterrows()}
    return s


def tick2013_cr1m_vs_cr1s():
    """2013 per-bar cr1m vs cr1s (the same comparison as TopstepX, for the side-by-side table)."""
    rows = []
    for tf in TFS:
        b = tick_sample_bars(tf)
        o = run_variant(b, 'd_cr1s', 3, tf)
        oc = run_variant(b, 'd_cr1m', 2, tf)
        r = o.r_bar.to_numpy()
        g = b.session_date.to_numpy()
        rth = b.rth.to_numpy()
        for sub, msk in (('all', np.ones(len(b), bool)), ('rth', rth), ('eth', ~rth)):
            row = corr_block(np.where(msk, b.d_cr1m.to_numpy(float), np.nan), b.d_cr1s.to_numpy(float), r, g)
            rows.append({'source': 'tick_sample_es_2013', 'tf_min': tf, 'variant': 'cr1m', 'reference': 'cr1s', 'subset': sub,
                         'scale': 'raw_delta', **row})
            row = corr_block(np.where(msk, oc.ud.to_numpy(), np.nan), o.ud.to_numpy(), o.ur.to_numpy(), g)
            rows.append({'source': 'tick_sample_es_2013', 'tf_min': tf, 'variant': 'cr1m', 'reference': 'cr1s', 'subset': sub,
                         'scale': 'sigma_units_ud', **row})
    return pd.DataFrame(rows)


def main():
    t0 = time.time()
    RES = studyenv.results_dir('fidelity')
    RES.mkdir(parents=True, exist_ok=True)
    a = part_a()
    b = part_b()
    c13 = tick2013_cr1m_vs_cr1s()
    names = ('per_bar_delta', 'cvd_paths', 'indicator_per_variant', 'indicator_agreement', 'event_overlap')
    for nm, df in zip(names, a[:5]):
        df.to_csv(RES / f'tick2013_{nm}.csv', index=False)
    for nm, df in zip(names, b[:5]):
        df.to_csv(RES / f'topstepx2026_{nm}.csv', index=False)
    side = pd.concat([c13, b[0]], ignore_index=True)
    side.to_csv(RES / 'cr1m_vs_cr1s_2013_vs_2026_per_bar.csv', index=False)
    s = summarise(a, b)
    s['cr1m_vs_cr1s_per_bar_2013_vs_2026_raw_all'] = {
        f'{r.source}_{r.tf_min}m': {k: r[k] for k in ('n', 'corr', 'spearman', 'pcorr_given_r', 'sign_agree')}
        for _, r in side[(side.subset == 'all') & (side.scale == 'raw_delta')].iterrows()}
    s['cr1m_vs_cr1s_per_bar_2013_vs_2026_sigma_units_all'] = {
        f'{r.source}_{r.tf_min}m': {k: r[k] for k in ('n', 'corr', 'spearman', 'pcorr_given_r', 'sign_agree')}
        for _, r in side[(side.subset == 'all') & (side.scale == 'sigma_units_ud')].iterrows()}
    s['cr1m_vs_cr1s_per_bar_2013_vs_2026_raw_rth'] = {
        f'{r.source}_{r.tf_min}m': {k: r[k] for k in ('n', 'corr', 'pcorr_given_r', 'sign_agree')}
        for _, r in side[(side.subset == 'rth') & (side.scale == 'raw_delta')].iterrows()}
    s['runtime_s'] = round(time.time() - t0, 1)
    s['notes'] = [
        'tick sample: 15 CME sessions 2013-09-02..20 (2013-09-13 = roll session, 2013-09-02 Labor Day short session), all kept; '
        'bootstrap = session blocks (15).',
        '1-minute chart with cr1m: TradingView gives tier 1 (Auto intrabars = chart bars, no Z or events); computed as if tier 2.',
        'events = labels as drawn (new clusters incl. hollow/provisional ones), Z alerts (al_z_*), pivot divergences; matching '
        'one-to-one, same class and side; pm_ke = within ±ke bars (±15 min on 1m/5m, ±1 bar on 15m).',
        'P(|Z|≥k) on bars with Z and zCalOk (as the Z tooltip); gate-open % of hqOk bars.',
        'TopstepX: no true delta; cr1s is the reference (1S proxy). Both runs use the same observation mask (incomplete bars '
        '= no-observation). Few bars: 15m numbers are indicative only.',
    ]
    json.dump(_clean(s), open(RES / 'fidelity_summary.json', 'w'), indent=1, default=str)
    print(json.dumps(_clean(s), indent=1, default=str)[:20000])


if __name__ == '__main__':
    main()
