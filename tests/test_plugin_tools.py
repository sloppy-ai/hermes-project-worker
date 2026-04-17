from hermes_plugin.project_worker.tools import build_tools


class FakeClient:
    def list_projects(self):
        return {"projects": ["demo", "beta"]}

    def show_project(self, name):
        return {"name": name, "status": "awaiting_approval", "pending_approval": {"approval_id": "appr_001"}}

    def enqueue_project(self, name, event_type, payload):
        return {"event": {"project": name, "type": event_type, "payload": payload}}

    def run_project(self, name):
        return {"result": {"project": name, "status": "completed", "summary": "Applied fix."}}

    def list_approvals(self, name):
        return {"approvals": [{"approval_id": "appr_001", "project": name}]}

    def approve(self, name, approval_id):
        return {"state": {"project": name, "status": "idle", "last_approval_id": approval_id}}

    def reject(self, name, approval_id, *, reason=None):
        return {"state": {"project": name, "status": "blocked", "last_approval_id": approval_id, "blocked_reason": reason}}


def test_tools_call_client_and_return_json_payloads():
    tools = build_tools(FakeClient())

    assert tools["project_worker_list"]() == {"projects": ["demo", "beta"]}
    assert tools["project_worker_show"]("demo")["status"] == "awaiting_approval"
    assert tools["project_worker_enqueue"]("demo", "manual.nudge", {"reason": "work now"})["event"]["type"] == "manual.nudge"
    assert tools["project_worker_run"]("demo")["result"]["summary"] == "Applied fix."
    assert tools["project_worker_approvals"]("demo")["approvals"][0]["approval_id"] == "appr_001"
    assert tools["project_worker_approve"]("demo", "appr_001")["state"]["status"] == "idle"
    assert tools["project_worker_reject"]("demo", "appr_001", "No deploy")["state"]["blocked_reason"] == "No deploy"
