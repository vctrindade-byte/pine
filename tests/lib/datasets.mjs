// Conjuntos de dados sintéticos usados pelos testes (determinísticos; ver synth.mjs).
// Cada função devolve { id, bars, klines, episodes, desc }.

import { generate, toKlines, scheduleEpisodes, mulberry32, gaussian } from './synth.mjs';
import { NO_INTRABARS, STUB_NA_VOL } from './channel.mjs';

const cache = new Map();
function memo(id, fn) {
  if (!cache.has(id)) cache.set(id, fn());
  return cache.get(id);
}

function build(id, opts, desc) {
  const { bars, meta } = generate(opts);
  return { id, bars, klines: toKlines(bars), episodes: opts.episodes || [], meta, desc };
}

/** T4: ~3000 barras com cabeça sem intrabars (limite de intrabars), barras de volume 0 e 2 episódios. */
export function matrixData(nBars = 3000) {
  return memo(`matrix-${nBars}`, () => {
    const head = Math.round(nBars * 0.05);
    const eps = [
      { type: 'absorption', start: Math.round(nBars * 0.45), len: 30, side: 1, strength: 0.4 },
      { type: 'pwf', start: Math.round(nBars * 0.75), len: 30, side: 1, strength: 1.0 },
    ];
    return build(`matrix-${nBars}`, { seed: 11, nBars, noIntrabarsHead: head, zeroVolProb: 0.003, episodes: eps },
      `${nBars} barras 5m, ${head} iniciais sem intrabars, ~0,3% com volume 0, 1 absorção + 1 preço-sem-fluxo`);
  });
}

/** T5/T8: série nula (sem episódios). */
export function nullData(nBars = 4500, seed = 5) {
  return memo(`null-${nBars}-${seed}`, () => build(`null-${nBars}-${seed}`, { seed, nBars }, `${nBars} barras 5m nulas (seed ${seed})`));
}

/**
 * T8: a série nula com blocos sem intrabars a meio do histórico (falhas de dados → fallback BVC, tier 1). As
 * mesmas sementes que nullData: fora dos blocos as barras são idênticas. Exercita o caminho de Z depois de uma
 * quebra de qualidade (hqOk, RMS dos últimos M valores válidos).
 */
export function gapData(nBars = 4500, seed = 5, blocks = [[1500, 5], [3000, 30]]) {
  const id = `gap-${nBars}-${seed}-${blocks.map((b) => b.join('+')).join('_')}`;
  return memo(id, () => build(id, { seed, nBars, noIntrabarsBlocks: blocks },
    `${nBars} barras 5m nulas (seed ${seed}) com blocos sem intrabars ${blocks.map(([s0, l]) => `${s0}+${l}`).join(', ')}`));
}

/**
 * T8 (guarda de gaps, METODOLOGIA §3.1): série nula com saltos de abertura de 60–120 bps (≈ 8–15σ) em ~1% das barras e
 * gaps pequenos N(0, 3 bps) em cada início de dia UTC (session.isfirstbar tem de forçar r = ln(C/O) mesmo abaixo
 * de 3σ). Com noIntrabarsProb > 0, barras isoladas sem intrabars exercitam também o BVC na barra com gap.
 */
export function jumpData({ nBars = 4000, seed = 41, noIntrabarsProb = 0 } = {}) {
  const id = `jump-${nBars}-${seed}-${noIntrabarsProb}`;
  return memo(id, () => {
    const d = build(id, { seed, nBars, noIntrabarsProb, gaps: { seed: 9 } },
      `${nBars} barras 5m nulas com saltos de abertura (~1%, 60–120 bps) e gaps diários pequenos` +
      (noIntrabarsProb > 0 ? `, ~${(100 * noIntrabarsProb).toFixed(1)}% isoladas sem intrabars` : ''));
    d.desc += ` [${d.bars.gapStats.nJump} saltos, ${d.bars.gapStats.nDay} inícios de dia]`;
    return d;
  });
}

/**
 * T7 (costura da cobertura): série nula cujas primeiras `head` barras não têm intrabars (fallback BVC, qualidade
 * baixa), como no início da cobertura de 1S/1T. A âncora diária activa quando a cobertura começa congela σ/ρ de uma
 * janela mista; as linhas têm de reiniciar na 1.ª barra cuja janela σ/ρ (N barras) está toda em dados finos.
 */
export function seamData(nBars = 1500, head = 200, seed = 5) {
  const id = `seam-${nBars}-${head}-${seed}`;
  return memo(id, () => build(id, { seed, nBars, noIntrabarsHead: head },
    `${nBars} barras 5m nulas, ${head} iniciais sem intrabars (início da cobertura a meio de um dia)`));
}

/** T6: episódios de absorção (lados alternados comprador/vendedor). */
export function absorptionData({ count = 10, spacing = 320, firstStart = 520, strength = 0.4 } = {}) {
  const id = `abs-${count}-${spacing}-${strength}`;
  return memo(id, () => {
    const episodes = scheduleEpisodes({ type: 'absorption', count, firstStart, spacing, lenMin: 20, lenMax: 40, sides: [1, -1], strength, seed: 21 });
    const nBars = firstStart + count * spacing + 60;
    return build(id, { seed: 13, nBars, episodes }, `${count} absorções (força ${strength}·V, 20–40 barras, λ≈0) em ${nBars} barras`);
  });
}

/** T6: episódios de preço sem fluxo (deriva alternada para cima/baixo, Δ≈0). */
export function pwfData({ count = 10, spacing = 320, firstStart = 520, strength = 1.0 } = {}) {
  const id = `pwf-${count}-${spacing}-${strength}`;
  return memo(id, () => {
    const episodes = scheduleEpisodes({ type: 'pwf', count, firstStart, spacing, lenMin: 20, lenMax: 40, sides: [1, -1], strength, seed: 22 });
    const nBars = firstStart + count * spacing + 60;
    return build(id, { seed: 17, nBars, episodes }, `${count} episódios preço-sem-fluxo (deriva ${strength}σr/barra, Δ≈0) em ${nBars} barras`);
  });
}

/** T9: barras isoladas sem intrabars e de volume 0, para o motor de delta. */
export function engineData(nBars = 1500) {
  return memo(`engine-${nBars}`, () => build(`engine-${nBars}`, { seed: 31, nBars, noIntrabarsProb: 0.02, zeroVolProb: 0.01 },
    `${nBars} barras 5m, ~2% isoladas sem intrabars, ~1% volume 0`));
}

/** Footprint por barra a partir do delta verdadeiro (um único nível: compra = V(1+q)/2, venda = V(1−q)/2). */
export function footprintFor(data, { missingEvery = 0 } = {}) {
  const out = [];
  data.bars.forEach((b, i) => {
    if (missingEvery > 0 && i % missingEvery === missingEvery - 1) return; // barras sem footprint
    const q = b.q, V = b.volume;
    out.push({ openTime: b.openTime, levels: [{ price: b.low, buyVolume: (V * (1 + q)) / 2, sellVolume: (V * (1 - q)) / 2 }] });
  });
  return out;
}

/**
 * T10: barras de 5 min agregadas de sub-barras de 1 min servidas pelo provider (request.security_lower_tf nativo,
 * sem stub). ~15% das sub-barras são doji (close = open) para exercitar o lado transportado da regra da vela,
 * ~3% têm volume 0; atravessa viragens de dia UTC (session.isfirstbar no contexto intrabar).
 */
export function nativeLtfData(nChart = 600, per = 5) {
  return memo(`native-${nChart}-${per}`, () => {
    const rng = mulberry32(77);
    const start = Date.UTC(2025, 0, 6, 20, 0, 0);
    const subs = [];
    let p = 50000;
    for (let i = 0; i < nChart * per; i++) {
      const t = start + i * 60000;
      const o = p;
      let c = rng() < 0.15 ? o : o * Math.exp(gaussian(rng) * 3e-4);
      c = Math.round(c * 100) / 100;
      const vol = rng() < 0.03 ? 0 : 1 + 5 * rng();
      subs.push({ openTime: t, closeTime: t + 59999, open: o, high: Math.max(o, c) + 0.5, low: Math.min(o, c) - 0.5, close: c, volume: vol });
      p = c;
    }
    const klines = [];
    for (let k = 0; k < nChart; k++) {
      const s = subs.slice(k * per, (k + 1) * per);
      klines.push({ openTime: s[0].openTime, closeTime: s[0].openTime + per * 60000 - 1, open: s[0].open, close: s.at(-1).close,
        high: Math.max(...s.map((x) => x.high)), low: Math.min(...s.map((x) => x.low)), volume: s.reduce((a, x) => a + x.volume, 0) });
    }
    return { id: `native-${nChart}-${per}`, klines, bars: klines, subs, per, desc: `${nChart} barras 5m agregadas de ${nChart * per} sub-barras de 1 min (15% doji, 3% volume 0)` };
  });
}

/**
 * T10 (volume em falta nos intrabars, pedido nativo): nativeLtfData com o volume dos intrabars em falta (na) ou nulo.
 *   allNa      — os 5 intrabars sem volume e o gráfico também sem volume
 *   allNaChart — os 5 intrabars sem volume, o gráfico com volume (a fonte escolhida é que conta)
 *   partNa     — 2 dos 5 intrabars sem volume (gráfico = soma dos outros): a barra fica incompleta → volume em falta
 *   zero       — os 5 intrabars com volume 0 (gráfico 0): sem negócios
 *   last       — a última barra, com os 5 intrabars e o gráfico sem volume (estado na tabela)
 */
export function nativeNaVolData() {
  return memo('native-navol', () => {
    const base = nativeLtfData();
    const per = base.per;
    const subs = base.subs.map((x) => ({ ...x }));
    const klines = base.klines.map((k) => ({ ...k }));
    const n = klines.length;
    const marks = { allNa: [300, 301], allNaChart: [350], partNa: [400], zero: [450], last: n - 1 };
    const setSub = (b, j, v) => { subs[b * per + j].volume = v; };
    for (const b of [...marks.allNa, ...marks.allNaChart, marks.last]) for (let j = 0; j < per; j++) setSub(b, j, NaN);
    for (const b of marks.partNa) { setSub(b, 1, NaN); setSub(b, 3, NaN); }
    for (const b of marks.zero) for (let j = 0; j < per; j++) setSub(b, j, 0);
    for (let b = 0; b < n; b++) {
      const v = subs.slice(b * per, (b + 1) * per).map((x) => x.volume);
      klines[b].volume = marks.allNaChart.includes(b) ? base.klines[b].volume
        : marks.partNa.includes(b) ? v.filter(Number.isFinite).reduce((a, x) => a + x, 0) : v.reduce((a, x) => a + x, 0);
    }
    return { id: 'native-navol', klines, bars: klines, subs, per, marks,
      desc: `${base.desc}; volume dos intrabars em falta em ${marks.allNa.length + marks.allNaChart.length + 1} barras (todos), parcial em ${marks.partNa.length}, nulo em ${marks.zero.length}` };
  });
}

/**
 * T12 (integridade do volume): série nula de alta qualidade (1S) com barras sem observação de fluxo a meio de um regime
 * de qualidade alta. Índices e papéis em `marks` (o teste usa-os para as verificações dirigidas):
 *   missIso  — volume em falta (na) isolado, sem intrabars (→ fallback BVC com volume na), três com um salto de ±6σ
 *   missRun  — volume em falta em barras seguidas: 3 com +5σ cada, 12 sem salto, 4 com −5σ cada
 *   zeroLtf  — volume 0 com intrabars (o stub devolve volume 0): planas (O = H = L = C) e com movimento de +4σ
 *   zeroBar  — volume 0 sem intrabars (fallback BVC; volume da fonte = volume do gráfico = 0), plana e com −4σ
 *   naChart  — volume do gráfico em falta MAS intrabars com volume (stub: STUB_NA_VOL): é uma observação
 *   grid     — a partir da barra 1600, uma barra plana sem negócios a cada 9 (pivots separados por barras sem negócios)
 *   lowQ     — barras observadas sem intrabars (qualidade baixa: partem o regime e bloqueiam pivots que as abarquem)
 *   burst    — barras sem negócios, com movimento, dentro das divergências construídas (pivPairs: pivots P1/P2 logo a seguir
 *              a uma lowQ; uma regra «observações seguidas > barras desde o pivot anterior», ou um lqBar que avançasse nas
 *              barras sem observação, rejeitaria estas divergências, que a regra em observações aceita)
 *   decoupled — barras 400–599 com o preço desligado do fluxo (ρ ≈ 0: gate fechado; exercita o contador «com o gate aberto»)
 *   moves    — barras sem observação com salto de preço (com a regra antiga davam «preço sem fluxo»)
 */
export function volIntegrityData({ nBars = 2400, seed = 5 } = {}) {
  const id = `volint-${nBars}-${seed}`;
  return memo(id, () => {
    const sr = 8; // σr nominal do gerador (bps)
    const ov = {};
    const marks = { missIso: [], missRun: [], zeroLtf: [], zeroBar: [], naChart: [], grid: [], lowQ: [], burst: [], decoupled: [], moves: [], pivPairs: [] };
    const set = (i, o, role) => { ov[i] = { ...(ov[i] || {}), ...o }; if (role) marks[role].push(i); };
    // preço desligado do fluxo (ρ ≈ 0 → gate fechado durante ~N observações): há |Z| ≥ limiar com o gate fechado
    const rngD = mulberry32(99);
    for (let i = 400; i < 600; i++) set(i, { r: sr * gaussian(rngD) }, 'decoupled');
    for (const [i, k] of [[700, 6], [760, -6], [820, 0], [880, 6], [940, 0]]) set(i, { volume: NaN, noIntra: true, ...(k ? { r: k * sr } : {}) }, 'missIso');
    for (let i = 1000; i < 1003; i++) set(i, { volume: NaN, noIntra: true, r: 5 * sr }, 'missRun');
    for (let i = 1100; i < 1112; i++) set(i, { volume: NaN, noIntra: true }, 'missRun');
    for (let i = 1200; i < 1204; i++) set(i, { volume: NaN, noIntra: true, r: -5 * sr }, 'missRun');
    for (const i of [1300, 1302, 1340]) set(i, { volume: 0, flat: true }, 'zeroLtf');
    for (const i of [1380, 1381]) set(i, { volume: 0, r: 4 * sr }, 'zeroLtf');
    for (let i = 1420; i < 1425; i++) set(i, { volume: 0, flat: true }, 'zeroLtf');
    set(1460, { volume: 0, noIntra: true, flat: true }, 'zeroBar');
    set(1470, { volume: 0, noIntra: true, r: -4 * sr }, 'zeroBar');
    for (const i of [1500, 1520, 1521, 1540]) set(i, { volume: NaN }, 'naChart');
    // zona dos pivots: divergências construídas (preço e fluxo impostos) logo a seguir a uma barra observada de qualidade
    // baixa S (sem intrabars, com volume). side +1: topos (subida até P1, queda com vendas, subida com vendas até P2 > P1);
    // side −1: fundos (simétrico). 'A': P1 = S+1 (observada, qualidade alta) e 6 barras sem negócios entre os pivots;
    // 'B': P1 = S+2 numa barra sem negócios (S+1..S+3 sem negócios, qualidade herdada da S = baixa).
    const cluster = (S, kind, side) => {
      for (let i = S - 4; i <= S; i++) set(i, { r: side * 2 * sr });
      set(S, { noIntra: true }, 'lowQ');
      if (kind === 'A') {
        set(S + 1, { r: side * 2 * sr });
        for (let i = S + 2; i <= S + 12; i++) set(i, { r: -side * 2 * sr, q: -side * 0.5, ...(i >= S + 5 && i <= S + 10 ? { volume: 0 } : {}) }, i >= S + 5 && i <= S + 10 ? 'burst' : null);
      } else {
        for (const [k, sg] of [[1, 1], [2, 1], [3, -1]]) set(S + k, { r: sg * side * 2 * sr, volume: 0 }, 'burst');
        for (let i = S + 4; i <= S + 12; i++) set(i, { r: -side * 2 * sr, q: -side * 0.5 });
      }
      for (let i = S + 13; i <= S + 21; i++) set(i, { r: side * 3 * sr, q: -side * 0.5 });
      for (let i = S + 22; i <= S + 24; i++) set(i, { r: -side * 2 * sr, q: 0 });
      marks.pivPairs.push({ S, kind, side, p1: S + (kind === 'A' ? 1 : 2), p2: S + 21 });
    };
    cluster(1640, 'A', 1); cluster(1700, 'B', 1); cluster(1760, 'A', -1); cluster(1820, 'B', -1);
    for (const i of [1991, 2151]) set(i, { noIntra: true }, 'lowQ');
    // e uma barra plana sem negócios a cada 9 (onde não houver outra alteração)
    for (let i = 1600; i < nBars - 5; i += 9) if (!ov[i]) set(i, { volume: 0, flat: true }, 'grid');
    // barras sem observação (volume em falta ou nulo) com salto de preço imposto
    marks.moves = Object.keys(ov).map(Number).filter((i) => ov[i].r !== undefined && ov[i].r !== 0 && (Number.isNaN(ov[i].volume) || ov[i].volume === 0)).sort((a, b) => a - b);
    const d = build(id, { seed, nBars, overrides: ov }, `${nBars} barras 5m nulas (seed ${seed}) com volume em falta/nulo a meio da ` +
      `qualidade alta: ${marks.missIso.length} em falta isoladas, ${marks.missRun.length} em falta seguidas, ${marks.zeroLtf.length + marks.zeroBar.length} sem ` +
      `negócios, ${marks.naChart.length} com o volume do gráfico em falta e intrabars com volume; na zona dos pivots ${marks.pivPairs.length} divergências ` +
      `construídas a seguir a barras de qualidade baixa (${marks.burst.length} barras sem negócios no meio), ${marks.lowQ.length} de qualidade baixa e ${marks.grid.length} sem negócios (1 em 9)`);
    d.marks = marks;
    return d;
  });
}

/**
 * T12 (aglomerados em observações): as absorções do T6 (mesmos episódios e semente) com sequências de `gap` barras planas
 * sem negócios (gap > ke = 3) dentro de cada episódio, a `offsets` barras do início. O período refractário dos eventos
 * conta observações (a unidade da janela ke do zF/zP), por isso um aglomerado não se parte numa sequência de barras sem
 * observação; uma regra em barras abriria aí um evento novo (etiqueta e alerta repetidos).
 */
export function clusterGapData({ gap = 4, offsets = [6, 14, 22] } = {}) {
  const id = `absgap-${gap}-${offsets.join('_')}`;
  return memo(id, () => {
    const count = 10, spacing = 320, firstStart = 520, strength = 0.4;
    const episodes = scheduleEpisodes({ type: 'absorption', count, firstStart, spacing, lenMin: 20, lenMax: 40, sides: [1, -1], strength, seed: 21 });
    const nBars = firstStart + count * spacing + 60;
    const ov = {}, gaps = [];
    for (const ep of episodes) {
      for (const o of offsets) {
        if (o + gap > ep.len) continue;
        for (let i = ep.start + o; i < ep.start + o + gap; i++) ov[i] = { volume: 0, flat: true };
        gaps.push(ep.start + o);
      }
    }
    const d = build(id, { seed: 13, nBars, episodes, overrides: ov }, `${count} absorções do T6 com ${gaps.length} sequências de ${gap} barras ` +
      `planas sem negócios dentro dos episódios (a ${offsets.join('/')} barras do início)`);
    d.marks = { gaps, gap };
    return d;
  });
}

/** T12: série curta cuja ÚLTIMA barra não tem observação (estado na tabela): kind 'miss' (volume em falta) ou 'zero'. */
export function volStateData(kind, nBars = 400, seed = 5) {
  const id = `volstate-${kind}-${nBars}-${seed}`;
  return memo(id, () => build(id, { seed, nBars, overrides: { [nBars - 1]: kind === 'miss' ? { volume: NaN, noIntra: true } : { volume: 0, flat: true } } },
    `${nBars} barras 5m; última barra ${kind === 'miss' ? 'com volume em falta' : 'sem negócios'}`));
}

/**
 * T12 (edição Footprint): footprint com volume PRÓPRIO, independente do do gráfico. Barras sem intrabars do conjunto
 * (volume em falta) ficam sem footprint (→ fallback BVC com o volume do gráfico na); as barras planas «sem negócios»
 * zeroLtf 1420–1424 e a grelha têm footprint de volume 0; as outras zeroLtf (gráfico com volume 0) têm footprint com
 * volume fpVol > 0 — o delta é o do footprint e a barra é uma observação; naChart: footprint com STUB_NA_VOL.
 * Devolve { footprint, fpBar } com fpBar[i] = { delta, vol } (ou null sem footprint) para a referência.
 */
export function volIntegrityFootprint(data, { fpVol = 50 } = {}) {
  const zeroFp = new Set([...data.marks.grid, ...data.marks.zeroLtf.filter((i) => i >= 1420 && i < 1425)]);
  const footprint = [], fpBar = [];
  data.bars.forEach((b, i) => {
    if (b.code === NO_INTRABARS) { fpBar.push(null); return; } // sem footprint
    const V = zeroFp.has(i) ? 0 : Number.isFinite(b.volume) && b.volume > 0 ? b.volume : b.volume === 0 ? fpVol : STUB_NA_VOL;
    const buy = (V * (1 + b.q)) / 2, sell = (V * (1 - b.q)) / 2;
    footprint.push({ openTime: b.openTime, levels: [{ price: b.low, buyVolume: buy, sellVolume: sell }] });
    fpBar.push({ delta: buy - sell, vol: buy + sell });
  });
  return { footprint, fpBar };
}
