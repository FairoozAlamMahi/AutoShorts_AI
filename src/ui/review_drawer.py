"""Review & Fast Fix-Up Tab: video preview, inline transcript editing, 10s re-render, and direct YouTube upload."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import gradio as gr

from ..core.orchestrator import JobOrchestrator
from ..core.database import DatabaseManager
from ..config.schema import CaptionMode, LayoutMode, CaptionTheme, FacecamPosition
from ..core.dto import TranscriptDTO, TranscriptSegmentDTO, TranscriptWordDTO
from ..core.youtube_uploader import YouTubeUploader


def create_review_tab(orchestrator: JobOrchestrator, db: DatabaseManager) -> None:
    """Builds the Review, Fast Fix-Up, and Direct YouTube Upload tab."""
    gr.Markdown("### Review Generated Shorts, Fast 10-Second Fix-Up & Direct YouTube Upload")
    uploader = YouTubeUploader()

    initial_clips = sorted(
        list(orchestrator.export_dir.glob("**/*.mp4")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    initial_choices = [str(p) for p in initial_clips]
    default_clip = initial_choices[0] if initial_choices else None
    default_thumb = (
        str(Path(default_clip).with_suffix(".thumb.jpg"))
        if default_clip and Path(default_clip).with_suffix(".thumb.jpg").exists()
        else None
    )

    with gr.Row():
        with gr.Column(scale=1):
            with gr.Row():
                clip_selector = gr.Dropdown(
                    choices=initial_choices,
                    value=default_clip,
                    label="Select Clip to Review",
                    interactive=True,
                    scale=3,
                )
                refresh_clips_btn = gr.Button("🔄 Refresh Clips", scale=1)

            video_player = gr.Video(value=default_clip, label="Clip Preview", interactive=False)
            thumbnail_preview = gr.Image(value=default_thumb, label="Cover Thumbnail (1080x1920)", interactive=False)

        with gr.Column(scale=1):
            gr.Markdown("#### Fast Adjustments (~10s Instant Re-Render)")
            with gr.Row():
                start_sec_box = gr.Number(label="Start Timestamp (s)", value=0.0, step=0.5)
                end_sec_box = gr.Number(label="End Timestamp (s)", value=20.0, step=0.5)

            with gr.Row():
                layout_dropdown = gr.Dropdown(
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
                    label="Layout Mode",
                    interactive=True,
                )
                facecam_pos_dropdown = gr.Dropdown(
                    choices=["TOP_LEFT", "TOP_RIGHT", "BOTTOM_LEFT", "BOTTOM_RIGHT"],
                    value="TOP_RIGHT",
                    label="Facecam Corner (For Split Mode)",
                    interactive=True,
                )

            with gr.Row():
                caption_style_dropdown = gr.Dropdown(
                    choices=["BURNED_IN_ANIMATED", "BURNED_IN_CLASSIC", "NONE"],
                    value="BURNED_IN_ANIMATED",
                    label="Caption Style",
                    interactive=True,
                )
                caption_theme_dropdown = gr.Dropdown(
                    choices=[
                        "MRBEAST_YELLOW",
                        "NEON_CYBER_GREEN",
                        "TIKTOK_RED_BOX",
                        "ELECTRIC_BLUE",
                        "CLEAN_WHITE",
                    ],
                    value="MRBEAST_YELLOW",
                    label="Caption Theme",
                    interactive=True,
                )
                caption_font_size_slider = gr.Slider(
                    minimum=40, maximum=90, value=68, step=2,
                    label="Font Size",
                    interactive=True,
                )

            bgm_dropdown = gr.Dropdown(
                choices=["None", "assets/music/ambient_lofi.mp3", "assets/music/action_pulse.mp3"],
                value="None",
                label="Background Music (Auto-Ducked during speech)",
                interactive=True,
            )

            transcript_box = gr.Textbox(
                label="Transcript Text (Edit words directly)",
                lines=2,
                interactive=True,
            )

            rerender_btn = gr.Button("⚡ Re-Render Single Clip (~10s)", variant="primary")
            rerender_status = gr.Textbox(label="Status", interactive=False)

            with gr.Accordion("🚀 Direct YouTube Shorts Upload & Scheduling (OAuth2 API)", open=False):
                gr.Markdown(
                    "**Directly publish or schedule your Short to YouTube with full metadata!**\n"
                    "• Ensure `data/client_secrets.json` or `data/youtube_token.json` is configured."
                )
                with gr.Row():
                    uploader_status_box = gr.Textbox(
                        label="OAuth2 Status",
                        value=uploader.get_status_summary().get("display", ""),
                        interactive=False,
                        scale=3,
                    )
                    save_secrets_box = gr.Textbox(
                        label="Paste client_secrets.json Content",
                        placeholder="{\"installed\": { ... }}",
                        lines=1,
                        scale=2,
                    )
                    save_secrets_btn = gr.Button("💾 Save Secrets", size="sm", scale=1)

                title_box = gr.Textbox(label="Title (Automatically adds #Shorts)", interactive=True)
                desc_box = gr.Textbox(label="Description & Hashtags", lines=2, interactive=True)
                tags_box = gr.Textbox(label="Tags (comma-separated)", value="gaming, shorts, funny", interactive=True)

                with gr.Row():
                    privacy_dropdown = gr.Dropdown(
                        choices=["private", "unlisted", "public"],
                        value="private",
                        label="Privacy Status",
                        interactive=True,
                    )
                    publish_at_box = gr.Textbox(
                        label="Scheduled Time (ISO 8601 UTC, e.g. 2026-10-30T15:00:00Z)",
                        placeholder="Optional: schedule future publish for private shorts",
                        interactive=True,
                    )

                upload_btn = gr.Button("🚀 Upload Short to YouTube", variant="primary")
                upload_status_box = gr.Textbox(label="Upload Result & YouTube Link", interactive=False, lines=2)

    def _on_clip_select(clip_path_str: str) -> Dict[Any, Any]:
        if not clip_path_str or not Path(clip_path_str).exists():
            return {
                video_player: None,
                thumbnail_preview: None,
                rerender_status: "Clip not found",
                start_sec_box: 0.0,
                end_sec_box: 20.0,
                title_box: "",
                desc_box: "",
            }

        clip_p = Path(clip_path_str)
        prov_path = clip_p.with_suffix(".provenance.json")
        meta_path = clip_p.with_suffix(".meta.json")
        thumb_path = clip_p.with_suffix(".thumb.jpg")

        start_val = 0.0
        end_val = 20.0
        title_val = ""
        desc_val = ""

        if prov_path.exists():
            try:
                prov_data = json.loads(prov_path.read_text(encoding="utf-8"))
                start_val = float(prov_data.get("start_sec", 0.0))
                end_val = float(prov_data.get("end_sec", 20.0))
            except Exception:
                pass

        if meta_path.exists():
            try:
                meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
                title_val = meta_data.get("primary_title", "")
                desc_val = meta_data.get("small_description", "")
            except Exception:
                pass

        thumb_val = str(thumb_path) if thumb_path.exists() else None

        return {
            video_player: str(clip_p),
            thumbnail_preview: thumb_val,
            rerender_status: f"Loaded {clip_p.name}",
            start_sec_box: start_val,
            end_sec_box: end_val,
            title_box: title_val,
            desc_box: desc_val,
        }

    def _on_rerender(
        clip_path_str: str,
        start_sec: float,
        end_sec: float,
        layout_mode_str: str,
        facecam_pos_str: str,
        caption_mode_str: str,
        caption_theme_str: str,
        font_size_val: int,
        bgm_choice: str,
        edited_text: str,
    ) -> Dict[Any, Any]:
        if not clip_path_str or not Path(clip_path_str).exists():
            return {rerender_status: "No active clip selected"}

        clip_p = Path(clip_path_str)
        stem = clip_p.stem
        if "_v" in stem:
            base_part, v_num = stem.rsplit("_v", 1)
            try:
                new_stem = f"{base_part}_v{int(v_num) + 1}"
            except ValueError:
                new_stem = f"{stem}_v2"
        else:
            new_stem = f"{stem}_v2"

        out_v2 = clip_p.parent / f"{new_stem}.mp4"

        # Resolve original 16:9 source video from SQLite if available
        job_id = clip_p.parent.name
        source_video = clip_p
        job = db.get_job(job_id)
        if job and job.get("source_id"):
            with db.get_connection() as conn:
                row = conn.execute("SELECT file_path_or_url FROM sources WHERE id = ?", (job["source_id"],)).fetchone()
                if row and Path(row["file_path_or_url"]).exists():
                    source_video = Path(row["file_path_or_url"])

        transcript = None
        if edited_text.strip():
            words = [
                TranscriptWordDTO(word=w, start_sec=start_sec + idx * 0.4, end_sec=start_sec + (idx + 1) * 0.4)
                for idx, w in enumerate(edited_text.strip().split())
            ]
            seg = TranscriptSegmentDTO(id=0, start_sec=start_sec, end_sec=end_sec, text=edited_text, words=words)
            transcript = TranscriptDTO(segments=[seg], speech_coverage_ratio=0.8)

        cap_mode = CaptionMode(caption_mode_str)
        lay_mode = LayoutMode(layout_mode_str)
        facecam_pos = FacecamPosition(facecam_pos_str)
        cap_theme = CaptionTheme(caption_theme_str)
        bgm_path = None if bgm_choice in ("None", "", None) else Path(bgm_choice)

        try:
            rendered = orchestrator.rerender_clip(
                source_video=source_video,
                output_mp4=out_v2,
                start_sec=float(start_sec),
                end_sec=float(end_sec),
                layout_mode=lay_mode,
                captions_mode=cap_mode,
                transcript=transcript,
                caption_theme=cap_theme,
                caption_font_size=int(font_size_val),
                facecam_pos=facecam_pos,
                bgm_path=bgm_path,
            )
            new_thumb = rendered.with_suffix(".thumb.jpg")
            return {
                video_player: str(rendered),
                thumbnail_preview: str(new_thumb) if new_thumb.exists() else None,
                rerender_status: f"Successfully re-rendered: {rendered.name} (<10s)",
            }
        except Exception as e:
            return {rerender_status: f"Re-render failed: {e}"}

    def _on_save_secrets(content: str) -> str:
        success, msg = uploader.save_client_secrets(content)
        status = uploader.get_status_summary().get("display", "")
        return f"{msg} | Status: {status}"

    def _on_upload_short(
        clip_path_str: str,
        title: str,
        desc: str,
        tags_str: str,
        privacy: str,
        publish_at: str,
    ) -> str:
        if not clip_path_str or not Path(clip_path_str).exists():
            return "Error: No valid clip selected to upload."
        if not title.strip():
            return "Error: Title cannot be empty."

        tag_list = [t.strip() for t in tags_str.split(",") if t.strip()]
        publish_iso = publish_at.strip() if publish_at.strip() else None

        result = uploader.upload_short(
            video_path=clip_path_str,
            title=title,
            description=desc,
            tags=tag_list,
            privacy_status=privacy,
            publish_at_iso=publish_iso,
        )
        return result.get("message", "Upload process concluded.")

    def _on_refresh_clips() -> Any:
        exported = sorted(
            list(orchestrator.export_dir.glob("**/*.mp4")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        choices = [str(p) for p in exported]
        return gr.Dropdown(choices=choices, value=choices[0] if choices else None)

    refresh_clips_btn.click(_on_refresh_clips, outputs=[clip_selector])
    clip_selector.change(
        _on_clip_select,
        inputs=[clip_selector],
        outputs=[video_player, thumbnail_preview, rerender_status, start_sec_box, end_sec_box, title_box, desc_box],
    )
    rerender_btn.click(
        _on_rerender,
        inputs=[
            clip_selector,
            start_sec_box,
            end_sec_box,
            layout_dropdown,
            facecam_pos_dropdown,
            caption_style_dropdown,
            caption_theme_dropdown,
            caption_font_size_slider,
            bgm_dropdown,
            transcript_box,
        ],
        outputs=[video_player, thumbnail_preview, rerender_status],
    )
    save_secrets_btn.click(_on_save_secrets, inputs=[save_secrets_box], outputs=[uploader_status_box])
    upload_btn.click(
        _on_upload_short,
        inputs=[clip_selector, title_box, desc_box, tags_box, privacy_dropdown, publish_at_box],
        outputs=[upload_status_box],
    )
