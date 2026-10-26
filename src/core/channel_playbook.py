"""Dynamic Channel Playbook & Retention Memory Engine.
Ranks winning layouts, hook formulas, and duration ranges based on real performance,
automatically biasing future batch generation towards high-retention formats.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from ..config.schema import LayoutMode, CaptionTheme, SceneCategory


DEFAULT_PLAYBOOK: Dict[str, Any] = {
    "version": "1.0",
    "total_analyzed_clips": 0,
    "top_performing_layouts": {
        "LAYOUT_B_CENTER_CROP": {"avg_retention_pct": 75.0, "sample_size": 1},
        "LAYOUT_4_3_BLUR_FIT": {"avg_retention_pct": 78.0, "sample_size": 1},
        "LAYOUT_HYBRID_CINEMA_STACK": {"avg_retention_pct": 72.0, "sample_size": 1},
    },
    "optimal_duration_range": {
        "min_sec": 30.0,
        "max_sec": 50.0,
    },
    "winning_caption_themes": {
        "MRBEAST_YELLOW": {"win_count": 1},
        "TIKTOK_RED_BOX": {"win_count": 1},
    },
    "historical_clips": [],
}


class ChannelPlaybook:
    """Maintains evolving channel intelligence to optimize future clip generation."""

    def __init__(self, playbook_path: Optional[Path | str] = None) -> None:
        self.path = Path(playbook_path or "data/channel_playbook.json").resolve()
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                content = json.loads(self.path.read_text(encoding="utf-8"))
                return content
            except Exception:
                pass
        return dict(DEFAULT_PLAYBOOK)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def record_clip_performance(
        self,
        clip_id: str,
        layout_mode: str,
        caption_theme: str,
        duration_sec: float,
        scene_category: str = "ACTION",
        retention_pct: Optional[float] = None,
        views: int = 0,
        hook_leak_pct: Optional[float] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        """Logs real-world performance for a clip and re-weights recommendations."""
        entry = {
            "clip_id": clip_id,
            "layout_mode": layout_mode,
            "caption_theme": caption_theme,
            "duration_sec": duration_sec,
            "scene_category": scene_category,
            "retention_pct": retention_pct if retention_pct is not None else 70.0,
            "views": views,
            "hook_leak_pct": hook_leak_pct,
            "notes": notes,
        }
        self.data.setdefault("historical_clips", []).append(entry)
        self.data["total_analyzed_clips"] = len(self.data["historical_clips"])

        # Update layout averages
        layouts = self.data.setdefault("top_performing_layouts", {})
        curr = layouts.setdefault(layout_mode, {"avg_retention_pct": 70.0, "sample_size": 0})
        prev_avg = curr["avg_retention_pct"]
        prev_n = curr["sample_size"]
        new_n = prev_n + 1
        new_ret = entry["retention_pct"]
        curr["avg_retention_pct"] = round((prev_avg * prev_n + new_ret) / new_n, 1)
        curr["sample_size"] = new_n

        # Update duration sweet spots (high retention clips > 75%)
        high_ret_durs = [
            c["duration_sec"] for c in self.data["historical_clips"] if c.get("retention_pct", 0) >= 75.0
        ]
        if high_ret_durs:
            avg_opt = sum(high_ret_durs) / len(high_ret_durs)
            self.data["optimal_duration_range"] = {
                "min_sec": max(15.0, round(avg_opt - 10.0, 1)),
                "max_sec": min(60.0, round(avg_opt + 10.0, 1)),
            }

        # Update caption theme wins
        if entry["retention_pct"] >= 75.0:
            themes = self.data.setdefault("winning_caption_themes", {})
            curr_theme = themes.setdefault(caption_theme, {"win_count": 0})
            curr_theme["win_count"] += 1

        self.save()
        return entry

    def get_recommendations(
        self,
        scene_category: Optional[str] = None,
        game_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Returns optimized generation parameters based on historical wins.
        """
        layouts = self.data.get("top_performing_layouts", {})
        # Sort layouts by average retention descending
        sorted_layouts = sorted(
            layouts.items(),
            key=lambda x: (x[1].get("avg_retention_pct", 0), x[1].get("sample_size", 0)),
            reverse=True,
        )

        top_layout = sorted_layouts[0][0] if sorted_layouts else "LAYOUT_B_CENTER_CROP"
        dur_range = self.data.get("optimal_duration_range", {"min_sec": 30.0, "max_sec": 50.0})

        # Theme recommendation
        themes = self.data.get("winning_caption_themes", {})
        sorted_themes = sorted(themes.items(), key=lambda x: x[1].get("win_count", 0), reverse=True)
        top_theme = sorted_themes[0][0] if sorted_themes else "MRBEAST_YELLOW"

        return {
            "recommended_layout": top_layout,
            "recommended_theme": top_theme,
            "recommended_min_duration_sec": dur_range.get("min_sec", 30.0),
            "recommended_max_duration_sec": dur_range.get("max_sec", 50.0),
            "total_analyzed_clips": self.data.get("total_analyzed_clips", 0),
        }
