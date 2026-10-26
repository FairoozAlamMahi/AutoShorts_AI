"""FFmpeg single-pass renderer supporting NVENC hardware encoding with CPU fallback."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
from .layout_builder import LayoutBuilder
from ..config.schema import LayoutMode, AudioProcessMode, FacecamPosition
from ..ingest.media_inspector import MediaInspector


class FFmpegRenderer:
    """Renders finished Shorts using NVENC hardware acceleration with CPU fallback."""

    def __init__(self, ffmpeg_path: Optional[str] = None, fonts_dir: Optional[Path | str] = None) -> None:
        self.ffmpeg_path = ffmpeg_path or self._resolve_ffmpeg()
        self.fonts_dir = Path(fonts_dir).resolve() if fonts_dir else Path("assets/fonts").resolve()
        self.inspector = MediaInspector()

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

    def render_clip(
        self,
        source_video: Path | str,
        output_mp4: Path | str,
        start_sec: float,
        duration_sec: float,
        layout_mode: LayoutMode = LayoutMode.LAYOUT_HYBRID_CINEMA_STACK,
        ass_path: Optional[Path | str] = None,
        audio_mode: AudioProcessMode = AudioProcessMode.LOUDNORM_EBU_R128,
        prefer_nvenc: bool = True,
        facecam_pos: FacecamPosition = FacecamPosition.TOP_LEFT,
        bgm_path: Optional[Path | str] = None,
        bgm_volume_duck_db: float = -18.0,
    ) -> Path:
        """
        Renders a single Short with layout framing, optional .ass subtitle burn-in,
        optional background music auto-ducking, and audio normalization.
        Attempts NVENC first, automatically falling back to libx264.
        """
        src = Path(source_video).resolve()
        dst = Path(output_mp4).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Inspect source media to verify audio presence
        inspection = self.inspector.inspect(src)
        has_audio = inspection.has_audio

        filtergraph = LayoutBuilder.build_filtergraph(
            layout_mode=layout_mode,
            ass_path=ass_path,
            fonts_dir=self.fonts_dir if self.fonts_dir.exists() else None,
            facecam_pos=facecam_pos,
        )

        has_bgm = bgm_path is not None and Path(bgm_path).exists()
        duck_vol = "0.20" if bgm_volume_duck_db <= -14.0 else "0.35"

        if has_bgm and has_audio:
            if audio_mode == AudioProcessMode.LOUDNORM_EBU_R128:
                combined_filter = f"{filtergraph};[1:a]volume={duck_vol}[bgm_duck];[0:a:0?][bgm_duck]amix=inputs=2:duration=first,loudnorm=I=-14:LRA=7:TP=-1.5[aout]"
            else:
                combined_filter = f"{filtergraph};[1:a]volume={duck_vol}[bgm_duck];[0:a:0?][bgm_duck]amix=inputs=2:duration=first[aout]"
        elif has_bgm and not has_audio:
            combined_filter = f"{filtergraph};[1:a]volume=0.35[aout]"
        else:
            combined_filter = filtergraph

        def _build_command(encoder: str) -> List[str]:
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-ss", f"{start_sec:.3f}",
                "-t", f"{duration_sec:.3f}",
                "-i", str(src),
            ]

            if has_bgm:
                cmd.extend(["-stream_loop", "-1", "-i", str(Path(bgm_path).resolve())])

            # Video filter
            cmd.extend([
                "-filter_complex", combined_filter,
                "-map", "[vout]",
            ])

            # Audio routing & auto-ducking
            if has_bgm:
                cmd.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"])
            else:
                if has_audio:
                    cmd.extend(["-map", "0:a:0?"])
                    if audio_mode == AudioProcessMode.LOUDNORM_EBU_R128:
                        cmd.extend(["-af", "loudnorm=I=-14:LRA=7:TP=-1.5", "-c:a", "aac", "-b:a", "192k"])
                    else:
                        cmd.extend(["-c:a", "aac", "-b:a", "192k"])
                else:
                    cmd.append("-an")

            # Video encoder settings
            if encoder == "h264_nvenc":
                cmd.extend([
                    "-c:v", "h264_nvenc",
                    "-preset", "p5",
                    "-rc", "vbr",
                    "-cq", "20",
                    "-pix_fmt", "yuv420p",
                ])
            else:
                cmd.extend([
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-crf", "20",
                    "-pix_fmt", "yuv420p",
                ])

            # Enforce constant 60 FPS
            cmd.extend([
                "-fps_mode", "cfr",
                "-r", "60",
                str(dst)
            ])
            return cmd

        # Try NVENC first if requested
        if prefer_nvenc:
            cmd_nvenc = _build_command("h264_nvenc")
            res = subprocess.run(cmd_nvenc, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False)
            if res.returncode == 0:
                return dst

        # Fallback to libx264 CPU encoder
        cmd_cpu = _build_command("libx264")
        res_cpu = subprocess.run(cmd_cpu, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False)
        if res_cpu.returncode != 0:
            raise RuntimeError(f"FFmpeg rendering failed: {res_cpu.stderr}")

        return dst

    def generate_thumbnail(
        self,
        video_path: Path | str,
        output_jpg: Path | str,
        timestamp_sec: Optional[float] = None,
    ) -> Path:
        """Extracts a high-quality 1080x1920 cover image from the short."""
        v = Path(video_path).resolve()
        out = Path(output_jpg).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        t = max(0.5, float(timestamp_sec if timestamp_sec is not None else 1.0))
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-ss", f"{t:.2f}",
            "-i", str(v),
            "-vframes", "1",
            "-q:v", "2",
            str(out)
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, shell=False)
        return out

    def rerender_single_clip(
        self,
        source_video: Path | str,
        output_mp4: Path | str,
        start_sec: float,
        duration_sec: float,
        layout_mode: LayoutMode,
        ass_path: Optional[Path | str] = None,
        audio_mode: AudioProcessMode = AudioProcessMode.LOUDNORM_EBU_R128,
        facecam_pos: FacecamPosition = FacecamPosition.TOP_LEFT,
        bgm_path: Optional[Path | str] = None,
    ) -> Path:
        """Fast ~10s re-render without re-running earlier pipeline stages."""
        rendered = self.render_clip(
            source_video=source_video,
            output_mp4=output_mp4,
            start_sec=start_sec,
            duration_sec=duration_sec,
            layout_mode=layout_mode,
            ass_path=ass_path,
            audio_mode=audio_mode,
            facecam_pos=facecam_pos,
            bgm_path=bgm_path,
        )
        # Update thumbnail alongside re-rendered clip
        thumb_path = Path(output_mp4).with_suffix(".thumb.jpg")
        self.generate_thumbnail(rendered, thumb_path, timestamp_sec=min(2.0, duration_sec * 0.5))
        return rendered
