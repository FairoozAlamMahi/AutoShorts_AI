"""Ollama VLM provider for local keyframe clutch verification and metadata generation."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
import httpx

from .base import VLMProvider
from ..core.dto import VLMAnalysisDTO, ClipMetadataDTO


class OllamaVLMProvider(VLMProvider):
    """VLM provider communicating with a local Ollama daemon (127.0.0.1:11434)."""

    def __init__(self, model_id: str = "qwen2.5vl:3b", host: str = "http://127.0.0.1:11434") -> None:
        super().__init__(model_id=model_id)
        self.host = host.rstrip("/")
        self.client: Optional[httpx.Client] = None

    def load_model(self) -> None:
        if not self.client:
            self.client = httpx.Client(base_url=self.host, timeout=45.0)
        self.is_loaded = True

    def unload_model(self) -> None:
        # Prompt Ollama to immediately release VRAM via keep_alive=0
        if self.client:
            try:
                self.client.post("/api/generate", json={"model": self.model_id, "keep_alive": 0})
            except Exception:
                pass
            self.client.close()
            self.client = None
        self.is_loaded = False

    def list_installed_models(self) -> List[str]:
        """Queries Ollama GET /api/tags for installed local models."""
        try:
            with httpx.Client(base_url=self.host, timeout=5.0) as client:
                res = client.get("/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    return [m.get("name") for m in data.get("models", [])]
        except Exception:
            pass
        return []

    def inspect_keyframes(self, frame_paths: List[str], prompt_context: str) -> VLMAnalysisDTO:
        if not self.is_loaded:
            self.load_model()

        images_b64: List[str] = []
        for fp in frame_paths:
            p = Path(fp)
            if p.exists() and p.stat().st_size > 0:
                images_b64.append(base64.b64encode(p.read_bytes()).decode("utf-8"))

        if not images_b64:
            return VLMAnalysisDTO(clutch_confidence=0.5, is_action_gameplay=True, scene_summary="No frames available")

        system_prompt = (
            "You are an expert gaming video editor and viral YouTube Shorts creator. "
            "Inspect the keyframes (Start, Climax/Action, Ending). "
            "1. Determine if this is active gameplay (is_action_gameplay: bool). Reject static loading/pause/menu screens. "
            "2. Classify the scene type into: ACTION, COMEDY, CLUTCH, DIALOGUE, or FAIL. "
            "3. Detect if a streamer facecam overlay is present (facecam_detected: TOP_LEFT, TOP_RIGHT, BOTTOM_LEFT, BOTTOM_RIGHT, or null). "
            "4. Recommend the best Shorts layout: "
            "   - LAYOUT_B_CENTER_CROP: For fast solo action/combat. "
            "   - LAYOUT_4_3_BLUR_FIT: For comedy, fails, or wide scenes where HUD/radar must remain visible. "
            "   - LAYOUT_FACECAM_SPLIT: If a streamer facecam is detected. "
            "   - LAYOUT_HYBRID_CINEMA_STACK: For tense clutches or cinematic moments. "
            "Respond strictly in JSON format with keys: "
            "clutch_confidence (float 0.0 to 1.0), is_action_gameplay (bool), scene_type (str), "
            "suggested_layout (str), facecam_detected (str or null), scene_summary (str), detected_events (list of str)."
        )

        try:
            assert self.client is not None
            payload = {
                "model": self.model_id,
                "prompt": f"{system_prompt}\nContext: {prompt_context}",
                "images": images_b64,
                "format": "json",
                "stream": False,
                "keep_alive": 0,
            }
            resp = self.client.post("/api/generate", json=payload)
            if resp.status_code == 200:
                result = json.loads(resp.json().get("response", "{}"))
                return VLMAnalysisDTO(
                    clutch_confidence=float(result.get("clutch_confidence", 0.7)),
                    is_action_gameplay=bool(result.get("is_action_gameplay", True)),
                    scene_type=str(result.get("scene_type", "ACTION")),
                    suggested_layout=result.get("suggested_layout"),
                    facecam_detected=result.get("facecam_detected"),
                    scene_summary=str(result.get("scene_summary", "")),
                    detected_events=list(result.get("detected_events", [])),
                )
        except Exception:
            pass

        return VLMAnalysisDTO(clutch_confidence=0.75, is_action_gameplay=True, scene_type="ACTION", scene_summary="Ollama inspection fallback")

    def generate_titles_and_description(self, context: Dict[str, Any]) -> ClipMetadataDTO:
        game = context.get("game_name") or "Gaming"
        speech_text = context.get("transcript_text", "")
        summary = context.get("scene_summary", "")

        prompt = (
            f"You are a top viral YouTube Shorts creator. Write high-CTR metadata for this gaming clip.\n"
            f"Title Guidelines:\n"
            f"- Use an intense curiosity-gap hook or punchline reaction (e.g. 'HE DIDN'T SEE THIS COMING 💀', 'The exact second he knew he lost...').\n"
            f"- Avoid robotic titles like '{game} Gameplay Clip #1'.\n"
            f"- Under 55 characters, punchy phrasing, 1 relevant emoji.\n"
            f"Game: {game}. Visual context: {summary}. Spoken audio: {speech_text}.\n"
            f"Respond strictly in JSON with keys: primary_title, alternative_titles (list of 2), small_description, tags (list of 4-6 hashtags)."
        )

        try:
            if not self.is_loaded:
                self.load_model()
            assert self.client is not None
            payload = {
                "model": self.model_id,
                "prompt": prompt,
                "format": "json",
                "stream": False,
                "keep_alive": 0,
            }
            resp = self.client.post("/api/generate", json=payload)
            if resp.status_code == 200:
                data = json.loads(resp.json().get("response", "{}"))
                return ClipMetadataDTO(
                    primary_title=data.get("primary_title", f"Unreal {game} Play!"),
                    alternative_titles=data.get("alternative_titles", []),
                    small_description=data.get("small_description", f"Insane moment in {game}!"),
                    tags=data.get("tags", ["#gaming", "#shorts"]),
                )
        except Exception:
            pass

        # Rule-based fallback
        return ClipMetadataDTO(
            primary_title=f"INSANE {game.upper()} MOMENT!",
            alternative_titles=[f"Unbelievable {game} Clutch", f"Top {game} Highlight"],
            small_description=f"Watch this crazy moment in {game}! Don't forget to like and subscribe for more.",
            tags=[f"#{game.lower().replace(' ', '')}", "#gaming", "#shorts", "#clutch"],
        )
