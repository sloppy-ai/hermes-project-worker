from __future__ import annotations

import plistlib
import sys
from pathlib import Path


DEFAULT_API_LABEL = "dev.nous.hermes-project-worker.api"
DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8765


def default_package_src() -> Path:
    return Path(__file__).resolve().parents[1]


def default_api_log_dir() -> Path:
    return Path.home() / "Library" / "Logs" / "hermes-project-worker"


def default_launch_agent_path(label: str = DEFAULT_API_LABEL) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def default_python_executable() -> str:
    return sys.executable


def build_launchctl_commands(path: str | Path, *, label: str = DEFAULT_API_LABEL) -> dict[str, str]:
    plist_path = Path(path)
    domain = f"gui/$(id -u)/{label}"
    return {
        "bootstrap_command": f"launchctl bootstrap gui/$(id -u) {plist_path}",
        "enable_command": f"launchctl enable {domain}",
        "kickstart_command": f"launchctl kickstart -k {domain}",
        "bootout_command": f"launchctl bootout gui/$(id -u) {plist_path}",
    }


def build_api_launch_agent_plist(
    *,
    label: str = DEFAULT_API_LABEL,
    python_executable: str | None = None,
    package_src: str | Path | None = None,
    host: str = DEFAULT_API_HOST,
    port: int = DEFAULT_API_PORT,
    log_dir: str | Path | None = None,
) -> str:
    python_cmd = python_executable or default_python_executable()
    src_dir = Path(package_src) if package_src is not None else default_package_src()
    logs = Path(log_dir) if log_dir is not None else default_api_log_dir()

    payload = {
        "Label": label,
        "ProgramArguments": [
            python_cmd,
            "-m",
            "hermes_project_worker",
            "api",
            "serve",
            "--host",
            host,
            "--port",
            str(port),
        ],
        "EnvironmentVariables": {
            "PYTHONPATH": str(src_dir),
        },
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "StandardOutPath": str(logs / "api.stdout.log"),
        "StandardErrorPath": str(logs / "api.stderr.log"),
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML).decode("utf-8")


def write_api_launch_agent_plist(
    *,
    path: str | Path | None = None,
    label: str = DEFAULT_API_LABEL,
    python_executable: str | None = None,
    package_src: str | Path | None = None,
    host: str = DEFAULT_API_HOST,
    port: int = DEFAULT_API_PORT,
    log_dir: str | Path | None = None,
) -> Path:
    plist_path = Path(path) if path is not None else default_launch_agent_path(label)
    logs = Path(log_dir) if log_dir is not None else default_api_log_dir()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(
        build_api_launch_agent_plist(
            label=label,
            python_executable=python_executable,
            package_src=package_src,
            host=host,
            port=port,
            log_dir=logs,
        ),
        encoding="utf-8",
    )
    return plist_path
