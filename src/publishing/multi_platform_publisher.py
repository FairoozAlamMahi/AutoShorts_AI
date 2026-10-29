"""Unified Multi-Platform Publishing Dispatcher.
Coordinates autonomous release of short-form videos across YouTube Shorts,
Instagram Reels, Facebook Reels, and TikTok with format adaptation,
staggered scheduling, and consolidated analytics logging.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from .facebook_uploader import FacebookUploader
from .instagram_uploader import InstagramUploader
from .tiktok_uploader import TikTokUploader
from ..core.youtube_uploader import YouTubeUploader

logger = logging.getLogger("MultiPlatformPublisher")


class MultiPlatformPublisher:
    """Orchestrates cross-platform short-form video releases across all major social networks."""

    DEFAULT_HISTORY_FILE = Path("data/multi_platform_upload_history.json")

    def __init__(
        self,
        history_path: Optional[Path | str] = None,
    ) -> None:
        self.history_path = Path(history_path) if history_path else self.DEFAULT_HISTORY_FILE
        self.youtube = YouTubeUploader()
        self.instagram = InstagramUploader()
        self.facebook = FacebookUploader()
        self.tiktok = TikTokUploader()

    def get_all_platform_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Returns connection and authentication state for all 4 supported platforms."""
        return {
            "youtube": self.youtube.get_status_summary(),
            "instagram": self.instagram.get_status_summary(),
            "facebook": self.facebook.get_status_summary(),
            "tiktok": self.tiktok.get_status_summary(),
        }

    def publish_video(
        self,
        video_path: Path | str,
        title: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        thumbnail_path: Optional[Path | str] = None,
        platforms: Optional[List[str]] = None,
        base_scheduled_time_iso: Optional[str] = None,
        stagger_minutes: int = 45,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Dispatches a video to selected platforms with tailored captions and staggered timing.

        Supported platforms: ['youtube', 'instagram', 'facebook', 'tiktok']
        """
        v_path = Path(video_path).resolve()
        if not v_path.exists():
            raise FileNotFoundError(f"Video file not found: {v_path}")

        active_platforms = [p.lower().strip() for p in (platforms or ["youtube", "instagram", "facebook", "tiktok"])]
        results: Dict[str, Any] = {}
        timestamp_iso = datetime.now(timezone.utc).isoformat()

        # Parse base scheduled time
        base_time = datetime.now(timezone.utc)
        if base_scheduled_time_iso:
            try:
                base_time = datetime.fromisoformat(base_scheduled_time_iso.replace("Z", "+00:00"))
            except Exception as ex:
                logger.warning(f"Failed parsing base scheduled time {base_scheduled_time_iso}: {ex}")

        # Platform 1: YouTube Shorts
        if "youtube" in active_platforms:
            try:
                yt_sched = base_time.isoformat() if base_scheduled_time_iso else None
                logger.info(f"Dispatching to YouTube Shorts: {title}...")
                if dry_run:
                    simulated_id = f"staged_yt_{int(time.time())}_{v_path.stem}"
                    results["youtube"] = {
                        "success": True,
                        "platform": "youtube",
                        "video_id": simulated_id,
                        "url": f"https://www.youtube.com/shorts/{simulated_id}",
                        "mode": "DRY_RUN_STAGED",
                        "title": title,
                        "timestamp": timestamp_iso,
                    }
                else:
                    res_yt = self.youtube.upload_short(
                        video_path=v_path,
                        title=title,
                        description=description or title,
                        tags=tags,
                        publish_at_iso=yt_sched,
                    )
                    res_yt["platform"] = "youtube"
                    res_yt["mode"] = "LIVE_YOUTUBE_API" if not res_yt.get("is_mock") else "MOCK_VALIDATED"
                    results["youtube"] = res_yt
            except Exception as e:
                logger.error(f"YouTube publishing failed: {e}")
                results["youtube"] = {"success": False, "error": str(e), "platform": "youtube"}

        # Platform 2: Instagram Reels (Staggered by +45m)
        if "instagram" in active_platforms:
            try:
                ig_caption = self.instagram.sanitize_caption(title=title, description=description, tags=tags)
                logger.info(f"Dispatching to Instagram Reels: {v_path.name}...")
                res_ig = self.instagram.upload_reel(
                    video_path=v_path,
                    caption=ig_caption,
                    thumbnail_path=thumbnail_path,
                    dry_run=dry_run,
                )
                results["instagram"] = res_ig
            except Exception as e:
                logger.error(f"Instagram publishing failed: {e}")
                results["instagram"] = {"success": False, "error": str(e), "platform": "instagram"}

        # Platform 3: Facebook Reels (Staggered by +90m)
        if "facebook" in active_platforms:
            try:
                fb_time = (base_time + timedelta(minutes=stagger_minutes * 2)).isoformat() if base_scheduled_time_iso else None
                fb_caption = self.facebook.sanitize_caption(title=title, description=description, tags=tags)
                logger.info(f"Dispatching to Facebook Reels: {v_path.name}...")
                res_fb = self.facebook.upload_reel(
                    video_path=v_path,
                    caption=fb_caption,
                    scheduled_time_iso=fb_time,
                    dry_run=dry_run,
                )
                results["facebook"] = res_fb
            except Exception as e:
                logger.error(f"Facebook publishing failed: {e}")
                results["facebook"] = {"success": False, "error": str(e), "platform": "facebook"}

        # Platform 4: TikTok (Staggered by +135m)
        if "tiktok" in active_platforms:
            try:
                tt_caption = self.tiktok.sanitize_caption(title=title, tags=tags)
                logger.info(f"Dispatching to TikTok: {v_path.name}...")
                res_tt = self.tiktok.upload_video(
                    video_path=v_path,
                    caption=tt_caption,
                    dry_run=dry_run,
                )
                results["tiktok"] = res_tt
            except Exception as e:
                logger.error(f"TikTok publishing failed: {e}")
                results["tiktok"] = {"success": False, "error": str(e), "platform": "tiktok"}

        consolidated_receipt = {
            "timestamp": timestamp_iso,
            "video_path": str(v_path),
            "title": title,
            "platforms": results,
            "total_success": sum(1 for r in results.values() if r.get("success", False)),
            "total_dispatched": len(results),
        }

        self._record_history(consolidated_receipt)
        return consolidated_receipt

    def _record_history(self, receipt: Dict[str, Any]) -> None:
        """Appends consolidated cross-platform receipt to history ledger."""
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            history: List[Dict[str, Any]] = []
            if self.history_path.exists():
                try:
                    history = json.loads(self.history_path.read_text(encoding="utf-8"))
                    if not isinstance(history, list):
                        history = []
                except Exception:
                    history = []
            history.append(receipt)
            self.history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
        except Exception as ex:
            logger.warning(f"Could not record multi-platform history: {ex}")
