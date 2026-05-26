from __future__ import annotations

from .segmentation import SegmentOptions


def segment_preset(mode: str = "heavy", compact: bool = False) -> SegmentOptions:
    if mode == "heavy":
        return SegmentOptions(
            bg_threshold=24.0,
            surface_threshold=None,
            min_area_px=18 if compact else 5,
            min_bbox_px=1,
            max_layers=2500 if compact else 10000,
            dilation_px=0,
            crop_padding_px=1,
            alpha_low=4.0,
            alpha_high=55.0,
            partition_large_components=True,
            partition_density_threshold=0.10,
            partition_min_gap_px=3,
            partition_max_depth=9,
            extract_internal_details=True,
            filled_component_min_area_px=9000,
            filled_component_min_ratio=0.55,
            internal_detail_color_distance=46.0,
            internal_detail_min_area_px=5,
            internal_detail_max_luma=0.72,
        )
    if mode == "granular":
        return SegmentOptions(
            bg_threshold=18.0,
            surface_threshold=None,
            min_area_px=60 if compact else 12,
            min_bbox_px=2,
            max_layers=700 if compact else 3000,
            dilation_px=0,
            crop_padding_px=1,
            alpha_low=4.0,
            alpha_high=48.0,
        )
    if mode == "grouped":
        return SegmentOptions(
            bg_threshold=42.0,
            surface_threshold=18.0,
            min_area_px=180 if compact else 120,
            max_layers=260 if compact else 500,
            dilation_px=3,
        )
    return SegmentOptions(
        bg_threshold=35.0,
        surface_threshold=18.0,
        min_area_px=140 if compact else 80,
        max_layers=320 if compact else 500,
        dilation_px=3,
    )
