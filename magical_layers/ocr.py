from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PIL import Image

from .models import BBox


@dataclass(slots=True)
class OcrWord:
    text: str
    bbox: BBox


@dataclass(slots=True)
class OcrLine:
    text: str
    bbox: BBox
    words: list[OcrWord]


def recognize_text(image: Image.Image, lang: str = "en") -> list[OcrLine]:
    """Run Windows OCR when available, returning empty results on failure."""
    try:
        import winocr  # type: ignore
    except Exception:
        return []

    try:
        raw: dict[str, Any] = winocr.recognize_pil_sync(image, lang)
    except Exception:
        return []

    lines: list[OcrLine] = []
    for raw_line in raw.get("lines", []):
        words: list[OcrWord] = []
        for raw_word in raw_line.get("words", []):
            rect = raw_word.get("bounding_rect") or {}
            text = str(raw_word.get("text") or "").strip()
            if not text:
                continue
            bbox = BBox(
                x=int(round(rect.get("x", 0))),
                y=int(round(rect.get("y", 0))),
                width=max(1, int(round(rect.get("width", 1)))),
                height=max(1, int(round(rect.get("height", 1)))),
            )
            words.append(OcrWord(text=text, bbox=bbox))
        line_text = str(raw_line.get("text") or " ".join(w.text for w in words)).strip()
        if not words or not line_text:
            continue
        left = min(w.bbox.x for w in words)
        top = min(w.bbox.y for w in words)
        right = max(w.bbox.right for w in words)
        bottom = max(w.bbox.bottom for w in words)
        lines.append(
            OcrLine(
                text=line_text,
                bbox=BBox(left, top, right - left, bottom - top),
                words=words,
            )
        )
    return merge_inline_lines(_dedupe_lines(lines))


def merge_inline_lines(lines: list[OcrLine]) -> list[OcrLine]:
    """Merge OCR fragments that are on the same visual baseline.

    Windows OCR often splits color changes into separate lines. For native PPTX
    text, those fragments should become one textbox with multiple runs.
    """
    if len(lines) < 2:
        return lines

    ordered = sorted(lines, key=lambda line: (line.bbox.y + line.bbox.height / 2, line.bbox.x))
    groups: list[list[OcrLine]] = []
    for line in ordered:
        placed = False
        center = line.bbox.y + line.bbox.height / 2
        for group in groups:
            g_top = min(item.bbox.y for item in group)
            g_bottom = max(item.bbox.bottom for item in group)
            g_center = (g_top + g_bottom) / 2
            g_height = max(item.bbox.height for item in group)
            if abs(center - g_center) > max(8, g_height * 0.33):
                continue

            left = min(item.bbox.x for item in group)
            right = max(item.bbox.right for item in group)
            gap = line.bbox.x - right if line.bbox.x >= right else left - line.bbox.right
            if gap <= max(90, g_height * 1.5):
                group.append(line)
                placed = True
                break
        if not placed:
            groups.append([line])

    merged = [_merge_group(group) for group in groups]
    return sorted(merged, key=lambda line: (line.bbox.y, line.bbox.x))


def _merge_group(group: list[OcrLine]) -> OcrLine:
    if len(group) == 1:
        return group[0]
    words = []
    for line in group:
        words.extend(line.words)
    words.sort(key=lambda word: (word.bbox.x, word.bbox.y))
    left = min(word.bbox.x for word in words)
    top = min(word.bbox.y for word in words)
    right = max(word.bbox.right for word in words)
    bottom = max(word.bbox.bottom for word in words)
    return OcrLine(
        text=" ".join(word.text for word in words),
        bbox=BBox(left, top, right - left, bottom - top),
        words=words,
    )


def _dedupe_lines(lines: list[OcrLine]) -> list[OcrLine]:
    seen: set[tuple[str, int, int, int, int]] = set()
    deduped: list[OcrLine] = []
    for line in lines:
        key = (
            line.text.lower(),
            round(line.bbox.x / 4),
            round(line.bbox.y / 4),
            round(line.bbox.width / 4),
            round(line.bbox.height / 4),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(line)
    return deduped
