from hermes_plugin.project_worker.client import ProjectWorkerPluginClient


class FakeApiClient:
    def __init__(self):
        self.calls = []

    def list_projects(self):
        self.calls.append(("list_projects",))
        return {"projects": ["demo"]}

    def get_project(self, name):
        self.calls.append(("get_project", name))
        return {"name": name, "status": "idle"}

    def enqueue_event(self, name, event_type, payload):
        self.calls.append(("enqueue_event", name, event_type, payload))
        return {"event": {"project": name, "type": event_type, "payload": payload}}

    def run_project(self, name):
        self.calls.append(("run_project", name))
        return {"result": {"summary": "done", "status": "completed"}}

    def list_approvals(self, name):
        self.calls.append(("list_approvals", name))
        return {"approvals": [{"approval_id": "appr_001"}]}

    def approve(self, name, approval_id):
        self.calls.append(("approve", name, approval_id))
        return {"state": {"status": "idle"}}

    def reject(self, name, approval_id, *, reason=None):
        self.calls.append(("reject", name, approval_id, reason))
        return {"state": {"status": "blocked", "blocked_reason": reason}}


def test_plugin_client_delegates_to_engine_api_client():
    api = FakeApiClient()
    client = ProjectWorkerPluginClient(api_client=api)

    assert client.list_projects() == {"projects": ["demo"]}
    assert client.show_project("demo") == {"name": "demo", "status": "idle"}
    assert client.enqueue_project("demo", "manual.nudge", {"reason": "work now"})["event"]["type"] == "manual.nudge"
    assert client.run_project("demo")["result"]["summary"] == "done"
    assert client.list_approvals("demo")["approvals"][0]["approval_id"] == "appr_001"
    assert client.approve("demo", "appr_001")["state"]["status"] == "idle"
    assert client.reject("demo", "appr_001", reason="No deploy")["state"]["blocked_reason"] == "No deploy"

    assert api.calls == [
        ("list_projects",),
        ("get_project", "demo"),
        ("enqueue_event", "demo", "manual.nudge", {"reason": "work now"}),
        ("run_project", "demo"),
        ("list_approvals", "demo"),
        ("approve", "demo", "appr_001"),
        ("reject", "demo", "appr_001", "No deploy"),
    ]
