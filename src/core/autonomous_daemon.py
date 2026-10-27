"""Autonomous Channel Operator Daemon & Watcher.
Monitors watched directories and YouTube channels, handles PC uptime catch-up synchronization,
enforces API quota limits, and dispatches staggered scheduled publishing.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .quota_guard import QuotaGuard
from .channel_playbook import ChannelPlaybook
from .youtube_uploader import YouTubeUploader
from ..agent_toolkit import AgentToolkit


DEFAULT_AUTOPILOT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "max_daily_shorts": 4,
    "stagger_hours": 5.5,
    "default_publish_mode": "SCHEDULE_STAGGERED",
    "target_channels": [],
    "last_sync_date": "",
    "watch_folder": "data/watch_folder",
}


class AutonomousDaemon:
    """Coordinates unattended highlight creation, telemetry syncing, and staggered publishing."""

    def __init__(
        self,
        project_root: Optional[Path | str] = None,
        config_path: Optional[Path | str] = None,
        quota_guard: Optional[QuotaGuard] = None,
        toolkit: Optional[AgentToolkit] = None,
    ) -> None:
        self.root = Path(project_root or Path(__file__).resolve().parent.parent.parent).resolve()
        data_dir = self.root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        self.config_path = Path(config_path or (data_dir / "autopilot_config.json")).resolve()
        self.processed_sources_path = (data_dir / "processed_sources.json").resolve()
        self.config = self._load_config()

        self.watch_folder = Path(self.config.get("watch_folder") or (data_dir / "watch_folder")).resolve()
        self.watch_folder.mkdir(parents=True, exist_ok=True)

        self.quota_guard = quota_guard or QuotaGuard(
            quota_path=data_dir / "daily_upload_quota.json",
            max_daily_uploads=self.config.get("max_daily_shorts", 4),
        )
        self.toolkit = toolkit or AgentToolkit(project_root=self.root)
        self.playbook = self.toolkit.playbook
        self.uploader = self.toolkit.uploader
        self.processed_sources = self._load_processed_sources()

    def _load_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                return json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        cfg = dict(DEFAULT_AUTOPILOT_CONFIG)
        self._save_config(cfg)
        return cfg

    def _save_config(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        target = cfg if cfg is not None else self.config
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(target, indent=2), encoding="utf-8")

    def _load_processed_sources(self) -> List[str]:
        if self.processed_sources_path.exists():
            try:
                return json.loads(self.processed_sources_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _mark_source_processed(self, source_identifier: str) -> None:
        if source_identifier not in self.processed_sources:
            self.processed_sources.append(source_identifier)
            self.processed_sources_path.parent.mkdir(parents=True, exist_ok=True)
            self.processed_sources_path.write_text(
                json.dumps(self.processed_sources, indent=2), encoding="utf-8"
            )

    def run_startup_catchup(self) -> Dict[str, Any]:
        """
        Executes daily telemetry check upon service launch.
        If today's sync has not occurred (e.g. PC was powered off), pulls yesterday's metrics
        from YouTube and updates the Channel Playbook automatically.
        """
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        last_sync = self.config.get("last_sync_date", "")

        if last_sync == today_utc:
            return {
                "status": "ALREADY_SYNCED_TODAY",
                "date": today_utc,
                "message": f"Daily telemetry catch-up already executed for {today_utc}.",
            }

        if not self.uploader.is_authenticated():
            return {
                "status": "SKIPPED_NOT_AUTHENTICATED",
                "date": today_utc,
                "message": "YouTube account not authenticated; skipping telemetry pull.",
            }

        # Query live channel telemetry
        telemetry = self.uploader.fetch_channel_shorts_analytics(max_results=10)
        shorts = telemetry.get("shorts", [])
        updated_clips = 0

        for s in shorts:
            vid_id = s.get("video_id")
            views = s.get("views", 0)
            if vid_id and views > 0:
                self.playbook.record_clip_performance(
                    clip_id=vid_id,
                    layout_mode=self.playbook.get_recommendations().get("recommended_layout", "LAYOUT_B_CENTER_CROP"),
                    caption_theme=self.playbook.get_recommendations().get("recommended_theme", "MRBEAST_YELLOW"),
                    duration_sec=45.0,
                    retention_pct=s.get("estimated_retention_pct", 72.0),
                    views=views,
                    notes=f"Auto-synced on PC startup ({today_utc})",
                )
                updated_clips += 1

        self.config["last_sync_date"] = today_utc
        self._save_config()

        return {
            "status": "CATCHUP_COMPLETED",
            "date": today_utc,
            "clips_updated": updated_clips,
            "channel_stats": telemetry.get("channel_stats", {}),
            "total_analyzed_clips": self.playbook.data.get("total_analyzed_clips", 0),
        }

    def scan_watch_folder(self) -> List[Path]:
        """Finds unprocessed video files dropped into the local watched directory."""
        if not self.watch_folder.exists():
            return []

        valid_exts = {".mp4", ".mkv", ".mov", ".webm"}
        found = []
        for p in self.watch_folder.iterdir():
            if p.is_file() and p.suffix.lower() in valid_exts:
                if str(p.name) not in self.processed_sources and str(p.resolve()) not in self.processed_sources:
                    found.append(p)
        return found

    def calculate_staggered_times(
        self,
        count: int,
        stagger_hours: Optional[float] = None,
        start_delay_minutes: float = 30.0,
    ) -> List[str]:
        """Calculates RFC 3339 schedule timestamps spaced 5-6 hours apart."""
        interval = stagger_hours if stagger_hours is not None else float(self.config.get("stagger_hours", 5.5))
        now = datetime.now(timezone.utc)
        start_time = now + timedelta(minutes=start_delay_minutes)

        timestamps = []
        for i in range(count):
            t = start_time + timedelta(hours=i * interval)
            timestamps.append(t.strftime("%Y-%m-%dT%H:%M:%SZ"))
        return timestamps

    def process_source(
        self,
        source_url_or_path: str,
        target_count: int = 3,
        publish_mode: str = "SCHEDULE_STAGGERED",
        game_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Processes a single source video, enforcing quota guard and cloud scheduling."""
        src_str = str(source_url_or_path).strip()
        effective_publish = publish_mode

        if publish_mode in ("SCHEDULE_STAGGERED", "DRAFT_UPLOAD"):
            ok, quota_msg = self.quota_guard.can_upload(target_count)
            if not ok:
                # Quota exhausted: fallback to local render without failing the job
                effective_publish = "OFF"

        result = self.toolkit.run_autonomous_campaign(
            source_url_or_path=src_str,
            target_count=target_count,
            publish_mode=effective_publish,
            game_name=game_name,
        )

        uploads = result.get("uploads", [])
        successful_uploads = sum(1 for u in uploads if u.get("success", False))

        if successful_uploads > 0:
            self.quota_guard.record_upload(
                count=successful_uploads,
                video_title=src_str,
            )

        self._mark_source_processed(src_str)
        if Path(src_str).exists():
            self._mark_source_processed(Path(src_str).name)

        result["quota_status"] = self.quota_guard.get_status()
        return result

    def run_cycle(self) -> Dict[str, Any]:
        """Executes one complete pass of the autonomous operator."""
        catchup_res = self.run_startup_catchup()
        watch_files = self.scan_watch_folder()
        processed_reports = []

        # Process watched local files within quota limits
        for vf in watch_files:
            quota_status = self.quota_guard.get_status()
            remaining_slots = quota_status.get("remaining_uploads", 0)
            if remaining_slots <= 0:
                break

            count = min(3, remaining_slots)
            rep = self.process_source(
                source_url_or_path=str(vf),
                target_count=count,
                publish_mode=self.config.get("default_publish_mode", "SCHEDULE_STAGGERED"),
            )
            processed_reports.append(rep)

        return {
            "timestamp_iso": datetime.now(timezone.utc).isoformat(),
            "catchup": catchup_res,
            "watch_files_found": len(watch_files),
            "jobs_executed": len(processed_reports),
            "reports": processed_reports,
            "quota": self.quota_guard.get_status(),
        }
