# Verdandi III: design

Status of this document: draft for Peter's approval (2026-10-22). Planning notes and decisions:
`odin3-ws/work/controller-scripts/briefs/verdandi-plan.md`.

## 1. Purpose

Verdandi III (Old Norse Verðandi, the Weaver of the Present Moment) helps a person understand the
architecture and design of a large program by watching a very small input travel through it: "the
Micro through the Macro". The first program is Odin III. A micro Verilog design is synthesized by the
real, current Odin III; Verdandi records every step and replays it as a playthrough the user walks
like a debugger: next, step in, step out, back, and jump to a stage. Each step shows the code that
ran, the data structures before and after, and where in the Verilog the touched objects came from.

It is for understanding, not for testing Odin III. It never changes Odin III.

## 2. Decisions (Peter, 2026-10-22)

- D1. A desktop app in the Wyrd III style (PySide6).
- D2. One playthrough of a whole run, end to end; it may be long, and the stages let the user skip
  ahead, jump in and jump back up. Lessons are later cut from the playthrough, not written apart.
- D3. No debugger (no gdb). Each step shows code and data structure contents; less important steps
  may be a higher-level explanation or a picture of the relevant slice of the data.
- D4. The method is general ("the Micro through the Macro"); Odin III is the first adapter.
- D6. Approach A, record then replay: it is for learning the flow (Peter chose it over live stepping
  and over trace points inside Odin III).
- D7. The finest level is the pass log (one entry per logged rewrite); trace points inside Odin III
  are a later option, not part of this design.
- D8. The playthrough ends at `write_blif` (the netlist handed to VTR); VPR stages are a later group.
- D9. The default playthrough is one small combined micro (a counter, an if/else register, a 4x4
  multiply and an add); `record` takes any design.
- D10. Notes: drafted from the Odin III paper and `docs/PASSES.md`, Peter edits them later; a step
  without a note gets a generated summary and a picture of its data slice.
- D11. ABC is opened up: each command of its script, including the K-LUT technology mapping
  (`if -K`), is a step shown as a graph transformation on the example (section 6a).
- D12. Its own package and app (`verdandi`, depends on the `odin3` package like Loki III); a Wyrd III
  Tools menu entry comes later.
- D5. It must follow code changes: everything is recorded from the current build and source tree;
  only short notes are written by hand, and a check flags notes whose anchor no longer exists.

## 3. Architecture

Two halves joined by a trace file, so the player does not depend on Odin III:

```
micro.v + arch ──> recorder (Odin III adapter, Python binding) ──> trace/ ──> player (PySide6)
                         │                                            ▲
                    ODIN3_ROOT source tree ── code locator ───────────┘ notes/ (anchored text)
```

- **Recorder** (`verdandi.odin3`): runs the production script through the `odin3` Python binding one
  pass at a time on a `Design`, snapshots the IR after each step, captures the pass log, and locates
  the code of each pass in the Odin III source tree. Writes a trace directory.
- **Trace** (`verdandi.trace`): a versioned, program-neutral format (section 5).
- **Player** (`verdandi.gui`): reads a trace and the notes; never imports `odin3`.
- **Notes** (`verdandi/notes/odin3/*.md`): short explanations keyed to anchors (a stage, a pass, a
  source function, a log rule). `verdandi check-notes` fails when an anchor is gone.

## 4. Levels of a playthrough (the step tree)

A playthrough is a tree. "Next" walks siblings, "in" opens children, "out" returns to the parent,
"back" undoes the last move (the trace is recorded, so back is free).

| Level | What a step is | Source of the data |
|---|---|---|
| L0 stage | A box of the paper's flow figure: Read architecture, Parse, Elaborate, Proc, FSM, Opt, Flatten, Width reduction, Hard-block mapping, Lower, ABC, Write BLIF | Pass names grouped by a stage map (data file, checked against `Odin3.passes()`) |
| L1 pass | One pass of the script, e.g. `opt -full` | `Design.run_pass` |
| L2 sub-step | A pass's documented parts, run one by one on a copy: `proc --stop-after clean|rmdead|prune|arst`, then `proc`; `opt` as `opt_expr`, `opt_merge`, `opt_muxtree`, `opt_reduce`, `opt_share`, `opt_dff`, `opt_clean` (order from the opt source); `fsm_detect` then `fsm`; Parse vs Elaborate from the PARSED and ELABORATED ASTs | `Design.copy()` + `run_pass` on the copy; marked "illustration" when the copy's result differs from the real pass's |
| L3 event | One logged action inside a step, e.g. `opt_expr: module 'm': <rule> on <type> '<cell>'` | The pass log at DEBUG level (`odin3_log_set_level`), parsed by per-pass patterns; passes without such lines have no L3 |

Every step carries: the IR (or AST) snapshot after it, the diff from the step before (objects added,
removed, changed), the provenance spans of the touched objects, the code locations, the log lines,
and its note if one matches.

## 5. Trace format (version 1)

A directory:

- `manifest.json`: format version, program (`odin3`), program version and ABI, source tree commit
  (`git rev-parse HEAD` of `ODIN3_ROOT`, or "unknown"), micro files, top, architecture, the script,
  the stage map version, record time.
- `steps.json`: the step tree: `id`, `parent`, `level`, `title`, `anchor` (e.g. `pass:opt_expr`),
  `snapshot` (file name), `diff`, `code` (list of `{file, line, end_line, function}`), `log` (lines),
  `illustration` (bool), `failed` (bool), `picture` (a graph file under `pic/`, for ABC steps). L2 and L3
  steps are ordinary child steps (`parent` set, `level` 2 or 3).
- `snap/<id>.json`: IR snapshot: modules, each with nodes (`id`, `name`, `type`, `params`, `pins`
  as `{port, bit, net}`, `sources`), nets (`id`, `name`, `drivers`, `sinks`, `sources`), wires; or an
  AST snapshot (`kind`, `sub`, `name`, `loc`, `children`). Deterministic order (by ID). `params` omits
  PROC-kind values: a `$proc`'s RTLIL body text is unbounded and outside the node-count size guard.
- `src/`: copies of the micro's Verilog (the player shows them; the user's file may change later).

Diffs match objects by ID within one design; across a `compact` (IDs renumbered) they match by name
and say so. Snapshots of a micro are small (hundreds of objects); a size guard refuses designs over a
limit (default 5000 nodes) with a clear message.

## 6. Code locator

For a pass name, the registering file is found by its `odin3_pass_def` usage string in
`src/passes/**` (and `src/frontends/**` for readers); the pass's files are that file's directory.
The name literal and the usage string normally sit on adjacent lines. A macro-registered family
(Odin III's `OPT_DEF` in `src/passes/opt/register.c`: the names in `k_pass_names`, the usage strings
~468 lines below) is found by a second clause, tried only when the first finds nothing: the file
contains the token `odin3_pass_def`, a literal equal to `"<name>"` and a usage literal anywhere in
the file. Requiring the token keeps a stray pass-name literal in an unrelated file (a reader's
format table) from winning.
Functions are found by a C function-definition scan of those files (name, start and end line). For
an L3 event, the rule name in the log line is searched in the pass's files to give the line that logs
it. Everything is read from `ODIN3_ROOT` at record time, so it follows the current source. No
external parser is needed; a scan that finds nothing gives the pass's files only.

## 6a. ABC as graph transformations

Odin III's `abc` pass hands each module's soft logic (one run per clock domain) to linked ABC with the
script `lib/abc/vtr.abc` (`strash; ifraig -v; scorr -v; dc2 -v; dch -f; if -K {K} -v; mfs2 -v;
print_stats`). Verdandi opens that step without changing Odin III:

1. On a copy of the design before `abc`, run `abc --lut K --via-blif DIR` to obtain the exact BLIF
   exchanged with ABC (the files the pass writes in DIR; the plan verifies their names).
2. Run the standalone ABC binary (`$ODIN3_ABC`, else `build/*/third_party/abc/abc`) on that input
   one command at a time, from the same script file read at record time (so a script change is
   followed): after each command `print_stats`, `write_dot` and `write_blif` give the step's numbers,
   its graph picture and its network.
3. Each command is an L2 step under the ABC stage, titled by what it does to the graph:
   - `strash`: the logic becomes an AIG (two-input ANDs and inverted edges), structurally hashed so
     equal subgraphs are shared;
   - `ifraig`, `scorr`: nodes proven equal (combinationally, then across registers) are merged;
   - `dc2`, `dch -f`: local rewriting and balancing of the AIG; `dch` keeps choice nodes, several
     equivalent structures for the mapper to pick from;
   - `if -K K` (the K-LUT technology mapping): every AIG node gets its K-feasible cuts, the mapper
     picks a cover of the AIG by cuts, each chosen cut becomes one K-input LUT whose truth table is
     the cut's function; shown as the AIG before and the LUT network after, with the example's
     depth (`lev`) from `print_stats` and its LUT count from the mapped network (or the pass log's
     `-> N LUTs`; counter2: 2 LUTs, depth 1, while its `nd` of 4 also counts the two output
     buffers);
   - `mfs2`: each LUT is simplified using don't-cares from its window (resubstitution).
   The notes for these steps explain the transformation in words and point at the example's numbers
   (nodes, levels, LUTs before and after).
4. The real `abc` pass then runs on the real design (L1), and its result is the next snapshot. When
   the standalone result differs from the linked one (its network node count `nd` from
   `print_stats`, compared with the linked run's), the L2 ABC steps are marked "illustration".

## 7. Player (Wyrd III style)

Main window panes:
- **Stage map**: the flow figure as boxes; the current stage lit; click to jump.
- **Step tree** with Next (N / Space), In (I / Enter), Out (O / Backspace), Back (B), stage jump
  (1-9), search by object name ("follow net q[3]": jump to every step that touched it).
- **Verilog**: the micro's source, with the provenance spans of the current step's touched objects
  highlighted.
- **Code**: the source file at the step's code location, function highlighted; tabs when several.
- **Data**: the snapshot as tables (nodes, nets) filtered to touched objects by default, an AST tree
  for parse/elaborate steps, and a picture of the touched slice (`write_dot`-style graph rendered with
  Graphviz `dot` when installed, else a table only).
- **Explanation**: the note for the step, else a generated summary ("opt_merge merged 2 cells: ...").
- **Diff** strip: added (green), removed (red), changed (amber) counts and lists.

`verdandi play` opens a trace; `verdandi-gui` opens a file dialog; Wyrd III can later add a Tools menu
entry (out of scope here).

## 8. Command line

- `verdandi record <files...> --top T [--arch ARCH.xml | --techlib LIB] [--k 6] [--script FILE]
  -o TRACE` (default script: the production flow `read_arch; read_verilog --nolatches --vtr-compat;
  proc; fsm; opt; flatten; opt -full; wreduce; hardmap; lower; abc --lut K; write_blif`, as
  tools/vtr-qor/qor_legs.py builds it). Exit codes: 0 ok, 1 a pass failed (trace written up to it),
  2 usage or environment error.
- `verdandi play TRACE`.
- `verdandi check-notes [--odin3-root DIR]`: every note anchor exists (pass names from
  `Odin3.passes()`, functions from the code locator); exit 1 lists the stale ones.
- `verdandi info TRACE`: steps per level, sizes.

## 9. Environment

Python 3.11+, `odin3` package (cffi binding; `ODIN3_LIB`), `ODIN3_ROOT` (source tree, for code),
PySide6 for the player (extra `gui`), Graphviz `dot` optional, a standalone ABC binary for the
opened-up ABC steps (`$ODIN3_ABC`, else `build/*/third_party/abc/abc` under `ODIN3_ROOT`; without one
the ABC stage has its L1 step only and a warning). Same setup as Loki III: CI installs the
odin3 v1.0.0 wheel and checks out the odin3 source at the matching tag.

## 10. Errors

A failing pass ends the recording with that step marked failed and its log kept (exit 1). A missing
`ODIN3_ROOT` records without code locations and warns. A DEBUG pattern that matches nothing gives no
L3 children (not an error). A trace of a newer format version is refused by an older player.

## 11. Testing

unittest; recorder tests on tiny micros written in the tests (a 2-bit counter, an always block with
if/else, a 4x4 multiply); trace round trip; diff on hand-made snapshots; code locator on a fixture
tree and on the real `ODIN3_ROOT` (skipped when absent); player smoke test offscreen
(`QT_QPA_PLATFORM=offscreen`): open a trace, Next, In, Out, Back, stage jump. ruff, mypy --strict.

## 12. Out of scope (later)

Lessons cut from playthroughs; trace points inside Odin III (a core change, Peter reviews); the VPR
stages (pack, place, route, with floorplan pictures); a Wyrd III Tools menu entry; adapters for other
programs; a web player for the docs site.

## 13. Visualization update (2026-10-23)

Peter reviewed a playthrough ("yes to all" D1-D9, brief `verdandi-viz-update.md`). These decisions
change the player, not the trace format: the snapshot already carries the nets and the AST. D1
(per-module playthroughs) shipped in V1; this section records D2-D4, the graph pane, and D8-D9,
the step's source at a chosen call depth and the directory zoom.

- **D2. Nets in the graph.** The Data pane's graph draws every net as an edge carrying a label.
  The core reports no net name on the recorded playthrough trace (every net record's name and
  aliases are empty, ports included; most nodes are unnamed too), so the fallback is qualified
  and traceable: a net whose source span covers an AST DECLARATOR or INSTANCE is labelled
  `<name> [<module>:<id>]`, and any other net `net <module>:<id>`; no edge is blank and no two
  unnamed nets share a label. Real net names need the recorder or the core to report the
  library's name and aliases (a core or recorder change, out of scope here; the trace format
  already has the room), not a player change. A "net names" checkbox hides and shows the edge
  labels. The Nets table shows the same (empty) names; the graph's fallbacks keep every edge
  legible.
- **D3. Which structure is shown.** The Data pane carries an explicit structure badge for the
  current step: "IR after <pass or stage> (netlist)" for an IR snapshot (a stage-anchored step
  names its stage), "AST (parsed)" or "AST (elaborated)" for an AST snapshot, "ABC network
  (picture)" for an ABC picture (with "ABC network: dot not available" beside the badge when the
  picture cannot be rendered), "symbol table" while the symbol table tab is visible, and
  "log event (no snapshot)" for a step without a snapshot. The badge follows the visible
  structure only: a hidden symbol table never names the badge. The symbol table becomes a shown
  structure: a table of scope (module), name, declaration and uses derived from the AST snapshot
  (a DECLARATOR or INSTANCE node declares a name, an IDENT node uses it), for the parse and
  elaborate steps. IR and PROC steps keep the IR view. A `$proc`'s RTLIL body is not part of a
  snapshot (section 5): the recorder's PROC-kind filter drops it, not only the size guard, so no
  per-node expand exists and none is added; showing the body needs a recorder change, out of
  scope here.
- **D4. The diff in colour.** The step diff is drawn on the IR graph as well as in the +/- log:
  an added node is solid green, a changed node amber, and a removed object a dashed red outline
  (a removed node or net has no place in the after snapshot, so it is drawn as its own node,
  labelled "removed <kind> <name or qualified id>" so it cannot be mistaken for a live edge
  label). An added or changed net colours its edge the same way. The +/- log stays as its own
  dock (the secondary view); the graph adds the spatial picture.
- **D8. The step's source at a chosen call depth.** The Code pane shows the exact lines of the
  function(s) behind the current step: each step `code` record carries file, line, end_line and
  function from `ODIN3_ROOT` (section 6), and the pane opens the record's file with that function
  span highlighted. A record that names a function but spans one line (a rule event's log call)
  is widened to the function's located definition, so depth 0 shows the body, not the log line;
  a record without a function keeps its own span (a pass record is its whole file). A depth
  control (0-5, default 0) sets how deep the code tree goes: depth 0 is
  the step's own functions only; depth 1 adds the bodies of their direct callees, and every
  further level adds the next ring of callees. A file with functions at several depths is one
  tab, each function highlighted in its depth's colour. Depth > 0 needs a call graph, read in
  this order:
  1. **The code-review-graph database of the Odin III checkout**, `ODIN3_ROOT/.code-review-graph/
     graph.db`, when that file exists and reads as a database. Function nodes carry `file_path`,
     `line_start` and `line_end`; `CALLS` edges name the caller and the callee, and a callee
     edge whose target is a bare name is resolved by function name (same file first, else the
     only match). The database is opened read-only: `graph.db` and its `-wal` are never
     written, though SQLite may create or touch the `graph.db-shm` shared-memory file beside it
     as read-side bookkeeping.
  2. **A static scan**, when no readable database is present: the section-6 C function-definition
     scan of the step's file finds the function spans, and a call-site scan of the function body
     (an identifier followed by `(`, C keywords and control statements excluded, comments and
     string literals skipped) names the
     callees, which are then resolved against the same file's definitions. A callee defined in
     another file is not followed by this fallback.
  A record without a function seeds every function its span intersects, so a whole-file pass
  record reaches all of its file's functions (a file scope); when its span meets no function,
  every function of the file seeds instead. The static scan seeds the same functions and scans
  only their bodies, so the two sources agree.
  A small note beside the control names the source in use ("call graph: code-review-graph DB",
  "call graph: code-review-graph DB (file scope)" when a file scope seeded the expansion,
  "call graph: static scan of <file>"), so the picture is never mistaken for one the database
  gave; the note names the missing source when there is none (no source tree, an unreadable
  database and an unreadable file). Depth 0 needs no call graph and adds no note.
- **D9. Directory zoom.** A Source dock carries a collapsible directory tree of `ODIN3_ROOT`,
  filled lazily: a directory's children are listed the first time it expands, and dot names are
  skipped, so opening the pane never walks the tree. The tree zooms to the current step's first
  `code` record: the path from the root to the record's file expands (`src`, `passes`, `proc.c`),
  the file item is highlighted, and a `.c` file expands to its functions (the section-6 scan)
  with the current function revealed. The tree keeps the keyboard (no selection, no focus), as
  the step tree does; clicking a file opens it in the Code pane as its own tab. Without a source
  tree the pane shows a note instead of a tree.
