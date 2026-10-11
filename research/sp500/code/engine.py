#!/usr/bin/env python3
"""Exact, fast Python port of the outputs of "Preço × CVD Normalizado [Order Flow]" (Pine v6, Standard edition).

The port follows src/price_cvd_normalizer.src.pine line by line for everything the event study needs: the price
increment r (gap rule), the delta engine (source / BVC fallback / no-observation rule), σr, σΔ, ρ (lagged one bar),
the clipped σ-units, the quality run (hqRun / hqNeed / hqOk), the divergence D and its lagged RMS calibration (Z,
zCalOk), the ρ gate, the legs, the short-window event statistics (fE, pE, zF, zP, nCalE, evWeak), the classes
absorbed / pinned / price-without-flow with their per-class-and-side clusters (refractory period of ke observations),
the new-event flags, the absorption resolution state machine, the Z alerts with hysteresis and the classical pivot
divergence. Drawing, table and text code is not ported (it has no effect on these values).

Pine semantics reproduced (PineTS 0.11.0 and the TradingView documentation agree on all of them):
  * ta.stdev is the POPULATION standard deviation; ta.stdev / ta.sma / ta.correlation / math.sum use the last
    `length` NON-na values (na values are skipped) and are na while fewer than `length` have been seen; on a bar whose
    value is na they return the value of the window as it stands (= the value at the last valid bar).
  * ta.correlation = (sma(xy) − sma(x)·sma(y)) / sqrt((sma(x²) − sma(x)²)·(sma(y²) − sma(y)²)), 0 when a variance ≤ 0
    (PineTS); r and Δ are na on exactly the same bars, so the five windows cover the same bars.
  * x[1] is the value on the previous bar; nz(x) replaces na by 0.
  * ta.highest/ta.lowest over the last ke bars (na before ke bars); ta.pivothigh/pivotlow with TradingView's
    asymmetric tie rule (a LEFT bar equal to the candidate does not disqualify it, a RIGHT bar equal to it does).
  * All historical bars are confirmed (barstate.isconfirmed = true).

Rounding (Params.pine_round, default True). PineTS rounds to 10 decimal places (Context.precision: Math.round(x·1e10)/1e10
when |x|·1e10 < 2^53) the results of ta.stdev / ta.sma / ta.correlation / ta.highest / ta.lowest / array.sum, the
return value of every user function (clip → ur, ud and the BVC z; normCdf; tanhF; rmsLag) and every `:=` / `+=`
update (delta, cum and sPrev inside rmsLag, cvdC); a plain declaration (`float x = …`, e.g. r, D, Z, fE, pE, zF, zP) and
math.sum are NOT rounded, and math.sum adds the window newest first. The port reproduces exactly those operations. This
matters only for EXACT TIES: on a tick grid the price often returns to the same level inside the event window, so
Σur is mathematically 0 (equal-magnitude log returns divided by the same σ); with the rounding it is exactly 0 and the
absorption condition sF·zP ≤ 0 holds, while plain float64 leaves ±1e-13 noise that decides the sign arbitrarily
(observed on a 1-minute ES chart with ke = 5: 3 absorptions differed). TradingView does not document such rounding; on
TradingView those ties are decided by its own float noise, so the rounded (mathematically exact) outcome is used.
pine_round=False gives plain float64. Validation: validate_pine.py (all flags identical, |ΔZ| ≤ 4e-10).

Vectorised with numpy; only the true state machines (clusters, resolution, alert hysteresis, pivot comparison) are
loops, and they run over the sparse candidate bars where possible.

Usage:
    from engine import Params, run_engine
    out = run_engine(bars, Params(tf_sec=300))     # bars: DataFrame/dict with the columns listed in run_engine
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

__all__ = ['Params', 'run_engine', 'event_windows', 'norm_cdf']


@dataclass
class Params:
    """Indicator inputs (Pine defaults) plus the chart timeframe and the study hooks.

    gate: False removes the ρ condition from the gate (gateOn = hqOk) — a study variant, not a Pine option.
    rho_min: the "ρ mínimo (gate)" input; the effective gate is max(rho_min, tanh(1.96/√(N−3))) as in Pine.
    """
    N: int = 100                 # nIn   janela σ/ρ
    K: int = 20                  # kIn   horizonte da divergência
    M: int = 1000                # mIn   janela de calibração
    clip: float = 4.0            # clipIn
    thr: float = 2.0             # thrIn
    thr2: float = 3.0            # thr2In
    rho_min: float = 0.30        # rhoMinIn
    gate: bool = True            # study hook: False → gate without the ρ condition
    drift: bool = False          # driftIn
    ev: bool = True              # evIn
    pwf: bool = True             # pwfIn
    ev_win_min: int = 15         # evWinIn (minutes)
    life_min: int = 60           # lifeIn (minutes)
    zf: float = 2.0              # zfIn
    pin: float = 3.0             # pinIn
    pin_p: float = 0.5           # pinPIn
    low_conf: bool = True        # lowConfIn (tier-2 events shown)
    piv: bool = True             # pivIn (Pine default is False; the study wants the pivots)
    piv_l: int = 5
    piv_r: int = 2
    piv_min: int = 5
    piv_max: int = 60
    piv_mag: float = 0.5
    tf_sec: int = 300            # chart timeframe in seconds (timeframe.in_seconds())
    bar_sig_len: int = 100       # fixed σ length of the gap rule / BVC fallback (literal 100 in the source)
    pine_round: bool = True      # round to 10 decimals where PineTS does (see module docstring); False = plain float64

    def to_dict(self):
        return asdict(self)


# ─────────────────────────────── helpers ───────────────────────────────

def pine_round(x: float) -> int:
    """Pine math.round for the positive arguments used here (ties round up)."""
    return int(math.floor(x + 0.5))


def tanh_f(y: float) -> float:
    """tanhF of the source: exp-based, argument clamped to ±20."""
    e = math.exp(2.0 * max(-20.0, min(20.0, y)))
    return (e - 1.0) / (e + 1.0)


def norm_cdf(z):
    """Φ by Abramowitz–Stegun 7.1.26, exactly as normCdf() in the source (vectorised)."""
    z = np.asarray(z, float)
    x = np.abs(z) / math.sqrt(2.0)
    t = 1.0 / (1.0 + 0.3275911 * x)
    e = 1.0 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-x * x)
    return 0.5 * (1.0 + np.sign(z) * e)


def event_windows(p: Params):
    """ke (event window, bars) and life (max resolution time, bars) exactly as in section 7/9 of the source."""
    ke = min(max(1, pine_round(p.ev_win_min * 60.0 / p.tf_sec)), max(1, math.floor(p.M / 20.0)))
    life = max(1, pine_round(p.life_min * 60.0 / p.tf_sec))
    return ke, life


def js_round(y):
    """JavaScript Math.round (ties toward +inf), exact for doubles."""
    y = np.asarray(y, float)
    f = np.floor(y)
    return f + ((y - f) >= 0.5)


def pinets_precision(x):
    """PineTS Context.precision(value, 10): Math.round(value*1e10)/1e10 when |value|*1e10 < 2^53 (else unchanged)."""
    x = np.asarray(x, float)
    with np.errstate(invalid='ignore'):
        ok = np.abs(x) * 1e10 < 2.0 ** 53
    return np.where(ok, js_round(x * 1e10) / 1e10, x)


def _ident(x):
    return np.asarray(x, float)


def _seq_sum(v, n):
    """Sum of each window of n consecutive values, accumulated NEWEST FIRST from 0 (the order of PineTS math.sum),
    aligned to the window's last element; NaN before."""
    L = len(v)
    out = np.full(L, np.nan)
    if L < n:
        return out
    acc = v[n - 1:].astype(float).copy()
    for j in range(1, n):
        acc += v[n - 1 - j:L - j]
    out[n - 1:] = acc
    return out


def _seq_ssd(v, n, mean):
    """Σ (v − mean)² over each window, newest first (PineTS ta.stdev); mean aligned to the window's last element."""
    L = len(v)
    out = np.full(L, np.nan)
    if L < n:
        return out
    m = mean[n - 1:]
    acc = (v[n - 1:] - m) ** 2
    for j in range(1, n):
        acc += (v[n - 1 - j:L - j] - m) ** 2
    out[n - 1:] = acc
    return out


def lag1(x):
    out = np.empty_like(x, dtype=float)
    out[0] = np.nan
    out[1:] = x[:-1]
    return out


def _win_reduce(v, n, fn, chunk=200_000):
    """fn over every full window of n consecutive elements of v (result aligned to the window's last element, NaN
    before). Chunked so that the temporaries stay small."""
    out = np.full(len(v), np.nan)
    if len(v) < n:
        return out
    w = sliding_window_view(v, n)
    for a in range(0, len(w), chunk):
        out[n - 1 + a:n - 1 + a + len(w[a:a + chunk])] = fn(w[a:a + chunk])
    return out


def _skipna(x, n, how, y=None, R=_ident):
    """Pine window over the last n non-na values (skip-na), value carried on na bars, NaN until n values exist.
    how: 'sum' (math.sum, newest-first, not rounded) | 'mean' (ta.sma) | 'std' (ta.stdev, population) |
    'corr' (ta.correlation, moment formula as PineTS / TradingView). R = rounding applied to the built-in's result."""
    x = np.asarray(x, float)
    ok = np.isfinite(x) if y is None else (np.isfinite(x) & np.isfinite(y))
    idx = np.flatnonzero(ok)
    res = np.full(len(x), np.nan)
    if len(idx) < n:
        return res
    v = x[idx]
    if how == 'sum':
        r = _seq_sum(v, n)
    elif how == 'mean':
        r = R(_seq_sum(v, n) / n)
    elif how == 'std':
        m = _seq_sum(v, n) / n
        r = R(np.sqrt(_seq_ssd(v, n, m) / n))
    elif how == 'corr':
        u = np.asarray(y, float)[idx]
        mx = _seq_sum(v, n) / n
        my = _seq_sum(u, n) / n
        mxy = _seq_sum(v * u, n) / n
        mxx = _seq_sum(v * v, n) / n
        myy = _seq_sum(u * u, n) / n
        vx = mxx - mx * mx
        vy = myy - my * my
        with np.errstate(invalid='ignore', divide='ignore'):
            r = R(np.where((vx <= 0) | (vy <= 0), 0.0, (mxy - mx * my) / np.sqrt(vx * vy)))
        r[~np.isfinite(mx)] = np.nan
    else:
        raise ValueError(how)
    # carry the last value on na bars
    res[idx] = r
    pos = np.full(len(x), -1)
    pos[idx] = idx
    pos = np.maximum.accumulate(pos)
    has = pos >= 0
    out = np.full(len(x), np.nan)
    out[has] = res[pos[has]]
    return out


def _rms_lag(x, m, warm, R=_ident):
    """rmsLag() of the source: RMS of the PREVIOUS valid values (expanding mean of x² with ≥ warm values; mean of the
    last m valid values once more than m exist). Returns (rms, n0 = number of previous valid values).
    With R = PineTS rounding: `cum += x2` and `sPrev := s` are rounded at each update and the returned RMS too."""
    x = np.asarray(x, float)
    ok = np.isfinite(x)
    n = len(x)
    cntb = np.zeros(n, dtype=np.int64)
    cntb[1:] = np.cumsum(ok)[:-1]                      # valid values strictly before t
    v2 = x[ok] * x[ok]
    k_cum = min(len(v2), m + 1)                         # cum is only read while cnt ≤ m
    cum = np.empty(k_cum)
    acc = 0.0
    for k in range(k_cum):                              # sequential, rounded like `cum += x2`
        acc = float(R(acc + v2[k]))
        cum[k] = acc
    s_prev = R(_seq_sum(v2, m) / m) if len(v2) >= m else np.full(len(v2), np.nan)
    out = np.full(n, np.nan)
    last = cntb - 1                                     # index (in valid values) of the last valid before t
    big = cntb > m
    out[big] = np.sqrt(s_prev[last[big]])
    mid = (~big) & (cntb >= warm) & (cntb > 0)
    out[mid] = np.sqrt(cum[last[mid]] / cntb[mid])
    return R(out), cntb


def _rolling_extreme(x, n, fn):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = fn(sliding_window_view(x, n), axis=1)
    return out


def _pivots(src, L, R, high=True):
    """ta.pivothigh/pivotlow (PineTS 0.11.0 = TradingView tie rule). Value reported on the confirmation bar t for the
    candidate at t − R; NaN elsewhere. No na in src (OHLC)."""
    n = len(src)
    out = np.full(n, np.nan)
    if n < L + R + 1:
        return out
    c = np.arange(L + R, n) - R                         # candidate index for each confirmation bar t = c + R
    cand = src[c]
    left = sliding_window_view(src, L)[c - L]           # src[c−L .. c−1]
    right = sliding_window_view(src, R)[c + 1]          # src[c+1 .. c+R]
    if high:
        ok = (left.max(axis=1) <= cand) & (right.max(axis=1) < cand)
    else:
        ok = (left.min(axis=1) >= cand) & (right.min(axis=1) > cand)
    t = c + R
    out[t[ok]] = cand[ok]
    return out


# ─────────────────────────────── engine ───────────────────────────────

def run_engine(bars, p: Params | None = None, return_internal: bool = False) -> pd.DataFrame:
    """Compute the indicator outputs bar by bar.

    bars (DataFrame or mapping of equal-length arrays), one row per CHART bar in time order:
      open, high, low, close   prices
      volume                   chart volume (NaN = missing)
      delta                    per-bar delta of the selected fine source (intrabars); NaN where the source has no data
      session_first            bool, session.isfirstbar
      tier                     configured quality of the fine source (cfgTier: 3 high, 2 medium, 1 low); scalar or array
      src_vol   (optional)     volume of the fine source (default: volume); NaN = missing
      has_src   (optional)     bool, the bar has intrabars (default: delta is finite). False → BVC-on-the-bar fallback
                               (tier 1), as with "Barras sem intrabars" = BVC.
    Returns a DataFrame (same index) with the per-bar outputs; attrs['params'], attrs['ke'], attrs['life'].
    """
    p = p or Params()
    g = (lambda k: np.asarray(bars[k])) if not isinstance(bars, pd.DataFrame) else (lambda k: bars[k].to_numpy())
    o = g('open').astype(float)
    h = g('high').astype(float)
    lo = g('low').astype(float)
    c = g('close').astype(float)
    vol = g('volume').astype(float)
    dsrc = g('delta').astype(float)
    n = len(c)
    sfirst = g('session_first').astype(bool)
    keys = bars.columns if isinstance(bars, pd.DataFrame) else bars.keys()
    tier_cfg = np.broadcast_to(np.asarray(g('tier') if 'tier' in keys else 2, dtype=np.int64), (n,)).copy()
    src_vol = g('src_vol').astype(float) if 'src_vol' in keys else vol.copy()
    has_src = g('has_src').astype(bool) if 'has_src' in keys else np.isfinite(dsrc)
    N, K, M = p.N, p.K, p.M
    ke, life = event_windows(p)
    R = pinets_precision if p.pine_round else _ident
    idx = np.arange(n)

    # ── 6.3 r with the gap rule; BVC on the bar (fallback) ──
    c1 = lag1(c)
    with np.errstate(divide='ignore', invalid='ignore'):
        r_raw = 1e4 * np.log(c / c1)
        s_raw_p = lag1(_skipna(r_raw, p.bar_sig_len, 'std', R=R))
        jump = np.abs(1e4 * np.log(o / c1)) > 3.0 * np.where(np.isfinite(s_raw_p), s_raw_p, 1e10)
        gap_bar = ~np.isfinite(c1) | sfirst | jump
        r_bar = np.where(gap_bar, 1e4 * np.log(c / o), r_raw)
    s_bar_p = lag1(_skipna(r_bar, p.bar_sig_len, 'std', R=R))
    with np.errstate(invalid='ignore', divide='ignore'):
        z_bar = np.where((s_bar_p > 0) & np.isfinite(r_bar), R(np.clip(r_bar / s_bar_p, -10.0, 10.0)), 0.0)
    bar_delta = vol * (2.0 * R(norm_cdf(z_bar)) - 1.0)

    # ── 6.5 source selection, no-observation rule, tier ──
    delta = R(np.where(has_src, dsrc, bar_delta))                 # `delta := …` (rounded by PineTS)
    bar_vol = np.where(has_src, src_vol, vol)
    tier0 = np.where(has_src, tier_cfg, 1)              # fallback BVC → tier 1 (never 0 with the BVC fallback)
    obs_vol = np.where(tier0 > 0, bar_vol, vol)
    vol_miss = (tier0 > 0) & ~np.isfinite(bar_vol)
    no_trade = np.isfinite(obs_vol) & (obs_vol == 0)
    no_obs = vol_miss | no_trade
    delta = np.where(no_obs, np.where(vol_miss, np.nan, 0.0), delta)
    # tier := tierP on no-observation bars (chain of inherited tiers)
    tier = tier0.copy()
    if no_obs.any():
        src_i = np.where(~no_obs, idx, -1)
        src_i = np.maximum.accumulate(src_i)
        tier = np.where(src_i >= 0, tier0[np.maximum(src_i, 0)], 0)

    # hqRun (observations only) and lqBar
    obs_i = np.flatnonzero(~no_obs)
    hq_obs = tier[obs_i] >= 2
    run = np.zeros(len(obs_i), dtype=np.int64)
    if len(obs_i):
        cs = np.cumsum(hq_obs)
        reset = np.where(~hq_obs, cs, 0)
        reset = np.maximum.accumulate(reset)
        run = cs - reset
    hq_run = np.zeros(n, dtype=np.int64)
    pos = np.full(n, -1)
    pos[obs_i] = np.arange(len(obs_i))
    pos = np.maximum.accumulate(pos)
    hq_run[pos >= 0] = run[pos[pos >= 0]]
    lq = np.where((~no_obs) & (tier < 2), idx, -1)
    lq_bar = np.maximum.accumulate(lq)

    # ── 7. increments and statistics ──
    delta_obs = np.where(no_obs, np.nan, delta)
    if p.drift:
        d_sma_p = lag1(_skipna(delta_obs, N, 'mean', R=R))
        d = np.where(np.isfinite(r_bar), delta_obs - d_sma_p, np.nan)
    else:
        d = np.where(np.isfinite(r_bar), delta_obs, np.nan)
    r = np.where(np.isfinite(d), r_bar, np.nan)
    d_disp = np.where(no_trade & np.isfinite(r_bar), 0.0, d)

    sr = _skipna(r, N, 'std', R=R)
    sd = _skipna(d, N, 'std', R=R)
    rho = _skipna(r, N, 'corr', d, R=R)
    sr_p, sd_p, rho_p = lag1(sr), lag1(sd), lag1(rho)
    with np.errstate(invalid='ignore', divide='ignore'):
        ur_raw = np.where(sr_p > 0, R(np.clip(r / sr_p, -p.clip, p.clip)), np.nan)   # clip() returns are rounded
        ud_raw = np.where(sd_p > 0, R(np.clip(d / sd_p, -p.clip, p.clip)), np.nan)
    u_ok = np.isfinite(ur_raw) & np.isfinite(ud_raw)
    ur = np.where(u_ok, ur_raw, np.nan)
    ud = np.where(u_ok, ud_raw, np.nan)

    hq_need = N + max(K, ke) + (N if p.drift else 0)
    hq_ok = (tier >= 2) & ~no_obs & (hq_run >= hq_need)

    sum_diff_k = _skipna(ur - ud, K, 'sum')
    rho_pz = np.where(np.isfinite(rho_p), rho_p, 0.0)
    d_stat = np.where(hq_ok, sum_diff_k / np.sqrt(2.0 * K * (1.0 - np.minimum(rho_pz, 0.95))), np.nan)
    rms_d, n_cal_d = _rms_lag(d_stat, M, N, R)
    with np.errstate(invalid='ignore', divide='ignore'):
        z = np.where((rms_d > 0) & np.isfinite(d_stat), d_stat / rms_d, np.nan)
    z_cal_ok = n_cal_d >= 2 * N
    rho_min_eff = max(p.rho_min, float(R(tanh_f(1.96 / math.sqrt(N - 3)))))
    if p.gate:
        gate_on = hq_ok & np.isfinite(rho_p) & (rho_p >= rho_min_eff)
    else:
        gate_on = hq_ok.copy()
    p_leg = _skipna(ur, K, 'sum') / math.sqrt(K)
    f_leg = _skipna(ud, K, 'sum') / math.sqrt(K)

    # cvdC (continuous CVD, for the pivots)
    dd = np.where(np.isfinite(d_disp), d_disp, 0.0)
    if p.pine_round and not np.array_equal(dd, np.round(dd)):   # `cvdC := nz(cvdC) + dDisp`, rounded at each step
        cvd_c = np.empty(n)
        acc = 0.0
        for i, v in enumerate(dd.tolist()):
            acc = float(R(acc + v))
            cvd_c[i] = acc
    else:                                               # integer deltas: the running sum is exact, rounding is a no-op
        cvd_c = np.cumsum(dd)
    first_valid = np.flatnonzero(np.isfinite(d_disp))
    cvd_c = cvd_c.astype(float)
    if len(first_valid):
        cvd_c[:first_valid[0]] = np.nan
    else:
        cvd_c[:] = np.nan

    # ── 9. events ──
    sum_ud_ke = _skipna(ud, ke, 'sum')
    sum_ur_ke = _skipna(ur, ke, 'sum')
    f_e = np.where(hq_ok, sum_ud_ke / math.sqrt(ke), np.nan)
    p_e = np.where(hq_ok, sum_ur_ke / math.sqrt(ke), np.nan)
    rms_f, n_cal_f = _rms_lag(f_e, M, N, R)
    rms_pp, n_cal_p = _rms_lag(p_e, M, N, R)
    with np.errstate(invalid='ignore', divide='ignore'):
        zf = np.where((rms_f > 0) & np.isfinite(f_e), f_e / rms_f, np.nan)
        zp = np.where((rms_pp > 0) & np.isfinite(p_e), p_e / rms_pp, np.nan)
    n_cal_e = np.minimum(n_cal_f, n_cal_p)
    hi_ke = _rolling_extreme(h, ke, np.max)
    lo_ke = _rolling_extreme(lo, ke, np.min)

    z_ok = np.isfinite(zf) & np.isfinite(zp)
    s_f = np.sign(np.where(np.isfinite(zf), zf, 0.0))
    s_p = np.sign(np.where(np.isfinite(zp), zp, 0.0))
    azf, azp = np.abs(zf), np.abs(zp)
    with np.errstate(invalid='ignore'):
        pinned = gate_on & z_ok & (azf >= p.pin) & (azp <= p.pin_p) & (s_f * zp < np.abs(rho_pz) * azf)
        absorbed = gate_on & z_ok & (((azf >= p.zf) & (s_f * zp <= 0)) | pinned)
        pwf = gate_on & z_ok & ~absorbed & (azp >= p.zf) & (s_p * zf <= 0)

    obs_idx = np.cumsum(np.isfinite(d))                 # obsIdx after this bar's increment

    def clusters(flag, side):
        new = np.zeros(n, dtype=bool)
        last_obs, last_side = None, 0
        for t in np.flatnonzero(flag):
            s = int(side[t])
            oi = int(obs_idx[t])
            if not (last_side == s and last_obs is not None and oi - last_obs <= ke):
                new[t] = True
            last_obs, last_side = oi, s
        return new

    abs_side = np.where(absorbed, np.where(s_f > 0, 1, -1), 0)
    pin_side = np.where(pinned, np.where(s_f > 0, 1, -1), 0)
    pwf_side = np.where(pwf, np.where(s_p > 0, 1, -1), 0)
    abs_new_cl = clusters(absorbed, abs_side)
    pin_new_cl = clusters(pinned, pin_side)
    pwf_new_cl = clusters(pwf, pwf_side)
    tier_ev_ok = (tier >= 3) | ((tier == 2) & p.low_conf)
    low_conf = tier == 2
    ev_weak = n_cal_e < max(20 * ke, 2 * N)
    hollow = low_conf | ev_weak
    new_abs = p.ev & tier_ev_ok & abs_new_cl
    new_pin = p.ev & tier_ev_ok & pin_new_cl
    new_pwf = p.pwf & tier_ev_ok & pwf_new_cl

    # absStart (1st bar of the current absorption cluster)
    abs_start = np.where(abs_new_cl, idx, -1)
    abs_start = np.maximum.accumulate(abs_start)

    # ── resolution machine (one pending absorption; a new one supersedes it) ──
    res_cont = np.zeros(n, dtype=bool)
    res_held = np.zeros(n, dtype=bool)
    res_exp = np.zeros(n, dtype=bool)
    res_side = np.zeros(n, dtype=np.int8)
    res_low = np.zeros(n, dtype=bool)
    res_weak = np.zeros(n, dtype=bool)
    res_age = np.full(n, -1, dtype=np.int32)             # bars from the event to its resolution (on the resolution bar)
    sup = np.zeros(n, dtype=bool)                        # this new event superseded a pending one
    sup_age = np.full(n, -1, dtype=np.int32)
    ev_outcome = np.zeros(n, dtype=np.int8)              # on the EVENT bar: 1 cont, 2 held, 3 expired, 4 superseded, 0 open
    ev_res_bar = np.full(n, -1, dtype=np.int64)          # on the EVENT bar: bar index where it ended
    ev_h0 = np.full(n, np.nan)
    ev_l0 = np.full(n, np.nan)
    pin_in_cl = np.zeros(n, dtype=bool)                  # pinned inside the pending absorption cluster (label mark)
    pend_side = np.zeros(n, dtype=np.int8)               # evSide at the end of the bar
    ev_side, ev_hi, ev_lo, ev_bar, ev_lowc, ev_weakc = 0, np.nan, np.nan, -1, False, False
    cl = c.tolist()
    na_list = new_abs.tolist()
    np_list = new_pin.tolist()
    nab = np.flatnonzero(new_abs | new_pin)
    # iterate over bars while an event is pending, plus every new-event bar
    t = 0
    nab_ptr = 0
    while True:
        if ev_side == 0:
            if nab_ptr >= len(nab):
                break
            t = int(nab[nab_ptr])
        if ev_side != 0 and t > ev_bar:
            ct = cl[t]
            if ev_side > 0:
                is_cont, is_held = ct > ev_hi, ct < ev_lo
            else:
                is_cont, is_held = ct < ev_lo, ct > ev_hi
            is_exp = (not is_cont) and (not is_held) and (t - ev_bar >= life)
            if is_cont or is_held or is_exp:
                res_cont[t], res_held[t], res_exp[t] = is_cont, is_held, is_exp
                res_side[t] = ev_side
                res_low[t], res_weak[t] = ev_lowc, ev_weakc
                res_age[t] = t - ev_bar
                ev_outcome[ev_bar] = 1 if is_cont else 2 if is_held else 3
                ev_res_bar[ev_bar] = t
                ev_side = 0
        if na_list[t]:
            if ev_side != 0:
                sup[t] = True
                sup_age[t] = t - ev_bar
                ev_outcome[ev_bar] = 4
                ev_res_bar[ev_bar] = t
            ev_side = 1 if s_f[t] > 0 else -1
            ev_hi, ev_lo, ev_bar = hi_ke[t], lo_ke[t], t
            ev_lowc, ev_weakc = bool(hollow[t]), bool(ev_weak[t])
            ev_h0[t], ev_l0[t] = ev_hi, ev_lo
        if np_list[t] and not na_list[t] and ev_side != 0 and ev_bar == abs_start[t] and ev_side == s_f[t]:
            pin_in_cl[t] = True
        pend_side[t] = ev_side
        while nab_ptr < len(nab) and nab[nab_ptr] <= t:
            nab_ptr += 1
        t += 1
        if t >= n:
            break
    # pend_side between visited bars: carry (bars skipped only while no event is pending → 0 already)

    # ── 11. Z alerts with hysteresis ──
    cross_up = np.zeros(n, dtype=bool)
    cross_dn = np.zeros(n, dtype=bool)
    up_armed, dn_armed = True, True
    thr = p.thr
    zl = z.tolist()
    gl = gate_on.tolist()
    for t in np.flatnonzero(np.isfinite(z)):
        zt = zl[t]
        cu = gl[t] and zt >= thr and up_armed
        cd = gl[t] and zt <= -thr and dn_armed
        if cu:
            up_armed = False
            cross_up[t] = True
        if cd:
            dn_armed = False
            cross_dn[t] = True
        if zt < thr - 1.0:
            up_armed = True
        if zt > -(thr - 1.0):
            dn_armed = True
    al_z_up = cross_up & z_cal_ok
    al_z_dn = cross_dn & z_cal_ok
    al_abs = new_abs & ~ev_weak
    al_pin_o = new_pin & ~new_abs & ~ev_weak
    al_pwf = new_pwf & ~ev_weak
    al_res = (res_cont | res_held) & ~res_weak

    # ── pivots ──
    ph = _pivots(h, p.piv_l, p.piv_r, True)
    pl = _pivots(lo, p.piv_l, p.piv_r, False)
    R = p.piv_r
    cvd_at = np.full(n, np.nan)
    cvd_at[R:] = cvd_c[:-R] if R > 0 else cvd_c
    piv_top = np.zeros(n, dtype=bool)
    piv_bot = np.zeros(n, dtype=bool)
    for arr, out, is_high in ((ph, piv_top, True), (pl, piv_bot, False)):
        last_v, last_cvd, last_bar = np.nan, np.nan, None
        for t in np.flatnonzero(np.isfinite(arr)):
            pb = t - R
            cv = cvd_at[t]
            if p.piv and last_bar is not None and np.isfinite(cv) and np.isfinite(last_cvd) and sd_p[t] > 0:
                gap = pb - last_bar
                hq_span = lq_bar[t] < last_bar
                if is_high:
                    cond = arr[t] > last_v and cv <= last_cvd - p.piv_mag * sd_p[t]
                else:
                    cond = arr[t] < last_v and cv >= last_cvd + p.piv_mag * sd_p[t]
                if p.piv_min <= gap <= p.piv_max and hq_span and cond:
                    out[t] = True
            last_v, last_cvd, last_bar = arr[t], cv, pb

    i8 = lambda a: a.astype(np.int8)
    out = pd.DataFrame({
        'gap_bar': i8(gap_bar), 'r_bar': r_bar, 'delta': delta, 'tier': tier.astype(np.int8), 'no_obs': i8(no_obs),
        'hq_run': hq_run.astype(np.int32), 'lq_bar': lq_bar, 'r': r, 'd': d,
        'sr_p': sr_p, 'sd_p': sd_p, 'rho_p': rho_p, 'ur': ur, 'ud': ud,
        'hq_ok': i8(hq_ok), 'D': d_stat, 'rms_d': rms_d, 'n_cal_d': n_cal_d.astype(np.int32), 'Z': z,
        'z_cal_ok': i8(z_cal_ok), 'gate': i8(gate_on), 'p_leg': p_leg, 'f_leg': f_leg,
        'fE': f_e, 'pE': p_e, 'zF': zf, 'zP': zp, 'n_cal_e': n_cal_e.astype(np.int32), 'ev_weak': i8(ev_weak),
        'hollow': i8(hollow), 'hi_ke': hi_ke, 'lo_ke': lo_ke,
        'absorbed': i8(absorbed), 'pinned': i8(pinned), 'pwf': i8(pwf),
        'abs_new_cl': i8(abs_new_cl), 'pin_new_cl': i8(pin_new_cl), 'pwf_new_cl': i8(pwf_new_cl),
        'new_abs': i8(new_abs), 'new_pin': i8(new_pin), 'new_pwf': i8(new_pwf), 'pin_in_cl': i8(pin_in_cl),
        'ev_side': np.where(new_abs, abs_side, 0).astype(np.int8), 'pwf_side': np.where(new_pwf, pwf_side, 0).astype(np.int8),
        'pin_side': np.where(new_pin, pin_side, 0).astype(np.int8),
        'ev_h0': ev_h0, 'ev_l0': ev_l0, 'ev_outcome': ev_outcome, 'ev_res_bar': ev_res_bar,
        'pend_side': pend_side,
        'res_cont': i8(res_cont), 'res_held': i8(res_held), 'res_exp': i8(res_exp), 'res_side': res_side,
        'res_age': res_age, 'res_low': i8(res_low), 'res_weak': i8(res_weak), 'sup': i8(sup), 'sup_age': sup_age,
        'cross_up': i8(cross_up), 'cross_dn': i8(cross_dn), 'al_z_up': i8(al_z_up), 'al_z_dn': i8(al_z_dn),
        'al_abs': i8(al_abs), 'al_pin_o': i8(al_pin_o), 'al_pwf': i8(al_pwf), 'al_res': i8(al_res),
        'cvd_c': cvd_c, 'ph': ph, 'pl': pl, 'piv_top': i8(piv_top), 'piv_bot': i8(piv_bot),
    }, index=bars.index if isinstance(bars, pd.DataFrame) else None)
    out.attrs['params'] = p.to_dict()
    out.attrs['ke'] = ke
    out.attrs['life'] = life
    out.attrs['hq_need'] = hq_need
    out.attrs['rho_min_eff'] = rho_min_eff
    return out
