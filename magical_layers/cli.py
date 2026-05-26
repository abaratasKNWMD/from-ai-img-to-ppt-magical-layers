from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from .orchestrator import PipelineOptions, image_to_layers
from .presets import segment_preset
from .pptx_writer import write_pptx
from .segmentation import SegmentOptions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert a flat image into editable-ish PPTX layers.")
    parser.add_argument("image", type=Path, help="Input PNG/JPG image.")
    parser.add_argument("-o", "--output", type=Path, default=Path("outputs/magical_layers.pptx"))
    parser.add_argument("--no-ocr", action="store_true", help="Keep text as raster pixels.")
    parser.add_argument("--ocr-lang", default="es", help="Windows OCR language, for example es or en.")
    parser.add_argument("--brain", action="store_true", help="Call OpenRouter for a planning note if env key exists.")
    parser.add_argument("--no-text-erase", action="store_true", help="Skip deterministic text removal before raster segmentation.")
    parser.add_argument(
        "--editable-text",
        choices=["none", "large", "all"],
        default="large",
        help="How much OCR text to recreate as editable PowerPoint text.",
    )
    parser.add_argument("--editable-min-height", type=int, default=None)
    parser.add_argument(
        "--preset",
        choices=["heavy", "auto", "granular", "grouped", "custom"],
        default="heavy",
        help="Segmentation preset. Use custom to honor threshold/min-area flags directly.",
    )
    parser.add_argument("--bg-threshold", type=float, default=35.0)
    parser.add_argument("--surface-threshold", type=float, default=18.0)
    parser.add_argument("--dilation", type=int, default=3)
    parser.add_argument("--min-area", type=int, default=100)
    parser.add_argument("--max-layers", type=int, default=500)
    parser.add_argument("--dpi", type=float, default=112.0)
    parser.add_argument("--json", type=Path, default=None, help="Optional metadata JSON path.")
    return parser


def main() -> None:
    load_dotenv()
    args = build_parser().parse_args()
    if args.preset == "custom":
        segment = SegmentOptions(
            bg_threshold=args.bg_threshold,
            surface_threshold=args.surface_threshold,
            dilation_px=args.dilation,
            min_area_px=args.min_area,
            max_layers=args.max_layers,
        )
    else:
        segment = segment_preset(args.preset)
    options = PipelineOptions(
        enable_ocr=not args.no_ocr,
        ocr_lang=args.ocr_lang,
        enable_brain=args.brain,
        erase_text=not args.no_text_erase,
        editable_text_mode=args.editable_text,
        editable_text_min_height=args.editable_min_height,
        segment=segment,
    )
    result = image_to_layers(args.image, options)
    output = write_pptx(result, args.output, dpi=args.dpi)
    print(f"Wrote {output}")
    print(json.dumps(result.metadata, indent=2))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result.metadata, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
