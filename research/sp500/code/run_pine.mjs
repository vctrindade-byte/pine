#!/usr/bin/env node
// Runs the REAL built Standard edition (price_cvd_normalizer.pine) in PineTS over chart bars exported by
// validate_pine.py, with the repository's LTF stub (tests/lib/preprocess.mjs + channel.mjs: the per-bar delta travels in
// the milliseconds of openTime), and writes every per-bar value needed to check the Python port bit by bit.
//
// The indicator file is never modified. The in-memory copy gets (1) the harness stub of request.security_lower_tf and
// (2) observation-only plots appended at the very end of the script (they read globals after every calculation of the
// bar and feed nothing back). The script's own alertcondition()/alert() calls are also returned.
//
// Usage: node run_pine.mjs --bars bars.json --out pine.json [--tf 5] [--prec auto|s1|m1] [--pine FILE] [--repo DIR]
//   bars.json: { "klines": [{openTime, closeTime, open, high, low, close, volume}, ...] }
//   env PINE_REPO (default: the repository that contains this file, ../../.. from research/sp500/code),
//   NODE_PATH or PINETS_DIR to find PineTS 0.11.0 (the repository's node_modules after `npm install` also works).

import { readFileSync, writeFileSync } from 'node:fs';
import { resolve, join, dirname } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const args = Object.fromEntries(process.argv.slice(2).reduce((a, x, i, all) => {
  if (x.startsWith('--')) a.push([x.slice(2), all[i + 1] && !all[i + 1].startsWith('--') ? all[i + 1] : 'true']);
  return a;
}, []));
const REPO = resolve(args.repo || process.env.PINE_REPO || join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..'));
const lib = (f) => import(pathToFileURL(join(REPO, 'tests', 'lib', f)).href);
const { preprocess } = await lib('preprocess.mjs');
const { runPineInProcess } = await lib('pinets.mjs');
const { inputsMeta, parseEnums, resolveOverrides } = await lib('inputs.mjs');

const pineFile = resolve(args.pine || join(REPO, 'price_cvd_normalizer.pine'));
const src = readFileSync(pineFile, 'utf8').replace(/\r\n/g, '\n');

// Observation-only instrumentation (appended at global scope after the last statement of the script).
const FLAGS = ['hqOk', 'gapBar', 'noObs', 'zCalOk', 'gateOn', 'evWeak', 'absorbed', 'pinned', 'pwf', 'absNewCl', 'pinNewCl',
  'pwfNewCl', 'newAbs', 'newPin', 'newPwf', 'resCont', 'resHeld', 'resExp', 'crossUp', 'crossDn', 'alZUp', 'alZDn', 'pivTop',
  'pivBot', 'alPinO', 'hollow', 'upArmed', 'dnArmed', 'resWeak', 'resLowC'];
const SERIES = ['rBar', 'delta', 'd', 'r', 'srP', 'sdP', 'rhoP', 'ur', 'ud', 'dStat', 'rmsD', 'nCalD', 'zDiv', 'fE', 'pE', 'zF',
  'zP', 'nCalE', 'evSide', 'evHi', 'evLo', 'evBar', 'resSide', 'hqRun', 'lqBar', 'tier', 'cvdC', 'ph', 'pl', 'absStart',
  'obsIdx', 'hiKe', 'loKe', 'pLeg', 'fLeg', 'barVol'];
const instr = ['', '// [validation] observation-only plots (read globals; nothing feeds back into the calculation)',
  `int __vFlags = ${FLAGS.map((f, i) => `(${f} ? ${2 ** i} : 0)`).join(' + ')}`,
  'plot(__vFlags, "VAL_flags", display = display.data_window)',
  ...SERIES.map((s) => `plot(${s}, "VAL_${s}", display = display.data_window)`), ''].join('\n');

const { code: stubbed } = preprocess(src, { stub: true });
const code = stubbed + '\n' + instr;

const meta = await inputsMeta(code);
const enums = parseEnums(src);
const wanted = { precIn: args.prec || 'auto', pivIn: true };
if (args.lowconf) wanted.lowConfIn = args.lowconf === 'true';
if (args.inputs) Object.assign(wanted, JSON.parse(args.inputs));   // e.g. '{"rhoMinIn":0,"nIn":50}'
const { overrides, resolved } = resolveOverrides(meta, enums, wanted);

const bars = JSON.parse(readFileSync(resolve(args.bars), 'utf8'));
const klines = bars.klines.map((k) => (k.volume === null ? { ...k, volume: NaN } : k));
const tf = String(args.tf || '5');
const t0 = Date.now();
const r = await runPineInProcess({ source: code, klines, timeframe: tf, inputs: overrides, syminfo: bars.syminfo || {} });
const wall = Date.now() - t0;

const pick = (title) => {
  if (r.plots.has(title)) return r.plots.get(title);
  for (const k of r.plotOrder) if (k.replace(/#\d+$/, '') === title) return r.plots.get(k);
  return null;
};
const out = { n: klines.length, tf, pine: pineFile, inputs: resolved, ms: r.ms, wall_ms: wall, flags: FLAGS, series: {}, plots: {} };
const arr = (a) => Array.from(a, (v) => (Number.isFinite(v) ? v : null));
for (const s of ['VAL_flags', ...SERIES.map((x) => `VAL_${x}`)]) {
  const a = pick(s);
  if (!a) throw new Error(`instrumentation plot ${s} not found`);
  out.series[s.replace(/^VAL_/, '')] = arr(a);
}
for (const t of ['Z (valor)', 'zF (evento)', 'zP (evento)', 'Gate (1 = aberto)', 'Qualidade (0–3)', 'Delta (barra)', 'σr (bps)',
  'σΔ', 'ρ(r, Δ)', 'Perna do preço (P_K)', 'Perna do fluxo (F_K)', 'Confiança do evento resolvido']) {
  const a = pick(t);
  if (a) out.plots[t] = arr(a);
}
out.alerts = r.alerts.map((a) => ({ type: a.type, title: a.title ?? null, bar: a.bar_index ?? a.barIndex ?? null, message: a.message ?? null }));
out.labels = r.labels.map((l) => ({ x: l.x ?? l.bar_index ?? null, text: String(l.text ?? l._text ?? '') }));
out.warnings = (r.warnings || []).slice(0, 20);
writeFileSync(resolve(args.out), JSON.stringify(out));
console.log(JSON.stringify({ n: out.n, tf, ms: r.ms, wall_ms: wall, alerts: out.alerts.length, labels: out.labels.length,
  heapMB: Math.round(process.memoryUsage().heapUsed / 1e6) }));
