"""Strict proposal validation and safety gates."""

import re
from pathlib import PurePath, PurePosixPath, PureWindowsPath

from runtime.planning.errors import PlanningValidationError

IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
FORBIDDEN_GATE = re.compile(r"\b(merge|deploy|release|git\s+push|gh\s+pr\s+merge)\b", re.I)


def validate_proposal(proposal, context):
    if proposal.project_id != context.project_id or proposal.request_id != context.request.request_id:
        raise PlanningValidationError("Proposal project or request identity mismatch")
    if not proposal.tasks:
        raise PlanningValidationError("Proposal must contain at least one task")
    identifiers = [x.task_id for x in proposal.tasks]
    if len(identifiers) != len(set(identifiers)):
        raise PlanningValidationError("Proposal task IDs must be unique")
    known = set(identifiers)
    seen = set()
    safe_files = {(x.repository_id, x.path) for x in context.relevant_files}
    known_paths = {path for _, path in safe_files}
    for task in proposal.tasks:
        if not IDENTIFIER.fullmatch(task.task_id):
            raise PlanningValidationError(f"Invalid task ID {task.task_id!r}")
        if not task.title.strip() or not task.description.strip():
            raise PlanningValidationError(f"Task {task.task_id!r} is empty")
        if not task.acceptance_criteria:
            raise PlanningValidationError(f"Task {task.task_id!r} has no acceptance criteria")
        if task.task_id in task.dependencies:
            raise PlanningValidationError(f"Task {task.task_id!r} depends on itself")
        missing = set(task.dependencies) - known
        if missing:
            raise PlanningValidationError(f"Task {task.task_id!r} has missing dependencies: {sorted(missing)}")
        forward = set(task.dependencies) - seen
        if forward:
            raise PlanningValidationError(
                f"Task {task.task_id!r} dependencies are not in deterministic order: {sorted(forward)}")
        for value in task.role_requirements + task.capability_requirements:
            if not IDENTIFIER.fullmatch(value):
                raise PlanningValidationError(f"Invalid role or capability identifier {value!r}")
        for path in task.candidate_files:
            _safe_path(path)
            if path not in known_paths:
                raise PlanningValidationError(f"Candidate file {path!r} is outside reviewed knowledge")
        for gate in task.quality_gates:
            _gate(gate)
        seen.add(task.task_id)
    for path in proposal.candidate_impacted_files:
        _safe_path(path)
        if path not in known_paths:
            raise PlanningValidationError(f"Candidate file {path!r} is outside reviewed knowledge")
    for gate in proposal.quality_gates:
        _gate(gate)
    _acyclic(proposal.tasks)
    return proposal


def _safe_path(value):
    if not isinstance(value, str) or not value.strip():
        raise PlanningValidationError("Candidate file path must be non-empty")
    if PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute():
        raise PlanningValidationError(f"Absolute candidate path {value!r} is unsafe")
    if ".." in PurePath(value.replace("\\", "/")).parts:
        raise PlanningValidationError(f"Traversal candidate path {value!r} is unsafe")


def _gate(value):
    if not isinstance(value, str) or not value.strip():
        raise PlanningValidationError("Quality gate command must be non-empty")
    if FORBIDDEN_GATE.search(value):
        raise PlanningValidationError(f"Quality gate {value!r} contains forbidden automation")


def _acyclic(tasks):
    graph = {x.task_id: x.dependencies for x in tasks}
    visiting, visited = set(), set()
    def visit(node):
        if node in visiting:
            raise PlanningValidationError("Proposal task dependencies contain a cycle")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node); visited.add(node)
    for node in graph:
        visit(node)
