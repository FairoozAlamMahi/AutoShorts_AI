"""Rights & Copyright manager enforcing factual attribution and provenance records."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from ..core.dto import ProvenanceDTO, YouTubeMetadataDTO
from ..config.schema import OwnershipType, RightsStatus, PreRunToggles


class RightsManager:
    """Manages copyright compliance, attribution generation, and provenance sidecars."""

    @staticmethod
    def generate_attribution_string(
        ownership_type: OwnershipType,
        uploader: Optional[str] = None,
        title: Optional[str] = None,
        url: Optional[str] = None,
    ) -> Optional[str]:
        """
        Builds a factual attribution line.
        Never invents fake permissions or uses 'no copyright infringement intended'.
        """
        if ownership_type == OwnershipType.MY_OWN_VIDEO:
            return None

        parts = []
        if uploader:
            clean_uploader = uploader.lstrip("@")
            parts.append(f"@{clean_uploader}")
        if title:
            # Truncate title if extremely long
            short_title = title[:50] + "..." if len(title) > 50 else title
            parts.append(f'"{short_title}"')

        credit_body = " - ".join(parts) if parts else "Original Creator"
        if url:
            return f"Source: {credit_body} ({url})"
        return f"Source: {credit_body}"

    @classmethod
    def build_provenance(
        cls,
        clip_id: str,
        source_sha256_prefix: str,
        toggles: PreRunToggles,
        start_sec: float,
        end_sec: float,
        yt_meta: Optional[YouTubeMetadataDTO] = None,
    ) -> ProvenanceDTO:
        """Constructs a ProvenanceDTO recording source identity and rights."""
        url = yt_meta.url if yt_meta else None
        title = yt_meta.title if yt_meta else None
        uploader = yt_meta.uploader if yt_meta else None

        attribution = cls.generate_attribution_string(
            ownership_type=toggles.ownership_type,
            uploader=uploader,
            title=title,
            url=url,
        )

        return ProvenanceDTO(
            clip_id=clip_id,
            source_file_sha256_prefix=source_sha256_prefix,
            source_url=url,
            source_title=title,
            source_uploader=uploader,
            start_sec=start_sec,
            end_sec=end_sec,
            created_at_iso=datetime.now(timezone.utc).isoformat(),
            ownership_type=toggles.ownership_type,
            rights_status=toggles.rights_status,
            attribution_text=attribution,
            toggles_snapshot=toggles.model_dump(),
        )

    @classmethod
    def export_provenance_json(cls, provenance: ProvenanceDTO, output_path: Path | str) -> Path:
        """Writes provenance DTO to clip_XX.provenance.json."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(provenance.model_dump_json(indent=2), encoding="utf-8")
        return out
