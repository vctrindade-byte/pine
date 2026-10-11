#!/usr/bin/env python3
"""Robustness of the pre-registered PRIMARY endpoint on other S&P 500 instruments: MES 2021–2026 and SPY 2000–2026
(regular hours only, and regular + extended hours), with ES as the reference run of the same code.

The event-study machinery is defined here once (signals, outcomes, inference, controls) and applied to the per-bar
feature files written by features.py (engine.py port of the indicator, defaults, "TradingView Auto" delta = candle rule
on 1-minute intrabars, tier 2).

Pre-registered definitions (indicator DEFAULTS only; nothing is tuned to outcomes)
  Signal bar t = the CONFIRMATION bar (its close); entry at the open of bar t+1; exit at the close of the last bar that
  starts before entry + H (clock horizon H = 5, 15, 30, 60 min; on a 5m chart 1, 3, 6, 12 bars). A slot without trades
  (missing bar) keeps the last price; a window that would cross a session break (end of the CME Globex session /
  the ET day for SPY) or a contract change is excluded.
  Signal classes and direction s (positive signed return = continuation of s):
    z_pos_flowled / z_pos_priceled / z_neg_flowled / z_neg_priceled
                   Z alerts (first cross of ±thr with gate, hysteresis, zCalOk ≥ 2N) split by the four neutral states:
                   flow-led (|F_K| > |P_K|) → s = sign(F_K); price-led → s = sign(P_K)
    abs_buy / abs_sell        new absorbed cluster (not ev_weak, i.e. the alertcondition), s = flow side
    pin_buy / pin_sell        new pinned cluster (not ev_weak), s = flow side
    pwf_up / pwf_down         new price-without-flow cluster (not ev_weak), s = price side
    res_cont_up / res_cont_dn / res_held_up / res_held_dn
                              resolution of an absorption on the resolution bar (not weak), s = direction of the
                              resolving close (continuation: event side; held: opposite side)
    piv_top (s = −1) / piv_bot (s = +1)   classical pivot divergence, on the confirmation bar (R bars after the pivot)
  Outcomes: signed log return from entry in σ-units = s·10⁴·ln(C_exit/O_entry) / (σr·√(H/tf)), σr = the indicator's
  lagged one-bar σ of r (bps) on the signal bar — PRIMARY; also bps, instrument points, hit rate, median, MFE and MAE
  (σ-units and points) over the horizon, unsigned |return| (volatility effect).
  PRIMARY ENDPOINT: signed σ-unit return at 30 min per class on the 5m chart; Benjamini–Hochberg FDR 5% over the 16
  classes (applied here within each replication dataset).
  Inference: day-clustered (session) standard errors (CR1, t with G−1 df) and day-block bootstrap 95% CIs; n events,
  n days.
  Controls / incremental value of CVD:
   (1) conditional twins — absorbed vs CONFIRMED flow shocks (|zF| ≥ 2 and s·zP ≥ |ρ|·|zF|, s = sign zF);
       price-without-flow vs price shocks WITH flow (|zP| ≥ 2 and sign(zP)·zF > 0, s = sign zP); twins are built
       exactly like the indicator's events (gate, per-side clusters with a refractory period of ke observations, tier
       rule, not ev_weak); difference of signed σ-returns with a day-clustered SE (influence-function form) and a
       day-block bootstrap CI;
   (2) matched controls — for every event, the mean outcome of all other bars of the same cell (the events of the
       same class removed; cell = session type RTH/ETH, 30-minute time-of-day bucket in exchange time, year, σr
       tercile within the year, sign of pE and tercile of |pE|), signed with the event's s: this is the expectation
       of a random matched control; difference event − control with day-clustered SE and (30 min) bootstrap CI;
   (3) unconditional baseline — mean outcome of all bars with the same filters (per class: mean(s)·baseline).
  Costs (secondary): naive "trade s for H" and the opposite rule, gross and net of a round trip:
  ES 0.325 pt (1 tick + ~$4), MES 0.45 pt (1 tick + ~$1), SPY $0.015/share (1 cent + fees) — the MES/SPY costs are
  approximate and not part of the pre-registration (which fixes the ES cost only).

Datasets (DATASETS below): es_5m (reference), es_5m_mes_period (ES on the MES sessions), mes_5m, spy_5m_rth (the
TradingView default SPY chart: regular hours only; intrabars and candle side are RTH-only), spy_5m_ext (regular +
extended hours in one stream). Plus the cross-instrument agreement (ES vs MES on common bars; ES vs SPY on common RTH
bars).

Usage:  python3 -I study_robust.py [dataset ...] [--boot 2000]      (env, required: OUT_DIR = study folder with features/)
Outputs: OUT_DIR/results/robust/: <dataset>_classes.csv, <dataset>_twins.csv, <dataset>_stability.csv,
         robust_primary_30m.csv, robust_twins_30m.csv, robust_cross_instrument.json, robust_summary.json.
Only statistics are written (no price rows).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import studyenv  # noqa: E402
SEED = 20261011
HORIZONS = (5, 15, 30, 60)
PRIMARY_H = 30

CME = dict(tz='America/Chicago', rth=(8 * 60 + 30, 15 * 60 + 15))
SPY = dict(tz='America/New_York', rth=(9 * 60 + 30, 16 * 60))
DATASETS = {
    'es_5m': dict(file='es_5m_cr1m', cost=0.325, unit='pt', **CME,
                  label='ES front month 5m, clean sessions 2008-01..2026-09 (reference run of this code)'),
    'es_5m_mes_period': dict(file='es_5m_cr1m', cost=0.325, unit='pt', period_of='mes_5m_cr1m', **CME,
                             label='ES 5m restricted to the MES sessions (2021-05..2026-09); indicator state from the full ES stream'),
    'mes_5m': dict(file='mes_5m_cr1m', cost=0.45, unit='pt', **CME, label='MES front month 5m, clean sessions 2021-05..2026-09'),
    'spy_5m_rth': dict(file='spy_5m_cr1m_rthonly', cost=0.015, unit='usd', **SPY,
                       label='SPY 5m, regular hours only (TradingView default chart), 2000..2026-04, Aug 2016 dropped'),
    'spy_5m_ext': dict(file='spy_5m_cr1m', cost=0.015, unit='usd', **SPY,
                       label='SPY 5m, regular + extended hours in one stream, 2000..2026-04, Aug 2016 dropped'),
}

CLASSES = ['z_pos_flowled', 'z_pos_priceled', 'z_neg_flowled', 'z_neg_priceled', 'abs_buy', 'abs_sell', 'pin_buy',
           'pin_sell', 'pwf_up', 'pwf_down', 'res_cont_up', 'res_cont_dn', 'res_held_up', 'res_held_dn', 'piv_top',
           'piv_bot']
FAMILY = {c: c.split('_')[0] if not c.startswith('z_') else 'z' for c in CLASSES}

COLS = ['t', 'session_date', 'o', 'h', 'l', 'c', 'sr_p', 'rho_p', 'Z', 'z_cal_ok', 'gate', 'hq_ok', 'tier', 'd',
        'p_leg', 'f_leg', 'zF', 'zP', 'pE', 'ev_weak', 'al_z_up', 'al_z_dn', 'new_abs', 'ev_side', 'new_pin', 'pin_side',
        'new_pwf', 'pwf_side', 'res_cont', 'res_held', 'res_side', 'res_weak', 'piv_top', 'piv_bot', 'absorbed', 'pinned']


# ───────────────────────────── inference ─────────────────────────────

def clustered_mean(y, g):
    """Mean with a cluster-robust (CR1) SE; t-test with G−1 df. y finite, g cluster codes."""
    n = len(y)
    if n == 0:
        return dict(n=0, days=0, mean=np.nan, se=np.nan, t=np.nan, p=np.nan)
    mu = float(y.mean())
    u, inv = np.unique(g, return_inverse=True)
    G = len(u)
    if G < 2:
        return dict(n=n, days=G, mean=mu, se=np.nan, t=np.nan, p=np.nan)
    e = np.bincount(inv, y - mu, G)
    se = math.sqrt(G / (G - 1) * float((e ** 2).sum())) / n
    t = mu / se if se > 0 else np.nan
    p = float(2 * stats.t.sf(abs(t), G - 1)) if np.isfinite(t) else np.nan
    return dict(n=n, days=G, mean=mu, se=se, t=t, p=p)


def clustered_diff(y1, g1, y0, g0):
    """Difference of means m1 − m0 with a day-clustered SE (sum of the per-day influence of both groups)."""
    n1, n0 = len(y1), len(y0)
    if n1 < 2 or n0 < 2:
        return dict(diff=np.nan, se=np.nan, t=np.nan, p=np.nan, days=0)
    m1, m0 = float(y1.mean()), float(y0.mean())
    inf = np.r_[(y1 - m1) / n1, -(y0 - m0) / n0]
    g = np.r_[g1, g0]
    u, inv = np.unique(g, return_inverse=True)
    G = len(u)
    e = np.bincount(inv, inf, G)
    se = math.sqrt(G / (G - 1) * float((e ** 2).sum()))
    d = m1 - m0
    t = d / se if se > 0 else np.nan
    return dict(diff=d, se=se, t=t, p=float(2 * stats.t.sf(abs(t), G - 1)) if np.isfinite(t) else np.nan, days=G)


def boot_mean_ci(y, g, B, rng):
    """Day-block bootstrap 95% CI of the mean (days resampled with replacement)."""
    if len(y) < 2 or B <= 0:
        return [np.nan, np.nan]
    u, inv = np.unique(g, return_inverse=True)
    G = len(u)
    S = np.bincount(inv, y, G)
    N = np.bincount(inv, minlength=G).astype(float)
    m = np.empty(B)
    for a in range(0, B, 250):
        b = min(B, a + 250)
        idx = rng.integers(0, G, size=(b - a, G))
        m[a:b] = S[idx].sum(1) / N[idx].sum(1)
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def boot_diff_ci(y1, g1, y0, g0, B, rng):
    if len(y1) < 2 or len(y0) < 2 or B <= 0:
        return [np.nan, np.nan]
    u, inv = np.unique(np.r_[g1, g0], return_inverse=True)
    G = len(u)
    i1, i0 = inv[:len(y1)], inv[len(y1):]
    S1, N1 = np.bincount(i1, y1, G), np.bincount(i1, minlength=G).astype(float)
    S0, N0 = np.bincount(i0, y0, G), np.bincount(i0, minlength=G).astype(float)
    d = np.empty(B)
    for a in range(0, B, 250):
        b = min(B, a + 250)
        idx = rng.integers(0, G, size=(b - a, G))
        with np.errstate(invalid='ignore', divide='ignore'):
            d[a:b] = S1[idx].sum(1) / N1[idx].sum(1) - S0[idx].sum(1) / N0[idx].sum(1)
    return [float(np.nanpercentile(d, 2.5)), float(np.nanpercentile(d, 97.5))]


def bh_qvalues(p):
    """Benjamini–Hochberg adjusted p-values (NaN kept)."""
    p = np.asarray(p, float)
    q = np.full(len(p), np.nan)
    ok = np.isfinite(p)
    m = ok.sum()
    if m == 0:
        return q
    pv = p[ok]
    o = np.argsort(pv)
    r = pv[o] * m / np.arange(1, m + 1)
    r = np.minimum.accumulate(r[::-1])[::-1]
    out = np.empty(m)
    out[o] = np.minimum(r, 1.0)
    q[ok] = out
    return q


# ───────────────────────────── data, outcomes, signals ─────────────────────────────

def load(ds: str) -> tuple[pd.DataFrame, dict]:
    cfg = DATASETS[ds]
    meta = json.load(open(studyenv.feat_dir() / f"{cfg['file']}.json"))
    cols = [c for c in COLS + ['contract'] if c in meta['columns']]
    df = pd.read_parquet(studyenv.feat_dir() / f"{cfg['file']}.parquet", columns=cols)
    if not df.t.is_monotonic_increasing:
        raise AssertionError(f'{ds}: bars are not in time order')
    if 'period_of' in cfg:
        pm = json.load(open(studyenv.feat_dir() / f"{cfg['period_of']}.json"))
        other = pd.read_parquet(studyenv.feat_dir() / f"{cfg['period_of']}.parquet", columns=['session_date']).session_date
        meta = dict(meta, restricted_to_sessions=[str(other.min().date()), str(other.max().date())], restricted_from=pm['file'])
        df.attrs['keep'] = (df.session_date >= other.min()) & (df.session_date <= other.max())
    return df, meta


def forward_outcomes(df: pd.DataFrame, tf_min: int, horizons=HORIZONS) -> dict:
    """Per bar i (as a signal bar), for each clock horizon H: valid flag, log return (bps) and point change from the
    open of bar i+1 to the close of the last bar starting before entry + H, and the max up / down excursions."""
    t = df.t.dt.as_unit('ns').array.asi8
    sess = pd.factorize(df.session_date)[0]
    ctr = pd.factorize(df['contract'])[0] if 'contract' in df.columns else np.zeros(len(df), np.int64)
    o, h, l, c = (df[k].to_numpy(float) for k in ('o', 'h', 'l', 'c'))
    n = len(df)
    tf = tf_min * 60 * 10 ** 9
    i = np.arange(n)
    e = np.minimum(i + 1, n - 1)
    has_e = (i + 1 < n) & (sess[e] == sess) & (ctr[e] == ctr)
    out = {}
    for H in horizons:
        if H < tf_min:
            continue
        nb = H // tf_min
        target = t[e] + H * 60 * 10 ** 9
        j = np.searchsorted(t, target, side='left') - 1
        j = np.clip(j, 0, n - 1)
        jn = np.minimum(j + 1, n - 1)
        complete = (t[j] + tf == target) | ((j + 1 < n) & (sess[jn] == sess))
        valid = has_e & (j >= e) & (sess[j] == sess) & (ctr[j] == ctr) & complete
        hmax = h[e].copy()
        lmin = l[e].copy()
        for k in range(1, nb):
            idx = np.minimum(e + k, n - 1)
            use = (e + k) <= j
            hmax = np.where(use, np.maximum(hmax, h[idx]), hmax)
            lmin = np.where(use, np.minimum(lmin, l[idx]), lmin)
        with np.errstate(divide='ignore', invalid='ignore'):
            out[H] = dict(valid=valid, nb=nb,
                          ret=np.where(valid, 1e4 * np.log(c[j] / o[e]), np.nan),
                          pts=np.where(valid, c[j] - o[e], np.nan),
                          up=np.where(valid, 1e4 * np.log(hmax / o[e]), np.nan),
                          dn=np.where(valid, 1e4 * np.log(o[e] / lmin), np.nan),
                          up_pts=np.where(valid, hmax - o[e], np.nan),
                          dn_pts=np.where(valid, o[e] - lmin, np.nan),
                          entry=np.where(valid, o[e], np.nan))
    return out


def cluster_starts(flag, side, obs_idx, ke):
    """First bar of each cluster (same side, refractory ke observations), as clusters() in engine.py."""
    new = np.zeros(len(flag), dtype=bool)
    last_obs, last_side = None, 0
    for t in np.flatnonzero(flag):
        s = int(side[t])
        oi = int(obs_idx[t])
        if not (last_side == s and last_obs is not None and oi - last_obs <= ke):
            new[t] = True
        last_obs, last_side = oi, s
    return new


def signals(df: pd.DataFrame, ke: int) -> pd.DataFrame:
    """All pre-registered signal classes (bar index i, class, direction s) plus the twin families."""
    g = lambda k: df[k].to_numpy()
    rows = []

    def add(mask, cls, s):
        idx = np.flatnonzero(mask)
        s = np.nan_to_num(np.broadcast_to(np.asarray(s, float), (len(df),))[idx]) if np.ndim(s) else np.full(len(idx), s)
        rows.append(pd.DataFrame({'i': idx, 'cls': cls, 's': np.asarray(s, np.int8)}))

    F, P = g('f_leg'), g('p_leg')
    flow_led = np.abs(F) > np.abs(P)
    up, dn = g('al_z_up') == 1, g('al_z_dn') == 1
    add(up & flow_led, 'z_pos_flowled', np.sign(F))
    add(up & ~flow_led, 'z_pos_priceled', np.sign(P))
    add(dn & flow_led, 'z_neg_flowled', np.sign(F))
    add(dn & ~flow_led, 'z_neg_priceled', np.sign(P))
    weak = g('ev_weak') == 1
    for col, side, name in (('new_abs', 'ev_side', 'abs'), ('new_pin', 'pin_side', 'pin')):
        m = (g(col) == 1) & ~weak
        add(m & (g(side) == 1), f'{name}_buy', 1)
        add(m & (g(side) == -1), f'{name}_sell', -1)
    m = (g('new_pwf') == 1) & ~weak
    add(m & (g('pwf_side') == 1), 'pwf_up', 1)
    add(m & (g('pwf_side') == -1), 'pwf_down', -1)
    rw = g('res_weak') == 1
    rs = g('res_side')
    add((g('res_cont') == 1) & ~rw & (rs == 1), 'res_cont_up', 1)
    add((g('res_cont') == 1) & ~rw & (rs == -1), 'res_cont_dn', -1)
    add((g('res_held') == 1) & ~rw & (rs == -1), 'res_held_up', 1)
    add((g('res_held') == 1) & ~rw & (rs == 1), 'res_held_dn', -1)
    add(g('piv_top') == 1, 'piv_top', -1)
    add(g('piv_bot') == 1, 'piv_bot', 1)

    # twins: built like the indicator's events (gate, clusters per side, refractory ke observations, not ev_weak)
    zf, zp, rho = g('zF'), g('zP'), g('rho_p')
    gate = g('gate') == 1
    z_ok = np.isfinite(zf) & np.isfinite(zp)
    rho_z = np.where(np.isfinite(rho), rho, 0.0)
    sf = np.sign(np.where(np.isfinite(zf), zf, 0.0))
    sp = np.sign(np.where(np.isfinite(zp), zp, 0.0))
    obs_idx = np.cumsum(np.isfinite(g('d')))
    tier = g('tier')
    tier_ok = tier >= 2               # tier 3, or tier 2 with "show medium-quality events" on (default)
    with np.errstate(invalid='ignore'):
        conf = gate & z_ok & (np.abs(zf) >= 2) & (sf * zp >= np.abs(rho_z) * np.abs(zf))
        pshock = gate & z_ok & (np.abs(zp) >= 2) & (sp * zf > 0)
    for flag, side, name in ((conf, sf, 'conf_flow'), (pshock, sp, 'pshock_flow')):
        new = cluster_starts(flag, np.where(flag, side, 0), obs_idx, ke) & tier_ok & ~weak
        add(new & (side > 0), f'{name}_up', 1)
        add(new & (side < 0), f'{name}_dn', -1)
    ev = pd.concat(rows, ignore_index=True)
    ev = ev[ev.s != 0].reset_index(drop=True)
    return ev


# ───────────────────────────── per-dataset analysis ─────────────────────────────

def cell_keys(df: pd.DataFrame, cfg: dict, pool: np.ndarray):
    """Matching cell of every bar: session type, 30-min ToD bucket (exchange time), year, σr tercile within the year,
    sign of pE and tercile of |pE| (terciles over the pool bars)."""
    lt = df.t.dt.tz_convert(cfg['tz'])
    mins = (lt.dt.hour * 60 + lt.dt.minute).to_numpy()
    rth = (mins >= cfg['rth'][0]) & (mins < cfg['rth'][1])
    tod = mins // 30
    year = pd.DatetimeIndex(df.session_date).year.to_numpy()
    sr = df.sr_p.to_numpy()
    pe = df.pE.to_numpy()
    sr_t = np.full(len(df), -1)
    for y in np.unique(year):
        m = pool & (year == y)
        if m.sum() < 3:
            continue
        q = np.nanpercentile(sr[m], [100 / 3, 200 / 3])
        yy = year == y
        sr_t[yy] = np.digitize(sr[yy], q)
    qa = np.nanpercentile(np.abs(pe[pool]), [100 / 3, 200 / 3])
    pe_t = np.digitize(np.abs(pe), qa)
    pe_s = (pe > 0).astype(int)
    key = ((((rth.astype(np.int64) * 64 + tod) * 3000 + year) * 4 + sr_t + 1) * 2 + pe_s) * 3 + pe_t
    key = np.where(np.isfinite(pe) & np.isfinite(sr), key, -1)
    return key, rth


def analyse(ds: str, B: int, rng) -> dict:
    t0 = time.time()
    cfg = DATASETS[ds]
    df, meta = load(ds)
    tf = int(meta['tf_min'])
    ke = int(meta['ke'])
    fo = forward_outcomes(df, tf)
    keep = df.attrs.get('keep', pd.Series(True, index=df.index)).to_numpy()
    ev = signals(df, ke)
    ev = ev[keep[ev.i.to_numpy()]].reset_index(drop=True)
    day = pd.factorize(df.session_date)[0]
    sr = df.sr_p.to_numpy()
    sr_ok = np.isfinite(sr) & (sr > 0)
    pool = keep & (df.hq_ok.to_numpy() == 1) & sr_ok
    key, rth = cell_keys(df, cfg, pool)
    year = pd.DatetimeIndex(df.session_date).year.to_numpy()
    q_sr = np.nanpercentile(sr[pool], [100 / 3, 200 / 3])
    srt = np.where(np.isfinite(sr), np.digitize(sr, q_sr), -1)       # global σr tercile (stability split)
    rows, twin_rows, stab_rows = [], [], []
    base = {}
    ev_i = ev.i.to_numpy()
    ev_s = ev.s.to_numpy().astype(float)
    for H, f in fo.items():
        nb = f['nb']
        with np.errstate(divide='ignore', invalid='ignore'):
            x_all = np.where(sr_ok, f['ret'] / (sr * math.sqrt(nb)), np.nan)
        ax_all = np.abs(x_all)
        okb = pool & f['valid'] & np.isfinite(x_all)
        base[H] = dict(mean_sigma=float(np.nanmean(x_all[okb])), mean_abs_sigma=float(np.nanmean(ax_all[okb])),
                       mean_bps=float(np.nanmean(f['ret'][okb])), n_bars=int(okb.sum()))
        # cell sums for matched controls (pool bars only)
        kk = np.where(okb, key, -1)
        valid_k = kk >= 0
        uk, kinv = np.unique(kk[valid_k], return_inverse=True)
        c_sum = np.bincount(kinv, x_all[valid_k], len(uk))
        c_abs = np.bincount(kinv, ax_all[valid_k], len(uk))
        c_n = np.bincount(kinv, minlength=len(uk)).astype(float)
        xe = ev_s * x_all[ev_i]
        ok_e = f['valid'][ev_i] & np.isfinite(xe) & pool[ev_i]
        for cls in sorted(ev.cls.unique()):
            m = (ev.cls.to_numpy() == cls) & ok_e
            ii, ss = ev_i[m], ev_s[m]
            y = xe[m]
            gd = day[ii]
            r = dict(dataset=ds, cls=cls, family=FAMILY.get(cls, 'twin'), H=H, bars=nb)
            cm = clustered_mean(y, gd)
            r.update({f'sig_{k}': v for k, v in cm.items() if k not in ('n', 'days')})
            r['n'], r['days'] = cm['n'], cm['days']
            r['sig_ci_lo'], r['sig_ci_hi'] = boot_mean_ci(y, gd, B, rng)
            # sensitivity (NOT pre-registered): outcome winsorised at ±5σ, to see whether a mean is carried by a few
            # extreme bars (σ-unit returns are heavy-tailed: kurtosis ≈ 30–300 over all bars)
            cw = clustered_mean(np.clip(y, -5, 5), gd)
            r['sig_mean_w5'], r['sig_p_w5'] = cw['mean'], cw['p']
            if len(y):
                r['sig_median'] = float(np.median(y))
                r['hit'] = float((y > 0).mean())
                r['loss'] = float((y < 0).mean())
                r['share_s_pos'] = float((ss > 0).mean())
                bps = ss * f['ret'][ii]
                pts = ss * f['pts'][ii]
                r['bps_mean'] = float(bps.mean())
                r['pts_mean'] = float(pts.mean())
                r['pts_se'] = clustered_mean(pts, gd)['se']
                mfe = np.where(ss > 0, f['up'][ii], f['dn'][ii])
                mae = np.where(ss > 0, f['dn'][ii], f['up'][ii])
                r['mfe_sig'] = float(np.mean(mfe / (sr[ii] * math.sqrt(nb))))
                r['mae_sig'] = float(np.mean(mae / (sr[ii] * math.sqrt(nb))))
                r['mfe_pts'] = float(np.mean(np.where(ss > 0, f['up_pts'][ii], f['dn_pts'][ii])))
                r['mae_pts'] = float(np.mean(np.where(ss > 0, f['dn_pts'][ii], f['up_pts'][ii])))
                r['abs_sig_mean'] = float(np.mean(np.abs(y)))
                r['cost'] = cfg['cost']
                r['net_pts_follow'] = r['pts_mean'] - cfg['cost']
                r['net_pts_opposite'] = -r['pts_mean'] - cfg['cost']
                r['cost_bps_mean'] = float(np.mean(1e4 * cfg['cost'] / f['entry'][ii]))
                r['net_bps_follow'] = r['bps_mean'] - r['cost_bps_mean']
                r['net_bps_opposite'] = -r['bps_mean'] - r['cost_bps_mean']
                # baseline
                r['baseline_sig'] = float(np.mean(ss) * base[H]['mean_sigma'])
                # matched controls: cell mean of the other pool bars, signed with s
                ek = key[ii]
                pos = np.searchsorted(uk, ek)
                pos = np.clip(pos, 0, max(len(uk) - 1, 0))
                found = (len(uk) > 0) & (uk[pos] == ek) & (ek >= 0)
                # remove this class's own events from their cells
                own = pd.DataFrame({'p': pos[found], 'x': x_all[ii][found], 'a': np.abs(x_all[ii][found])}).groupby('p').agg(
                    n=('x', 'size'), sx=('x', 'sum'), sa=('a', 'sum'))
                cn, cs, ca = c_n.copy(), c_sum.copy(), c_abs.copy()
                if len(own):
                    cn[own.index.to_numpy()] -= own.n.to_numpy()
                    cs[own.index.to_numpy()] -= own.sx.to_numpy()
                    ca[own.index.to_numpy()] -= own.sa.to_numpy()
                fm = found.copy()
                fm[found] = cn[pos[found]] > 0
                with np.errstate(invalid='ignore', divide='ignore'):
                    ctrl = ss * cs[pos] / cn[pos]
                    ctrl_abs = ca[pos] / cn[pos]
                dlt = (y - ctrl)[fm]
                cd = clustered_mean(dlt, gd[fm])
                r['ctrl_n_matched'] = int(fm.sum())
                r['ctrl_mean_sig'] = float(np.mean(ctrl[fm])) if fm.any() else np.nan
                r['ctrl_diff'], r['ctrl_diff_se'], r['ctrl_diff_p'] = cd['mean'], cd['se'], cd['p']
                if H == PRIMARY_H:
                    r['ctrl_diff_ci_lo'], r['ctrl_diff_ci_hi'] = boot_mean_ci(dlt, gd[fm], B, rng)
                r['ctrl_cells_median_bars'] = float(np.median(cn[pos[fm]])) if fm.any() else np.nan
                da = (np.abs(y) - ctrl_abs)[fm]
                ca_ = clustered_mean(da, gd[fm])
                r['abs_vs_ctrl_diff'], r['abs_vs_ctrl_se'] = ca_['mean'], ca_['se']
                # stability (secondary): halves / periods, session type, σ tercile, per-year signs
                if H == PRIMARY_H and cls in CLASSES:
                    yrs = year[ii]
                    for lab, mm in period_masks(ds, yrs).items():
                        st = clustered_mean(y[mm], gd[mm])
                        stab_rows.append(dict(dataset=ds, cls=cls, H=H, split='period', group=lab, n=st['n'], days=st['days'],
                                              mean=st['mean'], se=st['se'], p=st['p']))
                    for lab, mm in (('RTH', rth[ii]), ('ETH', ~rth[ii])):
                        st = clustered_mean(y[mm], gd[mm])
                        stab_rows.append(dict(dataset=ds, cls=cls, H=H, split='session', group=lab, n=st['n'], days=st['days'],
                                              mean=st['mean'], se=st['se'], p=st['p']))
                    srt_i = srt[ii]
                    for k in range(3):
                        mm = srt_i == k
                        st = clustered_mean(y[mm], gd[mm])
                        stab_rows.append(dict(dataset=ds, cls=cls, H=H, split='sigma_tercile', group=str(k + 1), n=st['n'],
                                              days=st['days'], mean=st['mean'], se=st['se'], p=st['p']))
                    npos = 0
                    uy = np.unique(yrs)
                    for yv in uy:
                        mm = yrs == yv
                        st = clustered_mean(y[mm], gd[mm])
                        npos += int(st['mean'] > 0)
                        stab_rows.append(dict(dataset=ds, cls=cls, H=H, split='year', group=str(yv), n=st['n'], days=st['days'],
                                              mean=st['mean'], se=st['se'], p=st['p']))
                    # share of years with a positive mean; p = two-sided sign test against 1/2
                    stab_rows.append(dict(dataset=ds, cls=cls, H=H, split='years_positive', group=f'{npos}/{len(uy)}',
                                          n=len(uy), days=np.nan, mean=npos / len(uy) if len(uy) else np.nan, se=np.nan,
                                          p=float(stats.binomtest(npos, len(uy)).pvalue) if len(uy) else np.nan))
            rows.append(r)
        # twins
        for a, b0 in (('abs', 'conf_flow'), ('pwf', 'pshock_flow')):
            for side_lab, sides in (('pooled', (1, -1)), ('up', (1,)), ('down', (-1,))):
                ca_ = [f'{a}_buy' if s > 0 else f'{a}_sell' for s in sides] if a == 'abs' else [f'{a}_up' if s > 0 else f'{a}_down' for s in sides]
                cb_ = [f'{b0}_up' if s > 0 else f'{b0}_dn' for s in sides]
                m1 = ev.cls.isin(ca_).to_numpy() & ok_e
                m0 = ev.cls.isin(cb_).to_numpy() & ok_e
                y1, y0 = xe[m1], xe[m0]
                g1, g0 = day[ev_i[m1]], day[ev_i[m0]]
                cd = clustered_diff(y1, g1, y0, g0)
                tr = dict(dataset=ds, twin=f'{a}_vs_{b0}', side=side_lab, H=H, n_event=len(y1), n_twin=len(y0),
                          days_event=len(np.unique(g1)), days_twin=len(np.unique(g0)),
                          mean_event=float(y1.mean()) if len(y1) else np.nan, mean_twin=float(y0.mean()) if len(y0) else np.nan,
                          se_event=clustered_mean(y1, g1)['se'], se_twin=clustered_mean(y0, g0)['se'],
                          diff=cd['diff'], diff_se=cd['se'], diff_t=cd['t'], diff_p=cd['p'],
                          abs_event=float(np.abs(y1).mean()) if len(y1) else np.nan, abs_twin=float(np.abs(y0).mean()) if len(y0) else np.nan)
                tr['diff_ci_lo'], tr['diff_ci_hi'] = boot_diff_ci(y1, g1, y0, g0, B if H == PRIMARY_H or side_lab == 'pooled' else 0, rng)
                twin_rows.append(tr)
    cl = pd.DataFrame(rows)
    prim = (cl.H == PRIMARY_H) & cl.cls.isin(CLASSES)
    cl['bh_q_primary'] = np.nan
    cl.loc[prim, 'bh_q_primary'] = bh_qvalues(cl.loc[prim, 'sig_p'].to_numpy())
    cl['bh_reject_5pct'] = cl.bh_q_primary <= 0.05
    calib = calibration(df, keep)
    info = dict(dataset=ds, label=cfg['label'], file=meta['file'], tf_min=tf, ke=ke, life=meta['life'],
                rows=int(keep.sum()), sessions=int(df.session_date[keep].nunique()),
                first=str(df.t[keep].iloc[0]), last=str(df.t[keep].iloc[-1]),
                cost=cfg['cost'], cost_unit=cfg['unit'], baseline=base, calibration=calib,
                restricted_to_sessions=meta.get('restricted_to_sessions'), runtime_s=round(time.time() - t0, 1))
    return dict(classes=cl, twins=pd.DataFrame(twin_rows), stability=pd.DataFrame(stab_rows), info=info)


def period_masks(ds, yrs):
    if ds.startswith('es_5m') and ds != 'es_5m_mes_period':
        return {'2008-2016': yrs <= 2016, '2017-2026': yrs >= 2017}
    if ds.startswith('spy'):
        return {'2000-2007': yrs <= 2007, '2008-2016': (yrs >= 2008) & (yrs <= 2016), '2017-2026': yrs >= 2017}
    return {'2021-2023': yrs <= 2023, '2024-2026': yrs >= 2024}


def calibration(df, keep):
    z = df.Z.to_numpy()
    zc = keep & np.isfinite(z) & (df.z_cal_ok.to_numpy() == 1)
    hq = keep & (df.hq_ok.to_numpy() == 1)
    g = df.gate.to_numpy() == 1
    rho = df.rho_p.to_numpy()[hq]
    return {'P_absZ_ge2_pct': float(100 * (np.abs(z[zc]) >= 2).mean()), 'P_absZ_ge3_pct': float(100 * (np.abs(z[zc]) >= 3).mean()),
            'gate_open_pct_of_hq': float(100 * g[hq].mean()),
            'rho_quantiles': {q: float(np.nanpercentile(rho, q)) for q in (5, 25, 50, 75, 95)},
            'z_bars': int(zc.sum())}


# ───────────────────────────── cross-instrument agreement ─────────────────────────────

def cross_instrument():
    """ES vs MES (same timestamps, both clean sessions) and ES vs SPY (common RTH bars): Z, zF and event agreement."""
    cols = ['t', 'Z', 'zF', 'zP', 'z_cal_ok', 'gate', 'new_abs', 'ev_side', 'new_pwf', 'pwf_side', 'al_z_up', 'al_z_dn', 'rth', 'rho_p']
    es = pd.read_parquet(studyenv.feat_dir() / 'es_5m_cr1m.parquet', columns=cols)
    out = {}
    for other, fn, rth_only in (('mes', 'mes_5m_cr1m', False), ('spy_rth', 'spy_5m_cr1m_rthonly', True)):
        ot = pd.read_parquet(studyenv.feat_dir() / f'{fn}.parquet', columns=cols)
        j = es.merge(ot, on='t', suffixes=('_es', '_o'))
        if rth_only:
            j = j[j.rth_es]
        both = np.isfinite(j.Z_es) & np.isfinite(j.Z_o) & (j.z_cal_ok_es == 1) & (j.z_cal_ok_o == 1)
        jj = j[both]
        res = {'common_bars': int(len(j)), 'common_bars_with_Z': int(both.sum()),
               'Z_corr': float(np.corrcoef(jj.Z_es, jj.Z_o)[0, 1]), 'zF_corr': float(np.corrcoef(jj.zF_es, jj.zF_o)[0, 1]),
               'zP_corr': float(np.corrcoef(jj.zP_es, jj.zP_o)[0, 1]),
               'Z_sign_agree': float((np.sign(jj.Z_es) == np.sign(jj.Z_o)).mean()),
               'rho_median_es': float(jj.rho_p_es.median()), 'rho_median_other': float(jj.rho_p_o.median())}
        for nm, a, s in (('abs', 'new_abs', 'ev_side'), ('pwf', 'new_pwf', 'pwf_side')):
            for side in (1, -1):
                ia = np.flatnonzero((j[f'{a}_es'] == 1) & (j[f'{s}_es'] == side))
                ib = np.flatnonzero((j[f'{a}_o'] == 1) & (j[f'{s}_o'] == side))
                for tol in (0, 3):
                    m = _match(ia, ib, tol)
                    res[f'{nm}_{"buy" if side > 0 else "sell"}_tol{tol}'] = dict(n_es=len(ia), n_other=len(ib), matched=m,
                                                                               jaccard=m / (len(ia) + len(ib) - m) if (len(ia) + len(ib) - m) else None)
        for a in ('al_z_up', 'al_z_dn'):
            ia, ib = np.flatnonzero(j[f'{a}_es'] == 1), np.flatnonzero(j[f'{a}_o'] == 1)
            for tol in (0, 3):
                m = _match(ia, ib, tol)
                res[f'{a}_tol{tol}'] = dict(n_es=len(ia), n_other=len(ib), matched=m,
                                            jaccard=m / (len(ia) + len(ib) - m) if (len(ia) + len(ib) - m) else None)
        out[f'es_vs_{other}'] = res
    return out


def _match(ia, ib, tol):
    """One-to-one nearest matching of sorted index arrays within tol (two-pointer greedy, exact for tol 0)."""
    m, p, used = 0, 0, np.zeros(len(ib), bool)
    for a in ia:
        lo = np.searchsorted(ib, a - tol, 'left')
        hi = np.searchsorted(ib, a + tol, 'right')
        best, bd = -1, None
        for k in range(lo, hi):
            if not used[k] and (bd is None or abs(ib[k] - a) < bd):
                best, bd = k, abs(ib[k] - a)
        if best >= 0:
            used[best] = True
            m += 1
    return m


# ───────────────────────────── main ─────────────────────────────

def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 5)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('datasets', nargs='*', default=list(DATASETS))
    ap.add_argument('--boot', type=int, default=2000)
    ap.add_argument('--no-cross', action='store_true')
    a = ap.parse_args()
    RES = studyenv.results_dir('robust')
    RES.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    infos, prim, twins = {}, [], []
    for ds in a.datasets:
        r = analyse(ds, a.boot, rng)
        r['classes'].to_csv(RES / f'{ds}_classes.csv', index=False)
        r['twins'].to_csv(RES / f'{ds}_twins.csv', index=False)
        r['stability'].to_csv(RES / f'{ds}_stability.csv', index=False)
        infos[ds] = r['info']
        c = r['classes']
        prim.append(c[(c.H == PRIMARY_H)])
        twins.append(r['twins'][r['twins'].H == PRIMARY_H])
        print(ds, json.dumps(_clean(r['info']))[:600], flush=True)
    P = pd.concat(prim, ignore_index=True)
    T = pd.concat(twins, ignore_index=True)
    # merge with previous runs of other datasets (when run on a subset)
    fp, ft = RES / 'robust_primary_30m.csv', RES / 'robust_twins_30m.csv'
    if fp.exists() and set(a.datasets) != set(DATASETS):
        P0, T0 = pd.read_csv(fp), pd.read_csv(ft)
        P = pd.concat([P0[~P0.dataset.isin(a.datasets)], P], ignore_index=True)
        T = pd.concat([T0[~T0.dataset.isin(a.datasets)], T], ignore_index=True)
    P.to_csv(fp, index=False)
    T.to_csv(ft, index=False)
    summ_f = RES / 'robust_summary.json'
    summ = json.load(open(summ_f)) if summ_f.exists() else {}
    summ.setdefault('datasets', {}).update(_clean(infos))
    if not a.no_cross:
        summ['cross_instrument'] = _clean(cross_instrument())
    summ['primary_30m'] = {}
    for ds, g in P.groupby('dataset'):
        gg = g[g.cls.isin(CLASSES)].set_index('cls').reindex(CLASSES)
        summ['primary_30m'][ds] = {c: _clean(dict(n=row.n, days=row.days, mean=row.sig_mean, se=row.sig_se, p=row.sig_p,
                                                  ci=[row.sig_ci_lo, row.sig_ci_hi], q=row.bh_q_primary, hit=row.get('hit'),
                                                  ctrl_diff=row.get('ctrl_diff'), ctrl_p=row.get('ctrl_diff_p'),
                                                  pts=row.get('pts_mean'), net_follow=row.get('net_pts_follow')))
                                   for c, row in gg.iterrows() if np.isfinite(row.n)}
        summ['primary_30m'][ds]['bh_rejections_5pct'] = [c for c, row in gg.iterrows() if row.bh_q_primary <= 0.05]
    # sign consistency of the primary endpoint across the replication datasets
    piv = P[P.cls.isin(CLASSES)].pivot_table(index='cls', columns='dataset', values='sig_mean').reindex(CLASSES)
    pvp = P[P.cls.isin(CLASSES)].pivot_table(index='cls', columns='dataset', values='sig_p').reindex(CLASSES)
    summ['primary_30m_means_by_dataset'] = {c: _clean({ds: dict(mean=piv.loc[c, ds], p=pvp.loc[c, ds]) for ds in piv.columns})
                                            for c in CLASSES}
    summ['twins_30m'] = {f'{r.dataset}|{r.twin}|{r.side}': _clean(dict(n_event=r.n_event, n_twin=r.n_twin, mean_event=r.mean_event,
                                                                        mean_twin=r.mean_twin, diff=r['diff'], se=r.diff_se, p=r.diff_p,
                                                                        ci=[r.diff_ci_lo, r.diff_ci_hi]))
                         for _, r in T.iterrows()}
    json.dump(summ, open(summ_f, 'w'), indent=1, default=str)
    print(json.dumps(summ.get('cross_instrument', {}), indent=1)[:4000])


if __name__ == '__main__':
    main()
