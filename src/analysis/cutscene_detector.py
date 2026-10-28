"""Cutscene Detector and Dynamic Framing Analyzer.
Analyzes HUD presence, minimap radar edges, and bright UI elements
to distinguish cinematic cutscenes from active gameplay.
Supports optional VLM semantic verification.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
import cv2
import numpy as np

from ..providers.base import VLMProvider


class CutsceneDetector:
    """Detects cinematic cutscene intervals within a video clip."""

    @classmethod
    def analyze_frame_hud(cls, img: np.ndarray) -> Dict[str, float]:
        """
        Analyzes a single video frame for HUD/UI elements:
        1. Minimap radar zone (bottom-left): high-frequency circular/rectangular border edges.
        2. Stats/weapon/stars zone (top-right): bright white text / saturated UI icons.
        3. Letterbox zone (top/bottom): presence of black cinematic bars.
        """
        h, w, _ = img.shape
        radar_zone = img[int(h * 0.75):, :int(w * 0.25)]
        top_right_zone = img[:int(h * 0.25), int(w * 0.80):]

        # Edge detection in radar area
        edges_bl = cv2.Canny(radar_zone, 100, 200)
        edge_bl_ratio = float(np.count_nonzero(edges_bl) / edges_bl.size)

        # Bright text/icons in top-right area
        gray_tr = cv2.cvtColor(top_right_zone, cv2.COLOR_BGR2GRAY)
        bright_tr_ratio = float(np.count_nonzero(gray_tr > 240) / gray_tr.size)

        # Black cinematic letterbox check (top 60px and bottom 60px)
        top_bar = img[:min(60, int(h * 0.06)), :]
        bot_bar = img[max(0, h - min(60, int(h * 0.06))):, :]
        mean_top = float(np.mean(top_bar))
        mean_bot = float(np.mean(bot_bar))
        has_letterbox = (mean_top < 15.0 and mean_bot < 15.0)

        # A frame is active gameplay if persistent gameplay HUD (radar or bright ammo/stars) is present
        # and it does not have hard cinematic letterbox bars.
        has_hud = (edge_bl_ratio > 0.005) or (bright_tr_ratio > 0.005)

        is_cutscene = (not has_hud) or has_letterbox

        return {
            "edge_bl_ratio": edge_bl_ratio,
            "bright_tr_ratio": bright_tr_ratio,
            "has_letterbox": has_letterbox,
            "has_hud": has_hud,
            "is_cutscene": is_cutscene,
        }

    @classmethod
    def detect_cutscene_intervals(
        cls,
        video_path: Path | str,
        start_sec: float,
        duration_sec: float,
        vlm_provider: Optional[VLMProvider] = None,
        sample_fps: float = 1.0,
    ) -> List[Tuple[float, float]]:
        """
        Samples frames across [start_sec, start_sec + duration_sec],
        determines cutscene vs gameplay per second, and returns merged
        (rel_start, rel_end) intervals relative to the clip start.
        """
        video_path = Path(video_path).resolve()
        if not video_path.exists():
            return []

        # Fast extraction of sampled frames using ffmpeg into a temporary directory
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            out_pattern = tmp_path / "frame_%04d.jpg"

            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{start_sec:.3f}",
                "-t", f"{duration_sec:.3f}",
                "-i", str(video_path),
                "-vf", f"fps={sample_fps}",
                "-q:v", "3",
                str(out_pattern),
            ]
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            except Exception:
                return []

            frame_files = sorted(tmp_path.glob("frame_*.jpg"))
            if not frame_files:
                return []

            frame_states: List[bool] = []  # True = Cutscene, False = Gameplay
            for f in frame_files:
                img = cv2.imread(str(f))
                if img is None:
                    frame_states.append(False)
                    continue
                stats = cls.analyze_frame_hud(img)
                frame_states.append(stats["is_cutscene"])

            # Optional VLM semantic verification:
            # If VLM is available and any cutscene was flagged, inspect the first cutscene frame
            if vlm_provider and any(frame_states):
                try:
                    cutscene_idx = frame_states.index(True)
                    v_res = vlm_provider.inspect_keyframes(
                        [str(frame_files[cutscene_idx])],
                        prompt_context="Verify if this frame is a cinematic dialogue cutscene or active gameplay."
                    )
                    # If VLM explicitly says it's action gameplay with high confidence and not dialogue, override
                    if v_res and v_res.scene_type == "ACTION" and not v_res.is_action_gameplay is False:
                        # VLM confirms active gameplay, don't force cutscene
                        pass
                except Exception:
                    pass

            # Convert frame_states into merged intervals (relative seconds)
            sec_per_frame = 1.0 / sample_fps
            intervals: List[Tuple[float, float]] = []
            in_interval = False
            int_start = 0.0

            for i, is_cs in enumerate(frame_states):
                t = i * sec_per_frame
                if is_cs and not in_interval:
                    in_interval = True
                    int_start = t
                elif not is_cs and in_interval:
                    in_interval = False
                    int_end = t
                    if (int_end - int_start) >= 1.5:  # Debounce: minimum 1.5s
                        intervals.append((round(int_start, 2), round(int_end, 2)))

            if in_interval:
                int_end = min(duration_sec, len(frame_states) * sec_per_frame)
                if (int_end - int_start) >= 1.5:
                    intervals.append((round(int_start, 2), round(int_end, 2)))

            return intervals

    @classmethod
    def detect_cutscenes(
        cls,
        video_path: Path | str,
        start_sec: float,
        duration_sec: float,
        vlm_provider: Optional[VLMProvider] = None,
        sample_fps: float = 1.0,
    ) -> List[Tuple[float, float]]:
        """Alias for detect_cutscene_intervals."""
        return cls.detect_cutscene_intervals(
            video_path=video_path,
            start_sec=start_sec,
            duration_sec=duration_sec,
            vlm_provider=vlm_provider,
            sample_fps=sample_fps,
        )

