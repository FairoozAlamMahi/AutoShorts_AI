"""Phase 5 Automated Tests: Crash Recovery, Edge-Case Hardening & Offline Certification."""
from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path
import pytest

from src.config.schema import DiscoveryMode, CaptionMode, LayoutMode, PreRunToggles
from src.core.dto import JobRequestDTO, TranscriptDTO, TranscriptSegmentDTO, TranscriptWordDTO
from src.core.database import DatabaseManager
from src.core.resource_guard import ResourceGuard
from src.providers.registry import ModelRegistry
from src.core.orchestrator import JobOrchestrator
from src.ingest.media_inspector import MediaInspector
from tests.synthetic_media_factory import SyntheticMediaFactory


@pytest.fixture
def test_orchestrator(tmp_path: Path) -> JobOrchestrator:
    db = DatabaseManager(db_path=tmp_path / "recovery_test.db")
    res_guard = ResourceGuard(scratch_dir=tmp_path / "scratch")
    reg = ModelRegistry(registry_path=tmp_path / "models_reg.json")
    return JobOrchestrator(
        db=db,
        resource_guard=res_guard,
        model_registry=reg,
        scratch_dir=tmp_path / "scratch",
        export_dir=tmp_path / "exports",
    )


class TestCrashRecoveryAndCheckpoints:
    """Tests resuming an interrupted job from stage checkpoints without re-running earlier stages."""

    def test_resume_from_transcription_checkpoint(self, test_orchestrator: JobOrchestrator, tmp_path: Path) -> None:
        # Create test video
        video_path = tmp_path / "crash_test.mp4"
        SyntheticMediaFactory.create_test_video(video_path, duration_sec=25.0, has_audio=True)

        job_id = "job_crash_001"
        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.FULL_AUTO,
            captions_mode=CaptionMode.BURNED_IN_ANIMATED,
            target_clip_count=1,
            min_duration_sec=18.0,
            max_duration_sec=20.0,
        )

        req = JobRequestDTO(job_id=job_id, source_path_or_url=str(video_path), toggles=toggles, created_at_iso="2026-10-25T00:00:00Z")
        test_orchestrator.db.create_job(req)
        test_orchestrator.db.register_source(source_id=job_id, file_path_or_url=str(video_path))

        # Simulate pre-existing cached transcript from completed Stage 2
        cached_words = [
            TranscriptWordDTO(word="CRAZY", start_sec=2.0, end_sec=2.5),
            TranscriptWordDTO(word="MOMENT", start_sec=2.5, end_sec=3.0),
        ]
        cached_transcript = TranscriptDTO(
            segments=[TranscriptSegmentDTO(id=0, start_sec=2.0, end_sec=3.0, text="CRAZY MOMENT", words=cached_words)],
            speech_coverage_ratio=0.5,
        )

        job_scratch = test_orchestrator.scratch_dir / job_id
        job_scratch.mkdir(parents=True, exist_ok=True)
        (job_scratch / "transcript.json").write_text(cached_transcript.model_dump_json(indent=2), encoding="utf-8")

        # Track stage progression
        stages_hit = []
        def progress_tracker(stage: str, pct: float) -> None:
            stages_hit.append(stage)

        # Resume job
        outputs = test_orchestrator.resume_job(job_id, progress_callback=progress_tracker)

        assert len(outputs) == 1
        assert outputs[0].exists()
        # Must have loaded cached Stage 2 transcript rather than re-running
        assert "STAGE_2_TRANSCRIPTION_CACHED" in stages_hit
        assert "COMPLETED" in stages_hit


class TestEdgeCaseHardening:
    """Tests pipeline behavior on silent videos and Variable Frame Rate (VFR) media."""

    def test_silent_video_pipeline(self, test_orchestrator: JobOrchestrator, tmp_path: Path) -> None:
        silent_video = tmp_path / "pure_silent.mp4"
        SyntheticMediaFactory.create_silent_video(silent_video, duration_sec=20.0)

        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.FULL_AUTO,
            captions_mode=CaptionMode.NONE,
            target_clip_count=1,
            min_duration_sec=18.0,
            max_duration_sec=20.0,
        )
        req = JobRequestDTO(job_id="job_silent", source_path_or_url=str(silent_video), toggles=toggles, created_at_iso="2026-10-25T00:00:00Z")
        outputs = test_orchestrator.run_job(req)

        assert len(outputs) == 1
        meta = MediaInspector().inspect(outputs[0])
        assert meta.width == 1080
        assert meta.height == 1920
        assert meta.has_audio is False

    def test_vfr_synchronization(self, test_orchestrator: JobOrchestrator, tmp_path: Path) -> None:
        vfr_video = tmp_path / "vfr_source.mp4"
        SyntheticMediaFactory.create_vfr_video(vfr_video, duration_sec=20.0)

        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.FULL_AUTO,
            captions_mode=CaptionMode.NONE,
            target_clip_count=1,
            min_duration_sec=18.0,
            max_duration_sec=20.0,
        )
        req = JobRequestDTO(job_id="job_vfr", source_path_or_url=str(vfr_video), toggles=toggles, created_at_iso="2026-10-25T00:00:00Z")
        outputs = test_orchestrator.run_job(req)

        assert len(outputs) == 1
        meta = MediaInspector().inspect(outputs[0])
        # Enforces constant 60 FPS
        assert meta.width == 1080
        assert meta.height == 1920
        assert abs(meta.fps - 60.0) < 1.0


class TestAirGapOfflineCertification:
    """Verifies 100% offline execution by blocking all non-loopback outbound socket connections."""

    def test_air_gapped_pipeline_execution(self, test_orchestrator: JobOrchestrator, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Monkeypatch socket.socket.connect to block outbound internet
        orig_connect = socket.socket.connect

        def guarded_connect(self, address):
            host = address[0]
            if host not in ("127.0.0.1", "localhost", "::1"):
                raise ConnectionRefusedError(f"AIR-GAP BLOCK: Attempted external connection to {host}")
            return orig_connect(self, address)

        monkeypatch.setattr(socket.socket, "connect", guarded_connect)

        local_video = tmp_path / "offline_sample.mp4"
        SyntheticMediaFactory.create_test_video(local_video, duration_sec=20.0, has_audio=True)

        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.FULL_AUTO,
            captions_mode=CaptionMode.NONE,
            transcription_enabled=False,  # Offline local signals + NVENC/CPU
            vlm_verification_enabled=False,
            target_clip_count=1,
            min_duration_sec=18.0,
            max_duration_sec=20.0,
        )
        req = JobRequestDTO(job_id="job_airgap", source_path_or_url=str(local_video), toggles=toggles, created_at_iso="2026-10-25T00:00:00Z")

        # Must execute cleanly with 0 external network requests
        outputs = test_orchestrator.run_job(req)
        assert len(outputs) == 1
        assert outputs[0].exists()
