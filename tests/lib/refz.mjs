// Reimplementação JS de referência de docs/METODOLOGIA.md §3.1 (rBar), §3.3 e §6 (σ, ρ, unidades-σ, D, RMS desfasado,
// Z, gate, pernas) — independente do Pine. Usada no T7/T8 para comparar com a saída do indicador no PineTS.
// Convenções Pine: ta.stdev é o desvio-padrão POPULACIONAL (biased = true); x[1] é o valor da barra anterior;
// ATENÇÃO: aqui as janelas são estritas (NaN se houver um na na janela). No Pine (docs da TradingView e PineTS 0.11.0)
// math.sum/ta.sma/ta.stdev/ta.correlation SALTAM os na (usam os últimos `length` valores não-na). Os resultados só
// coincidem enquanto Δ não tiver na a meio do histórico — é o caso de todos os conjuntos do T8 (o fallback «Nenhum»,
// que produz Δ = na, não é comparado aqui).
// O mesmo algoritmo foi reimplementado em Python, fora do repositório, para a validação com dados reais
// (docs/VALIDACAO.md, secção 3).

// ke = janela dos eventos em barras (METODOLOGIA §7.1; 3 em 5 min); hqNeed por omissão = N + max(K, ke) (+ N com deriva).
export const REF_DEFAULTS = Object.freeze({ N: 100, K: 20, M: 1000, clip: 4.0, rhoMin: 0.30, sigLenBar: 100, warm: null, ke: 3, drift: false, hqNeed: null });

const isF = Number.isFinite;

/** Desvio-padrão populacional numa janela deslizante de n (NaN se houver NaN na janela). */
export function rollingStdPop(x, n) {
  const out = new Float64Array(x.length).fill(NaN);
  for (let t = n - 1; t < x.length; t++) {
    let s = 0, s2 = 0, ok = true;
    for (let j = t - n + 1; j <= t; j++) { const v = x[j]; if (!isF(v)) { ok = false; break; } s += v; }
    if (!ok) continue;
    const m = s / n;
    for (let j = t - n + 1; j <= t; j++) s2 += (x[j] - m) ** 2;
    out[t] = Math.sqrt(s2 / n);
  }
  return out;
}

export function rollingCorr(x, y, n) {
  const out = new Float64Array(x.length).fill(NaN);
  for (let t = n - 1; t < x.length; t++) {
    let sx = 0, sy = 0, ok = true;
    for (let j = t - n + 1; j <= t; j++) { if (!isF(x[j]) || !isF(y[j])) { ok = false; break; } sx += x[j]; sy += y[j]; }
    if (!ok) continue;
    const mx = sx / n, my = sy / n;
    let cxy = 0, cxx = 0, cyy = 0;
    for (let j = t - n + 1; j <= t; j++) { const a = x[j] - mx, b = y[j] - my; cxy += a * b; cxx += a * a; cyy += b * b; }
    out[t] = cxx > 0 && cyy > 0 ? cxy / Math.sqrt(cxx * cyy) : NaN;
  }
  return out;
}

export function rollingSum(x, n) {
  const out = new Float64Array(x.length).fill(NaN);
  for (let t = n - 1; t < x.length; t++) {
    let s = 0, ok = true;
    for (let j = t - n + 1; j <= t; j++) { if (!isF(x[j])) { ok = false; break; } s += x[j]; }
    if (ok) out[t] = s;
  }
  return out;
}

export function lag1(x) {
  const out = new Float64Array(x.length).fill(NaN);
  for (let t = 1; t < x.length; t++) out[t] = x[t - 1];
  return out;
}

const clipv = (v, c) => Math.max(-c, Math.min(c, v));

/**
 * RMS não-centrado dos valores ANTERIORES (METODOLOGIA §6.3; dossier §7.3: "previous m non-na values"):
 * cnt = nº de valores válidos anteriores; cnt > m → RMS dos últimos m valores VÁLIDOS (os na são saltados,
 * como no ta.sma do Pine); cnt ≥ warm → média expansiva; senão NaN. Sem lacunas em x é idêntico a usar as
 * últimas m barras; depois de uma lacuna (tier ≤ 1 a meio do histórico) o Z volta logo que hqOk volta.
 */
export function rmsLag(x, m, warm) {
  const out = new Float64Array(x.length).fill(NaN);
  const sq = [];
  let cum = 0, cnt = 0;
  for (let t = 0; t < x.length; t++) {
    if (cnt > m) {
      let s = 0;
      for (let j = sq.length - m; j < sq.length; j++) s += sq[j];
      out[t] = Math.sqrt(s / m);
    } else if (cnt >= warm) {
      out[t] = Math.sqrt(cum / cnt);
    }
    if (isF(x[t])) { const v = x[t] * x[t]; cum += v; cnt++; sq.push(v); }
  }
  return out;
}

/** Chave do dia UTC (session.isfirstbar num símbolo 24x7 UTC). */
export function utcDayKey(ms) { return Math.floor(ms / 86400000); }

/** Chave da semana (segunda-feira 00:00 UTC). */
export function utcWeekKey(ms) { const d = Math.floor(ms / 86400000); return Math.floor((d + 3) / 7); } // 1970-01-01 = quinta

export function utcMonthKey(ms) { const dt = new Date(ms); return dt.getUTCFullYear() * 12 + dt.getUTCMonth(); }

/** rBar (METODOLOGIA §3.1) com guarda de gaps. */
export function computeRBar(open, close, openTime, sigLen = 100) {
  const n = close.length;
  const rRaw = new Float64Array(n).fill(NaN);
  for (let t = 1; t < n; t++) rRaw[t] = 1e4 * Math.log(close[t] / close[t - 1]);
  const sRawP = lag1(rollingStdPop(rRaw, sigLen));
  const rBar = new Float64Array(n);
  for (let t = 0; t < n; t++) {
    const first = t === 0 || utcDayKey(openTime[t]) !== utcDayKey(openTime[t - 1]);
    const gap = first || Math.abs(1e4 * Math.log(open[t] / close[t - 1])) > 3 * (isF(sRawP[t]) ? sRawP[t] : 1e10);
    rBar[t] = gap ? 1e4 * Math.log(close[t] / open[t]) : rRaw[t];
  }
  return rBar;
}

/**
 * Estatísticas de METODOLOGIA §3.3 e §6 a partir de rBar, delta e tier por barra.
 * hqOk: tier ≥ 2 há ≥ hqNeed barras seguidas, hqNeed = N + max(K, ke) (+ N com deriva): as janelas σ/ρ desfasadas
 * de TODOS os termos das somas K e ke ficam inteiras em barras de qualidade ≥ média (METODOLOGIA §6.4).
 * @returns objecto com séries Float64Array: r, d, sr, sd, rho, srP, sdP, rhoP, ur, ud, hqOk, D, rmsD, Z, gate, pLeg, fLeg,
 *          fE, pE, zF, zP (eventos, METODOLOGIA §7.1), lamOls e eta (η, eficiência de impacto)
 */
export function computeRef({ rBar, delta, tier, opts = {} }) {
  const o = { ...REF_DEFAULTS, ...opts };
  const warm = o.warm ?? o.N;
  const n = rBar.length;
  const d = Float64Array.from(delta, (v) => (isF(v) ? v : NaN));
  const r = new Float64Array(n);
  for (let t = 0; t < n; t++) r[t] = isF(d[t]) ? rBar[t] : NaN;
  const sr = rollingStdPop(r, o.N), sd = rollingStdPop(d, o.N), rho = rollingCorr(r, d, o.N);
  const srP = lag1(sr), sdP = lag1(sd), rhoP = lag1(rho);
  const ur = new Float64Array(n).fill(NaN), ud = new Float64Array(n).fill(NaN);
  for (let t = 0; t < n; t++) {
    if (srP[t] > 0 && isF(r[t])) ur[t] = clipv(r[t] / srP[t], o.clip);
    if (sdP[t] > 0 && isF(d[t])) ud[t] = clipv(d[t] / sdP[t], o.clip);
  }
  const hqOk = new Uint8Array(n);
  let run = 0;
  const hqNeed = o.hqNeed ?? (o.N + Math.max(o.K, o.ke) + (o.drift ? o.N : 0));
  for (let t = 0; t < n; t++) { run = tier[t] >= 2 ? run + 1 : 0; hqOk[t] = tier[t] >= 2 && run >= hqNeed ? 1 : 0; }
  const diff = new Float64Array(n);
  for (let t = 0; t < n; t++) diff[t] = ur[t] - ud[t];
  const sumU = rollingSum(diff, o.K), sumP = rollingSum(ur, o.K), sumF = rollingSum(ud, o.K);
  const D = new Float64Array(n).fill(NaN);
  for (let t = 0; t < n; t++) {
    if (!hqOk[t]) continue;
    const rp = isF(rhoP[t]) ? rhoP[t] : 0;
    D[t] = sumU[t] / Math.sqrt(2 * o.K * (1 - Math.min(rp, 0.95)));
  }
  const rmsD = rmsLag(D, o.M, warm);
  const Z = new Float64Array(n).fill(NaN);
  for (let t = 0; t < n; t++) if (rmsD[t] > 0 && isF(D[t])) Z[t] = D[t] / rmsD[t];
  const rhoMin = Math.max(o.rhoMin, Math.tanh(1.96 / Math.sqrt(o.N - 3)));
  const gate = new Uint8Array(n);
  for (let t = 0; t < n; t++) gate[t] = hqOk[t] && isF(rhoP[t]) && rhoP[t] >= rhoMin ? 1 : 0;
  const pLeg = sumP.map((v) => v / Math.sqrt(o.K)), fLeg = sumF.map((v) => v / Math.sqrt(o.K));
  // eventos: F_e = Σ_ke u_d/√ke, P_e = Σ_ke u_r/√ke (só com hqOk), z = valor / RMS desfasado próprio
  const sumFe = rollingSum(ud, o.ke), sumPe = rollingSum(ur, o.ke);
  const fE = new Float64Array(n).fill(NaN), pE = new Float64Array(n).fill(NaN);
  for (let t = 0; t < n; t++) if (hqOk[t]) { fE[t] = sumFe[t] / Math.sqrt(o.ke); pE[t] = sumPe[t] / Math.sqrt(o.ke); }
  const rmsF = rmsLag(fE, o.M, warm), rmsP = rmsLag(pE, o.M, warm);
  const zF = new Float64Array(n).fill(NaN), zP = new Float64Array(n).fill(NaN);
  for (let t = 0; t < n; t++) { if (rmsF[t] > 0 && isF(fE[t])) zF[t] = fE[t] / rmsF[t]; if (rmsP[t] > 0 && isF(pE[t])) zP[t] = pE[t] / rmsP[t]; }
  // λ OLS desfasado (bps por unidade de delta) e eficiência de impacto η = Σ_ke r / (λ_OLS·Σ_ke Δ), só com |F_e| ≥ 1.5
  // (METODOLOGIA §6.9, dossier §6.2: contexto no Data Window/tabela).
  const lamOls = new Float64Array(n).fill(NaN), eta = new Float64Array(n).fill(NaN);
  const sumRKe = rollingSum(r, o.ke), sumDKe = rollingSum(d, o.ke);
  for (let t = 0; t < n; t++) {
    if (sdP[t] > 0 && srP[t] > 0) lamOls[t] = (isF(rhoP[t]) ? rhoP[t] : 0) * srP[t] / sdP[t];
    const sD = isF(sumDKe[t]) ? sumDKe[t] : 0;
    if (isF(fE[t]) && Math.abs(fE[t]) >= 1.5 && isF(lamOls[t]) && lamOls[t] !== 0 && sD !== 0) eta[t] = sumRKe[t] / (lamOls[t] * sD);
  }
  return { r, d, sr, sd, rho, srP, sdP, rhoP, ur, ud, hqOk, D, rmsD, Z, gate, pLeg, fLeg, rhoMin, hqNeed, fE, pE, zF, zP, lamOls, eta };
}

/** Delta do fallback BVC na barra (METODOLOGIA §2.5): nz(volume)·(2Φ(clip(rBar/σ_{t−1}, ±10)) − 1). */
export function computeBarDelta(rBar, volume, sigLen = 100) {
  const sBarP = lag1(rollingStdPop(rBar, sigLen));
  return Float64Array.from(rBar, (rb, t) => {
    const z = sBarP[t] > 0 ? clipv(rb / sBarP[t], 10) : 0;
    const v = isF(volume[t]) ? volume[t] : 0;
    return v * (2 * normCdf(z) - 1);
  });
}

/** Φ por Abramowitz–Stegun 7.1.26 (o mesmo que o indicador usa). */
export function normCdf(z) {
  const x = Math.abs(z) / Math.SQRT2;
  const t = 1 / (1 + 0.3275911 * x);
  const e = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
  return 0.5 * (1 + Math.sign(z) * e);
}

/**
 * Referência de ltfSigned (METODOLOGIA §2.2–2.4) avaliada sub-barra a sub-barra, com estado contínuo (como no contexto
 * intrabar da TradingView): regra da vela com lado transportado (var dir = 1, nunca reiniciado; sem cotações
 * bid/ask) e BVC-Normal por intrabar com σ = desvio-padrão populacional de ΔC em sigLen sub-barras.
 * Devolve somas por barra do gráfico (per sub-barras por barra).
 */
export function refLtfSigned(subs, per, sigLen = 100) {
  const n = Math.floor(subs.length / per);
  const cand = new Float64Array(n), bvc = new Float64Array(n);
  let dir = 1;
  const dps = [];
  subs.slice(0, n * per).forEach((s, i) => {
    const cPrev = i > 0 ? subs[i - 1].close : NaN;
    const pDir = s.close > s.open ? 1 : s.close < s.open ? -1 : s.close > cPrev ? 1 : s.close < cPrev ? -1 : 0;
    dir = pDir !== 0 ? pDir : dir;
    const first = i === 0 || utcDayKey(s.openTime) !== utcDayKey(subs[i - 1].openTime);
    const dp = first || !isF(cPrev) ? s.close - s.open : s.close - cPrev;
    dps.push(dp);
    let sg = NaN;
    if (dps.length >= sigLen) {
      const w = dps.slice(-sigLen);
      const m = w.reduce((a, b) => a + b, 0) / sigLen;
      sg = Math.sqrt(w.reduce((a, b) => a + (b - m) ** 2, 0) / sigLen);
    }
    const z = sg > 0 ? clipv(dp / sg, 10) : 0;
    const k = Math.floor(i / per);
    const v = isF(s.volume) ? s.volume : 0;
    cand[k] += dir * v;
    bvc[k] += v * (2 * normCdf(z) - 1);
  });
  return { cand, bvc };
}
