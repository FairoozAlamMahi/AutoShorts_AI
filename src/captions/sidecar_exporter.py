"""Sidecar subtitle exporter creating synchronized .srt and .vtt files."""
from __future__ import annotations

from pathlib import Path
from typing import List, Dict
from .phrase_chunker import CaptionChunkDTO


class SidecarExporter:
    """Exports industry-standard SRT and WebVTT subtitle files."""

    @staticmethod
    def _format_time(seconds: float, separator: str) -> str:
        """Converts seconds into HH:MM:SS,mmm or HH:MM:SS.mmm format."""
        total_ms = int(round(seconds * 1000))
        ms = total_ms % 1000
        total_s = total_ms // 1000
        s = total_s % 60
        total_m = total_s // 60
        m = total_m % 60
        h = total_m // 60
        return f"{h:02d}:{m:02d}:{s:02d}{separator}{ms:03d}"

    @classmethod
    def export_srt(cls, chunks: List[CaptionChunkDTO], output_path: Path | str) -> Path:
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        lines: List[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            if not chunk.text.strip():
                continue
            start_str = cls._format_time(chunk.start_sec, ",")
            end_str = cls._format_time(chunk.end_sec, ",")
            lines.append(f"{idx}\n{start_str} --> {end_str}\n{chunk.text.strip()}\n\n")

        out.write_text("".join(lines), encoding="utf-8")
        return out

    @classmethod
    def export_vtt(cls, chunks: List[CaptionChunkDTO], output_path: Path | str) -> Path:
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        lines: List[str] = ["WEBVTT\n\n"]
        for idx, chunk in enumerate(chunks, start=1):
            if not chunk.text.strip():
                continue
            start_str = cls._format_time(chunk.start_sec, ".")
            end_str = cls._format_time(chunk.end_sec, ".")
            lines.append(f"{idx}\n{start_str} --> {end_str}\n{chunk.text.strip()}\n\n")

        out.write_text("".join(lines), encoding="utf-8")
        return out

    @classmethod
    def export_all(cls, chunks: List[CaptionChunkDTO], base_path_no_ext: Path | str) -> Dict[str, Path]:
        base = Path(base_path_no_ext)
        srt_path = cls.export_srt(chunks, base.with_suffix(".srt"))
        vtt_path = cls.export_vtt(chunks, base.with_suffix(".vtt"))
        return {"srt": srt_path, "vtt": vtt_path}
