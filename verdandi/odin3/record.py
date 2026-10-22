"""The recorder: run a script through Odin III pass by pass into a trace (spec 3, 4, 10).

The script is split on ``;``. Each command runs as one L1 pass step under an L0 stage step from
``stages.json`` (a pass the map does not list gets a stage titled by its name); the IR is
snapshotted after it and diffed against the previous IR snapshot. ``read_verilog`` also gives
two L2 children from the kept ASTs: "Parse" (PARSED) and "Elaborate" (ELABORATED). A failing
pass marks its step failed, writes the trace up to it and returns 1; a snapshot over
``max_nodes`` refuses the recording and returns 2, naming the step.
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
from verdandi.odin3.locator import Locator
from verdandi.odin3.snapshot import ast_snapshot, ir_snapshot, keep_all_asts, node_count
from verdandi.trace import FORMAT_VERSION, CodeRef, Manifest, Step, save

_STAGES_FILE = Path(__file__).with_name("stages.json")

# A "-top" or "--top" word in a pass's usage line (not a longer option that ends in "top").
_TOP_OPTION = re.compile(r"(?:^|\s)--?top(?:\s|=|$)")

# Characters a module name or a script path cannot hold: they would split or break the script.
_SCRIPT_UNSAFE = set(';"\n')


def stage_map() -> tuple[int, dict[str, str]]:
    """The stage map's version and its pass name -> stage title mapping."""
    data = json.loads(_STAGES_FILE.read_text(encoding="utf-8"))
    titles = {
        str(name): str(stage["title"]) for stage in data["stages"] for name in stage["passes"]
    }
    return int(data["version"]), titles


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
    if _SCRIPT_UNSAFE & set(top) or " " in top:
        raise ValueError(f"top module name {top!r} is not a Verilog identifier")
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
    """One CodeRef per registering file, the whole file (Task 8 refines to functions)."""
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
        self.steps: list[Step] = []
        self.snapshots: dict[str, dict[str, Any]] = {}
        self.previous: dict[str, Any] | None = None
        self.stage: Step | None = None

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
        """Record one script command; an exit code when the recording stops here."""
        parts = command.split(maxsplit=1)
        name = parts[0]
        arguments = parts[1].strip() if len(parts) > 1 else ""
        stage_title = self.titles.get(name, name)
        if self.stage is None or self.stage.title != stage_title:
            self.stage = _new_step(
                self.steps, parent=None, level=0, title=stage_title, anchor=f"stage:{stage_title}"
            )
        assert self.stage is not None
        refs = _code_refs(self.locator, name, self.odin3_root)
        step = _new_step(
            self.steps,
            parent=self.stage.id,
            level=1,
            title=command,
            anchor=f"pass:{name}",
            code=refs,
        )
        error: Exception | None = None
        with self.library.capture_log() as records:
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
        step.diff = diff(self.previous, snapshot, by_name=_renumbers(name, command))
        self.previous = snapshot
        self.stage.snapshot = step.snapshot
        if name == "read_verilog":
            return self._ast_children(step, design, refs)
        return None

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
        save(self.out, manifest, self.steps, self.snapshots, list(self.files))


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
    opened-up ABC sub-steps (Task 7; not used yet). ``odin3_root`` is where the code locator
    reads the source (None: the environment's ODIN3_ROOT, else no code locations); without a
    git checkout the manifest's source commit is ``"unknown"`` and the run warns once.
    """
    _ = abc
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
    root = odin3_root if odin3_root is not None else _env_root()
    locator = Locator(root)
    source_commit = locator.commit()
    if root is None or source_commit == "unknown":
        print(
            "verdandi record: warning: no Odin III source tree (ODIN3_ROOT unset or not a "
            "git checkout); recording without code locations",
            file=sys.stderr,
        )
    version, titles = stage_map()
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
        )
        return recording.run(commands)
