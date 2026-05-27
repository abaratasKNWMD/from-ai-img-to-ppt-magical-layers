# From AI Img to PPT - Magical Layers

Local image-to-PPTX layer extractor. Upload one or more flat PNG/JPG images and get a PowerPoint deck where visual regions are rebuilt as movable transparent raster layers, with optional OCR text reconstruction and optional OpenRouter-based candidate judging.

This is an open, deterministic approximation of "magic layers" style products. It is not a perfect clone of a closed commercial system, but it is designed to be hackable: segmentation, inpainting, OCR, scoring, and model judging are separate modules.

## What It Does

- Converts one image into one layered PPTX slide.
- Converts multiple images into one PPTX deck with one slide per image.
- Uses a heavy default preset that favors maximum object separation.
- Keeps black UI blocks, arrows, icons, small components, and pale surfaces as movable raster layers where possible.
- Optionally detects OCR text and recreates large text as native PowerPoint text boxes.
- Optionally runs an OpenRouter "brain" that judges multiple conversion candidates and picks the best one.
- Includes a browser UI, CLI tools, batch evaluation, and a Windows double-click launcher.

## What Is Committed

This repository should contain source code and documentation only:

- `server.py` - FastAPI web UI and job orchestration.
- `desktop_launcher.py` - Windows double-click launcher that starts the local server.
- `build_exe.ps1` - PyInstaller build script.
- `magical_layers/` - conversion, segmentation, OCR, PPTX, judging, and evaluation modules.
- `requirements.txt` - runtime dependencies.
- `requirements-build.txt` - optional Windows EXE build dependencies.
- `.env.example` - safe config template with no real keys.
- `INGEST.MD` - architecture notes for future LLM/code agents.

Local images, generated PPTX files, renders, logs, `.env`, `build/`, and `dist/` are ignored by git. The `images/` folder is intentionally kept empty except for `.gitkeep`; add your own test images locally.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Optional Windows OCR and EXE build dependencies:

```powershell
python -m pip install -r requirements-build.txt
```

If an API key was ever pasted into chat, logs, screenshots, or commits, revoke it. Put new keys only in `.env` or through the web UI settings.

## Run The Web App

```powershell
python -m uvicorn server:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

Use the UI to upload one or many images, choose processing options, watch the progress bar, and download the generated PPTX.

For dense architecture diagrams, keep **Pesado** selected and leave OCR off for the closest visual match. If you need native PowerPoint text objects, enable OCR and choose either large-text-only or the experimental all-text mode. All-text OCR is useful for analysis, but it can reduce visual fidelity on small dense labels.

The main job endpoints are:

- `POST /jobs` - create a conversion job. Send `files` for multi-image decks or legacy `file` for one image.
- `GET /jobs/{job_id}` - read status, progress, quality metrics, and download URL.
- `GET /jobs/{job_id}/download` - download the finished deck.
- `POST /convert` - legacy direct one-image conversion.

## Run From CLI

Best editability, text kept as raster pixels:

```powershell
python -m magical_layers.cli images\input.png -o outputs\input_layers.pptx --no-ocr --preset heavy
```

With metadata JSON:

```powershell
python -m magical_layers.cli images\input.png -o outputs\input_layers.pptx --json outputs\input_layers.json
```

Preset options:

```text
heavy     default, maximum separation
auto      balanced visual fidelity and layer count
granular  aggressive components, but less extreme than heavy
grouped   fewer layers, smaller PPTX files
custom    honor threshold/min-area flags directly
```

## Batch Evaluation

Put local test images in `images/`, then run:

```powershell
python -m magical_layers.batch --input-dir images --output-dir outputs\batch_quality --preset heavy --editable-text none --bg-thresholds 35,18
```

Batch mode writes PPTX candidates, rendered PNGs, preview images, `report.csv`, and `report.html`. These outputs are intentionally ignored by git.

## Optional OpenRouter Brain

Create `.env` from `.env.example` or save the key through the web UI:

```powershell
Copy-Item .env.example .env
```

Then set:

```text
OPENROUTER_API_KEY=...
OPENROUTER_BRAIN_MODELS=openrouter/free,openai/gpt-oss-120b:free,nvidia/nemotron-3-super-120b-a12b:free,poolside/laguna-m.1:free
OPENROUTER_JUDGE_MODELS=openrouter/free,openai/gpt-oss-120b:free,nvidia/nemotron-3-super-120b-a12b:free,poolside/laguna-m.1:free
```

When "Agentes OpenRouter" is enabled, each image runs a candidate race:

1. Generate `heavy`, `heavy_lite`, `granular`, `balanced`, and `light` candidates.
2. Render each candidate back to PNG.
3. Score visual fidelity with MAE, PSNR, and edge F1.
4. Build preview sheets.
5. Ask the configured free OpenRouter model chain to choose the best editability/fidelity tradeoff.
6. Fall back to a local deterministic score if OpenRouter is unavailable.

The LLM does not receive your API key in job metadata.

## Build A Double-Click Windows EXE

Install build dependencies:

```powershell
python -m pip install -r requirements-build.txt
```

Build:

```powershell
.\build_exe.ps1
```

The executable is written to:

```text
dist\MagicalLayers\MagicalLayers.exe
```

Double-clicking the EXE starts the local server, opens the web app in your browser, and shows a small control window with "Open" and "Close" actions. If port `8000` is busy, it automatically picks the next free local port.

## Publish To GitHub

This repo is intended to be published as:

```text
from-ai-img-to-ppt-magical-layers
```

Install GitHub CLI, log in, then run:

```powershell
winget install --id GitHub.cli
gh auth login
.\publish_github.ps1 -Visibility public
```

The script creates the GitHub repository from the local `main` branch and pushes the initial commit. Use `-Visibility private` if you want to keep the repo private.

## Current Limitations

- This is not SAM-quality segmentation yet; it uses deterministic image processing plus optional LLM judging.
- Inpainting is lightweight and deterministic, not full generative scene reconstruction.
- OCR is optional and Windows-focused through `winocr`; without it, text stays as raster pixels.
- Large, highly granular decks can contain hundreds or thousands of layers and may be heavy in PowerPoint.
- Source test images are not included because their license/privacy may be unclear.

## Suggested Roadmap

- Add a SAM/ONNX segmentation backend.
- Add a better local inpainting backend for moved-layer holes.
- Add font matching for OCR text reconstruction.
- Add grouping heuristics for black blocks with internal movable components.
- Add a packaged installer that copies the app to `%LOCALAPPDATA%`.
- Add public sample images with explicit licenses.

## License

No license has been selected yet. Add a `LICENSE` file before distributing this as open source for external reuse.
