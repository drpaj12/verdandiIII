# verdandi

Verdandi III: the Micro through the Macro, an interactive record-and-replay walk of a micro Verilog
design through the Odin III code. Part of Yggdrasil III.

Spec: `docs/specs/2026-10-22-verdandi-design.md`. Plan: `docs/plans/2026-10-22-verdandi-plan.md`.

## Setup

    python3 -m venv .venv && .venv/bin/pip install cffi -e ".[gui]" ruff mypy
    # Odin III for local runs (a release build of the checkout):
    export PYTHONPATH=<odin3>/plugins/python ODIN3_LIB=<odin3>/build/release/libodin3.so ODIN3_ROOT=<odin3>

## Build, test, lint

    .venv/bin/python -m unittest discover -s tests -t . -v
    .venv/bin/ruff check .
    .venv/bin/mypy --strict verdandi tests

## Rules

- Python 3.11+, no 3.12-only syntax. Runtime: standard library + `odin3`; PySide6 only under
  `verdandi/gui/`.
- Never change Odin III; read `ODIN3_ROOT` only. Never write outside the trace directory, the
  worktree and the system temp directory.
- Exit codes: 0 ok; 1 a pass failed (trace written up to it) or stale notes; 2 usage or environment
  error.
- Trace `FORMAT_VERSION = 1`; a player refuses a trace with a higher version.
- Deterministic snapshots: objects ordered by ID, `json.dumps(..., sort_keys=True, indent=1)`; time
  stamps only in `manifest.json`.
- Size guard: refuse when any snapshot exceeds `--max-nodes` nodes (default 5000).
- Default script (spec 8): `read_arch {arch}; read_verilog --nolatches --vtr-compat {files}; proc;
  fsm; opt; flatten; opt -full; wreduce; hardmap; lower; abc --lut {k}; write_blif {out}`; with
  `--techlib LIB` the first command is `read_techlib {lib}` and `hardmap` is omitted.
- ruff (line length 100) and `mypy --strict` clean; no `# noqa`, no `# type: ignore`.
- Never commit to `main`. Four PRs (groups A-D); merge each on green CI before starting the next
  group.
- Tests that need the Odin III library skip with `unittest.skipUnless(HAVE_ODIN3, ...)`; tests that
  need ABC, Graphviz or VTR skip the same way (helpers in `tests/helpers.py`).
