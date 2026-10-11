// Registo e impressão dos resultados. Estados: PASS, FAIL, WARN (não falha a suite), SKIP (não aplicável /
// dependência em falta). Código de saída ≠ 0 se houver pelo menos um FAIL.

export const STATUS = Object.freeze({ PASS: 'PASS', FAIL: 'FAIL', WARN: 'WARN', SKIP: 'SKIP' });
const ORDER = { FAIL: 3, WARN: 2, PASS: 1, SKIP: 0 };
const useColor = process.stdout.isTTY && !process.env.NO_COLOR;
const C = { PASS: '\x1b[32m', FAIL: '\x1b[31m', WARN: '\x1b[33m', SKIP: '\x1b[90m', dim: '\x1b[2m', reset: '\x1b[0m' };
const paint = (s, c) => (useColor ? C[c] + s + C.reset : s);

export class TestCase {
  constructor(id, name) {
    this.id = id; this.name = name; this.checks = []; this.notes = []; this.t0 = Date.now(); this.ms = 0; this.error = null;
  }
  /** Regista uma verificação. level: 'fail' (por omissão) ou 'warn' quando falha. */
  check(ok, label, detail = '', level = 'fail') {
    const status = ok ? STATUS.PASS : level === 'warn' ? STATUS.WARN : STATUS.FAIL;
    this.checks.push({ status, label, detail });
    return ok;
  }
  pass(label, detail = '') { return this.check(true, label, detail); }
  fail(label, detail = '') { return this.check(false, label, detail); }
  warn(label, detail = '') { this.checks.push({ status: STATUS.WARN, label, detail }); }
  skip(label, detail = '') { this.checks.push({ status: STATUS.SKIP, label, detail }); }
  note(s) { this.notes.push(s); }
  get status() {
    if (this.error) return STATUS.FAIL;
    if (!this.checks.length) return STATUS.SKIP;
    let best = STATUS.SKIP;
    for (const c of this.checks) if (ORDER[c.status] > ORDER[best]) best = c.status;
    return best;
  }
}

export class Reporter {
  constructor({ verbose = false } = {}) { this.cases = []; this.verbose = verbose; this.t0 = Date.now(); }
  start(id, name) {
    const tc = new TestCase(id, name);
    this.cases.push(tc);
    process.stdout.write(paint(`\n▶ ${id} ${name}\n`, 'dim'));
    return tc;
  }
  end(tc) {
    tc.ms = Date.now() - tc.t0;
    for (const c of tc.checks) {
      if (c.status === STATUS.PASS && !this.verbose) continue;
      process.stdout.write(`   ${paint(c.status.padEnd(4), c.status)} ${c.label}${c.detail ? ' — ' + c.detail : ''}\n`);
    }
    if (tc.error) process.stdout.write(`   ${paint('FAIL', 'FAIL')} excepção: ${tc.error.stack || tc.error}\n`);
    for (const n of tc.notes) process.stdout.write(paint(`   · ${n}\n`, 'dim'));
    const nPass = tc.checks.filter((c) => c.status === STATUS.PASS).length;
    process.stdout.write(`   → ${paint(tc.status, tc.status)} (${nPass}/${tc.checks.length} verificações OK, ${(tc.ms / 1000).toFixed(1)} s)\n`);
  }
  summary() {
    const lines = ['', '═'.repeat(78), 'RESUMO', '═'.repeat(78)];
    for (const tc of this.cases) {
      const nF = tc.checks.filter((c) => c.status === STATUS.FAIL).length + (tc.error ? 1 : 0);
      const nW = tc.checks.filter((c) => c.status === STATUS.WARN).length;
      const extra = [nF ? `${nF} falha(s)` : '', nW ? `${nW} aviso(s)` : ''].filter(Boolean).join(', ');
      lines.push(`${paint(tc.status.padEnd(4), tc.status)}  ${tc.id.padEnd(4)} ${tc.name}${extra ? '  [' + extra + ']' : ''}  (${(tc.ms / 1000).toFixed(1)} s)`);
    }
    const failed = this.cases.filter((tc) => tc.status === STATUS.FAIL).length;
    lines.push('─'.repeat(78));
    lines.push(`tempo total: ${((Date.now() - this.t0) / 1000).toFixed(1)} s (as execuções PineTS correm em paralelo, por isso o tempo por teste é só o de avaliação)`);
    lines.push(failed ? paint(`${failed} teste(s) FALHARAM`, 'FAIL') : paint('Todos os testes executados passaram (WARN/SKIP não falham a suite).', 'PASS'));
    process.stdout.write(lines.join('\n') + '\n');
    return failed;
  }
  toJSON() {
    return this.cases.map((tc) => ({ id: tc.id, name: tc.name, status: tc.status, ms: tc.ms, checks: tc.checks, notes: tc.notes, error: tc.error ? String(tc.error.stack || tc.error) : null }));
  }
}

/** Formatação compacta de números. */
export const fmt = (v, d = 3) => (Number.isFinite(v) ? v.toFixed(d) : String(v));
export const pct = (v, d = 1) => (Number.isFinite(v) ? (100 * v).toFixed(d) + '%' : String(v));
