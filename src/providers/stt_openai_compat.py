"""OpenAI-compatible local HTTP STT provider (whisper.cpp, Speaches)."""
from __future__ import annotations

import httpx
from pathlib import Path
from typing import Optional, List
from .base import TranscriptionProvider
from ..core.dto import TranscriptDTO, TranscriptSegmentDTO, TranscriptWordDTO


class OpenAICompatibleSTTProvider(TranscriptionProvider):
    """Transcription provider communicating with an OpenAI-compatible HTTP STT endpoint."""

    def __init__(self, model_id: str = "whisper-1", base_url: str = "http://127.0.0.1:8000/v1") -> None:
        super().__init__(model_id=model_id, device="network")
        self.base_url = base_url.rstrip("/")
        self.client: Optional[httpx.Client] = None

    def load_model(self) -> None:
        if not self.client:
            self.client = httpx.Client(base_url=self.base_url, timeout=60.0)
        self.is_loaded = True

    def unload_model(self) -> None:
        if self.client:
            self.client.close()
            self.client = None
        self.is_loaded = False

    def transcribe(self, audio_path: str, language: Optional[str] = "en") -> TranscriptDTO:
        p = Path(audio_path).resolve()
        if not p.exists() or p.stat().st_size == 0:
            return TranscriptDTO(segments=[], language=language or "en", is_skipped=True)

        if not self.is_loaded:
            self.load_model()

        url = f"{self.base_url}/audio/transcriptions"
        with open(p, "rb") as f:
            files = {"file": (p.name, f, "audio/wav")}
            data = {
                "model": self.model_id,
                "response_format": "verbose_json",
                "timestamp_granularities[]": ["word", "segment"],
            }
            if language:
                data["language"] = language

            try:
                assert self.client is not None
                resp = self.client.post(url, files=files, data=data)
                resp.raise_for_status()
                result = resp.json()
            except Exception as e:
                # Return empty transcript on connection/API error
                return TranscriptDTO(segments=[], language=language or "en", is_skipped=True)

        # Parse verbose_json format
        segments_dto: List[TranscriptSegmentDTO] = []
        raw_segments = result.get("segments", [])
        for idx, s in enumerate(raw_segments):
            words_dto: List[TranscriptWordDTO] = []
            for w in s.get("words", []):
                words_dto.append(TranscriptWordDTO(
                    word=w.get("word", "").strip(),
                    start_sec=float(w.get("start", 0.0)),
                    end_sec=float(w.get("end", 0.0)),
                    confidence=1.0,
                ))
            segments_dto.append(TranscriptSegmentDTO(
                id=idx,
                start_sec=float(s.get("start", 0.0)),
                end_sec=float(s.get("end", 0.0)),
                text=s.get("text", "").strip(),
                words=words_dto,
            ))

        return TranscriptDTO(
            segments=segments_dto,
            language=result.get("language", language or "en"),
            is_skipped=False,
            speech_coverage_ratio=0.5 if segments_dto else 0.0,
        )
