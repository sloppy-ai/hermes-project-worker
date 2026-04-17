import json
import plistlib
from pathlib import Path

from hermes_project_worker.launchd import build_api_launch_agent_plist, default_launch_agent_path, write_api_launch_agent_plist


def test_build_api_launch_agent_plist_uses_module_entrypoint_and_env(tmp_path):
    log_dir = tmp_path / "logs"

    payload = plistlib.loads(
        build_api_launch_agent_plist(
            label="dev.nous.hpw-api",
            python_executable="/venv/bin/python",
            package_src="/repo/src",
            host="127.0.0.1",
            port=8765,
            log_dir=log_dir,
        ).encode("utf-8")
    )

    assert payload["Label"] == "dev.nous.hpw-api"
    assert payload["ProgramArguments"] == [
        "/venv/bin/python",
        "-m",
        "hermes_project_worker",
        "api",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
    ]
    assert payload["EnvironmentVariables"] == {"PYTHONPATH": "/repo/src"}
    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] is True
    assert payload["StandardOutPath"] == str(log_dir / "api.stdout.log")
    assert payload["StandardErrorPath"] == str(log_dir / "api.stderr.log")


def test_write_api_launch_agent_plist_creates_parent_directories(tmp_path):
    path = tmp_path / "Library" / "LaunchAgents" / "dev.nous.hpw-api.plist"

    written = write_api_launch_agent_plist(
        path=path,
        label="dev.nous.hpw-api",
        python_executable="/venv/bin/python",
        package_src="/repo/src",
        host="127.0.0.1",
        port=9000,
        log_dir=tmp_path / "logs",
    )

    payload = plistlib.loads(path.read_bytes())

    assert written == path
    assert payload["ProgramArguments"][-1] == "9000"


def test_default_launch_agent_path_uses_home_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    path = default_launch_agent_path("dev.nous.hpw-api")

    assert path == tmp_path / "Library" / "LaunchAgents" / "dev.nous.hpw-api.plist"
