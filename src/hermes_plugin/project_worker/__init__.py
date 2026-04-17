from __future__ import annotations

from .client import ProjectWorkerPluginClient
from .commands import build_commands
from .tools import build_tools



def register(ctx, *, client: ProjectWorkerPluginClient | None = None, base_url: str | None = None) -> None:
    plugin_client = client or ProjectWorkerPluginClient(base_url=base_url)

    for name, func in build_tools(plugin_client).items():
        ctx.register_tool(name, func, description=f"Project Worker tool: {name}")

    for name, func in build_commands(plugin_client).items():
        ctx.register_command(name, func, description=f"Project Worker command: {name}")
