"""
Viral Audio Bank & Sound Library Manager
Indexes, analyzes, and catalogs trending phonk, electronic, and action stems.
Uses librosa for automated BPM analysis and beat-drop detection.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import logging
import os
import subprocess

logger = logging.getLogger(__name__)

AUDIO_BANK_DIR = Path("shorts_factory/assets/music/viral_bank").resolve()
MANIFEST_FILE = AUDIO_BANK_DIR / "manifest.json"


@dataclass
class AudioTrack:
    track_id: str
    title: str
    mood: str  # BRAZILIAN_PHONK, DRIFT_PHONK, DARK_FANTASY, RAGE_TRAP, HYPE_EDM
    file_path: str
    duration_sec: float
    bpm: float
    suggested_drop_sec: float
    source_url: Optional[str] = None
    creator: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "title": self.title,
            "mood": self.mood,
            "file_path": self.file_path,
            "duration_sec": self.duration_sec,
            "bpm": self.bpm,
            "suggested_drop_sec": self.suggested_drop_sec,
            "source_url": self.source_url,
            "creator": self.creator,
        }


class ViralAudioBank:
    """Central repository of viral gaming audio stems with automated beat profiling."""

    def __init__(self, base_dir: Optional[Path | str] = None):
        self.bank_dir = Path(base_dir).resolve() if base_dir else AUDIO_BANK_DIR
        self.bank_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.bank_dir / "manifest.json"
        self._tracks: Dict[str, AudioTrack] = {}
        self._load_manifest()

    def _load_manifest(self):
        if not self.manifest_path.exists():
            self._save_manifest()
            return

        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            for t_dict in raw.get("tracks", []):
                p = Path(t_dict.get("file_path", ""))
                if p.exists():
                    self._tracks[t_dict["track_id"]] = AudioTrack(
                        track_id=t_dict["track_id"],
                        title=t_dict["title"],
                        mood=t_dict["mood"],
                        file_path=str(p),
                        duration_sec=float(t_dict.get("duration_sec", 30.0)),
                        bpm=float(t_dict.get("bpm", 120.0)),
                        suggested_drop_sec=float(t_dict.get("suggested_drop_sec", 2.5)),
                        source_url=t_dict.get("source_url"),
                        creator=t_dict.get("creator"),
                    )
        except Exception as e:
            logger.warning(f"Failed to load audio bank manifest: {e}")

    def _save_manifest(self):
        data = {
            "version": "2.0",
            "tracks": [t.to_dict() for t in self._tracks.values()],
        }
        self.manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def profile_track(self, file_path: Path | str) -> Dict[str, float]:
        """Analyzes track with librosa to detect BPM, duration, and the primary beat drop timestamp."""
        p = Path(file_path).resolve()
        try:
            import librosa
            import numpy as np

            # Load first 45s of audio at 22050 Hz
            y, sr = librosa.load(str(p), sr=22050, duration=45.0)
            duration = float(librosa.get_duration(y=y, sr=sr))

            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            bpm_val = float(tempo[0]) if hasattr(tempo, "__len__") else float(tempo)
            if bpm_val < 60.0:
                bpm_val *= 2.0  # normalize half-tempo

            # Onset strength envelope to detect the primary explosion/drop
            onset_env = librosa.onset.onset_strength(y=y, sr=sr)
            times = librosa.times_like(onset_env, sr=sr)

            # Search in the 1.5s to 5.0s window for the opening drop
            mask = (times >= 1.5) & (times <= 5.0)
            if np.any(mask):
                sub_env = onset_env[mask]
                sub_times = times[mask]
                peak_idx = int(np.argmax(sub_env))
                drop_ts = float(sub_times[peak_idx])
            else:
                drop_ts = 2.5

            return {
                "duration_sec": round(duration, 2),
                "bpm": round(bpm_val, 1),
                "suggested_drop_sec": round(drop_ts, 2),
            }
        except Exception as e:
            logger.warning(f"Librosa profiling fallback for {p.name}: {e}")
            return {
                "duration_sec": 30.0,
                "bpm": 128.0,
                "suggested_drop_sec": 2.5,
            }

    def register_track(
        self,
        file_path: Path | str,
        track_id: str,
        title: str,
        mood: str,
        creator: Optional[str] = None,
        source_url: Optional[str] = None,
    ) -> AudioTrack:
        """Profiles and registers an audio track in the persistent bank."""
        p = Path(file_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Audio file does not exist: {p}")

        profile = self.profile_track(p)
        track = AudioTrack(
            track_id=track_id,
            title=title,
            mood=mood.upper(),
            file_path=str(p),
            duration_sec=profile["duration_sec"],
            bpm=profile["bpm"],
            suggested_drop_sec=profile["suggested_drop_sec"],
            source_url=source_url,
            creator=creator,
        )
        self._tracks[track_id] = track
        self._save_manifest()
        return track

    def get_track(self, track_id: str) -> Optional[AudioTrack]:
        return self._tracks.get(track_id)

    def list_tracks(self, mood: Optional[str] = None) -> List[AudioTrack]:
        tracks = list(self._tracks.values())
        if mood:
            m = mood.upper()
            tracks = [t for t in tracks if m in t.mood]
        return tracks

    def get_best_match_for_game(self, game_title: str) -> AudioTrack:
        """Selects an ideal viral track based on the game's energy and thematic genre."""
        g = game_title.lower()
        if any(w in g for w in ["phantom", "soul", "blade", "elden", "wuxia", "myth", "black"]):
            dark_tracks = self.list_tracks("DARK_FANTASY") + self.list_tracks("DRIFT_PHONK")
            if dark_tracks:
                return dark_tracks[0]

        if any(w in g for w in ["gta", "theft", "car", "drift", "speed", "stunt", "chase"]):
            rage_tracks = self.list_tracks("BRAZILIAN_PHONK") + self.list_tracks("RAGE_TRAP")
            if rage_tracks:
                return rage_tracks[0]

        # Default fallback
        if self._tracks:
            return list(self._tracks.values())[0]

        # In worst case create and return a procedural fallback track
        fallback_p = self.bank_dir / "procedural_phonk_pulse.wav"
        if not fallback_p.exists():
            self._generate_procedural_phonk(fallback_p)
        return self.register_track(
            file_path=fallback_p,
            track_id="procedural_phonk_pulse",
            title="Procedural Viral Phonk Pulse",
            mood="BRAZILIAN_PHONK",
            creator="Local Audio Engine",
        )

    def _generate_procedural_phonk(self, out_path: Path, duration_sec: float = 35.0):
        """Generates a heavy, punchy procedural 130 BPM Phonk groove with sub-bass drop."""
        import numpy as np
        import scipy.io.wavfile as wavfile

        sr = 44100
        total_samples = int(sr * duration_sec)
        t = np.linspace(0, duration_sec, total_samples, endpoint=False)
        audio = np.zeros(total_samples)

        bpm = 130.0
        beat_interval = 60.0 / bpm
        drop_sec = 2.6

        # 1. Cowbell melody (classic 80s / Phonk cowbell synth)
        cowbell_freqs = [587.33, 659.25, 783.99, 880.0]  # D5, E5, G5, A5
        for i in range(int(duration_sec / (beat_interval / 2))):
            hit_t = i * (beat_interval / 2)
            f = cowbell_freqs[i % len(cowbell_freqs)]
            idx = int(hit_t * sr)
            hit_dur = int(0.18 * sr)
            if idx + hit_dur < total_samples:
                ht = np.linspace(0, 0.18, hit_dur)
                decay = np.exp(-ht * 28.0)
                tone = (np.sin(2 * np.pi * f * ht) + 0.6 * np.sin(2 * np.pi * (f * 1.5) * ht)) * decay
                audio[idx : idx + hit_dur] += tone * 0.45

        # 2. Kick + 808 Sub-bass drop after drop_sec
        sub_freq = 42.0  # F1 note
        for beat in np.arange(0, duration_sec, beat_interval):
            if beat >= drop_sec:
                idx = int(beat * sr)
                kick_dur = int(0.35 * sr)
                if idx + kick_dur < total_samples:
                    kt = np.linspace(0, 0.35, kick_dur)
                    # Pitch-dropped kick
                    k_freq = sub_freq + 80.0 * np.exp(-kt * 45.0)
                    k_phase = 2 * np.pi * np.cumsum(k_freq) / sr
                    k_env = np.exp(-kt * 8.0)
                    audio[idx : idx + kick_dur] += np.sin(k_phase) * k_env * 0.95

        # Soft clipping
        audio = np.tanh(audio * 1.6)
        stereo = np.column_stack((audio * 0.95, audio * 1.0))
        data_int16 = (stereo * 32767 * 0.88).astype(np.int16)
        wavfile.write(str(out_path), sr, data_int16)


# Singleton instance
viral_audio_bank = ViralAudioBank()
