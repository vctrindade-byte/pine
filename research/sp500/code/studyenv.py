#!/usr/bin/env python3
"""Study paths, taken from environment variables only (fail closed).

The code of this study is meant to live inside the indicator's git repository (research/sp500/), but the market data
and every per-bar file derived from them are licensed for research only and must never be written inside a git work
tree. Therefore there are no path defaults relative to the code:

  DATA_DIR  folder of the clean 1-minute files (read only). Required by every script that reads market data.
  OUT_DIR   study folder (features/, validation/ and results/ underneath unless overridden). Required, no default.
  FEAT_DIR  per-bar feature files (default OUT_DIR/features). Refused inside a git work tree.
  RES_DIR   results of study_es.py (default OUT_DIR/results/es). Aggregate tables only, so it may be anywhere.

`work_dir()` (per-bar inputs written for PineTS by validate_pine.py) is also refused inside a git work tree.
"""
from __future__ import annotations

import os
from pathlib import Path


def _env(name: str) -> Path | None:
    v = os.environ.get(name, '').strip()
    return Path(v).expanduser().resolve() if v else None


def require(name: str, what: str) -> Path:
    """Path from environment variable `name`; stops with a message when it is not set."""
    p = _env(name)
    if p is None:
        raise SystemExit(f'{name} is not set ({what}). There is no default: set it explicitly, so that nothing is '
                         'read from or written to an unintended place (e.g. inside the git repository).')
    return p


def git_work_tree(p: Path) -> Path | None:
    """Root of the git work tree that contains p (p itself need not exist), or None."""
    p = Path(p).expanduser().resolve()
    for q in (p, *p.parents):
        if (q / '.git').exists():
            return q
    return None


def outside_git(p: Path, what: str) -> Path:
    """Return p, or stop when p lies inside a git work tree (licensed per-bar data must stay out of repositories)."""
    root = git_work_tree(p)
    if root is not None:
        raise SystemExit(f'refusing to use {p} for {what}: it is inside the git work tree {root}. Licensed per-bar data '
                         'must stay outside any repository; point OUT_DIR / FEAT_DIR to a scratch folder.')
    return p


def data_dir() -> Path:
    return require('DATA_DIR', 'folder of the clean 1-minute files')


def out_dir() -> Path:
    return require('OUT_DIR', 'study folder that holds features/ and results/')


def feat_dir() -> Path:
    """Per-bar feature files (derived from licensed data): never inside a git work tree."""
    return outside_git(_env('FEAT_DIR') or out_dir() / 'features', 'per-bar feature files (licensed data)')


def work_dir() -> Path:
    """Per-bar PineTS inputs of validate_pine.py (derived from licensed data): never inside a git work tree."""
    return outside_git(out_dir() / 'validation', 'per-bar PineTS inputs (licensed data)')


def results_dir(sub: str | None = None) -> Path:
    """Aggregate results: OUT_DIR/results[/sub]."""
    r = out_dir() / 'results'
    return r / sub if sub else r
