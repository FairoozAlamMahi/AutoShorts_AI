"""Unit and integration tests for newly implemented features:
1. YouTube Uploader & Scheduler
2. Facecam Split Layout
3. Dynamic BGM Auto-Ducking
4. Caption Themes & Font Sizing
5. Auto-Thumbnail Extraction
6. Batch Queue Processing
"""
import json
import pytest
from pathlib import Path
import numpy as np

from src.config.schema import (
    LayoutMode,
    FacecamPosition,
    CaptionMode,
    CaptionTheme,
    PreRunToggles,
    DiscoveryMode,
    OwnershipType,
    AudioProcessMode,
    MetadataMode,
    SceneCategory,
)
from src.rendering.layout_builder import LayoutBuilder
from src.rendering.ffmpeg_renderer import FFmpegRenderer
from src.captions.ass_compiler import ASSCompiler
from src.captions.phrase_chunker import CaptionChunkDTO
from src.core.dto import JobRequestDTO, TranscriptWordDTO, TranscriptSegmentDTO, TranscriptDTO, CandidateClipDTO
from src.core.orchestrator import JobOrchestrator
from src.core.youtube_uploader import YouTubeUploader
from src.core.database import DatabaseManager
from src.core.resource_guard import ResourceGuard
from src.providers.registry import ModelRegistry
from src.analysis.scene_classifier import MultimodalSceneClassifier, NarrativeBoundaryRefiner
from src.agent_toolkit import AgentToolkit
from tests.synthetic_media_factory import SyntheticMediaFactory


def test_caption_themes_and_font_sizes(tmp_path: Path):
    """Verifies that ASSCompiler compiles all themes and font sizes correctly."""
    words = [
        TranscriptWordDTO(word="INSANE", start_sec=0.1, end_sec=0.4),
        TranscriptWordDTO(word="CLUTCH!", start_sec=0.45, end_sec=0.8),
    ]
    chunks = [CaptionChunkDTO(start_sec=0.1, end_sec=0.8, text="INSANE CLUTCH!", words=words)]

    for theme in CaptionTheme:
        ass_file = tmp_path / f"caption_{theme.value}.ass"
        ASSCompiler.compile_ass(
            chunks=chunks,
            mode=CaptionMode.BURNED_IN_ANIMATED,
            output_path=ass_file,
            theme=theme,
            font_size=72,
        )
        assert ass_file.exists()
        content = ass_file.read_text(encoding="utf-8")
        assert "Fontsize, 72" in content or ",72," in content
        assert "Style: AnimatedPop" in content
        assert "INSANE" in content


def test_facecam_split_filtergraph():
    """Verifies filtergraph construction for Streamer Split layout."""
    for corner in FacecamPosition:
        fg = LayoutBuilder.build_filtergraph(
            layout_mode=LayoutMode.LAYOUT_FACECAM_SPLIT,
            facecam_pos=corner,
        )
        assert "scale=1080:720" in fg
        assert "scale=1080:1200" in fg
        assert "crop=" in fg
        assert "vstack=inputs=2" in fg


def test_ffmpeg_facecam_split_render(tmp_path: Path):
    """Verifies actual video rendering using LAYOUT_FACECAM_SPLIT."""
    src_video = SyntheticMediaFactory.create_test_video(tmp_path / "stream.mp4", duration_sec=3.0, has_audio=True)
    out_video = tmp_path / "stream_split.mp4"

    renderer = FFmpegRenderer()
    renderer.render_clip(
        source_video=src_video,
        output_mp4=out_video,
        start_sec=0.0,
        duration_sec=2.0,
        layout_mode=LayoutMode.LAYOUT_FACECAM_SPLIT,
        facecam_pos=FacecamPosition.TOP_RIGHT,
    )
    assert out_video.exists()
    assert out_video.stat().st_size > 1000

    info = renderer.inspector.inspect(out_video)
    assert info.width == 1080
    assert info.height == 1920


def test_ffmpeg_bgm_ducking_render(tmp_path: Path):
    """Verifies rendering with background music track auto-ducking."""
    src_video = SyntheticMediaFactory.create_test_video(tmp_path / "gameplay.mp4", duration_sec=3.0, has_audio=True)
    bgm_music = Path("shorts_factory/assets/music/ambient_lofi.mp3").resolve()
    if not bgm_music.exists():
        bgm_music = Path("assets/music/ambient_lofi.mp3").resolve()

    out_video = tmp_path / "ducked_output.mp4"
    renderer = FFmpegRenderer()
    renderer.render_clip(
        source_video=src_video,
        output_mp4=out_video,
        start_sec=0.0,
        duration_sec=2.0,
        bgm_path=bgm_music,
        bgm_volume_duck_db=-14.0,
    )
    assert out_video.exists()
    info = renderer.inspector.inspect(out_video)
    assert info.has_audio is True


def test_auto_thumbnail_generation(tmp_path: Path):
    """Verifies cover thumbnail extraction from rendered short."""
    src_video = SyntheticMediaFactory.create_test_video(tmp_path / "thumb_test.mp4", duration_sec=3.0)
    thumb_out = tmp_path / "thumb_test.thumb.jpg"

    renderer = FFmpegRenderer()
    res = renderer.generate_thumbnail(src_video, thumb_out, timestamp_sec=1.0)
    assert res.exists()
    assert res.stat().st_size > 500


def test_youtube_uploader_validation(tmp_path: Path):
    """Verifies YouTube uploader configuration, secrets saving, and validation."""
    secrets_file = tmp_path / "secrets.json"
    token_file = tmp_path / "token.json"
    uploader = YouTubeUploader(client_secrets_path=secrets_file, token_path=token_file)

    assert not uploader.is_configured()
    assert not uploader.is_authenticated()

    # Save mock client secrets
    secrets_payload = json.dumps({"installed": {"client_id": "test_id", "client_secret": "test_sec"}})
    ok, msg = uploader.save_client_secrets(secrets_payload)
    assert ok is True
    assert uploader.is_configured()

    # Test upload validation (fallback / mock mode)
    dummy_video = tmp_path / "test_upload.mp4"
    dummy_video.write_bytes(b"dummy mp4 content")

    res = uploader.upload_short(
        video_path=dummy_video,
        title="EPIC Clutch Play",
        description="Check this out! #gaming",
        tags=["action", "gaming"],
        privacy_status="private",
    )
    assert res["success"] is True
    assert "https://www.youtube.com/shorts/" in res["url"]


def test_orchestrator_batch_queue(tmp_path: Path):
    """Verifies JobOrchestrator.run_batch sequentially runs multiple video requests."""
    db_path = tmp_path / "batch_test.db"
    db = DatabaseManager(db_path=db_path)
    guard = ResourceGuard()
    reg = ModelRegistry()

    src1 = SyntheticMediaFactory.create_test_video(tmp_path / "vid1.mp4", duration_sec=16.0)
    src2 = SyntheticMediaFactory.create_test_video(tmp_path / "vid2.mp4", duration_sec=16.0)

    toggles = PreRunToggles(
        discovery_mode=DiscoveryMode.FULL_AUTO,
        captions_mode=CaptionMode.NONE,
        layout_mode=LayoutMode.LAYOUT_A_BLUR_FIT,
        metadata_mode=MetadataMode.OFF,
        audio_process_mode=AudioProcessMode.RAW_PASSTHROUGH,
        transcription_enabled=False,
        vlm_verification_enabled=False,
        target_clip_count=1,
        min_duration_sec=10.0,
        max_duration_sec=15.0,
    )

    req1 = JobRequestDTO(job_id="batch_job_1", source_path_or_url=str(src1), toggles=toggles, created_at_iso="2026-10-25T12:00:00Z")
    req2 = JobRequestDTO(job_id="batch_job_2", source_path_or_url=str(src2), toggles=toggles, created_at_iso="2026-10-25T12:00:00Z")

    orchestrator = JobOrchestrator(
        db=db,
        resource_guard=guard,
        model_registry=reg,
        scratch_dir=tmp_path / "scratch",
        export_dir=tmp_path / "exports",
    )

    progress_events = []
    def _cb(stage, pct, cur, tot):
        progress_events.append((stage, cur, tot))

    results = orchestrator.run_batch([req1, req2], progress_callback=_cb)
    assert "batch_job_1" in results
    assert "batch_job_2" in results
    assert len(results["batch_job_1"]) >= 1
    assert len(results["batch_job_2"]) >= 1
    assert len(progress_events) > 0
    # Check that thumbnail was generated alongside clip
    thumb = Path(results["batch_job_1"][0]).with_suffix(".thumb.jpg")
    assert thumb.exists()


def test_layout_4_3_filtergraphs():
    """Verifies FFmpeg filtergraphs for 4:3 Blur Fit ('Show It All') and 4:3 Horizontal Center Crop."""
    fg_blur = LayoutBuilder.build_filtergraph(layout_mode=LayoutMode.LAYOUT_4_3_BLUR_FIT)
    assert "scale=1080:1920" in fg_blur
    assert "scale=1080:1440" in fg_blur
    assert "boxblur=28:2" in fg_blur
    assert "overlay=(W-w)/2:(H-h)/2" in fg_blur

    fg_crop = LayoutBuilder.build_filtergraph(layout_mode=LayoutMode.LAYOUT_4_3_HORIZONTAL)
    assert "crop=ih*4/3:ih" in fg_crop
    assert "scale=1440:1080" in fg_crop


def test_layout_dimensions():
    """Verifies LayoutBuilder.get_dimensions returns accurate resolution pairs."""
    assert LayoutBuilder.get_dimensions(LayoutMode.LAYOUT_4_3_BLUR_FIT) == (1080, 1920)
    assert LayoutBuilder.get_dimensions(LayoutMode.LAYOUT_4_3_HORIZONTAL) == (1440, 1080)
    assert LayoutBuilder.get_dimensions(LayoutMode.LAYOUT_RAW_16_9) == (1920, 1080)
    assert LayoutBuilder.get_dimensions(LayoutMode.LAYOUT_HYBRID_CINEMA_STACK) == (1080, 1920)
    assert LayoutBuilder.get_dimensions(LayoutMode.LAYOUT_A_BLUR_FIT) == (1080, 1920)
    assert LayoutBuilder.get_dimensions(LayoutMode.LAYOUT_B_CENTER_CROP) == (1080, 1920)
    assert LayoutBuilder.get_dimensions(LayoutMode.LAYOUT_FACECAM_SPLIT) == (1080, 1920)


def test_ass_compiler_4_3_aspect_ratio(tmp_path: Path):
    """Verifies that ASSCompiler adapts PlayRes and margins for 4:3 resolutions."""
    words = [TranscriptWordDTO(word="SHOW", start_sec=0.1, end_sec=0.4), TranscriptWordDTO(word="ALL", start_sec=0.45, end_sec=0.8)]
    chunks = [CaptionChunkDTO(start_sec=0.1, end_sec=0.8, text="SHOW ALL", words=words)]
    ass_file = tmp_path / "captions_4_3.ass"

    ASSCompiler.compile_ass(
        chunks=chunks,
        mode=CaptionMode.BURNED_IN_ANIMATED,
        output_path=ass_file,
        layout_mode=LayoutMode.LAYOUT_4_3_HORIZONTAL,
    )
    assert ass_file.exists()
    content = ass_file.read_text(encoding="utf-8")
    assert "PlayResX: 1440" in content
    assert "PlayResY: 1080" in content
    assert ",160,1" in content


def test_ffmpeg_4_3_renders(tmp_path: Path):
    """Verifies physical rendering of 4:3 Blur Fit (1080x1920) and 4:3 Horizontal (1440x1080) with MediaInspector."""
    src_video = SyntheticMediaFactory.create_test_video(tmp_path / "source_16_9.mp4", duration_sec=3.0, has_audio=True)
    renderer = FFmpegRenderer()

    # 1. Test 4:3 Blur Fit (Vertical 9:16 Shorts Container: 1080x1920)
    out_blur = tmp_path / "out_4_3_blur.mp4"
    renderer.render_clip(
        source_video=src_video,
        output_mp4=out_blur,
        start_sec=0.0,
        duration_sec=2.0,
        layout_mode=LayoutMode.LAYOUT_4_3_BLUR_FIT,
    )
    assert out_blur.exists()
    info_blur = renderer.inspector.inspect(out_blur)
    assert info_blur.width == 1080
    assert info_blur.height == 1920

    # 2. Test 4:3 Horizontal Crop (1440x1080)
    out_crop = tmp_path / "out_4_3_crop.mp4"
    renderer.render_clip(
        source_video=src_video,
        output_mp4=out_crop,
        start_sec=0.0,
        duration_sec=2.0,
        layout_mode=LayoutMode.LAYOUT_4_3_HORIZONTAL,
    )
    assert out_crop.exists()
    info_crop = renderer.inspector.inspect(out_crop)
    assert info_crop.width == 1440
    assert info_crop.height == 1080


def test_per_clip_rules_parsing():
    """Verifies that PreRunToggles accurately parses count shorthands and range rules."""
    # 1. Shorthand "2B, 3A" -> 2 with layout B, 3 with layout A
    parsed1 = PreRunToggles.parse_per_clip_rules("2B, 3A")
    assert parsed1[1]["layout_mode"] == LayoutMode.LAYOUT_B_CENTER_CROP
    assert parsed1[2]["layout_mode"] == LayoutMode.LAYOUT_B_CENTER_CROP
    assert parsed1[3]["layout_mode"] == LayoutMode.LAYOUT_A_BLUR_FIT
    assert parsed1[4]["layout_mode"] == LayoutMode.LAYOUT_A_BLUR_FIT
    assert parsed1[5]["layout_mode"] == LayoutMode.LAYOUT_A_BLUR_FIT

    # 2. Range rule "1-2: LAYOUT_B_CENTER_CROP, 3-5: LAYOUT_4_3_BLUR_FIT"
    parsed2 = PreRunToggles.parse_per_clip_rules("1-2: LAYOUT_B_CENTER_CROP, 3-5: LAYOUT_4_3_BLUR_FIT")
    assert parsed2[1]["layout_mode"] == LayoutMode.LAYOUT_B_CENTER_CROP
    assert parsed2[2]["layout_mode"] == LayoutMode.LAYOUT_B_CENTER_CROP
    assert parsed2[3]["layout_mode"] == LayoutMode.LAYOUT_4_3_BLUR_FIT
    assert parsed2[4]["layout_mode"] == LayoutMode.LAYOUT_4_3_BLUR_FIT
    assert parsed2[5]["layout_mode"] == LayoutMode.LAYOUT_4_3_BLUR_FIT

    # 3. Rule with themes: "1: LAYOUT_B, MRBEAST_YELLOW; 2: LAYOUT_4_3_BLUR_FIT, CLEAN_WHITE"
    parsed3 = PreRunToggles.parse_per_clip_rules("1: LAYOUT_B, MRBEAST_YELLOW; 2: LAYOUT_4_3_BLUR_FIT, CLEAN_WHITE")
    assert parsed3[1]["layout_mode"] == LayoutMode.LAYOUT_B_CENTER_CROP
    assert parsed3[1]["caption_theme"] == CaptionTheme.MRBEAST_YELLOW
    assert parsed3[2]["layout_mode"] == LayoutMode.LAYOUT_4_3_BLUR_FIT
    assert parsed3[2]["caption_theme"] == CaptionTheme.CLEAN_WHITE


def test_narrative_boundary_refiner():
    """Verifies sentence-boundary snapping to avoid mid-word cuts."""
    seg1 = TranscriptSegmentDTO(id=0, start_sec=10.2, end_sec=14.8, text="Wait wait look at that car!")
    seg2 = TranscriptSegmentDTO(id=1, start_sec=15.5, end_sec=21.0, text="Bro what was that? Are you serious?")
    seg3 = TranscriptSegmentDTO(id=2, start_sec=21.8, end_sec=28.4, text="He completely missed the turn and crashed!")
    transcript = TranscriptDTO(segments=[seg1, seg2, seg3], speech_coverage_ratio=0.85)

    # Raw candidate around 11.0 to 20.0
    start, end, note = NarrativeBoundaryRefiner.refine_bounds(
        raw_start=11.0,
        raw_end=20.0,
        transcript=transcript,
        min_duration_sec=10.0,
        max_duration_sec=30.0,
        total_duration_sec=60.0,
    )
    # Start snaps to 10.2 (start of seg1)
    assert start == 10.2
    # End snaps to after seg2 (21.0 + 0.3 = 21.3)
    assert end >= 21.0
    assert "Snapped start" in note
    assert "Snapped end" in note


def test_multimodal_scene_classifier():
    """Verifies semantic scene categorization (Action vs Comedy vs Clutch vs Dialogue)."""
    # 1. Comedy scene
    c_comedy = CandidateClipDTO(
        clip_index=1, start_sec=0.0, end_sec=20.0, duration_sec=20.0,
        peak_timestamp_sec=10.0, visual_score=0.2, acoustic_score=0.4,
    )
    tr_comedy = TranscriptDTO(
        segments=[TranscriptSegmentDTO(id=0, start_sec=0.0, end_sec=15.0, text="hahaha bro what was that lmfao he wasted himself")],
        speech_coverage_ratio=0.75,
    )
    res_comedy = MultimodalSceneClassifier.classify(c_comedy, tr_comedy)
    assert res_comedy.category == SceneCategory.COMEDY
    assert res_comedy.recommended_layout == LayoutMode.LAYOUT_4_3_BLUR_FIT
    assert res_comedy.recommended_caption_theme == CaptionTheme.TIKTOK_RED_BOX

    # 2. Action scene
    c_action = CandidateClipDTO(
        clip_index=2, start_sec=0.0, end_sec=20.0, duration_sec=20.0,
        peak_timestamp_sec=10.0, visual_score=0.6, acoustic_score=0.8,
    )
    tr_action = TranscriptDTO(
        segments=[TranscriptSegmentDTO(id=0, start_sec=0.0, end_sec=15.0, text="shoot the car drive faster cops are shooting")],
        speech_coverage_ratio=0.5,
    )
    res_action = MultimodalSceneClassifier.classify(c_action, tr_action)
    assert res_action.category == SceneCategory.ACTION
    assert res_action.recommended_layout == LayoutMode.LAYOUT_B_CENTER_CROP
    assert res_action.recommended_caption_theme == CaptionTheme.MRBEAST_YELLOW


def test_orchestrator_heterogeneous_multi_clip_customization(tmp_path: Path):
    """Verifies a single job rendering multiple clips with different layouts (e.g. 1 with B, 1 with 4:3)."""
    src_video = SyntheticMediaFactory.create_test_video(tmp_path / "long_gameplay.mp4", duration_sec=12.0, has_audio=True)

    db = DatabaseManager(db_path=str(tmp_path / "test.db"))
    guard = ResourceGuard(scratch_dir=str(tmp_path / "scratch"), disk_threshold_gb=1.0)
    reg = ModelRegistry(registry_path=str(tmp_path / "reg.json"))
    orchestrator = JobOrchestrator(
        db=db,
        resource_guard=guard,
        model_registry=reg,
        scratch_dir=tmp_path / "scratch",
        export_dir=tmp_path / "exports",
    )

    # Configure per_clip_rules: "1: LAYOUT_B_CENTER_CROP, 2: LAYOUT_4_3_BLUR_FIT"
    toggles = PreRunToggles(
        discovery_mode=DiscoveryMode.MANUAL_ONLY,
        captions_mode=CaptionMode.NONE,
        layout_mode=LayoutMode.LAYOUT_HYBRID_CINEMA_STACK,
        metadata_mode=MetadataMode.OFF,
        audio_process_mode=AudioProcessMode.RAW_PASSTHROUGH,
        transcription_enabled=False,
        vlm_verification_enabled=False,
        target_clip_count=2,
        manual_timestamps=[
            {"start_sec": 0.0, "end_sec": 2.0, "label": "Action moment"},
            {"start_sec": 3.0, "end_sec": 5.0, "label": "Full screen moment"},
        ],
        per_clip_rules="1: LAYOUT_B_CENTER_CROP, 2: LAYOUT_4_3_BLUR_FIT",
    )

    req = JobRequestDTO(job_id="custom_hetero_job", source_path_or_url=str(src_video), toggles=toggles, created_at_iso="2026-10-27T00:00:00Z")
    rendered = orchestrator.run_job(req)
    assert len(rendered) == 2

    # Check Clip 1 is Layout B (1080x1920)
    info1 = orchestrator.renderer.inspector.inspect(rendered[0])
    assert info1.width == 1080
    assert info1.height == 1920

    # Check Clip 2 is 4:3 Blur Fit (1080x1920)
    info2 = orchestrator.renderer.inspector.inspect(rendered[1])
    assert info2.width == 1080
    assert info2.height == 1920

    # Check Provenance records store effective layouts
    prov1 = json.loads(Path(rendered[0]).with_suffix(".provenance.json").read_text(encoding="utf-8"))
    prov2 = json.loads(Path(rendered[1]).with_suffix(".provenance.json").read_text(encoding="utf-8"))
    assert prov1["toggles_snapshot"]["layout_mode"] == "LAYOUT_B_CENTER_CROP"
    assert prov2["toggles_snapshot"]["layout_mode"] == "LAYOUT_4_3_BLUR_FIT"


def test_agent_toolkit_interface(tmp_path: Path):
    """Verifies AgentToolkit helper methods for dialogue boundary refinement and classification."""
    toolkit = AgentToolkit(project_root=tmp_path)
    # Refine speech boundary
    res = toolkit.refine_speech_boundary(
        raw_start=5.0,
        raw_end=15.0,
        transcript_data={
            "segments": [
                {"id": 0, "start_sec": 4.5, "end_sec": 10.0, "text": "Starting the clutch play right now"},
                {"id": 1, "start_sec": 10.5, "end_sec": 16.0, "text": "And we got the win lets go!"},
            ]
        },
        min_dur=5.0,
        max_dur=20.0,
    )
    assert res["refined_start_sec"] == 4.5
    assert res["refined_end_sec"] >= 16.0


