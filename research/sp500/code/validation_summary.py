#!/usr/bin/env python3
"""Collect every results/validation_*.json written by validate_pine.py into results/validation_summary.json and print a
one-line-per-slice table (bars, Z bars, max |ΔZ|, |ΔzF|, |ΔzP|, flag/series/alert mismatches, event counts, runtimes)."""
import json
from pathlib import Path

import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import studyenv  # noqa: E402


def main():
    rows = []
    res_dir = studyenv.results_dir()
    for f in sorted(res_dir.glob('validation_*.json')):
        if f.name == 'validation_summary.json':
            continue
        r = json.load(open(f))
        s = r['series']
        flag_bad = sum(v['mismatch'] for v in r['flags'].values())
        ser_bad = [k for k, v in s.items() if v['na_mismatch'] or v.get('mismatch') or (v.get('tol') and v['max_rel'] >= v['tol'])]
        al_bad = [k for k, v in r['alertconditions'].items() if v['only_port'] or v['only_pine']]
        rows.append({
            'tag': r['tag'], 'ok': r['ok'], 'inst': r['inst'], 'tf_min': r['tf_min'], 'variant': r['variant'], 'tier': r['tier'],
            'sessions_filter': r.get('sessions_filter', 'clean'), 'inputs': r.get('inputs', {}), 'stress': r.get('stress'),
            'first_bar': r['start'], 'last_bar': r['end'], 'bars': r['n'], 'sessions': r['sessions'],
            'z_bars': s['zDiv']['defined_pine'], 'max_abs_dZ': s['zDiv']['max_abs'], 'max_abs_dzF': s['zF']['max_abs'],
            'max_abs_dzP': s['zP']['max_abs'], 'max_abs_dD': s['dStat']['max_abs'], 'max_rel_any_series': max(v['max_rel'] for v in s.values()),
            'flags_compared': len(r['flags']), 'flag_true_total': sum(v['pine_true'] for v in r['flags'].values()),
            'flag_mismatches': flag_bad, 'series_compared': len(s), 'series_bad': ser_bad,
            'alertcondition_bars_pine': sum(v['pine'] for v in r['alertconditions'].values()), 'alertcondition_bad': al_bad,
            'events': r['event_counts_port'], 'gate_open_bars': r['flags']['gateOn']['pine_true'],
            'gap_bars': r.get('gap_bars'), 'contract_changes': r.get('contract_changes'),
            'runtime_s': r['runtime_s'],
        })
    json.dump(rows, open(res_dir / 'validation_summary.json', 'w'), indent=1, default=str)
    hdr = f"{'tag':28s} {'ok':>4s} {'bars':>6s} {'Zbars':>6s} {'max|dZ|':>9s} {'max|dzF|':>9s} {'max|dzP|':>9s} {'flagT':>7s} " \
          f"{'fMis':>4s} {'alerts':>6s} {'abs':>4s} {'pin':>4s} {'pwf':>4s} {'cont':>4s} {'held':>4s} {'exp':>4s} {'sup':>3s} " \
          f"{'pinets_s':>8s} {'port_s':>6s}"
    print(hdr)
    for x in rows:
        e = x['events']
        print(f"{x['tag']:28s} {str(x['ok']):>4s} {x['bars']:6d} {x['z_bars']:6d} {x['max_abs_dZ']:9.2e} {x['max_abs_dzF']:9.2e} "
              f"{x['max_abs_dzP']:9.2e} {x['flag_true_total']:7d} {x['flag_mismatches']:4d} {x['alertcondition_bars_pine']:6d} "
              f"{e['new_abs']:4d} {e['new_pin']:4d} {e['new_pwf']:4d} {e['res_cont']:4d} {e['res_held']:4d} {e['res_exp']:4d} "
              f"{e['sup']:3d} {(x['runtime_s'].get('pinets_internal_ms') or float('nan')) / 1000:8.1f} {x['runtime_s']['port']:6.3f}")


if __name__ == '__main__':
    main()
