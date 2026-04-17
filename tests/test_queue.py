from hermes_project_worker.models import ProjectConfig, ProjectEvent, WorkerConfig
from hermes_project_worker.queue import (
    append_event,
    claim_pending_events,
    list_events,
    mark_event_status,
)
from hermes_project_worker.store import init_project


def _config(name: str = "demo") -> ProjectConfig:
    return ProjectConfig(
        name=name,
        repo_path=f"/tmp/{name}",
        mission="Test project",
        default_branch="main",
        worker=WorkerConfig(),
        allowed_actions=["small_bugfixes"],
        approval_required_actions=["deploy"],
    )


def _event(project: str, event_id: str, dedupe_key: str | None = None) -> ProjectEvent:
    return ProjectEvent(
        event_id=event_id,
        project=project,
        type="manual.nudge",
        source="manual",
        created_at="2026-04-17T23:00:00Z",
        dedupe_key=dedupe_key,
        payload={"reason": event_id},
    )


def test_append_and_list_events(monkeypatch, tmp_path):
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(tmp_path / "projects"))
    init_project(_config())

    append_event("demo", _event("demo", "evt_001"))

    events = list_events("demo")

    assert len(events) == 1
    assert events[0].event_id == "evt_001"
    assert events[0].status == "pending"


def test_claim_returns_oldest_pending_events_first(monkeypatch, tmp_path):
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(tmp_path / "projects"))
    init_project(_config())

    append_event("demo", _event("demo", "evt_001"))
    append_event("demo", _event("demo", "evt_002"))

    claimed = claim_pending_events("demo", limit=1)
    all_events = list_events("demo")

    assert [item.event_id for item in claimed] == ["evt_001"]
    assert all_events[0].status == "claimed"
    assert all_events[1].status == "pending"


def test_mark_event_status_updates_event(monkeypatch, tmp_path):
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(tmp_path / "projects"))
    init_project(_config())

    append_event("demo", _event("demo", "evt_001"))
    mark_event_status("demo", "evt_001", "completed")

    events = list_events("demo")

    assert events[0].status == "completed"


def test_duplicate_dedupe_key_is_coalesced(monkeypatch, tmp_path):
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(tmp_path / "projects"))
    init_project(_config())

    first = append_event("demo", _event("demo", "evt_001", dedupe_key="manual.demo"))
    second = append_event("demo", _event("demo", "evt_002", dedupe_key="manual.demo"))
    events = list_events("demo")

    assert first.event_id == "evt_001"
    assert second.event_id == "evt_001"
    assert len(events) == 1


def test_claiming_empty_queue_returns_empty_list(monkeypatch, tmp_path):
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(tmp_path / "projects"))
    init_project(_config())

    assert claim_pending_events("demo", limit=5) == []
