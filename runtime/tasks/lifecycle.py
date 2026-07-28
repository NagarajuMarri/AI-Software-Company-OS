from runtime.tasks.models import ExternalTaskStatus

ALLOWED_TRANSITIONS = {
    ExternalTaskStatus.CREATED: {ExternalTaskStatus.QUEUED, ExternalTaskStatus.CANCELLED},
    ExternalTaskStatus.QUEUED: {ExternalTaskStatus.RUNNING, ExternalTaskStatus.CANCELLED},
    ExternalTaskStatus.RUNNING: {
        ExternalTaskStatus.WAITING_FOR_REVIEW, ExternalTaskStatus.FAILED,
        ExternalTaskStatus.CANCELLED, ExternalTaskStatus.RECONCILIATION_REQUIRED,
    },
    ExternalTaskStatus.WAITING_FOR_REVIEW: {
        ExternalTaskStatus.APPROVED, ExternalTaskStatus.REJECTED,
        ExternalTaskStatus.CHANGES_REQUESTED,
    },
    ExternalTaskStatus.CHANGES_REQUESTED: {ExternalTaskStatus.QUEUED, ExternalTaskStatus.CANCELLED},
    ExternalTaskStatus.APPROVED: {ExternalTaskStatus.COMPLETED},
    ExternalTaskStatus.FAILED: {ExternalTaskStatus.QUEUED, ExternalTaskStatus.CANCELLED},
    ExternalTaskStatus.RECONCILIATION_REQUIRED: {
        ExternalTaskStatus.RUNNING, ExternalTaskStatus.FAILED,
        ExternalTaskStatus.WAITING_FOR_REVIEW,
    },
}
