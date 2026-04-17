from __future__ import annotations

import hashlib
import hmac
import os
from datetime import UTC, datetime

from ..models import ProjectConfig, ProjectEvent


class SignatureError(ValueError):
    pass



def validate_github_signature(config: ProjectConfig, body: bytes, signature_header: str | None) -> None:
    if not config.webhook_secret_env:
        return

    secret = os.getenv(config.webhook_secret_env)
    if not secret:
        raise SignatureError(f"missing webhook secret env: {config.webhook_secret_env}")
    if not signature_header or not signature_header.startswith("sha256="):
        raise SignatureError("missing github webhook signature")

    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    actual = signature_header.split("=", 1)[1]
    if not hmac.compare_digest(expected, actual):
        raise SignatureError("invalid github webhook signature")



def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")



def normalize_github_event(
    *,
    config: ProjectConfig,
    event_name: str,
    delivery_id: str,
    payload: dict,
    created_at: str | None = None,
) -> ProjectEvent:
    action = payload.get("action")
    event_type = f"github.{event_name}"
    if action and event_name != "push":
        event_type = f"{event_type}.{action}"

    repository = payload.get("repository") or {}
    issue = payload.get("issue") or {}
    pull_request = payload.get("pull_request") or {}
    head_commit = payload.get("head_commit") or {}

    title = issue.get("title") or pull_request.get("title") or head_commit.get("message")
    normalized_payload = {
        "delivery_id": delivery_id,
        "event": event_name,
        "action": action,
        "repository": repository.get("full_name"),
        "ref": payload.get("ref"),
        "issue_number": issue.get("number"),
        "pull_request_number": pull_request.get("number"),
        "head_commit_id": head_commit.get("id"),
        "title": title,
    }

    return ProjectEvent(
        event_id=f"evt_{delivery_id}",
        project=config.name,
        type=event_type,
        source="webhook",
        created_at=created_at or _utc_now(),
        dedupe_key=f"github.delivery:{delivery_id}",
        payload={k: v for k, v in normalized_payload.items() if v is not None},
    )
