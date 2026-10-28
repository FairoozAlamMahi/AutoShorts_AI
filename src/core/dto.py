"""Strict Pydantic v2 Data Transfer Objects (DTOs) passed between pipeline stages."""
from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from ..config.schema import PreRunToggles, OwnershipType, RightsStatus


class MediaInspectionDTO(BaseModel):
    """Result of ffprobe inspection on source media."""
    file_path: str
    duration_sec: float = Field(ge=0.0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0.0)
    is_vfr: bool = False
    video_codec: str
    audio_codec: Optional[str] = None
    has_audio: bool = False
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    bitrate_kbps: Optional[float] = None


class YouTubeMetadataDTO(BaseModel):
    """Extracted YouTube video and game metadata via yt-dlp."""
    url: str
    title: str
    uploader: str
    uploader_id: Optional[str] = None
    duration_sec: float = 0.0
    tags: List[str] = Field(default_factory=list)
    detected_game: Optional[str] = None
    description: Optional[str] = None
    view_count: Optional[int] = None
    downloaded_file_path: Optional[str] = None


class TranscriptWordDTO(BaseModel):
    """Individual word with precise millisecond-level alignment."""
    word: str
    start_sec: float = Field(ge=0.0)
    end_sec: float = Field(ge=0.0)
    confidence: float = 1.0


class TranscriptSegmentDTO(BaseModel):
    """Group of words representing a continuous speech phrase/sentence."""
    id: int
    start_sec: float = Field(ge=0.0)
    end_sec: float = Field(ge=0.0)
    text: str
    words: List[TranscriptWordDTO] = Field(default_factory=list)


class TranscriptDTO(BaseModel):
    """Complete video transcript."""
    segments: List[TranscriptSegmentDTO] = Field(default_factory=list)
    language: str = "en"
    is_skipped: bool = False
    speech_coverage_ratio: float = 0.0

    @property
    def total_words(self) -> int:
        return sum(len(s.words) for s in self.segments)

    @property
    def full_text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments if s.text.strip())


class CandidateClipDTO(BaseModel):
    """A scored highlight candidate window with envelope boundaries."""
    clip_index: int
    start_sec: float = Field(ge=0.0)
    end_sec: float = Field(gt=0.0)
    duration_sec: float = Field(gt=0.0)
    peak_timestamp_sec: float = Field(ge=0.0)
    acoustic_score: float = 0.0
    visual_score: float = 0.0
    speech_score: float = 0.0
    vlm_score: Optional[float] = None
    composite_score: float = 0.0
    is_manual: bool = False
    reason: str = ""
    sub_scores: Dict[str, float] = Field(default_factory=dict)
    scene_category: str = "ACTION"
    hook_score: Optional[float] = None
    hook_formula: Optional[str] = None
    hook_overlay_text: Optional[str] = None
    hook_breakdown: Dict[str, float] = Field(default_factory=dict)
    custom_layout: Optional[str] = None
    custom_caption_theme: Optional[str] = None
    custom_caption_font_size: Optional[int] = None
    custom_bgm_track: Optional[str] = None
    voice_audio_path: Optional[str] = None
    spoken_script: Optional[str] = None
    voice_persona: Optional[str] = None
    edit_template_id: Optional[str] = None
    impact_flash: bool = False
    transcript_snippet: str = ""
    keyframe_paths: List[str] = Field(default_factory=list)


class VLMAnalysisDTO(BaseModel):
    """Result of visual keyframe clutch inspection."""
    clutch_confidence: float = Field(ge=0.0, le=1.0)
    is_action_gameplay: bool = True
    scene_summary: str = ""
    scene_type: str = "ACTION"
    suggested_layout: Optional[str] = None
    facecam_detected: Optional[str] = None
    detected_events: List[str] = Field(default_factory=list)
    rejection_reason: Optional[str] = None


class ClipMetadataDTO(BaseModel):
    """Context-grounded generated titles, description, and hashtags."""
    primary_title: str
    alternative_titles: List[str] = Field(default_factory=list)
    small_description: str
    tags: List[str] = Field(default_factory=list)
    attribution_text: Optional[str] = None


class ProvenanceDTO(BaseModel):
    """Legal rights and source provenance record saved as clip_XX.provenance.json."""
    clip_id: str
    source_file_sha256_prefix: str
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    source_uploader: Optional[str] = None
    start_sec: float
    end_sec: float
    created_at_iso: str
    ownership_type: OwnershipType
    rights_status: RightsStatus
    attribution_text: Optional[str] = None
    toggles_snapshot: Dict[str, Any] = Field(default_factory=dict)


class JobRequestDTO(BaseModel):
    """Request to create and process a new video job."""
    job_id: str
    source_path_or_url: str
    toggles: PreRunToggles = Field(default_factory=PreRunToggles)
    clip_overrides: Dict[int, Dict[str, Any]] = Field(default_factory=dict)
    created_at_iso: str


class JobStatusDTO(BaseModel):
    """Current state of a background job."""
    job_id: str
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    current_stage: str = "INITIALIZED"
    progress_pct: float = 0.0
    error_message: Optional[str] = None
    exported_clips: List[str] = Field(default_factory=list)
