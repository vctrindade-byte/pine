#!/usr/bin/env node
// Harness de verificação do indicador "Preço × CVD Normalizado [Order Flow]".
// Uso: node tests/run_tests.mjs [--target std|fp|both|standin] [--only T4,T5] [--quick] [--verbose]
//                              [--bars 3000] [--json relatorio.json] [--shim runtime.error→harness] [--no-cache]
// Ver tests/README.md. Sai com código ≠ 0 se algum teste falhar.

import { writeFileSync } from 'node:fs';
import { Reporter } from './lib/report.mjs';
import { Target, TARGETS, setTargetFile, targetPath } from './lib/harness.mjs';
import { t1Build, t2Parse, t3Static } from './lib/tests_static.mjs';
import { t0SelfCheck, t4Matrix, t4Footprint, t5Null, t6Detection, t7Invariants, t8Reference, t9Engine, t10NativeLtf, t11Timeframes, prefetch } from './lib/tests_runtime.mjs';
import { maxJobs } from './lib/pinets.mjs';

function parseArgs(argv) {
  const a = { target: 'both', only: null, quick: false, verbose: false, bars: 3000, json: null, shims: [], noCache: false };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const next = () => { if (i + 1 >= argv.length) throw new Error(`falta valor para ${k}`); return argv[++i]; };
    if (k === '--target') a.target = next();
    else if (k === '--only') a.only = next().split(',').map((s) => s.trim().toUpperCase());
    else if (k === '--quick') a.quick = true;
    else if (k === '--verbose' || k === '-v') a.verbose = true;
    else if (k === '--bars') a.bars = Number(next());
    else if (k === '--json') a.json = next();
    else if (k === '--shim') a.shims.push(next());
    else if (k === '--no-cache') a.noCache = true;
    else if (k === '--file-std') a.fileStd = next();
    else if (k === '--file-fp') a.fileFp = next();
    else if (k === '--help' || k === '-h') { a.help = true; }
    else throw new Error(`argumento desconhecido: ${k}`);
  }
  if (!['std', 'fp', 'both', 'standin'].includes(a.target)) throw new Error(`--target inválido: ${a.target}`);
  return a;
}

const HELP = `Uso: node tests/run_tests.mjs [opções]
  --target std|fp|both|standin   alvo (por omissão: both = edições Standard + Footprint)
  --only T0,T4,...               corre só estes testes
  --quick                        matriz reduzida e séries mais curtas
  --bars N                       barras da matriz T4 (por omissão 3000)
  --json FICHEIRO                grava o relatório em JSON
  --shim ID                      activa um shim textual opcional (ver tests/README.md)
  --no-cache                     ignora a cache de parse do T2 (tests/out/parse-cache.json)
  --file-std / --file-fp CAMINHO testa outro ficheiro em vez da edição do repositório (ou PINE_STD_FILE/PINE_FP_FILE)
  --verbose                      mostra também as verificações que passaram`;

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) { console.log(HELP); return 0; }
  const rep = new Reporter({ verbose: args.verbose });
  const want = (id) => !args.only || args.only.includes(id);
  if (args.fileStd) setTargetFile('std', args.fileStd);
  if (args.fileFp) setTargetFile('fp', args.fileFp);
  const targetKeys = args.target === 'both' ? ['std', 'fp'] : [args.target];
  console.log(`Alvos: ${targetKeys.map((k) => targetPath(k)).join(', ')}${args.quick ? ' · modo rápido' : ''}`);

  // Preparação dos alvos (falha clara se o ficheiro não existir)
  const targets = [];
  for (const k of targetKeys) {
    const t = new Target(k, { shims: args.shims });
    try { await t.init(); t.ready = true; } catch (e) { t.ready = false; t.initError = e; }
    targets.push(t);
  }
  const withTarget = async (id, name, fn, { keys = targetKeys } = {}) => {
    if (!want(id)) return;
    for (const t of targets.filter((x) => keys.includes(x.key))) {
      const tc = rep.start(id, `${name} — ${t.info.label}`);
      if (!t.ready) {
        tc.fail(`preparar ${t.rel}`, t.initError.message.split('\n')[0] + (t.exists ? '' : ' (o indicador ainda não foi gerado? corra python3 tools/build.py)'));
      } else {
        try { await fn(tc, t); } catch (e) { tc.error = e; }
      }
      rep.end(tc);
    }
  };
  const plain = async (id, name, fn) => {
    if (!want(id)) return;
    const tc = rep.start(id, name);
    try { await fn(tc); } catch (e) { tc.error = e; }
    rep.end(tc);
  };

  // Lança já todas as execuções PineTS planeadas (workers em paralelo) enquanto T0–T3 correm.
  const runtimeIds = ['T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11'].filter(want);
  // T5–T11 em todas as edições pedidas (a Footprint tem o seu próprio motor/LTF/estatística por etiquetas @fp);
  // a matriz T4 completa só na Standard (a Footprint tem a sua matriz de footprint).
  const statKeys = targetKeys;
  const matrixKeys = targetKeys.includes('std') ? ['std'] : targetKeys;
  const ready = targets.filter((t) => t.ready);
  for (const t of ready) {
    if (want('T4') && matrixKeys.includes(t.key)) prefetch(t, ['T4'], { quick: args.quick, nBars: args.bars });
    if (want('T4') && t.key === 'fp') prefetch(t, ['T4'], { quick: args.quick, nBars: args.bars, footprintEdition: true });
  }
  for (const t of ready) prefetch(t, runtimeIds.filter((id) => id !== 'T4'), { quick: args.quick, nBars: args.bars });
  console.log(`PineTS em workers isolados: até ${maxJobs()} execuções em paralelo (HARNESS_JOBS para alterar).`);

  await plain('T0', 'Autoverificação do harness (PineTS, canal do delta, timeframe, inputs, built-ins)', (tc) => {
    for (const t of targets) if (!t.ready) tc.warn(`alvo ${t.rel} indisponível`, t.initError.message.split('\n')[0]);
    return t0SelfCheck(tc, targets);
  });
  await plain('T1', 'Build: python3 tools/build.py --check', (tc) => t1Build(tc, { targetKeys }));
  await plain('T2', 'Parse das edições com pynescript', (tc) => t2Parse(tc, { targetKeys, noCache: args.noCache }));
  await plain('T3', 'Verificações estáticas (sem footprint na Standard, linha LTF, banner)', (tc) => t3Static(tc, { targetKeys }));
  await withTarget('T4', 'Matriz de execução (modos × fonte × âncora)', (tc, t) => t4Matrix(tc, t, { quick: args.quick, nBars: args.bars }), { keys: matrixKeys });
  if (targetKeys.includes('fp')) await withTarget('T4', 'Matriz Footprint (fonte footprint via provider)', (tc, t) => t4Footprint(tc, t, { quick: args.quick, nBars: args.bars }), { keys: ['fp'] });
  await withTarget('T5', 'Calibração nula de Z', (tc, t) => t5Null(tc, t), { keys: statKeys });
  await withTarget('T6', 'Detecção de episódios injectados + auditoria exacta dos eventos e alertas', (tc, t) => t6Detection(tc, t, { quick: args.quick }), { keys: statKeys });
  await withTarget('T7', 'Invariantes (âncoras σ congeladas, preço implícito, janelas móveis, cone, deriva)', (tc, t) => t7Invariants(tc, t, { quick: args.quick }), { keys: statKeys });
  await withTarget('T8', 'Concordância com a referência JS (METODOLOGIA §6/§7, com quebras de qualidade)', (tc, t) => t8Reference(tc, t, { quick: args.quick }), { keys: statKeys });
  await withTarget('T9', 'Motor de delta e tier de qualidade', (tc, t) => t9Engine(tc, t), { keys: statKeys });
  await withTarget('T10', 'LTF nativo sem stub (ltfSigned no contexto intrabar)', (tc, t) => t10NativeLtf(tc, t), { keys: statKeys });
  await withTarget('T11', 'Timeframes, âncoras e qualidade (1m/1h/D/W/1S, sessão personalizada)', (tc, t) => t11Timeframes(tc, t), { keys: statKeys });

  const failed = rep.summary();
  if (args.json) { writeFileSync(args.json, JSON.stringify({ args, results: rep.toJSON() }, null, 2)); console.log(`relatório JSON: ${args.json}`); }
  return failed ? 1 : 0;
}

main().then((code) => { process.exitCode = code; }).catch((e) => { console.error(e.stack || e); process.exitCode = 2; });
