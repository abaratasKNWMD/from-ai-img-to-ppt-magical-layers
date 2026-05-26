from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont


@dataclass(slots=True)
class RenderResult:
    ok: bool
    image_path: Path | None = None
    error: str | None = None


def render_pptx_first_slide(
    pptx_path: str | Path,
    output_png: str | Path,
    width: int = 1600,
    height: int | None = None,
) -> RenderResult:
    try:
        import win32com.client  # type: ignore
    except Exception as exc:
        return RenderResult(ok=False, error=f"PowerPoint COM unavailable: {exc}")

    pptx = Path(pptx_path).resolve()
    output = Path(output_png).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    app = None
    pres = None
    try:
        app = win32com.client.Dispatch("PowerPoint.Application")
        pres = app.Presentations.Open(str(pptx), WithWindow=False)
        slide_width = int(pres.PageSetup.SlideWidth)
        slide_height = int(pres.PageSetup.SlideHeight)
        if height is None:
            height = max(1, round(width * slide_height / slide_width))
        pres.Slides(1).Export(str(output), "PNG", width, height)
        return RenderResult(ok=True, image_path=output)
    except Exception as exc:
        return RenderResult(ok=False, error=str(exc))
    finally:
        if pres is not None:
            try:
                pres.Close()
            except Exception:
                pass
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass


def render_pptx_slides(
    pptx_path: str | Path,
    output_dir: str | Path,
    width: int = 1600,
    max_slides: int | None = None,
) -> list[RenderResult]:
    try:
        import win32com.client  # type: ignore
    except Exception as exc:
        return [RenderResult(ok=False, error=f"PowerPoint COM unavailable: {exc}")]

    pptx = Path(pptx_path).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = None
    pres = None
    results: list[RenderResult] = []
    try:
        app = win32com.client.Dispatch("PowerPoint.Application")
        pres = app.Presentations.Open(str(pptx), WithWindow=False)
        slide_width = int(pres.PageSetup.SlideWidth)
        slide_height = int(pres.PageSetup.SlideHeight)
        height = max(1, round(width * slide_height / slide_width))
        count = int(pres.Slides.Count)
        if max_slides is not None:
            count = min(count, max_slides)
        for index in range(1, count + 1):
            slide_path = output / f"slide_{index:03d}.png"
            try:
                pres.Slides(index).Export(str(slide_path), "PNG", width, height)
                results.append(RenderResult(ok=True, image_path=slide_path))
            except Exception as exc:
                results.append(RenderResult(ok=False, error=str(exc)))
        return results
    except Exception as exc:
        return [RenderResult(ok=False, error=str(exc))]
    finally:
        if pres is not None:
            try:
                pres.Close()
            except Exception:
                pass
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass


def compare_render(original_path: str | Path, rendered_path: str | Path) -> dict[str, float]:
    original = Image.open(original_path).convert("RGB")
    rendered = Image.open(rendered_path).convert("RGB")
    original = original.resize(rendered.size, Image.Resampling.LANCZOS)
    a = np.asarray(original, dtype=np.float32)
    b = np.asarray(rendered, dtype=np.float32)
    diff = a - b
    mae = float(np.mean(np.abs(diff)))
    rmse = float(math.sqrt(np.mean(diff * diff)))
    psnr = 99.0 if rmse == 0 else float(20 * math.log10(255.0 / rmse))
    edge_f1 = _edge_f1(original, rendered)
    return {
        "mae": mae,
        "rmse": rmse,
        "psnr": psnr,
        "edge_f1": edge_f1,
    }


def make_comparison_image(
    original_path: str | Path,
    rendered_path: str | Path,
    output_path: str | Path,
    title: str,
    width: int = 1400,
) -> Path:
    original = Image.open(original_path).convert("RGB")
    rendered = Image.open(rendered_path).convert("RGB")
    original.thumbnail((width // 3, width // 3), Image.Resampling.LANCZOS)
    rendered = rendered.resize(original.size, Image.Resampling.LANCZOS)
    diff = ImageChops.difference(original, rendered)
    diff = diff.point(lambda v: min(255, v * 4))

    label_h = 34
    w, h = original.size
    sheet = Image.new("RGB", (w * 3, h + label_h * 2), "white")
    sheet.paste(original, (0, label_h))
    sheet.paste(rendered, (w, label_h))
    sheet.paste(diff, (w * 2, label_h))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
        small = ImageFont.truetype("arial.ttf", 13)
    except Exception:
        font = None
        small = None
    draw.text((8, 7), "Original", fill=(0, 0, 0), font=font)
    draw.text((w + 8, 7), "Rendered PPTX", fill=(0, 0, 0), font=font)
    draw.text((w * 2 + 8, 7), "Diff x4", fill=(0, 0, 0), font=font)
    draw.text((8, h + label_h + 7), title[:160], fill=(0, 0, 0), font=small)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=92)
    return output


def write_html_report(rows: list[dict[str, Any]], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    html_rows = []
    for row in rows:
        preview = row.get("preview")
        preview_html = f'<a href="{Path(preview).name}"><img src="{Path(preview).name}" loading="lazy"></a>' if preview else ""
        html_rows.append(
            "<tr>"
            f"<td>{row.get('index')}</td>"
            f"<td>{_escape(row.get('name', ''))}</td>"
            f"<td>{_escape(row.get('selected_mode', ''))}@{_escape(row.get('selected_threshold', ''))}</td>"
            f"<td>{row.get('editable_text_lines', '')}/{row.get('ocr_lines', '')}</td>"
            f"<td>{row.get('raster_layers', '')}</td>"
            f"<td>{_fmt(row.get('mae'))}</td>"
            f"<td>{_fmt(row.get('psnr'))}</td>"
            f"<td>{_fmt(row.get('edge_f1'))}</td>"
            f"<td>{preview_html}</td>"
            "</tr>"
        )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Magical Layers Batch Report</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; color: #181818; background: #fafafa; }}
    table {{ border-collapse: collapse; width: 100%; background: white; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
    th {{ background: #f1f1f1; text-align: left; }}
    img {{ width: 420px; max-width: 45vw; height: auto; display: block; }}
    .hint {{ color: #666; }}
  </style>
</head>
<body>
  <h1>Magical Layers Batch Report</h1>
  <p class="hint">Lower MAE and higher PSNR/edge F1 are better. Use previews for visual judgment.</p>
  <table>
    <thead><tr><th>#</th><th>Image</th><th>Mode</th><th>Editable/OCR</th><th>Raster</th><th>MAE</th><th>PSNR</th><th>Edge F1</th><th>Preview</th></tr></thead>
    <tbody>{''.join(html_rows)}</tbody>
  </table>
</body>
</html>"""
    output.write_text(html, encoding="utf-8")
    return output


def _edge_f1(a: Image.Image, b: Image.Image) -> float:
    ag = np.asarray(a.convert("L"), dtype=np.float32)
    bg = np.asarray(b.convert("L"), dtype=np.float32)
    ae = _edges(ag)
    be = _edges(bg)
    tp = float(np.logical_and(ae, be).sum())
    fp = float(np.logical_and(~ae, be).sum())
    fn = float(np.logical_and(ae, ~be).sum())
    if tp == 0 and fp == 0 and fn == 0:
        return 1.0
    return float(2 * tp / max(1.0, 2 * tp + fp + fn))


def _edges(gray: np.ndarray) -> np.ndarray:
    gx = np.zeros_like(gray)
    gy = np.zeros_like(gray)
    gx[:, 1:] = np.abs(gray[:, 1:] - gray[:, :-1])
    gy[1:, :] = np.abs(gray[1:, :] - gray[:-1, :])
    mag = np.maximum(gx, gy)
    threshold = max(12.0, float(np.percentile(mag, 91)))
    return mag >= threshold


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.3f}"
    except Exception:
        return str(value)


def _escape(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
