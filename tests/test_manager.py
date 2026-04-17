from hermes_project_worker.manager import ProjectWorkerManager
from hermes_project_worker.models import ProjectConfig, ProjectEvent, RunResult, WorkerConfig
from hermes_project_worker.queue import append_event, list_events
from hermes_project_worker.store import init_project, load_project_config, load_project_state


def _make_config(tmp_path, *, heartbeat_enabled=False, heartbeat_interval_seconds=3600):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir(exist_ok=True)
    return ProjectConfig(
        name="demo",
        repo_path=str(repo_dir),
        mission="Test project",
        default_branch="main",
        worker=WorkerConfig(use_worktree=False),
        allowed_actions=["small_bugfixes"],
        approval_required_actions=["deploy"],
        heartbeat_enabled=heartbeat_enabled,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
    )


def _append_manual_event():
    append_event(
        "demo",
        ProjectEvent(
            event_id="evt_001",
            project="demo",
            type="manual.nudge",
            source="cli",
            created_at="2026-04-17T23:00:00Z",
            payload={"reason": "work now"},
        ),
    )


def test_manager_skips_locked_project(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))
    _append_manual_event()
    calls = []

    def fake_runner(**_kwargs):
        calls.append("called")
        return RunResult(success=True, exit_code=0, status="completed", summary="done", task_class="small_bugfixes")

    manager = ProjectWorkerManager(runner=fake_runner)
    manager.lock_project("demo")

    result = manager.process_project("demo")

    assert result is None
    assert calls == []
    assert list_events("demo", status="pending")[0].event_id == "evt_001"


def test_manager_claims_pending_events_and_dispatches_one_run(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))
    _append_manual_event()
    calls = []

    def fake_runner(**kwargs):
        calls.append(kwargs)
        return RunResult(
            success=True,
            exit_code=0,
            status="completed",
            summary="Applied fix.",
            task_class="small_bugfixes",
            branch_name="hermes/fix-ci",
        )

    manager = ProjectWorkerManager(runner=fake_runner)
    result = manager.process_project("demo")

    state = load_project_state("demo")
    events = list_events("demo")

    assert result is not None
    assert len(calls) == 1
    assert [event.event_id for event in calls[0]["events"]] == ["evt_001"]
    assert state.status == "idle"
    assert state.last_summary == "Applied fix."
    assert state.open_branch == "hermes/fix-ci"
    assert events[0].status == "completed"


def test_manager_writes_running_state_before_dispatch(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))
    _append_manual_event()
    observed = {}

    def fake_runner(**kwargs):
        observed["arg_status"] = kwargs["state"].status
        observed["stored_status"] = load_project_state("demo").status
        return RunResult(success=True, exit_code=0, status="completed", summary="done", task_class="small_bugfixes")

    manager = ProjectWorkerManager(runner=fake_runner)
    manager.process_project("demo")

    assert observed["arg_status"] == "running"
    assert observed["stored_status"] == "running"
    assert load_project_state("demo").status == "idle"


def test_manager_enqueues_heartbeat_when_due(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    config = _make_config(tmp_path, heartbeat_enabled=True, heartbeat_interval_seconds=60)
    init_project(config)

    manager = ProjectWorkerManager(now_provider=lambda: "2026-04-18T00:02:00Z")
    state = load_project_state("demo")
    state.last_event_at = "2026-04-18T00:00:00Z"
    from hermes_project_worker.store import save_project_state
    save_project_state(state)

    created = manager.enqueue_due_heartbeats()
    events = list_events("demo", status="pending")

    assert created == 1
    assert len(events) == 1
    assert events[0].type == "heartbeat"


def test_manager_marks_approval_required_result_as_awaiting_approval(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))
    _append_manual_event()

    def fake_runner(**_kwargs):
        return RunResult(
            success=False,
            exit_code=0,
            status="awaiting_approval",
            summary="Need approval before deploy.",
            task_class="deploy",
            needs_approval=True,
            approval_reason="Deploy requires approval.",
        )

    manager = ProjectWorkerManager(runner=fake_runner)
    manager.process_project("demo")

    state = load_project_state("demo")
    events = list_events("demo")

    assert state.status == "awaiting_approval"
    assert state.pending_approval is not None
    assert state.pending_approval["task_class"] == "deploy"
    assert state.blocked_reason == "Deploy requires approval."
    assert events[0].status == "completed"
