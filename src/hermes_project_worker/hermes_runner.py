from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from .models import ProjectConfig, ProjectEvent, ProjectState, RunResult
from .prompting import build_worker_prompt
from .repo import derive_branch_name, get_execution_path, resolve_repo_path
from .result_parser import parse_worker_result
from .store import ensure_run_dir


SubprocessRunner = Callable[..., object]


def _build_task_slug(events: list[ProjectEvent]) -> str:
    if not events:
        return "task"
    first = events[0]
    title = first.payload.get("title") or first.payload.get("reason") or first.type
    return str(title)


def _build_command(config: ProjectConfig, prompt: str) -> list[str]:
    command = [config.worker.command, "chat", "--quiet", "--profile", config.worker.profile]
    if config.worker.use_worktree:
        command.append("--worktree")
    if config.worker.provider:
        command.extend(["--provider", config.worker.provider])
    if config.worker.model:
        command.extend(["--model", config.worker.model])
    command.extend(["-q", prompt])
    return command


def _persist_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _persist_result(run_dir: Path, result: RunResult) -> None:
    _persist_text(run_dir / "result.json", json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    _persist_text(run_dir / "summary.txt", result.summary)


def run_project_worker(
    *,
    config: ProjectConfig,
    state: ProjectState,
    events: list[ProjectEvent],
    run_id: str,
    subprocess_runner: SubprocessRunner | None = None,
) -> RunResult:
    runner = subprocess_runner or subprocess.run
    run_dir = ensure_run_dir(config.name, run_id)

    repo_path = resolve_repo_path(config)
    branch_name = derive_branch_name(config, _build_task_slug(events))
    execution_path = get_execution_path(config, branch_name)
    cwd_path = execution_path if execution_path.exists() else repo_path

    prompt = build_worker_prompt(
        config=config,
        state=state,
        events=events,
        repo_path=str(repo_path),
        worktree_path=str(execution_path),
    )
    _persist_text(run_dir / "prompt.txt", prompt)

    command = _build_command(config, prompt)
    stdout = ""
    stderr = ""
    exit_code = 1

    try:
        completed = runner(
            command,
            cwd=str(cwd_path),
            capture_output=True,
            text=True,
            timeout=config.worker.timeout_minutes * 60,
        )
        stdout = str(getattr(completed, "stdout", "") or "")
        stderr = str(getattr(completed, "stderr", "") or "")
        exit_code = int(getattr(completed, "returncode", 1))
    except subprocess.TimeoutExpired as exc:
        stdout = str(exc.stdout or "")
        stderr = str(exc.stderr or "")
        exit_code = 124
        result = RunResult(
            success=False,
            exit_code=exit_code,
            status="failed",
            summary=f"worker timed out after {config.worker.timeout_minutes} minutes",
        )
        _persist_text(run_dir / "stdout.txt", stdout)
        _persist_text(run_dir / "stderr.txt", stderr)
        _persist_result(run_dir, result)
        return result

    _persist_text(run_dir / "stdout.txt", stdout)
    _persist_text(run_dir / "stderr.txt", stderr)

    try:
        result = parse_worker_result(stdout, exit_code=exit_code)
    except ValueError as exc:
        result = RunResult(
            success=False,
            exit_code=exit_code,
            status="failed",
            summary=str(exc),
        )

    _persist_result(run_dir, result)
    return result
