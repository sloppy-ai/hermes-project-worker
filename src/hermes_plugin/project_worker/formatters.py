from __future__ import annotations



def format_project_summary(project: dict) -> str:
    lines = [
        "[Project Worker]",
        f"Project: {project.get('name')}",
        f"Status: {project.get('status')}",
    ]
    if project.get("current_run_id"):
        lines.append(f"Current run: {project['current_run_id']}")
    if project.get("pending_approval"):
        approval = project["pending_approval"]
        lines.append(f"Pending approval: {approval.get('approval_id')}")
    if project.get("blocked_reason"):
        lines.append(f"Reason: {project.get('blocked_reason')}")
    return "\n".join(lines)



def format_project_list(payload: dict) -> str:
    projects = payload.get("projects") or []
    if not projects:
        return "[Project Worker]\nNo projects found."
    return "[Project Worker]\n" + "\n".join(f"- {name}" for name in projects)



def format_approvals(payload: dict) -> str:
    approvals = payload.get("approvals") or []
    if not approvals:
        return "[Project Worker]\nNo pending approvals."
    lines = ["[Project Worker]"]
    for approval in approvals:
        lines.append(f"- {approval.get('approval_id')} ({approval.get('project')})")
    return "\n".join(lines)



def format_result(payload: dict) -> str:
    result = payload.get("result") or payload.get("state") or payload
    return "[Project Worker]\n" + "\n".join(f"{key}: {value}" for key, value in result.items())
