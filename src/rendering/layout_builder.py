"""Layout builder generating optimized FFmpeg filtergraphs for the 4 layout modes."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, List, Tuple
from ..config.schema import LayoutMode, FacecamPosition


class LayoutBuilder:
    """Builds FFmpeg filtergraphs for Cinema Stack, Blur Fit, Center Crop, Raw 16:9, Facecam Split, and 4:3 Modes."""

    @staticmethod
    def get_dimensions(layout_mode: LayoutMode) -> tuple[int, int]:
        """Returns the target (width, height) resolution for a given LayoutMode."""
        if layout_mode in (LayoutMode.LAYOUT_4_3_BLUR_FIT, LayoutMode.LAYOUT_4_3_HORIZONTAL):
            return 1440, 1080
        elif layout_mode == LayoutMode.LAYOUT_RAW_16_9:
            return 1920, 1080
        else:
            return 1080, 1920

    @staticmethod
    def escape_filter_path(path: Path | str) -> str:
        """
        Escapes Windows path for FFmpeg filter arguments:
        Replaces backslashes with forward slashes and escapes the drive colon (e.g., C\\:/path).
        """
        p_str = str(Path(path).resolve()).replace("\\", "/")
        return p_str.replace(":", r"\:")

    @classmethod
    def build_filtergraph(
        cls,
        layout_mode: LayoutMode,
        ass_path: Optional[Path | str] = None,
        fonts_dir: Optional[Path | str] = None,
        facecam_pos: FacecamPosition = FacecamPosition.TOP_LEFT,
        cutscene_intervals: Optional[List[Tuple[float, float]]] = None,
    ) -> str:
        """
        Generates the complete -filter_complex string.
        Output label is always [vout].
        Supports dynamic cutscene framing adaptation when cutscene_intervals is passed.
        """
        filters = []

        if layout_mode == LayoutMode.LAYOUT_HYBRID_CINEMA_STACK:
            # 1. Background: Blurred, 12% darkened 1080x1920
            filters.append(
                "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:2,eq=brightness=-0.12[bg]"
            )
            # 2. Foreground: Center 4:3 action zone scaled to 1080x1280
            filters.append(
                "[0:v]crop=ih*4/3:ih:(iw-ow)/2:0,scale=1080:1280:flags=lanczos[fg]"
            )
            # 3. Overlay foreground centered vertically at y=320 (leaving 320px top and bottom)
            filters.append("[bg][fg]overlay=(W-w)/2:320[v_comp]")

        elif layout_mode == LayoutMode.LAYOUT_A_BLUR_FIT:
            # 1. Background: Blurred, 12% darkened 1080x1920
            filters.append(
                "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:2,eq=brightness=-0.12[bg]"
            )
            # 2. Foreground: 100% widescreen fit scaled to 1080x608
            filters.append("[0:v]scale=1080:608:flags=lanczos[fg]")
            # 3. Centered overlay
            filters.append("[bg][fg]overlay=(W-w)/2:(H-h)/2[v_comp]")

        elif layout_mode == LayoutMode.LAYOUT_B_CENTER_CROP:
            if cutscene_intervals:
                # Dynamic cutscene adaptation:
                # 1. Background: Blurred, 12% darkened 1080x1920
                filters.append(
                    "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:2,eq=brightness=-0.12[bg]"
                )
                # 2. Cutscene foreground 4:3 fit scaled to 1080x1440
                filters.append(
                    "[0:v]crop=ih*4/3:ih:(iw-ow)/2:0,scale=1080:1440:flags=lanczos[fg]"
                )
                # 3. Cutscene composite: 4:3 centered over blurred background
                filters.append("[bg][fg]overlay=(W-w)/2:(H-h)/2[c43]")

                # 4. Standard 9:16 center crop zoom
                filters.append(
                    "[0:v]crop=ih*9/16:ih:(iw-ow)/2:0,scale=1080:1920:flags=lanczos[zoom]"
                )

                # 5. Dynamic overlay: c43 enabled only during cutscene intervals; reverts instantly to zoom during gameplay
                enable_cond = "+".join(f"between(t,{start:.2f},{end:.2f})" for start, end in cutscene_intervals)
                filters.append(f"[zoom][c43]overlay=0:0:enable='{enable_cond}'[v_comp]")
            else:
                # Full-screen 9:16 vertical crop
                filters.append(
                    "[0:v]crop=ih*9/16:ih:(iw-ow)/2:0,scale=1080:1920:flags=lanczos[v_comp]"
                )

        elif layout_mode == LayoutMode.LAYOUT_RAW_16_9:
            # Standard horizontal 16:9 trim (1920x1080)
            filters.append("[0:v]scale=1920:1080:flags=lanczos[v_comp]")

        elif layout_mode == LayoutMode.LAYOUT_FACECAM_SPLIT:
            # Facecam corner crop
            if facecam_pos == FacecamPosition.TOP_LEFT:
                x_pos, y_pos = "0", "0"
            elif facecam_pos == FacecamPosition.TOP_RIGHT:
                x_pos, y_pos = "iw-ow", "0"
            elif facecam_pos == FacecamPosition.BOTTOM_LEFT:
                x_pos, y_pos = "0", "ih-oh"
            else:  # BOTTOM_RIGHT
                x_pos, y_pos = "iw-ow", "ih-oh"

            # Top: Streamer facecam scaled to 1080x720
            filters.append(f"[0:v]crop=iw*0.30:ih*0.35:{x_pos}:{y_pos},scale=1080:720:flags=lanczos[cam]")
            # Bottom: Center gameplay action scaled to 1080x1200
            filters.append("[0:v]crop=ih*9/16*1.1:ih*0.9:(iw-ow)/2:ih*0.05,scale=1080:1200:flags=lanczos[game]")
            # Stack top (cam) and bottom (game) into 1080x1920
            filters.append("[cam][game]vstack=inputs=2[v_comp]")

        elif layout_mode == LayoutMode.LAYOUT_4_3_BLUR_FIT:
            # 1. Background: Blurred, 12% darkened 1440x1080
            filters.append(
                "[0:v]scale=1440:1080:force_original_aspect_ratio=increase,crop=1440:1080,boxblur=28:2,eq=brightness=-0.12[bg]"
            )
            # 2. Foreground: 100% widescreen fit scaled to 1440x810 (shows 100% full screen action)
            filters.append("[0:v]scale=1440:810:flags=lanczos[fg]")
            # 3. Centered overlay (leaving 135px blurred bars top & bottom)
            filters.append("[bg][fg]overlay=(W-w)/2:(H-h)/2[v_comp]")

        elif layout_mode == LayoutMode.LAYOUT_4_3_HORIZONTAL:
            # Full 4:3 Center Crop (1440x1080) showing 75% widescreen with zero bars
            filters.append(
                "[0:v]crop=ih*4/3:ih:(iw-ow)/2:0,scale=1440:1080:flags=lanczos[v_comp]"
            )

        else:
            raise ValueError(f"Unknown layout mode: {layout_mode}")

        # Subtitle burning via libass
        if ass_path and Path(ass_path).exists():
            clean_ass = cls.escape_filter_path(ass_path)
            if fonts_dir and Path(fonts_dir).exists():
                clean_fonts = cls.escape_filter_path(fonts_dir)
                filters.append(f"[v_comp]ass='{clean_ass}':fontsdir='{clean_fonts}'[vout]")
            else:
                filters.append(f"[v_comp]ass='{clean_ass}'[vout]")
        else:
            filters.append("[v_comp]null[vout]")

        return ";".join(filters)
