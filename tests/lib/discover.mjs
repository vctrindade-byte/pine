// Descoberta de títulos de plots a partir do código Pine (regex + emparelhamento de parênteses), para não
// fixar os títulos PT no harness. Os papéis (ROLES) mapeiam para listas de regex candidatas; quando vários
// títulos casam, o harness escolhe em tempo de execução o que tiver mais valores finitos.

import { stripComment } from './preprocess.mjs';
import { getPlot } from './pinets.mjs';

/** Extrai todas as chamadas plot(...) (inclui plotshape/plotchar? não — só plot) com título e display. */
export function parsePlotCalls(src) {
  const code = src.split('\n').map(stripComment).join('\n');
  const out = [];
  const re = /(^|[^\w.])plot\s*\(/g;
  let m;
  while ((m = re.exec(code))) {
    const start = m.index + m[0].length; // após "("
    const args = readArgs(code, start);
    if (!args) continue;
    const parts = splitTopLevel(args.text);
    let title = null;
    for (const p of parts) {
      const kw = p.match(/^\s*title\s*=\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')\s*$/s);
      if (kw) { title = unquote(kw[1]); break; }
    }
    if (title === null && parts.length > 1) {
      const pos = parts[1].trim();
      if (/^("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')$/s.test(pos)) title = unquote(pos);
    }
    const display = (parts.find((p) => /^\s*display\s*=/.test(p)) || '').replace(/^\s*display\s*=\s*/, '').trim() || null;
    const line = code.slice(0, m.index).split('\n').length;
    out.push({ title, display, line, expr: (parts[0] || '').trim() });
    re.lastIndex = args.end;
  }
  return out;
}

function readArgs(code, start) {
  let depth = 1, inStr = null;
  for (let i = start; i < code.length; i++) {
    const c = code[i];
    if (inStr) { if (c === '\\') { i++; continue; } if (c === inStr) inStr = null; continue; }
    if (c === '"' || c === "'") { inStr = c; continue; }
    if (c === '(' || c === '[') depth++;
    else if (c === ')' || c === ']') { depth--; if (depth === 0) return { text: code.slice(start, i), end: i + 1 }; }
  }
  return null;
}

function splitTopLevel(s) {
  const parts = [];
  let depth = 0, inStr = null, cur = '';
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (inStr) { cur += c; if (c === '\\') { cur += s[++i] ?? ''; continue; } if (c === inStr) inStr = null; continue; }
    if (c === '"' || c === "'") { inStr = c; cur += c; continue; }
    if (c === '(' || c === '[') depth++;
    if (c === ')' || c === ']') depth--;
    if (c === ',' && depth === 0) { parts.push(cur); cur = ''; continue; }
    cur += c;
  }
  if (cur.trim()) parts.push(cur);
  return parts;
}

function unquote(q) {
  return q.slice(1, -1).replace(/\\(.)/g, '$1');
}

/** Papéis → regex candidatas, por ordem de preferência. */
export const ROLES = {
  pLine: [/^preço \(normalizado\)$/i, /^preço\b.*normaliz/i, /^linha (de )?preço/i, /^preço$/i],
  fLine: [/^cvd \(normalizado\)$/i, /^cvd\b.*normaliz/i, /^linha (de )?(cvd|fluxo)/i, /^cvd$/i],
  zMain: [/^z divergência$/i, /^z\b.*diverg/i],
  z: [/^z$/i, /^z\s*\((?!.*\b(zf|zp)\b)/i, /^z\b(?!.*diverg)(?!f)(?!p)/i, /^z divergência$/i],
  delta: [/^delta$/i, /^delta\b(?!.*cvd)/i, /^Δ$/, /^delta/i],
  cvdA: [/cvd ancorado/i, /cvd.*âncora/i],
  sr: [/^σ\s*r\b/i, /^σr/i, /σ\s*r\b/i, /sigma.?r/i],
  sd: [/^σ\s*Δ/i, /^σΔ/i, /σ\s*delta/i, /^σ\s*d\b/i],
  rho: [/^ρ/i, /^rho\b/i],
  lamOls: [/λ\s*ols/i],
  pLeg: [/perna.*pre[çc]o/i, /^p\s*leg/i],
  fLeg: [/perna.*fluxo/i, /^f\s*leg/i],
  zF: [/^zF\b/],
  zP: [/^zP\b/],
  tier: [/^tier\b/i, /qualidade|tier/i],
  intrabars: [/intrabar/i],
  gate: [/^gate\b/i],
  eta: [/^η/i, /efici[eê]ncia/i],
};

/** Mapeia papéis → lista de títulos candidatos (por ordem) presentes no código. */
export function discoverRoles(src) {
  const calls = parsePlotCalls(src).filter((c) => c.title);
  const titles = [...new Set(calls.map((c) => c.title))];
  const roles = {};
  for (const [role, res] of Object.entries(ROLES)) {
    const cands = [];
    for (const re of res) for (const t of titles) if (re.test(t) && !cands.includes(t)) cands.push(t);
    // zF/zP nunca contam como Z
    roles[role] = role === 'z' ? cands.filter((t) => !/^z[FP]\b/.test(t)) : cands;
  }
  return { calls, titles, roles };
}

/**
 * Escolhe a série de um papel num resultado de execução: o candidato com mais valores finitos
 * (desempate pela ordem de preferência). Devolve { title, values } ou null.
 */
export function pickRole(run, roles, role, { from = 0 } = {}) {
  const cands = roles[role] || [];
  let best = null;
  for (const t of cands) {
    const v = getPlot(run, t);
    if (!v) continue;
    let n = 0;
    for (let i = from; i < v.length; i++) if (Number.isFinite(v[i])) n++;
    if (!best || n > best.n) best = { title: t, values: v, n };
  }
  return best;
}
