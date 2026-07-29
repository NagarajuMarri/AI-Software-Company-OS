"""Create, plan, persist, and reload isolated sample project state."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.project_manager import AIProjectManager, ManagerStateStore
from runtime.projects import InMemoryProjectRegistry, ManagedProject


def main() -> None:
    registry = InMemoryProjectRegistry((ManagedProject(
        "sample-product", "Sample Product", "Non-authoritative example",
        "https://example.com/sample-product", "main"),))
    with TemporaryDirectory() as directory:
        store = ManagerStateStore(directory)
        manager = AIProjectManager.initialize("sample-product", registry, store)
        manager.create_milestone("sample-foundation", "Sample foundation")
        manager.create_task("sample-foundation", "inspect", "Inspect project structure")
        manager.create_task("sample-foundation", "design", "Define architecture",
                            dependencies=("inspect",))
        manager.start_milestone("sample-foundation")
        print("next:", [task.task_id for task in manager.next_tasks()])
        manager.complete_task("inspect")
        print("unlocked:", [task.task_id for task in manager.next_tasks()])
        print("progress:", manager.progress().percentage)
        manager.save()
        print("reloaded:", AIProjectManager.load("sample-product", registry, store).current_state().project_id)


if __name__ == "__main__":
    main()
