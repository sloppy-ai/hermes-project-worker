from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .models import ProjectConfig, ProjectState


def get_projects_root() -> Path:
    override = os.getenv("HPW_PROJECTS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".hermes" / "projects"


def get_project_dir(project_name: str) -> Path:
    return get_projects_root() / project_name


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.stem}_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False))


def _atomic_write_yaml(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_text(path, yaml.safe_dump(payload, sort_keys=False))


def save_project_config(config: ProjectConfig) -> Path:
    path = get_project_dir(config.name) / "project.yaml"
    _atomic_write_yaml(path, config.to_dict())
    return path


def load_project_config(project_name: str) -> ProjectConfig:
    path = get_project_dir(project_name) / "project.yaml"
    if not path.exists():
        raise FileNotFoundError(f"missing project config: {project_name}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return ProjectConfig.from_dict(data)


def save_project_state(state: ProjectState) -> Path:
    path = get_project_dir(state.project) / "state.json"
    _atomic_write_json(path, state.to_dict())
    return path


def load_project_state(project_name: str) -> ProjectState:
    path = get_project_dir(project_name) / "state.json"
    if not path.exists():
        raise FileNotFoundError(f"missing project state: {project_name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return ProjectState.from_dict(data)


def init_project(config: ProjectConfig, *, overwrite: bool = False) -> Path:
    project_dir = get_project_dir(config.name)
    if project_dir.exists() and not overwrite and (project_dir / "project.yaml").exists():
        raise FileExistsError(f"project already exists: {config.name}")

    project_dir.mkdir(parents=True, exist_ok=True)
    for subdir in ("runs", "artifacts", "locks"):
        (project_dir / subdir).mkdir(parents=True, exist_ok=True)

    save_project_config(config)
    save_project_state(ProjectState.default_for_project(config.name))

    queue_path = project_dir / "queue.jsonl"
    if overwrite or not queue_path.exists():
        _atomic_write_text(queue_path, "")

    return project_dir


def list_projects() -> list[str]:
    root = get_projects_root()
    if not root.exists():
        return []

    projects: list[str] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "project.yaml").exists() and (child / "state.json").exists():
            projects.append(child.name)
    return projects


def get_queue_path(project_name: str) -> Path:
    return get_project_dir(project_name) / "queue.jsonl"


def ensure_run_dir(project_name: str, run_id: str) -> Path:
    run_dir = get_project_dir(project_name) / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def list_runs(project_name: str) -> list[dict[str, Any]]:
    runs_dir = get_project_dir(project_name) / "runs"
    if not runs_dir.exists():
        return []

    runs: list[dict[str, Any]] = []
    for child in sorted(runs_dir.iterdir(), key=lambda item: item.name, reverse=True):
        if not child.is_dir():
            continue
        result_path = child / "result.json"
        if not result_path.exists():
            continue
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        runs.append({"run_id": child.name, **payload})
    return runs
