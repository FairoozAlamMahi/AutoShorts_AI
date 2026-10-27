"""Audience Retention Diagnostics Engine.
Parses YouTube Studio retention exports and API telemetry to identify Hook Leaks,
Drop-off Cliffs, and Pacing Slides, paired with transcript dialogue and Playbook updates.
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

    @staticmethod
    def _parse_cell_value(cell_str: str) -> Optional[float]:
        """Parses a numerical value or MM:SS / HH:MM:SS timestamp into float seconds or percentage."""
        c = cell_str.strip().replace("%", "").replace(",", "").replace('"', '')
        if not c:
            return None
        if ":" in c:
            parts = c.split(":")
            try:
                if len(parts) == 2:
                    return float(parts[0]) * 60.0 + float(parts[1])
                elif len(parts) == 3:
                    return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
            except ValueError:
                return None
        try:
            return float(c)
        except ValueError:
            return None

    @classmethod
    def load_retention_data(cls, file_or_content: str | Path) -> List[Tuple[float, float]]:
        """
        Parses CSV file or string of (timestamp_or_pct, retention_pct).
        Supports YouTube Studio time formats ('0:00', '0:15') and percentage formats ('100%', '82.5%').
        """
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
            for cell in r:
                val = cls._parse_cell_value(cell)
                if val is not None:
                    nums.append(val)
            if len(nums) >= 2:
                rows.append((nums[0], nums[1]))

        return rows

    @classmethod
    def parse_studio_retention_csv(
        cls,
        file_or_content: str | Path,
        duration_sec: Optional[float] = None,
        transcript_segments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        High-level parser specifically built for YouTube Studio retention CSV exports.
        Extracts retention points, calculates hook leak, identifies cliffs, and correlates with dialogue.
        """
        points = cls.load_retention_data(file_or_content)
        if len(points) < 4:
            return {
                "success": False,
                "error": f"Insufficient data points in CSV ({len(points)} parsed, minimum 4 required).",
                "points": points,
            }

        analysis = cls.analyze_retention(
            retention_data=points,
            duration_sec=duration_sec,
            transcript_segments=transcript_segments,
        )
        analysis["success"] = True
        analysis["points"] = points
        return analysis

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
        top_cliffs = cls.correlate_dialogue_cliffs(top_cliffs, transcript_segments)

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
            recommendations.append("Steep Middle Slide: Clip pacing is dragging. Consider cutting duration down by 10-15s.")

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

    @classmethod
    def correlate_dialogue_cliffs(
        cls,
        cliffs: List[Dict[str, Any]],
        transcript_segments: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Correlates cliff timestamps against spoken transcript words or identifies dead air.
        Categorizes drop reasons (DEAD_AIR_SILENCE vs MONOTONE_PACING vs TOPIC_SHIFT).
        """
        for c in cliffs:
            t = c["at_seconds"]
            if not transcript_segments:
                c["spoken_dialogue"] = ""
                c["cliff_category"] = "UNANNOTATED"
                c["diagnosis"] = "No transcript supplied for correlation."
                continue

            matched_text = []
            for seg in transcript_segments:
                s_start = seg.get("start_sec", 0.0)
                s_end = seg.get("end_sec", 0.0)
                if s_start <= t + 2.5 and s_end >= t - 2.5:
                    matched_text.append(seg.get("text", ""))

            full_dialogue = " ".join(matched_text).strip()
            if not full_dialogue:
                c["spoken_dialogue"] = "[DEAD AIR / SILENCE]"
                c["cliff_category"] = "DEAD_AIR_SILENCE"
                c["diagnosis"] = "Viewer drop coincided with a lull in dialogue or visual energy. Cut dead air faster."
            else:
                c["spoken_dialogue"] = full_dialogue[:140]
                if len(full_dialogue.split()) < 4:
                    c["cliff_category"] = "SLOW_DIALOGUE_PACING"
                    c["diagnosis"] = f"Sparse speech ('{full_dialogue[:40]}...'). Accelerate subtitle pacing."
                else:
                    c["cliff_category"] = "TOPIC_OR_SCENE_TRANSITION"
                    c["diagnosis"] = f"Drop occurred during transition: '{full_dialogue[:50]}...'. Keep action moving."

        return cliffs

    @classmethod
    def apply_retention_penalties(
        cls,
        analysis: Dict[str, Any],
        playbook: Any,
        layout_mode: str,
        caption_theme: str,
    ) -> Dict[str, Any]:
        """
        Feeds retention diagnosis directly into ChannelPlaybook to optimize future video generation.
        """
        hook_leak = analysis.get("hook_leak_pct", 0.0)
        end_pct = analysis.get("end_pct", 70.0)
        verdict = analysis.get("verdict", "healthy")

        notes = f"Retention Audit: verdict={verdict}, hook_leak={hook_leak}%, completion={end_pct}%"
        playbook.record_clip_performance(
            clip_id="retention_audit_" + verdict,
            layout_mode=layout_mode,
            caption_theme=caption_theme,
            duration_sec=45.0,
            scene_category="ACTION",
            retention_pct=end_pct,
            views=1000,
            hook_leak_pct=hook_leak,
            notes=notes,
        )
        return {
            "status": "PLAYBOOK_UPDATED",
            "hook_leak": hook_leak,
            "completion": end_pct,
            "verdict": verdict,
            "updated_playbook_stats": playbook.get_recommendations(),
        }
