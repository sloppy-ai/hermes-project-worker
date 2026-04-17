from hermes_project_worker.mcp_server import create_mcp_server, serve_mcp


class FakeClient:
    def __init__(self):
        self.calls = []

    def list_projects(self):
        self.calls.append(("list_projects",))
        return {"projects": ["demo", "beta"]}

    def show_project(self, name):
        self.calls.append(("show_project", name))
        return {"name": name, "status": "idle"}

    def enqueue_project(self, name, event_type, payload):
        self.calls.append(("enqueue_project", name, event_type, payload))
        return {"event": {"project": name, "type": event_type, "payload": payload}}

    def run_project(self, name):
        self.calls.append(("run_project", name))
        return {"result": {"project": name, "summary": "Applied fix.", "status": "completed"}}

    def list_approvals(self, name):
        self.calls.append(("list_approvals", name))
        return {"approvals": [{"approval_id": "appr_001", "project": name}]}

    def approve(self, name, approval_id):
        self.calls.append(("approve", name, approval_id))
        return {"state": {"project": name, "status": "idle", "last_approval_id": approval_id}}

    def reject(self, name, approval_id, *, reason=None):
        self.calls.append(("reject", name, approval_id, reason))
        return {"state": {"project": name, "status": "blocked", "blocked_reason": reason}}

    def list_events(self, name):
        self.calls.append(("list_events", name))
        return {"events": [{"event_id": "evt_001", "project": name, "type": "manual.nudge"}]}

    def list_runs(self, name):
        self.calls.append(("list_runs", name))
        return {"runs": [{"run_id": "run_001", "project": name, "summary": "Applied fix."}]}


class FakeFastMCP:
    def __init__(self, name, **kwargs):
        self.name = name
        self.kwargs = kwargs
        self.tools = {}
        self.run_calls = []

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator

    def run(self, transport="stdio"):
        self.run_calls.append(transport)


def test_create_mcp_server_registers_expected_tools_and_delegates_to_client():
    client = FakeClient()
    fake_server = FakeFastMCP("ignored")

    server = create_mcp_server(client=client, fastmcp_factory=lambda name, **kwargs: fake_server)

    assert server is fake_server
    assert fake_server.name == "ignored"
    assert set(fake_server.tools) == {
        "list_projects",
        "show_project",
        "enqueue_project",
        "run_project",
        "list_approvals",
        "approve",
        "reject",
        "list_events",
        "list_runs",
    }

    assert fake_server.tools["list_projects"]() == {"projects": ["demo", "beta"]}
    assert fake_server.tools["show_project"]("demo")["name"] == "demo"
    assert fake_server.tools["enqueue_project"]("demo", "manual.nudge", {"reason": "work now"})["event"]["type"] == "manual.nudge"
    assert fake_server.tools["run_project"]("demo")["result"]["status"] == "completed"
    assert fake_server.tools["list_approvals"]("demo")["approvals"][0]["approval_id"] == "appr_001"
    assert fake_server.tools["approve"]("demo", "appr_001")["state"]["last_approval_id"] == "appr_001"
    assert fake_server.tools["reject"]("demo", "appr_001", reason="No deploy")["state"]["blocked_reason"] == "No deploy"
    assert fake_server.tools["list_events"]("demo")["events"][0]["event_id"] == "evt_001"
    assert fake_server.tools["list_runs"]("demo")["runs"][0]["run_id"] == "run_001"

    assert client.calls == [
        ("list_projects",),
        ("show_project", "demo"),
        ("enqueue_project", "demo", "manual.nudge", {"reason": "work now"}),
        ("run_project", "demo"),
        ("list_approvals", "demo"),
        ("approve", "demo", "appr_001"),
        ("reject", "demo", "appr_001", "No deploy"),
        ("list_events", "demo"),
        ("list_runs", "demo"),
    ]


def test_serve_mcp_runs_stdio_transport():
    fake_server = FakeFastMCP("ignored")

    serve_mcp(client=FakeClient(), fastmcp_factory=lambda name, **kwargs: fake_server)

    assert fake_server.run_calls == ["stdio"]
