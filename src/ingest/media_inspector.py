"""Media inspector using ffprobe (shell=False) with graceful audio and corruption handling."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional
from ..core.dto import MediaInspectionDTO


class CorruptMediaError(Exception):
    """Raised when media file is corrupt, 0 bytes, or unreadable by ffprobe."""
    pass


class MediaInspector:
    """Extracts stream metadata, duration, frame rates, and audio presence via ffprobe."""

    def __init__(self, ffprobe_path: Optional[str] = None) -> None:
        self.ffprobe_path = ffprobe_path or self._resolve_ffprobe()

    @staticmethod
    def _resolve_ffprobe() -> str:
        # Check standard PATH
        which_path = shutil.which("ffprobe")
        if which_path:
            return which_path

        # Check WinGet installation path
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            winget_pkgs = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
            if winget_pkgs.exists():
                for probe in winget_pkgs.glob("**/ffprobe.exe"):
                    return str(probe)

        return "ffprobe"

    @staticmethod
    def compute_sha256_prefix(file_path: Path | str, num_chars: int = 16) -> str:
        """Computes SHA-256 hash prefix for copyright provenance tracking."""
        p = Path(file_path)
        if not p.exists() or p.stat().st_size == 0:
            return "0000000000000000"
        hasher = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()[:num_chars]

    def inspect(self, file_path: Path | str) -> MediaInspectionDTO:
        p = Path(file_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Media file not found: {p}")
        if p.stat().st_size == 0:
            raise CorruptMediaError(f"Media file is empty (0 bytes): {p}")

        cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration,bit_rate:stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,sample_rate,channels",
            "-of", "json",
            str(p)
        ]

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                timeout=15,
                check=True
            )
        except subprocess.CalledProcessError as e:
            raise CorruptMediaError(f"ffprobe failed to read file {p}: {e.stderr.strip()}") from e
        except Exception as e:
            raise CorruptMediaError(f"ffprobe execution error for {p}: {e}") from e

        try:
            data = json.loads(res.stdout)
        except json.JSONDecodeError as e:
            raise CorruptMediaError(f"Invalid JSON returned from ffprobe: {e}") from e

        streams = data.get("streams", [])
        format_info = data.get("format", {})

        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        if not video_stream:
            raise CorruptMediaError(f"File contains no valid video stream: {p}")

        # Parse duration
        duration_sec = 0.0
        if "duration" in format_info and format_info["duration"] != "N/A":
            duration_sec = float(format_info["duration"])
        elif "duration" in video_stream and video_stream["duration"] != "N/A":
            duration_sec = float(video_stream["duration"])

        # Parse resolution
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
        video_codec = str(video_stream.get("codec_name", "unknown"))

        # Parse FPS & VFR
        fps = 60.0
        is_vfr = False
        r_fps_str = video_stream.get("r_frame_rate", "60/1")
        avg_fps_str = video_stream.get("avg_frame_rate", "60/1")

        def _eval_ratio(r_str: str) -> float:
            if "/" in r_str:
                num, den = r_str.split("/")
                return float(num) / float(den) if float(den) != 0 else 0.0
            return float(r_str)

        try:
            r_fps = _eval_ratio(r_fps_str)
            avg_fps = _eval_ratio(avg_fps_str)
            if avg_fps > 0:
                fps = round(avg_fps, 2)
            elif r_fps > 0:
                fps = round(r_fps, 2)
            # Flag VFR if r_frame_rate and avg_frame_rate deviate noticeably
            if r_fps > 0 and avg_fps > 0 and abs(r_fps - avg_fps) > 0.5:
                is_vfr = True
        except Exception:
            fps = 60.0

        # Parse Audio stream (gracefully handle missing audio)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        has_audio = audio_stream is not None
        audio_codec = str(audio_stream.get("codec_name")) if audio_stream else None
        sample_rate = int(audio_stream.get("sample_rate")) if (audio_stream and "sample_rate" in audio_stream) else None
        channels = int(audio_stream.get("channels")) if (audio_stream and "channels" in audio_stream) else None

        # Parse Bitrate
        bitrate_kbps = None
        if "bit_rate" in format_info and format_info["bit_rate"] != "N/A":
            bitrate_kbps = round(float(format_info["bit_rate"]) / 1000.0, 1)

        return MediaInspectionDTO(
            file_path=str(p),
            duration_sec=duration_sec,
            width=width,
            height=height,
            fps=fps,
            is_vfr=is_vfr,
            video_codec=video_codec,
            audio_codec=audio_codec,
            has_audio=has_audio,
            sample_rate=sample_rate,
            channels=channels,
            bitrate_kbps=bitrate_kbps,
        )
