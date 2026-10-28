"""Gradio UI Tab modules."""
from .dashboard import create_run_tab
from .review_drawer import create_review_tab
from .analytics_tab import create_analytics_tab
from .model_manager_tab import create_model_manager_tab
from .autopilot_tab import create_autopilot_tab

__all__ = [
    "create_run_tab",
    "create_review_tab",
    "create_analytics_tab",
    "create_model_manager_tab",
    "create_autopilot_tab",
]
