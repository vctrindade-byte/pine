// Canal do delta verdadeiro: codificado nos milissegundos do openTime de cada barra.
//
//   code = openTime % 1000  ∈ [0, 998]  →  q = code / 499 − 1  ∈ [−1, +1]  (rácio líquido do agressor, Δ/V)
//   code = 999                         →  "sem intrabars" nesta barra (o stub devolve arrays vazios)
//
// q = 0 é exactamente representável (code 499); a resolução é 1/499 ≈ 0,002 em Δ/V.
// Os limites de dia/semana/mês são múltiplos inteiros de segundos, por isso um desvio < 1 s no
// openTime nunca muda a barra de calendário: timeframe.change("1D"/"1W"/"1M") e session.isfirstbar
// continuam correctos (verificado com o PineTS 0.11.0 — ver tests/README.md).
// A barra-base (sem ms) tem de estar alinhada ao segundo.
//
// Volume dos intrabars: o do gráfico quando o gráfico tem volume; STUB_NA_VOL quando o volume do gráfico está em falta
// (na). Assim o harness consegue representar uma barra cujo volume do gráfico falta mas cujos intrabars têm negócios
// (o indicador tem de avaliar a falta de volume na FONTE escolhida, não no gráfico; T12). Volume 0 no gráfico → volume 0
// nos intrabars (o stub não representa «gráfico 0, intrabars > 0»; a edição Footprint testa-o com o footprint).

export const NO_INTRABARS = 999;
export const Q_SCALE = 499;
/** Volume total dos intrabars do stub numa barra cujo volume do gráfico é na. */
export const STUB_NA_VOL = 100;

/** Quantiza um rácio q ∈ [−1, 1] no código de ms (0..998). */
export function encodeQ(q) {
  if (!Number.isFinite(q)) throw new Error(`encodeQ: q não finito (${q})`);
  const qc = Math.max(-1, Math.min(1, q));
  return Math.round((qc + 1) * Q_SCALE);
}

/** Valor de q que o stub Pine decodifica a partir do código. */
export function decodeQ(code) {
  return code / Q_SCALE - 1;
}

/** Volume total dos intrabars do stub (NaN = barra sem intrabars): o do gráfico, ou STUB_NA_VOL se esse for na. */
export function stubVol(code, volume) {
  if (code === NO_INTRABARS) return NaN;
  return Number.isFinite(volume) ? volume : STUB_NA_VOL;
}

/** Delta exactamente igual ao que o stub Pine produz: stubVol · (code/499 − 1). */
export function stubDelta(code, volume) {
  if (code === NO_INTRABARS) return NaN;
  return stubVol(code, volume) * decodeQ(code);
}

/**
 * O stub devolve STUB_K intrabars por barra, com pesos desiguais (somam 1): exercita a soma por barra, a média de
 * intrabars e a cobertura da tabela. O array "BVC" vale STUB_BVC_SCALE × delta (distinguível do da regra da vela),
 * para que o input do classificador tenha efeito observável.
 */
export const STUB_K = 5;
export const STUB_WEIGHTS = [0.1, 0.15, 0.2, 0.25, 0.3];
export const STUB_BVC_SCALE = 0.5;

/** Delta que o stub devolve com o classificador BVC (= STUB_BVC_SCALE × delta da regra da vela). */
export function stubDeltaBvc(code, volume) {
  return STUB_BVC_SCALE * stubDelta(code, volume);
}

/** Texto Pine do stub injectado (função global, definida imediatamente antes da linha LTF). */
export const STUB_FN_NAME = '__ltfStub';
export function stubPineSource() {
  const parts = (x, k = 1) => STUB_WEIGHTS.map((w) => `${x} * ${(w * k).toFixed(4)}`).join(', ');
  return [
    '// [harness] stub de request.security_lower_tf: delta verdadeiro decodificado de time % 1000',
    `${STUB_FN_NAME}() =>`,
    '    int __c = time % 1000',
    `    float __v = na(volume) ? ${STUB_NA_VOL.toFixed(1)} : volume`,
    `    float __d = __v * (__c / ${Q_SCALE}.0 - 1.0)`,
    `    array<float> __a = array.from(${parts('__d')})`,
    `    array<float> __b = array.from(${parts('__d', STUB_BVC_SCALE)})`,
    `    array<float> __w = array.from(${parts('__v')})`,
    `    if __c >= ${NO_INTRABARS}`,
    '        __a := array.new_float(0)',
    '        __b := array.new_float(0)',
    '        __w := array.new_float(0)',
    '    [__a, __b, __w]',
  ].join('\n');
}
