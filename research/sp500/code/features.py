#!/usr/bin/env python3
"""Per-bar feature files: chart bars (bars.py) + every indicator output of the port (engine.py).

One parquet per (instrument, chart timeframe, delta variant[, gate variant]) in OUT_DIR/features, plus a JSON sidecar
with the parameters, the windows (ke, life, hqNeed), the data selection and the runtime. features/manifest.json lists
all files.

Datasets (default `all`):
  es_{5,15}m_cr1m          ES front month 2008–2026, clean sessions, 1-minute candle-rule delta, tier 2
  mes_{5,15}m_cr1m         MES 2021–2026, clean sessions, tier 2
  spy_{5,15}m_cr1m         SPY 2000–2026, regular + extended hours in ONE stream (rth column marks 09:30–16:00 ET;
                           session = ET calendar day, so the session's first bar is the first extended-hours bar),
                           August 2016 dropped, tier 2
  es_tick_{1,5,15}m_{true,cr1s,cr1m}
                           2013-09 Tick Data sample (15 sessions, roll session 2013-09-13 kept and flagged):
                           true = quote-rule aggressor delta, tier 3 (as 1T on TradingView);
                           cr1s = candle rule on 1-second bars, tier 3 (1S + candle rule);
                           cr1m = candle rule on 1-minute bars, tier 2. On the 1-minute chart cr1m is the bar's own
                           candle (Pine would give tier 1 and no statistics: computed here AS IF tier 2, column
                           pine_tier = 1 says so).
Gate variants (study hook): --gate off (gateOn = hqOk) or --rho-min X; the file name gets _gateoff / _rhomin<X>.

Usage: python3 -I features.py [all | es | mes | spy | es_tick | <dataset name>] [--gate off] [--rho-min 0.2]
Env (required, no defaults; see studyenv.py): DATA_DIR (clean 1-minute files), OUT_DIR (study folder) or
FEAT_DIR (feature folder). The feature folder is refused inside a git work tree (licensed per-bar data).
"""
from __future__ import annotations

import argparse
import json
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

# name → (instrument, tf_min, delta column, configured tier, pine tier)
DATASETS = {}
for tf in (5, 15):
    for inst in ('es', 'mes', 'spy'):
        DATASETS[f'{inst}_{tf}m_cr1m'] = (inst, tf, 'd_cr1m', 2, 2)
for tf in (1, 5, 15):
    DATASETS[f'es_tick_{tf}m_true'] = ('es_tick', tf, 'd_true', 3, 3)
    DATASETS[f'es_tick_{tf}m_cr1s'] = ('es_tick', tf, 'd_cr1s', 3, 3)
    DATASETS[f'es_tick_{tf}m_cr1m'] = ('es_tick', tf, 'd_cr1m', 2, 1 if tf == 1 else 2)

# extra bar-building options per dataset
for tf in (5, 15):
    DATASETS[f'spy_{tf}m_cr1m_rthonly'] = ('spy', tf, 'd_cr1m', 2, 2)
OPTS = {f'spy_{tf}m_cr1m_rthonly': {'rth_only': True} for tf in (5, 15)}

BAR_COLS = ['t', 'session_date', 'session_first', 'rth', 'o', 'h', 'l', 'c', 'v', 'n_1m', 'contract', 'adj_offset',
            'contract_change', 'roll_session', 'clean_session']


def build_dataset(name: str, params: E.Params, suffix: str = '', cache: dict | None = None):
    inst, tf, dcol, tier, pine_tier = DATASETS[name]
    t0 = time.time()
    opts = OPTS.get(name, {})
    key = (inst, tf, tuple(sorted(opts.items())))
    if cache is not None and key in cache:
        b = cache[key]
    else:
        b = B.build(inst, tf, **opts)
        if cache is not None:
            cache[key] = b
    t1 = time.time()
    p = E.Params(**{**params.to_dict(), 'tf_sec': tf * 60})
    eng = E.run_engine(pd.DataFrame({
        'open': b.o.to_numpy(float), 'high': b.h.to_numpy(float), 'low': b.l.to_numpy(float), 'close': b.c.to_numpy(float),
        'volume': b.v.to_numpy(float), 'delta': b[dcol].to_numpy(float), 'session_first': b.session_first.to_numpy(),
        'tier': tier}), p)
    t2 = time.time()
    out = b[[c for c in BAR_COLS if c in b.columns]].copy()
    out.insert(0, 'bar', np.arange(len(out), dtype=np.int64))       # bar_index (lq_bar, ev_res_bar refer to it)
    out['delta_src'] = b[dcol].to_numpy()
    if inst == 'es_tick':                                   # keep the other estimators for comparisons
        for c in ('d_true', 'd_cr1s', 'd_cr1m'):
            out[c] = b[c].to_numpy()
    out['pine_tier'] = np.int8(pine_tier)
    eng = eng.drop(columns=['delta'])
    for c in eng.columns:
        out[c] = eng[c].to_numpy()
    FEAT = studyenv.feat_dir()
    FEAT.mkdir(parents=True, exist_ok=True)
    fn = FEAT / f'{name}{suffix}.parquet'
    out.to_parquet(fn, index=False, compression='zstd')
    t3 = time.time()
    meta = {
        'file': fn.name, 'dataset': name, 'instrument': inst, 'tf_min': tf, 'delta_variant': dcol, 'tier_used': tier,
        'pine_tier': pine_tier, 'sessions': 'clean' if inst in ('es', 'mes') else ('all except Aug 2016' if inst == 'spy' else 'all (roll session flagged)'),
        'rth_only': bool(opts.get('rth_only', False)),
        'rows': int(len(out)), 'n_sessions': int(out.session_first.sum()), 'first_bar': str(out.t.iloc[0]), 'last_bar': str(out.t.iloc[-1]),
        'params': p.to_dict(), 'ke': eng.attrs['ke'], 'life': eng.attrs['life'], 'hq_need': eng.attrs['hq_need'],
        'rho_min_eff': eng.attrs['rho_min_eff'],
        'counts': {k: int(out[k].sum()) for k in ('new_abs', 'new_pin', 'new_pwf', 'res_cont', 'res_held', 'res_exp', 'sup',
                                                  'al_z_up', 'al_z_dn', 'piv_top', 'piv_bot', 'gate', 'hq_ok')},
        'z_defined': int(out.Z.notna().sum()),
        'runtime_s': {'bars': round(t1 - t0, 2), 'engine': round(t2 - t1, 2), 'write': round(t3 - t2, 2)},
        'columns': list(out.columns),
    }
    json.dump(meta, open(fn.with_suffix('.json'), 'w'), indent=1, default=str)
    print(json.dumps({k: meta[k] for k in ('file', 'rows', 'n_sessions', 'counts', 'runtime_s')}), flush=True)
    return meta


def update_manifest():
    items = []
    FEAT = studyenv.feat_dir()
    for j in sorted(FEAT.glob('*.json')):
        if j.name == 'manifest.json':
            continue
        m = json.load(open(j))
        items.append({k: m[k] for k in ('file', 'dataset', 'instrument', 'tf_min', 'delta_variant', 'tier_used', 'pine_tier',
                                        'sessions', 'rows', 'n_sessions', 'first_bar', 'last_bar', 'ke', 'life', 'hq_need',
                                        'rho_min_eff', 'counts', 'runtime_s')} | {'gate': m['params']['gate']})
    json.dump({'generated_by': 'features.py', 'column_doc': COLUMN_DOC, 'files': items}, open(FEAT / 'manifest.json', 'w'),
              indent=1, default=str)


COLUMN_DOC = {
    'bar': 'bar_index of the stream (row position)', 't': 'chart bar open time (UTC)', 'session_date': 'session label of the clean file (CME: date of the session opening '
    '17:00 CT the evening before; SPY: ET date)', 'session_first': 'session.isfirstbar (first chart bar of the session in '
    'the stream)', 'rth': 'bar open in 09:30–16:00 ET', 'o/h/l/c': 'unadjusted prices (add adj_offset for Panama)',
    'v': 'chart volume', 'n_1m': '1-minute bars in the chart bar', 'contract_change': 'contract differs from previous bar',
    'delta_src': 'per-bar delta fed to the indicator', 'pine_tier': 'tier TradingView would assign with this source',
    'gap_bar': 'r uses ln(C/O) (session first bar or |ln(O/C1)| > 3σ)', 'r_bar': 'price increment (bps)',
    'tier': 'quality used (after no-observation rule)', 'no_obs': 'no flow observation (source volume 0 or missing)',
    'hq_run': 'consecutive observations with tier ≥ 2', 'lq_bar': 'last observed bar index with tier < 2',
    'r/d': 'increments entering σ/ρ (na on no-observation bars)', 'sr_p/sd_p/rho_p': 'σr, σΔ, ρ lagged one bar',
    'ur/ud': 'clipped σ-units', 'hq_ok': 'statistics allowed (hqRun ≥ hqNeed)', 'D': 'divergence statistic',
    'rms_d': 'lagged RMS of D', 'n_cal_d': 'previous valid D values', 'Z': 'calibrated divergence Z',
    'z_cal_ok': 'n_cal_d ≥ 2N (Z alerts allowed)', 'gate': 'gateOn (hqOk and ρ ≥ ρmin; or hqOk with the gate off)',
    'p_leg/f_leg': 'P_K, F_K', 'fE/pE/zF/zP': 'event window statistics and their calibrated z', 'n_cal_e': 'previous valid '
    'fE values', 'ev_weak': 'nCalE < max(20·ke, 2N) (hollow, no alerts)', 'hollow': 'tier 2 or ev_weak',
    'hi_ke/lo_ke': 'highest high / lowest low over ke bars', 'absorbed/pinned/pwf': 'class membership on the bar',
    '*_new_cl': 'first bar of a cluster (class and side, refractory ke observations)', 'new_abs/new_pin/new_pwf':
    'new event (tier rule applied)', 'pin_in_cl': 'pinned inside the pending absorption cluster', 'ev_side/pin_side/pwf_side':
    '+1/−1 side on the new-event bar', 'ev_h0/ev_l0': 'H0/L0 of the new absorption', 'ev_outcome': 'on the absorption bar: '
    '1 continuation, 2 held, 3 expired, 4 superseded, 0 still open at the end (KNOWN ONLY LATER: do not use as a feature)',
    'ev_res_bar': 'row index where that absorption ended (later)', 'pend_side': 'side of the pending absorption after the bar',
    'res_cont/res_held/res_exp': 'resolution on this bar', 'res_side': 'side of the resolved event', 'res_age': 'bars '
    'from event to resolution', 'res_low/res_weak': 'resolved event was hollow / weak', 'sup/sup_age': 'this new event '
    'superseded a pending one / its age', 'cross_up/cross_dn': 'first crossing with hysteresis (gate on)',
    'al_z_up/al_z_dn': 'Z alerts (cross and z_cal_ok)', 'al_abs/al_pin_o/al_pwf/al_res': 'event alerts (not ev_weak)',
    'cvd_c': 'continuous CVD', 'ph/pl': 'pivot value on the confirmation bar (pivot at t − R)', 'piv_top/piv_bot':
    'classical pivot divergence (confirmation bar)',
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('which', nargs='*', default=['all'])
    ap.add_argument('--gate', default='on', choices=['on', 'off'])
    ap.add_argument('--rho-min', type=float, default=None)
    a = ap.parse_args()
    names = []
    for w in a.which:
        if w == 'all':
            names += list(DATASETS)
        elif w in DATASETS:
            names.append(w)
        else:
            names += [n for n, v in DATASETS.items() if v[0] == w]
    p = E.Params(gate=a.gate == 'on')
    suffix = '' if a.gate == 'on' else '_gateoff'
    if a.rho_min is not None:
        p.rho_min = a.rho_min
        suffix += f'_rhomin{a.rho_min:g}'
    cache = {}
    for n in names:
        build_dataset(n, p, suffix, cache)
        inst = DATASETS[n][0]
        for k in [k for k in cache if k[0] != inst]:       # keep memory low: one instrument at a time
            cache.pop(k)
    update_manifest()


if __name__ == '__main__':
    main()
