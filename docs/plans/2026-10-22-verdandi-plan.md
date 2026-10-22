# Verdandi III Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** record a micro Verilog design through the current Odin III pass by pass (stages, passes, sub-steps, ABC commands, logged rewrites) into a trace, and replay it in a Wyrd III style player that shows the code, the data and the Verilog provenance of every step.

**Architecture:** the recorder (`verdandi.odin3`) drives the `odin3` Python binding and a standalone ABC and writes a program-neutral trace directory (`verdandi.trace`); the player (`verdandi.gui`, PySide6) reads only the trace, the notes and the Odin III source tree. Notes are short markdown files keyed to anchors that `verdandi check-notes` verifies against the current source.

**Tech Stack:** Python 3.11+, `odin3` (cffi binding; `ODIN3_LIB`), PySide6 (extra `gui`), Graphviz `dot` (optional), ABC binary (optional), unittest, ruff, mypy --strict.

**Spec:** `docs/specs/2026-10-22-verdandi-design.md` (approved by Peter 2026-10-22). Section numbers below refer to it.

## Global Constraints

- Python 3.11+, no 3.12-only syntax. Runtime: standard library + `odin3`; PySide6 only under `verdandi/gui/`.
- Never change Odin III; read `ODIN3_ROOT` only. Never write outside the trace directory, the worktree and the system temp directory.
- Exit codes: 0 ok; 1 a pass failed (trace written up to it) or stale notes; 2 usage or environment error.
- Trace `FORMAT_VERSION = 1`; a player refuses a trace with a higher version.
- Deterministic snapshots: objects ordered by ID, `json.dumps(..., sort_keys=True, indent=1)`; time stamps only in `manifest.json`.
- Size guard: refuse when any snapshot exceeds `--max-nodes` nodes (default 5000).
- Default script (spec 8): `read_arch {arch}; read_verilog --nolatches --vtr-compat {files}; proc; fsm; opt; flatten; opt -full; wreduce; hardmap; lower; abc --lut {k}; write_blif {out}`; with `--techlib LIB` the first command is `read_techlib {lib}` and `hardmap` is omitted.
- ruff (line length 100) and `mypy --strict` clean; no `# noqa`, no `# type: ignore`.
- Never commit to main. Four PRs (groups A-D); merge each on green CI before starting the next group.
- Tests that need the Odin III library skip with `unittest.skipUnless(HAVE_ODIN3, ...)`; tests that need ABC, Graphviz or VTR skip the same way (helpers in `tests/helpers.py`).

## Review Focus

1. A pass that fails in the middle of the script: the trace up to it loads, the failed step is last and marked failed with its log; exit 1 (Task 6, `test_record_failing_pass`).
2. Objects removed by `opt_clean` or renumbered by `compact` between steps: no crash on dead IDs, diffs across `compact` match by name (Task 4, `test_diff_across_compact`; Task 3, `test_dead_objects_skipped`).
3. A pass whose DEBUG lines have no pattern, or whose format changed: no L3 children, no error (Task 8, `test_events_unknown_pass`).
4. `ODIN3_ROOT` unset or not a git tree, or no ABC binary: record without code links / without ABC sub-steps, warn once, manifest says `"unknown"` (Task 5, `test_locator_without_root`; Task 7, `test_abc_without_binary`).
5. Micro sources with CRLF line ends or tabs: the Verilog highlight covers the right characters (Task 11, `test_highlight_columns`).

---

## Group A: package, trace, snapshots (PR A)

### Task 1: Repository scaffold and CLI skeleton

**Files:**
- Create: `pyproject.toml`, `verdandi/__init__.py`, `verdandi/cli.py`, `CLAUDE.md`, `README.md`, `.gitignore`, `.github/workflows/ci.yml`, `tests/__init__.py`, `tests/helpers.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: console script `verdandi = "verdandi.cli:main"`; `main(argv: list[str] | None = None) -> int` with subcommands `record`, `play`, `check-notes`, `info`; until their task, each subcommand prints `verdandi <name>: not implemented yet` and returns 2.
- Produces: `tests/helpers.py`: `HAVE_ODIN3: bool` (importing `odin3` and `odin3.default()` succeed), `HAVE_ABC: bool` (`abc_binary()` not None), `HAVE_DOT: bool` (`shutil.which("dot")`), `ODIN3_ROOT: Path | None` (env var, existing dir), `abc_binary() -> str | None` (spec 9 lookup: `$ODIN3_ABC`, else `ODIN3_ROOT/build/*/third_party/abc/abc`, first executable).

- [ ] **Step 1: Write the failing tests** in `tests/test_cli.py`:

```python
def test_help_lists_subcommands(self) -> None:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as ex:
        main(["--help"])
    self.assertEqual(ex.exception.code, 0)
    for name in ("record", "play", "check-notes", "info"):
        self.assertIn(name, out.getvalue())

def test_unknown_subcommand_is_usage_error(self) -> None:
    with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ex:
        main(["nope"])
    self.assertEqual(ex.exception.code, 2)
```

- [ ] **Step 2: Run** `python -m unittest tests.test_cli -v`; expected: FAIL (ImportError).
- [ ] **Step 3: Implement** `verdandi/cli.py` with argparse subparsers; `pyproject.toml` (setuptools; name `verdandi`; `dependencies = ["odin3"]`; `[project.optional-dependencies] gui = ["PySide6>=6.6"]`; scripts `verdandi` and, from Task 10, `verdandi-gui`; ruff line-length 100; mypy strict).
- [ ] **Step 4: CI** `.github/workflows/ci.yml`, modelled on drpaj12/loki's: env `ODIN3_WHEEL: https://github.com/drpaj12/odin3/releases/download/v1.0.0/odin3-1.0.0-py3-none-linux_x86_64.whl`; checkout drpaj12/odin3 at `v1.0.0` into `odin3-src` (`ODIN3_ROOT`); `pip install cffi "$ODIN3_WHEEL" PySide6 ruff mypy -e .`; apt `graphviz`; jobs `lint` (ruff, mypy --strict verdandi tests) and `test` (`QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -t . -v`). No ABC build (ABC tests skip in CI).
- [ ] **Step 5: `CLAUDE.md`** (what Verdandi is; setup `python3 -m venv .venv && .venv/bin/pip install cffi -e ".[gui]" ruff mypy` plus the local Odin III env lines `PYTHONPATH=<odin3>/plugins/python ODIN3_LIB=<odin3>/build/release/libodin3.so ODIN3_ROOT=<odin3>`; test and lint commands; the Global Constraints as rules) and `README.md` (one paragraph plus the Yggdrasil III Documentation block used in the other repos).
- [ ] **Step 6: Run** the tests, `ruff check .`, `mypy --strict verdandi tests`; expected: PASS, clean.
- [ ] **Step 7: Commit** `feat: package scaffold and CLI skeleton`; push.

### Task 2: Trace model and file format

**Files:**
- Create: `verdandi/trace.py`, `tests/test_trace.py`

**Interfaces:**
- Produces (spec 5):

```python
FORMAT_VERSION = 1
@dataclass(frozen=True)
class ObjRef: module: str; kind: str; id: int; name: str          # kind: "node" | "net" | "wire"
@dataclass
class Diff: added: list[ObjRef]; removed: list[ObjRef]; changed: list[ObjRef]; by_name: bool
@dataclass
class CodeRef: file: str; line: int; end_line: int; function: str | None
@dataclass
class Step:
    id: str; parent: str | None; level: int; title: str; anchor: str
    snapshot: str | None = None; diff: Diff | None = None
    code: list[CodeRef] = field(default_factory=list); log: list[str] = field(default_factory=list)
    illustration: bool = False; failed: bool = False
    picture: str | None = None          # file under pic/ (ABC dot), optional
@dataclass
class Manifest:
    version: int; program: str; program_version: str; abi: int; source_commit: str
    files: list[str]; top: str; arch: str | None; script: str; stage_map_version: int; recorded: str
class Trace:
    def __init__(self, directory: Path, manifest: Manifest, steps: list[Step]) -> None
    def children(self, step_id: str | None) -> list[Step]    # None: the roots (level 0)
    def step(self, step_id: str) -> Step
    def snapshot(self, step: Step) -> dict[str, Any] | None  # loads snap/<file>, cached
def save(directory: Path, manifest: Manifest, steps: list[Step],
         snapshots: dict[str, dict[str, Any]], sources: list[Path],
         pictures: dict[str, Path] | None = None) -> None
def load(directory: Path) -> Trace                           # ValueError("trace format N is newer than 1")
```
Step ids are `"s0001"`, `"s0002"`, ... in recording order; levels 0-3 (spec 4).

- [ ] **Step 1: Failing tests:** `test_round_trip` (save, load: manifest and steps equal; saving the loaded trace again gives byte-identical `steps.json`), `test_refuses_newer_version` (manifest version 2: `load` raises `ValueError` whose text contains `"newer"`), `test_children_order` (roots and children come back in insertion order), `test_sources_copied` (a source with CRLF and a tab lands in `src/` byte for byte), `test_snapshot_cached` (two `snapshot()` calls return the same object).
- [ ] **Step 2: Run**, expected FAIL. **Step 3: Implement** with `dataclasses.asdict` and explicit `from_dict` helpers. **Step 4: Run**, PASS. **Step 5: Commit** `feat: trace model and format v1`; push.

### Task 3: IR and AST snapshots (Odin III adapter)

**Files:**
- Create: `verdandi/odin3/__init__.py`, `verdandi/odin3/snapshot.py`, `tests/micros.py`, `tests/test_snapshot.py`

**Interfaces:**
- Consumes: `odin3.Design`, `Design.modules()`, `Module.name/nodes()/nets()/wires()`, `Node.id`-bearing `ref`, `Node.type_name/name/params/pins()/sources()/is_live()`, `Pin.port/bit/net`, `Net.name/drivers()/pins()/sources()/aliases()`, `Design.ast()`, `Ast.form/roots`, `AstNode.kind/sub/name/loc/children` (read `plugins/python/odin3.py` in `ODIN3_ROOT` for exact names before coding).
- Produces: `ir_snapshot(design: odin3.Design) -> dict[str, Any]` = `{"kind": "ir", "modules": [{"name", "nodes": [{"id", "name", "type", "params", "pins": [{"port", "bit", "net"}], "sources": [[file, line, col, end_line, end_col]]}], "nets": [{"id", "name", "drivers": [node ids], "sinks": [node ids], "sources": [...]}], "wires": [{"id", "name"}]}]}`; `ast_snapshot(design, form: str) -> dict[str, Any] | None` = `{"kind": "ast", "form": "PARSED"|"ELABORATED", "roots": [{"kind", "sub", "name", "loc", "children": [...]}]}`; `node_count(snapshot) -> int`; `keep_all_asts(design) -> None` (calls `odin3_design_set_keep_ast` with `ODIN3_KEEP_AST_ALL`).
- Produces: `tests/micros.py`: `COUNTER2` (2-bit counter with synchronous reset), `IFELSE_REG` (`always @(posedge clk) if (en) q <= a & b; else q <= q;`), `MUL4` (4x4 multiply), `PLAYTHROUGH` (the four together in one top, used in Task 12); each a `(top: str, text: str)` pair.

- [ ] **Step 1: Failing tests** (skip without `HAVE_ODIN3`; write the micro to a temp file; techlib script without hardmap):
  - `test_counter_snapshot`: after `read_verilog` and `proc`, some node has `type == "$dff"` and a source whose line is the line of `always` in `COUNTER2`.
  - `test_snapshot_deterministic`: two `ir_snapshot` calls give equal `json.dumps(sort_keys=True)`.
  - `test_dead_objects_skipped`: after `opt; opt_clean`, every listed node is live (cross-check: each listed id resolves to a live node).
  - `test_ast_forms`: with `keep_all_asts` before `read_verilog`, `ast_snapshot(d, "PARSED")` and `"ELABORATED"` are both not None and the ELABORATED roots name the top.
- [ ] **Step 2-4:** run (FAIL), implement, run (PASS). Note in `snapshot.py`: `Design.ast()` returns the newest store; for the PARSED form walk `odin3_design_get_ast_at` by index and pick the store with `form == PARSED` of the same run.
- [ ] **Step 5: Commit** `feat: IR and AST snapshots`; push. **Open PR A** (Tasks 1-3).

---

## Group B: recorder (PR B)

### Task 4: Diff

**Files:** Create `verdandi/diff.py`, `tests/test_diff.py`.

**Interfaces:** `diff(before: dict[str, Any] | None, after: dict[str, Any], *, by_name: bool = False) -> Diff`. Key = `(module, kind, id)` (or `(module, kind, name)` when `by_name`); changed = same key, different `type`, `params`, `pins`, `drivers` or `sinks`. `before=None` makes everything "added". AST snapshots diff to an empty `Diff` (the player shows AST steps as trees).

- [ ] **Step 1: Failing tests** on hand-made snapshot dicts: `test_added_removed_changed` (one of each, exact `ObjRef`s), `test_diff_across_compact` (same names with new ids: `by_name=True` gives no added/removed), `test_empty_diff`, `test_none_before`.
- [ ] **Steps 2-5:** run, implement, run, commit `feat: snapshot diff`; push.

### Task 5: Code locator

**Files:** Create `verdandi/odin3/locator.py`, `tests/test_locator.py`, `tests/fixture_src/src/passes/demo/demo.c` (an `odin3_pass_def` initializer whose usage string is `"demo [--x]: does a demo"`, a function `static int demo_helper(int a)` and `odin3_status demo_pass_run(...)`, a `odin3_log(ODIN3_LOG_DEBUG, "demo: module '%s': %s on %s '%s'", ...)` line).

**Interfaces:** `class Locator:` `__init__(self, root: Path | None)`; `pass_files(self, name: str) -> list[Path]`; `functions(self, path: Path) -> list[CodeRef]`; `find_text(self, files: list[Path], text: str) -> list[CodeRef]`; `commit(self) -> str` (`git -C root rev-parse HEAD`, else `"unknown"`). Paths in `CodeRef.file` are relative to `root`.

- [ ] **Step 1: Failing tests:** `test_fixture_pass_found` (`pass_files("demo")` is `[.../demo/demo.c]`), `test_functions_spans` (both functions with their exact first and last line numbers), `test_find_text` (the DEBUG format line found with its line number), `test_locator_without_root` (`Locator(None)`: empty lists, commit `"unknown"`), `test_real_tree` (skip without `ODIN3_ROOT`: `pass_files("proc")` contains `src/passes/proc/proc_pass.c`; `pass_files("hardmap")` contains `src/passes/partial_map/register.c`; `pass_files("read_verilog")` is not empty).
- [ ] **Step 3: Implement:** registering file = a `.c` under `src/passes` or `src/frontends` containing a string literal equal to `"<name>"` followed (within 3 lines) by a literal starting with `"<name> "` or `"<name>:"` or equal to `"<name>"` (the usage string); the 3-line rule is the first clause and keeps its distance requirement. When no file matches, a second clause: a `.c` under those roots that contains the token `odin3_pass_def` and both a literal equal to `"<name>"` and a usage literal (`"<name>"`, starts with `"<name> "` or `"<name>:"`) anywhere in the file also registers (the `OPT_DEF` family: `src/passes/opt/register.c` holds the names in `k_pass_names` ~468 lines above the usage strings; a file without the token, such as `src/passes/abc/alias.c` or `allow.c` with its pass-name literals, cannot win). Return it plus the other `.c` files of its directory when that directory is not `src/passes` itself. Function scan: a line at column 0 matching `^[A-Za-z_][\w \*]*\b(\w+)\s*\([^;]*$` whose body opens with `{` on that line or the next; end = matching closing brace at column 0.
- [ ] **Steps 4-5:** run, commit `feat: code locator`; push.

### Task 6: Recorder: stages (L0), passes (L1), parse and elaborate

**Files:** Create `verdandi/odin3/stages.json`, `verdandi/odin3/record.py`, `tests/test_record.py`. Modify `verdandi/cli.py` (wire `record`, `info`).

**Interfaces:**
- `stages.json` = `{"version": 1, "stages": [{"title": "Read architecture", "passes": ["read_arch", "read_techlib"]}, {"title": "Parse and elaborate", "passes": ["read_verilog"]}, {"title": "Processes", "passes": ["proc"]}, {"title": "State machines", "passes": ["fsm"]}, {"title": "Optimisation", "passes": ["opt"]}, {"title": "Flatten", "passes": ["flatten"]}, {"title": "Width reduction", "passes": ["wreduce"]}, {"title": "Hard-block mapping", "passes": ["hardmap", "partial_map"]}, {"title": "Lower", "passes": ["lower"]}, {"title": "ABC: logic optimisation and K-LUT mapping", "passes": ["abc"]}, {"title": "Write BLIF", "passes": ["write_blif"]}]}`. A pass not listed gets its own stage titled by its name.
- `record(files: list[Path], top: str, out: Path, *, arch: Path | None = None, techlib: Path | None = None, k: int = 6, script: str | None = None, odin3_root: Path | None = None, max_nodes: int = 5000, abc: str | None = None) -> int`.
- `default_script(files, top, *, arch, techlib, k, blif_out) -> str` (Global Constraints text; `read_verilog` gets `-top {top}` only if the Odin III `read_verilog` usage string has it: check `Odin3.passes()`/usage first, else run `hierarchy -top {top}` after it).
- CLI: `verdandi record FILES... --top T (--arch X | --techlib L) [--k 6] [--script FILE] [--max-nodes N] -o TRACE`; `verdandi info TRACE` prints steps per level and the snapshot total size.

- [ ] **Step 1: Failing tests** (skip without odin3; techlib from `ODIN3_ROOT/lib/` or the wheel's techlib, whichever `odin3-flow` uses: check `tools/flow/odin3_flow.py` first):
  - `test_record_counter`: exit 0; every L1 step has a snapshot and a parent L0 step whose title is the stage of its pass; the `read_verilog` L1 step has two L2 children titled `"Parse"` and `"Elaborate"` with AST snapshots; `src/` holds the micro.
  - `test_record_failing_pass`: script `read_techlib ...; read_verilog ...; proc --no-such-flag`: exit 1; last step failed with a non-empty log; `load()` works.
  - `test_size_guard`: `max_nodes=3`: exit 2, stderr names the step.
  - `test_stage_map_passes_exist`: every pass in `stages.json` is in `odin3.default().passes()`.
- [ ] **Step 3: Implement:** split the script on `;`; `keep_all_asts` before the first command; run each with `Design.run_pass(name, args)` inside `odin3.default().capture_log()`; the log lines are the step's `log`; snapshot after each; manifest from `Odin3.version()/abi_version()` and `Locator.commit()`; code refs from `Locator.pass_files` (one `CodeRef` per file, `line=1`, `end_line` = file length) refined by `functions` in Task 8.
- [ ] **Steps 4-5:** run, commit `feat: recorder stages and passes`; push.

### Task 7: ABC opened up (spec 6a)

**Files:** Create `verdandi/odin3/abcsteps.py`, `tests/test_abcsteps.py`. Modify `verdandi/odin3/record.py`. (The ABC notes are written in Task 9.)

**Interfaces:**
- `abc_script(odin3_root: Path | None, k: int) -> list[str]`: the commands of `lib/abc/vtr.abc` (comments and blank lines dropped, `{K}` replaced), from the source tree; when absent, the spec's fallback list `["strash", "ifraig -v", "scorr -v", "dc2 -v", "dch -f", f"if -K {k} -v", "mfs2 -v"]`; the final `print_stats` is dropped (it is added after every command).
- `capture_abc_input(design: odin3.Design, k: int, workdir: Path) -> list[Path]`: runs `abc --lut {k} --via-blif {workdir}` on `design.copy()`; returns the BLIF files ABC read (verify the file naming in `src/passes/abc/run.c` around `choose_dir`; one per module and clock domain).
- `run_abc_steps(abc: str, blif: Path, commands: list[str], workdir: Path) -> list[AbcStep]` with `@dataclass class AbcStep: command: str; stats: dict[str, int]; dot: Path; blif: Path; log: list[str]`; one ABC process per command prefix (`read_blif in; cmd1; ...; cmdN; print_stats; write_dot sN.dot; write_blif sN.blif`), so each step's files come from ABC itself. `stats` parses `print_stats` (`i/o`, `lat`, `and` or `nd`, `lev`, and `edge` when present).
- `TITLES: dict[str, str]`: `strash` "AIG: structural hashing", `ifraig` "Merge equivalent nodes", `scorr` "Merge equivalent registers", `dc2` "Rewrite and balance", `dch` "Rewrite with choices", `if` "K-LUT technology mapping (cuts and cover)", `mfs2` "Simplify LUTs with don't-cares".
- Recorder (Task 6's `record`): before the real `abc` pass, if an ABC binary is found, add one L2 step per command under the ABC L1 step: title from `TITLES`, anchor `abc:<command word>`, `picture` = the dot file, `log` = ABC's output, snapshot = None; after the real pass, set `illustration=True` on them when the last step's network node count `nd` differs from the linked run's `nd` (the first `print_stats` line of the ABC L1 log, the run the replay follows); `nd` counts LUTs and one-input buffer nodes alike, so it is not the LUT count. The replay opens up run 0 only (the first module and clock domain): a design with several clock domains shows the first run's transformations under that L1 step, and the other runs are not opened up.

- [ ] **Step 1: Failing tests:** `test_abc_script_from_tree` (skip without `ODIN3_ROOT`: first command `strash`, an `if -K 6 -v` command present, no `print_stats`), `test_abc_steps_counter` (skip without ABC: 7 `AbcStep`s; after `strash` `stats["and"] > 0`; after `if` `stats["nd"] > 0`; every dot file exists and starts with `digraph`), `test_abc_without_binary` (record with `abc=None` and no `$ODIN3_ABC`: the ABC L1 step has no children, the warning appears once in stderr, exit 0).
- [ ] **Steps 2-5:** run, implement, run, commit `feat: ABC script steps as graph transformations`; push.

### Task 8: Sub-steps (L2) and logged events (L3)

**Files:** Create `verdandi/odin3/substeps.py`, `verdandi/odin3/events.py`, `tests/test_substeps.py`, `tests/test_events.py`. Modify `record.py`.

**Interfaces:**
- `SUBSTEPS`: `proc` -> `["proc --stop-after clean", "proc --stop-after rmdead", "proc --stop-after prune", "proc --stop-after arst", "proc"]` (each from a fresh copy of the before design: they are cumulative stop points); `fsm` -> `["fsm_detect", "fsm"]` (in sequence on one copy).
- `OPT_PROLOGUE = ["opt_expr", "opt_merge -nomux"]`, `OPT_LOOP = ["opt_muxtree", "opt_reduce", "opt_merge", "opt_dff", "opt_clean", "opt_expr"]` with `"opt_share"` inserted after `opt_merge` for `opt -full` (from `src/passes/opt/opt_loop.c` `k_default_loop`, Yosys order); the loop repeats while the snapshot changes, at most 10 iterations; each iteration is an L2 group step "Iteration n" with the sub-passes as its children (level 3 is then used for events of those sub-passes).
- `expand(before: odin3.Design, command: str) -> list[tuple[str, dict[str, Any], list[str]]]` (title, snapshot, log); `matches(a: dict, b: dict) -> bool` (equal multisets of node types per module and equal net counts).
- `PATTERNS: dict[str, list[re.Pattern[str]]]`; first entry `"opt_expr": [re.compile(r"^opt_expr: module '(?P<module>[^']*)': (?P<rule>\S+) on (?P<type>\S+) '(?P<cell>[^']*)'")]`. Add one pattern per DEBUG format that names an object, found with `grep -rn ODIN3_LOG_DEBUG src/passes` (abc, flatten, fsm, lower, partial_map, opt). `events(pass_name: str, log: list[str]) -> list[tuple[str, str]]` = (title like `"opt_expr: const_and on $and '$c12'"`, anchor `rule:<pass>:<rule>`).
- Recorder: while a pass or sub-pass runs, inside `capture_log()`, call `odin3_log_set_level(ODIN3_LOG_DEBUG)` (capture_log restores the level on exit); events become children of the step; each event's code ref = `Locator.find_text(pass files, the format text before the first %)`.

- [ ] **Step 1: Failing tests:** `test_proc_substeps_counter` (5 children, the last `matches` the real `proc` snapshot, none marked illustration), `test_opt_order_from_source` (skip without `ODIN3_ROOT`: the sequence of `ODIN3_OPT_SUB_*` names in `k_default_loop` equals `OPT_LOOP` without `opt_share` mapped to pass names; fails when Odin III changes the order), `test_opt_iterations_reach_fixed_point` (`IFELSE_REG`: last iteration's snapshot equals the one before it), `test_events_opt_expr` (micro `assign y = a & 1'b0;`: at least one event whose anchor starts `rule:opt_expr:`), `test_events_unknown_pass` (`events("nope", ["x"])` is empty).
- [ ] **Steps 2-5:** run, implement, run, commit `feat: sub-steps and logged events`; push. **Open PR B** (Tasks 4-8).

---

## Group C: notes and player (PR C)

### Task 9: Notes and check-notes

**Files:** Create `verdandi/notes.py`, `verdandi/notes/odin3/*.md`, `tests/test_notes.py`. Modify `cli.py` (`check-notes`).

**Interfaces:** note file = first line `anchor: <anchor>` (one of `stage:<title>`, `pass:<name>`, `func:<name>`, `rule:<pass>:<rule>`, `abc:<command>`), a blank line, then at most 15 lines of markdown. `load_notes(directory: Path) -> dict[str, str]`; `stale(notes: dict[str, str], passes: set[str], locator: Locator, stage_titles: set[str]) -> list[str]` (`abc:` anchors are checked against `abc_script`'s command words).
Notes to write (plain words, the why; every claim checked against the source or the paper, Part II stage sections, and `docs/PASSES.md`): one per stage in `stages.json`; `pass:proc`, `pass:opt_expr`, `pass:opt_merge`, `pass:opt_clean`, `pass:hardmap`, `pass:lower`, `pass:flatten`, `pass:wreduce`; `abc:strash`, `abc:ifraig`, `abc:scorr`, `abc:dc2`, `abc:dch`, `abc:if`, `abc:mfs2` (spec 6a wording, extended with what to look for in the example's numbers).

- [ ] **Step 1: Failing tests:** `test_note_parse`, `test_missing_anchor_line_rejected` (ValueError naming the file), `test_stale_pass_flagged` (`pass:nope` stale), `test_shipped_notes_not_stale` (skip without odin3 and `ODIN3_ROOT`), CLI `check-notes` exit 0 on the shipped notes and 1 on a temp dir with a stale note.
- [ ] **Steps 2-5:** run, implement, write the notes, run, commit `feat: notes and check-notes`; push.

### Task 10: Player window and navigation

**Files:** Create `verdandi/gui/__init__.py`, `verdandi/gui/app.py`, `verdandi/gui/mainwindow.py`, `verdandi/navigator.py` (pure, no Qt), `tests/test_navigator.py`, `tests/test_gui_smoke.py`. Modify `pyproject.toml` (`verdandi-gui = "verdandi.gui.app:main"`), `cli.py` (`play`).

**Interfaces:** `class Navigator:` `__init__(self, trace: Trace)`; `current(self) -> Step`; `next(self) -> Step` (next sibling, else the parent's next sibling); `step_in(self) -> Step` (first child, or unchanged); `step_out(self) -> Step` (parent, or unchanged at a root); `back(self) -> Step` (previous position in a history list); `jump_stage(self, index: int) -> Step` (0-based root); `follow(self, name: str) -> list[Step]` (steps whose diff names an object with that name, in order). Keys (spec 7): N or Space next, I or Enter in, O or Backspace out, B back, 1-9 stage jump, Ctrl+F follow. Window structure and style follow `wyrd/gui/mainwindow.py` and `wyrd/gui/app.py` (read only; do not import wyrd): stage map (a row of buttons, one per root), step tree (QTreeView), title label, empty docks for the panes of Task 11.

- [ ] **Step 1: Failing tests:** `test_next_in_out_back`, `test_next_climbs_to_parent_sibling`, `test_jump_stage`, `test_follow_net`, `test_back_after_jump` (on a hand-made trace from Task 2's `save`); `test_gui_smoke` (offscreen: open the window on that trace, send N, I, O, B, 3 key events, the title label shows the expected step titles in order).
- [ ] **Steps 2-5:** run, implement, run, commit `feat: player window and navigation`; push.

### Task 11: Panes: Verilog, code, data, explanation, diff

**Files:** Create `verdandi/gui/verilogpane.py`, `codepane.py`, `datapane.py`, `explainpane.py`, `diffstrip.py`, `verdandi/graph.py` (pure: `slice_dot(snapshot, diff, rings: int = 1) -> str`), `tests/test_panes.py`, `tests/test_graph.py`.

**Interfaces:** each pane: `show(self, step: Step, trace: Trace) -> None`.
- Verilog pane: the files in `src/`; highlight every source span of the diff's objects (`[file, line, col, end_line, end_col]`, 1-based, columns counted in characters after removing a trailing `\r`; a tab counts as one character).
- Code pane: `ODIN3_ROOT/<CodeRef.file>` (root from the environment or the app's setting), scroll to `line`, highlight `line..end_line`; tabs when several refs; text `source not available: <file>` when missing.
- Data pane: IR steps: tables of the touched nodes and nets (checkbox "all objects"); AST steps: a tree; ABC steps: the step's `picture` rendered with `dot -Tsvg` into a `QSvgWidget`; IR steps also get `slice_dot` of the touched objects plus one ring of neighbours when `dot` is on PATH, else tables only.
- Explanation pane: note lookup order: the step's anchor, its pass (`pass:<name>`), its stage (`stage:<title>`); else a generated text: `"{title}: {n} added, {m} removed, {c} changed"` plus up to 5 event titles.
- Diff strip: counts in green/red/amber and a list.

- [ ] **Step 1: Failing tests:** `test_highlight_columns` (CRLF and tab sources: the highlighted text equals the expected identifier), `test_code_missing_file`, `test_data_filters_touched`, `test_explain_fallback_order` (anchor note beats pass note beats stage note beats generated), `test_slice_dot` (output starts `digraph`, contains the touched node ids and their neighbours only), `test_graph_without_dot` (PATH without dot: no exception, tables shown).
- [ ] **Steps 2-5:** run, implement, run, commit `feat: player panes`; push. **Open PR C** (Tasks 9-11).

---

## Group D: the playthrough (PR D)

### Task 12: Default playthrough, manual and hub entry

**Files:** Create `examples/playthrough/playthrough.v` (= `tests/micros.PLAYTHROUGH`), `examples/playthrough/README.md` (the one command that records it and the one that plays it), `docs/user/index.md`, `docs/user/conf.py` (Sphinx + MyST, the shared Yggdrasil III Manuals sidebar template from drpaj12/wyrd `docs/user/_templates/manuals.html` with a Verdandi III line added), `.github/workflows/pages.yml` (as wyrd's), `tests/test_playthrough.py`. Modify `README.md`.

- [ ] **Step 1: Failing test** `test_playthrough_records` (skip without odin3; with ABC and the VTR arch when available, else techlib and no ABC sub-steps): exit 0; every stage of `stages.json` that the script reaches has at least one L1 step; `check-notes` exit 0; `info` reports more than 30 steps.
- [ ] **Step 2: Implement** the example and the manual: install, `verdandi record` with the arch `k6_frac_N10_frac_chain_mem32K_40nm.xml` from `vtr_root`, `verdandi play`, the keys, the levels, the ABC steps, notes and `check-notes`, how a code change is followed (re-record).
- [ ] **Step 3: Walk it by hand** once: `verdandi play` the recorded trace, N through every stage, jump to ABC, step into `if -K`; write what you saw in the PR description.
- [ ] **Step 4: Commit** `docs: playthrough example and manual`; push. **Open PR D.** After it merges: ask Peter to enable Pages for verdandiIII; then a YggdrasilIII hub PR adds Verdandi III (README table row and Documentation block, `docs/pieces/verdandi.md`, the Manuals sidebar line in all four manuals, and a tree-figure side branch "Verdandi III / Tool & Experiment: the Micro through the Macro").
