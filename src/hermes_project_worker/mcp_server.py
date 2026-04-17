from __future__ import annotations

from .operator_client import ProjectWorkerOperatorClient


def _load_fastmcp():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - exercised via runtime use, not tests
        raise RuntimeError(
            "MCP support requires the 'mcp' package. Install it with `pip install mcp` "
            "or `pip install 'hermes-project-worker[mcp]'`."
        ) from exc
    return FastMCP


def create_mcp_server(
    *,
    client: ProjectWorkerOperatorClient | None = None,
    base_url: str | None = None,
    fastmcp_factory=None,
):
    operator = client or ProjectWorkerOperatorClient(base_url=base_url)
    factory = fastmcp_factory or _load_fastmcp()
    server = factory("Hermes Project Worker", json_response=True)

    @server.tool()
    def list_projects() -> dict:
        """List all configured project workers."""
        return operator.list_projects()

    @server.tool()
    def show_project(project: str) -> dict:
        """Show one project's current state summary."""
        return operator.show_project(project)

    @server.tool()
    def enqueue_project(project: str, event_type: str, payload: dict | None = None) -> dict:
        """Enqueue a new project event without running it immediately."""
        return operator.enqueue_project(project, event_type, payload or {})

    @server.tool()
    def run_project(project: str) -> dict:
        """Trigger one immediate project worker cycle."""
        return operator.run_project(project)

    @server.tool()
    def list_approvals(project: str) -> dict:
        """List pending approval requests for a project."""
        return operator.list_approvals(project)

    @server.tool()
    def approve(project: str, approval_id: str) -> dict:
        """Approve a pending project action."""
        return operator.approve(project, approval_id)

    @server.tool()
    def reject(project: str, approval_id: str, reason: str | None = None) -> dict:
        """Reject a pending project action."""
        return operator.reject(project, approval_id, reason=reason)

    @server.tool()
    def list_events(project: str) -> dict:
        """List persisted project events."""
        return operator.list_events(project)

    @server.tool()
    def list_runs(project: str) -> dict:
        """List persisted project runs."""
        return operator.list_runs(project)

    return server


def serve_mcp(
    *,
    client: ProjectWorkerOperatorClient | None = None,
    base_url: str | None = None,
    fastmcp_factory=None,
) -> None:
    server = create_mcp_server(client=client, base_url=base_url, fastmcp_factory=fastmcp_factory)
    server.run(transport="stdio")
