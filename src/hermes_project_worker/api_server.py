from __future__ import annotations

import json
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .approvals import approve_pending_approval, reject_pending_approval
from .manager import ProjectWorkerManager
from .models import ProjectEvent
from .queue import append_event, list_events
from .store import list_projects, list_runs, load_project_config, load_project_state



def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")



def _new_event_id() -> str:
    return f"evt_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}"



def _project_summary(name: str) -> dict:
    config = load_project_config(name)
    state = load_project_state(name)
    return {
        "name": config.name,
        "repo_path": config.repo_path,
        "mission": config.mission,
        "default_branch": config.default_branch,
        "status": state.status,
        "current_run_id": state.current_run_id,
        "blocked_reason": state.blocked_reason,
        "last_summary": state.last_summary,
        "pending_approval": state.pending_approval,
    }


class ProjectWorkerAPIServer(ThreadingHTTPServer):
    def __init__(self, server_address, manager: ProjectWorkerManager):
        super().__init__(server_address, ProjectWorkerAPIHandler)
        self.manager = manager


class ProjectWorkerAPIHandler(BaseHTTPRequestHandler):
    server: ProjectWorkerAPIServer

    def log_message(self, format, *args):  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            parts = [part for part in path.split("/") if part]

            if parts == ["health"]:
                self._send_json(200, {"status": "ok"})
                return
            if parts == ["projects"]:
                self._send_json(200, {"projects": list_projects()})
                return
            if len(parts) == 2 and parts[0] == "projects":
                self._send_json(200, _project_summary(parts[1]))
                return
            if len(parts) == 3 and parts[0] == "projects" and parts[2] == "approvals":
                state = load_project_state(parts[1])
                approvals = [state.pending_approval] if state.pending_approval else []
                self._send_json(200, {"approvals": approvals})
                return
            if len(parts) == 3 and parts[0] == "projects" and parts[2] == "events":
                load_project_config(parts[1])
                self._send_json(200, {"events": [event.to_dict() for event in list_events(parts[1])]})
                return
            if len(parts) == 3 and parts[0] == "projects" and parts[2] == "runs":
                load_project_config(parts[1])
                self._send_json(200, {"runs": list_runs(parts[1])})
                return

            self._send_json(404, {"error": f"unknown endpoint: {path}"})
        except FileNotFoundError as exc:
            self._send_json(404, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            parts = [part for part in path.split("/") if part]
            body = self._read_json_body()

            if len(parts) == 3 and parts[0] == "projects" and parts[2] == "enqueue":
                project_name = parts[1]
                load_project_config(project_name)
                event = ProjectEvent(
                    event_id=_new_event_id(),
                    project=project_name,
                    type=str(body.get("type")),
                    source="api",
                    created_at=_utc_now(),
                    payload=body.get("payload") or {},
                )
                append_event(project_name, event)
                self._send_json(200, {"event": event.to_dict()})
                return

            if len(parts) == 3 and parts[0] == "projects" and parts[2] == "run":
                result = self.server.manager.process_project(parts[1])
                self._send_json(200, {"result": result.to_dict() if result else None})
                return

            if len(parts) == 5 and parts[0] == "projects" and parts[2] == "approvals" and parts[4] == "approve":
                state = approve_pending_approval(parts[1], parts[3])
                self._send_json(200, {"state": state.to_dict()})
                return

            if len(parts) == 5 and parts[0] == "projects" and parts[2] == "approvals" and parts[4] == "reject":
                state = reject_pending_approval(parts[1], parts[3], reason=body.get("reason"))
                self._send_json(200, {"state": state.to_dict()})
                return

            self._send_json(404, {"error": f"unknown endpoint: {path}"})
        except FileNotFoundError as exc:
            self._send_json(404, {"error": str(exc)})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return {}
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)



def create_api_server(*, host: str = "127.0.0.1", port: int = 8765, manager: ProjectWorkerManager | None = None) -> ProjectWorkerAPIServer:
    return ProjectWorkerAPIServer((host, port), manager or ProjectWorkerManager())



def serve_api(*, host: str = "127.0.0.1", port: int = 8765, manager: ProjectWorkerManager | None = None) -> None:
    server = create_api_server(host=host, port=port, manager=manager)
    try:
        server.serve_forever()
    finally:
        server.server_close()
