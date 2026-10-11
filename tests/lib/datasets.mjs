// Conjuntos de dados sintéticos usados pelos testes (determinísticos; ver synth.mjs).
// Cada função devolve { id, bars, klines, episodes, desc }.

import { generate, toKlines, scheduleEpisodes, mulberry32, gaussian } from './synth.mjs';

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
 * T8 (guarda de gaps, spec §4.3): série nula com saltos de abertura de 60–120 bps (≈ 8–15σ) em ~1% das barras e
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
