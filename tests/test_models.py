from hermes_project_worker.models import (
    ApprovalRequest,
    ProjectConfig,
    ProjectEvent,
    ProjectState,
    RunResult,
    WorkerConfig,
)


def test_project_config_round_trip():
    config = ProjectConfig(
        name="spark-agents",
        repo_path="/Users/sloppy/dev/spark-agents",
        mission="Keep the repo healthy.",
        default_branch="main",
        worker=WorkerConfig(command="hermes", profile="default"),
        allowed_actions=["small_bugfixes", "draft_prs"],
        approval_required_actions=["deploy"],
    )

    restored = ProjectConfig.from_dict(config.to_dict())

    assert restored == config
    assert restored.worker.command == "hermes"
    assert restored.allowed_actions == ["small_bugfixes", "draft_prs"]


def test_default_project_state_values():
    state = ProjectState.default_for_project("spark-agents")

    assert state.project == "spark-agents"
    assert state.status == "idle"
    assert state.current_run_id is None
    assert state.pending_approval is None
    assert state.retry_count == 0
    assert state.policy_version == 1


def test_project_event_round_trip():
    event = ProjectEvent(
        event_id="evt_123",
        project="spark-agents",
        type="manual.nudge",
        source="manual",
        created_at="2026-04-17T23:00:00Z",
        dedupe_key="manual.spark-agents",
        payload={"reason": "test"},
        status="pending",
    )

    restored = ProjectEvent.from_dict(event.to_dict())

    assert restored == event
    assert restored.payload["reason"] == "test"


def test_run_result_preserves_approval_fields():
    result = RunResult(
        success=False,
        exit_code=2,
        status="awaiting_approval",
        summary="Needs approval",
        task_class="infra_changes",
        needs_approval=True,
        approval_reason="Infra changes require approval.",
        branch_name="hermes/fix-ci",
    )

    restored = RunResult.from_dict(result.to_dict())

    assert restored == result
    assert restored.needs_approval is True
    assert restored.approval_reason == "Infra changes require approval."


def test_approval_request_round_trip():
    approval = ApprovalRequest(
        approval_id="appr_001",
        project="spark-agents",
        task_class="deploy",
        reason="Deploys require explicit approval.",
        status="pending",
    )

    restored = ApprovalRequest.from_dict(approval.to_dict())

    assert restored == approval
    assert restored.status == "pending"
