from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from typing import Any

import httpx


DEFAULT_FREE_BRAIN_MODELS = [
    "openrouter/free",
    "openai/gpt-oss-120b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "poolside/laguna-m.1:free",
]


@dataclass(slots=True)
class BrainConfig:
    enabled: bool = False
    models: list[str] = field(default_factory=lambda: openrouter_model_chain("OPENROUTER_BRAIN_MODELS", "OPENROUTER_MODEL"))
    base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    timeout_seconds: float = 45.0


def maybe_describe_plan(metadata: dict[str, Any], config: BrainConfig) -> dict[str, Any] | None:
    """Optional OpenRouter planning hook. It never runs unless enabled."""
    if not config.enabled:
        return None
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "Magical Layers Local",
    }
    last_error: str | None = None
    for model in _dedupe(config.models):
        payload = {
            "model": model,
            "messages": _messages(metadata),
            "temperature": 0.0,
        }
        try:
            with httpx.Client(timeout=config.timeout_seconds) as client:
                response = client.post(f"{config.base_url.rstrip('/')}/chat/completions", json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            content = data["choices"][0]["message"]["content"]
            return {
                "model_used": model,
                "content": content,
                "json": _parse_json_object(content),
            }
        except Exception as exc:
            last_error = f"{model}: {exc}"
            continue
    return {"error": last_error or "OpenRouter brain failed", "models_tried": _dedupe(config.models)}


def _messages(metadata: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are the deterministic QA brain for an image-to-layered-PPTX pipeline. "
                "Return concise JSON only. Do not use markdown."
            ),
        },
        {
            "role": "user",
            "content": (
                "Given this image-to-PPTX extraction metadata, diagnose whether layer separation "
                "is likely good enough and suggest the next deterministic pipeline change. "
                "Favor maximum editability for icons, arrows, labels, boxes, and dark blocks.\n\n"
                f"Metadata: {json.dumps(metadata, ensure_ascii=False)}\n\n"
                "Return exactly this JSON shape: "
                "{\"quality_risk\": string, \"recommended_preset\": string, "
                "\"next_pipeline_change\": string, \"confidence\": number}"
            ),
        },
    ]


def openrouter_model_chain(*env_names: str) -> list[str]:
    for name in env_names:
        value = os.getenv(name)
        if value:
            models = _split_models(value)
            if models:
                return models
    return DEFAULT_FREE_BRAIN_MODELS.copy()


def _split_models(value: str) -> list[str]:
    normalized = value.replace("\n", ",")
    return [part.strip() for part in normalized.split(",") if part.strip()]


def _parse_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        stripped = stripped[start : end + 1]
    try:
        parsed = json.loads(stripped)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
