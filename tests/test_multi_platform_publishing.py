"""Unit and Integration Tests for Multi-Platform Publishing Suite.
Verifies Facebook, Instagram, and TikTok uploaders alongside MultiPlatformPublisher.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

try:
    from src.publishing import (
        FacebookUploader,
        InstagramUploader,
        TikTokUploader,
        MultiPlatformPublisher,
    )
except ImportError:
    from shorts_factory.src.publishing import (
        FacebookUploader,
        InstagramUploader,
        TikTokUploader,
        MultiPlatformPublisher,
    )


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    """Creates a mock valid .mp4 file for staging tests."""
    v = tmp_path / "mock_short.mp4"
    v.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 1024)
    return v


def test_facebook_uploader_caption_and_dry_run(tmp_path: Path, sample_video: Path):
    fb = FacebookUploader(
        credentials_path=tmp_path / "fb_creds.json",
        history_path=tmp_path / "fb_history.json",
    )

    caption = fb.sanitize_caption(
        title="Epic Boss Parry",
        description="Check out this clean counter window.",
        tags=["#gaming", "reels", "#fyp", "viral"],
    )
    assert "Epic Boss Parry" in caption
    assert "#gaming" in caption
    assert "#reels" in caption

    # Dry-run execution
    receipt = fb.upload_reel(
        video_path=sample_video,
        caption=caption,
        dry_run=True,
    )
    assert receipt["success"] is True
    assert receipt["platform"] == "facebook"
    assert "staged_fb_" in receipt["video_id"]
    assert "facebook.com/reel" in receipt["url"]

    # History verified
    history_file = tmp_path / "fb_history.json"
    assert history_file.exists()
    history = json.loads(history_file.read_text(encoding="utf-8"))
    assert len(history) == 1
    assert history[0]["video_id"] == receipt["video_id"]


def test_tiktok_uploader_caption_and_dry_run(tmp_path: Path, sample_video: Path):
    tt = TikTokUploader(
        credentials_path=tmp_path / "tt_creds.json",
        session_path=tmp_path / "tt_session.json",
        history_path=tmp_path / "tt_history.json",
    )

    caption = tt.sanitize_caption(
        title="Insane Drift Stunt",
        tags=["drift", "#gaming", "fyp"],
    )
    assert "Insane Drift Stunt" in caption
    assert "#drift" in caption
    assert "#gaming" in caption

    # Dry-run execution
    receipt = tt.upload_video(
        video_path=sample_video,
        caption=caption,
        dry_run=True,
    )
    assert receipt["success"] is True
    assert receipt["platform"] == "tiktok"
    assert "staged_tt_" in receipt["publish_id"]
    assert "tiktok.com" in receipt["url"]

    # History verified
    history_file = tmp_path / "tt_history.json"
    assert history_file.exists()
    history = json.loads(history_file.read_text(encoding="utf-8"))
    assert len(history) == 1
    assert history[0]["publish_id"] == receipt["publish_id"]


def test_instagram_uploader_dry_run(tmp_path: Path, sample_video: Path):
    ig = InstagramUploader(
        session_path=tmp_path / "ig_session.json",
        credentials_path=tmp_path / "ig_creds.json",
        history_path=tmp_path / "ig_history.json",
    )

    caption = ig.sanitize_caption(
        title="Unreal Highway Evasion",
        tags=["#gta", "reels"],
    )
    assert "Unreal Highway Evasion" in caption
    assert "#gta" in caption

    receipt = ig.upload_reel(
        video_path=sample_video,
        caption=caption,
        dry_run=True,
    )
    assert receipt["success"] is True
    assert "staged_ig_" in receipt["media_id"]
    assert "instagram.com/reel" in receipt["url"]


def test_multi_platform_publisher_dispatch(tmp_path: Path, sample_video: Path):
    publisher = MultiPlatformPublisher(history_path=tmp_path / "multi_history.json")

    # Override history paths for clean tests
    publisher.facebook.history_path = tmp_path / "fb_hist.json"
    publisher.tiktok.history_path = tmp_path / "tt_hist.json"
    publisher.instagram.history_path = tmp_path / "ig_hist.json"

    statuses = publisher.get_all_platform_statuses()
    assert "youtube" in statuses
    assert "instagram" in statuses
    assert "facebook" in statuses
    assert "tiktok" in statuses

    # Multi-platform dry-run publish
    receipt = publisher.publish_video(
        video_path=sample_video,
        title="Grand Theft Auto Precision Drift",
        description="Autonomous Short generation test.",
        tags=["gta", "drift", "shorts", "gaming"],
        platforms=["youtube", "instagram", "facebook", "tiktok"],
        dry_run=True,
    )

    assert receipt["total_dispatched"] == 4
    assert receipt["total_success"] >= 3  # YT, FB, TT, IG dry-runs
    assert "facebook" in receipt["platforms"]
    assert "tiktok" in receipt["platforms"]
    assert "instagram" in receipt["platforms"]
    assert "youtube" in receipt["platforms"]

    assert receipt["platforms"]["facebook"]["success"] is True
    assert receipt["platforms"]["tiktok"]["success"] is True
    assert receipt["platforms"]["instagram"]["success"] is True
