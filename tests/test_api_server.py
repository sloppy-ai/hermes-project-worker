import json
import threading
from urllib.request import Request, urlopen

from hermes_project_worker.api_client import ProjectWorkerApiClient
from hermes_project_worker.api_server import create_api_server
from hermes_project_worker.approvals import create_approval_request, set_pending_approval
from hermes_project_worker.manager import ProjectWorkerManager
from hermes_project_worker.models import ProjectConfig, ProjectEvent, RunResult, WorkerConfig
from hermes_project_worker.queue import append_event, list_events
from hermes_project_worker.store import ensure_run_dir, init_project, load_project_state, save_project_state


class _ServerHandle:
    def __init__(self, server):
        self.server = server
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self.server

    def __exit__(self, exc_type, exc, tb):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def _make_config(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    return ProjectConfig(
        name="demo",
        repo_path=str(repo_dir),
        mission="Test project",
        default_branch="main",
        worker=WorkerConfig(use_worktree=False),
        allowed_actions=["small_bugfixes"],
        approval_required_actions=["deploy"],
    )


def _url(server, path):
    host, port = server.server_address[:2]
    return f"http://{host}:{port}{path}"


def test_health_endpoint_returns_ok(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    server = create_api_server(host="127.0.0.1", port=0)

    with _ServerHandle(server):
        response = json.loads(urlopen(_url(server, "/health")).read().decode("utf-8"))

    assert response == {"status": "ok"}


def test_projects_endpoints_return_known_projects(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))
    server = create_api_server(host="127.0.0.1", port=0)
    client = ProjectWorkerApiClient(_url(server, ""))

    with _ServerHandle(server):
        listing = client.list_projects()
        project = client.get_project("demo")

    assert listing["projects"] == ["demo"]
    assert project["name"] == "demo"
    assert project["status"] == "idle"


def test_enqueue_endpoint_writes_pending_event(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))
    server = create_api_server(host="127.0.0.1", port=0)
    client = ProjectWorkerApiClient(_url(server, ""))

    with _ServerHandle(server):
        response = client.enqueue_event("demo", "manual.nudge", {"reason": "api test"})

    events = list_events("demo")

    assert response["event"]["type"] == "manual.nudge"
    assert events[0].payload == {"reason": "api test"}
    assert events[0].status == "pending"


def test_run_endpoint_triggers_manager_run(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))
    append_event(
        "demo",
        ProjectEvent(
            event_id="evt_001",
            project="demo",
            type="manual.nudge",
            source="api",
            created_at="2026-04-17T23:00:00Z",
            payload={"reason": "work now"},
        ),
    )

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
    server = create_api_server(host="127.0.0.1", port=0, manager=manager)
    client = ProjectWorkerApiClient(_url(server, ""))

    with _ServerHandle(server):
        response = client.run_project("demo")

    state = load_project_state("demo")

    assert response["result"]["summary"] == "Applied fix."
    assert len(calls) == 1
    assert state.status == "idle"
    assert state.last_summary == "Applied fix."


def test_approval_endpoints_mutate_state(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))
    state = load_project_state("demo")
    approval = create_approval_request(project="demo", task_class="deploy", reason="Deploy needs approval.")
    save_project_state(set_pending_approval(state, approval))

    server = create_api_server(host="127.0.0.1", port=0)
    client = ProjectWorkerApiClient(_url(server, ""))

    with _ServerHandle(server):
        approvals = client.list_approvals("demo")
        approve_response = client.approve("demo", approval.approval_id)

    approved_state = load_project_state("demo")

    assert approvals["approvals"][0]["approval_id"] == approval.approval_id
    assert approve_response["state"]["status"] == "idle"
    assert approved_state.status == "idle"


def test_reject_endpoint_blocks_project(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))
    state = load_project_state("demo")
    approval = create_approval_request(project="demo", task_class="deploy", reason="Deploy needs approval.")
    save_project_state(set_pending_approval(state, approval))

    server = create_api_server(host="127.0.0.1", port=0)
    client = ProjectWorkerApiClient(_url(server, ""))

    with _ServerHandle(server):
        reject_response = client.reject("demo", approval.approval_id, reason="No deploy today.")

    rejected_state = load_project_state("demo")

    assert reject_response["state"]["status"] == "blocked"
    assert rejected_state.status == "blocked"
    assert rejected_state.blocked_reason == "No deploy today."


def test_events_and_runs_endpoints_return_persisted_records(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))
    append_event(
        "demo",
        ProjectEvent(
            event_id="evt_001",
            project="demo",
            type="manual.nudge",
            source="api",
            created_at="2026-04-17T23:00:00Z",
            payload={"reason": "work now"},
        ),
    )
    run_dir = ensure_run_dir("demo", "run_001")
    (run_dir / "result.json").write_text(
        json.dumps({"status": "completed", "summary": "Applied fix.", "success": True}, indent=2),
        encoding="utf-8",
    )

    server = create_api_server(host="127.0.0.1", port=0)
    client = ProjectWorkerApiClient(_url(server, ""))

    with _ServerHandle(server):
        events = client.list_events("demo")
        runs = client.list_runs("demo")

    assert events["events"][0]["event_id"] == "evt_001"
    assert events["events"][0]["type"] == "manual.nudge"
    assert runs["runs"][0]["run_id"] == "run_001"
    assert runs["runs"][0]["summary"] == "Applied fix."
