// Utilitários numéricos dos testes.

export const isF = Number.isFinite;

export function finiteFrac(arr, from = 0, to = arr.length) {
  let n = 0, f = 0;
  for (let i = Math.max(0, from); i < Math.min(arr.length, to); i++) { n++; if (isF(arr[i])) f++; }
  return n ? f / n : NaN;
}

/** Fracção de |x| ≥ thr entre os valores finitos (e opcionalmente onde mask[i] é verdadeiro). */
export function exceedFrac(arr, thr, { from = 0, mask = null } = {}) {
  let n = 0, e = 0;
  for (let i = from; i < arr.length; i++) {
    if (!isF(arr[i]) || (mask && !mask[i])) continue;
    n++; if (Math.abs(arr[i]) >= thr) e++;
  }
  return { n, frac: n ? e / n : NaN, count: e };
}

export function meanSd(arr, from = 0) {
  let n = 0, s = 0, s2 = 0;
  for (let i = from; i < arr.length; i++) if (isF(arr[i])) { n++; s += arr[i]; s2 += arr[i] * arr[i]; }
  const m = s / n;
  return { n, mean: m, sd: Math.sqrt(Math.max(0, s2 / n - m * m)) };
}

export function pearsonArr(a, b, from = 0) {
  let n = 0, sa = 0, sb = 0, saa = 0, sbb = 0, sab = 0;
  for (let i = from; i < Math.min(a.length, b.length); i++) {
    const x = a[i], y = b[i];
    if (!isF(x) || !isF(y)) continue;
    n++; sa += x; sb += y; saa += x * x; sbb += y * y; sab += x * y;
  }
  if (n < 3) return { n, r: NaN };
  const cov = sab / n - (sa / n) * (sb / n);
  return { n, r: cov / Math.sqrt((saa / n - (sa / n) ** 2) * (sbb / n - (sb / n) ** 2)) };
}

/** Erro relativo com piso absoluto: |a−b| / max(|b|, floor). */
export function relErr(a, b, floor = 1e-12) {
  if (!isF(a) || !isF(b)) return Infinity;
  return Math.abs(a - b) / Math.max(Math.abs(b), floor);
}

export function quantile(arr, q) {
  const v = Array.from(arr).filter(isF).sort((x, y) => x - y);
  if (!v.length) return NaN;
  const pos = (v.length - 1) * q, lo = Math.floor(pos), hi = Math.ceil(pos);
  return v[lo] + (v[hi] - v[lo]) * (pos - lo);
}

/** Resumo de erros: { n, maxErr, worstIdx, nBad }. */
export function compareSeries(idxs, getA, getB, tol, floor = 1e-12) {
  let n = 0, maxErr = 0, worstIdx = -1, nBad = 0;
  for (const i of idxs) {
    const a = getA(i), b = getB(i);
    const e = relErr(a, b, floor);
    n++;
    if (e > maxErr) { maxErr = e; worstIdx = i; }
    if (!(e <= tol)) nBad++;
  }
  return { n, maxErr, worstIdx, nBad };
}

export function range(a, b) { const out = []; for (let i = a; i < b; i++) out.push(i); return out; }
