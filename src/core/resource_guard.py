"""ResourceGuard - Sequential GPU VRAM lease manager, RAM/Disk checks, and scratch cleanup."""
from __future__ import annotations

import gc
import os
import shutil
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Dict, Any, Generator
import psutil

try:
    import torch
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False


class ResourceGuard:
    """
    Enforces hardware guardrails for 8 GB VRAM RTX 4060 Ti baseline:
    - Prevents concurrent GPU model leasing (Whisper and VLM never load simultaneously).
    - Flushes GPU cache upon stage exit.
    - Monitors available system RAM and SSD storage.
    - Safely purges per-job scratch directories without touching exports.
    """

    def __init__(self, scratch_dir: Path | str = "data/scratch", disk_threshold_gb: float = 10.0) -> None:
        self.scratch_dir = Path(scratch_dir).resolve()
        self.disk_threshold_gb = disk_threshold_gb
        self._gpu_lock = threading.Lock()
        self._active_lease_stage: Optional[str] = None

    def get_ram_snapshot(self) -> Dict[str, float]:
        """Returns RAM stats in GB."""
        mem = psutil.virtual_memory()
        return {
            "total_gb": round(mem.total / (1024 ** 3), 2),
            "available_gb": round(mem.available / (1024 ** 3), 2),
            "used_gb": round(mem.used / (1024 ** 3), 2),
            "percent_used": mem.percent,
        }

    def get_disk_snapshot(self, target_dir: Optional[Path | str] = None) -> Dict[str, Any]:
        """Returns disk space stats in GB for the drive containing target_dir."""
        check_path = Path(target_dir).resolve() if target_dir else self.scratch_dir
        check_path.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(str(check_path))
        free_gb = round(usage.free / (1024 ** 3), 2)
        total_gb = round(usage.total / (1024 ** 3), 2)
        is_low = free_gb < self.disk_threshold_gb
        return {
            "total_gb": total_gb,
            "free_gb": free_gb,
            "is_low_space": is_low,
            "threshold_gb": self.disk_threshold_gb,
        }

    def get_gpu_snapshot(self) -> Dict[str, Any]:
        """Queries GPU VRAM stats using torch.cuda or nvidia-smi fallback."""
        if _HAS_TORCH and torch.cuda.is_available():
            try:
                device = torch.cuda.current_device()
                gpu_name = torch.cuda.get_device_name(device)
                free_bytes, total_bytes = torch.cuda.mem_get_info(device)
                allocated_bytes = torch.cuda.memory_allocated(device)
                return {
                    "gpu_available": True,
                    "gpu_name": gpu_name,
                    "total_vram_mb": round(total_bytes / (1024 ** 2), 1),
                    "free_vram_mb": round(free_bytes / (1024 ** 2), 1),
                    "allocated_vram_mb": round(allocated_bytes / (1024 ** 2), 1),
                    "method": "torch.cuda",
                }
            except Exception:
                pass

        # Fallback to nvidia-smi
        try:
            cmd = ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,memory.used", "--format=csv,noheader,nounits"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3, check=True)
            line = res.stdout.strip().split("\n")[0]
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                return {
                    "gpu_available": True,
                    "gpu_name": parts[0],
                    "total_vram_mb": float(parts[1]),
                    "free_vram_mb": float(parts[2]),
                    "allocated_vram_mb": float(parts[3]),
                    "method": "nvidia-smi",
                }
        except Exception:
            pass

        return {
            "gpu_available": False,
            "gpu_name": None,
            "total_vram_mb": 0.0,
            "free_vram_mb": 0.0,
            "allocated_vram_mb": 0.0,
            "method": "none",
        }

    def get_system_snapshot(self) -> Dict[str, Any]:
        """Comprehensive snapshot of RAM, Disk, and GPU status."""
        return {
            "ram": self.get_ram_snapshot(),
            "disk": self.get_disk_snapshot(),
            "gpu": self.get_gpu_snapshot(),
            "active_gpu_stage": self._active_lease_stage,
        }

    @contextmanager
    def gpu_stage_lease(self, stage_name: str) -> Generator[Dict[str, Any], None, None]:
        """
        Exclusive context manager for sequential GPU model stages.
        Raises RuntimeError if another GPU stage is currently leasing VRAM.
        Automatically empties CUDA cache upon stage exit.
        """
        acquired = self._gpu_lock.acquire(blocking=False)
        if not acquired:
            raise RuntimeError(
                f"Concurrent GPU stage lease rejected! Stage '{stage_name}' cannot lease GPU "
                f"while stage '{self._active_lease_stage}' is active."
            )

        self._active_lease_stage = stage_name
        initial_snapshot = self.get_gpu_snapshot()

        try:
            yield initial_snapshot
        finally:
            # Force garbage collection and flush CUDA memory
            gc.collect()
            if _HAS_TORCH and torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass

            self._active_lease_stage = None
            self._gpu_lock.release()

    def purge_job_scratch(self, job_id: str) -> bool:
        """
        Safely deletes data/scratch/{job_id}.
        Security guardrails:
        - Prevents directory traversal outside scratch_dir.
        - NEVER allows deleting data/exports or the scratch root itself.
        """
        if not job_id or not job_id.strip() or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError(f"Invalid job_id for scratch purge: {job_id}")

        job_dir = (self.scratch_dir / job_id).resolve()

        # Guardrail: Must reside strictly inside scratch_dir and cannot be scratch_dir itself
        if job_dir == self.scratch_dir:
            raise ValueError("Refusing to delete root scratch directory!")
        if self.scratch_dir not in job_dir.parents:
            raise ValueError(f"Path traversal detected: {job_dir} is outside {self.scratch_dir}")

        if job_dir.exists() and job_dir.is_dir():
            shutil.rmtree(job_dir, ignore_errors=True)
            return True
        return False
