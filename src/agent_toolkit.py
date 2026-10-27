"""Agent Toolkit & MCP Automation Interface for ShortsFactory.
Enables token-efficient external AI agents (Antigravity, Claude, etc.)
to orchestrate clip discovery, narrative dialogue refinement, per-clip styling,
and automated YouTube scheduling.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

from .config.schema import (
    PreRunToggles,
    LayoutMode,
    CaptionMode,
    CaptionTheme,
    FacecamPosition,
    DiscoveryMode,
    OwnershipType,
    AudioProcessMode,
    MetadataMode,
)
from .core.dto import JobRequestDTO, TranscriptDTO, CandidateClipDTO
from .core.database import DatabaseManager
from .core.resource_guard import ResourceGuard
from .providers.registry import ModelRegistry
from .core.orchestrator import JobOrchestrator
from .core.youtube_uploader import YouTubeUploader
from .core.channel_playbook import ChannelPlaybook
from .analytics.hook_engine import HookEngine
from .analytics.title_linter import TitleLinter
from .analytics.retention_diagnostics import RetentionDiagnostics
from .analytics.agent_copilot import AgentCoPilotSynthesizer
from .analysis.scene_classifier import MultimodalSceneClassifier, NarrativeBoundaryRefiner, SceneClassificationResult


class AgentToolkit:
    """High-level programmatic controller for AI pair programmer and MCP agent delegation."""

    def __init__(self, project_root: Optional[Path | str] = None) -> None:
        self.root = Path(project_root or Path(__file__).parent.parent).resolve()
        data_dir = self.root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.scratch_dir = data_dir / "scratch"
        self.export_dir = data_dir / "exports"

        self.db = DatabaseManager(db_path=str(data_dir / "shorts_factory.db"))
        self.guard = ResourceGuard(scratch_dir=str(self.scratch_dir), disk_threshold_gb=10.0)
        self.registry = ModelRegistry(registry_path=str(data_dir / "models_registry.json"))
        self.playbook = ChannelPlaybook(playbook_path=data_dir / "channel_playbook.json")
        self.orchestrator = JobOrchestrator(
            db=self.db,
            resource_guard=self.guard,
            model_registry=self.registry,
            scratch_dir=self.scratch_dir,
            export_dir=self.export_dir,
            playbook=self.playbook,
        )
        self.uploader = YouTubeUploader(
            client_secrets_path=data_dir / "client_secrets.json",
            token_path=data_dir / "youtube_token.json",
        )

    def run_customized_job(
        self,
        source_url_or_path: str,
        target_count: int = 3,
        layout_mode: Union[LayoutMode, str] = LayoutMode.LAYOUT_HYBRID_CINEMA_STACK,
        caption_theme: Union[CaptionTheme, str] = CaptionTheme.MRBEAST_YELLOW,
        caption_mode: Union[CaptionMode, str] = CaptionMode.BURNED_IN_ANIMATED,
        game_name: Optional[str] = None,
        per_clip_rules: Optional[str] = None,
        per_clip_customizations: Optional[Dict[int, Dict[str, Any]]] = None,
        smart_layout_distribution: bool = True,
        min_duration_sec: float = 30.0,
        max_duration_sec: float = 60.0,
        bgm_track: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes a complete highlight generation run with per-clip customization.
        Supports rules like '2B, 3A' or '1-2: LAYOUT_B_CENTER_CROP, 3-5: LAYOUT_4_3_BLUR_FIT'.
        """
        job_id = f"job_agent_{uuid.uuid4().hex[:8]}"

        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.FULL_AUTO,
            captions_mode=CaptionMode(caption_mode) if isinstance(caption_mode, str) else caption_mode,
            layout_mode=LayoutMode(layout_mode) if isinstance(layout_mode, str) else layout_mode,
            caption_theme=CaptionTheme(caption_theme) if isinstance(caption_theme, str) else caption_theme,
            game_name_context=game_name,
            target_clip_count=target_count,
            min_duration_sec=min_duration_sec,
            max_duration_sec=max_duration_sec,
            bgm_track=bgm_track,
            smart_layout_distribution=smart_layout_distribution,
            per_clip_rules=per_clip_rules,
            per_clip_customizations=per_clip_customizations or {},
            transcription_enabled=True,
            use_speech_scoring=True,
            vlm_verification_enabled=True,
            metadata_mode=MetadataMode.LOCAL_VLM,
            audio_process_mode=AudioProcessMode.LOUDNORM_EBU_R128,
        )

        req = JobRequestDTO(
            job_id=job_id,
            source_path_or_url=source_url_or_path,
            toggles=toggles,
            clip_overrides=per_clip_customizations or {},
            created_at_iso=datetime.now(timezone.utc).isoformat(),
        )

        rendered_files = self.orchestrator.run_job(req)
        return {
            "job_id": job_id,
            "status": "COMPLETED",
            "rendered_clips": [str(p) for p in rendered_files],
            "total_clips": len(rendered_files),
        }

    def refine_speech_boundary(
        self,
        raw_start: float,
        raw_end: float,
        transcript_data: Union[TranscriptDTO, Dict[str, Any]],
        min_dur: float = 30.0,
        max_dur: float = 60.0,
    ) -> Dict[str, Any]:
        """Snaps clip boundaries to clean sentences, eliminating mid-word truncations."""
        if isinstance(transcript_data, dict):
            tr = TranscriptDTO.model_validate(transcript_data)
        else:
            tr = transcript_data

        start, end, note = NarrativeBoundaryRefiner.refine_bounds(
            raw_start=raw_start,
            raw_end=raw_end,
            transcript=tr,
            min_duration_sec=min_dur,
            max_duration_sec=max_dur,
        )
        return {
            "refined_start_sec": start,
            "refined_end_sec": end,
            "refined_duration_sec": round(end - start, 3),
            "refinement_note": note,
        }

    def classify_scene(
        self,
        clip: Union[CandidateClipDTO, Dict[str, Any]],
        transcript: Optional[Union[TranscriptDTO, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Classifies a clip into Action, Comedy, Clutch, Dialogue, or Fail."""
        c = CandidateClipDTO.model_validate(clip) if isinstance(clip, dict) else clip
        tr = TranscriptDTO.model_validate(transcript) if isinstance(transcript, dict) else transcript

        result: SceneClassificationResult = MultimodalSceneClassifier.classify(c, tr)
        return {
            "scene_category": result.category.value,
            "confidence": result.confidence,
            "reason": result.reason,
            "recommended_layout": result.recommended_layout.value,
            "recommended_caption_theme": result.recommended_caption_theme.value,
            "recommended_caption_font_size": result.recommended_caption_font_size,
            "recommended_bgm": result.recommended_bgm,
        }

    def upload_to_youtube(
        self,
        clip_path: str,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        privacy: str = "private",
        publish_at_iso: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Uploads or schedules a short to YouTube via OAuth2."""
        return self.uploader.upload_short(
            video_path=clip_path,
            title=title,
            description=description,
            tags=tags or ["#shorts", "#gaming"],
            privacy_status=privacy,
            publish_at_iso=publish_at_iso,
        )

    def run_autonomous_campaign(
        self,
        source_url_or_path: str,
        target_count: int = 3,
        strategy: str = "AUTO_OPTIMIZED",
        publish_mode: str = "OFF",
        game_name: Optional[str] = None,
        per_clip_rules: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes an end-to-end autonomous executive campaign:
        - Consults Channel Playbook for winning layout and optimal duration
        - Discovers highlights and formulates viral hook overlays
        - Renders final vertical Shorts
        - Optionally queues or uploads directly to YouTube
        """
        recs = self.playbook.get_recommendations(game_name=game_name)
        opt_layout = recs.get("recommended_layout", LayoutMode.LAYOUT_HYBRID_CINEMA_STACK.value)
        opt_theme = recs.get("recommended_theme", CaptionTheme.MRBEAST_YELLOW.value)
        min_dur = recs.get("recommended_min_duration_sec", 30.0)
        max_dur = recs.get("recommended_max_duration_sec", 55.0)

        job_result = self.run_customized_job(
            source_url_or_path=source_url_or_path,
            target_count=target_count,
            layout_mode=opt_layout,
            caption_theme=opt_theme,
            game_name=game_name,
            per_clip_rules=per_clip_rules,
            smart_layout_distribution=True,
            min_duration_sec=min_dur,
            max_duration_sec=max_dur,
        )

        rendered_clips = job_result.get("rendered_clips", [])
        uploads: List[Dict[str, Any]] = []

        if publish_mode in ("DRAFT_UPLOAD", "SCHEDULE_STAGGERED") and rendered_clips:
            from datetime import timedelta
            now = datetime.now(timezone.utc)
            for idx, clip_p in enumerate(rendered_clips):
                p = Path(clip_p)
                meta_p = p.with_suffix(".meta.json")
                title = p.stem
                desc = "Automated high-retention Short"
                tags = ["Shorts", "Gaming"]
                if meta_p.exists():
                    try:
                        m_data = json.loads(meta_p.read_text(encoding="utf-8"))
                        title = m_data.get("primary_title", title)
                        desc = m_data.get("small_description", desc)
                        tags = m_data.get("tags", tags)
                    except Exception:
                        pass

                sched_time = None
                if publish_mode == "SCHEDULE_STAGGERED":
                    sched_time = (now + timedelta(hours=6 * (idx + 1))).strftime("%Y-%m-%dT%H:%M:%SZ")

                privacy = "private" if (publish_mode in ("SCHEDULE_STAGGERED", "DRAFT_UPLOAD")) else "public"
                up_res = self.upload_to_youtube(
                    clip_path=str(p),
                    title=title,
                    description=desc,
                    tags=tags,
                    privacy=privacy,
                    publish_at_iso=sched_time,
                )
                uploads.append(up_res)

        return {
            "job_id": job_result.get("job_id"),
            "status": "COMPLETED",
            "campaign_strategy": strategy,
            "playbook_recommendations_used": recs,
            "total_clips_generated": len(rendered_clips),
            "rendered_clips": rendered_clips,
            "uploads": uploads,
        }

    def audit_retention_and_update_playbook(
        self,
        retention_csv_or_text: str | Path,
        clip_id: str,
        duration_sec: Optional[float] = None,
        layout_mode: str = "LAYOUT_B_CENTER_CROP",
        caption_theme: str = "MRBEAST_YELLOW",
        scene_category: str = "ACTION",
        views: int = 0,
        transcript: Optional[Union[TranscriptDTO, List[Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        """
        Parses YouTube retention curve, detects drop cliffs paired with spoken lines,
        and records clip performance into the Channel Playbook memory.
        """
        raw_pts = RetentionDiagnostics.load_retention_data(retention_csv_or_text)

        segments = None
        if isinstance(transcript, TranscriptDTO):
            segments = [s.model_dump() for s in transcript.segments]
        elif isinstance(transcript, list):
            segments = transcript

        audit = RetentionDiagnostics.analyze_retention(
            retention_data=raw_pts,
            duration_sec=duration_sec,
            transcript_segments=segments,
        )

        if "error" not in audit:
            ret_pct = audit.get("end_pct", 70.0)
            hook_leak = audit.get("hook_leak_pct", 0.0)
            self.playbook.record_clip_performance(
                clip_id=clip_id,
                layout_mode=layout_mode,
                caption_theme=caption_theme,
                duration_sec=duration_sec or 45.0,
                scene_category=scene_category,
                retention_pct=ret_pct,
                views=views,
                hook_leak_pct=hook_leak,
                notes=f"Audited: verdict={audit.get('verdict')}",
            )

        return {
            "clip_id": clip_id,
            "audit": audit,
            "playbook_total_analyzed": self.playbook.data.get("total_analyzed_clips", 0),
            "updated_recommendations": self.playbook.get_recommendations(),
        }

    def get_channel_performance_briefing(self) -> Dict[str, Any]:
        """Returns executive briefing on winning channel formats and retention intelligence."""
        recs = self.playbook.get_recommendations()
        return {
            "total_analyzed_clips": self.playbook.data.get("total_analyzed_clips", 0),
            "top_performing_layouts": self.playbook.data.get("top_performing_layouts", {}),
            "optimal_duration_range": self.playbook.data.get("optimal_duration_range", {}),
            "winning_caption_themes": self.playbook.data.get("winning_caption_themes", {}),
            "recommendations": recs,
        }

    def inspect_vlm_observations(self, job_id_or_path: str) -> Dict[str, Any]:
        """
        Reads the structured VLM visual observations and Whisper transcripts for a job.
        Enables the AI Agent to review what happened visually and dialogue-wise in the video.
        """
        p = Path(job_id_or_path)
        if not p.exists() or p.name != "vlm_observation_bundle.json":
            # Search in scratch
            candidate = self.root / "data" / "scratch" / job_id_or_path / "vlm_observation_bundle.json"
            if candidate.exists():
                p = candidate
            else:
                raise FileNotFoundError(f"VLM observation bundle not found for: {job_id_or_path}")

        return json.loads(p.read_text(encoding="utf-8"))

    def synthesize_and_judge_metadata(
        self,
        job_id_or_path: str,
        update_disk: bool = True,
    ) -> Dict[str, Any]:
        """
        Reviews VLM visual observations and Whisper speech semantics across all clips in a job.
        Synthesizes high-CTR Agent titles, descriptions, and on-screen hooks,
        algorithmically compares Agent proposals against VLM proposals using TitleLinter,
        and optionally updates the export .meta.json sidecars on disk.
        """
        bundle = self.inspect_vlm_observations(job_id_or_path)
        job_id = bundle.get("job_id", "")
        game_name = bundle.get("game_name", "Gaming")
        clips = bundle.get("clips", [])
        judgments: List[Dict[str, Any]] = []

        exports_dir = self.root / "data" / "exports" / job_id

        for c in clips:
            idx = c.get("clip_index", 1)
            synth = AgentCoPilotSynthesizer.synthesize_agent_metadata(
                clip_index=idx,
                transcript_text=c.get("transcript", ""),
                vlm_summary=c.get("vlm_summary"),
                detected_events=c.get("vlm_events", []),
                game_name=game_name,
                scene_type=c.get("scene_category", "ACTION"),
            )

            # Build VLM meta if VLM title proposed
            vlm_prop_title = c.get("vlm_proposed_title")
            vlm_meta = None
            if vlm_prop_title:
                from .core.dto import ClipMetadataDTO
                vlm_meta = ClipMetadataDTO(
                    primary_title=vlm_prop_title,
                    alternative_titles=[],
                    small_description=f"Highlight from {game_name}",
                    tags=["#shorts", "#gaming"],
                )

            judgment = AgentCoPilotSynthesizer.judge_and_select_best_metadata(
                agent_synthesis=synth,
                vlm_proposed_meta=vlm_meta,
                game_name=game_name,
            )
            judgments.append({
                "clip_index": idx,
                "winner": judgment["winner"],
                "reason": judgment["reason"],
                "agent_score": judgment["agent_score"],
                "vlm_score": judgment["vlm_score"],
                "selected_title": judgment["selected_metadata"].primary_title,
                "selected_hook_overlay": judgment["selected_hook_overlay"],
                "selected_metadata": judgment["selected_metadata"].model_dump(),
            })

            # If update_disk is enabled, write updated .meta.json to exports
            if update_disk and exports_dir.exists():
                meta_path = exports_dir / f"clip_{idx:02d}.meta.json"
                if meta_path.exists():
                    meta_path.write_text(
                        judgment["selected_metadata"].model_dump_json(indent=2),
                        encoding="utf-8",
                    )

        return {
            "job_id": job_id,
            "game_name": game_name,
            "total_clips_reviewed": len(clips),
            "judgments": judgments,
        }
