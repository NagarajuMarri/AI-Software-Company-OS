"""Deterministic executable-task selection."""

from runtime.project_manager.models import ProjectManagerState, TaskStatus


def next_tasks(state: ProjectManagerState):
    if state.active_milestone_id is None:
        return ()
    milestone = state.milestone(state.active_milestone_id)
    result = []
    for task_id in milestone.task_ids:
        task = state.task(task_id)
        if task.status != TaskStatus.TODO:
            continue
        if all(state.task(dep).status in {TaskStatus.DONE, TaskStatus.SKIPPED}
               for dep in task.dependencies):
            result.append(task)
    return tuple(result)
