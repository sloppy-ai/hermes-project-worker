from pathlib import Path

from hermes_project_worker.models import ProjectConfig, WorkerConfig
from hermes_project_worker.repo import derive_branch_name, get_execution_path, resolve_repo_path


def _make_config(tmp_path, *, use_worktree=True, worktree_parent=None, branch_naming="hermes/{task_slug}"):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    return ProjectConfig(
        name="demo",
        repo_path=str(repo_dir),
        mission="Test project",
        default_branch="main",
        worker=WorkerConfig(use_worktree=use_worktree),
        allowed_actions=["small_bugfixes"],
        approval_required_actions=["deploy"],
        worktree_parent=worktree_parent,
        branch_naming=branch_naming,
    )


def test_resolve_repo_path_returns_absolute_path(tmp_path):
    config = _make_config(tmp_path)

    assert resolve_repo_path(config) == (tmp_path / "repo").resolve()


def test_derive_branch_name_formats_slugified_task_slug(tmp_path):
    config = _make_config(tmp_path, branch_naming="worker/{task_slug}")

    assert derive_branch_name(config, "Fix CI on macOS!") == "worker/fix-ci-on-macos"


def test_get_execution_path_uses_worktree_parent_when_enabled(tmp_path):
    worktree_parent = tmp_path / "worktrees"
    config = _make_config(tmp_path, worktree_parent=str(worktree_parent))

    branch_name = derive_branch_name(config, "Fix CI")

    assert get_execution_path(config, branch_name) == worktree_parent / "hermes__fix-ci"


def test_get_execution_path_returns_repo_path_when_worktrees_disabled(tmp_path):
    config = _make_config(tmp_path, use_worktree=False)

    branch_name = derive_branch_name(config, "Fix CI")

    assert get_execution_path(config, branch_name) == Path(config.repo_path).resolve()
