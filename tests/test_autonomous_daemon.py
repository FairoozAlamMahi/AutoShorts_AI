"""Unit tests for Daily Quota Guard, Autonomous Daemon, Watch Folder, and Catch-Up Telemetry."""
import json
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from src.core.quota_guard import QuotaGuard, DEFAULT_DAILY_UPLOAD_LIMIT, MAX_DAILY_QUOTA_UNITS
from src.core.autonomous_daemon import AutonomousDaemon


def test_quota_guard_daily_limits(tmp_path: Path):
    """Verifies that QuotaGuard enforces maximum daily uploads and tracks units."""
    quota_file = tmp_path / "quota.json"
    guard = QuotaGuard(quota_path=quota_file, max_daily_uploads=4)

    # Initially fresh
    status = guard.get_status()
    assert status["uploads_today"] == 0
    assert status["remaining_uploads"] == 4
    assert status["is_quota_safe"]

    # Request 2 uploads -> approved
    ok, msg = guard.can_upload(2)
    assert ok
    guard.record_upload(count=2, video_title="Short 1 & 2")

    status = guard.get_status()
    assert status["uploads_today"] == 2
    assert status["remaining_uploads"] == 2

    # Request 3 uploads -> rejected (exceeds 4 total limit)
    ok, msg = guard.can_upload(3)
    assert not ok
    assert "Daily upload ceiling reached" in msg

    # Complete remaining 2
    guard.record_upload(count=2, video_title="Short 3 & 4")
    assert guard.get_status()["uploads_today"] == 4

    # Any further uploads rejected
    ok, msg = guard.can_upload(1)
    assert not ok


def test_quota_guard_utc_day_reset(tmp_path: Path):
    """Verifies that quota tracking resets on a new UTC date."""
    quota_file = tmp_path / "quota.json"
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    # Seed quota file with yesterday's exhausted numbers
    old_data = {
        "date": yesterday,
        "uploads_today": 4,
        "max_daily_uploads": 4,
        "estimated_units_spent": 6400,
        "max_quota_units": MAX_DAILY_QUOTA_UNITS,
        "upload_history": [],
    }
    quota_file.write_text(json.dumps(old_data), encoding="utf-8")

    # Load guard today
    guard = QuotaGuard(quota_path=quota_file, max_daily_uploads=4)
    ok, msg = guard.can_upload(2)
    assert ok  # Should have reset for today!
    assert guard.get_status()["uploads_today"] == 0


def test_autonomous_daemon_staggered_times(tmp_path: Path):
    """Verifies that scheduled drop times are staggered exactly by configured hours."""
    daemon = AutonomousDaemon(project_root=tmp_path)
    timestamps = daemon.calculate_staggered_times(count=3, stagger_hours=5.5, start_delay_minutes=30.0)

    assert len(timestamps) == 3
    t0 = datetime.fromisoformat(timestamps[0].replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(timestamps[1].replace("Z", "+00:00"))
    t2 = datetime.fromisoformat(timestamps[2].replace("Z", "+00:00"))

    diff1 = (t1 - t0).total_seconds() / 3600.0
    diff2 = (t2 - t1).total_seconds() / 3600.0
    assert diff1 == pytest.approx(5.5, rel=1e-3)
    assert diff2 == pytest.approx(5.5, rel=1e-3)


def test_autonomous_daemon_watch_folder_scan(tmp_path: Path):
    """Verifies that files in data/watch_folder are detected and duplicate-filtered."""
    daemon = AutonomousDaemon(project_root=tmp_path)
    watch_dir = daemon.watch_folder

    # Create dummy video files
    v1 = watch_dir / "gameplay_01.mp4"
    v2 = watch_dir / "stream_highlight.mkv"
    ignore_txt = watch_dir / "notes.txt"

    v1.write_bytes(b"dummy")
    v2.write_bytes(b"dummy")
    ignore_txt.write_text("ignore me")

    found = daemon.scan_watch_folder()
    assert len(found) == 2
    names = [p.name for p in found]
    assert "gameplay_01.mp4" in names
    assert "stream_highlight.mkv" in names
    assert "notes.txt" not in names

    # Mark one processed
    daemon._mark_source_processed(v1.name)
    subsequent = daemon.scan_watch_folder()
    assert len(subsequent) == 1
    assert subsequent[0].name == "stream_highlight.mkv"


def test_autonomous_daemon_startup_catchup(tmp_path: Path):
    """Verifies PC boot catch-up sync logic and playbook training."""
    daemon = AutonomousDaemon(project_root=tmp_path)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # With unauthenticated uploader
    res = daemon.run_startup_catchup()
    assert res["status"] in ("SKIPPED_NOT_AUTHENTICATED", "CATCHUP_COMPLETED", "ALREADY_SYNCED_TODAY")

    # Mock authenticated uploader returning mock shorts
    daemon.uploader.is_authenticated = MagicMock(return_value=True)
    daemon.uploader.fetch_channel_shorts_analytics = MagicMock(return_value={
        "success": True,
        "is_mock": True,
        "channel_stats": {"viewCount": "1000"},
        "shorts": [
            {
                "video_id": "vid_catchup_01",
                "title": "Clutch in Valorant",
                "views": 2500,
                "estimated_retention_pct": 79.0,
            }
        ]
    })

    # Force last_sync_date to be yesterday
    daemon.config["last_sync_date"] = "2026-10-25"
    catchup = daemon.run_startup_catchup()
    assert catchup["status"] == "CATCHUP_COMPLETED"
    assert catchup["clips_updated"] == 1
    assert daemon.config["last_sync_date"] == today

    # Second run today returns already synced
    second_run = daemon.run_startup_catchup()
    assert second_run["status"] == "ALREADY_SYNCED_TODAY"
