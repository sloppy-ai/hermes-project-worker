from __future__ import annotations

import os

from .api_client import ProjectWorkerApiClient


_DEFAULT_BASE_URL = "http://127.0.0.1:8765"


class ProjectWorkerOperatorClient:
    def __init__(self, *, base_url: str | None = None, api_client: ProjectWorkerApiClient | None = None) -> None:
        self.api_client = api_client or ProjectWorkerApiClient(base_url or os.getenv("HPW_API_BASE_URL", _DEFAULT_BASE_URL))

    def health(self) -> dict:
        return self.api_client.health()

    def list_projects(self) -> dict:
        return self.api_client.list_projects()

    def show_project(self, name: str) -> dict:
        return self.api_client.get_project(name)

    def enqueue_project(self, name: str, event_type: str, payload: dict | None = None) -> dict:
        return self.api_client.enqueue_event(name, event_type, payload or {})

    def run_project(self, name: str) -> dict:
        return self.api_client.run_project(name)

    def list_approvals(self, name: str) -> dict:
        return self.api_client.list_approvals(name)

    def approve(self, name: str, approval_id: str) -> dict:
        return self.api_client.approve(name, approval_id)

    def reject(self, name: str, approval_id: str, *, reason: str | None = None) -> dict:
        return self.api_client.reject(name, approval_id, reason=reason)

    def list_events(self, name: str) -> dict:
        return self.api_client.list_events(name)

    def list_runs(self, name: str) -> dict:
        return self.api_client.list_runs(name)
