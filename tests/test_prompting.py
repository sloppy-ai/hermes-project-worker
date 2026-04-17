from hermes_project_worker.models import ProjectConfig, ProjectEvent, ProjectState, WorkerConfig
from hermes_project_worker.prompting import build_worker_prompt


def test_prompt_contains_required_sections():
    config = ProjectConfig(
        name="spark-agents",
        repo_path="/Users/sloppy/dev/spark-agents",
        mission="Keep the repo healthy.",
        default_branch="main",
        worker=WorkerConfig(command="hermes", profile="default"),
        allowed_actions=["small_bugfixes", "draft_prs"],
        approval_required_actions=["deploy"],
    )
    state = ProjectState.default_for_project("spark-agents")
    events = [
        ProjectEvent(
            event_id="evt_001",
            project="spark-agents",
            type="manual.nudge",
            source="manual",
            created_at="2026-04-17T23:00:00Z",
            payload={"reason": "triage CI failures"},
        )
    ]

    prompt = build_worker_prompt(
        config=config,
        state=state,
        events=events,
        repo_path=config.repo_path,
        worktree_path="/tmp/worktree/spark-agents",
    )

    assert "Mission" in prompt
    assert "Project summary" in prompt
    assert "Current state" in prompt
    assert "Claimed events" in prompt
    assert "Allowed actions" in prompt
    assert "Approval-required and forbidden actions" in prompt
    assert "Repo/worktree path" in prompt
    assert "Validation commands" in prompt
    assert "Output contract" in prompt
    assert "Termination rules" in prompt
    assert "triage CI failures" in prompt
    assert "--- PROJECT_WORKER_RESULT ---" in prompt
