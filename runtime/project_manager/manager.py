"""Public deterministic AI Project Manager façade."""

from dataclasses import replace

from runtime.project_manager.errors import *
from runtime.project_manager.models import *
from runtime.project_manager.planner import next_tasks as plan_next
from runtime.project_manager.progress import milestone_progress, project_progress


class AIProjectManager:
    def __init__(self, registry, store, state):
        registry.get(state.project_id)
        self.registry, self.store, self._state = registry, store, state

    @classmethod
    def initialize(cls, project_id, registry, store, *, metadata=None):
        registry.get(project_id)
        if store.exists(project_id):
            raise ProjectManagerError(f"Manager state for {project_id!r} already exists")
        return cls(registry, store, ProjectManagerState(project_id, metadata=metadata or {}))

    @classmethod
    def load(cls, project_id, registry, store):
        registry.get(project_id)
        return cls(registry, store, store.load(project_id))

    def current_state(self): return self._state
    def progress(self): return project_progress(self._state)
    def milestone_progress(self, milestone_id): return milestone_progress(self._state, milestone_id)
    def next_tasks(self): return plan_next(self._state)
    def save(self): self.store.save(self._state)

    def create_milestone(self, milestone_id, title, *, goal=None, dependencies=(), metadata=None):
        if any(x.milestone_id == milestone_id for x in self._state.milestones):
            raise DuplicateMilestoneError(f"Milestone {milestone_id!r} already exists")
        for dependency in dependencies:
            if not any(x.milestone_id == dependency for x in self._state.milestones):
                raise UnknownDependencyError(f"Milestone dependency {dependency!r} does not exist")
        now = utc_now()
        item = Milestone(milestone_id, title, goal, dependencies=tuple(dependencies),
                         created_at=now, updated_at=now, metadata=metadata or {})
        self._state = replace(self._state, milestones=self._state.milestones + (item,), updated_at=now)
        return item

    def start_milestone(self, milestone_id):
        item = self._state.milestone(milestone_id)
        if item.status != MilestoneStatus.NOT_STARTED or self._state.active_milestone_id is not None:
            raise InvalidMilestoneTransitionError(f"Milestone {milestone_id!r} cannot be started")
        for dependency in item.dependencies:
            if self._state.milestone(dependency).status != MilestoneStatus.COMPLETED:
                raise InvalidMilestoneTransitionError(f"Milestone dependency {dependency!r} is incomplete")
        now = utc_now()
        updated = replace(item, status=MilestoneStatus.ACTIVE, started_at=now, updated_at=now)
        self._replace_milestone(updated, now, active=milestone_id,
                                project_status=ProjectManagementStatus.ACTIVE)
        return updated

    def complete_milestone(self, milestone_id):
        item = self._state.milestone(milestone_id)
        if item.status not in {MilestoneStatus.ACTIVE, MilestoneStatus.BLOCKED}:
            raise InvalidMilestoneTransitionError(f"Milestone {milestone_id!r} is not active")
        incomplete = [x for x in item.task_ids if self._state.task(x).status not in
                      {TaskStatus.DONE, TaskStatus.SKIPPED}]
        if incomplete:
            raise IncompleteMilestoneError(f"Milestone {milestone_id!r} has incomplete tasks: {incomplete}")
        now = utc_now()
        updated = replace(item, status=MilestoneStatus.COMPLETED, completed_at=now, updated_at=now)
        self._replace_milestone(updated, now, active=None)
        return updated

    def create_task(self, milestone_id, task_id, title, *, description=None, dependencies=(),
                    owner=None, estimated_effort=None, metadata=None):
        milestone = self._state.milestone(milestone_id)
        if any(x.task_id == task_id for x in self._state.tasks):
            raise DuplicateTaskError(f"Task {task_id!r} already exists")
        for dependency in dependencies:
            if not any(x.task_id == dependency for x in self._state.tasks):
                raise UnknownDependencyError(f"Task dependency {dependency!r} does not exist")
        now = utc_now()
        task = Task(task_id, title, description, dependencies=tuple(dependencies), owner=owner,
                    estimated_effort=estimated_effort, created_at=now, updated_at=now,
                    metadata=metadata or {})
        updated_milestone = replace(milestone, task_ids=milestone.task_ids + (task_id,), updated_at=now)
        milestones = tuple(updated_milestone if x.milestone_id == milestone_id else x
                           for x in self._state.milestones)
        self._state = replace(self._state, tasks=self._state.tasks + (task,),
                              milestones=milestones, updated_at=now)
        return task

    def start_task(self, task_id):
        task = self._state.task(task_id)
        if task.status != TaskStatus.TODO:
            raise InvalidTaskTransitionError(f"Task {task_id!r} cannot be started from {task.status.value}")
        self._require_dependencies(task)
        return self._transition(task, TaskStatus.IN_PROGRESS, started=True)

    def complete_task(self, task_id, *, actual_effort=None):
        task = self._state.task(task_id)
        if task.status not in {TaskStatus.TODO, TaskStatus.IN_PROGRESS}:
            raise InvalidTaskTransitionError(f"Task {task_id!r} cannot be completed from {task.status.value}")
        self._require_dependencies(task)
        return self._transition(task, TaskStatus.DONE, completed=True, actual_effort=actual_effort)

    def block_task(self, task_id, reason):
        if not isinstance(reason, str) or not reason.strip():
            raise ValidationError("A blocker reason is required")
        task = self._state.task(task_id)
        if task.status not in {TaskStatus.TODO, TaskStatus.IN_PROGRESS}:
            raise InvalidTaskTransitionError(f"Task {task_id!r} cannot be blocked")
        return self._transition(task, TaskStatus.BLOCKED, blocker_reason=reason)

    def unblock_task(self, task_id):
        task = self._state.task(task_id)
        if task.status != TaskStatus.BLOCKED:
            raise InvalidTaskTransitionError(f"Task {task_id!r} is not blocked")
        target = TaskStatus.IN_PROGRESS if task.started_at else TaskStatus.TODO
        return self._transition(task, target, blocker_reason=None)

    def skip_task(self, task_id):
        task = self._state.task(task_id)
        if task.status != TaskStatus.TODO:
            raise InvalidTaskTransitionError(f"Task {task_id!r} cannot be skipped")
        return self._transition(task, TaskStatus.SKIPPED, completed=True)

    def add_decision(self, decision_id, title, rationale, **kwargs):
        return self._append_record("decisions", Decision(decision_id, title, rationale, **kwargs), "decision_id")

    def add_note(self, note_id, content, **kwargs):
        return self._append_record("notes", Note(note_id, content, **kwargs), "note_id")

    def add_risk(self, risk_id, title, description, severity, **kwargs):
        return self._append_record("risks", Risk(risk_id, title, description, severity, **kwargs), "risk_id")

    def update_risk(self, risk_id, *, status=None, mitigation=None, severity=None):
        try: old = next(x for x in self._state.risks if x.risk_id == risk_id)
        except StopIteration as error: raise ProjectManagerError(f"Risk {risk_id!r} does not exist") from error
        updated = replace(old, status=status or old.status, severity=severity or old.severity,
                          mitigation=mitigation if mitigation is not None else old.mitigation)
        now = utc_now()
        self._state = replace(self._state, risks=tuple(updated if x.risk_id == risk_id else x
                                                       for x in self._state.risks), updated_at=now)
        return updated

    def _require_dependencies(self, task):
        missing = [x for x in task.dependencies if self._state.task(x).status not in
                   {TaskStatus.DONE, TaskStatus.SKIPPED}]
        if missing: raise UnmetTaskDependenciesError(f"Task {task.task_id!r} has incomplete dependencies: {missing}")

    def _transition(self, task, status, *, started=False, completed=False, **changes):
        now = utc_now()
        updated = replace(task, status=status, updated_at=now,
                          started_at=now if started and task.started_at is None else task.started_at,
                          completed_at=now if completed else task.completed_at, **changes)
        self._state = self._state.with_task(updated, now)
        return updated

    def _replace_milestone(self, item, now, active=None, project_status=None):
        self._state = replace(self._state,
            milestones=tuple(item if x.milestone_id == item.milestone_id else x for x in self._state.milestones),
            active_milestone_id=active, status=project_status or self._state.status, updated_at=now)

    def _append_record(self, collection, record, id_field):
        values = getattr(self._state, collection)
        if any(getattr(x, id_field) == getattr(record, id_field) for x in values):
            raise ProjectManagerError(f"Duplicate {collection[:-1]} ID {getattr(record, id_field)!r}")
        self._state = replace(self._state, **{collection: values + (record,), "updated_at": utc_now()})
        return record
