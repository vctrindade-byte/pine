// Contexto de um alvo (edição Standard, Footprint ou stand-in): lê o ficheiro, prepara o código (stub LTF +
// shims), lê inputs/enums/plots e executa no PineTS com cache de execuções.

import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { preprocess } from './preprocess.mjs';
import { inputsMeta, parseEnums, resolveOverrides, enumOptions, hasInput } from './inputs.mjs';
import { discoverRoles, pickRole } from './discover.mjs';
import { runPine, getPlot } from './pinets.mjs';

export const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

export const TARGETS = {
  std: { file: 'price_cvd_normalizer.pine', edition: 'std', label: 'Standard' },
  fp: { file: 'price_cvd_normalizer_footprint.pine', edition: 'fp', label: 'Footprint' },
  standin: { file: 'tests/fixtures/standin.pine', edition: 'standin', label: 'stand-in (tests/fixtures)' },
};

// Caminhos alternativos (ex.: testar uma build candidata noutra pasta): --file-std/--file-fp ou
// as variáveis de ambiente PINE_STD_FILE / PINE_FP_FILE.
const PATH_OVERRIDES = { std: process.env.PINE_STD_FILE || null, fp: process.env.PINE_FP_FILE || null, standin: null };
export function setTargetFile(key, path) { PATH_OVERRIDES[key] = path ? resolve(path) : null; }
export function targetPath(key) { return PATH_OVERRIDES[key] ? resolve(PATH_OVERRIDES[key]) : resolve(REPO, TARGETS[key].file); }

export class Target {
  constructor(key, { shims = [] } = {}) {
    this.key = key;
    this.info = TARGETS[key];
    this.path = targetPath(key);
    this.rel = this.path.startsWith(REPO + '/') ? relative(REPO, this.path) : this.path;
    this.exists = existsSync(this.path);
    this.shims = shims;
    this.runs = new Map();
  }

  async init() {
    if (!this.exists) throw new Error(`ficheiro em falta: ${this.rel}`);
    this.source = readFileSync(this.path, 'utf8').replace(/\r\n/g, '\n');
    const pre = preprocess(this.source, { stub: true, shims: this.shims });
    this.code = pre.code;
    this.applied = pre.applied;
    this.codeNoStub = preprocess(this.source, { stub: false, shims: this.shims }).code;
    this.meta = await inputsMeta(this.code);
    if (!this.meta.length) throw new Error('o scanner de inputs do PineTS não encontrou inputs (script inválido para o PineTS?)');
    this.enums = parseEnums(this.source);
    const disc = discoverRoles(this.source);
    this.roles = disc.roles;
    this.plotTitles = disc.titles;
    return this;
  }

  isFootprintEdition() { return /\brequest\.footprint\s*\(/.test(this.source); }
  enumOptions(key) { return enumOptions(this.meta, key); }
  hasInput(key) { return hasInput(this.meta, key); }
  /** Título da opção de um enum a partir do nome do membro (ex.: ('modeIn','sig') → "Unidades-σ ancoradas"). */
  option(key, member) { return resolveOverrides(this.meta, this.enums, { [key]: member }).resolved[0].value; }

  /**
   * Executa (com cache). wanted = overrides semânticos (validados). opts: { stub = true, footprint, timeframe }.
   */
  async run(data, wanted = {}, opts = {}) { return this.start(data, wanted, opts); }

  /**
   * Inicia (ou reutiliza) uma execução e devolve a promessa. As execuções correm em workers isolados, com
   * paralelismo limitado (HARNESS_JOBS); a cache guarda a promessa (também as rejeitadas: o erro é determinístico).
   */
  start(data, wanted = {}, { stub = true, footprint = null, fpTag = '', ltfBars = null, timeframe = '5', syminfo = {} } = {}) {
    const { overrides, resolved } = resolveOverrides(this.meta, this.enums, wanted);
    const key = JSON.stringify([data.id, overrides, stub, fpTag, ltfBars ? Object.keys(ltfBars) : null, timeframe, syminfo]);
    if (this.runs.has(key)) return this.runs.get(key);
    const p = runPine({ source: stub ? this.code : this.codeNoStub, klines: data.klines, timeframe, syminfo, inputs: overrides, footprint, ltfBars })
      .then((res) => Object.assign(res, { overrides, resolved, data }));
    p.catch(() => {}); // evita "unhandled rejection" em pré-carregamentos; quem espera recebe o erro
    this.runs.set(key, p);
    return p;
  }

  role(run, role, opts) { return pickRole(run, this.roles, role, opts); }
  plot(run, title) { return getPlot(run, title); }
}
