"""ShortsFactory Local - Gradio 5 Web Interface on 127.0.0.1:7860."""
from __future__ import annotations

import sys
from pathlib import Path
import gradio as gr

# Ensure shorts_factory root is on sys.path
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.database import DatabaseManager
from src.core.resource_guard import ResourceGuard
from src.providers.registry import ModelRegistry
from src.config.manager import ConfigManager
from src.core.orchestrator import JobOrchestrator
from src.core.channel_playbook import ChannelPlaybook
from src.core.youtube_uploader import YouTubeUploader
from src.ui.dashboard import create_run_tab
from src.ui.review_drawer import create_review_tab
from src.ui.model_manager_tab import create_model_manager_tab
from src.ui.analytics_tab import create_analytics_tab
from src.ui.autopilot_tab import create_autopilot_tab
from src.ui.war_room_tab import create_war_room_tab
from src.core.autopilot_v2 import AutopilotV2


def build_app(
    db: DatabaseManager,
    resource_guard: ResourceGuard,
    model_registry: ModelRegistry,
    orchestrator: JobOrchestrator,
    config_mgr: ConfigManager,
    uploader: Optional[YouTubeUploader] = None,
    playbook: Optional[ChannelPlaybook] = None,
) -> gr.Blocks:
    """Builds and wires the complete multi-tab Gradio UI."""
    u = uploader or YouTubeUploader()
    p = playbook or ChannelPlaybook()
    auto = AutopilotV2(db=db, resource_guard=resource_guard, model_registry=model_registry)

    with gr.Blocks(title="ShortsFactory Local") as demo:
        gr.Markdown("# ShortsFactory Local - AI Gaming Highlights & Viral Shorts Generator")

        with gr.Tabs():
            with gr.Tab("⚡ Viral Edits & Autopilot Hub"):
                create_autopilot_tab(orchestrator, auto)

            with gr.Tab("🎯 YouTube Agent War Room"):
                create_war_room_tab()

            with gr.Tab("Run & Queue"):
                create_run_tab(orchestrator)

            with gr.Tab("Review & Fast Fix-Up"):
                create_review_tab(orchestrator, db)

            with gr.Tab("Analytics & Channel Playbook"):
                create_analytics_tab(orchestrator, db, u, p)

            with gr.Tab("AI Models & Providers"):
                create_model_manager_tab(model_registry, resource_guard)

            with gr.Tab("Presets & Settings"):
                gr.Markdown("### Workflow Presets")
                presets = config_mgr.list_presets()
                preset_names = [p.name for p in presets]
                preset_dropdown = gr.Dropdown(choices=preset_names, label="Select Saved Preset")
                preset_details = gr.JSON(label="Preset Configuration")

                def _show_preset(name: str):
                    p = config_mgr.get_preset(name)
                    return p.model_dump() if p else {}

                preset_dropdown.change(_show_preset, inputs=[preset_dropdown], outputs=[preset_details])

    return demo


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ShortsFactory Local Web Interface")
    parser.add_argument("--share", action="store_true", default=True, help="Create a public shareable gradio.live URL for remote mobile access (default: True)")
    parser.add_argument("--no-share", action="store_false", dest="share", help="Disable public gradio.live URL")
    parser.add_argument("--port", type=int, default=7860, help="Port to listen on (default: 7860)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address to bind (default: 0.0.0.0)")
    parser.add_argument("--username", type=str, default=None, help="Optional username for basic auth")
    parser.add_argument("--password", type=str, default=None, help="Optional password for basic auth")
    args, _ = parser.parse_known_args()

    auth = None
    if args.username and args.password:
        auth = (args.username, args.password)

    data_dir = PROJECT_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db = DatabaseManager(db_path=str(data_dir / "shorts_factory.db"))
    resource_guard = ResourceGuard(scratch_dir=str(data_dir / "scratch"), disk_threshold_gb=10.0)
    model_registry = ModelRegistry(registry_path=str(data_dir / "models_registry.json"))
    config_mgr = ConfigManager(config_path=str(data_dir / "settings.json"), db=db)
    playbook = ChannelPlaybook(playbook_path=data_dir / "channel_playbook.json")
    uploader = YouTubeUploader(
        client_secrets_path=data_dir / "client_secrets.json",
        token_path=data_dir / "youtube_token.json",
    )
    orchestrator = JobOrchestrator(
        db=db,
        resource_guard=resource_guard,
        model_registry=model_registry,
        scratch_dir=str(data_dir / "scratch"),
        export_dir=str(data_dir / "exports"),
        playbook=playbook,
    )

    demo = build_app(
        db,
        resource_guard,
        model_registry,
        orchestrator,
        config_mgr,
        uploader=uploader,
        playbook=playbook,
    )
    demo.launch(
        server_name=args.host,
        server_port=args.port,
        share=args.share,
        auth=auth,
    )


if __name__ == "__main__":
    main()
