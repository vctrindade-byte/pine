// Sonda de built-ins: lista os "namespace.membro" e as funções globais que o script usa e verifica se o
// PineTS 0.11.0 os implementa (para distinguir limitações do runtime de erros do indicador).

import { codeOnly } from './preprocess.mjs';
import { loadPineTS } from './pinets.mjs';

const NAMESPACES = ['ta', 'math', 'str', 'request', 'timeframe', 'session', 'syminfo', 'barstate', 'label', 'line', 'table',
  'color', 'input', 'chart', 'footprint', 'runtime', 'display', 'position', 'size', 'yloc', 'xloc', 'format', 'plot', 'alert',
  'array', 'shape', 'location', 'text', 'extend', 'font', 'hline', 'dayofweek', 'box', 'linefill', 'polyline', 'map', 'matrix',
  'volume_row', 'currency', 'barmerge', 'order', 'scale', 'adjustment', 'log', 'ticker'];
const GLOBAL_FUNCS = ['plot', 'plotshape', 'plotchar', 'plotarrow', 'plotcandle', 'plotbar', 'fill', 'hline', 'bgcolor', 'barcolor',
  'alertcondition', 'alert', 'nz', 'na', 'fixnan', 'indicator', 'max_bars_back', 'timestamp'];

export function usedBuiltins(src) {
  const code = codeOnly(src);
  const used = new Set();
  const re = new RegExp(`(?<![\\w.])(${NAMESPACES.join('|')})\\.([A-Za-z_]\\w*)`, 'g');
  let m;
  while ((m = re.exec(code))) used.add(`${m[1]}.${m[2]}`);
  for (const f of GLOBAL_FUNCS) if (new RegExp(`(?<![\\w.])${f}\\s*\\(`).test(code)) used.add(`${f}()`);
  return [...used].sort();
}

/** Devolve { used, missing } verificando contra o objecto `pine` de um contexto PineTS. */
export async function probeBuiltins(src, ctxPine = null) {
  let P = ctxPine;
  if (!P) {
    const { PineTS, Indicator } = await loadPineTS();
    const bars = [];
    let t = Date.UTC(2025, 0, 6);
    for (let i = 0; i < 3; i++) { bars.push({ open: 1, high: 2, low: 0.5, close: 1.5, volume: 1, openTime: t, closeTime: t + 299999 }); t += 300000; }
    const provider = { async getMarketData() { return bars; }, async getSymbolInfo() { return { ticker: 'T', tickerid: 'X:T', timezone: 'UTC', mintick: 0.01, volumetype: 'base' }; }, configure() {} };
    const pine = new PineTS(provider, 'X:T', '5', 3);
    const ctx = await pine.run(new Indicator('//@version=6\nindicator("probe")\nplot(close)'));
    P = ctx.pine;
  }
  const used = usedBuiltins(src);
  const missing = [];
  for (const u of used) {
    if (u.endsWith('()')) { if (!(u.slice(0, -2) in P)) missing.push(u); continue; }
    const [ns, mem] = u.split('.');
    const obj = P[ns];
    if (obj === undefined || obj === null) { missing.push(u); continue; }
    if (ns === 'syminfo') continue; // syminfo.* vem do provider (getSymbolInfo); ver DEFAULT_SYMINFO
    let has = false;
    try { has = mem in obj; } catch { has = false; }
    if (!has) missing.push(u);
  }
  return { used, missing };
}
