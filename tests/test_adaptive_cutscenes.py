"""Test suite for Adaptive Cutscene Detector and Dynamic 4:3 to 9:16 Layout Transitions."""
import pytest
import numpy as np
from pathlib import Path

from src.analysis.cutscene_detector import CutsceneDetector
from src.rendering.layout_builder import LayoutBuilder
from src.config.schema import LayoutMode, PreRunToggles
from src.rendering.ffmpeg_renderer import FFmpegRenderer


def test_cutscene_detector_synthetic_frames():
    """Verifies that synthetic HUD vs cinematic frames are accurately distinguished."""
    # 1. Simulate cinematic cutscene frame (cinematic character framing, zero HUD, dark edges)
    cutscene_img = np.full((1080, 1920, 3), 40, dtype=np.uint8)
    # Add some soft gradient / face-like variation
    cutscene_img[300:700, 800:1200] = 120
    stats_cs = CutsceneDetector.analyze_frame_hud(cutscene_img)
    assert stats_cs["is_cutscene"] is True
    assert stats_cs["has_hud"] is False

    # 2. Simulate active gameplay frame with minimap radar in bottom-left and bright ammo text in top-right
    gameplay_img = cutscene_img.copy()
    # Draw high-contrast radar border ring in bottom-left (y: 800-1000, x: 50-250)
    import cv2
    cv2.circle(gameplay_img, (150, 950), 80, (255, 255, 255), 4)
    # Draw bright white text in top-right (ammo counter)
    cv2.putText(gameplay_img, "40 300", (1600, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)

    stats_gp = CutsceneDetector.analyze_frame_hud(gameplay_img)
    assert stats_gp["has_hud"] is True
    assert stats_gp["is_cutscene"] is False


def test_layout_builder_dynamic_cutscene_filtergraph():
    """Verifies LayoutBuilder creates dynamic enable='between(t,...)' filtergraphs for Layout B."""
    # Case 1: Standard Layout B without cutscene intervals
    fg_standard = LayoutBuilder.build_filtergraph(
        layout_mode=LayoutMode.LAYOUT_B_CENTER_CROP,
        cutscene_intervals=None,
    )
    assert "between(t" not in fg_standard
    assert "crop=ih*9/16" in fg_standard

    # Case 2: Dynamic cutscene adaptation
    intervals = [(0.0, 12.5), (20.0, 25.0)]
    fg_dynamic = LayoutBuilder.build_filtergraph(
        layout_mode=LayoutMode.LAYOUT_B_CENTER_CROP,
        cutscene_intervals=intervals,
    )
    assert "between(t,0.00,12.50)" in fg_dynamic
    assert "between(t,20.00,25.00)" in fg_dynamic
    assert "boxblur" in fg_dynamic
    assert "c43" in fg_dynamic
    assert "zoom" in fg_dynamic


def test_ffmpeg_dynamic_adaptive_cutscene_render(tmp_path):
    """Renders a dynamic 4-second Short switching from 4:3 cutscene to 9:16 zoom crop."""
    # Create synthetic test video
    src_video = tmp_path / "test_src.mp4"
    import subprocess
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=30",
        "-t", "3",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(src_video)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    renderer = FFmpegRenderer()
    out_mp4 = tmp_path / "test_out.mp4"

    # Render with cutscene interval for first 1.5s
    rendered = renderer.render_clip(
        source_video=src_video,
        output_mp4=out_mp4,
        start_sec=0.0,
        duration_sec=3.0,
        layout_mode=LayoutMode.LAYOUT_B_CENTER_CROP,
        cutscene_intervals=[(0.0, 1.5)],
    )

    assert rendered.exists()
    assert rendered.stat().st_size > 1000


def test_prerun_toggles_smart_cutscene_default():
    """Verifies that smart_cutscene_framing toggle defaults to True and can be disabled."""
    toggles = PreRunToggles()
    assert toggles.smart_cutscene_framing is True

    toggles_disabled = PreRunToggles(smart_cutscene_framing=False)
    assert toggles_disabled.smart_cutscene_framing is False
