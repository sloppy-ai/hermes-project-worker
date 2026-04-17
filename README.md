# hermes-project-worker

Standalone project orchestration engine that uses Hermes as the isolated execution backend.

Current control surfaces:
- `hpw ...` standalone CLI
- local HTTP API on `127.0.0.1:8765`
- MCP server for Hermes and other MCP-aware agents
- optional Hermes plugin wrapper

Core architecture:
- file-backed project state under `~/.hermes/projects/`
- standalone engine owns queue, approvals, manager loop, API, and webhooks
- Hermes is used as the worker runtime, not the daemon

## Development test command

```bash
source /Users/sloppy/.hermes/hermes-agent/venv/bin/activate
python -m pytest tests/ -q
```

## Local setup on macOS (Hermes dev checkout)

This is the lean local workflow for running HPW from a source checkout and exposing it to Hermes over MCP.

### 1. MCP prerequisite

The Python environment running Hermes needs the `mcp` package installed.

### 2. Hermes MCP config

Add this to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  hpw:
    command: "/path/to/python"
    args: ["-m", "hermes_project_worker", "mcp", "serve"]
    env:
      PYTHONPATH: "/absolute/path/to/hermes-project-worker/src"
      HPW_API_BASE_URL: "http://127.0.0.1:8765"
    connect_timeout: 30
    timeout: 120
```

For the current local checkout on the MBA, that resolves to:
- python: `/Users/sloppy/.hermes/hermes-agent/venv/bin/python`
- src: `/Users/sloppy/dev/hermes-project-worker/src`

Restart Hermes after changing MCP config.

### 3. Run the HPW API persistently with launchd

Generate the launch agent plist:

```bash
PYTHONPATH=/absolute/path/to/hermes-project-worker/src \
/path/to/python -m hermes_project_worker api write-launchd
```

On the current local machine that is:

```bash
PYTHONPATH=/Users/sloppy/dev/hermes-project-worker/src \
/Users/sloppy/.hermes/hermes-agent/venv/bin/python -m hermes_project_worker api write-launchd
```

That writes a plist to:

```text
~/Library/LaunchAgents/dev.nous.hermes-project-worker.api.plist
```

Load and start it:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/dev.nous.hermes-project-worker.api.plist
launchctl enable gui/$(id -u)/dev.nous.hermes-project-worker.api
launchctl kickstart -k gui/$(id -u)/dev.nous.hermes-project-worker.api
```

### 4. Verify

Check API health:

```bash
curl http://127.0.0.1:8765/health
```

Check the launch agent:

```bash
launchctl print gui/$(id -u)/dev.nous.hermes-project-worker.api
```

Expected log files:
- `~/Library/Logs/hermes-project-worker/api.stdout.log`
- `~/Library/Logs/hermes-project-worker/api.stderr.log`

### 5. Useful CLI commands

```bash
python -m hermes_project_worker --version
python -m hermes_project_worker api serve --host 127.0.0.1 --port 8765
python -m hermes_project_worker mcp serve
python -m hermes_project_worker api print-launchd
python -m hermes_project_worker api write-launchd
```

## Notes

- MCP is the agent-facing adapter, not the only control plane.
- HTTP + CLI stay as the boring operator/debug surface.
- For dev checkouts, `PYTHONPATH=/path/to/src` is the cleanest way to run HPW without packaging/installing a wheel first.
