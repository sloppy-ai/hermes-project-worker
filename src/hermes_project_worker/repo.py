from __future__ import annotations

import re
from pathlib import Path

from .models import ProjectConfig


_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def resolve_repo_path(config: ProjectConfig) -> Path:
    return Path(config.repo_path).expanduser().resolve()


def _slugify_task(task_slug: str) -> str:
    slug = _SLUG_PATTERN.sub("-", task_slug.strip().lower()).strip("-")
    return slug or "task"


def derive_branch_name(config: ProjectConfig, task_slug: str) -> str:
    return config.branch_naming.format(task_slug=_slugify_task(task_slug))


def get_execution_path(config: ProjectConfig, branch_name: str) -> Path:
    repo_path = resolve_repo_path(config)
    if not config.worker.use_worktree:
        return repo_path

    if config.worktree_parent:
        parent = Path(config.worktree_parent).expanduser()
    else:
        parent = repo_path.parent / ".worktrees" / config.name

    return parent / branch_name.replace("/", "__")
