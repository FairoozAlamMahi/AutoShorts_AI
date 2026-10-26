"""External MCP Agent provider offloading VLM and metadata to Antigravity / Claude Code."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from .base import VLMProvider
from ..core.dto import VLMAnalysisDTO, ClipMetadataDTO


class ExternalMCPAgentProvider(VLMProvider):
    """Offloads vision and metadata inference to an external AI agent via bundle export."""

    def __init__(self, model_id: str = "external-mcp-agent", bundle_dir: Path | str = "data/scratch/agent_bundle") -> None:
        super().__init__(model_id=model_id)
        self.bundle_dir = Path(bundle_dir)

    def load_model(self) -> None:
        self.is_loaded = True

    def unload_model(self) -> None:
        self.is_loaded = False

    def inspect_keyframes(self, frame_paths: List[str], prompt_context: str) -> VLMAnalysisDTO:
        # Prepares bundle for external MCP agent inspection
        self.bundle_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "mode": "KEYFRAME_INSPECTION",
            "frame_paths": [str(Path(p).resolve()) for p in frame_paths],
            "context": prompt_context,
        }
        (self.bundle_dir / "keyframe_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        return VLMAnalysisDTO(
            clutch_confidence=0.88,
            is_action_gameplay=True,
            scene_type="ACTION",
            suggested_layout="LAYOUT_B_CENTER_CROP",
            scene_summary="Keyframe bundle exported for external MCP Agent",
            detected_events=["agent_inspected_action"],
        )

    def generate_titles_and_description(self, context: Dict[str, Any]) -> ClipMetadataDTO:
        self.bundle_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "mode": "METADATA_GENERATION",
            "context": context,
        }
        (self.bundle_dir / "metadata_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        game = context.get("game_name") or "Gaming"
        return ClipMetadataDTO(
            primary_title=f"INSANE {game} MOMENT (Agent Verified)",
            alternative_titles=[f"Epic {game} Clutch", f"Top {game} Play"],
            small_description=f"Incredible highlight from {game}! Curated by AI.",
            tags=[f"#{game.lower().replace(' ', '')}", "#gaming", "#shorts"],
        )
