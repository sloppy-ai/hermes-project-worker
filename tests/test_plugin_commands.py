from hermes_plugin.project_worker import register
from hermes_plugin.project_worker.commands import build_commands


class FakeClient:
    def list_projects(self):
        return {"projects": ["demo", "beta"]}

    def show_project(self, name):
        return {
            "name": name,
            "status": "awaiting_approval",
            "current_run_id": "run_001",
            "blocked_reason": "Deploy requires approval.",
            "pending_approval": {"approval_id": "appr_001"},
        }

    def enqueue_project(self, name, event_type, payload):
        return {"event": {"project": name, "type": event_type, "payload": payload}}

    def run_project(self, name):
        return {"result": {"status": "completed", "summary": "Applied fix."}}

    def list_approvals(self, name):
        return {"approvals": [{"approval_id": "appr_001", "project": name}]}

    def approve(self, name, approval_id):
        return {"state": {"status": "idle", "last_approval_id": approval_id}}

    def reject(self, name, approval_id, *, reason=None):
        return {"state": {"status": "blocked", "blocked_reason": reason or "rejected"}}


class FakeContext:
    def __init__(self):
        self.tools = {}
        self.commands = {}

    def register_tool(self, name, func, description=None):
        self.tools[name] = {"func": func, "description": description}

    def register_command(self, name, func, description=None):
        self.commands[name] = {"func": func, "description": description}


def test_build_commands_render_operator_friendly_output():
    commands = build_commands(FakeClient())

    list_output = commands["pw list"]([])
    show_output = commands["pw show"](["demo"])
    approvals_output = commands["pw approvals"](["demo"])

    assert "demo" in list_output
    assert "Project: demo" in show_output
    assert "Pending approval: appr_001" in show_output
    assert "appr_001" in approvals_output


def test_register_wires_tools_and_commands():
    ctx = FakeContext()
    client = FakeClient()

    register(ctx, client=client)

    assert set(ctx.tools) >= {
        "project_worker_list",
        "project_worker_show",
        "project_worker_enqueue",
        "project_worker_run",
        "project_worker_approvals",
        "project_worker_approve",
        "project_worker_reject",
    }
    assert set(ctx.commands) >= {
        "pw list",
        "pw show",
        "pw nudge",
        "pw run",
        "pw approvals",
        "pw approve",
        "pw reject",
    }

    show_output = ctx.commands["pw show"]["func"](["demo"])
    assert "awaiting_approval" in show_output
