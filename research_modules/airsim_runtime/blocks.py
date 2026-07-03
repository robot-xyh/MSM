"""Process management for the Blocks binary."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from typing import Any


@dataclass
class BlocksProcessManager:
    """Launch and stop Blocks with a repo-local settings file."""

    blocks_script: Path
    settings_path: Path
    output_dir: Path
    extra_args: tuple[str, ...] = ()
    prefer_nvidia_offload: bool = True
    process: subprocess.Popen[str] | None = None

    def start(self) -> subprocess.Popen[str]:
        if self.process is not None and self.process.poll() is None:
            return self.process
        script = self.blocks_script.resolve()
        settings = self.settings_path.resolve()
        if not script.exists():
            raise FileNotFoundError(f"Blocks script not found: {script}")
        if not settings.exists():
            raise FileNotFoundError(f"AirSim settings file not found: {settings}")
        if not self._wait_for_rpc_port_closed(timeout_s=60.0):
            settings_payload = self._read_settings()
            host = str(settings_payload.get("LocalHostIp") or "127.0.0.1")
            port = int(settings_payload.get("ApiServerPort", 41451))
            raise RuntimeError(f"AirSim RPC port {host}:{port} is still open before Blocks launch")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.output_dir / "blocks_stdout_stderr.log"
        log_stream = log_path.open("w", encoding="utf-8")
        env = os.environ.copy()
        if self.prefer_nvidia_offload:
            env.setdefault("__NV_PRIME_RENDER_OFFLOAD", "1")
            env.setdefault("__GLX_VENDOR_LIBRARY_NAME", "nvidia")
            env.setdefault("__VK_LAYER_NV_optimus", "NVIDIA_only")
        command = [str(script), f"-settings={settings}", *self.extra_args]
        if not os.access(script, os.X_OK):
            command = ["bash", *command]
        self.process = subprocess.Popen(
            command,
            cwd=str(script.parent),
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        return self.process

    def stop(self, timeout_s: float = 8.0) -> None:
        if self.process is None:
            return
        if self.process.poll() is not None:
            self._wait_for_rpc_port_closed(timeout_s=timeout_s)
            return
        self.process.terminate()
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self._wait_for_rpc_port_closed(timeout_s=max(0.0, deadline - time.monotonic()))
                return
            time.sleep(0.2)
        self.process.kill()
        self.process.wait(timeout=5.0)
        self._wait_for_rpc_port_closed(timeout_s=timeout_s)

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def returncode(self) -> int | None:
        if self.process is None:
            return None
        return self.process.poll()

    @property
    def log_path(self) -> Path:
        return self.output_dir / "blocks_stdout_stderr.log"

    def read_log(self) -> str:
        if not self.log_path.exists():
            return ""
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def log_tail(self, line_count: int = 80) -> str:
        lines = self.read_log().splitlines()
        return "\n".join(lines[-line_count:])

    def diagnostics(self) -> dict[str, Any]:
        """Return actionable launch diagnostics from settings, logs, and port state."""
        settings = self._read_settings()
        api_host = str(settings.get("LocalHostIp") or "127.0.0.1")
        api_port = int(settings.get("ApiServerPort", 41451))
        log_text = self.read_log()
        lines = log_text.splitlines()
        command_lines = [line for line in lines if "LogInit: Command Line:" in line]
        vehicle_names = sorted(str(name) for name in settings.get("Vehicles", {}).keys())
        vehicle_log_hits = {
            name: (f"LogTemp: {name}" in log_text or f"\n{name}\n" in f"\n{log_text}\n")
            for name in vehicle_names
        }
        settings_path = str(self.settings_path.resolve())
        diagnostics = {
            "settings_path": settings_path,
            "settings_exists": self.settings_path.exists(),
            "api_host": api_host,
            "api_port": api_port,
            "rpc_port_status": _tcp_port_status(api_host, api_port),
            "process_running": self.is_running(),
            "process_returncode": self.returncode(),
            "command_line": command_lines[-1] if command_lines else "",
            "command_line_uses_settings_path": any(settings_path in line for line in command_lines),
            "loaded_settings_path_seen": (
                "Loaded settings from" in log_text and settings_path in log_text
            ),
            "game_mode_seen": "Game class is 'AirSimGameMode'" in log_text,
            "engine_initialized_seen": "Engine is initialized" in log_text,
            "api_server_disabled_seen": "API server is disabled in settings" in log_text,
            "rpc_start_failure_seen": "Cannot start RpcLib Server" in log_text,
            "openxr_error_count": log_text.count("OpenXR-Loader"),
            "hmd_error_count": log_text.count("LogHMD: Failed to enumerate extensions"),
            "vehicle_names_from_settings": vehicle_names,
            "vehicle_log_hits": vehicle_log_hits,
            "log_line_count": len(lines),
            "log_tail": self.log_tail(),
        }
        return diagnostics

    def write_diagnostics(self) -> Path:
        path = self.output_dir / "blocks_diagnostics.json"
        path.write_text(
            json.dumps(self.diagnostics(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    def format_diagnostics(self) -> str:
        diagnostics = self.diagnostics()
        tail = diagnostics.pop("log_tail", "")
        payload = json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True)
        if tail:
            return f"{payload}\n\n--- blocks log tail ---\n{tail}"
        return payload

    def _read_settings(self) -> dict[str, Any]:
        if not self.settings_path.exists():
            return {}
        try:
            return json.loads(self.settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _wait_for_rpc_port_closed(self, timeout_s: float = 8.0) -> bool:
        settings = self._read_settings()
        host = str(settings.get("LocalHostIp") or "127.0.0.1")
        port = int(settings.get("ApiServerPort", 41451))
        deadline = time.monotonic() + max(0.0, timeout_s)
        while time.monotonic() < deadline:
            if _tcp_port_status(host, port) != "open":
                return True
            time.sleep(0.2)
        return _tcp_port_status(host, port) != "open"


def _tcp_port_status(host: str, port: int) -> str:
    target_host = host or "127.0.0.1"
    try:
        with socket.create_connection((target_host, port), timeout=0.2):
            return "open"
    except ConnectionRefusedError:
        return "closed_refused"
    except TimeoutError:
        return "closed_timeout"
    except OSError as exc:
        return f"unreachable:{exc.__class__.__name__}"
