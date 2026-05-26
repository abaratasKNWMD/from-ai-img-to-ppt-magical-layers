from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

from .ocr import OcrLine


def erase_ocr_text(image: Image.Image, lines: list[OcrLine], pad: int = 3) -> Image.Image:
    """Remove OCR text pixels with a tiny deterministic local fill.

    This is not generative inpainting. It estimates the local surface color around
    each OCR word and paints only ink-like pixels inside the word box. It prevents
    editable text from leaving white/transparent holes in colored cards.
    """
    if not lines:
        return image.convert("RGBA")

    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    rgb = rgba[:, :, :3]
    height, width = rgb.shape[:2]

    for line in lines:
        for word in line.words:
            box = word.bbox.padded(pad, width, height)
            if box.width < 2 or box.height < 2:
                continue

            x0, y0, x1, y1 = box.x, box.y, box.right, box.bottom
            crop = rgb[y0:y1, x0:x1]
            if crop.size == 0:
                continue

            fill = _estimate_surface_color(rgb, x0, y0, x1, y1)
            diff = np.sqrt(np.sum((crop.astype(np.float32) - fill.astype(np.float32)) ** 2, axis=2))
            ink_mask = diff > _adaptive_ink_threshold(diff)
            ink_mask = _clean_mask(ink_mask)

            if ink_mask.sum() == 0:
                continue
            crop[ink_mask] = fill

    return Image.fromarray(rgba, mode="RGBA")


def _estimate_surface_color(rgb: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> np.ndarray:
    height, width = rgb.shape[:2]
    ring_pad = max(4, min(width, height) // 220)
    rx0 = max(0, x0 - ring_pad)
    ry0 = max(0, y0 - ring_pad)
    rx1 = min(width, x1 + ring_pad)
    ry1 = min(height, y1 + ring_pad)
    patch = rgb[ry0:ry1, rx0:rx1]
    if patch.size == 0:
        return np.array([255, 255, 255], dtype=np.uint8)

    mask = np.ones(patch.shape[:2], dtype=bool)
    inner_x0 = x0 - rx0
    inner_y0 = y0 - ry0
    inner_x1 = x1 - rx0
    inner_y1 = y1 - ry0
    mask[inner_y0:inner_y1, inner_x0:inner_x1] = False
    pixels = patch[mask]
    if len(pixels) < 8:
        pixels = patch.reshape(-1, 3)

    # Reject likely ink/icon pixels and keep the local card/background surface.
    px = pixels.astype(np.float32)
    lum = 0.2126 * px[:, 0] + 0.7152 * px[:, 1] + 0.0722 * px[:, 2]
    sat = px.max(axis=1) - px.min(axis=1)
    light_or_soft = px[(lum >= np.percentile(lum, 45)) | (sat < 30)]
    if len(light_or_soft) >= 8:
        px = light_or_soft
    return np.median(px, axis=0).round().clip(0, 255).astype(np.uint8)


def _adaptive_ink_threshold(diff: np.ndarray) -> float:
    if diff.size == 0:
        return 30.0
    p75 = float(np.percentile(diff, 75))
    return max(28.0, min(80.0, p75 * 0.55))


def _clean_mask(mask: np.ndarray) -> np.ndarray:
    img = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
    img = img.filter(ImageFilter.MaxFilter(size=3))
    img = img.filter(ImageFilter.MinFilter(size=3))
    return np.asarray(img) > 0

