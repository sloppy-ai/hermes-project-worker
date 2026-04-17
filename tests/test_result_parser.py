import pytest

from hermes_project_worker.result_parser import parse_worker_result


VALID_OUTPUT = """Did the thing.

--- PROJECT_WORKER_RESULT ---
status: completed
task_class: small_bugfixes
summary: Fixed the import path and ran tests.
branch_name: hermes/fix-import-path
pr_url:
needs_approval: false
approval_reason:
followup_event:
  type: manual.review_ready
  payload:
    reason: draft pr recommended
"""


def test_parser_accepts_valid_footer():
    result = parse_worker_result(VALID_OUTPUT)

    assert result.success is True
    assert result.status == "completed"
    assert result.task_class == "small_bugfixes"
    assert result.summary == "Fixed the import path and ran tests."
    assert result.branch_name == "hermes/fix-import-path"
    assert result.followup_event == {
        "type": "manual.review_ready",
        "payload": {"reason": "draft pr recommended"},
    }


def test_parser_rejects_missing_footer():
    with pytest.raises(ValueError, match="footer"):
        parse_worker_result("No structured result here")


def test_parser_rejects_malformed_footer():
    broken = """Summary\n\n--- PROJECT_WORKER_RESULT ---\nstatus completed\nsummary oops\n"""

    with pytest.raises(ValueError, match="malformed"):
        parse_worker_result(broken)


def test_parser_preserves_approval_fields():
    output = """Need approval.\n\n--- PROJECT_WORKER_RESULT ---\nstatus: awaiting_approval\ntask_class: infra_changes\nsummary: Needs approval before infra changes.\nneeds_approval: true\napproval_reason: infra changes require approval\n"""

    result = parse_worker_result(output)

    assert result.success is False
    assert result.needs_approval is True
    assert result.approval_reason == "infra changes require approval"
