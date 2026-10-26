"""Audience Retention Diagnostics Engine.
Parses YouTube Studio retention exports and API telemetry to identify Hook Leaks,
Drop-off Cliffs, and Pacing Slides, paired with transcript dialogue.
"""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple


class RetentionDiagnostics:
    """Diagnoses viewer drop-offs and correlates cliffs with spoken transcript lines."""

    @classmethod
    def load_retention_data(cls, file_or_content: str | Path) -> List[Tuple[float, float]]:
        """Parses CSV file or string of (timestamp_or_pct, retention_pct)."""
        content = ""
        p = Path(file_or_content)
        if p.exists() and p.is_file():
            content = p.read_text(encoding="utf-8-sig", errors="replace")
        else:
            content = str(file_or_content)

        rows: List[Tuple[float, float]] = []
        reader = csv.reader(io.StringIO(content))
        for r in reader:
            nums: List[float] = []
            for c in r:
                c_clean = c.strip().replace("%", "").replace(",", "")
                try:
                    nums.append(float(c_clean))
                except ValueError:
                    pass
            if len(nums) >= 2:
                rows.append((nums[0], nums[1]))

        return rows

    @classmethod
    def analyze_retention(
        cls,
        retention_data: List[Tuple[float, float]],
        duration_sec: Optional[float] = None,
        transcript_segments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Analyzes retention curves and correlates cliffs with dialogue.
        Returns hook_leak, cliffs, slide rate, and actionable recommendations.
        """
        if len(retention_data) < 4:
            return {"error": "Insufficient data points (minimum 4 required for retention analysis)"}

        xs = [r[0] for r in retention_data]
        ys = [r[1] for r in retention_data]
        # Determine if x-axis is percentage (0-100%) or raw seconds
        if max(xs) <= 1.05:
            is_pct_axis = True
            dur = duration_sec or 60.0
            xs = [x * 100.0 for x in xs]
            retention_data = list(zip(xs, ys))
        elif 95.0 <= max(xs) <= 100.5 and (duration_sec is None or abs(duration_sec - max(xs)) > 5.0):
            is_pct_axis = True
            dur = duration_sec or 60.0
        else:
            is_pct_axis = False
            dur = duration_sec or max(xs)

        def to_seconds(x: float) -> float:
            return (x / 100.0 * dur) if is_pct_axis else x

        start_val = ys[0] or 100.0
        # Hook leak window: first 15 seconds (industry standard for YouTube Shorts retention)
        cutoff_sec = min(15.0, dur)
        cutoff_x = (cutoff_sec / dur * 100.0) if is_pct_axis else cutoff_sec

        hook_points = [y for x, y in retention_data if x <= cutoff_x]
        hook_end = min(hook_points) if hook_points else start_val
        hook_leak = max(0.0, start_val - hook_end)

        # Detect drop-off cliffs (sudden drops between sequential points)
        drops: List[Dict[str, Any]] = []
        for i in range(1, len(retention_data)):
            d = ys[i - 1] - ys[i]
            span = max(0.1, xs[i] - xs[i - 1])
            rate = d / span
            if d > 1.2:  # Significant drop threshold
                sec_at = to_seconds(xs[i - 1])
                drops.append({
                    "lost_pct": round(d, 2),
                    "at_seconds": round(sec_at, 1),
                    "from_x": round(xs[i - 1], 1),
                    "to_x": round(xs[i], 1),
                })

        drops.sort(key=lambda x: x["lost_pct"], reverse=True)
        top_cliffs = drops[:5]

        # Correlate cliffs with transcript sentences
        if transcript_segments:
            for c in top_cliffs:
                t = c["at_seconds"]
                matched_text = []
                for seg in transcript_segments:
                    s_start = seg.get("start_sec", 0.0)
                    s_end = seg.get("end_sec", 0.0)
                    if s_start <= t + 2.5 and s_end >= t - 2.5:
                        matched_text.append(seg.get("text", ""))
                c["spoken_dialogue"] = " ".join(matched_text).strip()[:140]

        # Measure middle slide rate
        mid_drops = [ys[i - 1] - ys[i] for i in range(1, len(retention_data)) if xs[i - 1] > cutoff_x]
        slide = (sum(mid_drops) / len(mid_drops)) if mid_drops else 0.0

        # Formulate actionable diagnostics
        recommendations: List[str] = []
        if hook_leak > 35.0:
            recommendations.append("Severe Hook Leak (>35% lost in first 15s): Add a high-contrast on-screen text hook and eliminate opening verbal filler.")
        elif hook_leak > 25.0:
            recommendations.append("Moderate Hook Leak (25-35% lost in opening): Tighten the first 3 seconds to start directly on the action.")
        else:
            recommendations.append("Healthy Hook (<25% lost): Viewers are engaging with the opening!")

        if top_cliffs:
            cliff = top_cliffs[0]
            recommendations.append(f"Major Drop Cliff at {cliff['at_seconds']}s (-{cliff['lost_pct']}%): Viewers swiped away. Review pacing or topic transition at this timestamp.")

        if slide > 2.0:
            recommendations.append(f"Steep Middle Slide: Clip pacing is dragging. Consider cutting duration down by 10-15s.")

        verdict = "viral" if (hook_leak < 20 and ys[-1] > 65) else "healthy" if hook_leak < 28 else "needs_hook_tuning"

        return {
            "total_points": len(retention_data),
            "start_pct": round(start_val, 1),
            "end_pct": round(ys[-1], 1),
            "hook_leak_pct": round(hook_leak, 1),
            "verdict": verdict,
            "top_cliffs": top_cliffs,
            "slide_rate_per_unit": round(slide, 3),
            "recommendations": recommendations,
        }
