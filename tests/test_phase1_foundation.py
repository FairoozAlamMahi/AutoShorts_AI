"""Phase 1 Automated Foundation & Contract Tests."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.config.schema import (
    DiscoveryMode,
    CaptionMode,
    LayoutMode,
    MetadataMode,
    OwnershipType,
    RightsStatus,
    ManualTimestampRange,
    PreRunToggles,
    WorkflowPreset,
)
from src.core.dto import (
    MediaInspectionDTO,
    YouTubeMetadataDTO,
    CandidateClipDTO,
    ClipMetadataDTO,
    JobRequestDTO,
)
from src.core.database import DatabaseManager
from src.core.resource_guard import ResourceGuard
from src.providers.registry import ModelRegistry, ModelEntry
from src.ingest.media_inspector import MediaInspector, CorruptMediaError
from src.ingest.rights_manager import RightsManager
from tests.synthetic_media_factory import SyntheticMediaFactory


class TestPreRunTogglesAndBypasses:
    """Tests the PreRunToggles matrix and Section 3.2 bypass logic."""

    def test_default_toggles(self) -> None:
        toggles = PreRunToggles()
        assert toggles.discovery_mode == DiscoveryMode.FULL_AUTO
        assert toggles.captions_mode == CaptionMode.BURNED_IN_ANIMATED
        assert toggles.layout_mode == LayoutMode.LAYOUT_HYBRID_CINEMA_STACK
        assert toggles.transcription_enabled is True
        assert toggles.vlm_verification_enabled is True

        # Default bypass logic
        assert toggles.should_run_transcription() is True
        assert toggles.should_run_signal_analysis() is True
        assert toggles.should_run_vlm() is True
        assert toggles.should_compile_subtitles(has_words=True) is True
        assert toggles.should_burn_in_subtitles(has_words=True) is True
        assert toggles.should_export_sidecar(has_words=True) is False
        assert toggles.should_generate_metadata() is True

    def test_captions_none_bypasses(self) -> None:
        # If captions are NONE and speech scoring is disabled
        toggles = PreRunToggles(
            captions_mode=CaptionMode.NONE,
            use_speech_scoring=False,
        )
        assert toggles.should_run_transcription() is False
        assert toggles.should_compile_subtitles(has_words=True) is False
        assert toggles.should_burn_in_subtitles(has_words=True) is False
        assert toggles.should_export_sidecar(has_words=True) is False

    def test_manual_mode_bypasses(self) -> None:
        # MANUAL_ONLY skips signal analysis and VLM verification
        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.MANUAL_ONLY,
            captions_mode=CaptionMode.EXTERNAL_SIDECAR_ONLY,
        )
        assert toggles.should_run_signal_analysis() is False
        assert toggles.should_run_vlm() is False
        assert toggles.should_compile_subtitles(has_words=True) is True
        assert toggles.should_burn_in_subtitles(has_words=True) is False
        assert toggles.should_export_sidecar(has_words=True) is True

    def test_hybrid_mode_runs_signals(self) -> None:
        toggles = PreRunToggles(discovery_mode=DiscoveryMode.HYBRID)
        assert toggles.should_run_signal_analysis() is True
        assert toggles.should_run_vlm() is True

    def test_manual_timestamp_validation(self) -> None:
        # Valid range
        valid = ManualTimestampRange(start_sec=10.0, end_sec=25.0, label="Penta kill")
        assert valid.start_sec == 10.0
        assert valid.end_sec == 25.0

        # Invalid range: end_sec <= start_sec
        with pytest.raises(ValueError):
            ManualTimestampRange(start_sec=20.0, end_sec=15.0)

        with pytest.raises(ValueError):
            ManualTimestampRange(start_sec=10.0, end_sec=10.0)

    def test_json_serialization_roundtrip(self) -> None:
        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.HYBRID,
            captions_mode=CaptionMode.BURNED_IN_PLUS_SIDECAR,
            layout_mode=LayoutMode.LAYOUT_A_BLUR_FIT,
            manual_timestamps=[ManualTimestampRange(start_sec=5.0, end_sec=20.0)],
        )
        data = toggles.model_dump_json()
        restored = PreRunToggles.model_validate_json(data)
        assert restored.discovery_mode == DiscoveryMode.HYBRID
        assert restored.captions_mode == CaptionMode.BURNED_IN_PLUS_SIDECAR
        assert len(restored.manual_timestamps) == 1
        assert restored.manual_timestamps[0].start_sec == 5.0


class TestModelRegistry:
    """Tests hot-swappable model management and persistence in models_registry.json."""

    def test_default_models_loaded(self, model_registry: ModelRegistry) -> None:
        stt_models = model_registry.list_models("stt")
        vlm_models = model_registry.list_models("vlm")

        assert len(stt_models) >= 4
        assert len(vlm_models) >= 3

        active_stt = model_registry.get_active_model("stt")
        assert active_stt.id == "faster-whisper-large-v3-turbo"

        active_vlm = model_registry.get_active_model("vlm")
        assert active_vlm.id == "qwen2.5vl:3b"

    def test_switch_active_model(self, model_registry: ModelRegistry) -> None:
        model_registry.set_active_model("stt", "faster-whisper-small.en")
        assert model_registry.get_active_model("stt").id == "faster-whisper-small.en"

        model_registry.set_active_model("vlm", "qwen2.5vl:7b")
        assert model_registry.get_active_model("vlm").id == "qwen2.5vl:7b"

        # Verify invalid switch raises error
        with pytest.raises(ValueError):
            model_registry.set_active_model("stt", "non-existent-model")

        # Verify mismatched type raises error
        with pytest.raises(ValueError):
            model_registry.set_active_model("stt", "qwen2.5vl:7b")

    def test_register_new_model_and_persistence(self, tmp_path: Path) -> None:
        reg_file = tmp_path / "persistence_registry.json"
        reg1 = ModelRegistry(registry_path=reg_file)

        new_stt = ModelEntry(
            id="custom-stt-v1",
            type="stt",
            provider="faster_whisper",
            display_name="Custom Finetuned Whisper",
            disk_size_gb=1.2,
            vram_req_mb=1500.0,
            parameters={"repo_or_size": "user/whisper-finetuned"}
        )
        new_vlm = ModelEntry(
            id="llama-3.2-vision:11b",
            type="vlm",
            provider="ollama",
            display_name="Llama 3.2 Vision 11B",
            disk_size_gb=7.9,
            vram_req_mb=8500.0,
            parameters={"model_tag": "llama3.2-vision:11b"}
        )

        reg1.register_model(new_stt)
        reg1.register_model(new_vlm)
        reg1.set_active_model("stt", "custom-stt-v1")
        reg1.set_active_model("vlm", "llama-3.2-vision:11b")

        # Reload from same file
        reg2 = ModelRegistry(registry_path=reg_file)
        assert reg2.get_active_model("stt").id == "custom-stt-v1"
        assert reg2.get_active_model("vlm").id == "llama-3.2-vision:11b"
        assert reg2.estimate_vram_mb("llama-3.2-vision:11b") == 8500.0


class TestDatabasePersistence:
    """Tests SQLite WAL database operations, jobs, sources, and presets."""

    def test_database_init_and_wal_mode(self, temp_db: DatabaseManager) -> None:
        with temp_db.get_connection() as conn:
            mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            assert mode.lower() == "wal"

    def test_preset_persistence(self, temp_db: DatabaseManager) -> None:
        toggles = PreRunToggles(discovery_mode=DiscoveryMode.MANUAL_ONLY)
        preset = WorkflowPreset(name="GTA Stunt Cuts", description="Preset for manual GTA cuts", toggles=toggles)

        temp_db.save_preset(preset)
        loaded = temp_db.get_preset("GTA Stunt Cuts")
        assert loaded is not None
        assert loaded.name == "GTA Stunt Cuts"
        assert loaded.toggles.discovery_mode == DiscoveryMode.MANUAL_ONLY

        presets_list = temp_db.list_presets()
        assert any(p.name == "GTA Stunt Cuts" for p in presets_list)

        deleted = temp_db.delete_preset("GTA Stunt Cuts")
        assert deleted is True
        assert temp_db.get_preset("GTA Stunt Cuts") is None

    def test_job_and_clip_lifecycle(self, temp_db: DatabaseManager) -> None:
        job_req = JobRequestDTO(
            job_id="job_test_001",
            source_path_or_url="videos/gameplay.mp4",
            toggles=PreRunToggles(target_clip_count=2),
            created_at_iso="2026-10-25T10:00:00Z"
        )
        temp_db.create_job(job_req)

        job = temp_db.get_job("job_test_001")
        assert job is not None
        assert job["status"] == "PENDING"
        assert job["current_stage"] == "INITIALIZED"

        # Update progress
        temp_db.update_job_status("job_test_001", status="RUNNING", stage="TRANSCRIPTION", progress_pct=25.0)
        updated_job = temp_db.get_job("job_test_001")
        assert updated_job["status"] == "RUNNING"
        assert updated_job["progress_pct"] == 25.0

        # Save clip
        candidate = CandidateClipDTO(
            clip_index=1,
            start_sec=12.0,
            end_sec=32.0,
            duration_sec=20.0,
            peak_timestamp_sec=22.0,
            composite_score=0.92,
            sub_scores={"acoustic": 0.88, "visual": 0.95}
        )
        meta = ClipMetadataDTO(
            primary_title="INSANE 1v4 CLUTCH!",
            alternative_titles=["1 HP Victory", "Clean Headshots"],
            small_description="Unbelievable clutch in Warzone #gaming #shorts",
            tags=["warzone", "clutch", "shorts"]
        )
        temp_db.save_clip("clip_001", "job_test_001", candidate, meta, "data/exports/clip_001.mp4")

        clips = temp_db.get_clips_for_job("job_test_001")
        assert len(clips) == 1
        assert clips[0]["primary_title"] == "INSANE 1v4 CLUTCH!"
        assert clips[0]["composite_score"] == 0.92


class TestResourceGuard:
    """Tests system monitoring, exclusive GPU locking, and safe scratch purging."""

    def test_ram_and_disk_snapshots(self, resource_guard: ResourceGuard) -> None:
        ram = resource_guard.get_ram_snapshot()
        assert ram["total_gb"] > 0
        assert ram["available_gb"] > 0

        disk = resource_guard.get_disk_snapshot()
        assert disk["total_gb"] > 0
        assert disk["free_gb"] > 0

        sys_snap = resource_guard.get_system_snapshot()
        assert "ram" in sys_snap
        assert "disk" in sys_snap
        assert "gpu" in sys_snap

    def test_exclusive_gpu_lease_locking(self, resource_guard: ResourceGuard) -> None:
        with resource_guard.gpu_stage_lease("WHISPER_TRANSCRIPTION") as lease1:
            assert resource_guard._active_lease_stage == "WHISPER_TRANSCRIPTION"

            # Attempting second concurrent lease must raise RuntimeError
            with pytest.raises(RuntimeError) as exc_info:
                with resource_guard.gpu_stage_lease("VLM_VERIFICATION"):
                    pass
            assert "Concurrent GPU stage lease rejected" in str(exc_info.value)

        # After exiting lease, next stage must acquire lock cleanly
        assert resource_guard._active_lease_stage is None
        with resource_guard.gpu_stage_lease("VLM_VERIFICATION"):
            assert resource_guard._active_lease_stage == "VLM_VERIFICATION"

    def test_safe_scratch_purging(self, resource_guard: ResourceGuard, temp_scratch: Path) -> None:
        job_dir = temp_scratch / "job_abc"
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "temp_audio.wav").write_bytes(b"temp wav content")

        assert (job_dir / "temp_audio.wav").exists()
        purged = resource_guard.purge_job_scratch("job_abc")
        assert purged is True
        assert not job_dir.exists()

        # Guardrails: Invalid path traversal
        with pytest.raises(ValueError):
            resource_guard.purge_job_scratch("../outside")

        with pytest.raises(ValueError):
            resource_guard.purge_job_scratch("")


class TestSyntheticMediaAndFFprobe:
    """Tests SyntheticMediaFactory generation and MediaInspector parsing."""

    def test_standard_synthetic_video_inspection(self, tmp_path: Path) -> None:
        video_path = tmp_path / "test_1080p60.mp4"
        SyntheticMediaFactory.create_test_video(
            output_path=video_path,
            duration_sec=3.0,
            width=1920,
            height=1080,
            fps=60,
            has_audio=True,
        )

        assert video_path.exists()
        inspector = MediaInspector()
        meta = inspector.inspect(video_path)

        assert meta.width == 1920
        assert meta.height == 1080
        assert abs(meta.duration_sec - 3.0) < 0.2
        assert abs(meta.fps - 60.0) < 1.0
        assert meta.has_audio is True
        assert meta.audio_codec is not None
        assert "264" in meta.video_codec.lower()

        # Check SHA256 prefix
        sha_prefix = inspector.compute_sha256_prefix(video_path)
        assert len(sha_prefix) == 16
        assert int(sha_prefix, 16) > 0

    def test_silent_video_inspection(self, tmp_path: Path) -> None:
        silent_path = tmp_path / "test_silent.mp4"
        SyntheticMediaFactory.create_silent_video(
            output_path=silent_path,
            duration_sec=2.0,
            width=1280,
            height=720,
            fps=30,
        )

        inspector = MediaInspector()
        meta = inspector.inspect(silent_path)

        assert meta.width == 1280
        assert meta.height == 720
        assert meta.has_audio is False
        assert meta.audio_codec is None

    def test_corrupt_file_rejection(self, tmp_path: Path) -> None:
        corrupt_path = tmp_path / "corrupt.mp4"
        SyntheticMediaFactory.create_corrupt_file(corrupt_path)

        inspector = MediaInspector()
        with pytest.raises(CorruptMediaError):
            inspector.inspect(corrupt_path)


class TestRightsManagerAndProvenance:
    """Tests attribution formatting and provenance sidecar exports."""

    def test_attribution_generation(self) -> None:
        # My own video needs zero attribution
        attr_self = RightsManager.generate_attribution_string(
            ownership_type=OwnershipType.MY_OWN_VIDEO,
            uploader="ProGamer99"
        )
        assert attr_self is None

        # Third-party YouTube video generates factual attribution
        attr_third = RightsManager.generate_attribution_string(
            ownership_type=OwnershipType.YOUTUBE_THIRD_PARTY,
            uploader="@Shroud",
            title="Insane Valorant Ace on Haven",
            url="https://youtube.com/watch?v=abcdef12345"
        )
        assert attr_third is not None
        assert "@Shroud" in attr_third
        assert "Insane Valorant Ace" in attr_third
        assert "https://youtube.com/watch?v=abcdef12345" in attr_third
        assert "no copyright infringement intended" not in attr_third.lower()

    def test_provenance_export(self, tmp_path: Path) -> None:
        toggles = PreRunToggles(
            ownership_type=OwnershipType.YOUTUBE_THIRD_PARTY,
            rights_status=RightsStatus.CREATIVE_COMMONS
        )
        yt_meta = YouTubeMetadataDTO(
            url="https://youtube.com/watch?v=xyz",
            title="GTA V Stunt Challenge",
            uploader="StuntMaster",
            duration_sec=120.0
        )
        prov = RightsManager.build_provenance(
            clip_id="clip_007",
            source_sha256_prefix="a1b2c3d4e5f60718",
            toggles=toggles,
            start_sec=45.0,
            end_sec=75.0,
            yt_meta=yt_meta
        )

        assert prov.clip_id == "clip_007"
        assert prov.ownership_type == OwnershipType.YOUTUBE_THIRD_PARTY
        assert prov.attribution_text is not None

        export_file = tmp_path / "clip_007.provenance.json"
        RightsManager.export_provenance_json(prov, export_file)

        assert export_file.exists()
        loaded = json.loads(export_file.read_text(encoding="utf-8"))
        assert loaded["clip_id"] == "clip_007"
        assert loaded["ownership_type"] == "YOUTUBE_THIRD_PARTY"
        assert loaded["start_sec"] == 45.0
