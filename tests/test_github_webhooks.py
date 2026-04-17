import hashlib
import hmac
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from hermes_project_worker.models import ProjectConfig, WorkerConfig
from hermes_project_worker.queue import list_events
from hermes_project_worker.store import init_project
from hermes_project_worker.webhooks.server import create_webhook_server


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
        webhook_provider="github",
        webhook_route="demo-route",
        webhook_secret_env="HPW_GITHUB_WEBHOOK_SECRET",
    )


def _url(server, path):
    host, port = server.server_address[:2]
    return f"http://{host}:{port}{path}"


def _signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_github_webhook_enqueues_normalized_event(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    monkeypatch.setenv("HPW_GITHUB_WEBHOOK_SECRET", "topsecret")
    init_project(_make_config(tmp_path))
    server = create_webhook_server(host="127.0.0.1", port=0)

    payload = {
        "action": "opened",
        "repository": {"full_name": "example/demo"},
        "issue": {"number": 184, "title": "CI fails on macOS"},
    }
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        _url(server, "/webhooks/github/demo-route"),
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "delivery-001",
            "X-Hub-Signature-256": _signature("topsecret", body),
        },
        method="POST",
    )

    with _ServerHandle(server):
        response = urlopen(request)
        result = json.loads(response.read().decode("utf-8"))

    events = list_events("demo")

    assert response.status == 202
    assert result["status"] == "accepted"
    assert events[0].type == "github.issues.opened"
    assert events[0].payload["issue_number"] == 184
    assert events[0].payload["title"] == "CI fails on macOS"
    assert events[0].payload["delivery_id"] == "delivery-001"


def test_github_webhook_rejects_invalid_signature(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    monkeypatch.setenv("HPW_GITHUB_WEBHOOK_SECRET", "topsecret")
    init_project(_make_config(tmp_path))
    server = create_webhook_server(host="127.0.0.1", port=0)

    body = json.dumps({"action": "opened"}).encode("utf-8")
    request = Request(
        _url(server, "/webhooks/github/demo-route"),
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "delivery-001",
            "X-Hub-Signature-256": "sha256=deadbeef",
        },
        method="POST",
    )

    with _ServerHandle(server):
        try:
            urlopen(request)
            assert False, "expected HTTPError"
        except HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 401
            assert "signature" in payload["error"].lower()

    assert list_events("demo") == []


def test_github_webhook_returns_404_for_unknown_route(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    server = create_webhook_server(host="127.0.0.1", port=0)

    body = json.dumps({"zen": "keep it logically awesome"}).encode("utf-8")
    request = Request(
        _url(server, "/webhooks/github/missing-route"),
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "ping",
            "X-GitHub-Delivery": "delivery-404",
        },
        method="POST",
    )

    with _ServerHandle(server):
        try:
            urlopen(request)
            assert False, "expected HTTPError"
        except HTTPError as exc:
            assert exc.code == 404


def test_github_webhook_dedupes_repeated_delivery_ids(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    monkeypatch.setenv("HPW_GITHUB_WEBHOOK_SECRET", "topsecret")
    init_project(_make_config(tmp_path))
    server = create_webhook_server(host="127.0.0.1", port=0)

    payload = {
        "action": "opened",
        "repository": {"full_name": "example/demo"},
        "pull_request": {"number": 9, "title": "Fix CI"},
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": "delivery-repeat",
        "X-Hub-Signature-256": _signature("topsecret", body),
    }

    with _ServerHandle(server):
        for _ in range(2):
            request = Request(_url(server, "/webhooks/github/demo-route"), data=body, headers=headers, method="POST")
            response = urlopen(request)
            assert response.status == 202

    events = list_events("demo")

    assert len(events) == 1
    assert events[0].dedupe_key == "github.delivery:delivery-repeat"


def test_github_webhook_accepts_push_event_normalization(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    monkeypatch.setenv("HPW_GITHUB_WEBHOOK_SECRET", "topsecret")
    init_project(_make_config(tmp_path))
    server = create_webhook_server(host="127.0.0.1", port=0)

    payload = {
        "ref": "refs/heads/main",
        "repository": {"full_name": "example/demo"},
        "head_commit": {"id": "abc123", "message": "Update README"},
    }
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        _url(server, "/webhooks/github/demo-route"),
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": "delivery-push",
            "X-Hub-Signature-256": _signature("topsecret", body),
        },
        method="POST",
    )

    with _ServerHandle(server):
        response = urlopen(request)
        assert response.status == 202

    event = list_events("demo")[0]

    assert event.type == "github.push"
    assert event.payload["ref"] == "refs/heads/main"
    assert event.payload["head_commit_id"] == "abc123"
    assert event.payload["title"] == "Update README"
