#!/usr/bin/env python3
"""Chart bars (1m / 5m / 15m) built from the clean 1-minute files, one session at a time, with the delta variants the
indicator would see on TradingView.

Data come from DATA_DIR (env, required: see studyenv.py). Nothing is written here: the functions
return DataFrames; features.py and validate_pine.py save what they need.

Chart bars
  * bucket = floor(bar open time, timeframe) INSIDE a session (session_date of the 1-minute file): a chart bar never
    mixes two sessions; buckets are clock-aligned (CME sessions open at 17:00 CT, SPY at 04:00 ET: both aligned to
    15 minutes);
  * o = first o, h = max h, l = min l, c = last c, v = sum v (chart volume), n_1m = number of 1-minute bars;
  * session_first: first chart bar of each session in the stream that is fed to the indicator (session.isfirstbar);
  * rth: bar open time in 09:30 ≤ ET < 16:00; contract, adj_offset, roll_session, clean_session from the 1-minute
    file; contract_change: the contract differs from the previous chart bar of the stream.

Delta variants (sum over the 1-minute or 1-second intrabars of each chart bar)
  * d_cr1m  candle rule on 1-minute bars (TradingView CVD rule, the `ltfSigned` of the indicator without quotes):
            +v if c > o, −v if c < o, else compare c with the PREVIOUS 1-minute close, else keep the previous side.
            The side is carried across bars and sessions over the whole 1-minute stream of the file (as the intrabar
            context of request.security_lower_tf does), starting at +1. Recomputed here and checked against the
            d_cr1m column of the clean file.
  * d_true  (2013 tick sample) aggressor delta from the quote rule (Lee–Ready with the prevailing quote strictly
            before the trade; tick-rule fallback), = the `delta` column of es_ticks_2013-09_1m.
  * d_cr1s  (2013 tick sample) candle rule on 1-second bars, side carried over the whole 1-second stream; recomputed
            from es_ticks_2013-09_1s and checked against d_cr1s of the 1-minute file.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import studyenv  # noqa: E402


def data_dir() -> Path:
    """Folder of the clean 1-minute files (env DATA_DIR, required)."""
    return studyenv.data_dir()


ET = 'America/New_York'

FILES = {
    'es': 'es_1m_2008-2026.parquet',
    'mes': 'mes_1m_2021-2026.parquet',
    'spy': 'spy_1m_2000-2026.parquet',
    'es_tick_1m': 'es_ticks_2013-09_1m.parquet',
    'es_tick_1s': 'es_ticks_2013-09_1s.parquet',
}


def candle_dir(o, c, init=1):
    """Candle-rule side per bar, stateful over the whole sorted series (side carried; starts at `init`)."""
    o = np.asarray(o, float)
    c = np.asarray(c, float)
    cp = np.r_[np.nan, c[:-1]]
    with np.errstate(invalid='ignore'):
        p = np.where(c > o, 1.0, np.where(c < o, -1.0, np.where(c > cp, 1.0, np.where(c < cp, -1.0, np.nan))))
    return pd.Series(p).ffill().fillna(init).to_numpy().astype(np.int8)


def rth_flag(t_utc: pd.Series) -> np.ndarray:
    e = t_utc.dt.tz_convert(ET)
    m = e.dt.hour * 60 + e.dt.minute
    return ((m >= 570) & (m < 960)).to_numpy()


def load_1m(name: str, columns=None) -> pd.DataFrame:
    """Read one clean 1-minute file (sorted by t_utc) and recompute/check the candle-rule delta."""
    df = pd.read_parquet(data_dir() / FILES[name], columns=columns)
    if not df.t_utc.is_monotonic_increasing:
        df = df.sort_values('t_utc', kind='stable').reset_index(drop=True)
    if {'o', 'c', 'v'} <= set(df.columns):
        d = candle_dir(df.o, df.c).astype(np.int64) * df.v.to_numpy()
        if 'd_cr1m' in df.columns:
            bad = int((d != df.d_cr1m.to_numpy()).sum())
            if bad:
                raise AssertionError(f'{name}: recomputed d_cr1m differs from the file on {bad} bars')
        df['d_cr1m'] = d
    return df


def tick_sample_1m() -> pd.DataFrame:
    """2013 Tick Data ES sample at 1 minute with d_true, d_cr1s (recomputed from 1 s bars) and d_cr1m."""
    m = load_1m('es_tick_1m')
    s = pd.read_parquet(data_dir() / FILES['es_tick_1s'], columns=['t_utc', 'o', 'c', 'v']).sort_values('t_utc', kind='stable')
    s_dir = candle_dir(s.o, s.c).astype(np.int64)
    s_d = pd.Series(s_dir * s.v.to_numpy(), index=s.t_utc.dt.floor('1min').to_numpy())
    cr1s = s_d.groupby(level=0).sum()
    rec = cr1s.reindex(m.t_utc.to_numpy()).to_numpy()
    bad = int((rec != m.d_cr1s.to_numpy()).sum())
    if bad:
        raise AssertionError(f'tick sample: recomputed d_cr1s differs from the 1-minute file on {bad} bars')
    m['d_true'] = m['delta'].astype(np.int64)
    m['d_cr1s'] = rec.astype(np.int64)
    m['clean_session'] = True
    return m


def chart_bars(m1: pd.DataFrame, tf_min: int, delta_cols=('d_cr1m',), session_col='session_date') -> pd.DataFrame:
    """Aggregate a sorted 1-minute frame into chart bars of tf_min minutes, never across sessions."""
    tns = m1.t_utc.dt.as_unit('ns').array.asi8
    step = tf_min * 60 * 1_000_000_000
    key = tns - np.mod(tns, step)
    sess = m1[session_col].dt.as_unit('ns').array.asi8 if hasattr(m1[session_col], 'dt') else m1[session_col].to_numpy()
    new = np.r_[True, (key[1:] != key[:-1]) | (sess[1:] != sess[:-1])]
    starts = np.flatnonzero(new)
    ends = np.r_[starts[1:], len(m1)] - 1
    out = pd.DataFrame({
        't': pd.to_datetime(key[starts], utc=True),
        'session_date': m1[session_col].to_numpy()[starts],
        'o': m1.o.to_numpy()[starts],
        'h': np.maximum.reduceat(m1.h.to_numpy(), starts),
        'l': np.minimum.reduceat(m1.l.to_numpy(), starts),
        'c': m1.c.to_numpy()[ends],
        'v': np.add.reduceat(m1.v.to_numpy().astype(np.int64), starts),
        'n_1m': np.diff(np.r_[starts, len(m1)]).astype(np.int16),
    })
    for dc in delta_cols:
        out[dc] = np.add.reduceat(m1[dc].to_numpy().astype(np.int64), starts)
    for col in ('contract', 'adj_offset', 'roll_session', 'clean_session'):
        if col in m1.columns:
            out[col] = m1[col].to_numpy()[ends]
    out['rth'] = rth_flag(out.t)
    out = mark_stream(out)
    return out


def mark_stream(bars: pd.DataFrame) -> pd.DataFrame:
    """(Re)mark session_first and contract_change for the stream as it will be fed to the indicator."""
    b = bars.reset_index(drop=True)
    sess = b.session_date.to_numpy()
    b['session_first'] = np.r_[True, sess[1:] != sess[:-1]]
    if 'contract' in b.columns:
        ct = b.contract.to_numpy()
        b['contract_change'] = np.r_[False, ct[1:] != ct[:-1]]
    return b


def build(name: str, tf_min: int, sessions: str = 'clean', rth_only: bool = False) -> pd.DataFrame:
    """Chart bars for one instrument.

    name: 'es' | 'mes' | 'spy' | 'es_tick'. sessions: 'clean' (only clean_session sessions for the futures; SPY drops
    August 2016) or 'all'. For 'es_tick' the delta columns are d_true, d_cr1s and d_cr1m.
    rth_only: keep only 09:30–16:00 ET 1-minute bars (a chart with extended hours off: the intrabar stream is then
    RTH-only too, so the candle-rule side is re-carried over the RTH-only stream).
    """
    if name == 'es_tick':
        m1 = tick_sample_1m()
        deltas = ('d_true', 'd_cr1s', 'd_cr1m')
    else:
        m1 = load_1m(name)
        deltas = ('d_cr1m',)
    # the candle-rule side is carried over the full stream BEFORE any session is dropped (as on TradingView)
    if rth_only:
        m1 = m1[m1.rth.to_numpy()].reset_index(drop=True)
        m1['d_cr1m'] = candle_dir(m1.o, m1.c).astype(np.int64) * m1.v.to_numpy()
    if sessions == 'clean':
        if 'clean_session' in m1.columns:
            m1 = m1[m1.clean_session.to_numpy()].reset_index(drop=True)
        if name == 'spy':
            sd = pd.to_datetime(m1.session_date)
            m1 = m1[~((sd.dt.year == 2016) & (sd.dt.month == 8))].reset_index(drop=True)
    b = chart_bars(m1, tf_min, deltas)
    b.attrs.update({'instrument': name, 'tf_min': tf_min, 'sessions': sessions, 'rth_only': rth_only})
    return b


if __name__ == '__main__':
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else 'es_tick'
    tf = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    b = build(name, tf)
    print(b.head(), b.shape, b.session_first.sum(), 'sessions')
