"""
Concat MCP Client Bridge for Autonomous Video Editing.

Provides a Pythonic API to interact with the Concat video editor engine
over the Model Context Protocol (stdio JSON-RPC 2.0).

Supports:
- Headless project creation (1080x1920 vertical format for Shorts/TikTok/Reels).
- Media import and multi-track placement.
- Blur-fit and solid background styling.
- Word-level colored caption styling.
- Cubic-bezier animated zoom punches.
- Fast hardware-accelerated GPU export.
- Composited frame preview extraction without rendering.
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

def _find_default_concat_exe() -> Path:
    curr = Path(__file__).resolve().parent
    for _ in range(5):
        candidate = curr / "tools" / "concat" / "PFiles64" / "Concat" / "concat.exe"
        if candidate.exists():
            return candidate
        curr = curr.parent
    return Path(__file__).resolve().parent / "tools" / "concat" / "PFiles64" / "Concat" / "concat.exe"

DEFAULT_CONCAT_EXE = _find_default_concat_exe()

class ConcatError(Exception):
    """Raised when Concat MCP server returns an error."""
    pass

class ConcatMcpClient:
    def __init__(self, concat_exe: Optional[Path] = None, headless: bool = True):
        self.concat_exe = Path(concat_exe) if concat_exe else DEFAULT_CONCAT_EXE
        self.headless = headless
        self.proc: Optional[subprocess.Popen] = None
        self._req_id = 0

        if not self.concat_exe.exists():
            raise FileNotFoundError(f"Concat binary not found at {self.concat_exe}")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def start(self):
        """Starts the Concat MCP server process and performs the handshake."""
        args = [str(self.concat_exe), "--mcp"]
        if self.headless:
            args.append("headless")

        self.proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0
        )

        # 1. Initialize
        init_res = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "AutoShorts-Engine",
                "version": "1.0.0"
            }
        })

        # 2. Initialized notification
        self._send_notification("notifications/initialized")
        return init_res

    def stop(self):
        """Cleanly stops the Concat server process."""
        if self.proc:
            try:
                if self.proc.stdin:
                    self.proc.stdin.close()
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        if not self.proc or not self.proc.stdin or not self.proc.stdout:
            raise ConcatError("Concat MCP server is not running")

        req_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {}
        }

        line = json.dumps(payload) + "\n"
        self.proc.stdin.write(line)
        self.proc.stdin.flush()

        resp_line = self.proc.stdout.readline()
        if not resp_line:
            err_msg = self.proc.stderr.read() if self.proc.stderr else "Unknown error"
            raise ConcatError(f"Concat process exited unexpectedly: {err_msg}")

        try:
            resp = json.loads(resp_line)
        except json.JSONDecodeError as e:
            raise ConcatError(f"Failed to parse JSON response: {resp_line.strip()} ({e})")

        if "error" in resp:
            err = resp["error"]
            raise ConcatError(f"[{err.get('code')}] {err.get('message')}")

        return resp.get("result")

    def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        if not self.proc or not self.proc.stdin:
            raise ConcatError("Concat MCP server is not running")

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        line = json.dumps(payload) + "\n"
        self.proc.stdin.write(line)
        self.proc.stdin.flush()

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """Invokes an MCP tool by name."""
        res = self._send_request("tools/call", {
            "name": name,
            "arguments": arguments or {}
        })
        # Extract text or structured result
        content = res.get("content", [])
        if content and isinstance(content, list):
            text_items = [c.get("text") for c in content if c.get("type") == "text"]
            if text_items:
                try:
                    return json.loads(text_items[0])
                except Exception:
                    return text_items[0]
        return res

    # --- High Level Convenience Methods ---

    def create_project(self, location: str, name: str, width: int = 1080, height: int = 1920, fps: int = 60) -> str:
        """Creates a vertical video project and returns its absolute folder path."""
        res = self.call_tool("project_create", {
            "location": str(Path(location).resolve()),
            "name": name,
            "video": {
                "width": width,
                "height": height,
                "rateNum": fps,
                "rateDen": 1
            }
        })
        project_path = str(Path(location).resolve() / name)
        return project_path

    def open_project(self, project_path: str) -> Any:
        return self.call_tool("project_open", {"path": str(Path(project_path).resolve())})

    def save_project(self, project_path: str) -> Any:
        return self.call_tool("project_save", {"path": str(Path(project_path).resolve())})

    def close_project(self, project_path: str, save: bool = True) -> Any:
        return self.call_tool("project_close", {"path": str(Path(project_path).resolve()), "save": save})

    def read_timeline(self, project_path: str) -> Dict[str, Any]:
        return self.call_tool("timeline_read", {"path": str(Path(project_path).resolve())})

    def import_media(self, project_path: str, media_file: str) -> str:
        """Imports media into project and returns the mediaId."""
        res = self.call_tool("media_import", {
            "path": str(Path(project_path).resolve()),
            "file": str(Path(media_file).resolve())
        })
        if isinstance(res, dict) and "createdId" in res:
            return res["createdId"]
        # Fallback to reading timeline media bin
        tl = self.read_timeline(project_path)
        for m in tl.get("media", []):
            if m.get("file") == str(Path(media_file).resolve()):
                return m["id"]
        return res.get("createdId", "") if isinstance(res, dict) else str(res)

    def add_clip(self, project_path: str, media_id: str, track_id: str, start: float, ripple: bool = False) -> str:
        """Places a clip onto the timeline."""
        res = self.call_tool("clip_add", {
            "path": str(Path(project_path).resolve()),
            "mediaId": media_id,
            "trackId": track_id,
            "start": start,
            "ripple": ripple
        })
        if isinstance(res, dict):
            return res.get("createdId", "")
        return ""

    def add_track(self, project_path: str, bottom: bool = False) -> str:
        """Adds a track/lane to the timeline."""
        res = self.call_tool("track_add", {
            "path": str(Path(project_path).resolve()),
            "bottom": bottom
        })
        if isinstance(res, dict):
            return res.get("createdId", "")
        return ""

    def set_timeline_background(self, project_path: str, timeline_id: str, kind: str = "blur", amount: float = 0.8, color: str = "#000000"):
        """Sets blur-fit, color, or image background for 9:16 vertical canvas."""
        bg = {"kind": kind}
        if kind == "blur":
            bg["amount"] = amount
        elif kind == "color":
            bg["color"] = color

        return self.call_tool("timeline_background", {
            "path": str(Path(project_path).resolve()),
            "timelineId": timeline_id,
            "background": bg
        })

    def frame_clip(self, project_path: str, clip_id: str, framing: str = "fit"):
        """Sizes picture to frame ('fit' for blur-fit letterboxing, 'fill' for center crop)."""
        return self.call_tool("clip_frame", {
            "path": str(Path(project_path).resolve()),
            "clipId": clip_id,
            "framing": framing
        })

    def add_title(self, project_path: str, text: str, start: float, duration: float, offset_y: float = -0.3, font_size: float = 0.08, color: str = "#FFFF00", stroke_color: str = "#000000", stroke_width: float = 0.015) -> str:
        """Adds text overlay over the video."""
        res = self.call_tool("title_add", {
            "path": str(Path(project_path).resolve()),
            "start": start,
            "duration": duration,
            "offsetY": offset_y,
            "style": {
                "content": text,
                "fontSize": font_size,
                "fontWeight": 800,
                "color": color,
                "strokeColor": stroke_color,
                "strokeWidth": stroke_width
            }
        })
        if isinstance(res, dict):
            return res.get("createdId", "")
        return ""

    def style_title_words(self, project_path: str, clip_id: str, char_start: int, char_end: int, color: str = "#FF0033"):
        """Styles a range of characters in a title (e.g. red highlight on viral keyword)."""
        return self.call_tool("title_style_words", {
            "path": str(Path(project_path).resolve()),
            "clipId": clip_id,
            "start": char_start,
            "end": char_end,
            "patch": {
                "color": color,
                "fontWeight": 900
            }
        })

    def add_captions(self, project_path: str, captions: List[Dict[str, Any]], offset_y: float = 0.35):
        """Adds a list of captions [{start: sec, end: sec, text: str}]."""
        formatted = []
        for c in captions:
            formatted.append({
                "start": c["start"],
                "end": c["end"],
                "text": c["text"]
            })
        return self.call_tool("captions_add", {
            "path": str(Path(project_path).resolve()),
            "captions": formatted,
            "offsetY": offset_y
        })

    def export_video(self, project_path: str, output_path: str, crf: int = 20, preset: str = "medium", timeout_sec: int = 300) -> Dict[str, Any]:
        """Renders the timeline directly to an MP4 video."""
        start_res = self.call_tool("export_start", {
            "path": str(Path(project_path).resolve()),
            "output": str(Path(output_path).resolve()),
            "crf": crf,
            "preset": preset
        })
        job_id = start_res.get("job") if isinstance(start_res, dict) else None
        if not job_id:
            raise ConcatError(f"Export did not return a job ID: {start_res}")

        wait_res = self.call_tool("export_wait", {
            "job": job_id,
            "timeoutSeconds": timeout_sec
        })
        return wait_res
