import json

import pytest

from hermes_project_worker.approvals import create_approval_request, set_pending_approval
from hermes_project_worker.cli import build_parser, main
from hermes_project_worker.models import ProjectConfig, ProjectEvent, RunResult, WorkerConfig
from hermes_project_worker.queue import append_event, list_events
from hermes_project_worker.store import init_project, load_project_state, save_project_state


def _make_config(tmp_path):
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
    )


def test_build_parser_exposes_project_enqueue_command():
    parser = build_parser()

    args = parser.parse_args(["project", "enqueue", "demo", "--type", "manual.nudge", "--payload", '{"reason":"work now"}'])

    assert args.command == "project"
    assert args.project_command == "enqueue"
    assert args.name == "demo"
    assert args.type == "manual.nudge"


def test_build_parser_exposes_manager_api_webhook_and_mcp_commands():
    parser = build_parser()

    manager_args = parser.parse_args(["manager", "run"])
    api_args = parser.parse_args(["api", "serve", "--host", "127.0.0.1", "--port", "9898"])
    api_launchd_args = parser.parse_args([
        "api",
        "write-launchd",
        "--path",
        "/tmp/hpw-api.plist",
        "--python",
        "/venv/bin/python",
        "--src",
        "/repo/src",
    ])
    webhook_args = parser.parse_args(["webhook", "serve", "--host", "127.0.0.1", "--port", "9899"])
    mcp_args = parser.parse_args(["mcp", "serve"])

    assert manager_args.command == "manager"
    assert manager_args.manager_command == "run"
    assert api_args.command == "api"
    assert api_args.api_command == "serve"
    assert api_args.host == "127.0.0.1"
    assert api_args.port == 9898
    assert api_launchd_args.command == "api"
    assert api_launchd_args.api_command == "write-launchd"
    assert api_launchd_args.path == "/tmp/hpw-api.plist"
    assert api_launchd_args.python == "/venv/bin/python"
    assert api_launchd_args.src == "/repo/src"
    assert webhook_args.command == "webhook"
    assert webhook_args.webhook_command == "serve"
    assert webhook_args.port == 9899
    assert mcp_args.command == "mcp"
    assert mcp_args.mcp_command == "serve"


def test_main_returns_zero_for_help(capsys):
    exit_code = main(["--help"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "usage:" in captured.out.lower()


def test_project_init_creates_project_files(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))

    exit_code = main(["project", "init", "demo", "--repo", str(repo_dir)])

    assert exit_code == 0
    assert (projects_dir / "demo" / "project.yaml").exists()
    assert (projects_dir / "demo" / "state.json").exists()
    assert (projects_dir / "demo" / "queue.jsonl").exists()


def test_project_list_command_prints_empty_message(monkeypatch, capsys):
    monkeypatch.setattr("hermes_project_worker.cli.list_projects", lambda: [])

    exit_code = main(["project", "list"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "No projects found." in captured.out


def test_project_enqueue_writes_pending_event(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))

    exit_code = main([
        "project",
        "enqueue",
        "demo",
        "--type",
        "manual.nudge",
        "--payload",
        '{"reason": "work now"}',
    ])

    events = list_events("demo")

    assert exit_code == 0
    assert len(events) == 1
    assert events[0].type == "manual.nudge"
    assert events[0].payload == {"reason": "work now"}
    assert events[0].status == "pending"


def test_project_run_calls_runner_and_updates_state(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))
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
    calls = {}

    def fake_runner(*, config, state, events, run_id, subprocess_runner=None):
        calls["project"] = config.name
        calls["event_ids"] = [event.event_id for event in events]
        calls["run_id"] = run_id
        return RunResult(
            success=True,
            exit_code=0,
            status="completed",
            summary="Applied fix.",
            task_class="small_bugfixes",
            branch_name="hermes/fix-ci",
        )

    monkeypatch.setattr("hermes_project_worker.cli.run_project_worker", fake_runner)

    exit_code = main(["project", "run", "demo"])

    state = load_project_state("demo")
    events = list_events("demo")

    assert exit_code == 0
    assert calls["project"] == "demo"
    assert calls["event_ids"] == ["evt_001"]
    assert calls["run_id"].startswith("run_")
    assert state.status == "idle"
    assert state.current_run_id is None
    assert state.last_summary == "Applied fix."
    assert events[0].status == "completed"


def test_project_approvals_prints_pending_approval(monkeypatch, tmp_path, capsys):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))
    state = load_project_state("demo")
    approval = create_approval_request(project="demo", task_class="deploy", reason="Deploy needs approval.")
    save_project_state(set_pending_approval(state, approval))

    exit_code = main(["project", "approvals", "demo"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["approvals"][0]["approval_id"] == approval.approval_id


def test_project_approve_clears_pending_state(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))
    state = load_project_state("demo")
    approval = create_approval_request(project="demo", task_class="deploy", reason="Deploy needs approval.")
    save_project_state(set_pending_approval(state, approval))

    exit_code = main(["project", "approve", "demo", approval.approval_id])

    restored = load_project_state("demo")

    assert exit_code == 0
    assert restored.status == "idle"
    assert restored.pending_approval is None


def test_project_reject_blocks_project(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))
    state = load_project_state("demo")
    approval = create_approval_request(project="demo", task_class="deploy", reason="Deploy needs approval.")
    save_project_state(set_pending_approval(state, approval))

    exit_code = main(["project", "reject", "demo", approval.approval_id, "--reason", "No deploy today."])

    restored = load_project_state("demo")

    assert exit_code == 0
    assert restored.status == "blocked"
    assert restored.blocked_reason == "No deploy today."


def test_manager_run_invokes_manager_once(monkeypatch):
    calls = []

    class FakeManager:
        def run_once(self):
            calls.append("run_once")
            return 2

    monkeypatch.setattr("hermes_project_worker.cli.ProjectWorkerManager", FakeManager)

    exit_code = main(["manager", "run"])

    assert exit_code == 0
    assert calls == ["run_once"]


def test_api_serve_invokes_api_server(monkeypatch):
    calls = {}

    def fake_serve_api(*, host, port):
        calls["host"] = host
        calls["port"] = port

    monkeypatch.setattr("hermes_project_worker.cli.serve_api", fake_serve_api)

    exit_code = main(["api", "serve", "--host", "127.0.0.1", "--port", "9898"])

    assert exit_code == 0
    assert calls == {"host": "127.0.0.1", "port": 9898}


def test_api_write_launchd_writes_plist_and_prints_bootstrap_instructions(monkeypatch, capsys, tmp_path):
    calls = {}

    def fake_write_api_launch_agent_plist(**kwargs):
        calls.update(kwargs)
        return tmp_path / "Library" / "LaunchAgents" / "dev.nous.hpw-api.plist"

    monkeypatch.setattr("hermes_project_worker.cli.write_api_launch_agent_plist", fake_write_api_launch_agent_plist)

    exit_code = main([
        "api",
        "write-launchd",
        "--path",
        str(tmp_path / "hpw-api.plist"),
        "--python",
        "/venv/bin/python",
        "--src",
        "/repo/src",
    ])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert calls["path"] == tmp_path / "hpw-api.plist"
    assert calls["python_executable"] == "/venv/bin/python"
    assert calls["package_src"] == "/repo/src"
    assert payload["launch_agent_path"].endswith("dev.nous.hpw-api.plist")
    assert "launchctl bootstrap" in payload["bootstrap_command"]


def test_webhook_serve_invokes_webhook_server(monkeypatch):
    calls = {}

    def fake_serve_webhooks(*, host, port):
        calls["host"] = host
        calls["port"] = port

    monkeypatch.setattr("hermes_project_worker.cli.serve_webhooks", fake_serve_webhooks)

    exit_code = main(["webhook", "serve", "--host", "127.0.0.1", "--port", "9899"])

    assert exit_code == 0
    assert calls == {"host": "127.0.0.1", "port": 9899}


def test_mcp_serve_invokes_mcp_server(monkeypatch):
    calls = []

    def fake_serve_mcp():
        calls.append("serve")

    monkeypatch.setattr("hermes_project_worker.cli.serve_mcp", fake_serve_mcp)

    exit_code = main(["mcp", "serve"])

    assert exit_code == 0
    assert calls == ["serve"]


def test_project_show_returns_nonzero_for_missing_project(monkeypatch, capsys):
    def _raise(_name: str):
        raise FileNotFoundError("missing project")

    monkeypatch.setattr("hermes_project_worker.cli.load_project_config", _raise)

    exit_code = main(["project", "show", "ghost"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "missing project" in captured.err
