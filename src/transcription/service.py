"""TranscriptionService orchestrating audio extraction and STT provider with GPU lease."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional
from ..core.dto import TranscriptDTO
from ..core.resource_guard import ResourceGuard
from ..providers.base import TranscriptionProvider
from ..ingest.media_inspector import MediaInspector


class TranscriptionService:
    """Extracts 16kHz mono audio and coordinates pluggable STT models under ResourceGuard."""

    def __init__(
        self,
        provider: TranscriptionProvider,
        resource_guard: Optional[ResourceGuard] = None,
        scratch_dir: Path | str = "data/scratch",
        ffmpeg_path: Optional[str] = None,
    ) -> None:
        self.provider = provider
        self.resource_guard = resource_guard
        self.scratch_dir = Path(scratch_dir)
        self.ffmpeg_path = ffmpeg_path or self._resolve_ffmpeg()

    @staticmethod
    def _resolve_ffmpeg() -> str:
        which = shutil.which("ffmpeg")
        if which:
            return which
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            winget_pkgs = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
            if winget_pkgs.exists():
                for bin_file in winget_pkgs.glob("**/ffmpeg.exe"):
                    return str(bin_file)
        return "ffmpeg"

    def extract_audio(self, video_path: Path | str, output_wav: Path | str) -> Path:
        """Extracts 16kHz mono PCM WAV from input video."""
        src = Path(video_path).resolve()
        dst = Path(output_wav).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(src),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(dst)
        ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg audio extraction failed: {res.stderr}")
        return dst

    def transcribe_video(
        self,
        video_path: Path | str,
        job_id: str,
        language: Optional[str] = "en",
    ) -> TranscriptDTO:
        v_path = Path(video_path).resolve()

        # Check if video has an audio stream
        inspector = MediaInspector()
        try:
            inspection = inspector.inspect(v_path)
            if not inspection.has_audio:
                return TranscriptDTO(segments=[], language=language or "en", is_skipped=True)
        except Exception:
            pass

        wav_path = self.scratch_dir / job_id / "audio_16k.wav"
        self.extract_audio(v_path, wav_path)

        def _do_transcribe() -> TranscriptDTO:
            try:
                return self.provider.transcribe(str(wav_path), language=language)
            finally:
                # Crucial hardware guardrail: immediately release weights and flush VRAM
                self.provider.unload_model()

        if self.resource_guard:
            with self.resource_guard.gpu_stage_lease("WHISPER_TRANSCRIPTION"):
                return _do_transcribe()
        else:
            return _do_transcribe()
