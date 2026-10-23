"""The graph picture with clickable nodes: an SVG widget whose node hits carry a source loc (D6).

Graphviz's SVG puts each node in a group with the ``id`` the dot text gives it (``verdandi.graph``
names it ``vnd-<module>-<id>``), and Graphviz escapes the hyphens in the SVG source; Qt's SVG
renderer resolves the decoded id, so ``boundsOnElement`` gives a node's viewBox rectangle. A
left click is mapped from the widget's pixels into the viewBox (the SVG is fitted into the
widget's rectangle, its aspect ratio kept, centred), tested against the rectangles of the nodes
that carry a loc, and the smallest containing rectangle wins. A click on empty space reports
nothing. The widget never draws its own badges: the dot text carries them.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtSvgWidgets import QSvgWidget

from verdandi.provenance import Loc


class SvgGraph(QSvgWidget):
    """The slice picture; clicking a node reports that node's source loc."""

    def __init__(self) -> None:
        super().__init__()
        self.targets: dict[str, Loc] = {}
        self.on_node_clicked: Callable[[Loc], None] | None = None

    def set_graph(self, svg: QByteArray, targets: dict[str, Loc]) -> None:
        """Load one picture and the element-id -> loc hits a click can report."""
        self.targets = dict(targets)
        self.load(svg)

    def node_rect(self, element_id: str) -> QRectF:
        """The viewBox rectangle of one SVG element; empty when the picture lacks it."""
        return self.renderer().boundsOnElement(element_id)

    def node_at(self, point: QPointF) -> Loc | None:
        """The loc of the smallest node rectangle containing a widget point; None on empty space."""
        renderer = self.renderer()
        mapped = self._svg_point(point)
        if mapped is None:
            return None
        inside: list[tuple[QRectF, Loc]] = []
        for element_id, loc in sorted(self.targets.items()):
            if not renderer.elementExists(element_id):
                continue
            rect = renderer.boundsOnElement(element_id)
            if rect.contains(mapped):
                inside.append((rect, loc))
        if not inside:
            return None
        return min(inside, key=lambda pair: pair[0].width() * pair[0].height())[1]

    def _svg_point(self, point: QPointF) -> QPointF | None:
        """A widget point in viewBox coordinates; None without a drawable picture."""
        box = self.renderer().viewBoxF()
        if box.width() <= 0 or box.height() <= 0 or self.width() <= 0 or self.height() <= 0:
            return None
        scale = min(self.width() / box.width(), self.height() / box.height())
        if scale <= 0:
            return None
        offset_x = (self.width() - box.width() * scale) / 2
        offset_y = (self.height() - box.height() * scale) / 2
        return QPointF(
            (point.x() - offset_x) / scale + box.x(),
            (point.y() - offset_y) / scale + box.y(),
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            loc = self.node_at(event.position())
            if loc is not None and self.on_node_clicked is not None:
                self.on_node_clicked(loc)
                event.accept()
                return
        super().mousePressEvent(event)
