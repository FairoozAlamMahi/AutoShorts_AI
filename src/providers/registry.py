"""ModelRegistry - Pluggable model management backed by models_registry.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ModelEntry(BaseModel):
    id: str
    type: str = Field(description="'stt', 'vlm', or 'tts'")
    provider: str = Field(description="'faster_whisper', 'openai_compatible', 'ollama', 'llama_cpp', 'mcp_agent', etc.")
    display_name: str
    disk_size_gb: float = 0.0
    vram_req_mb: float = 0.0
    is_default: bool = False
    parameters: Dict[str, Any] = Field(default_factory=dict)


DEFAULT_REGISTRY: Dict[str, Any] = {
    "active_stt": "faster-whisper-large-v3-turbo",
    "active_vlm": "qwen2.5vl:3b",
    "models": [
        # Whisper STT Models
        {
            "id": "faster-whisper-large-v3-turbo",
            "type": "stt",
            "provider": "faster_whisper",
            "display_name": "Faster-Whisper Large v3 Turbo (CTranslate2)",
            "disk_size_gb": 1.5,
            "vram_req_mb": 1800.0,
            "is_default": True,
            "parameters": {"repo_or_size": "deepdml/faster-whisper-large-v3-turbo-ct2", "compute_type": "float16"}
        },
        {
            "id": "faster-whisper-small.en",
            "type": "stt",
            "provider": "faster_whisper",
            "display_name": "Faster-Whisper Small (English Only - Ultra Fast)",
            "disk_size_gb": 0.5,
            "vram_req_mb": 800.0,
            "is_default": False,
            "parameters": {"repo_or_size": "Systran/faster-whisper-small.en", "compute_type": "float16"}
        },
        {
            "id": "faster-whisper-medium",
            "type": "stt",
            "provider": "faster_whisper",
            "display_name": "Faster-Whisper Medium (CTranslate2)",
            "disk_size_gb": 1.5,
            "vram_req_mb": 2200.0,
            "is_default": False,
            "parameters": {"repo_or_size": "Systran/faster-whisper-medium", "compute_type": "float16"}
        },
        {
            "id": "faster-whisper-large-v3",
            "type": "stt",
            "provider": "faster_whisper",
            "display_name": "Faster-Whisper Large v3 (Max Accuracy)",
            "disk_size_gb": 3.1,
            "vram_req_mb": 3800.0,
            "is_default": False,
            "parameters": {"repo_or_size": "Systran/faster-whisper-large-v3", "compute_type": "float16"}
        },
        {
            "id": "local-openai-stt",
            "type": "stt",
            "provider": "openai_compatible",
            "display_name": "Local HTTP STT Endpoint (whisper.cpp / Speaches)",
            "disk_size_gb": 0.0,
            "vram_req_mb": 0.0,
            "is_default": False,
            "parameters": {"base_url": "http://127.0.0.1:8000/v1"}
        },
        # VLM Models
        {
            "id": "qwen2.5vl:3b",
            "type": "vlm",
            "provider": "ollama",
            "display_name": "Qwen 2.5 VL 3B (Ollama)",
            "disk_size_gb": 2.5,
            "vram_req_mb": 2800.0,
            "is_default": True,
            "parameters": {"model_tag": "qwen2.5vl:3b", "keep_alive": "0m"}
        },
        {
            "id": "qwen2.5vl:7b",
            "type": "vlm",
            "provider": "ollama",
            "display_name": "Qwen 2.5 VL 7B (Ollama - High Accuracy)",
            "disk_size_gb": 4.8,
            "vram_req_mb": 5200.0,
            "is_default": False,
            "parameters": {"model_tag": "qwen2.5vl:7b", "keep_alive": "0m"}
        },
        {
            "id": "Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf",
            "type": "vlm",
            "provider": "llama_cpp",
            "display_name": "Qwen 2.5 VL 3B Q4_K_M (Local GGUF)",
            "disk_size_gb": 2.5,
            "vram_req_mb": 2800.0,
            "is_default": False,
            "parameters": {"gguf_file": "data/models/vlm/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf"}
        },
        {
            "id": "external-mcp-agent",
            "type": "vlm",
            "provider": "mcp_agent",
            "display_name": "External MCP Agent Offload (Antigravity / Claude)",
            "disk_size_gb": 0.0,
            "vram_req_mb": 0.0,
            "is_default": False,
            "parameters": {"export_keyframe_strips": True}
        }
    ]
}


class ModelRegistry:
    """Manages available STT and VLM models, switching active choices and persisting configurations."""

    def __init__(self, registry_path: Path | str = "data/models_registry.json") -> None:
        self.registry_path = Path(registry_path)
        self.registry_data = self._load_or_init()

    def _load_or_init(self) -> Dict[str, Any]:
        if self.registry_path.exists():
            try:
                data = json.loads(self.registry_path.read_text(encoding="utf-8"))
                if "models" in data and "active_stt" in data and "active_vlm" in data:
                    return data
            except Exception:
                pass
        self.save_registry(DEFAULT_REGISTRY)
        return DEFAULT_REGISTRY

    def save_registry(self, data: Optional[Dict[str, Any]] = None) -> None:
        if data is not None:
            self.registry_data = data
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(json.dumps(self.registry_data, indent=2), encoding="utf-8")

    def list_models(self, model_type: Optional[str] = None) -> List[ModelEntry]:
        models = [ModelEntry.model_validate(m) for m in self.registry_data.get("models", [])]
        if model_type:
            return [m for m in models if m.type == model_type]
        return models

    def get_model(self, model_id: str) -> Optional[ModelEntry]:
        for m in self.list_models():
            if m.id == model_id:
                return m
        return None

    def get_active_model(self, model_type: str) -> ModelEntry:
        key = f"active_{model_type.lower()}"
        active_id = self.registry_data.get(key)
        if active_id:
            m = self.get_model(active_id)
            if m:
                return m
        # Fallback to first matching model
        for m in self.list_models(model_type):
            return m
        raise KeyError(f"No active or available model found for type '{model_type}'")

    def set_active_model(self, model_type: str, model_id: str) -> None:
        model = self.get_model(model_id)
        if not model:
            raise ValueError(f"Model ID '{model_id}' is not registered.")
        if model.type != model_type.lower():
            raise ValueError(f"Model '{model_id}' is of type '{model.type}', not '{model_type}'.")

        key = f"active_{model_type.lower()}"
        self.registry_data[key] = model_id
        self.save_registry()

    def register_model(self, entry: ModelEntry) -> None:
        # Check if ID already exists, update if so
        models = self.registry_data.get("models", [])
        for i, m in enumerate(models):
            if m["id"] == entry.id:
                models[i] = entry.model_dump()
                self.save_registry()
                return
        models.append(entry.model_dump())
        self.save_registry()

    def estimate_vram_mb(self, model_id: str) -> float:
        model = self.get_model(model_id)
        return model.vram_req_mb if model else 0.0

    def create_stt_provider(self, model_id: Optional[str] = None) -> Any:
        active = self.get_model(model_id) if model_id else self.get_active_model("stt")
        if not active:
            raise ValueError(f"No STT model found for ID '{model_id}'")

        if active.provider == "faster_whisper":
            from .stt_faster_whisper import FasterWhisperProvider
            repo_or_size = active.parameters.get("repo_or_size", active.id)
            return FasterWhisperProvider(model_id=repo_or_size)
        elif active.provider == "openai_compatible":
            from .stt_openai_compat import OpenAICompatibleSTTProvider
            base_url = active.parameters.get("base_url", "http://127.0.0.1:8000/v1")
            return OpenAICompatibleSTTProvider(model_id=active.id, base_url=base_url)
        else:
            raise ValueError(f"Unsupported STT provider: {active.provider}")

    def create_vlm_provider(self, model_id: Optional[str] = None) -> Any:
        active = self.get_model(model_id) if model_id else self.get_active_model("vlm")
        if not active:
            raise ValueError(f"No VLM model found for ID '{model_id}'")

        if active.provider == "ollama":
            from .vlm_ollama import OllamaVLMProvider
            model_tag = active.parameters.get("model_tag", active.id)
            return OllamaVLMProvider(model_id=model_tag)
        elif active.provider == "llama_cpp":
            from .vlm_llamacpp import LlamaCppGGUFProvider
            gguf_path = active.parameters.get("gguf_file")
            return LlamaCppGGUFProvider(model_id=active.id, gguf_path=gguf_path)
        elif active.provider == "mcp_agent":
            from .vlm_mcp_agent import ExternalMCPAgentProvider
            return ExternalMCPAgentProvider(model_id=active.id)
        else:
            raise ValueError(f"Unsupported VLM provider: {active.provider}")


