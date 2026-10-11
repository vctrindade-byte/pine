// T1 build --check, T2 parse pynescript, T3 verificações estáticas das edições.

import { spawnSync, spawn } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { createHash } from 'node:crypto';
import { REPO, TARGETS, targetPath } from './harness.mjs';
import { codeOnly, findLtfLine, stripComment } from './preprocess.mjs';

const shortPath = (p) => (p.startsWith(REPO + '/') ? p.slice(REPO.length + 1) : p);

/** Procura um Python com pynescript: $PINE_PYTHON, .venv/bin/python do repo, python3, python. */
export function findPynescriptPython() {
  const cands = [process.env.PINE_PYTHON, resolve(REPO, '.venv/bin/python'), 'python3', 'python'].filter(Boolean);
  const tried = [];
  for (const py of cands) {
    if (py.includes('/') && !existsSync(py)) { tried.push(`${py} (não existe)`); continue; }
    const r = spawnSync(py, ['-I', '-c', 'import pynescript, importlib.metadata as m; print(m.version("pynescript"))'], { encoding: 'utf8' });
    if (r.status === 0) return { python: py, version: r.stdout.trim(), tried };
    tried.push(`${py} (${r.error ? r.error.code : 'sem pynescript'})`);
  }
  return { python: null, version: null, tried };
}

export function t1Build(tc, { targetKeys }) {
  if (targetKeys.length === 1 && targetKeys[0] === 'standin') { tc.skip('N/A para o stand-in', 'T1 só se aplica às edições geradas por tools/build.py'); return; }
  const build = resolve(REPO, 'tools/build.py');
  const src = resolve(REPO, 'src/price_cvd_normalizer.src.pine');
  if (!tc.check(existsSync(src), 'fonte src/price_cvd_normalizer.src.pine existe', existsSync(src) ? '' : 'em falta — o indicador ainda não foi escrito?')) return;
  if (!tc.check(existsSync(build), 'tools/build.py existe', existsSync(build) ? '' : 'em falta')) return;
  const r = spawnSync('python3', [build, '--check'], { cwd: REPO, encoding: 'utf8' });
  if (r.error) { tc.fail('python3 tools/build.py --check', `não executou: ${r.error.code}`); return; }
  tc.check(r.status === 0, 'python3 tools/build.py --check sai com 0', `exit ${r.status}${(r.stdout + r.stderr).trim() ? ' — ' + (r.stdout + r.stderr).trim().split('\n').slice(-3).join(' | ') : ''}`);
}

// Um só processo Python para todos os ficheiros: o pynescript (ANTLR, runtime Python) gasta ~50 s a aquecer
// a cache DFA no primeiro parse; os seguintes no mesmo processo levam ~1–2 s.
const PARSE_PY = `
import sys, json, time, traceback
from pynescript.ast import parse
out = []
for p in sys.argv[1:]:
    t = time.time()
    try:
        parse(open(p, encoding="utf-8").read())
        out.append({"file": p, "ok": True, "s": round(time.time() - t, 2)})
    except Exception as e:
        msg = "".join(traceback.format_exception_only(type(e), e)).strip().splitlines()
        out.append({"file": p, "ok": False, "s": round(time.time() - t, 2), "error": " | ".join(msg[-4:])})
print("__RESULT__" + json.dumps(out))
`;

export async function t2Parse(tc, { targetKeys, noCache = false }) {
  const { python, version, tried } = findPynescriptPython();
  if (!python) { tc.warn('pynescript indisponível — T2 ignorado', `tentativas: ${tried.join('; ')}. Instale com: pip install -r requirements-dev.txt ou defina PINE_PYTHON`); return; }
  tc.note(`python: ${python} · pynescript ${version}`);
  if (version !== '0.3.0') tc.warn('versão do pynescript', `${version} (fixada: 0.3.0)`);
  const cachePath = resolve(REPO, 'tests/out/parse-cache.json');
  let cache = {};
  if (!noCache && existsSync(cachePath)) { try { cache = JSON.parse(readFileSync(cachePath, 'utf8')); } catch { cache = {}; } }
  const todo = [];
  const hashes = {};
  for (const k of targetKeys) {
    const p = targetPath(k);
    if (!existsSync(p)) { tc.fail(`parse ${shortPath(p)}`, 'ficheiro em falta'); continue; }
    const h = createHash('sha256').update(readFileSync(p)).update('pynescript ' + version).digest('hex');
    hashes[p] = h;
    if (cache[p] === h) { tc.pass(`pynescript parse ${TARGETS[k].file}`, 'em cache (ficheiro inalterado)'); continue; }
    todo.push([k, p]);
  }
  if (!todo.length) return;
  tc.note(`a analisar ${todo.length} ficheiro(s) num só processo (o 1.º parse aquece a cache do ANTLR: ~1 min)`);
  // assíncrono: não bloqueia o ciclo de eventos (os workers do PineTS continuam a correr em paralelo)
  const r = await new Promise((res) => {
    const ch = spawn(python, ['-I', '-c', PARSE_PY, ...todo.map(([, p]) => p)]);
    let stdout = '', stderr = '';
    ch.stdout.on('data', (b) => { stdout += b; });
    ch.stderr.on('data', (b) => { stderr += b; });
    ch.on('error', (e) => res({ status: -1, stdout, stderr: String(e) }));
    ch.on('close', (status) => res({ status, stdout, stderr }));
  });
  const line = (r.stdout || '').split('\n').find((l) => l.startsWith('__RESULT__'));
  if (!line) { tc.fail('pynescript executou', `exit ${r.status}: ${(r.stderr || '').trim().split('\n').slice(-3).join(' | ')}`); return; }
  for (const res of JSON.parse(line.slice('__RESULT__'.length))) {
    const k = todo.find(([, p]) => p === res.file)[0];
    if (tc.check(res.ok, `pynescript parse ${TARGETS[k].file}`, res.ok ? `${res.s} s` : res.error)) cache[res.file] = hashes[res.file];
    else delete cache[res.file];
  }
  try { mkdirSync(dirname(cachePath), { recursive: true }); writeFileSync(cachePath, JSON.stringify(cache, null, 1)); } catch { /* cache é opcional */ }
}

export function t3Static(tc, { targetKeys }) {
  const std = targetPath('std'), fp = targetPath('fp');
  const real = targetKeys.filter((k) => k !== 'standin');
  if (!real.length) {
    tc.skip('edições reais não seleccionadas', 'verificações estáticas do stand-in apenas');
  }
  if (real.includes('std')) {
    if (tc.check(existsSync(std), `${shortPath(std)} existe`, existsSync(std) ? '' : 'em falta')) {
      const src = readFileSync(std, 'utf8');
      const code = codeOnly(src);
      const hits = code.split('\n').map((l, i) => [i + 1, l]).filter(([, l]) => /footprint/i.test(l));
      tc.check(hits.length === 0, 'Standard: nenhuma ocorrência de "footprint" em código (fora de comentários/strings)',
        hits.length ? hits.slice(0, 5).map(([n, l]) => `L${n}: ${l.trim().slice(0, 80)}`).join(' | ') : '');
      tc.check(!/request\.footprint/.test(code), 'Standard: sem request.footprint()');
      // Texto visível ao utilizador (strings: dicas, rótulos, tabela, alertas): a Standard não fala de footprint.
      const txtHits = src.split('\n').map((l, i) => [i + 1, stripComment(l)]).filter(([, l]) => /footprint/i.test(l));
      tc.check(txtHits.length === 0, 'Standard: nenhum texto visível (strings fora de comentários) menciona "footprint"',
        txtHits.length ? txtHits.slice(0, 5).map(([n, l]) => `L${n}: ${l.trim().slice(0, 80)}`).join(' | ') : '');
      commonChecks(tc, 'Standard', src, code);
      tc.check(/indicator\s*\(\s*"Preço × CVD Normalizado \[Order Flow\]"/.test(src), 'Standard: título do indicator() conforme o README (Edições)', '', 'warn');
    }
  }
  if (real.includes('fp')) {
    if (tc.check(existsSync(fp), `${shortPath(fp)} existe`, existsSync(fp) ? '' : 'em falta')) {
      const src = readFileSync(fp, 'utf8');
      const code = codeOnly(src);
      const n = (code.match(/request\.footprint\s*\(/g) || []).length;
      tc.check(n === 1, 'Footprint: exactamente 1 chamada request.footprint()', `${n} encontradas`);
      commonChecks(tc, 'Footprint', src, code);
      tc.check(/indicator\s*\(\s*"Preço × CVD Normalizado \[Order Flow · Footprint\]"/.test(src), 'Footprint: título do indicator() conforme o README (Edições)', '', 'warn');
    }
  }
  if (targetKeys.includes('standin')) {
    const src = readFileSync(targetPath('standin'), 'utf8');
    commonChecks(tc, 'stand-in', src, codeOnly(src), { banner: false });
  }
}

function commonChecks(tc, label, src, code, { banner = true } = {}) {
  const lines = src.split('\n');
  tc.check(lines[0].trim() === '//@version=6', `${label}: linha 1 é //@version=6`, lines[0].slice(0, 40));
  if (banner) tc.check(/GERADO por tools\/build\.py/.test(lines[1] || ''), `${label}: banner "GERADO por tools/build.py" na linha 2`, (lines[1] || '').slice(0, 80));
  try {
    const { index } = findLtfLine(src);
    tc.pass(`${label}: linha LTF única "[aCand, aBvc, aVol] = request.security_lower_tf(" numa só linha física`, `L${index + 1}`);
  } catch (e) { tc.fail(`${label}: linha LTF única (necessária para o stub do harness; tests/README.md)`, e.message); }
  const tags = lines.filter((l) => /\/\/\s*@(fp|std)\s*$/.test(l));
  if (banner) tc.check(tags.length === 0, `${label}: sem etiquetas // @fp / // @std remanescentes`, tags.length ? `${tags.length} linhas` : '');
  const n = (code.match(/\bindicator\s*\(/g) || []).length;
  tc.check(n === 1, `${label}: exactamente 1 indicator()`, `${n}`);
}
