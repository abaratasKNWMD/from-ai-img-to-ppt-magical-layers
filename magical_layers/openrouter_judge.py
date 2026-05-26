from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .llm import DEFAULT_FREE_BRAIN_MODELS, openrouter_model_chain

DEFAULT_JUDGE_MODELS = DEFAULT_FREE_BRAIN_MODELS.copy()


def judge_model_chain() -> list[str]:
    return openrouter_model_chain("OPENROUTER_JUDGE_MODELS", "OPENROUTER_BRAIN_MODELS", "OPENROUTER_MODEL")


@dataclass(slots=True)
class JudgeConfig:
    enabled: bool = False
    model: str = os.getenv("OPENROUTER_MODEL", DEFAULT_JUDGE_MODELS[0])
    fallback_models: list[str] | None = None
    base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    timeout_seconds: float = 90.0
    include_images: bool = True


def judge_candidates(
    image_name: str,
    candidates: list[dict[str, Any]],
    config: JudgeConfig,
) -> dict[str, Any] | None:
    if not config.enabled:
        return None
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    compact_candidates = [_compact_candidate(index, candidate) for index, candidate in enumerate(candidates)]
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": _prompt(image_name, compact_candidates),
        }
    ]
    image_content: list[dict[str, Any]] = []
    if config.include_images:
        for candidate in candidates:
            preview = candidate.get("preview")
            if preview and Path(str(preview)).exists():
                image_content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": _image_data_url(Path(str(preview)))},
                    }
                )

    models = [config.model, *(config.fallback_models or [])]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "Magical Layers Local",
    }

    attempts = [("vision", [*content, *image_content])] if image_content else []
    attempts.append(("text", content))
    last_error: Exception | None = None

    for input_mode, attempt_content in attempts:
        result, last_error = _try_models(
            models=models,
            content=attempt_content,
            headers=headers,
            base_url=config.base_url,
            timeout_seconds=config.timeout_seconds,
        )
        if result is not None:
            result["input_mode"] = input_mode
            return result
    raise RuntimeError(f"OpenRouter judge failed for all models: {last_error}")


def _try_models(
    models: list[str],
    content: list[dict[str, Any]],
    headers: dict[str, str],
    base_url: str,
    timeout_seconds: float,
) -> tuple[dict[str, Any] | None, Exception | None]:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a strict QA judge for an image-to-PPTX layer extraction pipeline. "
                "Return JSON only. Do not include markdown."
            ),
        },
        {"role": "user", "content": content},
    ]
    last_error: Exception | None = None
    for model in _dedupe(models):
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.0,
        }
        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                response = client.post(f"{base_url.rstrip('/')}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
            text = data["choices"][0]["message"]["content"]
            parsed = _parse_json(text)
            parsed["model_used"] = model
            return parsed, None
        except Exception as exc:
            last_error = exc
            continue
    return None, last_error


def _prompt(image_name: str, candidates: list[dict[str, Any]]) -> str:
    return (
        "We convert a flat source slide image into a PPTX made of movable PNG layers. "
        "Each candidate was rendered back to PNG and compared to the original. "
        "Lower MAE/RMSE and higher PSNR/edge_f1 are better, but visual acceptability and editability both matter. "
        "This product is a Magical Layers clone: prefer candidates that separate arrows, icons, labels, dark-block "
        "internal details, and individual UI elements into many movable layers, as long as the render remains visually "
        "acceptable. Do not automatically pick the lowest MAE if it clearly groups important design objects. "
        "If images are attached, each attachment is a side-by-side preview: original, rendered PPTX, diff.\n\n"
        f"Image: {image_name}\n"
        f"Candidates: {json.dumps(candidates, ensure_ascii=False, indent=2)}\n\n"
        "Return exactly this JSON shape:\n"
        "{"
        "\"winner_index\": number, "
        "\"winner_reason\": string, "
        "\"quality_score\": number, "
        "\"failure_modes\": [string], "
        "\"next_pipeline_change\": string"
        "}"
    )


def _compact_candidate(index: int, candidate: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "candidate_mode",
        "candidate_threshold",
        "mae",
        "rmse",
        "psnr",
        "edge_f1",
        "raster_layers",
        "shapes",
        "text_shapes",
        "raw_components",
        "foreground_pixels",
        "largest_layer_ratio",
        "internal_detail_layers",
        "internal_detail_base_layers",
        "local_score",
        "render_error",
    ]
    compact = {key: candidate.get(key) for key in keys if key in candidate}
    compact["index"] = index
    return compact


def _image_data_url(path: Path) -> str:
    mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _parse_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        stripped = stripped[start : end + 1]
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("OpenRouter judge did not return a JSON object")
    return parsed


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
