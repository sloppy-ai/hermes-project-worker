from hermes_project_worker.models import ProjectConfig, WorkerConfig
from hermes_project_worker.policy import (
    ACTION_ALLOWED,
    ACTION_APPROVAL_REQUIRED,
    ACTION_FORBIDDEN,
    classify_task_action,
    validate_task_action,
)


def _project_config() -> ProjectConfig:
    return ProjectConfig(
        name="spark-agents",
        repo_path="/Users/sloppy/dev/spark-agents",
        mission="Keep the repo healthy.",
        default_branch="main",
        worker=WorkerConfig(command="hermes", profile="default"),
        allowed_actions=["small_bugfixes", "draft_prs"],
        approval_required_actions=["deploy", "infra_changes"],
    )


def test_allowed_action_is_allowed():
    config = _project_config()

    assert classify_task_action("small_bugfixes", config) == ACTION_ALLOWED
    assert validate_task_action("small_bugfixes", config) is True


def test_approval_required_action_is_flagged():
    config = _project_config()

    assert classify_task_action("deploy", config) == ACTION_APPROVAL_REQUIRED
    assert validate_task_action("deploy", config) is False


def test_unknown_action_is_forbidden():
    config = _project_config()

    assert classify_task_action("mystery_action", config) == ACTION_FORBIDDEN
    assert validate_task_action("mystery_action", config) is False
