from __future__ import annotations

from .client import ProjectWorkerPluginClient
from .formatters import format_approvals, format_project_list, format_project_summary, format_result



def build_commands(client: ProjectWorkerPluginClient) -> dict[str, callable]:
    def cmd_list(_args: list[str]) -> str:
        return format_project_list(client.list_projects())

    def cmd_show(args: list[str]) -> str:
        project = args[0]
        return format_project_summary(client.show_project(project))

    def cmd_nudge(args: list[str]) -> str:
        project = args[0]
        reason = args[1] if len(args) > 1 else "manual nudge"
        return format_result(client.enqueue_project(project, "manual.nudge", {"reason": reason}))

    def cmd_run(args: list[str]) -> str:
        return format_result(client.run_project(args[0]))

    def cmd_approvals(args: list[str]) -> str:
        return format_approvals(client.list_approvals(args[0]))

    def cmd_approve(args: list[str]) -> str:
        return format_result(client.approve(args[0], args[1]))

    def cmd_reject(args: list[str]) -> str:
        reason = args[2] if len(args) > 2 else None
        return format_result(client.reject(args[0], args[1], reason=reason))

    return {
        "pw list": cmd_list,
        "pw show": cmd_show,
        "pw nudge": cmd_nudge,
        "pw run": cmd_run,
        "pw approvals": cmd_approvals,
        "pw approve": cmd_approve,
        "pw reject": cmd_reject,
    }
