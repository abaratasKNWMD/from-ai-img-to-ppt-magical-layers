from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from PIL import Image


class LayerKind(str, Enum):
    BACKGROUND = "background"
    RASTER = "raster"
    TEXT = "text"


@dataclass(slots=True)
class BBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def area(self) -> int:
        return self.width * self.height

    def padded(self, pad: int, max_width: int, max_height: int) -> "BBox":
        x = max(0, self.x - pad)
        y = max(0, self.y - pad)
        right = min(max_width, self.right + pad)
        bottom = min(max_height, self.bottom + pad)
        return BBox(x=x, y=y, width=right - x, height=bottom - y)


@dataclass(slots=True)
class TextRun:
    text: str
    color: tuple[int, int, int]


@dataclass(slots=True)
class Layer:
    id: str
    kind: LayerKind
    bbox: BBox
    image: Image.Image | None = None
    text: str | None = None
    runs: list[TextRun] = field(default_factory=list)
    color: tuple[int, int, int] | None = None
    font_size: float | None = None
    bold: bool = True
    align: str = "left"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PipelineResult:
    image_width: int
    image_height: int
    background_color: tuple[int, int, int]
    layers: list[Layer]
    metadata: dict[str, Any] = field(default_factory=dict)
