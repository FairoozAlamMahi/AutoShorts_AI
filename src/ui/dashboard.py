"""Main Dashboard Tab: Pre-run optional toggles, queue launch, and live status."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Tuple
import gradio as gr

from ..config.schema import (
    DiscoveryMode,
    CaptionMode,
    LayoutMode,
    MetadataMode,
    AudioProcessMode,
    OwnershipType,
    RightsStatus,
    ManualTimestampRange,
    PreRunToggles,
    FacecamPosition,
    CaptionTheme,
)
from ..core.dto import JobRequestDTO
from ..core.orchestrator import JobOrchestrator
from ..ingest.cookie_manager import CookieManager


def parse_manual_timestamps(ts_string: str) -> List[ManualTimestampRange]:
    """Parses user input string like '12.5-32.0, 45.0-65.5' into ManualTimestampRange objects."""
    if not ts_string or not ts_string.strip():
        return []

    ranges: List[ManualTimestampRange] = []
    # Split by comma or newline
    items = re.split(r"[,;\n]+", ts_string.strip())
    for item in items:
        item = item.strip()
        if not item:
            continue
        # Format: start-end or start:end
        match = re.match(r"^([\d\.]+)\s*[-:]\s*([\d\.]+)$", item)
        if match:
            s = float(match.group(1))
            e = float(match.group(2))
            if e > s:
                ranges.append(ManualTimestampRange(start_sec=s, end_sec=e))
    return ranges


def create_run_tab(orchestrator: JobOrchestrator) -> None:
    """Builds the Run & Queue dashboard tab with all optional pre-run toggles."""
    gr.Markdown("### ShortsFactory Local — Automated Highlight & Vertical Short Generator")

    with gr.Row():
        with gr.Column(scale=2):
            source_input = gr.Textbox(
                label="Video Source(s) (Local MP4/MKV Path or YouTube URL — 1 per line for batch queue)",
                placeholder="e.g. C:/Videos/gameplay.mp4\nor https://youtube.com/watch?v=...\n(Add multiple paths/URLs on new lines to batch process them all sequentially!)",
                lines=3,
            )

            with gr.Accordion("🔑 YouTube Account / Cookies (Bypass Age-Restricted & Mature Videos e.g. GTA V)", open=False):
                gr.Markdown(
                    "**Sign In / Authenticate to Download Age-Restricted or 18+ Videos (e.g. GTA V):**\n"
                    "• **Option 1 (Recommended — Cookie-Editor):** Open an **Incognito/Private window**, log into YouTube, go to `https://www.youtube.com/robots.txt`, click Cookie-Editor ➔ Export (JSON), **close the incognito tab**, and paste below. *(Visiting robots.txt prevents YouTube's background scripts from rotating your session tokens!).*\n"
                    "• **Option 2 (Direct Browser Extraction):** Make sure your browser (Chrome/Edge/Brave) is **completely closed** before clicking Extract, because Windows locks open browser databases. (Firefox works while open)."
                )
                with gr.Row():
                    with gr.Column(scale=1):
                        browser_dropdown = gr.Dropdown(
                            choices=["chrome", "edge", "firefox", "brave", "opera", "vivaldi", "chromium"],
                            value="chrome",
                            label="Select Logged-In Browser",
                        )
                        extract_browser_btn = gr.Button("🔗 Extract & Link Browser", size="sm")

                    with gr.Column(scale=2):
                        paste_cookies_box = gr.Textbox(
                            label="Paste Cookies JSON (from Cookie-Editor extension)",
                            placeholder="[{\"domain\": \".youtube.com\", \"name\": \"LOGIN_INFO\", ...}]",
                            lines=2,
                        )
                        save_pasted_cookies_btn = gr.Button("💾 Save Pasted Cookies", size="sm")

                with gr.Row():
                    cookie_status_box = gr.Textbox(
                        label="Active YouTube Auth Status",
                        value=CookieManager.get_cookie_status().get("display", ""),
                        interactive=False,
                        scale=3,
                    )
                    verify_cookie_btn = gr.Button("🧪 Test Login", size="sm", scale=1)
                    clear_cookie_btn = gr.Button("🗑️ Remove Cookies", size="sm", scale=1)

            def _on_extract_browser(browser: str) -> str:
                success, msg, _ = CookieManager.extract_from_browser(browser)
                status = CookieManager.get_cookie_status().get("display", "")
                return f"{msg} | Status: {status}"

            def _on_save_pasted(raw_json: str) -> str:
                success, msg, _ = CookieManager.save_cookie_content(raw_json)
                status = CookieManager.get_cookie_status().get("display", "")
                return f"{msg} | Status: {status}"

            def _on_verify_cookies() -> str:
                success, msg = CookieManager.test_cookie_authentication()
                return msg

            def _on_clear_cookies() -> str:
                CookieManager.remove_saved_cookies()
                return CookieManager.get_cookie_status().get("display", "")

            extract_browser_btn.click(_on_extract_browser, inputs=[browser_dropdown], outputs=[cookie_status_box])
            save_pasted_cookies_btn.click(_on_save_pasted, inputs=[paste_cookies_box], outputs=[cookie_status_box])
            verify_cookie_btn.click(_on_verify_cookies, outputs=[cookie_status_box])
            clear_cookie_btn.click(_on_clear_cookies, outputs=[cookie_status_box])

            with gr.Row():
                ownership_dropdown = gr.Dropdown(
                    choices=["MY_OWN_VIDEO", "YOUTUBE_THIRD_PARTY"],
                    value="MY_OWN_VIDEO",
                    label="Source Ownership",
                )
                game_name_input = gr.Textbox(
                    label="Game Name / Creator Context (Optional)",
                    placeholder="e.g. GTA V, Warzone, Elden Ring",
                )

            with gr.Row():
                discovery_mode = gr.Dropdown(
                    choices=["FULL_AUTO", "MANUAL_ONLY", "HYBRID"],
                    value="FULL_AUTO",
                    label="Highlight Discovery Mode",
                )
                target_count_slider = gr.Slider(
                    minimum=1, maximum=15, value=3, step=1,
                    label="Target Shorts Count",
                )

            with gr.Row():
                duration_preset_dropdown = gr.Dropdown(
                    choices=[
                        "Custom (Set Sliders Below)",
                        "15–30s (Quick Hook)",
                        "30–60s (Standard 1-Min Short)",
                        "60–90s (Extended 1.5-Min Short)",
                        "90–120s (Long 2-Min Short)",
                        "120–180s (Max YouTube Short — 3 Mins)",
                    ],
                    value="30–60s (Standard 1-Min Short)",
                    label="Short Duration Preset",
                )

            with gr.Row():
                min_duration_slider = gr.Slider(
                    minimum=10, maximum=180, value=30, step=5,
                    label="Min Short Duration (Seconds)",
                )
                max_duration_slider = gr.Slider(
                    minimum=15, maximum=180, value=60, step=5,
                    label="Max Short Duration (Seconds — up to 180s / 3 mins for YouTube Shorts)",
                )

            def _on_duration_preset_change(choice: str):
                if "15–30s" in choice:
                    return 15, 30
                elif "30–60s" in choice:
                    return 30, 60
                elif "60–90s" in choice:
                    return 60, 90
                elif "90–120s" in choice:
                    return 90, 120
                elif "120–180s" in choice:
                    return 120, 180
                return 30, 60

            duration_preset_dropdown.change(
                _on_duration_preset_change,
                inputs=[duration_preset_dropdown],
                outputs=[min_duration_slider, max_duration_slider],
            )

            manual_timestamps_box = gr.Textbox(
                label="Manual Timestamps (Required for MANUAL_ONLY, optional for HYBRID)",
                placeholder="Format: 12.0-32.5, 45.2-68.0",
                lines=1,
            )

            with gr.Row():
                layout_mode = gr.Dropdown(
                    choices=[
                        "LAYOUT_HYBRID_CINEMA_STACK",
                        "LAYOUT_FACECAM_SPLIT",
                        "LAYOUT_A_BLUR_FIT",
                        "LAYOUT_B_CENTER_CROP",
                        "LAYOUT_4_3_BLUR_FIT",
                        "LAYOUT_4_3_HORIZONTAL",
                        "LAYOUT_RAW_16_9",
                    ],
                    value="LAYOUT_HYBRID_CINEMA_STACK",
                    label="Video Layout Style (9:16 Vertical, 4:3 Fit/Horizontal, 16:9 Raw)",
                )
                facecam_pos = gr.Dropdown(
                    choices=["TOP_LEFT", "TOP_RIGHT", "BOTTOM_LEFT", "BOTTOM_RIGHT"],
                    value="TOP_RIGHT",
                    label="Facecam Corner (For Streamer Split)",
                )

            with gr.Row():
                caption_mode = gr.Dropdown(
                    choices=[
                        "BURNED_IN_ANIMATED",
                        "BURNED_IN_CLASSIC",
                        "EXTERNAL_SIDECAR_ONLY",
                        "BURNED_IN_PLUS_SIDECAR",
                        "NONE",
                    ],
                    value="BURNED_IN_ANIMATED",
                    label="Subtitle & Caption Style",
                )
                caption_theme = gr.Dropdown(
                    choices=[
                        "MRBEAST_YELLOW",
                        "NEON_CYBER_GREEN",
                        "TIKTOK_RED_BOX",
                        "ELECTRIC_BLUE",
                        "CLEAN_WHITE",
                    ],
                    value="MRBEAST_YELLOW",
                    label="Caption Color Theme",
                )
                caption_font_size = gr.Slider(
                    minimum=40, maximum=90, value=68, step=2,
                    label="Caption Font Size",
                )

            with gr.Row():
                bgm_track_dropdown = gr.Dropdown(
                    choices=[
                        "None",
                        "assets/music/ambient_lofi.mp3",
                        "assets/music/action_pulse.mp3",
                    ],
                    value="None",
                    label="Dynamic Background Music (Auto-Ducked during speech)",
                )
                bgm_duck_slider = gr.Slider(
                    minimum=-24.0, maximum=-6.0, value=-14.0, step=1.0,
                    label="BGM Ducking Level (dB)",
                )

            with gr.Row():
                use_whisper_chk = gr.Checkbox(label="Use Speech Transcription (Whisper)", value=True)
                use_vlm_chk = gr.Checkbox(label="Use VLM Clutch Verification", value=True)
                use_metadata_chk = gr.Checkbox(label="Generate Title & Description", value=True)
                use_loudnorm_chk = gr.Checkbox(label="Normalize Audio (-14 LUFS)", value=True)

            with gr.Row():
                smart_dist_chk = gr.Checkbox(label="🧠 Smart Scene Customization (Auto-styles Action vs Comedy/Dialogue)", value=True)
                smart_cutscene_chk = gr.Checkbox(label="🎬 Smart Cutscene 4:3 Framing (Adapts zoom to 4:3 during cinematics)", value=True)
                per_clip_rules_box = gr.Textbox(
                    label="Per-Clip Customization (Optional, e.g. '2B, 3A' or '1-2: LAYOUT_B_CENTER_CROP, 3-5: LAYOUT_4_3_BLUR_FIT')",
                    placeholder="e.g. 2B, 3A or 1: LAYOUT_B, 2: LAYOUT_4_3_BLUR_FIT",
                    lines=1,
                    scale=2,
                )

            start_btn = gr.Button("🚀 Generate Shorts", variant="primary", size="lg")

        with gr.Column(scale=1):
            gr.Markdown("#### Job Status & Output")
            job_status_box = gr.Textbox(label="Stage Progress", value="Ready to process", interactive=False)
            output_clips_list = gr.JSON(label="Exported Shorts Files", value=[])

    def _on_start_job(
        src: str,
        ownership: str,
        game_name: str,
        disc_mode: str,
        target_count: int,
        manual_ts_str: str,
        min_dur: float,
        max_dur: float,
        lay_mode: str,
        facecam_corner: str,
        cap_mode: str,
        cap_theme: str,
        font_sz: int,
        bgm_choice: str,
        bgm_duck: float,
        use_whisper: bool,
        use_vlm: bool,
        use_meta: bool,
        use_loudnorm: bool,
        smart_dist: bool,
        smart_cutscene: bool,
        per_clip_rules_str: str,
        progress=gr.Progress(),
    ) -> Tuple[str, List[str]]:
        lines = [line.strip() for line in src.strip().splitlines() if line.strip()]
        if not lines:
            return "Error: Please provide at least one source video path or YouTube URL.", []

        manual_ranges = parse_manual_timestamps(manual_ts_str)
        bgm_path = None if bgm_choice in ("None", "", None) else str(bgm_choice)

        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode(disc_mode),
            captions_mode=CaptionMode(cap_mode),
            layout_mode=LayoutMode(lay_mode),
            facecam_pos=FacecamPosition(facecam_corner),
            caption_theme=CaptionTheme(cap_theme),
            caption_font_size=int(font_sz),
            bgm_track=bgm_path,
            bgm_volume_duck_db=float(bgm_duck),
            metadata_mode=MetadataMode.LOCAL_VLM if use_meta else MetadataMode.OFF,
            audio_process_mode=AudioProcessMode.LOUDNORM_EBU_R128 if use_loudnorm else AudioProcessMode.RAW_PASSTHROUGH,
            transcription_enabled=use_whisper,
            vlm_verification_enabled=use_vlm,
            target_clip_count=int(target_count),
            manual_timestamps=manual_ranges,
            ownership_type=OwnershipType(ownership),
            game_name_context=game_name.strip() if game_name.strip() else None,
            min_duration_sec=float(min_dur),
            max_duration_sec=float(max_dur),
            smart_layout_distribution=smart_dist,
            smart_cutscene_framing=smart_cutscene,
            per_clip_rules=per_clip_rules_str.strip() if per_clip_rules_str and per_clip_rules_str.strip() else None,
        )

        if len(lines) == 1:
            job_id = f"job_{uuid.uuid4().hex[:8]}"
            req = JobRequestDTO(
                job_id=job_id,
                source_path_or_url=lines[0],
                toggles=toggles,
                created_at_iso=datetime.now(timezone.utc).isoformat(),
            )

            def _ui_progress(stage: str, pct: float):
                progress(pct / 100.0, desc=f"{stage} ({int(pct)}%)")

            try:
                rendered = orchestrator.run_job(req, progress_callback=_ui_progress)
                paths_str = [str(p) for p in rendered]
                return f"✅ Job {job_id} Completed! Rendered {len(rendered)} Short(s).", paths_str
            except Exception as e:
                clean_err = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).strip()
                if not clean_err.startswith("["):
                    clean_err = f"[ERR_JOB_FAILED] {clean_err}"
                return f"❌ Job {job_id} Failed:\n{clean_err}", []
        else:
            requests = [
                JobRequestDTO(
                    job_id=f"job_{uuid.uuid4().hex[:8]}",
                    source_path_or_url=line,
                    toggles=toggles,
                    created_at_iso=datetime.now(timezone.utc).isoformat(),
                )
                for line in lines
            ]

            total_jobs = len(requests)
            all_rendered_paths: List[str] = []

            def _batch_progress(stage: str, pct: float, cur_idx: int, tot: int):
                overall_pct = ((cur_idx - 1) / tot) + (pct / 100.0) / tot
                progress(overall_pct, desc=f"Video [{cur_idx}/{tot}] {stage} ({int(pct)}%)")

            try:
                results = orchestrator.run_batch(requests, progress_callback=_batch_progress)
                for j_id, paths in results.items():
                    all_rendered_paths.extend([str(p) for p in paths])
                return f"✅ Batch Queue Complete! Processed {total_jobs} video(s), rendered {len(all_rendered_paths)} Shorts.", all_rendered_paths
            except Exception as e:
                clean_err = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).strip()
                if not clean_err.startswith("["):
                    clean_err = f"[ERR_BATCH_FAILED] {clean_err}"
                return f"❌ Batch queue failed:\n{clean_err}", all_rendered_paths

    start_btn.click(
        _on_start_job,
        inputs=[
            source_input, ownership_dropdown, game_name_input, discovery_mode,
            target_count_slider, manual_timestamps_box, min_duration_slider, max_duration_slider,
            layout_mode, facecam_pos, caption_mode, caption_theme, caption_font_size,
            bgm_track_dropdown, bgm_duck_slider,
            use_whisper_chk, use_vlm_chk, use_metadata_chk, use_loudnorm_chk,
            smart_dist_chk, smart_cutscene_chk, per_clip_rules_box,
        ],
        outputs=[job_status_box, output_clips_list],
    )
