"""Atomic schema-versioned knowledge persistence."""

import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from runtime.knowledge.errors import *
from runtime.knowledge.models import *


class KnowledgeStore:
    SCHEMA_VERSION = 1

    def __init__(self, state_root):
        self.state_root = Path(state_root)

    def path_for(self, project_id):
        return self.state_root / "knowledge" / project_id / "knowledge.json"

    def save(self, knowledge):
        path = self.path_for(knowledge.project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(knowledge)
        data["scanned_at"] = knowledge.scanned_at.isoformat()
        descriptor, temporary = tempfile.mkstemp(prefix=".knowledge.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(data, stream, sort_keys=True, indent=2)
                stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception as error:
            try: os.unlink(temporary)
            except FileNotFoundError: pass
            raise KnowledgeStorageError(f"Could not save knowledge for {knowledge.project_id!r}") from error

    def load(self, project_id):
        path = self.path_for(project_id)
        if not path.exists():
            raise KnowledgeNotFoundError(f"Knowledge for {project_id!r} has not been scanned")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("schema_version") != self.SCHEMA_VERSION:
                raise UnsupportedKnowledgeSchemaError(
                    f"Unsupported knowledge schema {data.get('schema_version')!r}")
            return _decode(data)
        except UnsupportedKnowledgeSchemaError:
            raise
        except Exception as error:
            raise KnowledgeCorruptError(f"Knowledge file {path} cannot be safely loaded") from error


def _decode(data):
    def symbol(x): return Symbol(**{**x, "decorators": tuple(x["decorators"])})
    def imp(x): return ImportReference(**{**x, "names": tuple(x["names"])})
    def file(x): return FileNode(**{**x, "symbols": tuple(symbol(v) for v in x["symbols"]),
        "imports": tuple(imp(v) for v in x["imports"]),
        "exports": tuple(ExportReference(**v) for v in x["exports"])})
    def repo(x): return RepositoryKnowledge(x["repository_id"], x["root"],
        tuple(DirectoryNode(**v) for v in x["directories"]),
        tuple(file(v) for v in x["files"]),
        tuple(DependencyEdge(**v) for v in x["dependencies"]))
    return ProjectKnowledge(data["project_id"], data["schema_version"],
                            tuple(repo(x) for x in data["repositories"]),
                            datetime.fromisoformat(data["scanned_at"]))
