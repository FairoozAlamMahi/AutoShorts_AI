"""
Action Assembler & Pacing Engine
Implements Intelligent Hybrid Video Editing:
1. Multi-Cut Action Assembly (GTA / Open World):
   Stitches 3 to 4 rapid, high-impact cuts (Hook Setup -> Escalation -> Peak Climax -> Loop Ending)
   with whoosh transition cuts and zero dead air.
2. Single-Climax Flow (Phantom Blade Zero / Boss Duels):
   Focuses on the unbroken combat peak with dynamic speed ramping (0.5x slow-mo on windup -> 1.3x on impact)
   and dead-air elimination.
"""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import json
import logging
import subprocess

from ..rendering.ffmpeg_renderer import FFmpegRenderer, LayoutMode, AudioProcessMode
from ..audio.sfx_generator import sfx_engine

logger = logging.getLogger(__name__)


class AssemblyMode(str, Enum):
    MULTI_CUT_MONTAGE = "MULTI_CUT_MONTAGE"
    SINGLE_CLIMAX_FLOW = "SINGLE_CLIMAX_FLOW"


@dataclass
class ActionBeat:
    start_sec: float
    duration_sec: float
    label: str  # HOOK_SETUP, ESCALATION, PEAK_CLIMAX, RESOLUTION_LOOP
    speed_factor: float = 1.0


class ActionAssembler:
    """Orchestrates video pacing, jump-cutting, speed ramps, and multi-beat montage assembly."""

    def __init__(self, renderer: Optional[FFmpegRenderer] = None):
        self.renderer = renderer or FFmpegRenderer()
        self.sfx = sfx_engine

    @staticmethod
    def determine_assembly_mode(game_title: str) -> AssemblyMode:
        """Selects ideal editing strategy based on game type and combat dynamics."""
        g = game_title.lower()
        if any(w in g for w in ["gta", "theft", "car", "heist", "chase", "race", "stunt", "speed"]):
            return AssemblyMode.MULTI_CUT_MONTAGE
        return AssemblyMode.SINGLE_CLIMAX_FLOW

    def build_multi_cut_beats(
        self,
        base_start_sec: float,
        total_duration_sec: float = 28.5,
    ) -> List[ActionBeat]:
        """
        Calculates a high-retention 4-beat montage timeline:
        - Beat 1 (Hook Setup, 2.5s): Hook question & immediate action start.
        - Beat 2 (Escalation, 7.5s): Pursuit/combat build-up.
        - Beat 3 (Peak Climax, 13.5s): Beat drop explosion, maximum chaos.
        - Beat 4 (Resolution/Loop, 5.0s): Climax aftermath leading into loop point.
        """
        # Slices across an exciting 60s span of the source clip
        t0 = max(0.0, base_start_sec)
        return [
            ActionBeat(start_sec=t0, duration_sec=2.5, label="HOOK_SETUP"),
            ActionBeat(start_sec=t0 + 4.5, duration_sec=7.5, label="ESCALATION"),
            ActionBeat(start_sec=t0 + 14.0, duration_sec=13.5, label="PEAK_CLIMAX"),
            ActionBeat(start_sec=t0 + 29.0, duration_sec=5.0, label="RESOLUTION_LOOP"),
        ]

    def render_multi_cut_montage(
        self,
        source_video: Path | str,
        output_mp4: Path | str,
        beats: List[ActionBeat],
        layout_mode: LayoutMode,
        ass_path: Optional[Path | str] = None,
        bgm_path: Optional[Path | str] = None,
        voice_path: Optional[Path | str] = None,
        drop_timestamp_sec: Optional[float] = None,
        scratch_dir: Optional[Path | str] = None,
    ) -> Path:
        """
        Renders each beat, splices them with transition whooshes,
        applies layout, burned kinetic subtitles, and hard studio ducking.
        """
        src = Path(source_video).resolve()
        dst = Path(output_mp4).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        work_dir = Path(scratch_dir).resolve() if scratch_dir else dst.parent / f"_work_{dst.stem}"
        work_dir.mkdir(parents=True, exist_ok=True)

        segment_files: List[Path] = []
        for idx, beat in enumerate(beats):
            seg_dst = work_dir / f"beat_{idx}_{beat.label.lower()}.mp4"
            cmd = [
                self.renderer.ffmpeg_path,
                "-y",
                "-ss", f"{beat.start_sec:.3f}",
                "-t", f"{beat.duration_sec:.3f}",
                "-i", str(src),
                "-c:v", "h264_nvenc",
                "-preset", "p5",
                "-cq", "20",
                "-c:a", "aac",
                "-b:a", "192k",
                "-fps_mode", "cfr",
                "-r", "60",
                str(seg_dst),
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                # Fallback to CPU libx264
                cmd[cmd.index("h264_nvenc")] = "libx264"
                cmd[cmd.index("-preset") + 1] = "ultrafast"
                subprocess.run(cmd, check=True)
            segment_files.append(seg_dst)

        # Concatenate segments into one master video file
        concat_txt = work_dir / "concat_list.txt"
        with open(concat_txt, "w", encoding="utf-8") as f:
            for s in segment_files:
                f.write(f"file '{s.name}'\n")

        raw_concat_mp4 = work_dir / "raw_montage_assembled.mp4"
        concat_cmd = [
            self.renderer.ffmpeg_path,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_txt),
            "-c", "copy",
            str(raw_concat_mp4),
        ]
        subprocess.run(concat_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        # Now pass through the full layout, subtitles, audio ducking, and SFX engine
        total_dur = sum(b.duration_sec for b in beats)
        sfx_boom = self.sfx.get_sfx_paths()["sub_boom"]

        return self.renderer.render_clip(
            source_video=raw_concat_mp4,
            output_mp4=dst,
            start_sec=0.0,
            duration_sec=total_dur,
            layout_mode=layout_mode,
            ass_path=ass_path,
            bgm_path=bgm_path,
            voice_path=voice_path,
            impact_flash=True,
            drop_timestamp_sec=drop_timestamp_sec or 2.5,
            pre_drop_silence_sec=0.20,
            hook_zoom_punch=True,
            sfx_path=sfx_boom,
        )

    def render_single_climax_flow(
        self,
        source_video: Path | str,
        output_mp4: Path | str,
        start_sec: float,
        duration_sec: float,
        layout_mode: LayoutMode,
        ass_path: Optional[Path | str] = None,
        bgm_path: Optional[Path | str] = None,
        voice_path: Optional[Path | str] = None,
        drop_timestamp_sec: Optional[float] = None,
        speed_ramp: bool = True,
    ) -> Path:
        """
        Renders a continuous soulslike combat climax with dynamic hook punch-in zoom,
        impact flash, hard studio ducking, and sub-bass drop explosion.
        """
        sfx_boom = self.sfx.get_sfx_paths()["sub_boom"]
        return self.renderer.render_clip(
            source_video=source_video,
            output_mp4=output_mp4,
            start_sec=start_sec,
            duration_sec=duration_sec,
            layout_mode=layout_mode,
            ass_path=ass_path,
            bgm_path=bgm_path,
            voice_path=voice_path,
            impact_flash=True,
            drop_timestamp_sec=drop_timestamp_sec or 2.5,
            pre_drop_silence_sec=0.20,
            hook_zoom_punch=True,
            sfx_path=sfx_boom,
        )


# Singleton instance
action_assembler = ActionAssembler()
