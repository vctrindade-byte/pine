#!/usr/bin/env python3
"""Bar-by-bar check of the Python port (engine.py) against the REAL built Standard edition run in PineTS.

Pipeline for one slice of chart bars:
  1. bars.py builds the chart bars (per session, delta variant chosen);
  2. the per-bar delta is sent through the repository's test channel (tests/lib/channel.mjs): the ms of openTime carry
     code = round((q + 1)·499), q = clip(Δ/V, ±1), and the LTF stub returns 5 intrabars whose sum is the delta. The port is
     fed EXACTLY the delta the stub produces (same float64 operations, including PineTS's 10-decimal rounding of
     assigned values), so any difference is a difference of the engine, not of the input;
  3. bar times are remapped so that every session starts a new UTC day (PineTS's session.isfirstbar is a change of
     calendar day in the symbol timezone): session.isfirstbar = the session_first flag of the port. Times are not used
     by any of the compared outputs (they only move the line anchors, which are not compared);
  4. run_pine.mjs runs the instrumented script (observation-only plots + the script's own alertconditions);
  5. every compared value must agree: all flags identical, |ΔZ|, |ΔzF|, |ΔzP| < 1e-6 (relative tolerance on the other
     continuous series), alertcondition bar sets identical.

Usage (PineTS 0.11.0 from the repository's node_modules after `npm install`, or via NODE_PATH / PINETS_DIR;
PINE_REPO = repository root, default: the repository that contains this file):
  python3 -I validate_pine.py --inst es --tf 5 --start 2019-01-01 --end 2020-01-01 [--variant d_cr1m] [--prec auto]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
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

# Repository root: PINE_REPO, else the git work tree that holds this file (research/sp500/code → ../../..).
PINE_REPO = Path(os.environ.get('PINE_REPO', '').strip() or HERE.parents[2]).expanduser().resolve()
Q_SCALE = 499
WEIGHTS = (0.1, 0.15, 0.2, 0.25, 0.3)        # channel.mjs STUB_WEIGHTS, printed with toFixed(4)
BASE_MS = 946857600000                       # 2000-01-03 00:00 UTC (a Monday)


def js_round(y):
    """JavaScript Math.round (ties toward +∞), exact for doubles."""
    y = np.asarray(y, float)
    f = np.floor(y)
    return f + ((y - f) >= 0.5)


def pinets_precision(x):
    """PineTS Context.precision(value, 10): Math.round(value·1e10)/1e10 when |value|·1e10 < 2^53."""
    x = np.asarray(x, float)
    ok = np.abs(x) * 1e10 < 2.0 ** 53
    return np.where(ok, js_round(x * 1e10) / 1e10, x)


def channel(q, v_src, no_intra=None):
    """code (ms of openTime) and the delta that the Pine stub reconstructs from it (bit-exact).
    q = Δ/V of the variant; v_src = volume the stub gives the intrabars (chart volume, or 100 when it is na);
    no_intra: bars without intrabars (code 999: the stub returns empty arrays, the indicator falls back to BVC)."""
    q = np.clip(np.nan_to_num(np.asarray(q, float)), -1.0, 1.0)
    v = np.asarray(v_src, float)
    code = js_round((q + 1.0) * Q_SCALE).astype(np.int64)
    if no_intra is not None:
        code[no_intra] = 999
    d0 = pinets_precision(v * (code / float(Q_SCALE) - 1.0))       # float __d = __v * (__c / 499.0 - 1.0)
    s = d0 * WEIGHTS[0]
    for w in WEIGHTS[1:]:
        s = s + d0 * w                                                # array.sum: left to right
    d = pinets_precision(s)
    if no_intra is not None:
        d[no_intra] = np.nan
    return code, d


def klines(b: pd.DataFrame, code, tf_min):
    """PineTS klines with session-per-UTC-day times and the delta code in the milliseconds."""
    t = b.t.dt.as_unit('ns').array.asi8 // 1_000_000
    sess_ord = np.cumsum(b.session_first.to_numpy()) - 1
    first_t = pd.Series(t).groupby(sess_ord).transform('first').to_numpy()
    off = t - first_t
    if off.max() >= 86_400_000:
        raise ValueError('a session spans more than one day: the remap cannot keep session.isfirstbar exact')
    ot = BASE_MS + sess_ord * 86_400_000 + off
    rows = []
    o, h, l, c, v = (b[k].to_numpy(float) for k in ('o', 'h', 'l', 'c', 'v'))
    for i in range(len(b)):
        rows.append({'openTime': int(ot[i] + code[i]), 'closeTime': int(ot[i] + tf_min * 60_000 - 1),
                     'open': o[i], 'high': h[i], 'low': l[i], 'close': c[i],
                     'volume': v[i] if np.isfinite(v[i]) else None})          # null → NaN in run_pine.mjs
    return rows


# Pine input variable → engine.Params field (for --inputs)
INPUT_TO_PARAM = {'nIn': 'N', 'kIn': 'K', 'mIn': 'M', 'clipIn': 'clip', 'thrIn': 'thr', 'thr2In': 'thr2', 'rhoMinIn': 'rho_min',
                  'driftIn': 'drift', 'evIn': 'ev', 'pwfIn': 'pwf', 'evWinIn': 'ev_win_min', 'lifeIn': 'life_min', 'zfIn': 'zf',
                  'pinIn': 'pin', 'pinPIn': 'pin_p', 'lowConfIn': 'low_conf', 'pivLIn': 'piv_l', 'pivRIn': 'piv_r',
                  'pivMinIn': 'piv_min', 'pivMaxIn': 'piv_max', 'pivMagIn': 'piv_mag'}

ALERT_KEYS = {
    'Z ≥ +limiar (preço à frente do fluxo)': 'alZUp', 'Z ≤ −limiar (fluxo à frente do preço)': 'alZDn',
    'Fluxo comprador absorvido': 'alAbsB', 'Fluxo vendedor absorvido': 'alAbsS',
    'Preço travado sob compras extremas': 'alPinB', 'Preço travado sob vendas extremas': 'alPinS',
    'Compras absorvidas → continuação (alta)': 'alResCB', 'Vendas absorvidas → continuação (baixa)': 'alResCS',
    'Compras absorvidas → segurou (baixa)': 'alResHB', 'Vendas absorvidas → segurou (alta)': 'alResHS',
    'Preço sem fluxo (subida)': 'alPwfU', 'Preço sem fluxo (queda)': 'alPwfD',
    'Divergência por pivots (topo)': 'pivTop', 'Divergência por pivots (fundo)': 'pivBot',
}


def port_alert_sets(e: pd.DataFrame):
    zf = e.zF.to_numpy()
    zp = e.zP.to_numpy()
    sF = np.sign(np.nan_to_num(zf))
    sP = np.sign(np.nan_to_num(zp))
    ew = e.ev_weak.to_numpy().astype(bool)
    na_ = e.new_abs.to_numpy().astype(bool)
    npn = e.new_pin.to_numpy().astype(bool)
    npw = e.new_pwf.to_numpy().astype(bool)
    al_abs = na_ & ~ew
    al_res = e.al_res.to_numpy().astype(bool)
    rc, rh, rs = e.res_cont.to_numpy().astype(bool), e.res_held.to_numpy().astype(bool), e.res_side.to_numpy()
    s = {
        'alZUp': e.al_z_up.to_numpy().astype(bool), 'alZDn': e.al_z_dn.to_numpy().astype(bool),
        'alAbsB': al_abs & (sF > 0), 'alAbsS': al_abs & (sF < 0),
        'alPinB': npn & ~ew & (sF > 0), 'alPinS': npn & ~ew & (sF < 0),
        'alResCB': al_res & rc & (rs > 0), 'alResCS': al_res & rc & (rs < 0),
        'alResHB': al_res & rh & (rs > 0), 'alResHS': al_res & rh & (rs < 0),
        'alPwfU': npw & ~ew & (sP > 0), 'alPwfD': npw & ~ew & (sP < 0),
        'pivTop': e.piv_top.to_numpy().astype(bool), 'pivBot': e.piv_bot.to_numpy().astype(bool),
    }
    return {k: set(np.flatnonzero(v).tolist()) for k, v in s.items()}


# Pine instrumentation name → (port column, kind). kind: 'flag' | 'int' | 'f' (float, tolerance)
FLAG_MAP = {
    'hqOk': 'hq_ok', 'gapBar': 'gap_bar', 'noObs': 'no_obs', 'zCalOk': 'z_cal_ok', 'gateOn': 'gate', 'evWeak': 'ev_weak',
    'absorbed': 'absorbed', 'pinned': 'pinned', 'pwf': 'pwf', 'absNewCl': 'abs_new_cl', 'pinNewCl': 'pin_new_cl',
    'pwfNewCl': 'pwf_new_cl', 'newAbs': 'new_abs', 'newPin': 'new_pin', 'newPwf': 'new_pwf', 'resCont': 'res_cont',
    'resHeld': 'res_held', 'resExp': 'res_exp', 'crossUp': 'cross_up', 'crossDn': 'cross_dn', 'alZUp': 'al_z_up',
    'alZDn': 'al_z_dn', 'pivTop': 'piv_top', 'pivBot': 'piv_bot', 'alPinO': 'al_pin_o', 'hollow': 'hollow',
    'resWeak': 'res_weak', 'resLowC': 'res_low',
}
SERIES_MAP = {
    'rBar': ('r_bar', 'f'), 'delta': ('delta', 'f'), 'd': ('d', 'f'), 'r': ('r', 'f'), 'srP': ('sr_p', 'f'),
    'sdP': ('sd_p', 'f'), 'rhoP': ('rho_p', 'f'), 'ur': ('ur', 'f'), 'ud': ('ud', 'f'), 'dStat': ('D', 'f'),
    'rmsD': ('rms_d', 'f'), 'nCalD': ('n_cal_d', 'int'), 'zDiv': ('Z', 'f'), 'fE': ('fE', 'f'), 'pE': ('pE', 'f'),
    'zF': ('zF', 'f'), 'zP': ('zP', 'f'), 'nCalE': ('n_cal_e', 'int'), 'evSide': ('pend_side', 'int'),
    'resSide': ('res_side', 'int'), 'hqRun': ('hq_run', 'int'), 'lqBar': ('lq_bar', 'int'), 'tier': ('tier', 'int'),
    'cvdC': ('cvd_c', 'f'), 'ph': ('ph', 'f'), 'pl': ('pl', 'f'), 'hiKe': ('hi_ke', 'f'), 'loKe': ('lo_ke', 'f'),
    'pLeg': ('p_leg', 'f'), 'fLeg': ('f_leg', 'f'),
}


def check_labels(pine: dict, e: pd.DataFrame, R: int):
    """The indicator's own labels: one per new absorption (side, «preço travado» at the event, the mid-cluster pinned
    mark, the confidence suffix and the RESOLUTION appended later), per price-without-flow event and per pivot divergence.
    Checks each label against the port, and that the label sets are complete when fewer than max_labels_count = 500."""
    n = len(e)
    new_abs = e.new_abs.to_numpy().astype(bool)
    abs_bars = np.flatnonzero(new_abs)
    pin_cl = np.flatnonzero(e.pin_in_cl.to_numpy().astype(bool))
    has_pin_mark = np.zeros(n, dtype=bool)
    if len(pin_cl):
        owner = abs_bars[np.searchsorted(abs_bars, pin_cl, side='right') - 1]
        has_pin_mark[owner] = True
    exp = {'abs': set(abs_bars.tolist()), 'pwf': set(np.flatnonzero(e.new_pwf.to_numpy()).tolist()),
           'top': set((np.flatnonzero(e.piv_top.to_numpy()) - R).tolist()), 'bot': set((np.flatnonzero(e.piv_bot.to_numpy()) - R).tolist())}
    got = {k: set() for k in exp}
    bad = []
    oc_name = {1: '→ continuação', 2: '→ absorção segurou', 3: '→ expirou', 4: '→ substituído'}
    for lab in pine.get('labels', []):
        x, txt = int(lab['x']), lab['text']
        lines = txt.split('\n')
        head = lines[0]
        if head.startswith(('Compras absorvidas', 'Vendas absorvidas')):
            got['abs'].add(x)
            side = 1 if head.startswith('Compras') else -1
            oc = int(e.ev_outcome.iat[x])
            want_res = [l for l in lines[1:] if l.startswith('→')]
            exp_res = [] if oc == 0 else [oc_name[oc]]
            res_ok = len(want_res) == len(exp_res) and all(w.startswith(x_) for w, x_ in zip(want_res, exp_res))
            if res_ok and oc in (1, 2):
                up = (side > 0) if oc == 1 else (side < 0)
                res_ok = want_res[0].endswith('↑' if up else '↓')
            low = e.tier.iat[x] == 2
            sfx = ' (baixa conf.)' if low else (' (cal. prov.)' if e.ev_weak.iat[x] else '')
            checks = {'is_new_abs': bool(new_abs[x]), 'side': int(e.ev_side.iat[x]) == side,
                      'pinned_head': ('· preço travado' in head) == bool(e.pinned.iat[x]), 'suffix': head.endswith(sfx) if sfx else not head.endswith(')'),
                      'pin_mark': ('· preço travado' in lines[1:]) == bool(has_pin_mark[x]), 'resolution': res_ok}
            if not all(checks.values()):
                bad.append({'bar': x, 'text': txt, 'failed': [k for k, v in checks.items() if not v]})
        elif head.startswith('Preço ↑ sem fluxo') or head.startswith('Preço ↓ sem fluxo'):
            got['pwf'].add(x)
            side = 1 if '↑' in head else -1
            if not (e.new_pwf.iat[x] and int(e.pwf_side.iat[x]) == side):
                bad.append({'bar': x, 'text': txt, 'failed': ['pwf']})
        elif head.startswith('Topo sem confirmação'):
            got['top'].add(x)
        elif head.startswith('Fundo sem confirmação'):
            got['bot'].add(x)
    total_exp = sum(len(v) for v in exp.values())
    complete = total_exp <= 500
    res = {'labels': len(pine.get('labels', [])), 'expected': total_exp, 'complete_set_checked': complete,
           'bad': bad[:10], 'n_bad': len(bad)}
    for k in exp:
        res[k] = {'pine': len(got[k]), 'port': len(exp[k]), 'only_pine': sorted(got[k] - exp[k])[:5],
                  'only_port': sorted(exp[k] - got[k])[:5] if complete else []}
    res['ok'] = not bad and all(not res[k]['only_pine'] and not res[k]['only_port'] for k in exp)
    return res


def compare(pine: dict, e: pd.DataFrame, warm: int):
    n = len(e)
    rep = {'n': n, 'warmup_bars': warm, 'flags': {}, 'series': {}, 'alertconditions': {}, 'ok': True}
    fl = np.array([np.nan if v is None else v for v in pine['series']['flags']], float).astype(np.int64)
    names = pine['flags']
    for i, nm in enumerate(names):
        if nm not in FLAG_MAP:
            continue
        pv = ((fl >> i) & 1).astype(bool)
        mv = e[FLAG_MAP[nm]].to_numpy().astype(bool)
        bad = np.flatnonzero(pv != mv)
        rep['flags'][nm] = {'pine_true': int(pv.sum()), 'port_true': int(mv.sum()), 'mismatch': int(len(bad)),
                            'first_bad': bad[:5].tolist()}
        if len(bad):
            rep['ok'] = False
    for nm, (col, kind) in SERIES_MAP.items():
        pv = np.array([np.nan if v is None else v for v in pine['series'][nm]], float)
        mv = e[col].to_numpy().astype(float)
        nan_bad = np.flatnonzero(np.isfinite(pv) != np.isfinite(mv))
        both = np.isfinite(pv) & np.isfinite(mv)
        diff = np.abs(pv[both] - mv[both])
        scale = np.maximum(1.0, np.abs(mv[both]))
        rel = diff / scale
        r = {'defined_pine': int(np.isfinite(pv).sum()), 'defined_port': int(np.isfinite(mv).sum()),
             'na_mismatch': int(len(nan_bad)), 'first_na_bad': nan_bad[:5].tolist(),
             'max_abs': float(diff.max()) if diff.size else 0.0, 'max_rel': float(rel.max()) if rel.size else 0.0}
        aw = both.copy()
        aw[:warm] = False
        r['max_abs_after_warmup'] = float(np.abs(pv[aw] - mv[aw]).max()) if aw.any() else 0.0
        if kind == 'int':
            r['mismatch'] = int((diff != 0).sum())
            if r['mismatch'] or r['na_mismatch']:
                rep['ok'] = False
        else:
            tol = 1e-6
            r['tol'] = tol
            if r['na_mismatch'] or r['max_rel'] >= tol:
                rep['ok'] = False
        rep['series'][nm] = r
    got = {k: set() for k in ALERT_KEYS.values()}
    other = 0
    for a in pine['alerts']:
        if a['type'] == 'alertcondition':
            k = ALERT_KEYS.get(a['title'])
            if k:
                got[k].add(int(a['bar']))
        else:
            other += 1
    exp = port_alert_sets(e)
    for k in got:
        miss, extra = sorted(exp[k] - got[k]), sorted(got[k] - exp[k])
        rep['alertconditions'][k] = {'pine': len(got[k]), 'port': len(exp[k]), 'only_port': miss[:5], 'only_pine': extra[:5]}
        if miss or extra:
            rep['ok'] = False
    rep['alert_calls'] = other
    rep['labels'] = check_labels(pine, e, int(e.attrs['params']['piv_r']))
    if not rep['labels']['ok']:
        rep['ok'] = False
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--inst', default='es')
    ap.add_argument('--tf', type=int, default=5)
    ap.add_argument('--start', default=None)
    ap.add_argument('--end', default=None)
    ap.add_argument('--variant', default='d_cr1m')
    ap.add_argument('--prec', default='auto', help="Pine 'Precisão intrabar': auto → tier 2, s1 → tier 3")
    ap.add_argument('--nbars', type=int, default=0, help='keep only the first n bars of the slice')
    ap.add_argument('--tag', default=None)
    ap.add_argument('--reuse', action='store_true', help='reuse an existing PineTS output for the same tag')
    ap.add_argument('--inputs', default=None, help='JSON of Pine inputs to override, e.g. \'{"rhoMinIn": 0, "nIn": 50}\'')
    ap.add_argument('--sessions', default='clean', choices=['clean', 'all'], help="'all' keeps roll/unclean sessions")
    ap.add_argument('--stress', type=int, default=0, help='seed > 0: inject volume-0 bars (0.3%%), missing-volume bars, '
                    'bars without intrabars (BVC fallback, tier 1) and one 30-bar block without intrabars')
    a = ap.parse_args()
    tag = a.tag or f'{a.inst}_{a.tf}m_{a.variant}_{a.start}_{a.end}_{a.prec}'
    work = studyenv.work_dir()                  # per-bar inputs: refused inside a git work tree
    work.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    b = B.build(a.inst, a.tf, sessions=a.sessions)
    if a.start:
        b = b[b.session_date >= pd.Timestamp(a.start)]
    if a.end:
        b = b[b.session_date < pd.Timestamp(a.end)]
    if a.nbars:
        b = b.iloc[:a.nbars]
    b = B.mark_stream(b)
    v_orig = b.v.to_numpy(float)
    q = b[a.variant].to_numpy(float) / v_orig
    no_intra = np.zeros(len(b), dtype=bool)
    if a.stress:
        rng = np.random.default_rng(a.stress)
        n = len(b)
        vol = v_orig.copy()
        vol[rng.choice(n, int(0.003 * n), replace=False)] = 0.0                 # bars without trades
        vol[rng.choice(n, max(3, int(0.0003 * n)), replace=False)] = np.nan     # chart volume missing (stub: 100)
        no_intra[rng.choice(n, max(3, int(0.0005 * n)), replace=False)] = True  # no intrabars → BVC fallback (tier 1)
        k0 = n // 2
        no_intra[k0:k0 + 30] = True
        both = rng.choice(n, 3, replace=False)                                  # no intrabars AND volume missing
        no_intra[both] = True
        vol[both] = np.nan
        b = b.assign(v=vol)
    v_chart = b.v.to_numpy(float)
    v_src = np.where(np.isfinite(v_chart), v_chart, 100.0)                      # channel.mjs STUB_NA_VOL
    code, dpine = channel(q, v_src, no_intra)
    t_bars = time.time() - t0
    bars_json = work / f'{tag}_bars.json'
    pine_json = work / f'{tag}_pine.json'
    if not (a.reuse and pine_json.exists()):
        with open(bars_json, 'w') as f:
            json.dump({'klines': klines(b, code, a.tf)}, f)
        env = dict(os.environ)
        cmd = ['node', '--max-old-space-size=12000', str(HERE / 'run_pine.mjs'), '--bars', str(bars_json), '--out', str(pine_json),
               '--tf', str(a.tf), '--prec', a.prec, '--repo', str(PINE_REPO)] + (['--inputs', a.inputs] if a.inputs else [])
        t1 = time.time()
        res = subprocess.run(cmd, env=env, capture_output=True, text=True)
        t_pine = time.time() - t1
        if res.returncode != 0:
            print(res.stdout, res.stderr)
            raise SystemExit('PineTS run failed')
        print(res.stdout.strip())
        bars_json.unlink()
    else:
        t_pine = float('nan')
    pine = json.load(open(pine_json))
    tier = 3 if a.prec in ('s1', 't1') else 2
    t2 = time.time()
    e = E.run_engine(pd.DataFrame({'open': b.o.to_numpy(float), 'high': b.h.to_numpy(float), 'low': b.l.to_numpy(float),
                                   'close': b.c.to_numpy(float), 'volume': b.v.to_numpy(float), 'delta': dpine,
                                   'src_vol': v_src, 'has_src': ~no_intra,
                                   'session_first': b.session_first.to_numpy(), 'tier': tier}),
                     E.Params(tf_sec=a.tf * 60, **{INPUT_TO_PARAM[k]: v for k, v in json.loads(a.inputs or '{}').items()}))
    t_port = time.time() - t2
    warm = int(e.attrs['hq_need'] + 3 * e.attrs['params']['N'])
    rep = compare(pine, e, warm)
    rep.update({'sessions_filter': a.sessions, 'contract_changes': int(b.contract_change.sum()) if 'contract_change' in b else None,
                'gap_bars': int(e.gap_bar.sum()), 'tag': tag, 'inputs': json.loads(a.inputs or '{}'), 'inst': a.inst, 'tf_min': a.tf, 'variant': a.variant, 'prec': a.prec, 'tier': tier,
                'start': str(b.t.iloc[0]), 'end': str(b.t.iloc[-1]), 'sessions': int(b.session_first.sum()),
                'ke': e.attrs['ke'], 'life': e.attrs['life'], 'runtime_s': {'bars': round(t_bars, 2), 'pinets': round(t_pine, 1),
                'pinets_internal_ms': pine.get('ms'), 'port': round(t_port, 3)},
                'channel_delta_vs_variant_max_rel': float(np.nanmax(np.abs(dpine - b[a.variant].to_numpy(float)) /
                                                                     np.maximum(v_src, 1))) if not a.stress else None,
                'stress': {'seed': a.stress, 'vol0': int((b.v == 0).sum()), 'vol_na': int(b.v.isna().sum()),
                           'no_intrabars': int(no_intra.sum())} if a.stress else None,
                'no_obs_bars': int(e.no_obs.sum()), 'tier_counts': {int(k): int(v) for k, v in e.tier.value_counts().items()},
                'event_counts_port': {k: int(e[k].sum()) for k in ('new_abs', 'new_pin', 'new_pwf', 'res_cont', 'res_held',
                                                                     'res_exp', 'sup', 'al_z_up', 'al_z_dn', 'piv_top', 'piv_bot')},
                'labels_pine': len(pine.get('labels', []))})
    out = studyenv.results_dir() / f'validation_{tag}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(rep, open(out, 'w'), indent=1, default=str)
    zs = rep['series']['zDiv']
    print(json.dumps({'tag': tag, 'ok': rep['ok'], 'n': rep['n'], 'Z_defined': zs['defined_pine'], 'Z_max_abs': zs['max_abs'],
                      'zF_max_abs': rep['series']['zF']['max_abs'], 'zP_max_abs': rep['series']['zP']['max_abs'],
                      'flag_mismatch': {k: v['mismatch'] for k, v in rep['flags'].items() if v['mismatch']},
                      'series_bad': {k: v for k, v in rep['series'].items() if v['na_mismatch'] or v.get('mismatch') or
                                     (v.get('tol') and v['max_rel'] >= v['tol'])},
                      'alert_bad': {k: v for k, v in rep['alertconditions'].items() if v['only_port'] or v['only_pine']},
                      'labels': {k: rep['labels'][k] for k in ('labels', 'expected', 'n_bad', 'ok')},
                      'events': rep['event_counts_port'], 'runtime_s': rep['runtime_s']}, default=str))


if __name__ == '__main__':
    main()
