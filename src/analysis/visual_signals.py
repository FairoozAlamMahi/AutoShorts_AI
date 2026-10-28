"""Visual signal analysis: 2 FPS 360p pipe, crosshair motion, HUD activity, and pause penalty."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional
import cv2
import numpy as np


class VisualSignalAnalyzer:
    """Extracts gameplay motion and HUD action from a 2 FPS 360p FFmpeg stream."""

    def __init__(self, ffmpeg_path: Optional[str] = None) -> None:
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

    def analyze_video_timeline(
        self,
        video_path: Path | str,
        total_duration_sec: float,
    ) -> np.ndarray:
        """
        Pipes 2 FPS 640x360 frames from FFmpeg and calculates visual excitement on a 1-second grid.
        - Center 50% crosshair action weighted 2.0x
        - Outer ring (HUD) weighted 1.0x
        - Static menu penalty applied when motion < threshold
        """
        grid_len = max(1, int(np.ceil(total_duration_sec)))
        v_path = Path(video_path).resolve()
        if not v_path.exists() or v_path.stat().st_size == 0:
            return np.zeros(grid_len, dtype=np.float32)

        width = 640
        height = 360
        frame_bytes = width * height * 3  # bgr24
        fps = 2

        cmd = [
            self.ffmpeg_path,
            "-hwaccel", "auto",
            "-v", "error",
            "-i", str(v_path),
            "-vf", f"fps={fps},scale={width}:{height}",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "pipe:1"
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
            bufsize=frame_bytes * 10
        )

        prev_gray: Optional[np.ndarray] = None
        frame_idx = 0
        raw_scores_per_sec = [[] for _ in range(grid_len)]

        # Define central 50% crosshair bounding box
        cy_start, cy_end = int(height * 0.25), int(height * 0.75)
        cx_start, cx_end = int(width * 0.25), int(width * 0.75)

        try:
            assert proc.stdout is not None
            while True:
                raw_frame = proc.stdout.read(frame_bytes)
                if not raw_frame or len(raw_frame) < frame_bytes:
                    break

                frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((height, width, 3))
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                if prev_gray is not None:
                    # Frame difference motion
                    diff = cv2.absdiff(gray, prev_gray)

                    # Central crosshair region (2x weight)
                    center_diff = diff[cy_start:cy_end, cx_start:cx_end]
                    center_motion = float(np.mean(center_diff))

                    # Outer region (1x weight)
                    total_motion = float(np.mean(diff))
                    weighted_motion = (2.0 * center_motion + 1.0 * total_motion) / 3.0

                    # Static menu / pause penalty: motion below baseline gets suppressed
                    if weighted_motion < 1.5:
                        weighted_motion *= 0.1

                    # Timestamp of current 2 FPS frame
                    timestamp_sec = frame_idx / fps
                    sec_bucket = min(grid_len - 1, int(timestamp_sec))
                    raw_scores_per_sec[sec_bucket].append(weighted_motion)

                prev_gray = gray
                frame_idx += 1

        finally:
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
            proc.wait()

        # Aggregate into 1-second grid
        grid_scores = np.zeros(grid_len, dtype=np.float32)
        for i in range(grid_len):
            if raw_scores_per_sec[i]:
                grid_scores[i] = np.mean(raw_scores_per_sec[i])

        # Normalize to [0, 1]
        ptp = np.ptp(grid_scores)
        if ptp > 1e-6:
            grid_scores = (grid_scores - np.min(grid_scores)) / ptp
        else:
            grid_scores = np.zeros_like(grid_scores)

        return grid_scores

    def analyze_segment(
        self,
        video_path: Path | str,
        start_sec: float,
        duration_sec: float,
    ) -> float:
        """
        Fast segment analyzer: computes average visual action score for a specific time window.
        Uses fast input seeking (-ss before -i).
        """
        v_path = Path(video_path).resolve()
        if not v_path.exists():
            return 0.0

        width = 640
        height = 360
        frame_bytes = width * height * 3
        fps = 2

        cmd = [
            self.ffmpeg_path,
            "-ss", f"{max(0.0, start_sec):.3f}",
            "-t", f"{duration_sec:.3f}",
            "-i", str(v_path),
            "-vf", f"fps={fps},scale={width}:{height}",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "pipe:1"
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
            bufsize=frame_bytes * 10
        )

        prev_gray: Optional[np.ndarray] = None
        scores: List[float] = []

        cy_start, cy_end = int(height * 0.25), int(height * 0.75)
        cx_start, cx_end = int(width * 0.25), int(width * 0.75)

        try:
            assert proc.stdout is not None
            while True:
                raw_frame = proc.stdout.read(frame_bytes)
                if not raw_frame or len(raw_frame) < frame_bytes:
                    break

                frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((height, width, 3))
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                if prev_gray is not None:
                    diff = cv2.absdiff(gray, prev_gray)
                    center_motion = float(np.mean(diff[cy_start:cy_end, cx_start:cx_end]))
                    total_motion = float(np.mean(diff))
                    weighted_motion = (2.0 * center_motion + 1.0 * total_motion) / 3.0
                    if weighted_motion < 1.5:
                        weighted_motion *= 0.1
                    scores.append(weighted_motion)

                prev_gray = gray
        finally:
            if proc.stdout:
                proc.stdout.close()
            proc.wait()

        if not scores:
            return 0.0
        return float(np.mean(scores))

