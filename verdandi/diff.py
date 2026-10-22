"""Snapshot diffs: the objects added, removed and changed between two IR snapshots.

Objects are matched by ``(module, kind, id)`` within one design, or by
``(module, kind, name)`` when the caller asks for ``by_name``: across a ``compact`` pass the
IDs are renumbered, so only names are stable. Under ``by_name`` the before-side references
inside node pins and net drivers/sinks are remapped to the after-side IDs by name before the
content is compared, so a pure renumbering is not a change. An AST snapshot (or any non-IR
snapshot) has no object IDs to compare and diffs to an empty ``Diff``; the player shows AST
steps as trees.

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
    """The snapshot's objects keyed by module, kind and ID (or name).

    A duplicate key raises ValueError: silently keeping one of the two objects would drop the
    other from every list of the diff.
    """
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
                key = (module_name, kind, ident)
                if key in index:
                    label = "name" if by_name else "id"
                    raise ValueError(
                        f"duplicate {kind} {label} {ident!r} in module {module_name!r}"
                    )
                index[key] = (ref, item)
    return index


def _id_map(
    before_index: dict[tuple[str, str, int | str], tuple[ObjRef, dict[str, Any]]],
    after_index: dict[tuple[str, str, int | str], tuple[ObjRef, dict[str, Any]]],
    kind: str,
) -> dict[int, int]:
    """Before-ID to after-ID for the objects of ``kind`` matched by key."""
    return {
        before_ref.id: after_index[key][0].id
        for key, (before_ref, _) in before_index.items()
        if key in after_index and before_ref.kind == kind
    }


def _remap(
    item: dict[str, Any], kind: str, node_ids: dict[int, int], net_ids: dict[int, int]
) -> dict[str, Any]:
    """A copy of a before-side object with its references renumbered to the after side."""
    if kind == "node" and item.get("pins"):
        return {
            **item,
            "pins": [
                {**pin, "net": net_ids.get(pin["net"], pin["net"])} for pin in item["pins"]
            ],
        }
    if kind == "net" and (item.get("drivers") or item.get("sinks")):
        return {
            **item,
            "drivers": [node_ids.get(d, d) for d in item.get("drivers", [])],
            "sinks": [node_ids.get(s, s) for s in item.get("sinks", [])],
        }
    return item


# The empty value of a changed field, used when a producer omits the field: absent must compare
# equal to present-empty, or every object turns amber.
_EMPTY: dict[str, Any] = {"type": "", "params": {}, "pins": [], "drivers": [], "sinks": []}


def _field(item: dict[str, Any], name: str) -> Any:
    """The field's value, or its empty value when the producer omitted it."""
    return item[name] if name in item else _EMPTY[name]


def _changed(kind: str, before: dict[str, Any], after: dict[str, Any]) -> bool:
    """True when an object matched by key differs in its content fields."""
    return any(
        _field(before, field) != _field(after, field) for field in _CHANGED_FIELDS.get(kind, ())
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
    node_ids: dict[int, int] = {}
    net_ids: dict[int, int] = {}
    if by_name:
        node_ids = _id_map(before_index, after_index, "node")
        net_ids = _id_map(before_index, after_index, "net")
    added: list[ObjRef] = []
    changed: list[ObjRef] = []
    for key, (ref, item) in after_index.items():
        previous = before_index.get(key)
        if previous is None:
            added.append(ref)
        else:
            previous_item = _remap(previous[1], ref.kind, node_ids, net_ids)
            if _changed(ref.kind, previous_item, item):
                changed.append(ref)
    removed = [ref for key, (ref, _) in before_index.items() if key not in after_index]
    return Diff(added=added, removed=removed, changed=changed, by_name=by_name)
