"""Comprehensive test suite for Analytics, Retention Diagnostics, Hook Engine, Title Linter, and Channel Playbook."""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.analytics.hook_engine import HookEngine
from src.analytics.title_linter import TitleLinter
from src.analytics.retention_diagnostics import RetentionDiagnostics
from src.core.channel_playbook import ChannelPlaybook
from src.core.youtube_uploader import YouTubeUploader
from src.ingest.cookie_manager import CookieManager
from src.captions.ass_compiler import ASSCompiler
from src.captions.phrase_chunker import CaptionChunkDTO
from src.core.dto import TranscriptWordDTO
from src.config.schema import CaptionMode, CaptionTheme, LayoutMode
from src.agent_toolkit import AgentToolkit


def test_hook_engine_scoring_and_formulation():
    """Verifies that weak verbal openings are scored low and high-stakes openings score high."""
    # Weak opening with filler and vague hype
    weak_opening = "Hey guys welcome back today basically we are going to do something really amazing"
    weak_res = HookEngine.score_hook(weak_opening)
    assert weak_res["overall_score"] < 65
    assert weak_res["verdict"] == "needs_hook_overlay"

    # High-stakes, concrete, direct-address opening
    strong_opening = "97% of players like you quit before video 30. Here is what the other 3% do differently."
    strong_res = HookEngine.score_hook(strong_opening)
    assert strong_res["overall_score"] > 65
    assert strong_res["sub_scores"]["stakes"] > 50
    assert strong_res["sub_scores"]["address"] > 50

    # Hook Overlay formulation
    overlay = HookEngine.generate_hook_overlay(
        transcript_snippet="we were trapped and almost died",
        game_name="Valorant",
        scene_type="CLUTCH",
    )
    assert len(overlay) > 5
    score = HookEngine.score_hook(overlay)
    assert score["overall_score"] >= 65


def test_title_linter_validation_and_cleaning():
    """Verifies mobile truncation detection, spam casing limits, and title formatting."""
    # Overly long title with shouting and vague buzzwords
    bad_title = "INSANE CRAZY MASSIVE UNBELIEVABLE GAMEPLAY IN MINECRAFT THAT WILL BLOW YOUR MIND COMPLETELY"
    lint_res = TitleLinter.lint_title(bad_title)
    assert not lint_res["is_mobile_safe"]
    assert any("all-caps words" in iss for iss in lint_res["issues"])
    assert any("generic buzzwords" in iss for iss in lint_res["issues"])

    # Clean, concise title
    clean_title = "1v4 Clutch with 1 HP Left"
    clean_res = TitleLinter.lint_title(clean_title)
    assert clean_res["is_mobile_safe"]
    assert clean_res["score"] > 60

    # Auto-formatter
    formatted = TitleLinter.clean_and_format_title("INSANE CRAZY ACE IN VALORANT")
    assert "#Shorts" in formatted
    assert len([w for w in formatted.split() if w.isupper() and not w.startswith("#")]) <= 2


def test_retention_diagnostics_drop_off_cliffs():
    """Verifies retention parser, Hook Leak calculation, and transcript cliff correlation."""
    csv_data = """0.0, 100.0
2.5, 90.0
5.0, 82.0
10.0, 75.0
15.0, 68.0
20.0, 60.0
25.0, 42.0
30.0, 40.0
40.0, 38.0
50.0, 35.0
"""
    pts = RetentionDiagnostics.load_retention_data(csv_data)
    assert len(pts) == 10

    segments = [
        {"start_sec": 0.0, "end_sec": 10.0, "text": "Welcome to the video we are playing a game"},
        {"start_sec": 20.0, "end_sec": 28.0, "text": "Suddenly our teammate went AFK and gave up"},
    ]

    analysis = RetentionDiagnostics.analyze_retention(
        retention_data=pts,
        duration_sec=50.0,
        transcript_segments=segments,
    )

    assert "error" not in analysis
    assert analysis["hook_leak_pct"] == pytest.approx(32.0, rel=0.1)  # 100 - 68
    assert len(analysis["top_cliffs"]) > 0

    # The cliff from 20s to 25s drops 18% (60 -> 42)
    major_cliff = analysis["top_cliffs"][0]
    assert major_cliff["lost_pct"] >= 15.0
    assert "AFK" in major_cliff.get("spoken_dialogue", "")
    assert len(analysis["recommendations"]) > 0


def test_channel_playbook_evolution(tmp_path: Path):
    """Verifies that recording clip retention dynamically trains the Playbook memory."""
    pb_file = tmp_path / "test_playbook.json"
    playbook = ChannelPlaybook(playbook_path=pb_file)

    # Initial recommendations
    init_recs = playbook.get_recommendations()
    assert "recommended_layout" in init_recs

    # Record winning clip for LAYOUT_4_3_BLUR_FIT with 88% retention
    playbook.record_clip_performance(
        clip_id="win_clip_01",
        layout_mode="LAYOUT_4_3_BLUR_FIT",
        caption_theme="MRBEAST_YELLOW",
        duration_sec=35.0,
        retention_pct=88.0,
        views=5000,
        hook_leak_pct=12.0,
    )

    # Record mediocre clip for LAYOUT_A_PAN_SCAN with 55% retention
    playbook.record_clip_performance(
        clip_id="med_clip_02",
        layout_mode="LAYOUT_A_PAN_SCAN",
        caption_theme="CLEAN_WHITE",
        duration_sec=60.0,
        retention_pct=55.0,
        views=800,
        hook_leak_pct=38.0,
    )

    assert playbook.data["total_analyzed_clips"] == 2
    recs = playbook.get_recommendations()
    # LAYOUT_4_3_BLUR_FIT should be recommended because it has highest retention
    assert recs["recommended_layout"] == "LAYOUT_4_3_BLUR_FIT"
    assert recs["recommended_theme"] == "MRBEAST_YELLOW"
    assert recs["recommended_min_duration_sec"] <= 35.0 <= recs["recommended_max_duration_sec"]

    # Verify persistence by reloading
    reloaded = ChannelPlaybook(playbook_path=pb_file)
    assert reloaded.data["total_analyzed_clips"] == 2
    assert reloaded.get_recommendations()["recommended_layout"] == "LAYOUT_4_3_BLUR_FIT"


def test_cookie_manager_downloader_separation(tmp_path: Path):
    """Verifies downloader_cookies.txt takes precedence and keeps credentials isolated."""
    downloader_file = tmp_path / "downloader_cookies.txt"
    legacy_file = tmp_path / "cookies.txt"

    # With neither existing, default resolve returns default
    resolved = CookieManager.resolve_cookie_file(downloader_file)
    assert resolved == downloader_file

    # Create dummy netscape cookie in downloader_cookies
    downloader_file.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2147483647\tLOGIN_INFO\tauth_tok\n")
    status = CookieManager.get_cookie_status(downloader_file)
    assert status["exists"]
    assert status["has_login_info"]
    assert status["count"] == 1


def test_youtube_uploader_telemetry_query(tmp_path: Path):
    """Verifies YouTube uploader telemetry fetch handles unauthenticated and development mode."""
    uploader = YouTubeUploader(
        client_secrets_path=tmp_path / "secrets.json",
        token_path=tmp_path / "token.json",
    )
    # Unauthenticated
    unauth = uploader.fetch_channel_shorts_analytics()
    assert not unauth["success"]
    assert "not authenticated" in unauth["error"].lower()

    # With mock token
    (tmp_path / "token.json").write_text(json.dumps({"account": "test@domain.com"}))
    auth_res = uploader.fetch_channel_shorts_analytics()
    assert auth_res["success"]
    assert "shorts" in auth_res


def test_ass_compiler_with_hook_overlay(tmp_path: Path):
    """Verifies that ASSCompiler renders the HookOverlay style and event."""
    ass_out = tmp_path / "test_hook.ass"
    chunks = [
        CaptionChunkDTO(
            start_sec=1.0,
            end_sec=3.0,
            text="hello world",
            words=[
                TranscriptWordDTO(word="hello", start_sec=1.0, end_sec=2.0),
                TranscriptWordDTO(word="world", start_sec=2.0, end_sec=3.0),
            ],
        )
    ]

    ASSCompiler.compile_ass(
        chunks=chunks,
        mode=CaptionMode.BURNED_IN_ANIMATED,
        output_path=ass_out,
        hook_overlay_text="WAIT FOR THE INSTANT KARMA 💀",
        hook_overlay_duration_sec=2.5,
    )

    content = ass_out.read_text(encoding="utf-8")
    assert "Style: HookOverlay" in content
    assert "WAIT FOR THE INSTANT KARMA 💀" in content
    assert "Dialogue: 1,0:00:00.00,0:00:02.50,HookOverlay" in content


def test_agent_toolkit_briefing_and_retention_audit(tmp_path: Path):
    """Verifies AgentToolkit retention auditing and executive briefing."""
    toolkit = AgentToolkit(project_root=tmp_path)

    # Initial briefing
    briefing = toolkit.get_channel_performance_briefing()
    assert "recommendations" in briefing
    assert "top_performing_layouts" in briefing

    # Run retention audit
    csv_str = "0.0, 100\n5.0, 85\n10.0, 75\n20.0, 70\n30.0, 68\n40.0, 65"
    audit_res = toolkit.audit_retention_and_update_playbook(
        retention_csv_or_text=csv_str,
        clip_id="test_clip_audit_01",
        duration_sec=40.0,
        layout_mode="LAYOUT_4_3_BLUR_FIT",
        caption_theme="MRBEAST_YELLOW",
    )

    assert audit_res["clip_id"] == "test_clip_audit_01"
    assert "audit" in audit_res
    assert audit_res["playbook_total_analyzed"] >= 1
