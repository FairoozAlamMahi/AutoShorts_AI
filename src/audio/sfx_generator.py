"""
Cinematic Sound Effects Generator & Manager
Produces procedural broadcast-quality (44.1 kHz, 16-bit stereo) sound effects:
- Sub-bass boom / impact thud
- Fast whoosh transition
- Tension riser / build-up swoosh
- Hit marker / transient punch
"""
from pathlib import Path
from typing import Dict
import math
import numpy as np
import scipy.io.wavfile as wavfile


class CinematicSFXEngine:
    """Manages and procedurally generates cinematic gaming sound effects."""

    def __init__(self, sfx_dir: Path | str = "shorts_factory/assets/sfx"):
        self.sfx_dir = Path(sfx_dir).resolve()
        self.sfx_dir.mkdir(parents=True, exist_ok=True)
        self.sample_rate = 44100
        self._ensure_default_sfx()

    def _ensure_default_sfx(self):
        """Generates default procedural SFX files if not already present."""
        if not (self.sfx_dir / "sub_boom.wav").exists():
            self.generate_sub_boom(self.sfx_dir / "sub_boom.wav")
        if not (self.sfx_dir / "whoosh.wav").exists():
            self.generate_whoosh(self.sfx_dir / "whoosh.wav")
        if not (self.sfx_dir / "riser.wav").exists():
            self.generate_riser(self.sfx_dir / "riser.wav")
        if not (self.sfx_dir / "hit_impact.wav").exists():
            self.generate_hit_impact(self.sfx_dir / "hit_impact.wav")

    def generate_sub_boom(self, out_path: Path | str, duration_sec: float = 1.8) -> Path:
        """Deep cinematic 808 sub-bass drop with exponential decay."""
        p = Path(out_path).resolve()
        sr = self.sample_rate
        total_samples = int(sr * duration_sec)
        t = np.linspace(0, duration_sec, total_samples, endpoint=False)

        # Exponential pitch glide from 92 Hz down to 32 Hz
        freq = 32.0 + (92.0 - 32.0) * np.exp(-t * 3.5)
        phase = 2 * np.pi * np.cumsum(freq) / sr

        # Fundamental + subtle 2nd harmonic for phone speaker audible punch
        wave = np.sin(phase) + 0.35 * np.sin(phase * 2)

        # Amplitude envelope: 5ms attack, exponential decay
        attack_len = int(0.005 * sr)
        env = np.exp(-t * 2.2)
        env[:attack_len] = np.linspace(0, 1, attack_len)

        # Soft clip saturation
        sig = wave * env
        sig = np.tanh(sig * 1.5)

        # Stereo track
        left = sig * 0.95
        right = sig * 1.0
        stereo = np.column_stack((left, right))
        data_int16 = (stereo * 32767 * 0.85).astype(np.int16)

        wavfile.write(str(p), sr, data_int16)
        return p

    def generate_whoosh(self, out_path: Path | str, duration_sec: float = 0.65) -> Path:
        """Fast dynamic whoosh transition with bandpass sweep."""
        p = Path(out_path).resolve()
        sr = self.sample_rate
        total_samples = int(sr * duration_sec)
        t = np.linspace(0, duration_sec, total_samples, endpoint=False)

        # White noise base
        noise = np.random.normal(0, 1, total_samples)

        # Smooth parabolic amplitude envelope peaking in the center
        env = np.sin(np.pi * (t / duration_sec)) ** 2.2

        # Filter simulation: frequency modulation via phase integration
        center_f = 250.0 + 1600.0 * np.sin(np.pi * (t / duration_sec))
        mod = np.sin(2 * np.pi * center_f * t)
        whoosh = noise * 0.4 + mod * 0.6
        whoosh = whoosh * env
        whoosh = np.tanh(whoosh * 1.8)

        # Subtle stereo pan from left to right
        pan_left = 1.0 - (t / duration_sec) * 0.5
        pan_right = 0.5 + (t / duration_sec) * 0.5
        stereo = np.column_stack((whoosh * pan_left, whoosh * pan_right))
        data_int16 = (stereo * 32767 * 0.80).astype(np.int16)

        wavfile.write(str(p), sr, data_int16)
        return p

    def generate_riser(self, out_path: Path | str, duration_sec: float = 2.0) -> Path:
        """Tension riser building up directly into the beat drop."""
        p = Path(out_path).resolve()
        sr = self.sample_rate
        total_samples = int(sr * duration_sec)
        t = np.linspace(0, duration_sec, total_samples, endpoint=False)

        # Exponential frequency rise from 90 Hz up to 880 Hz
        freq = 90.0 * ((880.0 / 90.0) ** (t / duration_sec))
        phase = 2 * np.pi * np.cumsum(freq) / sr

        # Sawtooth-like rich harmonics
        wave = (
            np.sin(phase)
            + 0.5 * np.sin(phase * 2)
            + 0.25 * np.sin(phase * 3)
            + 0.12 * np.sin(phase * 4)
        )

        # Crescendo envelope: slow start, steep ramp in last 30%
        env = (t / duration_sec) ** 1.8

        sig = wave * env * 0.6
        sig = np.tanh(sig * 1.4)

        stereo = np.column_stack((sig, sig))
        data_int16 = (stereo * 32767 * 0.82).astype(np.int16)

        wavfile.write(str(p), sr, data_int16)
        return p

    def generate_hit_impact(self, out_path: Path | str, duration_sec: float = 0.8) -> Path:
        """Punchy impact transient for counter attacks and collision edits."""
        p = Path(out_path).resolve()
        sr = self.sample_rate
        total_samples = int(sr * duration_sec)
        t = np.linspace(0, duration_sec, total_samples, endpoint=False)

        # Transient click + resonance
        freq = 45.0 + 140.0 * np.exp(-t * 22.0)
        phase = 2 * np.pi * np.cumsum(freq) / sr
        tone = np.sin(phase)

        noise = np.random.normal(0, 1, total_samples) * np.exp(-t * 30.0)
        env = np.exp(-t * 6.0)

        sig = (tone * 0.7 + noise * 0.5) * env
        sig = np.tanh(sig * 2.0)

        stereo = np.column_stack((sig, sig))
        data_int16 = (stereo * 32767 * 0.85).astype(np.int16)

        wavfile.write(str(p), sr, data_int16)
        return p

    def get_sfx(self, name: str) -> Path:
        """Returns the path to a specific SFX file by name."""
        paths = self.get_sfx_paths()
        if name in paths:
            return paths[name]
        return self.sfx_dir / f"{name}.wav"

    def get_sfx_paths(self) -> Dict[str, Path]:
        """Returns map of ready-to-use SFX files."""
        return {
            "sub_boom": self.sfx_dir / "sub_boom.wav",
            "whoosh": self.sfx_dir / "whoosh.wav",
            "riser": self.sfx_dir / "riser.wav",
            "hit_impact": self.sfx_dir / "hit_impact.wav",
        }


# Singleton instance
sfx_engine = CinematicSFXEngine()
