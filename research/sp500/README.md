# Estudo S&P 500: código e reprodução

Código do estudo de eventos pré-registado dos sinais do indicador no ES, no MES e no SPY. O relatório, com os
resultados e a sua interpretação, está em [docs/ESTUDO_SP500.md](../../docs/ESTUDO_SP500.md). Esta página explica como
obter os dados, reconstruir os ficheiros limpos e reproduzir cada tabela.

```
research/sp500/
  code/        código do estudo (Python 3; run_pine.mjs em Node)
  results/     resultados agregados de referência (só estatísticas: contagens, médias, p-valores, correlações)
    es/          estudo principal: results.md (todas as tabelas), interpretation.md, CHANGELOG.md, run_meta.json, CSV
    fidelity/    fidelidade do delta (amostra de ticks de 2013, TopstepX 2026)
    robust/      robustez (MES, SPY)
    validation_*.json, validation_summary.json, rounding_effect.json   validação do motor contra o Pine
```

## Regras sobre os dados

- **Os dados de mercado nunca entram no repositório**, nem os ficheiros derivados barra a barra (barras do gráfico,
  saídas do indicador por barra, entradas do PineTS). As licenças das fontes são para investigação ou avaliação e não
  permitem redistribuição.
- Os caminhos vêm só de variáveis de ambiente, sem valores por omissão (`code/studyenv.py`). Os scripts **recusam**
  escrever dados ou ficheiros por barra dentro de uma árvore git: aponte as pastas para fora do repositório.
- `results/` só tem estatísticas agregadas. O `.gitignore` da raiz exclui os ficheiros de dados (`*.parquet`, `*.csv`,
  `*.zst`, `*.gz`, `*.zip`, …) e as pastas `raw/`, `clean/`, `work/`, `features/` e `validation/` dentro de
  `research/sp500/`; a única excepção são os CSV agregados de `research/sp500/results/`.

## Requisitos

- Python ≥ 3.11 com numpy, pandas, pyarrow e scipy. Versões usadas: Python 3.13.16, numpy 2.5.3, pandas 3.0.5,
  scipy 1.18.1, pyarrow 26.0.0.
- Para reconstruir os dados (`load_clean.py`): também `zstandard` e `databento-dbn`.
- Para a validação contra o Pine: Node.js ≥ 20 e `npm install` na raiz do repositório (instala o PineTS 0.11.0; ver
  [tests/README.md](../../tests/README.md) para usar uma instalação existente com `NODE_PATH` ou `PINETS_DIR`).
- Corra sempre o Python com `-I` (modo isolado): os ficheiros de entrada são descarregados de terceiros.

## 1. Obter os dados

Cada fonte vai para uma subpasta de `RAW_DIR`, com o nome indicado. A coluna «Cópia usada» identifica de onde vieram
os ficheiros deste estudo: são cópias que terceiros publicaram em repositórios públicos do GitHub (e uma amostra
pública de fornecedor). **Publicar um ficheiro não concede uma licença.** Os termos do fornecedor original continuam a
aplicar-se; a via licenciada é comprar ou descarregar os dados directamente ao fornecedor, no formato descrito.
Verifique os termos antes de usar qualquer cópia.

| Subpasta de `RAW_DIR` | Ficheiros | Conteúdo | Fornecedor original (via licenciada) | Cópia usada | Licença |
|---|---|---|---|---|---|
| `tickdata_es_sample/` | `ES_Sample.zip` | ES, todos os negócios e cotações L1, 1–20 Set. 2013 | Tick Data LLC, amostras gratuitas do sítio do fornecedor | Amostra do fornecedor | Avaliação; sem redistribuição |
| `firstrate_via_jimmuell_mes-orb-strategy/` | `ES_full_1min_continuous_UNadjusted.txt` | ES contínuo não ajustado, 1 minuto (sessões até 2015 no estudo) | FirstRate Data | GitHub `jimmuell/mes-orb-strategy` (Git LFS) | FirstRate: investigação interna |
| `rueijrwu_FutureView/` | `glbx-mdp3-*.ohlcv-1m.dbn.zst` (mensais, Jun. 2010 →) e `meta/condition.json` | ES, barras de 1 minuto por contrato (todos os vencimentos) | Databento, dataset GLBX.MDP3, schema `ohlcv-1m`, símbolo-pai `ES.FUT`; `condition.json` = estado de qualidade por dia | GitHub `rueijrwu/FutureView` (Git LFS) | Databento/CME: investigação |
| `vinentHuynh_QuantResearch/` | `ES_v0_ohlcv1m_2010_2026_UTC.csv.gz` | ES contínuo por volume (`ES.v.0`), 1 minuto, até 29-09-2026 11:00 UTC; colunas `t,iid,o,h,l,c,v`, `t` em UTC | Databento, GLBX.MDP3, `ohlcv-1m`, `ES.v.0` | GitHub `vinentHuynh/QuantResearch` (`data/databento_updates/es-2026-09-29`) | Databento/CME: investigação |
| `dschace_trading-model_databento/` | `glbx-mdp3-*.ohlcv-1m.csv.zst` (mensais, Mai. 2021 →) e `condition.json` | MES, barras de 1 minuto por contrato | Databento, GLBX.MDP3, `ohlcv-1m`, `MES.FUT` | GitHub `dschace/trading-model` | Databento/CME: investigação |
| `axb0306_cme-futures-ohlc/` | `{ES,MES}_1min_*.csv`, `{ES,MES}_tick_*.csv` (estes são barras de 1 segundo) | ES e MES, 2026 | API TopstepX/ProjectX | GitHub `axb0306/cme-futures-ohlc` | Nenhuma declarada; só investigação |
| `prsdro_spy/` | `candles_1m.csv.gz` | SPY, 1 minuto, 2000–2026, horário regular e alargado | Não identificado | GitHub `prsdro/spy` (`data/candles_1m.csv.gz`) | Nenhuma declarada; só investigação |
| `github_alegitdude_backtester/` | `ES-glbx-20251105.mbp-10-sample.csv.zst` | ES MBP-10 com a marca de agressor (só para validar o classificador) | Databento, GLBX.MDP3, `mbp-10` | GitHub `alegitdude/Backtester` (dados de teste) | Databento/CME: investigação |
| `s3_frd001_firstrate_samples/` | `SPY_1min_sample_firstratedata.zip` | SPY, amostra 2022–2023 (só verificação cruzada) | FirstRate Data, amostra pública | Amostra do fornecedor | Amostra do fornecedor |
| `github_algoquant_HighFreq/` | `SPY_1min_2008-01-02_2014-05-19_ET_barstart.csv.gz` | SPY 2008–2014 (só verificação cruzada) | — | GitHub `algoquant/HighFreq` | Ver o repositório |
| `kfhoo88_ibkr-scalper/` | `SPY_IBKR_1min_1year_20251110.csv` | SPY 2024–2025 (só verificação cruzada) | Interactive Brokers | GitHub `kfhoo88/ibkr-scalper` | Ver o repositório |

Os formatos esperados são os publicados por cada fonte; as funções `build_*` de `code/load_clean.py` mostram como cada
um é lido. Se obtiver os dados directamente do fornecedor noutro formato, converta-os para o formato da tabela ou
adapte essas funções. Com outras fontes, os números não serão idênticos aos de `results/`.

## 2. Construir os ficheiros limpos

```bash
export RAW_DIR=/dados/sp500/raw          # fora do repositório
export DATA_DIR=/dados/sp500/clean       # fora do repositório; WORK_DIR (cache) por omissão = $DATA_DIR/work
python3 -I code/load_clean.py            # todos os conjuntos (es_tick es_1m mes_1m topstepx spy_1m)
python3 -I code/load_clean.py es_tick    # só um
```

Saídas em `DATA_DIR` (horas em UTC, carimbo no início da barra): `es_ticks_2013-09_{trades,1s,1m}.parquet`,
`es_1m_2008-2026.parquet` e `_sessions.parquet`, `mes_1m_2021-2026.parquet` e `_sessions.parquet`,
`{es,mes}_topstepx_2026_{1s,1m}.parquet`, `spy_1m_2000-2026.parquet` e `manifest.json`. O `manifest.json` documenta
as fontes, as verificações de integridade, as rolagens, a cobertura por ano e a lista de sessões limpas
(`clean_session`). Os preços dos futuros não são ajustados; `adj_offset` dá o ajuste aditivo, se for preciso.

Verificação: com as mesmas fontes, a reconstrução de `es_tick` a partir desta cópia do código deu ficheiros e
`manifest.json` idênticos aos usados no estudo.

## 3. Variáveis de ambiente

| Variável | Uso | Obrigatória |
|---|---|---|
| `RAW_DIR` | Downloads originais (só `load_clean.py`) | Sim, para `load_clean.py` |
| `DATA_DIR` | Ficheiros limpos de 1 minuto (saída de `load_clean.py`, entrada dos restantes) | Sim, para construir barras; opcional em `study_es.py` (sem ela, as análises post hoc de latência e do minuto de liquidação são omitidas) |
| `WORK_DIR` | Cache de `load_clean.py` | Não (`$DATA_DIR/work`) |
| `OUT_DIR` | Pasta do estudo: `features/`, `validation/` e `results/` por baixo | Sim (salvo se `FEAT_DIR` e `RES_DIR` estiverem definidas) |
| `FEAT_DIR` | Ficheiros de características por barra | Não (`$OUT_DIR/features`); recusada dentro de uma árvore git |
| `RES_DIR` | Resultados de `study_es.py` | Não (`$OUT_DIR/results/es`) |
| `PINE_REPO` | Raiz do repositório com o script Pine | Não (o repositório que contém este código) |
| `NODE_PATH` / `PINETS_DIR` | Instalação do PineTS 0.11.0 | Não, se `npm install` foi feito na raiz |

`OUT_DIR` deve ficar fora do repositório (lá ficam os ficheiros por barra). Os resultados agregados podem ir para
qualquer sítio; para comparar com os de referência, não os escreva por cima de `research/sp500/results/`.

## 4. Reproduzir, por ordem

A partir da raiz do repositório, com `DATA_DIR` e `OUT_DIR` definidas (tempos medidos com 4 CPUs):

```bash
# 4.1 Características por barra: barras de 5 e 15 minutos (e 1 minuto na amostra de ticks), todas as saídas do
#     indicador com os valores por omissão (cerca de 3 minutos; vários GB de memória para o ES de 5 minutos).
python3 -I research/sp500/code/features.py all

# 4.2 Validação do motor contra o script Pine real no PineTS (cerca de 30 minutos no total; um ano de ES de
#     5 minutos leva cerca de 8). Cada comando escreve $OUT_DIR/results/validation_<tag>.json.
V="python3 -I research/sp500/code/validate_pine.py"
$V --inst es --tf 5 --start 2019-01-01 --end 2020-01-01 --tag es5_2019
$V --inst es --tf 5 --start 2008-01-01 --end 2009-01-01 --sessions all --tag es5_2008_all
$V --inst es --tf 15 --start 2020-01-01 --end 2021-01-01 --tag es15_2020
$V --inst spy --tf 5 --start 2022-01-01 --end 2023-01-01 --tag spy5_2022
$V --inst es_tick --tf 1 --variant d_true --prec s1 --tag tick1_true
$V --inst es_tick --tf 1 --variant d_true --prec s1 --tag tick1_true_params --inputs \
   '{"rhoMinIn":0,"nIn":50,"kIn":10,"mIn":500,"driftIn":true,"evWinIn":5,"lifeIn":30,"zfIn":1.8,"pinIn":2.5,"pinPIn":0.8,"pivLIn":4,"pivRIn":3,"pivMinIn":3,"pivMaxIn":80,"pivMagIn":0.3,"thrIn":1.8}'
$V --inst es_tick --tf 5 --variant d_true --prec s1 --tag tick5_true
$V --inst es_tick --tf 5 --variant d_cr1s --prec s1 --tag tick5_cr1s
$V --inst es_tick --tf 5 --variant d_cr1m --prec auto --tag tick5_cr1m
$V --inst es_tick --tf 5 --variant d_true --prec s1 --stress 7 --tag tick5_true_stress7
$V --inst es_tick --tf 15 --variant d_true --prec s1 --tag tick15_true
$V --inst es_tick --tf 15 --variant d_cr1m --prec auto --tag tick15_cr1m
python3 -I research/sp500/code/validation_summary.py                       # → validation_summary.json
python3 -I research/sp500/code/rounding_effect.py es:5 es:15 mes:5 mes:15 spy:5 spy:15   # → rounding_effect.json

# 4.3 Fidelidade do delta (cerca de 15 segundos) → $OUT_DIR/results/fidelity/
python3 -I research/sp500/code/study_fidelity.py

# 4.4 Estudo principal no ES, 5 e 15 minutos (cerca de 3 minutos) → $OUT_DIR/results/es/
#     Corra-o depois de 4.3: a secção 11.2 de results.md cita números do estudo de fidelidade.
python3 -I research/sp500/code/study_es.py
python3 -I research/sp500/code/study_es.py --report-only    # só refaz results.md a partir dos CSV

# 4.5 Robustez no MES e no SPY, com o ES como referência (cerca de 35 segundos) → $OUT_DIR/results/robust/
python3 -I research/sp500/code/study_robust.py
```

Notas:

- `results/es/interpretation.md` foi escrito à mão depois dos resultados. Se existir em `RES_DIR`, `study_es.py`
  insere-o no topo de `results.md`; caso contrário, `results.md` começa na secção 1.
- `study_robust.py` usa um único gerador aleatório para todos os conjuntos, pela ordem por omissão. Para obter os mesmos
  intervalos *bootstrap* de `results/robust/`, corra todos os conjuntos de uma vez, sem argumentos; com um só conjunto,
  as estimativas, erros-padrão e p-valores são os mesmos, mas os intervalos *bootstrap* não.
- `study_es.py` pára se faltar um ficheiro de características do ES; `--rebuild-features` reconstrói-o a partir de
  `DATA_DIR`.
- `features.py es_5m_cr1m es_15m_cr1m --gate off` produz ficheiros de controlo com o gate desligado. O estudo do gate
  não precisa deles: reexecuta o motor com cada variante.

## 5. Onde está cada tabela do relatório

| Secção de [ESTUDO_SP500.md](../../docs/ESTUDO_SP500.md) | Script | Ficheiros de `results/` |
|---|---|---|
| 2. Dados | `load_clean.py` | `manifest.json` em `DATA_DIR` (não versionado) |
| 4. Validação do motor | `validate_pine.py`, `validation_summary.py`, `rounding_effect.py` | `validation_*.json`, `rounding_effect.json` |
| 5. Fidelidade do delta | `study_fidelity.py` | `fidelity/fidelity_summary.json`, `fidelity/*.csv` |
| 6. Calibração do Z | `study_es.py` | `es/zcal_{5,15}m.csv`, `es/zcal_year_{5,15}m.csv` (secção 8 de `es/results.md`) |
| 7. Resultado primário e horizontes | `study_es.py` | `es/classes_{5,15}m.csv`, `es/counts_*.csv`, `es/tod_*.csv`, `es/latency_*.csv` (secções 1–3 e 11.3) |
| 8. Gémeos e controlos | `study_es.py` | `es/twins_*.csv`, `es/matched_*.csv`, `es/matched_sens_*.csv`, `es/baseline_*.csv` (secções 4 e 11.1) |
| 9. Gate | `study_es.py` | `es/gate_*.csv`, `es/gate_diff_*.csv` (secção 5) |
| 10. MFE e MAE | `study_es.py` | colunas `mfe_*`, `mae_*` de `es/classes_*.csv` e `es/baseline_*.csv` |
| 11. Custos | `study_es.py` | `es/costs_*.csv`, `es/survival_*.csv` (secções 6 e 11.5) |
| 12. Estabilidade | `study_es.py` | `es/stability_*.csv`, `es/per_year_*.csv`, `es/per_year_summary_*.csv` (secção 7) |
| 13. Minuto de liquidação | `study_es.py` (com `DATA_DIR`) | `es/settle_*.csv`, `es/settle_minute_volume.csv`, `es/slot_drift_*.csv`, `es/prior_res_*.csv` (secções 11.2 e 11.4) |
| 14. Robustez | `study_robust.py` | `robust/*.csv`, `robust/robust_summary.json` |
| 15. Desvios ao plano | — | secção 10 de `es/results.md`, `es/CHANGELOG.md` |

## 6. Comparar com os resultados de referência

```bash
python3 -I - <<'EOF'
import glob, os, numpy as np, pandas as pd
ref, new = 'research/sp500/results', os.path.join(os.environ['OUT_DIR'], 'results')
for f in sorted(glob.glob(f'{ref}/**/*.csv', recursive=True)):
    g = f.replace(ref, new)
    a, b = pd.read_csv(f), pd.read_csv(g)
    bad = [c for c in a if not (a[c].equals(b[c]) or (a[c].dtype.kind in 'fi'
           and np.allclose(a[c], b[c], equal_nan=True, rtol=1e-12, atol=1e-12)))]
    print(os.path.relpath(f, ref), 'igual' if not bad and a.shape == b.shape else bad)
EOF
```

Com os mesmos dados de entrada, esta cópia do código reproduziu exactamente os 41 CSV de `results/es/`, os 17 de
`results/robust/` e os 11 de `results/fidelity/`, e o `results.md` igual linha a linha, excepto a linha da data.

## 7. Módulos

| Ficheiro | Função |
|---|---|
| `studyenv.py` | Caminhos a partir do ambiente; recusa pastas de dados dentro de uma árvore git |
| `load_clean.py` | Reconstrução dos ficheiros limpos a partir das fontes (secção 1) |
| `bars.py` | Barras de 1, 5 e 15 minutos por sessão e as variantes do delta (regra da vela em 1 minuto e em 1 segundo, delta verdadeiro) |
| `engine.py` | Tradução exacta das saídas do indicador para Python (validada contra o Pine) |
| `features.py` | Ficheiros de características por barra (barras + todas as saídas do indicador) |
| `validate_pine.py`, `run_pine.mjs` | Validação barra a barra contra o script Pine real no PineTS, através do canal de dados de `tests/lib/` |
| `validation_summary.py`, `rounding_effect.py` | Resumo da validação; efeito do arredondamento do PineTS nos históricos completos |
| `study_fidelity.py` | Fidelidade do delta (amostra de ticks de 2013, TopstepX 2026) |
| `study_es.py` | Estudo principal pré-registado no ES (o plano está na docstring do ficheiro) |
| `study_robust.py` | Robustez do resultado primário no MES e no SPY |

O indicador não é alterado por nenhum destes scripts: `run_pine.mjs` lê a edição Standard gerada e acrescenta, só em
memória, o substituto de `request.security_lower_tf` dos testes e plots de observação.
