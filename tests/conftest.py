"""Pytest configuration and shared fixtures for ShortsFactory tests."""
import os
import sys
from pathlib import Path
import pytest

# Ensure shorts_factory root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure FFmpeg is in PATH for all test runs
from src import _ensure_ffmpeg_in_path
_ensure_ffmpeg_in_path()

from src.core.database import DatabaseManager
from src.core.resource_guard import ResourceGuard
from src.providers.registry import ModelRegistry


@pytest.fixture
def temp_db(tmp_path: Path) -> DatabaseManager:
    """Provides an isolated SQLite WAL database manager in tmp_path."""
    db_file = tmp_path / "test_shorts.db"
    return DatabaseManager(db_path=db_file)


@pytest.fixture
def temp_scratch(tmp_path: Path) -> Path:
    """Provides an isolated scratch directory."""
    scratch = tmp_path / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    return scratch


@pytest.fixture
def resource_guard(temp_scratch: Path) -> ResourceGuard:
    """Provides an isolated ResourceGuard instance."""
    return ResourceGuard(scratch_dir=temp_scratch, disk_threshold_gb=5.0)


@pytest.fixture
def model_registry(tmp_path: Path) -> ModelRegistry:
    """Provides an isolated ModelRegistry instance."""
    reg_file = tmp_path / "test_models_registry.json"
    return ModelRegistry(registry_path=reg_file)
