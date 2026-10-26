# AutoShorts AI

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Hardware: 8GB VRAM Baseline](https://img.shields.io/badge/Hardware-8GB%20VRAM%20Baseline-76B900.svg)]()
[![Rendering: NVENC 60 FPS](https://img.shields.io/badge/Renderer-NVENC%2060%20FPS-blue.svg)]()
[![Tests: 72 Passed](https://img.shields.io/badge/Tests-72%20Passed-brightgreen.svg)]()

AutoShorts AI is an offline-capable, automated video repurposing engine designed to transform long-form horizontal content—such as podcasts, interviews, streams, tech tutorials, educational lectures, talking-head videos, and gameplay—into high-retention 9:16 vertical shorts (YouTube Shorts, TikTok, and Instagram Reels).

The system features dual operating paradigms: it can be orchestrated programmatically by autonomous AI agents via the Model Context Protocol (MCP), or it can execute completely offline using local models on consumer-grade GPUs (8 GB VRAM baseline) with zero mandatory cloud API costs.

---

## Operating Modes

### 1. AI Agent and MCP Orchestration
AutoShorts AI exposes an `AgentToolkit` and MCP automation interface. External AI agents (such as Claude, Antigravity, or custom autonomous workflows) can programmatically inspect media metadata, analyze transcript context, refine narrative boundaries, select visual framing modes, and dispatch rendering and YouTube scheduling tasks without manual human intervention.

### 2. Autonomous Local Fallback (Zero Token Cost)
When cloud API quotas are exhausted or privacy is strictly required, AutoShorts AI runs entirely on your local machine:
* Speech-to-Text: Local Faster-Whisper execution with Voice Activity Detection (VAD).
* Semantic and Visual Verification: Local Vision-Language Models (VLMs) via Ollama (e.g., Qwen 2.5 VL) or lightweight rule-based heuristic scoring.
* Resource Lease Management: Sequential GPU allocation guarantees that speech transcription and vision-language inference do not compete for VRAM simultaneously, preventing out-of-memory errors on 8 GB GPUs.
* Zero external API calls, zero recurring subscriptions, and zero telemetry.

---

## Key Technical Features

* Multi-Modal Candidate Scoring: Fuses audio RMS loudness transients, spectral flux onsets, visual crosshair motion tracking, and keyword excitement detection. Automatically adapts to pure acoustic signals on speechless segments.
* Advanced Subtitle Compiler: Compiles word-accurate Advanced SubStation Alpha (`.ass`) subtitles with kinetic pop animation (scale bounce and color highlighting), classic subtitle styling, or standalone synchronized `.srt` and `.vtt` sidecars.
* Hybrid Cinema Stack Layout: Converts widescreen 16:9 video to vertical 9:16 by layering an action-centered 4:3 foreground over an ambient, blurred, and darkened background. Blur-fit, center-crop, and raw horizontal modes are also supported.
* High-Performance NVENC Rendering: Hardware-accelerated 1080x1920 60 FPS Constant Frame Rate (CFR) video rendering via FFmpeg NVENC (with automatic CPU fallback) and EBU R128 (-14 LUFS) broadcast loudness normalization.
* Fast Review and Fix-Up Drawer: Interactive Gradio web interface featuring a sub-10-second fix-up drawer to inspect candidates, adjust timestamps, edit transcript text inline, and re-render individual clips rapidly.
* YouTube Integration: Built-in uploader supporting OAuth and session cookie authentication for automated drafting and scheduled publishing.

---

## Architecture and Pipeline

```
[Source Video: Local File or URL]
               │
               ▼
 [Stage 1: Ingest & Media Inspector (ffprobe)]
               │
        ┌──────┴──────────────────────────┐
        ▼                                 ▼
 [Stage 2: Speech STT]         [Stage 3: Multi-Modal Signals]
 (Faster-Whisper / VAD)        (RMS + Spectral Flux + Motion)
        │                                 │
        └──────────────┬──────────────────┘
                       ▼
 [Stage 4: Candidate Generator & Non-Max Suppression]
                       │
                       ▼
 [Stage 5: Verification & Metadata Generation]
 (Local VLM via Ollama / Agent MCP / Rule Engine)
                       │
        ┌──────────────┴──────────────────┐
        ▼                                 ▼
 [Stage 6: Caption Compiler]   [Stage 7: NVENC Video Renderer]
 (.ass / .srt / .vtt)          (1080x1920 60 FPS CFR)
                       │
                       ▼
 [Finished 9:16 Short + Metadata + Provenance Ledger]
```

---

## System Requirements

### Hardware
* GPU: NVIDIA GPU with at least 8 GB VRAM recommended (tested on RTX 4060 Ti 8GB, RTX 3060).
* CPU: Modern multi-core x86_64 processor.
* RAM: 16 GB system memory or higher.
* Storage: SSD recommended for temporary scratch workspace and cached media.

### Software
* Operating System: Windows 10/11 (64-bit) or Linux.
* Python: Version 3.11.x.
* FFmpeg: FFmpeg 7+ or 8+ compiled with `libass` and `h264_nvenc` support.
* NVIDIA Drivers: CUDA 12.x or 13.x compatible display driver.

---

## Quickstart

### 1. Clone the Repository
```bash
git clone https://github.com/FairoozAlamMahi/AutoShorts_AI.git
cd AutoShorts_AI
```

### 2. Install Dependencies
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux:
# source venv/bin/activate

pip install -r requirements.txt
```

### 3. Launch the Application
Run via the provided Windows batch script:
```cmd
run_shorts_factory.bat
```
Or directly through Python:
```bash
python app.py
```
Open your browser and navigate to `http://127.0.0.1:7860`.

---

## Pre-Run Configuration Toggles

| Parameter | Options | Description |
| :--- | :--- | :--- |
| Discovery Mode | `FULL_AUTO`, `MANUAL_ONLY`, `HYBRID` | Automated multi-modal detection, exact timestamp slicing, or combined discovery. |
| Caption Mode | `BURNED_IN_ANIMATED`, `BURNED_IN_CLASSIC`, `EXTERNAL_SIDECAR_ONLY`, `NONE` | Kinetic pop animation, classic two-line subtitles, external `.srt`/`.vtt`, or captions disabled. |
| Caption Theme | `MRBEAST_YELLOW`, `NEON_CYBER_GREEN`, `TIKTOK_RED_BOX`, `ELECTRIC_BLUE`, `CLEAN_WHITE` | Color palette and visual emphasis presets for rendered captions. |
| Video Layout | `LAYOUT_HYBRID_CINEMA_STACK`, `LAYOUT_4_3_BLUR_FIT`, `LAYOUT_4_3_HORIZONTAL`, `LAYOUT_A_BLUR_FIT`, `LAYOUT_B_CENTER_CROP`, `LAYOUT_FACECAM_SPLIT`, `LAYOUT_RAW_16_9` | 9:16 vertical stack, 4:3 full-screen blur fit ('show it all'), 4:3 center crop, 9:16 blur fit, 9:16 center crop, streamer facecam split, or 16:9 trim. |
| Smart Distribution | `True`, `False` | Automatically pairs action moments with high-tempo framing and comedy/dialogue scenes with 4:3 full-screen framing. |
| Per-Clip Rules | String (e.g. `'2B, 3A'`, `'1-2: LAYOUT_B, 3-5: LAYOUT_4_3_BLUR_FIT'`) | Granular per-clip layout, theme, and styling overrides within a single run. |
| Metadata Mode | `LOCAL_VLM`, `EXTERNAL_MCP_AGENT`, `RULE_BASED`, `OFF` | Hook titles and hashtags via local Ollama, external MCP agent manifest, or rule-based templates. |
| Audio Normalization | `LOUDNORM_EBU_R128`, `RAW_PASSTHROUGH` | Broadcast standard -14 LUFS loudness normalization or unmodified audio passthrough. |

---

## Programmatic Agent Usage (MCP)

To integrate AutoShorts AI with an autonomous agent:

```python
from src.agent_toolkit import AgentToolkit

# Initialize the programmatic agent toolkit
toolkit = AgentToolkit()

# Execute an automated job with heterogeneous per-clip rules
result = toolkit.run_customized_job(
    source_url_or_path="https://www.youtube.com/watch?v=...",
    target_count=5,
    per_clip_rules="2B, 3 with 4:3",
    smart_layout_distribution=True,
    caption_theme="MRBEAST_YELLOW",
    game_name="GTA 6",
)
print(f"Generated {result['total_clips']} clips: {result['rendered_clips']}")
```

---

## Test Suite

AutoShorts AI includes a comprehensive test suite utilizing deterministic synthetic media generation (requiring no external video downloads):

```bash
pytest tests -v
```

The test suite covers:
* Phase 1: Database WAL concurrency, DTO validation, ResourceGuard GPU leasing, and media inspection.
* Phase 2: Animated ASS subtitle compilation, sidecar generation, layout filtergraphs, and NVENC/CPU rendering.
* Phase 3: Multi-modal spike detection, silent/speechless clip fallbacks, and metadata generation.
* Phase 4: Stage bypass permutations, Gradio interface bindings, and rapid re-rendering.
* Phase 5: Interrupted job checkpoint resumption, VFR 60 FPS synchronization, and network-isolated execution.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
