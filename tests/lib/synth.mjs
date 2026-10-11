// Gerador sintético determinístico (semente) de barras de 5 minutos, 24/7 UTC, com fluxo assinado
// conhecido. Modelo (por barra t):
//
//   x_t = φ·x_{t−1} + √(1−φ²)·η_t                     (fluxo latente AR(1), variância 1)
//   q_t = clamp(sq·x_t, ±qMax)                          (rácio líquido do agressor Δ/V)
//   V_t = V0 · exp(σV·g_t − σV²/2) · sazonalidade(t)    (volume)
//   Δ_t = V_t · q̂_t   com q̂_t quantizado pelo canal de ms (o delta que o stub Pine vai ler)
//   r_t = σr·(ρ0·Δ_t/σΔ + √(1−ρ0²)·ε_t)    [bps]        (impacto linear: corr(r, Δ) ≈ ρ0)
//   O_t = C_{t−1},  C_t = O_t·exp(r_t/1e4),  H/L = max/min(O,C)·exp(±|ruído|)
//   Opção gaps (METODOLOGIA §3.1): saltos de abertura O_t ≠ C_{t−1} — em ~jumpProb das barras |ln(O/C₋₁)| de jumpMin–jumpMax
//   bps (≫ 3σ) e, em cada início de dia UTC, um gap pequeno N(0, daySd bps); a barra e todas as seguintes são
//   multiplicadas pelo factor acumulado (o retorno próprio de cada barra, ln(C/O), não muda). PRNG próprio: as
//   restantes séries são idênticas às geradas sem gaps.
//
// Episódios injectáveis (o resto da série segue o modelo nulo):
//   - absorption: L barras de fluxo forte e persistente (lado ±1) com λ ≈ 0 (preço plano: só ruído pequeno);
//   - pwf ("price without flow"): L barras com deriva no ruído do preço (sinal ±1) e Δ ≈ 0.
// O delta verdadeiro por barra (bars[i].delta) e a fracção compradora (bars[i].buyFrac) são conhecidos.

import { encodeQ, decodeQ, NO_INTRABARS } from './channel.mjs';

/** PRNG mulberry32 (determinístico, 32 bits). */
export function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function gaussian(rng) {
  let u = 0;
  while (u <= 1e-12) u = rng();
  const v = rng();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

export const DEFAULTS = Object.freeze({
  seed: 1,
  nBars: 3000,
  barSec: 300,
  start: Date.UTC(2025, 0, 6, 0, 0, 0), // segunda-feira 00:00 UTC
  price0: 50000,
  V0: 100,
  sigmaV: 0.4,
  seasonal: 0.3, // amplitude da sazonalidade intradiária do volume
  phi: 0.3, // persistência AR(1) do fluxo
  sq: 0.15, // desvio-padrão de q (Δ/V)
  qMax: 0.95,
  rho0: 0.5, // corr(r, Δ) alvo
  sigmaR: 8, // bps por barra
  zeroVolProb: 0, // probabilidade de barra com volume 0
  noIntrabarsHead: 0, // primeiras n barras sem intrabars (simula o limite de intrabars)
  noIntrabarsProb: 0, // probabilidade de barra isolada sem intrabars
  noIntrabarsBlocks: [], // [[início, comprimento], …]: blocos a meio do histórico sem intrabars (falhas/quebras de tier)
  episodes: [], // [{ type: 'absorption'|'pwf', start, len, side, strength }]
  gaps: null, // { seed, jumpProb, jumpMin, jumpMax (bps), daySd (bps), after }: saltos de abertura (ver acima)
});

/**
 * Gera barras. Devolve { bars, meta } onde cada barra tem:
 *   openTime (com o código nos ms), closeTime, open, high, low, close, volume,
 *   code, delta (NaN se sem intrabars), q, buyFrac, r (bps), episode (índice ou −1).
 */
export function generate(opts = {}) {
  const o = { ...DEFAULTS, ...opts };
  const rng = mulberry32(o.seed);
  const n = o.nBars;
  const barMs = o.barSec * 1000;
  const epAt = new Int32Array(n).fill(-1);
  o.episodes.forEach((ep, k) => {
    for (let i = ep.start; i < Math.min(n, ep.start + ep.len); i++) {
      if (epAt[i] !== -1) throw new Error(`episódios sobrepostos na barra ${i}`);
      epAt[i] = k;
    }
  });
  const sigmaDeltaNominal = o.sq * o.V0; // σΔ nominal (para a escala do impacto)
  const bars = [];
  let x = gaussian(rng);
  let price = o.price0;
  for (let i = 0; i < n; i++) {
    const t0 = o.start + i * barMs;
    // fluxo latente
    x = o.phi * x + Math.sqrt(1 - o.phi * o.phi) * gaussian(rng);
    const g = gaussian(rng);
    const e = gaussian(rng);
    const hNoise = Math.abs(gaussian(rng));
    const lNoise = Math.abs(gaussian(rng));
    const uZero = rng();
    const uNoIntra = rng();
    const secOfDay = ((t0 / 1000) % 86400);
    const season = 1 + o.seasonal * Math.sin((2 * Math.PI * secOfDay) / 86400);
    let V = o.V0 * Math.exp(o.sigmaV * g - (o.sigmaV * o.sigmaV) / 2) * season;
    let q = Math.max(-o.qMax, Math.min(o.qMax, o.sq * x));
    let priceFlowCoef = o.rho0; // peso do fluxo no retorno
    let noiseCoef = Math.sqrt(1 - o.rho0 * o.rho0);
    let drift = 0;
    const k = epAt[i];
    if (k >= 0) {
      const ep = o.episodes[k];
      const s = ep.side >= 0 ? 1 : -1;
      if (ep.type === 'absorption') {
        // fluxo forte e persistente; preço plano (λ≈0, só ruído pequeno)
        const strength = ep.strength ?? 0.4;
        q = s * strength + 0.03 * gaussian(rng);
        q = Math.max(-o.qMax, Math.min(o.qMax, q));
        priceFlowCoef = 0;
        noiseCoef = ep.noise ?? 0.5;
      } else if (ep.type === 'pwf') {
        // deriva no ruído do preço, fluxo ≈ 0
        const strength = ep.strength ?? 1.2; // deriva em σr por barra
        q = 0.02 * gaussian(rng);
        priceFlowCoef = 0;
        noiseCoef = ep.noise ?? 0.5;
        drift = s * strength;
      } else {
        throw new Error(`tipo de episódio desconhecido: ${ep.type}`);
      }
    }
    if (o.zeroVolProb > 0 && uZero < o.zeroVolProb) V = 0;
    const inBlock = o.noIntrabarsBlocks.some(([s0, len]) => i >= s0 && i < s0 + len);
    const noIntra = i < o.noIntrabarsHead || (o.noIntrabarsProb > 0 && uNoIntra < o.noIntrabarsProb) || inBlock;
    const code = noIntra ? NO_INTRABARS : encodeQ(q);
    const qHat = noIntra ? encodeless(q) : decodeQ(code);
    const delta = V * qHat; // delta verdadeiro (quantizado como o stub o vê)
    const r = o.sigmaR * (priceFlowCoef * (delta / sigmaDeltaNominal) + noiseCoef * e + drift);
    const open = price;
    const close = open * Math.exp(r / 1e4);
    const wick = (o.sigmaR * 0.3) / 1e4;
    const high = Math.max(open, close) * Math.exp(wick * hNoise);
    const low = Math.min(open, close) * Math.exp(-wick * lNoise);
    bars.push({
      openTime: t0 + code,
      closeTime: t0 + barMs - 1,
      open, high, low, close, volume: V,
      code,
      delta: noIntra ? NaN : delta,
      deltaTrue: delta, // delta do modelo mesmo quando a barra "não tem intrabars"
      q: qHat,
      buyFrac: (1 + qHat) / 2,
      r,
      episode: k,
    });
    price = close;
  }
  if (o.gaps) applyGaps(bars, o.gaps);
  return { bars, meta: { ...o, sigmaDeltaNominal } };
}

/** Saltos de abertura (METODOLOGIA §3.1): factor acumulado aplicado à barra do salto e a todas as seguintes. */
function applyGaps(bars, { seed = 9, jumpProb = 0.01, jumpMin = 60, jumpMax = 120, daySd = 3, after = 200 } = {}) {
  const rng = mulberry32(seed);
  const dayKey = (ms) => Math.floor(ms / 86400000);
  let mult = 1, nJump = 0, nDay = 0;
  for (let i = 0; i < bars.length; i++) {
    let g = 0;
    if (i > after && rng() < jumpProb) { g = ((rng() < 0.5 ? -1 : 1) * (jumpMin + (jumpMax - jumpMin) * rng())) / 1e4; nJump++; }
    else if (i > 0 && dayKey(bars[i].openTime) !== dayKey(bars[i - 1].openTime)) { g = (daySd * gaussian(rng)) / 1e4; nDay++; }
    mult *= Math.exp(g);
    const b = bars[i];
    b.open *= mult; b.high *= mult; b.low *= mult; b.close *= mult;
    b.high = Math.max(b.high, b.open, b.close); b.low = Math.min(b.low, b.open, b.close);
    b.gap = g;
  }
  bars.gapStats = { nJump, nDay };
}

// q quantizado mesmo sem canal (para deltaTrue de barras sem intrabars)
function encodeless(q) {
  return decodeQ(encodeQ(q));
}

/**
 * Coloca nEp episódios espaçados regularmente a partir de firstStart, alternando lados se pedido.
 */
export function scheduleEpisodes({ type, count, firstStart, spacing, lenMin = 20, lenMax = 40, sides = [1], strength, noise, seed = 99 }) {
  const rng = mulberry32(seed);
  const eps = [];
  for (let k = 0; k < count; k++) {
    const len = lenMin + Math.floor(rng() * (lenMax - lenMin + 1));
    eps.push({ type, start: firstStart + k * spacing, len, side: sides[k % sides.length], strength, noise });
  }
  return eps;
}

/** Correlação de Pearson ignorando pares não finitos. */
export function pearson(a, b) {
  let n = 0, sa = 0, sb = 0, saa = 0, sbb = 0, sab = 0;
  for (let i = 0; i < a.length; i++) {
    const x = a[i], y = b[i];
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    n++; sa += x; sb += y; saa += x * x; sbb += y * y; sab += x * y;
  }
  if (n < 3) return NaN;
  const cov = sab / n - (sa / n) * (sb / n);
  const va = saa / n - (sa / n) ** 2;
  const vb = sbb / n - (sb / n) ** 2;
  return cov / Math.sqrt(va * vb);
}

/** Barras no formato Kline que o PineTS espera (sem os campos extra). */
export function toKlines(bars) {
  return bars.map((b) => ({
    openTime: b.openTime, closeTime: b.closeTime,
    open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume,
  }));
}
