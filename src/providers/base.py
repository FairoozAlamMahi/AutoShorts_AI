"""Abstract base provider interfaces for Pluggable AI Models (STT, VLM, TTS)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from ..core.dto import TranscriptDTO, VLMAnalysisDTO, ClipMetadataDTO


class TranscriptionProvider(ABC):
    """Abstract interface for Speech-to-Text transcription engines."""

    def __init__(self, model_id: str, device: str = "cuda") -> None:
        self.model_id = model_id
        self.device = device
        self.is_loaded = False

    @abstractmethod
    def load_model(self) -> None:
        """Loads weights into memory/VRAM."""
        pass

    @abstractmethod
    def unload_model(self) -> None:
        """Releases weights and flushes VRAM."""
        pass

    @abstractmethod
    def transcribe(self, audio_path: str, language: Optional[str] = "en") -> TranscriptDTO:
        """Transcribes audio and returns timestamped words and segments."""
        pass


class VLMProvider(ABC):
    """Abstract interface for Vision-Language Models & Metadata generators."""

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self.is_loaded = False

    @abstractmethod
    def load_model(self) -> None:
        """Loads or validates connection to model."""
        pass

    @abstractmethod
    def unload_model(self) -> None:
        """Releases model resources."""
        pass

    @abstractmethod
    def inspect_keyframes(self, frame_paths: List[str], prompt_context: str) -> VLMAnalysisDTO:
        """Evaluates clutch gameplay keyframes and returns action confidence."""
        pass

    @abstractmethod
    def generate_titles_and_description(self, context: Dict[str, Any]) -> ClipMetadataDTO:
        """Generates primary title, alternative titles, description, and tags."""
        pass


class TTSProvider(ABC):
    """Abstract interface for AI Voiceover / Narration engines (Post-MVP ready)."""

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self.is_loaded = False

    @abstractmethod
    def load_model(self) -> None:
        pass

    @abstractmethod
    def unload_model(self) -> None:
        pass

    @abstractmethod
    def synthesize(self, text: str, output_path: str, voice: Optional[str] = None) -> str:
        """Synthesizes speech audio file and returns output path."""
        pass
