from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProjectWorkerApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urlopen(request) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8")
            raise RuntimeError(body or str(exc)) from exc
        except URLError as exc:
            raise RuntimeError(str(exc)) from exc

        return json.loads(body) if body else {}

    def health(self) -> dict:
        return self._request("GET", "/health")

    def list_projects(self) -> dict:
        return self._request("GET", "/projects")

    def get_project(self, name: str) -> dict:
        return self._request("GET", f"/projects/{name}")

    def enqueue_event(self, name: str, event_type: str, payload: dict | None = None) -> dict:
        return self._request("POST", f"/projects/{name}/enqueue", {"type": event_type, "payload": payload or {}})

    def run_project(self, name: str) -> dict:
        return self._request("POST", f"/projects/{name}/run", {})

    def list_approvals(self, name: str) -> dict:
        return self._request("GET", f"/projects/{name}/approvals")

    def list_events(self, name: str) -> dict:
        return self._request("GET", f"/projects/{name}/events")

    def list_runs(self, name: str) -> dict:
        return self._request("GET", f"/projects/{name}/runs")

    def approve(self, name: str, approval_id: str) -> dict:
        return self._request("POST", f"/projects/{name}/approvals/{approval_id}/approve", {})

    def reject(self, name: str, approval_id: str, *, reason: str | None = None) -> dict:
        payload = {"reason": reason} if reason is not None else {}
        return self._request("POST", f"/projects/{name}/approvals/{approval_id}/reject", payload)
