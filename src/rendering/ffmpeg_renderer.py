"""FFmpeg single-pass renderer supporting NVENC hardware encoding with CPU fallback."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging
from .layout_builder import LayoutBuilder
from .thumbnail_maker import thumbnail_maker, BadgeStyle
from ..audio.music_transition_engine import music_transition_engine
from ..config.schema import LayoutMode, AudioProcessMode, FacecamPosition
from ..ingest.media_inspector import MediaInspector

logger = logging.getLogger("FFmpegRenderer")


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
        cutscene_intervals: Optional[List[Tuple[float, float]]] = None,
        voice_path: Optional[Path | str] = None,
        impact_flash: bool = False,
        flash_timestamp_sec: Optional[float] = None,
        pre_drop_silence_sec: float = 0.0,
        drop_timestamp_sec: Optional[float] = None,
        hook_zoom_punch: bool = False,
        sfx_path: Optional[Path | str] = None,
    ) -> Path:
        """
        Renders a single Short with layout framing, optional .ass subtitle burn-in,
        optional neural voiceover, hard studio ducking, impact flash, dynamic hook zoom, and audio normalization.
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
            cutscene_intervals=cutscene_intervals,
            hook_zoom_punch=hook_zoom_punch,
        )

        # Impact flash (2-frame white strobe on beat drop or clutch hit)
        if impact_flash:
            flash_t = flash_timestamp_sec if flash_timestamp_sec is not None else (drop_timestamp_sec if drop_timestamp_sec is not None else 2.5)
            flash_t = max(0.1, min(flash_t, duration_sec - 0.2))
            filtergraph = f"{filtergraph};[vout]drawbox=x=0:y=0:w=1080:h=1920:color=white@0.85:t=fill:enable='between(t,{flash_t:.3f},{flash_t + 0.05:.3f})'[vout_flash]"
            final_video_label = "[vout_flash]"
        else:
            final_video_label = "[vout]"

        has_bgm = bgm_path is not None and Path(bgm_path).exists()
        has_voice = voice_path is not None and Path(voice_path).exists()
        has_sfx = sfx_path is not None and Path(sfx_path).exists()

        extra_inputs: List[str] = []
        current_idx = 1
        bgm_idx = None
        voice_idx = None
        sfx_idx = None

        if has_bgm:
            extra_inputs.extend(["-stream_loop", "-1", "-i", str(Path(bgm_path).resolve())])
            bgm_idx = current_idx
            current_idx += 1

        if has_voice:
            extra_inputs.extend(["-i", str(Path(voice_path).resolve())])
            voice_idx = current_idx
            current_idx += 1

        if has_sfx:
            extra_inputs.extend(["-i", str(Path(sfx_path).resolve())])
            sfx_idx = current_idx
            current_idx += 1

        # Detect voiceover duration for precise hard studio ducking
        vo_dur = 0.0
        if has_voice:
            try:
                import wave
                with wave.open(str(Path(voice_path).resolve()), "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    vo_dur = frames / float(rate) if rate > 0 else 3.5
            except Exception:
                vo_dur = 3.5

        # Construct hard studio ducking audio mixing graph
        audio_filters: List[str] = []
        has_aout = False

        if has_bgm or has_voice or has_sfx:
            drop_ts = drop_timestamp_sec if drop_timestamp_sec is not None else (vo_dur if vo_dur > 0.1 else 2.5)
            game_label = "[0:a:0?]"

            filt_lines, sfx_inputs, mix_inputs = music_transition_engine.build_transition_audio_filtergraph(
                has_game_audio=has_audio,
                game_audio_label=game_label,
                bgm_input_index=bgm_idx if has_bgm else None,
                voice_input_index=voice_idx if has_voice else None,
                vo_duration_sec=vo_dur,
                drop_timestamp_sec=drop_ts,
                pre_drop_silence_sec=pre_drop_silence_sec,
                enable_lowpass_buildup=True,
                enable_riser_buildup=True,
                enable_dual_impact=True,
                next_input_index=current_idx,
            )
            for sfx_p in sfx_inputs:
                extra_inputs.extend(["-i", str(sfx_p)])
                current_idx += 1
            audio_filters.extend(filt_lines)

            # 5. Master mixing with normalize=0 to preserve hard ducking dynamics
            if len(mix_inputs) > 1:
                mix_chain = f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0:normalize=0"
                if audio_mode == AudioProcessMode.LOUDNORM_EBU_R128:
                    mix_chain += ",loudnorm=I=-14:LRA=7:TP=-1.5"
                audio_filters.append(f"{mix_chain}[aout]")
                has_aout = True
            elif len(mix_inputs) == 1:
                single_chain = mix_inputs[0]
                filter_ops = []
                if audio_mode == AudioProcessMode.LOUDNORM_EBU_R128:
                    filter_ops.append("loudnorm=I=-14:LRA=7:TP=-1.5")
                else:
                    filter_ops.append("anull")
                audio_filters.append(f"{single_chain}{','.join(filter_ops)}[aout]")
                has_aout = True

        if audio_filters:
            combined_filter = f"{filtergraph};{';'.join(audio_filters)}"
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
            cmd.extend(extra_inputs)
            cmd.extend([
                "-filter_complex", combined_filter,
                "-map", final_video_label,
            ])

            if has_aout:
                cmd.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"])
            else:
                if has_audio and not extra_inputs:
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

    def generate_multi_thumbnails(
        self,
        video_path: Path | str,
        output_dir: Optional[Path | str] = None,
        duration_sec: Optional[float] = None,
        hook_overlay_text: Optional[str] = None,
        source_video: Optional[Path | str] = None,
        start_sec: float = 0.0,
        badge_style: BadgeStyle = BadgeStyle.MRBEAST_YELLOW,
    ) -> Dict[str, Path]:
        """
        Generates 3 multi-candidate cover thumbnails (thumb_A, thumb_B, thumb_C) for A/B testing:
        - thumb_A.jpg: High-contrast 3-word viral badge (MrBeast Yellow / Cyan / Red)
        - thumb_B.jpg: Curiosity / stakes callout badge
        - thumb_C.jpg: Clean AMOLED graded action freeze-frame (no text)
        - thumb.jpg: Primary thumbnail (defaults to Variant A)
        - <clip_stem>.thumbnails.json: Candidate metadata sidecar.
        """
        v = Path(video_path).resolve()
        parent_dir = Path(output_dir).resolve() if output_dir else v.parent
        parent_dir.mkdir(parents=True, exist_ok=True)
        stem = v.stem

        dur = duration_sec
        if dur is None:
            try:
                info = self.inspector.inspect(v)
                dur = info.duration_sec
            except Exception:
                dur = 30.0

        # When hook_overlay_text is provided, use the high-CTR viral packaging suite
        if hook_overlay_text:
            try:
                # Prefer source video if available for clean non-subtitled frames
                clean_src = Path(source_video).resolve() if source_video and Path(source_video).exists() else v
                clean_start = start_sec if (source_video and Path(source_video).exists()) else 0.0
                return thumbnail_maker.generate_packaging_suite(
                    source_video=clean_src,
                    output_dir=parent_dir,
                    clip_id=stem,
                    start_sec=clean_start,
                    duration_sec=dur,
                    hook_overlay_text=hook_overlay_text,
                    style=badge_style,
                )
            except Exception as e:
                logger.warning(f"Thumbnail packaging suite error: {e}")

        ts_a = max(0.5, dur * 0.15)
        ts_b = max(1.0, dur * 0.50)
        ts_c = max(1.5, dur * 0.85)

        p_a = parent_dir / f"{stem}.thumb_A.jpg"
        p_b = parent_dir / f"{stem}.thumb_B.jpg"
        p_c = parent_dir / f"{stem}.thumb_C.jpg"
        p_main = parent_dir / f"{stem}.thumb.jpg"

        self.generate_thumbnail(v, p_a, timestamp_sec=ts_a)
        self.generate_thumbnail(v, p_b, timestamp_sec=ts_b)
        self.generate_thumbnail(v, p_c, timestamp_sec=ts_c)

        if not p_main.exists() and p_a.exists():
            import shutil
            shutil.copyfile(p_a, p_main)

        meta_p = parent_dir / f"{stem}.thumbnails.json"
        meta_data = {
            "clip": stem,
            "candidates": {
                "thumb_A": {"path": str(p_a), "timestamp_sec": round(ts_a, 2), "label": "Hook Frame"},
                "thumb_B": {"path": str(p_b), "timestamp_sec": round(ts_b, 2), "label": "Climax Action"},
                "thumb_C": {"path": str(p_c), "timestamp_sec": round(ts_c, 2), "label": "Payoff Frame"},
            },
            "selected": "thumb_A",
            "hook_text": hook_overlay_text or "",
        }
        meta_p.write_text(json.dumps(meta_data, indent=2), encoding="utf-8")
        return {"A": p_a, "B": p_b, "C": p_c, "main": p_main}

        return {"A": p_a, "B": p_b, "C": p_c, "main": p_main}

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
        cutscene_intervals: Optional[List[Tuple[float, float]]] = None,
        voice_path: Optional[Path | str] = None,
        impact_flash: bool = False,
        flash_timestamp_sec: Optional[float] = None,
        pre_drop_silence_sec: float = 0.0,
        drop_timestamp_sec: Optional[float] = None,
        hook_zoom_punch: bool = False,
        sfx_path: Optional[Path | str] = None,
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
            cutscene_intervals=cutscene_intervals,
            voice_path=voice_path,
            impact_flash=impact_flash,
            flash_timestamp_sec=flash_timestamp_sec,
            pre_drop_silence_sec=pre_drop_silence_sec,
            drop_timestamp_sec=drop_timestamp_sec,
            hook_zoom_punch=hook_zoom_punch,
            sfx_path=sfx_path,
        )
        # Update thumbnail alongside re-rendered clip
        thumb_path = Path(output_mp4).with_suffix(".thumb.jpg")
        self.generate_thumbnail(rendered, thumb_path, timestamp_sec=min(2.0, duration_sec * 0.5))
        return rendered
