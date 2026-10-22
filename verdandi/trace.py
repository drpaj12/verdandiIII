"""Trace model and file format version 1.

A trace is a directory: ``manifest.json``, ``steps.json``, ``snap/``, ``src/`` and, for ABC
steps, ``pic/``. JSON is deterministic: keys sorted, one-space indent, one trailing newline.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

FORMAT_VERSION = 1


@dataclass(frozen=True)
class ObjRef:
    """One IR object touched by a step; kind is "node", "net" or "wire"."""

    module: str
    kind: str
    id: int
    name: str


@dataclass
class Diff:
    """Objects added, removed and changed between two snapshots."""

    added: list[ObjRef]
    removed: list[ObjRef]
    changed: list[ObjRef]
    by_name: bool


@dataclass
class CodeRef:
    """A span in the Odin III source tree; file is relative to its root."""

    file: str
    line: int
    end_line: int
    function: str | None


@dataclass
class Step:
    """One node of the playthrough tree, level 0 (stage) to 3 (event).

    ``level`` is a label, not a depth: an L3 event may sit directly under its L1 pass, and an
    iteration group and its children are both L2. Walk ``parent`` and children instead.
    """

    id: str
    parent: str | None
    level: int
    title: str
    anchor: str
    snapshot: str | None = None
    diff: Diff | None = None
    code: list[CodeRef] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    illustration: bool = False
    failed: bool = False
    picture: str | None = None


@dataclass
class Manifest:
    """Trace identity: program, source tree commit, inputs and script."""

    version: int
    program: str
    program_version: str
    abi: int
    source_commit: str
    files: list[str]
    top: str
    arch: str | None
    script: str
    stage_map_version: int
    recorded: str


class Trace:
    """A loaded trace: manifest, steps and lazily read snapshots."""

    def __init__(self, directory: Path, manifest: Manifest, steps: list[Step]) -> None:
        # Resolved once: snapshots are read lazily, and a later chdir must not move them.
        self.directory = Path(directory).resolve()
        self.manifest = manifest
        self.steps = list(steps)
        self._by_id: dict[str, Step] = {}
        self._children: dict[str | None, list[Step]] = {}
        for step in self.steps:
            self._by_id[step.id] = step
            self._children.setdefault(step.parent, []).append(step)
        self._snapshots: dict[str, dict[str, Any]] = {}

    def children(self, step_id: str | None) -> list[Step]:
        """Children in recording order; ``None`` gives the roots (level 0)."""
        return list(self._children.get(step_id, []))

    def step(self, step_id: str) -> Step:
        return self._by_id[step_id]

    def snapshot(self, step: Step) -> dict[str, Any] | None:
        """The step's snapshot, read once and cached; None when it has no snapshot."""
        if step.snapshot is None:
            return None
        name = _checked_name(step.snapshot, "snapshot")
        if name not in self._snapshots:
            path = self.directory / "snap" / name
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError(f"snapshot {name} is not a JSON object")
            self._snapshots[name] = loaded
        return self._snapshots[name]


def save(
    directory: Path,
    manifest: Manifest,
    steps: list[Step],
    snapshots: dict[str, dict[str, Any]],
    sources: list[Path],
    pictures: dict[str, Path] | None = None,
) -> None:
    """Write a trace directory atomically.

    The trace is written into a fresh temporary directory beside ``directory`` and
    swapped in when complete, so a failure leaves a previous trace untouched.
    An existing trace directory is replaced as a whole: files from an earlier save
    that are not part of this trace do not survive.
    """
    directory = Path(directory).resolve()
    _check_unique([_checked_name(name, "snapshot") for name in snapshots], "snapshot")
    _check_unique([_checked_name(name, "picture") for name in pictures or {}], "picture")
    _check_unique([source.name for source in sources], "source")
    directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{directory.name}.tmp-", dir=directory.parent))
    try:
        _write_trace(staging, manifest, steps, snapshots, sources, pictures or {})
        _swap_into_place(staging, directory)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _write_trace(
    directory: Path,
    manifest: Manifest,
    steps: list[Step],
    snapshots: dict[str, dict[str, Any]],
    sources: list[Path],
    pictures: dict[str, Path],
) -> None:
    snap_dir = directory / "snap"
    src_dir = directory / "src"
    snap_dir.mkdir()
    src_dir.mkdir()
    _write_json(directory / "manifest.json", asdict(manifest))
    _write_json(directory / "steps.json", [asdict(step) for step in steps])
    for name in sorted(snapshots):
        _write_json(snap_dir / name, snapshots[name])
    for source in sorted(sources, key=lambda path: path.name):
        shutil.copyfile(source, src_dir / source.name)
    if pictures:
        pic_dir = directory / "pic"
        pic_dir.mkdir()
        for name in sorted(pictures):
            shutil.copyfile(pictures[name], pic_dir / name)


def _swap_into_place(staging: Path, target: Path) -> None:
    """Move the finished trace in place, replacing an existing directory as a whole."""
    if not target.exists():
        os.replace(staging, target)
        return
    if not target.is_dir():
        raise ValueError(f"trace path {str(target)!r} is not a directory")
    previous = Path(tempfile.mkdtemp(prefix=f".{target.name}.old-", dir=target.parent))
    previous.rmdir()
    os.replace(target, previous)
    try:
        os.replace(staging, target)
    except OSError:
        os.replace(previous, target)
        raise
    shutil.rmtree(previous, ignore_errors=True)


def load(directory: Path) -> Trace:
    """Read a trace directory; refuse a format version newer than this player."""
    directory = Path(directory).resolve()
    manifest_data = _read_json_object(directory / "manifest.json")
    version = _parse_version(manifest_data.get("version"))
    if version > FORMAT_VERSION:
        raise ValueError(f"trace format {version} is newer than {FORMAT_VERSION}")
    steps_data = json.loads((directory / "steps.json").read_text(encoding="utf-8"))
    if not isinstance(steps_data, list):
        raise ValueError("steps.json is not a JSON array")
    steps = [_step_from_dict(item) for item in steps_data]
    return Trace(directory, _manifest_from_dict(manifest_data), steps)


def _checked_name(name: str, what: str) -> str:
    """A trace file name is one plain file name inside the trace directory."""
    if not name or name in {".", ".."} or "\0" in name:
        raise ValueError(f"{what} name {name!r} is not a file name")
    if name != Path(name).name or "/" in name or "\\" in name or Path(name).is_absolute():
        raise ValueError(f"{what} name {name!r} escapes the trace directory")
    return name


def _check_unique(names: Iterable[str], what: str) -> None:
    """Reject names that would collide; ignore case so a trace is portable."""
    seen: dict[str, str] = {}
    for name in names:
        key = name.casefold()
        if key in seen:
            raise ValueError(f"duplicate {what} name {name!r} collides with {seen[key]!r}")
        seen[key] = name


def _write_json(path: Path, data: Any) -> None:
    text = json.dumps(data, sort_keys=True, indent=1)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def _read_json_object(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path.name} is not a JSON object")
    return loaded


def _parse_version(value: Any) -> int:
    """A format version is a whole number of at least 1; reject anything else."""
    if isinstance(value, bool):
        raise ValueError(f"malformed trace format version {value!r}")
    if isinstance(value, int):
        version = value
    elif isinstance(value, float) and value.is_integer():
        version = int(value)
    elif isinstance(value, str) and value.strip().removeprefix("-").isdigit():
        version = int(value.strip())
    else:
        raise ValueError(f"malformed trace format version {value!r}")
    if version < 1:
        raise ValueError(f"malformed trace format version {value!r}")
    return version


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _obj_ref_from_dict(data: dict[str, Any]) -> ObjRef:
    return ObjRef(
        module=str(data["module"]),
        kind=str(data["kind"]),
        id=int(data["id"]),
        name=str(data["name"]),
    )


def _diff_from_dict(data: dict[str, Any]) -> Diff:
    return Diff(
        added=[_obj_ref_from_dict(item) for item in data["added"]],
        removed=[_obj_ref_from_dict(item) for item in data["removed"]],
        changed=[_obj_ref_from_dict(item) for item in data["changed"]],
        by_name=bool(data["by_name"]),
    )


def _code_ref_from_dict(data: dict[str, Any]) -> CodeRef:
    return CodeRef(
        file=str(data["file"]),
        line=int(data["line"]),
        end_line=int(data["end_line"]),
        function=_optional_str(data.get("function")),
    )


def _step_from_dict(data: dict[str, Any]) -> Step:
    diff_data = data.get("diff")
    return Step(
        id=str(data["id"]),
        parent=_optional_str(data.get("parent")),
        level=int(data["level"]),
        title=str(data["title"]),
        anchor=str(data["anchor"]),
        snapshot=_optional_str(data.get("snapshot")),
        diff=None if diff_data is None else _diff_from_dict(diff_data),
        code=[_code_ref_from_dict(item) for item in data.get("code", [])],
        log=[str(line) for line in data.get("log", [])],
        illustration=bool(data.get("illustration", False)),
        failed=bool(data.get("failed", False)),
        picture=_optional_str(data.get("picture")),
    )


def _manifest_from_dict(data: dict[str, Any]) -> Manifest:
    return Manifest(
        version=_parse_version(data.get("version")),
        program=str(data["program"]),
        program_version=str(data["program_version"]),
        abi=int(data["abi"]),
        source_commit=str(data["source_commit"]),
        files=[str(name) for name in data["files"]],
        top=str(data["top"]),
        arch=_optional_str(data.get("arch")),
        script=str(data["script"]),
        stage_map_version=int(data["stage_map_version"]),
        recorded=str(data["recorded"]),
    )
