"""The Odin III adapter: IR and AST snapshots (later: the recorder and code locator)."""

from verdandi.odin3.snapshot import ast_snapshot, ir_snapshot, keep_all_asts, node_count

__all__ = ["ast_snapshot", "ir_snapshot", "keep_all_asts", "node_count"]
