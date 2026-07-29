"""Bounded reviewed planning-context construction."""

from datetime import datetime, timezone

from runtime.knowledge.errors import KnowledgeNotFoundError
from runtime.planning.errors import KnowledgeStaleError, PlanningValidationError
from runtime.planning.models import ContextFile, ContextSymbol, ManagedProductPlanningContext
from runtime.project_manager.models import TaskStatus


class PlanningContextBuilder:
    def __init__(self, *, max_files=50, max_symbols=100, max_dependencies=100,
                 max_state_items=50, max_age_seconds=2_592_000):
        self.max_files, self.max_symbols = max_files, max_symbols
        self.max_dependencies, self.max_state_items = max_dependencies, max_state_items
        self.max_age_seconds = max_age_seconds
        if min(max_files, max_symbols, max_dependencies, max_state_items) < 0:
            raise PlanningValidationError("Context limits must be non-negative")

    def build(self, project, request, knowledge_engine, manager, *, now=None):
        knowledge = knowledge_engine.current()
        if knowledge.project_id != project.project_id or request.project_id != project.project_id:
            raise PlanningValidationError("Planning context project identity mismatch")
        if not knowledge.repositories:
            raise KnowledgeNotFoundError(f"Knowledge for {project.project_id!r} is missing")
        now = now or datetime.now(timezone.utc)
        if (now - knowledge.scanned_at).total_seconds() > self.max_age_seconds:
            raise KnowledgeStaleError(f"Knowledge for {project.project_id!r} is stale")
        files = []
        symbols = []
        for repository in sorted(knowledge.repositories, key=lambda x: x.repository_id):
            for item in repository.files:
                files.append(ContextFile(repository.repository_id, item.path,
                                         item.language, item.category))
                for symbol in item.symbols:
                    symbols.append(ContextSymbol(repository.repository_id, item.path,
                        symbol.name, symbol.kind, symbol.qualified_name))
        state = manager.current_state()
        if state.project_id != project.project_id:
            raise PlanningValidationError("Project manager state identity mismatch")
        stats = knowledge_engine.statistics()
        dependencies = sorted({edge.target for edge in knowledge_engine.dependencies()})
        return ManagedProductPlanningContext(
            project.project_id, project.name, project.repository_url, project.default_branch,
            request, knowledge.scanned_at, knowledge_engine.summary(),
            tuple(sorted(files, key=lambda x: (x.repository_id, x.path))[:self.max_files]),
            tuple(sorted(symbols, key=lambda x: (x.repository_id, x.path, x.qualified_name))[:self.max_symbols]),
            tuple((x.language, x.files) for x in stats.languages),
            tuple(dependencies[:self.max_dependencies]), state.status.value,
            state.active_milestone_id,
            tuple(x.task_id for x in state.tasks if x.status not in
                  {TaskStatus.DONE, TaskStatus.SKIPPED})[:self.max_state_items],
            tuple(x.title for x in state.decisions)[:self.max_state_items],
            tuple(x.title for x in state.risks)[:self.max_state_items],
            tuple(x.content for x in state.notes)[:self.max_state_items])
