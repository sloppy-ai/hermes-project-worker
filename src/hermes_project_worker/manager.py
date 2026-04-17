from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable

from .approvals import create_approval_request, set_pending_approval
from .hermes_runner import run_project_worker
from .policy import ACTION_ALLOWED, ACTION_APPROVAL_REQUIRED, classify_task_action
from .queue import append_event, claim_pending_events, list_events, mark_event_status
from .store import list_projects, load_project_config, load_project_state, save_project_state


Runner = Callable[..., object]
NowProvider = Callable[[], str]



def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")



def _new_run_id() -> str:
    return f"run_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}"



def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class ProjectWorkerManager:
    def __init__(
        self,
        *,
        runner: Runner = run_project_worker,
        now_provider: NowProvider = _utc_now,
    ) -> None:
        self.runner = runner
        self.now_provider = now_provider
        self._locks: set[str] = set()

    def lock_project(self, project_name: str) -> None:
        self._locks.add(project_name)

    def unlock_project(self, project_name: str) -> None:
        self._locks.discard(project_name)

    def enqueue_due_heartbeats(self) -> int:
        created = 0
        for project_name in list_projects():
            config = load_project_config(project_name)
            state = load_project_state(project_name)
            if not self._heartbeat_due(config.heartbeat_enabled, config.heartbeat_interval_seconds, state.last_event_at):
                continue

            now = self.now_provider()
            event = self._make_heartbeat_event(project_name, now)
            appended = append_event(project_name, event)
            if appended.event_id != event.event_id:
                continue
            state.last_event_at = now
            save_project_state(state)
            created += 1
        return created

    def run_once(self) -> int:
        self.enqueue_due_heartbeats()
        processed = 0
        for project_name in list_projects():
            if self.process_project(project_name) is not None:
                processed += 1
        return processed

    def process_project(self, project_name: str):
        if project_name in self._locks:
            return None

        config = load_project_config(project_name)
        state = load_project_state(project_name)
        if state.status == "awaiting_approval":
            return None

        self._locks.add(project_name)
        try:
            events = claim_pending_events(project_name, limit=1)
            if not events:
                return None

            run_id = _new_run_id()
            started_at = self.now_provider()
            state.status = "running"
            state.current_run_id = run_id
            state.current_task = events[0].type
            state.last_event_at = events[-1].created_at
            state.last_run_started_at = started_at
            state.blocked_reason = None
            save_project_state(state)

            result = self.runner(config=config, state=state, events=events, run_id=run_id)

            self._finalize_project_run(config.name, state, events, result)
            return result
        finally:
            self._locks.discard(project_name)

    def _finalize_project_run(self, project_name: str, state, events, result) -> None:
        finished_at = self.now_provider()
        permission = classify_task_action(result.task_class, load_project_config(project_name))

        if result.needs_approval or permission == ACTION_APPROVAL_REQUIRED:
            approval = create_approval_request(
                project=project_name,
                task_class=result.task_class or "unknown",
                reason=result.approval_reason or result.summary,
            )
            state = set_pending_approval(state, approval)
            event_status = "completed"
        elif permission == ACTION_ALLOWED and result.success:
            state.status = "idle"
            state.blocked_reason = None
            event_status = "completed"
        elif permission not in {ACTION_ALLOWED, ACTION_APPROVAL_REQUIRED} and result.task_class:
            state.status = "blocked"
            state.blocked_reason = f"forbidden task class: {result.task_class}"
            event_status = "failed"
        else:
            state.status = "failed"
            state.blocked_reason = result.summary
            event_status = "failed"

        for event in events:
            mark_event_status(project_name, event.event_id, event_status)

        state.current_run_id = None
        state.current_task = None
        state.last_run_finished_at = finished_at
        state.last_summary = result.summary
        if result.branch_name:
            state.open_branch = result.branch_name
        if result.pr_url:
            state.open_pr = result.pr_url
        save_project_state(state)

    def _heartbeat_due(self, enabled: bool, interval_seconds: int | None, last_event_at: str | None) -> bool:
        if not enabled or not interval_seconds:
            return False
        if last_event_at is None:
            return True
        now = _parse_timestamp(self.now_provider())
        last = _parse_timestamp(last_event_at)
        if now is None or last is None:
            return True
        return (now - last).total_seconds() >= interval_seconds

    def _make_heartbeat_event(self, project_name: str, created_at: str):
        from .models import ProjectEvent

        return ProjectEvent(
            event_id=f"evt_heartbeat_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}",
            project=project_name,
            type="heartbeat",
            source="manager",
            created_at=created_at,
            dedupe_key=f"heartbeat:{project_name}",
            payload={"reason": "scheduled heartbeat"},
        )
