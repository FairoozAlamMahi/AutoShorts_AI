"""Autopilot V2 Engine - Autonomous Viral Gaming Edit & Multi-Platform Publisher.
Orchestrates end-to-end ingestion, VLM scriptwriting, local Kokoro neural voiceover,
declarative viral edit templates (Phonk, Velocity, Blur Fit), and multi-platform publishing.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from .database import DatabaseManager
from .resource_guard import ResourceGuard
from ..providers.registry import ModelRegistry
from .orchestrator import JobOrchestrator
from .dto import JobRequestDTO
from ..config.schema import (
    PreRunToggles,
    DiscoveryMode,
    CaptionMode,
    LayoutMode,
    MetadataMode,
    CaptionTheme,
)
from ..templates.template_manager import EditTemplateManager, EditTemplate
from ..voice.voice_agent import VoiceSynthesisAgent, VoicePersona
from ..scripting.script_writer import ScriptWriterAgent, ScriptStyle
from ..publishing.instagram_uploader import InstagramUploader
from .youtube_uploader import YouTubeUploader

logger = logging.getLogger(__name__)


class AutopilotMode:
    HANDS_FREE = "HANDS_FREE"
    REVIEW = "REVIEW"


class AutopilotV2:
    """Complete autonomous channel operator and viral edit engine."""

    WATCH_FOLDER = Path("data/watch_folder")
    REFERENCE_EDITS_DIR = Path("data/reference_edits")
    STAGING_DIR = Path("data/staging")
    REPORTS_DIR = Path("data/autopilot_reports")

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        resource_guard: Optional[ResourceGuard] = None,
        model_registry: Optional[ModelRegistry] = None,
    ) -> None:
        self.db = db or DatabaseManager()
        self.resource_guard = resource_guard or ResourceGuard()
        self.model_registry = model_registry or ModelRegistry()
        self.orchestrator = JobOrchestrator(
            db=self.db,
            resource_guard=self.resource_guard,
            model_registry=self.model_registry,
        )
        self.template_mgr = EditTemplateManager()
        self.ig_uploader = InstagramUploader()
        self.yt_uploader = YouTubeUploader()

        # Ensure directories exist
        self.WATCH_FOLDER.mkdir(parents=True, exist_ok=True)
        (self.WATCH_FOLDER / "processed").mkdir(parents=True, exist_ok=True)
        self.REFERENCE_EDITS_DIR.mkdir(parents=True, exist_ok=True)
        self.STAGING_DIR.mkdir(parents=True, exist_ok=True)
        self.REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def get_ecosystem_status(self) -> Dict[str, Any]:
        """Provides full operational status of all ecosystem subsystems."""
        yt_status = self.yt_uploader.get_status_summary()
        ig_status = self.ig_uploader.get_status_summary()

        voice_ready = False
        try:
            import kokoro  # noqa: F401
            voice_ready = True
        except ImportError:
            voice_ready = False

        templates = self.template_mgr.list_templates()
        pending_watch = list(self.WATCH_FOLDER.glob("*.mp4")) + list(self.WATCH_FOLDER.glob("*.mkv"))

        return {
            "youtube": yt_status,
            "instagram": ig_status,
            "voice_synthesis_ready": voice_ready,
            "gpu_device": "NVIDIA GeForce RTX 4060 Ti (CUDA)",
            "registered_templates_count": len(templates),
            "template_ids": [t.template_id for t in templates],
            "watch_folder_pending_count": len(pending_watch),
        }

    def run_autopilot_pipeline(
        self,
        source: str | Path,
        mode: str = AutopilotMode.HANDS_FREE,
        game_title: Optional[str] = None,
        template_id: Optional[str] = "aura_brazilian_phonk",
        voice_persona: str = VoicePersona.DRAMATIC_TRAILER_BASS,
        clip_count: int = 3,
        publish_youtube: bool = True,
        publish_instagram: bool = True,
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Executes end-to-end viral edit generation and multi-platform publishing.
        """
        source_str = str(source).strip()
        is_url = source_str.startswith("http://") or source_str.startswith("https://")
        file_path = None if is_url else str(Path(source_str).resolve())
        yt_url = source_str if is_url else None

        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.FULL_AUTO,
            captions_mode=CaptionMode.BURNED_IN_ANIMATED,
            layout_mode=LayoutMode.LAYOUT_A_BLUR_FIT,
            smart_layout_distribution=True,
            target_clip_count=clip_count,
            voiceover_enabled=True,
            voice_persona=voice_persona,
            edit_template_id=template_id,
            impact_flash_enabled=True,
            autopilot_mode=mode,
            publish_youtube=publish_youtube,
            publish_instagram=publish_instagram,
            game_name_context=game_title or "Gaming",
        )

        import uuid
        job_id = f"auto_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        job_req = JobRequestDTO(
            job_id=job_id,
            source_path_or_url=source_str,
            toggles=toggles,
            created_at_iso=datetime.now(timezone.utc).isoformat(),
        )

        logger.info(f"Starting Autopilot V2 [{mode}] for source: {source_str}")
        rendered_paths = self.orchestrator.run_job(job_req, progress_callback=progress_callback)

        job_id = job_req.job_id
        candidates = self.db.get_candidates_for_job(job_id) if hasattr(self.db, "get_candidates_for_job") else []

        publication_results: Dict[str, Any] = {
            "job_id": job_id,
            "mode": mode,
            "rendered_shorts_count": len(rendered_paths),
            "rendered_files": [str(p) for p in rendered_paths],
            "youtube_dispatched": [],
            "instagram_dispatched": [],
            "staged_for_review": [],
        }

        if mode == AutopilotMode.HANDS_FREE:
            # Publish across YouTube and Instagram
            dispatch_info = self.dispatch_job_publications(
                job_id=job_id,
                rendered_clips=rendered_paths,
                candidates=candidates,
                publish_youtube=publish_youtube,
                publish_instagram=publish_instagram,
                game_title=toggles.game_name_context,
            )
            publication_results.update(dispatch_info)
        else:
            # Stage rendered media for human review
            for p in rendered_paths:
                p_path = Path(p)
                staged_dest = self.STAGING_DIR / f"{job_id}_{p_path.name}"
                shutil.copyfile(p_path, staged_dest)
                thumb_src = p_path.with_suffix(".thumb.jpg")
                if thumb_src.exists():
                    shutil.copyfile(thumb_src, staged_dest.with_suffix(".thumb.jpg"))
                publication_results["staged_for_review"].append(str(staged_dest))
            logger.info(f"Autopilot staged {len(rendered_paths)} shorts in {self.STAGING_DIR} for review.")

        # Save run report
        report_file = self.REPORTS_DIR / f"report_{job_id}.json"
        report_file.write_text(json.dumps(publication_results, indent=2), encoding="utf-8")

        return publication_results

    def dispatch_job_publications(
        self,
        job_id: str,
        rendered_clips: List[Path],
        candidates: Optional[List[Any]] = None,
        metadata_map: Optional[Dict[int, Any]] = None,
        publish_youtube: bool = True,
        publish_instagram: bool = True,
        game_title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches rendered shorts to YouTube Shorts and Instagram Reels."""
        yt_results = []
        ig_results = []

        now = datetime.now(timezone.utc)
        for i, clip_path in enumerate(rendered_clips):
            clip_file = Path(clip_path).resolve()
            clip_idx = i + 1
            meta_file = clip_file.with_suffix(".meta.json")

            title = f"Insane {game_title or 'Gaming'} Moment #{clip_idx} #Shorts"
            description = f"High octane gameplay from {game_title or 'Gaming'}.\n\nRate this play from 1 to 10!"
            tags = ["#shorts", "#gaming", "#action", "#viral"]
            comment = "Could you have pulled this off? Rate it 1-10 below!"

            if meta_file.exists():
                try:
                    data = json.loads(meta_file.read_text(encoding="utf-8"))
                    title = data.get("primary_title", title)
                    description = data.get("description", description)
                    tags = data.get("tags", tags)
                except Exception:
                    pass

            # Coordinate staggered publishing: 3.5 hours per clip for YouTube
            yt_schedule_time = now + timedelta(hours=3.5 * i) if i > 0 else None
            yt_schedule_iso = yt_schedule_time.isoformat() if yt_schedule_time else None

            # 1. YouTube Shorts Upload
            if publish_youtube:
                try:
                    res_yt = self.yt_uploader.upload_short(
                        video_path=clip_file,
                        title=title,
                        description=description,
                        tags=tags,
                        scheduled_time_iso=yt_schedule_iso,
                        auto_engagement_comment=comment,
                    )
                    yt_results.append(res_yt)
                except Exception as ex:
                    logger.warning(f"YouTube upload failed for {clip_file.name}: {ex}")
                    yt_results.append({"success": False, "error": str(ex), "video": clip_file.name})

            # 2. Instagram Reels Upload
            if publish_instagram:
                try:
                    ig_caption = InstagramUploader.sanitize_caption(
                        title=title.replace("#Shorts", "#Reels"),
                        description=description,
                        tags=tags + ["#reels", "#fyp", "#gamer"],
                        engagement_question=comment,
                    )
                    thumb_candidate = clip_file.with_suffix(".thumb.jpg")
                    res_ig = self.ig_uploader.upload_reel(
                        video_path=clip_file,
                        caption=ig_caption,
                        thumbnail_path=thumb_candidate if thumb_candidate.exists() else None,
                        dry_run=not self.ig_uploader.is_authenticated(),
                    )
                    ig_results.append(res_ig)
                except Exception as ex:
                    logger.warning(f"Instagram upload failed for {clip_file.name}: {ex}")
                    ig_results.append({"success": False, "error": str(ex), "video": clip_file.name})

        return {
            "youtube_dispatched": yt_results,
            "instagram_dispatched": ig_results,
        }

    def scan_and_process_watch_folder(
        self,
        mode: str = AutopilotMode.HANDS_FREE,
        template_id: str = "aura_brazilian_phonk",
    ) -> List[Dict[str, Any]]:
        """Scans data/watch_folder for new footage, processes, and archives."""
        video_exts = [".mp4", ".mkv", ".mov", ".avi"]
        found = [p for p in self.WATCH_FOLDER.iterdir() if p.is_file() and p.suffix.lower() in video_exts]

        results = []
        for v in found:
            logger.info(f"Watch folder detected: {v.name}. Launching autonomous edit pipeline...")
            res = self.run_autopilot_pipeline(
                source=v,
                mode=mode,
                template_id=template_id,
            )
            results.append(res)
            # Move to processed
            proc_dest = self.WATCH_FOLDER / "processed" / f"{int(time.time())}_{v.name}"
            shutil.move(str(v), str(proc_dest))
            logger.info(f"Moved {v.name} to {proc_dest}")

        return results

    def add_viral_edit(
        self,
        template_id: str,
        display_name: str,
        bgm_file: Optional[str] = None,
        bpm: Optional[float] = None,
        beat_drop_sec: float = 2.5,
        framing_mode: str = "LAYOUT_A_BLUR_FIT",
        visual_effects: Optional[List[str]] = None,
        recommended_persona: str = VoicePersona.DRAMATIC_TRAILER_BASS,
        caption_theme: str = "MRBEAST_YELLOW",
    ) -> EditTemplate:
        """
        Dynamically registers a new viral edit template with automated audio BPM/drop tracking.
        Enables adding new viral edits and music recipes on demand via chat or automation.
        """
        eff_bpm = bpm
        eff_drop = beat_drop_sec

        if bgm_file and Path(bgm_file).exists():
            try:
                info = self.template_mgr.analyze_audio_beatgrid(bgm_file)
                eff_bpm = info["bpm"]
                eff_drop = info["suggested_drop_sec"]
            except Exception as ex:
                logger.warning(f"Audio analysis fallback: {ex}")
                eff_bpm = eff_bpm or 125.0

        template = EditTemplate(
            template_id=template_id,
            display_name=display_name,
            bgm_file=bgm_file,
            bpm=round(float(eff_bpm or 120.0), 1),
            beat_drop_sec=round(float(eff_drop or 2.5), 2),
            framing_mode=framing_mode,
            visual_effects=visual_effects or ["ambient_blur", "2frame_flash"],
            recommended_persona=recommended_persona,
            caption_theme=caption_theme,
        )
        self.template_mgr.save_template(template)
        logger.info(f"Registered new viral edit template: '{display_name}' ({template_id})")
        return template
