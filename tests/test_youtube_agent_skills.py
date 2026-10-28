import json
import tempfile
from pathlib import Path
import pytest
try:
    from src.skills import youtube_agent
except ImportError:
    from shorts_factory.src.skills import youtube_agent


def test_hookscore_evaluation():
    # Strong hook with specific numbers and address
    strong_hook = "97% of creators quit before video 30. Here is what you must do instead."
    res = youtube_agent.score_hook(strong_hook)
    assert res.verdict_score >= 50
    assert "SPECIFICITY" in res.properties
    assert res.formula_name != ""

    # Test ranking multiple hooks
    hooks = [
        "Hey guys welcome back today I am doing a video",
        "Stop making this 1 combat mistake in Phantom Blade Zero right now.",
        "Watch this gameplay clip"
    ]
    ranked = youtube_agent.rank_hooks(hooks)
    assert len(ranked) == 3
    # The combat mistake hook should beat the generic intro hook
    assert ranked[0].verdict_score > ranked[-1].verdict_score


def test_title_and_thumbnail_linting():
    # Good mobile-safe title + distinct thumbnail text
    good_title = "Impossible 5-Star Police Escape in GTA"
    good_thumb = "5 STAR ESCAPE"
    res = youtube_agent.lint_title_and_thumbnail(good_title, good_thumb)
    assert res.char_count <= 40
    assert res.mobile_safe is True
    assert res.score >= 50

    # Bad title: too long, repeats thumbnail, shouting
    bad_title = "AMAZING INCREDIBLE INSANE CRAZY HUGE MASSIVE 100 PERCENT SECRET TRICK TO BEAT EVERY ENEMY IN PHANTOM BLADE ZERO"
    bad_thumb = "AMAZING INCREDIBLE SECRET TRICK"
    bad_res = youtube_agent.lint_title_and_thumbnail(bad_title, bad_thumb)
    assert bad_res.mobile_safe is False
    assert any(issue["kind"] == "duplicate" for issue in bad_res.issues)
    assert bad_res.score < res.score


def test_deadair_detector():
    with tempfile.NamedTemporaryFile("w", suffix=".srt", delete=False, encoding="utf-8") as f:
        f.write("""1
00:00:01,000 --> 00:00:03,000
Nobody believed he could survive this boss duel.

2
00:00:05,500 --> 00:00:06,000
um, like

3
00:00:07,000 --> 00:00:10,000
Watch what happens when he counters the tiger boss.
""")
        temp_path = f.name

    try:
        res = youtube_agent.detect_dead_air(temp_path, floor=0.45)
        assert res.cuts_count >= 1
        assert res.removed_sec > 0.0
        # Filler cue ("um, like") should be detected
        kinds = [c["kind"] for c in res.cuts]
        assert "DEAD" in kinds or "FILLER" in kinds
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_swipe_viral_outliers():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        data = [
            {"channel": "GamerA", "title": "Regular Game 1", "views": 10000, "url": "url1"},
            {"channel": "GamerA", "title": "Regular Game 2", "views": 12000, "url": "url2"},
            {"channel": "GamerA", "title": "Regular Game 3", "views": 11000, "url": "url3"},
            {"channel": "GamerA", "title": "This 1 Parry Changed Everything in PBZ", "views": 50000, "url": "url4"},
            {"channel": "ThinChannel", "title": "Solo Video", "views": 99999, "url": "url5"},
        ]
        json.dump(data, f)
        temp_path = f.name

    try:
        res = youtube_agent.find_viral_outliers(temp_path, min_multiple=2.0)
        assert len(res.outliers) == 1
        assert res.outliers[0]["channel"] == "GamerA"
        assert res.outliers[0]["multiple"] >= 4.0
        # Thin channel should be flagged
        assert len(res.skipped_thin_channels) == 1
    finally:
        Path(temp_path).unlink(missing_ok=True)
