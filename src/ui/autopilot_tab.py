"""Gradio UI Tab for Autonomous Viral Gaming Edits, Local Neural Voice, and Multi-Platform Publishing."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List, Tuple
import gradio as gr

from ..core.autopilot_v2 import AutopilotV2, AutopilotMode
from ..core.orchestrator import JobOrchestrator
from ..voice.voice_agent import VoicePersona
from ..templates.template_manager import EditTemplateManager


def create_autopilot_tab(orchestrator: JobOrchestrator, autopilot: Optional[AutopilotV2] = None) -> None:
    """Builds the Autonomous Viral Edits & Multi-Platform Hub tab."""
    auto = autopilot or AutopilotV2()
    template_mgr = auto.template_mgr

    gr.Markdown("### Autonomous Viral Edits & Multi-Platform Publishing Hub")
    gr.Markdown(
        "Transform raw gameplay into algorithm-optimized viral gaming edits with AI-scripted hooks, "
        "local neural voiceovers (RTX 4060 Ti CUDA), beat-drop visual effects, and automated multi-platform dispatch."
    )

    with gr.Row():
        # Column 1: Autopilot Launch Controls
        with gr.Column(scale=2):
            gr.Markdown("#### 1. Autopilot Production Pipeline")
            source_input = gr.Textbox(
                label="Video Source (YouTube URL or Local File Path)",
                placeholder="e.g. https://www.youtube.com/watch?v=... or C:/Videos/gameplay.mp4",
                lines=1,
            )

            with gr.Row():
                game_title_input = gr.Textbox(
                    label="Game Title Context",
                    value="Phantom Blade Zero",
                    placeholder="e.g. Phantom Blade Zero, Elden Ring, GTA V",
                    scale=2,
                )
                clip_count_slider = gr.Slider(
                    minimum=1, maximum=10, value=3, step=1,
                    label="Highlight Shorts Count",
                    scale=1,
                )

            with gr.Row():
                # Edit Templates
                existing_templates = template_mgr.list_templates()
                template_choices = [t.template_id for t in existing_templates] or ["aura_brazilian_phonk"]
                template_dropdown = gr.Dropdown(
                    choices=template_choices,
                    value=template_choices[0],
                    label="Viral Edit Template Recipe",
                )
                # Voice Personas
                persona_choices = [
                    VoicePersona.DRAMATIC_TRAILER_BASS,
                    VoicePersona.TIKTOK_HYPE_HOOK,
                    VoicePersona.CALM_LORE_STORYTELLER,
                    VoicePersona.BRITISH_DOCUMENTARY,
                    VoicePersona.FEMALE_INTENSE,
                ]
                voice_persona_dropdown = gr.Dropdown(
                    choices=persona_choices,
                    value=VoicePersona.DRAMATIC_TRAILER_BASS,
                    label="Local Voiceover Persona (RTX 4060 Ti)",
                )

            with gr.Row():
                autopilot_mode_radio = gr.Radio(
                    choices=[AutopilotMode.HANDS_FREE, AutopilotMode.REVIEW],
                    value=AutopilotMode.HANDS_FREE,
                    label="Autopilot Mode",
                    info="HANDS_FREE automatically publishes to YouTube & Instagram. REVIEW stages clips for 1-click human approval.",
                )

            with gr.Row():
                pub_yt_chk = gr.Checkbox(label="Publish to YouTube Shorts", value=True)
                pub_ig_chk = gr.Checkbox(label="Publish to Instagram Reels", value=True)

            launch_btn = gr.Button("⚡ Launch Autonomous Viral Edit Pipeline", variant="primary", size="lg")
            launch_output = gr.JSON(label="Pipeline Execution & Publishing Report", value={})

        # Column 2: System Health & Watch Folder
        with gr.Column(scale=1):
            gr.Markdown("#### 2. Multi-Platform & Hardware Ecosystem")
            refresh_health_btn = gr.Button("🔄 Refresh Ecosystem Status", size="sm")
            health_display = gr.JSON(label="Ecosystem Live Status", value=auto.get_ecosystem_status())

            gr.Markdown("#### 3. Gameplay Watch Folder")
            gr.Markdown("Drop gameplay recordings into `data/watch_folder/` for hands-free autonomous background editing.")
            process_watch_btn = gr.Button("📁 Process Watch Folder Footage Now", variant="secondary")
            watch_output = gr.JSON(label="Watch Folder Results", value=[])

    gr.Markdown("---")
    with gr.Accordion("➕ Add New Viral Edit Recipe / Music Beat-Grid Sync", open=False):
        gr.Markdown(
            "Add any new trending song or edit archetype. Audio is automatically analyzed with `librosa` "
            "to extract BPM and detect the highest-energy beat drop timestamp."
        )
        with gr.Row():
            new_id_box = gr.Textbox(label="Template ID", placeholder="e.g. drift_phonk_clutch")
            new_name_box = gr.Textbox(label="Display Name", placeholder="e.g. Brazilian Drift Phonk Peak")
            audio_path_box = gr.Textbox(label="Song Audio File Path (.mp3 / .wav)", placeholder="data/music/trending_track.mp3")

        with gr.Row():
            framing_choice = gr.Dropdown(
                choices=["LAYOUT_A_BLUR_FIT", "LAYOUT_4_3_BLUR_FIT", "LAYOUT_HYBRID_CINEMA_STACK"],
                value="LAYOUT_A_BLUR_FIT",
                label="Framing Mode",
            )
            bpm_input = gr.Number(label="BPM (Leave 0 to auto-detect)", value=0)
            drop_input = gr.Number(label="Beat Drop Sec (Leave 0 to auto-detect)", value=0)
            new_persona_choice = gr.Dropdown(
                choices=persona_choices,
                value=VoicePersona.DRAMATIC_TRAILER_BASS,
                label="Default Voice Persona",
            )

        register_template_btn = gr.Button("💾 Register New Viral Edit Recipe", variant="primary")
        register_status = gr.Textbox(label="Registration Status", interactive=False)

    # Wire event handlers
    def _refresh_status():
        return auto.get_ecosystem_status()

    refresh_health_btn.click(_refresh_status, inputs=[], outputs=[health_display])

    def _on_launch_pipeline(src, game, count, tmpl, persona, mode, yt, ig, progress=gr.Progress()):
        if not src or not src.strip():
            return {"error": "Please provide a valid YouTube URL or local video file path."}

        def _prog(stage, pct):
            progress(pct / 100.0, desc=f"{stage} ({int(pct)}%)")

        try:
            report = auto.run_autopilot_pipeline(
                source=src.strip(),
                mode=mode,
                game_title=game.strip(),
                template_id=tmpl,
                voice_persona=persona,
                clip_count=int(count),
                publish_youtube=yt,
                publish_instagram=ig,
                progress_callback=_prog,
            )
            return report
        except Exception as e:
            return {"status": "FAILED", "error": str(e)}

    launch_btn.click(
        _on_launch_pipeline,
        inputs=[
            source_input, game_title_input, clip_count_slider,
            template_dropdown, voice_persona_dropdown, autopilot_mode_radio,
            pub_yt_chk, pub_ig_chk,
        ],
        outputs=[launch_output],
    )

    def _on_process_watch(tmpl, mode):
        res = auto.scan_and_process_watch_folder(mode=mode, template_id=tmpl)
        return res

    process_watch_btn.click(
        _on_process_watch,
        inputs=[template_dropdown, autopilot_mode_radio],
        outputs=[watch_output],
    )

    def _on_register_template(t_id, t_name, audio_p, framing, bpm_val, drop_val, persona):
        if not t_id or not t_name:
            return "Error: Template ID and Display Name are required."
        try:
            eff_bpm = None if bpm_val <= 0 else float(bpm_val)
            eff_drop = 2.5 if drop_val <= 0 else float(drop_val)
            t = auto.add_viral_edit(
                template_id=t_id.strip(),
                display_name=t_name.strip(),
                bgm_file=audio_p.strip() if audio_p and audio_p.strip() else None,
                bpm=eff_bpm,
                beat_drop_sec=eff_drop,
                framing_mode=framing,
                recommended_persona=persona,
            )
            return f"Successfully registered template '{t.display_name}' ({t.template_id}) with BPM {t.bpm}!"
        except Exception as ex:
            return f"Registration failed: {ex}"

    register_template_btn.click(
        _on_register_template,
        inputs=[new_id_box, new_name_box, audio_path_box, framing_choice, bpm_input, drop_input, new_persona_choice],
        outputs=[register_status],
    )
