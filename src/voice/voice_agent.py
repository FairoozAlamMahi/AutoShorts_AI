"""Local Neural Voice Synthesis Agent.
CUDA-accelerated local TTS utilizing Kokoro-82M and VoiceStudio clone pipelines.
Provides curated viral gaming personas (Trailer Bass, Hype Hook, Lore Storyteller).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
import numpy as np

logger = logging.getLogger(__name__)


class VoicePersona:
    DRAMATIC_TRAILER_BASS = "DRAMATIC_TRAILER_BASS"  # Deep, resonant, cinematic movie trailer
    TIKTOK_HYPE_HOOK = "TIKTOK_HYPE_HOOK"            # Fast, energetic, attention-grabbing
    CALM_LORE_STORYTELLER = "CALM_LORE_STORYTELLER"  # Atmospheric, introspective, dark souls/rpg
    BRITISH_DOCUMENTARY = "BRITISH_DOCUMENTARY"      # Authoritative British narration
    FEMALE_INTENSE = "FEMALE_INTENSE"                # Expressive, sharp female protagonist
    CUSTOM_CLONE = "CUSTOM_CLONE"                    # Custom voice sample from voice_clones dir


PERSONA_CONFIG: Dict[str, Dict[str, Any]] = {
    VoicePersona.DRAMATIC_TRAILER_BASS: {
        "voice": "am_adam",
        "speed": 0.95,
        "description": "Deep resonant male movie trailer narrator",
    },
    VoicePersona.TIKTOK_HYPE_HOOK: {
        "voice": "am_michael",
        "speed": 1.05,
        "description": "High-energy fast TikTok gaming hook",
    },
    VoicePersona.CALM_LORE_STORYTELLER: {
        "voice": "bm_george",
        "speed": 0.96,
        "description": "Atmospheric British lore & dialogue narrator",
    },
    VoicePersona.BRITISH_DOCUMENTARY: {
        "voice": "bm_lewis",
        "speed": 1.0,
        "description": "Crisp documentary breakdown voice",
    },
    VoicePersona.FEMALE_INTENSE: {
        "voice": "af_bella",
        "speed": 1.02,
        "description": "Sharp, dramatic female narration",
    },
}


class VoiceSynthesisAgent:
    """Manages local neural voice synthesis with zero cloud dependencies."""

    def __init__(self, clone_dir: Optional[Path | str] = None) -> None:
        self.clone_dir = Path(clone_dir) if clone_dir else Path("data/voice_clones")
        self.clone_dir.mkdir(parents=True, exist_ok=True)
        self._pipeline = None

    def _get_pipeline(self):
        """Lazy loader for Kokoro pipeline to keep import times fast."""
        if self._pipeline is None:
            try:
                from kokoro import KPipeline
                # Suppress symlink warnings on Windows
                os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
                self._pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
            except Exception as e:
                logger.error(f"Failed to initialize Kokoro pipeline: {e}")
                raise RuntimeError(f"Local TTS initialization failed: {e}")
        return self._pipeline

    def synthesize(
        self,
        text: str,
        output_path: Path | str,
        persona: str = VoicePersona.DRAMATIC_TRAILER_BASS,
        speed: Optional[float] = None,
        custom_voice_path: Optional[Path | str] = None,
    ) -> Tuple[Path, float]:
        """
        Synthesizes text into high-quality 24kHz WAV audio.
        Returns (output_path, duration_sec).
        """
        out_file = Path(output_path).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)

        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Cannot synthesize empty text.")

        import soundfile as sf

        # Resolve voice and speed
        config = PERSONA_CONFIG.get(persona, PERSONA_CONFIG[VoicePersona.DRAMATIC_TRAILER_BASS])
        target_voice = config["voice"]
        target_speed = speed if speed is not None else config["speed"]

        # Support custom voice embeddings if provided
        if custom_voice_path and Path(custom_voice_path).exists():
            target_voice = str(Path(custom_voice_path).resolve())

        pipeline = self._get_pipeline()
        generator = pipeline(clean_text, voice=target_voice, speed=target_speed)

        audio_chunks = []
        for _, _, audio in generator:
            if hasattr(audio, "cpu"):
                audio = audio.cpu().numpy()
            audio_chunks.append(audio)

        if not audio_chunks:
            raise RuntimeError("TTS pipeline produced no audio output.")

        combined_audio = np.concatenate(audio_chunks, axis=0) if len(audio_chunks) > 1 else audio_chunks[0]
        sample_rate = 24000
        sf.write(str(out_file), combined_audio, sample_rate)

        duration_sec = float(len(combined_audio)) / float(sample_rate)
        logger.info(f"Synthesized voiceover [{persona}]: '{clean_text[:40]}...' ({duration_sec:.2f}s) -> {out_file}")
        return out_file, round(duration_sec, 2)

    def synthesize_hook(
        self,
        hook_text: str,
        output_path: Path | str,
        persona: str = VoicePersona.TIKTOK_HYPE_HOOK,
        max_duration_sec: float = 3.2,
    ) -> Tuple[Path, float]:
        """
        Synthesizes an opening viral hook guaranteed to fit within the opening drop window.
        Automatically increases speed if word count exceeds target window.
        """
        words = len(hook_text.split())
        speed = 1.05
        if words > 10:
            speed = 1.18
        elif words > 7:
            speed = 1.10

        out_file, dur = self.synthesize(
            text=hook_text,
            output_path=output_path,
            persona=persona,
            speed=speed,
        )

        return out_file, dur

    @staticmethod
    def list_personas() -> List[Dict[str, Any]]:
        """Returns the list of available voice personas and metadata."""
        return [
            {"id": k, "name": k.replace("_", " ").title(), "description": v["description"], "speed": v["speed"]}
            for k, v in PERSONA_CONFIG.items()
        ]
