from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .api_server import serve_api
from .approvals import approve_pending_approval, reject_pending_approval
from .hermes_runner import run_project_worker
from .launchd import (
    DEFAULT_API_HOST,
    DEFAULT_API_LABEL,
    DEFAULT_API_PORT,
    build_api_launch_agent_plist,
    build_launchctl_commands,
    default_package_src,
    default_python_executable,
    write_api_launch_agent_plist,
)
from .manager import ProjectWorkerManager
from .mcp_server import serve_mcp
from .models import ProjectConfig, ProjectEvent, WorkerConfig
from .queue import append_event, claim_pending_events, mark_event_status
from .store import init_project, list_projects, load_project_config, load_project_state, save_project_state
from .webhooks.server import serve_webhooks


_DEFAULT_ALLOWED_ACTIONS = [
    "issue_triage",
    "docs_updates",
    "dependency_updates",
    "test_repairs",
    "small_bugfixes",
    "draft_prs",
]

_DEFAULT_APPROVAL_ACTIONS = [
    "merge_default_branch",
    "deploy",
    "destructive_migration",
    "secret_changes",
    "infra_changes",
]


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    return f"{prefix}_{stamp}"


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hpw", description="Hermes Project Worker")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    project_parser = subparsers.add_parser("project", help="Inspect and run project state")
    project_subparsers = project_parser.add_subparsers(dest="project_command")

    project_init = project_subparsers.add_parser("init", help="Initialize a project")
    project_init.add_argument("name")
    project_init.add_argument("--repo", required=True)
    project_init.add_argument("--mission")
    project_init.add_argument("--default-branch", default="main")

    project_subparsers.add_parser("list", help="List known projects")
    project_show = project_subparsers.add_parser("show", help="Show one project")
    project_show.add_argument("name")

    project_enqueue = project_subparsers.add_parser("enqueue", help="Append one event to the project queue")
    project_enqueue.add_argument("name")
    project_enqueue.add_argument("--type", required=True)
    project_enqueue.add_argument("--payload", default="{}")

    project_run = project_subparsers.add_parser("run", help="Run one local worker cycle")
    project_run.add_argument("name")

    project_approvals = project_subparsers.add_parser("approvals", help="List pending approvals")
    project_approvals.add_argument("name")

    project_approve = project_subparsers.add_parser("approve", help="Approve a pending request")
    project_approve.add_argument("name")
    project_approve.add_argument("approval_id")

    project_reject = project_subparsers.add_parser("reject", help="Reject a pending request")
    project_reject.add_argument("name")
    project_reject.add_argument("approval_id")
    project_reject.add_argument("--reason")

    manager_parser = subparsers.add_parser("manager", help="Run manager operations")
    manager_subparsers = manager_parser.add_subparsers(dest="manager_command")
    manager_subparsers.add_parser("run", help="Process one manager cycle")

    api_parser = subparsers.add_parser("api", help="Serve the local project worker API")
    api_subparsers = api_parser.add_subparsers(dest="api_command")
    api_serve = api_subparsers.add_parser("serve", help="Start the local API server")
    api_serve.add_argument("--host", default=DEFAULT_API_HOST)
    api_serve.add_argument("--port", type=int, default=DEFAULT_API_PORT)

    api_write_launchd = api_subparsers.add_parser("write-launchd", help="Write a launchd plist for persistent API startup")
    api_write_launchd.add_argument("--path")
    api_write_launchd.add_argument("--label", default=DEFAULT_API_LABEL)
    api_write_launchd.add_argument("--python", default=default_python_executable())
    api_write_launchd.add_argument("--src", default=str(default_package_src()))
    api_write_launchd.add_argument("--host", default=DEFAULT_API_HOST)
    api_write_launchd.add_argument("--port", type=int, default=DEFAULT_API_PORT)
    api_write_launchd.add_argument("--log-dir")

    api_print_launchd = api_subparsers.add_parser("print-launchd", help="Print the launchd plist for persistent API startup")
    api_print_launchd.add_argument("--label", default=DEFAULT_API_LABEL)
    api_print_launchd.add_argument("--python", default=default_python_executable())
    api_print_launchd.add_argument("--src", default=str(default_package_src()))
    api_print_launchd.add_argument("--host", default=DEFAULT_API_HOST)
    api_print_launchd.add_argument("--port", type=int, default=DEFAULT_API_PORT)
    api_print_launchd.add_argument("--log-dir")

    webhook_parser = subparsers.add_parser("webhook", help="Serve webhook intake endpoints")
    webhook_subparsers = webhook_parser.add_subparsers(dest="webhook_command")
    webhook_serve = webhook_subparsers.add_parser("serve", help="Start the local webhook server")
    webhook_serve.add_argument("--host", default="127.0.0.1")
    webhook_serve.add_argument("--port", type=int, default=8770)

    mcp_parser = subparsers.add_parser("mcp", help="Serve the Project Worker MCP interface")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command")
    mcp_subparsers.add_parser("serve", help="Start the MCP stdio server")

    return parser


def _cmd_project_init(name: str, repo: str, mission: str | None, default_branch: str) -> int:
    config = ProjectConfig(
        name=name,
        repo_path=repo,
        mission=mission or f"Keep the {name} repo healthy with bounded autonomy.",
        default_branch=default_branch,
        worker=WorkerConfig(use_worktree=False),
        allowed_actions=list(_DEFAULT_ALLOWED_ACTIONS),
        approval_required_actions=list(_DEFAULT_APPROVAL_ACTIONS),
    )
    project_dir = init_project(config)
    print(str(project_dir))
    return 0


def _cmd_project_list() -> int:
    projects = list_projects()
    if not projects:
        print("No projects found.")
        return 0

    for project in projects:
        print(project)
    return 0


def _cmd_project_show(name: str) -> int:
    config = load_project_config(name)
    state = load_project_state(name)
    summary = {
        "name": config.name,
        "repo_path": config.repo_path,
        "mission": config.mission,
        "status": state.status,
        "current_run_id": state.current_run_id,
        "blocked_reason": state.blocked_reason,
    }
    _print_json(summary)
    return 0


def _cmd_project_enqueue(name: str, event_type: str, payload_text: str) -> int:
    load_project_config(name)
    payload = json.loads(payload_text)
    if not isinstance(payload, dict):
        raise ValueError("event payload must be a JSON object")

    event = ProjectEvent(
        event_id=_new_id("evt"),
        project=name,
        type=event_type,
        source="cli",
        created_at=_utc_now(),
        payload=payload,
    )
    append_event(name, event)
    _print_json(event.to_dict())
    return 0


def _cmd_project_run(name: str) -> int:
    config = load_project_config(name)
    state = load_project_state(name)
    events = claim_pending_events(name, limit=1)
    if not events:
        print("No pending events.")
        return 0

    run_id = _new_id("run")
    started_at = _utc_now()
    state.status = "running"
    state.current_run_id = run_id
    state.current_task = events[0].type
    state.last_event_at = events[-1].created_at
    state.last_run_started_at = started_at
    state.blocked_reason = None
    save_project_state(state)

    result = run_project_worker(config=config, state=state, events=events, run_id=run_id)

    finished_at = _utc_now()
    for event in events:
        mark_event_status(name, event.event_id, "completed" if result.success else "failed")

    state.current_run_id = None
    state.current_task = None
    state.last_run_finished_at = finished_at
    state.last_summary = result.summary
    if result.branch_name:
        state.open_branch = result.branch_name
    if result.pr_url:
        state.open_pr = result.pr_url

    if result.needs_approval:
        state.status = "blocked"
        state.blocked_reason = result.approval_reason or result.summary
    elif result.success:
        state.status = "idle"
        state.blocked_reason = None
    else:
        state.status = "failed"
        state.blocked_reason = result.summary

    save_project_state(state)
    _print_json(result.to_dict())
    return 0 if result.success else 1


def _cmd_project_approvals(name: str) -> int:
    state = load_project_state(name)
    approvals = [state.pending_approval] if state.pending_approval else []
    _print_json({"approvals": approvals})
    return 0


def _cmd_project_approve(name: str, approval_id: str) -> int:
    state = approve_pending_approval(name, approval_id)
    _print_json({"state": state.to_dict()})
    return 0


def _cmd_project_reject(name: str, approval_id: str, reason: str | None) -> int:
    state = reject_pending_approval(name, approval_id, reason=reason)
    _print_json({"state": state.to_dict()})
    return 0


def _cmd_manager_run() -> int:
    processed = ProjectWorkerManager().run_once()
    _print_json({"processed": processed})
    return 0


def _cmd_api_serve(host: str, port: int) -> int:
    serve_api(host=host, port=port)
    return 0


def _cmd_api_print_launchd(
    *,
    label: str,
    python_executable: str,
    package_src: str,
    host: str,
    port: int,
    log_dir: str | None,
) -> int:
    print(
        build_api_launch_agent_plist(
            label=label,
            python_executable=python_executable,
            package_src=package_src,
            host=host,
            port=port,
            log_dir=log_dir,
        )
    )
    return 0


def _cmd_api_write_launchd(
    *,
    path: str | None,
    label: str,
    python_executable: str,
    package_src: str,
    host: str,
    port: int,
    log_dir: str | None,
) -> int:
    plist_path = write_api_launch_agent_plist(
        path=Path(path) if path is not None else None,
        label=label,
        python_executable=python_executable,
        package_src=package_src,
        host=host,
        port=port,
        log_dir=log_dir,
    )
    _print_json({"launch_agent_path": str(plist_path), **build_launchctl_commands(plist_path, label=label)})
    return 0


def _cmd_webhook_serve(host: str, port: int) -> int:
    serve_webhooks(host=host, port=port)
    return 0


def _cmd_mcp_serve() -> int:
    serve_mcp()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

    if args.command is None:
        parser.print_help()
        return 0

    try:
        if args.command == "project":
            if args.project_command == "init":
                return _cmd_project_init(args.name, args.repo, args.mission, args.default_branch)
            if args.project_command == "list":
                return _cmd_project_list()
            if args.project_command == "show":
                return _cmd_project_show(args.name)
            if args.project_command == "enqueue":
                return _cmd_project_enqueue(args.name, args.type, args.payload)
            if args.project_command == "run":
                return _cmd_project_run(args.name)
            if args.project_command == "approvals":
                return _cmd_project_approvals(args.name)
            if args.project_command == "approve":
                return _cmd_project_approve(args.name, args.approval_id)
            if args.project_command == "reject":
                return _cmd_project_reject(args.name, args.approval_id, args.reason)
            parser.parse_args(["project", "--help"])
            return 0
        if args.command == "manager":
            if args.manager_command == "run":
                return _cmd_manager_run()
            parser.parse_args(["manager", "--help"])
            return 0
        if args.command == "api":
            if args.api_command == "serve":
                return _cmd_api_serve(args.host, args.port)
            if args.api_command == "write-launchd":
                return _cmd_api_write_launchd(
                    path=args.path,
                    label=args.label,
                    python_executable=args.python,
                    package_src=args.src,
                    host=args.host,
                    port=args.port,
                    log_dir=args.log_dir,
                )
            if args.api_command == "print-launchd":
                return _cmd_api_print_launchd(
                    label=args.label,
                    python_executable=args.python,
                    package_src=args.src,
                    host=args.host,
                    port=args.port,
                    log_dir=args.log_dir,
                )
            parser.parse_args(["api", "--help"])
            return 0
        if args.command == "webhook":
            if args.webhook_command == "serve":
                return _cmd_webhook_serve(args.host, args.port)
            parser.parse_args(["webhook", "--help"])
            return 0
        if args.command == "mcp":
            if args.mcp_command == "serve":
                return _cmd_mcp_serve()
            parser.parse_args(["mcp", "--help"])
            return 0
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    parser.print_help()
    return 0


def run() -> None:
    raise SystemExit(main())
