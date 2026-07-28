from datetime import datetime, timezone

from runtime.tasks.exceptions import ApprovalPolicyError
from runtime.tasks.models import ApprovalDecision, ApprovalStatus


def decision(task_id, status, approver_id, reason=""):
    if not isinstance(approver_id, str) or not approver_id.strip():
        raise ApprovalPolicyError("Approver identity is required")
    if status in {ApprovalStatus.REJECTED, ApprovalStatus.CHANGES_REQUESTED} and (
        not isinstance(reason, str) or not reason.strip()
    ):
        raise ApprovalPolicyError("A reason is required")
    return ApprovalDecision(
        task_id, status, approver_id, reason, datetime.now(timezone.utc)
    )
