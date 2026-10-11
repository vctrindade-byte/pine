#!/usr/bin/env python3
"""Gera as duas edições do indicador a partir da fonte única.

    python3 tools/build.py           # escreve as duas edições
    python3 tools/build.py --check   # sai com código ≠ 0 se os ficheiros gerados não coincidirem com a fonte

Fonte: src/price_cvd_normalizer.src.pine (o ÚNICO ficheiro Pine editado à mão).
Etiquetas de linha (no fim da linha física, depois do código, separadas por espaços):
    // @fp   → linha mantida SÓ na edição Footprint
    // @std  → linha mantida SÓ na edição Standard
Linhas sem etiqueta vão para as duas edições. Numa instrução com várias linhas, todas as linhas levam etiqueta.
Nas linhas mantidas, a etiqueta (e os espaços finais) é removida.

Saídas:
    price_cvd_normalizer.pine            Standard (todos os planos; sem nenhuma referência de código a footprint)
    price_cvd_normalizer_footprint.pine  Footprint (Premium/Ultimate)

Só biblioteca padrão.
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "price_cvd_normalizer.src.pine"
SRC_REL = "src/price_cvd_normalizer.src.pine"
EDITIONS = {
    "std": ROOT / "price_cvd_normalizer.pine",
    "fp": ROOT / "price_cvd_normalizer_footprint.pine",
}
VERSION_LINE = "//@version=6"
BANNER = f"// GERADO por tools/build.py a partir de {SRC_REL} — não editar à mão."

# Etiqueta válida: "// @fp" ou "// @std" no fim da linha, precedida de pelo menos um espaço (ou no início da linha).
TAG_RE = re.compile(r"(?:^|\s+)//\s*@(fp|std)\s*$")
# Qualquer coisa parecida com uma etiqueta, para apanhar gralhas (ex.: "// @FP", "//@fpp", "// @std x").
TAG_LIKE_RE = re.compile(r"//\s*@(?!version\b)[A-Za-z]\w*")
LTF_LINE_RE = re.compile(r"^\[\s*aCand\s*,\s*aBvc\s*,\s*aVol\s*\]\s*=\s*request\.security_lower_tf\(")


class BuildError(Exception):
    pass


def strip_strings_and_comments(line: str) -> str:
    """Devolve só o código da linha: remove literais de string ("..." e '...') e o comentário // final."""
    out = []
    i, n = 0, len(line)
    quote = None
    while i < n:
        c = line[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ('"', "'"):
            quote = c
            out.append(" ")
            i += 1
            continue
        if c == "/" and i + 1 < n and line[i + 1] == "/":
            break
        out.append(c)
        i += 1
    return "".join(out)


def split_tag(line: str, lineno: int) -> tuple[str, str | None]:
    """Separa (texto sem etiqueta, etiqueta|None). Falha em etiquetas mal formadas."""
    m = TAG_RE.search(line)
    if m:
        body = line[: m.start()].rstrip()
        if TAG_LIKE_RE.search(body):
            raise BuildError(f"{SRC_REL}:{lineno}: mais do que uma etiqueta na mesma linha")
        return body, m.group(1)
    stray = TAG_LIKE_RE.search(line)
    if stray:
        raise BuildError(f"{SRC_REL}:{lineno}: etiqueta inválida ou fora do fim da linha: {stray.group(0)!r}")
    return line.rstrip(), None


def build(src_text: str) -> dict[str, str]:
    lines = src_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or lines[0].strip() != VERSION_LINE:
        raise BuildError(f"{SRC_REL}:1: a primeira linha tem de ser {VERSION_LINE!r}")
    outs: dict[str, list[str]] = {ed: [VERSION_LINE, BANNER] for ed in EDITIONS}
    for lineno, raw in enumerate(lines[1:], start=2):
        body, tag = split_tag(raw, lineno)
        for ed in EDITIONS:
            if tag is None or tag == ed:
                outs[ed].append(body)
    texts = {ed: "\n".join(ls) + "\n" for ed, ls in outs.items()}
    for ed, text in texts.items():
        validate(ed, text)
    return texts


def validate(ed: str, text: str) -> None:
    """Verificações de sanidade das edições geradas (não substituem o compilador da TradingView)."""
    name = EDITIONS[ed].name
    lines = text.split("\n")
    code_lines = [strip_strings_and_comments(l) for l in lines]
    code = "\n".join(code_lines)
    if lines[0] != VERSION_LINE:
        raise BuildError(f"{name}: a linha 1 não é {VERSION_LINE}")
    n_ind = len(re.findall(r"(?<![\w.])indicator\s*\(", code))
    if n_ind != 1:
        raise BuildError(f"{name}: esperava exactamente 1 indicator(), encontrei {n_ind}")
    ltf_hits = [i for i, l in enumerate(lines) if LTF_LINE_RE.match(l)]
    n_ltf = len(re.findall(r"request\.security_lower_tf\s*\(", code))
    if len(ltf_hits) != 1 or n_ltf != 1:
        raise BuildError(f"{name}: esperava exactamente 1 linha '[aCand, aBvc, aVol] = request.security_lower_tf(' "
                         f"no âmbito global (linhas: {len(ltf_hits)}, chamadas: {n_ltf})")
    ltf_code = code_lines[ltf_hits[0]]
    if ltf_code.count("(") != ltf_code.count(")"):
        raise BuildError(f"{name}:{ltf_hits[0] + 1}: a chamada request.security_lower_tf tem de caber numa só linha física")
    n_fp_req = len(re.findall(r"request\.footprint\s*\(", code))
    if ed == "std":
        hits = [i + 1 for i, l in enumerate(code_lines) if re.search(r"footprint", l, re.IGNORECASE)]
        if hits:
            raise BuildError(f"{name}: código com 'footprint' na edição Standard (linhas {hits[:10]})")
        if re.search(r"request\.footprint", text):
            raise BuildError(f"{name}: o texto 'request.footprint' não pode aparecer na edição Standard")
    elif n_fp_req != 1:
        raise BuildError(f"{name}: esperava exactamente 1 chamada request.footprint(), encontrei {n_fp_req}")
    leftovers = [i + 1 for i, l in enumerate(lines) if TAG_RE.search(l)]
    if leftovers:
        raise BuildError(f"{name}: etiquetas // @fp / // @std remanescentes (linhas {leftovers[:10]})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gera as edições Standard e Footprint do indicador Preço × CVD.")
    ap.add_argument("--check", action="store_true",
                    help="não escreve nada; sai com 1 se os ficheiros gerados diferirem de uma compilação nova")
    args = ap.parse_args(argv)
    try:
        texts = build(SRC.read_text(encoding="utf-8"))
    except (OSError, BuildError) as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 2
    if args.check:
        stale = []
        for ed, path in EDITIONS.items():
            current = path.read_text(encoding="utf-8") if path.exists() else None
            if current != texts[ed]:
                stale.append(path.name)
                if current is None:
                    print(f"EM FALTA: {path.name}", file=sys.stderr)
                else:
                    diff = difflib.unified_diff(current.splitlines(), texts[ed].splitlines(),
                                                f"{path.name} (no disco)", f"{path.name} (compilação nova)", lineterm="", n=1)
                    print("\n".join(list(diff)[:40]), file=sys.stderr)
        if stale:
            print(f"DESACTUALIZADO: {', '.join(stale)} — corra: python3 tools/build.py", file=sys.stderr)
            return 1
        print("OK: edições actualizadas (" + ", ".join(p.name for p in EDITIONS.values()) + ")")
        return 0
    for ed, path in EDITIONS.items():
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texts[ed])
        print(f"escrito {path.relative_to(ROOT)} ({texts[ed].count(chr(10))} linhas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
