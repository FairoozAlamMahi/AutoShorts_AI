"""Phase 3 Automated Tests: Highlight Discovery, Adaptive Scoring, VLM & Metadata Engine."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pytest

from src.config.schema import DiscoveryMode, MetadataMode, OwnershipType, PreRunToggles, ManualTimestampRange
from src.core.dto import TranscriptDTO, TranscriptSegmentDTO, TranscriptWordDTO, YouTubeMetadataDTO, CandidateClipDTO
from src.analysis.audio_signals import AudioSignalAnalyzer
from src.analysis.visual_signals import VisualSignalAnalyzer
from src.analysis.candidate_generator import CandidateGenerator
from src.providers.vlm_mcp_agent import ExternalMCPAgentProvider
from src.metadata.service import MetadataService
from tests.synthetic_media_factory import SyntheticMediaFactory


class TestPlantedHighlightAccuracy:
    """Generates 60s synthetic video with planted bursts and verifies algorithmic discovery."""

    @pytest.fixture(scope="class")
    @classmethod
    def synthetic_60s_planted_video(cls, tmp_path_factory: pytest.TempPathFactory) -> Path:
        tmp_dir = tmp_path_factory.mktemp("planted_media")
        video_path = tmp_dir / "gameplay_60s.mp4"
        # Plant audio bursts at 15.0s–22.0s and 42.0s–49.0s
        SyntheticMediaFactory.create_test_video(
            output_path=video_path,
            duration_sec=60.0,
            width=640,
            height=360,
            fps=30,
            has_audio=True,
            planted_spikes=[(15.0, 22.0), (42.0, 49.0)],
        )
        return video_path

    def test_audio_analysis_detects_planted_spikes(self, synthetic_60s_planted_video: Path, tmp_path: Path) -> None:
        # Extract audio to wav for analysis
        from src.transcription.service import TranscriptionService
        wav_path = tmp_path / "audio_60s.wav"
        TranscriptionService(provider=None).extract_audio(synthetic_60s_planted_video, wav_path)

        scores, has_music = AudioSignalAnalyzer.analyze_audio_timeline(wav_path, total_duration_sec=60.0)
        assert len(scores) == 60

        # Burst 1 (around 18s) and Burst 2 (around 45s) must have high energy
        assert np.max(scores[15:23]) > np.mean(scores)
        assert np.max(scores[42:50]) > np.mean(scores)

    def test_full_auto_candidate_generator_captures_planted_bursts(self) -> None:
        # Construct synthetic signal arrays representing the planted bursts
        duration = 60.0
        grid_len = int(duration)
        a_scores = np.zeros(grid_len, dtype=np.float32)
        v_scores = np.zeros(grid_len, dtype=np.float32)

        # Plant bursts
        a_scores[18] = 1.0
        a_scores[17:21] = 0.8
        v_scores[18] = 0.9

        a_scores[46] = 1.0
        a_scores[45:48] = 0.85
        v_scores[46] = 0.95

        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.FULL_AUTO,
            target_clip_count=2,
            min_duration_sec=18.0,
            max_duration_sec=30.0,
            pre_roll_sec=8.0,
            post_roll_sec=5.0,
            min_gap_sec=10.0,
        )

        clips = CandidateGenerator.generate_candidates(
            toggles=toggles,
            total_duration_sec=duration,
            acoustic_scores=a_scores,
            visual_scores=v_scores,
            transcript=None,  # Speechless mode
        )

        assert len(clips) == 2
        # Verify first clip envelopes the first burst (~18s)
        assert clips[0].start_sec <= 18.0 <= clips[0].end_sec
        # Verify second clip envelopes the second burst (~46s)
        assert clips[1].start_sec <= 46.0 <= clips[1].end_sec
        # Verify zero jump cuts & valid duration
        for c in clips:
            assert 18.0 <= c.duration_sec <= 30.0


class TestAdaptiveWeightingAndBypasses:
    """Tests automatic commentary vs. speechless weighting and Manual/Hybrid modes."""

    def test_speechless_auto_switch(self) -> None:
        duration = 40.0
        grid_len = int(duration)
        a_scores = np.zeros(grid_len, dtype=np.float32)
        v_scores = np.zeros(grid_len, dtype=np.float32)
        a_scores[10] = 0.9
        v_scores[10] = 0.8

        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.FULL_AUTO,
            target_clip_count=1,
            transcription_enabled=False,  # Transcription turned OFF
        )

        clips = CandidateGenerator.generate_candidates(
            toggles=toggles,
            total_duration_sec=duration,
            acoustic_scores=a_scores,
            visual_scores=v_scores,
            transcript=None,
        )
        assert len(clips) == 1
        assert clips[0].peak_timestamp_sec == 10.0
        # Composite score in speechless mode uses 0.55*A + 0.45*V = 0.55*0.9 + 0.45*0.8 = 0.855
        assert abs(clips[0].composite_score - 0.855) < 0.05

    def test_manual_only_mode(self) -> None:
        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.MANUAL_ONLY,
            manual_timestamps=[
                ManualTimestampRange(start_sec=5.0, end_sec=25.0, label="Penta"),
                ManualTimestampRange(start_sec=35.0, end_sec=55.0, label="Baron Steal"),
            ]
        )
        clips = CandidateGenerator.generate_candidates(
            toggles=toggles,
            total_duration_sec=100.0,
        )
        assert len(clips) == 2
        assert clips[0].start_sec == 5.0
        assert clips[0].end_sec == 25.0
        assert clips[0].is_manual is True
        assert clips[1].start_sec == 35.0
        assert clips[1].end_sec == 55.0

    def test_hybrid_mode_combines_manual_and_auto(self) -> None:
        duration = 80.0
        grid_len = int(duration)
        a_scores = np.zeros(grid_len, dtype=np.float32)
        v_scores = np.zeros(grid_len, dtype=np.float32)
        # Auto peak at 50s
        a_scores[50] = 1.0
        v_scores[50] = 1.0

        toggles = PreRunToggles(
            discovery_mode=DiscoveryMode.HYBRID,
            target_clip_count=2,
            manual_timestamps=[
                ManualTimestampRange(start_sec=10.0, end_sec=30.0, label="Manual Stunt")
            ],
            min_duration_sec=18.0,
            max_duration_sec=25.0,
            min_gap_sec=5.0,
        )

        clips = CandidateGenerator.generate_candidates(
            toggles=toggles,
            total_duration_sec=duration,
            acoustic_scores=a_scores,
            visual_scores=v_scores,
        )
        assert len(clips) == 2
        # First clip is the locked manual clip
        assert clips[0].is_manual is True
        assert clips[0].start_sec == 10.0
        # Second clip is auto-filled from 50s peak
        assert clips[1].is_manual is False
        assert clips[1].start_sec <= 50.0 <= clips[1].end_sec


class TestMetadataAndAttribution:
    """Tests MetadataService across modes, reaction detection, and copyright attribution."""

    @pytest.fixture
    def sample_clip(self) -> CandidateClipDTO:
        return CandidateClipDTO(
            clip_index=1,
            start_sec=10.0,
            end_sec=30.0,
            duration_sec=20.0,
            peak_timestamp_sec=20.0,
            composite_score=0.9,
        )

    def test_rule_based_metadata_with_game_context(self, sample_clip: CandidateClipDTO) -> None:
        toggles = PreRunToggles(
            metadata_mode=MetadataMode.RULE_BASED,
            game_name_context="GTA V",
        )
        meta_service = MetadataService()
        result = meta_service.generate_metadata(clip=sample_clip, toggles=toggles)

        assert "GTA V" in result.primary_title
        assert len(result.primary_title) < 60
        assert len(result.alternative_titles) == 2
        assert "#gtav" in result.tags
        assert "#gaming" in result.tags

    def test_third_party_factual_attribution_enforced(self, sample_clip: CandidateClipDTO) -> None:
        toggles = PreRunToggles(
            metadata_mode=MetadataMode.RULE_BASED,
            ownership_type=OwnershipType.YOUTUBE_THIRD_PARTY,
        )
        yt_meta = YouTubeMetadataDTO(
            url="https://youtube.com/watch?v=12345",
            title="Best Call of Duty Clips",
            uploader="ProSniper",
            detected_game="Call of Duty: Warzone",
        )
        meta_service = MetadataService()
        result = meta_service.generate_metadata(clip=sample_clip, toggles=toggles, yt_meta=yt_meta)

        # Attribution must be present in metadata
        assert result.attribution_text is not None
        assert "@ProSniper" in result.attribution_text
        assert "https://youtube.com/watch?v=12345" in result.attribution_text
        assert result.attribution_text in result.small_description
        assert "no copyright infringement intended" not in result.small_description.lower()

    def test_metadata_off_mode(self, sample_clip: CandidateClipDTO) -> None:
        toggles = PreRunToggles(metadata_mode=MetadataMode.OFF)
        meta_service = MetadataService()
        result = meta_service.generate_metadata(clip=sample_clip, toggles=toggles)

        assert result.primary_title == "Highlight #1"
        assert result.small_description == ""
        assert len(result.tags) == 0

    def test_external_mcp_agent_bundle_export(self, sample_clip: CandidateClipDTO, tmp_path: Path) -> None:
        bundle_dir = tmp_path / "agent_test_bundle"
        agent_provider = ExternalMCPAgentProvider(bundle_dir=bundle_dir)
        meta_service = MetadataService(vlm_provider=agent_provider)

        toggles = PreRunToggles(
            metadata_mode=MetadataMode.EXTERNAL_MCP_AGENT,
            game_name_context="Valorant",
        )
        result = meta_service.generate_metadata(clip=sample_clip, toggles=toggles)

        assert "Valorant" in result.primary_title
        assert (bundle_dir / "metadata_manifest.json").exists()
        manifest_data = json.loads((bundle_dir / "metadata_manifest.json").read_text(encoding="utf-8"))
        assert manifest_data["mode"] == "METADATA_GENERATION"
        assert manifest_data["context"]["game_name"] == "Valorant"
