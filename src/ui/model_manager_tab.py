"""Model Manager Tab: hot-swap Whisper STT and VLM models and monitor VRAM."""
from __future__ import annotations

from typing import Tuple, List, Dict, Any
import gradio as gr
from ..providers.registry import ModelRegistry, ModelEntry
from ..core.resource_guard import ResourceGuard
from ..providers.vlm_ollama import OllamaVLMProvider


def create_model_manager_tab(registry: ModelRegistry, resource_guard: ResourceGuard) -> None:
    """Builds the AI Models & Providers configuration tab."""
    gr.Markdown("### AI Model Registry & Hardware Allocation")

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("#### Active Speech-to-Text Model (Whisper)")
            stt_models = registry.list_models("stt")
            stt_choices = [m.id for m in stt_models]
            active_stt = registry.get_active_model("stt").id

            stt_dropdown = gr.Dropdown(
                choices=stt_choices,
                value=active_stt,
                label="Select Active Whisper Model",
                interactive=True,
            )
            stt_status = gr.Textbox(label="STT Model Info", interactive=False)

            with gr.Accordion("Register Custom HuggingFace / Local STT Model", open=False):
                custom_stt_id = gr.Textbox(label="Model ID", placeholder="my-custom-whisper")
                custom_stt_repo = gr.Textbox(label="HuggingFace Repo / Path", placeholder="Systran/faster-whisper-medium")
                register_stt_btn = gr.Button("Register STT Model")

        with gr.Column(scale=1):
            gr.Markdown("#### Active Vision-Language & Metadata Model (VLM)")
            vlm_models = registry.list_models("vlm")
            vlm_choices = [m.id for m in vlm_models]
            active_vlm = registry.get_active_model("vlm").id

            vlm_dropdown = gr.Dropdown(
                choices=vlm_choices,
                value=active_vlm,
                label="Select Active VLM Model",
                interactive=True,
            )
            vlm_status = gr.Textbox(label="VLM Model Info", interactive=False)
            refresh_ollama_btn = gr.Button("Discover Installed Ollama Models")

    gr.Markdown("#### Real-Time Hardware Resource Guard Snapshot")
    system_stats_box = gr.JSON(label="System RAM / GPU VRAM / SSD Space")
    refresh_stats_btn = gr.Button("Refresh System Stats")

    # Callbacks
    def _on_stt_change(selected_id: str) -> str:
        registry.set_active_model("stt", selected_id)
        m = registry.get_model(selected_id)
        return f"Active: {m.display_name} | Est VRAM: {m.vram_req_mb} MB | Disk: {m.disk_size_gb} GB" if m else ""

    def _on_vlm_change(selected_id: str) -> str:
        registry.set_active_model("vlm", selected_id)
        m = registry.get_model(selected_id)
        return f"Active: {m.display_name} | Est VRAM: {m.vram_req_mb} MB" if m else ""

    def _on_refresh_stats() -> Dict[str, Any]:
        return resource_guard.get_system_snapshot()

    def _on_discover_ollama() -> gr.Dropdown:
        ollama = OllamaVLMProvider()
        installed = ollama.list_installed_models()
        for tag in installed:
            entry = ModelEntry(
                id=tag,
                type="vlm",
                provider="ollama",
                display_name=f"{tag} (Ollama Auto-Discovered)",
                vram_req_mb=3000.0,
                parameters={"model_tag": tag}
            )
            registry.register_model(entry)
        all_vlm = [m.id for m in registry.list_models("vlm")]
        return gr.Dropdown(choices=all_vlm)

    def _on_register_custom_stt(model_id: str, repo: str) -> gr.Dropdown:
        if model_id.strip() and repo.strip():
            entry = ModelEntry(
                id=model_id.strip(),
                type="stt",
                provider="faster_whisper",
                display_name=f"{model_id.strip()} (Custom)",
                parameters={"repo_or_size": repo.strip()}
            )
            registry.register_model(entry)
        all_stt = [m.id for m in registry.list_models("stt")]
        return gr.Dropdown(choices=all_stt)

    stt_dropdown.change(_on_stt_change, inputs=[stt_dropdown], outputs=[stt_status])
    vlm_dropdown.change(_on_vlm_change, inputs=[vlm_dropdown], outputs=[vlm_status])
    refresh_stats_btn.click(_on_refresh_stats, outputs=[system_stats_box])
    refresh_ollama_btn.click(_on_discover_ollama, outputs=[vlm_dropdown])
    register_stt_btn.click(_on_register_custom_stt, inputs=[custom_stt_id, custom_stt_repo], outputs=[stt_dropdown])
