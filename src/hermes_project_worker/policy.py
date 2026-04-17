from __future__ import annotations

from .models import ProjectConfig


ACTION_ALLOWED = "allowed"
ACTION_APPROVAL_REQUIRED = "approval_required"
ACTION_FORBIDDEN = "forbidden"


def classify_task_action(task_class: str | None, project_config: ProjectConfig) -> str:
    if not task_class:
        return ACTION_FORBIDDEN
    if task_class in project_config.allowed_actions:
        return ACTION_ALLOWED
    if task_class in project_config.approval_required_actions:
        return ACTION_APPROVAL_REQUIRED
    return ACTION_FORBIDDEN


def validate_task_action(task_class: str | None, project_config: ProjectConfig) -> bool:
    return classify_task_action(task_class, project_config) == ACTION_ALLOWED
