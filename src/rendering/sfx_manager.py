"""Game-Specific Audio & Transition SFX Library and Procedural Synthesizer.
Provides whoosh, riser, impact, fail, and clutch stingers for automated Shorts editing,
with a zero-dependency procedural WAV generator for 100% offline self-contained reliability.
"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class SyntheticSFXFactory:
    """Zero-dependency synthesizer that generates clean stereo 44.1kHz WAV SFX files."""

    SAMPLE_RATE = 44100

    @classmethod
    def generate_whoosh(cls, output_path: Path, duration_sec: float = 0.5) -> Path:
        """Generates a dynamic frequency-sweep air whoosh sound."""
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        total_samples = int(cls.SAMPLE_RATE * duration_sec)
        frames = bytearray()

        for i in range(total_samples):
            t = i / cls.SAMPLE_RATE
            p = t / duration_sec
            # Frequency sweeps from 250Hz up to 1200Hz then down to 400Hz
            freq = 250.0 + 950.0 * math.sin(math.pi * p)
            # Envelope: bell curve
            env = math.sin(math.pi * p) ** 2
            # Add subtle white-noise texture
            pseudo_noise = (((i * 1103515245 + 12345) & 0x7FFFFFFF) / 0x7FFFFFFF) * 0.2 - 0.1
            sample_val = (math.sin(2 * math.pi * freq * t) * 0.8 + pseudo_noise) * env * 0.85
            s16 = max(-32767, min(32767, int(sample_val * 32767)))
            # Stereo left and right
            frames.extend(struct.pack("<hh", s16, s16))

        with wave.open(str(out), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(cls.SAMPLE_RATE)
            wf.writeframes(frames)
        return out

    @classmethod
    def generate_impact(cls, output_path: Path, duration_sec: float = 0.7) -> Path:
        """Generates a deep sub-bass cinematic impact / hit."""
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        total_samples = int(cls.SAMPLE_RATE * duration_sec)
        frames = bytearray()

        for i in range(total_samples):
            t = i / cls.SAMPLE_RATE
            p = t / duration_sec
            # Frequency pitch drops rapidly from 160Hz down to 45Hz
            freq = 45.0 + 115.0 * math.exp(-6.0 * p)
            # Fast exponential attack, long resonant decay
            env = math.exp(-3.5 * p)
            sample_val = math.sin(2 * math.pi * freq * t) * env * 0.95
            s16 = max(-32767, min(32767, int(sample_val * 32767)))
            frames.extend(struct.pack("<hh", s16, s16))

        with wave.open(str(out), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(cls.SAMPLE_RATE)
            wf.writeframes(frames)
        return out

    @classmethod
    def generate_riser(cls, output_path: Path, duration_sec: float = 1.2) -> Path:
        """Generates an escalating suspense riser build-up."""
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        total_samples = int(cls.SAMPLE_RATE * duration_sec)
        frames = bytearray()

        for i in range(total_samples):
            t = i / cls.SAMPLE_RATE
            p = t / duration_sec
            # Frequency steadily rises from 150Hz to 900Hz
            freq = 150.0 + 750.0 * (p ** 2)
            # Volume ramps up smoothly
            env = 0.1 + 0.9 * (p ** 1.8)
            sample_val = math.sin(2 * math.pi * freq * t) * env * 0.8
            s16 = max(-32767, min(32767, int(sample_val * 32767)))
            frames.extend(struct.pack("<hh", s16, s16))

        with wave.open(str(out), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(cls.SAMPLE_RATE)
            wf.writeframes(frames)
        return out

    @classmethod
    def generate_fail_horn(cls, output_path: Path, duration_sec: float = 1.0) -> Path:
        """Generates a comedic descending trombone/fail horn stinger."""
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        total_samples = int(cls.SAMPLE_RATE * duration_sec)
        frames = bytearray()

        for i in range(total_samples):
            t = i / cls.SAMPLE_RATE
            p = t / duration_sec
            # Two descending tones: first half 220Hz (A3), second half 196Hz (G3) with pitch drop
            if p < 0.45:
                freq = 220.0
                env = math.sin(math.pi * (p / 0.45))
            else:
                p2 = (p - 0.45) / 0.55
                freq = 196.0 - 20.0 * p2
                env = math.sin(math.pi * p2) * 0.9
            # Rich brass harmonic: fundamental + 2nd + 3rd harmonic
            sample_val = (
                math.sin(2 * math.pi * freq * t) * 0.6
                + math.sin(4 * math.pi * freq * t) * 0.3
                + math.sin(6 * math.pi * freq * t) * 0.1
            ) * env * 0.85
            s16 = max(-32767, min(32767, int(sample_val * 32767)))
            frames.extend(struct.pack("<hh", s16, s16))

        with wave.open(str(out), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(cls.SAMPLE_RATE)
            wf.writeframes(frames)
        return out

    @classmethod
    def generate_clutch_stinger(cls, output_path: Path, duration_sec: float = 1.2) -> Path:
        """Generates a triumphant high-energy victory / clutch audio stinger."""
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        total_samples = int(cls.SAMPLE_RATE * duration_sec)
        frames = bytearray()

        for i in range(total_samples):
            t = i / cls.SAMPLE_RATE
            p = t / duration_sec
            # Ascending triad: C5 (523Hz), E5 (659Hz), G5 (784Hz)
            if p < 0.25:
                freq = 523.25
                env = math.sin(math.pi * (p / 0.25))
            elif p < 0.5:
                freq = 659.25
                env = math.sin(math.pi * ((p - 0.25) / 0.25))
            else:
                freq = 783.99
                p3 = (p - 0.5) / 0.5
                env = math.exp(-2.0 * p3)
            sample_val = (
                math.sin(2 * math.pi * freq * t) * 0.7
                + math.sin(4 * math.pi * freq * t) * 0.2
            ) * env * 0.85
            s16 = max(-32767, min(32767, int(sample_val * 32767)))
            frames.extend(struct.pack("<hh", s16, s16))

        with wave.open(str(out), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(cls.SAMPLE_RATE)
            wf.writeframes(frames)
        return out


class SFXManager:
    """Manages audio SFX sound library, auto-synthesizing missing assets when needed."""

    AVAILABLE_SFX = {
        "WHOOSH": "whoosh.wav",
        "IMPACT": "impact.wav",
        "RISER": "riser.wav",
        "FAIL": "fail_horn.wav",
        "CLUTCH": "clutch_stinger.wav",
    }

    def __init__(self, sfx_dir: Optional[Path | str] = None) -> None:
        if sfx_dir is not None:
            self.sfx_dir = Path(sfx_dir).resolve()
        else:
            self.sfx_dir = Path(__file__).resolve().parent.parent.parent / "assets" / "sfx"
        self.sfx_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_library()

    def _ensure_library(self) -> None:
        """Verifies all standard SFX exist; synthesizes any missing sound assets."""
        gens = {
            "whoosh.wav": SyntheticSFXFactory.generate_whoosh,
            "impact.wav": SyntheticSFXFactory.generate_impact,
            "riser.wav": SyntheticSFXFactory.generate_riser,
            "fail_horn.wav": SyntheticSFXFactory.generate_fail_horn,
            "clutch_stinger.wav": SyntheticSFXFactory.generate_clutch_stinger,
        }
        for filename, generator in gens.items():
            dest = self.sfx_dir / filename
            if not dest.exists():
                generator(dest)

    def get_sfx_path(self, sfx_type: str) -> Path:
        """Returns the absolute file path for a requested SFX type."""
        key = sfx_type.strip().upper()
        filename = self.AVAILABLE_SFX.get(key, "whoosh.wav")
        target = self.sfx_dir / filename
        if not target.exists():
            self._ensure_library()
        return target

    def get_sfx_for_scene(self, scene_category: str) -> Optional[Path]:
        """Maps detected scene types to appropriate SFX stingers."""
        cat = scene_category.strip().upper()
        if cat in ("ACTION", "COMBAT"):
            return self.get_sfx_path("IMPACT")
        elif cat in ("FAIL", "DEATH", "BUSTED"):
            return self.get_sfx_path("FAIL")
        elif cat in ("CLUTCH", "VICTORY", "HEIST_SUCCESS"):
            return self.get_sfx_path("CLUTCH")
        elif cat in ("SUSPENSE", "CHASE"):
            return self.get_sfx_path("RISER")
        return self.get_sfx_path("WHOOSH")
