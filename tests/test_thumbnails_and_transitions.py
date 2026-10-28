"""Tests for ThumbnailMaker (yt-package skill) and MusicTransitionEngine."""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from PIL import Image

try:
    from src.rendering.thumbnail_maker import ThumbnailMaker, BadgeStyle
    from src.audio.music_transition_engine import MusicTransitionEngine
except ImportError:
    from shorts_factory.src.rendering.thumbnail_maker import ThumbnailMaker, BadgeStyle
    from shorts_factory.src.audio.music_transition_engine import MusicTransitionEngine


def test_thumbnail_maker_sanitize_badge_text():
    tm = ThumbnailMaker()
    # Test 3-word rule
    res = tm.sanitize_badge_text("This is way too many words for a thumbnail")
    assert len(res.split()) == 3
    assert res == "THIS IS WAY"

    # Test punctuation stripping
    res2 = tm.sanitize_badge_text("PURE CINEMA...!")
    assert res2 == "PURE CINEMA"


def test_thumbnail_maker_render_badge(tmp_path: Path):
    tm = ThumbnailMaker()
    base = Image.new("RGB", (1080, 1920), (50, 50, 50))
    graded = tm.apply_color_grading(base)
    assert graded.size == (1080, 1920)

    # Test badge rendering
    badged = tm.render_badge(graded, "PURE CINEMA", style=BadgeStyle.MRBEAST_YELLOW)
    assert badged.size == (1080, 1920)
    out_file = tmp_path / "test_thumb.jpg"
    badged.save(out_file)
    assert out_file.exists()


def test_music_transition_engine_filtergraph():
    engine = MusicTransitionEngine()
    filter_lines, extra_inputs, mix_labels = engine.build_transition_audio_filtergraph(
        has_game_audio=True,
        game_audio_label="[0:a:0?]",
        bgm_input_index=1,
        voice_input_index=2,
        vo_duration_sec=3.5,
        drop_timestamp_sec=3.8,
        pre_drop_silence_sec=0.20,
        enable_lowpass_buildup=True,
        enable_riser_buildup=True,
        enable_dual_impact=True,
        next_input_index=3,
    )

    # Verify audio filter lines are constructed properly
    full_filter = ";".join(filter_lines)
    assert "lowpass" in full_filter
    assert "eval=frame" in full_filter
    assert "adelay=" in full_filter
    assert "[game_aud]" in mix_labels
    assert "[bgm_aud]" in mix_labels
    assert "[vox_aud]" in mix_labels
    assert "[sub_aud]" in mix_labels
    assert "[hit_aud]" in mix_labels
    assert len(extra_inputs) >= 2  # sub_boom, hit_impact (and riser if >= 1.2s)
