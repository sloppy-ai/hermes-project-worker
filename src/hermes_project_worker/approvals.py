from __future__ import annotations

from datetime import UTC, datetime

from .models import ApprovalRequest, ProjectState
from .store import load_project_state, save_project_state



def _new_approval_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    return f"appr_{stamp}"



def create_approval_request(*, project: str, task_class: str, reason: str) -> ApprovalRequest:
    return ApprovalRequest(
        approval_id=_new_approval_id(),
        project=project,
        task_class=task_class,
        reason=reason,
        status="pending",
    )



def set_pending_approval(state: ProjectState, approval: ApprovalRequest) -> ProjectState:
    state.status = "awaiting_approval"
    state.pending_approval = approval.to_dict()
    state.last_approval_id = approval.approval_id
    state.blocked_reason = approval.reason
    return state



def _require_pending_approval(project_name: str, approval_id: str) -> ProjectState:
    state = load_project_state(project_name)
    pending = state.pending_approval or {}
    if pending.get("approval_id") != approval_id:
        raise FileNotFoundError(f"missing approval request: {approval_id}")
    return state



def approve_pending_approval(project_name: str, approval_id: str) -> ProjectState:
    state = _require_pending_approval(project_name, approval_id)
    state.status = "idle"
    state.pending_approval = None
    state.last_approval_id = approval_id
    state.blocked_reason = None
    save_project_state(state)
    return state



def reject_pending_approval(project_name: str, approval_id: str, *, reason: str | None = None) -> ProjectState:
    state = _require_pending_approval(project_name, approval_id)
    pending_reason = (state.pending_approval or {}).get("reason")
    state.status = "blocked"
    state.pending_approval = None
    state.last_approval_id = approval_id
    state.blocked_reason = reason or pending_reason
    save_project_state(state)
    return state
