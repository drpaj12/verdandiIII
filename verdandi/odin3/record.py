"""The recorder: run a script through Odin III pass by pass into a trace (spec 3, 4, 10).

The script is split on ``;``. Each command runs as one L1 pass step under an L0 stage step from
``stages.json`` (a pass the map does not list gets a stage titled by its name); the IR is
snapshotted after it and diffed against the previous IR snapshot. ``read_verilog`` also gives
two L2 children from the kept ASTs: "Parse" (PARSED) and "Elaborate" (ELABORATED). An ``abc``
pass with a standalone ABC binary gets one L2 child per script command (spec 6a): the same
commands replayed on the BLIF the pass exchanges, illustrated by ABC's own picture and log.
``proc``, ``fsm`` and ``opt`` also give L2 children (spec 4): their documented parts, run on a
copy of the design before the pass, ``opt`` as its loop's iterations; the copy's steps are
illustrations when its last result differs from the pass's. A pass with event patterns logs at
DEBUG for its step, and each object-naming line becomes an L3 event child whose code ref is the
line that logs it.
Every step carries a diff: an L1 IR step against the previous IR snapshot (by name across a
renumbering pass), an L0 stage against the previous stage's final IR snapshot, an L2 AST step
and an L2 ABC step the empty diff. A failing pass marks its step failed, writes the trace up
to it and returns 1; a pass, AST or stage snapshot over ``max_nodes`` refuses the recording
and returns 2, naming the step, while an over-size sub-step snapshot only warns (a copy's
intermediate state is not the pass's own result).
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from verdandi.diff import diff
from verdandi.odin3.abcsteps import (
    TITLES,
    _parse_stats,
    abc_script,
    capture_abc_input,
    find_abc,
    run_abc_steps,
)
from verdandi.odin3.events import PATTERNS
from verdandi.odin3.events import match as match_event
from verdandi.odin3.locator import Locator
from verdandi.odin3.snapshot import ast_snapshot, ir_snapshot, keep_all_asts, node_count
from verdandi.odin3.substeps import ITERATION_PREFIX, SUBSTEPS, expand, matches
from verdandi.trace import FORMAT_VERSION, CodeRef, Diff, Manifest, Step, save

_STAGES_FILE = Path(__file__).with_name("stages.json")

# The commands whose documented parts are recorded as L2 children (spec 4, L2; plan Task 8).
_EXPANDED = frozenset(SUBSTEPS) | {"opt"}

# A "-top" or "--top" word in a pass's usage line (not a longer option that ends in "top").
_TOP_OPTION = re.compile(r"(?:^|\s)--?top(?:\s|=|$)")

# Characters a module name or a script path cannot hold: they would split or break the script.
_SCRIPT_UNSAFE = set(';"\n')

# A plain Verilog identifier: the top is also a file name (<top>.blif) and an option argument.
_TOP_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")

# The abc pass's "--script FILE" value: a double-quoted path, else one blank-free word.
_ABC_SCRIPT = re.compile(r'--script\s+(?:"([^"]*)"|(\S+))')


def _check_top(top: str) -> None:
    """Refuse a top that is not one Verilog identifier: it would name a path or an option."""
    if _TOP_NAME.fullmatch(top) is None:
        raise ValueError(f"top module name {top!r} is not a Verilog identifier")


def stage_map() -> tuple[int, dict[str, str]]:
    """The stage map's version and its pass name -> stage title mapping.

    A missing (OSError) or malformed (ValueError) map raises; the recorder turns either into
    a clean message and exit 2.
    """
    try:
        data = json.loads(_STAGES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{_STAGES_FILE.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{_STAGES_FILE.name} is not a JSON object")
    version = data.get("version")
    stages = data.get("stages")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError(f"{_STAGES_FILE.name}: malformed version {version!r}")
    if not isinstance(stages, list):
        raise ValueError(f"{_STAGES_FILE.name}: no list of stages")
    titles: dict[str, str] = {}
    for stage in stages:
        if not isinstance(stage, dict):
            raise ValueError(f"{_STAGES_FILE.name}: a stage is not a JSON object")
        title = stage.get("title")
        passes = stage.get("passes")
        if not isinstance(title, str) or not isinstance(passes, list):
            raise ValueError(f"{_STAGES_FILE.name}: a stage needs a title and a pass list")
        for name in passes:
            if not isinstance(name, str):
                raise ValueError(f"{_STAGES_FILE.name}: pass name {name!r} is not a string")
            titles[name] = title
    return version, titles


def _quote(path: Path) -> str:
    """One script argument: the path double-quoted; a path cannot hold a quote or a semicolon."""
    text = str(path)
    if _SCRIPT_UNSAFE & set(text):
        raise ValueError(f"{text}: a path cannot hold a double quote or a semicolon")
    return f'"{text}"'


def _read_verilog_usage() -> str | None:
    """The build's ``read_verilog`` usage line, or None when odin3 is not importable."""
    try:
        import odin3

        library = odin3.default()
    except Exception:
        return None
    names = library.passes()
    if "read_verilog" not in names:
        return None
    index = names.index("read_verilog")
    return library.text(library.get("odin3_pass_get_help", "const char *", index))


def _read_verilog_takes_top() -> bool:
    """True when the build's ``read_verilog`` usage offers its own top selection option."""
    usage = _read_verilog_usage()
    if usage is None:
        return False
    return _TOP_OPTION.search(usage.split(": ", 1)[0]) is not None


def _has_pass(name: str) -> bool:
    """True when the build registers a pass of this name."""
    try:
        import odin3

        return name in odin3.default().passes()
    except Exception:
        return False


def default_script(
    files: list[Path],
    top: str,
    *,
    arch: Path | None,
    techlib: Path | None,
    k: int,
    blif_out: Path,
) -> str:
    """The production flow's script (spec 8, Global Constraints), for the given inputs.

    ``read_verilog`` gets its own top option only when the build's usage line has one; the
    current build does not, so ``hierarchy --top {top}`` follows it. With a techlib, ``hardmap``
    is omitted (the techlib's blocks are already read); with an arch, ``read_arch`` reads it.
    """
    if (arch is None) == (techlib is None):
        raise ValueError("give exactly one of --arch and --techlib")
    _check_top(top)
    read_files = " ".join(_quote(path) for path in files)
    commands: list[str] = []
    if arch is not None:
        commands.append(f"read_arch {_quote(arch)}")
    else:
        assert techlib is not None
        commands.append(f"read_techlib {_quote(techlib)}")
    if _read_verilog_takes_top():
        commands.append(f"read_verilog --nolatches --vtr-compat --top {top} {read_files}")
    else:
        commands.append(f"read_verilog --nolatches --vtr-compat {read_files}")
        if _has_pass("hierarchy"):
            commands.append(f"hierarchy --top {top}")
        else:
            print(
                "verdandi record: warning: this Odin III build has no top-selection pass",
                file=sys.stderr,
            )
    commands.extend(["proc", "fsm", "opt", "flatten", "opt -full", "wreduce"])
    if techlib is None:
        commands.append("hardmap")
    commands.extend(["lower", f"abc --lut {k}", f"write_blif {_quote(blif_out)}"])
    return "; ".join(commands)


def _env_root() -> Path | None:
    """ODIN3_ROOT from the environment, when it names an existing directory."""
    value = os.environ.get("ODIN3_ROOT")
    if value:
        root = Path(value)
        if root.is_dir():
            return root
    return None


def _code_refs(locator: Locator, name: str, root: Path | None) -> list[CodeRef]:
    """One CodeRef per registering file, the whole file (an event's ref is the line that logs)."""
    refs: list[CodeRef] = []
    for path in locator.pass_files(name):
        end_line = 1
        if root is not None:
            try:
                text = (root / path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            end_line = max(1, len(text.splitlines()))
        refs.append(CodeRef(file=str(path), line=1, end_line=end_line, function=None))
    return refs


def _over_size(title: str, snapshot: dict[str, Any], max_nodes: int) -> str | None:
    """The size-guard message when the snapshot is over the limit, else None."""
    count = node_count(snapshot)
    if count <= max_nodes:
        return None
    return f"step '{title}' has {count} nodes, over --max-nodes {max_nodes}"


def _renumbers(name: str, command: str) -> bool:
    """True when a command renumbers object IDs: ``abc`` compacts internally, and so does the
    ``compact`` pass; only names are stable across such a step, so its diff matches by name."""
    return name == "abc" or "compact" in command.split()


def _lut_k(arguments: str, default: int) -> int:
    """The ``--lut K`` value of an ``abc`` command, or the recording's K when it gives none."""
    words = arguments.split()
    for index, word in enumerate(words):
        if word == "--lut" and index + 1 < len(words):
            try:
                return int(words[index + 1])
            except ValueError:
                return default
    return default


def _abc_script_path(arguments: str) -> Path | None:
    """The ``--script FILE`` path of an ``abc`` command, or None for the built-in script."""
    found = _ABC_SCRIPT.search(arguments)
    if found is None:
        return None
    value = found.group(1) if found.group(1) is not None else found.group(2)
    return Path(value)


def _no_abc_warning() -> None:
    """The one warning a recording without a standalone ABC binary prints (spec 9)."""
    print(
        "verdandi record: warning: no standalone ABC binary (ODIN3_ABC or "
        "build/*/third_party/abc/abc under ODIN3_ROOT); the ABC stage has its L1 step only",
        file=sys.stderr,
    )


def _new_step(
    steps: list[Step],
    *,
    parent: str | None,
    level: int,
    title: str,
    anchor: str,
    code: list[CodeRef] | None = None,
) -> Step:
    """Append a step with the next recording-order id; ids are s0001, s0002, ..."""
    step = Step(
        id=f"s{len(steps) + 1:04d}",
        parent=parent,
        level=level,
        title=title,
        anchor=anchor,
        code=[] if code is None else code,
    )
    steps.append(step)
    return step


class _Recording:
    """One recording session: the design, the steps so far and where they are written."""

    def __init__(
        self,
        *,
        files: list[Path],
        top: str,
        out: Path,
        arch: Path | None,
        script: str,
        stage_version: int,
        titles: dict[str, str],
        locator: Locator,
        odin3_root: Path | None,
        source_commit: str,
        library: Any,
        max_nodes: int,
        abc: str | None,
        k: int,
        workdir: Path,
    ) -> None:
        self.files = files
        self.top = top
        self.out = out
        self.arch = arch
        self.script = script
        self.stage_version = stage_version
        self.titles = titles
        self.locator = locator
        self.odin3_root = odin3_root
        self.source_commit = source_commit
        self.library = library
        self.max_nodes = max_nodes
        self.abc = abc
        self.k = k
        self.workdir = workdir
        self.abc_captures = 0
        self.steps: list[Step] = []
        self.snapshots: dict[str, dict[str, Any]] = {}
        self.pictures: dict[str, Path] = {}
        self.previous: dict[str, Any] | None = None
        self.stage: Step | None = None
        self.stage_before: dict[str, Any] | None = None
        self.stage_by_name = False
        self.warned_no_abc = False
        self._code_cache: dict[str, list[CodeRef]] = {}
        self._ref_cache: dict[tuple[str, str], list[CodeRef]] = {}

    def _pass_refs(self, name: str) -> list[CodeRef]:
        """The pass's code refs, computed once per recording."""
        refs = self._code_cache.get(name)
        if refs is None:
            refs = _code_refs(self.locator, name, self.odin3_root)
            self._code_cache[name] = refs
        return refs

    def run(self, commands: list[str]) -> int:
        """Record every command; 0 ok, 1 a pass failed, 2 a snapshot is over the size guard."""
        import odin3

        design = odin3.Design(self.library)
        try:
            keep_all_asts(design)
            for command in commands:
                code = self._command(design, command)
                if code is not None:
                    return code
            self._write()
            return 0
        finally:
            design.close()

    def _command(self, design: Any, command: str) -> int | None:
        """Record one script command; an exit code when the recording stops here.

        The step log is the library's log records; a pass with event patterns runs at DEBUG
        (capture_log restores the level) and its object-naming lines become L3 children. A pass
        with documented parts also gets L2 children, run on a copy of the design before it ran.
        """
        parts = command.split(maxsplit=1)
        name = parts[0]
        arguments = parts[1].strip() if len(parts) > 1 else ""
        stage_title = self.titles.get(name, name)
        if self.stage is None or self.stage.title != stage_title:
            # The stage step diffs from the step before it, which is the previous stage's
            # final IR snapshot (None before the first stage).
            self.stage_before = self.previous
            self.stage_by_name = False
            self.stage = _new_step(
                self.steps, parent=None, level=0, title=stage_title, anchor=f"stage:{stage_title}"
            )
        assert self.stage is not None
        refs = self._pass_refs(name)
        step = _new_step(
            self.steps,
            parent=self.stage.id,
            level=1,
            title=command,
            anchor=f"pass:{name}",
            code=refs,
        )
        before_snapshot = self.previous
        before = None
        if name in _EXPANDED:
            try:
                before = design.copy()
            except (OSError, RuntimeError, ValueError) as exc:
                # The copy only carries the sub-steps; without it the recording would show
                # less than the trace promises, so it ends as a usage error, not a traceback.
                print(
                    f"verdandi record: the sub-steps of '{command}' are not available: {exc}",
                    file=sys.stderr,
                )
                return 2
        try:
            abc_children: list[Step] = []
            abc_stats: dict[str, int] = {}
            if name == "abc":
                abc_children, abc_stats = self._abc_children(step, design, arguments)
            error: Exception | None = None
            with self.library.capture_log() as records:
                # A pass with events runs at DEBUG here (an expanded pass's events come from
                # its sub-steps); capture_log restores the level when the block ends.
                if name in PATTERNS and name not in _EXPANDED:
                    self.library.call(
                        "odin3_log_set_level", self.library.lib.ODIN3_LOG_DEBUG
                    )
                try:
                    design.run_pass(name, arguments)
                except Exception as exc:  # a failed pass ends the recording; its status says why
                    error = exc
            step.log = [record.message for record in records]
            if error is not None:
                step.failed = True
                why = next((line for line in reversed(step.log) if "failed" in line), None)
                if why is None:
                    why = step.log[-1] if step.log else str(error)
                print(f"verdandi record: step '{command}' failed: {why}", file=sys.stderr)
                self._write()
                return 1
            snapshot = ir_snapshot(design)
            over = _over_size(step.title, snapshot, self.max_nodes)
            if over is not None:
                print(f"verdandi record: {over}", file=sys.stderr)
                return 2
            step.snapshot = f"{step.id}.json"
            self.snapshots[step.snapshot] = snapshot
            by_name = _renumbers(name, command)
            step.diff = diff(self.previous, snapshot, by_name=by_name)
            self.previous = snapshot
            self.stage.snapshot = step.snapshot
            self.stage_by_name = self.stage_by_name or by_name
            self.stage.diff = diff(self.stage_before, snapshot, by_name=self.stage_by_name)
            self._mark_illustrations(abc_children, abc_stats, step.log)
            if before is not None:
                code = self._substeps(step, before, command, before_snapshot, snapshot)
                if code is not None:
                    return code
            else:
                self._events(step, name, step.log)
            if name == "read_verilog":
                return self._ast_children(step, design, refs)
            return None
        finally:
            if before is not None:
                before.close()

    def _events(self, parent: Step, pass_name: str, log: list[str]) -> None:
        """The log's object-naming DEBUG lines as L3 children of the pass's step (spec 4).

        An event's code refs are the DEBUG log calls of the pass's files whose format holds the
        text before the format's first ``%`` (spec 6), searched once per format: the line that
        logs the event, not a comment or a call that merely shares the prefix. An event is a
        log line, not a design state: it carries the empty diff, as an AST step does.
        """
        if pass_name not in PATTERNS:
            return
        files = self.locator.pass_files(pass_name)
        for line in log:
            found = match_event(pass_name, line)
            if found is None:
                continue
            title, anchor, prefix = found
            key = (pass_name, prefix)
            refs = self._ref_cache.get(key)
            if refs is None:
                refs = self.locator.find_log_text(files, prefix)
                self._ref_cache[key] = refs
            child = _new_step(
                self.steps,
                parent=parent.id,
                level=3,
                title=title,
                anchor=anchor,
                code=list(refs),
            )
            child.diff = Diff(added=[], removed=[], changed=[], by_name=False)

    def _substeps(
        self,
        parent: Step,
        before: Any,
        command: str,
        before_snapshot: dict[str, Any] | None,
        real_snapshot: dict[str, Any],
    ) -> int | None:
        """Record the command's documented parts as L2 children of its step (spec 4).

        Each entry's diff chains from the one before it (the pass's own before snapshot first).
        An iteration group carries its iteration's end snapshot, which is its last child's: the
        group points at that child's snapshot file instead of writing a second, identical copy.
        The sub-passes that follow it sit at the same level, so their events keep level 3. The
        sub-steps are illustrations when the last entry does not match the real pass's snapshot:
        the copy shows something else than the pass did.
        """
        pass_name = command.split(maxsplit=1)[0]
        try:
            entries = expand(before, command)
        except (OSError, RuntimeError, ValueError) as exc:
            print(
                f"verdandi record: warning: the sub-steps of '{command}' are not available: {exc}",
                file=sys.stderr,
            )
            return None
        if not entries:
            return None
        group: Step | None = None
        groups: list[tuple[Step, dict[str, Any]]] = []
        chain = before_snapshot
        created: list[Step] = []
        for title, snapshot, log in entries:
            over = _over_size(title, snapshot, self.max_nodes)
            if over is not None:
                # A copy's intermediate state is not the pass's result: the pass's own L1
                # snapshot enforces the bound, so an over-size sub-step only warns.
                print(
                    f"verdandi record: warning: sub-step of pass '{pass_name}': {over}",
                    file=sys.stderr,
                )
            sub_name = title.split(maxsplit=1)[0]
            grouping = title.startswith(ITERATION_PREFIX)
            if grouping:
                step = _new_step(
                    self.steps,
                    parent=parent.id,
                    level=2,
                    title=title,
                    anchor=f"pass:{pass_name}",
                    code=self._pass_refs(pass_name),
                )
                group = step
                groups.append((step, snapshot))
            else:
                step = _new_step(
                    self.steps,
                    parent=parent.id if group is None else group.id,
                    level=2,
                    title=title,
                    anchor=f"pass:{sub_name}",
                    code=self._pass_refs(sub_name),
                )
            step.log = list(log)
            step.diff = diff(chain, snapshot)
            if grouping:
                created.append(step)
                continue
            step.snapshot = f"{step.id}.json"
            self.snapshots[step.snapshot] = snapshot
            chain = snapshot
            self._events(step, sub_name, log)
            if group is not None:
                # The group's end state is its last child's: share the file, write no copy.
                group.snapshot = step.snapshot
            created.append(step)
        for step, snapshot in groups:
            if step.snapshot is None or self.snapshots[step.snapshot] != snapshot:
                # A group with no child (or whose last child ends elsewhere) keeps its own file.
                step.snapshot = f"{step.id}.json"
                self.snapshots[step.snapshot] = snapshot
        if not matches(entries[-1][1], real_snapshot):
            for step in created:
                step.illustration = True
        return None

    def _abc_children(
        self, parent: Step, design: Any, arguments: str
    ) -> tuple[list[Step], dict[str, int]]:
        """The opened-up ABC steps (spec 6a): one L2 step per script command.

        The commands replay on the BLIF the pass exchanges, captured from a copy of the design
        before the real pass runs; each step gets ABC's own picture and log and no snapshot.
        The commands are the source tree's lib/abc/vtr.abc, or the file the command's own
        ``--script`` names, read at record time so the replay follows the pass's script.
        The replay follows run 0 only (the first module and clock domain): a multi-domain design's
        later runs are not opened up, as the plan's Task 7 states.
        Each ``abc`` command gets its own directory under the recording's workdir, so a second
        capture neither replays an earlier BLIF nor overwrites the earlier command's pictures.
        Without an ABC binary the ABC stage keeps its L1 step only and warns once; a capture
        that fails warns too, rather than ending a recording the real pass may still complete.
        """
        if self.abc is None:
            if not self.warned_no_abc:
                self.warned_no_abc = True
                _no_abc_warning()
            return [], {}
        k = _lut_k(arguments, self.k)
        script = _abc_script_path(arguments)
        self.abc_captures += 1
        workdir = self.workdir / f"abc{self.abc_captures}"
        try:
            inputs = capture_abc_input(design, k, workdir)
            if not inputs:
                return [], {}
            abc_steps = run_abc_steps(
                self.abc,
                inputs[0],
                abc_script(self.odin3_root, k, script=script),
                workdir,
            )
        except (OSError, RuntimeError) as exc:
            print(
                f"verdandi record: warning: the ABC sub-steps are not available: {exc}",
                file=sys.stderr,
            )
            return [], {}
        if not abc_steps:
            return [], {}
        children: list[Step] = []
        for abc_step in abc_steps:
            word = abc_step.command.split()[0]
            title = TITLES.get(word, abc_step.command)
            child = _new_step(
                self.steps, parent=parent.id, level=2, title=title, anchor=f"abc:{word}"
            )
            child.log = list(abc_step.log)
            # An illustration still carries a diff, as an AST step does: the empty one.
            child.diff = Diff(added=[], removed=[], changed=[], by_name=False)
            if abc_step.dot.is_file():
                name = f"{child.id}.dot"
                self.pictures[name] = abc_step.dot
                child.picture = name
            children.append(child)
        return children, abc_steps[-1].stats

    @staticmethod
    def _mark_illustrations(
        children: list[Step], stats: dict[str, int], log: list[str]
    ) -> None:
        """Mark the ABC sub-steps when their network differs from the linked run's.

        Both sides are ABC's own network node count ``nd`` for the same exchange run: LUTs and
        one-input buffer nodes alike, so the two numbers compare like with like. The replay
        follows run 0, whose ``print_stats`` line is the first in the linked pass's log.
        """
        if not children or "nd" not in stats:
            return
        linked = _parse_stats(log, first=True)
        if "nd" in linked and linked["nd"] != stats["nd"]:
            for child in children:
                child.illustration = True

    def _ast_children(self, parent: Step, design: Any, refs: list[CodeRef]) -> int | None:
        """Add the kept PARSED and ELABORATED ASTs as L2 children of the read_verilog step."""
        for form, title in (("PARSED", "Parse"), ("ELABORATED", "Elaborate")):
            snapshot = ast_snapshot(design, form)
            if snapshot is None:
                continue
            over = _over_size(f"{parent.title} ({title})", snapshot, self.max_nodes)
            if over is not None:
                print(f"verdandi record: {over}", file=sys.stderr)
                return 2
            child = _new_step(
                self.steps,
                parent=parent.id,
                level=2,
                title=title,
                anchor=parent.anchor,
                code=list(refs),
            )
            child.snapshot = f"{child.id}.json"
            self.snapshots[child.snapshot] = snapshot
            # An AST step still carries a diff: Task 4's diff of an AST snapshot is empty.
            child.diff = diff(self.previous, snapshot)
        return None

    def _write(self) -> None:
        """Write the trace directory: the steps, snapshots and sources recorded so far."""
        manifest = Manifest(
            version=FORMAT_VERSION,
            program="odin3",
            program_version=self.library.version(),
            abi=self.library.abi_version(),
            source_commit=self.source_commit,
            files=[str(path) for path in self.files],
            top=self.top,
            arch=None if self.arch is None else str(self.arch),
            script=self.script,
            stage_map_version=self.stage_version,
            recorded=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        save(self.out, manifest, self.steps, self.snapshots, list(self.files), self.pictures)


def record(
    files: list[Path],
    top: str,
    out: Path,
    *,
    arch: Path | None = None,
    techlib: Path | None = None,
    k: int = 6,
    script: str | None = None,
    odin3_root: Path | None = None,
    max_nodes: int = 5000,
    abc: str | None = None,
) -> int:
    """Record ``files`` through Odin III into the trace at ``out``; exit code as the CLI's.

    ``script`` replaces the default script. ``abc`` is the standalone ABC binary for the
    opened-up ABC sub-steps (default: $ODIN3_ABC, else build/*/third_party/abc/abc under the
    source tree; without one the ABC stage keeps its L1 step only and warns once).
    ``odin3_root`` is where the code locator reads the source (None: the environment's
    ODIN3_ROOT, else no code locations); without a git checkout the manifest's source commit
    is ``"unknown"`` and the run warns once.
    """
    try:
        import odin3

        library = odin3.default()
    except Exception as exc:
        print(f"verdandi record: the odin3 binding is not available: {exc}", file=sys.stderr)
        return 2
    missing = [str(path) for path in files if not path.is_file()]
    missing.extend(
        str(path) for path in (arch, techlib) if path is not None and not path.is_file()
    )
    if missing:
        print(f"verdandi record: no such file: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        _check_top(top)
    except ValueError as exc:
        print(f"verdandi record: {exc}", file=sys.stderr)
        return 2
    root = odin3_root if odin3_root is not None else _env_root()
    binary = abc if abc is not None else find_abc(root)
    locator = Locator(root)
    source_commit = locator.commit()
    if root is None or source_commit == "unknown":
        print(
            "verdandi record: warning: no Odin III source tree (ODIN3_ROOT unset or not a "
            "git checkout); recording without code locations",
            file=sys.stderr,
        )
    try:
        version, titles = stage_map()
    except (OSError, ValueError) as exc:
        print(f"verdandi record: {exc}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="verdandi-record-") as scratch:
        if script is None:
            try:
                script = default_script(
                    files,
                    top,
                    arch=arch,
                    techlib=techlib,
                    k=k,
                    blif_out=Path(scratch) / f"{top}.blif",
                )
            except ValueError as exc:
                print(f"verdandi record: {exc}", file=sys.stderr)
                return 2
        commands = [part.strip() for part in script.split(";") if part.strip()]
        if not commands:
            print("verdandi record: the script has no commands", file=sys.stderr)
            return 2
        recording = _Recording(
            files=files,
            top=top,
            out=out,
            arch=arch,
            script=script,
            stage_version=version,
            titles=titles,
            locator=Locator(root),
            odin3_root=root,
            source_commit=source_commit,
            library=library,
            max_nodes=max_nodes,
            abc=binary,
            k=k,
            workdir=Path(scratch) / "abc",
        )
        try:
            return recording.run(commands)
        except (OSError, ValueError) as exc:
            print(f"verdandi record: {exc}", file=sys.stderr)
            return 2
