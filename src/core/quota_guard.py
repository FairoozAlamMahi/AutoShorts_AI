"""Daily API Quota Guard & Safe Upload Ceiling.
Enforces Google YouTube Data API v3 daily quota budget (max 4 uploads/day = 6,400 of 10,000 units),
preventing quota exhaustion and spam filter triggers.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Tuple, Optional


UPLOAD_UNIT_COST = 1600
DEFAULT_DAILY_UPLOAD_LIMIT = 4
MAX_DAILY_QUOTA_UNITS = 10000


class QuotaGuard:
    """Manages YouTube Data API quota expenditure and enforces daily upload limits."""

    def __init__(
        self,
        quota_path: Optional[Path | str] = None,
        max_daily_uploads: int = DEFAULT_DAILY_UPLOAD_LIMIT,
    ) -> None:
        self.path = Path(quota_path or "data/daily_upload_quota.json").resolve()
        self.max_daily_uploads = max_daily_uploads
        self.data: Dict[str, Any] = self._load()

    def _get_current_utc_date(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load(self) -> Dict[str, Any]:
        curr_date = self._get_current_utc_date()
        if self.path.exists():
            try:
                content = json.loads(self.path.read_text(encoding="utf-8"))
                if content.get("date") == curr_date:
                    return content
            except Exception:
                pass

        # Initialize fresh quota tracking for today
        new_data = {
            "date": curr_date,
            "uploads_today": 0,
            "max_daily_uploads": self.max_daily_uploads,
            "estimated_units_spent": 0,
            "max_quota_units": MAX_DAILY_QUOTA_UNITS,
            "upload_history": [],
        }
        self._save(new_data)
        return new_data

    def _save(self, data: Optional[Dict[str, Any]] = None) -> None:
        target = data if data is not None else self.data
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(target, indent=2), encoding="utf-8")

    def _reset_if_new_day(self) -> None:
        curr_date = self._get_current_utc_date()
        if self.data.get("date") != curr_date:
            self.data = {
                "date": curr_date,
                "uploads_today": 0,
                "max_daily_uploads": self.max_daily_uploads,
                "estimated_units_spent": 0,
                "max_quota_units": MAX_DAILY_QUOTA_UNITS,
                "upload_history": [],
            }
            self._save()

    def can_upload(self, count: int = 1) -> Tuple[bool, str]:
        """Checks whether the requested upload volume fits within today's quota budget."""
        self._reset_if_new_day()
        curr_uploads = self.data.get("uploads_today", 0)
        max_uploads = self.data.get("max_daily_uploads", self.max_daily_uploads)

        if curr_uploads + count > max_uploads:
            remaining = max(0, max_uploads - curr_uploads)
            return (
                False,
                f"Daily upload ceiling reached: {curr_uploads}/{max_uploads} uploaded today. "
                f"Requested {count}, but only {remaining} upload slot(s) remain today. "
                f"Resets at 00:00 UTC."
            )

        estimated_cost = count * UPLOAD_UNIT_COST
        spent = self.data.get("estimated_units_spent", 0)
        if spent + estimated_cost > MAX_DAILY_QUOTA_UNITS:
            return (
                False,
                f"Daily API quota limit exceeded: {spent}/{MAX_DAILY_QUOTA_UNITS} units spent today. "
                f"Resets at 00:00 UTC."
            )

        return True, f"Quota approved: {curr_uploads + count}/{max_uploads} uploads scheduled for today."

    def record_upload(self, count: int = 1, video_title: str = "", video_id: str = "") -> Dict[str, Any]:
        """Records an approved upload and updates spent units."""
        self._reset_if_new_day()
        self.data["uploads_today"] = self.data.get("uploads_today", 0) + count
        self.data["estimated_units_spent"] = self.data.get("estimated_units_spent", 0) + (count * UPLOAD_UNIT_COST)
        self.data.setdefault("upload_history", []).append({
            "timestamp_iso": datetime.now(timezone.utc).isoformat(),
            "count": count,
            "title": video_title,
            "video_id": video_id,
        })
        self._save()
        return self.data

    def record_api_call(self, unit_cost: int = 1) -> None:
        """Records lightweight API calls (search, list, etc.)."""
        self._reset_if_new_day()
        self.data["estimated_units_spent"] = self.data.get("estimated_units_spent", 0) + unit_cost
        self._save()

    def get_status(self) -> Dict[str, Any]:
        """Provides display status for Gradio UI and daemon logging."""
        self._reset_if_new_day()
        curr = self.data.get("uploads_today", 0)
        limit = self.data.get("max_daily_uploads", self.max_daily_uploads)
        spent = self.data.get("estimated_units_spent", 0)
        remaining_uploads = max(0, limit - curr)
        remaining_units = max(0, MAX_DAILY_QUOTA_UNITS - spent)

        return {
            "date": self.data.get("date"),
            "uploads_today": curr,
            "max_daily_uploads": limit,
            "remaining_uploads": remaining_uploads,
            "estimated_units_spent": spent,
            "remaining_units": remaining_units,
            "is_quota_safe": curr < limit and spent < MAX_DAILY_QUOTA_UNITS,
            "display": f"{curr}/{limit} Shorts Uploaded Today ({remaining_uploads} slots remaining)",
        }
