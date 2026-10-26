"""SQLite database persistence with WAL mode and future-ready schema."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List
from .dto import (
    MediaInspectionDTO,
    YouTubeMetadataDTO,
    CandidateClipDTO,
    ClipMetadataDTO,
    JobRequestDTO,
    JobStatusDTO,
)
from ..config.schema import PreRunToggles, OwnershipType, RightsStatus, WorkflowPreset


SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS presets (
    name TEXT PRIMARY KEY,
    description TEXT,
    toggles_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    file_path_or_url TEXT NOT NULL,
    sha256_prefix TEXT,
    title TEXT,
    uploader TEXT,
    duration_sec REAL DEFAULT 0.0,
    width INTEGER,
    height INTEGER,
    fps REAL,
    has_audio INTEGER DEFAULT 1,
    detected_game TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_rights (
    source_id TEXT PRIMARY KEY,
    ownership_type TEXT NOT NULL,
    rights_status TEXT NOT NULL,
    attribution_text TEXT,
    license_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(source_id) REFERENCES sources(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    source_id TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    current_stage TEXT NOT NULL DEFAULT 'INITIALIZED',
    progress_pct REAL DEFAULT 0.0,
    pre_run_toggles_json TEXT NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(source_id) REFERENCES sources(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS clips (
    clip_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    clip_index INTEGER NOT NULL,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    duration_sec REAL NOT NULL,
    composite_score REAL DEFAULT 0.0,
    sub_scores_json TEXT,
    primary_title TEXT,
    alt_titles_json TEXT,
    description TEXT,
    tags_json TEXT,
    exported_mp4_path TEXT,
    narration_script TEXT,
    upload_status TEXT DEFAULT 'NOT_QUEUED',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);
"""


class DatabaseManager:
    """Manages SQLite WAL database operations."""

    def __init__(self, db_path: Path | str = "data/shorts_factory.db") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self) -> None:
        with self.get_connection() as conn:
            conn.executescript(SCHEMA_SQL)

    # --- Presets ---

    def save_preset(self, preset: WorkflowPreset) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO presets (name, description, toggles_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    description = excluded.description,
                    toggles_json = excluded.toggles_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (preset.name, preset.description, preset.toggles.model_dump_json()),
            )

    def get_preset(self, name: str) -> Optional[WorkflowPreset]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT name, description, toggles_json FROM presets WHERE name = ?", (name,)).fetchone()
            if not row:
                return None
            toggles = PreRunToggles.model_validate_json(row["toggles_json"])
            return WorkflowPreset(name=row["name"], description=row["description"], toggles=toggles)

    def list_presets(self) -> List[WorkflowPreset]:
        with self.get_connection() as conn:
            rows = conn.execute("SELECT name, description, toggles_json FROM presets ORDER BY name").fetchall()
            presets = []
            for r in rows:
                toggles = PreRunToggles.model_validate_json(r["toggles_json"])
                presets.append(WorkflowPreset(name=r["name"], description=r["description"], toggles=toggles))
            return presets

    def delete_preset(self, name: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM presets WHERE name = ?", (name,))
            return cursor.rowcount > 0

    # --- Sources & Rights ---

    def register_source(
        self,
        source_id: str,
        file_path_or_url: str,
        sha256_prefix: Optional[str] = None,
        inspection: Optional[MediaInspectionDTO] = None,
        yt_meta: Optional[YouTubeMetadataDTO] = None,
    ) -> None:
        title = yt_meta.title if yt_meta else Path(file_path_or_url).stem
        uploader = yt_meta.uploader if yt_meta else "Local User"
        duration = inspection.duration_sec if inspection else (yt_meta.duration_sec if yt_meta else 0.0)
        width = inspection.width if inspection else None
        height = inspection.height if inspection else None
        fps = inspection.fps if inspection else None
        has_audio = 1 if (inspection and inspection.has_audio) else 1
        game = yt_meta.detected_game if yt_meta else None

        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sources (id, file_path_or_url, sha256_prefix, title, uploader, duration_sec, width, height, fps, has_audio, detected_game)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    file_path_or_url = excluded.file_path_or_url,
                    sha256_prefix = excluded.sha256_prefix,
                    title = excluded.title,
                    uploader = excluded.uploader,
                    duration_sec = excluded.duration_sec,
                    width = excluded.width,
                    height = excluded.height,
                    fps = excluded.fps,
                    has_audio = excluded.has_audio,
                    detected_game = excluded.detected_game
                """,
                (source_id, file_path_or_url, sha256_prefix, title, uploader, duration, width, height, fps, has_audio, game),
            )

    def set_source_rights(
        self,
        source_id: str,
        ownership_type: OwnershipType,
        rights_status: RightsStatus,
        attribution_text: Optional[str] = None,
        license_notes: Optional[str] = None,
    ) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO source_rights (source_id, ownership_type, rights_status, attribution_text, license_notes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    ownership_type = excluded.ownership_type,
                    rights_status = excluded.rights_status,
                    attribution_text = excluded.attribution_text,
                    license_notes = excluded.license_notes
                """,
                (source_id, ownership_type.value, rights_status.value, attribution_text, license_notes),
            )

    # --- Jobs ---

    def create_job(self, request: JobRequestDTO, source_id: Optional[str] = None) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO jobs (job_id, source_id, status, current_stage, progress_pct, pre_run_toggles_json, created_at)
                VALUES (?, ?, 'PENDING', 'INITIALIZED', 0.0, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    updated_at = CURRENT_TIMESTAMP
                """,
                (request.job_id, source_id, request.toggles.model_dump_json(), request.created_at_iso),
            )

    def update_job_status(
        self,
        job_id: str,
        status: str,
        stage: str,
        progress_pct: float,
        error_message: Optional[str] = None,
    ) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, current_stage = ?, progress_pct = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE job_id = ?
                """,
                (status, stage, progress_pct, error_message, job_id),
            )

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            return dict(row) if row else None

    # --- Clips ---

    def save_clip(
        self,
        clip_id: str,
        job_id: str,
        clip: CandidateClipDTO,
        meta: Optional[ClipMetadataDTO] = None,
        exported_path: Optional[str] = None,
    ) -> None:
        sub_scores_json = json.dumps(clip.sub_scores)
        primary_title = meta.primary_title if meta else f"Highlight #{clip.clip_index}"
        alt_titles_json = json.dumps(meta.alternative_titles) if meta else json.dumps([])
        description = meta.small_description if meta else ""
        tags_json = json.dumps(meta.tags) if meta else json.dumps([])

        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO clips (
                    clip_id, job_id, clip_index, start_sec, end_sec, duration_sec,
                    composite_score, sub_scores_json, primary_title, alt_titles_json,
                    description, tags_json, exported_mp4_path
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(clip_id) DO UPDATE SET
                    composite_score = excluded.composite_score,
                    sub_scores_json = excluded.sub_scores_json,
                    primary_title = excluded.primary_title,
                    alt_titles_json = excluded.alt_titles_json,
                    description = excluded.description,
                    tags_json = excluded.tags_json,
                    exported_mp4_path = excluded.exported_mp4_path
                """,
                (
                    clip_id, job_id, clip.clip_index, clip.start_sec, clip.end_sec,
                    clip.duration_sec, clip.composite_score, sub_scores_json,
                    primary_title, alt_titles_json, description, tags_json, exported_path,
                ),
            )

    def get_clips_for_job(self, job_id: str) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM clips WHERE job_id = ? ORDER BY clip_index", (job_id,)).fetchall()
            return [dict(r) for r in rows]
