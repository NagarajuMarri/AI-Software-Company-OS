"""Scan and reload an isolated sample repository."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.knowledge import KnowledgeStore, ProjectKnowledgeEngine
from runtime.projects import InMemoryProjectRegistry, ManagedProject


def main():
    with TemporaryDirectory() as directory:
        root = Path(directory) / "product"; root.mkdir()
        (root / "app.py").write_text("import json\n\ndef main():\n    return json.dumps({})\n",
                                     encoding="utf-8")
        registry = InMemoryProjectRegistry((ManagedProject(
            "sample", "Sample", "Isolated knowledge example",
            "https://example.com/sample", "main", local_path=str(root)),))
        store = KnowledgeStore(Path(directory) / "state")
        engine = ProjectKnowledgeEngine.create("sample", registry, store)
        engine.scan()
        print("statistics:", engine.statistics())
        print("symbol:", engine.find_symbol("main")[0].qualified_name)
        print("dependency:", engine.dependencies()[0].target)
        engine.save()
        print("reloaded:", ProjectKnowledgeEngine.load("sample", registry, store).summary())


if __name__ == "__main__":
    main()
