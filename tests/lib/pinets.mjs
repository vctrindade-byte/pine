// Carrega o PineTS (npm "pinets", versão fixada 0.11.0) e executa scripts Pine sobre barras sintéticas.
//
// Resolução do módulo, por ordem:
//   1. import('pinets')                      — node_modules do repositório (npm install / ln -s)
//   2. require('pinets') via createRequire     — respeita NODE_PATH (o import ESM ignora NODE_PATH)
//   3. $PINETS_DIR/pinets/dist/pinets.min.es.js ou $PINETS_DIR/dist/pinets.min.es.js

import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { Worker } from 'node:worker_threads';
import { availableParallelism } from 'node:os';

export const PINETS_VERSION = '0.11.0';
let cached = null;

export async function loadPineTS() {
  if (cached) return cached;
  const errors = [];
  try {
    cached = await import('pinets');
    return cached;
  } catch (e) { errors.push(`import('pinets'): ${e.code || e.message}`); }
  try {
    const require = createRequire(import.meta.url);
    cached = require('pinets');
    return cached;
  } catch (e) { errors.push(`require('pinets') [NODE_PATH=${process.env.NODE_PATH || ''}]: ${e.code || e.message}`); }
  const dir = process.env.PINETS_DIR;
  if (dir) {
    for (const p of [join(dir, 'pinets', 'dist', 'pinets.min.es.js'), join(dir, 'dist', 'pinets.min.es.js')]) {
      if (existsSync(p)) { cached = await import(pathToFileURL(p).href); return cached; }
    }
    errors.push(`PINETS_DIR=${dir}: pinets.min.es.js não encontrado`);
  }
  const err = new Error('PineTS não encontrado. Corra "npm install" (ou defina NODE_PATH/PINETS_DIR). Tentativas:\n  ' + errors.join('\n  '));
  err.code = 'PINETS_MISSING';
  throw err;
}

export async function pinetsVersion() {
  try {
    const require = createRequire(import.meta.url);
    return require('pinets/package.json').version;
  } catch { /* exports pode bloquear package.json */ }
  return PINETS_VERSION + '?';
}

/** Símbolo sintético por omissão (cripto 24/7, UTC). */
export const DEFAULT_SYMINFO = Object.freeze({
  ticker: 'SYNBTC', tickerid: 'HARNESS:SYNBTC', prefix: 'HARNESS', root: 'SYNBTC', description: 'Sintético (harness)',
  type: 'crypto', basecurrency: 'BTC', currency: 'USD', timezone: 'UTC', session: '24x7',
  mintick: 0.01, pricescale: 100, minmove: 1, pointvalue: 1, mincontract: 0.00001, volumetype: 'base',
  country: '', isin: '', current_contract: '', main_tickerid: 'HARNESS:SYNBTC', expiration_date: NaN,
  employees: NaN, industry: '', sector: '', shareholders: NaN, shares_outstanding_float: NaN, shares_outstanding_total: NaN,
});

/**
 * Provider PineTS em memória. O PineTS chama getMarketData(tickerId, timeframe, ...) para o gráfico e
 * getSymbolInfo para syminfo.* (mintick, volumetype, timezone). getFootprintData alimenta request.footprint().
 * ltfBars (opcional): { [timeframe]: Kline[] } para request.security_lower_tf nativo (não usado pelo stub).
 */
export function makeProvider({ klines, timeframe = '5', syminfo = {}, footprint = null, ltfBars = null }) {
  const info = { ...DEFAULT_SYMINFO, ...syminfo };
  return {
    calls: [],
    async getMarketData(tickerId, tf, limit, sDate, eDate) {
      this.calls.push({ tickerId, tf, limit, sDate, eDate });
      if (String(tf) === String(timeframe)) return klines;
      if (ltfBars && ltfBars[tf]) {
        return ltfBars[tf].filter((k) => (sDate === undefined || k.openTime >= sDate) && (eDate === undefined || k.openTime <= eDate));
      }
      return [];
    },
    async getSymbolInfo() { return info; },
    ...(footprint ? { async getFootprintData() { return footprint; } } : {}),
    configure() {},
  };
}

/** Converte um valor de plot do PineTS em número (na → NaN; bool → 0/1). */
export function toNum(v) {
  if (v === null || v === undefined) return NaN;
  if (typeof v === 'boolean') return v ? 1 : 0;
  if (typeof v === 'number') return v;
  const n = Number(v);
  return Number.isFinite(n) ? n : NaN;
}

/**
 * Executa um script Pine no PineTS.
 * @returns {{ plots: Map<string, Float64Array>, plotOrder: string[], labels: object[], alerts: object[],
 *            tables: any, warnings: object[], ms: number, ctx: any }}
 */
export async function runPineInProcess({ source, klines, timeframe = '5', syminfo = {}, inputs = {}, footprint = null, ltfBars = null, alertMode = 'all' }) {
  const { PineTS, Indicator } = await loadPineTS();
  const provider = makeProvider({ klines, timeframe, syminfo, footprint, ltfBars });
  const pine = new PineTS(provider, (syminfo.tickerid ?? DEFAULT_SYMINFO.tickerid), timeframe, klines.length);
  if (typeof pine.setAlertMode === 'function') pine.setAlertMode(alertMode);
  const ind = new Indicator(source, inputs);
  const t0 = Date.now();
  const ctx = await pine.run(ind);
  const ms = Date.now() - t0;
  const plots = new Map();
  const plotOrder = [];
  let labels = [];
  let tables = null;
  const lines = [];
  for (const [title, p] of Object.entries(ctx.plots || {})) {
    // labels com force_overlay = true vão para "__labels_overlay__"; os restantes para "__labels__"
    if (title.startsWith('__labels')) { labels.push(...flattenDrawings(p)); continue; }
    if (title.startsWith('__lines')) { lines.push(...flattenDrawings(p)); continue; }
    if (title.startsWith('__tables')) { const v = p?.data?.[0]?.value; if (v && (!tables || (Array.isArray(v) && v.length))) tables = v; continue; }
    if (title.startsWith('__')) continue;
    const data = p?.data || [];
    if (data.length !== klines.length) {
      // séries de fill/bgcolor/hline podem ter outro formato; guardamos só as séries por barra
      if (data.length === 0) continue;
    }
    const arr = new Float64Array(klines.length).fill(NaN);
    for (let i = 0; i < Math.min(data.length, klines.length); i++) arr[i] = toNum(data[i]?.value);
    plots.set(title, arr);
    plotOrder.push(title);
  }
  return { plots, plotOrder, labels, lines, alerts: ctx.alerts || [], tables, warnings: ctx.warnings || [], ms, ctx, indicator: ind, provider };
}

// ───────────── Execução isolada em worker threads ─────────────
// O PineTS 0.11.0 fica progressivamente mais lento quando várias execuções correm no mesmo isolate V8
// (medido: 4,7 s → 8,6 s em 5 execuções iguais, com o heap estável). Cada execução corre por isso num
// worker novo (isolate limpo), o que também permite paralelismo: HARNESS_JOBS (por omissão nº de CPUs − 1, máx. 4).
// HARNESS_INPROCESS=1 força a execução no processo principal (depuração).

const MAX_JOBS = Math.max(1, Number(process.env.HARNESS_JOBS) || Math.min(4, Math.max(1, availableParallelism() - 1)));
let active = 0;
const queue = [];
function acquire(priority = false) { return new Promise((res) => { if (active < MAX_JOBS) { active++; res(); } else if (priority) queue.unshift(res); else queue.push(res); }); }
function release() { const next = queue.shift(); if (next) next(); else active--; }
export function maxJobs() { return MAX_JOBS; }

/** Serializa um resultado para atravessar o postMessage (sem ctx/indicator/provider). */
export function serializeRun(r) {
  return { plots: [...r.plots.entries()], plotOrder: r.plotOrder, labels: r.labels, lines: r.lines, alerts: r.alerts, tables: r.tables, warnings: r.warnings, ms: r.ms };
}
function deserializeRun(o) { return { ...o, plots: new Map(o.plots) }; }

/**
 * Executa um script Pine no PineTS (num worker isolado, salvo HARNESS_INPROCESS=1).
 * @returns {{ plots: Map<string, Float64Array>, plotOrder: string[], labels: object[], alerts: object[], tables: any, warnings: object[], ms: number }}
 */
export async function runPine(job, { priority = false } = {}) {
  if (process.env.HARNESS_INPROCESS === '1') return runPineInProcess(job);
  await acquire(priority);
  try {
    return await new Promise((resolveP, rejectP) => {
      const w = new Worker(new URL('./pine_worker.mjs', import.meta.url), { workerData: job });
      let done = false;
      w.once('message', (msg) => {
        done = true;
        w.terminate();
        if (msg.ok) resolveP(deserializeRun(msg.result));
        else { const e = new Error(msg.error.message); e.stack = msg.error.stack; e.code = msg.error.code; rejectP(e); }
      });
      w.once('error', (e) => { done = true; rejectP(e); });
      w.once('exit', (code) => { if (!done) rejectP(new Error(`worker do PineTS terminou com código ${code}`)); });
    });
  } finally { release(); }
}

function flattenDrawings(p) {
  const out = [];
  const data = p?.data || [];
  for (const d of data) {
    const v = d?.value;
    if (Array.isArray(v)) out.push(...v);
    else if (v) out.push(v);
  }
  return out;
}

/**
 * Série de um plot pelo título declarado no código. Títulos repetidos recebem no PineTS o sufixo "#<n>"
 * (ex.: "Z#14"); aqui devolve-se a primeira chave cujo título-base coincide.
 */
export function getPlot(run, title) {
  if (run.plots.has(title)) return run.plots.get(title);
  for (const k of run.plotOrder) if (k.replace(/#\d+$/, '') === title) return run.plots.get(k);
  return undefined;
}

/** Barra (bar_index) de um label do PineTS, tolerante a formatos. */
export function labelBar(l) {
  for (const k of ['x', 'bar_index', '_x']) if (Number.isFinite(l?.[k])) return l[k];
  return NaN;
}

export function labelText(l) {
  return String(l?.text ?? l?._text ?? '');
}
