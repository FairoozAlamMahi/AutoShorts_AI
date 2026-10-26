"""Faster-Whisper CTranslate2 STT provider with GPU acceleration and CPU fallback."""
from __future__ import annotations

import gc
import os
from pathlib import Path
from typing import Optional, List, Dict
from .base import TranscriptionProvider
from ..core.dto import TranscriptDTO, TranscriptSegmentDTO, TranscriptWordDTO

try:
    import torch
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False


MODEL_ID_MAP: Dict[str, str] = {
    "faster-whisper-large-v3-turbo": "deepdml/faster-whisper-large-v3-turbo-ct2",
    "faster-whisper-small.en": "Systran/faster-whisper-small.en",
    "faster-whisper-medium": "Systran/faster-whisper-medium",
    "faster-whisper-large-v3": "Systran/faster-whisper-large-v3",
}


class FasterWhisperProvider(TranscriptionProvider):
    """Transcription provider powered by Faster-Whisper (CTranslate2)."""

    def __init__(self, model_id: str = "faster-whisper-large-v3-turbo", device: Optional[str] = None) -> None:
        if device is None:
            device = "cuda" if (_HAS_TORCH and torch.cuda.is_available()) else "cpu"
        super().__init__(model_id=model_id, device=device)
        self.model = None
        self.compute_type = "float16" if self.device == "cuda" else "int8"

    def _resolve_model_name(self) -> str:
        return MODEL_ID_MAP.get(self.model_id, self.model_id)

    def load_model(self) -> None:
        if self.is_loaded and self.model is not None:
            return

        from faster_whisper import WhisperModel

        repo_or_path = self._resolve_model_name()
        try:
            self.model = WhisperModel(
                repo_or_path,
                device=self.device,
                compute_type=self.compute_type,
            )
            self.is_loaded = True
        except Exception as e:
            # Automatic fallback to CPU if CUDA fails (e.g. VRAM shortage or missing cuDNN)
            if self.device == "cuda":
                self.device = "cpu"
                self.compute_type = "int8"
                self.model = WhisperModel(
                    repo_or_path,
                    device="cpu",
                    compute_type="int8",
                )
                self.is_loaded = True
            else:
                raise e

    def unload_model(self) -> None:
        self.model = None
        self.is_loaded = False
        gc.collect()
        if _HAS_TORCH and torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass

    def transcribe(self, audio_path: str, language: Optional[str] = "en") -> TranscriptDTO:
        p = Path(audio_path).resolve()
        if not p.exists() or p.stat().st_size == 0:
            return TranscriptDTO(segments=[], language=language or "en", is_skipped=True)

        if not self.is_loaded or self.model is None:
            self.load_model()

        segments_iter, info = self.model.transcribe(
            str(p),
            language=language,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=450),
        )

        segments_dto: List[TranscriptSegmentDTO] = []
        total_spoken_time = 0.0

        for seg_idx, seg in enumerate(segments_iter):
            words_dto: List[TranscriptWordDTO] = []
            if seg.words:
                for w in seg.words:
                    word_clean = w.word.strip()
                    if word_clean:
                        # Clamp word duration: max 0.65s for stretched single words
                        duration = max(0.05, w.end - w.start)
                        if duration > 0.65:
                            w_end = w.start + 0.65
                        else:
                            w_end = w.end

                        words_dto.append(TranscriptWordDTO(
                            word=word_clean,
                            start_sec=round(w.start, 3),
                            end_sec=round(w_end, 3),
                            confidence=round(getattr(w, "probability", 1.0), 3),
                        ))
                        total_spoken_time += max(0.0, w_end - w.start)

            segments_dto.append(TranscriptSegmentDTO(
                id=seg_idx,
                start_sec=round(seg.start, 3),
                end_sec=round(seg.end, 3),
                text=seg.text.strip(),
                words=words_dto,
            ))

        duration_sec = info.duration if hasattr(info, "duration") and info.duration > 0 else 1.0
        speech_coverage = min(1.0, round(total_spoken_time / duration_sec, 3))

        return TranscriptDTO(
            segments=segments_dto,
            language=info.language or language or "en",
            is_skipped=False,
            speech_coverage_ratio=speech_coverage,
        )
