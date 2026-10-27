"""Configuration schemas and pre-run toggle matrix for ShortsFactory Local."""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional, List, Union, Any, Dict
from pydantic import BaseModel, Field, model_validator, field_validator


class DiscoveryMode(str, Enum):
    FULL_AUTO = "FULL_AUTO"
    MANUAL_ONLY = "MANUAL_ONLY"
    HYBRID = "HYBRID"


class CaptionMode(str, Enum):
    NONE = "NONE"
    BURNED_IN_ANIMATED = "BURNED_IN_ANIMATED"
    BURNED_IN_CLASSIC = "BURNED_IN_CLASSIC"
    EXTERNAL_SIDECAR_ONLY = "EXTERNAL_SIDECAR_ONLY"
    BURNED_IN_PLUS_SIDECAR = "BURNED_IN_PLUS_SIDECAR"


class CaptionTheme(str, Enum):
    MRBEAST_YELLOW = "MRBEAST_YELLOW"
    NEON_CYBER_GREEN = "NEON_CYBER_GREEN"
    TIKTOK_RED_BOX = "TIKTOK_RED_BOX"
    ELECTRIC_BLUE = "ELECTRIC_BLUE"
    CLEAN_WHITE = "CLEAN_WHITE"


class LayoutMode(str, Enum):
    LAYOUT_HYBRID_CINEMA_STACK = "LAYOUT_HYBRID_CINEMA_STACK"
    LAYOUT_A_BLUR_FIT = "LAYOUT_A_BLUR_FIT"
    LAYOUT_B_CENTER_CROP = "LAYOUT_B_CENTER_CROP"
    LAYOUT_RAW_16_9 = "LAYOUT_RAW_16_9"
    LAYOUT_FACECAM_SPLIT = "LAYOUT_FACECAM_SPLIT"
    LAYOUT_4_3_BLUR_FIT = "LAYOUT_4_3_BLUR_FIT"
    LAYOUT_4_3_HORIZONTAL = "LAYOUT_4_3_HORIZONTAL"


class FacecamPosition(str, Enum):
    TOP_LEFT = "TOP_LEFT"
    TOP_RIGHT = "TOP_RIGHT"
    BOTTOM_LEFT = "BOTTOM_LEFT"
    BOTTOM_RIGHT = "BOTTOM_RIGHT"


class MetadataMode(str, Enum):
    LOCAL_VLM = "LOCAL_VLM"
    EXTERNAL_MCP_AGENT = "EXTERNAL_MCP_AGENT"
    AGENT_CO_PILOT = "AGENT_CO_PILOT"
    RULE_BASED = "RULE_BASED"
    OFF = "OFF"


class AudioProcessMode(str, Enum):
    LOUDNORM_EBU_R128 = "LOUDNORM_EBU_R128"
    RAW_PASSTHROUGH = "RAW_PASSTHROUGH"


class OwnershipType(str, Enum):
    MY_OWN_VIDEO = "MY_OWN_VIDEO"
    YOUTUBE_THIRD_PARTY = "YOUTUBE_THIRD_PARTY"


class SceneCategory(str, Enum):
    ACTION = "ACTION"
    COMEDY = "COMEDY"
    CLUTCH = "CLUTCH"
    DIALOGUE = "DIALOGUE"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class RightsStatus(str, Enum):
    ORIGINAL_RECORDING = "ORIGINAL_RECORDING"
    EXPLICIT_PERMISSION = "EXPLICIT_PERMISSION"
    CREATIVE_COMMONS = "CREATIVE_COMMONS"
    UNCERTAIN_DRAFT = "UNCERTAIN_DRAFT"


class ManualTimestampRange(BaseModel):
    start_sec: float = Field(ge=0.0, description="Start timestamp in seconds")
    end_sec: float = Field(gt=0.0, description="End timestamp in seconds")
    label: Optional[str] = Field(default=None, description="Optional clip note")

    @model_validator(mode="after")
    def validate_range(self) -> ManualTimestampRange:
        if self.end_sec <= self.start_sec:
            raise ValueError(f"end_sec ({self.end_sec}) must be strictly greater than start_sec ({self.start_sec})")
        return self


class PreRunToggles(BaseModel):
    """
    Every pipeline capability is strictly optional before starting a job.
    Provides dynamic bypass helpers implementing Section 3.2 of the build blueprint.
    """
    model_config = {"populate_by_name": True, "extra": "ignore"}

    @model_validator(mode="before")
    @classmethod
    def _handle_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "facecam_pos" in data and "facecam_position" not in data:
                data["facecam_position"] = data.pop("facecam_pos")
        return data
    discovery_mode: DiscoveryMode = Field(default=DiscoveryMode.FULL_AUTO)
    captions_mode: CaptionMode = Field(default=CaptionMode.BURNED_IN_ANIMATED)
    layout_mode: LayoutMode = Field(default=LayoutMode.LAYOUT_HYBRID_CINEMA_STACK)
    metadata_mode: MetadataMode = Field(default=MetadataMode.LOCAL_VLM)
    audio_process_mode: AudioProcessMode = Field(default=AudioProcessMode.LOUDNORM_EBU_R128)

    transcription_enabled: bool = Field(default=True, description="Master toggle for Whisper speech transcription")
    use_speech_scoring: bool = Field(default=True, description="Include speech excitement signals in highlight scoring")
    vlm_verification_enabled: bool = Field(default=True, description="Inspect candidate keyframes with local VLM")

    target_clip_count: int = Field(default=3, ge=1, le=15, description="Number of highlight shorts to generate")
    manual_timestamps: List[ManualTimestampRange] = Field(default_factory=list, description="Manual slice timestamps")

    ownership_type: OwnershipType = Field(default=OwnershipType.MY_OWN_VIDEO)
    rights_status: RightsStatus = Field(default=RightsStatus.ORIGINAL_RECORDING)
    game_name_context: Optional[str] = Field(default=None, description="Manual game title or YouTube metadata override")

    facecam_position: FacecamPosition = Field(default=FacecamPosition.TOP_LEFT, description="Streamer facecam corner for LAYOUT_FACECAM_SPLIT")
    caption_theme: CaptionTheme = Field(default=CaptionTheme.MRBEAST_YELLOW, description="Color and style theme for captions")
    caption_font_size: int = Field(default=68, ge=32, le=120, description="Font size for rendered captions")
    bgm_track: Optional[Union[str, Any]] = Field(default=None, description="Path or preset for background music (auto-ducks on speech)")
    bgm_volume_duck_db: float = Field(default=-18.0, description="Music attenuation during speech in dB")

    smart_layout_distribution: bool = Field(
        default=False,
        description="Auto-assign layouts and themes based on detected scene type (Action -> Layout B, Comedy/Dialogue -> 4:3 Blur Fit)"
    )
    per_clip_rules: Optional[str] = Field(
        default=None,
        description="Per-clip customization rules, e.g. '1-2: LAYOUT_B_CENTER_CROP, 3-5: LAYOUT_4_3_BLUR_FIT' or '2B, 3A'"
    )
    per_clip_customizations: Dict[int, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Parsed per-clip layout and styling overrides"
    )

    @staticmethod
    def resolve_layout_alias(alias: str) -> Optional[LayoutMode]:
        norm = alias.strip().upper().replace(" ", "_").replace("LAYOUT_", "")
        if norm in ("A", "A_BLUR_FIT", "BLUR_FIT", "BLUR"):
            return LayoutMode.LAYOUT_A_BLUR_FIT
        elif norm in ("B", "B_CENTER_CROP", "CENTER_CROP", "CROP"):
            return LayoutMode.LAYOUT_B_CENTER_CROP
        elif norm in ("4:3", "4_3", "4:3_FIT", "4_3_BLUR_FIT", "SHOW_ALL", "SHOW_IT_ALL"):
            return LayoutMode.LAYOUT_4_3_BLUR_FIT
        elif norm in ("4:3_CROP", "4_3_HORIZONTAL", "4:3_WIDE"):
            return LayoutMode.LAYOUT_4_3_HORIZONTAL
        elif norm in ("HYBRID", "CINEMA_STACK", "HYBRID_CINEMA_STACK", "STACK"):
            return LayoutMode.LAYOUT_HYBRID_CINEMA_STACK
        elif norm in ("FACECAM", "FACECAM_SPLIT", "SPLIT"):
            return LayoutMode.LAYOUT_FACECAM_SPLIT
        elif norm in ("RAW", "RAW_16_9", "16:9", "16_9"):
            return LayoutMode.LAYOUT_RAW_16_9
        try:
            return LayoutMode(alias)
        except Exception:
            return None

    @classmethod
    def parse_per_clip_rules(cls, rules_str: Optional[str]) -> Dict[int, Dict[str, Any]]:
        """
        Parses rules like:
        - '1-2: LAYOUT_B_CENTER_CROP, 3-5: LAYOUT_4_3_BLUR_FIT'
        - '2B, 3A' or '2 with layout B and 3 with layout A'
        - '1: LAYOUT_B, MRBEAST_YELLOW; 2: LAYOUT_4_3_BLUR_FIT, CLEAN_WHITE'
        """
        if not rules_str or not rules_str.strip():
            return {}

        raw = rules_str.strip()
        customizations: Dict[int, Dict[str, Any]] = {}

        # Pattern 1: Count shorthand, e.g. "2B, 3A" or "2 with layout B and 3 with layout A" or "2x B, 3x 4:3"
        count_pattern = re.findall(
            r"(\d+)\s*(?:x|with\s+layout|with)?\s*([a-zA-Z0-9_:\-]+)",
            raw,
            re.IGNORECASE,
        )
        # Verify if this is purely a count shorthand (doesn't contain ':' indicating range 1-2:)
        if ":" not in raw and count_pattern:
            current_clip = 1
            for count_str, layout_str in count_pattern:
                cnt = int(count_str)
                resolved = cls.resolve_layout_alias(layout_str)
                if resolved:
                    for _ in range(cnt):
                        customizations[current_clip] = {"layout_mode": resolved}
                        current_clip += 1
            if customizations:
                return customizations

        # Pattern 2: Range or specific index mapping, e.g. "1-2: LAYOUT_B, 3: LAYOUT_A"
        # Split on semicolons or commas that precede a new clip index/range
        items = re.split(r";\s*|,\s*(?=\d+(?:-\d+)?\s*:)", raw)
        for item in items:
            item = item.strip()
            if not item or ":" not in item:
                continue
            idx_part, rule_part = item.split(":", 1)
            idx_part = idx_part.strip().lower().replace("clip", "").replace("clips", "").strip()
            rule_tokens = [t.strip().rstrip(",") for t in rule_part.split() if t.strip().rstrip(",")]

            indices = []
            if "-" in idx_part:
                start_s, end_s = idx_part.split("-", 1)
                try:
                    for i in range(int(start_s), int(end_s) + 1):
                        indices.append(i)
                except ValueError:
                    pass
            else:
                try:
                    indices.append(int(idx_part))
                except ValueError:
                    pass

            for idx in indices:
                clip_dict: Dict[str, Any] = customizations.setdefault(idx, {})
                for tok in rule_tokens:
                    # Check layout
                    lay = cls.resolve_layout_alias(tok)
                    if lay:
                        clip_dict["layout_mode"] = lay
                        continue
                    # Check theme
                    tok_upper = tok.upper()
                    for theme in CaptionTheme:
                        if theme.value == tok_upper or tok_upper in theme.value:
                            clip_dict["caption_theme"] = theme
                            break

        return customizations

    def get_customization_for_clip(self, clip_index: int) -> Dict[str, Any]:
        """Resolves active per-clip override if configured, else returns empty dict."""
        if self.per_clip_customizations and clip_index in self.per_clip_customizations:
            return self.per_clip_customizations[clip_index]
        if self.per_clip_rules:
            parsed = self.parse_per_clip_rules(self.per_clip_rules)
            if clip_index in parsed:
                return parsed[clip_index]
        return {}

    @field_validator("bgm_track", mode="before")
    @classmethod
    def coerce_bgm_track(cls, v: Any) -> Optional[str]:
        if v is None or v == "":
            return None
        return str(v)

    min_duration_sec: float = Field(default=30.0, ge=5.0, le=180.0, description="Minimum short duration in seconds")
    max_duration_sec: float = Field(default=60.0, ge=10.0, le=180.0, description="Maximum short duration in seconds (YouTube Shorts allows up to 180s / 3 mins)")
    pre_roll_sec: float = Field(default=15.0, ge=0.0, le=90.0)
    post_roll_sec: float = Field(default=10.0, ge=0.0, le=90.0)
    min_gap_sec: float = Field(default=30.0, ge=5.0, le=120.0)

    @property
    def facecam_pos(self) -> FacecamPosition:
        return self.facecam_position

    @model_validator(mode="after")
    def validate_durations(self) -> PreRunToggles:
        if self.max_duration_sec < self.min_duration_sec:
            self.max_duration_sec = self.min_duration_sec
        return self

    # --- Bypass Decision Helpers (Section 3.2 Dynamic Pipeline Bypass Matrix) ---

    def should_run_transcription(self) -> bool:
        """
        Stage 2 Bypass Logic:
        Executed when: transcription_enabled is True AND (
            captions_mode != NONE OR (discovery_mode != MANUAL_ONLY AND use_speech_scoring == True)
        )
        Bypassed when: transcription_enabled is False OR (
            captions_mode == NONE AND (discovery_mode == MANUAL_ONLY OR use_speech_scoring == False)
        )
        """
        if not self.transcription_enabled:
            return False
        
        needs_captions = self.captions_mode != CaptionMode.NONE
        needs_speech_scoring = (self.discovery_mode != DiscoveryMode.MANUAL_ONLY) and self.use_speech_scoring
        return needs_captions or needs_speech_scoring

    def should_run_signal_analysis(self) -> bool:
        """
        Stage 3 Bypass Logic:
        Executed when: discovery_mode is FULL_AUTO or HYBRID.
        Bypassed when: discovery_mode == MANUAL_ONLY.
        """
        return self.discovery_mode in (DiscoveryMode.FULL_AUTO, DiscoveryMode.HYBRID)

    def should_run_vlm(self) -> bool:
        """
        Stage 4 Bypass Logic:
        Executed when: vlm_verification_enabled is True AND discovery_mode != MANUAL_ONLY.
        Bypassed when: vlm_verification_enabled is False OR discovery_mode == MANUAL_ONLY.
        """
        return self.vlm_verification_enabled and (self.discovery_mode != DiscoveryMode.MANUAL_ONLY)

    def should_compile_subtitles(self, has_words: bool = True) -> bool:
        """
        Stage 6 Bypass Logic:
        Executed when: captions_mode in (BURNED_IN_ANIMATED, BURNED_IN_CLASSIC, EXTERNAL_SIDECAR_ONLY, BURNED_IN_PLUS_SIDECAR)
        AND transcript has words.
        Bypassed when: captions_mode == NONE OR transcript contains 0 words.
        """
        if self.captions_mode == CaptionMode.NONE:
            return False
        return has_words

    def should_burn_in_subtitles(self, has_words: bool = True) -> bool:
        """Returns True if the video stream must burn in ASS subtitles."""
        if not has_words:
            return False
        return self.captions_mode in (
            CaptionMode.BURNED_IN_ANIMATED,
            CaptionMode.BURNED_IN_CLASSIC,
            CaptionMode.BURNED_IN_PLUS_SIDECAR,
        )

    def should_export_sidecar(self, has_words: bool = True) -> bool:
        """Returns True if .srt / .vtt sidecars should be written."""
        if not has_words:
            return False
        return self.captions_mode in (
            CaptionMode.EXTERNAL_SIDECAR_ONLY,
            CaptionMode.BURNED_IN_PLUS_SIDECAR,
        )

    def should_generate_metadata(self) -> bool:
        """
        Stage 5 Bypass Logic:
        Executed when metadata_mode != OFF.
        """
        return self.metadata_mode != MetadataMode.OFF


class WorkflowPreset(BaseModel):
    name: str
    description: Optional[str] = ""
    toggles: PreRunToggles = Field(default_factory=PreRunToggles)


class AppSettings(BaseModel):
    default_toggles: PreRunToggles = Field(default_factory=PreRunToggles)
    active_whisper_model_id: str = "faster-whisper-large-v3-turbo"
    active_vlm_model_id: str = "qwen2.5vl:3b"
    max_download_resolution: int = 1080
    disk_warning_threshold_gb: float = 10.0
    vram_warning_threshold_mb: float = 1024.0
    auto_purge_scratch: bool = True
    output_dir: str = "data/exports"
    scratch_dir: str = "data/scratch"
    models_dir: str = "data/models"
