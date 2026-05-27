from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np
from PIL import Image, ImageFilter

from .models import BBox, Layer, LayerKind, TextRun
from .ocr import OcrLine


@dataclass(slots=True)
class SegmentOptions:
    bg_threshold: float = 35.0
    surface_threshold: float | None = 18.0
    surface_min_pixels: int = 800
    alpha_low: float = 12.0
    alpha_high: float = 70.0
    dilation_px: int = 3
    crop_padding_px: int = 3
    min_area_px: int = 100
    min_bbox_px: int = 5
    max_layers: int = 500
    text_padding_px: int = 3
    partition_large_components: bool = False
    partition_min_area_px: int = 25000
    partition_min_span_px: int = 140
    partition_min_gap_px: int = 10
    partition_density_threshold: float = 0.012
    partition_max_depth: int = 7
    extract_internal_details: bool = False
    filled_component_min_area_px: int = 12000
    filled_component_min_ratio: float = 0.28
    internal_detail_color_distance: float = 52.0
    internal_detail_min_area_px: int = 8
    internal_detail_max_luma: float = 0.72


@dataclass(slots=True)
class _Run:
    y: int
    start: int
    end: int
    label: int


@dataclass(slots=True)
class _Component:
    label: int
    runs: list[_Run] = field(default_factory=list)
    area: int = 0
    min_x: int = 10**9
    min_y: int = 10**9
    max_x: int = -1
    max_y: int = -1

    @property
    def bbox(self) -> BBox:
        return BBox(self.min_x, self.min_y, self.max_x - self.min_x + 1, self.max_y - self.min_y + 1)


class _UnionFind:
    def __init__(self) -> None:
        self.parent: list[int] = []
        self.rank: list[int] = []

    def make(self) -> int:
        label = len(self.parent)
        self.parent.append(label)
        self.rank.append(0)
        return label

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
        else:
            self.parent[rb] = ra
            self.rank[ra] += 1


def estimate_background_color(image: Image.Image) -> tuple[int, int, int]:
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    candidates = [_corner_background_color(rgb)]
    sampled = _background_sample(image)
    border = _sample_border(sampled)
    candidates.extend(_top_quantized_colors(sampled, limit=12))
    candidates.extend(_top_quantized_colors(border, limit=8))
    candidates = _dedupe_colors(candidates)
    best = max(candidates, key=lambda color: _background_candidate_score(sampled, border, color))
    return _refine_background_color(sampled, best)


def _corner_background_color(rgb: np.ndarray) -> tuple[int, int, int]:
    h, w, _ = rgb.shape
    sample = max(8, min(h, w) // 24)
    patches = np.concatenate(
        [
            rgb[:sample, :sample].reshape(-1, 3),
            rgb[:sample, w - sample :].reshape(-1, 3),
            rgb[h - sample :, :sample].reshape(-1, 3),
            rgb[h - sample :, w - sample :].reshape(-1, 3),
        ],
        axis=0,
    )
    median = np.median(patches, axis=0)
    return tuple(int(round(v)) for v in median)


def _background_sample(image: Image.Image, max_side: int = 192) -> np.ndarray:
    sampled = image.convert("RGB").copy()
    sampled.thumbnail((max_side, max_side), Image.Resampling.BOX)
    return np.asarray(sampled, dtype=np.uint8)


def _sample_border(rgb: np.ndarray) -> np.ndarray:
    h, w, _ = rgb.shape
    band = max(2, min(h, w) // 18)
    return np.concatenate(
        [
            rgb[:band, :, :].reshape(-1, 3),
            rgb[h - band :, :, :].reshape(-1, 3),
            rgb[:, :band, :].reshape(-1, 3),
            rgb[:, w - band :, :].reshape(-1, 3),
        ],
        axis=0,
    )


def _top_quantized_colors(rgb: np.ndarray, limit: int) -> list[tuple[int, int, int]]:
    pixels = rgb.reshape(-1, 3).astype(np.uint32)
    quantized = (pixels // 16) * 16 + 8
    packed = (quantized[:, 0] << 16) | (quantized[:, 1] << 8) | quantized[:, 2]
    values, counts = np.unique(packed, return_counts=True)
    order = np.argsort(counts)[::-1][:limit]
    colors: list[tuple[int, int, int]] = []
    for index in order:
        value = int(values[index])
        colors.append(((value >> 16) & 255, (value >> 8) & 255, value & 255))
    return colors


def _dedupe_colors(colors: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    deduped: list[tuple[int, int, int]] = []
    for color in colors:
        if color not in deduped:
            deduped.append(color)
    return deduped


def _background_candidate_score(
    sampled: np.ndarray,
    border: np.ndarray,
    color: tuple[int, int, int],
) -> tuple[float, float, float]:
    sample_distance = _color_distance(sampled, color)
    border_distance = _color_distance(border.reshape(-1, 1, 3), color).reshape(-1)
    coverage = float(np.mean(sample_distance <= 30.0))
    border_coverage = float(np.mean(border_distance <= 30.0))
    luma = (color[0] * 0.2126 + color[1] * 0.7152 + color[2] * 0.0722) / 255.0
    return (coverage, border_coverage, luma)


def _refine_background_color(sampled: np.ndarray, color: tuple[int, int, int]) -> tuple[int, int, int]:
    distance = _color_distance(sampled, color)
    pixels = sampled[distance <= 30.0]
    if pixels.size == 0:
        return color
    median = np.median(pixels, axis=0)
    return tuple(int(round(v)) for v in median)


def _color_distance(rgb: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    values = rgb.astype(np.float32)
    target = np.asarray(color, dtype=np.float32).reshape(1, 1, 3)
    return np.sqrt(np.sum((values - target) ** 2, axis=2)).astype(np.float32)


def build_text_mask(size: tuple[int, int], lines: list[OcrLine], padding: int) -> np.ndarray:
    width, height = size
    mask = np.zeros((height, width), dtype=bool)
    for line in lines:
        for word in line.words:
            box = word.bbox.padded(padding, width, height)
            mask[box.y : box.bottom, box.x : box.right] = True
    return mask


def foreground_mask(
    image: Image.Image,
    background_color: tuple[int, int, int],
    threshold: float,
    text_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    bg = np.asarray(background_color, dtype=np.float32).reshape(1, 1, 3)
    distance = np.sqrt(np.sum((rgb - bg) ** 2, axis=2)).astype(np.float32)
    mask = distance > threshold
    if text_mask is not None:
        mask &= ~text_mask
    return mask, distance


def dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask
    img = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
    size = radius * 2 + 1
    img = img.filter(ImageFilter.MaxFilter(size=size))
    return np.asarray(img) > 0


def extract_raster_layers(
    image: Image.Image,
    lines: list[OcrLine],
    options: SegmentOptions,
) -> tuple[list[Layer], tuple[int, int, int], dict[str, int | float]]:
    image = image.convert("RGBA")
    width, height = image.size
    background_color = estimate_background_color(image)
    text_mask = build_text_mask(image.size, lines, options.text_padding_px) if lines else None
    raw_mask, distance = foreground_mask(image, background_color, options.bg_threshold, text_mask)
    work_mask = dilate(raw_mask, options.dilation_px)
    components = find_components(work_mask)

    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    layers: list[Layer] = []
    surface_layer = _extract_surface_layer(image, rgb, background_color, raw_mask, distance, options)
    if surface_layer is not None:
        layers.append(surface_layer)

    alpha_base = np.clip(
        (distance - options.alpha_low) / max(1.0, options.alpha_high - options.alpha_low) * 255.0,
        0,
        255,
    ).astype(np.uint8)
    alpha_base[~raw_mask] = 0

    filtered = [
        comp
        for comp in components
        if comp.area >= options.min_area_px
        and comp.bbox.width >= options.min_bbox_px
        and comp.bbox.height >= options.min_bbox_px
    ]
    filtered.sort(key=lambda c: (c.bbox.area, c.area), reverse=True)
    filtered = filtered[: options.max_layers]
    if options.partition_large_components:
        filtered = _partition_components(filtered, work_mask, options)
        filtered.sort(key=lambda c: (c.bbox.area, c.area), reverse=True)
        filtered = filtered[: options.max_layers]

    emitted_layers = 0
    for index, comp in enumerate(filtered, start=1):
        new_layers = _component_layers(image, rgb, alpha_base, comp, options, index)
        emitted_layers += len(new_layers)
        layers.extend(new_layers)

    layers.sort(key=lambda layer: (layer.bbox.area, layer.bbox.y, layer.bbox.x), reverse=True)
    stats = {
        "raw_components": len(components),
        "raster_layers": len(layers),
        "emitted_component_layers": emitted_layers,
        "foreground_pixels": int(raw_mask.sum()),
    }
    return layers, background_color, stats


def _partition_components(
    components: list[_Component],
    mask: np.ndarray,
    options: SegmentOptions,
) -> list[_Component]:
    partitioned: list[_Component] = []
    for comp in components:
        bbox = comp.bbox
        if (
            bbox.area < options.partition_min_area_px
            or (bbox.width < options.partition_min_span_px and bbox.height < options.partition_min_span_px)
        ):
            partitioned.append(comp)
            continue

        crop_mask = _component_mask(comp, bbox)
        regions = _split_mask_regions(crop_mask, bbox.x, bbox.y, options, 0)
        if len(regions) == 1:
            partitioned.append(comp)
            continue
        for region_mask, offset_x, offset_y in regions:
            if int(region_mask.sum()) == 0:
                continue
            for local_comp in find_components(region_mask):
                if local_comp.area <= 0:
                    continue
                partitioned.append(_offset_component(local_comp, offset_x, offset_y))
    return partitioned


def _split_mask_regions(
    mask: np.ndarray,
    offset_x: int,
    offset_y: int,
    options: SegmentOptions,
    depth: int,
) -> list[tuple[np.ndarray, int, int]]:
    height, width = mask.shape
    if (
        depth >= options.partition_max_depth
        or (width < options.partition_min_span_px and height < options.partition_min_span_px)
        or int(mask.sum()) < options.partition_min_area_px
    ):
        return [(mask, offset_x, offset_y)]

    split = _best_sparse_split(mask, options)
    if split is None:
        return [(mask, offset_x, offset_y)]

    axis, index = split
    if axis == 0:
        first = mask[:index, :]
        second = mask[index:, :]
        return [
            *_split_mask_regions(first, offset_x, offset_y, options, depth + 1),
            *_split_mask_regions(second, offset_x, offset_y + index, options, depth + 1),
        ]
    first = mask[:, :index]
    second = mask[:, index:]
    return [
        *_split_mask_regions(first, offset_x, offset_y, options, depth + 1),
        *_split_mask_regions(second, offset_x + index, offset_y, options, depth + 1),
    ]


def _best_sparse_split(mask: np.ndarray, options: SegmentOptions) -> tuple[int, int] | None:
    height, width = mask.shape
    col_density = mask.sum(axis=0) / max(1, height)
    row_density = mask.sum(axis=1) / max(1, width)
    col_gap = (
        _longest_sparse_run(col_density, options.partition_density_threshold, options.partition_min_gap_px)
        if width >= options.partition_min_span_px
        else None
    )
    row_gap = (
        _longest_sparse_run(row_density, options.partition_density_threshold, options.partition_min_gap_px)
        if height >= options.partition_min_span_px
        else None
    )
    candidates: list[tuple[float, int, int]] = []
    if col_gap is not None:
        start, end = col_gap
        index = (start + end) // 2
        if index >= options.partition_min_gap_px and width - index >= options.partition_min_gap_px:
            candidates.append(((end - start) / max(1, width), 1, index))
    if row_gap is not None:
        start, end = row_gap
        index = (start + end) // 2
        if index >= options.partition_min_gap_px and height - index >= options.partition_min_gap_px:
            candidates.append(((end - start) / max(1, height), 0, index))
    if not candidates:
        return None
    _, axis, index = max(candidates)
    return axis, index


def _longest_sparse_run(values: np.ndarray, threshold: float, min_gap: int) -> tuple[int, int] | None:
    sparse = values <= threshold
    best: tuple[int, int] | None = None
    start: int | None = None
    for index, value in enumerate(sparse):
        if value and start is None:
            start = index
        elif not value and start is not None:
            if index - start >= min_gap and (best is None or index - start > best[1] - best[0]):
                best = (start, index)
            start = None
    if start is not None and len(sparse) - start >= min_gap:
        if best is None or len(sparse) - start > best[1] - best[0]:
            best = (start, len(sparse))
    return best


def _offset_component(comp: _Component, offset_x: int, offset_y: int) -> _Component:
    return _Component(
        label=comp.label,
        runs=[_Run(run.y + offset_y, run.start + offset_x, run.end + offset_x, run.label) for run in comp.runs],
        area=comp.area,
        min_x=comp.min_x + offset_x,
        min_y=comp.min_y + offset_y,
        max_x=comp.max_x + offset_x,
        max_y=comp.max_y + offset_y,
    )


def _component_layers(
    image: Image.Image,
    rgb: np.ndarray,
    alpha_base: np.ndarray,
    comp: _Component,
    options: SegmentOptions,
    index: int,
) -> list[Layer]:
    bbox = comp.bbox.padded(options.crop_padding_px, image.width, image.height)
    component_mask = _component_mask(comp, bbox)
    crop_rgb = rgb[bbox.y : bbox.bottom, bbox.x : bbox.right]
    crop_alpha = alpha_base[bbox.y : bbox.bottom, bbox.x : bbox.right].copy()
    crop_alpha[~component_mask] = 0
    if crop_alpha.max(initial=0) == 0:
        return []

    if options.extract_internal_details:
        layers = _filled_component_layers(crop_rgb, crop_alpha, component_mask, bbox, comp, options, index)
        if layers:
            return layers

    return [
        Layer(
            id=f"raster_{index:03d}",
            kind=LayerKind.RASTER,
            bbox=bbox,
            image=Image.fromarray(np.dstack([crop_rgb, crop_alpha]), mode="RGBA"),
            metadata={"area": comp.area},
        )
    ]


def _component_mask(comp: _Component, bbox: BBox) -> np.ndarray:
    component_mask = np.zeros((bbox.height, bbox.width), dtype=bool)
    for run in comp.runs:
        y = run.y - bbox.y
        x0 = max(run.start, bbox.x) - bbox.x
        x1 = min(run.end + 1, bbox.right) - bbox.x
        if 0 <= y < bbox.height and x1 > x0:
            component_mask[y, x0:x1] = True
    return component_mask


def _filled_component_layers(
    crop_rgb: np.ndarray,
    crop_alpha: np.ndarray,
    component_mask: np.ndarray,
    bbox: BBox,
    comp: _Component,
    options: SegmentOptions,
    index: int,
) -> list[Layer]:
    fill_ratio = comp.area / max(1, bbox.area)
    if comp.area < options.filled_component_min_area_px or fill_ratio < options.filled_component_min_ratio:
        return []

    component_pixels = crop_rgb[component_mask]
    if component_pixels.size == 0:
        return []
    dominant = _dominant_rgb(component_pixels)
    dominant_luma = _luma(dominant)
    if dominant_luma > options.internal_detail_max_luma:
        return []
    detail_distance = _color_distance(crop_rgb, dominant)
    detail_mask = component_mask & (detail_distance >= options.internal_detail_color_distance)
    if int(detail_mask.sum()) < options.internal_detail_min_area_px:
        return []

    base_rgb = crop_rgb.copy()
    base_rgb[detail_mask] = np.asarray(dominant, dtype=np.uint8)
    layers = [
        Layer(
            id=f"raster_{index:03d}_base",
            kind=LayerKind.RASTER,
            bbox=bbox,
            image=Image.fromarray(np.dstack([base_rgb, crop_alpha]), mode="RGBA"),
            metadata={"area": comp.area, "internal_detail_base": True, "dominant_color": dominant},
        )
    ]

    detail_components = find_components(detail_mask)
    detail_components.sort(key=lambda c: (c.bbox.area, c.area), reverse=True)
    detail_count = 0
    for detail in detail_components:
        if (
            detail.area < options.internal_detail_min_area_px
            or detail.bbox.width < options.min_bbox_px
            or detail.bbox.height < options.min_bbox_px
        ):
            continue
        detail_count += 1
        detail_bbox = detail.bbox.padded(options.crop_padding_px, bbox.width, bbox.height)
        detail_component_mask = _component_mask(detail, detail_bbox)
        detail_rgb = crop_rgb[detail_bbox.y : detail_bbox.bottom, detail_bbox.x : detail_bbox.right]
        detail_alpha = crop_alpha[detail_bbox.y : detail_bbox.bottom, detail_bbox.x : detail_bbox.right].copy()
        detail_alpha[~detail_component_mask] = 0
        if detail_alpha.max(initial=0) == 0:
            continue
        layers.append(
            Layer(
                id=f"raster_{index:03d}_detail_{detail_count:03d}",
                kind=LayerKind.RASTER,
                bbox=BBox(
                    x=bbox.x + detail_bbox.x,
                    y=bbox.y + detail_bbox.y,
                    width=detail_bbox.width,
                    height=detail_bbox.height,
                ),
                image=Image.fromarray(np.dstack([detail_rgb, detail_alpha]), mode="RGBA"),
                metadata={"area": detail.area, "internal_detail": True},
            )
        )
    return layers


def _dominant_rgb(pixels: np.ndarray) -> tuple[int, int, int]:
    quantized = (pixels.astype(np.uint32) // 16) * 16 + 8
    packed = (quantized[:, 0] << 16) | (quantized[:, 1] << 8) | quantized[:, 2]
    values, counts = np.unique(packed, return_counts=True)
    value = int(values[int(np.argmax(counts))])
    color = ((value >> 16) & 255, (value >> 8) & 255, value & 255)
    distance = _color_distance(pixels.reshape(-1, 1, 3), color).reshape(-1)
    close = pixels[distance <= 28.0]
    if close.size == 0:
        return color
    median = np.median(close, axis=0)
    return tuple(int(round(v)) for v in median)


def _luma(color: tuple[int, int, int]) -> float:
    return (color[0] * 0.2126 + color[1] * 0.7152 + color[2] * 0.0722) / 255.0


def _extract_surface_layer(
    image: Image.Image,
    rgb: np.ndarray,
    background_color: tuple[int, int, int],
    high_mask: np.ndarray,
    distance: np.ndarray,
    options: SegmentOptions,
) -> Layer | None:
    if options.surface_threshold is None or options.surface_threshold >= options.bg_threshold:
        return None
    low_mask, _ = foreground_mask(image, background_color, options.surface_threshold, None)
    subtle_mask = low_mask & ~dilate(high_mask, max(1, options.dilation_px))
    if int(subtle_mask.sum()) < options.surface_min_pixels:
        return None
    bbox = _bbox_from_mask(subtle_mask)
    if bbox is None:
        return None
    bbox = bbox.padded(options.crop_padding_px, image.width, image.height)
    crop_mask = subtle_mask[bbox.y : bbox.bottom, bbox.x : bbox.right]
    crop_rgb = rgb[bbox.y : bbox.bottom, bbox.x : bbox.right]
    crop_alpha = np.zeros((bbox.height, bbox.width), dtype=np.uint8)
    crop_alpha[crop_mask] = 255
    layer_image = Image.fromarray(np.dstack([crop_rgb, crop_alpha]), mode="RGBA")
    return Layer(
        id="surface_001",
        kind=LayerKind.RASTER,
        bbox=bbox,
        image=layer_image,
        metadata={"surface_pixels": int(subtle_mask.sum())},
    )


def _bbox_from_mask(mask: np.ndarray) -> BBox | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    left = int(xs.min())
    top = int(ys.min())
    right = int(xs.max()) + 1
    bottom = int(ys.max()) + 1
    return BBox(left, top, right - left, bottom - top)


def find_components(mask: np.ndarray) -> list[_Component]:
    height, _ = mask.shape
    uf = _UnionFind()
    all_runs: list[_Run] = []
    previous: list[_Run] = []

    for y in range(height):
        row_runs = _row_runs(mask[y])
        current: list[_Run] = []
        prev_i = 0
        for start, end in row_runs:
            label = uf.make()
            run = _Run(y=y, start=start, end=end, label=label)
            while prev_i < len(previous) and previous[prev_i].end < start - 1:
                prev_i += 1
            j = prev_i
            while j < len(previous) and previous[j].start <= end + 1:
                if previous[j].end >= start - 1:
                    uf.union(label, previous[j].label)
                j += 1
            current.append(run)
            all_runs.append(run)
        previous = current

    by_root: dict[int, _Component] = {}
    for run in all_runs:
        root = uf.find(run.label)
        comp = by_root.get(root)
        if comp is None:
            comp = _Component(label=root)
            by_root[root] = comp
        comp.runs.append(run)
        width = run.end - run.start + 1
        comp.area += width
        comp.min_x = min(comp.min_x, run.start)
        comp.max_x = max(comp.max_x, run.end)
        comp.min_y = min(comp.min_y, run.y)
        comp.max_y = max(comp.max_y, run.y)

    return list(by_root.values())


def _row_runs(row: np.ndarray) -> list[tuple[int, int]]:
    true_idx = np.flatnonzero(row)
    if true_idx.size == 0:
        return []
    splits = np.flatnonzero(np.diff(true_idx) > 1) + 1
    groups = np.split(true_idx, splits)
    return [(int(group[0]), int(group[-1])) for group in groups if group.size]


def text_layers_from_ocr(
    image: Image.Image,
    lines: list[OcrLine],
    background_color: tuple[int, int, int],
    threshold: float,
) -> list[Layer]:
    text_layers: list[Layer] = []
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    bg = np.asarray(background_color, dtype=np.float32)

    for index, line in enumerate(lines, start=1):
        bbox = line.bbox.padded(2, image.width, image.height)
        crop = rgb[bbox.y : bbox.bottom, bbox.x : bbox.right]
        if crop.size == 0:
            continue
        diff = np.sqrt(np.sum((crop.astype(np.float32) - bg) ** 2, axis=2))
        pixels = crop[diff > threshold]
        color = _dominant_color(pixels)
        runs = _colored_runs_for_line(image, line, background_color, threshold)
        font_size = _estimate_font_size(line.text, line.bbox)
        text_layers.append(
            Layer(
                id=f"text_{index:03d}",
                kind=LayerKind.TEXT,
                bbox=bbox,
                text=line.text,
                runs=runs or [TextRun(line.text, color)],
                color=color,
                font_size=font_size,
                bold=_looks_bold(line.text, line.bbox.height),
                metadata={"words": len(line.words)},
            )
        )
    return text_layers


def _dominant_color(pixels: np.ndarray) -> tuple[int, int, int]:
    if pixels.size == 0:
        return (0, 0, 0)
    px = pixels.reshape(-1, 3).astype(np.float32)
    # Keep saturated colored pixels when they exist; otherwise use dark/ink pixels.
    maxc = px.max(axis=1)
    minc = px.min(axis=1)
    sat = maxc - minc
    colored = px[sat > 35]
    if len(colored) > max(8, len(px) // 12):
        px = colored
    else:
        lum = 0.2126 * px[:, 0] + 0.7152 * px[:, 1] + 0.0722 * px[:, 2]
        dark = px[lum < np.percentile(lum, 60)]
        if len(dark):
            px = dark
    med = np.median(px, axis=0)
    return tuple(int(max(0, min(255, round(v)))) for v in med)


def _colored_runs_for_line(
    image: Image.Image,
    line: OcrLine,
    background_color: tuple[int, int, int],
    threshold: float,
) -> list[TextRun]:
    # Word-level colors are a cheap deterministic approximation. Brand words with
    # per-letter colors use a horizontal ink-color split below.
    multicolor = _split_multicolor_single_word(image, line, background_color, threshold)
    if multicolor:
        return multicolor

    runs: list[TextRun] = []
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    bg = np.asarray(background_color, dtype=np.float32)
    for i, word in enumerate(line.words):
        bbox = word.bbox.padded(1, image.width, image.height)
        crop = rgb[bbox.y : bbox.bottom, bbox.x : bbox.right]
        diff = np.sqrt(np.sum((crop.astype(np.float32) - bg) ** 2, axis=2))
        color = _dominant_color(crop[diff > threshold])
        text = word.text
        if i < len(line.words) - 1:
            text += " "
        runs.append(TextRun(text=text, color=color))
    return runs


def _split_multicolor_single_word(
    image: Image.Image,
    line: OcrLine,
    background_color: tuple[int, int, int],
    threshold: float,
) -> list[TextRun]:
    if len(line.words) != 1 or " " in line.text or len(line.text) < 5:
        return []

    word = line.words[0]
    bbox = word.bbox.padded(2, image.width, image.height)
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    crop = rgb[bbox.y : bbox.bottom, bbox.x : bbox.right]
    if crop.size == 0:
        return []

    bg = np.asarray(background_color, dtype=np.float32)
    diff = np.sqrt(np.sum((crop.astype(np.float32) - bg) ** 2, axis=2))
    ink = diff > threshold
    cols = np.flatnonzero(ink.any(axis=0))
    if cols.size < 12:
        return []

    first = int(cols[0])
    last = int(cols[-1])
    color_code = np.zeros(last - first + 1, dtype=np.int8)
    last_code = 0
    for x in range(first, last + 1):
        px = crop[:, x][ink[:, x]]
        if len(px):
            med = np.median(px.astype(np.float32), axis=0)
            sat = float(med.max() - med.min())
            lum = float(0.2126 * med[0] + 0.7152 * med[1] + 0.0722 * med[2])
            last_code = 1 if sat > 45 and lum > 60 else 0
        color_code[x - first] = last_code

    # Smooth away antialiasing noise and tiny gaps between glyph strokes.
    if color_code.size >= 9:
        smoothed = color_code.copy()
        for i in range(color_code.size):
            window = color_code[max(0, i - 4) : min(color_code.size, i + 5)]
            smoothed[i] = 1 if window.mean() >= 0.5 else 0
        color_code = smoothed

    bands: list[tuple[int, int, int]] = []
    start = 0
    for i in range(1, len(color_code)):
        if color_code[i] != color_code[start]:
            bands.append((start, i - 1, int(color_code[start])))
            start = i
    bands.append((start, len(color_code) - 1, int(color_code[start])))
    bands = _merge_short_bands(bands, min_width=max(4, len(color_code) // 20))
    if len({band[2] for band in bands}) < 2 or len(bands) < 2:
        return []

    text = line.text
    n = len(text)
    total = max(1, len(color_code))
    runs: list[TextRun] = []
    previous_char_end = 0
    for index, (band_start, band_end, _code) in enumerate(bands):
        if index == len(bands) - 1:
            char_end = n
        else:
            char_end = max(previous_char_end + 1, round((band_end + 1) / total * n))
        char_start = previous_char_end
        if char_start >= n or char_end <= char_start:
            continue
        x0 = first + band_start
        x1 = first + band_end + 1
        band_pixels = crop[:, x0:x1][ink[:, x0:x1]]
        runs.append(TextRun(text=text[char_start:char_end], color=_dominant_color(band_pixels)))
        previous_char_end = char_end

    if "".join(run.text for run in runs) != text:
        return []
    return runs


def _merge_short_bands(bands: list[tuple[int, int, int]], min_width: int) -> list[tuple[int, int, int]]:
    merged = bands[:]
    changed = True
    while changed and len(merged) > 1:
        changed = False
        next_bands: list[tuple[int, int, int]] = []
        i = 0
        while i < len(merged):
            start, end, code = merged[i]
            width = end - start + 1
            if width < min_width:
                if next_bands:
                    ps, pe, pc = next_bands.pop()
                    next_bands.append((ps, end, pc))
                elif i + 1 < len(merged):
                    ns, ne, nc = merged[i + 1]
                    next_bands.append((start, ne, nc))
                    i += 1
                else:
                    next_bands.append((start, end, code))
                changed = True
            else:
                next_bands.append((start, end, code))
            i += 1
        merged = next_bands
    return merged


def _looks_bold(text: str, height: int) -> bool:
    return text.upper() == text or height >= 24


def _estimate_font_size(text: str, bbox: BBox, dpi: float = 112.0) -> float:
    if not text:
        return 12.0
    height_based = bbox.height * 72.0 / (dpi * 0.82)
    effective_chars = max(1.0, sum(0.55 if char == " " else 1.0 for char in text))
    width_based = bbox.width * 72.0 / (dpi * 0.56 * effective_chars)
    return max(5.0, min(72.0, height_based, width_based * 0.96))
