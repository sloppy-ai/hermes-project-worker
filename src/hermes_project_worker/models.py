from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(eq=True)
class WorkerConfig:
    command: str = "hermes"
    profile: str = "default"
    provider: str | None = None
    model: str | None = None
    use_worktree: bool = True
    timeout_minutes: int = 45

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "WorkerConfig":
        return cls(**(data or {}))


@dataclass(eq=True)
class ApprovalRequest:
    approval_id: str
    project: str
    task_class: str
    reason: str
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalRequest":
        return cls(**data)


@dataclass(eq=True)
class ProjectConfig:
    name: str
    repo_path: str
    mission: str
    default_branch: str
    worker: WorkerConfig
    allowed_actions: list[str]
    approval_required_actions: list[str]
    worktree_parent: str | None = None
    branch_naming: str = "hermes/{task_slug}"
    pr_strategy: str = "draft"
    heartbeat_enabled: bool = False
    heartbeat_interval_seconds: int | None = None
    webhook_provider: str | None = None
    webhook_route: str | None = None
    webhook_secret_env: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["worker"] = self.worker.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectConfig":
        payload = dict(data)
        payload["worker"] = WorkerConfig.from_dict(payload.get("worker"))
        return cls(**payload)


@dataclass(eq=True)
class ProjectState:
    project: str
    status: str = "idle"
    current_run_id: str | None = None
    current_task: str | None = None
    open_branch: str | None = None
    open_pr: str | None = None
    blocked_reason: str | None = None
    last_event_at: str | None = None
    last_run_started_at: str | None = None
    last_run_finished_at: str | None = None
    last_summary: str | None = None
    last_approval_id: str | None = None
    retry_count: int = 0
    pending_approval: dict[str, Any] | None = None
    policy_version: int = 1

    @classmethod
    def default_for_project(cls, project: str) -> "ProjectState":
        return cls(project=project)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectState":
        return cls(**data)


@dataclass(eq=True)
class ProjectEvent:
    event_id: str
    project: str
    type: str
    source: str
    created_at: str
    dedupe_key: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectEvent":
        return cls(**data)


@dataclass(eq=True)
class RunResult:
    success: bool
    exit_code: int
    status: str
    summary: str
    task_class: str | None = None
    branch_name: str | None = None
    pr_url: str | None = None
    needs_approval: bool = False
    approval_reason: str | None = None
    followup_event: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunResult":
        return cls(**data)
