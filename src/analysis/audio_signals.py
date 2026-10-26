"""Audio signal analysis: RMS loudness transients, spectral flux, and music detection."""
from __future__ import annotations

import os
import wave
from pathlib import Path
from typing import Tuple, Optional
import numpy as np
from scipy.signal import spectrogram


class AudioSignalAnalyzer:
    """Extracts short-time energy transients, gunfire/explosion onsets, and background music presence."""

    @staticmethod
    def read_wav_mono(wav_path: Path | str, target_sr: int = 16000) -> Tuple[np.ndarray, int]:
        """Reads 16-bit PCM WAV into normalized float32 numpy array (-1.0 to 1.0)."""
        with wave.open(str(wav_path), "rb") as wf:
            channels = wf.getnchannels()
            sr = wf.getframerate()
            n_frames = wf.getnframes()
            frames = wf.readframes(n_frames)

        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1)

        return samples, sr

    @classmethod
    def analyze_audio_timeline(
        cls,
        wav_path: Path | str,
        total_duration_sec: float,
    ) -> Tuple[np.ndarray, bool]:
        """
        Analyzes audio on a 1-second grid.
        Returns:
            grid_scores: np.ndarray of shape (ceil(total_duration_sec),) normalized to [0, 1]
            has_music_warning: bool (flags continuous harmonic music > 15s)
        """
        grid_len = max(1, int(np.ceil(total_duration_sec)))
        if not Path(wav_path).exists() or Path(wav_path).stat().st_size == 0:
            return np.zeros(grid_len, dtype=np.float32), False

        try:
            samples, sr = cls.read_wav_mono(wav_path)
        except Exception:
            return np.zeros(grid_len, dtype=np.float32), False

        if len(samples) == 0:
            return np.zeros(grid_len, dtype=np.float32), False

        # 1. Compute RMS energy per 1-second window
        rms_scores = np.zeros(grid_len, dtype=np.float32)
        step = sr  # 1 second step
        for i in range(grid_len):
            start = i * step
            end = min(len(samples), (i + 1) * step)
            if start < len(samples):
                chunk = samples[start:end]
                if len(chunk) > 0:
                    # 90th percentile short-term amplitude
                    chunk_abs = np.abs(chunk)
                    rms_scores[i] = np.percentile(chunk_abs, 90)

        # 2. Compute Spectral Flux (onset density) via Spectrogram
        try:
            frequencies, times, Sxx = spectrogram(samples, fs=sr, nperseg=512, noverlap=256)
            # Difference of successive spectral frames (rectified spectral flux)
            flux = np.diff(Sxx, axis=1)
            flux = np.maximum(0, flux)
            flux_per_time = np.sum(flux, axis=0)

            # Map flux to 1-second grid
            flux_scores = np.zeros(grid_len, dtype=np.float32)
            time_indices = times[:-1]
            for i in range(grid_len):
                mask = (time_indices >= i) & (time_indices < (i + 1))
                if np.any(mask):
                    flux_scores[i] = np.mean(flux_per_time[mask])
        except Exception:
            flux_scores = np.zeros(grid_len, dtype=np.float32)

        # 3. Detect background music (continuous harmonicity / low spectral flatness)
        has_music_warning = False
        try:
            # Spectral flatness = geometric_mean / arithmetic_mean
            eps = 1e-10
            geom_mean = np.exp(np.mean(np.log(Sxx + eps), axis=0))
            arith_mean = np.mean(Sxx + eps, axis=0)
            flatness = geom_mean / arith_mean
            # Low flatness (< 0.25) indicates tonal / harmonic content (music)
            harmonic_mask = flatness < 0.25

            # Count continuous seconds of harmonic content
            sec_harmonic = np.zeros(grid_len, dtype=bool)
            for i in range(grid_len):
                mask = (times >= i) & (times < (i + 1))
                if np.any(mask):
                    sec_harmonic[i] = np.mean(harmonic_mask[mask]) > 0.6

            # Check for >= 15 consecutive seconds
            streak = 0
            for is_harm in sec_harmonic:
                if is_harm:
                    streak += 1
                    if streak >= 15:
                        has_music_warning = True
                        break
                else:
                    streak = 0
        except Exception:
            has_music_warning = False

        # Normalize and blend RMS (0.6) and Spectral Flux (0.4)
        def _norm(arr: np.ndarray) -> np.ndarray:
            ptp = np.ptp(arr)
            return (arr - np.min(arr)) / ptp if ptp > 1e-6 else np.zeros_like(arr)

        norm_rms = _norm(rms_scores)
        norm_flux = _norm(flux_scores)
        combined = 0.6 * norm_rms + 0.4 * norm_flux
        return combined.astype(np.float32), has_music_warning
