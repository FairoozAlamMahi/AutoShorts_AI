"""Phrase chunker formatting word streams into Animated Pop and Classic caption blocks."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field
from ..core.dto import TranscriptDTO, TranscriptWordDTO


class CaptionChunkDTO(BaseModel):
    """A single subtitle event containing words or lines."""
    start_sec: float
    end_sec: float
    text: str
    words: List[TranscriptWordDTO] = Field(default_factory=list)


class PhraseChunker:
    """Transforms raw word timestamps into timed subtitle presentation blocks."""

    @classmethod
    def chunk_animated_pop(
        cls,
        transcript: TranscriptDTO,
        words_per_block: int = 3,
        max_pause_sec: float = 0.45,
    ) -> List[CaptionChunkDTO]:
        """
        Chunks words for Creator Animated Pop style:
        - 2 to 4 words per block (default 3).
        - Clears on pauses > max_pause_sec (0.45s).
        - Clamps stretched words to 0.65s.
        """
        all_words: List[TranscriptWordDTO] = []
        for seg in transcript.segments:
            for w in seg.words:
                all_words.append(w)

        if not all_words:
            return []

        chunks: List[CaptionChunkDTO] = []
        current_words: List[TranscriptWordDTO] = []

        for i, word in enumerate(all_words):
            if current_words:
                prev_word = current_words[-1]
                pause = word.start_sec - prev_word.end_sec
                # Break on long pause or block size limit
                if pause > max_pause_sec or len(current_words) >= words_per_block:
                    chunks.append(cls._make_chunk(current_words))
                    current_words = []

            current_words.append(word)

        if current_words:
            chunks.append(cls._make_chunk(current_words))

        return chunks

    @classmethod
    def chunk_classic(
        cls,
        transcript: TranscriptDTO,
        max_chars_per_line: int = 42,
        max_lines: int = 2,
        max_pause_sec: float = 0.45,
    ) -> List[CaptionChunkDTO]:
        """
        Chunks words for Classic Subtitles:
        - 1 to 2 lines per block (max 42 chars per line).
        - Breaks at punctuation or pauses.
        """
        all_words: List[TranscriptWordDTO] = []
        for seg in transcript.segments:
            for w in seg.words:
                all_words.append(w)

        if not all_words:
            return []

        chunks: List[CaptionChunkDTO] = []
        current_words: List[TranscriptWordDTO] = []
        max_block_chars = max_chars_per_line * max_lines

        for word in all_words:
            if current_words:
                prev_word = current_words[-1]
                pause = word.start_sec - prev_word.end_sec
                potential_text = " ".join(w.word for w in (current_words + [word]))
                ends_sentence = prev_word.word.endswith((".", "!", "?"))

                if pause > max_pause_sec or len(potential_text) > max_block_chars or ends_sentence:
                    chunks.append(cls._make_chunk(current_words))
                    current_words = []

            current_words.append(word)

        if current_words:
            chunks.append(cls._make_chunk(current_words))

        return chunks

    @staticmethod
    def _make_chunk(words: List[TranscriptWordDTO]) -> CaptionChunkDTO:
        clean_words = []
        for w in words:
            # Clamp duration to 0.65s max
            dur = w.end_sec - w.start_sec
            clamped_end = w.start_sec + 0.65 if dur > 0.65 else w.end_sec
            clean_words.append(TranscriptWordDTO(
                word=w.word,
                start_sec=w.start_sec,
                end_sec=clamped_end,
                confidence=w.confidence,
            ))

        start_sec = clean_words[0].start_sec
        end_sec = max(start_sec + 0.1, clean_words[-1].end_sec)
        text = " ".join(w.word for w in clean_words)
        return CaptionChunkDTO(
            start_sec=round(start_sec, 3),
            end_sec=round(end_sec, 3),
            text=text,
            words=clean_words,
        )
