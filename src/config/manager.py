"""Settings and Presets manager."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, List
from .schema import AppSettings, WorkflowPreset, PreRunToggles
from ..core.database import DatabaseManager


class ConfigManager:
    """Manages application settings and workflow presets."""

    def __init__(self, config_path: Path | str = "data/settings.json", db: Optional[DatabaseManager] = None) -> None:
        self.config_path = Path(config_path)
        self.db = db
        self.settings = self.load_settings()

    def load_settings(self) -> AppSettings:
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                return AppSettings.model_validate(data)
            except Exception:
                pass
        # Default settings
        settings = AppSettings()
        self.save_settings(settings)
        return settings

    def save_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(self.settings.model_dump_json(indent=2), encoding="utf-8")

    def get_preset(self, name: str) -> Optional[WorkflowPreset]:
        if self.db:
            preset = self.db.get_preset(name)
            if preset:
                return preset
        return self._get_builtin_presets().get(name)

    def save_preset(self, preset: WorkflowPreset) -> None:
        if self.db:
            self.db.save_preset(preset)

    def list_presets(self) -> List[WorkflowPreset]:
        builtins = list(self._get_builtin_presets().values())
        if self.db:
            db_presets = self.db.list_presets()
            existing_names = {p.name for p in db_presets}
            for b in builtins:
                if b.name not in existing_names:
                    db_presets.append(b)
            return db_presets
        return builtins

    @staticmethod
    def _get_builtin_presets() -> dict[str, WorkflowPreset]:
        from .schema import DiscoveryMode, CaptionMode, LayoutMode, MetadataMode
        return {
            "Full AI Gaming": WorkflowPreset(
                name="Full AI Gaming",
                description="Whisper + Signals + VLM Verification + Animated Captions + Hybrid Cinema Stack",
                toggles=PreRunToggles(
                    discovery_mode=DiscoveryMode.FULL_AUTO,
                    captions_mode=CaptionMode.BURNED_IN_ANIMATED,
                    layout_mode=LayoutMode.LAYOUT_HYBRID_CINEMA_STACK,
                    metadata_mode=MetadataMode.LOCAL_VLM,
                    transcription_enabled=True,
                    vlm_verification_enabled=True,
                )
            ),
            "Clean No-Captions": WorkflowPreset(
                name="Clean No-Captions",
                description="Fast audio/visual cut with zero subtitles and no Whisper transcription",
                toggles=PreRunToggles(
                    discovery_mode=DiscoveryMode.FULL_AUTO,
                    captions_mode=CaptionMode.NONE,
                    layout_mode=LayoutMode.LAYOUT_HYBRID_CINEMA_STACK,
                    metadata_mode=MetadataMode.OFF,
                    transcription_enabled=False,
                    use_speech_scoring=False,
                    vlm_verification_enabled=False,
                )
            ),
            "Manual Clip Slice": WorkflowPreset(
                name="Manual Clip Slice",
                description="Bypasses all scoring to slice exact timestamps entered by user",
                toggles=PreRunToggles(
                    discovery_mode=DiscoveryMode.MANUAL_ONLY,
                    captions_mode=CaptionMode.BURNED_IN_CLASSIC,
                    layout_mode=LayoutMode.LAYOUT_A_BLUR_FIT,
                    metadata_mode=MetadataMode.RULE_BASED,
                    vlm_verification_enabled=False,
                )
            ),
        }
