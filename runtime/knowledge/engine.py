"""Public Project Knowledge Engine and deterministic query API."""

from pathlib import Path

from runtime.knowledge.errors import RepositoryUnavailableError
from runtime.knowledge.models import *
from runtime.knowledge.scanner import RepositoryScanner


class ProjectKnowledgeEngine:
    def __init__(self, project, store, knowledge=None, scanner=None):
        self.project, self.store = project, store
        self._knowledge = knowledge or ProjectKnowledge(project.project_id)
        self.scanner = scanner or RepositoryScanner()

    @classmethod
    def load(cls, project_id, registry, store):
        project = registry.get(project_id)
        return cls(project, store, store.load(project_id))

    @classmethod
    def create(cls, project_id, registry, store):
        return cls(registry.get(project_id), store)

    def scan(self, repositories=None):
        if repositories is None:
            if not self.project.local_path:
                raise RepositoryUnavailableError(
                    f"Project {self.project.project_id!r} has no available local repository")
            repositories = ((self.project.project_id, self.project.local_path),)
        scanned = []
        for repository_id, root in repositories:
            if not Path(root).is_dir():
                raise RepositoryUnavailableError(f"Repository path {str(root)!r} is unavailable")
            scanned.append(self.scanner.scan(repository_id, root))
        self._knowledge = ProjectKnowledge(self.project.project_id,
                                           repositories=tuple(sorted(scanned, key=lambda x: x.repository_id)))
        return self._knowledge

    def save(self): self.store.save(self._knowledge)
    def current(self): return self._knowledge
    def repositories(self): return self._knowledge.repositories
    def files(self): return tuple(f for r in self.repositories() for f in r.files)
    def modules(self): return tuple(f for f in self.files() if f.module is not None)
    def classes(self): return self._symbols("class")
    def functions(self): return tuple(x for x in self.symbols() if x.kind in {"function", "method"})
    def symbols(self): return tuple(s for f in self.files() for s in f.symbols)
    def dependencies(self): return tuple(d for r in self.repositories() for d in r.dependencies)
    def languages(self): return self.statistics().languages

    def find_file(self, path):
        return tuple(x for x in self.files() if x.path == path or x.name == path)

    def find_symbol(self, name):
        return tuple(x for x in self.symbols() if x.name == name or x.qualified_name == name)

    def find_imports(self, module):
        return tuple(x for x in self.dependencies() if x.source == module or x.target == module)

    def find_dependents(self, module):
        return tuple(x.source for x in self.dependencies() if x.target == module)

    def statistics(self):
        files, symbols = self.files(), self.symbols()
        languages = tuple(LanguageStatistics(language,
            sum(x.language == language for x in files),
            sum(x.lines for x in files if x.language == language))
            for language in sorted({x.language for x in files}))
        largest = tuple(x.path for x in sorted(files, key=lambda x: (-x.size, x.path))[:10])
        return RepositoryStatistics(len(self.repositories()),
            sum(len(x.directories) for x in self.repositories()), len(files), len(symbols),
            sum(x.kind == "class" for x in symbols),
            sum(x.kind in {"function", "method"} for x in symbols),
            len(self.dependencies()), sum(x.category == "test" for x in files),
            sum(x.category == "documentation" for x in files),
            sum(x.category == "configuration" for x in files), languages, largest)

    def summary(self):
        stats = self.statistics()
        return {"project_id": self.project.project_id, "repositories": stats.repositories,
                "files": stats.files, "symbols": stats.symbols,
                "dependencies": stats.dependencies,
                "languages": {x.language: x.files for x in stats.languages}}

    def _symbols(self, kind):
        return tuple(x for x in self.symbols() if x.kind == kind)
