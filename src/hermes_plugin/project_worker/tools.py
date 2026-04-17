from __future__ import annotations

from .client import ProjectWorkerPluginClient



def build_tools(client: ProjectWorkerPluginClient) -> dict[str, callable]:
    return {
        "project_worker_list": lambda: client.list_projects(),
        "project_worker_show": lambda project: client.show_project(project),
        "project_worker_enqueue": lambda project, event_type, payload=None: client.enqueue_project(project, event_type, payload or {}),
        "project_worker_run": lambda project: client.run_project(project),
        "project_worker_approvals": lambda project: client.list_approvals(project),
        "project_worker_approve": lambda project, approval_id: client.approve(project, approval_id),
        "project_worker_reject": lambda project, approval_id, reason=None: client.reject(project, approval_id, reason=reason),
    }
