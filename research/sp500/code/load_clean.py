#!/usr/bin/env python3
"""Build clean S&P 500 intraday files for the price-vs-CVD event study.

Run with an isolated interpreter (the inputs are untrusted downloads):

    RAW_DIR=/data/sp500/raw DATA_DIR=/data/sp500/clean python3 -I load_clean.py                 # every dataset
    RAW_DIR=/data/sp500/raw DATA_DIR=/data/sp500/clean python3 -I load_clean.py es_tick es_1m   # a subset

Paths come from environment variables only (no defaults; see studyenv.py). None of them may lie inside a git work
tree: the inputs and outputs are licensed market data (research use only, no redistribution).

    RAW_DIR   folder of the raw downloads, one sub-folder per source (layout below; read only)
    DATA_DIR  output folder of the clean files and of manifest.json (the DATA_DIR of the study scripts)
    WORK_DIR  cache of decoded intermediate files (default DATA_DIR/work)

Raw layout expected under RAW_DIR (file names as published by each source; see research/sp500/README.md):

    tickdata_es_sample/ES_Sample.zip
    firstrate_via_jimmuell_mes-orb-strategy/ES_full_1min_continuous_UNadjusted.txt
    rueijrwu_FutureView/glbx-mdp3-YYYYMMDD-YYYYMMDD.ohlcv-1m.dbn.zst (monthly), rueijrwu_FutureView/meta/condition.json
    vinentHuynh_QuantResearch/ES_v0_ohlcv1m_2010_2026_UTC.csv.gz
    dschace_trading-model_databento/glbx-mdp3-YYYYMMDD-YYYYMMDD.ohlcv-1m.csv.zst (monthly), .../condition.json
    axb0306_cme-futures-ohlc/{ES,MES}_1min_*.csv, {ES,MES}_tick_*.csv (the *_tick_* files are 1-second bars)
    prsdro_spy/candles_1m.csv.gz
    github_alegitdude_backtester/ES-glbx-20251105.mbp-10-sample.csv.zst      (classifier check only)
    s3_frd001_firstrate_samples/SPY_1min_sample_firstratedata.zip           (SPY cross-check only)
    github_algoquant_HighFreq/SPY_1min_2008-01-02_2014-05-19_ET_barstart.csv.gz   (SPY cross-check only)
    kfhoo88_ibkr-scalper/SPY_IBKR_1min_1year_20251110.csv                    (SPY cross-check only)

Extra packages: zstandard and databento-dbn (to decode the Databento files), besides numpy, pandas and pyarrow.

Datasets (all outputs go to DATA_DIR, timestamps are tz-aware UTC and stamp the START of the bar):

  es_tick   Tier A. Tick Data LLC ES sample (ESU13 -> ESZ13, 2013-09-01..2013-09-20), every CME trade plus L1 quotes.
            Aggressor side is inferred: Lee-Ready with the prevailing quote taken STRICTLY BEFORE the trade's millisecond
            (validated on Databento ES MBP-10 with the exchange aggressor flag: 97% of volume classified by quote, 96.9%
            correct; 95.6% correct with the tick-rule fallback; per-minute delta corr 0.98).
            -> es_ticks_2013-09_trades.parquet, es_ticks_2013-09_1s.parquet, es_ticks_2013-09_1m.parquet
  es_1m     Tier C. ES front-month 1-minute bars 2008-01-02 .. 2026-09-29.
            sessions < 2016-01-04 : FirstRate continuous unadjusted (its own roll: first bar at/after the 14th 00:00 ET
                                    of the expiry month) with roll / dominance flags;
            sessions >= 2016-01-04: Databento GLBX.MDP3 per-contract bars, contract = the outright with the largest
                                    volume in that session (FirstRate substituted on Databento 'degraded' days when it is
                                    on the same contract);
            sessions >= 2026-09-17: Databento ES.v.0 tail (ESZ2026).
            -> es_1m_2008-2026.parquet, es_1m_2008-2026_sessions.parquet
  mes_1m    Tier C. MES front-month 1-minute bars 2021-05 .. 2026-09 (Databento per-contract, same rule as es_1m).
            -> mes_1m_2021-2026.parquet, mes_1m_2021-2026_sessions.parquet
  topstepx  Tier B (partial). TopstepX ES and MES 1-second bars (2026-03-09..04-15, mostly 14:30-21:00 UTC) and 1-minute
            bars (2026-01-20..04-15). -> {es,mes}_topstepx_2026_1s.parquet, {es,mes}_topstepx_2026_1m.parquet
  spy_1m    Tier C (equity cross-check). SPY 1-minute 2000-01-03..2026-04-09 (prsdro/spy), sorted and de-duplicated.
            -> spy_1m_2000-2026.parquet

Common columns of the 1-minute outputs: t_utc, o, h, l, c, v, session_date (CME: date of the session that opens at
17:00 CT the previous evening; SPY: ET calendar date), rth (09:30 <= ET < 16:00), d_cr1m (candle-rule signed volume of
the 1-minute bar itself, TradingView/ta rule: +v if c>o, -v if c<o, else compare c with the previous close, else keep the
previous side; this is what a 5m/15m chart sees with 1-minute intrabars).

Roll handling (futures): prices are UNADJUSTED. Every bar carries `contract` and `adj_offset`; add adj_offset to o/h/l/c
for a Panama (additive) back-adjusted series anchored on the last contract. Spreads are measured from simultaneous
Databento bars of both contracts (last common minute before the roll); before 2010-06 the spread is estimated from the
adjacent-minute gap when the roll falls mid-session and is NaN otherwise (adj_offset is then NaN for all earlier bars).
Session flags: roll_session (first session on a new contract or a session with a mid-session roll), partial (first or
last session of the file, cut by the data window), non_dominant
(the series' contract is not the highest-volume outright in that session), roll_window (pre-2010-06 sessions between
expiry-9 days and FirstRate's roll, where dominance cannot be checked), degraded (Databento quality flag), dom_share
(fraction of all outright volume of that session traded in the chosen contract). clean_session combines them:
not roll_session, not partial, not non_dominant, not roll_window, not degraded, and dom_share >= 0.70 when known.
Recommended for the event study: keep only clean_session bars (or drop roll sessions), and do not compute CVD across a
contract change.
"""
import sys
import io
import re
import json
import glob
import zipfile
from pathlib import Path

import os

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import studyenv  # noqa: E402

RAW = studyenv.outside_git(studyenv.require('RAW_DIR', 'folder of the raw downloads'), 'raw market data')
CLEAN = studyenv.outside_git(studyenv.require('DATA_DIR', 'output folder of the clean files'), 'clean market data')
WORK = studyenv.outside_git(Path(os.environ.get('WORK_DIR', '').strip() or CLEAN / 'work').expanduser().resolve(),
                            'decoded intermediate market data')
MANIFEST = CLEAN / 'manifest.json'
TICK = 0.25
CT, ET = 'America/Chicago', 'America/New_York'

P_TD_ZIP = RAW / 'tickdata_es_sample' / 'ES_Sample.zip'
P_FRD = RAW / 'firstrate_via_jimmuell_mes-orb-strategy' / 'ES_full_1min_continuous_UNadjusted.txt'
P_DBN_DIR = RAW / 'rueijrwu_FutureView'
P_DBN_COND = RAW / 'rueijrwu_FutureView' / 'meta' / 'condition.json'
P_ESV0 = RAW / 'vinentHuynh_QuantResearch' / 'ES_v0_ohlcv1m_2010_2026_UTC.csv.gz'
P_MES_DIR = RAW / 'dschace_trading-model_databento'
P_TSX = RAW / 'axb0306_cme-futures-ohlc'
P_SPY = RAW / 'prsdro_spy' / 'candles_1m.csv.gz'
P_MBP10 = RAW / 'github_alegitdude_backtester' / 'ES-glbx-20251105.mbp-10-sample.csv.zst'
P_SPY_FRD = RAW / 's3_frd001_firstrate_samples' / 'SPY_1min_sample_firstratedata.zip'
P_SPY_HF = RAW / 'github_algoquant_HighFreq' / 'SPY_1min_2008-01-02_2014-05-19_ET_barstart.csv.gz'
P_SPY_IB = RAW / 'kfhoo88_ibkr-scalper' / 'SPY_IBKR_1min_1year_20251110.csv'
SPLIT_SESSION = pd.Timestamp('2016-01-04')       # first session taken from Databento per-contract bars
TAIL_SESSION = pd.Timestamp('2026-09-17')        # first full ESZ2026 session in the ES.v.0 tail
MONTH_CODE = {'H': 3, 'M': 6, 'U': 9, 'Z': 12}


# ----------------------------------------------------------------------------------------------------------- helpers
def log(*a):
    print(*a, flush=True)


def utc_ns(s):
    """Normalise any tz-aware/naive-UTC timestamp Series to datetime64[ns, UTC]."""
    return pd.to_datetime(s, utc=True).dt.tz_convert('UTC').dt.as_unit('ns')


def session_date_cme(t_utc):
    """CME Globex session date: the session opening 17:00 CT on day D-1 is labelled D."""
    lt = t_utc.dt.tz_convert(CT).dt.tz_localize(None)
    return (lt + pd.Timedelta(hours=7)).dt.normalize()


def rth_flag(t_utc):
    e = t_utc.dt.tz_convert(ET)
    m = e.dt.hour * 60 + e.dt.minute
    return (m >= 570) & (m < 960)


def candle_dir(o, c, init=1):
    """TradingView/ta candle rule, stateful over the whole (sorted) series: c>o -> +1, c<o -> -1, else c vs previous
    close, else keep the previous side (start at +1)."""
    o = np.asarray(o, float)
    c = np.asarray(c, float)
    cp = np.r_[np.nan, c[:-1]]
    p = np.where(c > o, 1.0, np.where(c < o, -1.0, np.where(c > cp, 1.0, np.where(c < cp, -1.0, np.nan))))
    return pd.Series(p).ffill().fillna(init).to_numpy().astype(np.int8)


def bar_checks(df, price_cols=('o', 'h', 'l', 'c'), tick=TICK):
    """Integrity statistics for a bar table with t_utc, o, h, l, c, v."""
    t = df['t_utc']
    o, h, l, c, v = (df[k] for k in ('o', 'h', 'l', 'c', 'v'))
    px = df[list(price_cols)]
    out = {
        'rows': int(len(df)),
        'first': str(t.min()), 'last': str(t.max()),
        'monotonic_increasing': bool(t.is_monotonic_increasing),
        'duplicate_timestamps': int(t.duplicated().sum()),
        'nonpositive_price': int((px <= 0).any(axis=1).sum()),
        'nan_price': int(px.isna().any(axis=1).sum()),
        'ohlc_inconsistent': int(((l > np.minimum(o, c)) | (h < np.maximum(o, c)) | (l > h)).sum()),
        'zero_volume': int((v == 0).sum()), 'negative_volume': int((v < 0).sum()),
    }
    if tick:
        out['off_tick_grid'] = int((((px / tick) - (px / tick).round()).abs() > 1e-6).any(axis=1).sum())
    return out


def per_year_coverage(df, sess_col='session_date'):
    g = df.groupby(df[sess_col].dt.year)
    r = pd.DataFrame({'sessions': g[sess_col].nunique(), 'bars': g.size(), 'rth_bars': g['rth'].sum(), 'volume': g['v'].sum()})
    r['bars_per_session'] = (r.bars / r.sessions).round(1)
    r['rth_bars_per_session'] = (r.rth_bars / r.sessions).round(1)
    r['volume_per_session'] = (r.volume / r.sessions).round(0)
    return {int(k): {kk: (float(vv) if isinstance(vv, (float, np.floating)) else int(vv)) for kk, vv in row.items()}
            for k, row in r[['sessions', 'bars_per_session', 'rth_bars_per_session', 'volume_per_session']].iterrows()}


def missing_weekdays(sessions, start, end):
    s = set(pd.to_datetime(sessions).normalize())
    wd = pd.bdate_range(start, end)
    return [str(d.date()) for d in wd if d not in s]


def third_friday(y, m):
    d = pd.Timestamp(y, m, 1)
    return d + pd.Timedelta(days=(4 - d.weekday()) % 7 + 14)


def contract_expiry(contract):
    """'ESU2013' / 'MESZ2025' -> expiry date (3rd Friday)."""
    m = re.match(r'^M?ES([HMUZ])(\d{4})$', contract)
    return third_friday(int(m.group(2)), MONTH_CODE[m.group(1)])


def full_contract(root, raw_sym, ref_year):
    """'ESZ4' traded in ref_year -> 'ESZ2014'/'ESZ2024' (first year >= ref_year ending in that digit)."""
    code, d = raw_sym[len(root)], int(raw_sym[len(root) + 1:])
    y = ref_year - ref_year % 10 + d
    if y < ref_year:
        y += 10
    return f'{root}{code}{y}'


def update_manifest(key, value):
    m = {}
    if MANIFEST.exists():
        try:
            m = json.loads(MANIFEST.read_text())
        except ValueError:
            m = {}
    m[key] = value
    MANIFEST.write_text(json.dumps(m, indent=1, default=str))


def write_parquet(df, name):
    p = CLEAN / name
    df.to_parquet(p, index=False)
    log(f'  wrote {p.name}: {len(df):,} rows, {p.stat().st_size / 1e6:.1f} MB')
    return str(p)


def session_flags(sess, bars=None):
    """sess: DataFrame indexed by session_date with columns contract, mid_roll, dom_share, non_dominant, roll_window,
    degraded. Adds roll_session, partial (first/last session of the file cut by the data window) and clean_session."""
    prev = sess.contract.shift()
    sess['roll_session'] = (prev.notna() & (sess.contract != prev)) | sess.mid_roll
    sess['partial'] = False
    if bars is not None and len(sess):
        first_ct = bars.t_utc.iloc[0].tz_convert(CT)
        last_ct = bars.t_utc.iloc[-1].tz_convert(CT)
        if not (first_ct.hour == 17 and first_ct.minute <= 5):
            sess.loc[sess.index.min(), 'partial'] = True
        if last_ct.hour * 60 + last_ct.minute < 15 * 60 + 59 or last_ct.hour >= 17:
            sess.loc[sess.index.max(), 'partial'] = True
    ok_share = sess.dom_share.isna() | (sess.dom_share >= 0.70)
    sess['clean_session'] = ~sess.roll_session & ~sess.non_dominant & ~sess.roll_window & ~sess.degraded & ~sess.partial & ok_share
    return sess


def panama_offsets(bars, spreads):
    """bars sorted by time with a 'contract' column; spreads: list of (first_time_of_new_contract, spread) in time order
    (spread = new - old). Returns the additive offset per bar (NaN before an unmeasured roll)."""
    off = np.zeros(len(bars))
    t = bars['t_utc'].dt.tz_convert('UTC').dt.tz_localize(None).to_numpy(dtype='datetime64[ns]')
    cum = 0.0
    for t_roll, sp in reversed(spreads):
        cum = cum + sp if np.isfinite(cum) and sp is not None and np.isfinite(sp) else np.nan
        off[t < np.datetime64(t_roll.tz_convert('UTC').tz_localize(None), 'ns')] = cum
    return off


def spread_from_contracts(per_contract, old, new, t_roll, lookback_h=240):
    """new - old close at the last minute before t_roll where both contracts have a bar (Databento per-contract)."""
    lo = t_roll - pd.Timedelta(hours=lookback_h)
    a = per_contract[(per_contract.contract == old) & (per_contract.t_utc < t_roll) & (per_contract.t_utc >= lo)].set_index('t_utc').c
    b = per_contract[(per_contract.contract == new) & (per_contract.t_utc < t_roll) & (per_contract.t_utc >= lo)].set_index('t_utc').c
    j = pd.concat([a.rename('a'), b.rename('b')], axis=1, sort=True).dropna()
    if len(j) == 0:
        return None, None
    return float(j.b.iloc[-1] - j.a.iloc[-1]), str(j.index[-1])


# ------------------------------------------------------------------------------------------- Databento per-contract
def load_dbn_es_contracts():
    """Decode the Databento GLBX.MDP3 ES.FUT ohlcv-1m monthly DBN files (all instruments) and keep outright contracts.
    Cached in work/dbn_es_outrights_1m.parquet."""
    cache = WORK / 'dbn_es_outrights_1m.parquet'
    if cache.exists():
        d = pd.read_parquet(cache)
        return d.rename(columns={'t': 't_utc'}) if 't' in d.columns else d
    import zstandard as zstd                      # pip install zstandard databento-dbn
    import databento_dbn as dbn
    frames, maps = [], []
    for p in sorted(glob.glob(str(P_DBN_DIR / 'glbx-mdp3-*.ohlcv-1m.dbn.zst'))):
        dec = dbn.DBNDecoder()
        dec.write(zstd.ZstdDecompressor().decompressobj().decompress(open(p, 'rb').read()))
        recs = dec.decode()
        mp = recs[0].mappings
        for raw_sym, ivs in (mp.items() if isinstance(mp, dict) else mp):
            for iv in ivs:
                maps.append((raw_sym, int(iv['symbol']), iv['start_date']))
        r = recs[1:]
        if r:
            n = len(r)
            frames.append(pd.DataFrame({'ts': np.fromiter((x.ts_event for x in r), np.int64, n),
                                        'iid': np.fromiter((x.instrument_id for x in r), np.int64, n),
                                        'o': np.fromiter((x.open for x in r), np.int64, n) / 1e9,
                                        'h': np.fromiter((x.high for x in r), np.int64, n) / 1e9,
                                        'l': np.fromiter((x.low for x in r), np.int64, n) / 1e9,
                                        'c': np.fromiter((x.close for x in r), np.int64, n) / 1e9,
                                        'v': np.fromiter((x.volume for x in r), np.int64, n)}))
    sm = pd.DataFrame(maps, columns=['raw', 'iid', 'start']).drop_duplicates()
    sm = sm[sm.raw.str.match(r'^ES[HMUZ]\d$')]
    sm['contract'] = [full_contract('ES', r, pd.Timestamp(s).year) for r, s in zip(sm.raw, sm.start)]
    cmap = sm.groupby('iid').contract.agg(lambda s: s.mode().iloc[0])
    d = pd.concat(frames, ignore_index=True)
    d = d[d.iid.isin(cmap.index)].copy()
    d['contract'] = d.iid.map(cmap)
    d['t_utc'] = pd.to_datetime(d.ts, unit='ns', utc=True)
    d = d.drop(columns='ts').sort_values(['t_utc', 'contract']).reset_index(drop=True)
    d.to_parquet(cache, index=False)
    return d


def dbn_degraded_dates(path):
    c = json.loads(Path(path).read_text())
    return sorted(pd.Timestamp(x['date']) for x in c if x.get('condition') != 'available')


# --------------------------------------------------------------------------------------------------------- es_tick
def validate_classifier(symbol='ESZ5'):
    """Accuracy of the es_tick classifier (L1 quotes and trades in separate ms-stamped streams, quote strictly before the
    trade's ms, Lee-Ready + tick fallback) against the CME aggressor flag, on Databento ES MBP-10 records
    (2025-11-05 00:00-01:12 UTC, ESZ5)."""
    import zstandard as zstd
    with open(P_MBP10, 'rb') as fh:
        df = pd.read_csv(io.TextIOWrapper(zstd.ZstdDecompressor().stream_reader(fh)),
                         usecols=['ts_event', 'action', 'side', 'price', 'size', 'bid_px_00', 'ask_px_00', 'bid_sz_00', 'ask_sz_00', 'symbol'])
    d = df[df.symbol == symbol].reset_index(drop=True)
    na = 9223372036854775807
    for k in ('bid_px_00', 'ask_px_00', 'price'):
        d[k] = d[k].where(d[k] != na) / 1e9
    tr = d[d.action == 'T'].copy()
    q = d[d.action != 'T']
    k4 = ['bid_px_00', 'ask_px_00', 'bid_sz_00', 'ask_sz_00']
    q = q[q[k4].ne(q[k4].shift()).any(axis=1)].copy()
    q['tms'] = q.ts_event // 1_000_000
    tr['tms'] = tr.ts_event // 1_000_000
    mm = pd.merge_asof(tr[['tms', 'price', 'size', 'side']].reset_index(), q[['tms', 'bid_px_00', 'ask_px_00']], on='tms',
                       allow_exact_matches=False, direction='backward').set_index('index').loc[tr.index]
    px, b, a, v = mm.price.to_numpy(), mm.bid_px_00.to_numpy(), mm.ask_px_00.to_numpy(), mm['size'].to_numpy()
    valid = ~np.isnan(b) & ~np.isnan(a) & (b < a)
    mid = (a + b) / 2
    s_q = np.select([valid & (px >= a), valid & (px <= b), valid & (px > mid), valid & (px < mid)], [1, -1, 1, -1], 0)
    dp = np.sign(np.diff(px, prepend=np.nan))
    tick = pd.Series(np.where(dp == 0, np.nan, dp)).ffill().fillna(0).to_numpy()
    s_f = np.where(s_q != 0, s_q, tick)
    truth = np.where(mm.side == 'B', 1, np.where(mm.side == 'A', -1, 0))
    k = truth != 0
    mn = pd.to_datetime(tr.ts_event, unit='ns').dt.floor('1min').to_numpy()
    g = pd.DataFrame({'mn': mn, 't': truth * v, 'e': s_f * v}).groupby('mn').sum()
    return {'sample': f'Databento GLBX.MDP3 MBP-10 {symbol} 2025-11-05 00:00-01:12 UTC (GitHub alegitdude/Backtester test data)',
            'trades': int(len(tr)), 'contracts': int(v.sum()),
            'quote_classified_volume_share': round(float(v[k & (s_q != 0)].sum() / v[k].sum()), 4),
            'quote_accuracy_volume': round(float(v[k & (s_q != 0) & (s_q == truth)].sum() / v[k & (s_q != 0)].sum()), 4),
            'final_accuracy_volume_with_tick_fallback': round(float(v[k & (s_f == truth)].sum() / v[k].sum()), 4),
            'tick_rule_only_accuracy_volume': round(float(v[k & (tick == truth)].sum() / v[k].sum()), 4),
            'per_minute_delta_corr': round(float(np.corrcoef(g.e, g.t)[0, 1]), 4), 'minutes': int(len(g))}


def td_read():
    ct, cq = WORK / 'td_es_trades.parquet', WORK / 'td_es_quotes.parquet'
    if ct.exists() and cq.exists():
        return pd.read_parquet(ct), pd.read_parquet(cq)
    z = zipfile.ZipFile(P_TD_ZIP)

    def ts(df):
        return pd.to_datetime(df['Date'] + ' ' + df['Time'], format='%m/%d/%Y %H:%M:%S.%f')
    tr = pd.read_csv(z.open('ES_Trades.csv'), dtype={'Symbol': 'category', 'Date': str, 'Time': str, 'Price': float, 'Volume': 'int64',
                     'Market Flag': 'category', 'Sales Condition': 'category', 'Exclude Record Flag': 'category', 'Unfiltered Price': float})
    tr['t_local'] = ts(tr)
    tr = tr.drop(columns=['Date', 'Time'])
    tr['seq'] = np.arange(len(tr))
    tr.to_parquet(ct)
    q = pd.read_csv(z.open('ES_Quotes.csv'), dtype={'Symbol': 'category', 'Date': str, 'Time': str, 'Bid Price': float, 'Bid Size': float,
                    'Ask Price': float, 'Ask Size': float, 'Market Flag': 'category', 'Quote Condition': 'category'})
    q['t_local'] = ts(q)
    q = q.drop(columns=['Date', 'Time'])
    q['seq'] = np.arange(len(q))
    q.to_parquet(cq)
    return tr, q


def build_es_tick():
    log('[es_tick] Tick Data ES sample')
    tr, q = td_read()
    rep = {'source': 'Tick Data LLC free sample downloads/ES_Sample.zip (evaluation use, no redistribution)'}
    rep['raw_trades'] = int(len(tr))
    rep['raw_quotes'] = int(len(q))
    rep['trade_flags'] = {'market_flag': tr['Market Flag'].astype(str).value_counts().to_dict(),
                          'sales_condition': tr['Sales Condition'].astype(str).value_counts().to_dict(),
                          'exclude_flag_set': int(tr['Exclude Record Flag'].notna().sum())}
    rep['price_vs_unfiltered_differs'] = int((tr.Price != tr['Unfiltered Price']).sum())
    if P_MBP10.exists():
        rep['classifier_validation_vs_cme_aggressor_flag'] = validate_classifier()
        log('  classifier validation:', rep['classifier_validation_vs_cme_aggressor_flag'])
    parts = []
    for sym in sorted(tr.Symbol.astype(str).unique()):
        t = tr[tr.Symbol == sym].sort_values('seq')
        qq = q[q.Symbol == sym].sort_values('seq')
        assert t.t_local.is_monotonic_increasing and qq.t_local.is_monotonic_increasing
        m = pd.merge_asof(t[['t_local', 'seq', 'Unfiltered Price', 'Price', 'Volume']], qq[['t_local', 'Bid Price', 'Ask Price']],
                          on='t_local', allow_exact_matches=False, direction='backward')
        px = m['Unfiltered Price'].to_numpy()
        dp = np.sign(np.diff(px, prepend=np.nan))
        m['tick'] = pd.Series(np.where(dp == 0, np.nan, dp)).ffill().fillna(0).to_numpy().astype(np.int8)
        m['Symbol'] = sym
        parts.append(m)
    m = pd.concat(parts).sort_values('seq').reset_index(drop=True)
    px, b, a = m['Unfiltered Price'], m['Bid Price'], m['Ask Price']
    valid = b.notna() & a.notna() & (b < a)
    mid = (b + a) / 2
    side = np.select([valid & (px >= a), valid & (px <= b), valid & (px > mid), valid & (px < mid)], [1, -1, 1, -1], 0)
    method = np.select([valid & ((px >= a) | (px <= b)), valid & (px != mid)], ['Q', 'M'], 'T')
    side = np.where(side == 0, m.tick.to_numpy(), side).astype(np.int8)
    method = np.where((method == 'T') & (side == 0), 'U', method)
    out = pd.DataFrame({
        't_utc': m.t_local.dt.tz_localize(CT).dt.tz_convert('UTC'),
        'price': px.to_numpy(), 'price_filtered': m.Price.to_numpy(), 'size': m.Volume.to_numpy(),
        'side': side, 'method': pd.Categorical(method, categories=['Q', 'M', 'T', 'U']),
        'side_tick': m.tick.to_numpy(), 'bid': b.to_numpy(), 'ask': a.to_numpy(),
        'contract': m.Symbol.map({'ESU13': 'ESU2013', 'ESZ13': 'ESZ2013'}).to_numpy()})
    out['session_date'] = session_date_cme(out.t_utc)
    vol = out['size']
    rep['classification_volume_share'] = {k: round(float(vol[out.method == k].sum() / vol.sum()), 5) for k in ['Q', 'M', 'T', 'U']}
    rep['locked_or_crossed_or_missing_quote_volume_share'] = round(float(vol[~valid.to_numpy()].sum() / vol.sum()), 5)
    rep['buy_share_of_volume'] = round(float(vol[out.side == 1].sum() / vol.sum()), 4)
    rep['tick_rule_agreement_with_final_side_volume'] = round(float(vol[out.side == out.side_tick].sum() / vol.sum()), 4)
    # one contract per session (Tick Data rolls at the 2013-09-12 close, the CME roll date)
    spc = out.groupby('session_date').contract.nunique()
    rep['sessions'] = int(len(spc))
    rep['sessions_with_two_contracts'] = int((spc > 1).sum())
    # back-adjust offset from simultaneous Databento bars of both contracts (last common minute before the roll)
    dpc = load_dbn_es_contracts()
    t_roll = out.t_utc[out.contract == 'ESZ2013'].min()
    spread, at = spread_from_contracts(dpc, 'ESU2013', 'ESZ2013', t_roll.floor('1min'))
    rep['roll'] = {'first_ESZ2013_trade_utc': str(t_roll), 'spread_ESZ_minus_ESU': spread, 'measured_at_utc': at}
    out['adj_offset'] = np.where(out.contract == 'ESU2013', spread, 0.0)
    write_parquet(out.drop(columns=['session_date']), 'es_ticks_2013-09_trades.parquet')

    def bars(freq):
        k = out.t_utc.dt.floor(freq)
        sv = out['size'] * out.side
        g = out.assign(k=k, sv=sv, bv=np.where(out.side > 0, out['size'], 0), qv=np.where(out.method == 'Q', out['size'], 0),
                       qsv=np.where(out.method == 'Q', sv, 0), tsv=out['size'] * out.side_tick).groupby('k', sort=True)
        r = pd.DataFrame({'o': g.price.first(), 'h': g.price.max(), 'l': g.price.min(), 'c': g.price.last(), 'v': g['size'].sum(),
                          'n_trades': g.size(), 'buy_v': g.bv.sum(), 'delta': g.sv.sum(), 'v_quote': g.qv.sum(), 'delta_quote': g.qsv.sum(),
                          'delta_tick': g.tsv.sum(), 'contract': g.contract.last(), 'adj_offset': g.adj_offset.last()})
        r.index.name = 't_utc'
        r = r.reset_index()
        r['sell_v'] = r.v - r.buy_v
        return r
    s1 = bars('1s')
    s1['dir_cr'] = candle_dir(s1.o, s1.c)
    s1['d_cr'] = s1.dir_cr.astype(np.int64) * s1.v
    m1 = bars('1min')
    m1 = m1.merge(s1.assign(t_utc=s1.t_utc.dt.floor('1min')).groupby('t_utc').d_cr.sum().rename('d_cr1s').reset_index(), on='t_utc', how='left')
    m1['d_cr1m'] = candle_dir(m1.o, m1.c).astype(np.int64) * m1.v
    for df in (s1, m1):
        df['session_date'] = session_date_cme(df.t_utc)
        df['rth'] = rth_flag(df.t_utc)
        df['roll_session'] = df.session_date == session_date_cme(pd.Series([t_roll])).iloc[0]
    s1 = s1.drop(columns=['dir_cr'])
    rep['bars_1s'] = bar_checks(s1)
    rep['bars_1m'] = bar_checks(m1)
    rep['bars_1m']['sessions'] = {str(k.date()): int(v) for k, v in m1.groupby('session_date').size().items()}
    # cross-check against Databento per-contract bars of the same contract (independent vendor)
    j = m1.merge(dpc[['t_utc', 'contract', 'o', 'h', 'l', 'c', 'v']], on=['t_utc', 'contract'], how='inner', suffixes=('', '_dbn'))
    rep['xcheck_databento_same_contract'] = {'minutes_joined': int(len(j)), 'minutes_tickdata': int(len(m1)),
                                             'v_exact': round(float((j.v == j.v_dbn).mean()), 4), 'c_exact': round(float((j.c == j.c_dbn).mean()), 4),
                                             'h_exact': round(float((j.h == j.h_dbn).mean()), 4), 'l_exact': round(float((j.l == j.l_dbn).mean()), 4),
                                             'volume_ratio_td_over_dbn': round(float(j.v.sum() / j.v_dbn.sum()), 4)}
    # how well do the bar-based estimators track the trade-level delta (RTH, excluding the roll session)
    acc = {}
    base = m1[m1.rth & ~m1.roll_session].copy()
    for tf in ('1min', '5min', '15min'):
        g = base.assign(k=base.t_utc.dt.floor(tf)).groupby('k')[['delta', 'd_cr1s', 'd_cr1m', 'delta_tick', 'v']].sum()
        acc[tf] = {f'corr_{e}': round(float(np.corrcoef(g[e], g.delta)[0, 1]), 4) for e in ('d_cr1s', 'd_cr1m', 'delta_tick')}
        acc[tf].update({f'sign_agree_{e}': round(float((np.sign(g[e]) == np.sign(g.delta)).mean()), 4) for e in ('d_cr1s', 'd_cr1m', 'delta_tick')})
        acc[tf]['n'] = int(len(g))
    # session-anchored CVD path agreement (correlation of cumulative sums within each RTH session)
    cv = []
    for sd, g in base.groupby('session_date'):
        cv.append({e: np.corrcoef(g[e].cumsum(), g.delta.cumsum())[0, 1] for e in ('d_cr1s', 'd_cr1m', 'delta_tick')})
    acc['rth_cvd_path_corr_median'] = {k: round(float(v), 4) for k, v in pd.DataFrame(cv).median().items()}
    rep['estimator_vs_trade_delta_rth'] = acc
    write_parquet(s1, 'es_ticks_2013-09_1s.parquet')
    write_parquet(m1, 'es_ticks_2013-09_1m.parquet')
    update_manifest('es_tick', rep)
    log(json.dumps({k: rep[k] for k in ('classification_volume_share', 'xcheck_databento_same_contract', 'estimator_vs_trade_delta_rth')}, indent=1))


# ----------------------------------------------------------------------------------------------------------- es_1m
def firstrate_rule_contract(t_et_naive):
    """FirstRate's ES roll (verified against Databento labels 2010-06..2015): the series switches to the next quarterly
    contract at the first bar at/after 00:00 ET on the 14th of the expiry month."""
    yrs = range(t_et_naive.dt.year.min() - 1, t_et_naive.dt.year.max() + 2)
    rolls = sorted((pd.Timestamp(y, m, 14), f'ES{c}{y}') for y in yrs for c, m in MONTH_CODE.items())
    rt = np.array([r[0] for r in rolls], dtype='datetime64[ns]')
    idx = np.searchsorted(rt, t_et_naive.to_numpy(dtype='datetime64[ns]'), side='right')
    names = np.array([r[1] for r in rolls])
    return names[idx]


def build_es_1m():
    log('[es_1m] ES front-month 1-minute 2008-2026')
    rep = {'sources': {'firstrate': 'FirstRate Data ES continuous UNadjusted 1m (via GitHub jimmuell/mes-orb-strategy LFS; FirstRate licence, internal research only)',
                       'databento_contracts': 'Databento GLBX.MDP3 ES.FUT ohlcv-1m per contract (via GitHub rueijrwu/FutureView LFS; Databento/CME licence, research only)',
                       'databento_v0': 'Databento GLBX.MDP3 ES.v.0 ohlcv-1m (via GitHub vinentHuynh/QuantResearch; research only)'}}
    # --- FirstRate
    f = pd.read_csv(P_FRD, header=None, names=['dt', 'o', 'h', 'l', 'c', 'v'], dtype={'dt': str})
    tl = pd.to_datetime(f.dt, format='%Y-%m-%d %H:%M:%S')
    f['t_utc'] = tl.dt.tz_localize(ET, ambiguous='NaT', nonexistent='NaT').dt.tz_convert('UTC')
    rep['firstrate_raw'] = {'rows': int(len(f)), 'dst_ambiguous_or_nonexistent': int(f.t_utc.isna().sum())}
    f = f.dropna(subset=['t_utc']).drop(columns='dt')
    f['contract'] = firstrate_rule_contract(tl[f.index])
    f['session_date'] = session_date_cme(f.t_utc)
    f = f.sort_values('t_utc').reset_index(drop=True)
    rep['firstrate_checks'] = bar_checks(f)
    # --- Databento per contract
    d = load_dbn_es_contracts()
    d['session_date'] = session_date_cme(d.t_utc)
    sv = d.groupby(['session_date', 'contract']).v.sum().unstack(fill_value=0)
    dom = sv.idxmax(axis=1)
    tot = sv.sum(axis=1)
    degraded = set(dbn_degraded_dates(P_DBN_COND))
    # verify the FirstRate roll rule against exact (time, close) matches with Databento contracts
    j = f[['t_utc', 'c']].merge(d[['t_utc', 'contract', 'c']], on=['t_utc', 'c'], how='inner')
    j = j[~j.t_utc.duplicated(keep=False)]      # unambiguous matches only
    lab = f[['t_utc', 'contract']].merge(j[['t_utc', 'contract']], on='t_utc', suffixes=('', '_dbn'))
    lab_era = lab[lab.t_utc < pd.Timestamp('2016-01-04', tz='UTC')]
    rep['firstrate_rule_vs_databento_match'] = {'matched_minutes_pre2016': int(len(lab_era)),
                                                'agree_pre2016': round(float((lab_era.contract == lab_era.contract_dbn).mean()), 5),
                                                'agree_2016_on': round(float((lab.contract == lab.contract_dbn)[lab.t_utc >= pd.Timestamp('2016-01-04', tz='UTC')].mean()), 5)}
    # --- assemble per era
    fe = f[f.session_date < SPLIT_SESSION].copy()
    fe['src'] = 'firstrate'
    de = d[d.session_date >= SPLIT_SESSION].copy()
    de = de[de.contract == de.session_date.map(dom)].copy()
    de['src'] = 'databento_contract'
    de['degraded'] = de.t_utc.dt.tz_localize(None).dt.normalize().isin(degraded)
    # Databento degraded sessions -> FirstRate bars when FirstRate is on the same contract for the whole session
    dsess = set(de.loc[de.degraded, 'session_date'])
    fsc = f.groupby('session_date').contract.agg(['nunique', 'first'])
    swap = sorted(s for s in dsess if s in fsc.index and fsc.loc[s, 'nunique'] == 1 and fsc.loc[s, 'first'] == dom.get(s))
    rep['degraded_sessions_databento'] = [str(s.date()) for s in sorted(dsess)]
    rep['degraded_sessions_replaced_by_firstrate'] = [str(s.date()) for s in swap]
    de = de[~de.session_date.isin(swap)]
    fsw = f[f.session_date.isin(swap)].copy()
    fsw['src'] = 'firstrate'
    last_dbn_session = d.session_date.max()
    # ES.v.0 tail after the per-contract files end
    v0 = pd.read_csv(P_ESV0)
    v0['t_utc'] = pd.to_datetime(v0.t, utc=True)
    v0 = v0.rename(columns={'iid': 'iid'}).drop(columns='t')
    iid2c = d.drop_duplicates('iid').set_index('iid').contract
    v0['contract'] = v0.iid.map(iid2c)
    v0['session_date'] = session_date_cme(v0.t_utc)
    tail = v0[(v0.session_date >= TAIL_SESSION)].copy()
    rep['tail'] = {'contracts': tail.contract.value_counts().to_dict(), 'first': str(tail.t_utc.min()), 'last': str(tail.t_utc.max()),
                   'gap_sessions': [str(s.date()) for s in pd.bdate_range(last_dbn_session + pd.Timedelta(days=1), TAIL_SESSION - pd.Timedelta(days=1))]}
    assert tail.contract.eq('ESZ2026').all()
    tail['src'] = 'databento_v0'
    cols = ['t_utc', 'o', 'h', 'l', 'c', 'v', 'contract', 'session_date', 'src']
    parts = []
    for x in (fe, fsw, de, tail):
        x = x[cols].copy()
        log('   part', x.src.iloc[0] if len(x) else '-', len(x), x.t_utc.dtype)
        if len(x):
            x['t_utc'] = utc_ns(x.t_utc)
            parts.append(x)
    es = pd.concat(parts, ignore_index=True).sort_values('t_utc').reset_index(drop=True)
    es['v'] = es.v.astype(np.int64)
    es['degraded'] = (es.src != 'firstrate') & es.t_utc.dt.tz_localize(None).dt.normalize().isin(degraded)
    # --- sessions table and flags
    es['rth'] = rth_flag(es.t_utc)
    g = es.groupby('session_date')
    sess = pd.DataFrame({'contract': g.contract.last(), 'n_contracts': g.contract.nunique(), 'src': g.src.agg(lambda s: '+'.join(sorted(set(s)))),
                         'bars': g.size(), 'rth_bars': g.rth.sum(), 'v': g.v.sum(), 'degraded': g.degraded.any()})
    sess['mid_roll'] = sess.n_contracts > 1
    own = [sv.at[s, c] if (s in sv.index and c in sv.columns) else np.nan for s, c in zip(sess.index, sess.contract)]
    sess['dom_contract'] = dom.reindex(sess.index)
    sess['dom_share'] = (pd.Series(own, index=sess.index) / tot.reindex(sess.index)).round(4)
    sess.loc[sess.mid_roll, 'dom_share'] = np.nan
    sess['non_dominant'] = sess.dom_contract.notna() & ~sess.mid_roll & (sess.contract != sess.dom_contract)
    # pre-2010-06 FirstRate sessions: no per-contract volume -> flag the window between expiry-9d and FirstRate's roll
    sess['roll_window'] = False
    first_dbn = d.session_date.min()
    for y in range(2007, 2011):
        for code, mth in MONTH_CODE.items():
            exp = third_friday(y, mth)
            after = sess.index[sess.index >= pd.Timestamp(y, mth, 14)]
            if len(after) == 0 or pd.Timestamp(y, mth, 14) < sess.index.min():
                continue
            roll_sess = after.min()   # session holding FirstRate's switch (first bar at/after the 14th 00:00 ET)
            w = (sess.index >= exp - pd.Timedelta(days=9)) & (sess.index <= roll_sess) & (sess.index < first_dbn)
            sess.loc[w, 'roll_window'] = True
    sess = session_flags(sess, es)
    # back-adjust spreads at each contract change
    chg = es.contract != es.contract.shift()
    spreads, rolls = [], []
    for i in np.flatnonzero(chg.to_numpy())[1:]:
        old, new, t_new = es.contract.iat[i - 1], es.contract.iat[i], es.t_utc.iat[i]
        sp, at = spread_from_contracts(d, old, new, t_new)
        how = 'databento_simultaneous'
        if sp is None:
            gap_min = (t_new - es.t_utc.iat[i - 1]).total_seconds() / 60
            if gap_min <= 5:
                sp, at, how = float(es.o.iat[i] - es.c.iat[i - 1]), str(es.t_utc.iat[i - 1]), 'adjacent_minute_gap_estimate'
            else:
                sp, at, how = np.nan, None, 'unmeasured'
        spreads.append((t_new, sp))
        rolls.append({'from': old, 'to': new, 'first_bar_utc': str(t_new), 'spread': sp, 'measured_at': at, 'method': how})
    es['adj_offset'] = panama_offsets(es, spreads)
    es['d_cr1m'] = candle_dir(es.o, es.c).astype(np.int64) * es.v
    es = es.merge(sess[['roll_session', 'non_dominant', 'roll_window', 'dom_share', 'clean_session']].rename_axis('session_date').reset_index(),
                  on='session_date', how='left')
    rep['rolls'] = rolls
    rep['checks'] = bar_checks(es)
    rep['coverage_per_year'] = per_year_coverage(es)
    rep['sessions'] = {'total': int(len(sess)), 'clean': int(sess.clean_session.sum()), 'roll_session': int(sess.roll_session.sum()),
                       'non_dominant': int(sess.non_dominant.sum()), 'roll_window': int(sess.roll_window.sum()), 'degraded': int(sess.degraded.sum()),
                       'partial': [str(x.date()) for x in sess.index[sess.partial]],
                       'low_dom_share_lt_0.70': int((sess.dom_share < 0.70).sum())}
    rep['missing_weekdays'] = missing_weekdays(sess.index, '2008-01-02', '2026-09-29')
    # splice continuity
    rep['splice'] = {}
    for a, b in ((SPLIT_SESSION - pd.Timedelta(days=3), SPLIT_SESSION), (last_dbn_session, TAIL_SESSION)):
        x = es[(es.session_date >= a) & (es.session_date <= b)]
        x = x[x.src != x.src.shift()]
        rep['splice'][str(b.date())] = x[['t_utc', 'o', 'c', 'contract', 'src']].astype(str).to_dict('records')
    # cross-vendor agreement on the same contract and minute (2016+)
    fx = f[f.session_date >= SPLIT_SESSION][['t_utc', 'contract', 'o', 'h', 'l', 'c', 'v']]
    jj = fx.merge(d[['t_utc', 'contract', 'o', 'h', 'l', 'c', 'v']], on=['t_utc', 'contract'], suffixes=('_f', '_d'))
    jj['y'] = jj.t_utc.dt.year
    rep['xcheck_firstrate_vs_databento_same_contract'] = {int(y): {'n': int(len(g)), 'v_exact': round(float((g.v_f == g.v_d).mean()), 4),
                                                                    'c_exact': round(float((g.c_f == g.c_d).mean()), 4),
                                                                    'v_ratio_d_over_f': round(float(g.v_d.sum() / g.v_f.sum()), 4)} for y, g in jj.groupby('y')}
    sess_out = sess.reset_index().rename(columns={'index': 'session_date'})
    write_parquet(es[['t_utc', 'o', 'h', 'l', 'c', 'v', 'contract', 'adj_offset', 'session_date', 'rth', 'd_cr1m', 'src', 'roll_session',
                      'non_dominant', 'roll_window', 'degraded', 'dom_share', 'clean_session']], 'es_1m_2008-2026.parquet')
    write_parquet(sess_out, 'es_1m_2008-2026_sessions.parquet')
    update_manifest('es_1m', rep)
    log(json.dumps({k: rep[k] for k in ('firstrate_rule_vs_databento_match', 'checks', 'sessions', 'tail')}, indent=1, default=str))


# ---------------------------------------------------------------------------------------------------------- mes_1m
def load_mes_contracts():
    import zstandard as zstd
    parts = []
    for p in sorted(glob.glob(str(P_MES_DIR / 'glbx-mdp3-*.ohlcv-1m.csv.zst'))):
        with open(p, 'rb') as fh:
            df = pd.read_csv(io.TextIOWrapper(zstd.ZstdDecompressor().stream_reader(fh)),
                             usecols=['ts_event', 'instrument_id', 'open', 'high', 'low', 'close', 'volume', 'symbol'])
        df = df[df.symbol.str.match(r'^MES[HMUZ]\d$')]
        parts.append(df)
    a = pd.concat(parts, ignore_index=True)
    a['t_utc'] = pd.to_datetime(a.ts_event, format='ISO8601', utc=True)
    yrs = a.t_utc.dt.year
    a['contract'] = [full_contract('MES', s, y) for s, y in zip(a.symbol, yrs)]
    a = a.rename(columns={'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v', 'instrument_id': 'iid'})
    return a[['t_utc', 'iid', 'contract', 'o', 'h', 'l', 'c', 'v']].sort_values(['t_utc', 'contract']).reset_index(drop=True)


def build_mes_1m():
    log('[mes_1m] MES front-month 1-minute 2021-2026')
    rep = {'source': 'Databento GLBX.MDP3 MES.FUT ohlcv-1m per contract (via GitHub dschace/trading-model; research only)'}
    d = load_mes_contracts()
    rep['raw'] = {'rows_outrights': int(len(d)), 'contracts': int(d.contract.nunique()), 'dup_t_contract': int(d.duplicated(['t_utc', 'contract']).sum())}
    d['session_date'] = session_date_cme(d.t_utc)
    sv = d.groupby(['session_date', 'contract']).v.sum().unstack(fill_value=0)
    dom = sv.idxmax(axis=1)
    tot = sv.sum(axis=1)
    degraded = set(dbn_degraded_dates(P_MES_DIR / 'condition.json'))
    m = d[d.contract == d.session_date.map(dom)].copy()
    # drop the first (partial) session if the data starts mid-session, and the last if it ends mid-session
    m['degraded'] = m.t_utc.dt.tz_localize(None).dt.normalize().isin(degraded)
    g = m.groupby('session_date')
    sess = pd.DataFrame({'contract': g.contract.first(), 'bars': g.size(), 'v': g.v.sum(), 'degraded': g.degraded.any()})
    sess['mid_roll'] = False
    sess['dom_contract'] = dom.reindex(sess.index)
    sess['dom_share'] = (sv.max(axis=1) / tot).reindex(sess.index).round(4)
    sess['non_dominant'] = False
    sess['roll_window'] = False
    sess = session_flags(sess, m.sort_values('t_utc'))
    chg = m.contract != m.contract.shift()
    spreads, rolls = [], []
    for i in np.flatnonzero(chg.to_numpy())[1:]:
        old, new, t_new = m.contract.iat[i - 1], m.contract.iat[i], m.t_utc.iat[i]
        sp, at = spread_from_contracts(d, old, new, t_new)
        spreads.append((t_new, np.nan if sp is None else sp))
        rolls.append({'from': old, 'to': new, 'first_bar_utc': str(t_new), 'spread': sp, 'measured_at': at})
    m = m.reset_index(drop=True)
    m['adj_offset'] = panama_offsets(m, spreads)
    m['rth'] = rth_flag(m.t_utc)
    m['d_cr1m'] = candle_dir(m.o, m.c).astype(np.int64) * m.v
    m['v'] = m.v.astype(np.int64)
    m = m.merge(sess[['roll_session', 'dom_share', 'clean_session']].rename_axis('session_date').reset_index(), on='session_date', how='left')
    rep['rolls'] = rolls
    rep['checks'] = bar_checks(m)
    rep['coverage_per_year'] = per_year_coverage(m)
    rep['sessions'] = {'total': int(len(sess)), 'clean': int(sess.clean_session.sum()), 'roll_session': int(sess.roll_session.sum()),
                       'degraded': int(sess.degraded.sum()), 'partial': [str(x.date()) for x in sess.index[sess.partial]],
                       'low_dom_share_lt_0.70': int((sess.dom_share < 0.70).sum())}
    rep['missing_weekdays'] = missing_weekdays(sess.index, sess.index.min(), sess.index.max())
    write_parquet(m[['t_utc', 'o', 'h', 'l', 'c', 'v', 'contract', 'adj_offset', 'session_date', 'rth', 'd_cr1m', 'roll_session', 'degraded',
                     'dom_share', 'clean_session']], 'mes_1m_2021-2026.parquet')
    write_parquet(sess.rename_axis('session_date').reset_index(), 'mes_1m_2021-2026_sessions.parquet')
    update_manifest('mes_1m', rep)
    log(json.dumps({k: rep[k] for k in ('checks', 'sessions')}, indent=1, default=str))


# -------------------------------------------------------------------------------------------------------- topstepx
def build_topstepx():
    log('[topstepx] TopstepX ES / MES 1s and 1m bars')
    rep = {'source': 'TopstepX/ProjectX API bars committed to GitHub axb0306/cme-futures-ohlc (no licence stated; research only). '
                     'Files named *_tick_* are 1-second OHLCV bars.'}
    dpc_es = load_dbn_es_contracts()
    dpc_mes = load_mes_contracts()
    for root, dpc in (('ES', dpc_es), ('MES', dpc_mes)):
        r = {}
        s = pd.read_csv(glob.glob(str(P_TSX / f'{root}_tick_*.csv'))[0])
        m = pd.read_csv(glob.glob(str(P_TSX / f'{root}_1min_*.csv'))[0])
        for df in (s, m):
            df['t_utc'] = pd.to_datetime(df.datetime, format='ISO8601').dt.tz_localize('UTC')
            df.rename(columns={'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'}, inplace=True)
            df.drop(columns='datetime', inplace=True)
            df.sort_values('t_utc', inplace=True)
            df.drop_duplicates('t_utc', keep='last', inplace=True)
            df.reset_index(drop=True, inplace=True)
            df['session_date'] = session_date_cme(df.t_utc)
            df['rth'] = rth_flag(df.t_utc)
        # contract label per session by matching 1m closes with Databento per-contract bars
        j = m[['t_utc', 'c', 'v', 'session_date']].merge(dpc[['t_utc', 'contract', 'c', 'v']], on=['t_utc', 'c'], suffixes=('', '_d'))
        lab = j.groupby('session_date').contract.agg(lambda x: x.mode().iloc[0])
        m['contract'] = m.session_date.map(lab)
        s['contract'] = s.session_date.map(lab)
        roll_sess = set(lab.index[(lab != lab.shift()) & lab.shift().notna()])
        for df in (s, m):
            df['roll_session'] = df.session_date.isin(roll_sess)
        jj = m.merge(dpc[['t_utc', 'contract', 'c', 'v']], on=['t_utc', 'contract'], suffixes=('', '_d'))
        r['xcheck_1m_vs_databento_same_contract'] = {'n': int(len(jj)), 'v_exact': round(float((jj.v == jj.v_d).mean()), 4),
                                                     'c_exact': round(float((jj.c == jj.c_d).mean()), 4)}
        r['contract_by_session'] = {str(k.date()): v for k, v in lab.items() if lab.shift().get(k) != v}
        # 1s completeness per minute
        s['minute'] = s.t_utc.dt.floor('1min')
        agg = s.groupby('minute').agg(v1s=('v', 'sum'), n1s=('v', 'size'))
        s['dir_cr'] = candle_dir(s.o, s.c)
        agg['d_cr1s'] = (s.dir_cr.astype(np.int64) * s.v).groupby(s.minute).sum()
        m = m.merge(agg, left_on='t_utc', right_index=True, how='left')
        m['has_1s'] = m.v1s.notna()
        m['complete_1s'] = m.v1s == m.v
        m.loc[~m.complete_1s, 'd_cr1s'] = np.nan
        m['d_cr1m'] = candle_dir(m.o, m.c).astype(np.int64) * m.v
        s['minute_complete'] = s.minute.map(m.set_index('t_utc').complete_1s).fillna(False).astype(bool)
        s = s.drop(columns=['minute', 'dir_cr'])
        span = (m.t_utc >= s.t_utc.min()) & (m.t_utc <= s.t_utc.max())
        r['1s_checks'] = bar_checks(s)
        r['1m_checks'] = bar_checks(m)
        r['1s_coverage'] = {'minutes_in_1s_span': int(span.sum()), 'with_1s': int(m.has_1s[span].sum()), 'complete': int(m.complete_1s[span].sum()),
                            'rth_minutes_in_span': int((span & m.rth).sum()), 'rth_complete': int((m.complete_1s & m.rth & span).sum()),
                            'sessions_with_1s': int(s.session_date.nunique())}
        cs = m[span].groupby('session_date').agg(rth=('rth', 'sum'), rth_complete=('complete_1s', lambda x: int((x & m.loc[x.index, 'rth']).sum())))
        r['1s_rth_complete_by_session'] = {str(k.date()): f'{int(v.rth_complete)}/{int(v.rth)}' for k, v in cs.iterrows()}
        rep[root] = r
        lo = root.lower()
        write_parquet(s[['t_utc', 'o', 'h', 'l', 'c', 'v', 'contract', 'session_date', 'rth', 'roll_session', 'minute_complete']], f'{lo}_topstepx_2026_1s.parquet')
        write_parquet(m[['t_utc', 'o', 'h', 'l', 'c', 'v', 'contract', 'session_date', 'rth', 'roll_session', 'd_cr1m', 'd_cr1s', 'has_1s', 'complete_1s']],
                      f'{lo}_topstepx_2026_1m.parquet')
        log(root, json.dumps({k: r[k] for k in ('xcheck_1m_vs_databento_same_contract', '1s_coverage')}))
    update_manifest('topstepx', rep)


# ---------------------------------------------------------------------------------------------------------- spy_1m
def build_spy_1m():
    log('[spy_1m] SPY 1-minute 2000-2026')
    rep = {'source': 'GitHub prsdro/spy data/candles_1m.csv.gz (vendor undisclosed, no licence; research only)'}
    s = pd.read_csv(P_SPY)
    rep['raw_rows'] = int(len(s))
    rep['raw_sorted'] = bool(pd.to_datetime(s.timestamp).is_monotonic_increasing)
    rep['exact_duplicate_rows'] = int(s.duplicated().sum())
    s = s.drop_duplicates()
    tl = pd.to_datetime(s.timestamp, format='%Y-%m-%d %H:%M:%S')
    s['t_utc'] = tl.dt.tz_localize(ET, ambiguous='NaT', nonexistent='NaT').dt.tz_convert('UTC')
    s = s.rename(columns={'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'}).drop(columns='timestamp')
    rep['conflicting_duplicate_timestamps'] = int(s.t_utc.duplicated(keep=False).sum())
    s = s.sort_values(['t_utc', 'v']).drop_duplicates('t_utc', keep='last').reset_index(drop=True)
    s['session_date'] = s.t_utc.dt.tz_convert(ET).dt.tz_localize(None).dt.normalize()
    s['rth'] = rth_flag(s.t_utc)
    s['v'] = s.v.astype(np.int64)
    s['d_cr1m'] = candle_dir(s.o, s.c).astype(np.int64) * s.v
    rep['checks'] = bar_checks(s, tick=0.0)
    cov = per_year_coverage(s)
    rep['coverage_per_year'] = cov
    rth_days = s[s.rth].groupby('session_date').size()
    rep['rth_days_lt_380_bars'] = int((rth_days < 380).sum())
    rep['missing_weekdays_count'] = len(missing_weekdays(rth_days.index, '2000-01-03', s.session_date.max()))
    rep['missing_weekdays_2016'] = [d for d in missing_weekdays(rth_days.index, '2016-01-01', '2016-12-31')]
    # cross-checks of RTH volume and close against other SPY 1m sources
    xc = {}
    r = s[s.rth].set_index('t_utc')
    hf = pd.read_csv(P_SPY_HF)
    hf['t_utc'] = pd.to_datetime(hf.ts_et_bar_start).dt.tz_localize(ET).dt.tz_convert('UTC')
    z = zipfile.ZipFile(P_SPY_FRD)
    fr = pd.read_csv(z.open([n for n in z.namelist() if n.lower().endswith(('.txt', '.csv'))][0]))
    fr['t_utc'] = pd.to_datetime(fr.timestamp).dt.tz_localize(ET).dt.tz_convert('UTC')
    ib = pd.read_csv(P_SPY_IB)
    ib['t_utc'] = pd.to_datetime(ib.date, utc=True)
    for name, x in (('highfreq_wrds_2008_2014', hf), ('firstrate_sample_2022_2023', fr), ('ibkr_2024_2025', ib)):
        x = x.set_index('t_utc')
        jj = r.join(x[['close', 'volume']].astype(float), how='inner')
        xc[name] = {'n': int(len(jj)), 'close_abs_diff_le_0.01': round(float(((jj.c - jj.close).abs() <= 0.0101).mean()), 4),
                    'volume_ratio_prsdro_over_ref': round(float(jj.v.sum() / jj.volume.sum()), 4)}
    rep['xcheck_rth'] = xc
    write_parquet(s[['t_utc', 'o', 'h', 'l', 'c', 'v', 'session_date', 'rth', 'd_cr1m']], 'spy_1m_2000-2026.parquet')
    update_manifest('spy_1m', rep)
    log(json.dumps({k: rep[k] for k in ('checks', 'exact_duplicate_rows', 'missing_weekdays_2016', 'xcheck_rth')}, indent=1))


BUILDERS = {'es_tick': build_es_tick, 'es_1m': build_es_1m, 'mes_1m': build_mes_1m, 'topstepx': build_topstepx, 'spy_1m': build_spy_1m}

if __name__ == '__main__':
    todo = sys.argv[1:] or list(BUILDERS)
    unknown = [k for k in todo if k not in BUILDERS]
    if unknown:
        raise SystemExit(f'unknown dataset(s) {unknown}; choose from {list(BUILDERS)}')
    CLEAN.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    for k in todo:
        BUILDERS[k]()
