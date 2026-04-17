from hermes_project_worker.approvals import (
    approve_pending_approval,
    create_approval_request,
    reject_pending_approval,
    set_pending_approval,
)
from hermes_project_worker.models import ProjectConfig, WorkerConfig
from hermes_project_worker.store import init_project, load_project_state, save_project_state


def _make_config(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    return ProjectConfig(
        name="demo",
        repo_path=str(repo_dir),
        mission="Test project",
        default_branch="main",
        worker=WorkerConfig(use_worktree=False),
        allowed_actions=["small_bugfixes"],
        approval_required_actions=["deploy"],
    )


def test_set_pending_approval_populates_state(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))
    state = load_project_state("demo")

    approval = create_approval_request(project="demo", task_class="deploy", reason="Deploy requires approval.")
    updated = set_pending_approval(state, approval)
    save_project_state(updated)

    restored = load_project_state("demo")

    assert restored.status == "awaiting_approval"
    assert restored.last_approval_id == approval.approval_id
    assert restored.pending_approval == approval.to_dict()
    assert restored.blocked_reason == "Deploy requires approval."


def test_approve_pending_approval_clears_pending_state(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))
    state = load_project_state("demo")
    approval = create_approval_request(project="demo", task_class="deploy", reason="Deploy requires approval.")
    save_project_state(set_pending_approval(state, approval))

    approve_pending_approval("demo", approval.approval_id)

    restored = load_project_state("demo")

    assert restored.status == "idle"
    assert restored.pending_approval is None
    assert restored.last_approval_id == approval.approval_id
    assert restored.blocked_reason is None


def test_reject_pending_approval_blocks_project_with_reason(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setenv("HPW_PROJECTS_DIR", str(projects_dir))
    init_project(_make_config(tmp_path))
    state = load_project_state("demo")
    approval = create_approval_request(project="demo", task_class="deploy", reason="Deploy requires approval.")
    save_project_state(set_pending_approval(state, approval))

    reject_pending_approval("demo", approval.approval_id, reason="Rejected by operator.")

    restored = load_project_state("demo")

    assert restored.status == "blocked"
    assert restored.pending_approval is None
    assert restored.last_approval_id == approval.approval_id
    assert restored.blocked_reason == "Rejected by operator."
