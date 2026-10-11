#!/usr/bin/env python3
"""How much does the PineTS 10-decimal rounding (engine.Params.pine_round) change the outputs on full histories?

Runs the port twice on the same chart bars (pine_round True / False) and counts, per flag, the bars that differ, plus the
largest |ΔZ|, |ΔzF|, |ΔzP|. Differences come only from exact ties (window sums that are mathematically zero).
Writes results/rounding_effect.json.

Usage: python3 -I rounding_effect.py [es:5 es:15 mes:5 ...]
"""
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
FLAGS = ['hq_ok', 'gate', 'absorbed', 'pinned', 'pwf', 'new_abs', 'new_pin', 'new_pwf', 'res_cont', 'res_held', 'res_exp',
         'sup', 'cross_up', 'cross_dn', 'al_z_up', 'al_z_dn', 'piv_top', 'piv_bot']


def main():
    specs = sys.argv[1:] or ['es:5', 'es:15']
    res = {}
    for sp in specs:
        inst, tf = sp.split(':')
        tf = int(tf)
        b = B.build(inst, tf)
        col = 'd_cr1m'
        df = pd.DataFrame({'open': b.o.to_numpy(float), 'high': b.h.to_numpy(float), 'low': b.l.to_numpy(float),
                           'close': b.c.to_numpy(float), 'volume': b.v.to_numpy(float), 'delta': b[col].to_numpy(float),
                           'session_first': b.session_first.to_numpy(), 'tier': 2})
        t0 = time.time()
        a = E.run_engine(df, E.Params(tf_sec=tf * 60, pine_round=True))
        t1 = time.time()
        f = E.run_engine(df, E.Params(tf_sec=tf * 60, pine_round=False))
        t2 = time.time()
        r = {'bars': len(b), 'runtime_s': {'round': round(t1 - t0, 2), 'plain': round(t2 - t1, 2)},
             'flag_diff_bars': {k: int((a[k] != f[k]).sum()) for k in FLAGS},
             'flag_true_round': {k: int(a[k].sum()) for k in FLAGS}}
        for k in ('Z', 'zF', 'zP'):
            d = np.abs(a[k].to_numpy() - f[k].to_numpy())
            r[f'max_abs_d{k}'] = float(np.nanmax(d))
        res[sp] = r
        print(sp, json.dumps(r), flush=True)
    res_dir = studyenv.results_dir()
    res_dir.mkdir(parents=True, exist_ok=True)
    json.dump(res, open(res_dir / 'rounding_effect.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
