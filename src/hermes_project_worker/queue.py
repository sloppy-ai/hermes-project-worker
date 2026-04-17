from __future__ import annotations

import json
from typing import Iterable

from .models import ProjectEvent
from .store import _atomic_write_text, get_queue_path


_ACTIVE_STATUSES = {"pending", "claimed"}


def _load_all_events(project_name: str) -> list[ProjectEvent]:
    path = get_queue_path(project_name)
    if not path.exists():
        return []

    events: list[ProjectEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        events.append(ProjectEvent.from_dict(json.loads(line)))
    return events


def _save_all_events(project_name: str, events: Iterable[ProjectEvent]) -> None:
    path = get_queue_path(project_name)
    lines = [json.dumps(event.to_dict(), ensure_ascii=False) for event in events]
    content = "\n".join(lines)
    if content:
        content += "\n"
    _atomic_write_text(path, content)


def append_event(project_name: str, event: ProjectEvent) -> ProjectEvent:
    events = _load_all_events(project_name)
    if event.dedupe_key:
        for existing in events:
            if existing.dedupe_key == event.dedupe_key and existing.status in _ACTIVE_STATUSES:
                return existing

    events.append(event)
    _save_all_events(project_name, events)
    return event


def list_events(project_name: str, status: str | None = None) -> list[ProjectEvent]:
    events = _load_all_events(project_name)
    if status is None:
        return events
    return [event for event in events if event.status == status]


def claim_pending_events(project_name: str, limit: int = 1) -> list[ProjectEvent]:
    events = _load_all_events(project_name)
    claimed: list[ProjectEvent] = []

    for event in events:
        if event.status != "pending":
            continue
        event.status = "claimed"
        claimed.append(event)
        if len(claimed) >= limit:
            break

    if claimed:
        _save_all_events(project_name, events)

    return claimed


def mark_event_status(project_name: str, event_id: str, status: str) -> ProjectEvent:
    events = _load_all_events(project_name)
    for event in events:
        if event.event_id == event_id:
            event.status = status
            _save_all_events(project_name, events)
            return event
    raise FileNotFoundError(f"missing event: {event_id}")
