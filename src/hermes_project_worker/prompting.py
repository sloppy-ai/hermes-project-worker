from __future__ import annotations

import json
from textwrap import dedent

from .models import ProjectConfig, ProjectEvent, ProjectState


def _format_events(events: list[ProjectEvent]) -> str:
    if not events:
        return "- No claimed events."

    lines: list[str] = []
    for event in events:
        payload = json.dumps(event.payload, ensure_ascii=False, indent=2, sort_keys=True)
        lines.extend(
            [
                f"- Event ID: {event.event_id}",
                f"  Type: {event.type}",
                f"  Source: {event.source}",
                f"  Created at: {event.created_at}",
                f"  Payload: {payload}",
            ]
        )
    return "\n".join(lines)


def _format_validation_commands(config: ProjectConfig) -> str:
    return "- No validation commands configured in Stage 0. Add test/lint commands in later stages."


def build_worker_prompt(
    *,
    config: ProjectConfig,
    state: ProjectState,
    events: list[ProjectEvent],
    repo_path: str,
    worktree_path: str | None = None,
) -> str:
    effective_path = worktree_path or repo_path
    return dedent(
        f"""
        Mission
        {config.mission}

        Project summary
        - Name: {config.name}
        - Repo path: {config.repo_path}
        - Default branch: {config.default_branch}
        - PR strategy: {config.pr_strategy}

        Current state
        - Status: {state.status}
        - Current run ID: {state.current_run_id}
        - Current task: {state.current_task}
        - Blocked reason: {state.blocked_reason}
        - Last summary: {state.last_summary}

        Claimed events
        {_format_events(events)}

        Allowed actions
        {json.dumps(config.allowed_actions, ensure_ascii=False)}

        Approval-required and forbidden actions
        Approval required: {json.dumps(config.approval_required_actions, ensure_ascii=False)}
        Any action not explicitly allowed is forbidden.

        Repo/worktree path
        - Execute all work in: {effective_path}

        Validation commands
        {_format_validation_commands(config)}

        Output contract
        End your response with a machine-readable footer exactly in this shape:

        --- PROJECT_WORKER_RESULT ---
        status: completed
        task_class: small_bugfixes
        summary: Brief summary of what changed and what was verified.
        branch_name:
        pr_url:
        needs_approval: false
        approval_reason:
        followup_event:

        Termination rules
        - Do not omit the footer.
        - Do not perform approval-required actions without explicitly saying approval is needed.
        - Keep the summary concise and concrete.
        """
    ).strip()
