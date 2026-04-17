from __future__ import annotations

import yaml

from .models import RunResult


FOOTER_MARKER = "--- PROJECT_WORKER_RESULT ---"


_TERMINAL_SUCCESS_STATUSES = {"completed", "success"}


def parse_worker_result(output: str, *, exit_code: int = 0) -> RunResult:
    if FOOTER_MARKER not in output:
        raise ValueError("missing project worker footer")

    _, footer = output.split(FOOTER_MARKER, 1)
    footer = footer.strip()
    if not footer:
        raise ValueError("malformed project worker footer: empty footer")

    try:
        data = yaml.safe_load(footer)
    except yaml.YAMLError as exc:
        raise ValueError("malformed project worker footer") from exc

    if not isinstance(data, dict) or "status" not in data or "summary" not in data:
        raise ValueError("malformed project worker footer")

    status = str(data["status"])
    needs_approval = bool(data.get("needs_approval", False))
    success = (status in _TERMINAL_SUCCESS_STATUSES) and not needs_approval and exit_code == 0

    return RunResult(
        success=success,
        exit_code=exit_code,
        status=status,
        summary=str(data["summary"]),
        task_class=data.get("task_class"),
        branch_name=data.get("branch_name"),
        pr_url=data.get("pr_url"),
        needs_approval=needs_approval,
        approval_reason=data.get("approval_reason"),
        followup_event=data.get("followup_event"),
    )
