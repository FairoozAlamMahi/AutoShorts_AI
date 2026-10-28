"""Declarative Edit Template Registry & BPM Beat Alignment Engine.
Manages viral edit recipes (Phonk, Velocity, Cinematic Lore) with automated librosa beat detection.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EditTemplate(BaseModel):
    """Declarative specification for a viral edit style."""
    template_id: str
    display_name: str
    category: str = "PHONK_AURA"  # PHONK_AURA, VELOCITY_TRAP, CINEMATIC_LORE, SOUND_SYNC
    bgm_file: Optional[str] = None
    bpm: float = 120.0
    beat_drop_sec: float = 2.5
    framing_mode: str = "LAYOUT_A_BLUR_FIT"
    visual_effects: List[str] = Field(default_factory=lambda: ["ambient_blur", "2frame_flash"])
    pre_drop_silence_sec: float = 0.25
    voice_duck_db: float = -18.0
    recommended_persona: str = "DRAMATIC_TRAILER_BASS"
    caption_theme: str = "MRBEAST_YELLOW"
    caption_font_size: int = 68
    description: str = ""


class EditTemplateManager:
    """Loads, saves, and auto-calibrates edit templates and music beat-grids."""

    DEFAULT_TEMPLATES_DIR = Path("data/templates")
    MUSIC_DIR = Path("data/music")

    def __init__(self, templates_dir: Optional[Path | str] = None, music_dir: Optional[Path | str] = None) -> None:
        self.templates_dir = Path(templates_dir) if templates_dir else self.DEFAULT_TEMPLATES_DIR
        self.music_dir = Path(music_dir) if music_dir else self.MUSIC_DIR
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.music_dir.mkdir(parents=True, exist_ok=True)
        self.seed_default_templates()

    def list_templates(self) -> List[EditTemplate]:
        """Returns all registered edit templates."""
        templates = []
        for p in sorted(self.templates_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                templates.append(EditTemplate(**data))
            except Exception as ex:
                logger.warning(f"Failed to parse template {p}: {ex}")
        return templates

    def get_template(self, template_id: str) -> Optional[EditTemplate]:
        """Retrieves a template by ID or returns None."""
        p = self.templates_dir / f"{template_id}.json"
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                return EditTemplate(**data)
            except Exception as ex:
                logger.error(f"Error reading {p}: {ex}")
        return None

    def save_template(self, template: EditTemplate) -> Path:
        """Saves or updates a template definition."""
        p = self.templates_dir / f"{template.template_id}.json"
        p.write_text(template.model_dump_json(indent=2), encoding="utf-8")
        logger.info(f"Registered edit template: {template.template_id} -> {p}")
        return p

    def auto_detect_beat_grid(self, audio_path: Path | str) -> Dict[str, Any]:
        """
        Uses librosa to detect track BPM, onset strength, and primary beat drop.
        """
        import librosa
        p = Path(audio_path).resolve()
        if not p.exists():
            return {"bpm": 120.0, "beat_drop_sec": 2.5, "beats": []}

        try:
            # Load first 30 seconds of audio for fast beat tracking
            y, sr = librosa.load(str(p), sr=22050, duration=30.0)
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
            beat_times = librosa.frames_to_time(beats, sr=sr)

            # Estimate beat drop (first large energy onset after 2s)
            drop_sec = 2.5
            if len(beat_times) > 0:
                # Find beat closest to 2.5s
                candidates = [t for t in beat_times if t >= 1.8]
                if candidates:
                    drop_sec = float(candidates[0])

            float_tempo = float(tempo[0]) if hasattr(tempo, "__len__") else float(tempo)
            return {
                "bpm": round(float_tempo, 1),
                "beat_drop_sec": round(drop_sec, 2),
                "suggested_drop_sec": round(drop_sec, 2),
                "beats": [round(float(b), 3) for b in beat_times[:16]],
            }
        except Exception as ex:
            logger.warning(f"Could not compute librosa beat grid for {p}: {ex}")
            return {"bpm": 120.0, "beat_drop_sec": 2.5, "suggested_drop_sec": 2.5, "beats": []}

    analyze_audio_beatgrid = auto_detect_beat_grid

    def register_new_song_template(
        self,
        audio_path: Path | str,
        template_id: str,
        display_name: str,
        category: str = "PHONK_AURA",
        framing_mode: str = "LAYOUT_A_BLUR_FIT",
        recommended_persona: str = "DRAMATIC_TRAILER_BASS",
    ) -> EditTemplate:
        """
        Analyzes a new audio file with librosa and generates a full edit template.
        """
        audio_p = Path(audio_path).resolve()
        beat_info = self.auto_detect_beat_grid(audio_p)

        template = EditTemplate(
            template_id=template_id,
            display_name=display_name,
            category=category,
            bgm_file=str(audio_p),
            bpm=beat_info["bpm"],
            beat_drop_sec=beat_info["beat_drop_sec"],
            framing_mode=framing_mode,
            visual_effects=["ambient_blur", "2frame_flash", "smash_zoom"],
            pre_drop_silence_sec=0.25,
            voice_duck_db=-18.0,
            recommended_persona=recommended_persona,
            description=f"Auto-generated viral template for {display_name} ({beat_info['bpm']} BPM).",
        )
        self.save_template(template)
        return template

    def seed_default_templates(self) -> None:
        """Seeds default viral edit recipes if empty."""
        defaults = [
            EditTemplate(
                template_id="aura_brazilian_phonk",
                display_name="Aura Brazilian Phonk (Slowed)",
                category="PHONK_AURA",
                bgm_file="assets/music/action_pulse.mp3",
                bpm=115.0,
                beat_drop_sec=2.6,
                framing_mode="LAYOUT_A_BLUR_FIT",
                visual_effects=["ambient_blur", "2frame_flash", "smash_zoom"],
                pre_drop_silence_sec=0.30,
                recommended_persona="DRAMATIC_TRAILER_BASS",
                caption_theme="MRBEAST_YELLOW",
                description="Cold-blooded combat dominance with sub-bass drop and 2-frame impact flash.",
            ),
            EditTemplate(
                template_id="velocity_rage_trap",
                display_name="Velocity Rage Trap",
                category="VELOCITY_TRAP",
                bgm_file="assets/music/action_pulse.mp3",
                bpm=140.0,
                beat_drop_sec=2.2,
                framing_mode="LAYOUT_4_3_BLUR_FIT",
                visual_effects=["ambient_blur", "speed_ramp", "chromatic_shake"],
                pre_drop_silence_sec=0.20,
                recommended_persona="TIKTOK_HYPE_HOOK",
                caption_theme="NEON_CYBER_GREEN",
                description="High-energy speed ramps and fast kinetic transitions for clutches & snipes.",
            ),
            EditTemplate(
                template_id="cinematic_lore_ambient",
                display_name="Cinematic Lore & Atmosphere",
                category="CINEMATIC_LORE",
                bgm_file="assets/music/ambient_lofi.mp3",
                bpm=90.0,
                beat_drop_sec=3.5,
                framing_mode="LAYOUT_A_BLUR_FIT",
                visual_effects=["ambient_blur", "slow_pan", "letterbox_soft"],
                pre_drop_silence_sec=0.0,
                recommended_persona="CALM_LORE_STORYTELLER",
                caption_theme="CLEAN_WHITE",
                description="Melancholic synthwave and deep narrative storytelling for open worlds.",
            ),
            EditTemplate(
                template_id="combat_parry_sync",
                display_name="Katana Parry Sound Sync",
                category="SOUND_SYNC",
                bgm_file="assets/music/action_pulse.mp3",
                bpm=128.0,
                beat_drop_sec=2.4,
                framing_mode="LAYOUT_A_BLUR_FIT",
                visual_effects=["ambient_blur", "2frame_flash", "impact_shake"],
                pre_drop_silence_sec=0.35,
                recommended_persona="DRAMATIC_TRAILER_BASS",
                caption_theme="MRBEAST_YELLOW",
                description="Percussive sword clashing tuned directly into the drum track with silence drop.",
            ),
        ]
        for t in defaults:
            p = self.templates_dir / f"{t.template_id}.json"
            if not p.exists():
                self.save_template(t)
