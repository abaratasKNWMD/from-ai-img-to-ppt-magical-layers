from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from .llm import BrainConfig, maybe_describe_plan
from .inpaint import erase_ocr_text
from .models import PipelineResult
from .ocr import recognize_text
from .ocr import OcrLine
from .segmentation import SegmentOptions, extract_raster_layers, text_layers_from_ocr


@dataclass(slots=True)
class PipelineOptions:
    enable_ocr: bool = True
    ocr_lang: str = "es"
    enable_brain: bool = False
    erase_text: bool = True
    editable_text_mode: str = "large"
    editable_text_min_height: int | None = None
    segment: SegmentOptions = field(default_factory=SegmentOptions)


def image_to_layers(image_path: str | Path, options: PipelineOptions | None = None) -> PipelineResult:
    opts = options or PipelineOptions()
    image = Image.open(image_path).convert("RGBA")

    ocr_lines = recognize_text(image, opts.ocr_lang) if opts.enable_ocr else []
    editable_lines = _select_editable_lines(image.height, ocr_lines, opts)
    raster_source = erase_ocr_text(image, editable_lines) if editable_lines and opts.erase_text else image
    raster_layers, background_color, stats = extract_raster_layers(raster_source, [], opts.segment)
    text_layers = (
        text_layers_from_ocr(image, editable_lines, background_color, opts.segment.bg_threshold)
        if opts.enable_ocr
        else []
    )

    metadata: dict[str, Any] = {
        "source": str(image_path),
        "background_color": background_color,
        "ocr_lines": len(ocr_lines),
        "editable_text_lines": len(editable_lines),
        **stats,
    }
    brain_plan = maybe_describe_plan(metadata, BrainConfig(enabled=opts.enable_brain))
    if brain_plan:
        metadata["brain_plan"] = brain_plan

    return PipelineResult(
        image_width=image.width,
        image_height=image.height,
        background_color=background_color,
        layers=[*raster_layers, *text_layers],
        metadata=metadata,
    )


def _select_editable_lines(image_height: int, lines: list[OcrLine], opts: PipelineOptions) -> list[OcrLine]:
    if not opts.enable_ocr or opts.editable_text_mode == "none":
        return []
    if opts.editable_text_mode == "all":
        return lines
    threshold = opts.editable_text_min_height
    if threshold is None:
        threshold = max(32, round(image_height * 0.04))
    return [line for line in lines if line.bbox.height >= threshold]
