"""Stable integer progress calculations."""

from dataclasses import dataclass

from runtime.project_manager.models import ProjectManagerState, TaskStatus


@dataclass(frozen=True)
class Progress:
    total: int
    completed: int
    skipped: int
    blocked: int
    in_progress: int
    remaining: int
    percentage: int


def calculate(tasks) -> Progress:
    tasks = tuple(tasks)
    counts = {status: sum(t.status == status for t in tasks) for status in TaskStatus}
    total = len(tasks)
    complete = counts[TaskStatus.DONE]
    skipped = counts[TaskStatus.SKIPPED]
    percentage = 0 if total == 0 else ((complete + skipped) * 100) // total
    return Progress(total, complete, skipped, counts[TaskStatus.BLOCKED],
                    counts[TaskStatus.IN_PROGRESS], total - complete - skipped, percentage)


def project_progress(state: ProjectManagerState) -> Progress:
    return calculate(state.tasks)


def milestone_progress(state: ProjectManagerState, milestone_id: str) -> Progress:
    milestone = state.milestone(milestone_id)
    progress = calculate(state.task(task_id) for task_id in milestone.task_ids)
    if milestone.status.value == "COMPLETED" and progress.percentage != 100:
        return Progress(progress.total, progress.completed, progress.skipped,
                        progress.blocked, progress.in_progress, progress.remaining, 100)
    return progress
