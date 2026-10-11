#!/usr/bin/env python3
"""Pre-registered event study of the signals of «Preço × CVD Normalizado [Order Flow]» on ES (5m primary, 15m secondary).

The plan below was fixed BEFORE any outcome was computed; the code implements it literally. Indicator inputs are the
defaults (engine.Params()), pivots switched on (they are off by default in the indicator, but studied here).

DATA / SETTINGS
  ES front month 1-minute, 2008-01 → 2026-09, clean sessions only; chart bars 5m and 15m built from 1m (bars.py).
  Delta = "TradingView Auto": candle rule on 1-minute intrabars, side carried over the whole stream (d_cr1m), summed per
  chart bar → quality tier 2. Indicator defaults: N=100, K=20, M=1000, clip 4, thr 2/3, ρmin 0.30, event window 15 min
  (ke = 3 on 5m, 1 on 15m), life 60 min, zF 2, pinned 3 / 0.5, pivots L5 R2 distance 5–60 magnitude 0.5.
  The per-bar indicator outputs come from the validated port (engine.py; feature files written by features.py).

SIGNALS (the 14 alertcondition sets of the indicator; the two Z alerts split by the 4 neutral states → 16 classes)
  Z ≥ +thr first cross (alZUp = crossUp with hysteresis and zCalOk), Z ≤ −thr first cross (alZDn), each split by the
  dominant leg at the signal bar: flow-led |F_K| > |P_K|, price-led otherwise;
  absorbed buy / sell (alAbsB / alAbsS); pinned buy / sell (alPinB / alPinS); price-without-flow up / down (alPwfU /
  alPwfD); resolutions continuation up / down, held up / down (alResCB/CS/HS/HB); pivot top / bottom (pivTop / pivBot).
  A signal is taken at the CLOSE of the bar where it is known (pivots: confirmation bar, R bars after the pivot;
  resolutions: the resolution bar); entry at the OPEN of the next bar.
  Direction s: absorbed / pinned → flow side; price-without-flow → price side; Z states → sign of the leading leg
  (flow-led: sign F_K; price-led: sign P_K); resolutions → direction of the resolving close; pivot top −1, bottom +1.
  A positive signed return = continuation of s.

HORIZONS 5, 15, 30, 60 minutes (5m chart: 1, 3, 6, 12 bars; 15m chart: 1, 2, 4 bars; 5 min n/a on 15m). A window
  [signal bar t, exit bar t+n] is excluded when it crosses a session break or a contract roll.

OUTCOMES signed forward log return from the entry open to the close of bar t+n, in σ-units:
  s · 10⁴·ln(C[t+n] / O[t+1]) / (σr · √n), σr = the indicator's lagged one-bar σ of r in bps at the signal bar (sr_p)
  — PRIMARY; also bps and ES points; hit rate; median; MFE and MAE over bars t+1..t+n (σ-units and points);
  unsigned |return| (volatility effect).

PRIMARY ENDPOINT signed σ-unit return at 30 min for each of the 16 classes on ES 5m, full sample; Benjamini–Hochberg
  FDR 5% across these 16 tests. Everything else is secondary / descriptive.

INFERENCE day-clustered standard errors (CR1, t with G − 1 df) and day-block bootstrap 95% percentile CIs (days
  resampled with replacement); n events and n days reported.

CONTROLS (does CVD add information beyond price?)
  (1) conditional twins: absorbed (flow shock, price not following) vs CONFIRMED flow shocks (|zF| ≥ 2 and
      s·zP ≥ |ρ|·|zF|, s = sign zF); price-without-flow vs price shocks WITH flow (|zP| ≥ 2 and sign(zP)·zF > 0).
      The twins are built exactly like the indicator's classes (gate open, clusters per side with a refractory period of
      ke observations, no event while the zF/zP calibration is weak). Difference in signed returns, clustered SE.
  (2) matched random controls: same session type (RTH 08:30–15:15 CT vs ETH), 30-minute time-of-day bucket (CT), year,
      σr tercile, sign and |·| tercile of the recent 15-minute price move pE; difference event − control.
  (3) unconditional baseline: all bars with the same filters.
GATE STUDY default gate (ρmin 0.30) vs gate OFF (quality only) vs ρmin 0.20 and 0.40; events and Z alerts re-derived.
COSTS ES round trip ≈ 1.3 ticks = 0.325 pt (1 tick slippage + ~$4 commission): net expectancy in points of the naive
  rule "trade s for h" and of the opposite rule, gross and net.
STABILITY 2008–2016 vs 2017–2026; per-year sign; RTH vs ETH; σr terciles.
Z CALIBRATION P(|Z| ≥ 2), P(|Z| ≥ 3), gate-open share, ρ distribution, per timeframe and half.

Implementation choices that the plan leaves open are listed in IMPLEMENTATION_NOTES and in results.md. Corrections made
after the external review (matched-control design, cost p-value columns) and the post-hoc sensitivities added then are
listed in DEVIATIONS and in CHANGELOG.md of the results folder.

Usage:
    python3 -I study_es.py                    # 5m (primary) and 15m (secondary)
    python3 -I study_es.py --tf 5 --boot 2000 # quicker
    python3 -I study_es.py --report-only      # rebuild results.md from the saved CSV files
Env (see studyenv.py; no path defaults, so nothing lands inside the git repository by accident):
    OUT_DIR   study folder (required unless both FEAT_DIR and RES_DIR are set)
    FEAT_DIR  feature files (default OUT_DIR/features; refused inside a git work tree). A missing ES feature file stops
              the run; --rebuild-features rebuilds it with features.py from DATA_DIR.
    RES_DIR   results (default OUT_DIR/results/es)
    DATA_DIR  clean 1-minute files. Read for the post-hoc entry-latency and settlement-minute analyses (skipped, with a
              note in the log and the report, when DATA_DIR is not set) and by --rebuild-features.
Licensed price data are never written: the outputs are aggregate tables only.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sys
import time
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402

import studyenv  # noqa: E402


def feat_dir() -> Path:
    """Feature folder: FEAT_DIR, else OUT_DIR/features; never inside a git work tree (licensed per-bar data)."""
    return studyenv.feat_dir()


def res_dir() -> Path:
    """Results folder: RES_DIR, else OUT_DIR/results/es (aggregate tables only)."""
    v = os.environ.get('RES_DIR', '').strip()
    return Path(v).expanduser().resolve() if v else studyenv.results_dir('es')


REBUILD_FEATURES = False         # set by --rebuild-features

# ───────────────────────────── pre-registered constants ─────────────────────────────
HORIZONS_MIN = (5, 15, 30, 60)
PRIMARY_H = 30
PRIMARY_TF = 5
FDR_Q = 0.05
COST_PT = 0.325                  # ES round trip: 1 tick slippage (0.25 pt) + ~$4 commission (0.08 pt) ≈ 1.3 ticks
POINT_VALUE = 50.0               # $ per ES point
SPLIT_YEAR = 2017                # halves: session years 2008–2016 | 2017–2026
RTH_CT = (8 * 60 + 30, 15 * 60 + 15)   # RTH 08:30–15:15 CT (bar open time)
TOD_BUCKET_MIN = 30
GATE_VARIANTS = {                 # name → engine.Params overrides
    'default (ρmin 0.30)': {},
    'gate off (quality only)': {'gate': False},
    'ρmin 0.20': {'rho_min': 0.20},
    'ρmin 0.40': {'rho_min': 0.40},
}
SEED = 20261011
# implementation constants (not outcome-dependent; see IMPLEMENTATION_NOTES)
MIN_CTRL = 5                     # minimum matched control bars for an event to enter the matched comparison
# post-hoc constants (added after the external review; see DEVIATIONS — none enters a pre-registered number)
COST_STRESS_PT = 0.575           # stress round trip: 2 ticks of slippage (0.50 pt) + $3.75 commission (0.075 pt)
SETTLE_CT_MIN = 14 * 60 + 59     # the 14:59 CT minute: CME equity-index daily settlement window / NYSE closing auction
OPEN_CLOSE_BARS = {5: ('08:30', '15:00', '15:05'), 15: ('14:45', '15:00')}   # most frequent absorption bars (CT)
ERAS = (('2008–2012', 2008, 2012), ('2013–2020', 2013, 2020), ('2021–2026', 2021, 2026))  # session-end layouts
LATENCY_MIN = (0, 1, 2)          # entry delay after the alert bar closes, in 1-minute intrabars
PK_BINS = 12                     # quantile bins of the K-bar price leg P_K for the P_K-matched control
SETTLE_CLASSES = ('abs_buy', 'abs_sell', 'pin_buy', 'pin_sell')
RES_CLASSES = ('res_cont_up', 'res_cont_dn', 'res_held_up', 'res_held_dn')

CLASSES = [
    # key, family, label, s
    ('z_up_price', 'Z alert', 'Z≥+2 · price-led (P>0): price up without proportional buy flow', +1),
    ('z_up_flow', 'Z alert', 'Z≥+2 · flow-led (F<0): sell flow without proportional fall', -1),
    ('z_dn_flow', 'Z alert', 'Z≤−2 · flow-led (F>0): buy flow without proportional rise', +1),
    ('z_dn_price', 'Z alert', 'Z≤−2 · price-led (P<0): price down without proportional sell flow', -1),
    ('abs_buy', 'absorbed', 'Buy flow absorbed', +1),
    ('abs_sell', 'absorbed', 'Sell flow absorbed', -1),
    ('pin_buy', 'pinned', 'Price pinned under extreme buying', +1),
    ('pin_sell', 'pinned', 'Price pinned under extreme selling', -1),
    ('pwf_up', 'price w/o flow', 'Price up without buy flow', +1),
    ('pwf_dn', 'price w/o flow', 'Price down without sell flow', -1),
    ('res_cont_up', 'resolution', 'Buys absorbed → continuation (up)', +1),
    ('res_cont_dn', 'resolution', 'Sells absorbed → continuation (down)', -1),
    ('res_held_up', 'resolution', 'Sells absorbed → held (up)', +1),
    ('res_held_dn', 'resolution', 'Buys absorbed → held (down)', -1),
    ('piv_top', 'pivot', 'Pivot top without flow confirmation', -1),
    ('piv_bot', 'pivot', 'Pivot bottom without flow confirmation', +1),
]
CLASS_KEYS = [c[0] for c in CLASSES]
CLASS_S = {c[0]: c[3] for c in CLASSES}
CLASS_LABEL = {c[0]: c[2] for c in CLASSES}
CLASS_FAMILY = {c[0]: c[1] for c in CLASSES}

IMPLEMENTATION_NOTES = [
    'Event classes are the indicator\'s own alertcondition sets (alZUp/alZDn split by the dominant leg, alAbsB/S, '
    'alPinB/S, alPwfU/D, alResCB/CS/HB/HS, pivTop/pivBot): events while the zF/zP calibration is weak (evWeak) and '
    'resolutions of weak events are not alerts and are not studied. On the ES files this removes no event (the '
    'calibration is complete long before the first event).',
    'Horizons are counted in chart bars, as pre-registered. Windows are dropped only when they cross a session break '
    '(session_date changes) or a contract change. Windows that span an intra-session trading halt (mainly the '
    '15:15–15:30 CT halt that existed until 2021) are kept; their share is reported (column halt_share).',
    'σ-unit normalisation uses sr_p at the signal bar (σr of the N previous observations, the σ the indicator used on '
    'that bar) and √n with n the horizon in bars. Bars with sr_p ≤ 0 (e.g. the 2020-03-09 limit-locked market) are '
    'excluded.',
    'Hit rate = share of signed returns > 0 (the pre-registered definition); the share of exact zeros (tick grid) is '
    'reported separately. Because exact zeros count as misses, a random-direction trade scores below 50% on it. hit_nz '
    '(added after the review) = share of positive returns among the non-zero ones, whose no-information value is 50%.',
    'Clustered SE: CR1 with G/(G−1) small-sample factor, clusters = trading days (session_date), two-sided p from a t '
    'distribution with G − 1 df. Bootstrap: days with at least one event resampled with replacement, percentile '
    'interval; 10,000 replicates for the primary endpoint, 2,000 elsewhere; seeds derived from the cell name.',
    'Twins: CONFIRMED and PRICE-WITH-FLOW events are built with the indicator\'s machinery (gate open, z defined, '
    'cluster start per side with a refractory period of ke observations, not evWeak), the same as the absorbed and '
    'price-without-flow classes they are compared with. Sides pooled (main row) and per side. The comparison is a '
    'two-group regression with a dummy, CR1 clustered by day.',
    'Matched controls (as corrected after the review; see section 10): a cell is (year of the trading day, RTH '
    '08:30–15:15 CT vs ETH, 30-minute CT clock bucket, σr tercile WITHIN THE YEAR, sign of pE, tercile of |pE|). '
    'Candidate control bars: hqOk, gate open with the default ρmin, sr_p > 0, pE defined, valid window at the horizon. '
    'The |pE| terciles are computed over all candidates of the full sample (pE is already in σ-units); the σr terciles '
    'within each year (σr is in bps, and its level moves by a factor of several across years). Every event of the same '
    'class (for a twin set: of the same set) is removed from the cells, not only the event itself. Each event\'s control '
    'is the MEAN over the remaining bars of its cell (the expectation of a random matched draw), signed with the '
    f'event\'s s. Events whose cell has fewer than {MIN_CTRL} control bars are dropped from this comparison (count '
    'reported). The SE includes the sampling error of the control means: each control bar contributes its influence '
    '(weight of its cell in the event average / bars in the cell × its deviation from the cell mean) to its own day, and '
    'the event and control contributions are clustered together by day (CR1). se_ctrl_fixed is the SE with the control '
    'means treated as known (the original computation). The bootstrap resamples all trading days, recomputing the event '
    'mean and moving the control means through their per-day influence.',
    'Unconditional baseline: all candidate control bars (same filters), long direction (s = +1); the short-direction '
    'mean is its negative.',
    'Gate study: the variants are produced by re-running the validated engine on the same bars with the gate input '
    'changed (Params.gate / rho_min). This is the exact re-derivation from the zF/zP/ρ/Z series, because Z, zF, zP and '
    'their calibration do not depend on the gate; only the classes, clusters, resolutions and Z alerts do. Pivots do '
    'not depend on the gate. "Added" events = variant events of a class on bars where the default has no event of that '
    'class; "removed" = the converse.',
    'Costs: 0.325 pt per round trip subtracted from every event (naive rule, overlapping positions allowed); the '
    'opposite rule pays the same cost. The cost is also expressed in σ-units of each event (0.325 / (O_entry·σr·√n·1e−4)).',
    'Multiple testing outside the primary family: Benjamini–Hochberg q-values are computed within each secondary table '
    '(its own family) and reported only as a flag; nothing outside the primary family is confirmatory.',
]


# ───────────────────────────── data ─────────────────────────────

FEAT_COLS = ['t', 'session_date', 'o', 'h', 'l', 'c', 'v', 'contract', 'session_first', 'delta_src', 'rth']
SIG_COLS = ['d', 'sr_p', 'rho_p', 'hq_ok', 'tier', 'Z', 'z_cal_ok', 'gate', 'p_leg', 'f_leg', 'pE', 'zF', 'zP',
            'ev_weak', 'al_z_up', 'al_z_dn', 'al_abs', 'ev_side', 'new_pin', 'pin_side', 'al_pwf', 'pwf_side', 'al_res',
            'res_cont', 'res_held', 'res_side', 'res_weak', 'res_age', 'piv_top', 'piv_bot']


def feature_file(tf: int) -> Path:
    return feat_dir() / f'es_{tf}m_cr1m.parquet'


def load_features(tf: int) -> pd.DataFrame:
    """ES feature file of the validated port. A missing file stops the run unless --rebuild-features was given (it is
    then rebuilt from DATA_DIR with features.py, into the feature folder, which is refused inside a git work tree)."""
    fn = feature_file(tf)
    if not fn.exists():
        if not REBUILD_FEATURES:
            raise SystemExit(f'{fn} not found. Build it with features.py (env DATA_DIR, OUT_DIR/FEAT_DIR outside any git '
                             'work tree) or pass --rebuild-features.')
        import features as FT
        FT.build_dataset(f'es_{tf}m_cr1m', E.Params())
    return pd.read_parquet(fn, columns=FEAT_COLS + SIG_COLS)


def run_variant(F: pd.DataFrame, tf: int, **overrides) -> tuple[pd.DataFrame, dict]:
    """Re-run the engine on the bars of F with the given Params overrides; returns SIG_COLS and the windows."""
    p = E.Params(**{**E.Params().to_dict(), 'tf_sec': tf * 60, **overrides})
    out = E.run_engine(pd.DataFrame({
        'open': F.o.to_numpy(float), 'high': F.h.to_numpy(float), 'low': F.l.to_numpy(float),
        'close': F.c.to_numpy(float), 'volume': F.v.to_numpy(float), 'delta': F.delta_src.to_numpy(float),
        'session_first': F.session_first.to_numpy(), 'tier': 2}), p)
    meta = {'ke': out.attrs['ke'], 'life': out.attrs['life'], 'hq_need': out.attrs['hq_need'],
            'rho_min_eff': out.attrs['rho_min_eff'], 'params': p.to_dict()}
    return out[SIG_COLS].reset_index(drop=True), meta


def check_default_reproduces(F: pd.DataFrame, S: pd.DataFrame) -> dict:
    """The default re-run must reproduce the stored feature columns exactly (sanity check of the gate-study path)."""
    bad = {}
    for k in SIG_COLS:
        a, b = S[k].to_numpy(), F[k].to_numpy()
        same = np.array_equal(a, b, equal_nan=True) if a.dtype.kind == 'f' else np.array_equal(a, b)
        if not same:
            bad[k] = int((~np.isclose(a.astype(float), b.astype(float), equal_nan=True)).sum())
    if bad:
        raise AssertionError(f'default engine re-run differs from the feature file: {bad}')
    return {'checked_columns': len(SIG_COLS), 'mismatches': 0}


class Bars:
    """Per-bar arrays shared by all analyses of one timeframe."""

    def __init__(self, F: pd.DataFrame, tf: int):
        self.tf = tf
        self.n = len(F)
        self.o = F.o.to_numpy(float)
        self.h = F.h.to_numpy(float)
        self.l = F.l.to_numpy(float)
        self.c = F.c.to_numpy(float)
        self.sess, self.sess_labels = pd.factorize(F.session_date, sort=True)
        self.con, _ = pd.factorize(F.contract, sort=True)
        self.tmin = F.t.dt.as_unit('ns').array.asi8 // 60_000_000_000
        ct = F.t.dt.tz_convert('America/Chicago')
        mins = (ct.dt.hour * 60 + ct.dt.minute).to_numpy()
        self.mins = mins                                    # bar open time, minutes after 00:00 CT
        self.rth = (mins >= RTH_CT[0]) & (mins < RTH_CT[1])
        self.bucket = mins // TOD_BUCKET_MIN
        self.year = F.session_date.dt.year.to_numpy()
        self.h2 = self.year >= SPLIT_YEAR


# ───────────────────────────── outcomes ─────────────────────────────

class Window:
    """Raw (long-direction) forward outcomes for every bar t at a horizon of n bars: entry at O[t+1], exit at C[t+n]."""

    def __init__(self, B: Bars, sr_p: np.ndarray, n: int):
        N = B.n
        self.n = n
        self.valid = np.zeros(N, bool)
        nan = lambda: np.full(N, np.nan)   # noqa: E731
        self.entry, self.exit, self.hmax, self.lmin = nan(), nan(), nan(), nan()
        self.halt = np.zeros(N, bool)
        if N > n:
            t = np.arange(N - n)
            ok = (B.sess[t + n] == B.sess[t]) & (B.con[t + n] == B.con[t])
            hm = B.h[t + 1].copy()
            lm = B.l[t + 1].copy()
            for j in range(2, n + 1):
                np.maximum(hm, B.h[t + j], out=hm)
                np.minimum(lm, B.l[t + j], out=lm)
            self.valid[t] = ok
            self.entry[t] = B.o[t + 1]
            self.exit[t] = B.c[t + n]
            self.hmax[t] = hm
            self.lmin[t] = lm
            self.halt[t] = ok & ((B.tmin[t + n] - B.tmin[t + 1]) > (n - 1) * B.tf)
        with np.errstate(invalid='ignore', divide='ignore'):
            self.valid &= np.isfinite(sr_p) & (sr_p > 0)
            self.scale = np.where(self.valid, sr_p * math.sqrt(n), np.nan)        # bps per σ-unit
            self.r_bps = np.where(self.valid, 1e4 * np.log(self.exit / self.entry), np.nan)
            self.r_sig = self.r_bps / self.scale
            self.pts = np.where(self.valid, self.exit - self.entry, np.nan)
            self.up_bps = np.where(self.valid, 1e4 * np.log(self.hmax / self.entry), np.nan)
            self.dn_bps = np.where(self.valid, 1e4 * np.log(self.entry / self.lmin), np.nan)
            self.up_pts = np.where(self.valid, self.hmax - self.entry, np.nan)
            self.dn_pts = np.where(self.valid, self.entry - self.lmin, np.nan)
            self.cost_sig = np.where(self.valid, COST_PT / (self.entry * self.scale * 1e-4), np.nan)

    def signed(self, idx: np.ndarray, s) -> dict:
        """Signed outcomes for events at bars idx with direction s (scalar or array); invalid windows removed."""
        idx = np.asarray(idx, np.int64)
        s = np.broadcast_to(np.asarray(s, float), idx.shape)
        keep = self.valid[idx]
        idx, s = idx[keep], s[keep]
        up = s > 0
        sc = self.scale[idx]
        mfe_bps = np.where(up, self.up_bps[idx], self.dn_bps[idx])
        mae_bps = np.where(up, self.dn_bps[idx], self.up_bps[idx])
        return {
            'idx': idx, 's': s,
            'y': s * self.r_sig[idx], 'bps': s * self.r_bps[idx], 'pts': s * self.pts[idx],
            'mfe_sig': mfe_bps / sc, 'mae_sig': mae_bps / sc,
            'mfe_pts': np.where(up, self.up_pts[idx], self.dn_pts[idx]),
            'mae_pts': np.where(up, self.dn_pts[idx], self.up_pts[idx]),
            'raw_sig': self.r_sig[idx], 'cost_sig': self.cost_sig[idx], 'halt': self.halt[idx],
        }


# ───────────────────────────── statistics ─────────────────────────────

def _rng(*key) -> np.random.Generator:
    return np.random.default_rng(SEED + zlib.crc32('|'.join(map(str, key)).encode()))


def cl_mean(y, g) -> dict:
    """Mean with a day-clustered (CR1) standard error; two-sided p from t(G − 1)."""
    y = np.asarray(y, float)
    n = len(y)
    if n == 0:
        return {'n': 0, 'days': 0, 'mean': np.nan, 'se': np.nan, 't': np.nan, 'p': np.nan}
    codes, inv = np.unique(g, return_inverse=True)
    G = len(codes)
    m = float(y.mean())
    if G < 2:
        return {'n': n, 'days': G, 'mean': m, 'se': np.nan, 't': np.nan, 'p': np.nan}
    sg = np.bincount(inv, weights=y - m, minlength=G)
    se = math.sqrt(G / (G - 1) * float(np.sum(sg * sg))) / n
    t = m / se if se > 0 else np.nan
    p = float(2 * stats.t.sf(abs(t), G - 1)) if np.isfinite(t) else np.nan
    return {'n': n, 'days': G, 'mean': m, 'se': se, 't': t, 'p': p}


def boot_ci(y, g, B, key, chunk=500) -> tuple[float, float]:
    """Day-block bootstrap 95% percentile CI of the mean (days with events resampled with replacement)."""
    y = np.asarray(y, float)
    if len(y) < 2 or B <= 0:
        return (np.nan, np.nan)
    codes, inv = np.unique(g, return_inverse=True)
    G = len(codes)
    if G < 2:
        return (np.nan, np.nan)
    S = np.bincount(inv, weights=y, minlength=G)
    C = np.bincount(inv, minlength=G).astype(float)
    rng = _rng('boot', key)
    res = []
    for b0 in range(0, B, chunk):
        idx = rng.integers(0, G, size=(min(chunk, B - b0), G), dtype=np.int32)
        res.append(S[idx].sum(1) / C[idx].sum(1))
    lo, hi = np.percentile(np.concatenate(res), [2.5, 97.5])
    return float(lo), float(hi)


def boot_diff_ci(y1, g1, y0, g0, B, key, chunk=500) -> tuple[float, float]:
    """Day-block bootstrap CI of mean(y1) − mean(y0): the days of both groups are resampled together."""
    if len(y1) < 2 or len(y0) < 2 or B <= 0:
        return (np.nan, np.nan)
    codes, inv = np.unique(np.r_[g1, g0], return_inverse=True)
    G = len(codes)
    i1, i0 = inv[:len(g1)], inv[len(g1):]
    S1 = np.bincount(i1, weights=np.asarray(y1, float), minlength=G)
    C1 = np.bincount(i1, minlength=G).astype(float)
    S0 = np.bincount(i0, weights=np.asarray(y0, float), minlength=G)
    C0 = np.bincount(i0, minlength=G).astype(float)
    rng = _rng('bootdiff', key)
    res = []
    for b0 in range(0, B, chunk):
        idx = rng.integers(0, G, size=(min(chunk, B - b0), G), dtype=np.int32)
        with np.errstate(invalid='ignore', divide='ignore'):
            res.append(S1[idx].sum(1) / C1[idx].sum(1) - S0[idx].sum(1) / C0[idx].sum(1))
    r = np.concatenate(res)
    r = r[np.isfinite(r)]
    lo, hi = np.percentile(r, [2.5, 97.5])
    return float(lo), float(hi)


def cl_diff(y1, g1, y0, g0) -> dict:
    """mean(y1) − mean(y0) by OLS on [1, D] with CR1 standard errors clustered by day (days may hold both groups)."""
    y1 = np.asarray(y1, float)
    y0 = np.asarray(y0, float)
    if len(y1) < 2 or len(y0) < 2:
        return {'diff': np.nan, 'se': np.nan, 't': np.nan, 'p': np.nan}
    y = np.r_[y1, y0]
    D = np.r_[np.ones(len(y1)), np.zeros(len(y0))]
    X = np.column_stack([np.ones(len(y)), D])
    codes, inv = np.unique(np.r_[g1, g0], return_inverse=True)
    G = len(codes)
    n, k = X.shape
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ (X.T @ y)
    e = y - X @ beta
    U = np.column_stack([np.bincount(inv, weights=X[:, j] * e, minlength=G) for j in range(k)])
    V = G / (G - 1) * (n - 1) / (n - k) * XtX_inv @ (U.T @ U) @ XtX_inv
    se = math.sqrt(V[1, 1])
    t = beta[1] / se if se > 0 else np.nan
    return {'diff': float(beta[1]), 'se': se, 't': t, 'p': float(2 * stats.t.sf(abs(t), G - 1))}


def bh(p, q=FDR_Q) -> tuple[np.ndarray, np.ndarray]:
    """Benjamini–Hochberg q-values and rejections at level q (NaN p-values count as 1)."""
    p = np.asarray(p, float)
    pp = np.where(np.isfinite(p), p, 1.0)
    m = len(pp)
    if m == 0:
        return pp, pp.astype(bool)
    order = np.argsort(pp)
    ranked = pp[order] * m / np.arange(1, m + 1)
    qv = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(qv, 1.0)
    return out, out <= q


# ───────────────────────────── signals ─────────────────────────────

def class_masks(S: pd.DataFrame) -> tuple[dict, dict]:
    """Boolean mask per class (the indicator's alertcondition sets) and consistency counts."""
    g = lambda k: S[k].to_numpy()   # noqa: E731
    flow_led = np.abs(g('f_leg')) > np.abs(g('p_leg'))
    up, dn = g('al_z_up') == 1, g('al_z_dn') == 1
    al_abs, ev_side = g('al_abs') == 1, g('ev_side')
    pin = (g('new_pin') == 1) & (g('ev_weak') == 0)
    pin_side = g('pin_side')
    al_pwf, pwf_side = g('al_pwf') == 1, g('pwf_side')
    al_res, rc, rh, rs = g('al_res') == 1, g('res_cont') == 1, g('res_held') == 1, g('res_side')
    m = {
        'z_up_price': up & ~flow_led, 'z_up_flow': up & flow_led,
        'z_dn_flow': dn & flow_led, 'z_dn_price': dn & ~flow_led,
        'abs_buy': al_abs & (ev_side > 0), 'abs_sell': al_abs & (ev_side < 0),
        'pin_buy': pin & (pin_side > 0), 'pin_sell': pin & (pin_side < 0),
        'pwf_up': al_pwf & (pwf_side > 0), 'pwf_dn': al_pwf & (pwf_side < 0),
        'res_cont_up': al_res & rc & (rs > 0), 'res_cont_dn': al_res & rc & (rs < 0),
        'res_held_up': al_res & rh & (rs < 0), 'res_held_dn': al_res & rh & (rs > 0),
        'piv_top': g('piv_top') == 1, 'piv_bot': g('piv_bot') == 1,
    }
    f, p = g('f_leg'), g('p_leg')
    checks = {   # implied signs of the neutral states (METODOLOGIA 6.6): all must be 0
        'z_up_flow_with_F>=0': int((m['z_up_flow'] & (f >= 0)).sum()),
        'z_up_price_with_P<=0': int((m['z_up_price'] & (p <= 0)).sum()),
        'z_dn_flow_with_F<=0': int((m['z_dn_flow'] & (f <= 0)).sum()),
        'z_dn_price_with_P>=0': int((m['z_dn_price'] & (p >= 0)).sum()),
        'events_dropped_as_evWeak': int((((g('new_pin') == 1) | (S.al_abs.to_numpy() == 1)) & (g('ev_weak') == 1)).sum()),
        'resolutions_dropped_as_weak': int(((rc | rh) & (g('res_weak') == 1)).sum()),
    }
    return m, checks


def _cluster_starts(flag, side, obs_idx, ke):
    """First bar of each cluster of `flag` per side, refractory period of ke observations (engine.clusters)."""
    new = np.zeros(len(flag), bool)
    last_obs, last_side = None, 0
    for t in np.flatnonzero(flag):
        s = int(side[t])
        oi = int(obs_idx[t])
        if not (last_side == s and last_obs is not None and oi - last_obs <= ke):
            new[t] = True
        last_obs, last_side = oi, s
    return new


def twin_events(S: pd.DataFrame, ke: int, p: E.Params = E.Params()) -> dict:
    """CONFIRMED flow shocks and PRICE shocks WITH flow, built like the indicator's classes.

    Returns {name: (mask, side)} for 'absorbed', 'confirmed', 'pwf', 'price_with_flow'."""
    zf, zp = S.zF.to_numpy(), S.zP.to_numpy()
    rho = S.rho_p.to_numpy()
    rho_pz = np.where(np.isfinite(rho), rho, 0.0)
    z_ok = np.isfinite(zf) & np.isfinite(zp)
    sF = np.sign(np.where(np.isfinite(zf), zf, 0.0))
    sP = np.sign(np.where(np.isfinite(zp), zp, 0.0))
    gate = S.gate.to_numpy() == 1
    ok_ev = (S.tier.to_numpy() >= 2) & (S.ev_weak.to_numpy() == 0)
    obs_idx = np.cumsum(np.isfinite(S.d.to_numpy()))
    with np.errstate(invalid='ignore'):
        conf = gate & z_ok & (np.abs(zf) >= p.zf) & (sF * zp >= np.abs(rho_pz) * np.abs(zf))
        pwith = gate & z_ok & (np.abs(zp) >= p.zf) & (sP * zf > 0)
    side_f = np.where(sF > 0, 1, -1)
    side_p = np.where(sP > 0, 1, -1)
    conf_new = _cluster_starts(conf, np.where(conf, side_f, 0), obs_idx, ke) & ok_ev
    pwith_new = _cluster_starts(pwith, np.where(pwith, side_p, 0), obs_idx, ke) & ok_ev
    absm = S.al_abs.to_numpy() == 1
    pwfm = S.al_pwf.to_numpy() == 1
    return {
        'absorbed': (absm, S.ev_side.to_numpy().astype(float)),
        'confirmed': (conf_new, side_f.astype(float)),
        'pwf': (pwfm, S.pwf_side.to_numpy().astype(float)),
        'price_with_flow': (pwith_new, side_p.astype(float)),
    }


# ───────────────────────────── analyses ─────────────────────────────

def horizons_bars(tf: int) -> list[tuple[int, int]]:
    """(minutes, bars) for the pre-registered horizons available on this timeframe."""
    return [(hm, hm // tf) for hm in HORIZONS_MIN if hm % tf == 0 and hm >= tf]


def hit_nonzero(y) -> float:
    """Share of positive returns among the non-zero ones (exact zeros, frequent on the tick grid, left out)."""
    y = np.asarray(y, float)
    nz = y != 0
    return float(np.mean(y[nz] > 0)) if nz.any() else np.nan


def describe(o: dict, sess: np.ndarray, B: int, key) -> dict:
    """All per-cell outcome statistics of a set of signed events."""
    g = sess[o['idx']]
    y = o['y']
    r = cl_mean(y, g)
    lo, hi = boot_ci(y, g, B, key) if B else (np.nan, np.nan)
    n = len(y)
    f = lambda a: float(np.mean(a)) if n else np.nan   # noqa: E731
    return {
        **r, 'boot_lo': lo, 'boot_hi': hi,
        'hit': f(y > 0), 'loss': f(y < 0), 'zero_share': f(y == 0), 'hit_nz': hit_nonzero(y),
        'median': float(np.median(y)) if n else np.nan,
        'mean_bps': f(o['bps']), 'mean_pts': f(o['pts']),
        'mfe_sig': f(o['mfe_sig']), 'mae_sig': f(o['mae_sig']), 'mfe_pts': f(o['mfe_pts']), 'mae_pts': f(o['mae_pts']),
        'abs_sig': f(np.abs(y)), 'halt_share': f(o['halt']),
    }


def class_table(tf, masks, wins, Bars_, B_primary, B_other, tag) -> pd.DataFrame:
    rows = []
    for k in CLASS_KEYS:
        idx = np.flatnonzero(masks[k])
        for hm, n in horizons_bars(tf):
            o = wins[n].signed(idx, CLASS_S[k])
            B = B_primary if (hm == PRIMARY_H) else B_other
            d = describe(o, Bars_.sess, B, (tag, tf, k, hm))
            rows.append({'tf': tf, 'class': k, 'family': CLASS_FAMILY[k], 's': CLASS_S[k], 'h_min': hm, 'h_bars': n,
                         'n_signals': len(idx), **d})
    T = pd.DataFrame(rows)
    T['mde80'] = 2.80 * T.se            # post hoc: minimum detectable effect, two-sided 5%, 80% power
    # BH within the table (secondary family) and within the 30-min slice (primary family on 5m)
    T['q_table'], T['fdr_table'] = bh(T.p.to_numpy())
    pr = T.h_min == PRIMARY_H
    q, rej = bh(T.loc[pr, 'p'].to_numpy())
    T.loc[pr, 'q_30m'] = q
    T.loc[pr, 'fdr_30m'] = rej
    return T


def candidate_controls(S: pd.DataFrame, Bars_: Bars, tf: int) -> tuple[dict, np.ndarray, dict]:
    """Candidate control bars and their matching-cell keys (−1 = not a candidate).

    Candidates: hqOk, gate open (default ρmin), sr_p > 0, pE defined. Returns {design: key} with
      'bucket' (the pre-registered design): year × RTH/ETH × 30-min CT bucket × σr tercile WITHIN THE YEAR × sign(pE)
               × |pE| tercile (|pE| terciles over all candidates: pE is already in σ-units);
      'slot'   (post hoc): the same with the exact chart-bar slot of the day instead of the 30-min bucket;
      'pk'     (post hoc): year × RTH/ETH × 30-min CT bucket × 12 quantile bins of the K-bar price leg P_K (the leg that
               defines the Z classes);
    plus the FULL-SAMPLE σr tercile of every bar (the 'volatility terciles' of the stability split)."""
    sr = S.sr_p.to_numpy()
    pe = S.pE.to_numpy()
    pk = S.p_leg.to_numpy()
    with np.errstate(invalid='ignore'):
        base = (S.hq_ok.to_numpy() == 1) & (S.gate.to_numpy() == 1) & np.isfinite(sr) & (sr > 0) & np.isfinite(pe)
    year = Bars_.year.astype(np.int64)
    q_sr = np.quantile(sr[base], [1 / 3, 2 / 3])
    sr_t = np.digitize(sr, q_sr)                                   # full-sample terciles (stability split)
    sr_ty = np.full(Bars_.n, 1, np.int64)                          # terciles within the year (matching)
    cuts_y = {}
    for yv in np.unique(year[base]):
        m = base & (year == yv)
        q = np.quantile(sr[m], [1 / 3, 2 / 3])
        cuts_y[int(yv)] = [float(q[0]), float(q[1])]
        yy = year == yv
        sr_ty[yy] = np.digitize(sr[yy], q)
    q_pe = np.quantile(np.abs(pe[base]), [1 / 3, 2 / 3])
    pe_t = np.digitize(np.abs(pe), q_pe)
    pe_s = np.sign(np.where(np.isfinite(pe), pe, 0.0)).astype(np.int64) + 1
    rth = Bars_.rth.astype(np.int64)
    slot = (Bars_.mins // tf).astype(np.int64)                     # exact chart-bar slot of the day (CT)
    tail = (sr_ty * 3 + pe_s) * 3 + pe_t
    keys = {
        'bucket': np.where(base, ((year * 2 + rth) * 48 + Bars_.bucket) * 27 + tail, -1),
        'slot': np.where(base, ((year * 2 + rth) * 1440 + slot) * 27 + tail, -1),
    }
    okp = base & np.isfinite(pk)
    q_pk = np.quantile(pk[okp], np.linspace(0, 1, PK_BINS + 1)[1:-1])
    pkb = np.digitize(pk, q_pk)
    keys['pk'] = np.where(okp, ((year * 2 + rth) * 48 + Bars_.bucket) * PK_BINS + pkb, -1)
    info = {'sr_terciles_bps_full_sample': q_sr.tolist(), 'sr_terciles_bps_by_year': cuts_y,
            'abs_pE_terciles': q_pe.tolist(), 'P_K_bin_edges': q_pk.tolist(), 'candidates': int(base.sum())}
    return keys, sr_t, info


class CellPool:
    """Candidate control bars of one horizon (valid outcome window), grouped by matching cell.

    For an event set, match() removes every bar of that set (all events of the same class, not only the event itself)
    from the cells, takes each event's control as the mean over the remaining bars of its cell (the expectation of a
    random matched draw), and returns the per-day influence of the control means on the event average: the control
    means are estimates, and their sampling error (clustered by the day of each control bar) enters the SE."""

    def __init__(self, key: np.ndarray, w: 'Window', Bars_: Bars):
        self.key = key
        self.bar = np.flatnonzero((key >= 0) & w.valid)
        self.uk, self.inv = np.unique(key[self.bar], return_inverse=True)
        self.x = w.r_sig[self.bar]
        self.ax = np.abs(self.x)
        self.day = Bars_.sess[self.bar]
        self.ndays = len(Bars_.sess_labels)
        nc = len(self.uk)
        self.S = np.bincount(self.inv, weights=self.x, minlength=nc)
        self.Sa = np.bincount(self.inv, weights=self.ax, minlength=nc)
        self.C = np.bincount(self.inv, minlength=nc).astype(float)

    def match(self, o: dict, own: np.ndarray, sess: np.ndarray) -> dict:
        nc = len(self.uk)
        own_in = own[self.bar]
        oi = self.inv[own_in]
        S = self.S - np.bincount(oi, weights=self.x[own_in], minlength=nc)
        Sa = self.Sa - np.bincount(oi, weights=self.ax[own_in], minlength=nc)
        C = self.C - np.bincount(oi, minlength=nc)
        ei = o['idx']
        ek = self.key[ei]
        if nc:
            pos = np.clip(np.searchsorted(self.uk, ek), 0, nc - 1)
            found = (ek >= 0) & (self.uk[pos] == ek)
        else:
            pos, found = np.zeros(len(ei), np.int64), np.zeros(len(ei), bool)
        cnt = np.where(found, C[pos], 0.0)
        ok = found & (cnt >= MIN_CTRL)
        pk = pos[ok]
        n = int(ok.sum())
        with np.errstate(invalid='ignore', divide='ignore'):
            cbar = np.where(C > 0, S / C, np.nan)
            cabar = np.where(C > 0, Sa / C, np.nan)
        s, y = o['s'][ok], o['y'][ok]
        r = {'ok': ok, 'n': n, 'g': sess[ei[ok]], 'y': y, 's': s, 'cnt': cnt[ok], 'c': s * cbar[pk], 'ca': cabar[pk],
             'own_removed': int(own_in.sum())}
        r['dd'] = y - r['c']
        r['da'] = np.abs(y) - r['ca']
        V = np.zeros(self.ndays)
        Va = np.zeros(self.ndays)
        if n:
            ws = np.bincount(pk, weights=s, minlength=nc) / n       # weight of each cell's control mean in the average
            wa = np.bincount(pk, minlength=nc) / n
            ctl = ~own_in
            cj = self.inv[ctl]
            used = wa[cj] > 0
            cj = cj[used]
            dj = self.day[ctl][used]
            V = np.bincount(dj, weights=ws[cj] / C[cj] * (self.x[ctl][used] - cbar[cj]), minlength=self.ndays)
            Va = np.bincount(dj, weights=wa[cj] / C[cj] * (self.ax[ctl][used] - cabar[cj]), minlength=self.ndays)
        r['V'], r['Va'] = V, Va
        return r


def lin_mean(v, g, V, ndays) -> dict:
    """Mean of matched per-event values (event − control) with a day-clustered SE (CR1) that includes the sampling error
    of the control means: day contribution U_g = Σ_{events of g} (v_i − v̄)/n − V_g, V_g = influence of the control
    bars of day g. se_ctrl_fixed = the same without V (control means treated as known). p from t(G − 1), G = event days."""
    v = np.asarray(v, float)
    n = len(v)
    if n < 2:
        return {'n': n, 'days': int(len(np.unique(g))), 'mean': float(v.mean()) if n else np.nan, 'se': np.nan,
                'se_ctrl_fixed': np.nan, 't': np.nan, 'p': np.nan}
    m = float(v.mean())
    G = len(np.unique(g))
    Ue = np.bincount(g, weights=(v - m) / n, minlength=ndays)
    f = G / (G - 1) if G > 1 else np.nan
    se_e = math.sqrt(f * float(np.sum(Ue * Ue)))
    U = Ue - V
    se = math.sqrt(f * float(np.sum(U * U)))
    t = m / se if se > 0 else np.nan
    p = float(2 * stats.t.sf(abs(t), G - 1)) if np.isfinite(t) else np.nan
    return {'n': n, 'days': G, 'mean': m, 'se': se, 'se_ctrl_fixed': se_e, 't': t, 'p': p}


def lin_diff(va, ga, Va, vb, gb, Vb, ndays) -> dict:
    """Difference of two matched means (set a − set b) with the same joint day-clustered SE (events and control bars of
    both sets; days may hold both)."""
    va, vb = np.asarray(va, float), np.asarray(vb, float)
    if len(va) < 2 or len(vb) < 2:
        return {'diff': np.nan, 'se': np.nan, 'p': np.nan}
    ma, mb = float(va.mean()), float(vb.mean())
    U = (np.bincount(ga, weights=(va - ma) / len(va), minlength=ndays) - Va
         - np.bincount(gb, weights=(vb - mb) / len(vb), minlength=ndays) + Vb)
    G = len(np.unique(np.r_[ga, gb]))
    se = math.sqrt(G / (G - 1) * float(np.sum(U * U)))
    t = (ma - mb) / se if se > 0 else np.nan
    return {'diff': ma - mb, 'se': se, 'p': float(2 * stats.t.sf(abs(t), G - 1)) if np.isfinite(t) else np.nan}


def lin_boot(v, g, V, ndays, B, key, chunk=500) -> tuple[float, float]:
    """Day-block bootstrap 95% percentile CI of a matched mean: all trading days resampled with replacement; the event
    part is recomputed as a ratio, the control-mean part through its per-day influence V with the same day weights."""
    v = np.asarray(v, float)
    if len(v) < 2 or B <= 0:
        return (np.nan, np.nan)
    E_ = np.bincount(g, weights=v, minlength=ndays)
    N_ = np.bincount(g, minlength=ndays).astype(float)
    rng = _rng('boot', key)
    res = []
    for b0 in range(0, B, chunk):
        idx = rng.integers(0, ndays, size=(min(chunk, B - b0), ndays), dtype=np.int32)
        with np.errstate(invalid='ignore', divide='ignore'):
            res.append(E_[idx].sum(1) / N_[idx].sum(1) - V[idx].sum(1))
    r = np.concatenate(res)
    r = r[np.isfinite(r)]
    lo, hi = np.percentile(r, [2.5, 97.5])
    return float(lo), float(hi)


def matched_row(o: dict, P: CellPool, own: np.ndarray, sess: np.ndarray, B: int, bkey) -> dict:
    """One row of a matched-control table for the signed events o."""
    r = P.match(o, own, sess)
    d = lin_mean(r['dd'], r['g'], r['V'], P.ndays)
    a = lin_mean(r['da'], r['g'], r['Va'], P.ndays)
    lo, hi = lin_boot(r['dd'], r['g'], r['V'], P.ndays, B, bkey) if B else (np.nan, np.nan)
    ne = len(o['idx'])
    f = lambda x: float(np.mean(x)) if r['n'] else np.nan   # noqa: E731
    return {'n_events': ne, 'n_matched': r['n'], 'dropped_no_controls': ne - r['n'], 'own_removed': r['own_removed'],
            'days': d['days'], 'median_controls': float(np.median(r['cnt'])) if r['n'] else np.nan,
            'event_mean': f(r['y']), 'control_mean': f(r['c']), 'diff': d['mean'], 'se': d['se'],
            'se_ctrl_fixed': d['se_ctrl_fixed'], 'p': d['p'], 'boot_lo': lo, 'boot_hi': hi,
            'event_abs': f(np.abs(r['y'])), 'control_abs': f(r['ca']), 'abs_diff': a['mean'], 'abs_diff_se': a['se'],
            'abs_diff_p': a['p']}


def matched_table(tf, sets, wins, pools, Bars_, B, tag, horizons=None, design='bucket') -> pd.DataFrame:
    """Event − matched-control differences for each event set {name: (idx, s, own mask)}."""
    rows = []
    for hm, n in horizons_bars(tf):
        if horizons is not None and hm not in horizons:
            continue
        w, P = wins[n], pools[n]
        for name, (idx, s, own) in sets.items():
            o = w.signed(idx, s)
            rows.append({'tf': tf, 'design': design, 'set': name, 'h_min': hm,
                         **matched_row(o, P, own, Bars_.sess, B, (tag, 'matched', design, tf, name, hm))})
    T = pd.DataFrame(rows)
    T['q_table'], T['fdr_table'] = bh(T.p.to_numpy())
    pr = T.h_min == PRIMARY_H
    q, rej = bh(T.loc[pr, 'p'].to_numpy())
    T.loc[pr, 'q_30m'] = q
    T.loc[pr, 'fdr_30m'] = rej
    return T


def twins_table(tf, tw, wins, pools, Bars_, B, tag) -> pd.DataFrame:
    """Event set vs its twin. Signed σ return (pre-registered): diff = event − twin, two-group regression, CR1 by day,
    day-block bootstrap CI. Unsigned |σ| (added after the review, post hoc, secondary): the unmatched difference of mean
    |σ| (same regression) and the difference of the MATCHED |σ| excess (|σ| − matched-control |σ|, each set against its
    own cells with its own events removed), with the joint day-clustered SE that includes the control-mean error."""
    rows = []
    pairs = [('absorbed', 'confirmed'), ('pwf', 'price_with_flow')]
    for a, b in pairs:
        for side_name, side_sel in (('both sides', None), ('buy / up side (+1)', 1), ('sell / down side (−1)', -1)):
            for hm, n in horizons_bars(tf):
                w, P = wins[n], pools[n]
                out, mt = {}, {}
                for nm in (a, b):
                    m, sd = tw[nm]
                    sel = m & (sd == side_sel) if side_sel is not None else m
                    idx = np.flatnonzero(sel)
                    out[nm] = w.signed(idx, sd[idx])
                    mt[nm] = P.match(out[nm], m, Bars_.sess)
                y1, y0 = out[a]['y'], out[b]['y']
                g1, g0 = Bars_.sess[out[a]['idx']], Bars_.sess[out[b]['idx']]
                d = cl_diff(y1, g1, y0, g0)
                lo, hi = boot_diff_ci(y1, g1, y0, g0, B, (tag, 'twin', tf, a, side_name, hm)) if B else (np.nan, np.nan)
                r1, r0 = cl_mean(y1, g1), cl_mean(y0, g0)
                du = cl_diff(np.abs(y1), g1, np.abs(y0), g0)
                ma, mb = mt[a], mt[b]
                dm = lin_diff(ma['da'], ma['g'], ma['Va'], mb['da'], mb['g'], mb['Va'], P.ndays)
                rows.append({'tf': tf, 'event': a, 'twin': b, 'side': side_name, 'h_min': hm,
                             'n_event': r1['n'], 'days_event': r1['days'], 'mean_event': r1['mean'], 'se_event': r1['se'],
                             'n_twin': r0['n'], 'days_twin': r0['days'], 'mean_twin': r0['mean'], 'se_twin': r0['se'],
                             'diff': d['diff'], 'se': d['se'], 'p': d['p'], 'boot_lo': lo, 'boot_hi': hi,
                             'hit_event': float(np.mean(y1 > 0)) if len(y1) else np.nan,
                             'hit_twin': float(np.mean(y0 > 0)) if len(y0) else np.nan,
                             'hit_nz_event': hit_nonzero(y1), 'hit_nz_twin': hit_nonzero(y0),
                             'abs_event': float(np.mean(np.abs(y1))) if len(y1) else np.nan,
                             'abs_twin': float(np.mean(np.abs(y0))) if len(y0) else np.nan,
                             'abs_diff_unmatched': du['diff'], 'abs_diff_unmatched_se': du['se'],
                             'abs_diff_unmatched_p': du['p'],
                             'abs_excess_event': float(np.mean(ma['da'])) if ma['n'] else np.nan,
                             'abs_excess_twin': float(np.mean(mb['da'])) if mb['n'] else np.nan,
                             'n_matched_event': ma['n'], 'n_matched_twin': mb['n'],
                             'abs_excess_diff': dm['diff'], 'abs_excess_diff_se': dm['se'], 'abs_excess_diff_p': dm['p']})
    T = pd.DataFrame(rows)
    T['q_table'], T['fdr_table'] = bh(T.p.to_numpy())
    return T


def baseline_table(tf, wins, Bars_, key) -> pd.DataFrame:
    rows = []
    for split, sel in (('full', np.ones(Bars_.n, bool)), ('2008–2016', ~Bars_.h2), ('2017–2026', Bars_.h2),
                       ('RTH', Bars_.rth), ('ETH', ~Bars_.rth)):
        for hm, n in horizons_bars(tf):
            w = wins[n]
            idx = np.flatnonzero((key >= 0) & w.valid & sel)
            o = w.signed(idx, 1.0)
            g = Bars_.sess[o['idx']]
            r = cl_mean(o['y'], g)
            ra = cl_mean(np.abs(o['y']), g)
            rows.append({'tf': tf, 'split': split, 'h_min': hm, 'n_bars': r['n'], 'days': r['days'],
                         'mean_long': r['mean'], 'se': r['se'], 'p': r['p'], 'hit_long': float(np.mean(o['y'] > 0)),
                         'zero_share': float(np.mean(o['y'] == 0)), 'median': float(np.median(o['y'])),
                         'mean_bps_long': float(np.mean(o['bps'])), 'mean_pts_long': float(np.mean(o['pts'])),
                         'abs_sig': ra['mean'], 'abs_sig_se': ra['se'],
                         'mfe_long_sig': float(np.mean(o['mfe_sig'])), 'mae_long_sig': float(np.mean(o['mae_sig'])),
                         'mfe_long_pts': float(np.mean(o['mfe_pts'])), 'mae_long_pts': float(np.mean(o['mae_pts']))})
    return pd.DataFrame(rows)


def costs_table(tf, masks, wins, Bars_) -> pd.DataFrame:
    """Naive rules 'trade s for h' and the opposite, in ES points, gross and net of COST_PT (and of the post-hoc stress
    cost COST_STRESS_PT). p_net_eq0 / p_opp_net_eq0: two-sided clustered test of net = 0. p_net_gt0_1s /
    p_opp_net_gt0_1s: one-sided test of net > 0 (BH over all full-sample rule cells in main()). valid_share = share of
    the class's signals whose window at this horizon is valid (long horizons lose close-clustered events to the session
    end, so the population changes with h)."""
    rows = []

    def p2(t, df):
        return float(2 * stats.t.sf(abs(t), df))

    for k in CLASS_KEYS:
        idx = np.flatnonzero(masks[k])
        for split, sel in (('full', None), ('2008–2016', ~Bars_.h2), ('2017–2026', Bars_.h2)):
            ii = idx if sel is None else idx[sel[idx]]
            for hm, n in horizons_bars(tf):
                o = wins[n].signed(ii, CLASS_S[k])
                g = Bars_.sess[o['idx']]
                r = cl_mean(o['pts'], g)
                rn = cl_mean(o['y'] - o['cost_sig'], g)
                ro = cl_mean(-o['y'] - o['cost_sig'], g)
                nn = r['n']
                ok = bool(nn and r['se'] and np.isfinite(r['se']) and r['days'] > 1)
                df_ = r['days'] - 1
                t_net = (r['mean'] - COST_PT) / r['se'] if ok else np.nan
                t_opp = (-r['mean'] - COST_PT) / r['se'] if ok else np.nan
                rows.append({'tf': tf, 'class': k, 'split': split, 'h_min': hm, 'n_signals': len(ii), 'n': nn,
                             'valid_share': nn / len(ii) if len(ii) else np.nan, 'days': r['days'],
                             'gross_pts': r['mean'], 'se_pts': r['se'],
                             'net_pts': r['mean'] - COST_PT if nn else np.nan,
                             'net_usd': (r['mean'] - COST_PT) * POINT_VALUE if nn else np.nan,
                             'opp_net_pts': -r['mean'] - COST_PT if nn else np.nan,
                             'p_net_eq0': p2(t_net, df_) if ok else np.nan,
                             'p_opp_net_eq0': p2(t_opp, df_) if ok else np.nan,
                             'p_net_gt0_1s': float(stats.t.sf(t_net, df_)) if ok else np.nan,
                             'p_opp_net_gt0_1s': float(stats.t.sf(t_opp, df_)) if ok else np.nan,
                             'net_pts_stress': r['mean'] - COST_STRESS_PT if nn else np.nan,
                             'opp_net_pts_stress': -r['mean'] - COST_STRESS_PT if nn else np.nan,
                             'win_net': float(np.mean(o['pts'] > COST_PT)) if nn else np.nan,
                             'win_net_opp': float(np.mean(-o['pts'] > COST_PT)) if nn else np.nan,
                             'cost_sig_mean': float(np.mean(o['cost_sig'])) if nn else np.nan,
                             'net_sig': rn['mean'], 'net_sig_se': rn['se'], 'net_sig_p': rn['p'],
                             'opp_net_sig': ro['mean'], 'opp_net_sig_se': ro['se'], 'opp_net_sig_p': ro['p']})
    return pd.DataFrame(rows)


def costs_bh(R: dict) -> dict:
    """One-sided BH over every full-sample rule cell (class × horizon × direction, all timeframes run): adds q_net_1s /
    q_opp_net_1s to the cost tables in place; returns the family size and the smallest q."""
    parts = []
    for tf in sorted(R):
        C = R[tf]['costs']
        m = (C.split == 'full').to_numpy()
        for col in ('p_net_gt0_1s', 'p_opp_net_gt0_1s'):
            parts.append((tf, col, np.flatnonzero(m), C[col].to_numpy()[m]))
    p_all = np.concatenate([x[3] for x in parts]) if parts else np.array([])
    q_all, _ = bh(p_all)
    i = 0
    for tf, col, rows, pv in parts:
        C = R[tf]['costs']
        qcol = {'p_net_gt0_1s': 'q_net_1s', 'p_opp_net_gt0_1s': 'q_opp_net_1s'}[col]
        if qcol not in C.columns:
            C[qcol] = np.nan
        C.loc[C.index[rows], qcol] = q_all[i:i + len(pv)]
        i += len(pv)
    return {'cells': int(len(p_all)), 'min_q': float(np.min(q_all)) if len(q_all) else np.nan,
            'min_p_1s': float(np.nanmin(p_all)) if len(p_all) else np.nan}


def stability_tables(tf, masks, wins, pools, Bars_, sr_t) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Splits at the primary horizon: halves, RTH/ETH, σr terciles (full-sample cut points; raw signed σ return and
    matched difference, the latter with the same matched design as section 4); per-year means."""
    n = PRIMARY_H // tf
    w, P = wins[n], pools[n]
    splits = [('2008–2016', ~Bars_.h2), ('2017–2026', Bars_.h2), ('RTH', Bars_.rth), ('ETH', ~Bars_.rth),
              ('σr tercile 1 (low)', sr_t == 0), ('σr tercile 2', sr_t == 1), ('σr tercile 3 (high)', sr_t == 2)]
    rows = []
    yrows = []
    for k in CLASS_KEYS:
        idx = np.flatnonzero(masks[k])
        for name, sel in splits:
            o = w.signed(idx[sel[idx]], CLASS_S[k])
            g = Bars_.sess[o['idx']]
            r = cl_mean(o['y'], g)
            mr = P.match(o, masks[k], Bars_.sess)
            dm = lin_mean(mr['dd'], mr['g'], mr['V'], P.ndays)
            rows.append({'tf': tf, 'class': k, 'split': name, 'h_min': PRIMARY_H, 'n': r['n'], 'days': r['days'],
                         'mean': r['mean'], 'se': r['se'], 'p': r['p'],
                         'hit': float(np.mean(o['y'] > 0)) if r['n'] else np.nan, 'hit_nz': hit_nonzero(o['y']),
                         'matched_diff': dm['mean'], 'matched_se': dm['se'], 'matched_p': dm['p']})
        o = w.signed(idx, CLASS_S[k])
        yrs = Bars_.year[o['idx']]
        for yv in np.unique(Bars_.year):
            sel = yrs == yv
            yrows.append({'tf': tf, 'class': k, 'year': int(yv), 'n': int(sel.sum()),
                          'mean': float(np.mean(o['y'][sel])) if sel.any() else np.nan})
    T = pd.DataFrame(rows)
    T['q_table'], T['fdr_table'] = bh(T.p.to_numpy())
    return T, pd.DataFrame(yrows)


def per_year_summary(Y: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for k in CLASS_KEYS:
        y = Y[(Y['class'] == k) & (Y.n > 0)]
        pos = int((y['mean'] > 0).sum())
        tot = int(len(y))
        rows.append({'class': k, 'years_with_events': tot, 'years_positive': pos,
                     'sign_test_p': float(stats.binomtest(pos, tot, 0.5).pvalue) if tot else np.nan,
                     'signs': ''.join('+' if m > 0 else ('−' if m < 0 else '0') for m in y['mean'])})
    return pd.DataFrame(rows)


def gate_study(tf, F, Bars_, wins, base_masks, B, tag) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Per-class outcomes under each gate variant, plus the events added / removed relative to the default."""
    rows, diff_rows, meta = [], [], {}
    for vname, ov in GATE_VARIANTS.items():
        if not ov:
            masks = base_masks
            meta[vname] = {'rho_min_eff': None}
        else:
            S, vm = run_variant(F, tf, **ov)
            masks, _ = class_masks(S)
            meta[vname] = {'rho_min_eff': vm['rho_min_eff'], 'gate_open_share_of_hq': float(
                (S.gate.to_numpy() == 1).sum() / max(1, (S.hq_ok.to_numpy() == 1).sum()))}
            del S
        for k in CLASS_KEYS:
            idx = np.flatnonzero(masks[k])
            for hm, n in horizons_bars(tf):
                o = wins[n].signed(idx, CLASS_S[k])
                g = Bars_.sess[o['idx']]
                r = cl_mean(o['y'], g)
                lo, hi = boot_ci(o['y'], g, B, (tag, 'gate', vname, tf, k, hm)) if (B and hm == PRIMARY_H) else (np.nan, np.nan)
                rows.append({'tf': tf, 'variant': vname, 'class': k, 'h_min': hm, 'n_signals': len(idx), **r,
                             'boot_lo': lo, 'boot_hi': hi, 'hit': float(np.mean(o['y'] > 0)) if r['n'] else np.nan})
            if ov:
                n = PRIMARY_H // tf
                for what, sel in (('added', masks[k] & ~base_masks[k]), ('removed', base_masks[k] & ~masks[k])):
                    o = wins[n].signed(np.flatnonzero(sel), CLASS_S[k])
                    g = Bars_.sess[o['idx']]
                    r = cl_mean(o['y'], g)
                    diff_rows.append({'tf': tf, 'variant': vname, 'class': k, 'set': what, 'h_min': PRIMARY_H,
                                      'n_signals': int(sel.sum()), **r})
    T = pd.DataFrame(rows)
    for vname in GATE_VARIANTS:
        m = (T.variant == vname) & (T.h_min == PRIMARY_H)
        q, rej = bh(T.loc[m, 'p'].to_numpy())
        T.loc[m, 'q_30m'] = q
        T.loc[m, 'fdr_30m'] = rej
    return T, pd.DataFrame(diff_rows), meta


def z_calibration(tf, S: pd.DataFrame, Bars_: Bars) -> tuple[pd.DataFrame, pd.DataFrame]:
    Z = S.Z.to_numpy()
    zc = S.z_cal_ok.to_numpy() == 1
    hq = S.hq_ok.to_numpy() == 1
    gate = S.gate.to_numpy() == 1
    rho = S.rho_p.to_numpy()

    def calib(sel):
        zz = np.isfinite(Z) & zc & sel
        zs = Z[zz]
        big = np.abs(Z) >= 2
        blocks = int(np.sum(big & zz & ~np.r_[False, (big & zz)[:-1]]))
        hh = hq & sel
        rr = rho[hh & np.isfinite(rho)]
        q = np.quantile(rr, [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]) if len(rr) else [np.nan] * 7
        g_on = zz & gate
        return {'bars': int(sel.sum()), 'bars_hq_ok': int(hh.sum()), 'bars_Z_calOk': int(zz.sum()),
                'P_absZ_ge2': float(np.mean(np.abs(zs) >= 2)) if len(zs) else np.nan,
                'P_absZ_ge3': float(np.mean(np.abs(zs) >= 3)) if len(zs) else np.nan,
                'P_Z_ge2': float(np.mean(zs >= 2)) if len(zs) else np.nan,
                'P_Z_le_m2': float(np.mean(zs <= -2)) if len(zs) else np.nan,
                'mean_Z': float(np.mean(zs)) if len(zs) else np.nan,
                'rms_Z': float(np.sqrt(np.mean(zs ** 2))) if len(zs) else np.nan,
                'blocks_absZ_ge2': blocks,
                'gate_open_share': float(np.mean(gate[hh])) if hh.any() else np.nan,
                'P_absZ_ge2_gate': float(np.mean(np.abs(Z[g_on]) >= 2)) if g_on.any() else np.nan,
                'rho_p05': q[0], 'rho_p10': q[1], 'rho_p25': q[2], 'rho_p50': q[3], 'rho_p75': q[4],
                'rho_p90': q[5], 'rho_p95': q[6],
                'P_rho_lt_0.30': float(np.mean(rr < 0.30)) if len(rr) else np.nan,
                'P_rho_lt_0.196': float(np.mean(rr < 0.196)) if len(rr) else np.nan,
                'P_rho_lt_0': float(np.mean(rr < 0)) if len(rr) else np.nan,
                'z_alerts_up': int(((S.al_z_up.to_numpy() == 1) & sel).sum()),
                'z_alerts_dn': int(((S.al_z_dn.to_numpy() == 1) & sel).sum())}

    rows = []
    for name, sel in (('full', np.ones(Bars_.n, bool)), ('2008–2016', ~Bars_.h2), ('2017–2026', Bars_.h2),
                      ('RTH', Bars_.rth), ('ETH', ~Bars_.rth)):
        rows.append({'tf': tf, 'split': name, **calib(sel)})
    yrows = [{'tf': tf, 'year': int(yv), **calib(Bars_.year == yv)} for yv in np.unique(Bars_.year)]
    return pd.DataFrame(rows), pd.DataFrame(yrows)


def event_counts(tf, masks, Bars_) -> pd.DataFrame:
    rows = []
    for k in CLASS_KEYS:
        m = masks[k]
        row = {'tf': tf, 'class': k, 'total': int(m.sum()), 'days': int(len(np.unique(Bars_.sess[m]))),
               'rth': int((m & Bars_.rth).sum()), 'eth': int((m & ~Bars_.rth).sum()),
               '2008–2016': int((m & ~Bars_.h2).sum()), '2017–2026': int((m & Bars_.h2).sum())}
        rows.append(row)
    return pd.DataFrame(rows)


def tod_table(tf, masks, F) -> pd.DataFrame:
    """POST HOC (added after the results were seen; descriptive only): where in the CT clock the events fall."""
    hm = F.t.dt.tz_convert('America/Chicago').dt.strftime('%H:%M').to_numpy()
    rows = []
    for k in CLASS_KEYS:
        m = masks[k]
        h = pd.Series(hm[m])
        vc = h.value_counts()
        rows.append({'tf': tf, 'class': k, 'n': int(m.sum()),
                     'share_open_0830_0859': float(h.between('08:30', '08:59').mean()) if len(h) else np.nan,
                     'share_close_1445_1514': float(h.between('14:45', '15:14').mean()) if len(h) else np.nan,
                     'top_bars_ct': ', '.join(f'{i} ({v})' for i, v in vc.head(4).items())})
    return pd.DataFrame(rows)


# ───────────────────────────── post hoc (added after the external review) ─────────────────────────────
# Everything in this section was added after the results and the review were seen. It is descriptive / sensitivity
# analysis only: no number here enters the primary family, and every table says so in results.md (section 11).

def load_1m_clean() -> pd.DataFrame | None:
    """Clean-session ES 1-minute rows for the latency and settlement-minute analyses; None when DATA_DIR is not set."""
    if not os.environ.get('DATA_DIR', '').strip():
        return None
    import bars as BR
    m1 = BR.load_1m('es', columns=['t_utc', 'o', 'c', 'v', 'session_date', 'clean_session', 'd_cr1m'])
    m1 = m1[m1.clean_session.to_numpy()].reset_index(drop=True)
    ct = m1.t_utc.dt.tz_convert('America/Chicago')
    m1['ct_min'] = (ct.dt.hour * 60 + ct.dt.minute).to_numpy()
    return m1


def intrabars(m1: pd.DataFrame, F: pd.DataFrame, tf: int) -> dict:
    """1-minute rows of every chart bar of F (the construction of bars.chart_bars, checked against the feature file)
    and the sign of the candle-rule delta of the 14:59 CT minute of every session."""
    tns = m1.t_utc.dt.as_unit('ns').array.asi8
    key = tns - np.mod(tns, tf * 60 * 1_000_000_000)
    sk = m1.session_date.dt.as_unit('ns').array.asi8
    starts = np.flatnonzero(np.r_[True, (key[1:] != key[:-1]) | (sk[1:] != sk[:-1])])
    ends = np.r_[starts[1:], len(m1)] - 1
    if len(starts) != len(F) or not np.array_equal(key[starts], F.t.dt.as_unit('ns').array.asi8):
        raise AssertionError(f'{tf}m: the 1-minute rows do not map onto the chart bars of the feature file')
    is59 = m1.ct_min.to_numpy() == SETTLE_CT_MIN
    sign59 = pd.Series(np.sign(m1.d_cr1m.to_numpy()[is59]).astype(float), index=m1.session_date.to_numpy()[is59])
    return {'c1': m1.c.to_numpy(float), 'starts': starts, 'ends': ends, 'sign59': sign59}


def settle_volume_table(m1: pd.DataFrame) -> pd.DataFrame:
    """Share of each year's clean-session volume traded in the 14:59 CT minute."""
    is59 = m1.ct_min.to_numpy() == SETTLE_CT_MIN
    v = m1.v.to_numpy().astype(float)
    d = pd.DataFrame({'year': m1.session_date.dt.year.to_numpy(), 'v': v, 'v59': np.where(is59, v, 0.0),
                      'm59': is59.astype(int)})
    g = d.groupby('year').sum()
    sess = m1.groupby(m1.session_date.dt.year).session_date.nunique()
    return pd.DataFrame({'year': g.index.astype(int), 'sessions': sess.reindex(g.index).to_numpy(),
                         'sessions_with_1459': g.m59.to_numpy(), 'share_volume_1459': (g.v59 / g.v).to_numpy()})


def latency_table(tf, masks, Bars_, sr_p, wins, ib) -> pd.DataFrame:
    """Entry delayed by d one-minute intrabars after the alert bar closes: d = 0 is the plan's O[t+1] (the first print
    after the close: a zero-latency upper bound); d ≥ 1 enters at the close of the d-th 1-minute bar of the stream after
    the signal bar. Exit C[t+n], σ scale and window filter as in the plan; the delayed entry must fall at or before the
    last minute of the exit bar. BH within each delay over the 16 classes."""
    n = PRIMARY_H // tf
    w = wins[n]
    out = []
    for d in LATENCY_MIN:
        rows = []
        for k in CLASS_KEYS:
            idx = np.flatnonzero(masks[k])
            idx = idx[w.valid[idx]]
            if d == 0:
                ent = Bars_.o[idx + 1]
            else:
                r1 = ib['starts'][idx + 1] + (d - 1)
                keep = r1 <= ib['ends'][idx + n]
                idx, r1 = idx[keep], r1[keep]
                ent = ib['c1'][r1]
            s = CLASS_S[k]
            y = s * 1e4 * np.log(Bars_.c[idx + n] / ent) / (sr_p[idx] * math.sqrt(n))
            r = cl_mean(y, Bars_.sess[idx])
            rows.append({'tf': tf, 'h_min': PRIMARY_H, 'delay_min': d, 'class': k, **r, 'hit_nz': hit_nonzero(y),
                         'mean_pts': float(np.mean(s * (Bars_.c[idx + n] - ent))) if len(idx) else np.nan,
                         'entry_drift_pts': float(np.mean(s * (ent - Bars_.o[idx + 1]))) if len(idx) else np.nan})
        T = pd.DataFrame(rows)
        T['q'], T['fdr'] = bh(T.p.to_numpy())
        out.append(T)
    return pd.concat(out, ignore_index=True)


def settle_table(tf, masks, Bars_, wins, pools, pools_slot, ke, session_date, ib) -> pd.DataFrame:
    """Absorbed / pinned events by whether their event window (the ke chart bars ending at the event bar) contains the
    14:59 CT minute, and without the most frequent open / close bars; signed σ return at 30 min, matched difference with
    the pre-registered cells (30-min bucket) and with exact-slot cells. side_eq_sign1459 = share of the events whose side
    equals the sign of the candle-rule delta of that session's 14:59 CT minute (needs DATA_DIR)."""
    n = PRIMARY_H // tf
    w, P, Ps = wins[n], pools[n], pools_slot[n]
    sb = Bars_.mins == (SETTLE_CT_MIN // tf) * tf
    in_win = sb.copy()
    for j in range(1, ke):
        in_win |= np.r_[np.zeros(j, bool), sb[:-j] & (Bars_.sess[j:] == Bars_.sess[:-j])]
    oc_min = [int(x[:2]) * 60 + int(x[3:]) for x in OPEN_CLOSE_BARS[tf]]
    oc = np.isin(Bars_.mins, oc_min)
    subsets = (('all', np.ones(Bars_.n, bool)), ('window contains 14:59 CT', in_win),
               ('window without 14:59 CT', ~in_win), ('without the ' + '/'.join(OPEN_CLOSE_BARS[tf]) + ' CT bars', ~oc))
    rows = []
    for k in SETTLE_CLASSES:
        idx_all = np.flatnonzero(masks[k])
        s = CLASS_S[k]
        for name, sel in subsets:
            idx = idx_all[sel[idx_all]]
            o = w.signed(idx, s)
            r = cl_mean(o['y'], Bars_.sess[o['idx']])
            mb = P.match(o, masks[k], Bars_.sess)
            db = lin_mean(mb['dd'], mb['g'], mb['V'], P.ndays)
            ms = Ps.match(o, masks[k], Bars_.sess)
            ds = lin_mean(ms['dd'], ms['g'], ms['V'], Ps.ndays)
            agree, n_sign = np.nan, 0
            if ib is not None and name == 'window contains 14:59 CT' and len(idx):
                sg = ib['sign59'].reindex(session_date[idx]).to_numpy()
                has = np.isfinite(sg) & (sg != 0)
                n_sign = int(has.sum())
                agree = float(np.mean(sg[has] == s)) if has.any() else np.nan
            rows.append({'tf': tf, 'class': k, 'subset': name, 'n_signals': len(idx),
                         'share_of_class': len(idx) / len(idx_all) if len(idx_all) else np.nan,
                         'n': r['n'], 'days': r['days'], 'mean': r['mean'], 'se': r['se'], 'p': r['p'],
                         'hit_nz': hit_nonzero(o['y']),
                         'matched_diff': db['mean'], 'matched_se': db['se'], 'matched_p': db['p'],
                         'slot_matched_diff': ds['mean'], 'slot_matched_se': ds['se'], 'slot_matched_p': ds['p'],
                         'slot_n_matched': ds['n'], 'side_eq_sign1459': agree, 'n_with_1459': n_sign})
    return pd.DataFrame(rows)


def slot_drift_table(tf, Bars_, wins, key) -> pd.DataFrame:
    """Unconditional long σ return at 30 min of all candidate bars by exact bar slot, around the open and the cash close
    (the drift that the 30-minute matching bucket averages over)."""
    n = PRIMARY_H // tf
    w = wins[n]
    slots = list(range(8 * 60 + 30, 9 * 60, tf)) + list(range(14 * 60, 15 * 60 + 15, tf))
    rows = []
    for m in slots:
        idx = np.flatnonzero((key >= 0) & w.valid & (Bars_.mins == m))
        o = w.signed(idx, 1.0)
        r = cl_mean(o['y'], Bars_.sess[o['idx']])
        rows.append({'tf': tf, 'slot_ct': f'{m // 60:02d}:{m % 60:02d}', 'h_min': PRIMARY_H, **r,
                     'hit_nz': hit_nonzero(o['y'])})
    return pd.DataFrame(rows)


def prior_session_res_table(tf, masks, Bars_, wins, res_age) -> pd.DataFrame:
    """Resolutions split by whether the absorption they resolve was born in an earlier session (pending events survive
    the daily break and weekends because the life is counted in bars, so the reopen gap can trigger them)."""
    first = np.r_[True, Bars_.sess[1:] != Bars_.sess[:-1]]
    rows = []
    for k in RES_CLASSES:
        idx_all = np.flatnonzero(masks[k])
        prior = Bars_.sess[idx_all - res_age[idx_all]] != Bars_.sess[idx_all]
        for name, sel in (('all', np.ones(len(idx_all), bool)), ('absorption born in an earlier session', prior),
                          ('absorption born in the same session', ~prior)):
            idx = idx_all[sel]
            for hm, n in horizons_bars(tf):
                o = wins[n].signed(idx, CLASS_S[k])
                r = cl_mean(o['y'], Bars_.sess[o['idx']])
                rows.append({'tf': tf, 'class': k, 'subset': name, 'h_min': hm, 'n_signals': len(idx),
                             'on_first_bar': int(first[idx].sum()), **r})
    return pd.DataFrame(rows)


def survival_table(tf, masks, Bars_, wins) -> pd.DataFrame:
    """Share of the signals whose outcome window is valid, by era and for the cash-close bars. The session-end layout
    changed over the sample (in these data the last bar of the session opens at 16:15 CT until 2012, 16:00 in 2013–14
    and 15:45 from 2016; the 15:15–15:30 CT halt removes the 15:15 bar until mid-2021), so a long window that starts
    near the cash close crosses the session end in some eras and not in others."""
    close = (Bars_.mins >= 14 * 60 + 45) & (Bars_.mins < 15 * 60 + 15)
    rows = []
    for k in CLASS_KEYS:
        idx_all = np.flatnonzero(masks[k])
        for name, sel in (('all', np.ones(Bars_.n, bool)), ('cash-close bars 14:45–15:14 CT', close)):
            idx = idx_all[sel[idx_all]]
            for era, a, b in (('all years', 0, 9999),) + ERAS:
                ii = idx[(Bars_.year[idx] >= a) & (Bars_.year[idx] <= b)]
                for hm, n in horizons_bars(tf):
                    nv = int(wins[n].valid[ii].sum())
                    rows.append({'tf': tf, 'class': k, 'subset': name, 'era': era, 'h_min': hm, 'n_signals': len(ii),
                                 'n_valid': nv, 'valid_share': nv / len(ii) if len(ii) else np.nan})
    return pd.DataFrame(rows)


# ───────────────────────────── driver ─────────────────────────────

def run_tf(tf: int, B_primary: int, B_other: int, log, m1: pd.DataFrame | None = None) -> dict:
    t0 = time.time()
    F = load_features(tf)
    Bars_ = Bars(F, tf)
    S = F[SIG_COLS].reset_index(drop=True)
    ke, life = E.event_windows(E.Params(tf_sec=tf * 60))
    log(f'[{tf}m] {len(F):,} bars, {len(Bars_.sess_labels):,} sessions; ke={ke} life={life}')
    S_chk, _ = run_variant(F, tf)
    chk = check_default_reproduces(F, S_chk)
    del S_chk
    log(f'[{tf}m] default engine re-run reproduces the feature file ({chk})')
    masks, checks = class_masks(S)
    log(f'[{tf}m] consistency checks: {checks}')
    wins = {n: Window(Bars_, S.sr_p.to_numpy(), n) for _, n in horizons_bars(tf)}
    keys, sr_t, cinfo = candidate_controls(S, Bars_, tf)
    pools = {n: CellPool(keys['bucket'], wins[n], Bars_) for _, n in horizons_bars(tf)}
    tag = 'es'
    res = {}
    res['counts'] = event_counts(tf, masks, Bars_)
    res['tod'] = tod_table(tf, masks, F)
    res['classes'] = class_table(tf, masks, wins, Bars_, B_primary, B_other, tag)
    log(f'[{tf}m] class table done ({time.time() - t0:.0f}s)')
    tw = twin_events(S, ke)
    res['twins'] = twins_table(tf, tw, wins, pools, Bars_, B_other, tag)
    sets = {k: (np.flatnonzero(masks[k]), CLASS_S[k], masks[k]) for k in CLASS_KEYS}
    for nm in ('confirmed', 'price_with_flow'):
        m, sd = tw[nm]
        idx = np.flatnonzero(m)
        sets[f'twin:{nm}'] = (idx, sd[idx], m)
    res['matched'] = matched_table(tf, sets, wins, pools, Bars_, B_other, tag)
    log(f'[{tf}m] twins and matched controls done ({time.time() - t0:.0f}s)')
    res['baseline'] = baseline_table(tf, wins, Bars_, keys['bucket'])
    res['costs'] = costs_table(tf, masks, wins, Bars_)
    res['stability'], res['per_year'] = stability_tables(tf, masks, wins, pools, Bars_, sr_t)
    res['per_year_summary'] = per_year_summary(res['per_year'])
    res['zcal'], res['zcal_year'] = z_calibration(tf, S, Bars_)
    log(f'[{tf}m] baseline, costs, stability, Z calibration done ({time.time() - t0:.0f}s)')
    res['gate'], res['gate_diff'], gmeta = gate_study(tf, F, Bars_, wins, masks, B_other, tag)
    log(f'[{tf}m] gate study done ({time.time() - t0:.0f}s)')
    # ── post hoc (added after the external review; section 11 of results.md) ──
    n30 = PRIMARY_H // tf
    slot30 = {n30: CellPool(keys['slot'], wins[n30], Bars_)}
    pk30 = {n30: CellPool(keys['pk'], wins[n30], Bars_)}
    res['matched_sens'] = pd.concat(
        [matched_table(tf, sets, wins, pk30, Bars_, B_other, tag, horizons=(PRIMARY_H,), design='P_K bins'),
         matched_table(tf, sets, wins, slot30, Bars_, B_other, tag, horizons=(PRIMARY_H,), design='exact bar slot')],
        ignore_index=True)
    ib = intrabars(m1, F, tf) if m1 is not None else None
    res['settle'] = settle_table(tf, masks, Bars_, wins, pools, slot30, ke, F.session_date.to_numpy(), ib)
    res['slot_drift'] = slot_drift_table(tf, Bars_, wins, keys['bucket'])
    res['prior_res'] = prior_session_res_table(tf, masks, Bars_, wins, S.res_age.to_numpy())
    res['survival'] = survival_table(tf, masks, Bars_, wins)
    if ib is not None:
        res['latency'] = latency_table(tf, masks, Bars_, S.sr_p.to_numpy(), wins, ib)
    else:
        res['latency'] = pd.DataFrame(columns=['tf', 'h_min', 'delay_min', 'class'])
        log(f'[{tf}m] DATA_DIR not set: the entry-latency table and the 14:59 side check are skipped')
    log(f'[{tf}m] post-hoc sensitivities done ({time.time() - t0:.0f}s)')
    twin_counts = {nm: int(tw[nm][0].sum()) for nm in tw}
    halt = {hm: float(np.mean(wins[n].halt[wins[n].valid])) for hm, n in horizons_bars(tf)}
    res['meta'] = {'tf': tf, 'bars': int(len(F)), 'sessions': int(len(Bars_.sess_labels)),
                   'first_bar': str(F.t.iloc[0]), 'last_bar': str(F.t.iloc[-1]), 'ke': ke, 'life': life,
                   'reproduce_check': chk, 'consistency_checks': checks, 'controls': cinfo, 'twin_counts': twin_counts,
                   'gate_variants': gmeta, 'halt_share_all_valid_windows': halt,
                   'valid_windows': {hm: int(wins[n].valid.sum()) for hm, n in horizons_bars(tf)},
                   'intrabars_used': ib is not None, 'runtime_s': round(time.time() - t0, 1)}
    return res


# ───────────────────────────── report ─────────────────────────────

def _fmt(v, kind=None):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return '—'
    if isinstance(v, (bool, np.bool_)):
        return 'yes' if v else 'no'
    if kind == 'p':
        return '<0.001' if v < 0.001 else f'{v:.3f}'
    if kind == 'pct':
        return f'{100 * v:.1f}%'
    if kind == 'pct2':
        return f'{100 * v:.2f}%'
    if kind == 'int' or isinstance(v, (int, np.integer)):
        return f'{int(v):,}'
    if kind == 'f2':
        return f'{v:.2f}'
    if kind == 'f4':
        return f'{v:.4f}'
    if isinstance(v, (float, np.floating)):
        return f'{v:.3f}'
    return str(v)


def md_table(df: pd.DataFrame, cols: list, kinds: dict | None = None, rename: dict | None = None) -> str:
    kinds = kinds or {}
    rename = rename or {}
    esc = lambda x: str(x).replace('|', '\\|')   # noqa: E731 — a literal | (as in |σ|) would split the cell
    head = [esc(rename.get(c, c)) for c in cols]
    lines = ['| ' + ' | '.join(head) + ' |', '|' + '|'.join('---' for _ in cols) + '|']
    for _, r in df.iterrows():
        lines.append('| ' + ' | '.join(esc(_fmt(r[c], kinds.get(c))) for c in cols) + ' |')
    return '\n'.join(lines)


def ci(lo, hi):
    return '—' if not (np.isfinite(lo) and np.isfinite(hi)) else f'[{lo:+.3f}, {hi:+.3f}]'


DEVIATIONS = [
    # Every departure from the pre-registered plan, with its reason. None changes a definition, a parameter, a horizon,
    # a filter or the primary family. Items 1–2 were decided while writing the code, before any outcome was computed;
    # item 3 was added after the results were seen and is labelled post hoc; items 4–7 come from the external review
    # (after the results were seen): item 4 corrects errors in the matched-control implementation, items 5–7 are
    # relabelled columns and post-hoc additions. CHANGELOG.md lists how each number moved.
    'Gate study procedure: the ρmin 0.20 / 0.40 and gate-off variants were re-derived by re-running the validated '
    'engine on the same bars with the gate input changed, instead of with separate code that re-derives the classes '
    'from the stored zF/zP/ρ/Z series. Reason: the two are identical by construction (Z, zF, zP and their calibration '
    'do not depend on the gate; only the classes, clusters, resolutions and Z alerts do), and the engine is the '
    'validated implementation of the cluster and resolution machines. Checks: the default re-run reproduces the 29 '
    'stored signal columns exactly, and the cluster routine used for the twins rebuilds alAbs and alPwf exactly.',
    'Matched controls procedure: instead of drawing a finite random sample of matched control bars per event, each '
    'event\'s control is the mean over ALL candidate bars of its matching cell (leaving the event bar out), i.e. the '
    'expectation of a random matched draw. Reason: same estimand, no Monte Carlo noise. Events whose cell holds fewer '
    f'than {MIN_CTRL} control bars are dropped from that comparison (counts in the table, 0.1–9% of events).',
    'Post-hoc additions (descriptive, after the results were seen; no test, no effect on any pre-registered number): '
    'the time-of-day concentration table of the events (`tod_*.csv`, section 1) and the minimum detectable effect '
    'column of the primary table (MDE80 = 2.80 × clustered SE: two-sided 5% test, 80% power).',
    'Correction after review, matched controls (control (2) of the plan; the plan itself is unchanged): (a) all events '
    'of the same class are now removed from the control cells (before: only the event bar itself; on 15m the same-class '
    'events were about 8% of the controls of absorbed and pinned events, which pulled event − control toward 0); (b) the '
    'σr tercile is now taken within each year (before: full-sample cut points, so within a year-specific cell σr was '
    'matched only coarsely; the plan says "σr tercile" without fixing the reference set, and the robustness study '
    'already used within-year terciles); (c) the SE and the bootstrap now include the sampling error of the control '
    'means (before: treated as fixed, which understated the SE by about 5–6% for the rare 15m classes). The stability '
    'table\'s matched column uses the same design. The σr-tercile STABILITY split keeps the full-sample cut points '
    '(volatility regimes in absolute terms, as pre-registered).',
    'Relabelled after review, costs: the p-value columns of the cost tables were named p_net_gt0 / p_opp_net_gt0 but held '
    'two-sided tests of net = 0; they are now p_net_eq0 / p_opp_net_eq0. Added: one-sided p of net > 0 '
    '(p_net_gt0_1s, p_opp_net_gt0_1s) with BH over all full-sample rule cells of both timeframes (q_net_1s, '
    'q_opp_net_1s); valid_share (share of signals with a valid window at that horizon); a stress cost of '
    f'{COST_STRESS_PT} pt (2 ticks + commission). The pre-registered cost ({COST_PT} pt) and its net numbers are unchanged.',
    'Post-hoc additions after review (secondary or descriptive, section 11; none enters the primary family): hit rate '
    'among non-zero outcomes (hit_nz); in the twin table, the unsigned |σ| comparison of each set with its twin '
    '(unmatched difference and difference of the matched |σ| excess); a P_K-matched control (year × RTH × 30-min '
    f'bucket × {PK_BINS} bins of the K-bar price leg P_K) and an exact-bar-slot control; the settlement-minute '
    'sensitivity of absorbed and pinned events (window containing the 14:59 CT minute or not, without the most '
    'frequent open / close bars, side vs the 14:59 candle) with the slot drift and the 14:59 volume share; entry '
    'latency of 1 and 2 minutes; resolutions of absorptions born in an earlier session; window survival by era.',
]


def _as_bool(v):
    if isinstance(v, str):
        return {'True': True, 'False': False}.get(v, np.nan)
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return np.nan
    return bool(v)


def _ci_col(T: pd.DataFrame) -> pd.DataFrame:
    T = T.copy()
    T['CI_boot'] = [ci(a, b) for a, b in zip(T.boot_lo, T.boot_hi)]
    return T


TF_NAME = {5: 'ES 5m (primary timeframe)', 15: 'ES 15m (secondary timeframe)'}


def write_report(R: dict, meta: dict, vol59: pd.DataFrame | None = None):
    L = []
    A = L.append
    tfs = sorted(R)
    A('# ES event study (pre-registered): «Preço × CVD Normalizado [Order Flow]»')
    A('')
    A(f'Generated by `study_es.py` on {time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}. Every number comes from the '
      'CSV files of this folder (names at the end). The results contain aggregate statistics only, no price data.')
    A('')
    interp = res_dir() / 'interpretation.md'
    if interp.exists():
        A(interp.read_text().strip())
        A('')

    # 1 ── data
    A('## 1. Data, settings and signals')
    A('')
    for tf in tfs:
        m = R[tf]['meta']
        A(f'- **ES {tf}m**: {m["bars"]:,} bars, {m["sessions"]:,} clean sessions, {m["first_bar"][:10]} → '
          f'{m["last_bar"][:10]}; ke = {m["ke"]} bars, life = {m["life"]} bars. Valid outcome windows: '
          + ', '.join(f'{h} min {v:,}' for h, v in m['valid_windows'].items())
          + '. Share of valid windows that span an intra-session halt: '
          + ', '.join(f'{h} min {100 * v:.2f}%' for h, v in m['halt_share_all_valid_windows'].items()) + '.')
    A('- Delta: candle rule on 1-minute intrabars, side carried over the whole 1-minute stream (TradingView "Auto" on '
      'an intraday chart), summed per chart bar: quality tier 2 (medium). Indicator inputs: defaults (N 100, K 20, '
      'M 1000, clip 4, thresholds 2/3, ρmin 0.30, event window 15 min, life 60 min, zF 2, pinned 3/0.5) with pivots '
      'on (L5 R2, distance 5–60, magnitude 0.5).')
    A('- Signals = the indicator\'s 14 alertcondition sets, with the two Z alerts split by the dominant leg (16 '
      'classes). Signal at the close of the bar where it is known; entry at the next open; exit at the close n bars '
      'after the signal bar. s = flow side (absorbed, pinned), price side (price without flow), leading leg (Z states), '
      'direction of the resolving close (resolutions), −1 top / +1 bottom (pivots). Positive = continuation of s.')
    A('- Primary outcome: s·10⁴·ln(C[t+n]/O[t+1]) / (σr·√n), σr = the indicator\'s lagged one-bar σ (bps) at the '
      'signal bar. "σ" below always means these units. A random-direction trade has expectation 0 σ; the drift of the '
      'unconditional long trade is in section 4 (baseline).')
    A('- Entry timing: O[t+1] is the first trade after the alert bar closes, i.e. a zero-latency upper bound. A '
      'TradingView alert gated on the bar close reaches a trader seconds later, and a manual order later still; users '
      'without CME real-time data on TradingView see bars delayed by 10 minutes, which uses up the 5- and 15-minute '
      'horizons. Entry delays of 1 and 2 minutes are in section 11.3 (post hoc).')
    A('- Data scope: front-month, dominant-contract sessions only (the clean sessions of the 1-minute file: 75 roll '
      'sessions, 30 non-dominant-contract sessions and 35 roll-window sessions are left out; manifest es_1m.sessions). '
      'A TradingView user on ES1! keeps those sessions in the stream and, depending on the continuous-contract roll '
      'setting, may chart the expiring contract for part of roll week while its volume collapses; σΔ, ρ and the RMS of '
      'D (M = 1,000 bars, about 3.6 sessions on 5m) then differ from the study\'s for a few sessions around each roll. '
      'Outcome windows never cross a session or a contract change. The results cover non-roll, dominant-contract weeks.')
    A('')
    for tf in tfs:
        A(f'**Event counts, {TF_NAME[tf]}** (signals; a few lose their outcome window at a session end):')
        A('')
        A(md_table(R[tf]['counts'], ['class', 'total', 'days', 'rth', 'eth', '2008–2016', '2017–2026'],
                   {c: 'int' for c in ['total', 'days', 'rth', 'eth', '2008–2016', '2017–2026']},
                   {'rth': 'RTH', 'eth': 'ETH'}))
        A('')
        A(f'Post hoc (descriptive, added after the results were seen): time of day of the events, {tf}m (CT bar open '
          'times; open = 08:30–08:59, cash close = 14:45–15:14).')
        A('')
        A(md_table(R[tf]['tod'], ['class', 'n', 'share_open_0830_0859', 'share_close_1445_1514', 'top_bars_ct'],
                   {'n': 'int', 'share_open_0830_0859': 'pct', 'share_close_1445_1514': 'pct'},
                   {'share_open_0830_0859': 'open', 'share_close_1445_1514': 'cash close', 'top_bars_ct': 'top bars (n)'}))
        m = R[tf]['meta']
        A('')
        A(f'Checks ({tf}m): ' + ', '.join(f'{k} = {v}' for k, v in m['consistency_checks'].items())
          + f'. The default engine re-run reproduced all {m["reproduce_check"]["checked_columns"]} signal columns of '
          'the feature file exactly. Twin event counts: '
          + ', '.join(f'{k} {v:,}' for k, v in m['twin_counts'].items()) + '.')
        A('')

    # 2 ── primary
    if PRIMARY_TF in R:
        T = R[PRIMARY_TF]['classes']
        P = _ci_col(T[T.h_min == PRIMARY_H])
        A('## 2. Primary endpoint: signed σ return at 30 min, ES 5m, full sample')
        A('')
        A(f'Family of {len(P)} tests, Benjamini–Hochberg at q = {FDR_Q}. SE clustered by trading day, p two-sided '
          '(t, G − 1 df); CI_boot = day-block bootstrap 95% percentile CI (10,000 replicates).')
        A('')
        A(md_table(P, ['class', 's', 'n', 'days', 'mean', 'se', 't', 'p', 'q_30m', 'fdr_30m', 'CI_boot', 'hit',
                       'zero_share', 'hit_nz', 'median', 'mean_bps', 'mde80'],
                   {'n': 'int', 'days': 'int', 'p': 'p', 'q_30m': 'p', 'hit': 'pct', 's': 'int', 't': 'f2',
                    'zero_share': 'pct', 'hit_nz': 'pct'},
                   {'mean': 'mean σ', 'q_30m': 'q (BH)', 'fdr_30m': 'FDR 5%', 'hit': 'hit rate', 'mean_bps': 'bps',
                    'mde80': 'MDE80 σ', 'zero_share': '=0', 'hit_nz': 'hit ≠0'}))
        A('')
        A('MDE80 (post hoc) = 2.80 × SE: the true mean that a two-sided 5% test would detect with 80% power. bps = mean '
          'signed return in basis points. hit rate = share > 0 (pre-registered; exact zeros count as misses, so a '
          'random-direction trade scores about 47–48% on it); =0 = share of exact zeros; hit ≠0 = share > 0 among the '
          'non-zero returns (no-information value 50%; added after the review).')
        A('')
        sig = P[P.p < 0.05]
        A(f'**{int(P.fdr_30m.sum())} of {len(P)} classes survive the FDR correction.** Raw p < 0.05: '
          + (', '.join(f'{r["class"]} ({r["mean"]:+.3f} σ, p = {_fmt(r["p"], "p")}, q = {_fmt(r["q_30m"], "p")})'
                       for _, r in sig.iterrows()) or 'none') + '.')
        A('')

    # 3 ── all horizons
    A('## 3. All horizons and outcome measures (secondary)')
    A('')
    A('q = BH over every cell of the table (its own family; flag only). MFE / MAE = mean maximum favourable / adverse '
      'excursion from the entry over the horizon (positive numbers). |σ| = mean unsigned return (volatility effect; '
      'compare with the baseline |σ| in section 4). =0: share of exactly zero returns (tick grid).')
    A('')
    for i, tf in enumerate(tfs, 1):
        T = _ci_col(R[tf]['classes'])
        A(f'### 3.{i} {TF_NAME[tf]}')
        A('')
        A(md_table(T, ['class', 'h_min', 'n', 'days', 'mean', 'CI_boot', 'p', 'q_table', 'hit', 'zero_share', 'hit_nz',
                       'median', 'mean_bps', 'mean_pts', 'mfe_sig', 'mae_sig', 'mfe_pts', 'mae_pts', 'abs_sig'],
                   {'n': 'int', 'days': 'int', 'h_min': 'int', 'p': 'p', 'q_table': 'p', 'hit': 'pct',
                    'zero_share': 'pct', 'hit_nz': 'pct', 'mean_bps': 'f2', 'mean_pts': 'f2', 'mfe_pts': 'f2',
                    'mae_pts': 'f2'},
                   {'h_min': 'h', 'mean': 'mean σ', 'q_table': 'q', 'zero_share': '=0', 'hit_nz': 'hit ≠0',
                    'mean_bps': 'bps',
                    'mean_pts': 'pts', 'mfe_sig': 'MFE σ', 'mae_sig': 'MAE σ', 'mfe_pts': 'MFE pts',
                    'mae_pts': 'MAE pts', 'abs_sig': '|σ|'}))
        A('')
        if tf != PRIMARY_TF:
            P = T[T.h_min == PRIMARY_H]
            A(f'{tf}m at 30 min with BH over its 16 classes (secondary, not confirmatory): {int(P.fdr_30m.sum())} of '
              f'{len(P)} survive.')
            A('')

    # 4 ── controls
    A('## 4. Controls: does the CVD add information beyond price?')
    A('')
    A('**Conditional twins.** Absorbed (flow shock, price not following) vs CONFIRMED flow shocks (|zF| ≥ 2, '
      's·zP ≥ |ρ|·|zF|); price without flow vs price shocks WITH flow (|zP| ≥ 2, sign(zP)·zF > 0). The twins are '
      'built as indicator events (gate open, cluster start per side, refractory ke observations). diff = event − twin '
      '(σ), two-group regression, SE clustered by day; CI_boot = day-block bootstrap of the difference. A second table '
      '(added after the review, post hoc, secondary) compares the UNSIGNED moves: the unmatched difference of mean |σ| '
      'and the difference of the matched |σ| excess (|σ| minus the |σ| of the matched controls, each set against its '
      'own cells), with a day-clustered SE that includes the control-mean error.')
    A('')
    A('**Matched random controls.** Cell = year × RTH (08:30–15:15 CT) / ETH × 30-min CT bucket × σr tercile within '
      f'the year × sign of pE × tercile of |pE|. Control = mean over the cell\'s candidate bars (≥ {MIN_CTRL}) after '
      'removing every event of the same class (or twin set), signed with the event\'s s. diff = event − control (σ); '
      '|σ| diff = |event| − control |σ| (volatility effect). se includes the sampling error of the control means '
      '(se ctrl fixed: without it, the original computation). Rows "twin:*" are the twin sets, for reference. '
      'Design corrected after the review (section 10, CHANGELOG.md).')
    A('')
    A('**Unconditional baseline.** All candidate bars (hqOk, gate open, σr > 0, pE defined, valid window), long '
      'direction.')
    A('')
    k = 0
    for tf in tfs:
        k += 1
        T = _ci_col(R[tf]['twins'])
        A(f'### 4.{k} Conditional twins, {TF_NAME[tf]}')
        A('')
        A(md_table(T, ['event', 'twin', 'side', 'h_min', 'n_event', 'mean_event', 'n_twin', 'mean_twin', 'diff', 'se',
                       'p', 'q_table', 'CI_boot', 'hit_nz_event', 'hit_nz_twin'],
                   {'h_min': 'int', 'n_event': 'int', 'n_twin': 'int', 'p': 'p', 'q_table': 'p', 'hit_nz_event': 'pct',
                    'hit_nz_twin': 'pct'},
                   {'h_min': 'h', 'n_event': 'n ev', 'n_twin': 'n twin', 'mean_event': 'event σ',
                    'mean_twin': 'twin σ', 'q_table': 'q', 'hit_nz_event': 'hit≠0 ev', 'hit_nz_twin': 'hit≠0 twin'}))
        A('')
        A(f'Unsigned moves, event set vs twin ({tf}m; post hoc, secondary, no multiplicity correction): |σ| ev / twin = '
          'mean |σ|; unmatched diff = |σ| ev − |σ| twin; excess = mean(|σ| − matched-control |σ|) of each set; excess '
          'diff = event excess − twin excess.')
        A('')
        A(md_table(T, ['event', 'twin', 'side', 'h_min', 'abs_event', 'abs_twin', 'abs_diff_unmatched',
                       'abs_diff_unmatched_p', 'abs_excess_event', 'abs_excess_twin', 'abs_excess_diff',
                       'abs_excess_diff_se', 'abs_excess_diff_p'],
                   {'h_min': 'int', 'abs_diff_unmatched_p': 'p', 'abs_excess_diff_p': 'p'},
                   {'h_min': 'h', 'abs_event': '|σ| ev', 'abs_twin': '|σ| twin', 'abs_diff_unmatched': 'unmatched diff',
                    'abs_diff_unmatched_p': 'p', 'abs_excess_event': 'excess ev', 'abs_excess_twin': 'excess twin',
                    'abs_excess_diff': 'excess diff', 'abs_excess_diff_se': 'SE', 'abs_excess_diff_p': 'p excess'}))
        A('')
        k += 1
        mi = R[tf]['meta']['controls']
        T = _ci_col(R[tf]['matched'])
        A(f'### 4.{k} Matched random controls, {TF_NAME[tf]}')
        A('')
        yc = mi['sr_terciles_bps_by_year']
        y0, y1 = min(yc, key=int), max(yc, key=int)
        A(f'{mi["candidates"]:,} candidate bars; σr tercile cuts within the year, e.g. {y0}: {yc[y0][0]:.2f} / '
          f'{yc[y0][1]:.2f} bps, {y1}: {yc[y1][0]:.2f} / {yc[y1][1]:.2f} bps (all years in run_meta.json); |pE| tercile '
          f'cuts {mi["abs_pE_terciles"][0]:.3f} / {mi["abs_pE_terciles"][1]:.3f}.')
        A('')
        A(md_table(T, ['set', 'h_min', 'n_matched', 'dropped_no_controls', 'own_removed', 'median_controls',
                       'event_mean', 'control_mean', 'diff', 'se', 'se_ctrl_fixed', 'p', 'q_table', 'CI_boot',
                       'event_abs', 'control_abs', 'abs_diff', 'abs_diff_p'],
                   {'h_min': 'int', 'n_matched': 'int', 'dropped_no_controls': 'int', 'median_controls': 'int',
                    'own_removed': 'int', 'p': 'p', 'q_table': 'p', 'abs_diff_p': 'p'},
                   {'h_min': 'h', 'n_matched': 'n', 'dropped_no_controls': 'no ctrl', 'own_removed': 'own out',
                    'median_controls': 'ctrl/ev', 'event_mean': 'event σ', 'control_mean': 'control σ',
                    'se_ctrl_fixed': 'se ctrl fixed', 'q_table': 'q', 'event_abs': '|σ| ev',
                    'control_abs': '|σ| ctrl', 'abs_diff': '|σ| diff', 'abs_diff_p': 'p |σ|'}))
        A('')
        P = T[T.h_min == PRIMARY_H]
        A(f'At 30 min, BH over the {len(P)} sets of that slice: {int(P.fdr_30m.sum())} differences survive.')
        A('')
        k += 1
        A(f'### 4.{k} Unconditional baseline, {TF_NAME[tf]}')
        A('')
        A(md_table(R[tf]['baseline'], ['split', 'h_min', 'n_bars', 'days', 'mean_long', 'se', 'p', 'hit_long',
                                       'zero_share', 'mean_bps_long', 'mean_pts_long', 'abs_sig', 'mfe_long_sig',
                                       'mae_long_sig', 'mfe_long_pts', 'mae_long_pts'],
                   {'h_min': 'int', 'n_bars': 'int', 'days': 'int', 'p': 'p', 'hit_long': 'pct', 'zero_share': 'pct',
                    'mean_bps_long': 'f2', 'mean_pts_long': 'f2', 'mfe_long_pts': 'f2', 'mae_long_pts': 'f2',
                    'mean_long': 'f4'},
                   {'h_min': 'h', 'n_bars': 'n', 'mean_long': 'mean σ', 'hit_long': 'hit', 'zero_share': '=0',
                    'mean_bps_long': 'bps', 'mean_pts_long': 'pts', 'abs_sig': '|σ|', 'mfe_long_sig': 'MFE σ',
                    'mae_long_sig': 'MAE σ', 'mfe_long_pts': 'MFE pts', 'mae_long_pts': 'MAE pts'}))
        A('')

    # 5 ── gate
    A('## 5. Gate study')
    A('')
    A('Variants re-derived by the engine on the same bars (Z, zF, zP and their calibration do not depend on the '
      'gate). Signed σ return at 30 min per variant; BH within each variant\'s 16 classes (flag only). "added" = '
      'events of the variant on bars where the default has none of that class; "removed" = the converse. Other '
      'horizons per variant are in `gate_{tf}m.csv`.')
    A('')
    for i, tf in enumerate(tfs, 1):
        A(f'### 5.{i} {TF_NAME[tf]}')
        A('')
        gm = R[tf]['meta']['gate_variants']
        A('Gate-open share of hqOk bars: ' + '; '.join(
            f'{kk}: {100 * v["gate_open_share_of_hq"]:.2f}%' for kk, v in gm.items() if 'gate_open_share_of_hq' in v)
          + '; default: section 8.')
        A('')
        G = R[tf]['gate']
        Gp = _ci_col(G[G.h_min == PRIMARY_H])
        A(md_table(Gp, ['variant', 'class', 'n', 'days', 'mean', 'se', 'p', 'q_30m', 'fdr_30m', 'CI_boot', 'hit'],
                   {'n': 'int', 'days': 'int', 'p': 'p', 'q_30m': 'p', 'hit': 'pct'},
                   {'mean': 'mean σ', 'q_30m': 'q', 'fdr_30m': 'FDR 5%'}))
        A('')
        D = R[tf]['gate_diff']
        D = D[D.n_signals > 0]
        A('Added / removed events, 30 min:')
        A('')
        A(md_table(D, ['variant', 'class', 'set', 'n_signals', 'n', 'days', 'mean', 'se', 'p'],
                   {'n_signals': 'int', 'n': 'int', 'days': 'int', 'p': 'p'}, {'mean': 'mean σ'}))
        A('')

    # 6 ── costs
    A(f'## 6. Costs: naive rules (round trip {COST_PT} pt = ${COST_PT * POINT_VALUE:.2f} per contract)')
    A('')
    A(f'The pre-registered cost of {COST_PT} pt (1 tick of slippage + about $4 commission) is a LOWER BOUND: it fits a '
      '1-lot in normal RTH liquidity, measured against trade prints. It is optimistic where these signals cluster (the '
      '08:30 CT open, the 15:00 CT settlement, the 07:30 and 09:00 CT release bars, the 17:00 CT reopen), in the thin '
      '2008–2012 overnight book and in the 2008 and 2020 stress periods; retail all-in commissions are often $4–5 per '
      f'round trip. A stress column at {COST_STRESS_PT} pt (2 ticks + commission) is added (post hoc). No news-calendar or '
      'FOMC filter was applied: recurring release times are absorbed only by the 30-minute matching bucket.')
    A('')
    A(f'gross = mean s·(C[t+n] − O[t+1]) in points; net = gross − {COST_PT}; opp net = −gross − {COST_PT} (the opposite '
      'rule); p net / p opp = clustered TWO-SIDED test of net = 0 (columns p_net_eq0 / p_opp_net_eq0; a small p can '
      'mean significantly NEGATIVE); p>0 / q>0 = one-sided test of net > 0 and its BH q-value over all full-sample rule '
      f'cells of both timeframes and both directions ({meta.get("costs_one_sided_bh", {}).get("cells", "—")} cells); '
      f'net 2t = net at the {COST_STRESS_PT} pt stress cost; valid = share of the class\'s signals with a valid window at '
      'that horizon (long horizons lose the events near the cash close to the session end, unevenly by era: section '
      '11.5, so the population changes with the horizon); cost σ = mean cost in σ-units; net σ = mean(σ return − cost '
      'σ), the scale-free version (point means weigh the later, higher-priced years more). Overlapping trades are all '
      'counted (no position management).')
    A('')
    for i, tf in enumerate(tfs, 1):
        C = R[tf]['costs']
        A(f'### 6.{i} {TF_NAME[tf]}')
        A('')
        A(md_table(C[C.split == 'full'], ['class', 'h_min', 'n', 'valid_share', 'gross_pts', 'se_pts', 'net_pts',
                                          'p_net_eq0', 'p_net_gt0_1s', 'q_net_1s', 'net_pts_stress', 'opp_net_pts',
                                          'p_opp_net_eq0', 'p_opp_net_gt0_1s', 'q_opp_net_1s', 'opp_net_pts_stress',
                                          'win_net', 'win_net_opp', 'cost_sig_mean', 'net_sig', 'opp_net_sig'],
                   {'h_min': 'int', 'n': 'int', 'valid_share': 'pct', 'p_net_eq0': 'p', 'p_opp_net_eq0': 'p',
                    'p_net_gt0_1s': 'p', 'p_opp_net_gt0_1s': 'p', 'q_net_1s': 'p', 'q_opp_net_1s': 'p',
                    'win_net': 'pct', 'win_net_opp': 'pct'},
                   {'h_min': 'h', 'valid_share': 'valid', 'gross_pts': 'gross pts', 'se_pts': 'SE',
                    'net_pts': 'net pts', 'p_net_eq0': 'p net', 'p_net_gt0_1s': 'p>0', 'q_net_1s': 'q>0',
                    'net_pts_stress': 'net 2t', 'opp_net_pts': 'opp net pts', 'p_opp_net_eq0': 'p opp',
                    'p_opp_net_gt0_1s': 'p>0 opp', 'q_opp_net_1s': 'q>0 opp', 'opp_net_pts_stress': 'opp net 2t',
                    'win_net': 'win net', 'win_net_opp': 'win opp', 'cost_sig_mean': 'cost σ', 'net_sig': 'net σ',
                    'opp_net_sig': 'opp net σ'}))
        A('')
        A('By half, 30 min:')
        A('')
        A(md_table(C[(C.split != 'full') & (C.h_min == PRIMARY_H)],
                   ['class', 'split', 'n', 'gross_pts', 'se_pts', 'net_pts', 'opp_net_pts', 'cost_sig_mean', 'net_sig',
                    'opp_net_sig'],
                   {'n': 'int'}, {'gross_pts': 'gross pts', 'se_pts': 'SE', 'net_pts': 'net pts',
                                  'opp_net_pts': 'opp net pts', 'cost_sig_mean': 'cost σ', 'net_sig': 'net σ',
                                  'opp_net_sig': 'opp net σ'}))
        A('')

    # 7 ── stability
    A('## 7. Stability at 30 min')
    A('')
    A('mean = signed σ return; matched diff = event − matched control (section 4), both clustered by day; q = BH over '
      'the table (flag only). Per-year signs: years 2008 → 2026 in order, years without events skipped; sign test '
      'against 50%.')
    A('')
    for i, tf in enumerate(tfs, 1):
        A(f'### 7.{i} {TF_NAME[tf]}')
        A('')
        A(md_table(R[tf]['stability'], ['class', 'split', 'n', 'days', 'mean', 'se', 'p', 'q_table', 'hit_nz',
                                        'matched_diff', 'matched_se', 'matched_p'],
                   {'n': 'int', 'days': 'int', 'p': 'p', 'q_table': 'p', 'hit_nz': 'pct', 'matched_p': 'p'},
                   {'mean': 'mean σ', 'q_table': 'q', 'hit_nz': 'hit ≠0', 'matched_diff': 'matched diff',
                    'matched_se': 'SE m', 'matched_p': 'p m'}))
        A('')
        A(md_table(R[tf]['per_year_summary'], ['class', 'years_with_events', 'years_positive', 'sign_test_p', 'signs'],
                   {'years_with_events': 'int', 'years_positive': 'int', 'sign_test_p': 'p'},
                   {'years_with_events': 'years', 'years_positive': 'positive', 'sign_test_p': 'p (sign)'}))
        A('')

    # 8 ── Z calibration
    A('## 8. Z calibration and gate on ES')
    A('')
    A('Bars with Z and zCalOk (≥ 2N previous D values), as in the indicator\'s frequency tip. Normal reference: '
      'P(|Z| ≥ 2) = 4.55%, P(|Z| ≥ 3) = 0.27%. Gate open = share of hqOk bars. ρ = lagged ρ̂ over hqOk bars. '
      'blocks = contiguous runs of |Z| ≥ 2. RTH = 08:30–15:15 CT.')
    A('')
    Zc = pd.concat([R[tf]['zcal'] for tf in tfs], ignore_index=True)
    A(md_table(Zc, ['tf', 'split', 'bars_Z_calOk', 'P_absZ_ge2', 'P_absZ_ge3', 'P_Z_ge2', 'P_Z_le_m2', 'mean_Z', 'rms_Z',
                    'blocks_absZ_ge2', 'gate_open_share', 'P_absZ_ge2_gate', 'z_alerts_up', 'z_alerts_dn'],
               {'tf': 'int', 'bars_Z_calOk': 'int', 'P_absZ_ge2': 'pct2', 'P_absZ_ge3': 'pct2', 'P_Z_ge2': 'pct2',
                'P_Z_le_m2': 'pct2', 'gate_open_share': 'pct', 'P_absZ_ge2_gate': 'pct2', 'blocks_absZ_ge2': 'int',
                'z_alerts_up': 'int', 'z_alerts_dn': 'int'},
               {'bars_Z_calOk': 'bars', 'P_absZ_ge2': 'P(|Z|≥2)', 'P_absZ_ge3': 'P(|Z|≥3)', 'P_Z_ge2': 'P(Z≥2)',
                'P_Z_le_m2': 'P(Z≤−2)', 'blocks_absZ_ge2': 'blocks', 'gate_open_share': 'gate open',
                'P_absZ_ge2_gate': 'P(|Z|≥2 | gate)', 'z_alerts_up': 'alerts up', 'z_alerts_dn': 'alerts dn'}))
    A('')
    A(md_table(Zc, ['tf', 'split', 'bars_hq_ok', 'rho_p05', 'rho_p10', 'rho_p25', 'rho_p50', 'rho_p75', 'rho_p90',
                    'rho_p95', 'P_rho_lt_0.30', 'P_rho_lt_0.196', 'P_rho_lt_0'],
               {'tf': 'int', 'bars_hq_ok': 'int', 'P_rho_lt_0.30': 'pct2', 'P_rho_lt_0.196': 'pct2',
                'P_rho_lt_0': 'pct2'},
               {'bars_hq_ok': 'hqOk bars', 'rho_p05': 'ρ p5', 'rho_p10': 'ρ p10', 'rho_p25': 'ρ p25',
                'rho_p50': 'ρ p50', 'rho_p75': 'ρ p75', 'rho_p90': 'ρ p90', 'rho_p95': 'ρ p95',
                'P_rho_lt_0.30': 'P(ρ<0.30)', 'P_rho_lt_0.196': 'P(ρ<0.196)', 'P_rho_lt_0': 'P(ρ<0)'}))
    A('')
    A('Per year:')
    A('')
    Zy = pd.concat([R[tf]['zcal_year'] for tf in tfs], ignore_index=True)
    A(md_table(Zy, ['tf', 'year', 'bars_Z_calOk', 'P_absZ_ge2', 'P_absZ_ge3', 'mean_Z', 'gate_open_share', 'rho_p50',
                    'P_rho_lt_0.30', 'z_alerts_up', 'z_alerts_dn'],
               {'tf': 'int', 'year': 'int', 'bars_Z_calOk': 'int', 'P_absZ_ge2': 'pct2', 'P_absZ_ge3': 'pct2',
                'gate_open_share': 'pct', 'P_rho_lt_0.30': 'pct2', 'z_alerts_up': 'int', 'z_alerts_dn': 'int'},
               {'bars_Z_calOk': 'bars', 'P_absZ_ge2': 'P(|Z|≥2)', 'P_absZ_ge3': 'P(|Z|≥3)', 'gate_open_share': 'gate',
                'rho_p50': 'ρ median', 'P_rho_lt_0.30': 'P(ρ<0.30)', 'z_alerts_up': 'up', 'z_alerts_dn': 'dn'}))
    A('')

    # 9 / 10 ── notes
    A('## 9. Implementation choices (fixed before any outcome was computed; the matched-control item as corrected after '
      'the review, section 10)')
    A('')
    for s in IMPLEMENTATION_NOTES:
        A(f'- {s}')
    A('')
    A('## 10. Deviations from the plan')
    A('')
    if DEVIATIONS:
        for s in DEVIATIONS:
            A(f'- {s}')
    else:
        A('None.')
    A('')
    # 11 ── post hoc (after the review)
    A('## 11. Post-hoc sensitivities (added after the external review)')
    A('')
    A('Everything in this section was added after the results and the review were seen. It is descriptive or '
      'sensitivity analysis: nothing here is confirmatory, and none of it changes a pre-registered number. q-values, '
      'where shown, are BH within the table slice named in the text (a flag only).')
    A('')
    # 11.1 alternative matched controls
    A('### 11.1 Alternative matched controls (30 min)')
    A('')
    A(f'Same machinery as section 4 (same-class events removed, control-mean error in the SE), other cells. **P_K bins**: '
      f'year × RTH/ETH × 30-min bucket × {PK_BINS} quantile bins of the K-bar price leg P_K, the leg that defines the Z '
      'classes (the pre-registered cells match the 15-minute move pE, not P_K). **Exact bar slot**: the pre-registered '
      'cells with the exact bar of the day instead of the 30-minute bucket (the post-close drift differs between slots '
      'of the same bucket: 11.2). q = BH over the 18 sets of each design.')
    A('')
    for tf in tfs:
        T = R[tf]['matched_sens']
        if len(T):
            T = _ci_col(T)
            A(f'**{TF_NAME[tf]}**')
            A('')
            A(md_table(T, ['design', 'set', 'n_matched', 'median_controls', 'event_mean', 'control_mean', 'diff', 'se',
                           'p', 'q_30m', 'CI_boot', 'abs_diff', 'abs_diff_p'],
                       {'n_matched': 'int', 'median_controls': 'int', 'p': 'p', 'q_30m': 'p', 'abs_diff_p': 'p'},
                       {'n_matched': 'n', 'median_controls': 'ctrl/ev', 'event_mean': 'event σ',
                        'control_mean': 'control σ', 'q_30m': 'q', 'abs_diff': '|σ| diff', 'abs_diff_p': 'p |σ|'}))
            A('')
    # 11.2 settlement minute
    A('### 11.2 The 14:59 CT settlement minute and absorbed / pinned events (30 min)')
    A('')
    fid = {}
    try:
        fs = json.load(open(studyenv.results_dir('fidelity') / 'fidelity_summary.json'))
        ti = fs['topstepx_info']['es']
        fid = {'share': ti['settlement_minute_volume_share'], 'c_all': ti['1m_raw_corr_cr1m_cr1s_all'],
               'c_ex': ti['1m_raw_corr_cr1m_cr1s_excl_settlement_minute'],
               'rec': fs['event_overlap_pooled']['5m_cr1m_vs_true_flow_events_pm_ke']['recall']}
    except Exception:   # noqa: BLE001 — the fidelity study is optional here
        fid = {}
    A('Mechanism (a hypothesis, not tested as such): the 14:59 CT minute (CME equity-index settlement window, NYSE '
      'closing auction) carries a large and growing share of the session volume (table below). Under the TradingView '
      'Auto candle rule the WHOLE volume of that one 1-minute candle is given to one side, by the sign of its close − '
      'open. An event window that contains this minute therefore gets a large |Δ| whose side is set by a single candle, '
      'and a flow shock (|zF| ≥ 2) with little price move: an "absorption" or "pinned" label that is at least partly an '
      'artefact of the delta estimator, not only of intraday volume seasonality. '
      + (f'The fidelity study points the same way: on the TopstepX ES 2026 sample the 14:59 CT minute holds '
         f'{100 * fid["share"]:.1f}% of the volume, and the 1-minute correlation of the candle-rule delta with the '
         f'1-second candle-rule delta is {fid["c_all"]:.2f} with that minute and {fid["c_ex"]:.2f} without it; on the '
         f'2013 tick sample the 5m flow-event recall of the 1-minute candle rule against the true aggressor delta is '
         f'{fid["rec"]:.2f} (±ke bars). ' if fid else '')
      + 'Events whose window (the ke bars ending at the event bar) contains the 14:59 minute are compared with the '
      'others, and the most frequent open / close bars are dropped; side = sign(14:59) is the share of the in-window '
      'events whose side equals the sign of that session\'s 14:59 candle-rule delta.')
    A('')
    if vol59 is not None and len(vol59):
        V = vol59.copy()
        A('Share of the clean-session volume traded in the 14:59 CT minute, by year: '
          + ', '.join(f'{int(r.year)} {100 * r.share_volume_1459:.1f}%' for r in V.itertuples()) + '.')
        A('')
    for tf in tfs:
        T = R[tf]['settle']
        if not len(T):
            continue
        A(f'**{TF_NAME[tf]}**')
        A('')
        A(md_table(T, ['class', 'subset', 'n_signals', 'share_of_class', 'n', 'mean', 'se', 'p', 'hit_nz',
                       'matched_diff', 'matched_p', 'slot_matched_diff', 'slot_matched_p', 'side_eq_sign1459'],
                   {'n_signals': 'int', 'n': 'int', 'share_of_class': 'pct', 'p': 'p', 'hit_nz': 'pct',
                    'matched_p': 'p', 'slot_matched_p': 'p', 'side_eq_sign1459': 'pct'},
                   {'n_signals': 'signals', 'share_of_class': 'share', 'mean': 'mean σ', 'hit_nz': 'hit ≠0',
                    'matched_diff': 'matched diff', 'matched_p': 'p m', 'slot_matched_diff': 'slot-matched diff',
                    'slot_matched_p': 'p slot', 'side_eq_sign1459': 'side = sign(14:59)'}))
        A('')
        D = R[tf]['slot_drift']
        if len(D):
            A(f'Unconditional long σ return at 30 min by exact bar slot, all candidate bars ({tf}m): '
              + ', '.join(f'{r.slot_ct} {r.mean:+.3f} (p {_fmt(r.p, "p")})' for r in D.itertuples()) + '.')
            A('')
    # 11.3 latency
    A('### 11.3 Entry latency (30 min)')
    A('')
    A('Entry at the close of the 1st or 2nd one-minute intrabar after the alert bar closes, instead of the first print '
      '(delay 0, the plan). Exit, σ scale and windows unchanged. drift = mean s·(delayed entry − O[t+1]) in points: how '
      'far the price moved in the signal\'s direction while waiting (positive = a worse entry for the "trade s" rule). '
      'BH within each delay over the 16 classes.')
    A('')
    for tf in tfs:
        T = R[tf]['latency']
        if not len(T):
            A(f'{TF_NAME[tf]}: not computed (DATA_DIR was not set).')
            A('')
            continue
        summ = []
        for d, g in T.groupby('delay_min'):
            summ.append(f'delay {int(d)} min: {int(g.fdr.map(_as_bool).fillna(False).sum())} of {len(g)} under BH, '
                        f'smallest p {_fmt(g.p.min(), "p")}, smallest q {_fmt(g.q.min(), "p")}')
        A(f'**{TF_NAME[tf]}**: ' + '; '.join(summ) + '.')
        A('')
        W = T.pivot(index='class', columns='delay_min', values=['n', 'mean', 'p', 'entry_drift_pts']).reindex(CLASS_KEYS)
        W.columns = [f'{a}_{b}' for a, b in W.columns]
        W = W.reset_index()
        cols = ['class'] + [f'{a}_{d}' for d in LATENCY_MIN for a in ('n', 'mean', 'p')] + \
            [f'entry_drift_pts_{d}' for d in LATENCY_MIN if d]
        kinds = {f'n_{d}': 'int' for d in LATENCY_MIN} | {f'p_{d}': 'p' for d in LATENCY_MIN} | \
            {f'entry_drift_pts_{d}': 'f2' for d in LATENCY_MIN}
        ren = {f'n_{d}': f'n d{d}' for d in LATENCY_MIN} | {f'mean_{d}': f'σ d{d}' for d in LATENCY_MIN} | \
            {f'p_{d}': f'p d{d}' for d in LATENCY_MIN} | {f'entry_drift_pts_{d}': f'drift d{d} pts' for d in LATENCY_MIN}
        A(md_table(W, cols, kinds, ren))
        A('')
    # 11.4 resolutions born in an earlier session
    A('### 11.4 Resolutions of absorptions born in an earlier session')
    A('')
    A('The life of a pending absorption is counted in bars, so it survives the daily maintenance break and weekends; '
      'the 17:00 CT reopen gap can then break H0/L0 and trigger a "continuation" or "held" alert that a trader would '
      'not read as a flow resolution (and the reopen book is the thinnest of the day). Signed σ return at 30 min; '
      'first bar = resolutions on the first bar of the session. All horizons in `prior_res_{tf}m.csv`.')
    A('')
    for tf in tfs:
        T = R[tf]['prior_res']
        if not len(T):
            continue
        T = T[T.h_min == PRIMARY_H]
        A(f'**{TF_NAME[tf]}**')
        A('')
        A(md_table(T, ['class', 'subset', 'n_signals', 'on_first_bar', 'n', 'days', 'mean', 'se', 'p'],
                   {'n_signals': 'int', 'on_first_bar': 'int', 'n': 'int', 'days': 'int', 'p': 'p'},
                   {'n_signals': 'signals', 'on_first_bar': 'first bar', 'mean': 'mean σ'}))
        A('')
    # 11.5 window survival
    A('### 11.5 Window survival by era')
    A('')
    A('Share of the signals whose outcome window is valid at 60 min (the longest horizon), by era. The session-end '
      'layout changed over the sample (in these data the last bar of the session opens at 16:15 CT until 2012, 16:00 '
      'in 2013–14 and 15:45 from 2016; the 15:15–15:30 CT halt removes the 15:15 bar until mid-2021), so a 60-minute '
      'window that starts near the cash close crosses the session end in some eras and not in others: for events '
      'clustered at the close, the 60-minute cell is a different population from the 30-minute cell. All horizons in '
      '`survival_{tf}m.csv`.')
    A('')
    for tf in tfs:
        T = R[tf]['survival']
        if not len(T):
            continue
        hmax = int(T.h_min.max())
        T = T[T.h_min == hmax]
        W = T.pivot_table(index=['class', 'subset'], columns='era', values='valid_share', aggfunc='first')
        Nn = T.pivot_table(index=['class', 'subset'], columns='era', values='n_signals', aggfunc='first')
        W = W.reindex(columns=['all years'] + [e[0] for e in ERAS])
        W.columns = [f'valid {c}' for c in W.columns]
        W['signals'] = Nn['all years']
        W = W.reset_index()
        W['class'] = pd.Categorical(W['class'], CLASS_KEYS, ordered=True)
        W = W.sort_values(['class', 'subset'])
        W['class'] = W['class'].astype(str)
        W = W[W.signals > 0]
        A(f'**{TF_NAME[tf]}**, {hmax} min')
        A('')
        vc = [c for c in W.columns if c.startswith('valid ')]
        A(md_table(W, ['class', 'subset', 'signals'] + vc, {'signals': 'int'} | {c: 'pct' for c in vc}))
        A('')

    A('## Files')
    A('')
    for fn in sorted(p.name for p in res_dir().glob('*.csv')):
        A(f'- `{fn}`')
    A('- `run_meta.json`: parameters, windows, checks, matching cut-points, runtimes. `run.log`: run log. '
      '`interpretation.md`: the summary at the top of this file. `CHANGELOG.md`: changes after the external review and '
      'how each result moved.')
    A('')
    (res_dir() / 'results.md').write_text('\n'.join(L))


TABLES = ['counts', 'tod', 'classes', 'twins', 'matched', 'baseline', 'costs', 'stability', 'per_year',
          'per_year_summary', 'zcal', 'zcal_year', 'gate', 'gate_diff',
          # post hoc (after the review)
          'matched_sens', 'settle', 'slot_drift', 'prior_res', 'survival', 'latency']


def _read_csv(fn: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(fn)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def main():
    global REBUILD_FEATURES
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--tf', type=int, nargs='+', default=[5, 15])
    ap.add_argument('--boot', type=int, default=10000, help='bootstrap replicates for the primary endpoint')
    ap.add_argument('--boot-other', type=int, default=2000, help='bootstrap replicates elsewhere')
    ap.add_argument('--report-only', action='store_true', help='rebuild results.md from the saved CSV files')
    ap.add_argument('--rebuild-features', action='store_true',
                    help='rebuild a missing ES feature file from DATA_DIR (opt-in; the feature folder must lie outside '
                         'any git work tree)')
    a = ap.parse_args()
    REBUILD_FEATURES = a.rebuild_features
    rd = res_dir()
    rd.mkdir(parents=True, exist_ok=True)
    log_f = open(rd / 'run.log', 'a')

    def log(msg):
        line = f'{time.strftime("%H:%M:%S")} {msg}'
        print(line, flush=True)
        log_f.write(line + '\n')
        log_f.flush()

    R = {}
    if a.report_only:
        meta = json.load(open(rd / 'run_meta.json'))
        for tf in a.tf:
            R[tf] = {nm: _read_csv(rd / f'{nm}_{tf}m.csv') for nm in TABLES}
            R[tf]['meta'] = meta['tf'][str(tf)]
            for k in ('fdr_30m', 'fdr_table', 'fdr'):
                for nm in TABLES:
                    if k in R[tf][nm].columns:
                        R[tf][nm][k] = R[tf][nm][k].map(_as_bool)
        write_report(R, meta, _read_csv(rd / 'settle_minute_volume.csv'))
        return
    t0 = time.time()
    m1 = load_1m_clean()
    log('1-minute file loaded for the post-hoc latency / settlement analyses' if m1 is not None
        else 'DATA_DIR not set: post-hoc analyses that need the 1-minute file are skipped')
    vol59 = settle_volume_table(m1) if m1 is not None else pd.DataFrame()
    for tf in a.tf:
        R[tf] = run_tf(tf, a.boot if tf == PRIMARY_TF else a.boot_other, a.boot_other, log, m1)
    del m1
    cbh = costs_bh(R)
    for tf in a.tf:
        for nm in TABLES:
            R[tf][nm].to_csv(rd / f'{nm}_{tf}m.csv', index=False)
    vol59.to_csv(rd / 'settle_minute_volume.csv', index=False)
    meta = {'generated': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'python': platform.python_version(),
            'numpy': np.__version__, 'pandas': pd.__version__, 'feature_dir': str(feat_dir()),
            'params_default': E.Params().to_dict(), 'horizons_min': HORIZONS_MIN, 'primary': {'tf': PRIMARY_TF,
            'h_min': PRIMARY_H, 'fdr_q': FDR_Q}, 'cost_pt': COST_PT, 'cost_stress_pt': COST_STRESS_PT,
            'costs_one_sided_bh': cbh, 'split_year': SPLIT_YEAR, 'rth_ct': RTH_CT,
            'boot': {'primary': a.boot, 'other': a.boot_other, 'seed': SEED}, 'min_ctrl': MIN_CTRL,
            'gate_variants': GATE_VARIANTS, 'posthoc': {'settle_ct_min': SETTLE_CT_MIN, 'open_close_bars': OPEN_CLOSE_BARS,
            'eras': ERAS, 'latency_min': LATENCY_MIN, 'pk_bins': PK_BINS},
            'runtime_s': round(time.time() - t0, 1), 'tf': {str(tf): R[tf]['meta'] for tf in R}}
    json.dump(meta, open(rd / 'run_meta.json', 'w'), indent=1, default=str)
    write_report(R, meta, vol59)
    log(f'done in {time.time() - t0:.0f}s → {rd / "results.md"}')


if __name__ == '__main__':
    main()
