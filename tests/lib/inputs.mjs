// Resolução de overrides de inputs. O PineTS aceita overrides por varId (ou título) e, para enums, o
// TÍTULO da opção (ex.: "Unidades-σ ancoradas"); valores desconhecidos são IGNORADOS em silêncio
// (o script corre com o default). Por isso este módulo valida tudo e falha alto.
//
// Chaves aceites: varId (ex.: "modeIn"), título exacto, ou um papel semântico de INPUT_ROLES.
// Valores de enum aceites: título exacto, "Enum.membro", "membro", ou um fragmento único do título.

import { loadPineTS } from './pinets.mjs';

/** Papéis semânticos → candidatos (varIds de spec.md e regex sobre o título PT). */
export const INPUT_ROLES = {
  srcIn: { varIds: ['srcIn'], title: [/fonte/i] },
  precIn: { varIds: ['precIn'], title: [/precis/i] },
  ltfCustIn: { varIds: ['ltfCustIn', 'ltfCust'], title: [/personaliz/i] },
  clsIn: { varIds: ['clsIn'], title: [/classific/i] },
  fallbackIn: { varIds: ['fallbackIn'], title: [/fallback|sem intrabar/i] },
  driftIn: { varIds: ['driftIn'], title: [/deriva/i] },
  modeIn: { varIds: ['modeIn'], title: [/^modo/i] },
  anchIn: { varIds: ['anchIn'], title: [/âncora|ancora/i] },
  wIn: { varIds: ['wIn'], title: [/janela w/i] },
  lamIn: { varIds: ['lamIn'], title: [/λ|impacto/i] },
  ovlIn: { varIds: ['ovlIn'], title: [/gráfico principal/i] },
  viewIn: { varIds: ['viewIn'], title: [/visualiza|vista/i] },
  coneIn: { varIds: ['coneIn'], title: [/cone/i] },
  nIn: { varIds: ['nIn'], title: [/\(N\)/] },
  kIn: { varIds: ['kIn'], title: [/\(K\)/] },
  mIn: { varIds: ['mIn'], title: [/\(M\)/] },
  clipIn: { varIds: ['clipIn'], title: [/winsoriz/i] },
  thrIn: { varIds: ['thrIn'], title: [/^limiar \|Z\|/i] },
  thr2In: { varIds: ['thr2In'], title: [/limiar forte/i] },
  rhoMinIn: { varIds: ['rhoMinIn'], title: [/ρ mínimo|rho/i] },
  evIn: { varIds: ['evIn'], title: [/eventos de absor/i] },
  pwfIn: { varIds: ['pwfIn'], title: [/preço sem fluxo/i] },
  lowConfIn: { varIds: ['lowConfIn'], title: [/baixa confian/i] },
  tblIn: { varIds: ['tblIn'], title: [/tabela/i] },
  ticksIn: { varIds: ['ticksIn'], title: [/ticks/i] },
  fpFillIn: { varIds: ['fpFillIn'], title: [/preencher|footprint.*intrabar/i] },
  pivIn: { varIds: ['pivIn'], title: [/pivot/i] },
};

/** Lê as declarações enum do código: { Nome: [{ member, title }] }. */
export function parseEnums(src) {
  const out = {};
  const lines = src.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^(?:export\s+)?enum\s+(\w+)\s*(?:\/\/.*)?$/);
    if (!m) continue;
    const members = [];
    for (let j = i + 1; j < lines.length; j++) {
      const l = lines[j];
      if (/^\s*$/.test(l) || /^\s*\/\//.test(l)) { if (/^\s*$/.test(l)) break; continue; }
      if (!/^\s+/.test(l)) break;
      const mm = l.match(/^\s+(\w+)\s*(?:=\s*"((?:[^"\\]|\\.)*)")?/);
      if (mm) members.push({ member: mm[1], title: mm[2] !== undefined ? mm[2] : mm[1] });
    }
    out[m[1]] = members;
  }
  return out;
}

/** Metadados dos inputs via scanner do PineTS (varId, título, tipo, opções, default). */
export async function inputsMeta(src) {
  const { Indicator } = await loadPineTS();
  return new Indicator(src).getInputsMeta();
}

function findInput(meta, key) {
  let hit = meta.find((m) => m.varId === key) || meta.find((m) => m.title === key);
  if (hit) return hit;
  const role = INPUT_ROLES[key];
  if (role) {
    for (const v of role.varIds) { hit = meta.find((m) => m.varId === v); if (hit) return hit; }
    for (const re of role.title) {
      const hits = meta.filter((m) => re.test(m.title || ''));
      if (hits.length === 1) return hits[0];
    }
  }
  return null;
}

function resolveEnumValue(input, value, enums) {
  const opts = input.options || [];
  if (opts.includes(value)) return value;
  const s = String(value);
  // "Enum.membro" ou "membro"
  const [en, mem] = s.includes('.') ? s.split('.', 2) : [null, s];
  const candidates = Object.entries(enums).filter(([name, members]) =>
    (en === null || name === en) && members.length === opts.length && members.every((x) => opts.includes(x.title)));
  for (const [, members] of candidates) {
    const m = members.find((x) => x.member === mem);
    if (m) return m.title;
  }
  // fragmento único do título (sem distinguir maiúsculas)
  const frag = opts.filter((o) => o.toLowerCase().includes(s.toLowerCase()));
  if (frag.length === 1) return frag[0];
  return undefined;
}

/**
 * Converte overrides semânticos em overrides PineTS validados (chave = varId ou título).
 * Lança erro se um input/valor não puder ser resolvido.
 * @returns {{ overrides: Record<string, unknown>, resolved: Array<{key, input, value}> }}
 */
export function resolveOverrides(meta, enums, wanted) {
  const overrides = {};
  const resolved = [];
  for (const [key, value] of Object.entries(wanted || {})) {
    if (value === undefined) continue;
    const input = findInput(meta, key);
    if (!input) throw new Error(`input "${key}" não encontrado (inputs: ${meta.map((m) => m.varId || m.title).join(', ')})`);
    let v = value;
    if (input.type === 'enum') {
      v = resolveEnumValue(input, value, enums);
      if (v === undefined) throw new Error(`valor "${value}" inválido para o input enum "${input.title}" (opções: ${input.options.join(' | ')})`);
    } else if (input.type === 'int' || input.type === 'float') {
      if (!Number.isFinite(Number(value))) throw new Error(`valor numérico inválido para "${input.title}": ${value}`);
      v = Number(value);
    } else if (input.type === 'bool') {
      v = Boolean(value);
    } else if (input.options && input.options.length && !input.options.includes(value)) {
      throw new Error(`valor "${value}" fora das opções de "${input.title}"`);
    }
    const k = input.varId || input.title;
    overrides[k] = v;
    resolved.push({ key, input: k, title: input.title, value: v });
  }
  return { overrides, resolved };
}

/** Opções (títulos) de um input enum, por papel. */
export function enumOptions(meta, key) {
  const input = findInput(meta, key);
  return input && input.type === 'enum' ? input.options.slice() : [];
}

export function hasInput(meta, key) {
  return Boolean(findInput(meta, key));
}
