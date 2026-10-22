"""Snapshot diffs: the objects added, removed and changed between two IR snapshots.

Objects are matched by ``(module, kind, id)`` within one design, or by
``(module, kind, name)`` when the caller asks for ``by_name``: across a ``compact`` pass the
IDs are renumbered, so only names are stable. An AST snapshot (or any non-IR snapshot) has no
object IDs to compare and diffs to an empty ``Diff``; the player shows AST steps as trees.

Order is deterministic: added and changed objects follow the after snapshot, removed objects
follow the before snapshot, both in the snapshot's own order (modules, then nodes, nets, wires).
"""

from __future__ import annotations

from typing import Any

from verdandi.trace import Diff, ObjRef

# Snapshot collection name -> object kind in an ObjRef, in snapshot order.
_SINGULAR = {"nodes": "node", "nets": "net", "wires": "wire"}

# The fields whose change makes an object "changed"; sources are provenance, not content.
_CHANGED_FIELDS: dict[str, tuple[str, ...]] = {
    "node": ("type", "params", "pins"),
    "net": ("drivers", "sinks"),
    "wire": (),
}


def _index(
    snapshot: dict[str, Any], by_name: bool
) -> dict[tuple[str, str, int | str], tuple[ObjRef, dict[str, Any]]]:
    """The snapshot's objects keyed by module, kind and ID (or name); later duplicates win."""
    index: dict[tuple[str, str, int | str], tuple[ObjRef, dict[str, Any]]] = {}
    for module in snapshot.get("modules", []):
        module_name = str(module["name"])
        for plural, kind in _SINGULAR.items():
            for item in module.get(plural, []):
                ident: int | str = str(item["name"]) if by_name else int(item["id"])
                ref = ObjRef(
                    module=module_name,
                    kind=kind,
                    id=int(item["id"]),
                    name=str(item["name"]),
                )
                index[(module_name, kind, ident)] = (ref, item)
    return index


def _changed(kind: str, before: dict[str, Any], after: dict[str, Any]) -> bool:
    """True when an object matched by key differs in its content fields."""
    return any(
        before.get(field) != after.get(field) for field in _CHANGED_FIELDS.get(kind, ())
    )


def diff(before: dict[str, Any] | None, after: dict[str, Any], *, by_name: bool = False) -> Diff:
    """Objects added, removed and changed from snapshot ``before`` to snapshot ``after``.

    ``before`` is None for the first snapshot, which makes everything added. Non-IR snapshots
    (AST steps) diff to an empty Diff. Changed objects are reported with their after identity.
    """
    if after.get("kind") != "ir" or (before is not None and before.get("kind") != "ir"):
        return Diff(added=[], removed=[], changed=[], by_name=by_name)
    before_index = {} if before is None else _index(before, by_name)
    after_index = _index(after, by_name)
    added: list[ObjRef] = []
    changed: list[ObjRef] = []
    for key, (ref, item) in after_index.items():
        previous = before_index.get(key)
        if previous is None:
            added.append(ref)
        elif _changed(ref.kind, previous[1], item):
            changed.append(ref)
    removed = [ref for key, (ref, _) in before_index.items() if key not in after_index]
    return Diff(added=added, removed=removed, changed=changed, by_name=by_name)
