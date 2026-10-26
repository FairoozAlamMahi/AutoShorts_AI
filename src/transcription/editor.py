"""Transcript editing, timestamp nudging, and clip window slicing utilities."""
from __future__ import annotations

from typing import List
from ..core.dto import TranscriptDTO, TranscriptSegmentDTO, TranscriptWordDTO


class TranscriptEditor:
    """Provides inline text corrections and timestamp alignment adjustments."""

    @staticmethod
    def slice_transcript_for_window(transcript: TranscriptDTO, start_sec: float, end_sec: float) -> TranscriptDTO:
        """
        Slices and re-bases transcript words to a clip window [start_sec, end_sec].
        Timestamps are re-aligned relative to 0.0 (the beginning of the clipped video).
        """
        if transcript.is_skipped or not transcript.segments:
            return TranscriptDTO(segments=[], is_skipped=True, language=transcript.language)

        new_segments: List[TranscriptSegmentDTO] = []
        seg_counter = 0

        for seg in transcript.segments:
            # Check overlap with [start_sec, end_sec]
            if seg.end_sec < start_sec or seg.start_sec > end_sec:
                continue

            sliced_words: List[TranscriptWordDTO] = []
            for w in seg.words:
                if w.end_sec < start_sec or w.start_sec > end_sec:
                    continue
                # Re-base to 0.0
                rel_start = max(0.0, round(w.start_sec - start_sec, 3))
                rel_end = max(rel_start + 0.05, round(min(w.end_sec, end_sec) - start_sec, 3))
                sliced_words.append(TranscriptWordDTO(
                    word=w.word,
                    start_sec=rel_start,
                    end_sec=rel_end,
                    confidence=w.confidence,
                ))

            if sliced_words:
                seg_text = " ".join(w.word for w in sliced_words)
                new_segments.append(TranscriptSegmentDTO(
                    id=seg_counter,
                    start_sec=sliced_words[0].start_sec,
                    end_sec=sliced_words[-1].end_sec,
                    text=seg_text,
                    words=sliced_words,
                ))
                seg_counter += 1

        return TranscriptDTO(
            segments=new_segments,
            language=transcript.language,
            is_skipped=len(new_segments) == 0,
            speech_coverage_ratio=transcript.speech_coverage_ratio,
        )

    @staticmethod
    def update_word_text(transcript: TranscriptDTO, segment_id: int, word_index: int, new_text: str) -> TranscriptDTO:
        for seg in transcript.segments:
            if seg.id == segment_id and 0 <= word_index < len(seg.words):
                seg.words[word_index].word = new_text.strip()
                seg.text = " ".join(w.word for w in seg.words)
                break
        return transcript

    @staticmethod
    def nudge_word_timestamp(transcript: TranscriptDTO, segment_id: int, word_index: int, delta_sec: float) -> TranscriptDTO:
        for seg in transcript.segments:
            if seg.id == segment_id and 0 <= word_index < len(seg.words):
                w = seg.words[word_index]
                w.start_sec = max(0.0, round(w.start_sec + delta_sec, 3))
                w.end_sec = max(w.start_sec + 0.05, round(w.end_sec + delta_sec, 3))
                break
        return transcript
