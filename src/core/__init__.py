"""Core package exports for ShortsFactory."""
from .database import DatabaseManager
from .resource_guard import ResourceGuard
from .channel_playbook import ChannelPlaybook
from .youtube_uploader import YouTubeUploader
from .quota_guard import QuotaGuard
from .autonomous_daemon import AutonomousDaemon
from .instagram_uploader import InstagramUploader


def __getattr__(name: str):
    if name == "JobOrchestrator":
        from .orchestrator import JobOrchestrator
        return JobOrchestrator
    elif name in ("AutopilotV2", "AutopilotMode"):
        from .autopilot_v2 import AutopilotV2, AutopilotMode
        if name == "AutopilotV2":
            return AutopilotV2
        return AutopilotMode
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "DatabaseManager",
    "ResourceGuard",
    "ChannelPlaybook",
    "YouTubeUploader",
    "InstagramUploader",
    "QuotaGuard",
    "AutonomousDaemon",
    "AutopilotV2",
    "AutopilotMode",
    "JobOrchestrator",
]
