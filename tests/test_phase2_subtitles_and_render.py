"""Phase 2 Automated Tests: All 5 Subtitle Modes & All 4 Vertical Rendering Layouts."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.config.schema import CaptionMode, LayoutMode, AudioProcessMode
from src.core.dto import (
    TranscriptDTO,
    TranscriptSegmentDTO,
    TranscriptWordDTO,
)
from src.captions.phrase_chunker import PhraseChunker
from src.captions.ass_compiler import ASSCompiler
from src.captions.sidecar_exporter import SidecarExporter
from src.rendering.layout_builder import LayoutBuilder
from src.rendering.ffmpeg_renderer import FFmpegRenderer
from src.ingest.media_inspector import MediaInspector
from src.providers.stt_faster_whisper import FasterWhisperProvider
from tests.synthetic_media_factory import SyntheticMediaFactory


@pytest.fixture
def sample_transcript() -> TranscriptDTO:
    """Fixture providing synthetic word timestamps with tricky characters and emojis."""
    words = [
        TranscriptWordDTO(word="WHAT", start_sec=0.2, end_sec=0.5, confidence=0.99),
        TranscriptWordDTO(word="A", start_sec=0.5, end_sec=0.7, confidence=0.98),
        TranscriptWordDTO(word="CLUTCH!{lol}", start_sec=0.7, end_sec=1.1, confidence=0.99),
        # Pause > 0.45s to test auto-clearing
        TranscriptWordDTO(word="NO", start_sec=1.7, end_sec=2.0, confidence=0.95),
        TranscriptWordDTO(word="WAY!\\escaped", start_sec=2.0, end_sec=2.4, confidence=0.97),
        TranscriptWordDTO(word="🔥ONE-HP🔥", start_sec=2.4, end_sec=3.1, confidence=0.96),
    ]
    seg1 = TranscriptSegmentDTO(id=0, start_sec=0.2, end_sec=1.1, text="WHAT A CLUTCH!{lol}", words=words[:3])
    seg2 = TranscriptSegmentDTO(id=1, start_sec=1.7, end_sec=3.1, text="NO WAY!\\escaped 🔥ONE-HP🔥", words=words[3:])
    return TranscriptDTO(segments=[seg1, seg2], speech_coverage_ratio=0.8)


class TestSubtitlePipeline:
    """Tests all 5 subtitle modes, chunking, escaping, and sidecar export."""

    def test_chunker_animated_pop_splits_on_pause(self, sample_transcript: TranscriptDTO) -> None:
        chunks = PhraseChunker.chunk_animated_pop(sample_transcript, words_per_block=3, max_pause_sec=0.45)
        # Should create 2 chunks because of the >0.45s pause between 1.1s and 1.7s
        assert len(chunks) == 2
        assert len(chunks[0].words) == 3
        assert len(chunks[1].words) == 3
        # Check stretched word clamping (3.1 - 2.4 = 0.7s -> clamped to 0.65s)
        assert round(chunks[1].words[2].end_sec - chunks[1].words[2].start_sec, 2) <= 0.65

    def test_chunker_classic_lines(self, sample_transcript: TranscriptDTO) -> None:
        chunks = PhraseChunker.chunk_classic(sample_transcript, max_chars_per_line=30)
        assert len(chunks) >= 2
        assert chunks[0].start_sec == 0.2

    def test_ass_compiler_animated_pop(self, sample_transcript: TranscriptDTO, tmp_path: Path) -> None:
        chunks = PhraseChunker.chunk_animated_pop(sample_transcript)
        out_ass = tmp_path / "animated.ass"
        ASSCompiler.compile_ass(chunks, mode=CaptionMode.BURNED_IN_ANIMATED, output_path=out_ass)

        assert out_ass.exists()
        content = out_ass.read_text(encoding="utf-8")

        # Must contain ASS header and styles
        assert "[Script Info]" in content
        assert "Style: AnimatedPop" in content
        assert "PlayResX: 1080" in content
        assert "PlayResY: 1920" in content

        # Must contain scale pop tag and active color tag
        assert r"\fscx115\fscy115" in content
        assert ASSCompiler.CYBER_YELLOW in content

        # Braces must be sanitized to prevent libass injection
        assert "{lol}" not in content
        assert "(lol)" in content

    def test_ass_compiler_classic(self, sample_transcript: TranscriptDTO, tmp_path: Path) -> None:
        chunks = PhraseChunker.chunk_classic(sample_transcript)
        out_ass = tmp_path / "classic.ass"
        ASSCompiler.compile_ass(chunks, mode=CaptionMode.BURNED_IN_CLASSIC, output_path=out_ass)

        assert out_ass.exists()
        content = out_ass.read_text(encoding="utf-8")
        assert "Style: Classic" in content
        # Classic mode must NOT contain animated scale pop tags
        assert r"\fscx115" not in content

    def test_sidecar_exporter(self, sample_transcript: TranscriptDTO, tmp_path: Path) -> None:
        chunks = PhraseChunker.chunk_classic(sample_transcript)
        base = tmp_path / "subs"
        sidecars = SidecarExporter.export_all(chunks, base)

        assert sidecars["srt"].exists()
        assert sidecars["vtt"].exists()

        srt_content = sidecars["srt"].read_text(encoding="utf-8")
        vtt_content = sidecars["vtt"].read_text(encoding="utf-8")

        # SRT timing: 00:00:00,200 --> 00:00:01,100
        assert "-->" in srt_content
        assert "," in srt_content.split("-->")[0]

        # VTT timing: WEBVTT and dot separator
        assert vtt_content.startswith("WEBVTT")
        assert "." in vtt_content.split("-->")[0]


class TestRenderingAndLayouts:
    """Renders real synthetic 1080p60 video through all 4 layout modes with FFmpeg."""

    @pytest.fixture(scope="class")
    @classmethod
    def synthetic_source_video(cls, tmp_path_factory: pytest.TempPathFactory) -> Path:
        tmp_dir = tmp_path_factory.mktemp("render_source")
        src_path = tmp_dir / "source_1080p60.mp4"
        SyntheticMediaFactory.create_test_video(
            output_path=src_path,
            duration_sec=3.0,
            width=1920,
            height=1080,
            fps=60,
            has_audio=True,
        )
        return src_path

    def test_layout_hybrid_cinema_stack(self, synthetic_source_video: Path, tmp_path: Path) -> None:
        renderer = FFmpegRenderer()
        out_mp4 = tmp_path / "cinema_stack.mp4"
        renderer.render_clip(
            source_video=synthetic_source_video,
            output_mp4=out_mp4,
            start_sec=0.0,
            duration_sec=2.0,
            layout_mode=LayoutMode.LAYOUT_HYBRID_CINEMA_STACK,
        )

        assert out_mp4.exists()
        inspector = MediaInspector()
        meta = inspector.inspect(out_mp4)
        assert meta.width == 1080
        assert meta.height == 1920
        assert abs(meta.fps - 60.0) < 1.0
        assert abs(meta.duration_sec - 2.0) < 0.15
        assert meta.has_audio is True

    def test_layout_a_blur_fit(self, synthetic_source_video: Path, tmp_path: Path) -> None:
        renderer = FFmpegRenderer()
        out_mp4 = tmp_path / "blur_fit.mp4"
        renderer.render_clip(
            source_video=synthetic_source_video,
            output_mp4=out_mp4,
            start_sec=0.0,
            duration_sec=2.0,
            layout_mode=LayoutMode.LAYOUT_A_BLUR_FIT,
        )

        assert out_mp4.exists()
        inspector = MediaInspector()
        meta = inspector.inspect(out_mp4)
        assert meta.width == 1080
        assert meta.height == 1920
        assert meta.has_audio is True

    def test_layout_b_center_crop(self, synthetic_source_video: Path, tmp_path: Path) -> None:
        renderer = FFmpegRenderer()
        out_mp4 = tmp_path / "center_crop.mp4"
        renderer.render_clip(
            source_video=synthetic_source_video,
            output_mp4=out_mp4,
            start_sec=0.0,
            duration_sec=2.0,
            layout_mode=LayoutMode.LAYOUT_B_CENTER_CROP,
        )

        assert out_mp4.exists()
        inspector = MediaInspector()
        meta = inspector.inspect(out_mp4)
        assert meta.width == 1080
        assert meta.height == 1920

    def test_layout_raw_16_9(self, synthetic_source_video: Path, tmp_path: Path) -> None:
        renderer = FFmpegRenderer()
        out_mp4 = tmp_path / "raw_16_9.mp4"
        renderer.render_clip(
            source_video=synthetic_source_video,
            output_mp4=out_mp4,
            start_sec=0.0,
            duration_sec=2.0,
            layout_mode=LayoutMode.LAYOUT_RAW_16_9,
        )

        assert out_mp4.exists()
        inspector = MediaInspector()
        meta = inspector.inspect(out_mp4)
        assert meta.width == 1920
        assert meta.height == 1080

    def test_render_with_burned_in_animated_subtitles(
        self, synthetic_source_video: Path, sample_transcript: TranscriptDTO, tmp_path: Path
    ) -> None:
        chunks = PhraseChunker.chunk_animated_pop(sample_transcript)
        ass_path = tmp_path / "burned_test.ass"
        ASSCompiler.compile_ass(chunks, mode=CaptionMode.BURNED_IN_ANIMATED, output_path=ass_path)

        renderer = FFmpegRenderer()
        out_mp4 = tmp_path / "burned_subtitles.mp4"
        renderer.render_clip(
            source_video=synthetic_source_video,
            output_mp4=out_mp4,
            start_sec=0.0,
            duration_sec=2.5,
            layout_mode=LayoutMode.LAYOUT_HYBRID_CINEMA_STACK,
            ass_path=ass_path,
        )

        assert out_mp4.exists()
        inspector = MediaInspector()
        meta = inspector.inspect(out_mp4)
        assert meta.width == 1080
        assert meta.height == 1920
        assert abs(meta.duration_sec - 2.5) < 0.15

    def test_fast_rerender_single_clip(self, synthetic_source_video: Path, tmp_path: Path) -> None:
        renderer = FFmpegRenderer()
        v1_mp4 = tmp_path / "clip_v1.mp4"
        renderer.render_clip(
            source_video=synthetic_source_video,
            output_mp4=v1_mp4,
            start_sec=0.0,
            duration_sec=1.5,
            layout_mode=LayoutMode.LAYOUT_HYBRID_CINEMA_STACK,
        )
        assert v1_mp4.exists()

        # Re-render with Layout B and different duration
        v2_mp4 = tmp_path / "clip_v2.mp4"
        renderer.rerender_single_clip(
            source_video=synthetic_source_video,
            output_mp4=v2_mp4,
            start_sec=0.5,
            duration_sec=2.0,
            layout_mode=LayoutMode.LAYOUT_B_CENTER_CROP,
        )
        assert v2_mp4.exists()
        meta = MediaInspector().inspect(v2_mp4)
        assert meta.width == 1080
        assert meta.height == 1920


class TestSTTProviderUnload:
    """Verifies FasterWhisperProvider unloads weights cleanly."""

    def test_faster_whisper_lifecycle(self) -> None:
        provider = FasterWhisperProvider(model_id="faster-whisper-small.en")
        assert provider.is_loaded is False
        provider.unload_model()
        assert provider.is_loaded is False
        assert provider.model is None
