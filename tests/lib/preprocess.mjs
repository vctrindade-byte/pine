// Pré-processamento textual do script Pine ANTES de o entregar ao PineTS. O ficheiro do indicador nunca é
// alterado em disco: o harness trabalha sobre uma cópia em memória.
//
// 1) Stub LTF: a linha única do pedido intrabar (ver tests/README.md, «Stub do request.security_lower_tf»)
//        [aCand, aBvc, aVol] = request.security_lower_tf(syminfo.tickerid, ltf, ltfSigned(100), ignore_invalid_timeframe = true)
//    passa a
//        [aCand, aBvc, aVol] = __ltfStub()
//    e a função __ltfStub() (ver channel.mjs) é inserida imediatamente antes dessa linha.
// 2) Shims: substituições textuais para built-ins que o PineTS 0.11.0 não implementa (lista em SHIMS;
//    documentada em tests/README.md). Cada shim só se aplica se o padrão existir no script.

import { stubPineSource, STUB_FN_NAME } from './channel.mjs';

export const LTF_LINE_RE = /^(\s*)\[\s*aCand\s*,\s*aBvc\s*,\s*aVol\s*\]\s*=\s*request\.security_lower_tf\(/;

/** Localiza a linha LTF. Lança erro se não houver exactamente uma, ou se não for uma única linha física. */
export function findLtfLine(src) {
  const lines = src.split('\n');
  const hits = [];
  lines.forEach((l, i) => { if (LTF_LINE_RE.test(l)) hits.push(i); });
  if (hits.length !== 1) {
    throw new Error(`esperava exactamente 1 linha "[aCand, aBvc, aVol] = request.security_lower_tf(", encontrei ${hits.length}`);
  }
  const idx = hits[0];
  const line = lines[idx];
  const m = line.match(LTF_LINE_RE);
  if (m[1].length > 0) throw new Error(`a linha LTF (linha ${idx + 1}) está indentada — tem de estar no âmbito global`);
  const code = stripComment(line);
  if (parenBalance(code) !== 0) throw new Error(`a linha LTF (linha ${idx + 1}) não fecha os parênteses na mesma linha física`);
  const total = (src.match(/request\.security_lower_tf\s*\(/g) || []).length;
  if (total !== 1) throw new Error(`request.security_lower_tf aparece ${total} vezes (exige-se exactamente 1 local de chamada)`);
  return { index: idx, line };
}

/** Substitui o lado direito da linha LTF pela chamada ao stub e insere a função do stub antes dela. */
export function injectLtfStub(src) {
  if (new RegExp(`\\b${STUB_FN_NAME}\\b`).test(src)) throw new Error(`${STUB_FN_NAME} já existe no script`);
  const { index, line } = findLtfLine(src);
  const lines = src.split('\n');
  const comment = commentPart(line);
  lines[index] = `[aCand, aBvc, aVol] = ${STUB_FN_NAME}()` + (comment ? '  ' + comment : '');
  lines.splice(index, 0, stubPineSource());
  return lines.join('\n');
}

// Remove um comentário // fora de strings.
export function stripComment(line) {
  let inStr = null;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (inStr) { if (c === '\\') { i++; continue; } if (c === inStr) inStr = null; continue; }
    if (c === '"' || c === "'") { inStr = c; continue; }
    if (c === '/' && line[i + 1] === '/') return line.slice(0, i);
  }
  return line;
}

/**
 * Só código: remove comentários // e esvazia o conteúdo dos literais de string (mantém as aspas),
 * para que buscas por padrões (ex.: "footprint") não contem texto de comentários/strings.
 */
export function codeOnly(src) {
  const out = [];
  for (const line of src.split('\n')) {
    let res = '', inStr = null;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (inStr) { if (c === '\\') { i++; continue; } if (c === inStr) { inStr = null; res += c; } continue; }
      if (c === '"' || c === "'") { inStr = c; res += c; continue; }
      if (c === '/' && line[i + 1] === '/') break;
      res += c;
    }
    out.push(res);
  }
  return out.join('\n');
}

function commentPart(line) {
  const code = stripComment(line);
  return line.slice(code.length).trim();
}

function parenBalance(code) {
  let bal = 0, inStr = null;
  for (let i = 0; i < code.length; i++) {
    const c = code[i];
    if (inStr) { if (c === '\\') { i++; continue; } if (c === inStr) inStr = null; continue; }
    if (c === '"' || c === "'") { inStr = c; continue; }
    if (c === '(') bal++; else if (c === ')') bal--;
  }
  return bal;
}

/**
 * Shims textuais. Cada entrada: { id, why, test: RegExp, apply(src) }.
 * Mantidos ao mínimo; o PineTS 0.11.0 já suporta os built-ins do indicador que foram sondados
 * (ver tests/lib/builtins.mjs e o teste T0). Um shim novo só deve ser adicionado quando a sonda
 * mostrar que o PineTS não implementa um built-in que o indicador usa.
 */
export const SHIMS = [
  {
    id: 'runtime.error→harness',
    why: 'runtime.error() aborta a execução inteira no PineTS; o harness transforma-o num plot de sinalização ' +
      '"__harness_runtime_error" para que os testes reportem o erro em vez de rebentar sem contexto.',
    test: /\bruntime\.error\s*\(/,
    apply(src) {
      // Mantém a semântica (o erro é registado) mas sem lançar excepção: substitui por uma atribuição a uma var.
      let out = src.replace(/\bruntime\.error\s*\(/g, '__harnessRtErr(');
      const fn = [
        '// [harness] shim de runtime.error(): regista a mensagem em vez de abortar',
        'var string __harnessRtMsg = ""',
        '__harnessRtErr(string msg) =>',
        '    __harnessRtMsg := msg',
        '    0',
      ].join('\n');
      return insertAfterDeclaration(out, fn) + '\nplot(str.length(__harnessRtMsg) > 0 ? 1 : 0, "__harness_runtime_error", display = display.data_window)\n';
    },
    enabled: false, // desligado por omissão: só com --shim-runtime-error (o comportamento real é abortar)
  },
];

/** Insere texto imediatamente depois da declaração indicator(...) (que pode ocupar várias linhas). */
export function insertAfterDeclaration(src, text) {
  const lines = src.split('\n');
  let i = lines.findIndex((l) => /^\s*indicator\s*\(/.test(l));
  if (i < 0) throw new Error('declaração indicator( não encontrada');
  let bal = parenBalance(stripComment(lines[i]));
  while (bal > 0 && i + 1 < lines.length) { i++; bal += parenBalance(stripComment(lines[i])); }
  lines.splice(i + 1, 0, text);
  return lines.join('\n');
}

/**
 * Prepara o código: stub LTF (se stub=true) + shims activos. Devolve { code, applied: [ids] }.
 */
export function preprocess(src, { stub = true, shims = [] } = {}) {
  let code = src.replace(/\r\n/g, '\n');
  const applied = [];
  if (stub) { code = injectLtfStub(code); applied.push('ltf-stub'); }
  for (const s of SHIMS) {
    const on = s.enabled || shims.includes(s.id);
    if (on && s.test.test(code)) { code = s.apply(code); applied.push(s.id); }
  }
  return { code, applied };
}
