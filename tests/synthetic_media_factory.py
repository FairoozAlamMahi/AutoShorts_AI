"""Synthetic Media Factory - Generates real test MP4 videos via FFmpeg lavfi."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple


class SyntheticMediaFactory:
    """Generates deterministic synthetic media files for testing without external assets."""

    @staticmethod
    def _resolve_ffmpeg() -> str:
        which_path = shutil.which("ffmpeg")
        if which_path:
            return which_path

        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            winget_pkgs = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
            if winget_pkgs.exists():
                for bin_file in winget_pkgs.glob("**/ffmpeg.exe"):
                    return str(bin_file)

        return "ffmpeg"

    @classmethod
    def create_test_video(
        cls,
        output_path: Path | str,
        duration_sec: float = 5.0,
        width: int = 1920,
        height: int = 1080,
        fps: int = 60,
        has_audio: bool = True,
        audio_tone_hz: int = 440,
        planted_spikes: Optional[List[Tuple[float, float]]] = None,
    ) -> Path:
        """
        Generates a 1080p60 test MP4 video with lavfi testsrc and sine audio.
        planted_spikes: Optional list of (start_sec, end_sec) ranges where audio volume spikes.
        """
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg_bin = cls._resolve_ffmpeg()

        video_filter = f"testsrc=size={width}x{height}:rate={fps}"

        cmd = [
            ffmpeg_bin,
            "-y",
            "-f", "lavfi",
            "-i", video_filter,
        ]

        if has_audio:
            if planted_spikes:
                # Base tone 440Hz + volume spikes at planted windows
                volume_expr = "1.0"
                for s_start, s_end in planted_spikes:
                    volume_expr = f"if(between(t,{s_start},{s_end}),10.0,{volume_expr})"
                audio_filter = f"sine=frequency={audio_tone_hz}:sample_rate=44100,volume=eval=frame:volume='{volume_expr}'"
            else:
                audio_filter = f"sine=frequency={audio_tone_hz}:sample_rate=44100"

            cmd.extend([
                "-f", "lavfi",
                "-i", audio_filter,
                "-c:a", "aac",
                "-b:a", "128k",
            ])
        else:
            cmd.append("-an")

        cmd.extend([
            "-t", str(duration_sec),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            str(out)
        ])

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg failed to create synthetic video: {res.stderr}")

        return out

    @classmethod
    def create_silent_video(
        cls,
        output_path: Path | str,
        duration_sec: float = 3.0,
        width: int = 1920,
        height: int = 1080,
        fps: int = 60,
    ) -> Path:
        """Generates video with strictly zero audio tracks."""
        return cls.create_test_video(
            output_path=output_path,
            duration_sec=duration_sec,
            width=width,
            height=height,
            fps=fps,
            has_audio=False,
        )

    @classmethod
    def create_vfr_video(cls, output_path: Path | str, duration_sec: float = 20.0) -> Path:
        """Generates a Variable Frame Rate (VFR) test video."""
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg_bin = cls._resolve_ffmpeg()

        cmd = [
            ffmpeg_bin,
            "-y",
            "-f", "lavfi",
            "-i", "testsrc=size=640x360:rate=30",
            "-t", str(duration_sec),
            "-vf", "mpdecimate",
            "-fps_mode", "vfr",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-an",
            str(out)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg failed to create VFR video: {res.stderr}")
        return out

    @classmethod
    def create_corrupt_file(cls, output_path: Path | str) -> Path:
        """Generates a corrupt / non-media file for testing error resilience."""
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"CORRUPT_NOT_A_VALID_MP4_HEADER_OR_DATA\x00\xff\x00\xaa" * 10)
        return out
