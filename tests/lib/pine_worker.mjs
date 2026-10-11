// Worker de uma execução PineTS (ver runPine em pinets.mjs): recebe o job em workerData, devolve o resultado
// serializado e termina. Um isolate novo por execução evita a degradação de desempenho do PineTS.
import { parentPort, workerData } from 'node:worker_threads';
import { runPineInProcess, serializeRun } from './pinets.mjs';

try {
  const r = await runPineInProcess(workerData);
  parentPort.postMessage({ ok: true, result: serializeRun(r) });
} catch (e) {
  parentPort.postMessage({ ok: false, error: { message: String(e?.message ?? e), stack: String(e?.stack ?? ''), code: e?.code } });
}
