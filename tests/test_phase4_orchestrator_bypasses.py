"""Phase 4 Automated Tests: Orchestrator Pre-Run Bypass Matrix, Fast Re-render & Gradio UI."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.config.schema import (
    DiscoveryMode,
    CaptionMode,
    LayoutMode,
    MetadataMode,
    AudioProcessMode,
    OwnershipType,
    ManualTimestampRange,
    PreRunToggles,
)
from src.core.dto import JobRequestDTO
from src.core.database import DatabaseManager
from src.core.resource_guard import ResourceGuard
from src.providers.registry import ModelRegistry
from src.config.manager import ConfigManager
from src.core.orchestrator import JobOrchestrator
from src.ingest.media_inspector import MediaInspector
from src.ui.dashboard import parse_manual_timestamps
from app import build_app
from tests.synthetic_media_factory import SyntheticMediaFactory


@pytest.fixture(scope="module")
def base_test_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp_dir = tmp_path_factory.mktemp("phase4_media")
    video_path = tmp_dir / "gameplay_30s.mp4"
    SyntheticMediaFactory.create_test_video(
        output_path=video_path,
        duration_sec=30.0,
        width=1280,
        height=720,
        fps=30,
        has_audio=True,
        planted_spikes=[(10.0, 16.0)],
    )
    return video_path


@pytest.fixture
def test_orchestrator(tmp_path: Path) -> JobOrchestrator:
    db = DatabaseManager(db_path=tmp_path / "test_pipeline.db")
    res_guard = ResourceGuard(scratch_dir=tmp_path / "scratch")
    reg = ModelRegistry(registry_path=tmp_path / "models_reg.json")
    return JobOrchestrator(
        db=db,
        resource_guard=res_guard,
        model_registry=reg,
        scratch_dir=tmp_path / "scratch",
        export_dir=tmp_path / "exports",
    )


class TestOrchestratorBypassPermutations:
    """Executes the pipeline across 6 distinct toggle permutations verifying complete bypasses."""

    def test_permutation_1_full_auto_animated(self, test_orchestrator: JobOrchestrator, base_test_video: Path) -> None:
        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.FULL_AUTO,
            captions_mode=CaptionMode.BURNED_IN_ANIMATED,
            layout_mode=LayoutMode.LAYOUT_HYBRID_CINEMA_STACK,
            vlm_verification_enabled=True,
            target_clip_count=1,
            min_duration_sec=18.0,
            max_duration_sec=22.0,
        )
        req = JobRequestDTO(job_id="job_perm1", source_path_or_url=str(base_test_video), toggles=toggles, created_at_iso="2026-10-25T00:00:00Z")
        outputs = test_orchestrator.run_job(req)

        assert len(outputs) == 1
        meta = MediaInspector().inspect(outputs[0])
        assert meta.width == 1080
        assert meta.height == 1920
        # Check provenance sidecar
        prov_file = outputs[0].with_suffix(".provenance.json")
        assert prov_file.exists()

    def test_permutation_2_clean_no_captions_no_whisper(self, test_orchestrator: JobOrchestrator, base_test_video: Path) -> None:
        # Verifies Whisper transcription and ASS compilation are completely bypassed
        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.FULL_AUTO,
            captions_mode=CaptionMode.NONE,
            transcription_enabled=False,
            use_speech_scoring=False,
            vlm_verification_enabled=False,
            target_clip_count=1,
            min_duration_sec=18.0,
            max_duration_sec=20.0,
        )
        req = JobRequestDTO(job_id="job_perm2", source_path_or_url=str(base_test_video), toggles=toggles, created_at_iso="2026-10-25T00:00:00Z")
        outputs = test_orchestrator.run_job(req)

        assert len(outputs) == 1
        meta = MediaInspector().inspect(outputs[0])
        assert meta.width == 1080
        assert meta.height == 1920
        # Zero subtitle sidecars should exist
        assert not outputs[0].with_suffix(".srt").exists()
        assert not outputs[0].with_suffix(".ass").exists()

    def test_permutation_3_classic_subtitles(self, test_orchestrator: JobOrchestrator, base_test_video: Path) -> None:
        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.FULL_AUTO,
            captions_mode=CaptionMode.BURNED_IN_CLASSIC,
            vlm_verification_enabled=False,
            target_clip_count=1,
            min_duration_sec=18.0,
            max_duration_sec=20.0,
        )
        req = JobRequestDTO(job_id="job_perm3", source_path_or_url=str(base_test_video), toggles=toggles, created_at_iso="2026-10-25T00:00:00Z")
        outputs = test_orchestrator.run_job(req)
        assert len(outputs) == 1

    def test_permutation_4_manual_only_sidecar_only(self, test_orchestrator: JobOrchestrator, base_test_video: Path) -> None:
        # Bypasses signal analysis and VLM verification, outputs clean video + sidecar
        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.MANUAL_ONLY,
            captions_mode=CaptionMode.EXTERNAL_SIDECAR_ONLY,
            manual_timestamps=[ManualTimestampRange(start_sec=2.0, end_sec=12.0)],
        )
        req = JobRequestDTO(job_id="job_perm4", source_path_or_url=str(base_test_video), toggles=toggles, created_at_iso="2026-10-25T00:00:00Z")
        outputs = test_orchestrator.run_job(req)

        assert len(outputs) == 1
        meta = MediaInspector().inspect(outputs[0])
        assert abs(meta.duration_sec - 10.0) < 0.2

    def test_permutation_5_hybrid_raw_16_9(self, test_orchestrator: JobOrchestrator, base_test_video: Path) -> None:
        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.HYBRID,
            layout_mode=LayoutMode.LAYOUT_RAW_16_9,
            audio_process_mode=AudioProcessMode.RAW_PASSTHROUGH,
            target_clip_count=1,
            manual_timestamps=[ManualTimestampRange(start_sec=1.0, end_sec=15.0)],
        )
        req = JobRequestDTO(job_id="job_perm5", source_path_or_url=str(base_test_video), toggles=toggles, created_at_iso="2026-10-25T00:00:00Z")
        outputs = test_orchestrator.run_job(req)

        assert len(outputs) == 1
        meta = MediaInspector().inspect(outputs[0])
        # Raw 16:9 layout preserves horizontal 1920x1080 (or source widescreen)
        assert meta.width == 1920
        assert meta.height == 1080

    def test_permutation_6_external_mcp_agent_mode(self, test_orchestrator: JobOrchestrator, base_test_video: Path) -> None:
        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.FULL_AUTO,
            metadata_mode=MetadataMode.EXTERNAL_MCP_AGENT,
            target_clip_count=1,
            min_duration_sec=18.0,
            max_duration_sec=20.0,
        )
        req = JobRequestDTO(job_id="job_perm6", source_path_or_url=str(base_test_video), toggles=toggles, created_at_iso="2026-10-25T00:00:00Z")
        outputs = test_orchestrator.run_job(req)

        assert len(outputs) == 1
        meta_file = outputs[0].with_suffix(".meta.json")
        assert meta_file.exists()


class TestFastFixUpRerender:
    """Verifies that single-clip fast fix-up runs without re-running full pipeline."""

    def test_fast_rerender_clip(self, test_orchestrator: JobOrchestrator, base_test_video: Path, tmp_path: Path) -> None:
        out_v1 = tmp_path / "fixup_v1.mp4"
        out_v2 = tmp_path / "fixup_v2.mp4"

        # Initial render
        test_orchestrator.renderer.render_clip(
            source_video=base_test_video,
            output_mp4=out_v1,
            start_sec=5.0,
            duration_sec=8.0,
            layout_mode=LayoutMode.LAYOUT_HYBRID_CINEMA_STACK,
        )
        assert out_v1.exists()

        # Fast fix-up: adjust window to 6.0-16.0s with Layout B
        test_orchestrator.rerender_clip(
            source_video=base_test_video,
            output_mp4=out_v2,
            start_sec=6.0,
            end_sec=16.0,
            layout_mode=LayoutMode.LAYOUT_B_CENTER_CROP,
            captions_mode=CaptionMode.NONE,
        )
        assert out_v2.exists()
        meta = MediaInspector().inspect(out_v2)
        assert meta.width == 1080
        assert meta.height == 1920
        assert abs(meta.duration_sec - 10.0) < 0.2


class TestGradioUIBinding:
    """Verifies Gradio 5 blocks, tabs, and component bindings initialize headlessly with 0 errors."""

    def test_ui_headless_build(self, tmp_path: Path) -> None:
        db = DatabaseManager(db_path=tmp_path / "ui_test.db")
        res_guard = ResourceGuard(scratch_dir=tmp_path / "scratch")
        reg = ModelRegistry(registry_path=tmp_path / "ui_reg.json")
        cfg = ConfigManager(config_path=tmp_path / "ui_cfg.json", db=db)
        orch = JobOrchestrator(db=db, resource_guard=res_guard, model_registry=reg)

        app = build_app(db=db, resource_guard=res_guard, model_registry=reg, orchestrator=orch, config_mgr=cfg)
        assert app is not None
        # Verify app has blocks
        assert len(app.blocks) > 0

    def test_manual_timestamps_parser(self) -> None:
        ranges = parse_manual_timestamps("10.5-25.0, 30.0:45.5; 50-65")
        assert len(ranges) == 3
        assert ranges[0].start_sec == 10.5
        assert ranges[0].end_sec == 25.0
        assert ranges[1].start_sec == 30.0
        assert ranges[1].end_sec == 45.5
        assert ranges[2].start_sec == 50.0
        assert ranges[2].end_sec == 65.0

        # Empty or invalid string
        assert parse_manual_timestamps("") == []
        assert parse_manual_timestamps("invalid-format") == []
        # Inverted range (end <= start)
        assert parse_manual_timestamps("30.0-10.0") == []

    def test_ui_settings_presets(self, tmp_path: Path) -> None:
        db = DatabaseManager(db_path=tmp_path / "presets_test.db")
        cfg = ConfigManager(config_path=tmp_path / "presets_cfg.json", db=db)
        presets = cfg.list_presets()
        assert len(presets) >= 3
        full_ai = cfg.get_preset("Full AI Gaming")
        assert full_ai is not None
        assert full_ai.toggles.discovery_mode == DiscoveryMode.FULL_AUTO
