from pathlib import Path

from hermes_project_worker.models import ProjectConfig, ProjectState, WorkerConfig
from hermes_project_worker.store import (
    ensure_run_dir,
    get_projects_root,
    init_project,
    list_projects,
    load_project_config,
    load_project_state,
    save_project_state,
)


def test_projects_root_uses_env_override(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))

    assert get_projects_root() == projects_dir


def test_init_project_creates_expected_layout(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))

    config = ProjectConfig(
        name="demo",
        repo_path="/tmp/demo",
        mission="Test project",
        default_branch="main",
        worker=WorkerConfig(),
        allowed_actions=["small_bugfixes"],
        approval_required_actions=["deploy"],
    )

    project_dir = init_project(config)

    assert project_dir == projects_dir / "demo"
    assert (project_dir / "project.yaml").exists()
    assert (project_dir / "state.json").exists()
    assert (project_dir / "queue.jsonl").exists()
    assert (project_dir / "runs").is_dir()
    assert (project_dir / "artifacts").is_dir()
    assert (project_dir / "locks").is_dir()


def test_config_round_trip(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))

    config = ProjectConfig(
        name="demo",
        repo_path="/tmp/demo",
        mission="Test project",
        default_branch="main",
        worker=WorkerConfig(profile="codex"),
        allowed_actions=["small_bugfixes"],
        approval_required_actions=["deploy"],
    )
    init_project(config)

    restored = load_project_config("demo")

    assert restored == config
    assert restored.worker.profile == "codex"


def test_state_round_trip(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))

    config = ProjectConfig(
        name="demo",
        repo_path="/tmp/demo",
        mission="Test project",
        default_branch="main",
        worker=WorkerConfig(),
        allowed_actions=["small_bugfixes"],
        approval_required_actions=["deploy"],
    )
    init_project(config)

    state = load_project_state("demo")
    state.status = "blocked"
    state.blocked_reason = "Waiting on input"
    save_project_state(state)

    restored = load_project_state("demo")

    assert restored.status == "blocked"
    assert restored.blocked_reason == "Waiting on input"


def test_list_projects_returns_initialized_projects(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))

    init_project(
        ProjectConfig(
            name="alpha",
            repo_path="/tmp/alpha",
            mission="Alpha",
            default_branch="main",
            worker=WorkerConfig(),
            allowed_actions=["small_bugfixes"],
            approval_required_actions=["deploy"],
        )
    )
    init_project(
        ProjectConfig(
            name="beta",
            repo_path="/tmp/beta",
            mission="Beta",
            default_branch="main",
            worker=WorkerConfig(),
            allowed_actions=["small_bugfixes"],
            approval_required_actions=["deploy"],
        )
    )
    orphan = projects_dir / "orphan"
    orphan.mkdir(parents=True)

    assert list_projects() == ["alpha", "beta"]


def test_ensure_run_dir_creates_run_directory(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))

    init_project(
        ProjectConfig(
            name="demo",
            repo_path="/tmp/demo",
            mission="Test project",
            default_branch="main",
            worker=WorkerConfig(),
            allowed_actions=["small_bugfixes"],
            approval_required_actions=["deploy"],
        )
    )

    run_dir = ensure_run_dir("demo", "run_001")

    assert run_dir == Path(projects_dir / "demo" / "runs" / "run_001")
    assert run_dir.is_dir()
