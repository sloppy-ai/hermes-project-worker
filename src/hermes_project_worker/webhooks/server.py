from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from ..queue import append_event, list_events
from ..store import list_projects, load_project_config
from .github import SignatureError, normalize_github_event, validate_github_signature



def _resolve_project(provider: str, route: str):
    for project_name in list_projects():
        config = load_project_config(project_name)
        if config.webhook_provider == provider and config.webhook_route == route:
            return config
    raise FileNotFoundError(f"missing webhook route: {provider}/{route}")


class ProjectWorkerWebhookServer(ThreadingHTTPServer):
    pass


class ProjectWorkerWebhookHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            parts = [part for part in path.split("/") if part]
            if len(parts) != 3 or parts[0] != "webhooks" or parts[1] != "github":
                self._send_json(404, {"error": f"unknown endpoint: {path}"})
                return

            route = parts[2]
            config = _resolve_project("github", route)
            body = self._read_body()
            payload = self._parse_json(body)
            validate_github_signature(config, body, self.headers.get("X-Hub-Signature-256"))

            delivery_id = self.headers.get("X-GitHub-Delivery")
            event_name = self.headers.get("X-GitHub-Event")
            if not delivery_id:
                raise ValueError("missing X-GitHub-Delivery header")
            if not event_name:
                raise ValueError("missing X-GitHub-Event header")

            event = normalize_github_event(
                config=config,
                event_name=event_name,
                delivery_id=delivery_id,
                payload=payload,
            )

            existing = next((item for item in list_events(config.name) if item.dedupe_key == event.dedupe_key), None)
            if existing is None:
                existing = append_event(config.name, event)

            self._send_json(202, {"status": "accepted", "event": existing.to_dict()})
        except FileNotFoundError as exc:
            self._send_json(404, {"error": str(exc)})
        except SignatureError as exc:
            self._send_json(401, {"error": str(exc)})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or 0)
        return self.rfile.read(length) if length > 0 else b""

    def _parse_json(self, body: bytes) -> dict:
        if not body:
            return {}
        payload = json.loads(body.decode("utf-8"))
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



def create_webhook_server(*, host: str = "127.0.0.1", port: int = 8770) -> ProjectWorkerWebhookServer:
    return ProjectWorkerWebhookServer((host, port), ProjectWorkerWebhookHandler)



def serve_webhooks(*, host: str = "127.0.0.1", port: int = 8770) -> None:
    server = create_webhook_server(host=host, port=port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
