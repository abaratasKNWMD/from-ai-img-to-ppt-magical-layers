# INGEST - Agent Handoff Notes

This file is for future LLM/code agents that need to understand and improve the project quickly.

## Mission

Build a local "AI image to editable PowerPoint" tool:

1. User uploads one or more flat generated images.
2. The system decomposes each image into movable visual layers.
3. The system writes a PPTX deck with one transformed slide per image.
4. Optional agents/models judge candidate outputs, but the core conversion stays deterministic.

Primary quality goal: maximize editability without destroying visual fidelity. In practice this means separating arrows, icons, panels, labels, dark blocks, pale surfaces, and foreground objects into sensible PPTX layers.

## Entry Points

- `server.py`
  - FastAPI web app.
  - Owns the upload UI, `/jobs` API, progress tracking, OpenRouter settings UI, and download endpoint.
  - `_run_job()` orchestrates multi-image deck creation.
- `desktop_launcher.py`
  - Windows double-click wrapper.
  - Starts `server.app` through Uvicorn in-process, chooses a free localhost port, opens the browser, and shows a small Tkinter control window.
- `build_exe.ps1`
  - Builds `dist/MagicalLayers/MagicalLayers.exe` with PyInstaller.
- `magical_layers/cli.py`
  - One-image command line converter.
- `magical_layers/batch.py`
  - Batch converter and evaluator.

## Core Modules

- `magical_layers/orchestrator.py`
  - High-level single-image conversion.
  - Loads image, runs optional OCR/text erasure, runs segmentation, writes PPTX.
- `magical_layers/segmentation.py`
  - Deterministic image decomposition.
  - Heavy mode includes small component splitting, sparse partitioning, internal detail extraction, and surface detection.
- `magical_layers/presets.py`
  - Preset definitions. `heavy` is the default and should remain the editability-first preset.
- `magical_layers/inpaint.py`
  - Lightweight deterministic fill for text removal / holes.
- `magical_layers/ocr.py`
  - Optional Windows OCR via `winocr`; safely returns empty OCR results if unavailable.
- `magical_layers/pptx_writer.py`
  - Writes single-slide and multi-slide PPTX decks using `python-pptx`.
- `magical_layers/evaluation.py`
  - Renders PPTX slides, computes MAE/PSNR/edge F1, creates previews.
- `magical_layers/agentic.py`
  - Agentic candidate race.
  - Generates multiple candidates, scores them, and selects best output.
- `magical_layers/openrouter_judge.py`
  - OpenRouter judge ensemble/fallback logic.
- `magical_layers/llm.py`
  - OpenRouter client helpers and default free model chain.
- `magical_layers/models.py`
  - Shared dataclasses.

## Current Agent Graph

For a web job with OpenRouter agents enabled:

```text
UI upload
  -> POST /jobs
    -> _run_job()
      -> for each input image
        -> run_agentic_selection()
          -> CandidateGenerator: heavy
          -> CandidateGenerator: heavy_lite
          -> CandidateGenerator: granular
          -> CandidateGenerator: balanced
          -> CandidateGenerator: light
          -> Renderer/Evaluator for each candidate
          -> PreviewSheetBuilder
          -> OpenRouterJudge ensemble
          -> LocalFallbackJudge if no valid model vote
      -> write_pptx_deck()
      -> expose /download
```

For a normal deterministic job:

```text
UI upload or CLI
  -> convert_image_to_pptx()
    -> optional OCR
    -> optional deterministic text erase
    -> segment_image()
    -> write_pptx()
```

## Important Quality Heuristics

- Do not treat large black rectangles as plain slide background by default. They may be design blocks that must remain movable.
- Preserve pale cards/shadows as surface layers. Otherwise UI-like generated images lose panels and depth.
- In heavy mode, favor more layers over smaller PPTX files.
- In heavy mode, partition sparse wide/short or tall/narrow components. Large selection boxes around long arrows, table rules, and connector bands are a quality failure even when visual render metrics look acceptable.
- Do not over-merge arrows/icons into nearby text or panels.
- OCR should be opt-in because raster text usually gives better visual fidelity than imperfect native text reconstruction.
- Full OCR mode can recover many text lines in dense diagrams, but it is experimental; validate visual output because font sizing/OCR errors can be worse than keeping text rasterized.
- If an LLM model is missing/rate-limited, the job must still finish with local deterministic scoring.

## OpenRouter Notes

Keys must never be committed. `.env` is ignored by git. `.env.example` is safe.

Default free model chain:

```text
openrouter/free
openai/gpt-oss-120b:free
nvidia/nemotron-3-super-120b-a12b:free
poolside/laguna-m.1:free
```

The UI can update the model list at runtime. Use this when free models are deprecated.

## Local Data Policy

Do not commit:

- `images/*` test inputs.
- `outputs/*` PPTX/renders/reports.
- `.env`.
- `build/*`.
- `dist/*`.
- Any pasted API key or generated binary artifact.

If public samples are needed, create `samples/` with explicitly licensed images and document their source/license.

## Verification Commands

Use these after edits:

```powershell
python -m compileall server.py desktop_launcher.py magical_layers
python -m ruff check server.py desktop_launcher.py magical_layers
```

Run the web app:

```powershell
python -m uvicorn server:app --reload --host 127.0.0.1 --port 8000
```

CLI smoke test:

```powershell
python -m magical_layers.cli images\input.png -o outputs\input_layers.pptx --no-ocr --preset heavy
```

Batch smoke test:

```powershell
python -m magical_layers.batch --input-dir images --output-dir outputs\batch_quality --limit 1 --editable-text none --bg-thresholds 35,18
```

Build EXE:

```powershell
python -m pip install -r requirements-build.txt
.\build_exe.ps1
```

## High-Value Improvements

1. Add SAM/ONNX segmentation backend behind a clean interface.
2. Add real local inpainting backend for background hole repair.
3. Add shape/vector reconstruction for arrows, icons, and simple UI primitives.
4. Add robust layer grouping: "move as group" while preserving internal components.
5. Add font matching/OCR style transfer.
6. Add automated PowerPoint render comparison in CI if a renderer is available.
7. Add an installer or self-contained app folder with persistent user config.

## Coding Style

- Keep deterministic conversion usable without any LLM/API key.
- Keep OpenRouter as optional judging/planning, not as a hard dependency.
- Prefer focused modules over one huge class.
- Keep generated artifacts out of git.
- When changing segmentation, always test on images with black blocks, arrows/icons, pale cards, small text, and high-contrast UI panels.
