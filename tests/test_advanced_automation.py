"""Comprehensive Test Suite for Advanced Autonomous Channel Operator Features:
- Target YouTube Channel & Playlist Auto-Scraper
- YouTube Studio Retention CSV Parser & Dialogue-to-Cliff Correlation
- Multi-Candidate Thumbnail Generator (thumb_A, thumb_B, thumb_C) & A/B Metadata Logging
- Game-Specific Audio & Transition SFX Library (SyntheticSFXFactory & SFXManager)
- Auto-Pinned High-Engagement Comment Generation & Posting
- 100% Unattended Hand-Over-The-Keys Campaign Mode
- Aspect Ratio Safeguard (ensure_vertical_short)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.core.autonomous_daemon import AutonomousDaemon
from src.core.quota_guard import QuotaGuard
from src.core.youtube_uploader import YouTubeUploader
from src.analytics.retention_diagnostics import RetentionDiagnostics
from src.analytics.agent_copilot import AgentCoPilotSynthesizer
from src.rendering.ffmpeg_renderer import FFmpegRenderer
from src.rendering.sfx_manager import SyntheticSFXFactory, SFXManager
from tests.synthetic_media_factory import SyntheticMediaFactory


def test_youtube_studio_retention_csv_parsing(tmp_path: Path):
    """Verifies that RetentionDiagnostics parses YouTube Studio standard CSV exports with MM:SS time formats."""
    # Standard YouTube Studio export format
    csv_content = """Video time,Audience retention (%)
0:00,100.0%
0:02,94.2%
0:05,88.0%
0:10,79.5%
0:15,70.0%
0:20,68.2%
0:25,52.0%
0:30,48.0%
0:35,46.5%
0:40,45.0%
"""
    csv_path = tmp_path / "studio_retention.csv"
    csv_path.write_text(csv_content, encoding="utf-8")

    parsed = RetentionDiagnostics.parse_studio_retention_csv(csv_path, duration_sec=45.0)
    assert parsed["success"] is True
    assert len(parsed["points"]) == 10
    # First point: 0 sec, 100%
    assert parsed["points"][0] == (0.0, 100.0)
    # Fifth point: 15 sec, 70%
    assert parsed["points"][4] == (15.0, 70.0)
    # Hook leak in first 15 seconds: 100 - 70 = 30%
    assert parsed["hook_leak_pct"] == 30.0
    assert len(parsed["top_cliffs"]) > 0


def test_dialogue_to_cliff_auto_correlation():
    """Verifies that sudden audience drop-off cliffs are correlated with spoken transcript or flagged as dead air."""
    cliffs = [
        {"at_seconds": 12.0, "lost_pct": 14.5},
        {"at_seconds": 25.0, "lost_pct": 8.0},
    ]
    # Transcript only speaks at 10-14s; 23-27s is dead air/silence
    segments = [
        {"start_sec": 10.0, "end_sec": 14.0, "text": "Wait what are they doing over there?"},
    ]

    correlated = RetentionDiagnostics.correlate_dialogue_cliffs(cliffs, segments)
    assert len(correlated) == 2

    # Cliff 1: matched dialogue
    c1 = correlated[0]
    assert "Wait what are they doing" in c1["spoken_dialogue"]
    assert c1["cliff_category"] in ("SLOW_DIALOGUE_PACING", "TOPIC_OR_SCENE_TRANSITION")

    # Cliff 2: dead air detected
    c2 = correlated[1]
    assert c2["cliff_category"] == "DEAD_AIR_SILENCE"
    assert "[DEAD AIR / SILENCE]" in c2["spoken_dialogue"]


def test_multi_candidate_thumbnail_generation(tmp_path: Path):
    """Verifies generation of 3 distinct cover thumbnails (thumb_A, thumb_B, thumb_C) and metadata logging."""
    src_video = SyntheticMediaFactory.create_test_video(tmp_path / "short_clip.mp4", duration_sec=4.0, has_audio=True)
    renderer = FFmpegRenderer()

    thumbs = renderer.generate_multi_thumbnails(
        video_path=src_video,
        output_dir=tmp_path / "thumbs",
        duration_sec=4.0,
        hook_overlay_text="WHAT HAPPENED HERE?",
    )

    assert thumbs["A"].exists()
    assert thumbs["B"].exists()
    assert thumbs["C"].exists()
    assert thumbs["main"].exists()

    meta_file = tmp_path / "thumbs" / "short_clip.thumbnails.json"
    assert meta_file.exists()
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    assert "thumb_A" in meta["candidates"]
    assert "thumb_B" in meta["candidates"]
    assert "thumb_C" in meta["candidates"]
    assert meta["hook_text"] == "WHAT HAPPENED HERE?"


def test_synthetic_sfx_library_and_manager(tmp_path: Path):
    """Verifies that SyntheticSFXFactory generates valid WAV files and SFXManager provides scene-matched stingers."""
    sfx_dir = tmp_path / "sfx"
    manager = SFXManager(sfx_dir=sfx_dir)

    whoosh_path = manager.get_sfx_path("WHOOSH")
    assert whoosh_path.exists()
    assert whoosh_path.stat().st_size > 1000

    impact_path = manager.get_sfx_for_scene("ACTION")
    assert impact_path.exists()
    assert impact_path.name == "impact.wav"

    fail_path = manager.get_sfx_for_scene("BUSTED")
    assert fail_path.exists()
    assert fail_path.name == "fail_horn.wav"

    clutch_path = manager.get_sfx_for_scene("VICTORY")
    assert clutch_path.exists()
    assert clutch_path.name == "clutch_stinger.wav"


def test_auto_pinned_engagement_comment():
    """Verifies that AgentCoPilotSynthesizer crafts viral question comments to pin on uploaded Shorts."""
    # Context 1: Characters present
    comm1 = AgentCoPilotSynthesizer.generate_engagement_comment(
        transcript_text="Jason look out for the cops! Lucia take the wheel!",
        game_name="GTA 6",
        scene_type="ACTION",
    )
    assert "Vice City" in comm1 or "Jason" in comm1 or "?" in comm1

    # Context 2: Fail moment
    comm2 = AgentCoPilotSynthesizer.generate_engagement_comment(
        transcript_text="",
        game_name="GTA 6",
        scene_type="FAIL",
    )
    assert "fail" in comm2.lower() or "1 to 10" in comm2

    # Context 3: Clutch moment
    comm3 = AgentCoPilotSynthesizer.generate_engagement_comment(
        transcript_text="Unbelievable headshot right at the buzzer",
        game_name="Valorant",
        scene_type="CLUTCH",
    )
    assert "?" in comm3


def test_target_channel_scraper_mock(tmp_path: Path):
    """Verifies that AutonomousDaemon parses scraped target channels and avoids re-scraping processed entries."""
    daemon = AutonomousDaemon(
        project_root=tmp_path,
        config_path=tmp_path / "autopilot_config.json",
    )
    daemon.config["target_channels"] = ["https://www.youtube.com/@TestGamingChannel/videos"]
    daemon._save_config()

    # Mock yt-dlp flat-playlist response
    mock_ytdlp_json = json.dumps({
        "entries": [
            {"id": "vid_001", "title": "Insane GTA 6 Mission 1", "url": "https://www.youtube.com/watch?v=vid_001"},
            {"id": "vid_002", "title": "Lucia Speedrun Part 2", "url": "https://www.youtube.com/watch?v=vid_002"},
        ]
    })

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_ytdlp_json)
        scraped = daemon.scrape_target_channels(max_videos_per_target=2, auto_download=False)

    assert len(scraped) == 2
    assert scraped[0]["video_id"] == "vid_001"
    assert scraped[1]["video_id"] == "vid_002"

    # Mark vid_001 as already processed
    daemon._mark_source_processed("vid_001")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_ytdlp_json)
        scraped2 = daemon.scrape_target_channels(max_videos_per_target=2, auto_download=False)

    assert len(scraped2) == 1
    assert scraped2[0]["video_id"] == "vid_002"


def test_ensure_vertical_short_safeguard(tmp_path: Path):
    """Verifies that YouTubeUploader.ensure_vertical_short transcodes landscape videos into 1080x1920 vertical canvas."""
    # Create horizontal 16:9 test video (1920x1080)
    horiz_video = SyntheticMediaFactory.create_test_video(tmp_path / "horizontal_video.mp4", duration_sec=2.0, has_audio=True)
    uploader = YouTubeUploader(token_path=tmp_path / "token.json")

    # Pass horizontal video to ensure_vertical_short
    fixed_path = uploader.ensure_vertical_short(horiz_video)
    assert Path(fixed_path).exists()
    assert "_vertical" in Path(fixed_path).name

    # Inspect the converted video
    renderer = FFmpegRenderer()
    info = renderer.inspector.inspect(fixed_path)
    assert info.width == 1080
    assert info.height == 1920
    assert info.width <= info.height
