// T0 auto-verificação do harness, T4 matriz de execução, T5 calibração nula, T6 detecção + auditoria exacta dos
// eventos, T7 invariantes, T8 concordância com a referência JS (spec §5/§7), T9 motor de delta e tier, T10 LTF
// nativo, T11 timeframes/âncoras/qualidade.

import { loadPineTS, pinetsVersion, runPine, labelBar, labelText, getPlot, maxJobs } from './pinets.mjs';
import { generate, toKlines } from './synth.mjs';
import { stubPineSource, stubDelta, stubDeltaBvc, STUB_K, NO_INTRABARS, encodeQ, decodeQ } from './channel.mjs';
import { matrixData, nullData, gapData, jumpData, seamData, absorptionData, pwfData, engineData, footprintFor, nativeLtfData } from './datasets.mjs';
import { computeRBar, computeRef, computeBarDelta, utcDayKey, utcWeekKey, utcMonthKey, refLtfSigned } from './refz.mjs';
import { probeBuiltins } from './builtins.mjs';
import { fmt, pct } from './report.mjs';
import { isF, finiteFrac, exceedFrac, meanSd, pearsonArr, relErr, quantile, compareSeries, range } from './util.mjs';

// detecção = etiqueta/alerta de absorção ou travado; as resoluções (títulos com "→") não contam
const ABS_LABEL_RE = /absorvid|travad/i;
const isResolutionTitle = (title) => /→/.test(title || '');
const PWF_LABEL_RE = /sem fluxo/i;

function defNum(target, varId, fallback) {
  const m = target.meta.find((x) => x.varId === varId);
  return m && isF(Number(m.defval)) ? Number(m.defval) : fallback;
}

/** Parâmetros por omissão do alvo; ke/life/hqNeed como no indicador (spec §5/§7) para um gráfico de tfSec segundos. */
function params(target, tfSec = 300) {
  const N = defNum(target, 'nIn', 100), K = defNum(target, 'kIn', 20), M = defNum(target, 'mIn', 1000);
  const keRaw = Math.max(1, Math.round((defNum(target, 'evWinIn', 15) * 60) / tfSec));
  const ke = Math.min(keRaw, Math.max(1, Math.floor(M / 20)));
  const life = Math.max(1, Math.round((defNum(target, 'lifeIn', 60) * 60) / tfSec));
  return { N, K, M, W: defNum(target, 'wIn', 100), clip: defNum(target, 'clipIn', 4), thr: defNum(target, 'thrIn', 2),
    rhoMin: defNum(target, 'rhoMinIn', 0.3), ke, life, hqNeed: N + Math.max(K, ke),
    zf: defNum(target, 'zfIn', 2), pin: defNum(target, 'pinIn', 3), pinP: defNum(target, 'pinPIn', 0.5),
    piv: { L: defNum(target, 'pivLIn', 5), R: defNum(target, 'pivRIn', 2), min: defNum(target, 'pivMinIn', 5),
      max: defNum(target, 'pivMaxIn', 60), mag: defNum(target, 'pivMagIn', 0.5) } };
}

function requireRole(tc, target, run, role, label) {
  const p = target.role(run, role);
  if (!p) { tc.fail(`plot "${label}" encontrado`, `candidatos no código: ${(target.roles[role] || []).join(', ') || '(nenhum)'} · plots executados: ${run.plotOrder.slice(0, 40).join(', ')}`); return null; }
  return p;
}

function optRole(target, run, role) { return target.role(run, role); }

function arr(data, f) { return Float64Array.from(data.bars, f); }

// ───────────────────────────── T0 ─────────────────────────────
export async function t0SelfCheck(tc, targets) {
  const mod = await loadPineTS();
  tc.check(Boolean(mod.PineTS && mod.Indicator), 'PineTS carregado', `versão ${await pinetsVersion()}`);
  // canal + stub isolados num script mínimo
  const { bars } = generate({ seed: 2, nBars: 700, noIntrabarsProb: 0.05, zeroVolProb: 0.02 });
  const src = ['//@version=6', 'indicator("harness self-check")', stubPineSource(),
    '[aCand, aBvc, aVol] = __ltfStub()', 'int nIntra = na(aVol) ? 0 : aVol.size()',
    'plot(nIntra > 0 ? aCand.sum() : na, "d")', 'plot(nIntra, "n")', 'plot(timeframe.in_seconds(), "tf")',
    'plot(timeframe.change("1D") ? 1 : 0, "chgD")', 'plot(timeframe.change("1W") ? 1 : 0, "chgW")', 'plot(session.isfirstbar ? 1 : 0, "sfb")',
    'plot(syminfo.mintick, "mt")', 'plot(barstate.isconfirmed ? 1 : 0, "conf")'].join('\n');
  const run = await runPine({ source: src, klines: toKlines(bars), timeframe: '5' }, { priority: true });
  const d = run.plots.get('d'), n = run.plots.get('n');
  let bad = 0;
  bars.forEach((b, i) => {
    const exp = stubDelta(b.code, b.volume);
    if (b.code === NO_INTRABARS ? n[i] !== 0 || isF(d[i]) : n[i] !== STUB_K || Math.abs(d[i] - exp) > 1e-9 * Math.max(1, Math.abs(exp))) bad++;
  });
  tc.check(bad === 0, `stub LTF: ${STUB_K} intrabars por barra; a soma é o delta decodificado de time % 1000 (código 999 → sem intrabars)`, `${bad}/${bars.length} barras divergentes`);
  let qbad = 0;
  for (let q = -1; q <= 1.0000001; q += 0.001) if (Math.abs(decodeQ(encodeQ(q)) - q) > 0.5 / 499 + 1e-12) qbad++;
  tc.check(qbad === 0, 'canal: erro de quantização ≤ 1/998 em Δ/V');
  tc.check(run.plots.get('tf').every((v) => v === 300), 'timeframe.in_seconds() = 300 (gráfico de 5 min via provider)');
  const expD = bars.map((b, i) => (i > 0 && utcDayKey(b.openTime) !== utcDayKey(bars[i - 1].openTime) ? 1 : 0));
  const expW = bars.map((b, i) => (i > 0 && utcWeekKey(b.openTime) !== utcWeekKey(bars[i - 1].openTime) ? 1 : 0));
  const gotD = Array.from(run.plots.get('chgD')), gotW = Array.from(run.plots.get('chgW')), sfb = Array.from(run.plots.get('sfb'));
  tc.check(gotD.every((v, i) => v === expD[i]), 'timeframe.change("1D") nas viragens de dia UTC, apesar dos ms do canal', `esperado ${expD.filter(Boolean).length}, obtido ${gotD.filter(Boolean).length}`);
  tc.check(gotW.every((v, i) => v === expW[i]), 'timeframe.change("1W") às segundas 00:00 UTC');
  tc.check(sfb.every((v, i) => v === (i === 0 ? 1 : expD[i])), 'session.isfirstbar no início de cada dia UTC');
  tc.check(run.plots.get('mt').every((v) => v === 0.01), 'syminfo.mintick = 0.01 via provider');
  tc.check(run.plots.get('conf').every((v) => v === 1), 'barstate.isconfirmed verdadeiro em todas as barras históricas');
  for (const t of targets) {
    if (!t.ready) continue;
    const { used, missing } = await probeBuiltins(t.source);
    t.builtins = { used, missing };
    tc.check(missing.length === 0, `${t.info.label}: todos os built-ins usados existem no PineTS (${used.length})`, missing.length ? `em falta: ${missing.join(', ')} — adicionar shim em tests/lib/preprocess.mjs` : '', 'warn');
    tc.note(`${t.info.label}: ${t.plotTitles.length} plots com título; papéis: ` + ['pLine', 'fLine', 'z', 'zMain', 'delta', 'cvdA', 'sr', 'sd', 'rho', 'tier']
      .map((r) => `${r}→${(t.roles[r] || [])[0] ?? '∅'}`).join(', '));
    for (const r of ['pLine', 'fLine', 'z']) tc.check((t.roles[r] || []).length > 0, `${t.info.label}: título do papel "${r}" descoberto no código`, (t.roles[r] || []).join(' | '));
    for (const k of ['srcIn', 'precIn', 'modeIn', 'anchIn']) tc.check(t.hasInput(k), `${t.info.label}: input "${k}" encontrado`);
  }
}

// ───────────────────────────── T4 ─────────────────────────────
function t4Configs(target, { quick = false, nBars = 3000 } = {}) {
  const P = params(target);
  const data = matrixData(quick ? Math.min(nBars, 1500) : nBars);
  const head = data.bars.findIndex((b) => b.code !== NO_INTRABARS);
  const modes = target.enumOptions('modeIn');
  const sources = [['LTF (stub)', target.option('srcIn', 'ltf'), true], ['barras do gráfico', target.option('srcIn', 'bar'), false]];
  const anchorMembers = quick ? ['auto'] : ['auto', 'd1', 'w1'];
  const anchors = anchorMembers.map((m) => [m, target.option('anchIn', m)]);
  const views = target.enumOptions('viewIn');
  const toggles = ['coneIn', 'pivIn', 'driftIn', 'ovlIn', 'bgIn'].filter((k) => target.hasInput(k));
  const warmLines = Math.max(2 * P.N + P.K, P.W + P.N + 1) + 5;
  const warmZ = head + 3 * P.N + P.K + 5;
  const cfgs = [];
  let i = 0;
  for (const mode of modes) for (const [srcName, src, isLtf] of sources) for (const [anchName, anch] of anchors) {
    const wanted = { modeIn: mode, srcIn: src, anchIn: anch };
    if (views.length) wanted.viewIn = views[i % views.length];
    toggles.forEach((k, j) => { wanted[k] = ((i >> j) & 1) === 1; });
    i++;
    const label = `${mode} · ${srcName} · âncora ${anchName}${wanted.viewIn ? ' · ' + wanted.viewIn : ''}`;
    cfgs.push({ label, data, wanted, isLtf, hist: /histograma/i.test(wanted.viewIn || '') });
  }
  return { data, cfgs, warmLines, warmZ, toggles };
}

export async function t4Matrix(tc, target, opts = {}) {
  const { data, cfgs, warmLines, warmZ, toggles } = t4Configs(target, opts);
  tc.note(`dados: ${data.desc}`);
  const proms = cfgs.map((c) => target.run(c.data, c.wanted));
  let nRuns = 0, totalMs = 0;
  for (let k = 0; k < cfgs.length; k++) {
    const { label, isLtf, hist } = cfgs[k];
    let run;
    try { run = await proms[k]; } catch (e) { tc.fail(`executa sem excepções: ${label}`, String(e.message || e).split('\n')[0].slice(0, 300)); continue; }
    nRuns++; totalMs += run.ms;
    const pl = requireRole(tc, target, run, 'pLine', 'linha de preço'), fl = requireRole(tc, target, run, 'fLine', 'linha CVD');
    if (!pl || !fl) continue;
    const fp = finiteFrac(pl.values, warmLines), ff = finiteFrac(fl.values, warmLines);
    tc.check(fp >= 0.95 && ff >= 0.95, `linhas finitas ≥95% após aquecimento (${warmLines}): ${label}`, `preço ${pct(fp)}, CVD ${pct(ff)}`, hist ? 'warn' : 'fail');
    const z = target.role(run, 'z');
    if (isLtf) {
      const fz = z ? finiteFrac(z.values, warmZ) : 0;
      tc.check(fz >= 0.95, `Z finito ≥95% após ${warmZ} barras: ${label}`, z ? `${pct(fz)} ("${z.title}")` : 'plot Z não encontrado');
    } else if (z) {
      tc.check(finiteFrac(z.values, 0) === 0, `Z ausente (na) com fonte só-barras (tier 1): ${label}`, `${pct(finiteFrac(z.values, 0))} finito`, 'warn');
    }
    if (run.warnings.length) tc.warn(`avisos do runtime: ${label}`, run.warnings.slice(0, 3).map((w) => w.message).join(' | '));
  }
  tc.note(`${nRuns} execuções, ${(totalMs / 1000).toFixed(1)} s de CPU no PineTS (média ${(totalMs / Math.max(1, nRuns) / 1000).toFixed(2)} s, ${maxJobs()} em paralelo); toggles rodados: ${toggles.join(', ') || '—'}`);
}

function t4fpConfigs(target, { quick = false, nBars = 3000 } = {}) {
  const data = matrixData(quick ? Math.min(nBars, 1500) : nBars);
  let fpSrc = null;
  try { fpSrc = target.option('srcIn', 'fp'); } catch { return { data, fpSrc: null, cases: [] }; }
  const full = footprintFor(data);
  const holes = footprintFor(data, { missingEvery: 7 });
  const cases = [
    { label: 'footprint · sig', wanted: { srcIn: fpSrc, modeIn: target.option('modeIn', 'sig') }, fp: full, tag: 'full' },
    { label: 'footprint · imp', wanted: { srcIn: fpSrc, modeIn: target.option('modeIn', 'imp') }, fp: full, tag: 'full' },
    { label: 'footprint c/ falhas, sem preenchimento', wanted: { srcIn: fpSrc, ...(target.hasInput('fpFillIn') ? { fpFillIn: false } : {}) }, fp: holes, tag: 'holes' },
    ...(target.hasInput('fpFillIn') ? [{ label: 'footprint c/ falhas, preenchido por intrabar', wanted: { srcIn: fpSrc, fpFillIn: true }, fp: holes, tag: 'holes' }] : []),
    { label: 'intrabar (stub) na edição Footprint', wanted: { srcIn: target.option('srcIn', 'ltf') }, fp: null, tag: '' },
  ];
  if (quick) cases.splice(1, 1);
  return { data, fpSrc, cases };
}

/** T4 (Footprint): fonte footprint via provider (getFootprintData), com e sem preenchimento. */
export async function t4Footprint(tc, target, opts = {}) {
  const P = params(target);
  const { data, fpSrc, cases } = t4fpConfigs(target, opts);
  if (!tc.check(Boolean(fpSrc), 'opção "Footprint" no input de fonte')) return;
  const warm = Math.max(2 * P.N + P.K, P.W + P.N + 1) + 5;
  const trueDelta = arr(data, (b) => b.volume * b.q);
  const proms = cases.map((c) => target.run(data, c.wanted, { footprint: c.fp, fpTag: c.tag }));
  for (let k = 0; k < cases.length; k++) {
    const c = cases[k];
    let run;
    try { run = await proms[k]; } catch (e) { tc.fail(`executa sem excepções: ${c.label}`, String(e.message || e).split('\n')[0].slice(0, 300)); continue; }
    const pl = requireRole(tc, target, run, 'pLine', 'linha de preço'), fl = requireRole(tc, target, run, 'fLine', 'linha CVD');
    if (pl && fl) tc.check(finiteFrac(pl.values, warm) >= 0.95 && finiteFrac(fl.values, warm) >= 0.95, `linhas finitas ≥95%: ${c.label}`, `${pct(finiteFrac(pl.values, warm))} / ${pct(finiteFrac(fl.values, warm))}`);
    const dl = optRole(target, run, 'delta'), tier = optRole(target, run, 'tier');
    if (c.tag === 'full' && dl) {
      const idx = range(0, data.bars.length).filter((t) => data.bars[t].volume > 0);
      const cmp = compareSeries(idx, (t) => dl.values[t], (t) => trueDelta[t], 1e-6, 1e-9);
      tc.check(cmp.nBad === 0, `delta do footprint = delta verdadeiro (buy − sell): ${c.label}`, `${cmp.nBad}/${cmp.n} barras fora de 1e-6 (pior ${fmt(cmp.maxErr, 9)} na barra ${cmp.worstIdx})`);
      if (tier) tc.check(idx.every((t) => tier.values[t] === 3), `tier 3 com footprint: ${c.label}`, `valores: ${[...new Set(idx.map((t) => tier.values[t]))].join(',')}`);
    }
    if (c.tag === 'holes' && tier) {
      const missing = range(0, data.bars.length).filter((t) => t % 7 === 6 && data.bars[t].volume > 0 && data.bars[t].code !== NO_INTRABARS && t > 0 && data.bars[t - 1].volume > 0);
      const fill = c.wanted.fpFillIn === true;
      const tiers = [...new Set(missing.map((t) => tier.values[t]))];
      tc.check(fill ? tiers.every((v) => v >= 2) : tiers.every((v) => v <= 1), `barras sem footprint → ${fill ? 'intrabar (tier ≥ 2)' : 'fallback (tier ≤ 1)'}: ${c.label}`, `tiers observados: ${tiers.join(',')}`);
    }
  }
}

// ───────────────────────────── T5 ─────────────────────────────
function statWanted(target) {
  return { srcIn: target.option('srcIn', 'ltf'), precIn: target.option('precIn', 's1'), modeIn: target.option('modeIn', 'sig') };
}

export async function t5Null(tc, target, { nBars = 4500 } = {}) {
  const data = nullData(Math.max(4000, nBars));
  tc.note(`dados: ${data.desc}; precisão 1S (tier 3)`);
  const run = await target.run(data, statWanted(target));
  const z = requireRole(tc, target, run, 'z', 'Z');
  if (!z) return;
  const e2 = exceedFrac(z.values, 2), e3 = exceedFrac(z.values, 3);
  const ms = meanSd(z.values);
  tc.check(data.bars.length >= 4000, 'série nula com ≥ 4000 barras', `${data.bars.length}`);
  tc.check(e2.n >= 3000, 'Z definido em ≥ 3000 barras', `${e2.n} ("${z.title}")`);
  tc.check(e2.frac >= 0.02 && e2.frac <= 0.12, 'P(|Z| ≥ 2) ∈ [2%, 12%]', `${pct(e2.frac, 2)} (${e2.count}/${e2.n})`);
  tc.check(e3.frac < 0.03, 'P(|Z| ≥ 3) < 3%', `${pct(e3.frac, 2)} (${e3.count}/${e3.n})`);
  const gate = optRole(target, run, 'gate');
  const rho = optRole(target, run, 'rho');
  const gateFrac = gate ? gate.values.filter((v) => v === 1).length / Math.max(1, gate.values.filter(isF).length) : NaN;
  tc.note(`Z: média ${fmt(ms.mean)}, dp ${fmt(ms.sd)}; ρ mediano ${rho ? fmt(quantile(rho.values, 0.5)) : 'n/d'}` + (gate ? `; gate aberto em ${pct(gateFrac)} das barras` : ''));
  return run;
}

// ───────────────────────────── T6 ─────────────────────────────
function t6Sets(quick) {
  return { absorption: absorptionData({ count: quick ? 6 : 10 }), pwf: pwfData({ count: quick ? 6 : 10 }) };
}

/** Execução extra do T6: absorções com precisão Auto em 5 min ("1" → qualidade média, eventos de baixa confiança). */
function t6LowConfWanted(target) {
  return { ...statWanted(target), precIn: target.option('precIn', 'auto') };
}

/**
 * Execução extra do T6: absorções com a divergência por pivots ligada (auditoria dos pivots, spec §7) e com o |zP|
 * máximo do «travado» em 2.0 — aí a exclusão da classe CONFIRMADO (s·zP ≥ |ρ|·|zF|) deixa de ser inócua.
 */
const T6_PIV_PINP = 2.0;
function t6PivWanted(target) {
  return target.hasInput('pivIn') && target.hasInput('pinPIn') && FULL_EVENTS_RE.test(target.source) ? { ...statWanted(target), pivIn: true, pinPIn: T6_PIV_PINP } : null;
}

/**
 * Execução extra do T6: série nula com o |zP| máximo do «travado» no máximo do input (3.0). Na série nula há ~20 barras
 * com |zF| ≥ 3 em que o preço acompanhou o fluxo (s·zP ≥ |ρ|·|zF|, classe CONFIRMADO): têm de ficar fora do «travado».
 */
const T6_NULL_PINP = 3.0;
function t6PinWanted(target) {
  return target.hasInput('pinPIn') && FULL_EVENTS_RE.test(target.source) ? { ...statWanted(target), pinPIn: T6_NULL_PINP } : null;
}

const sgn = (x) => (x > 0 ? 1 : x < 0 ? -1 : 0);
// alertcondition por título (spec §9, títulos revistos) → chave da auditoria
const ALERT_KEYS = [
  ['zUp', /^Z ≥/], ['zDn', /^Z ≤/], ['absB', /^Fluxo comprador absorvido/], ['absS', /^Fluxo vendedor absorvido/],
  ['pinB', /^Preço travado sob compras/], ['pinS', /^Preço travado sob vendas/],
  ['contB', /^Compras absorvidas → continuação/], ['contS', /^Vendas absorvidas → continuação/],
  ['heldB', /^Compras absorvidas → segurou/], ['heldS', /^Vendas absorvidas → segurou/],
  ['pwfU', /^Preço sem fluxo \(subida\)/], ['pwfD', /^Preço sem fluxo \(queda\)/],
  ['pivT', /^Divergência por pivots \(topo\)/], ['pivB', /^Divergência por pivots \(fundo\)/],
];
// o indicador revisto tem a camada de eventos completa (o stand-in não)
const FULL_EVENTS_RE = /"Preço travado sob compras extremas"/;

/**
 * Referência da divergência por pivots (spec §7, dossier §6.6) a partir do OHLC e dos plots do indicador (delta → CVD
 * contínuo, σΔ desfasado, qualidade → hqRun). Pivots com a regra de empates do PineTS (à esquerda só um valor
 * estritamente maior desqualifica; à direita ≥ desqualifica). Devolve as barras de confirmação {top, bot}.
 */
function pivotRef(data, run, target, pv) {
  const n = data.bars.length, { L, R } = pv;
  const hi = data.bars.map((b) => b.high), lo = data.bars.map((b) => b.low);
  const dl = optRole(target, run, 'delta'), sd = optRole(target, run, 'sd'), tr = optRole(target, run, 'tier');
  if (!dl || !sd || !tr) return null;
  const cvdC = new Float64Array(n).fill(NaN);
  for (let i = 0, c = NaN; i < n; i++) { if (isF(dl.values[i])) c = (isF(c) ? c : 0) + dl.values[i]; cvdC[i] = c; }
  const top = [], bot = [];
  let run2 = 0, lastPh = NaN, lastPhCvd = NaN, lastPhBar = NaN, lastPl = NaN, lastPlCvd = NaN, lastPlBar = NaN;
  for (let i = 0; i < n; i++) {
    run2 = tr.values[i] >= 2 ? run2 + 1 : 0;
    if (i < L + R) continue;
    const c = i - R, sdP = sd.values[i], cvdAt = cvdC[c];
    let okH = true, okL = true;
    for (let j = 1; j <= L; j++) { if (hi[c - j] > hi[c]) okH = false; if (lo[c - j] < lo[c]) okL = false; }
    for (let j = 1; j <= R; j++) { if (hi[c + j] >= hi[c]) okH = false; if (lo[c + j] <= lo[c]) okL = false; }
    if (okH) {
      if (isF(lastPhBar) && isF(cvdAt) && isF(lastPhCvd) && sdP > 0) {
        const gap = c - lastPhBar;
        if (gap >= pv.min && gap <= pv.max && run2 > i - lastPhBar && hi[c] > lastPh && cvdAt <= lastPhCvd - pv.mag * sdP) top.push(i);
      }
      lastPh = hi[c]; lastPhCvd = cvdAt; lastPhBar = c;
    }
    if (okL) {
      if (isF(lastPlBar) && isF(cvdAt) && isF(lastPlCvd) && sdP > 0) {
        const gap = c - lastPlBar;
        if (gap >= pv.min && gap <= pv.max && run2 > i - lastPlBar && lo[c] < lastPl && cvdAt >= lastPlCvd + pv.mag * sdP) bot.push(i);
      }
      lastPl = lo[c]; lastPlCvd = cvdAt; lastPlBar = c;
    }
  }
  return { top, bot };
}
const setMinus = (a, b) => { const B = new Set(b); return a.filter((x) => !B.has(x)); };
const sameSet = (a, b) => a.length === b.length && setMinus(a, b).length === 0 && setMinus(b, a).length === 0;

/**
 * Auditoria EXACTA da camada de eventos (spec §7/§9): a partir dos plots do próprio indicador (zF, zP, gate,
 * qualidade, Z) e do OHLC re-deriva as classes (absorvido ∪ travado, preço sem fluxo), a 1.ª barra de cada
 * aglomerado, a máquina de resolução (H0/L0 = máximo/mínimo em ke barras, vida em barras) e os alertas, e exige
 * igualdade com as etiquetas e os alertas emitidos. Usa os inputs por omissão (eventos e baixa confiança ligados).
 * Não verifica o cálculo de zF/zP (isso é o T8, contra a referência JS).
 */
export function auditEvents(tc, target, run, data, P, name, { piv = false } = {}) {
  if (!FULL_EVENTS_RE.test(target.source)) { tc.skip(`${name}: auditoria de eventos (o alvo não tem a camada de eventos completa)`); return; }
  const g = (role) => optRole(target, run, role);
  const zF = g('zF'), zP = g('zP'), gate = g('gate'), tier = g('tier'), Z = g('z'), rho = g('rho');
  if (!zF || !zP || !gate || !tier || !Z || !rho) { tc.fail(`${name}: plots zF/zP/gate/qualidade/Z/ρ para a auditoria de eventos`); return; }
  const F = zF.values, Pz = zP.values, G = gate.values, T = tier.values, ZZ = Z.values, RH = rho.values;
  const n = data.bars.length;
  const hi = data.bars.map((b) => b.high), lo = data.bars.map((b) => b.low), cl = data.bars.map((b) => b.close);
  const abs = new Uint8Array(n), pin = new Uint8Array(n), pwf = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    if (!(G[i] === 1 && isF(F[i]) && isF(Pz[i]))) continue;
    // travado: fluxo extremo, preço quase parado, e nunca a classe CONFIRMADO (s·zP ≥ |ρ|·|zF|)
    const rh = isF(RH[i]) ? Math.abs(RH[i]) : 0;
    pin[i] = Math.abs(F[i]) >= P.pin && Math.abs(Pz[i]) <= P.pinP && sgn(F[i]) * Pz[i] < rh * Math.abs(F[i]) ? 1 : 0;
    abs[i] = (Math.abs(F[i]) >= P.zf && sgn(F[i]) * Pz[i] <= 0) || pin[i] ? 1 : 0;
    pwf[i] = !abs[i] && Math.abs(Pz[i]) >= P.zf && sgn(Pz[i]) * F[i] <= 0 ? 1 : 0;
  }
  const tierOk = (i) => T[i] >= 3 || T[i] === 2;
  // 1.ª barra de cada aglomerado, por classe E por lado: novo quando o lado muda ou quando a última barra da mesma classe
  // e do mesmo lado ficou a mais de ke barras (período refractário de ke barras; com ke = 1 = "cond e não cond[1]").
  const clusterStarts = (cls, sideOf) => {
    const out = new Uint8Array(n);
    let lastBar = NaN, lastSide = 0;
    for (let i = 0; i < n; i++) {
      if (!cls[i]) continue;
      const sd = sideOf(i);
      out[i] = lastSide === sd && isF(lastBar) && i - lastBar <= P.ke ? 0 : 1;
      lastBar = i; lastSide = sd;
    }
    return out;
  };
  const absNew = clusterStarts(abs, (i) => sgn(F[i])), pinNew = clusterStarts(pin, (i) => sgn(F[i])), pwfNew = clusterStarts(pwf, (i) => sgn(Pz[i]));
  // Diferenças face à regra antiga "cond e não cond[1]" (só informativo): inversões de lado em barras seguidas e
  // reinícios do mesmo lado suprimidos pelo período refractário.
  let nFlip = 0, nRefr = 0;
  for (const [cls, nw] of [[abs, absNew], [pwf, pwfNew]]) {
    for (let i = 1; i < n; i++) {
      const oldStart = cls[i] === 1 && cls[i - 1] !== 1;
      if (nw[i] && !oldStart) nFlip++;
      if (oldStart && !nw[i]) nRefr++;
    }
  }
  // Calibração: nº de valores válidos ANTERIORES de D (= de fE/pE: todos válidos exactamente nas barras hqOk). Um valor
  // finito de Z/zF numa barra implica ≥ N anteriores; daí n_cal(i) = N + nº de Z (zF) finitos antes de i.
  const cntBefore = (v) => { const out = new Int32Array(n); let c = 0; for (let i = 0; i < n; i++) { out[i] = c; if (isF(v[i])) c++; } return out; };
  const zBefore = cntBefore(ZZ), fBefore = cntBefore(F);
  const zCalOk = (i) => P.N + zBefore[i] >= 2 * P.N;                       // alertas de Z só com ≥ 2N valores
  const evWeak = (i) => P.N + fBefore[i] < Math.max(20 * P.ke, 2 * P.N);  // rótulo oco «cal. prov.» e sem alertas
  const zU = (i) => G[i] === 1 && isF(ZZ[i]) && ZZ[i] >= P.thr;
  const zD = (i) => G[i] === 1 && isF(ZZ[i]) && ZZ[i] <= -P.thr;
  const exp = Object.fromEntries([...ALERT_KEYS.map(([k]) => k), 'alert'].map((k) => [k, []]));
  const absBars = [], pwfBars = [];
  const res = new Map();      // barra do evento → resolução esperada
  const pinTag = new Set();   // eventos que ganham "· preço travado" depois da 1.ª barra
  let ev = null, absStart = NaN;
  // divergência por pivots (só com pivIn ligado): referência independente; sem pivIn não pode haver alertas de pivot
  const pr = piv ? pivotRef(data, run, target, P.piv) : { top: [], bot: [] };
  if (!pr) { tc.fail(`${name}: plots delta/σΔ/qualidade para a referência dos pivots`); return; }
  const pivTopSet = new Set(pr.top), pivBotSet = new Set(pr.bot);
  exp.pivT = pr.top.slice(); exp.pivB = pr.bot.slice();
  // alertas de Z com histerese: 1.º cruzamento; rearma depois de Z < limiar − 1 (lado +) / Z > −(limiar − 1) (lado −)
  let upArmed = true, dnArmed = true;
  let nWeakSkipped = 0, nZProvSkipped = 0;
  for (let i = 0; i < n; i++) {
    if (absNew[i]) absStart = i;
    let rAl = false;
    if (ev && i > ev.bar) {
      const cont = ev.side > 0 ? cl[i] > ev.hi : cl[i] < ev.lo;
      const held = ev.side > 0 ? cl[i] < ev.lo : cl[i] > ev.hi;
      const expd = !cont && !held && i - ev.bar >= P.life;
      if (cont || held || expd) {
        res.set(ev.bar, cont ? 'continuação' : held ? 'segurou' : 'expirou');
        // a resolução de um evento com calibração fraca não alerta
        if (!ev.weak) {
          if (cont) exp[ev.side > 0 ? 'contB' : 'contS'].push(i);
          if (held) exp[ev.side > 0 ? 'heldB' : 'heldS'].push(i);
          rAl = cont || held;
        }
        ev = null;
      }
    }
    const nAbs = absNew[i] && tierOk(i), nPin = pinNew[i] && tierOk(i), nPwf = pwfNew[i] && tierOk(i);
    const wk = evWeak(i);
    if ((nAbs || nPin || nPwf) && wk) nWeakSkipped++;
    if (nAbs) {
      if (ev) res.set(ev.bar, 'substituído');
      let h = -Infinity, l = Infinity;
      for (let j = Math.max(0, i - P.ke + 1); j <= i; j++) { h = Math.max(h, hi[j]); l = Math.min(l, lo[j]); }
      ev = { bar: i, side: F[i] > 0 ? 1 : -1, hi: h, lo: l, weak: wk };
      absBars.push(i);
      if (!wk) exp[ev.side > 0 ? 'absB' : 'absS'].push(i);
    }
    if (nPin && !wk) exp[F[i] > 0 ? 'pinB' : 'pinS'].push(i);
    if (nPin && !nAbs && ev && ev.bar === absStart && ev.side === sgn(F[i])) pinTag.add(ev.bar);
    if (nPwf) { pwfBars.push(i); if (!wk) exp[Pz[i] > 0 ? 'pwfU' : 'pwfD'].push(i); }
    // cruzamento de Z: desarma sempre; só alerta com a calibração de ≥ 2N valores
    const cU = zU(i) && upArmed, cD = zD(i) && dnArmed;
    const aU = cU && zCalOk(i), aD = cD && zCalOk(i);
    if ((cU || cD) && !zCalOk(i)) nZProvSkipped++;
    if (aU) exp.zUp.push(i);
    if (aD) exp.zDn.push(i);
    if (cU) upArmed = false;
    if (cD) dnArmed = false;
    if (isF(ZZ[i]) && ZZ[i] < P.thr - 1) upArmed = true;
    if (isF(ZZ[i]) && ZZ[i] > -(P.thr - 1)) dnArmed = true;
    if (aU || aD || (nAbs && !wk) || (nPin && !nAbs && !wk) || (nPwf && !wk) || rAl || pivTopSet.has(i) || pivBotSet.has(i)) exp.alert.push(i);
  }
  // etiquetas
  const labs = run.labels.map((l) => ({ x: labelBar(l), txt: labelText(l) }));
  const absL = labs.filter((l) => /absorvid/i.test(l.txt)), pwfL = labs.filter((l) => /sem fluxo/i.test(l.txt));
  const absX = absL.map((l) => l.x), pwfX = pwfL.map((l) => l.x);
  tc.check(sameSet(absX, absBars), `${name}: etiquetas de absorção exactamente na 1.ª barra de cada aglomerado (gate aberto, qualidade ≥ média)`,
    `${absX.length} etiquetas, ${absBars.length} esperadas; só esperadas: ${setMinus(absBars, absX).slice(0, 5).join(',') || '—'}; só etiquetas: ${setMinus(absX, absBars).slice(0, 5).join(',') || '—'}`);
  tc.check(sameSet(pwfX, pwfBars), `${name}: etiquetas de preço sem fluxo exactamente na 1.ª barra de cada aglomerado`,
    `${pwfX.length} etiquetas, ${pwfBars.length} esperadas; só esperadas: ${setMinus(pwfBars, pwfX).slice(0, 5).join(',') || '—'}; só etiquetas: ${setMinus(pwfX, pwfBars).slice(0, 5).join(',') || '—'}`);
  let badSide = 0, badPin = 0, badRes = 0, badPwfSide = 0;
  const ex = [];
  const resCount = {};
  for (const l of absL) {
    const side = F[l.x] > 0 ? 1 : -1;
    if (!(side > 0 ? /^Compras/.test(l.txt) : /^Vendas/.test(l.txt))) badSide++;
    if ((pin[l.x] === 1 || pinTag.has(l.x)) !== /travado/.test(l.txt)) badPin++;
    const want = res.get(l.x) ?? 'pendente';
    const got = /→ continuação/.test(l.txt) ? 'continuação' : /→ (absorção )?segurou/.test(l.txt) ? 'segurou' : /→ expirou/.test(l.txt) ? 'expirou'
      : /→ substituído/.test(l.txt) ? 'substituído' : 'pendente';
    resCount[got] = (resCount[got] || 0) + 1;
    // seta = sentido em que o preço resolveu: continuação no sentido do fluxo, «segurou» no oposto
    const arrowWant = got === 'continuação' ? (side > 0 ? '↑' : '↓') : got === 'segurou' ? (side > 0 ? '↓' : '↑') : null;
    const arrowOk = !arrowWant || new RegExp(`→ (continuação|absorção segurou) ${arrowWant}`).test(l.txt);
    if ((l.txt.match(/→/g) || []).length > 1) { badRes++; if (ex.length < 3) ex.push(`@${l.x} várias resoluções`); }
    else if (want !== got) { badRes++; if (ex.length < 3) ex.push(`@${l.x} esperado ${want}, obtido ${got}`); }
    else if (!arrowOk) { badRes++; if (ex.length < 3) ex.push(`@${l.x} seta da resolução errada (esperada ${arrowWant}): ${l.txt.replace(/\n/g, ' / ')}`); }
  }
  for (const l of pwfL) if (!(Pz[l.x] > 0 ? /↑/.test(l.txt) : /↓/.test(l.txt))) badPwfSide++;
  // Confiança no próprio rótulo (spec §7): «(baixa conf.)» com qualidade média; senão «(cal. prov.)» com calibração
  // fraca do zF/zP (< max(20·ke, 2N) valores); estilo oco (fundo com 65% de transparência → alfa 0x59) nos dois casos.
  let badConf = 0;
  const exConf = [];
  const labObjs = run.labels.filter((l) => /absorvid|sem fluxo/i.test(labelText(l)));
  for (const lo2 of labObjs) {
    const x = labelBar(lo2), txt = labelText(lo2).split('\n')[0];
    const lowC = T[x] === 2, wk = evWeak(x);
    const wantSfx = lowC ? '(baixa conf.)' : wk ? '(cal. prov.)' : null;
    const gotSfx = /\(baixa conf\.\)/.test(txt) ? '(baixa conf.)' : /\(cal\. prov\.\)/.test(txt) ? '(cal. prov.)' : null;
    const hollowGot = /59$/i.test(String(lo2.color || ''));
    if (wantSfx !== gotSfx || (lowC || wk) !== hollowGot) { badConf++; if (exConf.length < 3) exConf.push(`@${x} esperado ${wantSfx ?? 'sem sufixo'}${lowC || wk ? ' (oco)' : ''}, obtido «${txt}» ${lo2.color}`); }
  }
  if (labObjs.length) tc.check(badConf === 0, `${name}: confiança no rótulo — «(baixa conf.)» com qualidade média, «(cal. prov.)» com < max(20·ke, 2N) valores de calibração do zF; oco nos dois casos`,
    exConf.join('; ') || `${labObjs.length} rótulos (${labObjs.filter((l) => /59$/i.test(String(l.color || ''))).length} ocos)`);
  tc.check(badSide === 0 && badPwfSide === 0, `${name}: lado das etiquetas (compras/vendas pelo sinal de zF; ↑/↓ pelo sinal de zP)`, `${badSide} + ${badPwfSide} divergentes`);
  tc.check(badPin === 0, `${name}: «travado» nas etiquetas = travado na 1.ª barra ou a surgir no mesmo aglomerado pendente`, `${badPin} divergentes`);
  tc.check(badRes === 0, `${name}: resolução de cada absorção = máquina de estados de referência (H0/L0 em ${P.ke} barras, vida ${P.life}; seta ↑/↓ do sentido)`, ex.join('; ') || `${absL.length} etiquetas`);
  if (piv) {
    // etiquetas dos pivots na barra do pivot (confirmação − R)
    const topL = labs.filter((l) => /^Topo sem confirma/.test(l.txt)).map((l) => l.x), botL = labs.filter((l) => /^Fundo sem confirma/.test(l.txt)).map((l) => l.x);
    const wantT = pr.top.map((i) => i - P.piv.R), wantB = pr.bot.map((i) => i - P.piv.R);
    tc.check(pr.top.length + pr.bot.length > 0, `${name}: há divergências por pivots para auditar`, `${pr.top.length} topos, ${pr.bot.length} fundos`, 'warn');
    tc.check(sameSet(topL, wantT) && sameSet(botL, wantB), `${name}: etiquetas de divergência por pivots = referência (na barra do pivot, R = ${P.piv.R})`,
      `topo ${topL.length}/${wantT.length}, fundo ${botL.length}/${wantB.length}; só esperadas: ${[...setMinus(wantT, topL), ...setMinus(wantB, botL)].slice(0, 5).join(',') || '—'}`);
  }
  // alertas
  const got = Object.fromEntries([...ALERT_KEYS.map(([k]) => k), 'alert'].map((k) => [k, []]));
  for (const al of run.alerts) {
    if (al.type === 'alertcondition') { const k = ALERT_KEYS.find(([, re]) => re.test(al.title || '')); if (k) got[k[0]].push(al.bar_index); }
    else got.alert.push(al.bar_index);
  }
  const badAl = Object.keys(exp).filter((k) => !sameSet(got[k], exp[k])).map((k) => `${k}: ${got[k].length} vs ${exp[k].length}`);
  tc.check(badAl.length === 0, `${name}: alertcondition (por título) e alert() exactamente nas barras esperadas (1.º cruzamento / 1.ª barra de cada classe)`,
    badAl.join('; ') || Object.keys(exp).map((k) => `${k} ${exp[k].length}`).join(', '));
  // Texto do estado (spec §5, quatro estados neutros) nas mensagens alert() dos cruzamentos de Z: tem de bater com o sinal
  // de Z e com a perna dominante (|F_K| > |P_K| → fluxo; senão preço), lidas dos plots P_K/F_K do próprio indicador.
  const pL = g('pLeg'), fL = g('fLeg');
  if (pL && fL) {
    const ST = [[/Fluxo comprador sem subida/, (p, f, z) => z < 0 && Math.abs(f) > Math.abs(p)], [/Preço a cair sem fluxo vendedor/, (p, f, z) => z < 0 && Math.abs(p) >= Math.abs(f)],
      [/Fluxo vendedor sem queda/, (p, f, z) => z > 0 && Math.abs(f) > Math.abs(p)], [/Preço a subir sem fluxo comprador/, (p, f, z) => z > 0 && Math.abs(p) >= Math.abs(f)]];
    let nSt = 0, badSt = 0;
    const exSt = [];
    for (const al of run.alerts) {
      const m = String(al.message || '');
      if (al.type === 'alertcondition' || !/Z [≥≤] [+−]limiar: /.test(m)) continue;
      const i = al.bar_index, hit = ST.filter(([re]) => re.test(m));
      nSt++;
      if (!(hit.length === 1 && hit[0][1](pL.values[i], fL.values[i], ZZ[i]))) { badSt++; if (exSt.length < 3) exSt.push(`@${i} Z ${fmt(ZZ[i], 2)} P_K ${fmt(pL.values[i], 2)} F_K ${fmt(fL.values[i], 2)}: ${m.slice(0, 90)}`); }
    }
    if (nSt) tc.check(badSt === 0, `${name}: texto do estado nas mensagens alert() dos cruzamentos de Z = sinal de Z + perna dominante (|F_K| vs |P_K|)`, exSt.join('; ') || `${nSt} mensagens`);
  }
  tc.note(`${name}: ${absL.length} absorções (${Object.entries(resCount).map(([k, v]) => `${k} ${v}`).join(', ')}), ${pwfL.length} preço sem fluxo, ${exp.pinB.length + exp.pinS.length} travados com alerta, ${exp.zUp.length + exp.zDn.length} alertas de Z` +
    ` (sem alerta por calibração: ${nWeakSkipped} eventos, ${nZProvSkipped} cruzamentos de Z; aglomerados: ${nFlip} inversões de lado em barras seguidas, ${nRefr} reinícios refractários)` +
    (piv ? `, pivots: ${pr.top.length} topos e ${pr.bot.length} fundos` : ''));
  return { nFlip, nRefr, absBars, sides: absBars.map((i) => sgn(F[i])) };
}

export async function t6Detection(tc, target, { quick = false } = {}) {
  const P = params(target);
  const tol = 2;
  const sets = t6Sets(quick);
  const proms = Object.fromEntries(Object.entries(sets).map(([k, d]) => [k, target.run(d, statWanted(target))]));
  const lowConfProm = target.option('precIn', 'auto') ? target.run(sets.absorption, t6LowConfWanted(target)) : null;
  const pivW = t6PivWanted(target), pinW = t6PinWanted(target);
  const pivProm = pivW ? target.run(sets.absorption, pivW) : null;
  const pinProm = pinW ? target.run(nullData(4500), pinW) : null;
  for (const kind of ['absorption', 'pwf']) {
    const data = sets[kind];
    tc.note(`dados: ${data.desc}`);
    const run = await proms[kind];
    auditEvents(tc, target, run, data, P, `${kind === 'absorption' ? 'absorção' : 'preço sem fluxo'} (1S, qualidade alta)`);
    const z = requireRole(tc, target, run, 'z', 'Z');
    if (!z) continue;
    let zHits = 0, evHits = 0, sideOk = 0;
    const detail = [];
    data.episodes.forEach((ep) => {
      const a = ep.start, b = ep.start + ep.len - 1 + tol;
      const expSign = kind === 'absorption' ? -ep.side : ep.side;
      let zHit = false, zBest = 0;
      for (let t = a; t <= b && t < z.values.length; t++) {
        const v = z.values[t] * expSign;
        if (isF(v) && v > zBest) zBest = v;
        if (v >= P.thr) zHit = true;
      }
      const re = kind === 'absorption' ? ABS_LABEL_RE : PWF_LABEL_RE;
      const labs = run.labels.filter((l) => { const x = labelBar(l); return x >= a && x <= b && re.test(labelText(l)); });
      const alts = run.alerts.filter((al) => al.type === 'alertcondition' && al.bar_index >= a && al.bar_index <= b && re.test(al.title || '') && !isResolutionTitle(al.title));
      const ev = labs.length > 0 || alts.length > 0;
      if (kind === 'absorption' && labs.length) {
        const txt = labelText(labs[0]);
        if (ep.side > 0 ? /compr/i.test(txt) : /vend/i.test(txt)) sideOk++;
      }
      if (zHit) zHits++;
      if (ev) evHits++;
      detail.push(`${ep.side > 0 ? '+' : '−'}@${a}:${zHit ? 'Z' : '·'}${ev ? 'E' : '·'}(${fmt(zBest, 1)})`);
    });
    const nEp = data.episodes.length;
    const name = kind === 'absorption' ? 'absorção' : 'preço sem fluxo';
    const sgn = kind === 'absorption' ? 'Z ≤ −2 (compra absorvida) / Z ≥ +2 (venda absorvida)' : 'Z ≥ +2 (subida) / Z ≤ −2 (queda)';
    tc.check(zHits / nEp >= 0.7, `${name}: ${sgn} dentro do episódio em ≥ 70%`, `${zHits}/${nEp}`);
    if (kind === 'absorption') {
      tc.check(evHits / nEp >= 0.5, 'absorção: etiqueta ou alertcondition "absorvido" em ≥ 50% dos episódios', `${evHits}/${nEp}`);
      tc.note(`etiquetas de absorção com o lado certo (comprador/vendedor): ${sideOk}/${nEp}`);
    } else {
      tc.note(`preço sem fluxo: etiqueta/alerta "sem fluxo" em ${evHits}/${nEp} (informativo)`);
    }
    // falsos positivos longe dos episódios
    const far = new Uint8Array(z.values.length).fill(1);
    data.episodes.forEach((ep) => { for (let t = ep.start - P.K; t < ep.start + ep.len + 3 * P.K; t++) if (t >= 0 && t < far.length) far[t] = 0; });
    const fp = exceedFrac(z.values, 2, { mask: far });
    tc.check(fp.frac <= 0.15, `${name}: P(|Z| ≥ 2) fora dos episódios ≤ 15%`, `${pct(fp.frac, 1)} de ${fp.n}`, 'warn');
    tc.note(`${name} por episódio [sinal@início: Z/E(melhor Z·sinal)]: ${detail.join(' ')}`);
  }
  if (lowConfProm) {
    const run = await lowConfProm;
    const tier = optRole(target, run, 'tier');
    if (tier) tc.check(Array.from(tier.values).slice(1).some((v) => v === 2), 'precisão Auto em 5 min: qualidade média (eventos de baixa confiança)', `tiers: ${[...new Set(Array.from(tier.values))].join(',')}`);
    auditEvents(tc, target, run, sets.absorption, P, 'absorção (Auto = 1 min, qualidade média)');
    const hollow = run.labels.filter((l) => /absorvid|sem fluxo/i.test(labelText(l)));
    const notHollow = hollow.filter((l) => !/59$/i.test(String(l.color || ''))); // 65% de transparência → alfa 0x59
    if (FULL_EVENTS_RE.test(target.source)) tc.check(hollow.length === 0 || notHollow.length === 0, 'qualidade média: rótulos em estilo oco (fundo com 65% de transparência)',
      `${notHollow.length}/${hollow.length} rótulos com outro fundo (ex.: ${notHollow.slice(0, 2).map((l) => l.color).join(', ') || '—'})`, 'warn');
  }
  if (pivProm) {
    const run = await pivProm;
    auditEvents(tc, target, run, sets.absorption, { ...P, pinP: T6_PIV_PINP }, `absorção com pivots ligados e |zP| travado ≤ ${T6_PIV_PINP} (1S)`, { piv: true });
  }
  if (pinProm) {
    const run = await pinProm;
    auditEvents(tc, target, run, nullData(4500), { ...P, pinP: T6_NULL_PINP }, `série nula com |zP| travado ≤ ${T6_NULL_PINP} (exclui a classe CONFIRMADO)`);
  }
}

// ───────────────────────────── T7 ─────────────────────────────
function anchorsOf(data, keyFn) {
  const out = [0];
  for (let t = 1; t < data.bars.length; t++) if (keyFn(data.bars[t].openTime) !== keyFn(data.bars[t - 1].openTime)) out.push(t);
  return out;
}

/**
 * Execuções do T7 (todas sobre a série nula): sig com âncora Auto (= T5), sig semanal, imp com λσ, e (se existirem
 * os inputs) roll/lz/mm e sig com cone + remoção da deriva.
 */
function t7Wanted(target, quick) {
  const sigW = statWanted(target);
  const w = { sigAuto: sigW };
  if (!quick) w.sigWeek = { ...sigW, anchIn: target.option('anchIn', 'w1') };
  w.imp = { ...sigW, modeIn: target.option('modeIn', 'imp'), lamIn: target.option('lamIn', 'vm') };
  for (const m of ['roll', 'lz', 'mm']) { try { w[m] = { ...sigW, modeIn: target.option('modeIn', m) }; } catch { /* modo inexistente */ } }
  if (target.hasInput('coneIn') && target.hasInput('driftIn')) w.coneDrift = { ...sigW, coneIn: true, driftIn: true };
  return w;
}

/** Desvio-padrão populacional e média numa janela que termina em t. */
function winStats(x, t, W) {
  let s = 0;
  for (let j = t - W + 1; j <= t; j++) s += x[j];
  const m = s / W;
  let v = 0;
  for (let j = t - W + 1; j <= t; j++) v += (x[j] - m) ** 2;
  return { mean: m, sd: Math.sqrt(v / W) };
}

function cmpClose(tc, label, idx, got, want, rel = 1e-6, abs = 1e-7) {
  const c = compareSeries(idx, got, want, rel, abs);
  tc.check(c.nBad === 0 && c.n > 0, label, `${c.nBad}/${c.n} fora de ${rel} (pior ${fmt(c.maxErr, 9)} @${c.worstIdx})`);
}

/**
 * Âncoras esperadas (spec §6 + revisão 2): 1.ª barra, mudanças de calendário e — se o σ/ρ congelado na âncora veio de
 * uma janela com barras de qualidade ≤ baixa — a 1.ª barra de qualidade ≥ média cuja janela σ/ρ desfasada (N barras)
 * está toda em qualidade ≥ média (reinício na costura da cobertura). sdP/srP: plots σΔ/σr do indicador.
 */
function expectedAnchors(data, tier, srP, sdP, N, keyFn) {
  const n = data.bars.length, out = [];
  let run = 0, runP = 0, ok = false, fine = false, init = false;
  for (let t = 0; t < n; t++) {
    runP = run;
    run = tier[t] >= 2 ? run + 1 : 0;
    const winFine = runP >= N;
    const cal = t > 0 && keyFn(data.bars[t].openTime) !== keyFn(data.bars[t - 1].openTime);
    const seam = init && ok && !fine && winFine && tier[t] >= 2 && !cal;
    if (!init || cal || seam) { out.push(t); init = true; ok = srP[t] > 0 && sdP[t] > 0; fine = winFine; }
    else if (!ok) { ok = srP[t] > 0 && sdP[t] > 0; fine = winFine; }
  }
  return out;
}

const seamWanted = (target) => (/anchFine/.test(target.source) ? statWanted(target) : null);

export async function t7Invariants(tc, target, { quick = false } = {}) {
  const P = params(target);
  const seamW = seamWanted(target);
  const seamProm = seamW ? target.run(seamData(), seamW) : null;
  const data = nullData(4500);
  const n = data.bars.length;
  const close = arr(data, (b) => b.close), open = arr(data, (b) => b.open);
  const delta = arr(data, (b) => stubDelta(b.code, b.volume));
  const ref = computeRef({ rBar: computeRBar(open, close, data.bars.map((b) => b.openTime)), delta, tier: new Float64Array(n).fill(3), opts: P });
  // Linhas interrompidas na barra de reinício da âncora (plot.style_linebr + na): o indicador revisto fá-lo; o
  // stand-in não. Nesse caso a primeira barra comparável é a seguinte à âncora.
  const breaks = /plot\.style_linebr/.test(target.source);
  const W7 = t7Wanted(target, quick);
  const runsP = Object.fromEntries(Object.entries(W7).map(([k, w]) => [k, target.run(data, w)]));
  const anchorCases = [['sigAuto', utcDayKey, 'diária (auto em 5m)'], ...(W7.sigWeek ? [['sigWeek', utcWeekKey, 'semanal']] : [])];
  let sigAuto = null, srAuto = null;
  for (const [key, keyFn, aname] of anchorCases) {
    const run = await runsP[key];
    const pl = requireRole(tc, target, run, 'pLine', 'linha de preço'), fl = requireRole(tc, target, run, 'fLine', 'linha CVD');
    if (!pl || !fl) return;
    const srR = optRole(target, run, 'sr'), sdR = optRole(target, run, 'sd'), cvd = optRole(target, run, 'cvdA');
    const sr = (t) => (srR ? srR.values[t] : ref.srP[t]), sd = (t) => (sdR ? sdR.values[t] : ref.sdP[t]);
    if (!srR || !sdR) tc.warn(`σr/σΔ no Data Window não encontrados — uso σ da referência JS`, `candidatos: ${[...(target.roles.sr || []), ...(target.roles.sd || [])].join(', ')}`);
    const anchors = anchorsOf(data, keyFn);
    const valid = anchors.filter((a) => a > P.N + 1 && a + 1 < n && isF(sr(a)) && isF(sd(a)));
    tc.check(valid.length >= (key === 'sigAuto' ? 10 : 1), `âncoras ${aname} testáveis após aquecimento`, `${valid.length} de ${anchors.length}`);
    // (a) CVD ancorado reinicia nas âncoras e acumula delta entre elas
    if (cvd) {
      const scale = Math.max(...Array.from(delta).map(Math.abs).filter(isF));
      const anchorSet = new Set(anchors);
      let badReset = 0, badAcc = 0;
      for (let t = P.N; t < n; t++) {
        const e = anchorSet.has(t) ? delta[t] : cvd.values[t - 1] + delta[t];
        if (!(Math.abs(cvd.values[t] - e) <= 1e-9 * scale * 10)) { if (anchorSet.has(t)) badReset++; else badAcc++; }
      }
      tc.check(badReset === 0, `"${cvd.title}" reinicia (= delta da barra) nas âncoras ${aname}`, `${badReset} âncoras divergentes`);
      tc.check(badAcc === 0, `"${cvd.title}" acumula Δ entre âncoras (${aname})`, `${badAcc} barras divergentes`);
    } else tc.warn('plot "CVD ancorado" não encontrado no Data Window');
    // (b) no reinício: linhas interrompidas na âncora (na) e, na barra seguinte, F = (Δ_a + Δ_a+1)/σΔ_a,
    //     P = 1e4·ln(C_a+1/O_a)/σr_a  (sem interrupção: F = Δ_a/σΔ_a e P = 1e4·ln(C_a/O_a)/σr_a na própria âncora)
    if (breaks) {
      const notNa = valid.filter((a) => isF(pl.values[a]) || isF(fl.values[a]));
      tc.check(notNa.length === 0, `sig, âncora ${aname}: linhas interrompidas (na) na barra de reinício`, `${notNa.length}/${valid.length} âncoras com valor`);
    }
    const o1 = breaks ? 1 : 0;
    const cf = compareSeries(valid, (a) => fl.values[a + o1], (a) => (delta[a] + (o1 ? delta[a + 1] : 0)) / sd(a), 1e-6, 1e-9);
    const cp = compareSeries(valid, (a) => pl.values[a + o1], (a) => (1e4 * Math.log(close[a + o1] / open[a])) / sr(a), 1e-6, 1e-9);
    tc.check(cf.nBad === 0, `sig, âncora ${aname}: perna de fluxo no reinício = ΣΔ/σΔ(congelado)`, `${cf.nBad}/${cf.n} fora de 1e-6 (pior ${fmt(cf.maxErr, 9)} @${cf.worstIdx})`);
    tc.check(cp.nBad === 0, `sig, âncora ${aname}: perna de preço no reinício = 1e4·ln(C/O_a)/σr(congelado)`, `${cp.nBad}/${cp.n} fora de 1e-6 (pior ${fmt(cp.maxErr, 9)} @${cp.worstIdx})`);
    const medAbs = quantile(valid.map((a) => Math.abs(fl.values[a + o1])), 0.5);
    tc.check(medAbs < 2, `perna de fluxo ≈ 0 no reinício (mediana |F| < 2σ)`, fmt(medAbs));
    // (c) σ congelado dentro do segmento
    let nSeg = 0, badSegF = 0, badSegP = 0;
    for (let k = 0; k < anchors.length; k++) {
      const a = anchors[k];
      if (!valid.includes(a)) continue;
      const end = k + 1 < anchors.length ? anchors[k + 1] : n;
      let cvdA = 0;
      for (let t = a; t < end; t++) {
        cvdA += delta[t];
        if (breaks && t === a) continue;
        nSeg++;
        if (relErr(fl.values[t], cvdA / sd(a), 1e-9) > 1e-6 && Math.abs(fl.values[t] - cvdA / sd(a)) > 1e-7) badSegF++;
        const pExp = (1e4 * (Math.log(close[t]) - Math.log(open[a]))) / sr(a);
        if (relErr(pl.values[t], pExp, 1e-9) > 1e-6 && Math.abs(pl.values[t] - pExp) > 1e-7) badSegP++;
      }
    }
    tc.check(badSegF === 0 && badSegP === 0, `sig, âncora ${aname}: σ congelado no segmento (F = CVD_a/σΔ_a, P = 1e4·ln(C/O_a)/σr_a)`, `${badSegF + badSegP}/${2 * nSeg} pontos divergentes`);
    if (key === 'sigAuto') { sigAuto = { run, fl, anchors, valid, sr }; srAuto = sr; }
  }
  // (d) modo preço implícito com λσ (vol-matched)
  if (sigAuto) {
    let imp;
    try { imp = await runsP.imp; } catch (e) { tc.fail('modo imp executa', e.message); return; }
    const pl = requireRole(tc, target, imp, 'pLine', 'linha de preço (imp)'), fl = requireRole(tc, target, imp, 'fLine', 'linha CVD (imp)');
    if (!pl || !fl) return;
    const cc = compareSeries(range(0, n), (t) => pl.values[t], (t) => close[t], 1e-12, 1e-12);
    tc.check(cc.nBad === 0, 'imp: linha de preço = close', `${cc.nBad} barras divergentes`);
    const { anchors, valid } = sigAuto;
    let nPts = 0, badRatio = 0, worst = 0;
    for (let k = 0; k < anchors.length; k++) {
      const a = anchors[k];
      if (!valid.includes(a)) continue;
      const end = k + 1 < anchors.length ? anchors[k + 1] : n;
      const lnA = Math.log(open[a]);
      const expRatio = srAuto(a) / 1e4; // (ln fLine − lnA) / F_sig = σr_a / 1e4
      for (let t = a; t < end; t++) {
        const fs = sigAuto.fl.values[t];
        if (!(Math.abs(fs) > 0.5)) continue;
        const e = relErr((Math.log(fl.values[t]) - lnA) / fs, expRatio);
        nPts++; worst = Math.max(worst, e);
        if (!(e <= 1e-5)) badRatio++;
      }
    }
    tc.check(nPts > 100 && badRatio === 0, 'imp (λσ): (ln fLine − lnA) ∝ perna de fluxo sig, razão = σr_a/1e4 constante no segmento', `${badRatio}/${nPts} pontos fora de 1e-5 (pior ${fmt(worst, 8)})`);
  }
  // (e) modos em janela móvel W (fórmulas fechadas; CVD contínuo = Σ Δ desde a 1.ª barra)
  const W = P.W;
  const cvdC = new Float64Array(n);
  for (let t = 0, c = 0; t < n; t++) { c += delta[t]; cvdC[t] = c; }
  const lnC = Float64Array.from(close, Math.log);
  const from = W + P.N + 2;
  const idx = range(from, n);
  for (const m of ['roll', 'lz', 'mm']) {
    if (!runsP[m]) { tc.skip(`modo ${m} inexistente`); continue; }
    const run = await runsP[m];
    const pl = requireRole(tc, target, run, 'pLine', `linha de preço (${m})`), fl = requireRole(tc, target, run, 'fLine', `linha CVD (${m})`);
    if (!pl || !fl) continue;
    let pe, fe, txt;
    if (m === 'roll') {
      pe = (t) => (1e4 * (lnC[t] - lnC[t - W])) / ref.srP[t]; fe = (t) => (cvdC[t] - cvdC[t - W]) / ref.sdP[t];
      txt = 'P = 1e4·(lnC − lnC[W])/σr, F = (CVD − CVD[W])/σΔ (σ móveis desfasados)';
    } else if (m === 'lz') {
      pe = (t) => { const w = winStats(lnC, t, W); return (lnC[t] - w.mean) / w.sd; };
      fe = (t) => { const w = winStats(cvdC, t, W); return (cvdC[t] - w.mean) / w.sd; };
      txt = 'z-score de níveis em W barras (média e σ populacional)';
    } else {
      const mm = (x, t) => { let lo = Infinity, hi = -Infinity; for (let j = t - W + 1; j <= t; j++) { lo = Math.min(lo, x[j]); hi = Math.max(hi, x[j]); } return 100 * (2 * (x[t] - lo) / (hi - lo) - 1); };
      pe = (t) => mm(close, t); fe = (t) => mm(cvdC, t);
      txt = 'min–máx em W barras → −100..+100';
    }
    // lz: o ta.stdev do PineTS sobre ln(C) (σ da janela ~1e-3 de um nível ~10.8) perde ~1e-5 de precisão relativa;
    // 1e-4 continua muito abaixo do erro de qualquer fórmula errada (ex.: média desfasada → O(0.1)).
    const tol = m === 'lz' ? 1e-4 : 1e-6;
    cmpClose(tc, `${m}: linha de preço = ${txt}`, idx, (t) => pl.values[t], pe, tol, tol);
    cmpClose(tc, `${m}: linha CVD = ${txt}`, idx, (t) => fl.values[t], fe, tol, tol);
  }
  // (f) cone nulo iid (sig): coneUp − P = P − coneDn = 2·√(2n(1 − max(ρ_a, 0))), n = barras desde a âncora + 1;
  //     deriva removida: incremento do CVD ancorado = Δ − SMA_N(Δ)[1]
  if (runsP.coneDrift) {
    const run = await runsP.coneDrift;
    const pl = requireRole(tc, target, run, 'pLine', 'linha de preço (cone)');
    const upT = target.plotTitles.find((x) => /^cone.*\+/i.test(x)), dnT = target.plotTitles.find((x) => /^cone.*[−-]/i.test(x));
    const up = upT && target.plot(run, upT), dn = dnT && target.plot(run, dnT), rho = optRole(target, run, 'rho'), cvd = optRole(target, run, 'cvdA');
    if (pl && up && dn && rho) {
      const anchors = anchorsOf(data, utcDayKey);
      let nPts = 0, bad = 0, worst = 0;
      for (let k = 0; k < anchors.length; k++) {
        const a = anchors[k];
        if (a <= 2 * P.N + 2 || !isF(rho.values[a])) continue;
        const end = k + 1 < anchors.length ? anchors[k + 1] : n;
        for (let t = a + 1; t < end; t++) {
          const w = 2 * Math.sqrt(2 * (t - a + 1) * (1 - Math.max(rho.values[a], 0)));
          const e = Math.max(Math.abs(up[t] - pl.values[t] - w), Math.abs(pl.values[t] - dn[t] - w)); // target.plot → array
          nPts++; worst = Math.max(worst, e);
          if (!(e <= 1e-6 * Math.max(1, w))) bad++;
        }
      }
      tc.check(nPts > 100 && bad === 0, 'cone nulo: ±2·√(2n(1 − max(ρ_a, 0))) em torno da linha do preço (ρ congelado na âncora)', `${bad}/${nPts} pontos divergentes (pior ${fmt(worst, 9)})`);
    } else tc.warn('cone: plots do cone, da linha de preço ou de ρ não encontrados');
    if (cvd) {
      const anchorSet = new Set(anchorsOf(data, utcDayKey));
      let nPts = 0, bad = 0, worst = 0;
      for (let t = P.N + 2; t < n; t++) {
        let m = 0;
        for (let j = t - P.N; j < t; j++) m += delta[j];
        const dd = delta[t] - m / P.N;
        const e = anchorSet.has(t) ? cvd.values[t] - dd : cvd.values[t] - cvd.values[t - 1] - dd;
        nPts++; worst = Math.max(worst, Math.abs(e));
        if (!(Math.abs(e) <= 1e-6 * Math.max(1, Math.abs(dd)))) bad++;
      }
      tc.check(bad === 0, 'deriva removida: incremento do CVD ancorado = Δ − SMA_N(Δ)[1]', `${bad}/${nPts} barras divergentes (pior ${fmt(worst, 9)})`);
    }
  }
  // (g) costura da cobertura: σ/ρ congelados numa janela mista → as linhas reiniciam quando a janela fica toda fina
  if (seamProm) {
    const sd = seamData();
    const run = await seamProm;
    const fl = requireRole(tc, target, run, 'fLine', 'linha CVD (costura)'), tr = optRole(target, run, 'tier');
    const srR = optRole(target, run, 'sr'), sdR = optRole(target, run, 'sd'), cvd = optRole(target, run, 'cvdA');
    if (fl && tr && srR && sdR && cvd) {
      const exp = expectedAnchors(sd, tr.values, srR.values, sdR.values, P.N, utcDayKey).filter((a) => a >= P.N + 5);
      const cal = anchorsOf(sd, utcDayKey).filter((a) => a >= P.N + 5);
      const seam = setMinus(exp, cal);
      const naBars = range(P.N + 5, sd.bars.length).filter((t) => !isF(fl.values[t]));
      tc.check(seam.length === 1 && sameSet(naBars, exp), `costura da cobertura (${sd.desc}): linhas reiniciam nas âncoras do calendário e uma vez na 1.ª barra com janela σ/ρ toda fina`,
        `esperadas ${exp.join(',')} (costura ${seam.join(',') || '—'}); interrupções ${naBars.slice(0, 8).join(',')}`);
      if (seam.length === 1) {
        const a = seam[0], end = cal.find((x) => x > a) ?? sd.bars.length;
        let bad = 0;
        for (let t = a + 1; t < end; t++) if (relErr(fl.values[t], cvd.values[t] / sdR.values[a], 1e-9) > 1e-6) bad++;
        const dl = optRole(target, run, 'delta');
        const resetOk = dl ? Math.abs(cvd.values[a] - dl.values[a]) <= 1e-9 * Math.max(1, Math.abs(dl.values[a])) : true;
        tc.check(bad === 0 && resetOk, `costura: "${cvd.title}" reinicia na barra ${a} e F = CVD_a/σΔ congelado aí (janela toda fina)`,
          `${bad}/${end - a - 1} barras divergentes; reinício do CVD ${resetOk ? 'ok' : 'falhou'}`);
      }
    } else tc.warn('costura: plots da linha CVD, qualidade, σ ou CVD ancorado não encontrados');
  }
}

// ───────────────────────────── T8 ─────────────────────────────
function t8Sets(quick) {
  // jumpData: guarda de gaps de spec §4.3 (saltos de abertura ≫ 3σ e gaps pequenos no início do dia); a 2.ª variante
  // junta barras isoladas sem intrabars (BVC na barra com r = ln(C/O) nos gaps). Também no modo rápido (mutações).
  return [nullData(4500), gapData(), jumpData(), jumpData({ noIntrabarsProb: 0.003 }), ...(quick ? [] : [absorptionData({ count: 10 })])];
}

/** Delta e tier por barra como o indicador os vê com o stub: barras sem intrabars → BVC na barra, tier 1. */
function stubDeltaTier(data) {
  const close = arr(data, (b) => b.close), open = arr(data, (b) => b.open), vol = arr(data, (b) => b.volume);
  const rBar = computeRBar(open, close, data.bars.map((b) => b.openTime));
  const barDelta = computeBarDelta(rBar, vol);
  const n = data.bars.length;
  const delta = new Float64Array(n), tier = new Float64Array(n);
  for (let t = 0; t < n; t++) {
    const noIntra = data.bars[t].code === NO_INTRABARS;
    delta[t] = vol[t] === 0 ? 0 : noIntra ? barDelta[t] : stubDelta(data.bars[t].code, vol[t]);
    tier[t] = vol[t] === 0 ? (t > 0 ? tier[t - 1] : 0) : noIntra ? 1 : 3;
  }
  return { rBar, delta, tier };
}

export async function t8Reference(tc, target, { quick = false } = {}) {
  const P = params(target);
  for (const data of t8Sets(quick)) {
    const run = await target.run(data, statWanted(target));
    const z = requireRole(tc, target, run, 'z', 'Z');
    if (!z) return;
    const { rBar, delta, tier } = stubDeltaTier(data);
    const ref = computeRef({ rBar, delta, tier, opts: P });
    const warm = 3 * P.N + P.K;
    const { r, n } = pearsonArr(z.values, ref.Z, warm);
    tc.check(r >= 0.98, `${data.id}: corr(Z Pine, Z referência JS) ≥ 0.98`, `r = ${fmt(r, 5)} em ${n} barras`);
    if (r < 0.995 && r >= 0.98) tc.warn(`${data.id}: corr < 0.995`, 'diferença de detalhe (aquecimento do RMS, regra de gap, …)');
    let onlyOne = 0, maxAbs = 0, firstOnly = -1;
    for (let t = warm; t < data.bars.length; t++) {
      if (isF(z.values[t]) !== isF(ref.Z[t])) { onlyOne++; if (firstOnly < 0) firstOnly = t; }
      else if (isF(z.values[t])) maxAbs = Math.max(maxAbs, Math.abs(z.values[t] - ref.Z[t]));
    }
    // hqOk = N + max(K, ke) barras seguidas de qualidade ≥ média (σ/ρ de todos os termos das somas no regime); depois de
    // uma quebra o Z volta logo que o hqOk volta (RMS dos últimos M valores VÁLIDOS).
    tc.check(onlyOne === 0, `${data.id}: Z definido exactamente nas mesmas barras que a referência (após ${warm}; hqNeed = ${ref.hqNeed})`,
      `${onlyOne} barras só num dos lados${firstOnly >= 0 ? ` (1.ª @${firstOnly})` : ''}`);
    tc.check(maxAbs <= 1e-6, `${data.id}: |Z Pine − Z ref| ≤ 1e-6 (aquecimento expansivo incluído)`, `máx ${fmt(maxAbs, 9)}`);
    // zF/zP (eventos, spec §7): mesma definição de hqOk e RMS desfasado próprio
    for (const [role, refSer, name] of [['zF', ref.zF, 'zF'], ['zP', ref.zP, 'zP']]) {
      const pz = optRole(target, run, role);
      if (!pz) { tc.warn(`${name} (Data Window) não encontrado`); continue; }
      let one = 0, mx = 0;
      for (let t = warm; t < data.bars.length; t++) {
        if (isF(pz.values[t]) !== isF(refSer[t])) one++;
        else if (isF(pz.values[t])) mx = Math.max(mx, Math.abs(pz.values[t] - refSer[t]));
      }
      tc.check(one === 0 && mx <= 1e-6, `${data.id}: ${name} = referência JS (janela ke = ${P.ke}, RMS desfasado)`, `${one} barras só num lado; máx |Δ| ${fmt(mx, 9)}`);
    }
    // Pernas P_K/F_K (Data Window; decidem o texto do estado) e λ OLS (bps/1000): nenhum outro teste os verifica.
    // Só nas edições reais (o stand-in usa outras convenções: λ sem ×1000 e pernas filtradas pelo hqOk).
    const lamRef = Float64Array.from(ref.lamOls, (v) => v * 1000);
    const legChecks = target.info.edition === 'standin' ? [] :
      [['pLeg', ref.pLeg, 'P_K = Σ_K u_r/√K', warm], ['fLeg', ref.fLeg, 'F_K = Σ_K u_d/√K', warm], ['lamOls', lamRef, 'λ OLS = ρ·σr/σΔ·1000', P.N + 2]];
    // η (eficiência de impacto, só com |F_e| ≥ 1.5): definido nas mesmas barras e igual à referência
    const etaP = target.info.edition === 'standin' ? null : optRole(target, run, 'eta');
    if (etaP) {
      let one = 0, mx = 0, nEta = 0;
      for (let t = warm; t < data.bars.length; t++) {
        if (isF(etaP.values[t]) !== isF(ref.eta[t])) one++;
        else if (isF(etaP.values[t])) { nEta++; mx = Math.max(mx, relErr(etaP.values[t], ref.eta[t], 1e-6)); }
      }
      tc.check(one === 0 && mx <= 1e-6 && nEta > 0, `${data.id}: "${etaP.title}" = referência JS (Σ_ke r / (λ_OLS·Σ_ke Δ) com |F_e| ≥ 1.5)`,
        `${nEta} barras com η; ${one} só num lado; máx erro relativo ${fmt(mx, 9)}`);
    }
    // Delta por barra (inclui o BVC na barra das barras sem intrabars, com r = ln(C/O) nos gaps) = referência
    if (data.bars.gapStats) {
      const dp = optRole(target, run, 'delta');
      if (dp) {
        const cmp = compareSeries(range(1, data.bars.length), (t) => dp.values[t], (t) => delta[t], 1e-9, 1e-6);
        tc.check(cmp.nBad === 0, `${data.id}: delta por barra = referência (stub; BVC na barra com guarda de gaps)`, `${cmp.nBad}/${cmp.n} fora de 1e-9 (pior ${fmt(cmp.maxErr, 9)} @${cmp.worstIdx})`);
      }
      let changed = 0;
      for (let t = 1; t < data.bars.length; t++) if (Math.abs(rBar[t] - 1e4 * Math.log(data.bars[t].close / data.bars[t - 1].close)) > 1e-9) changed++;
      tc.note(`${data.id}: ${data.bars.gapStats.nJump} saltos de abertura e ${data.bars.gapStats.nDay} gaps de início de dia → a regra de gaps muda r em ${changed} barras`);
    }
    for (const [role, refSer, name, from] of legChecks) {
      const pz = optRole(target, run, role);
      if (!pz) { tc.warn(`${name} (Data Window) não encontrado`); continue; }
      const cmp = compareSeries(range(from, data.bars.length), (t) => pz.values[t], (t) => refSer[t], 1e-6, 1);
      tc.check(cmp.nBad === 0, `${data.id}: "${pz.title}" = referência JS (${name})`, `${cmp.nBad}/${cmp.n} fora de 1e-6 (pior ${fmt(cmp.maxErr, 9)} @${cmp.worstIdx})`);
    }
    if (data.meta?.noIntrabarsBlocks?.length) {
      for (const [s0, len] of data.meta.noIntrabarsBlocks) {
        const back = range(s0 + len, data.bars.length).find((t) => isF(z.values[t]));
        tc.note(`${data.id}: bloco ${s0}+${len} sem intrabars → Z volta na barra ${back ?? '—'} (${back !== undefined ? back - (s0 + len) : '—'} barras depois; hqNeed = ${ref.hqNeed})`);
      }
    }
    tc.note(`${data.id}: max |ΔZ| = ${fmt(maxAbs, 9)} (desde ${warm}); Z Pine "${z.title}"`);
    for (const [role, refSer, name] of [['sr', ref.srP, 'σr'], ['sd', ref.sdP, 'σΔ'], ['rho', ref.rhoP, 'ρ']]) {
      const pp = optRole(target, run, role);
      if (!pp) { tc.warn(`${name} (Data Window) não encontrado`); continue; }
      const cmp = compareSeries(range(P.N + 2, data.bars.length), (t) => pp.values[t], (t) => refSer[t], 1e-6, 1e-9);
      tc.check(cmp.nBad === 0, `${data.id}: "${pp.title}" = ${name} desfasado (populacional, N=${P.N}) da referência`, `${cmp.nBad}/${cmp.n} fora de 1e-6 (pior ${fmt(cmp.maxErr, 8)} @${cmp.worstIdx})`, 'warn');
    }
  }
}

// ───────────────────────────── T9 ─────────────────────────────
function t9Wanted(target) {
  const ltf = target.option('srcIn', 'ltf');
  const w = { s1: { srcIn: ltf, precIn: target.option('precIn', 's1') }, auto: { srcIn: ltf, precIn: target.option('precIn', 'auto') },
    bar: { srcIn: target.option('srcIn', 'bar') } };
  if (target.hasInput('ltfCustIn')) w.custom = { srcIn: ltf, precIn: target.option('precIn', 'custom'), ltfCustIn: '5' };
  if (target.hasInput('fallbackIn')) w.none = { srcIn: ltf, precIn: target.option('precIn', 's1'), fallbackIn: target.option('fallbackIn', 'none') };
  if (target.hasInput('clsIn')) w.bvc = { srcIn: ltf, precIn: target.option('precIn', 's1'), clsIn: target.option('clsIn', 'bvc') };
  // qualidade alta só para 1T/1S com a regra da vela (revisão 2): segundos ≠ 1 abaixo do gráfico → média
  if (target.hasInput('ltfCustIn') && target.info.edition !== 'standin') w.cust30 = { srcIn: ltf, precIn: target.option('precIn', 'custom'), ltfCustIn: '30S' };
  return w;
}

export async function t9Engine(tc, target) {
  const data = engineData(1500);
  tc.note(`dados: ${data.desc}`);
  const n = data.bars.length;
  const close = arr(data, (b) => b.close), open = arr(data, (b) => b.open), vol = arr(data, (b) => b.volume);
  const rBar = computeRBar(open, close, data.bars.map((b) => b.openTime));
  const barDelta = computeBarDelta(rBar, vol);
  const stub = arr(data, (b) => stubDelta(b.code, b.volume));
  const ltf = target.option('srcIn', 'ltf');
  const intra = range(1, n).filter((t) => data.bars[t].code !== NO_INTRABARS && vol[t] > 0);
  const noIntra = range(1, n).filter((t) => data.bars[t].code === NO_INTRABARS && vol[t] > 0);
  const zeroV = range(1, n).filter((t) => vol[t] === 0);
  const get = (run, role) => optRole(target, run, role);
  const W = t9Wanted(target);
  const P9 = Object.fromEntries(Object.entries(W).map(([k, w]) => [k, target.run(data, w)]));
  // (1) precisão 1S → tier 3, delta = stub; sem intrabars → fallback BVC tier 1; volume 0 → delta 0, tier anterior
  const r1 = await P9.s1;
  const d1 = get(r1, 'delta'), t1 = get(r1, 'tier');
  if (!d1) { tc.fail('plot "delta" (Data Window) encontrado', `candidatos: ${(target.roles.delta || []).join(', ')}`); return; }
  let c = compareSeries(intra, (t) => d1.values[t], (t) => stub[t], 1e-9, 1e-9);
  tc.check(c.nBad === 0, 'intrabar (stub): delta da barra = delta verdadeiro decodificado', `${c.nBad}/${c.n} (pior ${fmt(c.maxErr, 10)})`);
  c = compareSeries(noIntra, (t) => d1.values[t], (t) => barDelta[t], 1e-6, 1e-6);
  tc.check(c.nBad === 0, 'barras sem intrabars: delta = BVC-Normal na barra (spec §4.3)', `${c.nBad}/${c.n} fora de 1e-6 (pior ${fmt(c.maxErr, 8)} @${c.worstIdx})`);
  tc.check(zeroV.every((t) => d1.values[t] === 0), 'volume 0: delta = 0', `${zeroV.filter((t) => d1.values[t] !== 0).length}/${zeroV.length} divergentes`);
  const ni = get(r1, 'intrabars');
  if (ni) tc.check(intra.every((t) => ni.values[t] === STUB_K) && noIntra.every((t) => ni.values[t] === 0),
    `"${ni.title}" = ${STUB_K} com intrabars (stub) e 0 sem intrabars`, `valores: ${[...new Set(Array.from(ni.values))].join(',')}`);
  if (W.bvc) {
    const rb = await P9.bvc;
    const db = get(rb, 'delta');
    const cb = compareSeries(intra, (t) => db.values[t], (t) => stubDeltaBvc(data.bars[t].code, vol[t]), 1e-7, 1e-6); // soma de 5 partes
    tc.check(cb.nBad === 0, 'classificador BVC: delta = soma do array BVC do pedido intrabar (o input tem efeito)', `${cb.nBad}/${cb.n} (pior ${fmt(cb.maxErr, 10)})`);
    const tb = get(rb, 'tier');
    if (tb && target.info.edition !== 'standin') tc.check(intra.every((t) => tb.values[t] === 2), 'classificador BVC com 1S: qualidade média (tier 2; dossier §3.2: 1S BVC ≈ 1 min com a regra da vela)',
      `tiers: ${[...new Set(intra.map((t) => tb.values[t]))].join(',')}`);
  }
  if (W.cust30) {
    const t30 = get(await P9.cust30, 'tier');
    if (t30) tc.check(intra.every((t) => t30.values[t] === 2), 'LTF personalizado "30S" em 5m: qualidade média (alta só com 1T/1S)', `tiers: ${[...new Set(intra.map((t) => t30.values[t]))].join(',')}`);
  }
  if (t1) {
    tc.check(intra.every((t) => t1.values[t] === 3), 'precisão 1S: tier 3 nas barras com intrabars', `tiers: ${[...new Set(intra.map((t) => t1.values[t]))].join(',')}`);
    tc.check(noIntra.every((t) => t1.values[t] === 1), 'sem intrabars (fallback BVC): tier 1', `tiers: ${[...new Set(noIntra.map((t) => t1.values[t]))].join(',')}`);
    tc.check(zeroV.every((t) => t1.values[t] === t1.values[t - 1]), 'volume 0: tier = tier da barra anterior', `${zeroV.filter((t) => t1.values[t] !== t1.values[t - 1]).length} divergentes`);
  } else tc.warn('plot "tier" (Data Window) não encontrado — verificações de tier ignoradas');
  // (1b) volume de ticks (syminfo.volumetype "tick", ou FX à vista): sem lado agressor → delta derivado do preço →
  // qualidade baixa (tier 1) mesmo com 1S, sem Z, sem eventos e sem alertas; a tabela diz porquê.
  // (série nula sem falhas de intrabars: com qualidade alta haveria Z, eventos e alert())
  if (/volume de ticks/.test(target.source)) {
    const nd = nullData(1500, 5);
    for (const [nm, si] of [['volumetype "tick"', { volumetype: 'tick' }], ['FX (syminfo.type "forex")', { type: 'forex', volumetype: 'n/a' }]]) {
      const rt = await target.run(nd, W.s1, { syminfo: si });
      const tt = get(rt, 'tier'), zt = get(rt, 'z');
      if (tt) tc.check(Array.from(tt.values).every((v) => v === 1), `precisão 1S com ${nm}: qualidade baixa (tier 1, volume de ticks sem lado agressor)`, `tiers: ${[...new Set(Array.from(tt.values))].join(',')}`);
      if (zt) tc.check(finiteFrac(zt.values) === 0, `${nm}: sem Z`, pct(finiteFrac(zt.values)));
      const txt = tableText(rt);
      tc.check(/volume de ticks/.test(txt) && /Sem sinais: volume de ticks/.test(txt), `${nm}: tabela com o aviso «volume de ticks» e o estado «Sem sinais: volume de ticks»`, txt.split('\n').slice(0, 3).join(' | ').slice(0, 200));
      const evL = rt.labels.filter((l) => /absorvid|sem fluxo/i.test(labelText(l)));
      tc.check(evL.length === 0 && rt.alerts.length === 0, `${nm}: sem eventos nem alertas`, `${evL.length} rótulos, ${rt.alerts.length} alertas`);
    }
  }
  // (1c) unidade adaptativa do λ (lamExp): com volume × 1e6 o λ por unidade fica minúsculo; a tabela tem de o mostrar
  // numa escala de 10^(3k) unidades com o valor do λσ em [0.1, 1000).
  if (/bps por/.test(target.source)) {
    const nd = nullData(1500, 5);
    const big = { ...nd, id: `${nd.id}-vol1e6`, bars: nd.bars.map((b) => ({ ...b, volume: b.volume * 1e6 })), klines: nd.klines.map((k) => ({ ...k, volume: k.volume * 1e6 })) };
    const [rs, rb] = await Promise.all([target.run(nd, W.s1), target.run(big, W.s1)]);
    const RE = /λσ (\d+(?:\.\d+)?) bps por (1 unidade|mil unidades|1 milhão de unidades|10⁹ unidades|10¹² unidades)/;
    const ms = tableText(rs).match(RE), mb = tableText(rb).match(RE);
    const SC = { '1 unidade': 1, 'mil unidades': 1e3, '1 milhão de unidades': 1e6, '10⁹ unidades': 1e9, '10¹² unidades': 1e12 };
    const okB = mb && Number(mb[1]) >= 0.1 && Number(mb[1]) < 1000 && mb[2] !== '1 unidade';
    tc.check(Boolean(okB), 'volume × 1e6: λσ na tabela numa escala de 10^(3k) unidades com valor em [0.1, 1000)', mb ? `${mb[1]} bps por ${mb[2]}` : 'λσ não encontrado');
    if (ms && mb) {
      const perUnitS = Number(ms[1]) / SC[ms[2]], perUnitB = Number(mb[1]) / SC[mb[2]];
      tc.check(Math.abs(perUnitB * 1e6 / perUnitS - 1) < 0.02, 'volume × 1e6: λσ por unidade = λσ original / 1e6 (± arredondamento a 3 algarismos)',
        `${ms[1]} bps por ${ms[2]} vs ${mb[1]} bps por ${mb[2]}`);
    }
  }
  // (2) precisão Auto em 5m → "1" → tier 2
  const r2 = await P9.auto;
  const t2 = get(r2, 'tier');
  if (t2) tc.check(intra.every((t) => t2.values[t] === 2), 'precisão Auto em 5m ("1"): tier 2', `tiers: ${[...new Set(intra.map((t) => t2.values[t]))].join(',')}`);
  // (3) personalizado = timeframe do gráfico → tier 1, sem Z
  if (target.hasInput('ltfCustIn')) {
    const r3 = await P9.custom;
    const t3 = get(r3, 'tier'), z3 = get(r3, 'z');
    if (t3) tc.check(intra.every((t) => t3.values[t] <= 1), 'LTF personalizado = TF do gráfico ("5"): tier ≤ 1', `tiers: ${[...new Set(intra.map((t) => t3.values[t]))].join(',')}`);
    if (z3) tc.check(finiteFrac(z3.values) === 0, 'tier ≤ 1: Z ausente (na)', pct(finiteFrac(z3.values)));
  }
  // (4) só barras do gráfico
  const r4 = await P9.bar;
  const d4 = get(r4, 'delta'), t4 = get(r4, 'tier');
  c = compareSeries(range(1, n).filter((t) => vol[t] > 0), (t) => d4.values[t], (t) => barDelta[t], 1e-6, 1e-6);
  tc.check(c.nBad === 0, '"Só barras do gráfico": delta = BVC-Normal na barra', `${c.nBad}/${c.n} (pior ${fmt(c.maxErr, 8)} @${c.worstIdx})`);
  if (t4) tc.check(range(0, n).every((t) => t4.values[t] === 1), '"Só barras do gráfico": tier 1', `tiers: ${[...new Set(Array.from(t4.values))].join(',')}`);
  // (5) fallback "Nenhum"
  if (target.hasInput('fallbackIn')) {
    const r5 = await P9.none;
    const d5 = get(r5, 'delta'), t5 = get(r5, 'tier'), pl5 = get(r5, 'pLine');
    tc.check(noIntra.every((t) => !isF(d5.values[t])), 'fallback "Nenhum": delta na sem intrabars', `${noIntra.filter((t) => isF(d5.values[t])).length} finitos`);
    if (t5) tc.check(noIntra.every((t) => t5.values[t] === 0), 'fallback "Nenhum": tier 0 sem intrabars', `tiers: ${[...new Set(noIntra.map((t) => t5.values[t]))].join(',')}`);
    if (pl5) tc.check(noIntra.every((t) => !isF(pl5.values[t])), 'fallback "Nenhum": linhas na quando não há delta (spec §6)', `${noIntra.filter((t) => isF(pl5.values[t])).length} finitos`, 'warn');
  } else tc.skip('input fallbackIn inexistente (stand-in)');
}

// ───────────────────────────── T10 ─────────────────────────────
function t10Runs(target) {
  const data = nativeLtfData();
  const base = { srcIn: target.option('srcIn', 'ltf'), precIn: target.option('precIn', 'm1') };
  const cls = target.hasInput('clsIn') ? [['candle', 'regra da vela'], ['bvc', 'BVC por intrabar']] : [[null, 'classificador por omissão']];
  return cls.map(([m, name]) => ({ name, member: m, data, wanted: m ? { ...base, clsIn: target.option('clsIn', m) } : base,
    opts: { stub: false, ltfBars: { 1: data.subs } } }));
}

/** T10: request.security_lower_tf NATIVO (sem stub): ltfSigned avaliado pelo PineTS sobre sub-barras de 1 min. */
export async function t10NativeLtf(tc, target) {
  const runs = t10Runs(target);
  const data = runs[0].data;
  tc.note(`dados: ${data.desc}; precisão "1 minuto" (tier 2); sem cotações bid/ask (a regra das cotações do "1T" não é exercitada)`);
  const ref = refLtfSigned(data.subs, data.per);
  const proms = runs.map((r) => target.run(r.data, r.wanted, r.opts));
  for (let k = 0; k < runs.length; k++) {
    const r = runs[k];
    let run;
    try { run = await proms[k]; } catch (e) { tc.fail(`executa sem excepções (${r.name})`, String(e.message || e).split('\n')[0]); continue; }
    const d = optRole(target, run, 'delta'), ni = optRole(target, run, 'intrabars'), tier = optRole(target, run, 'tier');
    if (!d) { tc.fail('plot "delta" encontrado'); continue; }
    if (ni) tc.check(Array.from(ni.values).every((v) => v === data.per), `${r.name}: ${data.per} intrabars por barra`, `valores: ${[...new Set(Array.from(ni.values))].join(',')}`);
    if (tier) tc.check(Array.from(tier.values).every((v) => v === 2), `${r.name}: tier 2 com intrabars de 1 min`, `valores: ${[...new Set(Array.from(tier.values))].join(',')}`);
    const exp = r.member === 'bvc' ? ref.bvc : ref.cand;
    const cmp = compareSeries(range(0, data.klines.length), (t) => d.values[t], (t) => exp[t], 1e-7, 1);
    tc.check(cmp.nBad === 0, `${r.name}: delta da barra = soma da referência JS de ltfSigned (estado contínuo entre barras)`,
      `${cmp.nBad}/${cmp.n} fora de 1e-7 (pior ${fmt(cmp.maxErr, 10)} @${cmp.worstIdx})`);
  }
  // Intrabars esparsos (mercado pouco líquido): só 2 das 5 sub-barras de 1 min por barra de 5 min → média 2 < 60% de 5
  // possíveis → aviso «poucos intrabars» na tabela (o stub devolve sempre 5 e não exercita este aviso).
  if (target.info.edition !== 'standin' && /poucos intrabars/.test(target.source)) {
    const sparse = { ...data, id: `${data.id}-sparse`, subs: data.subs.filter((_, i) => i % data.per === 1 || i % data.per === 3) };
    let run;
    try { run = await target.run(sparse, runs[0].wanted, { stub: false, ltfBars: { 1: sparse.subs } }); } catch (e) { tc.fail('intrabars esparsos: executa sem excepções', String(e.message || e).split('\n')[0]); return; }
    const ni = optRole(target, run, 'intrabars');
    if (ni) tc.check(Array.from(ni.values).every((v) => v === 2), 'intrabars esparsos: 2 intrabars por barra', `valores: ${[...new Set(Array.from(ni.values))].join(',')}`);
    const txt = tableText(run);
    tc.check(/⚠[^\n]*poucos intrabars/.test(txt) && /2\.0 de 5 possíveis/.test(txt), 'intrabars esparsos: tabela com «⚠ poucos intrabars» (2.0 de 5 possíveis)', txt.split('\n').slice(0, 4).join(' | ').slice(0, 240));
  }
}

// ───────────────────────────── T11 ─────────────────────────────
/** Texto de todas as células (e dicas) das tabelas de uma execução. */
function tableText(run) {
  const out = [];
  const walk = (x) => {
    if (!x) return;
    if (Array.isArray(x)) { x.forEach(walk); return; }
    if (typeof x === 'object') {
      if (typeof x.text === 'string') out.push(x.text);
      if (typeof x.tooltip === 'string' && x.tooltip) out.push(x.tooltip);
      if (x.cells) walk(x.cells);
    }
  };
  walk(run.tables);
  return out.join('\n');
}

const tfCache = new Map();
function tfData(id, barSec, nBars, episodes = []) {
  if (!tfCache.has(id)) {
    const { bars, meta } = generate({ seed: 7, nBars, barSec, episodes });
    tfCache.set(id, { id, bars, klines: toKlines(bars), meta, episodes, desc: `${nBars} barras de ${barSec} s` });
  }
  return tfCache.get(id);
}

// Absorções de UMA barra, de lados opostos em barras seguidas (ke = 1 em 15 min): cada barra tem de começar um evento
// novo (a regra antiga "cond e não cond[1]" engolia a segunda). Depois do aquecimento de 2N valores do zF.
const FLIP_EPISODES = [500, 650, 800, 950, 1100, 1250, 1400].flatMap((s0, k) => {
  const s1 = k % 2 === 0 ? 1 : -1;
  return [{ type: 'absorption', start: s0, len: 1, side: s1, strength: 0.6 }, { type: 'absorption', start: s0 + 1, len: 1, side: -s1, strength: 0.6 }];
});

/**
 * Casos do T11: timeframe do gráfico × precisão × âncora. tier = qualidade esperada nas barras com intrabars;
 * z = 'none' (sem Z) | 'some' (Z definido após o aquecimento); anchorKey = chave de calendário cuja mudança é
 * uma âncora (a linha do fluxo interrompe-se aí); tbl = regex que o texto da tabela tem de conter.
 */
function t11Cases(target) {
  const opt = (k, m) => { try { return target.option(k, m); } catch { return null; } };
  const ltf = opt('srcIn', 'ltf'), auto = opt('precIn', 'auto'), s1 = opt('precIn', 's1');
  const year = (ms) => new Date(ms).getUTCFullYear();
  const sessKey = (ms) => Math.floor((ms - 8.5 * 3600e3) / 86400e3); // muda às 08:30 UTC (bolsa = UTC no harness)
  const cases = [
    { id: '1m · Auto', tf: '1', sec: 60, n: 1500, wanted: { srcIn: ltf, precIn: auto }, tier: 1, z: 'none', anchorKey: utcDayKey, tbl: /Sem sinais no gráfico de 1 min: escolha 1S ou 1T/ },
    { id: '1m · 1S', tf: '1', sec: 60, n: 1500, wanted: { srcIn: ltf, precIn: s1 }, tier: 3, z: 'some', anchorKey: utcDayKey, audit: true, alertTf: '1 min' },
    { id: '1h · Auto', tf: '60', sec: 3600, n: 1500, wanted: { srcIn: ltf, precIn: auto }, tier: 2, z: 'some', anchorKey: utcDayKey, tbl: /âncora diária/, audit: true, alertTf: '1 h' },
    { id: 'D · Auto', tf: 'D', sec: 86400, n: 600, wanted: { srcIn: ltf, precIn: auto }, tier: 2, z: 'some', anchorKey: utcMonthKey, tbl: /âncora mensal/ },
    { id: 'D · âncora diária (inválida)', tf: 'D', sec: 86400, n: 600, wanted: { srcIn: ltf, precIn: auto, anchIn: opt('anchIn', 'd1') }, tier: 2, anchorKey: utcMonthKey, tbl: /âncora inválida/ },
    { id: 'W · Auto', tf: 'W', sec: 604800, n: 300, wanted: { srcIn: ltf, precIn: auto }, tier: 2, anchorKey: year, tbl: /âncora anual/ },
    { id: '1S · Auto (intrabars = gráfico)', tf: '1S', sec: 1, n: 1500, wanted: { srcIn: ltf, precIn: auto }, tier: 1, z: 'none', optional: true, tbl: /Sem sinais no gráfico de 1 s: escolha 1T/ },
  ];
  const sess = opt('anchIn', 'sess');
  if (sess) cases.push({ id: '5m · sessão 0830-1515', tf: '5', sec: 300, n: 2000, wanted: { srcIn: ltf, precIn: s1, anchIn: sess }, tier: 3, z: 'some', anchorKey: sessKey, tbl: /âncora sessão 0830-1515/ });
  // Sessão que atravessa a meia-noite (CME Globex / FX): uma só âncora por dia, às 17:00 (nunca também à meia-noite).
  const sessKey17 = (ms) => Math.floor((ms - 17 * 3600e3) / 86400e3);
  if (sess && target.hasInput('sessIn')) cases.push({ id: '5m · sessão 1700-1600 (atravessa a meia-noite)', tf: '5', sec: 300, n: 2000,
    wanted: { srcIn: ltf, precIn: s1, anchIn: sess, sessIn: '1700-1600' }, tier: 3, anchorKey: sessKey17, tbl: /âncora sessão 1700-1600/ });
  cases.push({ id: '15m · 1S · absorções opostas em barras seguidas (ke = 1)', tf: '15', sec: 900, n: 1500, wanted: { srcIn: ltf, precIn: s1 },
    tier: 3, z: 'some', anchorKey: utcDayKey, audit: true, flips: true, episodes: FLIP_EPISODES });
  return cases.map((c) => ({ ...c, data: tfData(`tf-${c.tf}-${c.sec}-${c.n}${c.episodes ? '-flips' : ''}`, c.sec, c.n, c.episodes) }));
}

/** T11: timeframes, âncoras e qualidade fora dos 5 min (1m/1h/D/W/1S e sessão personalizada). */
export async function t11Timeframes(tc, target) {
  if (target.info.edition === 'standin') { tc.skip('stand-in: sem tabela/estados revistos'); return; }
  const cases = t11Cases(target);
  const proms = cases.map((c) => target.run(c.data, c.wanted, { timeframe: c.tf }));
  for (let k = 0; k < cases.length; k++) {
    const c = cases[k];
    const P = params(target, c.sec);
    let run;
    try { run = await proms[k]; } catch (e) {
      tc.check(false, `${c.id}: executa sem excepções`, String(e.message || e).split('\n')[0].slice(0, 200), c.optional ? 'warn' : 'fail');
      continue;
    }
    const n = c.data.bars.length;
    const tier = optRole(target, run, 'tier'), z = optRole(target, run, 'z'), fl = optRole(target, run, 'fLine');
    const intra = range(1, n).filter((t) => c.data.bars[t].code !== NO_INTRABARS && c.data.bars[t].volume > 0);
    if (tier) tc.check(intra.every((t) => tier.values[t] === c.tier), `${c.id}: qualidade ${c.tier} nas barras com intrabars`, `tiers: ${[...new Set(intra.map((t) => tier.values[t]))].join(',')}`);
    const warmZ = P.hqNeed + P.N + 5;
    if (z && c.z === 'none') tc.check(finiteFrac(z.values) === 0, `${c.id}: sem Z (qualidade baixa → sem sinais)`, `${pct(finiteFrac(z.values))} finito`);
    if (z && c.z === 'some' && n > warmZ + 20) tc.check(finiteFrac(z.values, warmZ) >= 0.9, `${c.id}: Z definido após o aquecimento (${warmZ} barras)`, pct(finiteFrac(z.values, warmZ)));
    if (fl && c.anchorKey) {
      const from = P.N + 5;
      const anchors = anchorsOf(c.data, c.anchorKey).filter((a) => a >= from);
      const naBars = range(from, n).filter((t) => !isF(fl.values[t]));
      tc.check(anchors.length > 0 && sameSet(naBars, anchors), `${c.id}: a linha do fluxo reinicia (interrompe-se) exactamente nas âncoras esperadas`,
        `${anchors.length} âncoras após ${from}; interrupções ${naBars.length}; só âncoras: ${setMinus(anchors, naBars).slice(0, 4).join(',') || '—'}; só interrupções: ${setMinus(naBars, anchors).slice(0, 4).join(',') || '—'}`);
    }
    if (c.tbl) { const txt = tableText(run); tc.check(c.tbl.test(txt), `${c.id}: tabela contém ${c.tbl}`, txt.split('\n').slice(0, 6).join(' | ').slice(0, 300)); }
    const evLabs = run.labels.filter((l) => /absorvid|sem fluxo/i.test(labelText(l)));
    if (evLabs.length) {
      const withNote = evLabs.filter((l) => /Apenas contexto/.test(String(l.tooltip ?? '')));
      const htf = c.sec >= 3600;
      tc.check(htf ? withNote.length === evLabs.length : withNote.length === 0, `${c.id}: nota «Apenas contexto» nas dicas dos eventos ${htf ? 'em todos (gráfico ≥ 1h)' : 'em nenhum (< 1h)'}`, `${withNote.length}/${evLabs.length}`);
    }
    const au = c.audit ? auditEvents(tc, target, run, c.data, P, `${c.id} (ke = ${P.ke}, vida = ${P.life})`) : null;
    if (c.flips && au) {
      // pares injectados com etiquetas nas DUAS barras e lados opostos
      const at = new Map(au.absBars.map((b, k) => [b, au.sides[k]]));
      const pairs = c.episodes.filter((_, k) => k % 2 === 0).map((e) => e.start);
      const both = pairs.filter((b) => at.has(b) && at.has(b + 1) && at.get(b) === -at.get(b + 1));
      // (nem todos os pares passam: o gate ρ ou o zP podem bloquear uma das barras; a regra é verificada pela auditoria)
      tc.check(au.nFlip > 0 && both.length >= 1, `${c.id}: absorções de lados opostos em barras seguidas dão dois eventos (inversão de lado)`,
        `${au.nFlip} inversões; pares com evento nas duas barras: ${both.length}/${pairs.length} (${pairs.map((b) => `${b}:${at.get(b) ?? '·'}/${at.get(b + 1) ?? '·'}`).join(' ')})`);
    }
    // alert(): símbolo com o prefixo da bolsa e timeframe legível (horas em h, não «60 min»)
    if (c.alertTf) {
      const al = run.alerts.filter((a) => a.type !== 'alertcondition');
      const head = `HARNESS:SYNBTC ${c.alertTf} · `;
      tc.check(al.length > 0 && al.every((a) => String(a.message || '').startsWith(head)), `${c.id}: alert() começa por «${head.trim()}»`,
        al.length ? String(al[0].message).slice(0, 60) : 'sem alert()');
    }
  }
}

// ───────────────────────────── pré-carregamento ─────────────────────────────
/**
 * Lança já (sem esperar) todas as execuções planeadas dos testes pedidos, para que corram em paralelo nos
 * workers enquanto os testes são avaliados por ordem. Erros de configuração são ignorados aqui (o teste
 * correspondente reporta-os).
 */
export function prefetch(target, ids, { quick = false, nBars = 3000, footprintEdition = false } = {}) {
  const go = (fn) => { try { fn(); } catch { /* o teste reporta */ } };
  const has = (id) => ids.includes(id);
  // ordem = ordem de avaliação (a fila de workers é FIFO)
  if (has('T4')) {
    if (footprintEdition) go(() => { const { data, cases } = t4fpConfigs(target, { quick, nBars }); for (const c of cases) target.run(data, c.wanted, { footprint: c.fp, fpTag: c.tag }); });
    else go(() => { for (const c of t4Configs(target, { quick, nBars }).cfgs) target.run(c.data, c.wanted); });
  }
  if (footprintEdition) return;
  if (has('T5') || has('T7') || has('T8')) go(() => target.run(nullData(4500), statWanted(target)));
  if (has('T6') || has('T8')) go(() => { for (const d of Object.values(t6Sets(quick))) target.run(d, statWanted(target)); });
  if (has('T6')) go(() => target.run(t6Sets(quick).absorption, t6LowConfWanted(target)));
  if (has('T6')) go(() => { const w = t6PivWanted(target); if (w) target.run(t6Sets(quick).absorption, w); });
  if (has('T6')) go(() => { const w = t6PinWanted(target); if (w) target.run(nullData(4500), w); });
  if (has('T7')) go(() => { const w = seamWanted(target); if (w) target.run(seamData(), w); });
  if (has('T7')) go(() => { for (const w of Object.values(t7Wanted(target, quick))) target.run(nullData(4500), w); });
  if (has('T8')) go(() => { for (const d of t8Sets(quick)) target.run(d, statWanted(target)); });
  if (has('T9')) go(() => { for (const w of Object.values(t9Wanted(target))) target.run(engineData(1500), w); });
  if (has('T10')) go(() => { for (const r of t10Runs(target)) target.run(r.data, r.wanted, r.opts); });
  if (has('T11') && target.info.edition !== 'standin') go(() => { for (const c of t11Cases(target)) target.run(c.data, c.wanted, { timeframe: c.tf }).catch(() => {}); });
}
