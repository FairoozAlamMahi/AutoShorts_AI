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
        self.orchestrator = JobOrchestrator(
            db=self.db,
            resource_guard=self.guard,
            model_registry=self.registry,
            scratch_dir=self.scratch_dir,
            export_dir=self.export_dir,
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
            video_file_path=clip_path,
            title=title,
            description=description,
            tags=tags or ["#shorts", "#gaming"],
            privacy_status=privacy,
            publish_at_iso=publish_at_iso,
        )
