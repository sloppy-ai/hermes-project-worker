import json
from pathlib import Path

from hermes_project_worker.hermes_runner import run_project_worker
from hermes_project_worker.models import ProjectConfig, ProjectEvent, ProjectState, WorkerConfig
from hermes_project_worker.store import init_project, load_project_state


class _CompletedProcess:
    def __init__(self, *, stdout: str, stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _make_config(tmp_path, *, use_worktree=False):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    return ProjectConfig(
        name="demo",
        repo_path=str(repo_dir),
        mission="Test project",
        default_branch="main",
        worker=WorkerConfig(use_worktree=use_worktree),
        allowed_actions=["small_bugfixes"],
        approval_required_actions=["deploy"],
    )


def _make_event() -> ProjectEvent:
    return ProjectEvent(
        event_id="evt_001",
        project="demo",
        type="manual.nudge",
        source="cli",
        created_at="2026-04-17T23:00:00Z",
        payload={"reason": "test local run"},
    )


def _valid_output() -> str:
    return """Completed the requested work.

--- PROJECT_WORKER_RESULT ---
status: completed
task_class: small_bugfixes
summary: Fixed the issue.
branch_name: hermes/fix-ci
pr_url:
needs_approval: false
approval_reason:
followup_event:
"""


def test_run_project_worker_writes_prompt_file(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))

    config = _make_config(tmp_path)
    init_project(config)
    state = load_project_state("demo")
    calls = {}

    def fake_subprocess(command, **kwargs):
        calls["command"] = command
        calls["cwd"] = kwargs["cwd"]
        calls["timeout"] = kwargs["timeout"]
        return _CompletedProcess(stdout=_valid_output())

    run_project_worker(
        config=config,
        state=state,
        events=[_make_event()],
        run_id="run_001",
        subprocess_runner=fake_subprocess,
    )

    prompt_path = projects_dir / "demo" / "runs" / "run_001" / "prompt.txt"
    assert prompt_path.exists()
    assert "Mission" in prompt_path.read_text(encoding="utf-8")
    assert Path(calls["cwd"]) == (tmp_path / "repo").resolve()
    assert calls["timeout"] == 45 * 60


def test_run_project_worker_persists_stdout_and_stderr(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))

    config = _make_config(tmp_path)
    init_project(config)
    state = load_project_state("demo")

    def fake_subprocess(_command, **_kwargs):
        return _CompletedProcess(stdout=_valid_output(), stderr="warning: noisy but fine")

    run_project_worker(
        config=config,
        state=state,
        events=[_make_event()],
        run_id="run_002",
        subprocess_runner=fake_subprocess,
    )

    run_dir = projects_dir / "demo" / "runs" / "run_002"
    assert run_dir.joinpath("stdout.txt").read_text(encoding="utf-8") == _valid_output()
    assert run_dir.joinpath("stderr.txt").read_text(encoding="utf-8") == "warning: noisy but fine"


def test_run_project_worker_returns_structured_result_for_valid_footer(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))

    config = _make_config(tmp_path)
    init_project(config)
    state = load_project_state("demo")

    def fake_subprocess(_command, **_kwargs):
        return _CompletedProcess(stdout=_valid_output())

    result = run_project_worker(
        config=config,
        state=state,
        events=[_make_event()],
        run_id="run_003",
        subprocess_runner=fake_subprocess,
    )

    run_dir = projects_dir / "demo" / "runs" / "run_003"
    persisted = json.loads(run_dir.joinpath("result.json").read_text(encoding="utf-8"))

    assert result.success is True
    assert result.status == "completed"
    assert result.summary == "Fixed the issue."
    assert result.task_class == "small_bugfixes"
    assert result.branch_name == "hermes/fix-ci"
    assert persisted["summary"] == "Fixed the issue."
    assert run_dir.joinpath("summary.txt").read_text(encoding="utf-8") == "Fixed the issue."


def test_run_project_worker_returns_failed_result_when_footer_is_missing(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))

    config = _make_config(tmp_path)
    init_project(config)
    state = load_project_state("demo")

    def fake_subprocess(_command, **_kwargs):
        return _CompletedProcess(stdout="Narrative only, no machine-readable footer.")

    result = run_project_worker(
        config=config,
        state=state,
        events=[_make_event()],
        run_id="run_004",
        subprocess_runner=fake_subprocess,
    )

    assert result.success is False
    assert result.status == "failed"
    assert "footer" in result.summary.lower()


def test_run_project_worker_surfaces_nonzero_exit_code(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))

    config = _make_config(tmp_path)
    init_project(config)
    state = load_project_state("demo")

    def fake_subprocess(_command, **_kwargs):
        return _CompletedProcess(stdout=_valid_output(), stderr="bad exit", returncode=7)

    result = run_project_worker(
        config=config,
        state=state,
        events=[_make_event()],
        run_id="run_005",
        subprocess_runner=fake_subprocess,
    )

    assert result.success is False
    assert result.exit_code == 7
    assert result.status == "completed"
    assert (projects_dir / "demo" / "runs" / "run_005" / "stderr.txt").read_text(encoding="utf-8") == "bad exit"
