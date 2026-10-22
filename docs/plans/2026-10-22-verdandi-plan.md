# Verdandi III Implementation Plan

> **For agentic workers:** implement task by task (TDD: failing test, implement, pass, ruff, mypy,
> commit, push). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a recorder that runs the current Odin III on a micro Verilog design pass by pass and writes
a trace, and a PySide6 player that walks the trace as a playthrough (stages, passes, sub-steps,
logged events) showing code, data and Verilog provenance.

**Architecture:** recorder (`verdandi.odin3`, uses the `odin3` Python binding) -> trace directory
(`verdandi.trace`, program-neutral JSON) -> player (`verdandi.gui`, never imports `odin3`). Notes are
markdown files with anchors, checked against the current source.

**Tech Stack:** Python 3.11+, `odin3` (cffi binding, `ODIN3_LIB`), PySide6 (extra `gui`), Graphviz
`dot` optional, unittest, ruff, mypy --strict.

**Spec:** `docs/specs/2026-10-22-verdandi-design.md` (read it first; section numbers below refer to it).

## Global Constraints

- Python 3.11+ (no 3.12-only syntax). Runtime core is standard library + `odin3`; PySide6 only under
  `verdandi/gui/`.
- Never change Odin III; read its source tree (`ODIN3_ROOT`) only.
- Exit codes: 0 ok; 1 a pass failed / stale notes; 2 usage or environment error.
- Trace format version 1 (spec 5); the player refuses a newer version.
- Deterministic output: snapshots ordered by ID, JSON with sorted keys, no timestamps inside
  snapshots (only in the manifest).
- Size guard: refuse a design whose IR exceeds 5000 nodes after any step (option `--max-nodes`).
- ruff (line length 100) and `mypy --strict` clean; no `# noqa` / `# type: ignore`.
- Never commit to main; one PR per task group (A, B, C, D below); merge on green CI.

## Review Focus

1. A pass that fails mid-script: the trace up to it is written and loadable, the failed step shows
   its log; exit 1 (Task 6 test `test_record_failing_pass`).
2. `compact` or `opt_clean` renumbering/removing objects between steps: diffs match by name across a
   compact and never crash on dead IDs (Task 4 test `test_diff_across_compact`).
3. A pass with no DEBUG pattern or a pattern that no longer matches after an Odin III change: no L3
   children, no error (Task 7 test `test_events_unknown_pass`).
4. `ODIN3_ROOT` missing or at a different commit than the library: record without code, warn, and the
   manifest says "unknown" (Task 5 test `test_locator_without_root`).
5. The player opened on a trace whose `src/` Verilog has CRLF line endings or a tab: highlights land
   on the right columns (Task 10 test `test_highlight_columns`).

---

## Group A: package, trace format, snapshots (one PR)

### Task 1: Repository scaffold

**Files:** Create `pyproject.toml`, `verdandi/__init__.py`, `verdandi/cli.py`, `CLAUDE.md`,
`README.md`, `.github/workflows/ci.yml`, `tests/__init__.py`, `tests/test_cli.py`.

**Interfaces:** Produces console scripts `verdandi = verdandi.cli:main` and
`verdandi-gui = verdandi.gui.app:main` (the latter added in Task 9); `main(argv: list[str] | None) -> int`
with subcommands `record`, `play`, `check-notes`, `info` (stubs returning 2 "not implemented" until
their task).

- [ ] Test `test_help_lists_subcommands`: `main(["--help"])` exits 0 and the output names the four
  subcommands; `test_unknown_subcommand` returns 2.
- [ ] Implement with argparse; `pyproject.toml`: name `verdandi`, deps `["odin3"]`, extras
  `gui = ["PySide6>=6.6"]`, dev tools ruff, mypy.
- [ ] CI: copy the shape of drpaj12/loki `.github/workflows/ci.yml` (installs
  `cffi` and the odin3 v1.0.0 wheel `ODIN3_WHEEL`, checks out drpaj12/odin3 at `v1.0.0` into
  `odin3-src` as `ODIN3_ROOT`); jobs: lint (ruff, mypy), test (unittest), with
  `QT_QPA_PLATFORM=offscreen` and PySide6 installed for the GUI tests. Builds no ABC (the recorder
  tests use scripts without `abc`).
- [ ] `CLAUDE.md`: what it is, setup (`python3 -m venv .venv && .venv/bin/pip install -e ".[gui]"
  ruff mypy cffi` plus the local odin3 env lines), test/lint commands, rules (from spec Global
  Constraints).
- [ ] Commit, push.

### Task 2: Trace model and file format

**Files:** Create `verdandi/trace.py`, `tests/test_trace.py`.

**Interfaces (Produces):**
```python
FORMAT_VERSION = 1
@dataclass class CodeRef: file: str; line: int; end_line: int; function: str | None
@dataclass class Step: id: str; parent: str | None; level: int; title: str; anchor: str
    snapshot: str | None; diff: Diff | None; code: list[CodeRef]; log: list[str]
    illustration: bool = False; failed: bool = False
@dataclass class Diff: added: list[ObjRef]; removed: list[ObjRef]; changed: list[ObjRef]; by_name: bool
@dataclass class ObjRef: module: str; kind: str; id: int; name: str
@dataclass class Manifest: version: int; program: str; program_version: str; abi: int
    source_commit: str; files: list[str]; top: str; arch: str | None; script: str
    stage_map_version: int; recorded: str
class Trace: manifest: Manifest; steps: list[Step]
    def children(self, step_id: str | None) -> list[Step]
    def snapshot(self, step: Step) -> dict[str, Any]   # loads snap/<file>
def save(trace: Trace, snapshots: dict[str, dict[str, Any]], directory: Path, sources: list[Path]) -> None
def load(directory: Path) -> Trace                   # ValueError on version > FORMAT_VERSION
```
- [ ] Tests: `test_round_trip` (save then load equals, sorted-key JSON byte-identical on re-save),
  `test_refuses_newer_version`, `test_children_order` (insertion order kept), `test_sources_copied`
  (files land in `src/` with their bytes unchanged).
- [ ] Implement; commit, push.

### Task 3: IR and AST snapshots (Odin III adapter)

**Files:** Create `verdandi/odin3/__init__.py`, `verdandi/odin3/snapshot.py`, `tests/test_snapshot.py`,
`tests/micros.py` (inline micro Verilog strings: `COUNTER2`, `IFELSE_REG`, `MUL4`).

**Interfaces:**
- Consumes `odin3.Design`, `Module.nodes()/nets()/wires()`, `Node.type_name/name/params/pins/sources`,
  `Net.name/drivers/pins/sources/aliases`, `Design.ast()` (`Ast.roots`, `AstNode.kind/sub/name/loc/children`).
- Produces `ir_snapshot(design: odin3.Design) -> dict[str, Any]` and
  `ast_snapshot(design: odin3.Design, form: str) -> dict[str, Any] | None` (form "PARSED" or
  "ELABORATED"; None when not kept), and `node_count(snapshot) -> int`.
- [ ] Tests (skip when the odin3 library is not loadable): `test_counter_snapshot` (after
  `read_verilog` + `proc` the snapshot has a `$dff` node whose `sources` point into the micro, lines
  as written), `test_snapshot_deterministic` (two snapshots of the same design are equal),
  `test_dead_objects_skipped` (after `opt_clean` no node with `is_live() == False` appears),
  `test_ast_forms` (with keep-AST ALL set via `odin3_design_set_keep_ast`, both forms exist and the
  ELABORATED root names the top).
- [ ] Implement: keep-AST is set with `design.call("odin3_design_set_keep_ast", design.ptr,
  lib.ODIN3_KEEP_AST_ALL)` (verify the enum name in `include/odin3/odin3.h` near line 1298 first).
- [ ] Commit, push. **Open PR A** (Tasks 1-3).

---

## Group B: recorder (one PR)

### Task 4: Diff

**Files:** Create `verdandi/diff.py`, `tests/test_diff.py`.

**Interfaces:** `diff(before: dict, after: dict, *, by_name: bool = False) -> Diff`; changed = same
key, different `type`, `params`, `pins` or driver set.
- [ ] Tests on hand-made snapshots: `test_added_removed_changed`, `test_diff_across_compact`
  (IDs renumbered: with `by_name=True` the renamed-ID objects are "same", not add+remove),
  `test_empty_diff`.
- [ ] Implement; commit, push.

### Task 5: Code locator

**Files:** Create `verdandi/odin3/locator.py`, `tests/test_locator.py`, fixture `tests/fixture_src/`
(a tiny fake `src/passes/demo/demo.c` with an `odin3_pass_def` usage string `"demo [--x]"` and two
functions).

**Interfaces:** `class Locator(root: Path | None)`: `pass_files(name: str) -> list[Path]`,
`functions(path: Path) -> list[CodeRef]`, `find_text(name: str, text: str) -> list[CodeRef]`,
`commit() -> str` ("unknown" when not a git tree or root is None).
- [ ] Tests: `test_fixture_pass_found`, `test_functions_spans` (start/end lines of both fixture
  functions), `test_locator_without_root` (empty results, commit "unknown"), `test_real_tree_proc`
  (skipped without `ODIN3_ROOT`: `pass_files("proc")` includes `src/passes/proc/proc_pass.c`;
  `pass_files("hardmap")` resolves to `src/passes/partial_map/register.c`).
- [ ] Implement: the registering file is the `.c` under `src/passes` or `src/frontends` whose text has
  a string literal starting with `"<name> "` or equal to `"<name>"` inside a pass definition; function
  scan = a regex for C function definitions at column 0 (`^[a-z_].*\b(\w+)\(.*\)\s*\{?$` followed by
  a body) with brace counting for the end line. Keep it simple; misses only lose code links.
- [ ] Commit, push.

### Task 6: Recorder (L0 stages, L1 passes)

**Files:** Create `verdandi/odin3/record.py`, `verdandi/odin3/stages.json`, `tests/test_record.py`.

**Interfaces:** `record(files: list[Path], top: str, out: Path, *, arch: Path | None, techlib: Path |
None, k: int, script: str | None, odin3_root: Path | None, max_nodes: int) -> int` (exit code).
`stages.json`: `{"version": 1, "stages": [{"title": "Parse and elaborate", "passes": ["read_verilog"]}, ...]}`
covering the default script's passes in order (spec 4 L0 list).
- [ ] Tests: `test_record_counter` (techlib script without abc: steps exist for every pass, L0 parents
  group them per `stages.json`, each L1 step has a snapshot and a diff, `src/` holds the micro),
  `test_record_failing_pass` (a script with a bad pass argument: exit 1, the failed step is last,
  marked failed, its log kept, the trace loads), `test_size_guard` (`max_nodes=5` refuses with exit 2
  and a message naming the step), `test_stage_map_matches_passes` (every pass in `stages.json` is in
  `Odin3.passes()`).
- [ ] Implement: split the script on `;`, run each command with `Design.run_pass`, wrap each in
  `Odin3.capture_log()` to keep its lines, snapshot after each; `read_verilog` also records
  `ast_snapshot` PARSED and ELABORATED as two L2 children ("Parse", "Elaborate").
- [ ] `verdandi record` wired in `cli.py`.
- [ ] Commit, push.

### Task 7: L2 sub-steps and L3 events

**Files:** Create `verdandi/odin3/substeps.py`, `verdandi/odin3/events.py`, `tests/test_substeps.py`,
`tests/test_events.py`.

**Interfaces:**
- `SUBSTEPS: dict[str, list[str]]` = `{"proc": ["proc --stop-after clean", "proc --stop-after rmdead",
  "proc --stop-after prune", "proc --stop-after arst", "proc"], "opt": [<opt sub-passes in the order
  the opt pass runs them>], "fsm": ["fsm_detect", "fsm"]}`. Read the order of opt's sub-passes from
  `src/passes/opt/` before writing it, and add a test that fails if `opt`'s documented order changes
  (search the source for the sequence).
- `expand(design_before: odin3.Design, command: str) -> list[tuple[str, dict, list[str]]]`: runs the
  sub-steps on copies of `design_before` (a `--stop-after X` step starts from a fresh copy of the
  before design; a sequence of separate sub-passes such as opt's runs in order on one copy), returns (title, snapshot, log) per sub-step;
  `matches_real(last_snapshot, real_snapshot) -> bool` (node/net counts and types equal) sets the
  `illustration` flag when false.
- `events(pass_name: str, log: list[str]) -> list[tuple[str, str]]` (title, anchor `rule:<pass>:<rule>`):
  patterns per pass in a table; first pattern: `^opt_expr: module '(?P<m>[^']*)': (?P<rule>\S+) on
  (?P<type>\S+) '(?P<cell>[^']*)'` (from `src/passes/opt/expr.c` line ~322). Add the other passes'
  DEBUG formats found by `grep -rn ODIN3_LOG_DEBUG src/passes` (abc, flatten, fsm, lower,
  partial_map) as patterns where the line names an object.
- [ ] Tests: `test_proc_substeps_counter` (5 children, last equals the real proc snapshot, no
  illustration flag), `test_opt_substeps_order` (the source-order test), `test_events_opt_expr` (a
  micro with `a & 1'b0` yields an opt_expr event naming the rule), `test_events_unknown_pass` (no
  events, no error).
- [ ] Recorder: set the log level to DEBUG during each pass (`odin3_log_set_level`; note that
  `capture_log` raises the level to at least INFO; restore after), attach L2 and L3 children, code refs
  from the locator (`find_text` of the rule name for L3).
- [ ] Commit, push. **Open PR B** (Tasks 4-7).

---

## Group C: notes and the player (one PR)

### Task 8: Notes and check-notes

**Files:** Create `verdandi/notes.py`, `verdandi/notes/odin3/*.md` (one per L0 stage, and one each
for `proc`, `opt_expr`, `opt_clean`, `hardmap`, `lower`, `abc`), `tests/test_notes.py`.

**Interfaces:** note file = front matter `anchor: pass:proc` (or `stage:<title>`, `func:<name>`,
`rule:<pass>:<rule>`) + markdown body (at most ~15 lines, plain words, the why of the step).
`load_notes(dir) -> dict[str, str]`; `stale(notes, passes: set[str], locator) -> list[str]`.
- [ ] Tests: `test_note_parse`, `test_stale_pass_flagged` (an anchor `pass:nope` is stale),
  `test_real_notes_not_stale` (skipped without odin3: every shipped note's anchor exists).
- [ ] Write the notes from the Odin III paper's Part II stage descriptions and `docs/PASSES.md`
  (read only); every claim must match the source.
- [ ] `verdandi check-notes` wired; commit, push.

### Task 9: Player window and navigation

**Files:** Create `verdandi/gui/__init__.py`, `verdandi/gui/app.py`, `verdandi/gui/mainwindow.py`,
`verdandi/gui/navigator.py`, `tests/test_gui_nav.py`. Follow `wyrd/gui/mainwindow.py` and
`wyrd/gui/app.py` for structure, docks and style (read only; do not import wyrd).

**Interfaces:** `Navigator(trace)`: `current() -> Step`, `next()`, `step_in()`, `step_out()`,
`back()`, `jump_stage(index: int)`, `follow(name: str) -> list[Step]` (steps whose diff touches an
object with that name). Keys per spec 7.
- [ ] Tests (pure, no Qt): `test_next_in_out_back`, `test_jump_stage`, `test_follow_net`,
  `test_back_after_jump`. GUI smoke (offscreen): open a recorded trace, press N, I, O, B, 3; the step
  title label changes as expected.
- [ ] Implement window: stage map (row of buttons from the L0 steps), step tree, the panes as empty
  docks to be filled in Task 10; `verdandi play TRACE` and `verdandi-gui`.
- [ ] Commit, push.

### Task 10: Panes: Verilog, code, data, explanation, diff

**Files:** Create `verdandi/gui/verilogpane.py`, `codepane.py`, `datapane.py`, `explainpane.py`,
`diffstrip.py`, `tests/test_gui_panes.py`.

**Interfaces:** each pane has `show(step: Step, trace: Trace) -> None`.
- Verilog: highlight the `sources` spans of the diff's objects (1-based line/col from the snapshot).
- Code: open `CodeRef.file` under `ODIN3_ROOT` (from the environment or a setting), scroll to the
  line, highlight the function span; show "source not available" when the file is missing.
- Data: tables of touched nodes and nets (toggle "all objects"), AST tree for PARSED/ELABORATED
  steps, and a graph picture of the touched slice plus one neighbour ring via Graphviz `dot -Tsvg`
  (QSvgWidget) when `dot` is on PATH.
- Explanation: the note for the step's anchor (falling back to its pass, then its stage), else a
  generated sentence from the diff counts and the L3 events.
- [ ] Tests: `test_highlight_columns` (CRLF and tab sources), `test_code_missing_file`,
  `test_data_filters_touched`, `test_explain_fallback_order`, `test_graph_without_dot` (no `dot`:
  table only, no error).
- [ ] Commit, push. **Open PR C** (Tasks 8-10).

---

## Group D: the end-to-end playthrough (one PR)

### Task 11: The default playthrough and docs

**Files:** Create `examples/playthrough/counter_mul.v` (a counter, an if/else register, a 4x4
multiply and an add, in one small top), `examples/playthrough/README.md`, `docs/user/index.md`
(short manual: install, record, play, keys, notes), update `README.md` (Documentation block like the
other Yggdrasil III repos).
- [ ] Record with the default production script on k6_frac_N10_frac_chain_mem32K_40nm (`--arch`
  from the VTR tree in `vtr_root`) including `abc` when an ABC is available; check the playthrough
  from Read architecture to Write BLIF opens and walks with N only, and with stage jumps.
- [ ] Test `test_playthrough_records` (skipped without odin3/ABC/VTR): record succeeds, every L0
  stage has at least one step, `check-notes` passes.
- [ ] Commit, push. **Open PR D**; after merge, add Verdandi III to the YggdrasilIII hub (pieces page,
  README table row, Manuals sidebar, tree figure branch "Tool & Experiment: the Micro through the
  Macro") in a hub PR.
